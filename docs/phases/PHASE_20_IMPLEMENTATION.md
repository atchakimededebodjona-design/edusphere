# Phase 20 Implementation Report — Security & Pre-Pilot Hardening

Chaque affirmation ci-dessous distingue **PROUVÉ RÉELLEMENT** (exécution réelle observée) de
**NON VÉRIFIÉ** (jamais transformé en preuve). Une interruption d'environnement (Docker Desktop,
détaillée en §17) a coupé la toute fin de la campagne de validation — ce rapport le documente
explicitement plutôt que de la masquer.

## 1. Executive Summary

Quatre sujets traités, exactement le périmètre validé par `PHASE_20_DISCOVERY.md` : (A) rate
limiting complété sur `register`/`refresh`/`verify-by-code` (le "verify-by-code" de la Discovery
désigne en réalité `GET /report-cards/verify/{code}` — aucun endpoint de vérification de compte
par code n'existe dans ce dépôt, voir §3), (B) audit transport/CORS/headers avec ajout de 4
en-têtes de sécurité sans risque, HTTPS documenté comme prérequis non fabriqué, (C) RLS ajoutée
sur `organizations` (gap MEDIUM connu depuis la Phase 1), (D) traçabilité obligatoire des
ajustements manuels de `StudentFee`. Migration unique `0010`. 25 nouveaux tests, tous passés
avant l'interruption d'environnement de fin de session (voir §17 pour l'état exact des dernières
vérifications).

## 2. État initial

Confirmé avant toute modification : `HEAD` = `32209dd` (Phase 19), arbre de travail propre,
`docs/phases/PHASE_19_DISCOVERY.md`/`PHASE_19_IMPLEMENTATION.md`/`PHASE_20_DISCOVERY.md` lus
intégralement. Aucun push effectué depuis la Phase 19 (confirmé : `origin/main` toujours à
`46e9cf5` au début de cette phase).

## 3. Écarts Discovery ↔ code

**Écart critique trouvé et corrigé avant tout code** : la Discovery (et la commande
d'implémentation elle-même) nomme "verify-by-code" comme un des trois endpoints à protéger.
Vérification par grep exhaustif (`verify` sur tout `apps/api/app`) : **aucun endpoint de
vérification de compte utilisateur par code n'existe dans ce dépôt** — pas de flux
email-verification, pas de 2FA. Le seul endpoint "verify" trouvé est
`GET /report-cards/verify/{code}` (vérification publique d'un bulletin via QR code, Phase 5).
C'est cet endpoint qui a été protégé — documenté ici pour que la divergence de nom avec la
Discovery ne soit jamais interprétée comme un oubli.

**Deuxième écart, découvert pendant l'implémentation, pas anticipé par la Discovery** : ajouter
RLS à `organizations` a révélé un bug préexistant dans
`organizations/router.py::update_organization` — l'ordre `commit()` puis `refresh()` (inversé par
rapport à la convention `flush → refresh → commit` déjà établie ailleurs, ex.
`schools/router.py::update_school`) fonctionnait par accident tant que `organizations` n'avait
aucune RLS. Avec RLS + FORCE activés, le `refresh()` après `commit()` échouait
(`InvalidRequestError: Could not refresh instance`) car le contexte tenant (`SET LOCAL`
équivalent) expire au commit. Corrigé en réordonnant en `flush → refresh → commit`, comme partout
ailleurs. Ce n'est pas un bug introduit par cette phase — c'est un bug dormant révélé par le
durcissement, corrigé dans le périmètre strict de la Phase 20 (aucune fonctionnalité changée,
seulement l'ordre de deux appels déjà présents).

Aucun autre écart trouvé — le reste de la Discovery correspondait exactement au code réel.

## 4. Rate limiting

Trois fonctions ajoutées à `apps/api/app/core/rate_limit.py`, suivant exactement le motif déjà
établi (login/forgot-password : compteur Redis, fail-open sur `RedisError`, `429` +
`Retry-After`) :

| Endpoint | Clé | Seuil par défaut | Justification de la clé |
|---|---|---|---|
| `POST /auth/register` | IP | 20 / 3600s | Créer une organisation n'est jamais un trafic légitime récurrent partagé par une école (contrairement au login) — voir §4.1 pour l'ajustement réel du seuil |
| `POST /auth/refresh` | `user_id` (résolu après validation du jeton) | 30 / 300s | Le jeton tourne à chaque appel (rotation déjà en place depuis la Phase 1) — une clé basée sur le jeton ne verrait jamais plus d'une requête par fenêtre |
| `GET /report-cards/verify/{code}` | IP | 30 / 60s | Endpoint public, seule clé disponible ; le code a 384 bits d'entropie (`secrets.token_urlsafe(48)`), le brute-force reste infaisable indépendamment de cette limite |

Vérifié avant tout choix de seuil (§7 de la commande) : format des codes de vérification
(`generate_opaque_token()` = 384 bits), durée de validité (aucune pour le code de bulletin — il
ne périme jamais, contrairement à un token de reset password), stockage (le code EST la clé
primaire `verification_code`, indexé unique), Redis déjà utilisé pour login/forgot-password
(convention réutilisée à l'identique).

### 4.1 Ajustement réel du seuil `register` (5 → 20)

Choix initial : 5/heure par IP, par analogie avec le raisonnement "register est rare". **Corrigé
sur preuve réelle, pas sur supposition** : en tentant d'exécuter la suite Playwright réelle de ce
dépôt (`apps/web/e2e/`) contre la stack Docker vivante, la première requête a révélé que **toutes
les requêtes d'un navigateur Playwright résolvent à la même IP de boucle locale (`127.0.0.1`,
constaté via la clé Redis `register_attempts:127.0.0.1` réellement créée)**, et que cette seule
suite déclenche plus de 5 inscriptions réelles dans une même exécution (3 scénarios dans
`admin-onboarding.spec.ts` + plusieurs dans `setup-wizard.spec.ts`). Relevé à 20/heure en
conséquence. Exactement l'exemple que la consigne anticipait ("ne pas inventer un seuil
arbitraire") — ici corrigé par une preuve réelle observée en cours de phase, pas laissé tel quel.

### 4.2 Piège de test découvert et corrigé

`register_school()` (helper partagé par la quasi-totalité des ~230 tests existants) appelle
`POST /auth/register` des dizaines de fois par exécution de suite — sous `httpx.ASGITransport`,
toutes ces requêtes partagent la même IP factice. Sans correction, le nouveau rate limiting
`register` aurait bloqué la suite de tests **existante** dès le 6ᵉ appel, bien avant tout test
dédié au rate limiting. Corrigé en ajoutant un nettoyage du compteur Redis `register_attempts:*`
au début de `register_school()` (`apps/api/tests/conftest.py`) — motif équivalent au
`_clear_key(email)` déjà utilisé par les tests de rate limiting login/forgot-password, appliqué
une fois pour toutes dans le helper partagé. Le rate limiting réel reste testé indépendamment par
les tests dédiés (§7), qui gèrent leur propre fenêtre.

## 5. HTTPS

**Aucun HTTPS de production déclaré "GO"** — conformément à la règle explicite de cette phase.
Audit complet effectué (Docker, reverse proxy, cookies, CORS, URLs, liens de reçus) :

**Déjà prêt côté application** (vérifié, pas supposé) : aucun cookie n'est utilisé nulle part
(web : `localStorage`, mobile : `expo-secure-store`) — donc aucun attribut `Secure`/`SameSite` à
ajouter, ils ne s'appliquent qu'à des cookies inexistants ici. Toutes les URLs consommées
(`NEXT_PUBLIC_API_URL`, `EXPO_PUBLIC_API_URL`, `PUBLIC_BASE_URL`, `PUBLIC_WEB_BASE_URL`) sont déjà
des variables d'environnement — passer en `https://` est un changement de configuration, pas de
code. `CORS_ALLOWED_ORIGINS` est déjà une liste explicite, jamais `*` en dur.

**Reste un prérequis de déploiement, NON VÉRIFIÉ** : aucun reverse proxy réel n'existe
(`infrastructure/nginx/` reste un placeholder Phase 0, volontairement non remplacé par une
configuration fabriquée), aucun domaine/certificat réel. Documenté en détail, avec la
configuration nginx recommandée pour le jour où un hébergement réel existe, dans
`docs/deployment/PRODUCTION_CONFIGURATION.md` (section "HTTPS / Transport Security").

## 6. Security headers

Middleware ajouté (`apps/api/app/main.py::security_headers_middleware`), 4 en-têtes sans risque
de régression fonctionnelle : `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: geolocation=(),
camera=(), microphone=()`.

Volontairement **absents**, avec justification : `Strict-Transport-Security` (n'a de sens que
posé par un reverse proxy qui termine réellement le TLS — voir §5) et `Content-Security-Policy`
(cible pertinente = `apps/web`/Next.js, pas cette API JSON ; une CSP mal calibrée peut casser
silencieusement l'hydratation Next.js sans un environnement réel pour la valider — consigne
explicite de ne jamais l'ajouter à l'aveugle).

**Vérifié réellement en conditions live** (pas seulement par test unitaire) :
```
GET http://localhost:8000/api/v1/health
x-content-type-options: nosniff
x-frame-options: DENY
referrer-policy: strict-origin-when-cross-origin
permissions-policy: geolocation=(), camera=(), microphone=()
```
Les 2 tests dédiés (`test_security_headers_present_on_every_response`,
`test_security_headers_present_on_error_responses_too`) ont été écrits et exécutés une fois avec
succès avant la dernière reconstruction d'image ; leur ré-exécution finale après le tout dernier
changement (ajustement du seuil `register`) a été interrompue par la panne Docker de fin de
session (§17) — la vérification HTTP live ci-dessus, faite après cette même reconstruction,
reste la preuve la plus directe possible de leur bon fonctionnement en pratique.

## 7. CORS

Audité, jugé sain : `allow_origins` = liste explicite (jamais `*` en dur dans le code),
`allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`. Aucune modification de
code — `allow_credentials=True` combiné à une origine `*` littérale serait dangereux, mais la
liste n'est jamais `*` dans le code, seulement configurable via `.env`. Point documenté (pas
corrigé par du code, aucun risque réel identifié puisqu'aucun cookie n'existe) : ne jamais définir
`CORS_ALLOWED_ORIGINS=*` en pilote/production.

## 8. RLS organizations

Migration `0010` : `ALTER TABLE organizations ENABLE/FORCE ROW LEVEL SECURITY` +
`CREATE POLICY organizations_tenant_isolation` — motif identique aux 29 autres tables déjà
protégées, avec `id` comme colonne de comparaison (cette table EST la racine tenant, pas de
colonne `organization_id` séparée). `register` (création d'organisation) continue de fonctionner
sans changement : il s'exécute déjà sous `set_platform_wide_context(db)` (Phase 1), qui bypasse
la policy exactement comme pour `schools`/`user_roles`. `create_school` ne lit jamais la table
`organizations` — aucun impact. Seul `organizations/router.py::update_organization` nécessitait
une correction (§3).

## 9. StudentFee.updated_by

Colonne `updated_by` (UUID, nullable, FK `users.id ON DELETE SET NULL`) ajoutée à `student_fees`
(migration `0010`). Nullable : les lignes créées par `generate_student_fees` ne sont l'œuvre
d'aucun utilisateur en particulier — seul un ajustement manuel via `PATCH /student-fees/{id}`
renseigne ce champ, quel que soit le champ modifié (montant, échéance, ou note seule).

## 10. Ajustements financiers

`fees/router.py::update_student_fee` durci : une **note non vide devient obligatoire** dès que
`amount_due` est fourni dans la requête (rejet `422` sinon, y compris une note composée
uniquement d'espaces). Autorisation inchangée (`fees.manage`, déjà scopée tenant/école par
`ensure_permission`) ; contexte tenant inchangé (RLS déjà en place depuis la Phase 19 sur
`student_fees`). Pas de système comptable construit — un seul champ, une seule règle de
validation, conforme à la consigne anti-sur-ingénierie.

## 11. Authorization / IDOR

Aucune nouvelle route sensible introduite cette phase (uniquement des durcissements sur des
routes existantes). Ré-audité par les tests §16 (Phase 19 revisitée avec un regard sécurité) :
`organizations`, `schools`, `student_fees`, `payments` — tous confirmés correctement scopés par
tenant, aucune régression IDOR trouvée. Motif 404 (anti-énumération) confirmé inchangé pour le
module `parent`.

## 12. Authentication hardening

Aucune réécriture du système d'authentification (conforme à la consigne). Seul changement :
`refresh()` (`auth/service.py`) vérifie désormais le rate limiting **après** validation du jeton
et **avant** toute mutation (révocation/émission) — un jeton invalide ne consomme jamais de
compteur, une requête rate-limitée ne brûle jamais un jeton encore valide. Rotation de jeton,
expiration JWT, révocation de session : tous inchangés, tous re-testés sans régression (§16).

## 13. Secrets

Audit du diff complet Phase 20 (`git diff --cached`) par recherche de motifs de secrets
(mots de passe, clés API, clés privées, préfixes de clés connus) : **SECRET FOUND: NO**. Seules
les valeurs de test déjà connues du dépôt (`SuperSecret123`, etc.) apparaissent, sans rapport avec
un secret réel. `.env`/`.env.example` non modifiés cette phase.

## 14. Logging

Aucun nouveau log ajouté ne contient de secret — les nouveaux `logger.warning(...)` de
`rate_limit.py` (Redis indisponible) suivent exactement le motif déjà en place pour
login/forgot-password (message fixe, jamais de valeur utilisateur/jeton/mot de passe interpolée).

## 15. Error handling

`429` avec `Retry-After` pour les 3 nouveaux rate limits (cohérent avec l'existant), `422` pour
note manquante sur ajustement de frais, `404` inchangé pour `organizations`/`schools` cross-tenant
(RLS rend la ligne invisible avant même la vérification de permission — comportement déjà
accepté pour `schools` depuis la Phase 1, désormais identique pour `organizations`). Aucune trace
technique, aucune fuite tenant observée dans les réponses d'erreur testées.

## 16. Migration

`apps/api/alembic/versions/0010_security_hardening.py` — additive, ne modifie aucune migration
0001-0009. Validations réelles effectuées :
- `alembic current` (0009) → `alembic upgrade head` → `0010 (head)` sur la base de développement
  réelle : **PROUVÉ**.
- Chaîne complète `0001 → 0010` rejouée sur un Postgres 16 jetable (conteneur + réseau Docker
  dédiés, détruits après coup) : **PROUVÉ**, succès intégral.
- `downgrade`/`upgrade` spécifiquement pour la révision `0010` (isolée) : **NON VÉRIFIÉ** — fait
  pour `0009` en Phase 19, pas répété pour `0010` avant que Docker Desktop ne devienne
  indisponible (voir §17). Le `downgrade()` de `0010` a été relu manuellement (symétrique exact de
  l'`upgrade()` : `DROP COLUMN`, puis `DROP POLICY`/`NO FORCE`/`DISABLE ROW LEVEL SECURITY`) mais
  jamais exécuté.

## 17. Tests

**25 nouveaux tests** (`apps/api/tests/test_security_hardening.py`) : rate limiting register (5),
rate limiting refresh (6), rate limiting verify-by-code (4), security headers (2), RLS
organizations (5 : raw session + `pg_class.relrowsecurity/relforcerowsecurity` + `pg_policy` +
non-régression lecture/écriture propre organisation + non-régression création), traçabilité
StudentFee (5).

**État réel des exécutions, dans l'ordre chronologique** (transparence totale, comme demandé) :
1. `test_security_hardening.py` seul, 25 tests (sans les 2 tests d'en-têtes, ajoutés plus tard) :
   **25 passed** — après correction de 8 échecs réels trouvés et corrigés (setup d'inscription
   manquant dans un helper de test, bug de rotation de jeton dans un test, ordre commit/refresh
   dans `organizations/router.py`, nettoyage du rate limit register dans `conftest.py`).
2. Suite complète (`pytest -q`, tous fichiers), avec le seuil `register=5` et sans les en-têtes de
   sécurité : **233 passed** (208 existants + 25 nouveaux), **PROUVÉ RÉELLEMENT**, zéro régression.
3. Après ajout des en-têtes de sécurité (2 tests de plus, 27 au total dans le fichier) et
   reconstruction de l'image : `ruff check .` → clean ; `mypy app` → clean, 78 fichiers.
4. Tentative de suite complète après l'ajout des en-têtes : interrompue par ma propre recréation
   du conteneur (exit 137) — pas un échec de test, une interruption que j'ai moi-même causée en
   enchaînant une reconstruction pendant qu'un test tournait encore.
5. Découverte réelle (via tentative Playwright, voir §4.1) que le seuil `register=5` était trop
   bas ; ajustement à `20`, reconstruction de l'image.
6. `mypy app` (sur le code final) → clean, 78 fichiers — **PROUVÉ**.
7. Nouvelle tentative de suite complète : a affiché ~70/233 tests réussis (aucun échec visible
   dans la portion affichée) puis s'est arrêtée sur une erreur de flux (`EOF`) côté `docker exec` —
   très probablement causée par des commandes Docker concurrentes que j'exécutais en parallèle
   (vidage Redis, tentative Playwright). **NON CONCLUANT**, pas un échec confirmé.
8. Nouvelle tentative : **Docker Desktop s'est arrêté complètement** (`docker ps`/`docker version`
   échouent avec "failed to connect to the docker API", aucun processus Docker restant,
   confirmé par `Get-Process`). Plusieurs tentatives de reconnexion (avec attente) sur ~2 minutes :
   toujours indisponible. Aucun service Windows Docker n'existe sur cet hôte pour le redémarrer
   par commande ; un redémarrage nécessiterait une action manuelle (interface graphique) hors de
   portée de cette session.

**Conclusion honnête sur les tests** : la logique de chacun des 25 nouveaux tests a été prouvée
correcte à un instant donné (étape 1, avec `register=5`). Le changement de seuil `register`
5→20 est un changement de constante pure (aucune logique modifiée) sur un test déjà conçu pour
être agnostique au seuil (`settings.register_rate_limit_max_attempts` lu dynamiquement, jamais la
valeur `5` codée en dur) — la confiance dans sa validité à `20` est très élevée mais **NON
RECONFIRMÉE par une exécution complète après ce changement précis**, à cause de la panne Docker.
Les en-têtes de sécurité sont, eux, prouvés en conditions live (§6) indépendamment de pytest.

**Ce qui reste explicitement NON VÉRIFIÉ à la fin de cette phase**, à ré-exécuter dès que Docker
est de nouveau disponible :
- Suite complète (`pytest -q`) contre l'état final exact du code (en-têtes + `register=20`
  ensemble).
- `downgrade`/`upgrade` isolé de la migration `0010` (voir §16).
- Suite Playwright réelle (`apps/web/e2e/`) — browsers désormais installés (`npx playwright
  install chromium` réussi), mais le binaire Chrome Headless Shell téléchargé est incompatible
  avec la libc musl de l'image `node:20-alpine` (`apps/web/Dockerfile`) :
  `Error relocating ... posix_fallocate64: symbol not found`. **Contrainte d'environnement
  préexistante, indépendante de cette phase** — l'image web n'a jamais été conçue pour exécuter un
  navigateur automatisé (c'est un serveur Next.js de production). Non corrigé ici (ajouter une
  couche de compatibilité glibc à une image de production serait hors périmètre d'une phase de
  durcissement sécurité). Playwright reste donc **NON VÉRIFIÉ** dans cet environnement, comme
  documenté par les phases précédentes.

## 18. Web

Aucun changement de code web cette phase (aucun besoin identifié — pas de cookies, URLs déjà
paramétrées). Revalidé tel quel, **avant** la panne Docker :
```
pnpm run lint         → ✔ No ESLint warnings or errors
pnpm run type-check   → (aucune erreur)
pnpm run build        → ✓ Compiled successfully, 18 routes
```
Playwright : voir §17 (NOT VERIFIED, contrainte d'environnement).

## 19. Mobile

Aucun changement de code mobile (aucun besoin identifié — API_URL déjà paramétrée, pas d'écriture
financière mobile, non demandée). `tsc --noEmit` via conteneur `node:20-alpine` temporaire
(indépendant du crash Docker Desktop, exécuté séparément) : **0 erreur, PROUVÉ**.

## 20. Docker

Avant la panne (§17) : `docker compose config --quiet` → exit 0 ; `docker compose ps` → 4/4 `Up`,
`api`/`db`/`redis` `(healthy)` ; `GET /health` → `{"status":"ok"}` ; `GET /ready` →
`{"status":"ready","checks":{"database":"ok","redis":"ok","storage":"ok"}}` — tous **PROUVÉS
RÉELLEMENT** sur l'état final du code (en-têtes + `register=20`), juste avant que Docker Desktop
ne s'arrête. Aucun volume supprimé, aucune donnée réinitialisée à aucun moment de cette phase.

## 21. Backup/restore

Sauvegarde réelle exécutée sur le schéma Phase 20 (`scripts/windows/backup-all.ps1`, avant la
panne Docker) :
```
Backup DB OK: backups\edusphere_20260905T142803Z.dump (5783.1 KB) - intégrité vérifiée (pg_restore --list)
Backup storage OK: backups\storage_20260905T142803Z.tar.gz (818.8 KB) - 389 fichiers, intégrité vérifiée
Copie externe vérifiée (SHA-256 identique) — D:\EduSphere-Backups\...
```
**PROUVÉ RÉELLEMENT** : le mécanisme de sauvegarde reste pleinement compatible avec le schéma
Phase 20 (RLS `organizations`, colonne `student_fees.updated_by`) — `pg_dump` ne fait aucune
hypothèse sur le contenu du schéma, seulement sur la connectivité. Un test de restauration
complet vers une base dédiée (comme en Phases 15/17) n'a **pas** été répété cette phase — jugé
redondant avec la preuve déjà apportée à deux reprises que le mécanisme de restauration
fonctionne, combiné à la preuve ci-dessus que la sauvegarde elle-même reste intacte sur ce schéma ;
**NON VÉRIFIÉ explicitement cette phase**, à noter comme tel plutôt que supposé.

## 22. Fichiers modifiés

16 fichiers (1434 insertions, 7 suppressions) :

**Nouveaux** : `apps/api/alembic/versions/0010_security_hardening.py`,
`apps/api/tests/test_security_hardening.py`, `docs/phases/PHASE_20_DISCOVERY.md` (Discovery,
phase précédente), `docs/phases/PHASE_20_IMPLEMENTATION.md` (ce fichier).

**Modifiés** : `apps/api/app/core/config.py` (3 nouveaux blocs de settings), `apps/api/app/core/
rate_limit.py` (+131 lignes, 3 nouvelles paires de fonctions), `apps/api/app/main.py` (middleware
d'en-têtes), `apps/api/app/modules/auth/router.py` (register), `apps/api/app/modules/auth/
service.py` (refresh), `apps/api/app/modules/fees/models.py` (`updated_by`),
`apps/api/app/modules/fees/router.py` (validation note obligatoire), `apps/api/app/modules/fees/
schemas.py` (`updated_by` exposé), `apps/api/app/modules/organizations/router.py` (correction
ordre flush/refresh/commit), `apps/api/app/modules/report_cards/router.py` (verify),
`apps/api/tests/conftest.py` (nettoyage rate limit register), `apps/api/tests/
test_tenant_isolation.py` (403→404 accepté pour organizations, cohérent avec schools),
`docs/deployment/PRODUCTION_CONFIGURATION.md` (sections rate limiting/HTTPS/headers/CORS).

Aucune migration historique modifiée, aucun test supprimé, aucun fichier `.env` touché, aucune
nouvelle dépendance.

## 23. Commit

Audit pré-commit : `git status --porcelain` (liste exacte ci-dessus), `git diff --cached` relu,
grep de motifs de secrets sur le diff complet → **SECRET FOUND: NO**.

Commit **non encore créé au moment de la rédaction de ce rapport** — voir §27 (critère spécial) :
la panne Docker de fin de session empêche de reconfirmer l'état final exact avant de committer,
conformément à la règle "ne jamais transformer une hypothèse en preuve". Le commit sera créé dès
que la suite complète aura pu être rejouée avec succès contre le code final (voir §17), pas avant.

## 24. Limites

Seuils de rate limiting choisis pour un pilote, pas des valeurs de sécurité absolues (documenté
comme tel). `verify-by-code` protégé mais son entropie rend déjà le brute-force infaisable
indépendamment de cette limite — protection en profondeur, pas une correction d'une vulnérabilité
exploitable aujourd'hui. HTTPS reste un prérequis de déploiement non vérifié (jamais affirmé
autrement). `Content-Security-Policy` volontairement non ajoutée (risque de casser Next.js sans
environnement réel pour la tester). Aucun audit log global construit (hors périmètre explicite) —
seule la lacune `StudentFee.updated_by` a été fermée.

## 25. Risques résiduels

HTTPS/TLS toujours absent — le risque le plus important documenté, hors de portée du code
applicatif seul. Rate limiting register/refresh/verify reste par IP ou user_id, pas une défense
absolue contre un attaquant distribué (defense-in-depth, pas une garantie). Livraison SMTP externe
toujours jamais prouvée (Phase 16/17, inchangé). Validation mobile réelle sur device toujours
jamais faite (Phase 12, inchangé). **Nouveau risque résiduel de cette phase** : la suite de tests
complète n'a pas été reconfirmée dans son état final exact après le tout dernier ajustement de
seuil, à cause de la panne d'environnement documentée en §17 — à refaire avant de considérer cette
phase totalement close.

## 26. Production readiness

Verdict inchangé par rapport à la Phase 19 Discovery : **B. PILOT READY**, avec les mêmes réserves
qu'avant (HTTPS, SMTP externe, validation mobile réelle) plus, désormais, deux gaps
spécifiquement fermés (RLS organizations, traçabilité StudentFee) et un rate limiting complété. Ne
devient pas C. PRODUCTION READY pour cette seule raison — HTTPS reste la lacune la plus
structurante, indépendante de tout travail applicatif possible dans cette session.

## 27. Verdict

**GO WITH NOTES**

Les 4 sujets du périmètre (rate limiting, HTTPS/headers/CORS, RLS organizations, traçabilité
StudentFee) sont tous traités avec une preuve réelle solide, obtenue avant l'interruption
d'environnement : migration appliquée et rejouée sur base neuve, RLS testée au niveau applicatif
ET au niveau catalogue PostgreSQL, traçabilité financière testée, 233 tests passés sans
régression à une étape intermédiaire stable, en-têtes de sécurité vérifiés en conditions live,
sauvegarde réelle confirmée compatible avec le nouveau schéma, ruff/mypy/web/mobile tous clean.

Le "WITH NOTES" reflète honnêtement ce qui n'a **pas** pu être reconfirmé à cause de la panne
Docker Desktop survenue en fin de session (§17) : une exécution complète et unique de la suite de
tests contre l'état final exact du code (après le dernier ajustement de seuil), le cycle
`downgrade`/`upgrade` isolé de la migration `0010`, et l'exécution complète de la suite Playwright
(bloquée par une incompatibilité glibc/musl préexistante, sans rapport avec cette phase). Aucun de
ces points n'indique un défaut réel connu — ce sont des vérifications interrompues, pas des
échecs observés. Conformément à la règle de ce projet, ce rapport ne transforme pas cette absence
de preuve finale en une affirmation de succès : le commit (§23) est volontairement différé jusqu'à
ce que la suite complète ait pu être rejouée avec succès une dernière fois.
