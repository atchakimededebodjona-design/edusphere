# PHASE 13 DISCOVERY REPORT

Date : 2026-09-04
Nature de cette phase : Discovery uniquement. Aucun code de production modifié. Seule
modification : ce document.

## 1. Executive Summary

Après 12 phases, EduSphere couvre une boucle académique complète et fonctionnelle (inscription
→ présence → notes → bulletin → email parent) avec une isolation tenant globalement saine
(confirmé par un audit de sécurité dédié cette fois-ci, pas seulement supposé). Mais cet audit a
mis au jour deux failles réelles, jusqu'ici non détectées dans les 12 phases précédentes :

- **une vulnérabilité HIGH de traversée de chemin** dans l'upload de fichiers (photo élève,
  document, logo école) — un utilisateur disposant de `students.manage` (y compris le rôle
  `STAFF`) peut écrire un fichier en dehors du répertoire de stockage prévu en choisissant un nom
  de fichier contenant `../`, car le nom original n'est jamais assaini avant d'être intégré au
  chemin ;
- **un canal de fuite temporelle (timing side-channel)** sur `/auth/login` et
  `/auth/forgot-password` qui permet de déduire si un email existe, en contradiction directe avec
  l'objectif anti-énumération déjà documenté dans le code lui-même.

Ces deux constats, combinés à des lacunes déjà connues mais reclassées ici avec plus de
précision (gestion incohérente d'`IntegrityError`, absence de rate limiting sur `/register`,
`/refresh` et la vérification publique de bulletin), font que **le meilleur investissement pour
Phase 13 est un round de durcissement sécurité ciblé**, et non une nouvelle fonctionnalité, ni le
chantier Git/CI, ni l'observabilité — ces deux derniers restent réels et documentés, mais aucun
n'a produit de preuve d'un risque aussi concret et immédiatement exploitable que la traversée de
chemin.

## 2. État réel après Phase 12

- Phase 12 (Mobile App Resilience Hardening) a corrigé la gestion d'erreur réseau sur les 11
  écrans mobiles, sans toucher au backend, au web, ni à la base de données — confirmé par
  relecture du rapport et du code : `apps/mobile` seul a changé.
- Aucun changement de schéma depuis la migration `0008` (Phase 7).
- Le dépôt reste sans Git initialisé : `Test-Path ".git"` renvoie `False`, et la commande `git`
  elle-même est absente de cet hôte (`git : Le terme «git» n'est pas reconnu...`) — donc même un
  `git init` local ne serait pas exécutable dans get environnement sans installer l'outil au
  préalable. Confirmé à l'instant, pas supposé.
- `docker compose ps` confirme 4 conteneurs actifs (db, redis, api, web) ; `db` et `redis`
  rapportent `(healthy)` (ils ont un healthcheck Compose) ; `api` et `web` ne rapportent **aucun**
  statut de santé — `docker inspect` renvoie littéralement `map has no entry for key "Health"`,
  preuve directe qu'aucun healthcheck n'est défini pour ces deux services, pas seulement qu'il
  est actuellement vert.

## 3. Boucle métier actuellement couverte

Inchangée depuis la Phase 12 Discovery (aucune fonctionnalité ajoutée depuis) : bootstrap
organisation/école → onboarding (wizard 7 étapes) → configuration académique → inscription
élèves/tuteurs (+ import) → présence (web + mobile, écriture) → notes (web + mobile, écriture)
→ génération et publication de bulletins PDF → email au tuteur à la publication → consultation
parent (mobile, lecture seule, y compris PDF). Dashboard admin à 4 métriques. Cette boucle reste
correcte et testée ; ce qui a changé cette fois, c'est la profondeur de l'audit de sécurité qui
la traverse (voir §8), pas la boucle elle-même.

## 4. Gaps identifiés

| Gap | Type | Sévérité | Impact pilote | Complexité |
|---|---|---|---|---|
| Traversée de chemin via nom de fichier non assaini (upload photo/document/logo) | Security | HIGH | Un compte STAFF/admin compromis ou malveillant peut écrire des fichiers hors du répertoire de stockage | Faible |
| Canal de fuite temporelle sur login/forgot-password (énumération de compte par latence) | Security | HIGH | Un attaquant peut déduire quels emails existent malgré la réponse générique | Faible |
| Pas de détection de réutilisation de refresh token / pas de révocation en cascade | Security | MEDIUM | Un token de refresh volé n'est pas détecté comme tel, seulement rejeté au second usage légitime | Moyenne |
| `IntegrityError` non interceptée sur 6 endpoints de création (500 au lieu de 409) | Reliability | MEDIUM | Erreurs 500 opaques pour l'utilisateur sur des cas prévisibles (doublon, concurrence) | Faible |
| Pas de rate limiting sur `/register`, `/refresh`, `/report-cards/verify/{code}` | Security | MEDIUM | Énumération/abus non throttlé (mitigé par l'entropie des tokens pour `/verify`) | Faible |
| `organizations` sans politique RLS | Security | MEDIUM | Défense en profondeur absente ; aucun contournement exploitable trouvé (couche applicative saine) | Moyenne |
| Notes modifiables sans garde-fou après publication d'un bulletin déjà envoyé | Data integrity | MEDIUM | Désynchronisation silencieuse entre bulletin/email envoyés et notes réelles | Moyenne |
| Aucune CI réellement exécutée depuis la Phase 0 (pas de dépôt Git, `git` absent de l'hôte) | Infrastructure | MEDIUM | Aucun filet de sécurité automatisé sur 13 phases de changements | Moyenne (technique) / dépend d'une décision (compte/remote) |
| Zéro observabilité : pas de logs structurés, pas de suivi d'erreurs, `/health` ne vérifie ni DB ni Redis, `api`/`web` sans healthcheck Docker | Observability | MEDIUM | Un incident réel serait invisible jusqu'à ce qu'un utilisateur se plaigne | Moyenne |
| Publication de bulletin non groupée, résultat d'envoi d'email invisible dans l'UI | UX | LOW | Confort admin, pas un défaut actif | Faible |
| Cycle de vie utilisateur incomplet (pas de désactivation/édition) | Feature | LOW | Contournable manuellement en pilote à faible effectif | Faible-Moyenne |
| Sauvegarde purement manuelle, sans planification | Reliability | LOW (déjà documenté, inchangé) | Risque en cas d'oubli humain | Faible |

## 5. Risques résiduels

**HIGH**
- Traversée de chemin dans l'upload de fichiers (H1, §8).
- Canal de fuite temporelle login/forgot-password (H2, §8).

**MEDIUM**
- Absence de détection de réutilisation de refresh token (M3).
- Sessions révoquées restent utilisables jusqu'à 15 min via un access token déjà émis (M4 —
  compromis JWT sans état, acceptable mais à documenter, pas à considérer comme "réglé par
  logout").
- `IntegrityError` non gérée sur 6 endpoints (M2).
- Pas de rate limiting sur `/register`, `/refresh`, `/verify/{code}` (M5, M6).
- `organizations` sans RLS (M1 — aucun contournement trouvé, mais deuxième ligne de défense
  absente).
- Notes modifiables après publication sans garde-fou (Candidat D).
- CI jamais exécutée réellement (dépôt Git inexistant, `git` absent de l'hôte).
- Observabilité nulle (logs non structurés, `/health` non représentatif, pas de healthcheck
  Docker sur api/web).

**LOW**
- Emails loggés en clair sur échec d'envoi (L1 — PII mineure, pas de secret).
- `rbac` : `GET /roles`/`GET /permissions` toujours non protégés par permission (L2).
- Pas de plafond absolu de durée de session (rolling refresh 30 jours, L3).
- Publication de bulletin non groupée, UX cycle de vie utilisateur incomplet, sauvegarde
  manuelle.

## 6. État Git / CI

Constat réel, rien de supposé :
- `Test-Path ".git"` → `False`. Aucun dépôt Git à la racine du projet.
- La commande `git` elle-même échoue (`CommandNotFoundException`) sur cet hôte — l'outil n'est
  pas installé, pas seulement non initialisé.
- `.github/workflows/ci.yml` existe et est bien formé (jobs `web`, `mobile`, `api`), mais comme
  aucun dépôt Git ne pousse jamais vers GitHub, **ce fichier n'a jamais été exécuté par GitHub
  Actions**, ni dans cet environnement ni, selon les rapports de phases précédents, à aucun
  moment depuis la Phase 0.
- Ce que la CI *ferait* si elle tournait a été vérifié manuellement, phase après phase, en
  exécutant les mêmes commandes à la main dans les conteneurs (`ruff check .`, `mypy app`,
  `pytest`, `tsc --noEmit`) — ces vérifications sont réelles individuellement, mais ne
  constituent pas une CI : rien ne les redéclenche automatiquement à chaque changement, et rien
  n'empêche une régression non détectée manuellement d'être "validée" par erreur.
- Pas d'action entreprise ici (conforme à la consigne : ne pas initialiser Git pendant cette
  Discovery).

## 7. État Observabilité

Constat réel :
- `apps/api/app/main.py` : aucune configuration de logging (`logging.basicConfig`), aucun
  gestionnaire d'exception personnalisé — les erreurs non interceptées tombent sur le
  comportement par défaut de FastAPI/Starlette (trace affichée sur stdout du conteneur `api` via
  uvicorn, réponse générique `{"detail": "Internal Server Error"}` au client).
- `GET /api/v1/health` (`app/api/v1/health.py`) renvoie systématiquement `{"status": "ok"}` sans
  vérifier la connectivité PostgreSQL ni Redis — un healthcheck qui resterait vert même si la
  base de données ou Redis était indisponible.
- `docker inspect` confirme à l'instant qu'aucun `HEALTHCHECK` n'est défini pour les services
  `api` et `web` dans `docker-compose.yml` (contrairement à `db`/`redis`, qui rapportent
  `(healthy)`).
- Seuls deux points du code appellent `logger.*` dans tout `apps/api/app` : `core/email.py`
  (échec d'envoi, log l'adresse email en clair — PII mineure, voir L1) et `core/rate_limit.py`
  (indisponibilité Redis). Aucune bibliothèque de logs structurés, de suivi d'erreurs (Sentry ou
  équivalent), de métriques ou de traces n'est présente nulle part dans le dépôt.
- Conclusion factuelle : si un incident survenait pendant un pilote réel, la seule information
  disponible serait un flux de texte non structuré dans `docker compose logs`, sans corrélation
  de requête, sans alerte, et sans garantie que l'endpoint `/health` révèle même le problème.

## 8. Audit sécurité / intégrité

Audit dédié réalisé (lecture de code uniquement, aucune modification). Résultats classés par
sévérité, preuve fichier:ligne à l'appui.

**HIGH**
- **Traversée de chemin dans l'upload de fichiers** — `app/core/storage.py` construit le chemin
  final par simple concaténation (`self._base_path / path`) et les appelants
  (`students/router.py` photo/documents, `schools/router.py` logo) intègrent `file.filename` tel
  quel dans le chemin cible, sans normalisation ni retrait des séquences `..`/séparateurs. Un
  utilisateur avec la permission `students.manage` (dont le rôle `STAFF`) peut donc écrire hors
  du répertoire de stockage prévu.
- **Canal de fuite temporelle sur `/auth/login` et `/auth/forgot-password`** —
  `auth/service.py` : l'évaluation court-circuitée (`user is None or ... or not
  verify_password(...)`) fait que le hachage bcrypt (~100ms) n'est exécuté que si le compte
  existe, rendant la latence de réponse elle-même un oracle d'énumération, malgré une réponse
  HTTP générique côté `forgot-password` et un comptage de rate-limit identique dans les deux cas.

**MEDIUM**
- `organizations` toujours sans politique RLS (confirmé de nouveau) — aucun contournement
  exploitable trouvé cette fois-ci (les endpoints organisation utilisent systématiquement l'id
  de la ressource chargée, jamais un id fourni par le client, pour la vérification de
  permission), mais aucune deuxième ligne de défense si un futur endpoint oublie ce contrôle.
- 6 endpoints de création (`create_academic_term`, `create_assessment`, `create_session`,
  `create_guardian`, `create_or_attach_user`, `generate_report_cards_for_class`) ne capturent pas
  `IntegrityError` contrairement à leurs équivalents qui le font déjà (ex. `create_academic_year`,
  `create_assessment_type`) — 500 opaque au lieu de 409 propre, et une vraie fenêtre de course
  possible sur la création d'utilisateur concurrente.
- Aucune détection de réutilisation de refresh token ni de révocation en cascade d'une famille de
  sessions.
- Un access token déjà émis reste utilisable jusqu'à 15 minutes après une révocation de session
  (compromis JWT sans état standard, mais à ne pas confondre avec "logout immédiat").
- Aucun rate limiting sur `/auth/register`, `/auth/refresh`, et `GET /report-cards/verify/{code}`
  (ce dernier mitigé par l'entropie du code à 384 bits, mais toujours non throttlé).
- Modification de notes possible sans aucun contrôle après publication d'un bulletin pour
  l'élève/période concernés (`grades/router.py` : `POST/PATCH /results` ne référence jamais
  `ReportCard.status`/`published_at`).

**LOW**
- Emails loggés en clair sur échec d'envoi (`core/email.py`).
- `GET /roles`/`GET /permissions` toujours accessibles à tout utilisateur authentifié sans
  vérification de permission dédiée, malgré l'existence d'une permission `roles.read` prévue
  précisément pour cela.
- Pas de plafond absolu de durée de session (rolling refresh 30 jours).

**Confirmé sain — aucun problème trouvé** (vérifié activement, pas seulement supposé) :
- Aucune fuite cross-school/cross-org trouvée : tous les contrôles de permission utilisent
  l'id de la ressource réellement chargée, jamais un paramètre fourni par l'appelant.
- Cohérence 404 vs 403 : les ressources introuvables ou hors périmètre renvoient 404 de façon
  homogène (le module parent le fait systématiquement par conception, documenté et vérifié) ;
  aucun cas trouvé où un 403 confirmerait à tort l'existence d'une ressource à un non-ayant-droit.
- Aucun schéma de réponse Pydantic ne fuit un hash de mot de passe ou un token brut.
- Accès parent : chaque endpoint vérifie réellement le lien Guardian → utilisateur → élève avant
  de renvoyer quoi que ce soit ; aucun accès par simple `student_id` deviné.
- Réinitialisation de mot de passe : à usage unique, limitée dans le temps, réponse générique
  correcte dans sa forme (seule la latence, voir HIGH ci-dessus, fuit une information).
- Aucun usage non justifié de `set_platform_wide_context()` (bypass RLS) trouvé en dehors des
  deux points déjà connus et documentés (création de tenant, vérification publique de bulletin).

## 9. Audit préparation pilote

Le parcours complet (création compte → configuration → année scolaire → termes → niveaux →
matières → classes → enseignants → élèves → guardians → inscriptions → présence → notes →
bulletins → publication → email parent → consultation parent) reste, dans ses grandes lignes,
identique à ce qui avait été audité en Phase 12 Discovery : chaque étape a un endpoint et une UI
fonctionnels, testés. Rien de nouveau n'a été découvert dans cette étape du parcours lui-même
depuis la dernière Discovery (Phase 12 n'a touché que le mobile). Le risque réel pour un pilote
n'est donc plus "un endpoit manque" mais bien ce que cette Discovery a mis en évidence
différemment : (1) une vulnérabilité concrète dans le point d'entrée "upload de fichier" que ce
parcours utilise trois fois (photo élève, documents, logo école) et (2) l'absence de tout moyen
de savoir, une fois l'école en train d'utiliser le produit, si quelque chose s'est mal passé.

## 10. Candidats évalués

| Candidat | Type | Problème | Migration | Nouvelles deps | Backend | Web | Mobile |
|---|---|---|---|---|---|---|---|
| **A. Pilot Security & Data Hardening Round 2** (mis à jour par cette Discovery) | Security | Traversée de chemin (HIGH), fuite temporelle (HIGH), `IntegrityError` non gérée (6 endpoints), pas de rate limiting sur register/refresh/verify | Non | Non | Oui | Non | Non |
| B. Report Card Publish UX Completion | UX | Publication unitaire, résultat d'envoi d'email invisible | Non | Non | Léger | Oui | Non |
| C. User Account Lifecycle Completion | Feature | Pas de désactivation/édition utilisateur, pas de changement de mot de passe connecté | Non | Non | Oui | Oui | Non |
| D. Grade Correction Safeguard After Publication | Data integrity | Notes modifiables sans garde-fou après publication d'un bulletin déjà envoyé | Non | Non | Oui | Oui (statut) | Non |
| E. Git / CI & Engineering Reliability | Infrastructure | Aucune CI réellement exécutée depuis la Phase 0 ; `git` absent de l'hôte | Non | Non (outillage, pas dépendance applicative) | Non | Non | Non |
| F. Production Observability / Operational Monitoring | Observability | Zéro logs structurés, `/health` non représentatif, pas de healthcheck Docker api/web | Non | Possible (mineure, ex. lib de logging structuré) | Oui | Non | Non |

Aucun candidat supplémentaire n'a été jugé nécessaire : les deux failles HIGH découvertes
s'intègrent naturellement dans le candidat A déjà prévu pour réévaluation, sans justifier une
catégorie séparée.

## 11. Score

Notes sur 10, moyenne sur 9 critères (valeur pilote, impact utilisateur, fréquence, urgence,
réduction du risque, réutilisation de l'existant, simplicité, sécurité, maintenabilité) :

| Candidat | Valeur pilote | Impact util. | Fréquence | Urgence | Réduction risque | Réutilisation | Simplicité | Sécurité | Maintenabilité | **Score global** |
|---|---|---|---|---|---|---|---|---|---|---|
| **A. Security Hardening R2** | 8 | 5 | 4 | 9 | 9 | 8 | 7 | 10 | 8 | **7.56** |
| D. Grade Correction Safeguard | 7 | 6 | 4 | 6 | 7 | 7 | 5 | 5 | 7 | 6.00 |
| B. Report Card Publish UX | 6 | 6 | 5 | 3 | 2 | 9 | 8 | 5 | 7 | 5.67 |
| C. User Lifecycle | 7 | 6 | 3 | 4 | 4 | 7 | 7 | 6 | 7 | 5.67 |
| E. Git/CI | 5 | 1 | 2 | 6 | 7 | 9 | 8 | 3 | 9 | 5.56 |
| F. Observability | 6 | 2 | 3 | 5 | 6 | 6 | 6 | 4 | 8 | 5.11 |

Le candidat A se détache nettement (7.56 vs 5.1-6.0 pour les autres), porté par une urgence et
une sécurité maximales — deux vulnérabilités HIGH réelles et concrètes, pas des risques
théoriques. Ce n'est pas un score construit pour justifier une conclusion déjà prise : c'est la
première fois dans ce projet qu'un audit dédié révèle des failles de cette sévérité, ce qui
change mécaniquement le classement par rapport aux Discovery précédentes.

## 12. Finance / Mobile Money

Aucune brique n'existe encore (confirmé de nouveau : aucun modèle, aucune route, le rôle
`ACCOUNTANT` reste vide de permissions). Valeur pilote réelle mais non démontrée par un besoin
concret exprimé. Complexité élevée (paiements, réconciliation, relances). Risque financier et de
sécurité élevé par nature (données de paiement). Dépendance externe obligatoire (fournisseur
Mobile Money). **Réponse à la question posée : non, ce n'est pas plus prioritaire que le
durcissement nécessaire au pilote** — introduire une surface de paiement pendant qu'une
vulnérabilité HIGH d'upload de fichiers et une fuite d'énumération de comptes restent ouvertes
serait irresponsable : l'infrastructure doit être renforcée d'abord, la finance touchant par
nature des données plus sensibles que tout ce qui existe aujourd'hui dans EduSphere.

## 13. Offline

La Phase 12 a déjà traité la résilience réseau minimale (gestion d'erreur, retry, timeout) — ce
n'est pas la même chose qu'un offline-first réel (file de synchronisation locale, écriture hors
ligne avec réconciliation ultérieure). Aucune preuve nouvelle d'un besoin réel n'est apparue dans
cet audit. **Réponse : non, l'offline ne doit pas passer devant le durcissement sécurité.** Si un
workflow devait un jour le justifier, ce serait la prise de présence en classe (le plus fréquent,
le plus sensible à une coupure ponctuelle) — mais rien n'indique aujourd'hui qu'un pilote réel
ait rencontré ce problème en pratique, seulement une hypothèse.

## 14. EDU AI

Aucune fondation nouvelle depuis la dernière évaluation : pas de pilote réel en cours, donc pas
de volume de données d'usage réel à exploiter, et aucune observabilité pour mesurer l'effet d'une
fonctionnalité IA une fois introduite (paradoxe : on ne peut pas évaluer la valeur d'une feature
qu'on ne peut pas observer). **Réponse : non, EDU AI ne doit pas passer devant le durcissement.**
Rien n'a changé sur ce point depuis la Phase 12 Discovery.

## 15. Réponses aux Q1-Q12

**Q1 — Une école pilote peut-elle utiliser EduSphere pendant plusieurs semaines sans intervention
technique constante ?** Fonctionnellement oui pour le parcours normal. Opérationnellement, le
filet de sécurité est mince : une vulnérabilité d'upload non corrigée, une sauvegarde purement
manuelle, et une absence totale de visibilité sur les erreurs signifient que rien ne garantit
qu'un problème serait détecté avant qu'un utilisateur ne s'en plaigne.

**Q2 — Quels sont les workflows quotidiens réellement couverts ?** Présence et saisie de notes
(web + mobile), consultation parent (mobile), génération/publication de bulletins avec email —
tous couverts et testés.

**Q3 — Quel workflow métier important reste trop manuel ?** Publication de bulletin unitaire
(pas de "publier tout"), et absence de tout mécanisme forçant une régénération/renotification
après une correction de note post-publication.

**Q4 — Plus gros risque d'une mauvaise expérience pendant un pilote ?** Une erreur serveur (par
exemple une `IntegrityError` non gérée) survenant à un moment critique (génération de bulletins
pour toute une classe) sans qu'aucune alerte ni log exploitable ne permette à l'équipe de le
savoir avant que l'école ne le signale.

**Q5 — Plus gros risque de sécurité/intégrité restant ?** La traversée de chemin dans l'upload de
fichiers (HIGH) — un compte interne (y compris `STAFF`) peut écrire hors du répertoire de
stockage prévu.

**Q6 — Une erreur de production serait-elle détectée rapidement aujourd'hui ?** Non — confirmé :
pas de logs structurés, `/health` ne vérifie ni la base de données ni Redis, et les conteneurs
`api`/`web` n'ont aucun healthcheck Docker (vérifié à l'instant via `docker inspect`).

**Q7 — Peut-on diagnostiquer correctement un incident avec l'observabilité actuelle ?** Non — au
mieux, une lecture manuelle de logs texte non structurés dans `docker compose logs`, sans
corrélation de requête ni contexte.

**Q8 — La CI doit-elle devenir prioritaire avant d'ajouter des fonctionnalités ?** C'est un
chantier légitime et de plus en plus urgent (13 phases sans filet automatisé), mais ce n'est pas
la priorité choisie ici : une vulnérabilité HIGH concrète et exploitable dès aujourd'hui prime sur
un gap de processus, même important. Fortement recommandé comme prochain chantier après Phase 13.

**Q9 — Le modèle de données actuel est-il suffisamment sûr pour continuer à ajouter des
fonctionnalités importantes ?** Structurellement oui (l'audit confirme qu'aucune fuite
cross-tenant n'a été trouvée, l'isolation par permission + RLS fonctionne comme conçu), mais pas
tant que les failles HIGH identifiées ici restent ouvertes — en particulier avant d'élargir la
surface d'upload de fichiers ou d'authentification avec de nouvelles fonctionnalités.

**Q10 — Finance/paiements doit-il passer devant la fiabilité ?** Non (voir §12).

**Q11 — Offline doit-il passer devant la fiabilité ?** Non (voir §13).

**Q12 — EDU AI doit-il passer devant la fiabilité ?** Non (voir §14).

## 16. Recommandation Phase 13

**RECOMMANDATION PHASE 13 : Pilot Security & Data Hardening Round 2 (ciblée sur les failles
découvertes dans cette Discovery)**

- **Problème** : deux vulnérabilités HIGH concrètes découvertes par audit dédié — (1) traversée
  de chemin dans l'upload de fichiers (photo élève, document, logo école) permettant à un compte
  `students.manage`/`STAFF` d'écrire hors du répertoire de stockage prévu ; (2) un canal de fuite
  temporelle sur `/auth/login` et `/auth/forgot-password` permettant de déduire l'existence d'un
  compte malgré une réponse générique. S'y ajoutent des gaps MEDIUM déjà identifiés et toujours
  ouverts (6 endpoints sans capture `IntegrityError`, absence de rate limiting sur
  `/register`/`/refresh`/`/verify/{code}`).
- **Utilisateur concerné** : indirectement tous — c'est l'intégrité du système lui-même, pas une
  fonctionnalité visible.
- **Valeur** : élimine deux vecteurs de compromission réels avant qu'une vraie école (avec de
  vraies données d'élèves) ne les expose en conditions réelles.
- **Urgence** : haute — contrairement aux candidats B/C/D/E/F, il s'agit de vulnérabilités déjà
  présentes et exploitables aujourd'hui par un utilisateur interne légitimement authentifié, pas
  d'un risque théorique futur.
- **Risque réduit** : compromission du système de fichiers serveur ; énumération de comptes
  utilisateurs.
- **Existant réutilisable** : `StorageProvider`, pattern de rate limiting Redis déjà établi
  (Phases 7.2/10.1), pattern `try/except IntegrityError → 409` déjà présent sur plusieurs
  endpoints à répliquer sur les 6 manquants.
- **Complexité** : faible à moyenne — corrections ciblées, pas de nouvelle architecture.
- **Migration** : non.
- **Dépendances** : aucune nouvelle.
- **Backend** : oui. **Web** : non. **Mobile** : non.
- **Pourquoi maintenant** : c'est la première fois qu'un audit sécurité dédié est mené sur ce
  projet (les Discovery précédentes évaluaient des fonctionnalités et de la dette générale, pas
  spécifiquement la sécurité de bout en bout) — attendre encore une phase avant de corriger une
  faille HIGH déjà identifiée et documentée serait injustifiable.
- **Pourquoi les autres attendent** : B, C sont des améliorations de confort sans urgence ; D
  (garde-fou de notes) est un vrai gap d'intégrité mais de sévérité MEDIUM, pas HIGH — attend son
  tour ; E (Git/CI) et F (Observabilité) restent des chantiers légitimes et de plus en plus
  urgents, mais aucun des deux ne corrige une vulnérabilité activement exploitable aujourd'hui —
  fortement recommandés comme Phase 14/15 immédiatement après ce round de sécurité.

## 17. Scope proposé

### IN SCOPE (pour une future Phase 13 Implementation — non commencée ici)
- Assainir la construction des chemins de fichiers dans `app/core/storage.py` et ses appelants
  (`students/router.py`, `schools/router.py`) : ne plus jamais intégrer `file.filename` brut dans
  un chemin ; dériver un nom de fichier sûr (ex. UUID + extension validée par allowlist).
  Vérifier explicitement qu'aucun chemin résolu ne sort du répertoire de stockage configuré.
- Neutraliser le canal de fuite temporelle sur `/auth/login` et `/auth/forgot-password`
  (exécuter un travail de hachage équivalent même quand le compte n'existe pas, pour égaliser la
  latence de réponse).
- Ajouter `try/except IntegrityError → 409` sur les 6 endpoints identifiés (§8), en répliquant le
  pattern déjà utilisé ailleurs, sans réécrire la logique métier existante.
- Ajouter un rate limiting sur `/auth/register`, `/auth/refresh`, et
  `GET /report-cards/verify/{code}`, en réutilisant le pattern Redis fail-open déjà établi
  (fonctions parallèles dédiées, comme fait en Phase 10.1 — pas de refactor des fonctions de
  login existantes).
- Tests réels démontrant chaque correction (tentative de traversée de chemin rejetée, latence
  égalisée ou au minimum non exploitable de façon pratique, 409 propre sur doublon/concurrence,
  rate limiting vérifié sur les 3 nouveaux endpoints).

### OUT OF SCOPE
- RLS sur `organizations` (MEDIUM, sans contournement exploitable trouvé) — reporté.
- Détection de réutilisation de refresh token / révocation en cascade de session (MEDIUM,
  changement plus architectural) — reporté.
- Garde-fou de correction de notes après publication (Candidat D) — reporté à une phase dédiée.
- Git/CI (Candidat E), Observabilité (Candidat F) — reportés, fortement recommandés en suivant
  immédiat.
- Toute nouvelle fonctionnalité (finance, offline, IA, UX bulletin, cycle de vie utilisateur).
- Toute modification de schéma/migration.
- Tout changement web ou mobile.

## 18. Critères de réussite

- Une tentative d'upload avec un nom de fichier contenant `../` échoue proprement ou est
  neutralisée sans jamais écrire hors du répertoire de stockage configuré — vérifié par un test
  réel, pas seulement une relecture de code.
- La latence de réponse de `/auth/login` et `/auth/forgot-password` ne permet plus de distinguer
  de façon pratique un compte existant d'un compte inexistant — mesuré, pas seulement supposé.
- Les 6 endpoints identifiés renvoient 409 (pas 500) sur un conflit d'unicité, vérifié par un
  test réel par endpoint.
- Les 3 nouveaux endpoints rate-limités le sont effectivement, vérifié par des tests réels
  (comme fait en Phase 7.2/10.1), avec fail-open confirmé si Redis est indisponible.
- Aucune régression : suite de tests backend existante toujours 100% verte, `ruff`/`mypy`
  toujours propres.
- Aucun fichier web ou mobile modifié ; aucune migration créée.

## 19. Risques de l'implémentation future

- Le correctif de timing side-channel doit être fait avec soin pour ne pas introduire un nouveau
  déséquilibre de latence ailleurs (ex. toujours hacher un mot de passe factice de complexité
  comparable) — risque faible mais à tester explicitement, pas seulement à implémenter en
  confiance.
- L'assainissement des noms de fichiers touche un chemin déjà utilisé par des données réelles en
  environnement de développement (photos/documents déjà uploadés) — vérifier la rétrocompatibilité
  de lecture des fichiers déjà stockés avant de changer le format des chemins futurs, pour ne pas
  casser l'accès aux fichiers existants.
- Ajouter un rate limiting sur `/register` doit rester cohérent avec le flux d'onboarding
  légitime (un admin qui corrige une erreur de formulaire plusieurs fois de suite ne doit pas se
  retrouver bloqué) — seuils à calibrer avec le même soin que pour le login (Phase 7.2) et le
  forgot-password (Phase 10.1).

## 20. Conclusion

DISCOVERY GO
