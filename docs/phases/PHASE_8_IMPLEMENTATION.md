# PHASE 8 IMPLEMENTATION REPORT

## 1. Résumé

Assistant de mise en place académique (Onboarding & Setup Wizard), fonctionnalité **web
uniquement**, conforme au périmètre approuvé dans `docs/phases/PHASE_8_DISCOVERY.md`. Parcours
guidé en 7 étapes (année scolaire → termes → niveaux → matières → classes → affectations
enseignants → résumé), orchestrant exclusivement des endpoints `academics`/`users` déjà
existants — **aucune nouvelle route API, aucune nouvelle table, aucune migration**.

Un bug préexistant bloquant a été découvert pendant l'implémentation (voir §16) : il n'a **pas**
été corrigé (hors périmètre explicite — ne pas modifier `auth`), seulement documenté et contourné
pour les besoins des tests.

## 2. Fonctionnalités implémentées

- Page `/setup`, accessible via un nouvel élément de navigation « Mise en place » (visible
  uniquement avec la permission `academics.manage`, déjà existante).
- 7 étapes avec titre, description, indicateur de progression cliquable, boutons
  Précédent/Continuer, états de chargement et erreurs.
- Étape 1 : sélection d'une année scolaire existante (radio) ou création d'une nouvelle.
- Étape 2 : termes/périodes de l'année sélectionnée, liste + création.
- Étape 3 : niveaux éducatifs de l'école, liste + création.
- Étape 4 : matières de l'école, liste + création.
- Étape 5 : classes de l'année sélectionnée, liste + création (bloque proprement si aucun
  niveau n'existe encore, sans inventer de règle métier).
- Étape 6 : affectations enseignants — sélection d'une classe puis réutilisation du composant
  existant `ClassSubjectsEditor` (attache matière + assigne enseignant, code inchangé, juste
  exporté).
- Étape 7 : résumé (comptages réels par appel API, pas de nouveau statut stocké), liens
  "Modifier" ramenant à l'étape concernée.
- Aucune donnée n'est jamais recréée : chaque étape charge d'abord l'existant, la création est
  une action explicite de l'utilisateur.
- Gestion d'erreurs centralisée (`formatWizardError`) : réseau, session expirée, permission
  refusée, ressource inexistante, doublon (409), erreur serveur, erreur de validation (422 —
  détail renvoyé tel quel par l'API).

## 3. Parcours utilisateur

Identique à la proposition validée en Discovery : Année → Termes → Niveaux → Matières → Classes
→ Affectations → Résumé, avec possibilité de revenir en arrière à tout moment (navigation libre
une fois une année sélectionnée) sans perte de données (tout est déjà persisté côté serveur dès
sa création).

## 4. Endpoints réutilisés

Aucun endpoint créé. Réutilisés tels quels :
`GET/POST /academic-years`, `GET/POST /academic-terms`, `GET/POST /education-levels`,
`GET/POST /subjects`, `GET/POST /classes`, `GET/POST /classes/{id}/subjects`,
`GET/POST /classes/{id}/teachers`, `GET /users`.

## 5. Fichiers créés

- `apps/web/lib/wizard/errors.ts`
- `apps/web/app/(app)/setup/page.tsx`
- `apps/web/app/(app)/setup/WizardSteps.tsx`
- `apps/web/e2e/setup-wizard.spec.ts`

## 6. Fichiers modifiés

- `apps/web/app/(app)/academics/ClassesPanel.tsx` — `ClassSubjectsEditor` rendu exportable
  (un mot-clé `export` ajouté), aucune autre modification. Aucune logique métier changée.
- `apps/web/components/app-shell/Nav.tsx` — ajout d'une entrée « Mise en place ».

Aucun fichier `apps/api`, `apps/mobile`, ou lié à l'authentification, l'assiduité, les notes,
les bulletins ou le portail parent n'a été modifié.

## 7. Migration DB

**NON.** Aucune migration créée, aucune modification de schéma. `alembic current` confirmé à
`0008 (head)` après implémentation (inchangé).

## 8. Dépendances ajoutées

**Aucune** dépendance de production ou de développement ajoutée à `package.json`. Pour exécuter
réellement Playwright dans cet environnement (conteneur `web` basé sur `node:20-alpine`,
incompatible avec le build Chromium glibc que Playwright télécharge par défaut), un paquet
`chromium` + `gcompat` a été installé **manuellement dans le conteneur en cours d'exécution**
(`apk add`) uniquement pour cette vérification — **rien n'a été ajouté au `Dockerfile` ni à aucun
fichier commité** ; un `docker compose build` reproduit l'image exactement comme avant cette
phase.

## 9. Tests exécutés

- Suite `pytest` complète (régression backend, aucun code API modifié).
- `ruff check .`, `mypy app` (régression backend).
- `pnpm --filter @edusphere/web lint`, `type-check`, `build` (nouveau code web).
- Suite Playwright existante (`e2e/smoke.spec.ts`) — non-régression.
- Nouvelle suite Playwright (`e2e/setup-wizard.spec.ts`, 6 tests) — exécutée réellement contre
  l'API + Postgres réels du docker-compose, aucun mock. Couvre : accès autorisé, refus RBAC,
  chargement de données déjà existantes (avec re-sélection sans doublon après rechargement de
  page), création à chaque étape (année, termes, niveaux, matières, classes, affectation
  matière+enseignant), navigation précédent/suivant, prévention de doublon avec message
  compréhensible, session expirée, isolation tenant entre deux écoles.

## 10. Résultats pytest

**114 passed**, 0 failed, 2 warnings pré-existants sans rapport avec cette phase
(153.46s).

## 11. Résultats ruff

`All checks passed!`

## 12. Résultats mypy

`Success: no issues found in 68 source files`

## 13. Résultats Playwright

- `e2e/smoke.spec.ts` : **3 passed**.
- `e2e/setup-wizard.spec.ts` : **6 passed** (après une itération : voir §15 pour le détail des
  deux bugs réels trouvés et corrigés pendant cette vérification, pas seulement des ajustements
  de test).

ESLint : **0 warning/erreur**. TypeScript (`tsc --noEmit`) : **0 erreur**.

## 14. Build web

`next build` (via `docker compose build web`) : **succès**, toutes les routes compilées
(incluant `/setup`), aucune erreur de type ni de build.

## 15. Sécurité / isolation

- RBAC : la page `/setup` vérifie `academics.manage` côté client (masquage du lien de nav +
  message de refus explicite si accès direct par URL) ; chaque appel API sous-jacent reste
  protégé côté serveur par `ensure_permission` (inchangé, non contourné) — un enseignant
  authentifié qui contournerait le masquage frontend obtiendrait un 403 réel de l'API, pas un
  accès effectif. Vérifié réellement : un compte TEACHER créé pour le test ne voit pas le lien
  et reçoit le message de refus.
- Isolation tenant : vérifiée réellement avec deux écoles distinctes — les années de l'école A
  n'apparaissent jamais dans l'assistant de l'école B (aucun paramètre d'école n'est jamais
  saisissable par l'utilisateur dans le wizard ; `currentSchoolId` vient uniquement de la
  session authentifiée).
- Validation serveur : toutes les créations passent par les schémas Pydantic existants,
  inchangés ; le frontend ne fait jamais confiance à ses propres contrôles (les erreurs 409/422
  du serveur sont affichées telles quelles).
- Deux bugs réels trouvés et corrigés pendant l'implémentation (pas des ajustements de test) :
  1. Les `useEffect` de chargement initial de chaque étape n'avaient pas de `.catch()` : une
     erreur de chargement (session expirée, réseau) laissait l'étape bloquée indéfiniment sur
     « Chargement... » sans jamais afficher de message. Corrigé dans les 7 composants de
     `WizardSteps.tsx` (chaque chargement a maintenant son propre état d'erreur affiché via
     `StepError`).
  2. Les assertions de test `getByRole("alert")` remontaient aussi le `route-announcer`
     interne de Next.js (`#__next-route-announcer__`, qui porte aussi `role="alert"`) —
     corrigé en ciblant le texte exact du message affiché.

## 16. Problèmes découverts (voir aussi §17 « Discovered / Deferred »)

Le plus significatif est détaillé en §17. Rien d'autre de nouveau côté sécurité/isolation n'a
été trouvé au-delà de ce qui est listé ici et en §17.

## 17. Discovered / Deferred

### CRITIQUE — `currentSchoolId` ne se résout jamais pour un admin auto-inscrit via `/register`

**Problème** : `POST /api/v1/auth/register` (voir `apps/api/app/modules/auth/service.py:79-85`)
attribue volontairement au nouvel admin un rôle `SCHOOL_ADMIN` **scopé organisation**
(`school_id=None`) — comportement backend intentionnel et correct (un admin d'organisation gère
toutes les écoles de son organisation ; `ensure_permission`/`get_scoped_permission_codes`
traitent bien un rôle scopé organisation comme valable pour n'importe quelle école de cette
organisation, vérifié dans `apps/api/app/core/permissions.py:49-75`). Mais
`apps/web/lib/auth/AuthProvider.tsx:60` dérive `currentSchoolId` uniquement par
`me.roles.find(role => role.school_id)` — il ignore complètement un rôle scopé organisation sans
`school_id` explicite. Résultat : pour l'admin qui vient de créer son école via le formulaire
d'inscription public, `currentSchoolId` reste **indéfiniment `null`**.

**Impact** : ce n'est pas spécifique au wizard. **Toute page qui dépend de `currentSchoolId`**
(tableau de bord, `/academics`, `/students`, `/school`, et maintenant `/setup`) reste bloquée sur
« Chargement... » indéfiniment pour cet admin, tant qu'il n'existe pas un second compte scopé
école (créé via la page Utilisateurs, qui elle fonctionne correctement — `school_id` y est
explicite). Concrètement : **le parcours d'inscription publique, mis bout à bout, ne mène
aujourd'hui à aucune page fonctionnelle de l'application pour son propre créateur.** Trouvé en
exerçant réellement `/register` → dashboard via Playwright (jamais exercé ainsi auparavant : les
vérifications précédentes utilisaient systématiquement des comptes créés directement via l'API
avec un `school_id` explicite).

**Pourquoi non corrigé ici** : la règle explicite de Phase 8 est de ne pas modifier `auth`
sauf nécessité directement bloquante pour LE WIZARD lui-même ; le wizard a été rendu vérifiable
en utilisant un compte school-admin correctement scopé (créé via l'API, même mécanisme que la
page Utilisateurs existante — voir le commentaire en tête de
`apps/web/e2e/setup-wizard.spec.ts`), donc ce bug n'est pas bloquant *pour cette phase*. Il l'est
en revanche pour tout pilote réel.

**Priorité suggérée** : P0 — plus urgent que toute nouvelle fonctionnalité, y compris ce wizard.
**Phase suggérée** : correctif ciblé et minimal (probablement quelques lignes dans
`AuthProvider.tsx` : si aucun rôle scopé école n'existe mais qu'un rôle scopé organisation
existe, résoudre l'école via `GET /schools?organization_id=...` et prendre la première/l'unique
école), à traiter **avant** la Phase 9, indépendamment de tout autre travail produit.

### MINEUR — `create_academic_term` ne catche pas `IntegrityError`

Déjà noté par l'audit global précédent. Concrètement pour ce wizard : créer deux termes de même
nom pour la même année (étape 2) renverrait un 500 générique au lieu d'un 409 « Cet élément
existe déjà. » — le message affiché resterait compréhensible (« Une erreur serveur est survenue.
Réessayez dans un instant. », pas de stack trace côté client) mais moins précis que pour les
autres ressources. Non corrigé (modification d'`apps/api`, hors périmètre web de cette phase).
**Priorité** : P2. **Phase suggérée** : à regrouper avec d'autres corrections de dette technique
mineure (déjà identifiée, pas nouvelle).

## 18. Critères d'acceptation

| Critère | Statut |
|---|---|
| Un admin (correctement scopé école) configure une école neuve de bout en bout sans deviner l'ordre des étapes | ✅ Vérifié réellement (Playwright) |
| Aucune régression `pytest`/`ruff`/`mypy` | ✅ 114/114, clean, clean |
| Aucun module existant modifié en dehors du wizard et des deux modifications additives listées en §6 | ✅ |
| Documentation reflétant l'état réel | Non traité ici (hors périmètre explicite de cette phase — le README reste la dette documentée en Discovery) |

## 19. GO / GO WITH NOTES / BLOCKED

**GO WITH NOTES**

Le wizard lui-même est complet, testé réellement de bout en bout (6/6 Playwright, 114/114
pytest, lint/type-check/build propres), et respecte strictement le périmètre approuvé (aucune
migration, aucune nouvelle dépendance, aucun module métier touché en dehors de deux changements
additifs minimes).

La note bloquante concerne un problème **découvert, pas introduit** par cette phase : voir §17.
Sans un correctif minimal de `currentSchoolId`, une école qui s'inscrit elle-même via
`/register` ne pourra pas utiliser ce wizard (ni aucune autre page dépendant de l'école
courante) avec son compte administrateur initial — un contournement existe (créer un second
compte scopé école via la page Utilisateurs) mais n'est pas une expérience acceptable pour un
premier pilote réel.

---

PHASE 8 IMPLEMENTATION COMPLETE

Status:
GO WITH NOTES

Tests:
pytest 114/114 — ruff clean — mypy clean (68 fichiers) — eslint clean — tsc clean — next build OK — Playwright wizard 6/6 — Playwright smoke 3/3

Migration:
NONE

Next:
ATTENDRE VALIDATION
