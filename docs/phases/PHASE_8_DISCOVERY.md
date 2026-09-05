# PHASE 8 — DISCOVERY & SCOPE PROPOSAL

Document d'audit uniquement. Aucun code applicatif modifié, aucune migration créée, aucune
base de données touchée. Toutes les observations ci-dessous proviennent d'une inspection
réelle du dépôt (lecture directe des fichiers, pas des rapports de phases précédentes).

## 1. Executive Summary

Le socle EduSphere (Phases 0 → 7.3) est réel, cohérent et complet sur le **parcours métier
central** d'une école : organisation → école → année scolaire → classes → élèves → enseignants
→ présences → notes → bulletins → consultation parent. Chaque étape de ce parcours a été
vérifiée dans le code (routers, modèles, tests, écrans web/mobile), pas seulement supposée à
partir des rapports de phases. La sécurité pré-pilote (SSTI, rate limiting, backup/restore) est
également confirmée en place.

Ce que l'audit révèle, en revanche, c'est que **le parcours administrateur de mise en place
initiale d'une école est entièrement manuel et technique**, et que **la création de comptes
enseignants/parents ne peut aujourd'hui pas fonctionner avec de vrais utilisateurs non
techniques** : la création d'un compte renvoie un jeton de réinitialisation affiché en clair
dans l'écran d'administration (`dev_reset_token`), sans aucune infrastructure d'email. C'est un
vrai frein à un pilote avec du personnel scolaire réel, pas une fonctionnalité "avancée"
manquante.

**Phase 8 recommandée : Assistant de mise en place (Onboarding & Setup Wizard) côté web.**
Elle n'ajoute aucune nouvelle table, ne touche à aucun module métier existant, et s'attaque
directement au frein identifié le plus concret et le moins risqué à corriger avant un pilote.

## 2. État réel du dépôt

Inspection directe effectuée :

- `README.md` (racine) — **obsolète** : annonce "phases 0 à 5", ne mentionne ni présence
  (Phase 6), ni portail parent (Phase 7), ni durcissement sécurité (7.2), ni backup (7.3).
- `docs/architecture/overview.md` — à jour sur les principes Phase 0 (stockage, monorepo,
  infra), mais ne documente aucune phase après la 0.
- `docs/phases/` — un seul document de phase existant (`PHASE_6_ATTENDANCE_PLAN.md`) avant
  celui-ci et `docs/database/BACKUP_RESTORE.md` (Phase 7.3).
- `docs/api/`, `docs/product/` — vides (`.gitkeep` uniquement).
- Pas de `CLAUDE.md` dans le dépôt.
- Pas de dépôt Git initialisé (`git` n'est même pas installé comme commande sur cet
  environnement) — la CI GitHub Actions (`.github/workflows/ci.yml`) n'a donc jamais pu
  s'exécuter réellement.
- `apps/api/app/modules/` : 11 modules — `academics`, `attendance`, `auth`, `grades`,
  `organizations`, `parent`, `rbac`, `report_cards`, `schools`, `students`, `users`.
- `apps/api/alembic/versions/` : 8 migrations (`0001`→`0008`), cohérentes avec les modules
  ci-dessus, aucune trace de modules non livrés.
- `apps/api/tests/` : 15 fichiers de tests (114 tests passants, vérifié en Phase 7.3).
- `apps/web/app/` : écrans pour academics, grades, report-cards, students, school, users,
  attendance, auth (login/register), verify (QR public). **Pas d'écran dashboard réel** — la
  page d'accueil est un message de bienvenue statique.
- `apps/mobile/app/` : espace `(teacher)` complet et réellement branché à l'API (classes,
  présences, évaluations, saisie de notes) ; espace `(parent)` en lecture seule (enfants,
  bulletins). Pas d'espace admin/staff sur mobile (cohérent avec le README).
- `packages/*` : vides, comme documenté.
- `scripts/` : `db-shell.sh`, `db-backup.sh`, `db-restore-test.sh`, `db-verify-counts.sql`
  (Phase 7.3).

## 3. Matrice fonctionnelle

| Domaine | Existe | Partiel | Absent | État réel | Priorité pilote |
|---|:---:|:---:|:---:|---|---|
| Auth | ✅ | | | Login, refresh, logout, sessions, forgot/reset password (token seulement, pas d'email), rate limiting | — |
| Organizations | ✅ | | | CRUD minimal (get/patch), RLS active | — |
| Schools | ✅ | | | CRUD, logo, currency/timezone | — |
| Academic years | ✅ | | | CRUD complet | — |
| Classes | ✅ | | | CRUD, rattachement niveau/année | — |
| Teachers | | ✅ | | Comptes créés via `users`, pas d'écran dédié "enseignants" (passe par `users` générique) | Moyenne |
| Teacher assignments | ✅ | | | Affectation classe/matière/enseignant, utilisée pour limiter les droits mobile enseignant | — |
| Students | ✅ | | | CRUD, recherche, photo, documents, **import CSV/Excel** | — |
| Guardians | ✅ | | | CRUD, lien élève-tuteur, lien vers compte `PARENT` | — |
| Enrollments | ✅ | | | Inscription par année/classe | — |
| Attendance | ✅ | | | Sessions, appel, statistiques, mobile enseignant | — |
| Grades | ✅ | | | Évaluations, notes, moyennes, classements | — |
| Report cards | ✅ | | | Génération, publication, PDF, QR verify public | — |
| Parent portal (web verify) | ✅ | | | Page publique `/verify/{code}` | — |
| Parent mobile | | ✅ | | Lecture seule (enfants, présences, notes, bulletins PDF) — pas de notifications | Haute (déjà couvert) |
| User management | | ✅ | | Création/liste par école ; **pas d'invitation par email**, jeton affiché en clair (dev) | **Haute** |
| RBAC | ✅ | | | 10 rôles, permissions par domaine, isolation tenant | — |
| Dashboard | | ✅ | | Page statique "bienvenue" — aucune métrique réelle | Moyenne |
| Admissions | | | ✅ | Aucun flux de candidature ; les élèves sont créés/importés directement | Faible (hors périmètre pilote initial) |
| Timetable | | | ✅ | `teacher_assignments` n'a ni jour ni horaire ; aucun emploi du temps | Faible/Moyenne |
| Assignments/homework | | | ✅ | Aucun modèle | Faible |
| School fees | | | ✅ | Aucun modèle | Faible (hors périmètre explicite) |
| Invoicing | | | ✅ | Aucun modèle | Faible |
| Payments | | | ✅ | Aucun modèle | Faible (exclu explicitement) |
| Receipts | | | ✅ | Aucun modèle | Faible |
| Communications | | | ✅ | Aucun modèle (ni email ni SMS ni notification) | Moyenne |
| Notifications | | | ✅ | Aucune (push/email/SMS) | Moyenne |
| Documents (génériques) | | ✅ | | `student_documents` existe (par élève) ; pas de gestion documentaire générique école | Faible |
| Search | | ✅ | | Recherche nom/matricule sur élèves uniquement ; pas de recherche globale | Faible |
| Imports/exports | | ✅ | | Import élèves (CSV/Excel) ; **aucun export**, aucun import enseignants/classes | Moyenne |
| Analytics | | ✅ | | Stats par classe (perf, présence) ; rien au niveau école | Moyenne |
| Audit logs | | | ✅ | Aucune table de traçabilité des actions admin | Faible/Moyenne (P2 déjà noté en Phase 7.1/audit global) |
| Settings | | ✅ | | Infos école basiques (adresse, devise, fuseau, logo) ; pas de paramètres pédagogiques (barème, seuils) | Faible |
| School branding | | ✅ | | Logo uploadable ; pas de couleurs/thème | Faible |
| Mobile offline | | | ✅ | Aucun cache/sync — nécessite une connexion active | Faible (hors périmètre explicite) |
| Synchronisation | | | ✅ | N/A (pas d'offline) | Faible |
| AI | | | ✅ | Aucune fonctionnalité IA | Exclu explicitement |
| API documentation | | ✅ | | Swagger/OpenAPI auto-généré (FastAPI par défaut) ; `docs/api/` vide, rien de curé | Faible |

## 4. Audit technique

- **Architecture FastAPI** : modules bien séparés (`models.py`/`schemas.py`/`router.py`/
  `service.py` quand la logique le justifie) — cohérent sur les 11 modules.
- **Multi-tenant / RLS / RBAC** : chaque router vérifié observe le même patron
  (`_get_*_or_404` puis `ensure_permission(..., organization_id=..., school_id=...)`) — aucune
  incohérence relevée dans les modules inspectés.
- **Pagination / filtres** : `list_students` a une recherche et des filtres (classe, statut)
  mais **aucune pagination** (`limit`/`offset`) — avec 945 élèves déjà en base de dev (résidus
  de tests), une vraie école de plusieurs centaines d'élèves chargerait tout en une requête.
  Pas bloquant pour un premier pilote (une école typique reste sous quelques centaines
  d'élèves) mais à surveiller.
- **Gestion des erreurs** : `HTTPException` + 404 explicites systématiques dans les modules
  vus. Le Global Audit (rapporté en Phase 7.2) avait relevé `IntegrityError` non catché sur
  certains endpoints (`create_academic_term`, `create_assessment`) — non revérifié ici (pas
  dans le périmètre de cet audit, pas de code modifié).
- **Stockage fichiers** : abstraction `StorageProvider` respectée, contrôle d'accès au niveau
  API (pas d'URLs signées publiques) — cohérent avec les principes Phase 0.
- **Redis** : utilisé uniquement pour le rate limiting login (Phase 7.2) — capacité inexploitée
  au-delà (pourrait servir à du cache si un besoin réel apparaît, pas une raison de l'utiliser
  maintenant).
- **CI** : `.github/workflows/ci.yml` bien formé (web/mobile/api, services postgres+redis) mais
  **n'a jamais tourné réellement** faute de dépôt Git initialisé — c'est une dette silencieuse :
  toute régression introduite depuis plusieurs phases n'a été détectée que par exécution
  manuelle de pytest/ruff/mypy, pas par une CI automatique.
- **Secrets** : `.env.example` complet et cohérent avec les variables réellement utilisées
  (vérifié en Phase 7.3), rien de committé en dur.
- **Backup/restore** : opérationnel et réellement testé (Phase 7.3).
- **Code mort / duplication** : rien d'évident relevé dans les modules inspectés ; pas d'audit
  exhaustif ligne à ligne effectué (hors périmètre de cette discovery).

### Dette technique réelle identifiée

1. **README obsolète** (decrit l'état à Phase 5) — risque de désorientation pour quiconque
   rejoint le projet.
2. **CI jamais exécutée** (pas de dépôt Git) — filet de sécurité automatique absent.
3. **Pas de pagination** sur les listes volumineuses (`students` au minimum).
4. **`IntegrityError` non catché** sur certains endpoints (relevé par l'audit global,
   non re-vérifié ici).
5. **Absence de `CLAUDE.md`** — pas de document d'orientation pour un futur agent/développeur.

### Risques P0/P1/P2 (constatés, pas de nouveau P0 découvert)

- **P0** : aucun nouveau P0 découvert par cet audit.
- **P1** : **absence totale d'infrastructure d'email** — bloque toute distribution réelle de
  identifiants à des utilisateurs non techniques (détaillé en §6 et §9).
- **P2** : pagination absente, CI jamais exécutée, README désynchronisé, `organizations` sans
  RLS et absence de contraintes CHECK en base (déjà notés par l'audit global 0→7, non
  revérifiés ici mais toujours dans le code).

## 5. Audit sécurité

Cet audit n'est pas une re-revue de sécurité complète (déjà faite en Phase 7.2/audit global).
Observation nouvelle pertinente pour Phase 8 : l'écran `apps/web/app/(app)/users/page.tsx`
affiche `dev_reset_token` en clair dans l'interface après création d'un compte
(`apps\web\app\(app)\users\page.tsx:144-152`). Ce n'est pas une régression de sécurité — le
token n'est émis que hors environnement `production` (déjà vérifié Phase 7.2) — mais c'est un
signal fort que **le flux d'onboarding utilisateur n'a jamais été conçu pour de vrais
utilisateurs finaux**, seulement pour du test développeur.

## 6. Audit UX école pilote

Simulation du parcours réel (école pilote, admin non technique) :

| Étape | État |
|---|---|
| 1. Création organisation | Fonctionne (`/auth/register`) mais c'est un formulaire d'inscription développeur (organisation+école+admin en un seul appel avec des champs techniques : slug, country_code) |
| 2. Création école | Couplée à l'étape 1 pour la première école ; écoles suivantes via écran web `School` |
| 3. Année scolaire | Écran dédié, fonctionne, mais nécessite de connaître le concept "année scolaire" avant "termes/trimestres" avant "classes" |
| 4. Classes | Nécessite d'avoir créé au préalable : niveau éducatif, matières, salles (optionnel) — **4 écrans distincts à visiter dans le bon ordre** avant de pouvoir créer une seule classe |
| 5. Élèves | **Bon** — import CSV/Excel disponible, expérience déjà correcte |
| 6. Enseignants | Créés via l'écran générique "Utilisateurs" — pas de distinction UX enseignant/staff, pas d'import en masse |
| 7. Affectation enseignant/classe/matière | Écran dédié existe (`academics` panel) mais dépend d'avoir déjà fait 4 et 6 |
| 8. Présences | **Bon** — fonctionne au web et surtout au mobile (usage réel en classe) |
| 9. Notes | **Bon** — écrans de saisie web et mobile fonctionnels |
| 10. Génération bulletins | **Bon** — modèle personnalisable, génération PDF, désormais sécurisé (Phase 7.2) |
| 11. Publication | **Bon** — un clic, QR de vérification généré |
| 12. Consultation parent | **Bon** côté mobile (lecture seule) et web (`/verify/{code}` public) |

**Ce qui fonctionne déjà bien** : tout le cycle "vie quotidienne" d'une école une fois
configurée (présence, notes, bulletins, consultation parent) — c'est le cœur de la valeur
produit, et il est solide.

**Ce qui est difficile aujourd'hui** :
- La configuration académique initiale (étapes 3-4-7) exige de comprendre et suivre un ordre
  précis à travers 6-7 écrans distincts, sans guidage ni valeurs par défaut suggérées.
- Il n'existe **aucun moyen pour un enseignant ou un parent de recevoir ses identifiants** sans
  qu'un administrateur EduSphere ne lise manuellement un jeton dans l'écran d'administration et
  ne le transmette lui-même (WhatsApp, SMS manuel, etc.) — praticable pour un tout petit pilote
  (une poignée d'enseignants) mais pas pour un vrai déploiement école (dizaines d'enseignants,
  centaines de parents).

**Éléments indispensables avant un vrai test école** (au sens strict — sans lesquels le pilote
échouerait ou exigerait un accompagnement manuel permanent d'un ingénieur EduSphere) :
- Réduire la charge de configuration académique initiale.
- Un moyen viable de distribuer les identifiants aux enseignants/parents.

Aucun des deux n'exige de nouvelle table ni de refonte : ce sont des problèmes d'assemblage/UX
et d'intégration d'un service externe simple (email), pas d'architecture.

## 7. Dette technique

Voir §4. Résumé priorisé pour Phase 8 : aucun des éléments de dette technique listés
(pagination, CI, README, `IntegrityError`) n'empêche un pilote de fonctionner à court terme —
ce sont des améliorations de robustesse à traiter dans une phase ultérieure dédiée
maintenabilité, pas des bloquants pilote.

## 8. Risques

- **Risque produit** : lancer un pilote sans résoudre la distribution de comptes force un
  accompagnement manuel permanent par l'équipe EduSphere pour chaque nouvel enseignant/parent
  — non scalable même pour une seule école de taille moyenne.
- **Risque UX** : un admin d'école livré à lui-même face à 6-7 écrans de configuration
  académique sans guidage risque d'abandonner avant d'atteindre la valeur réelle (bulletins,
  présence).
- **Risque de dérive de périmètre** : la tentation est grande d'ajouter des fonctionnalités
  "avancées" (paiements, IA, offline) qui n'ont aucune valeur tant que le socle n'a pas été
  testé par une vraie école — l'audit ne recommande aucune d'entre elles maintenant.
- **Risque de régression** : toute Phase 8 doit rester non intrusive sur les modules validés
  (attendance, grades, report_cards, parent) — les candidats retenus n'y touchent pas.

## 9. Candidats Phase 8

### Candidat 1 — Onboarding & Setup Wizard (assistant de mise en place)

- **Objectif** : réduire le parcours de configuration initiale d'une école (étapes 3-4-7 du
  §6) à un flux guidé séquentiel, réutilisant les endpoints existants.
- **Inclus** : écran web "Mise en place" qui enchaîne année scolaire → termes → niveaux →
  matières → classes → affectations enseignants, avec suggestions de valeurs par défaut
  (ex. 3 trimestres pré-remplis) ; indicateur de progression ; possibilité de sauter des étapes.
- **Explicitement exclus** : aucun changement de modèle de données ; pas d'import en masse de
  classes/matières (juste le formulaire guidé) ; pas de personnalisation avancée (thème,
  branding).
- **Dépendances** : aucune nouvelle — 100% construit sur les endpoints `academics` existants.
- **Valeur pilote** : élevée — lève directement le principal frein identifié en §6 pour la mise
  en route d'une école.
- **Complexité** : faible à moyenne (uniquement front-end web, orchestration d'appels
  existants).
- **Risques** : faibles — pas de nouvelle logique métier, pas de nouvelle table.
- **Tests nécessaires** : tests front (si un framework de test web existe — à vérifier), tests
  manuels du flux complet ; aucun nouveau test backend requis (endpoints déjà couverts par
  `test_academics.py`).
- **Estimation qualitative** : **faible-moyenne**.

### Candidat 2 — Comptes utilisateurs : invitation par email réelle

- **Objectif** : remplacer le `dev_reset_token` affiché en clair par un vrai envoi d'email
  (invitation à la création de compte, lien de réinitialisation de mot de passe fonctionnel
  pour de vrais utilisateurs).
- **Inclus** : intégration d'un service d'envoi d'email simple (SMTP ou API d'un fournisseur),
  template d'invitation et de reset, désactivation de l'exposition du token en environnement
  non-dev.
- **Explicitement exclus** : SMS, notifications push, communications marketing, tout système de
  templates avancé.
- **Dépendances** : nécessite de choisir un fournisseur/mécanisme d'envoi d'email (nouvelle
  dépendance externe, nouveau secret à gérer) — c'est la seule vraie décision d'architecture
  parmi les 3 candidats.
- **Valeur pilote** : élevée à moyen terme (indispensable dès que le nombre d'enseignants/
  parents dépasse ce qu'un accompagnement manuel peut absorber), mais **contournable à très
  court terme** pour un tout premier petit pilote (distribution manuelle des identifiants par
  l'équipe EduSphere).
- **Complexité** : moyenne (nouvelle dépendance externe, gestion des échecs d'envoi, secrets).
- **Risques** : dépendance à un service tiers, risque de délivrabilité (spam), a un coût
  (même minime) contrairement aux deux autres candidats.
- **Tests nécessaires** : tests d'intégration avec mock du service d'envoi, tests du flux
  reset/invitation de bout en bout.
- **Estimation qualitative** : **moyenne**.

### Candidat 3 — Tableau de bord opérationnel de base

- **Objectif** : remplacer la page d'accueil statique par un vrai tableau de bord (effectif
  élèves, taux de présence de la semaine, complétude de saisie des notes, bulletins publiés).
- **Inclus** : quelques requêtes d'agrégation par école (déjà toutes les données existent) +
  écran web.
- **Explicitement exclus** : analytics avancées, graphiques historiques multi-années,
  exports de rapports.
- **Dépendances** : aucune nouvelle.
- **Valeur pilote** : moyenne — utile pour convaincre une direction d'école de la valeur du
  produit pendant le pilote, mais n'empêche rien de fonctionner si absent.
- **Complexité** : faible.
- **Risques** : faibles.
- **Tests nécessaires** : tests des nouvelles requêtes d'agrégation.
- **Estimation qualitative** : **faible**.

## 10. Phase 8 recommandée

**Candidat 1 — Onboarding & Setup Wizard.**

Réponse à la question posée : c'est l'étape qui augmente le plus la valeur réelle d'EduSphere
pour une première école pilote sans fragiliser le socle existant, parce qu'elle :
- s'attaque au frein le plus concret observé en simulant le parcours réel d'une école (§6) ;
- ne touche à aucun module métier validé (attendance/grades/report_cards/parent/backup/
  sécurité restent intacts) ;
- n'introduit aucune nouvelle dépendance externe ni nouveau secret (contrairement au
  Candidat 2) ;
- reste réversible : c'est une couche d'orchestration front-end au-dessus d'endpoints déjà
  testés, pas un changement d'architecture.

Le Candidat 2 (email) reste réel et documenté ici comme **probable Phase 9** : il devient
nécessaire dès que le pilote dépasse une poignée d'enseignants, mais n'est pas strictement
bloquant pour démarrer un tout premier test avec accompagnement rapproché. Le Candidat 3
(dashboard) est une amélioration à faible risque qui peut suivre indépendamment.

## 11. Scope IN

- Nouvel écran web "Mise en place de l'école" (wizard multi-étapes).
- Enchaînement guidé : année scolaire → termes → niveaux éducatifs → matières → classes →
  affectations enseignants.
- Valeurs par défaut suggérées (ex. modèle 3-trimestres), modifiables.
- Indicateur de progression, possibilité de revenir en arrière ou sauter une étape.
- Réutilisation stricte des endpoints `academics` existants (aucun nouvel endpoint requis a
  priori — à confirmer en phase de planification détaillée si un besoin d'action groupée
  apparaît).

## 12. Scope OUT

- Aucun nouveau modèle de données, aucune migration.
- Pas d'import en masse de classes/matières/enseignants (hors périmètre — pourrait être un
  candidat de phase ultérieure si le besoin est confirmé par le pilote).
- Pas d'email/invitation (Candidat 2, phase séparée).
- Pas de dashboard analytics (Candidat 3, phase séparée).
- Pas de personnalisation de branding au-delà du logo déjà existant.
- Pas de modification des modules attendance/grades/report_cards/parent/auth/backup.
- Pas d'IA, offline, paiements, multi-campus, multi-pays, microservices.

## 13. Dépendances

Aucune dépendance externe nouvelle. Dépendance interne : les endpoints `academics` (années,
termes, niveaux, matières, classes, affectations) et `users` (création enseignant) doivent
rester stables — aucune modification de leur contrat n'est prévue par ce scope.

## 14. Plan d'implémentation proposé (à valider avant tout code)

1. Concevoir l'enchaînement d'écrans (maquette simple) reprenant l'ordre validé en §6.
2. Implémenter le wizard comme nouvelle route web `(app)/setup`, chaque étape appelant les
   endpoints existants (`academic-years`, `academic-terms`, `education-levels`, `subjects`,
   `classes`, `classes/{id}/teachers`).
3. Ajouter des valeurs par défaut pré-remplies (ex. 3 termes standards) éditables avant
   soumission.
4. Ajouter un indicateur d'état "école configurée" (dérivé de l'existence d'au moins une classe
   avec une affectation enseignant) pour orienter un nouvel admin vers le wizard ou le
   dashboard existant.
5. Mettre à jour `README.md` et créer/mettre à jour la documentation produit (`docs/product/`)
   pour refléter l'état réel jusqu'à Phase 8 (corrige la dette #1 du §4 en passant, sans que ce
   soit son objectif principal).

## 15. Plan de tests

- Tests manuels de bout en bout du wizard sur une école fraîchement créée (pas de données
  résiduelles), jusqu'à la première prise de présence et la première saisie de notes.
- Vérification que les endpoints existants ne changent pas de comportement (les tests
  `test_academics.py` existants doivent rester verts sans modification).
- Vérification tenant isolation : le wizard ne doit permettre de configurer que l'école
  courante de l'admin connecté (RBAC déjà en place, à revérifier pour ce nouveau parcours).
- Pas de nouveau test backend nécessaire si aucun endpoint n'est ajouté ; si un endpoint de
  commodité est ajouté en cours de conception détaillée, il devra avoir ses propres tests
  suivant les conventions existantes.

## 16. Critères d'acceptation

- Un admin peut configurer une école neuve de zéro jusqu'à "prête pour la présence/les notes"
  sans quitter le wizard ni deviner l'ordre des étapes.
- Aucune régression sur `pytest` (114 tests actuels), `ruff`, `mypy`.
- Aucun module existant modifié en dehors de l'ajout du nouvel écran web et, si nécessaire,
  d'endpoints de commodité strictement additifs.
- La documentation (`README.md` a minima) reflète l'état réel du produit après Phase 8.

## 17. Risques et mitigations

| Risque | Mitigation |
|---|---|
| Le wizard masque des options avancées dont un admin aurait besoin | Garder les écrans détaillés existants accessibles en parallèle, le wizard n'est pas le seul chemin |
| Confusion si l'admin quitte le wizard à mi-parcours | Chaque étape sauvegarde immédiatement via les endpoints existants (pas d'état transitoire perdu) |
| Sous-estimer le besoin d'email/invitation pendant le pilote | Documenter explicitement (fait ici, §9/§10) que Candidat 2 est la suite probable si le pilote le confirme |

## 18. Conditions GO / NO-GO

**GO** si : le premier pilote visé implique un admin d'école qui configurera lui-même
l'établissement (même avec un accompagnement initial), et que l'équipe EduSphere peut encore
distribuer manuellement les identifiants enseignants/parents pendant ce premier pilote
(effectif limité, ex. moins de 20 enseignants).

**NO-GO / à requalifier** si : le pilote prévu implique d'emblée un grand nombre de comptes
enseignants/parents sans accompagnement manuel possible — dans ce cas, le Candidat 2
(invitation email) devient prioritaire avant ou en parallèle du wizard.

---

# PHASE 8 DISCOVERY COMPLETE

Recommended Phase 8:
Onboarding & Setup Wizard (assistant de mise en place académique côté web)

Why:
Le parcours métier central (présence, notes, bulletins, consultation parent) est déjà complet
et solide. Le frein réel identifié en simulant le parcours d'une école pilote est la
configuration académique initiale, éclatée sur 6-7 écrans sans guidage — pas une fonctionnalité
manquante. Le wizard s'attaque à ce frein sans toucher au socle validé, sans nouvelle
dépendance, et reste entièrement réversible.

Scope:
Nouvel écran web guidé enchaînant année scolaire → termes → niveaux → matières → classes →
affectations enseignants, avec valeurs par défaut suggérées. Aucune nouvelle table, aucune
migration, réutilisation stricte des endpoints existants.

Main risks:
Risque faible et maîtrisé — le vrai risque produit identifié (distribution de comptes
enseignants/parents sans email réel) n'est PAS couvert par cette phase et devra être requalifié
avant un pilote à grande échelle (Candidat 2, probable Phase 9).

GO / NO-GO:
GO pour un premier pilote à effectif limité avec accompagnement manuel possible pour la
distribution des comptes ; NO-GO en l'état si le pilote prévu implique d'emblée un grand nombre
de comptes sans accompagnement — dans ce cas, requalifier le Candidat 2 en priorité.
