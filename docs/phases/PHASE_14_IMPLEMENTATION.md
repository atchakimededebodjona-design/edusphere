# PHASE 14 IMPLEMENTATION REPORT

Date : 2026-09-04
Périmètre : infrastructure de déploiement (`docker-compose.yml`) + documentation + un test
backend complémentaire. Aucune logique métier applicative modifiée.

## 1. Objectif

Corriger les deux problèmes de durabilité de déploiement identifiés par l'audit réel de la
Phase 14 Discovery : (A) le service `api` n'a aucun stockage de fichiers persistant, (B) la
configuration email active (`EMAIL_PROVIDER=local`) ne délivre jamais réellement un email.
Rendre les deux vérifiables et documentés, sans transformer la phase en refonte d'infrastructure.

## 2. Problème initial

### Storage

`docker inspect edusphere-api-1` (avant cette phase) renvoyait `Mounts=[]` — confirmé à
nouveau en tout début de cette implémentation avant toute modification. `LocalStorageProvider`
(`apps/api/app/core/storage.py`) écrit sous `STORAGE_LOCAL_PATH=./storage`, résolu par le code
en `/app/storage` (WORKDIR `/app`, voir `Dockerfile`) — un chemin entièrement interne à la
couche writable du conteneur. Photos élèves, documents, logos d'école et PDF de bulletins y
vivaient sans aucune protection contre une recréation de conteneur.

Point notable découvert en relisant le dépôt avant de modifier quoi que ce soit :
`apps/api/.gitignore` contenait déjà `apps/api/storage/`, et `apps/api/.dockerignore` excluait
déjà `storage` du contexte de build — le projet anticipait ce bind mount depuis le début, mais
ne l'avait jamais réellement câblé dans `docker-compose.yml`.

### Email

`.env` (actif) : `EMAIL_PROVIDER=local`. `LocalEmailProvider` (`apps/api/app/core/email.py`)
écrit chaque email en fichier texte sous `EMAIL_LOCAL_PATH` — confirmé en relisant le fichier :
aucune ligne de ce provider n'établit de connexion réseau. `SmtpEmailProvider` existe déjà
(Phase 9, `smtplib` de la bibliothèque standard, aucune dépendance externe) mais n'a jamais été
activé — toutes les variables `SMTP_*` sont vides dans `.env`/`.env.example`.

## 3. Solution Storage

- **Chemin applicatif** : inchangé — `STORAGE_LOCAL_PATH=./storage` (aucune variable modifiée).
- **Volume/mount** : bind mount ajouté dans `docker-compose.yml`, service `api` :
  ```yaml
  volumes:
    - ./apps/api/storage:/app/storage
  ```
  Choix d'un bind mount hôte (plutôt qu'un volume Docker nommé) pour cohérence avec le pattern
  déjà établi pour les sauvegardes PostgreSQL (`backups/`, répertoire hôte directement
  inspectable) et parce que `.gitignore`/`.dockerignore` anticipaient déjà exactement ce chemin.
- **Configuration** : aucune variable d'environnement nouvelle — `StorageProvider` reste
  l'unique abstraction utilisée par les modules métier, aucun contournement introduit.
- **Comportement après recréation** : démontré en §4, pas seulement supposé.

## 4. Test de persistance

Exécuté réellement, dans cet ordre, sans toucher aux volumes `pgdata`/`redisdata` :

1. `docker compose config --quiet` → configuration valide.
2. `docker compose up -d --force-recreate api` → premier recréation pour appliquer le nouveau
   mount ; `docker inspect edusphere-api-1` confirme
   `{"Type":"bind","Source":".../apps/api/storage","Destination":"/app/storage","RW":true}`.
3. Fichier de test créé **via l'abstraction applicative réelle**, pas une écriture disque brute :
   ```
   storage.upload('phase14_persistence_test/probe.txt', b'phase14-durability-probe')
   storage.download(...) → b'phase14-durability-probe'  (lu immédiatement après écriture)
   ```
   Confirmé également visible côté hôte : `apps\api\storage\phase14_persistence_test\probe.txt`.
4. `docker compose up -d --force-recreate api` → **second** recréation, celle qui aurait
   auparavant effacé le fichier.
5. Après recréation : `storage.download('phase14_persistence_test/probe.txt')` →
   `b'phase14-durability-probe'` — **identique**, lu par un tout nouveau conteneur.
6. Nettoyage : `storage.delete('phase14_persistence_test/probe.txt')` (via l'application, pas un
   `rm` manuel) → confirmé absent (`Test-Path` → `False`) ; répertoire de test vide supprimé.
   Aucun volume supprimé, `pgdata`/`redisdata` jamais touchés (confirmé par leur ancienneté
   inchangée dans `docker compose ps` tout au long de cette phase : `db`/`redis` toujours
   "20h"/"3h" d'exécution alors que `api` a été recréé plusieurs fois).

**Résultat réel : la persistance est démontrée, pas supposée.**

Effet de bord découvert pendant cette démonstration (documenté par honnêteté, pas dissimulé) :
un premier cycle `--force-recreate` sans `--build` a rechargé l'**image** telle que construite
avant les corrections de sécurité de la Phase 13 (celles-ci n'avaient été copiées que dans le
conteneur en cours d'exécution via `docker cp`, jamais reconstruites dans l'image). La suite de
tests est alors brièvement repassée à 146 (au lieu de 167). Corrigé par un rebuild réel de
l'image (`docker compose build api`) avant de poursuivre — voir §9 pour la preuve du retour à un
état complet et cohérent. Aucune donnée de stockage n'a été affectée par cet épisode (le bind
mount survit indépendamment du contenu de l'image) ; seul le code applicatif chargé en mémoire
était temporairement obsolète.

## 5. Backup Storage

Documenté dans un nouveau fichier dédié,
[`docs/database/STORAGE_BACKUP_RESTORE.md`](../database/STORAGE_BACKUP_RESTORE.md), avec
référence croisée ajoutée dans `docs/database/BACKUP_RESTORE.md` :

- **Emplacement** : `apps/api/storage/` (hôte), bind-monté dans le conteneur `api`.
- **Méthode de backup** : `tar -czf backups/storage_<horodatage>.tar.gz -C apps/api storage` —
  manuelle, cohérente avec le même niveau de simplicité déjà retenu pour PostgreSQL en
  Phase 7.3 ; aucun orchestrateur construit.
- **Méthode de restore** : extraction vers un répertoire temporaire puis vérification
  (`diff -rq`) avant toute promotion manuelle — pas de restauration destructive testée dans
  cette phase (conforme à la consigne).
- **Relation avec le backup PostgreSQL** : explicitement documentée comme **distincte** — le
  dump PostgreSQL ne contient aucun fichier, et les deux doivent être sauvegardés/restaurés
  ensemble (même horodatage) pour éviter une désynchronisation entre les chemins référencés en
  base (`photo_path`, `file_path`, `logo_path`, `pdf_path`) et les fichiers réellement présents.
- **Limite explicitement affirmée** (règle de vérité) : un bind mount protège contre la
  recréation de conteneur, **pas** contre une panne disque, la perte de la machine hôte, ou une
  suppression accidentelle — jamais présenté comme un backup en soi.

## 6. Email Configuration

Documenté dans [`docs/deployment/PRODUCTION_CONFIGURATION.md`](../deployment/PRODUCTION_CONFIGURATION.md)
(nouveau document) :

- **Provider local** (actuel, `EMAIL_PROVIDER=local`) : reste la valeur correcte pour le
  développement et les tests automatisés — non modifié.
- **Provider production disponible** : `SmtpEmailProvider`, déjà implémenté (Phase 9,
  `smtplib` standard, zéro nouvelle dépendance) mais jamais activé en pratique.
- **Variables** : `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
  `SMTP_FROM_ADDRESS`, `SMTP_USE_TLS` — toutes déjà présentes dans `.env.example` (vides), aucune
  variable inventée.
- **Sélection** : `get_email_provider(settings.email_provider, ...)` — inchangée, aucune
  modification de code nécessaire pour activer SMTP en production ; seule la configuration
  change.
- **Comportement** : documenté explicitement en tableau comparatif LOCAL vs PRODUCTION dans le
  document, avec l'avertissement explicite de ne jamais dire "les emails sont configurés" tant
  que `EMAIL_PROVIDER=local`.

## 7. Validation Email

- **Testé localement (réellement exécuté)** : `LocalEmailProvider` — suite existante
  (`test_local_email_provider_writes_a_file_with_expected_content`, tests d'intégration
  forgot-password/invitation/notification bulletin) — tous verts, voir §9.
- **Testé au niveau configuration (nouveau, ajouté cette phase)** :
  `test_get_email_provider_local_returns_local_provider`,
  `test_get_email_provider_smtp_returns_smtp_provider` (instanciation de `SmtpEmailProvider`
  avec des valeurs manifestement factices via `monkeypatch`, jamais un secret réel),
  `test_get_email_provider_rejects_unknown_provider` — les trois exécutés réellement, tous
  verts.
- **Livraison réelle externe** : **NON TESTÉE**. Aucun serveur SMTP réel n'est disponible dans
  cet environnement. Ceci est affirmé explicitement, conformément à la règle de vérité de cette
  phase — ne jamais prétendre qu'un email a quitté cet environnement alors qu'aucun fournisseur
  réel n'y est configuré.

## 8. Sécurité

- Aucun secret committé : `docker-compose.yml` ne contient que le chemin du bind mount, aucune
  valeur sensible. `.env` et `.env.example` n'ont pas été modifiés dans cette phase.
- `docs/deployment/PRODUCTION_CONFIGURATION.md` et `docs/database/STORAGE_BACKUP_RESTORE.md` ne
  contiennent que des noms de variables et des placeholders explicitement factices — vérifié par
  relecture complète des deux documents avant publication.
- Le nouveau test `test_get_email_provider_smtp_returns_smtp_provider` utilise
  `smtp.example-test.invalid` / `test-user-placeholder` / `test-password-placeholder` —
  volontairement non fonctionnels, jamais un identifiant réel.
- Aucun secret ni contenu d'email loggé — inchangé par rapport à l'état déjà audité en
  Phase 13/14 Discovery (le seul logging existant, `core/email.py`, log l'adresse destinataire
  en cas d'échec, finding LOW déjà connu, non aggravé ni traité ici).

## 9. Tests

Tous exécutés réellement dans le conteneur `api`, **après reconstruction complète de l'image**
(voir l'incident documenté en §4) :

```
ruff check .          → All checks passed!
mypy app               → Success: no issues found in 70 source files
pytest -q              → 170 passed, 2 warnings in 126.08s (0:02:06)
```

170 = 167 (état après Phase 13) + 3 nouveaux tests de sélection de provider email (§7). Zéro
échec, zéro régression.

```
docker compose config --quiet   → valide (code de sortie 0)
alembic current                  → 0008 (head), inchangé
docker compose ps                → 4/4 services actifs ; db/redis "healthy", jamais recréés
                                    pendant cette phase (ancienneté inchangée) ; api rebuild et
                                    recréé intentionnellement (objet de cette phase) ; web
                                    jamais touché
```

Tests storage : voir §4 (persistance démontrée par un scénario réel d'écriture →
recréation → lecture, pas par simple présence du volume).

Tests email : voir §7.

Fonctionnalités listées en consigne (§20), toutes couvertes par la suite existante et
re-vérifiées vertes dans ce run : upload photo étudiant, upload document étudiant, upload logo
école, génération PDF bulletin, lecture des fichiers (`test_students.py`, `test_schools.py`,
`test_report_cards*.py`), LocalEmailProvider, forgot-password, création utilisateur/invitation,
notification bulletin (`test_email.py`, `test_forgot_password_rate_limit.py`,
`test_report_cards_notifications.py`).

## 10. Fichiers modifiés

Modifiés :
- `docker-compose.yml` (ajout du bind mount `apps/api` storage)
- `apps/api/tests/test_email.py` (3 tests de sélection de provider ajoutés)
- `docs/database/BACKUP_RESTORE.md` (note de renvoi vers le nouveau document storage)

Créés :
- `docs/database/STORAGE_BACKUP_RESTORE.md`
- `docs/deployment/PRODUCTION_CONFIGURATION.md`

Aucun autre fichier modifié. En particulier : aucun fichier sous `apps/api/app/` (code
applicatif), aucun fichier `apps/web`, aucun fichier `apps/mobile`, `.env`/`.env.example`
non modifiés, `Dockerfile`/`.dockerignore`/`.gitignore` non modifiés (déjà corrects).

## 11. Migrations

Confirmé : **aucune migration créée**. `alembic current` reste `0008 (head)` avant et après
cette phase (revérifié §9).

## 12. Dépendances

Confirmé : **aucune nouvelle dépendance**. `requirements.txt`/`requirements-dev.txt` non
modifiés. `SmtpEmailProvider` utilise exclusivement `smtplib`/`email.message` (bibliothèque
standard), déjà en place depuis la Phase 9.

## 13. Hors scope / dette future

Explicitement non traité dans cette phase, conformément à la consigne :

- **Git / CI** : toujours non initialisée. Prochaine priorité future légitime, non commencée ici.
- **Observabilité** : toujours absente (logs non structurés, `/health` ne vérifie ni DB ni
  Redis, `api`/`web` sans healthcheck Docker). Non traité — un vrai health check aurait été
  naturel à coupler à cette phase mais est resté explicitement hors périmètre par consigne.
- **Findings MEDIUM de sécurité** (Phase 13) : RLS `organizations`, `IntegrityError` sur les
  endpoints identifiés, rate limiting `register`/`refresh`/`verify-by-code`, détection de
  réutilisation de refresh token — inchangés.
- **Garde-fou de correction de notes après publication** (Phase 13/14 Discovery) — inchangé.
- **Stockage cloud** (S3/GCS/Azure) — volontairement non introduit ; le bind mount local suffit
  pour un pilote et évite une dépendance externe non encore nécessaire. `StorageProvider`
  permettrait cette migration proprement plus tard si le besoin est démontré.
- **Obtention réelle d'un compte SMTP** pour le pilote — dépendance opérationnelle (un
  fournisseur, des identifiants), pas technique ; hors du périmètre de ce qui peut être "codé".

## 14. Risques résiduels

- Le bind mount protège contre la recréation de conteneur, pas contre une panne disque ou la
  perte de la machine hôte — documenté explicitement, jamais présenté comme un backup (§5).
- Aucune sauvegarde automatique du répertoire de stockage n'existe (même limite assumée que pour
  PostgreSQL) — sauvegarde manuelle documentée, non planifiée.
- La configuration SMTP réelle reste à faire avant tout pilote effectif — ce n'est pas un
  changement de code, mais son absence signifie que les emails ne partent toujours pas
  aujourd'hui tant que quelqu'un n'a pas renseigné de vraies variables `SMTP_*`.
- L'incident de reconstruction d'image (§4) confirme, de façon presque ironique, l'exactitude du
  diagnostic de cette phase : même du code déjà "corrigé" peut redevenir invisible si son
  chemin de déploiement n'est pas fiable — un rappel supplémentaire, pas résolu ici, que Git/CI
  (§13) reste une dette réelle.

## 15. Statut

GO
