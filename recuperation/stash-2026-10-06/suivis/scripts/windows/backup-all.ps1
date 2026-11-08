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
    empreinte SHA-256 pour les deux archives -> retention (7 jours par defaut) -> envoi Backblaze
    B2 avec retry controle (Phase 8.4 / 8.4.3) -> copie externe locale existante (Phase 17).

    Phase 8.4.3 (observabilite + resilience, suite a l'echec B2 du 2026-10-01 dont la cause
    n'avait pas pu etre determinee faute de journalisation persistante - voir Phase 8.4.2) :
    - log persistant par execution (backups/logs/backup_<timestamp>.log) ;
    - capture reelle du code de sortie / stdout / stderr de chaque appel rclone (plus de message
      generique) ;
    - retry controle (3 tentatives, 30s puis 60s d'attente) sur l'envoi B2 UNIQUEMENT (jamais
      pg_dump/storage/copie D:, qui reutilisent les memes fichiers locaux deja produits) ;
    - manifest enrichi (cloud.attempts/startedAt/completedAt/durationSeconds/error structure) ;
    - statut "external" (D:) desormais INDEPENDANT du statut "cloud" (B2) : un echec D: ne fait
      plus echouer le script (exit 1) tant que le backup local a reussi - voir .PARAMETER
      ExternalDestination et la section "overall" du manifest.

.PARAMETER RetentionDays
    Nombre de jours de backups a conserver (par defaut 7, cadence quotidienne pilote).

.PARAMETER LogRetentionDays
    Nombre de jours de logs persistants (backups/logs/) a conserver (par defaut 30, Phase 8.4.3).
    Les logs plus anciens sont supprimes ; jamais les logs recents, jamais de suppression de
    backups eux-memes par ce parametre.

.PARAMETER ExternalDestination
    Repertoire sur un support physiquement distinct du disque principal (Phase 17 - copie hors
    machine). Par defaut D:\EduLinkage-Backups. Audits Phases 8.0-8.3 : ce disque s'est revele
    instable dans son identite physique sur cet hote (memes lettres de lecteur reassignees a des
    partitions differentes) - la copie Backblaze B2 ci-dessous est donc la seule copie hors
    machine dont l'identite est verifiee independamment de la lettre de lecteur. Depuis la Phase
    8.4.3, un echec de cette copie externe est journalise (external.status = "failed") mais
    n'interrompt plus le script : seul un echec du backup LOCAL (PostgreSQL/storage) reste
    bloquant.

.PARAMETER RcloneRemote
    Nom du remote rclone configure pour Backblaze B2 (Phase 8.4). Par defaut
    "backblaze-edulinkage", correspondant a la section [backblaze-edulinkage] du fichier
    rclone.conf reference par -RcloneConfig.

.PARAMETER RcloneBucket
    Nom du bucket Backblaze B2 cible (Phase 8.4). Par defaut "edulinkage-backups".

.PARAMETER RcloneConfig
    Chemin du fichier de configuration rclone contenant les credentials B2 (Phase 8.4). Ce
    fichier vit EXCLUSIVEMENT hors du depot (jamais commite, jamais dans .env) ; ce script ne
    reference jamais un credential en dur et ne journalise jamais son contenu. Par defaut sous
    le profil de l'utilisateur courant (%USERPROFILE%\.config\rclone\rclone.conf).

.PARAMETER B2MaxRetries
    Nombre maximal de tentatives d'envoi B2 (Phase 8.4.3, par defaut 3). Attente 30s apres
    l'echec de la tentative 1, 60s apres l'echec de la tentative 2. Jamais de retry infini.

.EXAMPLE
    powershell -File scripts\windows\backup-all.ps1
#>
param(
    [int]$RetentionDays = 7,
    [int]$LogRetentionDays = 30,
    [string]$ExternalDestination = "D:\EduLinkage-Backups",
    [string]$RcloneRemote = "backblaze-edulinkage",
    [string]$RcloneBucket = "edulinkage-backups",
    [string]$RcloneConfig = (Join-Path $env:USERPROFILE ".config\rclone\rclone.conf"),
    [int]$B2MaxRetries = 3
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")

$Timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$BackupDir = "backups"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

# --- Logging persistant (Phase 8.4.3) -----------------------------------------------------------
# Un fichier par execution, cree des le debut, jamais envoye vers B2 pendant cette phase (demande
# explicite) - sert uniquement de preuve locale pour diagnostiquer un futur echec sans dependre
# des journaux Windows (dont la retention s'est revelee hors de notre controle, Phase 8.4.2).
$LogDir = Join-Path $BackupDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "backup_$Timestamp.log"
New-Item -ItemType File -Force -Path $LogFile | Out-Null

function Write-Log {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("INFO", "WARN", "ERROR")][string]$Level,
        [Parameter(Mandatory = $true)][string]$Message
    )
    $line = "[$((Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))] [$Level] $Message"
    # Add-Content peut echouer transitoirement (verrou de fichier par un antivirus, une
    # synchronisation OneDrive, un lecteur concurrent...) - constate reellement pendant les tests
    # Phase 8.4.3. La journalisation ne doit jamais devenir, elle-meme, une cause de crash du
    # backup : on retente brievement puis on abandonne silencieusement ce SEUL message (il reste
    # visible sur la console ci-dessous).
    for ($i = 0; $i -lt 3; $i++) {
        try { Add-Content -Path $LogFile -Value $line -ErrorAction Stop; break }
        catch { Start-Sleep -Milliseconds 200 }
    }
    switch ($Level) {
        "ERROR" { Write-Warning $Message }
        "WARN" { Write-Warning $Message }
        default { Write-Output $Message }
    }
}

# Retention des logs (30 jours par defaut) - jamais les logs recents, jamais les backups eux-memes.
Write-Log "INFO" "=== Retention des logs (${LogRetentionDays} jours) ==="
$LogCutoff = (Get-Date).AddDays(-$LogRetentionDays)
$OldLogs = Get-ChildItem $LogDir -Filter "backup_*.log" -File | Where-Object { $_.LastWriteTime -lt $LogCutoff }
foreach ($l in $OldLogs) {
    Remove-Item $l.FullName -Force
    Write-Log "INFO" "Log obsolete supprime (retention depassee) : $($l.FullName)"
}

function Protect-Secrets {
    # Scrubbing defensif applique UNIQUEMENT a la sortie brute de rclone avant journalisation -
    # jamais applique aux empreintes SHA-256/SHA-1 legitimes produites ailleurs dans ce script.
    # Cible la forme des credentials B2 (Key ID hexadecimal, Application Key prefixee "K00"),
    # jamais leur valeur reelle (jamais lue par ce script - rclone.conf n'est jamais ouvert ici).
    param([string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return $Text }
    $Text = $Text -replace '\bK00[0-9A-Za-z/+]{20,}\b', '***REDACTED-B2-APPLICATION-KEY***'
    $Text = $Text -replace '\b[0-9a-fA-F]{24,}\b', '***REDACTED-ID***'
    return $Text
}

function Fail($Message) {
    Write-Log "ERROR" $Message
    Write-Log "ERROR" "Backup local en echec - execution interrompue."
    exit 1
}

# --- Informations systeme non sensibles (Phase 8.4.3, diagnostic) -------------------------------
Write-Log "INFO" "Backup started (id=$Timestamp)"
Write-Log "INFO" "Hostname: $env:COMPUTERNAME"
Write-Log "INFO" "PowerShell version: $($PSVersionTable.PSVersion.ToString())"
Write-Log "INFO" "Destination B2 : ${RcloneRemote}:${RcloneBucket}"
try {
    $cDrive = Get-PSDrive -Name C -ErrorAction Stop
    Write-Log "INFO" ("Espace libre C: : {0:N1} Go" -f ($cDrive.Free / 1GB))
}
catch { Write-Log "WARN" "Espace libre C: non determinable : $($_.Exception.Message)" }
$extDriveLetter = Split-Path -Qualifier $ExternalDestination -ErrorAction SilentlyContinue
if ($extDriveLetter -and (Test-Path "$extDriveLetter\")) {
    try {
        $dDrive = Get-PSDrive -Name ($extDriveLetter.TrimEnd(":")) -ErrorAction Stop
        Write-Log "INFO" ("Espace libre ${extDriveLetter} : {0:N1} Go" -f ($dDrive.Free / 1GB))
    }
    catch { Write-Log "WARN" "Espace libre ${extDriveLetter} non determinable : $($_.Exception.Message)" }
}
else {
    Write-Log "INFO" "Destination externe ${ExternalDestination} non accessible au demarrage de ce run (informatif, verifie a nouveau avant la copie)."
}

# --- 1. Backup PostgreSQL --------------------------------------------------------------------
Write-Log "INFO" "PostgreSQL dump started"
$DbOutFile = Join-Path $BackupDir "edulinkage_$Timestamp.dump"
$ContainerTmp = "/tmp/edulinkage_backup_$Timestamp.dump"

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

    $DbHash = (Get-FileHash $DbOutFile -Algorithm SHA256).Hash
    "$DbHash  $(Split-Path $DbOutFile -Leaf)" | Set-Content "$DbOutFile.sha256"

    $DbSize = "{0:N1} KB" -f ((Get-Item $DbOutFile).Length / 1KB)
    Write-Log "INFO" "PostgreSQL dump completed: $DbOutFile ($DbSize) - integrite verifiee (pg_restore --list)."
}
finally {
    docker compose exec -T db rm -f $ContainerTmp 2>$null | Out-Null
}

# --- 2. Backup stockage fichiers -------------------------------------------------------------
Write-Log "INFO" "Storage archive started"
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

$StorageHash = (Get-FileHash $StorageOutFile -Algorithm SHA256).Hash
"$StorageHash  $(Split-Path $StorageOutFile -Leaf)" | Set-Content "$StorageOutFile.sha256"

$StorageSize = "{0:N1} KB" -f ((Get-Item $StorageOutFile).Length / 1KB)
Write-Log "INFO" "Storage archive completed: $StorageOutFile ($StorageSize) - $ArchiveFileCount fichiers, integrite verifiee."

# --- 3. Retention locale -------------------------------------------------------------------------
Write-Log "INFO" "=== Retention locale ($RetentionDays jours) ==="
$Cutoff = (Get-Date).AddDays(-$RetentionDays)
$OldFiles = Get-ChildItem $BackupDir -File | Where-Object {
    ($_.Name -like "edusphere_*.dump" -or $_.Name -like "edulinkage_*.dump" -or $_.Name -like "storage_*.tar.gz" -or $_.Name -like "*.sha256") -and $_.LastWriteTime -lt $Cutoff
}
foreach ($f in $OldFiles) {
    Remove-Item $f.FullName -Force
    Write-Log "INFO" "Supprime (retention depassee): $($f.FullName)"
}
Write-Log "INFO" "Retention locale appliquee : $($OldFiles.Count) fichier(s) obsolete(s) supprime(s)."

# --- 4. Envoi Backblaze B2 avec retry controle (Phase 8.4 / 8.4.3) -------------------------------
# Positionne AVANT la copie externe locale (section 5) : cette derniere s'est averee peu fiable
# sur cet hote (Phases 8.0-8.3) et ne doit plus pouvoir empecher l'envoi cloud. Regle stricte :
# un echec B2 (meme apres tous les retries) ne fait JAMAIS echouer ce script - le backup LOCAL
# ci-dessus reste valide dans tous les cas ; seul l'evenement "cloud" est marque en echec,
# journalise avec le detail reel (code de sortie + message rclone, jamais un credential).
Write-Log "INFO" "B2 upload started"

$Year = $Timestamp.Substring(0, 4)
$Month = $Timestamp.Substring(4, 2)
$Day = $Timestamp.Substring(6, 2)

$RcloneExe = (Get-Command rclone -ErrorAction SilentlyContinue).Source
if (-not $RcloneExe) {
    # Le shim PATH de winget ne persiste pas de facon fiable sur cet hote (constate Phase 8.4) -
    # recherche de secours directement sous le repertoire d'installation WinGet.
    $RcloneExe = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "rclone.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}

if ($RcloneExe) {
    try {
        $rcloneVersionOutput = & $RcloneExe version 2>$null | Select-Object -First 1
        Write-Log "INFO" "rclone version: $rcloneVersionOutput"
    }
    catch { Write-Log "WARN" "Impossible de determiner la version de rclone : $($_.Exception.Message)" }
    Write-Log "INFO" "rclone remote utilise : ${RcloneRemote} (configuration non affichee)"
}
else {
    Write-Log "WARN" "rclone introuvable (ni dans PATH, ni sous WinGet Packages)."
}

# Diagnostic reseau informatif (Phase 8.4.3, Etape 10) - ne bloque JAMAIS les tentatives B2. Sert
# uniquement a laisser une preuve dans le log pour un futur diagnostic (contrairement au 2026-10-01
# ou l'etat reseau au moment exact de l'appel B2 n'avait pu etre reconstitue qu'a posteriori via
# les journaux Windows - voir Phase 8.4.2).
try {
    $netTest = Test-NetConnection -ComputerName "api.backblazeb2.com" -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue -ErrorAction Stop
    if ($netTest) { Write-Log "INFO" "Network check: reachable (api.backblazeb2.com:443)" }
    else { Write-Log "WARN" "Network check: unavailable (api.backblazeb2.com:443)" }
}
catch {
    Write-Log "WARN" "Network check: inconclusive ($($_.Exception.Message))"
}

function Invoke-Rclone {
    # Capture reelle et separee du code de sortie / stdout / stderr, via Start-Process plutot que
    # l'operateur d'appel natif `&` : sous $ErrorActionPreference = "Stop", une simple ligne sur le
    # flux d'erreur standard d'un executable natif (capturee via 2>&1) devient une exception
    # PowerShell terminante (constate concretement Phase 8.4, sur l'envoi du manifest) - Start-Process
    # ne souffre pas de ce probleme, le flux d'erreur de l'enfant ne passe jamais par le flux
    # d'erreur de PowerShell.
    param([string[]]$Arguments)
    $stdoutFile = [IO.Path]::GetTempFileName()
    $stderrFile = [IO.Path]::GetTempFileName()
    try {
        $proc = Start-Process -FilePath $RcloneExe -ArgumentList $Arguments -NoNewWindow -Wait -PassThru `
            -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
        $stdout = Protect-Secrets (Get-Content $stdoutFile -Raw -ErrorAction SilentlyContinue)
        $stderr = Protect-Secrets (Get-Content $stderrFile -Raw -ErrorAction SilentlyContinue)
        return [ordered]@{ ExitCode = $proc.ExitCode; StdOut = $stdout; StdErr = $stderr }
    }
    finally {
        Remove-Item $stdoutFile, $stderrFile -Force -ErrorAction SilentlyContinue
    }
}

function Send-ToBackblazeOne {
    # Une tentative d'envoi+verification pour UN fichier. Retourne un statut structure (jamais
    # seulement un booleen) pour que l'appelant puisse journaliser/conserver le code de sortie et
    # le message reel de rclone en cas d'echec (Phase 8.4.3, Etape 4) - plus de message generique.
    param([string]$LocalFile, [string]$RemoteSubPath)
    try {
        $remoteTarget = "${RcloneRemote}:${RcloneBucket}/${RemoteSubPath}/"
        $copyResult = Invoke-Rclone -Arguments @("copy", $LocalFile, $remoteTarget, "--retries", "3", "--low-level-retries", "5", "--stats=0")
        if ($copyResult.ExitCode -ne 0) {
            Write-Log "ERROR" "rclone copy exit code=$($copyResult.ExitCode) fichier=$(Split-Path $LocalFile -Leaf)"
            if ($copyResult.StdErr) { Write-Log "ERROR" "rclone stderr=$($copyResult.StdErr.Trim())" }
            return [ordered]@{ Success = $false; Stage = "upload"; ExitCode = $copyResult.ExitCode; Message = ($copyResult.StdErr.Trim()) }
        }

        # Jamais se contenter du code de sortie de la copie : verification distante reelle
        # (presence + taille), meme principe que verify_remote_file() dans scripts/backup-all.sh.
        $remoteName = Split-Path $LocalFile -Leaf
        $localSize = (Get-Item $LocalFile).Length
        $listResult = Invoke-Rclone -Arguments @("lsl", "${RcloneRemote}:${RcloneBucket}/${RemoteSubPath}")
        if ($listResult.ExitCode -ne 0) {
            Write-Log "ERROR" "rclone lsl exit code=$($listResult.ExitCode) chemin=${RemoteSubPath}"
            if ($listResult.StdErr) { Write-Log "ERROR" "rclone stderr=$($listResult.StdErr.Trim())" }
            return [ordered]@{ Success = $false; Stage = "verify"; ExitCode = $listResult.ExitCode; Message = ($listResult.StdErr.Trim()) }
        }
        $match = ($listResult.StdOut -split "`n") | Where-Object { $_ -match [Regex]::Escape($remoteName) } | Select-Object -First 1
        if (-not $match) {
            $msg = "Fichier absent sur Backblaze apres envoi : ${RemoteSubPath}/${remoteName}"
            Write-Log "ERROR" $msg
            return [ordered]@{ Success = $false; Stage = "verify"; ExitCode = 0; Message = $msg }
        }
        $remoteSize = ($match.Trim() -split '\s+')[0]
        if ([int64]$remoteSize -ne $localSize) {
            $msg = "Taille distante ($remoteSize) differente de la taille locale ($localSize) pour ${RemoteSubPath}/${remoteName}"
            Write-Log "ERROR" $msg
            return [ordered]@{ Success = $false; Stage = "verify"; ExitCode = 0; Message = $msg }
        }
        Write-Log "INFO" "Verifie sur Backblaze (presence + taille = $localSize octets) : ${RemoteSubPath}/${remoteName}"
        return [ordered]@{ Success = $true; Stage = $null; ExitCode = 0; Message = $null }
    }
    catch {
        $msg = "Exception pendant l'envoi/verification Backblaze : $($_.Exception.Message)"
        Write-Log "ERROR" $msg
        return [ordered]@{ Success = $false; Stage = "upload"; ExitCode = -1; Message = $msg }
    }
}

function Send-BackupSetToBackblaze {
    # Envoie l'ensemble des fichiers d'UNE tentative (dump + sha256 + storage + sha256 + checksums
    # combine). Les memes fichiers locaux deja produits sont reutilises a chaque tentative de
    # retry (Phase 8.4.3, Etape 6) - jamais regeneres.
    param([string]$ChecksumsFile)
    $targets = @(
        @{ File = $DbOutFile; Sub = "postgres/$Year/$Month/$Day" }
        @{ File = "$DbOutFile.sha256"; Sub = "postgres/$Year/$Month/$Day" }
        @{ File = $StorageOutFile; Sub = "storage/$Year/$Month/$Day" }
        @{ File = "$StorageOutFile.sha256"; Sub = "storage/$Year/$Month/$Day" }
        @{ File = $ChecksumsFile; Sub = "checksums/$Year/$Month/$Day" }
    )
    $firstFailure = $null
    $allOk = $true
    foreach ($t in $targets) {
        $r = Send-ToBackblazeOne -LocalFile $t.File -RemoteSubPath $t.Sub
        if (-not $r.Success) {
            $allOk = $false
            if (-not $firstFailure) { $firstFailure = $r }
        }
    }
    return [ordered]@{ Success = $allOk; Failure = $firstFailure }
}

$CloudStatus = "failed"
$CloudAttempts = 0
$CloudErrorDetail = $null
$CloudStartedAt = (Get-Date).ToUniversalTime().ToString("o")

if (-not $RcloneExe) {
    $CloudErrorDetail = [ordered]@{ stage = "setup"; message = "rclone introuvable (ni dans PATH, ni sous WinGet Packages)."; exitCode = $null }
    Write-Log "ERROR" $CloudErrorDetail.message
}
elseif (-not (Test-Path $RcloneConfig)) {
    $CloudErrorDetail = [ordered]@{ stage = "setup"; message = "Fichier de configuration rclone introuvable : $RcloneConfig"; exitCode = $null }
    Write-Log "ERROR" $CloudErrorDetail.message
}
else {
    $env:RCLONE_CONFIG = $RcloneConfig

    # Empreintes combinees de cette execution (format sha256sum standard), envoyees sous checksums/.
    $ChecksumsFile = Join-Path $BackupDir "SHA256SUMS_$Timestamp.txt"
    @(
        "$DbHash  $(Split-Path $DbOutFile -Leaf)"
        "$StorageHash  $(Split-Path $StorageOutFile -Leaf)"
    ) | Set-Content $ChecksumsFile

    # Retry controle : B2_MAX_RETRIES tentatives, 30s puis 60s d'attente entre tentatives, jamais
    # infini, jamais de nouvelle tentative au-dela de $B2MaxRetries (Phase 8.4.3, Etape 5).
    $waitSeconds = @(30, 60)
    for ($attempt = 1; $attempt -le $B2MaxRetries; $attempt++) {
        $CloudAttempts = $attempt
        Write-Log "INFO" "B2 attempt $attempt/$B2MaxRetries"
        $result = Send-BackupSetToBackblaze -ChecksumsFile $ChecksumsFile
        if ($result.Success) {
            $CloudStatus = "success"
            $CloudErrorDetail = $null
            Write-Log "INFO" "B2 upload successful (attempt $attempt/$B2MaxRetries)"
            break
        }
        else {
            Write-Log "ERROR" "B2 attempt $attempt failed"
            $CloudErrorDetail = [ordered]@{
                stage    = $result.Failure.Stage
                message  = $result.Failure.Message
                exitCode = $result.Failure.ExitCode
            }
            if ($attempt -lt $B2MaxRetries) {
                $wait = $waitSeconds[$attempt - 1]
                Write-Log "INFO" "Attente ${wait}s avant la tentative suivante."
                Start-Sleep -Seconds $wait
            }
        }
    }
}
$CloudCompletedAt = (Get-Date).ToUniversalTime().ToString("o")
$CloudDurationSeconds = [Math]::Round(([DateTime]::Parse($CloudCompletedAt) - [DateTime]::Parse($CloudStartedAt)).TotalSeconds, 1)

if ($CloudStatus -eq "success") {
    Write-Log "INFO" "B2 upload finished: success (attempts=$CloudAttempts, duration=${CloudDurationSeconds}s)"
}
else {
    Write-Log "WARN" "B2 upload finished: failed apres $CloudAttempts tentative(s) (duration=${CloudDurationSeconds}s). Le backup LOCAL reste valide et n'est jamais supprime a cause de cet echec cloud."
}

# --- 5. Copie externe (Phase 17, disque local) - statut INDEPENDANT de B2 (Phase 8.4.3) ---------
# Depuis la Phase 8.4.3, un echec de cette copie n'interrompt plus le script (plus d'appel a
# Fail ici) : seul un echec du backup LOCAL (section 1/2) reste bloquant. "external" et "cloud"
# sont rapportes separement dans le manifest, jamais l'un a cause de l'autre.
Write-Log "INFO" "External copy D: started"
$ExternalStatus = "failed"
$externalDrive = Split-Path -Qualifier $ExternalDestination -ErrorAction SilentlyContinue
if (-not $externalDrive -or -not (Test-Path "$externalDrive\")) {
    $ExternalStatus = "skipped"
    Write-Log "WARN" "External copy D: skipped - destination inaccessible ($ExternalDestination). Le backup LOCAL reste valide ; aucune copie hors machine locale n'a ete produite pour cette execution (B2 reste independant, voir ci-dessus)."
}
else {
    try {
        New-Item -ItemType Directory -Force -Path $ExternalDestination | Out-Null
        $filesToCopy = @($DbOutFile, "$DbOutFile.sha256", $StorageOutFile, "$StorageOutFile.sha256")
        $externalOk = $true
        foreach ($f in $filesToCopy) {
            $destFile = Join-Path $ExternalDestination (Split-Path $f -Leaf)
            Copy-Item -Path $f -Destination $destFile -Force

            # Jamais se contenter de la copie elle-meme : recalcule le SHA-256 du fichier a
            # destination et le compare a l'empreinte produite a la source.
            if ($f -notlike "*.sha256") {
                $sourceHash = (Get-FileHash $f -Algorithm SHA256).Hash
                $destHash = (Get-FileHash $destFile -Algorithm SHA256).Hash
                if ($sourceHash -ne $destHash) {
                    $externalOk = $false
                    Write-Log "ERROR" "External copy D: integrite KO : $destFile (SHA-256 source != destination)."
                }
                else {
                    Write-Log "INFO" "External copy D: verifiee (SHA-256 identique) : $destFile"
                }
            }
        }
        $ExternalStatus = if ($externalOk) { "success" } else { "failed" }
    }
    catch {
        $ExternalStatus = "failed"
        Write-Log "ERROR" "External copy D: exception : $($_.Exception.Message)"
    }
}
if ($ExternalStatus -eq "failed") {
    Write-Log "WARN" "External copy D: failed (non bloquant - cloud.status reste independant)."
}
else {
    Write-Log "INFO" "External copy D: $ExternalStatus"
}

# --- Manifest de cette execution (Phase 8.4 / 8.4.3) --------------------------------------------
# Jamais de secret dedans. Toujours ecrit localement, quel que soit l'etat cloud/external, pour
# garder une trace exacte et structuree de ce qui s'est reellement passe (local/cloud/external
# distincts, voir Etape 13).
$Overall = if ($CloudStatus -eq "success" -and $ExternalStatus -eq "success") { "success" } else { "partial" }

$Manifest = [ordered]@{
    timestamp = (Get-Date).ToUniversalTime().ToString("o")
    local     = [ordered]@{ postgres = "success"; storage = "success" }
    postgres  = [ordered]@{
        file   = (Split-Path $DbOutFile -Leaf)
        size   = (Get-Item $DbOutFile).Length
        sha256 = $DbHash
    }
    storage   = [ordered]@{
        file   = (Split-Path $StorageOutFile -Leaf)
        size   = (Get-Item $StorageOutFile).Length
        sha256 = $StorageHash
    }
    cloud     = [ordered]@{
        provider        = "backblaze-b2"
        bucket          = $RcloneBucket
        status          = $CloudStatus
        attempts        = $CloudAttempts
        startedAt       = $CloudStartedAt
        completedAt     = $CloudCompletedAt
        durationSeconds = $CloudDurationSeconds
        error           = $CloudErrorDetail
    }
    external  = [ordered]@{
        destination = $ExternalDestination
        status      = $ExternalStatus
    }
    overall   = $Overall
}
$ManifestFile = Join-Path $BackupDir "backup-manifest_$Timestamp.json"
$Manifest | ConvertTo-Json -Depth 6 | Set-Content $ManifestFile
if ($RcloneExe -and (Test-Path $RcloneConfig)) {
    Send-ToBackblazeOne -LocalFile $ManifestFile -RemoteSubPath "manifests/$Year/$Month/$Day" | Out-Null
}

Write-Log "INFO" "Backup completed (overall=$Overall, cloud=$CloudStatus, external=$ExternalStatus)"
exit 0
