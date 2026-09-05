# PHASE 10 DISCOVERY

Document d'audit uniquement. Aucun code modifié, aucune migration créée, aucune dépendance
installée, aucune donnée touchée.

## 1. Executive Summary

Après les Phases 0 à 9, EduSphere a un socle académique complet et testé (présence, notes,
bulletins, portail parent) et un onboarding qui fonctionne réellement de bout en bout, jusqu'à
la distribution des comptes (Phase 9). Ce qui manque désormais le plus n'est **plus une
fonctionnalité métier absente**, mais un déficit d'information pour l'administrateur : le
tableau de bord — le tout premier écran qu'un directeur d'école voit chaque jour — reste un
message de bienvenue statique, inchangé depuis la Phase 0. C'est le seul des trois "moments de
valeur" (admin/enseignant/parent) qui échoue complètement le test des 30 secondes (§7).

Deux constats secondaires méritent d'être documentés (sans être corrigés ici, conformément à la
règle de cette phase) : `dev_reset_token` existe toujours, en coexistence avec l'envoi d'email
réel (comportement voulu de la Phase 9, pas une régression) ; et `POST /auth/forgot-password`
n'a, contrairement à `/auth/login`, **aucun rate limiting** — un gap de sécurité concret introduit
en pratique par la Phase 9 elle-même (avant, une requête en boucle ne faisait qu'écrire une ligne
en base ; depuis Phase 9, elle déclenche un envoi d'email réel à chaque appel).

**Recommandation : Phase 10 = Tableau de bord opérationnel de l'administrateur.**

## 2. État réel du dépôt

- Toujours pas de `CLAUDE.md`.
- `docs/phases/` contient maintenant 6 documents (Phase 6, 8, 8 Implementation, 8.1, 9
  Discovery, 9 Implementation) — le reste de `docs/` inchangé (`docs/architecture/overview.md`
  toujours limité à la Phase 0, `docs/api/` et `docs/product/` toujours vides).
- `apps/api/app/modules/` : toujours 11 modules métier — aucun nouveau module depuis la Phase 9
  (email a été ajouté dans `app/core/`, pas comme module métier, cohérent avec le patron
  `StorageProvider`).
- `apps/api/alembic/versions/` : toujours 8 migrations (`0001`→`0008`), confirmé inchangé.
- `apps/api/tests/` : 16 fichiers, **120 tests** (114 + 6 de `test_email.py`).
- `apps/web/app/` : deux nouvelles pages publiques (`(auth)/forgot-password`,
  `(auth)/reset-password`) depuis la Phase 9. Le dashboard (`(app)/page.tsx`) est **toujours**,
  relu ligne à ligne, un message de bienvenue statique + un seul lien vers `/school` — strictement
  identique à son état en Phase 8 et Phase 9 Discovery.
- `apps/mobile/app/` : inchangé. L'écran d'accueil enseignant (`(teacher)/index.tsx`) est une
  simple liste de classes (`FlatList` sur `schoolClasses.list()`), sans aucun résumé du jour
  (pas de "présences à faire aujourd'hui", pas de compteur, pas de notification).
- `dev_reset_token`/`dev_token` : toujours présents dans le code (`users/service.py`,
  `auth/router.py`, `auth/service.py`), désormais **en plus** d'un envoi d'email réel — c'est le
  comportement voulu par la Phase 9, pas un oubli.
- `POST /auth/forgot-password` (`apps/api/app/modules/auth/router.py:77-82`) : confirmé, **aucun
  appel à `ensure_login_not_rate_limited` ou équivalent**, contrairement à `/auth/login`
  (`router.py:44`). Nouveau constat de cette Discovery — voir §10/§16.

## 3. Cartographie fonctionnelle

Reprend les matrices des Discoveries précédentes, mise à jour uniquement là où l'état a changé.

| Domaine | Existe | Partiel | Absent | État réel | Utilisateurs |
|---|:---:|:---:|:---:|---|---|
| Onboarding (register→wizard) | ✅ | | | Inchangé depuis 8.1, fonctionne réellement | Admin |
| **Dashboard admin** | | ✅ | | **Toujours** statique, aucune métrique | Admin |
| Email transactionnel | ✅ | | | Nouveau (Phase 9), fonctionne réellement | Tous |
| Users/roles/permissions | ✅ | | | Inchangé, solide | Admin |
| Academic setup | ✅ | | | Inchangé, guidé par le wizard | Admin |
| Students (CRUD/import/guardians/docs) | ✅ | | | Inchangé, solide | Admin |
| Attendance | ✅ | | | Inchangé, solide (web + mobile enseignant) | Admin, enseignant |
| Grades | ✅ | | | Inchangé, solide (web + mobile enseignant) | Admin, enseignant |
| Report cards + QR | ✅ | | | Inchangé, solide, sécurisé | Admin, parent |
| Parent portal (mobile + web verify) | ✅ | | | Inchangé, lecture seule fonctionnelle | Parent |
| **Teacher home/dashboard** | | ✅ | | Liste de classes simple, aucun résumé du jour | Enseignant |
| Homework/devoirs | | | ✅ | Toujours absent | Enseignant, parent |
| Timetable/emploi du temps | | | ✅ | Toujours absent | Tous |
| Communication/notifications in-app | | | ✅ | Toujours absent (aucun modèle) | Tous |
| Finance/fees/paiements | | | ✅ | Toujours absent, confirmé par recherche | Admin, parent |
| Search (globale) | | ✅ | | Toujours limité à la recherche élèves | Admin |
| Audit logs | | | ✅ | Toujours absent | Admin |
| Mobile offline | | | ✅ | Toujours absent | Tous |
| AI / EDU AI | | | ✅ | Toujours totalement absent | — |
| Rate limiting login | ✅ | | | Inchangé (Phase 7.2) | — |
| **Rate limiting forgot-password** | | | ✅ | **Absent — nouveau constat** (voir §2) | — |

## 4. Parcours administrateur

Connexion (fonctionne) → dashboard (**échoue** : rien à voir) → gérer enseignants (fonctionne,
et depuis Phase 9 l'invitation par email fonctionne réellement) → gérer élèves (fonctionne,
complet) → superviser présences/notes (fonctionne, via les pages dédiées, pas via une vue
d'ensemble) → générer bulletins (fonctionne) → communiquer (n'existe pas) → suivre les
opérations importantes (n'existe pas) → obtenir des indicateurs utiles (n'existe pas).

**Point de rupture** : pour savoir "comment va mon école aujourd'hui", l'admin doit ouvrir
manuellement Présences, puis Notes, puis Bulletins, puis Utilisateurs — quatre écrans, aucune
synthèse. C'est une manipulation répétée à chaque connexion, pas un problème ponctuel.

## 5. Parcours enseignant

Connexion (mobile, fonctionne) → voir ses classes (liste simple, fonctionne) → identifier ses
cours/matières (visible en entrant dans une classe) → prendre présence (fonctionne, testé
réellement) → saisir notes (fonctionne, testé réellement) → consulter résultats (fonctionne) →
devoirs (n'existe pas) → communiquer (n'existe pas) → retrouver rapidement les informations
utiles (partiellement : pas de vue "aujourd'hui", l'enseignant doit naviguer classe par classe).

L'enseignant **peut réellement travailler quotidiennement** — présence et notes sont les deux
tâches qui reviennent chaque jour/semaine, et les deux fonctionnent bien. Rien ne l'empêche de
faire son travail de base. Ce qui manque est un confort (un écran "aujourd'hui"), pas un
blocage.

## 6. Parcours parent

Connexion (mobile, fonctionne) → voir ses enfants (fonctionne) → présence (fonctionne) → notes
(fonctionne) → bulletins PDF (fonctionne) → informations importantes (n'existe pas, aucune
notification) → situation financière (n'existe pas, aucun module finance).

Rien ne bloque ce parcours ; l'absence de notification signifie que le parent doit se souvenir
d'ouvrir l'app.

## 7. Moment of Value

| Rôle | Ce qu'il doit obtenir | Délai cible | Résultat réel aujourd'hui |
|---|---|---|---|
| Admin | Un signal sur l'état de l'école (présence du jour, notes en attente, alertes) | < 30 s | **Échec total** — écran vide, message statique |
| Enseignant | Voir ses classes du jour et pouvoir prendre présence | < 1 min | **Réussi** — liste de classes accessible immédiatement, prise de présence en quelques taps |
| Parent | Voir la dernière information sur son enfant (présence/note récente) | Immédiat | **Réussi** — accessible dès l'ouverture de l'app mobile, pas de navigation complexe |

Seul le rôle **admin** échoue ce test aujourd'hui, et c'est un échec total (pas partiel) :
aucune information n'est disponible sans naviguer ailleurs.

## 8. Gaps P0/P1/P2/P3

**P0 — bloque l'utilisation d'une école pilote** : aucun. Le pilote peut fonctionner tel quel
(tous les parcours métier critiques sont opérationnels).

**P1 — très fortement recommandé avant ou pendant le pilote** :
- Dashboard opérationnel admin. *Utilisateur* : admin. *Impact* : élevé (premier écran vu à
  chaque connexion). *Fréquence* : quotidienne. *Solution* : agrégations sur données déjà
  existantes. *Dépendances* : aucune. *Complexité* : faible.
- Rate limiting sur `forgot-password`. *Utilisateur* : tous (protection). *Impact* : moyen
  (vecteur de nuisance par email, pas de fuite de données). *Fréquence* : latent (exploitable à
  tout moment tant que non corrigé). *Solution* : réutiliser `app/core/rate_limit.py`, même
  patron que `/login`. *Dépendances* : aucune (Redis déjà en place). *Complexité* : faible.

**P2 — amélioration importante mais non bloquante** :
- Notifications in-app (nécessite une migration, voir Phase 9 Discovery Candidat 3).
- Import enseignants en masse.
- Recherche globale (au-delà des élèves).
- Audit logs.
- Module finance interne (frais, sans paiement).

**P3 — future évolution** :
- Devoirs/homework, emploi du temps, offline mobile, IA, paiements Mobile Money,
  multi-campus/pays.

## 9. UX

- Navigation cohérente et déjà bien établie (barre latérale filtrée par permission, conventions
  Tailwind homogènes sur tout `apps/web`).
- États loading/erreur déjà standardisés sur les écrans construits depuis la Phase 7.2/8/9
  (`ApiError`, messages compréhensibles, jamais de stack trace côté client).
- Le dashboard est la seule page qui ne respecte pas cette cohérence par omission : elle
  n'affiche simplement rien d'utile, pas une régression de qualité mais un vide fonctionnel.
- Pagination toujours absente sur les listes volumineuses (déjà noté en Phase 8 Discovery,
  toujours vrai, non bloquant à l'échelle d'une première école pilote).
- Responsive : le wizard (Phase 8) a été conçu et testé responsive ; les écrans plus anciens
  n'ont pas été audités spécifiquement pour le responsive dans cette Discovery (hors périmètre
  d'un audit approfondi ligne à ligne de chaque écran).

## 10. Sécurité

Rien de nouveau au-delà de ce qui était déjà documenté (Phase 7.2, Phase 8/9 Discovery), **sauf
un constat nouveau et concret** : `POST /auth/forgot-password` n'a aucun rate limiting
(`apps/api/app/modules/auth/router.py:77-82` — confirmé par lecture directe, à comparer avec
`login` ligne 44 qui appelle `ensure_login_not_rate_limited`). Avant la Phase 9, l'impact d'un
abus était limité (une ligne en base, un `dev_token` renvoyé en dev uniquement). **Depuis la
Phase 9, chaque appel déclenche un envoi d'email réel** — un script appelant cet endpoint en
boucle sur une adresse réelle devient un vecteur de nuisance (spam / email bombing) contre un
utilisateur légitime, sans qu'aucune limite ne s'applique. Ce n'est pas une fuite de données
(la réponse reste anti-énumération), mais c'est un abus de service réel et non protégé.

Autres points déjà connus, reconfirmés sans changement : tenant isolation/RLS/RBAC solides et
testés, `organizations` toujours sans RLS (P2 déjà noté), pagination absente (P2 déjà noté).

## 11. Finance

Toujours totalement absent (aucun modèle, confirmé par recherche dans `apps/api/app`).
Réponse à la question posée : **non, pas prioritaire maintenant**. Le socle académique
quotidien (présence/notes/bulletins) est ce qui doit prouver sa valeur en premier lors d'un
pilote ; les frais scolaires restent gérables par les moyens existants de l'école pendant cette
période. Si/quand ce domaine devient prioritaire, la séquence recommandée reste : **module
financier interne d'abord** (frais, factures, soldes — sans paiement), **intégration Mobile
Money ensuite** — jamais l'inverse, pour des raisons de complexité et de risque réglementaire
déjà documentées en Phase 9 Discovery §12.

## 12. Communication

La Phase 9 fournit une infrastructure email transactionnelle solide, mais **strictement limitée
à l'authentification** (invitation, reset password) par conception — ce n'est pas un système de
notifications métier, et l'étendre à des notifications (bulletin publié, absence détectée) est
un développement distinct (nouveaux déclencheurs, nouvelle table pour tracer ce qui a été
envoyé/lu si affiché in-app, décisions de fréquence/opt-out). Ce n'est **pas** ce qui apporte le
plus de valeur immédiate : le dashboard répond à un vide total (§7), la communication améliore
un usage déjà fonctionnel (les parents savent déjà consulter l'app). Recommandation : ne pas
exploiter davantage l'infrastructure email dans Phase 10 — la garder telle quelle
(authentification uniquement) et traiter les notifications comme un candidat distinct, futur,
si le pilote confirme le besoin.

## 13. Espace enseignant

- L'enseignant **peut réellement travailler quotidiennement** (§5) — présence et notes,
  les deux tâches critiques, fonctionnent bien et sont testées.
- Le dashboard enseignant, au sens strict, **n'existe pas** — l'écran d'accueil
  (`apps/mobile/app/(teacher)/index.tsx`) est une liste de classes sans résumé du jour.
- Les classes sont facilement accessibles (une liste, un tap).
- Présence et notes sont efficaces (déjà testées réellement en Phases 6/8).
- Devoirs : **pas nécessaires maintenant** — aucun signal d'un besoin non couvert dans le
  parcours actuel, ajouter cette fonctionnalité maintenant serait anticipatoire, pas fondé sur
  un usage réel observé.
- Emploi du temps : **pas nécessaire maintenant**, même raisonnement — les classes/matières/
  affectations suffisent au fonctionnement actuel (présence et notes ne dépendent pas d'un
  emploi du temps formalisé).

## 14. Mobile / Offline

- Parent mobile : mature, inchangé, fonctionnel (§6).
- Teacher mobile : mature pour les tâches critiques, écran d'accueil minimal (§13).
- Offline : toujours aucune dépendance technique en place. Réévalué explicitement pour cette
  Discovery : rien dans l'usage actuel (aucun retour de pilote réel, puisqu'aucun pilote n'a
  encore eu lieu) ne justifie cet investissement lourd maintenant. Reste une évolution à
  réévaluer **après** un premier pilote réel, seulement si la connectivité s'avère être un vrai
  point de friction rapporté par des utilisateurs réels — pas une hypothèse a priori liée à la
  zone géographique cible.
- Notifications push : dépendrait d'une infrastructure de notification qui n'existe pas encore
  (§12) — non pertinent isolément.

## 15. AI / EDU AI

Recherche renouvelée dans tout le dépôt : toujours aucune trace de code, d'abstraction, de
dépendance ou de configuration liée à l'IA. Rien n'a changé depuis la Phase 9 Discovery.
Réponse à la question posée : l'IA n'apporte aujourd'hui strictement aucune valeur pilote
supérieure aux gaps identifiés — le premier écran que voit un administrateur est encore vide.
Construire de l'IA avant un dashboard basique serait un contre-exemple direct de priorisation
par la valeur réelle. **Hors périmètre, sans ambiguïté, encore cette phase.**

## 16. Email

- Fournisseur actuel : `LocalEmailProvider` par défaut (`EMAIL_PROVIDER=local`), écrit chaque
  email en fichier sous `EMAIL_LOCAL_PATH` — comportement dev/tests, jamais un envoi réel.
- Configuration production : `EMAIL_PROVIDER=smtp` + `SMTP_HOST`/`SMTP_PORT`/`SMTP_USERNAME`/
  `SMTP_PASSWORD`/`SMTP_FROM_ADDRESS`/`SMTP_USE_TLS`, tous en variables d'environnement, aucun
  fournisseur figé (cohérent avec le principe déjà appliqué au stockage).
- Invitation et reset password : les deux fonctionnent réellement et sont testés (Phase 9,
  120/120 pytest, 16/16 Playwright).
- Extensibilité : l'abstraction `EmailProvider` (une seule méthode `send(to, subject, body)`,
  texte brut) est volontairement minimale — suffisante pour l'usage actuel (authentification),
  mais n'a ni templates HTML, ni file d'attente, ni retry, ni suivi d'ouverture. Ce n'est **pas**
  un défaut : c'est le périmètre exact validé par la Phase 9 Discovery. Une extension serait
  nécessaire si Phase 10 (ou une phase ultérieure) exploitait l'email pour des notifications
  métier à volume plus élevé — pas le cas de la recommandation de cette Discovery.
- Sécurité des tokens : `PasswordResetToken` reste la seule source de vérité, expiration 30
  minutes (`PASSWORD_RESET_TOKEN_EXPIRE_MINUTES`), usage unique (`used_at`), hashé en base
  (`token_hash`, jamais stocké en clair) — inchangé, solide.
- URLs : construites côté serveur à partir de `settings.public_web_base_url` — jamais
  d'entrée utilisateur dans la construction du lien.
- Logs : les échecs d'envoi sont loggés (`logger.warning`, `app/core/email.py`) sans jamais
  inclure le corps du message ni le jeton — pas de fuite de token dans les logs applicatifs.
  **Nuance identifiée** : en mode `local` (dev/tests), le corps complet — y compris le jeton en
  clair — est écrit sur disque sous `EMAIL_LOCAL_PATH`. C'est intentionnel et sans risque en
  développement, mais constitue un risque opérationnel si `EMAIL_PROVIDER` restait
  accidentellement à `local` en production (mauvaise configuration, pas un bug de code) — à
  garder en tête dans la checklist de mise en production, pas un problème de cette phase.
- **Aucun problème critique lié à l'email lui-même** ; le seul problème de sécurité réel
  découvert cette phase est en amont, sur l'endpoint qui déclenche l'envoi (§10), pas sur
  l'infrastructure d'envoi elle-même.

## 17. dev_reset_token

- Toujours présent dans le code (`users/service.py`, `auth/service.py`, `auth/router.py`),
  confirmé par recherche directe.
- Toujours affiché côté web, uniquement en développement (`apps/web/app/(app)/users/page.tsx`) —
  comportement inchangé et voulu depuis la Phase 9 : en production, `dev_reset_token`/
  `dev_token` sont `None`, seul l'email réel part.
- Est-il encore nécessaire ? **Oui, en développement/tests** — 6 tests de `test_email.py` et
  plusieurs suites Playwright (`setup-wizard`, `admin-onboarding`, `password-reset`) l'utilisent
  explicitement comme mécanisme de préparation de test (obtenir un jeton valide sans lire une
  vraie boîte mail). Le retirer casserait ces tests sans aucun bénéfice pour un pilote réel
  (déjà invisible en production).
- Peut-il être remplacé progressivement par le système email ? Il l'est déjà, **en
  production** — c'est exactement ce que la Phase 9 a livré. Il n'y a rien à "remplacer" en
  dev/tests : c'est un outil de développement légitime, pas une dette.
- **Priorité : P3 / non applicable** — ce n'est plus un problème depuis la Phase 9 ; le maintenir
  en dev est une décision correcte, pas un gap à corriger.

## 18. Candidats

Maximum 5, issus de l'analyse ci-dessus.

### Candidat 1 — Tableau de bord opérationnel admin
Métriques réelles (effectif élèves, taux de présence récent, complétude de saisie des notes,
bulletins publiés) sur la page d'accueil admin, remplaçant le message statique. Réutilise les
listes déjà existantes (`/students`, `/attendance-records`, `/results`, `/report-cards`).
Complexité faible, aucune dépendance, migration incertaine (probable endpoint de synthèse, à
trancher en planification détaillée — pas nécessairement une nouvelle table).

### Candidat 2 — Notifications in-app
Centre de notifications minimal (in-app uniquement), déclenché par des événements déjà
existants (bulletin publié, présence enregistrée). Nécessite une nouvelle table (seul candidat
de cette liste à en requérir une).

### Candidat 3 — Rate limiting sur forgot-password
Réutilisation directe de `app/core/rate_limit.py` (même patron que `/login`) sur
`POST /auth/forgot-password`. Très faible complexité, corrige un gap de sécurité concret et
nouvellement significatif (§10).

### Candidat 4 — Recherche globale
Étendre la recherche au-delà des élèves (utilisateurs, classes) — confort administratif,
pas de blocage identifié.

### Candidat 5 — Import enseignants en masse
Symétrique à l'import élèves déjà existant. Confort ponctuel (onboarding initial), valeur
répétée faible une fois l'école configurée.

## 19. Matrice de priorisation

Méthode : `Score = Valeur×0,25 + Impact_quotidien×0,20 + Impact_utilisateur×0,20 +
Urgence×0,20 − Complexité×0,10 − Risque×0,05` (formule proposée dans le brief, adoptée telle
quelle — elle pondère fortement la valeur et l'usage réel, pénalise modérément la complexité,
et pénalise faiblement le risque puisque aucun candidat ici ne présente de risque élevé).
Notes sur 10.

| Candidat | Valeur | Impact quotidien | Impact utilisateur | Urgence | Complexité | Risque | Score | Position |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1. Dashboard admin | 8 | 8 | 7 | 8 | 3 | 2 | **6,20** | **1** |
| 2. Notifications in-app | 6 | 5 | 6 | 5 | 5 | 3 | 4,05 | 2 |
| 3. Rate limiting forgot-password | 5 | 2 | 3 | 6 | 2 | 1 | 3,20 | 3 |
| 4. Recherche globale | 4 | 4 | 4 | 3 | 4 | 2 | 2,70 | 4 |
| 5. Import enseignants en masse | 4 | 2 | 3 | 3 | 3 | 2 | 2,20 | 5 |

## 20. Phase 10 recommandée

**Candidat 1 — Tableau de bord opérationnel admin.**

Réponse à la question posée : c'est le seul gap qui fait échouer complètement le test du
"moment de valeur" (§7) — pour n'importe quel autre rôle, ou n'importe quel autre candidat de
cette liste, l'utilisateur obtient déjà quelque chose d'utile aujourd'hui. Pour l'admin ouvrant
son tableau de bord, il n'obtient rien. C'est aussi le candidat au score le plus élevé (6,20,
nettement devant le second à 4,05), pour la complexité la plus faible.

**Pourquoi pas les autres maintenant :**
- Notifications in-app : valeur réelle mais nécessite une migration et un travail de conception
  (quels événements, quelle fréquence) non trivial ; améliore un usage déjà fonctionnel plutôt
  que de combler un vide total.
- Rate limiting forgot-password : gap réel et peu coûteux à corriger, mais son urgence/fréquence
  d'exploitation reste plus faible que l'impact quotidien d'un dashboard vide vu à **chaque**
  connexion admin — candidat sérieux pour une prochaine petite phase de durcissement, pas pour
  occuper Phase 10 à lui seul.
- Recherche globale et import en masse : confort, pas de blocage, scores nettement inférieurs.
- Finance, IA, offline, devoirs/emploi du temps : explicitement évalués et écartés (§11, §13,
  §14, §15) — aucun signal réel n'en justifie la priorité maintenant.

## 21. Scope IN

Métriques réelles sur la page d'accueil admin (`(app)/page.tsx`) : effectif élèves actifs, taux
de présence récent (ex. 7 derniers jours), complétude de saisie des notes (évaluations avec
résultats saisis / total), nombre de bulletins publiés. Calcul par agrégation de données déjà
existantes, scopé à l'école courante (`currentSchoolId`), respectant les permissions déjà en
place (visible seulement si l'utilisateur a les droits de lecture correspondants sur chaque
domaine agrégé).

## 22. Scope OUT

Graphiques historiques multi-années, exports, analytics avancées, comparaisons inter-écoles,
notifications, rate limiting forgot-password (candidat distinct), recherche globale, import en
masse, finance, IA, offline, devoirs, emploi du temps, refactoring général, toute modification
d'`auth`/RBAC/RLS.

## 23. Architecture proposée (pour approbation future, rien exécuté)

- **Backend** : probable endpoint de synthèse par école (ex. `GET /schools/{id}/dashboard` ou
  équivalent) plutôt que de rapatrier des listes complètes côté frontend — à trancher en
  planification détaillée selon le coût réel des agrégations côté client d'abord mesuré.
- **Frontend** : réécriture de `apps/web/app/(app)/page.tsx` uniquement ; aucun autre écran
  touché.
- **Mobile** : aucun changement attendu (le dashboard est un besoin web admin, pas mobile).
- **DB** : probablement aucune migration (lecture agrégée de tables existantes) — à confirmer en
  planification si un endpoint dédié s'avère nécessaire pour des raisons de performance
  (agrégation SQL plutôt que rapatriement de listes complètes).
- **Permissions** : réutilisation stricte des permissions déjà existantes par domaine
  (`students.read`, `attendance.read`, `grades.read`, `report_cards.read`) — pas de nouvelle
  permission.
- **Sécurité** : lecture seule, aucune nouvelle surface d'écriture, isolation tenant héritée des
  endpoints réutilisés.
- **Tests** : tests des agrégations (si endpoint dédié), tests E2E Playwright du nouvel affichage.
- **Dépendances** : aucune anticipée.

## 24. Plan d'implémentation (indicatif, non exécuté)

1. Décider agrégation côté frontend (simple, rapide) vs. endpoint de synthèse dédié (plus
   scalable) — probablement démarrer simple, réutiliser les listes existantes, mesurer avant
   d'optimiser.
2. Construire les 4 métriques du Scope IN sur `(app)/page.tsx`.
3. États loading/erreur cohérents avec les conventions déjà établies (`ApiError`, pas de
   blocage silencieux).
4. Tests + E2E.

## 25. Plan de tests (indicatif)

Backend (si endpoint dédié) : agrégations correctes, isolation tenant. Frontend/E2E : le
dashboard affiche des valeurs réelles après avoir configuré une école de test (élèves,
présences, notes, bulletin publié), respecte les permissions (un rôle sans `attendance.read`
ne voit pas cette métrique).

## 26. Critères d'acceptation (indicatifs)

- Un admin voit au moins une métrique réelle et correcte en moins de 30 secondes après
  connexion, sans naviguer ailleurs.
- Aucune régression : pytest, ruff, mypy, Playwright existants tous verts.
- Aucune migration si évitable ; si nécessaire, justifiée explicitement.
- Responsive, cohérent avec les conventions UI déjà établies.

## 27. Risques

Risque de sur-ingénierie si l'agrégation est prématurément optimisée avant d'avoir mesuré un
besoin réel de performance — mitigé en commençant simple (§24, étape 1). Aucun risque de
sécurité ou d'isolation identifié (lecture seule, permissions réutilisées).

## 28. Conditions GO / NO-GO

**GO** — aucune dépendance bloquante, complexité faible, valeur la plus élevée de tous les
candidats évalués, comble un vide total plutôt qu'une amélioration marginale.

**NO-GO / à requalifier** uniquement si le prochain pilote se concentre exclusivement sur la
validation du parcours enseignant/parent sans jamais impliquer d'administrateur actif au
quotidien — scénario peu probable pour un pilote destiné à démontrer une valeur complète.

---

PHASE 10 DISCOVERY COMPLETE

Recommended Phase 10:
Tableau de bord opérationnel admin

Why:
C'est le seul des trois "moments de valeur" (admin/enseignant/parent) qui échoue complètement
aujourd'hui — le dashboard admin est un message statique inchangé depuis la Phase 0, alors que
les parcours enseignant et parent fonctionnent déjà bien. Score le plus élevé de la matrice de
priorisation (6,20), complexité la plus faible.

Pilot value:
Donne à l'administrateur d'une école pilote une vue d'ensemble réelle dès la connexion, au lieu
de devoir naviguer manuellement dans 4 écrans différents pour savoir "comment va mon école".

Priority:
P1

Complexity:
Faible

Main risks:
Sur-ingénierie si l'agrégation est optimisée prématurément ; aucun risque de sécurité ou
d'isolation identifié (lecture seule, permissions déjà existantes réutilisées).

Scope:
4 métriques réelles (effectif élèves, taux de présence récent, complétude de saisie des notes,
bulletins publiés) sur la page d'accueil admin existante, aucune nouvelle page, aucune nouvelle
permission, migration probablement évitable.

GO / NO-GO:
GO

WAITING FOR APPROVAL
