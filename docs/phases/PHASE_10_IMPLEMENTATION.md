# PHASE 10 IMPLEMENTATION REPORT

## 1. Objectif

Transformer la page d'accueil admin existante (`apps/web/app/(app)/page.tsx`, statique depuis la
Phase 0) en un véritable tableau de bord opérationnel, strictement limité aux 4 métriques
approuvées dans `docs/phases/PHASE_10_DISCOVERY.md`.

## 2. Métriques

1. **Effectif élèves** — nombre d'élèves actifs de l'école courante.
2. **Taux de présence récent** — pour le terme académique courant.
3. **Complétude de saisie des notes** — pour le terme académique courant.
4. **Bulletins publiés** — total pour l'école courante.

## 3. Définitions métier (exactes, aucune règle inventée)

- **Effectif** : `Student.status == "ACTIVE"` scopé à l'école — champ et valeur déjà existants
  (`apps/api/app/modules/students/models.py:32`), déjà utilisés comme filtre par
  `students/router.py::list_students` (paramètre `status`).
- **Terme courant** : le terme de l'année marquée `AcademicYear.is_current = true` dont la
  période (`start_date`/`end_date`) couvre la date du jour. Réutilise deux champs déjà
  existants et déjà porteurs de la notion de "courant"/"période" ailleurs dans l'application
  (`AcademicYear.is_current` — déjà utilisé côté web pour présélectionner une année, ex.
  `ClassesPanel.tsx`) ; aucune nouvelle notion de période introduite.
- **Taux de présence** : **exactement** la même formule que la Phase 6
  (`attendance/service.py::_summarize` — `(présents + retards) / total × 100`, un retard comptant
  comme une présence, décision déjà validée en Phase 6), désormais agrégée à l'échelle de
  l'école pour le terme courant via une nouvelle fonction `compute_school_summary` qui **appelle
  directement `_summarize`** (aucune formule dupliquée). Si aucune donnée n'existe pour le terme
  courant (ou si aucun terme courant n'est résolu), la valeur est `null` → affiché
  « Aucune donnée », jamais un pourcentage trompeur.
- **Complétude de saisie des notes** : pour les évaluations (`assessments`) créées dans le terme
  courant, résultats **attendus** (une inscription active — `student_enrollments.status ==
  "ACTIVE"`, même filtre que `grades/service.py::recompute_term_average`/`recompute_term_ranks`
  déjà existants — dans la classe de l'évaluation, comptée une fois par évaluation) vs résultats
  **effectivement saisis** (`assessment_results`). `null` si aucune évaluation n'existe pour le
  terme courant. Cette définition correspond exactement à l'exemple suggéré par le brief
  ("évaluations attendues vs évaluations saisies") et n'invente aucune notion de note "planifiée"
  séparée de l'évaluation elle-même — le modèle ne porte pas cette distinction, et il n'a pas été
  nécessaire d'en ajouter une pour obtenir un résultat réel et exact.
- **Bulletins publiés** : `ReportCard.published_at IS NOT NULL`, scopé à l'école — exactement le
  même filtre que celui déjà utilisé par `parent/router.py::list_child_report_cards`.

## 4. Architecture

Un seul nouvel endpoint agrégé a été créé, sa nécessité étant démontrée par l'audit du code
existant : **aucun** des endpoints `attendance`, `grades` ou `report_cards` n'offre de listing à
l'échelle de l'école (tous exigent `class_id`, `class_subject_id`, ou `class_id`+
`academic_term_id`) — seul `GET /students?school_id=` l'est déjà. Récupérer les 4 métriques sans
un endpoint dédié aurait exigé de boucler sur toutes les classes de l'école côté frontend (N+1
explicitement proscrit par le brief). L'endpoint reste strictement limité aux 4 métriques : ce
n'est pas un système générique d'analytics, il n'expose aucune donnée au-delà de ces 4 champs.

- `GET /api/v1/schools/{school_id}/dashboard` (nouveau, dans `schools/router.py`, module déjà
  responsable des informations sur une école).
- Logique d'agrégation : nouveau `apps/api/app/modules/schools/service.py` (le module `schools`
  n'avait pas encore de fichier `service.py`), qui délègue le calcul de chaque métrique
  spécialisée à son **module d'origine** plutôt que de dupliquer la logique :
  - `attendance/service.py::compute_school_summary` (nouveau, appelle `_summarize` existant).
  - `grades/service.py::compute_school_completeness` (nouveau).
  - Effectif et bulletins publiés : requêtes directes dans `schools/service.py` (pas de formule
    à centraliser, un simple filtre).
- Ce patron — un routeur qui appelle directement le `service` d'un **autre** module — est déjà
  établi dans ce dépôt (`parent/router.py` appelle `attendance.service.compute_student_summary`
  directement, avec le commentaire "réutilise le calcul de la Phase 6, aucune réécriture") : la
  Phase 10 suit exactement la même convention.

## 5. Endpoints réutilisés

Aucun endpoint existant modifié. La nouvelle route réutilise les tables et relations déjà
exposées par `students`, `attendance`, `grades`, `report_cards`, `academics` — pas d'appel à
d'autres endpoints HTTP (agrégation faite directement en base, une seule requête réseau depuis
le frontend).

## 6. Endpoints créés

`GET /api/v1/schools/{school_id}/dashboard` — un seul, strictement limité aux 4 métriques,
protégé par les 4 permissions de lecture déjà existantes (voir §11).

## 7. Fichiers créés

- `apps/api/app/modules/schools/service.py`
- `apps/api/tests/test_dashboard.py`
- `apps/web/e2e/dashboard.spec.ts`

## 8. Fichiers modifiés

- `apps/api/app/modules/attendance/service.py` — ajout de `compute_school_summary`.
- `apps/api/app/modules/grades/service.py` — ajout de `compute_school_completeness`.
- `apps/api/app/modules/schools/schemas.py` — ajout de `SchoolDashboardOut`.
- `apps/api/app/modules/schools/router.py` — ajout de la route `GET /{school_id}/dashboard`.
- `apps/web/lib/schools/client.ts` — ajout de `getSchoolDashboard()` + type `SchoolDashboard`.
- `apps/web/app/(app)/page.tsx` — remplacement du contenu statique par les 4 métriques (seule
  page modifiée côté frontend, conformément à la consigne).

Aucun autre fichier `apps/api`, `apps/mobile`, RBAC, wizard, email, attendance/grades/
report_cards **métier** (au-delà des deux fonctions d'agrégation ajoutées), ou parent portal n'a
été modifié.

## 9. Migration

**Aucune.** Toutes les données proviennent de tables déjà existantes. `alembic current` confirmé
à `0008 (head)` après implémentation, inchangé.

## 10. Dépendances

**Aucune nouvelle dépendance.** Ni backend (`pyproject.toml`/`requirements.txt` inchangés) ni
frontend (`package.json` inchangé). Aucun cache/Redis introduit pour cette phase.

## 11. Isolation tenant

- La route est scopée par `school_id` dans l'URL, résolu en objet `School` réel (404 si
  inexistant), puis chaque permission est vérifiée avec `organization_id=school.organization_id,
  school_id=school.id` — même patron que toutes les autres routes du module `schools`.
- **Vérifié réellement** (`test_dashboard_tenant_isolation`) : le dashboard de l'école A ne
  reflète jamais les données de l'école B (effectif et bulletins publiés à 0 pour A alors que B
  est peuplée), et l'admin de A reçoit 403/404 en tentant de consulter directement le dashboard
  de B.
- Aucune requête SQL de la nouvelle logique ne filtre autrement que par `school_id` explicite —
  pas de risque de fuite via un identifiant mal scopé.

## 12. Sécurité

- **Permissions réutilisées, aucune nouvelle créée** : la route exige les 4 permissions de
  lecture déjà existantes (`students.read`, `attendance.read`, `grades.read`,
  `report_cards.read`), toutes scopées école via `ensure_permission` déjà existant.
- **Un utilisateur non autorisé ne peut pas accéder aux données** : vérifié réellement
  (`test_dashboard_permission_denied_for_accountant`, pytest ; test Playwright équivalent côté
  UI) — un compte `ACCOUNTANT` (qui ne possède aucune des 4 permissions dans le catalogue RBAC
  actuel) reçoit 403.
- **Point documenté, décision assumée** : `TEACHER` et `STAFF` possèdent, par la conception RBAC
  déjà existante (Phases 1-6), les 4 permissions de lecture à l'échelle de l'école — ils peuvent
  donc techniquement appeler ce nouvel endpoint et voir des **agrégats** (4 nombres/pourcentages,
  aucune donnée nominative, aucun détail par élève). Ce n'est pas une nouvelle surface
  d'exposition de données personnelles ; c'est une conséquence directe du modèle de permissions
  déjà en vigueur, pas une décision spécifique à cette phase. Restreindre davantage aurait exigé
  soit une nouvelle permission (explicitement interdit), soit une vérification de rôle en dur
  (contournerait le système RBAC) — aucune des deux n'a été retenue.

## 13. UX

- 4 cartes métriques (`MetricCard`), grille responsive (1 colonne mobile, 2 en tablette, 4 en
  desktop — classes Tailwind `grid-cols-1 sm:grid-cols-2 lg:grid-cols-4`), cohérentes avec le
  design system déjà en place (mêmes classes `rounded border border-slate-200`, mêmes tons que
  le reste de l'application).
- États couverts : chargement (« Chargement des indicateurs... »), succès (les 4 cartes),
  vide/absence de données par métrique (« Aucune donnée », jamais une valeur trompeuse), erreur
  (message clair dans un encart rouge, jamais un blocage indéfini).
- Chaque métrique de période (présence, complétude) affiche le nom du terme courant sous la
  valeur, satisfaisant l'exigence d'indication de période.
- Le dashboard reste simple : aucun graphique, aucun filtre, aucune interaction complexe —
  conforme à la consigne de ne pas en faire un outil analytique.

## 14. Tests

### Backend (`apps/api/tests/test_dashboard.py`, 6 tests, exécutés réellement)

1. Métriques réelles et exactes sur une école peuplée (2 élèves, 1 présent/1 absent → 50%, 1
   résultat saisi sur 2 attendus → 50%, 1 bulletin publié sur 2 générés).
2. École vide → tout à zéro/`null`, aucune valeur fabriquée.
3. Absence de données de présence (notes présentes) → `attendance_rate: null`,
   `grade_completeness_rate` correct.
4. Absence de données de notes (présence présente) → `grade_completeness_rate: null`,
   `attendance_rate` correct.
5. Isolation tenant (voir §11).
6. Permission refusée pour un rôle sans les 4 permissions requises (voir §12).

### Playwright (`apps/web/e2e/dashboard.spec.ts`, 3 tests, exécutés réellement, sans mock)

1. Métriques réelles affichées après une configuration complète pilotée par appels API réels
   (mêmes chiffres que côté backend : deux « 50% », le nom du terme, aucune « Aucune donnée »).
2. École vide : zéros et « Aucune donnée » affichés, jamais de blocage sur le chargement.
3. Permission refusée : message d'erreur clair affiché, jamais de blocage infini sur le
   chargement.

### Non-régression (réexécutée réellement)

- `setup-wizard.spec.ts` : 6/6.
- `admin-onboarding.spec.ts` : 3/3.
- `password-reset.spec.ts` : 4/4.
- `smoke.spec.ts` : 3/3.
- **Total Playwright : 19/19.**

## 15. Résultats pytest

**126 passed**, 0 failed (120 précédents + 6 nouveaux), 2 warnings pré-existants sans rapport
avec cette phase.

## 16. Résultats ruff

`All checks passed!`

## 17. Résultats mypy

`Success: no issues found in 70 source files` (69 → 70, nouveau fichier `schools/service.py`).

## 18. Playwright

**19/19** au total (3 nouveaux dashboard + 16 régression), détaillé §14.

## 19. Build

`next build` (via `docker compose build web`) : succès. ESLint et `tsc --noEmit` : 0 avertissement/
erreur.

## 20. Problèmes découverts

Aucun bug préexistant découvert pendant cette phase. Le module `schools` n'avait pas de fichier
`service.py` avant cette phase (toute sa logique vivait dans `router.py`) — pas un problème,
juste une observation ayant guidé le choix d'en créer un pour cette phase plutôt que de continuer
à tout mettre dans le routeur (le calcul des 4 métriques est trop substantiel pour rester inline,
contrairement aux endpoints existants du module qui restent simples).

## 21. Éléments différés

**PHASE 10.1 — Forgot Password Rate Limiting** (P1). `POST /api/v1/auth/forgot-password` reste
sans rate limiting, identifié pendant la Phase 10 Discovery. Non traité ici — hors périmètre
strict du dashboard, `auth` non modifié conformément à la consigne explicite de cette phase.

Aucun autre élément différé nouveau. Rien parmi les candidats #2/#3/#4/#5 de la Discovery n'a
été entamé (notifications in-app, recherche globale, import enseignants en masse).

## 22. Critères d'acceptation

| Critère | Statut |
|---|---|
| Un admin voit au moins une métrique réelle en moins de 30 secondes après connexion | ✅ Vérifié réellement (Playwright) |
| Les 4 métriques utilisent des définitions déjà existantes, aucune formule inventée | ✅ Voir §3 |
| Isolation tenant | ✅ Vérifiée réellement (pytest + conception) |
| Permissions réutilisées, aucune nouvelle | ✅ |
| États loading/empty/error gérés, jamais de blocage indéfini | ✅ Vérifié réellement (Playwright) |
| Responsive | ✅ Grille Tailwind adaptative |
| Aucune régression | ✅ 126/126 pytest, 19/19 Playwright, ruff/mypy/lint/type-check/build tous propres |
| Aucune migration | ✅ `alembic current` = `0008 (head)`, inchangé |
| Aucune nouvelle dépendance | ✅ |

## 23. Verdict

**GO**

Le tableau de bord opérationnel admin fonctionne réellement de bout en bout, avec des métriques
exactes et vérifiées (backend et E2E), sans régression, sans migration, sans nouvelle
dépendance, strictement dans le périmètre des 4 métriques approuvées.

---

PHASE 10 IMPLEMENTATION COMPLETE

Implemented:
Operational Admin Dashboard

Metrics:
Effectif élèves actifs, taux de présence (terme courant), complétude de saisie des notes (terme courant), bulletins publiés

Migration:
NO

Tests:
pytest 126/126 — ruff clean — mypy clean (70 fichiers)

Playwright:
19/19 (3 nouveaux dashboard.spec.ts + 16 régression : setup-wizard 6/6, admin-onboarding 3/3, password-reset 4/4, smoke 3/3)

Build:
next build OK — eslint clean — tsc clean

Deferred:
Forgot Password Rate Limiting — Phase 10.1

Status:
GO

WAITING FOR VALIDATION
