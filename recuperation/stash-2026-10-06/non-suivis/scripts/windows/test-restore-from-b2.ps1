<#
.SYNOPSIS
    Test automatise de restauration PostgreSQL depuis Backblaze B2 (Phase 8.4.4).

.DESCRIPTION
    Selectionne le backup B2 le plus recent dont le manifest indique cloud.status == "success"
    (jamais un backup partiellement uploade), le telecharge, verifie son integrite SHA-256
    (reference d'integrite - jamais remplacee par le SHA-1 natif de rclone), le restaure dans
    une base PostgreSQL TEMPORAIRE et EXPLICITEMENT NOMMEE (jamais la production), verifie les
    tables critiques et leurs comptages, puis nettoie systematiquement (base temporaire, fichiers
    telecharges) - meme en cas d'echec a n'importe quelle etape.

    Ne modifie jamais backup-all.ps1. Reutilise scripts/db-verify-counts.sql (deja la reference
    projet pour les 7 tables critiques) et les memes fonctions que backup-all.ps1 (Write-Log,
    Protect-Secrets, resolution rclone) via BackupCommon.ps1, sans dupliquer une 3e fois cette
    logique.

.PARAMETER RcloneRemote
    Remote rclone B2 (par defaut "backblaze-edulinkage", identique a backup-all.ps1).

.PARAMETER RcloneBucket
    Bucket B2 (par defaut "edulinkage-backups").

.PARAMETER RcloneConfig
    Chemin du fichier de configuration rclone (jamais commite, jamais affiche).

.PARAMETER DbService
    Nom du service docker compose PostgreSQL (par defaut "db"). Permet de simuler une base
    indisponible (Test 3) en passant un nom de service inexistant, sans toucher au vrai service.

.PARAMETER SimulateIntegrityFailure
    Test 2 uniquement : force un echec de verification SHA-256 sans modifier le backup B2 reel.

.EXAMPLE
    powershell -File scripts\windows\test-restore-from-b2.ps1
#>
param(
    [string]$RcloneRemote = "backblaze-edulinkage",
    [string]$RcloneBucket = "edulinkage-backups",
    [string]$RcloneConfig = (Join-Path $env:USERPROFILE ".config\rclone\rclone.conf"),
    [string]$DbService = "db",
    [switch]$SimulateIntegrityFailure
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")
. (Join-Path $PSScriptRoot "BackupCommon.ps1")

$Timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$BackupDir = "backups"
$LogDir = Join-Path $BackupDir "logs"
$ManifestDir = Join-Path $BackupDir "manifests"
New-Item -ItemType Directory -Force -Path $LogDir, $ManifestDir | Out-Null
$LogFile = Join-Path $LogDir "restore_$Timestamp.log"
New-Item -ItemType File -Force -Path $LogFile | Out-Null

# Retention des logs de restore (30 jours, Objectif 2) - jamais les backups/objets B2.
$LogCutoff = (Get-Date).AddDays(-30)
Get-ChildItem $LogDir -Filter "restore_*.log" -File | Where-Object { $_.LastWriteTime -lt $LogCutoff } | ForEach-Object {
    Remove-Item $_.FullName -Force
    Write-Log -LogFile $LogFile -Level "INFO" -Message "Log de restore obsolete supprime : $($_.FullName)"
}

Write-Log -LogFile $LogFile -Level "INFO" -Message "Starting B2 restore test (id=$Timestamp)"

$ProductionDbName = $env:POSTGRES_DB
if (-not $ProductionDbName) {
    # .env n'est pas charge par PowerShell (seul docker compose le lit) - lu ici en lecture
    # seule, uniquement pour le garde-fou de securite, jamais pour s'y connecter directement.
    $envLine = Get-Content ".env" -ErrorAction SilentlyContinue | Where-Object { $_ -match '^POSTGRES_DB=' } | Select-Object -First 1
    if ($envLine) { $ProductionDbName = ($envLine -split '=', 2)[1].Trim() }
}
if (-not $ProductionDbName) { $ProductionDbName = "edusphere" }
Write-Log -LogFile $LogFile -Level "INFO" -Message "Nom de base production a ne jamais cibler : $ProductionDbName"

$RestoreDb = "edusphere_restore_test"
Assert-SafeRestoreTargetName -Name $RestoreDb -ProductionDbName $ProductionDbName
Write-Log -LogFile $LogFile -Level "INFO" -Message "Base de restauration cible (jamais production) : $RestoreDb"

$DownloadDir = Join-Path $env:TEMP "edulinkage-restore-test-$Timestamp"
New-Item -ItemType Directory -Force -Path $DownloadDir | Out-Null

$RestoreManifest = [ordered]@{
    timestamp  = (Get-Date).ToUniversalTime().ToString("o")
    source     = [ordered]@{ provider = "backblaze-b2"; bucket = $RcloneBucket; backupId = $null; manifestObject = $null; postgresObject = $null }
    integrity  = [ordered]@{ algorithm = "SHA-256"; expected = $null; actual = $null; status = "unknown" }
    restore    = [ordered]@{ database = $RestoreDb; status = "unknown" }
    validation = [ordered]@{ status = "unknown"; tables = [ordered]@{} }
    cleanup    = [ordered]@{ status = "unknown" }
    overall    = "failed"
}

function Save-RestoreManifest {
    $path = Join-Path $ManifestDir "restore-manifest_$Timestamp.json"
    $RestoreManifest | ConvertTo-Json -Depth 6 | Set-Content $path
    Write-Log -LogFile $LogFile -Level "INFO" -Message "Restore manifest ecrit : $path"
}

$ExitCode = 1
try {
    $RcloneExe = Resolve-RcloneExe
    if (-not $RcloneExe) { throw "rclone introuvable (ni PATH, ni WinGet Packages)." }
    if (-not (Test-Path $RcloneConfig)) { throw "Fichier de configuration rclone introuvable : $RcloneConfig" }
    $env:RCLONE_CONFIG = $RcloneConfig

    # --- 1. Selection du dernier backup B2 dont cloud.status == "success" --------------------
    Write-Log -LogFile $LogFile -Level "INFO" -Message "Recherche des manifests B2 (${RcloneRemote}:${RcloneBucket}/manifests)..."
    $listResult = Invoke-RcloneCommon -RcloneExe $RcloneExe -Arguments @("lsf", "${RcloneRemote}:${RcloneBucket}/manifests", "-R", "--include", "*.json")
    if ($listResult.ExitCode -ne 0) { throw "Impossible de lister les manifests B2 (exit=$($listResult.ExitCode)) : $($listResult.StdErr)" }
    $candidates = ($listResult.StdOut -split "`n") | Where-Object { $_.Trim() -ne "" } | Sort-Object -Descending
    if (-not $candidates -or $candidates.Count -eq 0) { throw "Aucun manifest trouve sur B2 - aucun backup eligible." }
    Write-Log -LogFile $LogFile -Level "INFO" -Message "$($candidates.Count) manifest(s) trouve(s) sur B2, recherche du plus recent avec cloud.status=success..."

    $SelectedManifestPath = $null
    $SelectedManifest = $null
    foreach ($c in ($candidates | Select-Object -First 20)) {
        $tmpManifest = Join-Path $DownloadDir ([IO.Path]::GetFileName($c.Trim()))
        $dl = Invoke-RcloneCommon -RcloneExe $RcloneExe -Arguments @("copyto", "${RcloneRemote}:${RcloneBucket}/manifests/$($c.Trim())", $tmpManifest)
        if ($dl.ExitCode -ne 0 -or -not (Test-Path $tmpManifest)) { continue }
        try {
            $parsed = Get-Content $tmpManifest -Raw | ConvertFrom-Json
        }
        catch { continue }
        if ($parsed.cloud -and $parsed.cloud.status -eq "success") {
            $SelectedManifestPath = $c.Trim()
            $SelectedManifest = $parsed
            break
        }
    }
    if (-not $SelectedManifest) { throw "Aucun backup avec cloud.status==success trouve parmi les manifests recents - restore test annule (jamais un backup partiel)." }

    $RestoreManifest.source.backupId = [IO.Path]::GetFileNameWithoutExtension($SelectedManifest.postgres.file)
    $RestoreManifest.source.manifestObject = "manifests/$SelectedManifestPath"
    Write-Log -LogFile $LogFile -Level "INFO" -Message "Selected backup : $($SelectedManifest.postgres.file) (manifest=$SelectedManifestPath, cloud.status=success)"

    # Le chemin postgres/<meme YYYY/MM/DD que le manifest>/<fichier> - meme execution, memes dates.
    $datePart = ($SelectedManifestPath -replace '/[^/]+$', '')
    $PostgresRemotePath = "${RcloneRemote}:${RcloneBucket}/postgres/$datePart/$($SelectedManifest.postgres.file)"
    $RestoreManifest.source.postgresObject = "postgres/$datePart/$($SelectedManifest.postgres.file)"

    # --- 2. Telechargement dump + verification SHA-256 (reference d'integrite) ----------------
    Write-Log -LogFile $LogFile -Level "INFO" -Message "Telechargement : $PostgresRemotePath"
    $localDump = Join-Path $DownloadDir $SelectedManifest.postgres.file
    $dlDump = Invoke-RcloneCommon -RcloneExe $RcloneExe -Arguments @("copyto", $PostgresRemotePath, $localDump)
    if ($dlDump.ExitCode -ne 0 -or -not (Test-Path $localDump)) { throw "Echec du telechargement du dump depuis B2 : $($dlDump.StdErr)" }

    $actualSha256 = (Get-FileHash $localDump -Algorithm SHA256).Hash
    $expectedSha256 = $SelectedManifest.postgres.sha256
    if ($SimulateIntegrityFailure) {
        # Test 2 (Objectif 8) : simulation controlee, sans jamais modifier le backup B2 reel -
        # on force seulement la valeur ATTENDUE localement, le fichier distant n'est pas touche.
        $expectedSha256 = "0000000000000000000000000000000000000000000000000000000000000000"
        Write-Log -LogFile $LogFile -Level "WARN" -Message "SimulateIntegrityFailure actif : SHA-256 attendu force a une valeur invalide pour ce test (B2 non modifie)."
    }
    $RestoreManifest.integrity.expected = $expectedSha256
    $RestoreManifest.integrity.actual = $actualSha256

    if ($actualSha256 -ne $expectedSha256) {
        $RestoreManifest.integrity.status = "failed"
        throw "Integrite KO : SHA-256 attendu ($expectedSha256) != SHA-256 reel ($actualSha256) - restauration ANNULEE."
    }
    $RestoreManifest.integrity.status = "success"
    Write-Log -LogFile $LogFile -Level "INFO" -Message "SHA-256 verification successful"

    # --- 3. Restauration dans une base TEMPORAIRE, jamais la production ----------------------
    $ContainerId = (docker compose ps -q $DbService 2>$null)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ContainerId)) {
        throw "Service PostgreSQL '$DbService' injoignable (docker compose ps a echoue ou ne renvoie aucun conteneur) - restauration annulee, production non affectee."
    }
    $ContainerTmp = "/tmp/restore_test_$Timestamp.dump"
    docker cp $localDump "${ContainerId}:${ContainerTmp}"
    if ($LASTEXITCODE -ne 0) { throw "Echec de copie du dump vers le conteneur $DbService." }

    # SQL ecrit dans un fichier temporaire puis execute via psql -f : une requete inline -c "..."
    # imbriquant une 3e paire de guillemets doubles s'est revelee corrompue par le passage
    # d'arguments PowerShell 5.1 -> executable natif (constate reellement pendant les tests
    # Phase 8.4.4 - "syntax error at end of input" cote psql, quelle que soit la forme de
    # guillemets essayee). Le fichier evite ce probleme entierement - meme principe deja utilise
    # ci-dessous pour db-verify-counts.sql. OWNER explicite omis : le role connectant devient
    # proprietaire par defaut.
    Assert-SafeRestoreTargetName -Name $RestoreDb -ProductionDbName $ProductionDbName
    $PrepareSqlLocal = Join-Path $DownloadDir "prepare-restore-db.sql"
    "DROP DATABASE IF EXISTS $RestoreDb;`nCREATE DATABASE $RestoreDb;" | Set-Content $PrepareSqlLocal
    $ContainerPrepareSql = "/tmp/prepare-restore-db-$Timestamp.sql"
    docker cp $PrepareSqlLocal "${ContainerId}:${ContainerPrepareSql}"
    if ($LASTEXITCODE -ne 0) { throw "Echec de copie du script de preparation de base vers le conteneur." }
    docker compose exec -T $DbService sh -c "PGPASSWORD=`"`$POSTGRES_PASSWORD`" psql -U `"`$POSTGRES_USER`" -d postgres -v ON_ERROR_STOP=1 -f '$ContainerPrepareSql'"
    if ($LASTEXITCODE -ne 0) { throw "Echec DROP/CREATE DATABASE $RestoreDb (base de test uniquement, jamais la production)." }
    docker compose exec -T $DbService rm -f $ContainerPrepareSql 2>$null | Out-Null

    docker compose exec -T $DbService sh -c "PGPASSWORD=`"`$POSTGRES_PASSWORD`" pg_restore -U `"`$POSTGRES_USER`" -d '$RestoreDb' '$ContainerTmp'"
    if ($LASTEXITCODE -ne 0) { $RestoreManifest.restore.status = "failed"; throw "pg_restore a signale une erreur sur $RestoreDb." }
    $RestoreManifest.restore.status = "success"
    Write-Log -LogFile $LogFile -Level "INFO" -Message "PostgreSQL restore successful"

    # --- 4. Validation : existence reelle des tables critiques + comptages -------------------
    $criticalTables = @("organizations", "schools", "users", "students", "attendance_records", "assessment_results", "report_cards")
    $tableList = ($criticalTables | ForEach-Object { "'$_'" }) -join ","
    $existQuery = "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name = ANY(ARRAY[$tableList]);"
    $ExistSqlLocal = Join-Path $DownloadDir "check-tables-exist.sql"
    $existQuery | Set-Content $ExistSqlLocal
    $ContainerExistSql = "/tmp/check-tables-exist-$Timestamp.sql"
    docker cp $ExistSqlLocal "${ContainerId}:${ContainerExistSql}"
    $existRaw = docker compose exec -T $DbService sh -c "PGPASSWORD=`"`$POSTGRES_PASSWORD`" psql -U `"`$POSTGRES_USER`" -d '$RestoreDb' -t -A -f '$ContainerExistSql'"
    if ($LASTEXITCODE -ne 0) { throw "Impossible de verifier l'existence des tables critiques dans $RestoreDb." }
    docker compose exec -T $DbService rm -f $ContainerExistSql 2>$null | Out-Null
    $existingTables = @($existRaw -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" })
    foreach ($t in $criticalTables) {
        if ($existingTables -notcontains $t) {
            Write-Log -LogFile $LogFile -Level "WARN" -Message "Table critique absente du schema restaure : $t"
        }
    }

    $ContainerSql = "/tmp/db-verify-counts-$Timestamp.sql"
    docker cp "scripts\db-verify-counts.sql" "${ContainerId}:${ContainerSql}"
    $countsRaw = docker compose exec -T $DbService sh -c "PGPASSWORD=`"`$POSTGRES_PASSWORD`" psql -U `"`$POSTGRES_USER`" -d '$RestoreDb' -t -A -F'|' -f '$ContainerSql'"
    if ($LASTEXITCODE -ne 0) { throw "db-verify-counts.sql a echoue sur $RestoreDb (une table attendue manque-t-elle reellement ?)." }
    docker compose exec -T $DbService rm -f $ContainerSql 2>$null | Out-Null

    $validationOk = $true
    foreach ($line in ($countsRaw -split "`n")) {
        $line = $line.Trim()
        if ($line -eq "") { continue }
        $parts = $line -split '\|'
        if ($parts.Count -ne 2) { continue }
        $tableName = $parts[0].Trim()
        $rowCount = $parts[1].Trim()
        $RestoreManifest.validation.tables[$tableName] = [int]$rowCount
        Write-Log -LogFile $LogFile -Level "INFO" -Message "${tableName}: ${rowCount} rows"
        if ($existingTables -notcontains $tableName) { $validationOk = $false }
    }
    if ($existingTables.Count -ne $criticalTables.Count) {
        $validationOk = $false
        Write-Log -LogFile $LogFile -Level "WARN" -Message "Seules $($existingTables.Count)/$($criticalTables.Count) tables critiques existent dans le schema restaure."
    }

    # Comparaison avec le manifest source : le manifest de backup ne contient pas de comptages
    # par table (seulement taille/SHA-256 des fichiers) - rien a comparer ici, ne pas fabriquer
    # de valeurs attendues (consigne explicite).
    Write-Log -LogFile $LogFile -Level "INFO" -Message "Comparaison avec le manifest source : non disponible (le manifest de backup ne contient pas de comptages par table)."

    # Requete simple (Objectif 1 point 12).
    docker compose exec -T $DbService sh -c "PGPASSWORD=`"`$POSTGRES_PASSWORD`" psql -U `"`$POSTGRES_USER`" -d '$RestoreDb' -c 'SELECT 1;'" | Out-Null
    if ($LASTEXITCODE -ne 0) { $validationOk = $false; Write-Log -LogFile $LogFile -Level "WARN" -Message "La requete simple (SELECT 1) a echoue sur $RestoreDb." }

    $RestoreManifest.validation.status = if ($validationOk) { "success" } else { "failed" }
    if (-not $validationOk) { throw "Validation post-restauration en echec (tables critiques manquantes ou requete simple en echec)." }

    $RestoreManifest.overall = "success"
    $ExitCode = 0
    Write-Log -LogFile $LogFile -Level "INFO" -Message "RESTORE TEST SUCCESS"
}
catch {
    Write-Log -LogFile $LogFile -Level "ERROR" -Message "Restore test failed : $($_.Exception.Message)"
    $RestoreManifest.overall = "failed"
    $RestoreManifest.error = [ordered]@{ stage = "restore-test"; message = $_.Exception.Message }
    Send-BackupAlert -LogFile $LogFile -Subject "Restore test FAILED" -Message $_.Exception.Message
    $ExitCode = 1
}
finally {
    # --- 5. Nettoyage systematique, meme en cas d'echec a n'importe quelle etape --------------
    # $ErrorActionPreference="Continue" UNIQUEMENT pour ce bloc : constate reellement pendant les
    # tests Phase 8.4.4 (Test 3 - service Docker inexistant) qu'un appel natif en echec (exit non
    # nul) peut se transformer en exception terminante sous "Stop" meme avec stderr redirige vers
    # $null - "Continue" elimine ce risque pour de bon plutot que de continuer a chasser le
    # mecanisme exact. Le nettoyage ne doit jamais crasher, quelle que soit la cause de l'echec
    # initial.
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $cleanupOk = $true
    try {
        Assert-SafeRestoreTargetName -Name $RestoreDb -ProductionDbName $ProductionDbName
        $CleanupContainerId = (docker compose ps -q $DbService 2>$null)
        if (-not [string]::IsNullOrWhiteSpace($CleanupContainerId)) {
            # Verifie d'abord que la base existe reellement avant de tenter un DROP : une
            # commande "DROP DATABASE IF EXISTS" sur une base absente emet un NOTICE sur stderr
            # qui, combine a $ErrorActionPreference="Stop", se transforme en exception PowerShell
            # meme si l'operation SQL elle-meme est un succes benin (constate reellement pendant
            # les tests Phase 8.4.4, Test 2 - integrite volontairement incorrecte : aucune base
            # n'avait ete creee, le DROP "reussi-mais-inutile" etait pourtant journalise comme un
            # echec de cleanup). Eviter l'appel plutot que son message est plus sur que de
            # continuer a chasser la cause exacte de cette conversion stderr->exception.
            $CheckExistsSqlLocal = Join-Path $DownloadDir "check-db-exists.sql"
            "SELECT 1 FROM pg_database WHERE datname='$RestoreDb';" | Set-Content $CheckExistsSqlLocal -ErrorAction SilentlyContinue
            $ContainerCheckExistsSql = "/tmp/check-db-exists-$Timestamp.sql"
            docker cp $CheckExistsSqlLocal "${CleanupContainerId}:${ContainerCheckExistsSql}" 2>$null | Out-Null
            $dbExistsRaw = docker compose exec -T $DbService sh -c "PGPASSWORD=`"`$POSTGRES_PASSWORD`" psql -U `"`$POSTGRES_USER`" -d postgres -t -A -f '$ContainerCheckExistsSql'" 2>$null
            docker compose exec -T $DbService rm -f $ContainerCheckExistsSql 2>$null | Out-Null

            if (($dbExistsRaw -join "") -match "1") {
                $CleanupSqlLocal = Join-Path $DownloadDir "cleanup-restore-db.sql"
                "DROP DATABASE IF EXISTS $RestoreDb;" | Set-Content $CleanupSqlLocal -ErrorAction SilentlyContinue
                $ContainerCleanupSql = "/tmp/cleanup-restore-db-$Timestamp.sql"
                docker cp $CleanupSqlLocal "${CleanupContainerId}:${ContainerCleanupSql}" 2>$null | Out-Null
                docker compose exec -T $DbService sh -c "PGPASSWORD=`"`$POSTGRES_PASSWORD`" psql -U `"`$POSTGRES_USER`" -d postgres -v ON_ERROR_STOP=1 -f '$ContainerCleanupSql'" 2>$null | Out-Null
                if ($LASTEXITCODE -ne 0) { $cleanupOk = $false; Write-Log -LogFile $LogFile -Level "WARN" -Message "Cleanup base de test : DROP DATABASE a renvoye un code d'erreur." }
                else { Write-Log -LogFile $LogFile -Level "INFO" -Message "Cleanup base de test : $RestoreDb supprimee." }
                docker compose exec -T $DbService rm -f $ContainerCleanupSql 2>$null | Out-Null
            }
            else {
                Write-Log -LogFile $LogFile -Level "INFO" -Message "Cleanup base de test : $RestoreDb n'existe pas (rien a nettoyer)."
            }
        }
        else {
            Write-Log -LogFile $LogFile -Level "INFO" -Message "Cleanup base de test : service '$DbService' injoignable, aucune base de test n'a donc pu etre creee - rien a nettoyer."
        }
    }
    catch { $cleanupOk = $false; Write-Log -LogFile $LogFile -Level "WARN" -Message "Cleanup base de test : $($_.Exception.Message)" }
    try {
        if (Test-Path $DownloadDir) { Remove-Item $DownloadDir -Recurse -Force -ErrorAction Stop }
    }
    catch { $cleanupOk = $false; Write-Log -LogFile $LogFile -Level "WARN" -Message "Cleanup fichiers temporaires : $($_.Exception.Message)" }
    $RestoreManifest.cleanup.status = if ($cleanupOk) { "success" } else { "failed" }
    Write-Log -LogFile $LogFile -Level "INFO" -Message "Cleanup $($RestoreManifest.cleanup.status)"
    Save-RestoreManifest
    if ($RestoreManifest.overall -ne "success" -and $RestoreManifest.cleanup.status -ne "success") {
        Send-BackupAlert -LogFile $LogFile -Subject "Restore test cleanup FAILED" -Message "Le nettoyage apres echec de restauration n'a pas pu etre confirme - verification manuelle recommandee."
    }
}

exit $ExitCode
