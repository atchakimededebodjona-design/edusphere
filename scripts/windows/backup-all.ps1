<#
.SYNOPSIS
    Sauvegarde combinee PostgreSQL + stockage fichiers (Phase 15 - Automated Backup & Recovery
    Hardening) - equivalent PowerShell natif de scripts/backup-all.sh.

.DESCRIPTION
    Ce projet documente scripts/backup-all.sh (bash) comme procedure CANONIQUE, portable vers
    un vrai hote de deploiement Linux (voir docs/database/BACKUP_RESTORE.md). Sur CET hote de
    developpement Windows, bash (via le lanceur WSL disponible ici) n'a pas acces a Docker -
    contrainte deja documentee dans les phases precedentes de ce projet. Ce script reimplemente
    la meme logique en PowerShell natif (docker.exe est directement accessible depuis
    PowerShell), pour permettre une automatisation REELLEMENT fonctionnelle sur CET hote
    (Register-ScheduledTask), plutot que de pretendre qu'un script bash non executable ici
    tourne automatiquement.

    Etapes : pg_dump dans le conteneur db -> docker cp vers backups/ -> verification integrite
    (pg_restore --list) -> tar de apps/api/storage (deja un repertoire hote depuis la Phase 14,
    aucun docker cp necessaire) -> verification integrite (listing + comptage de fichiers) ->
    empreinte SHA-256 pour les deux archives -> retention (7 jours par defaut).

.PARAMETER RetentionDays
    Nombre de jours de backups a conserver (par defaut 7, cadence quotidienne pilote).

.PARAMETER ExternalDestination
    Repertoire sur un support physiquement distinct du disque principal (Phase 17 - copie hors
    machine). Par defaut D:\EduSphere-Backups (disque physique distinct confirme sur cet hote -
    voir docs/database/BACKUP_RESTORE.md). Si ce chemin n'est pas accessible au moment de
    l'execution, la copie externe echoue explicitement (jamais silencieuse) mais le backup LOCAL
    deja produit reste valide.

.EXAMPLE
    powershell -File scripts\windows\backup-all.ps1
#>
param(
    [int]$RetentionDays = 7,
    [string]$ExternalDestination = "D:\EduSphere-Backups"
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")

$Timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$BackupDir = "backups"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

function Fail($Message) {
    Write-Error $Message
    exit 1
}

# --- 1. Backup PostgreSQL --------------------------------------------------------------------
Write-Output "=== Backup PostgreSQL ==="
$DbOutFile = Join-Path $BackupDir "edusphere_$Timestamp.dump"
$ContainerTmp = "/tmp/edusphere_backup_$Timestamp.dump"

try {
    docker compose exec -T db sh -c "PGPASSWORD=`"`$POSTGRES_PASSWORD`" pg_dump -U `"`$POSTGRES_USER`" -d `"`$POSTGRES_DB`" -Fc -f '$ContainerTmp'"
    if ($LASTEXITCODE -ne 0) { Fail "pg_dump a echoue - aucun backup DB valide produit." }

    $ContainerId = (docker compose ps -q db).Trim()
    docker cp "${ContainerId}:${ContainerTmp}" $DbOutFile
    if ($LASTEXITCODE -ne 0) { Fail "Echec de copie du dump vers l'hote." }

    if (-not (Test-Path $DbOutFile) -or (Get-Item $DbOutFile).Length -eq 0) {
        Fail "Dump PostgreSQL vide ou absent."
    }

    # PowerShell 5.1 ne supporte pas l'operateur `<` (redirection d'entree standard) vers un
    # executable natif, contrairement a bash (utilise par scripts/db-backup.sh) ou cmd.exe -
    # on delegue donc cette seule ligne a cmd.exe, qui gere cette redirection de facon fiable
    # sans transformation de texte sur les octets binaires du dump.
    cmd /c "docker compose exec -T db pg_restore --list < `"$DbOutFile`"" | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "Le dump genere n'est pas une archive pg_restore valide (integrite KO)." }

    Get-FileHash $DbOutFile -Algorithm SHA256 | ForEach-Object { "$($_.Hash)  $(Split-Path $DbOutFile -Leaf)" } | Set-Content "$DbOutFile.sha256"

    $DbSize = "{0:N1} KB" -f ((Get-Item $DbOutFile).Length / 1KB)
    Write-Output "Backup DB OK: $DbOutFile ($DbSize) - integrite verifiee (pg_restore --list)."
}
finally {
    docker compose exec -T db rm -f $ContainerTmp 2>$null | Out-Null
}

# --- 2. Backup stockage fichiers -------------------------------------------------------------
Write-Output "=== Backup stockage fichiers ==="
$StorageDir = "apps\api\storage"
$StorageOutFile = Join-Path $BackupDir "storage_$Timestamp.tar.gz"

if (-not (Test-Path $StorageDir)) { Fail "$StorageDir introuvable - le bind mount Phase 14 est-il en place ?" }

$SourceFileCount = (Get-ChildItem $StorageDir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count

tar -czf $StorageOutFile -C "apps\api" "storage"
if ($LASTEXITCODE -ne 0) { Fail "tar a echoue - aucune archive de stockage valide produite." }

if (-not (Test-Path $StorageOutFile) -or (Get-Item $StorageOutFile).Length -eq 0) {
    Fail "Archive de stockage vide."
}

$ArchiveEntries = tar -tzf $StorageOutFile
$ArchiveFileCount = ($ArchiveEntries | Where-Object { $_ -notmatch '/$' } | Measure-Object).Count
if ($ArchiveFileCount -ne $SourceFileCount) {
    Remove-Item $StorageOutFile -Force
    Fail "Integrite KO - $SourceFileCount fichiers source vs $ArchiveFileCount dans l'archive."
}

Get-FileHash $StorageOutFile -Algorithm SHA256 | ForEach-Object { "$($_.Hash)  $(Split-Path $StorageOutFile -Leaf)" } | Set-Content "$StorageOutFile.sha256"

$StorageSize = "{0:N1} KB" -f ((Get-Item $StorageOutFile).Length / 1KB)
Write-Output "Backup storage OK: $StorageOutFile ($StorageSize) - $ArchiveFileCount fichiers, integrite verifiee."

# --- 3. Retention ------------------------------------------------------------------------------
Write-Output "=== Retention ($RetentionDays jours) ==="
$Cutoff = (Get-Date).AddDays(-$RetentionDays)
$OldFiles = Get-ChildItem $BackupDir -File | Where-Object {
    ($_.Name -like "edusphere_*.dump" -or $_.Name -like "storage_*.tar.gz" -or $_.Name -like "*.sha256") -and $_.LastWriteTime -lt $Cutoff
}
foreach ($f in $OldFiles) {
    Remove-Item $f.FullName -Force
    Write-Output "Supprime (retention depassee): $($f.FullName)"
}
Write-Output "Retention appliquee : $($OldFiles.Count) fichier(s) obsolete(s) supprime(s)."

# --- 4. Copie externe (Phase 17 - hors machine) ------------------------------------------------
Write-Output "=== Copie externe vers $ExternalDestination ==="
$externalDrive = Split-Path -Qualifier $ExternalDestination -ErrorAction SilentlyContinue
if (-not $externalDrive -or -not (Test-Path "$externalDrive\")) {
    Fail "Destination externe inaccessible ($ExternalDestination) - le backup LOCAL ci-dessus reste valide, mais aucune copie hors machine n'a ete produite pour cette execution."
}

New-Item -ItemType Directory -Force -Path $ExternalDestination | Out-Null

$filesToCopy = @($DbOutFile, "$DbOutFile.sha256", $StorageOutFile, "$StorageOutFile.sha256")
foreach ($f in $filesToCopy) {
    $destFile = Join-Path $ExternalDestination (Split-Path $f -Leaf)
    Copy-Item -Path $f -Destination $destFile -Force

    # Jamais se contenter de la copie elle-meme : recalcule le SHA-256 du fichier a destination
    # et le compare a l'empreinte produite a la source (pas juste re-copier le .sha256 sans le
    # revalider) - seule preuve reelle que la copie n'a pas ete corrompue en route.
    if ($f -notlike "*.sha256") {
        $sourceHash = (Get-FileHash $f -Algorithm SHA256).Hash
        $destHash = (Get-FileHash $destFile -Algorithm SHA256).Hash
        if ($sourceHash -ne $destHash) {
            Fail "Integrite KO apres copie externe : $destFile (SHA-256 source != destination)."
        }
        Write-Output "Copie verifiee (SHA-256 identique) : $destFile"
    }
}

Write-Output "=== Backup combine + copie externe termines avec succes ==="
exit 0
