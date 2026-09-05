# PHASE 17 IMPLEMENTATION REPORT

Date : 2026-09-04
Périmètre : backup externe, restauration depuis l'externe, documentation de reprise après
sinistre. Aucun changement `apps/api/app/`, `apps/web`, `apps/mobile`, `docker-compose.yml`,
aucune migration.

## 1. Discovery

- **Stockage externe** : un second disque physique a été trouvé sur cet hôte (`D:`, numéro de
  disque `1`, distinct du disque `0` hébergeant `C:`/Docker — confirmé via
  `Get-Partition`/`Get-PhysicalDisk`, pas seulement une seconde lettre de lecteur). Étiqueté
  "Evelyne G." — appartenance visiblement personnelle à une autre personne. **Utilisation
  soumise à confirmation explicite de l'utilisateur avant toute écriture** (voir ci-dessous) —
  accordée, avec l'exigence d'un sous-dossier dédié et isolé (`D:\EduSphere-Backups\`), jamais le
  disque entier.
- **SMTP externe** : `SMTP_HOST`/`SMTP_USERNAME`/`SMTP_PASSWORD` tous vides dans `.env` actif
  (revérifié réellement, longueurs extraites = 0 sur les trois). **Aucun compte SMTP réel,
  aucune boîte de destination disponible.**

Décision prise avant toute modification : demander confirmation explicite à l'utilisateur avant
d'écrire quoi que ce soit sur un disque appartenant visiblement à un tiers — obtenue
("Oui, utiliser D:\ dans un sous-dossier dédié") avant de commencer le travail décrit ci-dessous.

## 2. Backup externe

- **Méthode** : `scripts/windows/backup-all.ps1` étendu avec un paramètre
  `-ExternalDestination` (défaut `D:\EduSphere-Backups`) — copie le dump PostgreSQL et l'archive
  de stockage (+ leurs `.sha256`) juste après leur production locale, puis **recalcule** le
  SHA-256 du fichier copié et le compare à celui de la source (pas une simple copie du `.sha256`
  déjà produit). `scripts/backup-all.sh` (portable) reçoit l'équivalent via une variable
  `EXTERNAL_BACKUP_DIR`, documenté mais non exécutable sur cet hôte (bash sans accès Docker,
  contrainte déjà connue).
- **Destination** : `D:\EduSphere-Backups\` — disque physique distinct confirmé.
- **Automatisation** : la tâche planifiée Windows existante (`EduSphere-DailyBackup`, Phase 15)
  référence le fichier de script, pas son contenu — elle applique donc automatiquement la
  nouvelle logique de copie externe à sa prochaine exécution planifiée, sans ré-enregistrement
  nécessaire (vérifié : `(Get-ScheduledTask ...).Actions` pointe vers le chemin du script).
- **Preuve réelle** : `powershell -File scripts\windows\backup-all.ps1` exécuté réellement →
  ```
  Backup DB OK: backups\edusphere_20260904T183949Z.dump (4 270,2 KB)
  Backup storage OK: backups\storage_20260904T183949Z.tar.gz (208,4 KB) - 85 fichiers
  Copie verifiee (SHA-256 identique) : D:\EduSphere-Backups\edusphere_20260904T183949Z.dump
  Copie verifiee (SHA-256 identique) : D:\EduSphere-Backups\storage_20260904T183949Z.tar.gz
  === Backup combine + copie externe termines avec succes ===
  EXIT CODE: 0
  ```
  Fichiers réellement présents à destination, vérifiés indépendamment du script
  (`Get-ChildItem D:\EduSphere-Backups`) : les 4 fichiers attendus, tailles cohérentes.

## 3. Vérification intégrité

- SHA-256 recalculé après copie et comparé à la source pour les deux archives — identique dans
  les deux cas (voir §2, preuve réelle).
- Tailles vérifiées : `4 372 699` octets (dump, source) = taille du fichier à destination
  (`Get-ChildItem` indépendant, §2).
- Existence réelle confirmée : 4 fichiers listés à `D:\EduSphere-Backups\` par une commande
  séparée de celle du script (pas seulement le message de succès du script lui-même).

## 4. Restore depuis l'externe

**PostgreSQL** (depuis `D:\EduSphere-Backups\edusphere_20260904T183949Z.dump`, pas la copie
locale) :
1. `docker cp` du dump externe vers le conteneur `db`.
2. `CREATE DATABASE edusphere_dr_test` (jamais la base source).
3. `pg_restore` → succès, code de sortie 0.
4. Comptages comparés à la base source sur 7 tables — **identiques** :
   `assessment_results=843, attendance_records=791, organizations=3644, report_cards=412,
   schools=3650, students=2588, users=4207`.
5. `DROP DATABASE edusphere_dr_test` — nettoyage, base source jamais touchée.

**Storage** (depuis `D:\EduSphere-Backups\storage_20260904T183949Z.tar.gz`) :
1. `bash scripts/storage-restore-test.sh /mnt/d/EduSphere-Backups/storage_....tar.gz` (chemin WSL
   correct pour `D:\`, découvert après un premier essai avec un chemin `D:/...` qui échoue —
   WSL monte les lecteurs Windows sous `/mnt/`).
2. Résultat réel : `RESTORE SUCCESS ... 85 fichiers` — extrait dans un répertoire temporaire,
   jamais `apps/api/storage/`, nettoyé automatiquement en fin de script.

## 5. SMTP réel

**Configuration** : inchangée — `SmtpEmailProvider` (Phase 9/16) reste l'abstraction disponible,
aucune modification de code cette phase (conforme à la consigne : ne rien modifier tant qu'aucun
identifiant réel n'est disponible).

**Test** : aucun — `SMTP_HOST`/`SMTP_USERNAME`/`SMTP_PASSWORD` confirmés vides dans `.env` actif
(longueurs extraites = 0, sans jamais afficher les valeurs).

**Réception réelle** : **REAL EXTERNAL SMTP DELIVERY NOT VERIFIED.** Documenté dans
`docs/deployment/DISASTER_RECOVERY.md` (scénario 6) et `docs/deployment/PRODUCTION_CONFIGURATION.md`
— variables à renseigner, procédure de test à exécuter dès qu'un compte réel sera disponible,
résultat attendu.

## 6. Disaster Recovery

Scénario "machine principale perdue" simulé réellement, sans jamais toucher à l'environnement
courant :

1. Conteneur PostgreSQL **entièrement indépendant** démarré via `docker run` (pas
   `docker compose`, aucun lien avec la pile existante), `POSTGRES_USER=edusphere` pour recréer
   le rôle bootstrap de l'image officielle.
2. **Découverte réelle en cours de test** : une première tentative de restauration a échoué (71
   erreurs `pg_restore`, rôle `edusphere`/`edusphere_app` inexistants sur une instance
   Postgres vraiment vierge — `pg_dump` ne capture pas les rôles, objets du cluster, pas de la
   base). Les DONNÉES elles-mêmes s'étaient correctement chargées malgré ces erreurs (vérifié :
   `students=2588` déjà correct après la première tentative) mais la restauration n'était pas
   propre.
3. Rôle `edusphere_app` recréé manuellement avec l'instruction SQL exacte de la migration 0002
   (`CREATE ROLE ... ALTER ROLE ... GRANT ...`).
4. Nouvelle tentative : `pg_restore` **sans aucune erreur**, code de sortie 0.
5. Comptages vérifiés identiques à la source sur 4 tables représentatives.
6. RLS vérifiée active et forcée sur les tables restaurées
   (`relrowsecurity=t, relforcerowsecurity=t` sur `schools`/`students`/`user_roles`).
7. Archive de stockage externe extraite séparément (§4) — 85 fichiers.
8. Conteneur temporaire supprimé (`docker rm -f edusphere-dr-simulation`) — aucune trace laissée,
   reconfirmé par `docker ps -a`.
9. **Pile réelle jamais interrompue** — `GET /health`/`GET /ready` de la pile en cours
   d'exécution revérifiés `200` immédiatement après la simulation, `docker compose ps` montrant
   les 4 services `Up`/`(healthy)` sans discontinuité.

**Non démontré, affirmé explicitement** : faire pointer une véritable instance API EduSphere
(nouvelle pile `docker-compose`) vers ces ressources reconstituées pour observer son propre
`/health`/`/ready` passer au vert — nécessiterait de dupliquer toute l'architecture applicative,
hors périmètre explicite de cette phase. Ce qui EST démontré : les données (base + fichiers) sont
intégralement reconstituables à partir des seules copies externes, dans un environnement
totalement indépendant — c'est la question posée par cette phase.

Détail complet dans [`docs/deployment/DISASTER_RECOVERY.md`](../deployment/DISASTER_RECOVERY.md)
(nouveau document, 6 scénarios).

## 7. Documentation

- `docs/database/BACKUP_RESTORE.md` — section "Copie externe (Phase 17)", limites mises à jour,
  découverte du rôle `edusphere_app` documentée.
- `docs/database/STORAGE_BACKUP_RESTORE.md` — "Stockage indépendant" passé de NON RÉSOLU à
  **RÉSOLU SUR CET HÔTE** (distinction explicite : pas résolu par principe pour un futur hôte de
  production).
- `docs/deployment/PRODUCTION_CONFIGURATION.md` — case "destination externe" toujours **non
  cochée** pour la production (aucun hôte de production choisi), avec note claire que le
  mécanisme est prouvé sur cet hôte de développement.
- `docs/deployment/DISASTER_RECOVERY.md` (nouveau) — 6 scénarios, ordre exact des opérations,
  distinction PROUVÉ RÉELLEMENT / CONFIGURÉ MAIS NON TESTÉ / DOCUMENTÉ MAIS NON DISPONIBLE pour
  chacun.

## 8. Sécurité

- Aucun secret hardcodé dans les scripts modifiés — confirmé par extraction réelle des valeurs de
  `POSTGRES_PASSWORD`/`APP_DB_PASSWORD` (jamais affichées) et recherche dans tous les fichiers
  `.ps1`/`.sh` sous `scripts/` : aucune correspondance.
- `.env` jamais copié vers `D:\EduSphere-Backups\` — confirmé (`Test-Path` → `False`), et le
  contenu du dossier ne comprend que les 4 fichiers de backup attendus.
- Mot de passe SMTP jamais affiché (aucun test SMTP réel n'a été tenté, donc aucune occasion de
  l'exposer).
- **Finding réel, documenté honnêtement plutôt que dissimulé** : les permissions NTFS de
  `D:\EduSphere-Backups\` (héritées du disque tiers) sont plus larges que celles de `backups/`
  local — `AUTORITE NT\Utilisateurs authentifiés: Modify` et `BUILTIN\Utilisateurs:
  ReadAndExecute`, contre uniquement SYSTEM/Administrateurs/utilisateur courant en local. Non
  modifié dans cette phase (resserrer les ACL d'un dossier sur le disque d'une autre personne
  dépasse le périmètre "backup externe" de cette phase) — à corriger avant un pilote réel si ce
  disque devait rester la destination (peu probable, voir limitations).

## 9. Tests

```
ruff check .                    → All checks passed!
mypy app                         → Success: no issues found in 72 source files
pytest -q                        → 183 passed, 2 warnings in 182.20s (identique à Phase 16 — aucun code applicatif modifié)
docker compose config --quiet    → valide
alembic current                   → 0008 (head)
alembic heads                      → 0008 (head)
docker compose ps                   → 4/4 services actifs, api/db/redis (healthy)
GET /api/v1/health                   → 200 {"status":"ok"}
GET /api/v1/ready                     → 200 {"status":"ready","checks":{"database":"ok","redis":"ok","storage":"ok"}}
```

## 10. Fichiers modifiés

Modifiés : `scripts/windows/backup-all.ps1` (copie externe + vérification), `scripts/backup-all.sh`
(équivalent portable), `docs/database/BACKUP_RESTORE.md`, `docs/database/STORAGE_BACKUP_RESTORE.md`,
`docs/deployment/PRODUCTION_CONFIGURATION.md`.

Créés : `docs/deployment/DISASTER_RECOVERY.md`.

État de l'hôte (hors dépôt, pas un fichier Git puisqu'aucun dépôt n'existe) : 4 fichiers de
backup réels dans `D:\EduSphere-Backups\` (dump + storage + leurs `.sha256`).

Aucun fichier `apps/api/app/`, `apps/web`, `apps/mobile`, `docker-compose.yml`, `.env`,
`.env.example` modifié.

## 11. Migration

**AUCUNE.** `alembic current` = `alembic heads` = `0008 (head)`, inchangé avant/après (§9).

## 12. Dépendances

**AUCUNE nouvelle.** `Get-FileHash`/`sha256sum`, `tar`, `docker` : tous déjà présents et déjà
utilisés depuis les Phases 14-16.

## 13. Limitations

- SMTP externe réel toujours non vérifié — dépendance opérationnelle (obtenir un compte),
  documentée, non résolue dans cette phase (aucune ressource disponible).
- La résolution du stockage externe est **spécifique à cette machine de développement** — un
  disque appartenant à une autre personne, utilisé avec son accord implicite via l'utilisateur du
  projet, pas une solution pérenne. Un vrai hôte de production nécessitera sa propre destination
  externe, à établir et tester séparément.
- Permissions NTFS de la destination externe plus larges que souhaitable (§8) — non corrigées,
  peu pertinent vu la nature temporaire/exceptionnelle de cette destination.
- Aucune rétention automatique sur la copie externe (s'accumule indéfiniment).
- La bascule complète d'une instance applicative vers les ressources reconstituées après sinistre
  n'a pas été démontrée (§6) — seule la récupération des données l'a été.

## 14. Risques résiduels

- Le disque `D:` reste physiquement dans la même machine que `C:` — protège contre la perte du
  disque système spécifiquement, pas contre un sinistre affectant la machine entière (vol,
  incendie, dégât des eaux). Une vraie indépendance géographique reste à construire pour un
  pilote réel (hébergeur cloud ou site distant, aucun choisi à ce stade).
- Aucun chiffrement des archives, ni localement ni sur la copie externe.
- Dépendance à la disponibilité continue d'un disque appartenant à un tiers sur cette machine de
  développement — peut disparaître (déconnexion, retrait) sans préavis pour ce projet.

## 15. Verdict

GO WITH NOTES

P1 (backup externe) : **GO** — destination externe réelle utilisée, copie automatique
opérationnelle et vérifiée (SHA-256), restauration DB+storage depuis l'externe réellement
testée, simulation de perte de machine réussie dans un environnement totalement indépendant.
P2 (SMTP externe) : **non résolu**, comme anticipé — aucune ressource SMTP réelle disponible dans
cet environnement, documenté explicitement (`REAL EXTERNAL SMTP DELIVERY NOT VERIFIED`), aucun
code modifié en son absence. Conformément à la règle de décision de cette phase (§15 de la
consigne : "GO WITH NOTES si... SMTP externe non disponible... mais que tout le reste reste sain
et documenté"), le verdict global est GO WITH NOTES.
