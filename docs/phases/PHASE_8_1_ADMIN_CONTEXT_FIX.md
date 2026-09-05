# PHASE 8.1 — ADMIN SCHOOL CONTEXT & ONBOARDING FIX

## 1. Problème initial

Un administrateur qui s'inscrit via `POST /api/v1/auth/register` reste bloqué indéfiniment sur
« Chargement... » sur le dashboard, `/academics`, et l'assistant de mise en place (`/setup`) —
aucune de ces pages n'arrive jamais à déterminer l'école courante pour ce compte. Découvert en
Phase 8 en exerçant réellement le parcours `/register` → dashboard via Playwright (jamais exercé
ainsi auparavant : toutes les vérifications précédentes utilisaient des comptes créés directement
via l'API avec un `school_id` explicite).

## 2. Cause racine

`POST /register` (`apps/api/app/modules/auth/service.py:79-85`) attribue à l'admin un rôle
`SCHOOL_ADMIN` **scopé organisation** (`school_id=None`) — comportement backend **intentionnel
et correct** : un admin d'organisation gère toutes les écoles de son organisation, et
`ensure_permission`/`get_scoped_permission_codes`
(`apps/api/app/core/permissions.py:49-75`) traitent bien un rôle scopé organisation comme valable
pour n'importe quelle école de cette organisation. Le backend n'a donc aucun bug.

Le bug est côté frontend : `apps/web/lib/auth/AuthProvider.tsx` dérivait `currentSchoolId`
uniquement par `me.roles.find(role => role.school_id)` — ignorant tout rôle scopé organisation
sans `school_id` explicite. Pour cet admin, `currentSchoolId` restait donc `null` pour toujours,
et chaque page consommatrice affichait sa propre garde `if (!currentSchoolId) return
<p>Chargement...</p>` sans jamais se résoudre ni afficher d'erreur.

## 3. Solution retenue

**Aucun changement backend.** L'endpoint `GET /api/v1/schools?organization_id=...` existait déjà,
déjà protégé par `ensure_permission("schools.read", organization_id=...)` (satisfait par un rôle
scopé organisation), et déjà couvert par un test d'isolation tenant existant
(`test_admin_a_cannot_list_schools_of_organization_b`, `apps/api/tests/test_tenant_isolation.py:51`).
C'est l'endpoint le plus simple et le moins invasif permettant à un admin organisationnel de
retrouver l'école à laquelle il appartient — réutilisé tel quel.

Correctif entièrement frontend, dans `AuthProvider.tsx` :

1. Priorité inchangée : si un rôle scopé école existe (compte créé via la page Utilisateurs),
   c'est la source de vérité — comportement Phase 1-8 préservé à l'identique.
2. Sinon, si un rôle scopé organisation existe, résolution via `GET /schools?organization_id=` :
   - **0 école** : état `empty` (n'arrive jamais en pratique aujourd'hui — voir §10 — mais géré
     proprement, pas de blocage).
   - **1 école** : résolution automatique, silencieuse — c'est le cas réel du bug signalé.
   - **≥2 écoles** : **jamais de sélection arbitraire**. Un choix déjà fait explicitement sur ce
     navigateur (mémorisé en `localStorage`, comme les jetons de session) est réutilisé s'il est
     toujours valide ; sinon un écran de sélection explicite s'affiche (`AuthGate.tsx`).
   - **Erreur réseau/session/serveur** : état `error` avec message clair, bouton Réessayer et
     bouton Se reconnecter — jamais de blocage silencieux.
3. `AuthGate.tsx` (le point de passage unique de toutes les pages `(app)`) rend ces états
   explicitement, ce qui évite de dupliquer la logique dans chaque page consommatrice — aucune
   des pages existantes (dashboard, `/academics`, `/setup`, etc.) n'a été modifiée.

**Aucune nouvelle table.** La mémorisation du choix multi-écoles utilise `localStorage`
(`edusphere.selected_school_id`), exactement le mécanisme déjà utilisé pour les jetons de
session (`apps/web/lib/auth/session.ts`) — pas de nouvelle colonne, pas de nouvelle table, pas de
nouveau système d'état global (pas de Redux).

## 4. Fichiers modifiés

- `apps/web/lib/auth/AuthProvider.tsx` — logique de résolution du contexte école (voir §3).
- `apps/web/app/(app)/AuthGate.tsx` — rendu des états `loading`/`selection-needed`/`empty`/`error`
  au lieu d'un unique état `Chargement...` indéfini.
- `apps/web/lib/schools/client.ts` — ajout de `listSchools(organizationId)`, wrapper client pur
  autour de l'endpoint existant `GET /schools?organization_id=`, aucun nouvel endpoint.

**Fichiers créés** :
- `apps/web/e2e/admin-onboarding.spec.ts`

Aucun fichier `apps/api`, `apps/mobile`, RBAC, migrations, wizard (`apps/web/app/(app)/setup/*`),
attendance, grades, report_cards ou parent portal n'a été modifié.

## 5. Migrations

**NON.** `alembic current` confirmé à `0008 (head)`, inchangé.

## 6. Tests

### Réels, exécutés (Playwright, `apps/web/e2e/admin-onboarding.spec.ts`)

1. **CRITIQUE, sans mock** : nouvel admin → register → login (automatique) → dashboard réel
   (plus de "Chargement..." bloqué) → clic sur « Mise en place » → assistant réellement affiché.
   Exécuté contre l'API + Postgres réels du docker-compose.
2. Admin avec 2 écoles pour la même organisation : l'écran de sélection s'affiche (jamais de
   choix arbitraire), la sélection résout le contexte, et un rechargement de page mémorise le
   choix (pas de redemande).
3. Erreur lors de la détermination du contexte (interception ciblée et explicitement documentée
   de `GET /schools?organization_id=`, distincte du parcours critique #1 qui reste 100% réel) :
   message clair, boutons Réessayer/Se reconnecter présents, Réessayer récupère avec succès une
   fois la panne simulée levée.

### Non-régression (réexécutés réellement)

- `apps/web/e2e/setup-wizard.spec.ts` (Phase 8, compte school-scopé) : **6/6** — confirme que le
  chemin prioritaire (rôle scopé école) est inchangé.
- `apps/web/e2e/smoke.spec.ts` : **3/3**.
- `pytest` (backend, aucun fichier modifié) : **114/114**.

### Couverture des scénarios demandés

| # | Scénario demandé | Couverture |
|---|---|---|
| 1-6 | register/login/contexte/dashboard/wizard | Test critique #1 ci-dessus (réel) |
| 7 | utilisateur sans école accessible | **Non testable via un parcours réel** — voir §10 : aucun chemin public ne peut aujourd'hui produire une organisation à 0 école (`register` en crée toujours une, aucun `DELETE /schools` n'existe), et les rôles plateforme (seul autre cas menant à `empty`) ne sont créables que par seed direct en base, hors de portée d'un test E2E. La branche de code est simple (`schools.length === 0`) et revue manuellement, mais **je ne prétends pas l'avoir testée en conditions réelles** |
| 8 | utilisateur avec plusieurs écoles | Test #2 ci-dessus (réel) |
| 9 | utilisateur d'une autre organisation | Couvert par le test backend **déjà existant** `test_admin_a_cannot_list_schools_of_organization_b` (non dupliqué — c'est la garantie de sécurité réelle, au niveau où elle doit être appliquée) |
| 10 | session expirée | Couvert par `setup-wizard.spec.ts` (le mécanisme d'erreur de session, identique) + le test #3 exerce la même branche `error` de `AuthGate` |
| 11 | erreur API | Test #3 ci-dessus |

## 7. Sécurité

- Aucune modification de RBAC, RLS, ou du système JWT.
- `organization_id` utilisé pour `listSchools()` provient **exclusivement** de `me.roles` (donc
  du token JWT vérifié côté serveur), jamais d'une entrée utilisateur — aucune possibilité pour
  le client de demander les écoles d'une autre organisation.
- La garantie d'isolation reste imposée côté serveur (`ensure_permission` + RLS), pas seulement
  côté client — un appel forgé resterait bloqué en 403, comme le confirme le test backend
  existant réutilisé (§6, item 9).
- Le choix d'école mémorisé en `localStorage` est un confort d'navigation par navigateur, jamais
  une source d'autorisation : il ne fait que présélectionner une valeur parmi celles renvoyées
  par un appel déjà autorisé — sélectionner un id hors de cette liste n'est pas possible depuis
  l'UI, et serait de toute façon rejeté côté serveur par les endpoits consommateurs.

## 8. E2E

Voir §6. Le parcours critique demandé (NEW ADMIN → REGISTER → LOGIN → DASHBOARD → SETUP WIZARD)
est vérifié réellement, sans mock, et passe.

## 9. Régressions

- Enseignants : inchangé — leur rôle est toujours créé scopé école via `users.create()`
  (`school_id` explicite), donc ils empruntent le chemin prioritaire n°1, jamais touché.
- Parents : inchangé, même raison ; portail mobile non touché (aucun fichier `apps/mobile`
  modifié).
- RBAC : inchangé, aucune permission ajoutée/retirée/modifiée.
- RLS : inchangée, aucune migration.
- `pytest` 114/114, `ruff` clean, `mypy` clean (68 fichiers), `eslint` clean, `tsc` clean,
  `next build` réussi.
- `apps/web/e2e/setup-wizard.spec.ts` (Phase 8) : 6/6, confirmant qu'aucune régression n'a été
  introduite dans le wizard lui-même (non modifié).

## 10. Problèmes différés

- **État `empty` non exerçable en E2E réel** (voir §6, item 7) : documenté, pas un défaut du
  correctif — juste hors de portée d'un test de bout en bout avec les moyens publics actuels de
  l'application.
- **`dev_reset_token` / distribution des comptes** : explicitement hors périmètre (rappelé par
  la consigne), non traité.
- Le README racine reste désynchronisé (déjà noté en Phase 8 Discovery) — non traité ici, hors
  périmètre.

## 11. Verdict

**GO**

Le parcours REGISTER → LOGIN → DÉTERMINATION DU CONTEXTE ÉCOLE → DASHBOARD → SETUP WIZARD
fonctionne réellement pour un administrateur nouvellement créé, vérifié sans mock. Aucune
régression détectée. Aucune migration. Aucun module hors périmètre touché.

---

PHASE 8.1 COMPLETE

Status:
GO

Pilot onboarding:
WORKING

Tests:
pytest 114/114 — ruff clean — mypy clean (68 fichiers) — eslint clean — tsc clean — next build OK
Playwright admin-onboarding 3/3 (dont le parcours critique réel, sans mock) — setup-wizard 6/6 — smoke 3/3

Migration:
NO

ATTENDRE VALIDATION.
