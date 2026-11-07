#!/usr/bin/env bash
# Initialisation du cluster PostgreSQL de TEST uniquement (service db-test, docker-compose.test.yml).
# Exécuté par l'entrypoint officiel postgres:16 lors de la PREMIÈRE initialisation du volume
# edusphere_test_db_data, en tant que POSTGRES_USER (edusphere_test_admin), via le socket local.
#
# Peut être EXÉCUTÉ ou SOURCÉ par docker-entrypoint.sh (selon le bit exécutable) : ce script ne
# modifie aucune option du shell, n'affiche rien et n'utilise jamais `set -x` — son environnement
# contient POSTGRES_PASSWORD et PGPASSWORD (docker-entrypoint.sh, file_env et _main).
#
# - \getenv : le mot de passe du rôle de nettoyage n'apparaît jamais dans les arguments de psql.
# - VERBOSITY terse : une erreur ne recopie jamais le texte de la requête dans les journaux.
# - log_min_error_statement = panic (session et rôle administrateur) : le serveur ne journalise
#   jamais une instruction en échec issue de ces sessions (0002 insère un mot de passe dans le
#   texte de son ALTER ROLE).
# - Base « edusphere » inerte (décision D1-B) : seule cible du GRANT CONNECT écrit en dur dans la
#   migration 0002 ; aucune connexion possible, aucune donnée, aucun marqueur.
: "${EDUSPHERE_TEST_CLEANER_PASSWORD:?EDUSPHERE_TEST_CLEANER_PASSWORD manquant}"
PGHOST= PGHOSTADDR= psql -v ON_ERROR_STOP=1 --no-password --no-psqlrc --quiet \
  --username "$POSTGRES_USER" --dbname postgres <<'SQL'
\set VERBOSITY terse
SET log_min_error_statement = 'panic';
\getenv cleaner_pw EDUSPHERE_TEST_CLEANER_PASSWORD
CREATE ROLE edusphere_test_cleaner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
  NOREPLICATION NOINHERIT PASSWORD :'cleaner_pw';
\unset cleaner_pw
ALTER ROLE edusphere_test_admin SET log_min_error_statement = 'panic';
ALTER DATABASE edusphere_test SET app.test_marker = 'edusphere-test-sentinel-v1';
CREATE DATABASE edusphere WITH ALLOW_CONNECTIONS false;
REVOKE ALL ON DATABASE edusphere FROM PUBLIC;
SQL
