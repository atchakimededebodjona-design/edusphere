# PHASE 11 DISCOVERY

Document d'audit uniquement. Aucun code modifié, aucune migration créée, aucune dépendance
installée, aucune donnée touchée.

## 1. Executive Summary

Après 6 phases consécutives centrées sur l'administrateur et l'infrastructure (7.2 sécurité, 7.3
backup, 8 wizard, 8.1 contexte école, 9 email, 10 dashboard, 10.1 rate limiting), le socle admin
est maintenant solide et l'onboarding fonctionne réellement de bout en bout. Mais **aucune de ces
six phases n'a apporté quoi que ce soit aux enseignants ou aux parents** — leurs parcours sont
exactement dans l'état où la Phase 7.1 les a laissés.

En simulant le parcours réel des trois acteurs (§3), l'enseignant peut déjà travailler
quotidiennement sans blocage (présence + notes fonctionnent bien). Le parent, en revanche,
**doit se souvenir seul d'ouvrir l'application** — rien ne l'y ramène. C'est le déficit de valeur
le plus concret identifié cette phase, et il touche un acteur systématiquement sous-servi par les
phases précédentes (l'audit précédent lui-même avait noté : "ne pas privilégier automatiquement
l'administration").

La Phase 9 a construit une infrastructure email transactionnelle qui n'est aujourd'hui utilisée
que pour l'authentification (invitation, reset password) — jamais pour ramener un parent vers
l'application au moment où une information réelle et attendue existe (un bulletin vient d'être
publié).

**Recommandation : Phase 11 = notification email au parent lors de la publication d'un
bulletin**, une extension ciblée et minimale de l'infrastructure déjà construite en Phase 9 —
pas le centre de notifications in-app plus large déjà évoqué (et repoussé) dans les Discoveries
précédentes, dont la complexité (nouvelle table, écran de liste, marquage lu/non lu) reste
disproportionnée pour la valeur immédiate visée.

## 2. État réel du dépôt

- Toujours pas de `CLAUDE.md`.
- `docs/phases/` : 9 documents désormais (jusqu'à Phase 10.1 incluse).
- `apps/api/alembic/versions/` : toujours 8 migrations (`0001`→`0008`) — confirmé inchangé,
  aucune des Phases 8 à 10.1 n'a touché au schéma.
- `apps/api/tests/` : 18 fichiers (114 → 120 → 126 → 135 tests au fil des Phases 9/10/10.1).
- `apps/api/app/core/` : `email.py` (Phase 9, `EmailProvider`/`LocalEmailProvider`/
  `SmtpEmailProvider`), `rate_limit.py` (Phase 7.2 + Phase 10.1, désormais deux mécanismes
  indépendants : login et forgot-password).
- `apps/api/app/modules/schools/service.py` (Phase 10, tableau de bord) — seul module ayant
  gagné un fichier `service.py` récemment.
- `Guardian` (`apps/api/app/modules/students/models.py:40-55`) : porte déjà un champ `email`
  (nullable, indépendant de tout compte utilisateur `user_id`) — donné dès la Phase 3, jamais
  exploité pour autre chose que l'affichage/la saisie administrative jusqu'ici.
- `ReportCard.published_at` (Phase 5) : déjà l'événement exact et déjà déclenché par un seul
  endpoint (`POST /report-cards/{id}/publish`) — point d'accroche naturel pour toute
  notification liée à la publication, sans nouvelle table de suivi d'événements.
- Aucun autre changement structurel constaté depuis la Phase 10.1 Implementation.

## 3. Cartographie fonctionnelle

| Domaine | Complet | Partiel | Absent | État réel | Valeur quotidienne |
|---|:---:|:---:|:---:|---|---|
| Onboarding | ✅ | | | Fonctionne réellement (8.1) | Admin |
| Dashboard admin | ✅ | | | 4 métriques réelles (Phase 10) | Admin |
| Email transactionnel | ✅ | | | Auth uniquement (invitation, reset) | Tous (indirect) |
| Rate limiting | ✅ | | | Login + forgot-password (10.1) | — |
| Academic setup / users / roles | ✅ | | | Inchangé, solide | Admin |
| Students (CRUD/import/guardians/docs) | ✅ | | | Inchangé, solide | Admin |
| Attendance | ✅ | | | Inchangé, solide (web + mobile enseignant) | Admin, enseignant |
| Grades | ✅ | | | Inchangé, solide (web + mobile enseignant) | Admin, enseignant |
| Report cards + QR | ✅ | | | Inchangé, solide, sécurisé | Admin, parent |
| Parent portal (mobile + web verify) | ✅ | | | Lecture seule fonctionnelle, **aucun rappel actif** | Parent |
| **Notification parent (bulletin publié)** | | | ✅ | **Absent — candidat recommandé** | Parent |
| Notifications in-app générales | | | ✅ | Toujours absent (nouvelle table nécessaire) | Tous |
| Teacher dashboard/"aujourd'hui" | | ✅ | | Liste de classes simple, pas de vue du jour | Enseignant |
| Homework/devoirs, emploi du temps | | | ✅ | Toujours absent, évalué non urgent (§8) | Enseignant, parent |
| Finance/fees/paiements | | | ✅ | Toujours totalement absent | Admin, parent |
| Recherche globale | | ✅ | | Limitée aux élèves | Admin |
| Import enseignants en masse | | | ✅ | Confort, valeur ponctuelle faible | Admin |
| Export élèves/rapports | | | ✅ | Toujours absent | Admin |
| Audit logs | | | ✅ | Toujours absent | Admin/Plateforme |
| Mobile offline | | | ✅ | Toujours absent, non urgent (§13) | Tous |
| AI / EDU AI | | | ✅ | Toujours totalement absent | — |

## 4. Parcours administrateur

**Jour 1** : inscription → onboarding (wizard) → enseignants/élèves — fonctionne réellement de
bout en bout depuis la Phase 8.1, aucune sortie d'EduSphere nécessaire.
**Semaine 1** : présence, notes, bulletins, dashboard, gestion utilisateurs — tout fonctionne,
l'admin peut désormais voir un état réel de son école dès la connexion (Phase 10).
**Semaine 2+** : supervision (dashboard), suivi (dashboard + écrans dédiés), **communication
(absente)**, rapports (limités aux 4 métriques du dashboard, pas d'export), opérations
récurrentes (fonctionnent, rien de nouveau à signaler). Le seul point où l'admin sort encore
mentalement d'EduSphere : il n'a aucun moyen de savoir si les parents consultent réellement les
bulletins publiés, ni de les relancer autrement qu'en dehors de l'application (téléphone, réseil
social, bouche-à-oreille).

## 5. Parcours enseignant

Chaque jour : connexion (mobile) → classes → présence → notes → informations pédagogiques —
**tout fonctionne**, testé réellement (Phases 6, 8). Devoirs : absent, pas encore nécessaire
(§8). Communication : absente, mais rien dans l'usage quotidien actuel ne le rend bloquant (les
échanges famille-école restent, pour l'instant, hors de l'application, comme c'était déjà le cas
avant EduSphere). **Un enseignant pourrait réellement travailler avec EduSphere tous les jours
dès aujourd'hui** — c'est la conclusion de l'audit précédent, reconfirmée sans changement.

## 6. Parcours parent

Chaque semaine (en théorie) : connexion → enfants → présence → notes → bulletins — tout
fonctionne **si le parent pense à se connecter**. Rien ne l'y invite activement. **Le parent ne
reçoit aujourd'hui aucun signal de valeur qui le ramène régulièrement dans l'application** — la
réponse à la question posée par le brief est non, pas encore, malgré un contenu de qualité déjà
disponible une fois qu'il se connecte.

## 7. Table Stakes

| Fonctionnalité | Existe | Mature | Nécessaire au pilote | Peut attendre |
|---|:---:|:---:|:---:|:---:|
| Auth + multi-tenancy + RBAC | ✅ | ✅ | ✅ | — |
| Présence | ✅ | ✅ | ✅ | — |
| Notes/bulletins | ✅ | ✅ | ✅ | — |
| Portail parent (lecture) | ✅ | ✅ | ✅ | — |
| Dashboard admin | ✅ | ✅ (minimal mais réel) | ✅ | — |
| Email transactionnel | ✅ | ✅ (scope auth) | ✅ | — |
| **Rappel actif parent** | ❌ | — | ✅ (voir §6) | Non — c'est la Phase 11 proposée |
| Finance | ❌ | — | Non (voir §9) | Oui |
| Notifications in-app générales | ❌ | — | Non (voir §10) | Oui |
| Devoirs/emploi du temps | ❌ | — | Non (voir §8) | Oui |
| Audit logs | ❌ | — | Non (voir §15) | Oui |
| AI | ❌ | — | Non (voir §18) | Oui |
| Offline | ❌ | — | Non (voir §13) | Oui |

## 8. Gaps P0/P1/P2/P3

**P0** : aucun. Le pilote fonctionne déjà de bout en bout pour les trois acteurs.

**P1** :
- Notification email au parent à la publication d'un bulletin (voir §17 Candidat 1). *Impact* :
  seul mécanisme actuel capable de faire revenir un parent sans dépendre de sa propre initiative.
  *Fréquence* : à chaque publication de bulletin (récurrent, par trimestre/période).

**P2** :
- Notifications in-app générales (plus large, nouvelle table, complexité significativement plus
  élevée que le Candidat 1 pour un gain marginal supplémentaire à ce stade).
- Recherche globale (au-delà des élèves).
- Audit logs.
- Export élèves/rapports.
- Import enseignants en masse.
- Module finance interne.

**P3** :
- Devoirs, emploi du temps, offline mobile, IA, paiements Mobile Money, multi-campus/pays,
  white-label.

## 9. Finance

Toujours totalement absent (confirmé, aucun changement depuis les Discoveries précédentes).
Réponse à la question posée : **non, une école ne peut pas aujourd'hui gérer sa vie financière
sans quitter EduSphere** — mais ce n'est toujours pas ce qui manque le plus pour un premier
pilote. Le pilote sert à valider la valeur du cœur académique (présence/notes/bulletins) et,
désormais, à combler le déficit d'engagement parent — pas à remplacer un système de facturation
scolaire dès le premier déploiement. **Réponse : B — finance doit attendre une phase
ultérieure.** Si/quand elle redevient prioritaire, la séquence reste : module financier interne
(frais, factures, soldes) **avant** toute intégration Mobile Money — jamais l'inverse, pour des
raisons de complexité et de risque réglementaire déjà documentées dans les Discoveries
précédentes (Phases 9 et 10), inchangées.

## 10. Communication

- **Déjà utilisable** : `EmailProvider` (Phase 9), actuellement scopé exclusivement à
  l'authentification (invitation de compte, réinitialisation de mot de passe).
- **Ce qui manque** : tout usage de cette infrastructure pour une notification métier — c'est
  exactement le gap identifié en §6/§17.
- **Notifications in-app prioritaires ?** Pas maintenant — complexité nettement supérieure
  (nouvelle table, écran de liste, gestion lu/non lu) pour une valeur incrémentale plus faible
  qu'un simple email au bon moment, qui atteint le parent même s'il n'ouvre jamais l'app.
- **SMS nécessaires ?** Non pour ce pilote — l'email suffit tant que la majorité des tuteurs
  disposent d'une adresse email enregistrée (`Guardian.email`, déjà collectée depuis la Phase 3)
  ; le SMS est une extension future si le pilote révèle que l'email ne suffit pas (taux
  d'adresses email manquantes trop élevé en pratique).
- **Les emails suffisent-ils pour le pilote ?** Oui, pour le déclencheur identifié
  (publication de bulletin) — un événement peu fréquent, à fort signal, pour lequel un email
  est un canal approprié (pas besoin d'instantanéité comme le SMS/push).

## 11. Espace enseignant

Aucun changement depuis la Phase 10 Discovery. Dashboard enseignant toujours minimal (liste de
classes, pas de vue "aujourd'hui"), mais **ce n'est pas le plus gros obstacle** à un usage
quotidien — il n'y a pas d'obstacle bloquant identifié. Présence et notes, les deux tâches
critiques et récurrentes, fonctionnent bien. Devoirs et emploi du temps restent non nécessaires
maintenant, faute de signal réel d'un besoin non couvert.

## 12. Parent Experience

- **Fréquence d'utilisation actuelle** : dépend entièrement de l'initiative du parent — aucune
  donnée d'usage réel n'existe encore (aucun pilote n'a eu lieu), mais le mécanisme produit lui
  seul offre aujourd'hui zéro incitation à revenir.
- **Valeur actuelle une fois connecté** : réelle et complète (enfants, présence, notes,
  bulletins PDF).
- **Informations manquantes** : aucune information manque au contenu lui-même ; ce qui manque
  est le déclencheur qui ramène le parent au bon moment.
- **Notifications** : absentes, c'est le gap central de cette Discovery.
- **Communication** : absente, non bloquante pour l'instant (§10).
- **Frais scolaires/paiements** : absents, non prioritaires (§9).
- Conformément à la consigne, aucune fonctionnalité n'est ajoutée "juste pour enrichir" le
  parent mobile — le candidat retenu répond à un déficit d'engagement concret et mesurable en
  principe (le parent ne revient pas sans signal), pas à un enrichissement gratuit.

## 13. Mobile / Offline

Aucun changement depuis la Phase 10 Discovery. Parent et teacher mobile matures pour leurs
usages actuels. **Le pilote ne nécessite pas d'expérience offline maintenant** — aucun signal
d'un besoin réel (aucun pilote n'a encore eu lieu pour le confirmer), et l'investissement
(synchronisation, résolution de conflits) resterait disproportionné tant que la connectivité
n'a pas été identifiée comme un vrai point de friction par de vrais utilisateurs. Push
notifications : dépendraient d'une infrastructure de notification qui, avec le Candidat 1
proposé, resterait volontairement basée sur l'email (pas le push) pour cette phase — plus
simple, pas de nouvelle dépendance (Expo push nécessiterait une intégration dédiée), et
suffisant pour l'événement ciblé.

## 14. Import / Export

Aucun changement : import CSV/Excel élèves déjà existant et fonctionnel (Phase 3). Import
enseignants en masse toujours absent (confort, pas un blocage — la création un par un via le
wizard/la page Utilisateurs fonctionne). Aucun export (élèves, rapports) nulle part. Réponse à
la question posée : une école avec des données déjà existantes peut entrer ses élèves
rapidement (import déjà supporté) ; elle ne peut pas encore exporter quoi que ce soit
d'EduSphere. Impact sur le pilote : faible — l'entrée de données est le sens qui compte le plus
au démarrage d'un pilote, et il est déjà couvert pour le domaine le plus volumineux (élèves).

## 15. Audit / Traçabilité

Toujours totalement absent (aucun modèle). Non nécessaire avant un premier pilote réel — utile
pour la confiance/la conformité à plus long terme, mais rien dans le fonctionnement quotidien
actuel n'en dépend, et aucun incident n'a révélé de besoin de traçabilité rétroactive. P2,
inchangé par rapport aux Discoveries précédentes.

## 16. Sécurité

Aucun problème nouveau découvert cette phase. État confirmé, inchangé depuis la Phase 10.1 :
- Auth, RBAC, RLS, tenant/school isolation : solides, testés extensivement (135 tests pytest,
  19 tests Playwright couvrant explicitement l'isolation tenant à plusieurs niveaux).
- Rate limiting : login (Phase 7.2) et forgot-password (Phase 10.1), tous deux fail-open sur
  Redis indisponible, tous deux vérifiés réellement.
- Reset password / tokens email : expiration 30 minutes, usage unique, jamais stockés en clair
  (`token_hash`) — inchangé.
- `organizations` sans RLS et absence de contraintes CHECK en base restent les seuls points P2
  déjà notés par l'audit global (Phase 7.1), jamais corrigés car jamais bloquants — statut
  inchangé, toujours non urgents.
- **Aucun problème P0/P1 nouveau.**

## 17. Email transactionnel

- `EmailProvider` : ABC stable (`send(to, subject, body)`), `LocalEmailProvider` (dev/tests,
  écrit sur disque) et `SmtpEmailProvider` (bibliothèque standard uniquement) — inchangés depuis
  la Phase 9.
- Provider dev : `local`, comportement inchangé et sûr (rien n'est réellement envoyé).
- Provider production : `smtp`, configuré via variables d'environnement, toujours aucun
  fournisseur figé.
- Invitation et reset password : fonctionnent réellement, testés (Phase 9), désormais protégés
  par rate limiting (Phase 10.1).
- Tokens : expiration et usage unique inchangés, sécurité déjà auditée (Phase 9/10.1).
- URLs : construites côté serveur à partir de `public_web_base_url`, jamais d'entrée
  utilisateur.
- **Aucun gap ne bloque le pilote au niveau de l'infrastructure elle-même** — le seul gap réel
  est fonctionnel : cette infrastructure, déjà solide, n'est pas encore utilisée pour autre
  chose que l'authentification. C'est précisément ce que le Candidat 1 propose de combler, sans
  toucher à l'infrastructure elle-même (réutilisation pure).

## 18. AI / EDU AI

Recherche renouvelée : toujours aucune trace de code, d'abstraction, de dépendance ou de
configuration liée à l'IA nulle part dans le dépôt. Rien n'a changé depuis les Discoveries
précédentes. Elle n'existe pas, n'est pas utile aujourd'hui (aucun problème concret identifié
dans cette Discovery qu'elle résoudrait mieux qu'une fonctionnalité métier classique), et reste
nettement moins prioritaire que le déficit d'engagement parent identifié ici. **Documenté comme
futur, sans ambiguïté, pour la quatrième fois consécutive.**

## 19. White Label / Multi-Pays / Scale

Aucune fonctionnalité de ce type ne doit être construite maintenant (conforme à la consigne).
Évaluation architecturale uniquement : le modèle Organization → School (multi-tenant depuis la
Phase 1) supporte déjà nativement plusieurs écoles par organisation et plusieurs organisations
par plateforme — rien dans les phases récentes n'a introduit de couplage à un pays ou une
devise unique qui bloquerait une expansion future (`currency`/`timezone` sont déjà des champs
par école, pas des constantes globales). Aucune décision actuelle n'a été identifiée comme un
obstacle bloquant à l'expansion — pas de sur-architecture nécessaire ni à corriger.

## 20. Candidats

Maximum 5, issus de l'analyse ci-dessus.

### Candidat 1 — Notification email au parent : bulletin publié

#### Nom
Notification email — bulletin publié

#### Problème
Le parent ne reçoit aujourd'hui aucun signal quand un bulletin de son enfant est publié — il
doit se souvenir seul de vérifier l'application.

#### Utilisateurs concernés
Parents (destinataires), indirectement l'administration (valeur perçue du produit).

#### Valeur pilote
Élevée — seul mécanisme actuel capable de ramener activement un parent vers l'application, sans
lui demander une action préalable.

#### Fréquence d'utilisation
Une fois par publication de bulletin (par classe, par période académique) — peu fréquent mais à
fort signal, cohérent avec un canal email plutôt qu'un canal instantané.

#### Fonctionnalités IN
À la publication d'un bulletin (`POST /report-cards/{id}/publish`, déjà existant, inchangé),
envoi d'un email best-effort (même philosophie que Phase 9 — un échec d'envoi ne bloque jamais
la publication elle-même, déjà commitée) à chaque `Guardian.email` non nul lié à l'élève
concerné (via `StudentGuardian`, relation déjà existante).

#### Fonctionnalités OUT
SMS, push, notifications in-app, centre de notifications, préférences d'opt-out granulaires,
tout déclencheur autre que la publication d'un bulletin (pas de notification sur une note
individuelle, une absence, etc. — hors périmètre de cette phase).

#### Backend
Nouvel appel à `send_email_best_effort` (déjà existant, `app/core/email.py`) depuis le point où
`published_at` est renseigné (`report_cards/router.py::publish_report_card` ou
`report_cards/service.py`, à confirmer en planification détaillée). Récupération des
`Guardian.email` via la relation déjà existante `StudentGuardian`.

#### Frontend
Aucun changement nécessaire a priori — la publication reste le même bouton, le même appel API.
Un indicateur optionnel ("email envoyé à N tuteur(s)") pourrait être envisagé en planification
détaillée, sans être indispensable au périmètre minimal.

#### Mobile
Aucun changement.

#### DB / Migration
**Aucune** — aucune nouvelle table, `Guardian.email` et `ReportCard.published_at` existent déjà.

#### Dépendances
Aucune nouvelle — réutilisation stricte d'`EmailProvider` (Phase 9).

#### Sécurité
Aucune nouvelle surface : l'email envoyé ne contient pas le bulletin lui-même (juste un lien
vers l'application/le PDF déjà protégé par authentification, ou le code de vérification QR déjà
public par conception — Phase 5), pas de nouvelle donnée personnelle exposée au-delà de ce que
`Guardian.email` contient déjà. Isolation tenant héritée (l'agrégation reste par élève/école,
aucune requête cross-école).

#### Complexité
Faible.

#### Tests
Backend : la publication déclenche un envoi pour chaque tuteur avec email, aucun envoi pour un
tuteur sans email, aucun envoi en cas d'échec de publication, best-effort (panne d'envoi
n'empêche pas la publication). E2E : vérification via le mécanisme déjà établi
(`LocalEmailProvider` + lecture de fichier en test, cf. `test_email.py`).

#### Risques
Volume d'emails si beaucoup de bulletins sont publiés d'un coup (génération en masse déjà
existante peut publier plusieurs bulletins successivement) — mitigation : rester best-effort,
ne pas introduire de file d'attente pour cette phase (sur-ingénierie prématurée), réévaluer si
le volume réel du pilote le justifie.

---

### Candidat 2 — Notifications in-app (centre de notifications général)

#### Nom
Centre de notifications in-app

#### Problème
Aucun signal in-app pour aucun événement (bulletin, présence, etc.) — approche plus large que
le Candidat 1.

#### Utilisateurs concernés
Parents principalement, admin secondairement.

#### Valeur pilote
Moyenne — améliore l'engagement au-delà du seul événement "bulletin publié", mais chevauche
largement la valeur du Candidat 1 pour un coût de développement nettement supérieur.

#### Fréquence d'utilisation
Potentiellement plus fréquente que le Candidat 1 si étendue à plusieurs types d'événements —
mais cette extension elle-même n'est pas justifiée par un besoin observé.

#### Fonctionnalités IN
Table d'événements, liste in-app, marquage lu/non lu.

#### Fonctionnalités OUT
Email, SMS, push (dans un premier temps), préférences granulaires.

#### Backend / Frontend / Mobile
Nouveaux endpoints (création, liste, marquage lu), nouvel écran liste (web + mobile parent).

#### DB / Migration
**Oui** — nouvelle table d'événements/notifications, seul candidat de cette liste à en exiger
une.

#### Dépendances
Aucune externe.

#### Sécurité
Isolation tenant à vérifier soigneusement (un parent ne doit voir que ses propres événements).

#### Complexité
Moyenne à élevée (relativement aux autres candidats de cette liste).

#### Tests
Backend (déclenchement, isolation), frontend/E2E (affichage, marquage lu).

#### Risques
Périmètre qui s'élargit facilement (quels événements ? quelle fréquence ? quel design
d'écran ?) — risque de scope creep documenté explicitement.

---

### Candidat 3 — Recherche globale (au-delà des élèves)

#### Nom
Recherche globale admin

#### Problème
La recherche reste limitée aux élèves ; retrouver un utilisateur ou une classe exige de
naviguer manuellement.

#### Utilisateurs concernés
Admin.

#### Valeur pilote
Faible à moyenne — confort, pas de blocage identifié.

#### Fréquence d'utilisation
Occasionnelle.

#### Fonctionnalités IN
Extension de la recherche existante à `users` et `classes`.

#### Fonctionnalités OUT
Recherche plein texte avancée, indexation dédiée (Elasticsearch ou équivalent).

#### Backend / Frontend / Mobile
Extension de filtres déjà existants ; aucun changement mobile.

#### DB / Migration
Aucune a priori (filtres SQL sur des colonnes déjà indexées pour la plupart).

#### Dépendances
Aucune.

#### Sécurité
Aucun changement au-delà des permissions déjà en place.

#### Complexité
Faible à moyenne.

#### Tests
Tests de filtrage, isolation tenant.

#### Risques
Faibles.

---

### Candidat 4 — Import enseignants en masse

#### Nom
Import CSV enseignants

#### Problème
Créer plusieurs enseignants un par un reste lent pour une école de taille moyenne.

#### Utilisateurs concernés
Admin.

#### Valeur pilote
Faible — confort ponctuel (onboarding initial), valeur non récurrente une fois l'école
configurée.

#### Fréquence d'utilisation
Une fois par école, à la configuration initiale.

#### Fonctionnalités IN
Import CSV réutilisant le patron déjà existant (`students/import`).

#### Fonctionnalités OUT
Import de notes/présences en masse.

#### Backend / Frontend / Mobile
Nouvel endpoint d'import (ou boucle frontend sur `POST /users` existant), aucun changement
mobile.

#### DB / Migration
Aucune.

#### Dépendances
Aucune.

#### Sécurité
Aucun changement au-delà des contrôles déjà en place sur `POST /users`.

#### Complexité
Faible à moyenne.

#### Tests
Tests d'import (succès, doublons, erreurs partielles).

#### Risques
Faibles — mais valeur limitée à un usage ponctuel, pas quotidien.

---

### Candidat 5 — Audit logs

#### Nom
Journal d'audit administratif

#### Problème
Aucune traçabilité de qui a modifié quoi, ni quand.

#### Utilisateurs concernés
Admin/plateforme (confiance, conformité future).

#### Valeur pilote
Faible à court terme — utile pour la confiance à long terme, pas pour l'usage quotidien
immédiat.

#### Fréquence d'utilisation
Consultation occasionnelle (investigation), écriture continue en arrière-plan.

#### Fonctionnalités IN
Table d'événements d'audit sur les actions sensibles (création/modification d'utilisateur,
suppression, changement de rôle).

#### Fonctionnalités OUT
Interface de recherche avancée, alerting.

#### Backend / Frontend / Mobile
Middleware ou hooks d'écriture sur les actions sensibles ; écran de consultation minimal.

#### DB / Migration
**Oui** — nouvelle table.

#### Dépendances
Aucune.

#### Sécurité
Les logs eux-mêmes doivent être protégés (accès admin uniquement) et ne jamais contenir de
secret.

#### Complexité
Moyenne à élevée (décider quelles actions tracer sans sur-ingénierie).

#### Tests
Vérification que les actions sensibles sont bien tracées, isolation tenant des logs.

#### Risques
Périmètre qui s'élargit facilement ("quelles actions tracer ?") — risque de scope creep.

## 21. Matrice de priorisation

Méthode : `Score = Valeur×0,20 + Impact_quotidien×0,20 + Impact_utilisateur×0,15 +
Urgence×0,15 + Fréquence×0,15 − Complexité×0,10 − Risque×0,05` (formule proposée dans le brief,
adoptée telle quelle). Pondération : la valeur et l'impact quotidien pèsent le plus (0,20
chacun) car ce sont les meilleurs indicateurs d'un usage réel et soutenu ; impact utilisateur,
urgence et fréquence pèsent 0,15 chacun (importants mais secondaires à l'usage quotidien réel) ;
complexité pénalise davantage (0,10) que risque (0,05) car, à ce stade du produit, le temps de
développement est une contrainte plus immédiate que le risque technique (aucun candidat ici
n'est intrinsèquement risqué). Notes sur 10.

| Candidat | Valeur | Impact quotidien | Impact utilisateur | Urgence | Fréquence | Complexité | Risque | Score | Position |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1. Notification email bulletin publié | 7 | 5 | 8 | 6 | 6 | 2 | 2 | **5,10** | **1** |
| 2. Notifications in-app générales | 6 | 5 | 6 | 4 | 5 | 6 | 3 | 3,70 | 2 |
| 3. Recherche globale | 4 | 4 | 3 | 2 | 4 | 4 | 2 | 2,45 | 3 |
| 4. Import enseignants en masse | 3 | 1 | 2 | 2 | 1 | 3 | 2 | 1,15 | 4 (ex æquo) |
| 5. Audit logs | 4 | 1 | 2 | 2 | 1 | 5 | 2 | 1,15 | 4 (ex æquo) |

## 22. Phase 11 recommandée

**Candidat 1 — Notification email au parent : bulletin publié.**

**Pourquoi elle** : c'est le seul candidat qui s'attaque à un déficit d'engagement réel et
concret (le parent ne revient pas sans signal, §6/§12), identifié en simulant le parcours
complet plutôt qu'en listant des fonctionnalités isolément. Elle obtient le score le plus élevé
(5,10, nettement devant 3,70 pour le second) tout en restant la complexité la plus faible du
lot.

**Pourquoi maintenant** : l'infrastructure nécessaire (`EmailProvider`, `Guardian.email`,
`ReportCard.published_at`) existe déjà intégralement — c'est une pure réutilisation, pas une
nouvelle construction. Après six phases consécutives centrées sur l'administrateur, c'est aussi
le moment naturel de redresser l'équilibre vers les acteurs sous-servis (enseignant déjà bien
couvert, parent qui ne l'est pas encore activement).

**Pourquoi pas les autres maintenant** :
- Notifications in-app (Candidat 2) : chevauche largement la valeur du Candidat 1 pour une
  complexité near-double (nouvelle table, écran, gestion lu/non lu) — mieux vaut valider
  d'abord la valeur du signal le plus simple (email) avant d'investir dans un centre de
  notifications généraliste.
- Recherche globale, import enseignants, audit logs (Candidats 3-5) : tous confortés comme P2,
  valeur ponctuelle ou non-quotidienne, scores nettement inférieurs.
- Finance, IA, offline, devoirs/emploi du temps : explicitement évalués et écartés (§9, §13,
  §18, §11) — aucun signal réel n'en justifie la priorité maintenant.

**Ce qui serait perdu en la retardant** : le pilote démarrerait avec un portail parent
fonctionnel mais silencieux — la meilleure fonctionnalité déjà construite (bulletins PDF,
Phase 7.1) resterait sous-exploitée faute de rappel actif, risquant de sous-estimer la valeur
réelle du produit auprès des familles pendant la fenêtre d'évaluation du pilote.

## 23. Scope IN

À la publication d'un bulletin (`POST /report-cards/{id}/publish`, endpoint et logique déjà
existants, inchangés), envoi d'un email best-effort à chaque `Guardian.email` non nul lié à
l'élève concerné, réutilisant `EmailProvider`/`send_email_best_effort` (Phase 9) tel quel.

## 24. Scope OUT

SMS, push, notifications in-app, centre de notifications, préférences d'opt-out, tout
déclencheur autre que la publication de bulletin, dashboard, finance, paiements, IA, offline,
devoirs, emploi du temps, recherche globale, import en masse, audit logs, refactoring général,
toute modification du flux de génération/publication de bulletin au-delà de l'ajout de l'envoi
d'email.

## 25. Architecture proposée (pour approbation future, rien exécuté)

- **Backend** : point d'ajout probable dans `report_cards/service.py` ou `report_cards/router.py`
  au moment où `published_at` est renseigné — à trancher précisément en planification détaillée
  (préférence probable pour le service, cohérent avec le patron déjà établi de garder la
  logique métier hors du routeur quand elle dépasse une ligne).
- **API** : aucun nouvel endpoint, aucun changement de contrat sur `POST /report-cards/{id}/publish`.
- **Services** : réutilisation de `send_email_best_effort` (`app/core/email.py`), nouvelle
  requête pour récupérer les `Guardian.email` liés à l'élève via `StudentGuardian`.
- **Modèles** : aucun changement.
- **DB / migration** : aucune.
- **Frontend** : aucun changement obligatoire (voir §20 Candidat 1, indicateur optionnel non
  indispensable).
- **Mobile** : aucun changement.
- **Permissions** : aucune nouvelle — l'envoi est un effet de bord de la publication, déjà
  protégée par `report_cards.manage`.
- **Sécurité** : best-effort (jamais bloquant), pas de nouvelle donnée personnelle exposée.
- **Tests** : backend (déclenchement par tuteur avec email, absence d'envoi sans email, non-
  blocage en cas d'échec), cohérents avec les conventions déjà établies (`test_email.py`).
- **E2E** : vérification via `LocalEmailProvider` + lecture de fichier, même patron que la
  Phase 9.
- **Performance** : un envoi par tuteur par bulletin publié, best-effort, pas de file d'attente
  pour ce périmètre (voir §20 Candidat 1, Risques).

## 26. Plan d'implémentation (indicatif, non exécuté)

1. Localiser précisément le point de publication (`report_cards/service.py` probable) et y
   ajouter la récupération des tuteurs avec email + l'appel `send_email_best_effort` par tuteur.
2. Vérifier qu'un échec d'envoi n'empêche jamais la publication de se terminer (transaction déjà
   commitée avant l'envoi, comme pour les emails d'authentification en Phase 9).
3. Tests backend + E2E.

## 27. Plan de tests (indicatif)

Backend : publication déclenche un envoi par tuteur avec email (contenu contient le nom de
l'élève et une référence au bulletin), aucun envoi pour un tuteur sans email, panne d'envoi
n'empêche pas la publication (best-effort), isolation tenant (les tuteurs d'un autre élève/école
ne reçoivent jamais rien). E2E : publication réelle via l'UI, vérification qu'un email a été
"envoyé" (`LocalEmailProvider`).

## 28. Critères d'acceptation (indicatifs)

- Publier un bulletin envoie réellement un email à chaque tuteur ayant une adresse enregistrée.
- Un tuteur sans email n'entraîne ni erreur ni blocage.
- Une panne d'envoi n'empêche jamais la publication de réussir.
- Aucune régression : pytest, ruff, mypy, Playwright existants tous verts.
- Aucune migration, aucune nouvelle dépendance.

## 29. Risques

| Risque | Probabilité | Impact | Mitigation |
|---|---|---|---|
| Volume d'emails lors d'une publication en masse (plusieurs bulletins d'un coup) | Moyenne | Faible (coût, pas de panne) | Rester best-effort, réévaluer une file d'attente seulement si le volume réel du pilote le justifie |
| Scope creep vers un centre de notifications complet | Moyenne (déjà proposé 3 fois dans des Discoveries précédentes) | Moyen (retarderait la livraison) | Périmètre strictement limité au Scope IN (§23), Candidat 2 explicitement documenté comme hors périmètre |
| Adresses `Guardian.email` manquantes en pratique | Inconnue (dépend des données réelles du pilote) | Moyen (réduit la portée du bénéfice) | Mesurable dès le premier pilote ; justifierait alors d'évaluer un canal SMS complémentaire dans une phase ultérieure |
| Risque sécurité/données personnelles | Faible | Faible | Aucune nouvelle donnée exposée au-delà de ce que `Guardian.email` contient déjà ; email ne contient pas le contenu du bulletin lui-même |

## 30. Conditions GO / NO-GO

**GO** — infrastructure entièrement déjà construite (Phase 9), complexité la plus faible de
tous les candidats évalués, score de priorisation le plus élevé, aucune dépendance bloquante,
répond à un déficit d'engagement réel identifié en simulant le parcours complet du parent.

**NO-GO / à requalifier** uniquement si le pilote prévu ne prévoit aucun compte parent actif
(scénario peu probable, le portail parent étant déjà un livrable central du produit depuis la
Phase 7).

---

# PHASE 11 DISCOVERY COMPLETE

Recommended Phase 11:
Notification email au parent — bulletin publié

Why:
Après six phases consécutives centrées sur l'administrateur, le parent reste le seul acteur sans
aucun mécanisme actif le ramenant vers l'application — l'infrastructure nécessaire
(EmailProvider, Guardian.email, ReportCard.published_at) existe déjà intégralement depuis les
Phases 3/5/9, il ne manque qu'une réutilisation ciblée.

Primary user:
Parent (destinataire), valeur indirecte pour l'administration (engagement perçu du produit)

Pilot value:
Seul mécanisme actuel capable de faire revenir un parent vers l'application sans dépendre de sa
propre initiative, au moment précis où une information réelle et attendue existe.

Priority:
P1

Complexity:
Faible

Main risks:
Volume d'emails en cas de publication en masse (mitigé par une approche best-effort, sans file
d'attente pour ce périmètre) ; tentation de scope creep vers un centre de notifications complet
(déjà proposé et repoussé trois fois), explicitement exclu du périmètre.

Scope:
Envoi d'un email best-effort à chaque tuteur ayant une adresse enregistrée, déclenché
uniquement par la publication d'un bulletin déjà existante — aucune nouvelle table, aucun
nouvel endpoint, aucune nouvelle dépendance.

GO / NO-GO:
GO

WAITING FOR APPROVAL
