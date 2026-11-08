<#
.SYNOPSIS
    Fonctions partagees entre backup-all.ps1, test-restore-from-b2.ps1 et check-backup-health.ps1
    (Phase 8.4.4). Dot-source ce fichier : ". $PSScriptRoot\BackupCommon.ps1".

.DESCRIPTION
    backup-all.ps1 n'est PAS modifie par la Phase 8.4.4 (il a sa propre copie locale de ces
    fonctions, deja validee Phase 8.4.3) - ce fichier existe pour que les DEUX NOUVEAUX scripts
    de cette phase (restauration automatisee, verification de sante) ne dupliquent pas une
    troisieme fois la meme logique de journalisation / masquage de secrets / alerte.
#>

function Write-Log {
    param(
        [Parameter(Mandatory = $true)][string]$LogFile,
        [Parameter(Mandatory = $true)][ValidateSet("INFO", "WARN", "ERROR")][string]$Level,
        [Parameter(Mandatory = $true)][string]$Message
    )
    $line = "[$((Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))] [$Level] $Message"
    # Jamais laisser un incident de journalisation (verrou de fichier transitoire...) faire
    # echouer le script appelant - meme garde-fou que backup-all.ps1 (Phase 8.4.3).
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

function Protect-Secrets {
    # Identique a backup-all.ps1 (Phase 8.4.3) - jamais applique aux empreintes SHA-256/SHA-1
    # legitimes, uniquement a la sortie brute d'outils externes (rclone) avant journalisation.
    param([string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return $Text }
    $Text = $Text -replace '\bK00[0-9A-Za-z/+]{20,}\b', '***REDACTED-B2-APPLICATION-KEY***'
    $Text = $Text -replace '\b[0-9a-fA-F]{24,}\b', '***REDACTED-ID***'
    return $Text
}

function Invoke-RcloneCommon {
    # Capture reelle exit code / stdout / stderr via Start-Process (voir backup-all.ps1 Phase
    # 8.4.3 pour la justification detaillee : $ErrorActionPreference="Stop" transforme sinon
    # une simple ligne de stderr natif en exception terminante).
    param([string]$RcloneExe, [string[]]$Arguments)
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

function Resolve-RcloneExe {
    $exe = (Get-Command rclone -ErrorAction SilentlyContinue).Source
    if (-not $exe) {
        $exe = Get-ChildItem -Path "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter "rclone.exe" -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
    }
    return $exe
}

function Send-BackupAlert {
    # Abstraction d'alerte (Phase 8.4.4, Objectif 4/Strategie d'alerte). Aucun fournisseur reel
    # n'etait configure au moment de l'audit de cette phase (EMAIL_PROVIDER=local, SMTP_* vides,
    # aucun webhook Discord/Slack/Teams trouve dans le projet) - cette fonction N'INVENTE AUCUN
    # credential : elle journalise toujours clairement l'evenement, et n'essaie un envoi HTTP que
    # si BACKUP_ALERT_ENABLED=true ET BACKUP_ALERT_WEBHOOK_URL est renseigne (variables
    # d'environnement, jamais en dur). Un echec d'envoi ne doit JAMAIS faire echouer l'appelant.
    param(
        [Parameter(Mandatory = $true)][string]$LogFile,
        [Parameter(Mandatory = $true)][string]$Subject,
        [Parameter(Mandatory = $true)][string]$Message
    )
    Write-Log -LogFile $LogFile -Level "WARN" -Message "ALERT: $Subject - $Message"

    if ($env:BACKUP_ALERT_ENABLED -ne "true") {
        Write-Log -LogFile $LogFile -Level "INFO" -Message "Alerting desactive (BACKUP_ALERT_ENABLED != 'true') - evenement journalise uniquement, aucun envoi tente."
        return
    }
    $webhookUrl = $env:BACKUP_ALERT_WEBHOOK_URL
    if ([string]::IsNullOrWhiteSpace($webhookUrl)) {
        Write-Log -LogFile $LogFile -Level "WARN" -Message "BACKUP_ALERT_ENABLED=true mais BACKUP_ALERT_WEBHOOK_URL n'est pas defini - evenement journalise uniquement."
        return
    }
    try {
        # Format generique {text: ...} - compatible Slack/Discord/webhooks simples. A adapter si
        # un fournisseur reel (Teams, autre) est retenu en Phase 8.4.5 - aucune valeur en dur ici.
        $body = @{ text = "[EduLinkage Backup Alert] $Subject`n$Message" } | ConvertTo-Json -Compress
        Invoke-RestMethod -Uri $webhookUrl -Method Post -Body $body -ContentType "application/json" -TimeoutSec 10 -ErrorAction Stop | Out-Null
        Write-Log -LogFile $LogFile -Level "INFO" -Message "Alerte envoyee via webhook."
    }
    catch {
        Write-Log -LogFile $LogFile -Level "WARN" -Message "Echec d'envoi de l'alerte webhook (non bloquant) : $($_.Exception.Message)"
    }
}

function Assert-SafeRestoreTargetName {
    # Garde-fou explicite (Phase 8.4.4, Objectif 1 point 14) : refuse tout nom de base qui
    # pourrait correspondre a la production. Jamais de DROP sans passer par cette fonction.
    param([string]$Name, [string]$ProductionDbName)
    $forbidden = @($ProductionDbName, "edusphere", "postgres", "production") | Where-Object { $_ }
    if ($forbidden -contains $Name) {
        throw "Refus de securite : le nom de base cible '$Name' correspond a un nom reserve/production. Operation annulee."
    }
    if ($Name -notlike "edusphere_restore_test*") {
        throw "Refus de securite : le nom de base cible '$Name' ne suit pas la convention attendue 'edusphere_restore_test*'. Operation annulee."
    }
}
