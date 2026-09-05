# PHASE 15 IMPLEMENTATION REPORT

Date : 2026-09-04
Périmètre : scripts de sauvegarde/restauration + documentation + une tâche planifiée Windows.
Aucun code applicatif (`apps/api/app/`, `apps/web`, `apps/mobile`) modifié.

## 1. Objectif

Faire passer la protection des données d'EduSphere de la simple **persistance** (Phase 14 —
bind mount survivant à une recréation de conteneur) à un vrai **backup** : sauvegarde
automatisée et cohérente de PostgreSQL et du stockage fichiers, intégrité vérifiée, restauration
réellement testée, et documentation honnête de ce qui reste non résolu (protection contre la
perte de la machine hôte elle-même).

## 2. État initial

Confirmé avant toute modification :
- Un seul dump PostgreSQL existait dans `backups/` (`edusphere_20260904T002519Z.dump`, daté de
  la Phase 7.3, jamais renouvelé).
- Aucune archive du stockage fichiers n'existait.
- `apps/api/storage/` (bind mount Phase 14) contenait 337 entrées (121 fichiers, 216 dossiers) —
  voir §3.
- Aucun mécanisme de planification n'existait (ni cron, ni tâche Windows).
- `backups/` et `apps/api/storage/` vivent tous deux sur la même machine que PostgreSQL — aucune
  copie indépendante nulle part.

## 3. Inventaire des 337 fichiers

Inspecté avant toute suppression, conformément à la consigne :

- **Répartition** : `report_cards/` (96 fichiers, tous `.pdf`), `students/` (17 fichiers —
  `.jpg` pour les photos, `.pdf` pour les documents, plus des fichiers sans extension), `schools/`
  (8 fichiers — `.png`/`.jpg` pour les logos, `.ini` pour deux d'entre eux).
- **Nature confirmée par les noms de fichiers eux-mêmes**, sans ambiguïté possible :
  `photo_<uuid>_photo.jpg`, `<uuid>_certificate.pdf` — motifs exacts produits par
  `test_students.py`/`test_schools.py` ; `photo_<uuid>_passwd` et `logo_<uuid>_win.ini` —
  noms de fichiers *assainis* provenant précisément des tests de traversée de chemin de
  `test_storage_security.py` (Phase 13 : `../../../../etc/passwd`, `..\..\..\windows\win.ini`),
  confirmant à la fois l'origine test **et** que l'assainissement Phase 13 fonctionne toujours
  correctement.
- **Aucune donnée utilisateur réelle mélangée** : ce projet n'a jamais eu de déploiement pilote
  réel — chaque ligne en base de données a elle aussi été créée par les mêmes suites de tests
  automatisées (`register_school()`/`unique_email()`, voir `tests/conftest.py`), donc aucun
  fichier ne pouvait légitimement appartenir à un utilisateur réel.
- **Action** : nettoyage confirmé sûr et effectué — `apps/api/storage/` vidé (répertoire
  lui-même conservé, c'est la cible du bind mount). Un nouveau run complet de la suite de tests
  (§12) a depuis repeuplé le répertoire avec de nouveaux fichiers de test (118 au moment de la
  rédaction) — résidu attendu et inoffensif, cohérent avec la convention déjà établie dans ce
  projet de ne jamais réinitialiser les données de test entre les runs.

## 4. Backup PostgreSQL

- **Méthode/format** : inchangé — `pg_dump -Fc` (déjà en place depuis la Phase 7.3).
- **Emplacement** : `backups/edusphere_<horodatage>.dump`.
- **Fréquence** : quotidienne (voir §7, automatisation réelle).
- **Rétention** : 7 jours par défaut, rotation automatique (voir `scripts/backup-all.sh`).
- **Intégrité** : `pg_restore --list` (déjà en place) + **nouveau** : empreinte SHA-256 écrite à
  côté de chaque dump (`.sha256`).

## 5. Backup Storage

- **Méthode** (nouveau, `scripts/storage-backup.sh`) : `tar -czf` de `apps/api/storage/` (déjà
  un répertoire hôte depuis la Phase 14 — aucun `docker cp` nécessaire, contrairement au dump
  PostgreSQL).
- **Emplacement** : `backups/storage_<horodatage>.tar.gz`, même répertoire que les dumps.
- **Fréquence** : quotidienne, synchronisée avec le backup PostgreSQL (même exécution de
  `backup-all.sh`/`backup-all.ps1`).
- **Rétention** : 7 jours par défaut, même mécanisme que PostgreSQL.
- **Intégrité** : comparaison du nombre de fichiers source vs nombre d'entrées dans l'archive
  (`tar -tzf`) + empreinte SHA-256.

## 6. Stockage indépendant

**Statut réel, affirmé explicitement plutôt que supposé** : **NON RÉSOLU.**

- Vérifié sur cet hôte : un seul volume système (`C:`) — `Get-PSDrive -PSProvider FileSystem` ne
  renvoie qu'une entrée. Aucun second disque, aucun emplacement réseau disponible dans cet
  environnement pour une copie indépendante.
- `backups/`, `pgdata` et `apps/api/storage/` restent tous les trois sur la même machine.
- Conformément à la consigne (§8 du prompt), l'automatisation locale a été mise en place (§7),
  mais la protection contre la perte totale de l'hôte **n'est pas déclarée résolue**. Une
  procédure exacte de copie vers un support indépendant (clé USB, disque externe, ou stockage
  distant une fois un hébergeur retenu) est documentée dans
  [`docs/database/STORAGE_BACKUP_RESTORE.md`](../database/STORAGE_BACKUP_RESTORE.md).

## 7. Automatisation

Réellement mise en place et vérifiée, pas seulement écrite :

- **Scripts portables** (`scripts/storage-backup.sh`, `scripts/storage-restore-test.sh`,
  `scripts/backup-all.sh`) — bash, destinés à un vrai hôte de déploiement Linux, où une entrée
  `crontab` standard suffit (exemple documenté).
- **Sur cet hôte de développement Windows** : `bash` (lanceur WSL disponible ici) n'a pas accès à
  Docker — contrainte déjà documentée dans les phases précédentes, reconfirmée en Phase 15
  (`bash -c "docker compose ps"` → `the command 'docker' could not be found in this WSL 2
  distro`). `scripts/windows/backup-all.ps1` réimplémente la même logique en PowerShell natif
  (aucune dépendance à bash) et a été **réellement planifiée** :
  ```
  Register-ScheduledTask -TaskName "EduSphere-DailyBackup" ...  (quotidien, 2h00)
  ```
  Preuve d'exécution réelle, pas seulement d'enregistrement :
  - `Start-ScheduledTask` déclenché manuellement → `LastTaskResult = 0` (succès).
  - Nouveaux fichiers `edusphere_20260904T172747Z.dump` et `storage_20260904T172747Z.tar.gz`
    apparus dans `backups/` à l'heure exacte du déclenchement (17:27:47-49 UTC+local) — preuve
    que c'est bien le Planificateur de tâches Windows qui a exécuté le script, pas seulement une
    exécution manuelle de ma part.

## 8. Restore PostgreSQL

Test réel exécuté (pas supposé) :
1. `docker cp` du dump frais vers le conteneur `db`.
2. `CREATE DATABASE edusphere_restore_test` (jamais la base source).
3. `pg_restore` du dump dans cette base dédiée → succès (code de sortie 0).
4. Comparaison des comptages (`scripts/db-verify-counts.sql`) entre `edusphere_restore_test` et
   la base source `edusphere` — **résultat réel, identique sur les 7 tables** :
   `assessment_results=765, attendance_records=717, organizations=3292, report_cards=352,
   schools=3298, students=2344, users=3807`.
5. Nettoyage : `DROP DATABASE edusphere_restore_test` — base source jamais touchée.

## 9. Restore Storage

Test réel exécuté de bout en bout, pas seulement une extraction vers un répertoire temporaire
comme le limitait la documentation avant cette phase :
1. Fichier de test écrit via `StorageProvider.upload()` (pas une écriture disque brute) :
   `phase15_backup_test/probe.txt`.
2. Capturé par un run réel de `backup-all.ps1` → `storage_20260904T172507Z.tar.gz` (1 fichier).
3. `scripts/storage-restore-test.sh backups/storage_20260904T172507Z.tar.gz` exécuté avec succès
   via `bash` (aucune dépendance à Docker pour cette opération, contrairement au restore DB —
   confirmé fonctionnel sur cet hôte) :
   ```
   RESTORE SUCCESS: ... extrait dans /tmp/edusphere_storage_restore_test.OPXO8o — 1 fichiers.
   ```
   `apps/api/storage/` jamais touché ; répertoire temporaire supprimé automatiquement.
4. Nettoyage : fichier de test supprimé via `StorageProvider.delete()`.

## 10. Disaster Recovery

Simulation réelle (pas seulement documentée) de la perte des deux sources de données, sans
détruire l'environnement courant :
- **PostgreSQL** : restauré vers une base temporaire dédiée (§8) — équivalent fonctionnel de
  "reconstituer la base à partir d'un backup" sans toucher à la base réelle.
- **Stockage fichiers** : restauré vers un répertoire temporaire dédié (§9) — équivalent
  fonctionnel de "reconstituer le stockage à partir d'un backup" sans toucher au répertoire réel.
- **Non simulé** : la perte de la machine hôte elle-même (scénario le plus grave identifié en
  Phase 15 Discovery) reste, par nature, non testable sans détruire réellement l'environnement —
  ce que la consigne interdit explicitement. Son irrésolution reste donc affirmée (§6), pas
  démontrée comme corrigée.
- **Durée observée** (pas un chronométrage de production, juste ce qui a été mesuré ici) :
  backup combiné DB+storage complet en quelques secondes sur ce volume de données actuel (dump
  ~3,9 Mo) ; restauration PostgreSQL vers la base de test également de l'ordre de quelques
  secondes. Ces durées ne préjugent pas de ce qu'elles seraient sur un volume de données réel de
  pilote, plus important.

## 11. Sécurité

- **Permissions** : `backups/` vérifié via `Get-Acl` — seuls `NT AUTHORITY\SYSTEM`,
  `BUILTIN\Administrators` et l'utilisateur courant ont un accès (`FullControl`) ; aucun accès
  élargi (`Everyone`/`Users`) trouvé.
- **Secrets** : aucun script n'écrit `.env`, un secret JWT, un mot de passe SMTP ou un token dans
  une archive ou un log — les dumps PostgreSQL contiennent des mots de passe utilisateurs
  **hachés** uniquement (déjà vérifié en Phase 7.3, inchangé). Les identifiants PostgreSQL sont
  référencés via les variables d'environnement déjà présentes dans le conteneur, jamais en argument
  de ligne de commande visible (`ps`) ni écrits en dur.
- **Chiffrement** : **aucun**, confirmé absent, non ajouté dans cette phase (conforme à la
  consigne de ne pas installer une solution complexe uniquement pour cette phase) — documenté
  comme limite dans les deux documents de backup.
- **Échec de backup non masqué** : `scripts/storage-backup.sh`, `scripts/backup-all.sh`, et
  `scripts/windows/backup-all.ps1` retournent tous un code de sortie non nul et un message
  explicite sur `stderr`/console à chaque étape pouvant échouer (tar, vérification d'intégrité,
  pg_dump, pg_restore, copie) — vérifié par lecture de code, chaque chemin d'erreur se termine
  par un `exit 1`/`Fail`, jamais un `exit 0` implicite en cas d'échec.

## 12. Tests

Tous exécutés réellement :

```
docker compose config --quiet   → valide (code de sortie 0)
ruff check .                     → All checks passed!
mypy app                         → Success: no issues found in 70 source files
pytest -q                        → 170 passed, 2 warnings in 124.12s (0:02:04)
alembic current                  → 0008 (head), inchangé
docker compose ps                → 4/4 services actifs ; db/redis "healthy", jamais recréés
                                    pendant cette phase (ancienneté inchangée)
GET /api/v1/health                → {"status":"ok"}
```

170 = identique à la fin de la Phase 14 — zéro régression, aucun code applicatif n'ayant été
modifié cette phase.

Backup DB : réel, réussi (§4/§7). Backup files : réel, réussi (§5/§7). Restore DB : réel, réussi
(§8). Restore files : réel, réussi (§9). Recovery complet : simulation réelle des deux volets
DB+storage vers un environnement temporaire (§10), perte de l'hôte lui-même non simulable sans
destruction (non tentée, conformément à la consigne).

## 13. Fichiers modifiés

Créés :
- `scripts/storage-backup.sh`
- `scripts/storage-restore-test.sh`
- `scripts/backup-all.sh`
- `scripts/windows/backup-all.ps1`

Modifiés :
- `docs/database/BACKUP_RESTORE.md` (automatisation, table Scripts, section Limites)
- `docs/database/STORAGE_BACKUP_RESTORE.md` (automatisation, restore réellement testé, section
  "Stockage indépendant — NON RÉSOLU", correction d'un exemple PowerShell `-AsUTC` non testé et
  en réalité invalide sous Windows PowerShell 5.1 — découvert et corrigé en cours de phase)

Hors dépôt Git (aucun dépôt n'existe, rien à committer) : une tâche planifiée Windows
`EduSphere-DailyBackup` a été enregistrée sur cette machine (`Register-ScheduledTask`) — un
changement d'état de l'hôte, pas un fichier du dépôt, documenté ici par transparence.

Aucun fichier `apps/api/app/`, `apps/web`, `apps/mobile`, `docker-compose.yml`, `Dockerfile`,
`.env`/`.env.example` modifié. Nettoyage : contenu de `apps/api/storage/` (337 entrées de test
confirmées, voir §3) — le répertoire lui-même conservé.

## 14. Migrations

Confirmé : **aucune migration créée**. `alembic current` reste `0008 (head)` avant et après
cette phase (§12).

## 15. Dépendances

Confirmé : **aucune nouvelle dépendance**. Tous les outils utilisés (`pg_dump`, `pg_restore`,
`tar`, `sha256sum`/`Get-FileHash`, le Planificateur de tâches Windows) sont déjà présents dans
l'environnement (image `postgres:16-alpine`, Windows 10+, bibliothèque standard). Aucun package
Python, npm, ni image Docker ajoutée.

## 16. Hors scope

Explicitement non traité, conformément à la consigne :

- **Git / CI** : toujours non initialisée — non touchée.
- **Observabilité** : toujours absente (`/health` toujours un stub) — non installée.
- **SMTP production** : toujours `EMAIL_PROVIDER=local` — non modifié, non activé.
- **Findings MEDIUM Phase 13** (RLS `organizations`, `IntegrityError`, rate limiting
  `register`/`refresh`/`verify-by-code`, détection de réutilisation de refresh token, garde-fou
  de correction de notes après publication) — inchangés.
- **Stockage cloud** (S3/GCS/Azure) — non implémenté ; `StorageProvider` le permettrait
  proprement plus tard, mais aucun hébergeur n'est figé à ce stade (règle Phase 0).
- **Copie hors machine réellement automatisée** — seule la procédure manuelle est documentée
  (§6) ; aucun support indépendant n'étant disponible dans cet environnement, rien n'a pu être
  automatisé au-delà de ce qui est réellement réalisable ici.

## 17. Risques résiduels

- **Le plus important** : la protection contre la perte de la machine hôte reste non résolue —
  affirmé explicitement, pas dissimulé (§6). C'est la limite la plus significative de cette
  phase, à traiter avant tout pilote réel avec des données qui comptent.
- Le chiffrement des archives au repos reste absent.
- Le volume de données réel d'un pilote effectif sera plus important que les ~4 Mo actuels — les
  durées observées (§10) ne sont pas représentatives à cette échelle.
- La tâche planifiée Windows n'existe que sur cette machine de développement précise — elle ne
  se transfère pas automatiquement vers un futur hôte de production (Linux, probablement) ; les
  scripts bash portables (`backup-all.sh`) sont prévus pour cette transition, mais leur
  planification via `crontab` sur un vrai hôte n'a pas pu être testée ici (aucun hôte Linux
  disponible dans cet environnement).
- La rétention 7 jours n'a pas encore été observée en conditions réelles sur une pleine semaine.

## 18. Statut

GO WITH NOTES

Le mécanisme de backup+restore est réel, automatisé, testé de bout en bout pour PostgreSQL et le
stockage fichiers, avec intégrité vérifiée et échecs correctement signalés. La réserve porte sur
un point explicitement non résolu et assumé comme tel : aucune copie des sauvegardes n'existe en
dehors de cette machine — la perte de l'hôte lui-même resterait catastrophique malgré cette
phase. Ce n'est pas un oubli mais un constat honnête, documenté avec une procédure claire pour
le résoudre avant un pilote réel.
