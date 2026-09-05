#!/usr/bin/env bash
# Sauvegarde PostgreSQL (Phase 7.3 — backup & restore readiness).
#
# Produit un dump `pg_dump` au format custom (-Fc, compressé, restaurable sélectivement avec
# pg_restore) dans backups/ à la racine du repo — un emplacement HOTE, totalement indépendant
# du volume Docker `pgdata` (un volume Docker n'est pas une sauvegarde : il disparaît avec
# `docker volume rm`, `docker compose down -v`, ou une corruption du disque de l'hôte Docker).
#
# Le dump est d'abord écrit dans /tmp DANS le conteneur (stockage éphémère du conteneur, pas
# le volume pgdata), puis copié vers l'hôte avec `docker cp` (copie binaire fiable, contrairement
# à une redirection shell qui peut être altérée par l'encodage du terminal sur certains hôtes).
#
# Credentials : jamais en dur ici, jamais en argument de ligne de commande (visible dans `ps`
# ou l'historique shell). Le script exploite le fait que `docker compose exec` s'exécute DANS
# le conteneur `db`, où POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB sont déjà présents dans
# l'environnement (définis par docker-compose.yml / .env) — le script ne fait que les référencer.
#
# Usage : scripts/db-backup.sh [service-compose]   (défaut: db)
set -euo pipefail

SERVICE="${1:-db}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="${BACKUP_DIR}/edusphere_${TIMESTAMP}.dump"
CONTAINER_TMP="/tmp/edusphere_backup_${TIMESTAMP}.dump"

mkdir -p "$BACKUP_DIR"

cleanup() {
  docker compose exec -T "$SERVICE" rm -f "$CONTAINER_TMP" > /dev/null 2>&1 || true
}
trap cleanup EXIT

if ! docker compose exec -T "$SERVICE" sh -c \
  "PGPASSWORD=\"\$POSTGRES_PASSWORD\" pg_dump -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Fc -f '$CONTAINER_TMP'"
then
  echo "ERREUR: pg_dump a échoué — aucun backup valide produit." >&2
  exit 1
fi

CONTAINER_ID="$(docker compose ps -q "$SERVICE")"
if ! docker cp "${CONTAINER_ID}:${CONTAINER_TMP}" "$OUT_FILE"; then
  echo "ERREUR: échec de copie du dump vers l'hôte." >&2
  exit 1
fi

if [ ! -s "$OUT_FILE" ]; then
  echo "ERREUR: dump vide." >&2
  rm -f "$OUT_FILE"
  exit 1
fi

# Intégrité : le dump copié sur l'hôte doit être une archive pg_restore valide, pas juste un
# fichier non vide.
if ! docker compose exec -T "$SERVICE" pg_restore --list < "$OUT_FILE" > /dev/null 2>&1; then
  echo "ERREUR: le dump généré n'est pas une archive pg_restore valide (intégrité KO)." >&2
  exit 1
fi

SIZE="$(du -h "$OUT_FILE" | cut -f1)"
echo "Backup OK: $OUT_FILE ($SIZE) — intégrité vérifiée (pg_restore --list)."
