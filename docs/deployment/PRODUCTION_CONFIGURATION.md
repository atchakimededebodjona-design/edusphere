# Configuration de déploiement — Développement vs Pilote/Production

Phase 14 (Deployment Durability & Production Configuration Readiness). Ce document liste les
variables d'environnement **réellement lues par le code** (`apps/api/app/core/config.py`,
`docker-compose.yml`) — aucune variable inventée — et clarifie lesquelles doivent
impérativement changer avant un déploiement pilote avec de vraies données d'école.

## Principe

Le développement local (`.env` actuel, valeurs par défaut) ne doit **jamais** être confondu avec
une configuration prête pour un pilote réel. Ce document existe pour rendre cette distinction
explicite et vérifiable, pas pour construire une nouvelle configuration.

## Variables obligatoires à changer avant un pilote réel

| Variable | Valeur dev actuelle | Pourquoi elle doit changer |
|---|---|---|
| `ENVIRONMENT` | `development` | **Critique** — tant que ce n'est pas `production`, l'API renvoie `dev_token`/`dev_reset_token` en clair dans les réponses API (`auth/service.py::request_password_reset`, `users/service.py::create_or_attach_user`) : n'importe qui interceptant une réponse HTTP obtient directement un token de réinitialisation de mot de passe ou d'activation de compte. Ce n'est acceptable qu'en développement. |
| `JWT_SECRET_KEY` | `replace_with_a_long_random_secret` (placeholder littéral dans `.env.example`) | Si cette valeur par défaut arrive en pilote, n'importe qui peut forger un token d'accès valide pour n'importe quel utilisateur. Doit être un secret long et aléatoire, généré pour ce déploiement, jamais réutilisé du dépôt. |
| `POSTGRES_PASSWORD` / `APP_DB_PASSWORD` | `changeme_local_only` / `changeme_app_role_local_only` | Noms explicitement "local only" dans le dépôt lui-même — à remplacer par des secrets générés, jamais committés. |
| `EMAIL_PROVIDER` | `local` | Tant que la valeur reste `local`, **aucun email n'est envoyé à une vraie adresse** — voir section dédiée ci-dessous. C'est la découverte centrale de la Phase 14 Discovery. |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Doit inclure le(s) domaine(s) réel(s) du frontend déployé, sinon le navigateur des utilisateurs bloque les appels API. |
| `PUBLIC_BASE_URL` / `PUBLIC_WEB_BASE_URL` | `http://localhost:8000` / `http://localhost:3000` | Utilisées pour construire les liens de vérification QR des bulletins et les liens dans les emails — doivent pointer vers les domaines réellement accessibles par les parents/écoles. |
| `NEXT_PUBLIC_API_URL` / `EXPO_PUBLIC_API_URL` | `http://localhost:8000` | Le web et le mobile ne pourront pas joindre l'API depuis un appareil réel si ces valeurs restent `localhost`. |

## Email — Local vs Production (Phase 9 + Phase 14)

Le code ne change pas : `EmailProvider` (`apps/api/app/core/email.py`) a **déjà** deux
implémentations, sélectionnées par `EMAIL_PROVIDER` :

| | `EMAIL_PROVIDER=local` (actuel) | `EMAIL_PROVIDER=smtp` (disponible, jamais activé en pratique) |
|---|---|---|
| Comportement | `LocalEmailProvider` écrit chaque email en fichier texte sous `EMAIL_LOCAL_PATH` (`./emails`) | `SmtpEmailProvider` envoie réellement via `smtplib` (bibliothèque standard, déjà présent dans `requirements.txt` — **aucune nouvelle dépendance**) |
| Livraison réelle | **Aucune** | Réelle, vers une vraie boîte mail |
| Usage prévu | Développement / tests uniquement | Pilote / production |
| Variables nécessaires | `EMAIL_LOCAL_PATH` | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_ADDRESS`, `SMTP_USE_TLS` (toutes déjà présentes dans `.env.example`, valeurs vides par défaut) |

**Pour activer un envoi réel avant un pilote** : renseigner un compte SMTP réel (fourni par
l'hébergeur ou un service tiers — décision opérationnelle, pas technique) dans les variables
`SMTP_*` ci-dessus, puis passer `EMAIL_PROVIDER=smtp`. Aucune modification de code n'est
nécessaire — l'abstraction existe déjà depuis la Phase 9 et n'a jamais été réellement activée.

**Ne jamais écrire ou dire "les emails sont configurés" tant que `EMAIL_PROVIDER=local`** — le
code fonctionne, mais aucun utilisateur réel ne reçoit quoi que ce soit.

## Stockage fichiers (Phase 14)

Voir [`docs/database/STORAGE_BACKUP_RESTORE.md`](../database/STORAGE_BACKUP_RESTORE.md) pour le
détail. En résumé : `STORAGE_LOCAL_PATH=./storage` reste valide pour un pilote de taille
modeste, désormais persisté via un bind mount Docker (`apps/api/storage/` sur l'hôte). Aucun
changement de variable nécessaire ; le risque corrigé était l'absence de montage, pas la valeur
de la variable elle-même.

## Variables avec une valeur par défaut raisonnable (optionnelles)

`LOG_LEVEL`, `LOGIN_RATE_LIMIT_MAX_ATTEMPTS`/`WINDOW_SECONDS`,
`FORGOT_PASSWORD_RATE_LIMIT_MAX_ATTEMPTS`/`WINDOW_SECONDS`, `JWT_ALGORITHM`,
`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS`, `SMTP_USE_TLS` — ces valeurs
fonctionnent en l'état pour un premier pilote ; à ajuster seulement si un besoin concret
apparaît.

## Variables strictement pour le développement local

`STORAGE_PROVIDER=local`/`STORAGE_LOCAL_PATH`, `EMAIL_PROVIDER=local`/`EMAIL_LOCAL_PATH` — ces
valeurs restent correctes pour le développement et les tests automatisés (voir
`apps/api/tests/conftest.py`, `apps/api/tests/test_email.py`) ; ne pas les changer localement,
seulement dans la configuration du déploiement pilote lui-même.

## Rate limiting (Phase 20 — durcissement pré-pilote)

Complète le rate limiting login/forgot-password (Phases 7.2/10.1) sur trois endpoints qui n'en
avaient aucun. Toutes les valeurs sont des `Settings` (`apps/api/app/core/config.py`), ajustables
sans changement de code, fail-open si Redis est injoignable (même principe que login/forgot-
password — Redis reste une dépendance non critique de l'authentification elle-même) :

| Endpoint | Clé Redis | Fenêtre par défaut | Réponse au dépassement |
|---|---|---|---|
| `POST /auth/register` | IP (`register_attempts:{ip}`) | 20 tentatives / 3600s | `429` + `Retry-After` |
| `POST /auth/refresh` | `user_id` résolu après validation du jeton (`refresh_attempts:{user_id}`) | 30 tentatives / 300s | `429` + `Retry-After` |
| `GET /report-cards/verify/{code}` | IP (`report_card_verify_attempts:{ip}`) | 30 tentatives / 60s | `429` + `Retry-After` |

Justification des clés (détail dans `apps/api/app/core/rate_limit.py`) : `register` par IP —
contrairement au login, créer une organisation n'est jamais un trafic légitime récurrent partagé
par une école entière. `refresh` par `user_id`, pas par le jeton lui-même — le jeton tourne à
chaque appel (rotation déjà en place depuis la Phase 1), une clé basée sur le jeton ne verrait
jamais plus d'une requête par fenêtre. `verify` par IP — endpoint public, seule clé disponible ;
le code a 384 bits d'entropie (`secrets.token_urlsafe(48)`), le brute-force reste infaisable
indépendamment de cette limite, dont le seul rôle réel est de décourager un scraping automatisé.

Seuils de pilote raisonnables, pas des valeurs de sécurité absolues — à revoir avec des données
d'usage réelles une fois un vrai pilote lancé, pas avant. **Ajusté une fois pendant cette même
phase sur preuve réelle** : le seuil `register` initial (5/heure) a été testé contre la suite
Playwright réelle de ce dépôt (`apps/web/e2e/`) exécutée pour de vrai contre la stack Docker
vivante — toutes les requêtes d'un navigateur Playwright résolvent à la même IP de boucle locale
(`127.0.0.1`, constaté réellement), et cette seule suite déclenche plus de 5 inscriptions dans la
même exécution (admin-onboarding + setup-wizard). Relevé à 20/heure en conséquence — un exemple
concret de "ne pas inventer un seuil arbitraire", ici corrigé par une preuve réelle plutôt que
laissé tel quel.

## HTTPS / Transport Security (Phase 20)

**État réel : HTTP uniquement, HTTPS non testé, aucun environnement de déploiement réel
disponible pour le faire.** Ce document ne déclare PAS "HTTPS production GO" — ce serait une
affirmation non vérifiable sans domaine/certificat/hébergeur réels (voir règle du projet : ne
jamais fabriquer un faux environnement de production pour "prouver" une configuration).

Ce qui est **déjà prêt** côté application (vérifié par lecture du code, pas supposé) :
- Aucun cookie n'est utilisé nulle part (web : `localStorage`, voir `apps/web/lib/auth/session.ts` ;
  mobile : `expo-secure-store`) — donc aucun attribut `Secure`/`SameSite` à ajouter : ils ne
  s'appliquent qu'aux cookies, qui n'existent pas dans ce projet.
- Toutes les URLs consommées par le web (`NEXT_PUBLIC_API_URL`) et le mobile
  (`EXPO_PUBLIC_API_URL`) sont déjà des variables d'environnement, jamais codées en dur —
  passer de `http://` à `https://` est un changement de configuration, pas de code.
- `CORS_ALLOWED_ORIGINS` est déjà une liste explicite (jamais `*` en dur dans le code) —
  `allow_credentials=True` combiné à des origines explicites reste valide même après HTTPS ;
  seule la VALEUR de la variable doit changer pour un domaine réel en `https://`.

Ce qui **reste un prérequis de déploiement, non vérifié dans cet environnement** :
- Un reverse proxy terminant réellement le TLS (nginx/Caddy/Traefik — `infrastructure/nginx/`
  ne contient toujours qu'un placeholder Phase 0, volontairement non remplacé par une fausse
  configuration ici).
- Un nom de domaine et un certificat réels (Let's Encrypt ou équivalent) — aucun des deux
  n'existe pour ce projet à ce jour.
- La redirection HTTP→HTTPS et l'en-tête `Strict-Transport-Security` (HSTS) — à poser sur ce
  reverse proxy le jour où il existe réellement, jamais dans l'application elle-même (c'est le
  proxy, pas l'API, qui sait si la connexion entrante est réellement chiffrée). Configuration
  nginx recommandée pour ce jour-là (documentée ici, non déployée) :
  ```
  add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
  return 301 https://$host$request_uri;  # sur le vhost HTTP
  ```
- Une `Content-Security-Policy` pour `apps/web` (Next.js) — délibérément non ajoutée cette phase :
  une CSP mal calibrée peut casser silencieusement l'hydratation Next.js, et aucun environnement
  de build/hébergement réel n'est disponible ici pour la valider avant de l'imposer.

**Conclusion honnête** : la préparation technique (pas de cookies à sécuriser, URLs déjà
paramétrables, CORS déjà explicite) est validée. Le HTTPS de production lui-même reste **NON
VÉRIFIÉ** et ne doit jamais être présenté autrement tant qu'un domaine/certificat/reverse proxy
réels n'existent pas.

## Security headers (Phase 20)

Ajoutés à toute réponse de l'API (`apps/api/app/main.py::security_headers_middleware`), sans
risque de régression (aucun ne change un comportement fonctionnel), testés réellement
(`apps/api/tests/test_security_hardening.py`) :

| En-tête | Valeur | Pourquoi |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | Empêche un navigateur de deviner un type MIME différent de celui déclaré |
| `X-Frame-Options` | `DENY` | Protège `/docs`/`/redoc` (Swagger/ReDoc) contre le clickjacking |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Évite de fuiter l'URL complète (avec éventuels paramètres) vers un domaine tiers |
| `Permissions-Policy` | `geolocation=(), camera=(), microphone=()` | Aucune de ces API n'est utilisée — désactivation explicite par hygiène |

`Strict-Transport-Security` et `Content-Security-Policy` : voir section HTTPS ci-dessus pour la
justification de leur absence délibérée à ce stade.

## CORS (audit Phase 20)

Configuration actuelle (`apps/api/app/main.py`) : `allow_origins` = liste explicite depuis
`CORS_ALLOWED_ORIGINS` (jamais `*` en dur), `allow_credentials=True`, `allow_methods=["*"]`,
`allow_headers=["*"]`. Audité, jugé sain : `allow_credentials=True` combiné à une origine `*`
littérale serait dangereux (et rejeté par les navigateurs de toute façon) — mais la liste
d'origines n'est jamais `*` dans le code, seulement configurable via `.env`. **Point d'attention
documenté, non corrigé par du code** : ne jamais définir `CORS_ALLOWED_ORIGINS=*` en pilote/
production — ce n'est pas empêché techniquement (c'est une variable d'environnement), seulement
déconseillé ici par écrit, puisqu'aucune donnée sensible (cookie) n'y transite de toute façon
(`allow_credentials=True` n'a d'effet réel que pour des cookies, qui n'existent pas dans ce
projet — voir section HTTPS) : le risque réel de mal configurer cette variable reste donc plus
faible qu'il ne le serait avec des cookies de session.

## Health / Readiness / Observabilité (Phase 16)

- `GET /api/v1/health` — liveness, aucune dépendance vérifiée, utilisé par le `HEALTHCHECK`
  Docker du service `api` (`docker-compose.yml`).
- `GET /api/v1/ready` — readiness réelle : vérifie PostgreSQL (`SELECT 1`), Redis (`PING`), et le
  stockage fichiers (écriture réelle via `StorageProvider`). `200` si tout est `"ok"`, `503`
  sinon, avec le détail par dépendance (`{"database": "ok"|"error", ...}`) — jamais de chaîne de
  connexion ni de message d'exception dans la réponse.
- Logs : `LOG_LEVEL` (déjà présent depuis la Phase 0) est désormais réellement appliqué
  (`app/core/logging_config.py`) — une ligne de démarrage, et une ligne d'erreur (sans secret)
  pour chaque échec de vérification `/ready` ou exception HTTP non gérée.
- Testé réellement en Phase 16 (arrêt/redémarrage contrôlé de `db`/`redis`, voir
  [Phase 16](../phases/PHASE_16_IMPLEMENTATION.md)) — pas seulement écrit.

## Checklist de configuration production

Cocher uniquement ce qui est **réellement vérifié dans le déploiement visé** — ne jamais cocher
une case sur la base d'une intention ou d'une documentation seule.

- [ ] `ENVIRONMENT=production` (voir tableau ci-dessus — sinon `dev_token`/`dev_reset_token` fuient)
- [ ] `JWT_SECRET_KEY` remplacé par un secret généré, pas le placeholder du dépôt
- [ ] PostgreSQL production configuré (`DATABASE_URL`/`APP_DATABASE_URL`, mots de passe non par défaut)
- [ ] Redis production configuré (`REDIS_URL`)
- [ ] SMTP production configuré (`SMTP_HOST`/`PORT`/`USERNAME`/`PASSWORD`/`FROM_ADDRESS`)
- [ ] `EMAIL_PROVIDER=smtp` (jamais `local` en production — voir section dédiée ci-dessus)
- [ ] Stockage configuré (`STORAGE_LOCAL_PATH` monté sur un volume/disque persistant — voir
      section "Stockage fichiers" ci-dessus)
- [ ] Backups activés (tâche planifiée exécutant `scripts/backup-all.sh` — voir Phase 15)
- [ ] Backup PostgreSQL testé (restauration réelle vers une base de test, pas seulement produit)
- [ ] Backup storage testé (restauration réelle vers un répertoire de test)
- [ ] **Destination externe des backups configurée (sur l'hôte de PRODUCTION réel)** — **NON
      COCHÉ**, volontairement : aucun hôte de production n'est encore choisi. Le **mécanisme**
      (copie automatique + revérification SHA-256 après copie + restauration réelle depuis la
      copie externe) a été prouvé de bout en bout en Phase 17, mais **sur la machine de
      développement**, vers un disque physique distinct (`D:\EduSphere-Backups`) appartenant à
      une autre personne (usage exceptionnel, accordé explicitement, non reproductible tel quel
      en production) — voir `docs/database/STORAGE_BACKUP_RESTORE.md`, section "Stockage
      indépendant — RÉSOLU sur cet hôte". Ne cocher cette case qu'après avoir répété la même
      copie + vérification vers un véritable support de production (disque externe dédié, NAS,
      stockage cloud retenu).
- [ ] `/health` vérifié (réponse 200 réelle observée)
- [ ] `/ready` vérifié (réponse 200 avec tout "ok" réellement observée, ET réponse 503 observée
      lors d'un test de panne contrôlée d'au moins une dépendance)
- [ ] Docker healthchecks vérifiés (`docker compose ps` affichant `(healthy)` pour `api`/`db`/`redis`)
- [ ] Logs vérifiés (ligne de démarrage visible, aucun secret dans `docker compose logs`)
- [ ] Aucun secret dans Git — non applicable tant qu'aucun dépôt Git n'existe (voir Git/CI
      ci-dessous) ; à revérifier explicitement au moment de l'initialisation du dépôt
- [ ] HTTPS / reverse proxy prévu — **non traité par ce projet à ce stade** (aucune configuration
      nginx/Caddy/Traefik n'existe, `infrastructure/nginx/` ne contient qu'un placeholder Phase 0).
      Voir section "HTTPS / Transport Security (Phase 20)" ci-dessus pour ce qui est déjà prêt
      côté application vs ce qui reste un prérequis de déploiement.
- [ ] Domaine configuré — dépend de l'hébergeur retenu, non figé
- [x] Rate limiting register/refresh/verify-by-code — **PASS**, réellement testé (Phase 20, voir
      section dédiée ci-dessus et `PHASE_20_IMPLEMENTATION.md`)
- [x] Security headers de base (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
      `Permissions-Policy`) — **PASS**, réellement testés (Phase 20)
- [ ] HSTS / Content-Security-Policy — **NON APPLICABLE tant que HTTPS réel n'existe pas** (voir
      section HTTPS ci-dessus)
- [x] RLS sur `organizations` — **PASS**, gap fermé et testé réellement (Phase 20, migration 0010)
- [x] Traçabilité des ajustements manuels de frais (`StudentFee.updated_by` + note obligatoire) —
      **PASS**, testé réellement (Phase 20)
- [ ] Procédure de restauration disponible (voir `docs/database/BACKUP_RESTORE.md`,
      `STORAGE_BACKUP_RESTORE.md`, et [`docs/deployment/DISASTER_RECOVERY.md`](DISASTER_RECOVERY.md)
      pour l'ordre exact des opérations par scénario de perte)

## Ce que ce document NE couvre PAS (hors périmètre)

- Git / CI (dette documentée, `docs/phases/PHASE_14_DISCOVERY.md` §4, toujours non initialisée
  en Phase 16) — aucune variable de secrets CI n'est configurée ici.
- Observabilité au-delà des logs minimaux ci-dessus (pas d'ELK/Grafana/Prometheus/OpenTelemetry —
  aucun composant de ce type n'existait dans le dépôt, donc aucun n'a été configuré, conformément
  à la consigne de la Phase 16 de ne pas en introduire un sans qu'il préexiste).
- HTTPS/reverse proxy — voir case décochée ci-dessus.
- Choix d'un hébergeur cloud pour le stockage, la base de données, ou la destination externe des
  backups — aucun n'est figé, cohérent avec la règle établie depuis la Phase 0.
