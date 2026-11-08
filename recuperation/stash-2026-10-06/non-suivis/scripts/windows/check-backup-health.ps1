<#
.SYNOPSIS
    Verifie la sante du dernier backup produit par backup-all.ps1, sans le relancer (Phase 8.4.4,
    Objectif 6).

.DESCRIPTION
    Lit uniquement le manifest LOCAL le plus recent (backups/backup-manifest_*.json, deja produit
    par backup-all.ps1 - jamais modifie par ce script), verifie sa fraicheur et ses statuts
    (overall/cloud/external), et declenche une alerte (Send-BackupAlert, BackupCommon.ps1) si
    necessaire. N'ecrit, ne recree ni ne supprime aucun manifest existant.

.PARAMETER MaxAgeHours
    Age maximal tolere du dernier manifest avant de le considerer "backup absent depuis trop
    longtemps" (par defaut 36h, soit 1.5x la cadence quotidienne attendue).

.EXAMPLE
    powershell -File scripts\windows\check-backup-health.ps1
#>
param(
    [int]$MaxAgeHours = 36
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")
. (Join-Path $PSScriptRoot "BackupCommon.ps1")

$Timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$BackupDir = "backups"
$LogDir = Join-Path $BackupDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "health-check_$Timestamp.log"
New-Item -ItemType File -Force -Path $LogFile | Out-Null

Write-Log -LogFile $LogFile -Level "INFO" -Message "Backup health check started"

$Healthy = $true
$Reasons = @()

$latestManifest = Get-ChildItem $BackupDir -Filter "backup-manifest_*.json" -File -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -First 1

if (-not $latestManifest) {
    $Healthy = $false
    $Reasons += "Aucun manifest de backup trouve dans $BackupDir - impossible de confirmer qu'un backup a deja reussi."
    Write-Log -LogFile $LogFile -Level "ERROR" -Message $Reasons[-1]
}
else {
    Write-Log -LogFile $LogFile -Level "INFO" -Message "Dernier manifest : $($latestManifest.FullName)"
    $ageHours = [Math]::Round(((Get-Date) - $latestManifest.LastWriteTime).TotalHours, 1)
    Write-Log -LogFile $LogFile -Level "INFO" -Message "Age du dernier manifest : ${ageHours}h (seuil : ${MaxAgeHours}h)"
    if ($ageHours -gt $MaxAgeHours) {
        $Healthy = $false
        $Reasons += "Dernier backup age de ${ageHours}h, superieur au seuil de ${MaxAgeHours}h - backup absent depuis une periode anormalement longue."
        Write-Log -LogFile $LogFile -Level "ERROR" -Message $Reasons[-1]
    }

    try {
        $manifest = Get-Content $latestManifest.FullName -Raw | ConvertFrom-Json
    }
    catch {
        $Healthy = $false
        $Reasons += "Manifest illisible/corrompu : $($_.Exception.Message)"
        Write-Log -LogFile $LogFile -Level "ERROR" -Message $Reasons[-1]
        $manifest = $null
    }

    if ($manifest) {
        Write-Log -LogFile $LogFile -Level "INFO" -Message "overall=$($manifest.overall) cloud.status=$($manifest.cloud.status) external.status=$($manifest.external.status)"

        if ($manifest.overall -ne "success") {
            $Healthy = $false
            $Reasons += "overall != success (valeur reelle: $($manifest.overall))"
            Write-Log -LogFile $LogFile -Level "ERROR" -Message $Reasons[-1]
        }
        if ($manifest.cloud -and $manifest.cloud.status -eq "failed") {
            $Healthy = $false
            $Reasons += "cloud.status == failed"
            Write-Log -LogFile $LogFile -Level "ERROR" -Message $Reasons[-1]
        }
        if ($manifest.external -and $manifest.external.status -eq "failed") {
            $Healthy = $false
            $Reasons += "external.status == failed"
            Write-Log -LogFile $LogFile -Level "ERROR" -Message $Reasons[-1]
        }
    }
}

# Dernier resultat de restore test disponible, a titre informatif (ne conditionne pas, a lui
# seul, le statut "Healthy" de CE check - qui porte sur le backup, pas sur le restore test dont
# la cadence est differente, hebdomadaire - voir Objectif 5).
$latestRestoreManifest = Get-ChildItem (Join-Path $BackupDir "manifests") -Filter "restore-manifest_*.json" -File -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -First 1
if ($latestRestoreManifest) {
    try {
        $restoreManifest = Get-Content $latestRestoreManifest.FullName -Raw | ConvertFrom-Json
        Write-Log -LogFile $LogFile -Level "INFO" -Message "Dernier restore test : $($latestRestoreManifest.Name) overall=$($restoreManifest.overall)"
        if ($restoreManifest.overall -ne "success") {
            # Signale, mais ne bascule pas Healthy=false a lui seul : un restore test est un
            # controle periodique distinct du backup quotidien (Objectif 6 porte sur le backup).
            Write-Log -LogFile $LogFile -Level "WARN" -Message "Le dernier restore test n'est pas en succes (overall=$($restoreManifest.overall)) - a surveiller separement."
        }
    }
    catch { Write-Log -LogFile $LogFile -Level "WARN" -Message "Dernier restore manifest illisible : $($_.Exception.Message)" }
}
else {
    Write-Log -LogFile $LogFile -Level "INFO" -Message "Aucun restore test trouve pour le moment (informatif, Phase 8.4.4 vient de l'introduire)."
}

if ($Healthy) {
    Write-Log -LogFile $LogFile -Level "INFO" -Message "BACKUP HEALTH CHECK: OK"
    exit 0
}
else {
    $summary = $Reasons -join " | "
    Send-BackupAlert -LogFile $LogFile -Subject "Backup health check FAILED" -Message $summary
    Write-Log -LogFile $LogFile -Level "ERROR" -Message "BACKUP HEALTH CHECK: FAILED ($summary)"
    exit 1
}
