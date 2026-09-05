# PHASE 9 IMPLEMENTATION REPORT

## 1. Objectif

Implémenter le candidat classé #1 de `docs/phases/PHASE_9_DISCOVERY.md` : une infrastructure
d'email transactionnel minimale, strictement limitée à l'invitation de compte et la
réinitialisation de mot de passe — pour que les comptes enseignants/parents créés par un admin
puissent réellement être activés sans transmission manuelle hors application d'un jeton.

## 2. Candidat implémenté

**Candidat 1 — Infrastructure d'email transactionnel (invitation de compte + réinitialisation de
mot de passe)**, seul candidat traité. Les candidats #2 (dashboard), #3 (notifications in-app)
et #4 (import enseignants en masse) n'ont pas été entamés, conformément à la consigne.

## 3. Fonctionnalités réalisées

- Abstraction `EmailProvider` (backend), mêmes principes que `StorageProvider` : `send()`
  abstrait, `LocalEmailProvider` (dev/tests, écrit chaque email en fichier), `SmtpEmailProvider`
  (envoi réel, bibliothèque standard uniquement).
- `POST /auth/forgot-password` déclenche désormais un envoi réel (best-effort) en plus du
  comportement existant (`dev_token` toujours renvoyé hors production, inchangé).
- `POST /users` (création de compte) déclenche un envoi d'invitation réel (best-effort) pour
  tout **nouvel** utilisateur, en plus du comportement existant (`dev_reset_token`, inchangé).
- Deux nouvelles pages web publiques : `/forgot-password` (demande) et `/reset-password?token=...`
  (définition du nouveau mot de passe), toutes deux pilotant les endpoints existants
  `POST /auth/forgot-password` / `POST /auth/reset-password` sans aucun changement de contrat.
- Lien « Mot de passe oublié ? » ajouté sur la page de connexion.
- L'écran Utilisateurs affiche désormais un message de confirmation d'envoi réel (« un email
  d'invitation a été envoyé ») hors développement, et conserve l'affichage du lien en clair
  uniquement en développement (comportement déjà existant, texte clarifié).

## 4. Scope IN respecté

Envoi d'email réel à la création d'un compte ✅, envoi d'email réel pour `forgot-password` ✅,
configuration via variables d'environnement sans fournisseur figé ✅, templates texte
minimalistes ✅. Rien de plus n'a été ajouté.

## 5. Scope OUT respecté

Aucun SMS, aucune notification push, aucune notification métier (bulletin publié, absence),
aucune messagerie/annonce, aucun dashboard, aucun import en masse, aucune finance, aucun
paiement, aucune IA, aucun offline, aucun refactoring général de `auth`, aucune nouvelle
architecture de communication généraliste. Vérifié fichier par fichier lors de la relecture
finale (§6/§7) — aucun débordement.

## 6. Fichiers créés

- `apps/api/app/core/email.py`
- `apps/api/tests/test_email.py`
- `apps/web/app/(auth)/forgot-password/page.tsx`
- `apps/web/app/(auth)/reset-password/page.tsx`
- `apps/web/e2e/password-reset.spec.ts`

## 7. Fichiers modifiés

- `apps/api/app/core/config.py` — nouveaux réglages email (voir §12).
- `apps/api/app/modules/auth/service.py` — `request_password_reset` déclenche un envoi.
- `apps/api/app/modules/users/service.py` — `create_or_attach_user` déclenche un envoi pour un
  nouvel utilisateur.
- `.env` / `.env.example` — nouvelles variables `EMAIL_*` / `SMTP_*`.
- `apps/web/lib/auth/client.ts` — ajout de `forgotPassword()` / `resetPassword()`.
- `apps/web/app/(auth)/login/page.tsx` — lien « Mot de passe oublié ? ».
- `apps/web/app/(app)/users/page.tsx` — texte de confirmation d'envoi.

Aucun autre fichier `apps/api`, `apps/mobile`, RBAC, wizard (`apps/web/app/(app)/setup/*`),
attendance, grades, report_cards ou parent portal n'a été modifié.

## 8. Changements backend

Voir §3/§7. Aucun changement de contrat d'API (mêmes endpoints, mêmes schémas de requête/réponse,
`dev_token`/`dev_reset_token` inchangés) — uniquement un effet de bord supplémentaire (envoi
d'email) ajouté aux services existants.

## 9. Changements frontend

Deux nouvelles pages publiques + un lien + un texte clarifié (voir §3/§7). Aucune page existante
(dashboard, wizard, académique, etc.) modifiée au-delà de `login/page.tsx` et `users/page.tsx`.

## 10. Changements mobile

**Aucun.** Le flux de connexion mobile est inchangé ; aucun fichier `apps/mobile` modifié.

## 11. Migrations éventuelles

**Aucune.** `alembic current` confirmé à `0008 (head)` après implémentation, inchangé.

## 12. Dépendances éventuelles

**Aucune nouvelle dépendance.** `SmtpEmailProvider` n'utilise que la bibliothèque standard
Python (`smtplib`, `email.message`) — rien ajouté à `pyproject.toml`/`requirements.txt`, rien
ajouté à `package.json`. Nouvelles variables d'environnement (pas des dépendances logicielles) :
`EMAIL_PROVIDER`, `EMAIL_LOCAL_PATH`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
`SMTP_FROM_ADDRESS`, `SMTP_USE_TLS`.

## 13. Sécurité et isolation tenant

- Aucune modification de RBAC, RLS, JWT, ou du modèle de permissions.
- `PasswordResetToken` (déjà existant) reste la seule source de vérité pour définir un mot de
  passe — son expiration (30 minutes) et son usage unique (`used_at`) sont inchangés.
- L'envoi est **best-effort** (`send_email_best_effort`, `app/core/email.py`) : une panne
  d'envoi ne peut jamais faire échouer ni la création de compte ni la demande de
  réinitialisation, déjà commitées en base — même principe de robustesse déjà appliqué au rate
  limiting Redis (Phase 7.2).
- Garantie anti-énumération de compte préservée et renforcée : `forgot-password` sur un email
  inconnu ne déclenche toujours aucun `dev_token` (comportement existant) et, vérifié
  spécifiquement par un nouveau test, **aucun envoi d'email n'est déclenché non plus** dans ce
  cas (`test_forgot_password_unknown_email_sends_nothing`).
- Aucun secret nouveau exposé : les identifiants SMTP restent en variables d'environnement,
  jamais committés (`.env` reste dans `.gitignore`, inchangé).
- La page `/reset-password` ne fait confiance à aucun contrôle client : le jeton est validé
  côté serveur par l'endpoint existant, déjà testé (`test_password_reset_flow`).

## 14. Tests exécutés

- Suite `pytest` complète (120 tests, dont 6 nouveaux dans `test_email.py`).
- `ruff check .`, `mypy app`.
- `pnpm --filter @edusphere/web lint`, `type-check`, `build`.
- Suites Playwright existantes (`smoke.spec.ts`, `setup-wizard.spec.ts`,
  `admin-onboarding.spec.ts`) — non-régression.
- Nouvelle suite Playwright (`password-reset.spec.ts`, 4 tests) — exécutée réellement contre
  l'API + Postgres réels, aucun mock du backend. `dev_token` n'est utilisé que pour obtenir un
  jeton valide en préparation de test (même convention que les phases précédentes) ; le parcours
  UI lui-même (`/forgot-password`, `/reset-password`, connexion) est piloté entièrement via de
  vrais clics/saisies dans un vrai navigateur.

## 15. Résultats pytest

**120 passed**, 0 failed, 2 warnings pré-existants sans rapport avec cette phase (98.93s).

## 16. Résultats ruff

`All checks passed!`

## 17. Résultats mypy

`Success: no issues found in 69 source files` (68 → 69, nouveau fichier `email.py`).

## 18. Tests E2E/Playwright

- `password-reset.spec.ts` (nouveau) : **4/4** — message générique anti-énumération, lien
  invalide géré proprement, réinitialisation réelle de bout en bout (lien → mot de passe →
  connexion réussie), validation de correspondance des deux mots de passe.
- `setup-wizard.spec.ts` : **6/6** (non-régression).
- `admin-onboarding.spec.ts` : **3/3** (non-régression).
- `smoke.spec.ts` : **3/3** (non-régression).
- **Total : 16/16.**

## 19. Build

`next build` (via `docker compose build web`) : succès, toutes les routes compilées (incluant
`/forgot-password` et `/reset-password`), aucune erreur de type ni de build. ESLint et
`tsc --noEmit` : 0 avertissement/erreur.

## 20. Bugs découverts et corrigés

Aucun bug préexistant découvert pendant cette phase (contrairement aux Phases 8/8.1). Un seul
ajustement mineur en cours d'implémentation, corrigé avant tout test : la page
`/reset-password` utilise `useSearchParams()` (Next.js App Router), qui exige un boundary
`<Suspense>` pour ne pas échouer au build statique — ajouté dès l'écriture initiale, confirmé
sans erreur au premier `next build`.

## 21. Éléments différés

Rien de nouveau par rapport à ce que la Discovery avait déjà explicitement mis hors périmètre
(SMS, push, notifications métier, messagerie, dashboard, import en masse, finance, paiements,
IA, offline). Aucun nouvel élément différé identifié pendant l'implémentation.

## 22. Critères d'acceptation

| Critère | Statut |
|---|---|
| Un compte créé via `POST /users` déclenche un envoi d'email réel (au sens de l'abstraction `EmailProvider`) | ✅ Vérifié réellement (`test_create_user_triggers_invitation_email`) |
| `forgot-password` déclenche un envoi réel, jamais pour un compte inexistant | ✅ Vérifié réellement (`test_forgot_password_triggers_a_real_email_send`, `test_forgot_password_unknown_email_sends_nothing`) |
| Un enseignant/parent peut définir son mot de passe et se connecter en suivant uniquement le lien reçu, via l'UI réelle | ✅ Vérifié réellement (Playwright, `password-reset.spec.ts`) |
| Aucune régression | ✅ 120/120 pytest, 16/16 Playwright, ruff/mypy/lint/type-check/build tous propres |
| Aucune migration | ✅ `alembic current` = `0008 (head)`, inchangé |
| Aucune nouvelle dépendance | ✅ bibliothèque standard uniquement |

## 23. Verdict final

**GO**

L'infrastructure d'email transactionnel fonctionne réellement de bout en bout (backend et
frontend), sans régression, sans migration, sans nouvelle dépendance, strictement dans le
périmètre approuvé. Le maillon identifié en Phase 8 Discovery comme bloquant l'usage réel du
produit par les enseignants et les parents est levé.

---

PHASE 9 IMPLEMENTATION COMPLETE

Implemented:
Infrastructure d'email transactionnel (invitation de compte + réinitialisation de mot de passe)

Tests:
pytest 120/120 — ruff clean — mypy clean (69 fichiers) — eslint clean — tsc clean — next build OK
Playwright password-reset 4/4 (nouveau) — setup-wizard 6/6 — admin-onboarding 3/3 — smoke 3/3 (16/16 au total)

Migration:
NO

Dependencies:
Aucune (bibliothèque standard Python — smtplib/email.message — uniquement)

Status:
GO

WAITING FOR VALIDATION
