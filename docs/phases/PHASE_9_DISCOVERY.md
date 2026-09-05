# PHASE 9 DISCOVERY

Document d'audit uniquement. Aucun code modifié, aucune migration créée, aucune donnée touchée.

## 1. Executive Summary

Depuis la Phase 8 Discovery, deux choses ont changé concrètement : l'assistant de mise en place
existe et fonctionne (Phase 8), et le parcours d'inscription publique mène désormais réellement
au dashboard et au wizard pour un nouvel administrateur (Phase 8.1 a corrigé la détermination du
contexte école). **Le socle métier reste exactement ce qu'il était** : présence, notes,
bulletins, portail parent mobile sont solides et n'ont pas bougé.

Concrètement, une école peut maintenant, de bout en bout et sans intervention technique
extérieure : s'inscrire, se configurer via le wizard, et faire fonctionner le cycle
présence/notes/bulletins/consultation parent au quotidien pour son **administrateur et ses
enseignants**. Le maillon qui reste cassé est la **distribution des comptes** : un
enseignant ou un parent créé par l'admin ne peut aujourd'hui recevoir ses identifiants que si
quelqu'un lit manuellement un jeton affiché en clair dans l'écran d'administration
(`dev_reset_token`) et le lui transmet hors application. Ce problème était déjà identifié en
Phase 8 Discovery (Candidat 2, différé) — il n'a pas été traité depuis, et il est maintenant
littéralement la seule chose qui empêche le reste du produit (déjà construit, déjà testé) d'être
utilisé par autre chose qu'une poignée d'utilisateurs accompagnés à la main.

**Recommandation : Phase 9 = infrastructure d'email transactionnel minimale**, strictement
limitée à l'invitation de compte et la réinitialisation de mot de passe (pas d'annonces, pas de
messagerie, pas de notifications métier). Voir §17.

## 2. État réel du dépôt

- Toujours pas de `CLAUDE.md`, toujours pas de dépôt Git initialisé (la CI GitHub Actions n'a
  donc toujours jamais tourné réellement).
- `apps/api/app/modules/` : toujours 11 modules (`academics`, `attendance`, `auth`, `grades`,
  `organizations`, `parent`, `rbac`, `report_cards`, `schools`, `students`, `users`) — **aucun
  nouveau module backend** depuis la Phase 8 Discovery. Confirmé par recherche : toujours aucune
  trace de `fee`/`invoice`/`payment`/`receipt` dans `apps/api/app`, et toujours aucune trace de
  `AI`/IA/LLM nulle part dans le dépôt applicatif.
- `apps/api/alembic/versions/` : toujours 8 migrations (`0001`→`0008`), inchangé — confirme que
  les Phases 8 et 8.1 n'ont réellement rien touché en base.
- `apps/api/tests/` : toujours 15 fichiers, 114 tests (inchangé, Phases 8/8.1 sont 100%
  frontend).
- `apps/web/app/(app)/` : un nouvel écran `setup/` (le wizard, Phase 8) et `AuthGate.tsx` modifié
  (Phase 8.1). Le dashboard (`(app)/page.tsx`) est **toujours** un message de bienvenue statique
  + un seul lien — relu ligne à ligne, rien n'a changé depuis la Phase 8 Discovery.
- `apps/web/e2e/` : 3 fichiers maintenant (`smoke.spec.ts`, `setup-wizard.spec.ts`,
  `admin-onboarding.spec.ts`, 12 tests au total) — tous exécutés réellement pendant les Phases 8
  et 8.1, tous verts. **Mais toujours absents de la CI** : `.github/workflows/ci.yml` ne fait
  tourner, côté web, que lint/type-check/build — aucun job n'exécute Playwright. Comme la CI ne
  tourne de toute façon jamais (pas de Git), l'impact réel est nul aujourd'hui, mais c'est une
  dette qui deviendra réelle dès qu'un dépôt Git existera.
- `apps/mobile/app/` : inchangé depuis la Phase 8 Discovery — espace `(teacher)` complet
  (classes, présences, évaluations, notes), espace `(parent)` en lecture seule. Aucun écran
  admin/staff sur mobile.
- `docs/` : 3 nouveaux documents de phase (8, 8 Implementation, 8.1), le reste inchangé
  (`docs/architecture/overview.md` toujours limité à la Phase 0, `docs/api/` et `docs/product/`
  toujours vides).
- `README.md` : toujours désynchronisé (annonce "phases 0 à 5"), non corrigé depuis la Phase 8
  Discovery où ce constat avait déjà été fait.

## 3. Matrice fonctionnelle

Reprend la matrice de la Phase 8 Discovery, mise à jour uniquement là où l'état a changé.

| Domaine | Complet | Partiel | Absent | État réel | Valeur pilote | Priorité |
|---|:---:|:---:|:---:|---|---|---|
| Onboarding (register→wizard) | ✅ | | | **Changé** — fonctionne réellement de bout en bout depuis 8.1 | — | — |
| Dashboard | | ✅ | | **Inchangé** — page statique, aucune métrique | Moyenne | P2 |
| School settings/branding | | ✅ | | Inchangé (logo, infos de base) | Faible | P3 |
| Academic setup | ✅ | | | Inchangé, mais désormais guidé par le wizard | — | — |
| Students (CRUD/import/guardians/docs) | ✅ | | | Inchangé, solide | — | — |
| Attendance | ✅ | | | Inchangé, solide (web + mobile enseignant) | — | — |
| Grades | ✅ | | | Inchangé, solide (web + mobile enseignant) | — | — |
| Report cards + QR | ✅ | | | Inchangé, solide, sécurisé (Phase 7.2) | — | — |
| Parent portal (mobile + web verify) | ✅ | | | Inchangé, lecture seule fonctionnelle | — | — |
| **User invitation / distribution de comptes** | | ✅ | | **Inchangé depuis Phase 8 Discovery — toujours `dev_reset_token` affiché en clair, toujours aucun email** | **Élevée** | **P0/P1 — voir §14** |
| Communication / notifications | | | ✅ | Toujours absent (aucun modèle) | Moyenne | P2 |
| Finance / fees / paiements | | | ✅ | Toujours absent (aucun modèle, confirmé par recherche) | Faible pour un premier pilote | P2/P3 |
| Timetable | | | ✅ | Toujours absent | Faible/Moyenne | P3 |
| Assignments/homework | | | ✅ | Toujours absent | Faible | P3 |
| Search (globale) | | ✅ | | Toujours limité à la recherche élèves | Faible | P3 |
| Audit logs | | | ✅ | Toujours absent | Faible/Moyenne | P2 |
| Mobile offline | | | ✅ | Toujours absent | Faible pour un premier pilote — voir §11 | P3 |
| AI | | | ✅ | Toujours totalement absent, aucune trace dans le dépôt | Nulle actuellement | Hors périmètre |
| CI réelle (Git + Playwright) | | ✅ | | Playwright existe et passe en local, mais n'est dans aucun pipeline ; la CI elle-même ne tourne jamais (pas de Git) | Faible pour un pilote, réelle pour la suite | P2 (dette) |

## 4. Parcours admin

Connexion → dashboard (fonctionne, mais n'affiche rien d'utile) → gestion utilisateurs
(fonctionne pour CRÉER un compte, **casse immédiatement après** : impossible de transmettre les
identifiants sans sortir de l'application) → suivi élèves/présences/notes/bulletins (tout
fonctionne, écrans de gestion complets) → communication (n'existe pas) → rapports (n'existent
pas au-delà des panneaux de stats par classe déjà présents dans Notes/Présences).

**Point de rupture identifié** : la création d'un compte utilisateur est un cul-de-sac
fonctionnel pour l'admin — il obtient un jeton technique à copier-coller manuellement, ce que
personne ne fera de façon fiable pour plus de quelques comptes.

## 5. Parcours enseignant

Connexion (mobile) → voir ses classes → prendre les présences → saisir les notes → consulter les
informations nécessaires : **tout fonctionne**, testé réellement en Phase 6/Phase 8. Pas de
devoirs/travail à donner (absent, cohérent avec le périmètre produit actuel). Le seul point de
friction en amont : comment cet enseignant reçoit-il ses identifiants au départ ? Même point de
rupture qu'en §4.

## 6. Parcours parent

Connexion (mobile) → voir ses enfants → présence → notes → bulletins (PDF) : **tout fonctionne**,
testé réellement en Phase 7/7.1. Pas de notifications — le parent doit penser à ouvrir
l'application. Même point de rupture qu'en §4 pour l'obtention initiale du compte.

## 7. Gaps

**P0 — bloque un pilote réel avec un effectif normal** (au-delà d'une poignée de comptes
accompagnés à la main) :
- Distribution des comptes enseignants/parents (dev_reset_token, voir §14).

**P1 — fortement recommandé avant pilote** :
- Aucun autre gap n'atteint ce niveau. Le socle métier (présence/notes/bulletins/parent) est
  déjà au niveau P1 validé lors des phases précédentes.

**P2 — amélioration importante mais non bloquante** :
- Dashboard opérationnel (métriques réelles).
- Communication/notifications de base.
- Audit logs.
- Finance/fees (module interne, avant toute intégration de paiement).
- CI réelle (Git + Playwright dans le pipeline).

**P3 — futur** :
- Timetable, assignments/homework, recherche globale, offline mobile, IA, paiements Mobile
  Money, multi-campus.

## 8. Dette UX

- Dashboard sans valeur informative — un directeur d'école n'a aucune vue d'ensemble sans
  naviguer manuellement dans chaque module.
- Distribution de comptes non professionnelle (jeton technique visible à l'écran) — mauvaise
  première impression pour un pilote avec de vrais utilisateurs non techniques.
- Aucune notification — l'engagement parent dépend entièrement de leur initiative à ouvrir
  l'app.

## 9. Dette technique

- README toujours désynchronisé (déjà noté, jamais corrigé).
- Playwright non intégré à la CI (nouveau constat cette phase — la CI ne le faisait pas avant
  non plus, mais il n'y avait pas encore de suite Playwright à intégrer).
- Pas de dépôt Git — la CI n'a jamais tourné une seule fois depuis la Phase 0.
- Pagination absente sur les listes volumineuses (`students`, déjà noté en Phase 8 Discovery,
  toujours vrai).

## 10. Sécurité

Rien de nouveau détecté par cette discovery au-delà de ce qui était déjà connu (Phase 7.2, Phase
8 Discovery §5). Le point le plus pertinent pour Phase 9 : tant que la distribution de comptes
repose sur un jeton affiché en clair et transmis hors bande, il existe un risque opérationnel
(un admin pourrait être tenté de transmettre ce jeton par un canal non sécurisé — SMS en clair,
email non chiffré vers une adresse tierce, etc.) — pas une vulnérabilité du code lui-même, mais
un risque de processus que corrige indirectement une vraie infrastructure d'email avec des liens
à usage unique et expiration (déjà en place côté backend — `PasswordResetToken` a une expiration
de 30 minutes, `app/modules/users/service.py:19,66`).

## 11. Mobile

- **Teacher mobile** : mature, réellement utilisé et testé (Phase 6/8). Aucun gap critique.
- **Parent mobile** : mature pour un usage en lecture seule (Phase 7/7.1). Aucun gap critique.
- **Besoin réel d'un teacher mobile plus riche** (devoirs, communication) : pas justifié
  maintenant — aucun signal qu'il manque à un usage quotidien de base.
- **Offline** : aucune dépendance technique en place (pas de cache local, pas de queue de
  synchronisation, pas de résolution de conflits). L'évaluer honnêtement : un premier pilote se
  déroule typiquement dans un établissement qui a déjà accepté d'essayer un outil numérique — une
  connectivité au moins intermittente est une hypothèse raisonnable à ce stade. Construire de
  l'offline maintenant serait un investissement lourd (queue de synchronisation, résolution de
  conflits, tests de bout en bout beaucoup plus complexes) pour un besoin non confirmé par un
  usage réel. **Pas justifié pour Phase 9** — à réévaluer après un premier pilote si la
  connectivité s'avère être un vrai point de friction rapporté par les utilisateurs.

## 12. Finance

Complètement absent (confirmé par recherche dans tout `apps/api/app` — aucune trace de
fee/invoice/payment/receipt). Évaluation :
- Importance pour un premier pilote : réelle à moyen terme (les écoles se soucient des frais de
  scolarité), mais **pas bloquante** pour valider la valeur du produit sur son cœur actuel
  (vie académique quotidienne). Une école pilote peut très bien continuer à gérer ses frais par
  ses moyens existants pendant que le pilote évalue le reste.
- Paiement Mobile Money : hors de portée immédiate — complexité et risque réglementaire élevés,
  explicitement à éviter tant que le besoin n'est pas confirmé par un pilote réel.
- Un module financier **interne** (frais, factures, sans intégration de paiement) serait la
  bonne séquence si/quand ce domaine devient prioritaire — mais rien dans l'état actuel du
  produit ne justifie de le faire maintenant plutôt que de débloquer la distribution de comptes.
- **Conclusion : P2/P3, pas Phase 9.**

## 13. AI

Aucune trace de code, d'abstraction, ni de dépendance liée à l'IA nulle part dans le dépôt.
Rien à auditer de plus concret qu'une absence totale. Évaluation : l'IA n'apporte aujourd'hui
aucune valeur pilote supérieure aux gaps identifiés — le produit n'a même pas encore résolu la
distribution de comptes à ses utilisateurs de base. **Hors périmètre, sans ambiguïté.**

## 14. dev_reset_token

- **Où ça en est** : inchangé depuis la Phase 8 Discovery. `POST /users` renvoie toujours
  `dev_reset_token` en clair (`apps/api/app/modules/users/service.py:70`), affiché tel quel dans
  l'écran web (`apps/web/app/(app)/users/page.tsx:144-152`).
- **Impact réel sur le pilote** : c'est maintenant, après la Phase 8.1, le **seul** obstacle
  restant entre "le produit fonctionne bien pour un administrateur" et "le produit fonctionne
  bien pour toute l'école" (enseignants + parents). Tout le reste de la chaîne (présence, notes,
  bulletins, consultation parent) est déjà construit et déjà testé — seul l'accès initial des
  comptes est cassé.
- **Priorité** : **P0 pour un pilote à effectif réel** (au-delà d'une poignée de comptes gérés à
  la main par l'équipe EduSphere) ; P1 si le premier pilote reste volontairement très restreint
  (quelques enseignants, accompagnement manuel possible pendant une courte période).
- **Doit-il devenir Phase 9 ?** Oui — c'est la recommandation de ce document (§17). C'est un
  problème borné, déjà entièrement caractérisé (aucune nouvelle investigation nécessaire),
  directement dans la continuité logique des Phases 8/8.1 (l'onboarding admin fonctionne,
  l'onboarding du reste de l'école ne fonctionne pas).

## 15. Candidats Phase 9

### Candidat 1 — Infrastructure d'email transactionnel (invitation + reset password)

## Nom
Comptes utilisateurs : invitation par email réelle

## Problème résolu
`dev_reset_token` affiché en clair, aucun moyen pour un enseignant/parent de recevoir ses
identifiants sans intervention manuelle hors application.

## Valeur pour l'école
Élevée et immédiate — débloque l'usage réel du produit par tout le personnel et les familles,
pas seulement par l'administrateur.

## Utilisateurs concernés
Admin (qui invite), enseignants, parents, staff — tous les rôles non-admin.

## Fonctionnalités IN
Envoi d'un email à la création d'un compte (lien de définition de mot de passe), envoi d'un
email pour `forgot-password` (remplace le `dev_token` par un vrai envoi hors environnement dev),
templates minimalistes (texte + lien), configuration via variables d'environnement (fournisseur
SMTP ou API, sans figer de choix commercial définitif).

## Fonctionnalités OUT
SMS, notifications push, tout système de templates avancé, communication/annonces, file
d'attente de emails à grande échelle, tracking d'ouverture.

## Données concernées
`PasswordResetToken` (déjà existant, réutilisé tel quel — expiration déjà en place). Aucune
nouvelle donnée métier.

## Endpoints existants réutilisables
`POST /users` (création + token, déjà en place), `POST /auth/forgot-password`,
`POST /auth/reset-password` (déjà en place) — le changement est **où le jeton part**, pas
l'API elle-même.

## Nouveaux endpoints nécessaires
Aucun changement de contrat d'API a priori — remplacement de l'implémentation qui produit
`dev_reset_token`/`dev_token` par un envoi réel (au lieu de, ou en plus de, le retourner dans la
réponse hors environnement de production).

## Migration nécessaire ?
Non.

## Dépendances
Un service d'envoi d'email (nouvelle dépendance externe — SMTP ou API d'un fournisseur), un
nouveau secret à gérer (`.env`).

## Risques
Délivrabilité (spam), dépendance à un service tiers, coût (même minime), configuration
différente dev/production à documenter clairement (cohérent avec le principe déjà appliqué pour
`dev_reset_token`/`dev_token`, qui distingue déjà l'environnement).

## Complexité
Moyenne.

## Tests nécessaires
Tests d'intégration avec un service d'envoi mocké/intercepté (convention à établir, cohérente
avec l'absence de mock ailleurs dans le projet — probablement un « fake » d'envoi en test,
comme `dev_reset_token` le fait déjà implicitement), tests de bout en bout du flux
invitation → email → définition de mot de passe → connexion.

## Impact sur mobile
Aucun changement de code mobile nécessaire — les écrans de connexion existants restent
identiques, seul le mécanisme d'obtention du mot de passe initial change.

## Impact sur sécurité
Positif : supprime un jeton actuellement exposé côté client ; ajoute une dépendance externe à
sécuriser (secrets SMTP/API, jamais committés — cohérent avec les conventions déjà en place).

---

### Candidat 2 — Tableau de bord opérationnel

## Nom
Dashboard avec métriques réelles

## Problème résolu
La page d'accueil n'affiche aucune information utile — aucun signal de valeur immédiat pour un
directeur d'école.

## Valeur pour l'école
Moyenne — utile pour convaincre pendant le pilote, mais rien ne cesse de fonctionner si absent.

## Utilisateurs concernés
Admin, direction.

## Fonctionnalités IN
Effectif élèves, taux de présence récent, complétude de saisie des notes, nombre de bulletins
publiés — agrégations sur des données déjà existantes.

## Fonctionnalités OUT
Graphiques historiques multi-années, exports, analytics avancées, comparaisons inter-écoles.

## Données concernées
Aucune nouvelle — lecture agrégée de `students`, `attendance_records`, `assessment_results`,
`report_cards`.

## Endpoints existants réutilisables
Listes déjà existantes (`/students`, `/attendance-records`, `/results`, `/report-cards`) — un
calcul d'agrégation pourrait rester côté frontend pour un premier jet, ou nécessiter un
endpoint de synthèse dédié pour éviter de rapatrier des volumes complets.

## Nouveaux endpoints nécessaires
Probable : un endpoint de synthèse par école (à justifier précisément en phase de planification
détaillée si le calcul côté frontend s'avère trop coûteux en requêtes).

## Migration nécessaire ?
Non.

## Dépendances
Aucune.

## Risques
Faibles.

## Complexité
Faible.

## Tests nécessaires
Tests des agrégations (nouveaux, si un endpoint dédié est créé) ; tests frontend/E2E d'affichage.

## Impact sur mobile
Aucun.

## Impact sur sécurité
Aucun — lecture seule de données déjà accessibles à l'admin.

---

### Candidat 3 — Notifications in-app basiques

## Nom
Centre de notifications minimal (in-app, pas email/SMS/push)

## Problème résolu
Aucun signal quand un événement pertinent se produit (bulletin publié, absence enregistrée) —
l'utilisateur doit vérifier activement.

## Valeur pour l'école
Moyenne — améliore l'engagement, ne débloque rien de cassé.

## Utilisateurs concernés
Parents principalement, admin secondairement.

## Fonctionnalités IN
Une liste d'événements en base, consultable dans l'app (web + mobile), pas de canal externe.

## Fonctionnalités OUT
Email, SMS, push, préférences de notification granulaires, communication bidirectionnelle.

## Données concernées
**Nouvelle table nécessaire** (événements/notifications) — seul candidat des quatre à en
requérir une.

## Endpoints existants réutilisables
Aucun directement — les événements déclencheurs existent déjà (publication de bulletin,
enregistrement de présence) mais rien ne les capture actuellement.

## Nouveaux endpoints nécessaires
Oui — création + liste + marquage lu, a minima.

## Migration nécessaire ?
**Oui.**

## Dépendances
Aucune externe.

## Risques
Complexité de décider quels événements déclenchent une notification sans sur-ingénierie.

## Complexité
Moyenne.

## Tests nécessaires
Tests backend (création d'événement sur déclencheur, isolation tenant), tests frontend/E2E.

## Impact sur mobile
Écran(s) nouveaux côté parent mobile.

## Impact sur sécurité
Isolation tenant à vérifier soigneusement (un parent ne doit voir que les événements de ses
propres enfants).

---

### Candidat 4 — Import en masse enseignants/classes (extension de l'esprit du wizard)

## Nom
Import CSV enseignants (et affectations) — symétrique à l'import élèves déjà existant

## Problème résolu
Créer plusieurs enseignants un par un via le wizard/la page Utilisateurs reste lent pour une
école de taille moyenne.

## Valeur pour l'école
Faible à moyenne — confort, pas un blocage (le flux un-par-un fonctionne déjà, y compris via le
wizard).

## Utilisateurs concernés
Admin uniquement.

## Fonctionnalités IN
Import CSV réutilisant le composant déjà existant côté élèves (`StudentImportForm.tsx` comme
référence de patron UI), création de comptes en masse via `POST /users` existant.

## Fonctionnalités OUT
Import de notes/présences en masse, mapping de colonnes avancé.

## Données concernées
Aucune nouvelle.

## Endpoints existants réutilisables
`POST /users` (appelé en boucle) — le patron `POST /students/import` montre déjà comment un
import en masse a été construit dans ce projet (`apps/api/app/modules/students/router.py:166`,
`StudentImportReport`).

## Nouveaux endpoints nécessaires
Potentiellement un endpoint d'import dédié (comme pour les élèves) plutôt qu'une boucle
d'appels individuels côté frontend, pour un rapport d'erreurs cohérent.

## Migration nécessaire ?
Non.

## Dépendances
Aucune.

## Risques
Faibles — mais **n'a de valeur réelle que si le Candidat 1 est déjà fait** : importer 30
enseignants en masse ne sert à rien tant qu'aucun d'eux ne peut recevoir ses identifiants.

## Complexité
Faible à moyenne.

## Tests nécessaires
Tests d'import (succès, doublons, erreurs partielles), cohérents avec les tests d'import élèves
existants.

## Impact sur mobile
Aucun.

## Impact sur sécurité
Aucun changement au-delà des contrôles déjà en place sur `POST /users`.

## 16. Matrice de priorisation

Échelle 1 (faible) à 5 (élevé) pour Valeur/Urgence ; 1 (élevé) à 5 (faible) pour
Complexité/Risque (inversées pour que Score = somme favorise le meilleur compromis).

| Candidat | Valeur | Urgence | Complexité (inv.) | Risque (inv.) | Score | Position |
|---|---:|---:|---:|---:|---:|---:|
| 1. Email transactionnel | 5 | 5 | 3 | 3 | **16** | **1** |
| 2. Dashboard opérationnel | 3 | 2 | 4 | 5 | 14 | 2 |
| 4. Import enseignants en masse | 2 | 1 | 4 | 5 | 12 | 3 |
| 3. Notifications in-app | 3 | 2 | 3 | 3 | 11 | 4 |

Logique : le Candidat 1 obtient le score le plus élevé malgré une complexité et un risque
légèrement supérieurs aux autres (dépendance externe), parce que c'est le seul candidat dont
l'urgence est réellement maximale (bloque l'usage du produit par la majorité des utilisateurs
finaux, pas juste un confort) — et parce que le Candidat 4 n'a de sens qu'après lui.

## 17. Phase 9 recommandée

**Candidat 1 — Infrastructure d'email transactionnel (invitation de compte + réinitialisation de
mot de passe), strictement limitée à cet usage.**

Réponse à la question posée : ce n'est pas la fonctionnalité la plus technique ni la plus
visible, mais c'est ce qui permet à tout ce qui est **déjà construit et déjà testé**
(présence, notes, bulletins, portail parent) d'atteindre réellement les enseignants et les
parents d'une école pilote, chaque semaine, sans accompagnement manuel permanent de l'équipe
EduSphere.

## 18. Scope IN

- Envoi d'email réel à la création d'un compte (`POST /users`) hors environnement de
  développement, remplaçant l'exposition de `dev_reset_token`.
- Envoi d'email réel pour `forgot-password`, remplaçant `dev_token`.
- Configuration du fournisseur d'envoi via variables d'environnement, sans engagement commercial
  figé.
- Templates texte minimalistes.

## 19. Scope OUT

SMS, push, notifications métier (bulletin publié, absence), messagerie/annonces, dashboard,
import en masse, finance, paiements, IA, offline, refactoring général de `auth`, nouvelle
architecture de communication généraliste. Rien de ce qui est listé ici ne doit entrer dans
Phase 9 — candidats pour des phases ultérieures distinctes si confirmés par le pilote.

## 20. Dépendances

Un service d'envoi d'email (fournisseur SMTP ou API — décision à prendre en phase de
planification détaillée, pas ici), un nouveau secret dans `.env.example`.

## 21. Plan d'implémentation (proposition, non exécutée)

- Backend : remplacer la production de `dev_reset_token`/`dev_token` par un envoi réel dans
  `apps/api/app/modules/users/service.py` et `apps/api/app/modules/auth/service.py`, derrière
  une interface d'envoi minimale (cohérent avec le patron déjà utilisé pour `StorageProvider` —
  abstraction simple, implémentation locale/dev vs réelle).
- Frontend : retirer l'affichage de `dev_reset_token` dans `apps/web/app/(app)/users/page.tsx`
  hors contexte de développement (ou le conserver uniquement en dev, comme aujourd'hui pour le
  `dev_token` de `forgot-password`).
- DB : aucune migration.
- Tests : tests backend avec un envoi intercepté/fake ; test E2E du flux complet (créer un
  compte → « recevoir » le lien dans l'environnement de test → définir le mot de passe → se
  connecter).
- Mobile : aucun changement de code attendu.

## 22. Plan de tests (proposition)

Backend : création de compte déclenche un envoi (vérifié via l'interface d'envoi interceptée),
`forgot-password` déclenche un envoi, expiration du lien toujours respectée (comportement déjà
existant, à préserver). Frontend/E2E : le flux complet fonctionne réellement de bout en bout en
environnement de test.

## 23. Critères d'acceptation (proposition)

- Un compte créé via `POST /users` ne renvoie plus de jeton exploitable directement dans la
  réponse API hors développement.
- Un enseignant/parent peut définir son mot de passe et se connecter en suivant uniquement ce
  qu'il reçoit par email, sans intervention manuelle d'un tiers.
- Aucune régression : `pytest`, `ruff`, `mypy`, suites Playwright existantes toutes vertes.

## 24. Risques

Délivrabilité email (spam), dépendance externe nouvelle (première du genre dans ce projet),
coût, nécessité de documenter clairement la distinction dev/production (déjà un principe
appliqué ailleurs, à reconduire).

## 25. Conditions GO / NO-GO

**GO** si le prochain pilote vise un effectif réel d'enseignants/parents (au-delà d'une poignée
de comptes qu'un accompagnement manuel peut absorber) — ce qui est l'hypothèse par défaut pour
un pilote destiné à démontrer une vraie valeur.

**NO-GO / à requalifier** uniquement si le prochain pilote reste volontairement minuscule
(quelques comptes, accompagnement manuel accepté) — dans ce cas seulement, le Candidat 2
(dashboard) pourrait passer devant, sans que cela change la conclusion que le Candidat 1 reste
nécessaire avant tout pilote à taille réelle.

---

# PHASE 9 DISCOVERY COMPLETE

Recommended Phase 9:
Infrastructure d'email transactionnel (invitation de compte + réinitialisation de mot de passe)

Why:
Le socle métier (présence, notes, bulletins, portail parent) est déjà construit et déjà testé ;
l'onboarding admin fonctionne désormais réellement (Phase 8.1). Le seul maillon encore cassé est
la distribution des comptes aux enseignants et parents (dev_reset_token affiché en clair, aucun
email réel) — sans ça, rien de ce qui existe déjà ne peut être utilisé chaque semaine par
personne d'autre que l'administrateur.

Pilot impact:
Débloque l'usage réel du produit par tout le personnel et les familles d'une école pilote, pas
seulement par son administrateur.

Complexity:
Moyenne

Main risks:
Délivrabilité email, nouvelle dépendance externe (première de ce type dans le projet), coût
minime, configuration dev/production à documenter.

GO / NO-GO:
GO pour un pilote à effectif réel. NO-GO seulement si le pilote reste volontairement restreint à
quelques comptes accompagnés manuellement — cas peu probable pour un pilote destiné à démontrer
une vraie valeur.

WAITING FOR APPROVAL
