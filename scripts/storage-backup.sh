#!/usr/bin/env bash
# Sauvegarde du stockage fichiers applicatif (Phase 15 — Automated Backup & Recovery Hardening).
#
# Produit une archive tar.gz de apps/api/storage/ (bind mount hôte du StorageProvider, voir
# Phase 14 et docker-compose.yml) dans backups/ — le même répertoire hôte que les dumps
# PostgreSQL (scripts/db-backup.sh), pour rester synchronisé dans le temps avec eux (voir
# docs/database/STORAGE_BACKUP_RESTORE.md, "Ordre de restauration").
#
# Contrairement au dump PostgreSQL, aucun `docker cp` n'est nécessaire ici : depuis la Phase 14,
# apps/api/storage/ EST déjà un répertoire hôte (bind mount), lisible directement par ce script
# sans passer par le conteneur.
#
# Usage : scripts/storage-backup.sh
set -euo pipefail

STORAGE_DIR="apps/api/storage"
BACKUP_DIR="${BACKUP_DIR:-backups}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="${BACKUP_DIR}/storage_${TIMESTAMP}.tar.gz"

if [ ! -d "$STORAGE_DIR" ]; then
  echo "ERREUR: $STORAGE_DIR introuvable — le bind mount Phase 14 est-il en place ?" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

SOURCE_FILE_COUNT="$(find "$STORAGE_DIR" -type f | wc -l | tr -d ' ')"

if ! tar -czf "$OUT_FILE" -C "$(dirname "$STORAGE_DIR")" "$(basename "$STORAGE_DIR")"; then
  echo "ERREUR: tar a échoué — aucune archive valide produite." >&2
  rm -f "$OUT_FILE"
  exit 1
fi

if [ ! -s "$OUT_FILE" ]; then
  echo "ERREUR: archive vide." >&2
  rm -f "$OUT_FILE"
  exit 1
fi

# Intégrité : l'archive doit être listable (pas seulement non vide) et contenir le même nombre
# de fichiers que la source au moment de la sauvegarde.
ARCHIVE_FILE_COUNT="$(tar -tzf "$OUT_FILE" 2>/dev/null | grep -v '/$' | wc -l | tr -d ' ')"
if [ "$ARCHIVE_FILE_COUNT" -ne "$SOURCE_FILE_COUNT" ]; then
  echo "ERREUR: intégrité KO — $SOURCE_FILE_COUNT fichiers source vs $ARCHIVE_FILE_COUNT dans l'archive." >&2
  rm -f "$OUT_FILE"
  exit 1
fi

# Empreinte SHA-256 à côté de l'archive — permet de détecter une corruption ultérieure sans
# dépendre uniquement de la taille du fichier.
if command -v sha256sum > /dev/null 2>&1; then
  sha256sum "$OUT_FILE" > "${OUT_FILE}.sha256"
fi

SIZE="$(du -h "$OUT_FILE" | cut -f1)"
echo "Backup OK: $OUT_FILE ($SIZE) — $ARCHIVE_FILE_COUNT fichiers, intégrité vérifiée (comptage + listing tar)."
