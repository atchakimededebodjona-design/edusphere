# Stockage fichiers (StorageProvider) — Backup & Restore

Phase 14 (Deployment Durability & Production Configuration Readiness). Décrit la sauvegarde du
stockage fichiers applicatif — **distinct et complémentaire** de
[`docs/database/BACKUP_RESTORE.md`](BACKUP_RESTORE.md), qui ne couvre que PostgreSQL.

## Pourquoi un document séparé

`scripts/db-backup.sh` sauvegarde uniquement les tables PostgreSQL. Il ne sauvegarde **jamais**
les fichiers écrits par `LocalStorageProvider` (`apps/api/app/core/storage.py`) : photos
élèves, documents élèves, logos d'école, PDF de bulletins. Avant la Phase 14, ces fichiers
vivaient uniquement dans la couche writable du conteneur `api` — un simple
`docker compose up --build` les effaçait définitivement, sans lien avec l'état de la sauvegarde
PostgreSQL. **Ne jamais présenter le backup PostgreSQL comme un backup complet d'EduSphere.**

## Emplacement (depuis Phase 14)

`STORAGE_LOCAL_PATH=./storage` (voir `.env`) est désormais monté en bind mount hôte via
`docker-compose.yml` :

```yaml
api:
  volumes:
    - ./apps/api/storage:/app/storage
```

Chemin hôte : `apps/api/storage/` (déjà présent dans `.gitignore` et `.dockerignore` — anticipé
depuis le début du projet, jamais réellement monté avant cette phase). Ce bind mount protège
contre la recréation/le remplacement du conteneur `api`. Il ne protège **pas** contre : une
panne disque de la machine hôte, la perte de l'hôte lui-même, une suppression accidentelle du
répertoire, ou l'absence de sauvegarde de ce répertoire — un volume/bind mount n'est **pas** un
backup (même principe déjà énoncé pour `pgdata` dans `BACKUP_RESTORE.md`).

## Procédure de backup (automatisée depuis Phase 15)

- **Script portable** : `scripts/storage-backup.sh` — tar de `apps/api/storage/` vers
  `backups/storage_<horodatage>.tar.gz`, vérifie que l'archive est non vide, que son listing
  (`tar -tzf`) est lisible et que son nombre de fichiers correspond exactement à la source, puis
  écrit une empreinte SHA-256 à côté (`.sha256`). Retourne un code de sortie non nul et un
  message clair sur `stderr` en cas d'échec à n'importe quelle étape (jamais un `exit 0` masquant
  un échec).
- **Combiné avec PostgreSQL** : `scripts/backup-all.sh` exécute `db-backup.sh` puis
  `storage-backup.sh` l'un après l'autre (fenêtre de désynchronisation de l'ordre de la seconde,
  voir "Ordre de restauration" ci-dessous), puis applique une rétention de 7 jours par défaut
  (variable `RETENTION_DAYS`).
- **Sur cet hôte de développement (Windows)** : `bash` (lanceur WSL disponible ici) n'a pas accès
  à Docker — contrainte déjà documentée dans les phases précédentes de ce projet, reconfirmée en
  Phase 15. `scripts/windows/backup-all.ps1` réimplémente la même logique en PowerShell natif
  (`docker.exe` est directement accessible depuis PowerShell) et est **réellement planifié** sur
  cet hôte via une tâche planifiée Windows (`Register-ScheduledTask`, nom `EduSphere-DailyBackup`,
  quotidienne à 2h) — voir [Phase 15](../phases/PHASE_15_IMPLEMENTATION.md) pour la preuve
  d'exécution réelle (déclenchement manuel + attente du déclenchement planifié suivant, résultat
  `LastTaskResult=0`).
- **Sur un vrai hôte de déploiement (Linux, futur)** : utiliser directement
  `scripts/backup-all.sh` via une entrée crontab standard, par exemple
  `0 2 * * * cd /path/to/edusphere && scripts/backup-all.sh >> /var/log/edusphere-backup.log 2>&1`.

Aucun secret n'est contenu dans ces archives — uniquement des fichiers utilisateur (images,
PDF, documents), jamais de mot de passe, token ou clé (le stockage applicatif ne sert qu'à cet
usage, confirmé par lecture de `app/core/storage.py` et de ses appelants).

## Procédure de restauration (testée réellement en Phase 15)

Comme pour PostgreSQL, ne jamais extraire directement par-dessus le répertoire de production.
`scripts/storage-restore-test.sh <archive.tar.gz>` extrait vers un répertoire **temporaire**
dédié (jamais `apps/api/storage/`), vérifie que l'extraction a produit au moins un fichier, puis
nettoie automatiquement ce répertoire temporaire en fin de script.

**Test réel exécuté en Phase 15** (pas seulement une extraction vers un répertoire temporaire
comme le limitait cette section avant Phase 15) : un fichier de test a été écrit via
`StorageProvider.upload()`, capturé par un vrai backup, puis restauré via
`scripts/storage-restore-test.sh` — extraction réussie, contenu identique, répertoire temporaire
nettoyé automatiquement, `apps/api/storage/` jamais touché. Résultat réel :
`RESTORE SUCCESS ... 1 fichiers`. Voir le rapport Phase 15 pour le détail complet.

## Ordre de restauration (important — risque de désynchronisation)

Les lignes en base (`Student.photo_path`, `StudentDocument.file_path`, `School.logo_path`,
`ReportCard.pdf_path`) référencent des chemins de fichiers **par chaîne de caractères**, sans
contrainte d'intégrité au niveau du système de fichiers. Restaurer la base de données et le
stockage fichiers à partir de deux instantanés pris à des moments différents peut donc produire
un état incohérent :

- un enregistrement en base pointe vers un fichier absent de l'archive de stockage restaurée
  (téléchargement en 404) ;
- ou l'inverse : des fichiers restaurés qui ne sont plus référencés par aucune ligne (orphelins,
  inoffensif mais consomme de l'espace).

**Recommandation** : toujours sauvegarder `scripts/db-backup.sh` et l'archive de stockage
ci-dessus l'un juste après l'autre, et toujours les restaurer ensemble, comme une paire
horodatée — jamais un dump PostgreSQL d'un jour avec une archive de stockage d'un autre jour.

## Stockage indépendant de la source — RÉSOLU sur cet hôte (Phase 17)

**Résolu sur cette machine de développement précise, pas résolu par principe pour un futur hôte
de production différent** — distinction importante, affirmée explicitement.

Vérifié en Phase 15 : à ce moment-là, cet hôte n'exposait qu'un seul volume système (`C:`).
Reconfirmé en Phase 17 : un second disque **physiquement distinct** (`D:`, numéro de disque `1`
contre `0` pour `C:` — vérifié via `Get-Partition`/`Get-PhysicalDisk`, pas seulement une seconde
lettre de lecteur sur le même disque) est disponible sur cette machine — **avec l'accord explicite
de l'utilisateur**, ce disque appartenant visiblement à une autre personne (étiquette de volume
"Evelyne G."). Un sous-dossier dédié et isolé, `D:\EduSphere-Backups\`, est utilisé — jamais le
disque entier — pour ne jamais interférer avec son contenu existant.

`scripts/windows/backup-all.ps1` copie désormais automatiquement chaque backup (dump PostgreSQL +
archive de stockage + leurs `.sha256`) vers cette destination après la production locale, et
**revérifie le SHA-256 après copie** (pas seulement une copie du fichier `.sha256` déjà produit —
un nouveau calcul à destination, comparé à celui de la source). La tâche planifiée Windows
`EduSphere-DailyBackup` (Phase 15) exécute ce script sans modification nécessaire — la copie
externe est donc automatiquement incluse dans l'exécution quotidienne suivante.

**Preuve réelle (Phase 17)** : backup produit, copié, SHA-256 identique source/destination
confirmé pour les deux archives ; restauration PostgreSQL **depuis la copie externe** (pas la
copie locale) vers une base de test, comptages identiques à la source sur 7 tables ; restauration
storage **depuis la copie externe** vers un répertoire temporaire, fichiers identiques. Voir
[Phase 17](../phases/PHASE_17_IMPLEMENTATION.md) pour le détail complet et la simulation de perte
totale de la machine principale.

**Ce qui reste vrai malgré cette résolution** : `scripts/backup-all.sh` (portable, pour un futur
hôte Linux de production) accepte la même logique via `EXTERNAL_BACKUP_DIR`, mais **aucun
support externe n'a été identifié ni testé pour un hôte de production réel** — seulement pour
cet hôte de développement précis. Ne pas supposer que ce point reste résolu après un changement
de machine hébergeant EduSphere sans revérifier.

```bash
# Équivalent portable (hôte Linux, EXTERNAL_BACKUP_DIR à définir selon le support réel) :
EXTERNAL_BACKUP_DIR=/mnt/backup-externe scripts/backup-all.sh
```

## Développement vs Production

| | Développement (actuel, depuis Phase 15) | Production (future) |
|---|---|---|
| Persistance | Bind mount hôte (`apps/api/storage/`, Phase 14) | À déterminer — un stockage objet (S3-compatible ou équivalent) serait la solution naturelle grâce à l'abstraction `StorageProvider` déjà en place, mais aucun hébergeur n'est figé à ce stade (cohérent avec la règle Phase 0) |
| Backup | **Automatisé** (`scripts/backup-all.sh` / tâche planifiée Windows `EduSphere-DailyBackup`), quotidien | Planifié de la même façon, sur l'hôte de production retenu |
| Rétention | 7 jours (rotation automatique) | À réévaluer selon le volume réel |
| Intégrité | Comptage de fichiers + listing `tar` + empreinte SHA-256 | Idem |
| Stockage indépendant de la source | **Résolu sur cet hôte** (`D:\EduSphere-Backups`, disque physique distinct) | À établir sur l'hôte de production réel une fois choisi |
| Chiffrement | Aucun | À évaluer selon l'hébergeur retenu |

## Limites actuelles

- Un bind mount local protège contre la recréation de conteneur, pas contre une panne disque ou
  la perte de la machine hôte — désormais mitigé par la copie externe (Phase 17), pas éliminé
  (le disque `D:` reste physiquement dans la même machine/le même boîtier ; il protège contre la
  perte du disque `C:` spécifiquement, pas contre un sinistre affectant la machine entière — vol,
  incendie, dégât des eaux).
- Aucun chiffrement des archives au repos, y compris sur la copie externe.
- La rétention (7 jours) n'a pas encore été observée sur une durée réelle de 7 jours — seul le
  mécanisme de suppression a été vérifié par lecture de code et par un run réel qui n'avait rien
  à supprimer. Aucune rétention n'est appliquée sur la copie externe elle-même (elle s'accumule
  indéfiniment sur `D:\EduSphere-Backups` tant que personne ne la nettoie manuellement).
- La copie externe dépend de la disponibilité continue d'un disque appartenant à une autre
  personne sur cette machine de développement — pas une solution pérenne pour un vrai pilote,
  seulement une démonstration réelle que le mécanisme fonctionne de bout en bout.
