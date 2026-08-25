#!/usr/bin/env bash
# Ouvre un shell psql sur la base du projet, via le conteneur Postgres déjà lancé par
# docker-compose (postgres:16-alpine embarque psql — rien à installer sur la machine hôte).
set -euo pipefail

: "${POSTGRES_USER:=edusphere}"
: "${POSTGRES_DB:=edusphere}"
CONTAINER="${1:-edusphere-db-1}"

exec docker exec -it "$CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
