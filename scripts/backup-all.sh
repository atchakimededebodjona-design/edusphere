#!/usr/bin/env bash
# Sauvegarde combinée PostgreSQL + stockage fichiers + envoi Backblaze B2 (Phase 15 — Automated
# Backup & Recovery Hardening ; durcissement Backblaze — voir docs/database/BACKUP_RESTORE.md).
#
# Exécute scripts/db-backup.sh puis scripts/storage-backup.sh l'un juste après l'autre — pas
# atomique (les deux systèmes de stockage sont indépendants, voir "Backup cohérent" dans
# docs/database/STORAGE_BACKUP_RESTORE.md), mais la fenêtre entre les deux reste de l'ordre de
# la seconde, largement suffisante pour un pilote à faible fréquence d'écriture. Un échec de
# L'UN OU L'AUTRE fait échouer ce script dans son ensemble (jamais masqué) — voir §20 de la
# consigne Phase 15 : un script qui retourne toujours 0 malgré un échec n'est pas acceptable.
#
# Applique ensuite une politique de rétention LOCALE simple : conserve les RETENTION_DAYS
# derniers jours de backups (7 par défaut — cadence quotidienne recommandée pour un pilote, voir
# docs/database/BACKUP_RESTORE.md "Fréquence recommandée"), supprime le reste. Rotation par date
# de fichier, pas de politique complexe (cohérent avec la retenue déjà appliquée en Phase 7.3).
#
# Envoie enfin le dump, l'archive storage et leurs empreintes SHA-256 vers Backblaze B2, via le
# remote rclone déjà configuré HORS de ce dépôt (credentials exclusivement dans rclone.conf,
# jamais ici). `rclone copy` n'accepte qu'UNE source et UNE destination à la fois (contrairement
# à `cp`) — chaque fichier est donc envoyé par un appel distinct. Après l'envoi, chaque fichier
# est revérifié directement sur Backblaze (présence + taille, et SHA-256 si le remote l'expose
# réellement) avant que ce script ne se termine avec succès. Un échec d'upload ou de
# vérification distante fait échouer ce script au même titre qu'un échec du backup local.
#
# La rétention LOCALE et la conservation DISTANTE sont indépendantes : ce script n'efface
# jamais rien sur Backblaze.
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
# Remote/chemin Backblaze B2 — la configuration (clés, endpoint) vit exclusivement dans
# rclone.conf sur l'hôte (hors de ce dépôt) ; ce script ne référence jamais un credential.
RCLONE_REMOTE="${RCLONE_REMOTE:-backblaze-edulinkage}"
RCLONE_BACKUP_PATH="${RCLONE_BACKUP_PATH:-edulinkage-backups}"

echo "=== Backup PostgreSQL ==="
if ! DUMP_FILE="$("$SCRIPT_DIR/db-backup.sh" "$SERVICE")"; then
  echo "ERREUR: backup PostgreSQL échoué — backup-all.sh interrompu (pas de backup storage sans DB)." >&2
  exit 1
fi
if [ -z "$DUMP_FILE" ] || [ ! -s "$DUMP_FILE" ]; then
  echo "ERREUR: db-backup.sh n'a pas produit de chemin de dump valide (\"$DUMP_FILE\")." >&2
  exit 1
fi
echo "Dump produit par cette exécution : $DUMP_FILE"

echo "=== Backup stockage fichiers ==="
if ! STORAGE_FILE="$("$SCRIPT_DIR/storage-backup.sh")"; then
  echo "ERREUR: backup stockage fichiers échoué — le backup PostgreSQL ci-dessus reste valide," \
       "mais la paire DB+storage de cette exécution est incomplète." >&2
  exit 1
fi
if [ -z "$STORAGE_FILE" ] || [ ! -s "$STORAGE_FILE" ]; then
  echo "ERREUR: storage-backup.sh n'a pas produit de chemin d'archive valide (\"$STORAGE_FILE\")." >&2
  exit 1
fi
echo "Archive storage produite par cette exécution : $STORAGE_FILE"

# Empreintes associées à CETTE exécution (déjà produites par les deux scripts ci-dessus quand
# sha256sum est disponible sur l'hôte).
DUMP_SHA256="${DUMP_FILE}.sha256"
STORAGE_SHA256="${STORAGE_FILE}.sha256"

echo "=== Vérification locale avant envoi distant ==="
for f in "$DUMP_FILE" "$STORAGE_FILE"; do
  if [ ! -s "$f" ]; then
    echo "ERREUR: fichier attendu manquant ou vide juste avant l'envoi Backblaze : $f" >&2
    exit 1
  fi
done
echo "Fichiers de cette exécution présents et non vides localement : $DUMP_FILE, $STORAGE_FILE"

echo "=== Rétention locale (${RETENTION_DAYS} jours) ==="
DELETED_COUNT=0
while IFS= read -r -d '' old_file; do
  rm -f "$old_file"
  DELETED_COUNT=$((DELETED_COUNT + 1))
  echo "Supprimé (rétention dépassée): $old_file"
done < <(find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'edusphere_*.dump' -o -name 'storage_*.tar.gz' -o -name '*.sha256' \) -mtime "+${RETENTION_DAYS}" -print0)
echo "Rétention locale appliquée : $DELETED_COUNT fichier(s) obsolète(s) supprimé(s), les backups des ${RETENTION_DAYS} derniers jours conservés. (La conservation distante sur Backblaze est indépendante — ce script n'y supprime jamais rien.)"

if [ -n "$EXTERNAL_BACKUP_DIR" ]; then
  echo "=== Copie externe vers ${EXTERNAL_BACKUP_DIR} ==="
  if [ ! -d "$EXTERNAL_BACKUP_DIR" ] && ! mkdir -p "$EXTERNAL_BACKUP_DIR" 2>/dev/null; then
    echo "ERREUR: destination externe inaccessible (${EXTERNAL_BACKUP_DIR}) — le backup LOCAL ci-dessus reste valide, mais aucune copie hors machine n'a été produite pour cette exécution." >&2
    exit 1
  fi
  for f in "$DUMP_FILE" "$STORAGE_FILE"; do
    cp "$f" "$EXTERNAL_BACKUP_DIR/"
    [ -e "${f}.sha256" ] && cp "${f}.sha256" "$EXTERNAL_BACKUP_DIR/"
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

echo "=== Envoi vers Backblaze B2 (${RCLONE_REMOTE}:${RCLONE_BACKUP_PATH}/) ==="
if ! command -v rclone > /dev/null 2>&1; then
  echo "ERREUR: rclone est introuvable dans le PATH — impossible d'envoyer vers Backblaze." >&2
  exit 1
fi

# Fichiers de CETTE exécution à envoyer : dump + archive storage, et leurs empreintes SHA-256
# quand elles existent (absentes seulement si sha256sum n'est pas disponible sur l'hôte).
UPLOAD_FILES=("$DUMP_FILE" "$STORAGE_FILE")
[ -e "$DUMP_SHA256" ] && UPLOAD_FILES+=("$DUMP_SHA256")
[ -e "$STORAGE_SHA256" ] && UPLOAD_FILES+=("$STORAGE_SHA256")

REMOTE_TARGET="${RCLONE_REMOTE}:${RCLONE_BACKUP_PATH}/"
for f in "${UPLOAD_FILES[@]}"; do
  echo "Envoi : $(basename "$f")"
  # Un seul fichier par appel : `rclone copy SOURCE DEST` n'accepte pas plusieurs sources
  # positionnelles (contrairement à `cp`) — c'était la cause de l'échec précédent
  # ("Command copy needs 2 arguments maximum: you provided 4 non flag arguments").
  if ! rclone copy "$f" "$REMOTE_TARGET" --retries 3 --low-level-retries 5 --stats=0; then
    echo "ERREUR: échec de l'envoi Backblaze pour $f — backup-all.sh interrompu." >&2
    exit 1
  fi
done
echo "Envoi Backblaze terminé pour ${#UPLOAD_FILES[@]} fichier(s)."

echo "=== Vérification distante sur Backblaze ==="

# Vérifie qu'un fichier local donné est réellement présent sur Backblaze avec la même taille,
# et compare aussi le SHA-256 quand le remote rclone l'expose réellement pour ce backend — sans
# jamais prétendre avoir recalculé un SHA-256 distant si ce n'est pas le cas.
verify_remote_file() {
  local local_file="$1"
  local remote_name
  remote_name="$(basename "$local_file")"

  local remote_size
  # `|| true` : sous `set -e`, une pipe qui échoue franchement (rclone injoignable, bucket
  # erroné...) ne doit jamais tuer le script silencieusement ici (son message d'erreur est
  # volontairement redirigé vers /dev/null) — elle doit tomber dans le contrôle explicite
  # ci-dessous, qui traite une absence de résultat comme un échec diagnostiqué.
  remote_size="$(rclone lsl "${RCLONE_REMOTE}:${RCLONE_BACKUP_PATH}" 2>/dev/null | awk -v name="$remote_name" '$4==name {print $1; exit}')" || true
  if [ -z "$remote_size" ]; then
    echo "ERREUR: fichier absent sur Backblaze après envoi (ou remote injoignable) : ${RCLONE_BACKUP_PATH}/${remote_name}" >&2
    return 1
  fi

  local local_size
  local_size="$(wc -c < "$local_file" | tr -d ' ')"
  if [ "$remote_size" != "$local_size" ]; then
    echo "ERREUR: taille distante (${remote_size}) différente de la taille locale (${local_size}) pour ${RCLONE_BACKUP_PATH}/${remote_name}" >&2
    return 1
  fi
  echo "Vérifié sur Backblaze (présence + taille = ${local_size} octets) : ${RCLONE_BACKUP_PATH}/${remote_name}"

  local remote_hash local_hash
  if remote_hash="$(rclone hashsum sha256 "${RCLONE_REMOTE}:${RCLONE_BACKUP_PATH}/${remote_name}" 2>/dev/null | awk '{print $1}')" && [ -n "$remote_hash" ]; then
    local_hash="$(sha256sum "$local_file" | cut -d' ' -f1)"
    if [ "$remote_hash" != "$local_hash" ]; then
      echo "ERREUR: SHA-256 distant (${remote_hash}) différent du SHA-256 local (${local_hash}) pour ${RCLONE_BACKUP_PATH}/${remote_name}" >&2
      return 1
    fi
    echo "SHA-256 distant vérifié identique au local : ${RCLONE_BACKUP_PATH}/${remote_name}"
  else
    echo "SHA-256 distant non disponible via ce remote rclone/Backblaze — vérification limitée à la présence + la taille pour ${RCLONE_BACKUP_PATH}/${remote_name}."
  fi
}

for f in "${UPLOAD_FILES[@]}"; do
  if ! verify_remote_file "$f"; then
    echo "ERREUR: la vérification distante Backblaze a échoué pour $f — backup-all.sh interrompu." >&2
    exit 1
  fi
done

echo "=== Backup combiné + envoi Backblaze terminés avec succès ==="
