# Disaster Recovery

Phase 17 (Pilot Infrastructure & External Services Readiness). Procédure de reprise après
sinistre pour EduSphere, couvrant chaque niveau de perte — du conteneur isolé à la machine
entière — et l'ordre exact des opérations pour reconstituer un état fonctionnel.

**Principe directeur, affirmé explicitement (règle de vérité)** : ce document distingue
`PROUVÉ RÉELLEMENT` (testé en conditions réelles, avec preuve dans
[`docs/phases/PHASE_17_IMPLEMENTATION.md`](../phases/PHASE_17_IMPLEMENTATION.md)) de
`CONFIGURÉ MAIS NON TESTÉ` de `DOCUMENTÉ MAIS NON DISPONIBLE`. Ne jamais confondre ces niveaux.

## Scénario 1 — Conteneur API perdu

**Statut : PROUVÉ RÉELLEMENT** (Phase 14/16).

- Cause typique : crash, recréation volontaire (`docker compose up --build`), remplacement
  d'image.
- Données perdues : **aucune** — le stockage fichiers est un bind mount hôte (Phase 14,
  `apps/api/storage/`), pas la couche writable du conteneur.
- Procédure : `docker compose up -d api` (ou `restart: unless-stopped` automatique en cas de
  crash). Vérifier `docker compose ps` (`(healthy)`) et `GET /api/v1/health`.
- Temps observé : quelques secondes à ~1 minute (reconstruction + démarrage).

## Scénario 2 — PostgreSQL perdu (conteneur/volume `db`)

**Statut : PROUVÉ RÉELLEMENT, y compris depuis la copie externe** (Phase 15 et 17).

Procédure, dans l'ordre exact :

1. Identifier le dernier backup valide : local (`backups/edusphere_<horodatage>.dump`) ou externe
   (`D:\EduSphere-Backups\edusphere_<horodatage>.dump`, Phase 17 — préférer l'externe si la
   machine/le disque principal est en cause).
2. Recréer le conteneur `db` si nécessaire (`docker compose up -d db`) — l'image
   `postgres:16-alpine` avec `POSTGRES_USER=edusphere`/`POSTGRES_PASSWORD`/`POSTGRES_DB=edusphere`
   (déjà dans `docker-compose.yml`) recrée automatiquement le rôle `edusphere` (bootstrap de
   l'image officielle).
3. **Recréer le rôle applicatif `edusphere_app`** — étape découverte comme nécessaire en Phase 17
   (`pg_dump` ne capture pas les rôles, objets au niveau du cluster, pas de la base) : soit en
   rejouant `alembic upgrade head` sur une base vide (recrée tout le schéma ET les rôles/policies
   RLS), soit, si on restaure directement un dump vers une base neuve, en exécutant d'abord :
   ```sql
   DO $$
   BEGIN
       IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'edusphere_app') THEN
           CREATE ROLE edusphere_app LOGIN;
       END IF;
   END
   $$;
   ALTER ROLE edusphere_app WITH LOGIN PASSWORD '<APP_DB_PASSWORD>'
       NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION;
   GRANT CONNECT ON DATABASE edusphere TO edusphere_app;
   GRANT USAGE ON SCHEMA public TO edusphere_app;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO edusphere_app;
   ```
   (extrait exact de `apps/api/alembic/versions/0002_auth_multitenancy.py`). Sans cette étape,
   `pg_restore` produit des erreurs de propriétaire/droits sur chaque table — **les données se
   restaurent correctement malgré ces erreurs** (vérifié réellement, voir Phase 17), mais l'accès
   applicatif (`APP_DATABASE_URL`, qui se connecte en `edusphere_app`) ne fonctionnerait pas tant
   que ce rôle n'existe pas, et les `GRANT`/`ALTER TABLE ... OWNER TO` échoueraient.
4. `pg_restore` du dump dans la base `edusphere`.
5. Vérification : comparer les comptages (`scripts/db-verify-counts.sql`) à une valeur de
   référence connue si disponible ; vérifier RLS (`SELECT relrowsecurity, relforcerowsecurity
   FROM pg_class WHERE relname = 'schools';` → doit renvoyer `t, t`).
6. Redémarrer/reconnecter l'API (`docker compose restart api`), vérifier `GET /api/v1/ready`
   (`checks.database == "ok"`).

**Preuve réelle (Phase 17)** : restauration depuis `D:\EduSphere-Backups\` (pas la copie locale)
vers une base de test dédiée, comptages identiques à la source sur 7 tables.

## Scénario 3 — Stockage fichiers perdu (`apps/api/storage/`)

**Statut : PROUVÉ RÉELLEMENT, y compris depuis la copie externe** (Phase 15 et 17).

1. Identifier la dernière archive valide : locale (`backups/storage_<horodatage>.tar.gz`) ou
   externe (`D:\EduSphere-Backups\storage_<horodatage>.tar.gz`).
2. Recréer le répertoire si nécessaire : `mkdir -p apps/api/storage`.
3. Extraire l'archive **directement** dans `apps/api/storage/` (contrairement aux tests de
   restauration, qui extraient toujours vers un répertoire temporaire par précaution) :
   `tar -xzf <archive> -C apps/api`.
4. Vérifier le nombre de fichiers (`find apps/api/storage -type f | wc -l`) contre le compte
   annoncé par le script de backup au moment de sa production.
5. Redémarrer l'API si elle était en cours d'exécution pendant la restauration (le bind mount
   étant déjà monté, un simple accès suffit généralement, mais un redémarrage garantit un état
   propre) : `docker compose restart api`.

**Preuve réelle (Phase 17)** : extraction depuis `D:\EduSphere-Backups\storage_....tar.gz` (pas
la copie locale) vers un répertoire temporaire, 85 fichiers extraits, correspondant exactement au
nombre annoncé à la production du backup.

**Rappel important** (voir `STORAGE_BACKUP_RESTORE.md`, "Ordre de restauration") : restaurer
PostgreSQL et le stockage à partir d'horodatages différents peut désynchroniser les références de
fichiers en base — toujours restaurer une paire produite ensemble.

## Scénario 4 — Machine principale perdue

**Statut : PROUVÉ RÉELLEMENT pour PostgreSQL + stockage, dans un environnement temporaire
indépendant — PAS prouvé pour la bascule complète de l'application elle-même** (voir limite
ci-dessous).

Simulation réellement exécutée en Phase 17, sans jamais toucher à l'environnement courant :

1. Conteneur PostgreSQL **entièrement indépendant** démarré (`docker run`, pas
   `docker compose` — aucun lien avec la pile existante), avec `POSTGRES_USER=edusphere` pour
   recréer le rôle bootstrap.
2. Rôle `edusphere_app` recréé manuellement (SQL exact ci-dessus, scénario 2 étape 3).
3. Dump **externe uniquement** (`D:\EduSphere-Backups\...`) restauré — succès, 0 erreur.
4. Comptages vérifiés identiques à la source sur 4 tables représentatives
   (`students=2588, organizations=3644, users=4207, report_cards=412`).
5. RLS vérifiée active et forcée sur les tables restaurées (`relrowsecurity=t,
   relforcerowsecurity=t`).
6. Archive de stockage externe extraite séparément (scénario 3) — 85 fichiers, succès.
7. Conteneur PostgreSQL temporaire supprimé (`docker rm -f`) — aucune trace laissée.
8. `GET /api/v1/health` et `GET /api/v1/ready` de la **pile réelle, jamais interrompue**,
   revérifiés `200` tout au long de cette simulation — preuve que rien n'a été perturbé.

**Ce qui N'A PAS été démontré, affirmé explicitement** : faire pointer une instance réelle de
l'API EduSphere (nouveau conteneur `api`, nouvelle pile `docker-compose`) vers ces ressources
reconstituées, pour observer `/health`/`/ready` **de cette nouvelle pile** passer au vert. Cela
nécessiterait de dupliquer l'ensemble de la pile applicative (une nouvelle architecture parallèle,
explicitement hors périmètre de cette phase) plutôt que de risquer une interruption de
l'environnement de développement partagé par les phases précédentes. Ce qui est prouvé : **les
données (base + fichiers) sont intégralement reconstituables à partir des seules copies
externes**, dans un environnement totalement indépendant de la machine/pile d'origine — c'est le
cœur de la question posée par cette phase. Le déploiement d'une nouvelle instance applicative sur
une nouvelle machine reste une procédure standard (voir
`docs/deployment/PRODUCTION_CONFIGURATION.md`), non ré-exécutée ici pour ne rien casser.

## Scénario 5 — Redis perdu

**Statut : PROUVÉ RÉELLEMENT** (Phase 16).

Fail-open déjà en place (`app/core/rate_limit.py`) : une perte de Redis dégrade uniquement le
rate limiting login/mot de passe oublié, sans affecter le reste de l'application. Aucune
procédure de restauration nécessaire — `docker compose start redis` suffit, aucune donnée
persistante critique dans `redisdata` (compteurs de rate limiting uniquement).

## Scénario 6 — EmailProvider indisponible

**Statut : CONFIGURÉ MAIS NON TESTÉ EN LIVRAISON EXTERNE RÉELLE.**

`send_email_best_effort` avale toute exception (Phase 9) — un incident SMTP n'affecte jamais une
transaction déjà commitée (compte créé, mot de passe réinitialisé, bulletin publié). Aucune
procédure de restauration système nécessaire. **Mais** : `EMAIL_PROVIDER=local` reste actif dans
cet environnement, et aucun compte SMTP réel n'y est disponible —
**REAL EXTERNAL SMTP DELIVERY NOT VERIFIED**. Voir
`docs/deployment/PRODUCTION_CONFIGURATION.md` pour la configuration nécessaire avant un pilote
réel.

## Vérifications finales (après toute restauration)

1. `docker compose ps` — tous les services `Up`, `(healthy)` pour `api`/`db`/`redis`.
2. `GET /api/v1/health` → `200 {"status":"ok"}`.
3. `GET /api/v1/ready` → `200 {"status":"ready","checks":{"database":"ok","redis":"ok","storage":"ok"}}`.
4. `alembic current` → `0008 (head)` (aucune dérive de schéma).
5. Comptages de tables clés comparés à une valeur de référence connue si disponible.
6. Un fichier de stockage connu (photo, PDF) téléchargeable via l'API sans erreur 404.
