#!/usr/bin/env bash
# Test de restauration du stockage fichiers (Phase 15 — Automated Backup & Recovery Hardening).
#
# Extrait une archive produite par scripts/storage-backup.sh dans un répertoire TEMPORAIRE dédié
# — ne touche JAMAIS apps/api/storage/ (le répertoire réellement servi par l'application). Sert
# à démontrer réellement : backup -> extraction -> vérification, pas seulement à supposer que
# l'archive est utilisable (même principe que scripts/db-restore-test.sh pour PostgreSQL).
#
# Usage : scripts/storage-restore-test.sh <chemin-archive.tar.gz>
set -euo pipefail

ARCHIVE_FILE="${1:?Usage: scripts/storage-restore-test.sh <archive.tar.gz>}"
RESTORE_TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/edusphere_storage_restore_test.XXXXXX")"

if [ ! -s "$ARCHIVE_FILE" ]; then
  echo "ERREUR: archive introuvable ou vide: $ARCHIVE_FILE" >&2
  exit 1
fi

cleanup() {
  rm -rf "$RESTORE_TEST_DIR"
}
trap cleanup EXIT

if ! tar -xzf "$ARCHIVE_FILE" -C "$RESTORE_TEST_DIR"; then
  echo "RESTORE FAILED (extraction tar en échec)." >&2
  exit 1
fi

EXTRACTED_FILE_COUNT="$(find "$RESTORE_TEST_DIR" -type f | wc -l | tr -d ' ')"
if [ "$EXTRACTED_FILE_COUNT" -eq 0 ]; then
  echo "RESTORE FAILED (archive extraite mais vide)." >&2
  exit 1
fi

echo "RESTORE SUCCESS: $ARCHIVE_FILE extrait dans $RESTORE_TEST_DIR — $EXTRACTED_FILE_COUNT fichiers."
echo "Répertoire temporaire de test, supprimé automatiquement en fin de script — apps/api/storage/ n'a jamais été touché."
