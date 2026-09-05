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
      nginx/Caddy/Traefik n'existe, `infrastructure/nginx/` ne contient qu'un placeholder Phase 0)
- [ ] Domaine configuré — dépend de l'hébergeur retenu, non figé
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
