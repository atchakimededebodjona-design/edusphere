# PostgreSQL — Backup & Restore

Phase 7.3 (backup & pilot readiness). Décrit la stratégie minimale de sauvegarde/restauration
de la base PostgreSQL d'EduSphere, testée réellement (voir rapport Phase 7.3).

**Important (Phase 14)** : ce document ne couvre QUE PostgreSQL. Les fichiers écrits par
`StorageProvider` (photos élèves, documents, logos, PDF de bulletins) sont sauvegardés
séparément — voir [`docs/database/STORAGE_BACKUP_RESTORE.md`](STORAGE_BACKUP_RESTORE.md). Ne
jamais présenter une sauvegarde de cette base comme une sauvegarde complète d'EduSphere.

## Principe

Un volume Docker (`pgdata`) **n'est pas une sauvegarde** : il disparaît avec
`docker volume rm`, `docker compose down -v`, ou une corruption du disque de l'hôte Docker.
La stratégie ci-dessous produit un artefact de sauvegarde **indépendant** de ce volume, sur le
système de fichiers de l'hôte (ou, en production, un stockage externe durable).

## Scripts

| Fichier | Rôle |
|---|---|
| [`scripts/db-backup.sh`](../../scripts/db-backup.sh) | Produit un dump `pg_dump` (format custom `-Fc`) et le copie sur l'hôte |
| [`scripts/db-restore-test.sh`](../../scripts/db-restore-test.sh) | Restaure un dump dans une base de test dédiée et vérifie son contenu |
| [`scripts/db-verify-counts.sql`](../../scripts/db-verify-counts.sql) | Requête de comptage utilisée pour la vérification post-restauration |
| [`scripts/backup-all.sh`](../../scripts/backup-all.sh) (Phase 15) | Combine le backup DB ci-dessus et le backup stockage fichiers (voir `STORAGE_BACKUP_RESTORE.md`), applique la rétention |
| [`scripts/windows/backup-all.ps1`](../../scripts/windows/backup-all.ps1) (Phase 15) | Équivalent PowerShell natif de `backup-all.sh` — utilisé pour la planification réelle sur cet hôte de développement Windows |

## Format du backup

`pg_dump -Fc` (format **custom**, compressé) — permet une restauration sélective avec
`pg_restore` et une vérification d'intégrité sans restaurer (`pg_restore --list`), contrairement
à un dump SQL texte brut.

## Emplacement / stockage

- **Développement** : `backups/` à la racine du repo (créé par le script, non versionné —
  voir `.gitignore`). C'est un emplacement hôte, indépendant du volume `pgdata`, mais un simple
  répertoire local **ne constitue pas** une stratégie de disaster recovery de production.
- **Production (future, non implémentée)** : un stockage objet ou externe durable (ex.
  stockage compatible S3, disque réseau géré par l'hébergeur), physiquement séparé de la
  machine hébergeant PostgreSQL. Aucun hébergeur n'est figé à ce stade (cohérent avec la
  règle Phase 0 de ne pas figer d'hébergeur avant décision).

## Procédure de backup

```bash
scripts/db-backup.sh [service-compose]   # défaut: db
```

Étapes internes : `pg_dump -Fc` dans le conteneur (`/tmp`, stockage éphémère du conteneur) →
copie binaire sûre vers l'hôte via `docker cp` → suppression du fichier temporaire du
conteneur → vérification d'intégrité (`pg_restore --list`) sur le fichier hôte. Échoue avec un
code de sortie non nul et un message explicite à chaque étape qui peut échouer (dump vide,
échec de copie, archive invalide).

## Procédure de restauration / test

```bash
scripts/db-restore-test.sh <chemin-du-dump> [service-compose]
```

Restaure **exclusivement** dans une base dédiée `edusphere_restore_test` sur la même instance
PostgreSQL — **jamais** dans la base source. La base de test est recréée (DROP/CREATE) à
chaque exécution pour un test reproductible ; ce DROP/CREATE ne porte jamais sur la base
applicative. Affiche ensuite les comptages de tables clés (`scripts/db-verify-counts.sql`) à
comparer manuellement avec la base source pour conclure `RESTORE SUCCESS` / `RESTORE FAILED`.

Un test réel a été exécuté le 2026-09-04 (voir rapport Phase 7.3) : comptages identiques sur
7 tables, école de référence retrouvée intacte, RLS/policies/contraintes identiques entre
source et restauration.

## Gestion des secrets

Aucun mot de passe n'est écrit en dur dans les scripts ni passé en argument de ligne de
commande (visible dans `ps` ou l'historique shell). Les scripts s'exécutent **dans** le
conteneur `db` via `docker compose exec`, où `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`
sont déjà présents dans l'environnement (définis par `docker-compose.yml` / `.env`, jamais
committés) — les scripts ne font que les référencer via `$POSTGRES_PASSWORD`. Les fichiers de
dump ne contiennent pas de secret applicatif (JWT secret, credentials autres que les données
métier) — ils contiennent uniquement les données des tables (y compris les mots de passe
utilisateurs, mais **hachés** — `hashed_password`, jamais en clair).

## Fréquence et automatisation (Phase 15)

Backup **quotidien**, désormais **automatisé** plutôt que manuel :

- `scripts/backup-all.sh` (portable, pour un vrai hôte Linux) exécute `db-backup.sh` puis
  `scripts/storage-backup.sh` (voir `STORAGE_BACKUP_RESTORE.md`), puis applique une rétention de
  7 jours par défaut (`RETENTION_DAYS`).
- Sur cet hôte de développement (Windows, où `bash` n'a pas accès à Docker — contrainte déjà
  documentée), `scripts/windows/backup-all.ps1` réimplémente la même logique en PowerShell natif
  et est planifié via une tâche Windows réelle (`EduSphere-DailyBackup`, quotidienne à 2h,
  `Register-ScheduledTask`) — déclenchement manuel réel vérifié en Phase 15
  (`LastTaskResult=0`, nouveaux fichiers produits à l'heure exacte du déclenchement).
- Sur un vrai hôte Linux de déploiement : `crontab` standard invoquant
  `scripts/backup-all.sh`, voir `STORAGE_BACKUP_RESTORE.md` pour l'exemple exact.

Rétention : 7 backups quotidiens conservés par défaut, rotation automatique par date de fichier
(pas de politique complexe, cohérent avec le volume de backups encore faible à ce stade).

## Développement vs Production

| | Développement (actuel, depuis Phase 15) | Production (future, à mettre en place) |
|---|---|---|
| Déclenchement | **Automatique** — tâche planifiée Windows sur cet hôte ; `crontab` sur un hôte Linux | Planifié, même mécanisme, sur l'hôte de production retenu |
| Stockage | `backups/` local + copie automatique vers `D:\EduSphere-Backups` (disque physique distinct, Phase 17) | Stockage externe durable sur l'hôte de production réel — à établir séparément, voir `STORAGE_BACKUP_RESTORE.md` |
| Fréquence | Quotidienne | Quotidienne minimum |
| Rétention | 7 jours, rotation automatique | Politique de rétention à réévaluer selon le volume réel |
| Intégrité | `pg_restore --list` + empreinte SHA-256 (Phase 15) | Idem |
| Chiffrement | Aucun | À évaluer selon l'hébergeur retenu |

## Copie externe (Phase 17)

Depuis la Phase 17, `scripts/windows/backup-all.ps1` copie automatiquement chaque dump vers
`D:\EduSphere-Backups\` (disque physique distinct de celui hébergeant Docker sur cet hôte,
confirmé via `Get-Partition`/`Get-PhysicalDisk`, avec l'accord explicite de l'utilisateur — voir
`STORAGE_BACKUP_RESTORE.md` pour le détail complet et l'avertissement sur la portée de cette
résolution). SHA-256 revérifié après copie. Restauration **depuis cette copie externe**
réellement testée en Phase 17 (comptages identiques sur 7 tables), y compris une simulation
complète de perte de la machine principale — voir
[`docs/deployment/DISASTER_RECOVERY.md`](../deployment/DISASTER_RECOVERY.md).

## Limites actuelles

- La copie externe (Phase 17) est **résolue sur cette machine de développement précise**, pas
  par principe pour un futur hôte de production différent — à revérifier explicitement à chaque
  changement de machine hébergeant EduSphere.
- Aucun chiffrement des dumps au repos, y compris sur la copie externe.
- Le test de restauration démontre la restauration d'un dump complet ; il ne couvre pas un
  scénario de restauration partielle (point-in-time recovery), hors périmètre de cette phase.
- La rétention 7 jours s'applique à `backups/` local ; aucune rétention n'est appliquée sur la
  copie externe (`D:\EduSphere-Backups`), qui s'accumule tant que personne ne la nettoie
  manuellement.
- **Reconstituer une base de données entièrement neuve à partir du seul dump ne suffit pas** :
  `pg_dump` ne capture pas les rôles PostgreSQL au niveau du cluster (`edusphere`, créé par
  l'image officielle via `POSTGRES_USER` ; `edusphere_app`, créé par la migration 0002) — sans
  les recréer d'abord, `pg_restore` produit des erreurs de propriétaire/droits (les données
  elles-mêmes se restaurent correctement malgré ces erreurs, mais RLS et les droits applicatifs
  ne seraient pas corrects tant que `edusphere_app` n'existe pas). Procédure exacte documentée
  dans `docs/deployment/DISASTER_RECOVERY.md`, découverte et validée réellement en Phase 17.
