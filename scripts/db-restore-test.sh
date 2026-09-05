#!/usr/bin/env bash
# Test de restauration PostgreSQL (Phase 7.3 — backup & restore readiness).
#
# Restaure un dump produit par scripts/db-backup.sh dans une base DEDIEE de test
# (edusphere_restore_test, sur la même instance Postgres) — ne touche JAMAIS la base source
# ($POSTGRES_DB). Sert à démontrer réellement : backup -> nouvelle base -> restore -> vérification,
# pas seulement à supposer que le dump est utilisable.
#
# Usage : scripts/db-restore-test.sh <chemin-du-dump> [service-compose]
set -euo pipefail

DUMP_FILE="${1:?Usage: scripts/db-restore-test.sh <dump-file> [service]}"
SERVICE="${2:-db}"
RESTORE_DB="edusphere_restore_test"
CONTAINER_DUMP_TMP="/tmp/$(basename "$DUMP_FILE")"
CONTAINER_SQL_TMP="/tmp/db-verify-counts.sql"

if [ ! -s "$DUMP_FILE" ]; then
  echo "ERREUR: dump introuvable ou vide: $DUMP_FILE" >&2
  exit 1
fi

CONTAINER_ID="$(docker compose ps -q "$SERVICE")"

cleanup() {
  docker compose exec -T "$SERVICE" rm -f "$CONTAINER_DUMP_TMP" "$CONTAINER_SQL_TMP" > /dev/null 2>&1 || true
}
trap cleanup EXIT

docker cp "$DUMP_FILE" "${CONTAINER_ID}:${CONTAINER_DUMP_TMP}"
docker cp "$(dirname "$0")/db-verify-counts.sql" "${CONTAINER_ID}:${CONTAINER_SQL_TMP}"

# Base de restauration dédiée, recréée à chaque run pour un test reproductible. DROP/CREATE ne
# porte que sur edusphere_restore_test — jamais sur $POSTGRES_DB (la base source).
docker compose exec -T "$SERVICE" sh -c \
  "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U \"\$POSTGRES_USER\" -d postgres -v ON_ERROR_STOP=1 -c \"DROP DATABASE IF EXISTS ${RESTORE_DB};\""
docker compose exec -T "$SERVICE" sh -c \
  "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U \"\$POSTGRES_USER\" -d postgres -v ON_ERROR_STOP=1 -c \"CREATE DATABASE ${RESTORE_DB} OWNER \\\"\$POSTGRES_USER\\\";\""

if ! docker compose exec -T "$SERVICE" sh -c \
  "PGPASSWORD=\"\$POSTGRES_PASSWORD\" pg_restore -U \"\$POSTGRES_USER\" -d '$RESTORE_DB' '$CONTAINER_DUMP_TMP'"
then
  echo "RESTORE FAILED (pg_restore a signalé une erreur)." >&2
  exit 1
fi

echo "--- Comptages dans $RESTORE_DB (base restaurée) ---"
if ! docker compose exec -T "$SERVICE" sh -c \
  "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -U \"\$POSTGRES_USER\" -d '$RESTORE_DB' -f '$CONTAINER_SQL_TMP'"
then
  echo "RESTORE FAILED (vérification post-restauration impossible)." >&2
  exit 1
fi

echo "RESTORE SUCCESS: $RESTORE_DB peuplée à partir de $DUMP_FILE — voir comptages ci-dessus."
echo "Comparer ces comptages avec ceux de la base source (\$POSTGRES_DB) pour conclure."
