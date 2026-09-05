#!/usr/bin/env bash
# Sauvegarde combinée PostgreSQL + stockage fichiers (Phase 15 — Automated Backup & Recovery
# Hardening).
#
# Exécute scripts/db-backup.sh puis scripts/storage-backup.sh l'un juste après l'autre — pas
# atomique (les deux systèmes de stockage sont indépendants, voir "Backup cohérent" dans
# docs/database/STORAGE_BACKUP_RESTORE.md), mais la fenêtre entre les deux reste de l'ordre de
# la seconde, largement suffisante pour un pilote à faible fréquence d'écriture. Un échec de
# L'UN OU L'AUTRE fait échouer ce script dans son ensemble (jamais masqué) — voir §20 de la
# consigne Phase 15 : un script qui retourne toujours 0 malgré un échec n'est pas acceptable.
#
# Applique ensuite une politique de rétention simple : conserve les RETENTION_DAYS derniers
# jours de backups (7 par défaut — cadence quotidienne recommandée pour un pilote, voir
# docs/database/BACKUP_RESTORE.md "Fréquence recommandée"), supprime le reste. Rotation par date
# de fichier, pas de politique complexe (cohérent avec la retenue déjà appliquée en Phase 7.3).
#
# Usage : scripts/backup-all.sh [service-compose]   (défaut: db)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE="${1:-db}"
BACKUP_DIR="${BACKUP_DIR:-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
# Phase 17 — répertoire sur un support physiquement distinct du disque hébergeant Docker/
# PostgreSQL (point de montage réseau, disque externe, etc. selon l'hôte réel). Vide par défaut :
# aucun hébergeur n'est figé pour un vrai déploiement Linux (cohérent avec la règle Phase 0) — à
# définir explicitement via cette variable avant utilisation. Voir scripts/windows/backup-all.ps1
# pour l'équivalent réellement testé sur l'hôte de développement de ce projet (D:\, un second
# disque physique confirmé distinct de celui hébergeant Docker).
EXTERNAL_BACKUP_DIR="${EXTERNAL_BACKUP_DIR:-}"

echo "=== Backup PostgreSQL ==="
if ! "$SCRIPT_DIR/db-backup.sh" "$SERVICE"; then
  echo "ERREUR: backup PostgreSQL échoué — backup-all.sh interrompu (pas de backup storage sans DB)." >&2
  exit 1
fi

echo "=== Backup stockage fichiers ==="
if ! "$SCRIPT_DIR/storage-backup.sh"; then
  echo "ERREUR: backup stockage fichiers échoué — le backup PostgreSQL ci-dessus reste valide," \
       "mais la paire DB+storage de cette exécution est incomplète." >&2
  exit 1
fi

echo "=== Rétention (${RETENTION_DAYS} jours) ==="
DELETED_COUNT=0
while IFS= read -r -d '' old_file; do
  rm -f "$old_file"
  DELETED_COUNT=$((DELETED_COUNT + 1))
  echo "Supprimé (rétention dépassée): $old_file"
done < <(find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'edusphere_*.dump' -o -name 'storage_*.tar.gz' -o -name '*.sha256' \) -mtime "+${RETENTION_DAYS}" -print0)
echo "Rétention appliquée : $DELETED_COUNT fichier(s) obsolète(s) supprimé(s), les backups des ${RETENTION_DAYS} derniers jours conservés."

if [ -n "$EXTERNAL_BACKUP_DIR" ]; then
  echo "=== Copie externe vers ${EXTERNAL_BACKUP_DIR} ==="
  if [ ! -d "$EXTERNAL_BACKUP_DIR" ] && ! mkdir -p "$EXTERNAL_BACKUP_DIR" 2>/dev/null; then
    echo "ERREUR: destination externe inaccessible (${EXTERNAL_BACKUP_DIR}) — le backup LOCAL ci-dessus reste valide, mais aucune copie hors machine n'a été produite pour cette exécution." >&2
    exit 1
  fi
  # db-backup.sh/storage-backup.sh ne remontent pas leur horodatage à cet appelant — on copie
  # donc le dump et l'archive les plus récemment produits (ceux de CETTE exécution, qui vient de
  # se terminer avec succès juste au-dessus) plutôt que de reconstruire un nom de fichier.
  latest_dump="$(ls -t "${BACKUP_DIR}"/edusphere_*.dump 2>/dev/null | head -n 1)"
  latest_storage="$(ls -t "${BACKUP_DIR}"/storage_*.tar.gz 2>/dev/null | head -n 1)"
  for f in "$latest_dump" "$latest_storage"; do
    [ -n "$f" ] && [ -e "$f" ] || continue
    cp "$f" "$f.sha256" "$EXTERNAL_BACKUP_DIR/"
    # Revalidation réelle après copie, pas seulement une copie du fichier .sha256 déjà produit —
    # même principe que scripts/windows/backup-all.ps1.
    dest_file="${EXTERNAL_BACKUP_DIR}/$(basename "$f")"
    if command -v sha256sum > /dev/null 2>&1; then
      source_hash="$(sha256sum "$f" | cut -d' ' -f1)"
      dest_hash="$(sha256sum "$dest_file" | cut -d' ' -f1)"
      if [ "$source_hash" != "$dest_hash" ]; then
        echo "ERREUR: intégrité KO après copie externe : $dest_file" >&2
        exit 1
      fi
      echo "Copie vérifiée (SHA-256 identique) : $dest_file"
    fi
  done
fi

echo "=== Backup combiné terminé avec succès ==="
