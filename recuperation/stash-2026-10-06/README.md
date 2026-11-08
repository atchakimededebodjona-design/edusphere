# Contenu du stash du 2026-10-06 (sauvegarde de récupération)

Stash d'origine : `b6d125d` — « On main: backup Windows avant synchronisation main 2026-10-06 »,
créé sur la base `9ea81da` avec les fichiers non suivis (3 parents : base, index `6c4d6f4`,
non suivis `103cf7d`). Le commit d'origine exact et son historique restent dans le bundle
`D:\RECUPERATION_HP_2026-11-08\edusphere-all.bundle` (non poussé : la base `9ea81da` et ses
5 ancêtres du 2026-09-21 contiennent une valeur de test non qualifiée).

- `suivis/` : versions des fichiers suivis modifiés dans le stash (`.env.example`,
  `scripts/windows/backup-all.ps1`), contenu exact du stash.
- `stash-modifications-suivies.patch` : diff du stash par rapport à sa base `9ea81da`.
- `non-suivis/` : fichiers non suivis capturés par le stash — dont les scripts appelés par les
  tâches planifiées `EduSphere-BackupHealth` (`check-backup-health.ps1`) et
  `EduSphere-WeeklyRestoreTest` (`test-restore-from-b2.ps1`), introuvables ailleurs.

L'index du stash ne diffère pas de sa base (rien n'était indexé). Aucun secret : les accès
Backblaze passent par la configuration rclone (`$env:RCLONE_CONFIG`) et les mots de passe
PostgreSQL par des variables ; `BACKUP_ALERT_WEBHOOK_URL` est vide dans `.env.example`.
Ces fichiers sont rangés à part : ils ne remplacent aucun fichier actif du dépôt.
