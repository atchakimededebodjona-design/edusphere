# PHASE 10.1 IMPLEMENTATION REPORT — Forgot Password Rate Limiting

## Objectif

Empêcher l'abus d'envoi d'emails de réinitialisation via `POST /api/v1/auth/forgot-password`,
resté sans rate limiting alors que la Phase 9 a rendu cet endpoint capable de déclencher un vrai
envoi d'email (email bombing possible contre un utilisateur réel).

## Inspection préalable (résumé)

- `app/core/rate_limit.py` (Phase 7.2) : compteur Redis par email (`login_attempts:<email>`),
  fail-open si Redis est injoignable (`except RedisError` → log warning, jamais de blocage),
  429 + en-tête `Retry-After` au dépassement.
- `auth/router.py::login` : `ensure_login_not_rate_limited` avant authentification,
  `register_failed_login_attempt` uniquement sur 401, `reset_login_attempts` sur succès.
- `auth/router.py::forgot_password` (avant modification) : aucun appel à `rate_limit`, réponse
  toujours identique (compte existant ou non) via `dev_token`.
- `auth/service.py::request_password_reset` : retourne le jeton brut uniquement hors
  `production` — comportement anti-énumération déjà en place au niveau service, inchangé.
- `config.py` : `login_rate_limit_max_attempts`/`window_seconds` déjà présents.
- `tests/test_auth_rate_limit.py` : 9 tests couvrant le login, tous réutilisés comme patron pour
  cette phase (mêmes conventions : Redis réel, `monkeypatch` pour la fenêtre, `_clear_key`).

## Limite choisie

**3 demandes par 15 minutes (900 secondes)** par email — plus strict que le login (5/300s),
car un envoi d'email coûte plus cher qu'une simple vérification de mot de passe, et une vraie
demande de réinitialisation reste un événement rare pour un utilisateur légitime (contrairement
à une tentative de connexion, qui peut légitimement échouer plusieurs fois de suite par
faute de frappe).

## Fenêtre

900 secondes (15 minutes), fenêtre fixe réinitialisée à la première demande (`EXPIRE` posé au
premier `INCR`, identique au mécanisme login).

## Clé utilisée

`forgot_password_attempts:<email en minuscules>` — Redis, préfixe **distinct** de
`login_attempts:` (login/Phase 7.2) : les deux mécanismes sont indépendants, l'un n'affecte
jamais l'autre (vérifié, voir §Tests).

## Comportement 429

Identique au login : `HTTP 429`, en-tête `Retry-After` (secondes restantes avant expiration du
compteur), détail générique (`"Too many password reset requests. Please try again later."`) —
aucune information sur l'existence du compte.

## Comportement Redis indisponible

**Fail-open**, identique au login : toute `RedisError` (y compris une erreur de connexion réelle)
est capturée, journalisée en `warning`, et la requête continue normalement (jamais de blocage,
jamais d'erreur 500). Vérifié réellement (§Tests, `test_redis_unavailable_fails_open`) en
pointant le client Redis partagé vers un port fermé.

## Fichiers modifiés

- `apps/api/app/core/rate_limit.py` — ajout de `_forgot_password_key`,
  `ensure_forgot_password_not_rate_limited`, `register_forgot_password_attempt`. **Aucune ligne
  du code login existant modifiée** (choix délibéré : petite duplication acceptée plutôt qu'un
  partage de code qui aurait touché un chemin de sécurité déjà testé — voir commentaire dans le
  fichier).
- `apps/api/app/core/config.py` — ajout de `forgot_password_rate_limit_max_attempts` (3) et
  `forgot_password_rate_limit_window_seconds` (900).
- `apps/api/app/modules/auth/router.py` — `forgot_password` appelle désormais
  `ensure_forgot_password_not_rate_limited` avant le service, puis
  `register_forgot_password_attempt` après (systématiquement, compte existant ou non). Aucune
  autre ligne modifiée ; `login`, `refresh`, `logout`, `reset_password` intacts.
- `.env` / `.env.example` — ajout de `FORGOT_PASSWORD_RATE_LIMIT_MAX_ATTEMPTS` /
  `FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS`.

**Fichier créé** : `apps/api/tests/test_forgot_password_rate_limit.py`.

Aucun fichier `apps/web`, `apps/mobile`, dashboard (Phase 10), wizard, email (`app/core/email.py`),
JWT, ou migration n'a été modifié.

## Migration

**Aucune.** `alembic current` confirmé à `0008 (head)`, inchangé.

## Dépendances

**Aucune nouvelle.** Réutilisation stricte de `redis` (déjà une dépendance depuis la Phase 7.2)
et du client Redis déjà instancié dans `app/core/rate_limit.py`.

## Sécurité

- Compteur par email (pas par IP), même raisonnement que le login : une école partage souvent
  une IP, un compteur par IP bloquerait des utilisateurs légitimes.
- Comptage strictement identique que le compte existe ou non — vérifié réellement
  (`test_no_account_existence_leak`, `test_nonexistent_account_is_rate_limited_identically`) :
  aucune fuite d'information nouvelle, la garantie anti-énumération déjà en place au niveau
  service (`dev_token`/réponse HTTP) est préservée et désormais protégée en amont par la limite.
- Fail-open préservé à l'identique du login : Redis reste un composant non critique pour
  l'authentification et la réinitialisation de mot de passe.
- Aucune nouvelle permission, aucune modification de JWT, aucune modification du flux métier
  `reset_password` (jeton, expiration 30 min, usage unique — tous inchangés).

## Tests

**`apps/api/tests/test_forgot_password_rate_limit.py` — 9 tests, exécutés réellement (Redis réel
du docker-compose, sans mock) :**

1. `test_normal_requests_below_threshold_are_allowed` — demandes normales sous le seuil.
2. `test_threshold_exceeded_returns_429` — dépassement de limite.
3. `test_rate_limit_window_expires_and_requests_succeed_again` — fenêtre de limitation (fenêtre
   réduite via `monkeypatch` pour un test rapide et déterministe, même convention que
   `test_auth_rate_limit.py`).
4. `test_existing_account_is_rate_limited` — compte existant.
5. `test_nonexistent_account_is_rate_limited_identically` — compte inexistant.
6. `test_no_account_existence_leak` — absence de fuite d'information.
7. `test_redis_unavailable_fails_open` — Redis indisponible (client pointé vers un port fermé,
   erreur de connexion réelle capturée par le fail-open).
8. `test_login_rate_limiting_still_works_independently` — régression login.
9. `test_reset_password_flow_still_works_after_rate_limited_request_window` — régression
   reset-password (flux complet jeton → nouveau mot de passe → connexion).

## Résultats pytest

**135 passed**, 0 failed (126 précédents + 9 nouveaux), 2 warnings pré-existants sans rapport
avec cette phase (108.97s).

## Résultats ruff

`All checks passed!`

## Résultats mypy

`Success: no issues found in 70 source files` (inchangé — aucun nouveau fichier sous `app/`).

## Playwright

Suites pertinentes réexécutées réellement (endpoint modifié = `forgot-password`, exercé par
`password-reset.spec.ts`) :
- `password-reset.spec.ts` : **4/4** (aucun test n'appelle `forgot-password` plus de 3 fois pour
  le même email — sous la nouvelle limite, aucun impact).
- Suites additionnelles revérifiées par prudence : `setup-wizard.spec.ts` 6/6,
  `admin-onboarding.spec.ts` 3/3, `dashboard.spec.ts` 3/3, `smoke.spec.ts` 3/3.
- **Total : 19/19.**

## Build

Aucun fichier frontend modifié — build web non nécessaire pour cette phase (dernière image déjà
construite et vérifiée en Phase 10 reste valide).

## Verdict

**GO**

Le rate limiting de `forgot-password` fonctionne réellement, réutilise l'infrastructure Redis et
le mécanisme déjà en place (structure, philosophie fail-open, en-tête `Retry-After`), sans
toucher une seule ligne du rate limiting login existant, sans migration, sans nouvelle
dépendance, sans régression sur l'authentification ou la réinitialisation de mot de passe.

---

PHASE 10.1 COMPLETE

Status:
GO

WAITING FOR VALIDATION
