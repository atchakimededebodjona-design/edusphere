# Runbook — Mise en production des abonnements (Phase 29, lots A et C) et des migrations 0024 à 0028

> **Statut : exécuté en production le 2026-11-13, de 20:40 à 21:03 UTC.** Coupure d'environ une
> minute à partir de 21:00 UTC. Version déployée : `3c6796a` ; révision Alembic `0028`. Journal
> d'exécution, valeurs relevées et écarts rencontrés : §13. Préparé et répété le même jour sur une
> base PostgreSQL 16.16 jetable (§0.3).

Ce runbook s'appuie sur le runbook du lot 3 de la caisse
([`SCHOOL_CASHIER_LOT3_MIGRATION_RUNBOOK.md`](SCHOOL_CASHIER_LOT3_MIGRATION_RUNBOOK.md)) et le
remplace pour l'exécution : la production n'ayant jamais reçu le lot 3, les deux mises en
production n'en font qu'une. Le runbook du lot 3 reste la référence pour le détail de la
migration `0026` : contraintes (§4.3), tests fonctionnels de la caisse (§5) et conséquences d'un
downgrade (§6.2).

Toutes les commandes s'exécutent sur le serveur, dans le répertoire du déploiement
(`/opt/edusphere`, celui des unités systemd), avec l'utilisateur qui lance habituellement
`docker compose`. **Ne jamais copier le contenu de `.env` ni la sortie de `docker compose config`
dans un ticket, un message ou une conversation : ils contiennent les mots de passe.**

## 0. Ce que contient cette mise en production

### 0.1 Constat en lecture seule (2026-11-13, requêtes publiques sans authentification)

| Route | Réponse | Signification |
|---|---|---|
| `GET /api/v1/health` | `200` | API en service |
| `GET /api/v1/partner/organizations` (PR #19) | `401` | route présente : production au moins à la révision `0023` |
| `GET /api/v1/cashier/students/search` (PR #26) | `404` | lot 2 de la caisse absent |
| `GET /api/v1/cash/sessions/current` (PR #27) | `404` | lot 3 absent : révision inférieure à `0026` |
| `GET /api/v1/school-subscription` (PR #28) | `404` | abonnements absents |

La révision exacte (`0023`, `0024` ou `0025`) n'est connue que sur le serveur (étape 1).

### 0.2 Ce qui part en production (`main`, PR #20 à #29)

| PR | Migration | Effet pour les utilisateurs |
|---|---|---|
| #20 à #24 | `0024` (PR #22) | Corrections de droits. Une attribution de rôle ne peut plus exister en double : **`0024` s'arrête sans rien modifier si des doublons existent** (contrôlé à l'étape 2). L'ancienne route `POST /schools` répond `410` : la création d'école passe par les parcours plateforme et partenaire. |
| #25 | `0025` | Nouveau rôle `CAISSIER`. Nouvelle permission `payments.cancel`, donnée aux rôles qui annulaient déjà les paiements (SUPER_ADMIN, SCHOOL_ADMIN, DIRECTOR, ACCOUNTANT). |
| #26, #27 | `0026` | Écrans de caisse. **Aucun changement dans la façon d'encaisser des comptes existants** : l'ouverture de caisse n'est exigée que des comptes `CAISSIER`, et il n'en existe aucun. Les administrateurs, directeurs et comptables voient de nouveaux menus : « Caisse », « Ma caisse » et « Supervision caisse ». Pour eux, ouvrir une caisse reste facultatif. |
| #28 | `0027` | Abonnements : page « Abonnement » pour SCHOOL_ADMIN (paiement), DIRECTOR et ACCOUNTANT (consultation) ; pages plateforme pour PLATFORM_OWNER. Trimestre gratuit, grille de prix, factures, paiement manuel. **Aucun blocage d'accès.** |
| #29 | `0028` | Tâche quotidienne : rappels J-30, J-7 et J0 de fin de couverture, rappel 3 jours avant l'expiration d'une facture, expiration automatique des factures, reçus PDF. |

Les cinq migrations sont **strictement additives**. L'ancienne version de l'API fonctionne avec le
nouveau schéma, sauf sur un point : l'affichage des notifications d'abonnement (§10.1).

### 0.3 Répétition déjà faite (2026-11-13, base jetable PostgreSQL 16.16)

Base migrée jusqu'à `0023` avec le code de `main`, puis garnie de données réalistes : 3 écoles
dans 2 organisations, 6 comptes dont un inactif, des rôles d'école et d'organisation, et 40
paiements. Résultats :

- `phase29-precheck.sql` : identique sur la base et sur sa copie restaurée depuis `pg_dump -Fc`
  (`pg_restore` : code 0) ;
- `alembic upgrade head` (0023 → 0028) sur la copie : **2,5 s** ; `phase29-postcheck.sql` :
  **20 contrôles OK sur 20** ;
- `grant_free_quarters` : sans date de lancement, aucune attribution ; avec `2026-11-16`,
  3 trimestres du 2026-11-16 au 2027-02-15 ; une relance n'en crée aucun autre ;
  `subscription_reminders` : 0 rappel ; tâches exécutées avec le rôle applicatif `edusphere_app`,
  donc RLS et droits réels ;
- `alembic downgrade 0023` : **2,3 s**, l'état d'origine est retrouvé (seules les 3 entrées
  d'audit des trimestres restent, comme prévu) ; puis `upgrade head` : 20 contrôles OK sur 20, et
  la réattribution donne les mêmes dates ;
- doublon volontaire dans `user_roles` : `0024` s'arrête, la base reste en `0023` et rien n'est
  créé. Toutes les migrations s'exécutent dans **une seule transaction** (`alembic/env.py`).

Ce qui n'a **pas** été répété : la construction des images sur le serveur, le volume réel de la
production, et les parcours d'interface sur des données réelles. Ces parcours sont couverts par la
CI (`tests/test_subscriptions*.py`, `tests/test_school_cashier*.py`).

## 1. Décisions à prendre avant de commencer

1. **Date de lancement** `SUBSCRIPTION_LAUNCH_DATE` (`AAAA-MM-JJ`) :
   - les écoles déjà en service reçoivent leur trimestre gratuit **à partir de cette date** ;
   - une école créée après cette date le reçoit à partir de sa date de création ;
   - **cette date ne peut plus être corrigée pour une école déjà servie** : une période attribuée
     n'est jamais modifiée. Il faut donc la fixer juste du premier coup ;
   - recommandation : le jour de la mise en production, ou le jour annoncé aux écoles. Jamais plus
     de 60 jours dans le passé : sinon, les premiers trimestres finissent dans moins de 30 jours et
     le premier passage de la tâche envoie aussitôt des rappels J-30 ;
   - sans date (valeur vide), rien n'est attribué et les écoles voient « Aucun abonnement ».
     Il vaut donc mieux la fixer pendant la fenêtre de maintenance (étape 5).
2. **Montants réels de la grille** : ils peuvent attendre (étape 8). Tant qu'aucune grille n'est
   active, une école ne peut pas émettre de facture. Ce n'est pas gênant pendant le trimestre
   gratuit, mais la grille doit être active **au moins 30 jours avant la fin des premiers
   trimestres**, puisque les rappels J-30 invitent à renouveler.
3. **Paiement** : le paiement Mobile Money (lot B, PayGate) n'est pas livré. À la fin des
   trimestres gratuits, seul le paiement manuel enregistré par la plateforme sera possible.
4. **Fenêtre de maintenance** : 15 à 30 minutes, annoncée aux écoles. À éviter : 02:00 (sauvegarde
   quotidienne), puis 06:00 et 06:30 (tâches de rappel, qui exigent que l'API tourne).

## 2. Étape 1 — Inventaire du serveur (lecture seule)

```sh
cd /opt/edusphere
git status -sb
git log -1 --format='%H %ci %s'
docker compose ps
docker compose images
docker compose exec -T api alembic current
docker compose exec -T db printenv POSTGRES_USER POSTGRES_DB
df -h / /var/lib/docker
systemctl list-timers 'edusphere-*' --all --no-pager
ls -l /etc/systemd/system/edusphere-*
```

Noter :
- **`COMMIT_PROD`**, le commit déployé ;
- **`REV_PROD`**, la révision Alembic ;
- les noms des images `api` et `web`. La suite suppose `edusphere-api:latest` et
  `edusphere-web:latest` : adapter les commandes si `docker compose images` montre d'autres noms.

**Arrêt** si l'une de ces conditions est vraie :
- le répertoire n'est pas un dépôt git ;
- `git status` montre des modifications locales ;
- `REV_PROD` est inférieure à `0023` ;
- il reste moins de 5 Go libres pour les images et la copie de la base.

## 3. Étape 2 — Récupérer le code et contrôler la base (sans effet sur le service)

Mettre à jour les fichiers ne change rien aux conteneurs en cours : ils ne changent qu'à l'étape 5.
Depuis la PR #19, `docker-compose.yml`, les Dockerfile et les scripts de sauvegarde sont
inchangés. Seuls des fichiers ont été ajoutés : `deploy/systemd/` et `scripts/release/`.

```sh
git fetch https://github.com/atchakimededebodjona-design/edusphere.git main:refs/remotes/origin/main
git log -1 --format='%H %s' origin/main   # le commit dont la CI GitHub est verte
git merge --ff-only origin/main           # si la branche locale est main ; sinon s'arrêter
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -v ON_ERROR_STOP=1 -f -' \
  < scripts/release/phase29-precheck.sql
```

Le dépôt est public : on récupère le code par HTTPS. Le remote `origin` du serveur pointe vers
`git@github.com:…` et `root` n'y a aucune clé autorisée, donc `git fetch origin` échoue avec
`Permission denied (publickey)` (constaté le 2026-11-13). La commande ci-dessus met à jour
`origin/main` sans modifier la configuration git du serveur.

Résultat attendu de `phase29-precheck.sql`, qui est en lecture seule :
1. la révision `REV_PROD` ;
2. `deja_present` à `true` pour les migrations déjà appliquées et `false` pour les autres ;
3. **doublons : 0 partout.** Sinon, et si `0024` n'est pas encore appliquée : **NO-GO**, car
   supprimer des doublons est une décision humaine, hors de ce runbook ;
4. le volume de `payments`, qui sert à estimer la durée des 3 index de `0026` ;
5. les comptages de référence.

## 4. Étape 3 — Construire les nouvelles images (sans les démarrer)

```sh
docker tag edusphere-api:latest edusphere-api:avant-phase29   # images de retour arrière
docker tag edusphere-web:latest edusphere-web:avant-phase29
grep -c '^EDULINKAGE_NON_DEPLOYABLE_BUILD' .env               # attendu : 0
grep '^NEXT_PUBLIC_API_URL=' .env                             # attendu : https://api.edulinkage.com
docker compose build api web
docker image ls 'edusphere-*'
```

La construction ne touche pas aux conteneurs en cours. Elle échoue d'elle-même si
`NEXT_PUBLIC_API_URL` est absente ou locale (`apps/web/config/apiUrl.js`).

## 5. Étape 4 — Répétition sur une copie restaurée (préproduction jetable)

Cette étape vérifie deux choses en une fois : que la sauvegarde se restaure dans une **autre
instance PostgreSQL**, et que la migration passe sur les **données réelles**. Le service reste
ouvert pendant toute l'étape. La copie tourne dans un conteneur à part, sur un réseau Docker à
part, sans port publié.

### 5.1 Sauvegardes et comptages

```sh
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -v ON_ERROR_STOP=1 -f -' \
  < scripts/release/phase29-precheck.sql > /tmp/precheck-prod.txt
scripts/db-backup.sh          # noter le fichier produit : backups/edulinkage_<horodatage>.dump
scripts/storage-backup.sh     # reçus et documents (non modifiés par les migrations)
```

### 5.2 Instance jetable et restauration

```sh
DUMP=backups/edulinkage_<horodatage>.dump
PG_USER=$(docker compose exec -T db printenv POSTGRES_USER </dev/null)
PG_DB=$(docker compose exec -T db printenv POSTGRES_DB </dev/null)
REP_PW=$(openssl rand -hex 16)     # mot de passe jetable, jamais affiché
docker network create edl-repetition
docker run -d --name edl-repetition-db --network edl-repetition \
  -e POSTGRES_USER="$PG_USER" -e POSTGRES_PASSWORD="$REP_PW" -e POSTGRES_DB="$PG_DB" postgres:16-alpine
until docker logs edl-repetition-db 2>&1 | grep -q 'PostgreSQL init process complete'; do sleep 2; done
until docker exec edl-repetition-db pg_isready -U "$PG_USER" -d "$PG_DB" -q; do sleep 1; done
docker exec edl-repetition-db psql -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 \
  -c "CREATE ROLE edusphere_app LOGIN PASSWORD '$REP_PW'"
docker cp "$DUMP" edl-repetition-db:/tmp/prod.dump
docker exec edl-repetition-db pg_restore -U "$PG_USER" -d "$PG_DB" /tmp/prod.dump; echo "pg_restore : code $?"
docker exec -i edl-repetition-db psql -U "$PG_USER" -d "$PG_DB" -X -v ON_ERROR_STOP=1 -f - \
  < scripts/release/phase29-precheck.sql > /tmp/precheck-copie.txt
diff /tmp/precheck-prod.txt /tmp/precheck-copie.txt && echo IDENTIQUE
```

Attendu :
- `pg_restore : code 0` ;
- `IDENTIQUE`, ou des écarts seulement sur des lignes que l'activité entre les deux commandes
  explique (`notifications`, `audit_logs`). **Un écart sur `payments` ou `schools` impose de
  recommencer l'étape 5.1.**
- Un écart sur la **taille** de `payments` (section 4) est normal. Une table restaurée n'a pas
  d'espace mort, elle est donc plus compacte : le 2026-11-13, 112 kB en production contre 56 kB
  sur la copie, pour 0 ligne des deux côtés. Seuls les comptages de lignes comptent.

`</dev/null` empêche `docker compose exec` de lire, dans le terminal, les lignes collées qui
suivent.

Le rôle `edusphere_app` est créé avant la restauration, car le dump contient ses droits.

### 5.3 Migration de la copie avec la nouvelle image

```sh
rep() { docker run --rm --network edl-repetition -e ENVIRONMENT=development \
  -e DATABASE_URL="postgresql+asyncpg://$PG_USER:$REP_PW@edl-repetition-db:5432/$PG_DB" \
  -e APP_DATABASE_URL="postgresql+asyncpg://edusphere_app:$REP_PW@edl-repetition-db:5432/$PG_DB" \
  -e SUBSCRIPTION_LAUNCH_DATE="${LAUNCH:-}" edusphere-api:latest "$@"; }
rep alembic current                  # attendu : REV_PROD
time rep alembic upgrade head        # noter la durée « real »
docker exec -i edl-repetition-db psql -U "$PG_USER" -d "$PG_DB" -X -v ON_ERROR_STOP=1 -f - \
  < scripts/release/phase29-postcheck.sql
```

Attendu :
- **20 lignes `OK`, aucune `KO`** ;
- une durée de quelques secondes : seuls les 3 index de `payments` dépendent du volume.

`ENVIRONMENT=development` ne concerne que ces conteneurs jetables : ils ne servent aucune requête
et n'ont pas les secrets de production.

### 5.4 Répétition des tâches avec la date de lancement choisie

```sh
LAUNCH=AAAA-MM-JJ                     # la date décidée au §1
rep python -m app.jobs.grant_free_quarters
rep python -m app.jobs.subscription_reminders
docker exec -i edl-repetition-db psql -U "$PG_USER" -d "$PG_DB" -X -v ON_ERROR_STOP=1 -f - \
  < scripts/release/phase29-state.sql
```

Attendu :
- autant de trimestres attribués que d'écoles, et `ecoles_sans_trimestre = 0` ;
- des dates conformes à la décision ;
- `0 rappel(s)` si la date respecte la règle des 60 jours (§1).

### 5.5 Retour arrière testé, puis nettoyage

```sh
time rep alembic downgrade <REV_PROD>
docker exec -i edl-repetition-db psql -U "$PG_USER" -d "$PG_DB" -X -v ON_ERROR_STOP=1 -f - \
  < scripts/release/phase29-precheck.sql   # révision REV_PROD ; seul audit_logs a pu augmenter
rep alembic upgrade head
docker exec -i edl-repetition-db psql -U "$PG_USER" -d "$PG_DB" -X -v ON_ERROR_STOP=1 -f - \
  < scripts/release/phase29-postcheck.sql  # 20 OK
docker rm -f -v edl-repetition-db && docker network rm edl-repetition
unset REP_PW
```

`-v` supprime aussi le volume anonyme de la copie. Copier ensuite le dump **hors du serveur** et
noter son empreinte : `sha256sum "$DUMP"`.

## 6. Étape 5 — Fenêtre de maintenance (production)

Durée attendue : le temps mesuré au §5.3, plus une à deux minutes pour l'arrêt, la sauvegarde et le
redémarrage.

```sh
docker compose stop web api                 # plus aucune écriture à partir d'ici
scripts/db-backup.sh                        # dump final ; noter le fichier
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -v ON_ERROR_STOP=1 -f -' \
  < scripts/release/phase29-precheck.sql    # révision REV_PROD, doublons 0
docker compose run --rm --no-deps api alembic upgrade head
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -v ON_ERROR_STOP=1 -f -' \
  < scripts/release/phase29-postcheck.sql   # 20 OK
```

- `docker compose run --rm --no-deps api` lance la migration avec la **nouvelle** image et
  l'environnement de production, donc avec le rôle propriétaire de `DATABASE_URL`. Les droits
  d'`edusphere_app` sur les nouvelles tables en dépendent (contrôle 11). Aucun port n'est publié
  et `db` n'est pas redémarrée.
- **Si la migration échoue ou si une ligne est `KO`** : ne pas démarrer la nouvelle API.
  Conserver la sortie complète et appliquer le §10.1. Si la migration a échoué, la base est
  restée à `REV_PROD`, puisque tout tient dans une seule transaction.

Ajouter ensuite les deux réglages, après avoir vérifié qu'ils n'existent pas déjà, puis démarrer :

```sh
grep -c '^SUBSCRIPTION_' .env               # attendu : 0
printf '\nSUBSCRIPTION_INVOICE_VALIDITY_DAYS=30\nSUBSCRIPTION_LAUNCH_DATE=%s\n' AAAA-MM-JJ >> .env
docker compose up -d api web
docker compose ps                           # api « healthy », web démarré
curl -s http://127.0.0.1:8000/api/v1/health; echo
curl -s http://127.0.0.1:8000/api/v1/ready; echo        # database, redis, storage : "ok"
docker compose exec -T api printenv SUBSCRIPTION_LAUNCH_DATE SUBSCRIPTION_INVOICE_VALIDITY_DAYS
```

Si la date n'est pas encore décidée, écrire `SUBSCRIPTION_LAUNCH_DATE=` (vide) et y revenir plus
tard. Il faudra alors modifier `.env`, lancer `docker compose up -d api` (l'environnement n'est lu
qu'à la création du conteneur), puis reprendre l'étape 6.

## 7. Étape 6 — Tâches planifiées et trimestres gratuits

Mêmes conventions que `edusphere-overdue-reminders` (utilisateur `edusphere`, répertoire
`/opt/edusphere`), déjà en service.

```sh
sudo install -m 0644 \
  deploy/systemd/edusphere-grant-free-quarters.service deploy/systemd/edusphere-grant-free-quarters.timer \
  deploy/systemd/edusphere-subscription-reminders.service deploy/systemd/edusphere-subscription-reminders.timer \
  /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start edusphere-grant-free-quarters.service       # premier passage, attendu à la main
journalctl -u edusphere-grant-free-quarters.service -n 5 --no-pager -o cat
sudo systemctl start edusphere-subscription-reminders.service
journalctl -u edusphere-subscription-reminders.service -n 5 --no-pager -o cat
sudo systemctl enable --now edusphere-grant-free-quarters.timer edusphere-subscription-reminders.timer
systemctl list-timers 'edusphere-*' --no-pager
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -v ON_ERROR_STOP=1 -f -' \
  < scripts/release/phase29-state.sql
```

Attendu :
- `N trimestre(s) attribué(s)`, où N est le nombre d'écoles, puis `0 rappel(s)` ;
- des minuteries toutes les heures (trimestres) et à 06:30 (rappels) ;
- `ecoles_sans_trimestre = 0` et les dates de la décision.

## 8. Étape 7 — Vérifications après l'ouverture

Sans créer de données fictives en production.

1. **De l'extérieur** :
   - les routes du §0.1 répondent `401` au lieu de `404` ;
   - `https://edulinkage.com` se charge, et son en-tête CSP contient
     `connect-src 'self' https://api.edulinkage.com`.
2. **PLATFORM_OWNER** :
   - `/platform/subscriptions` liste chaque école en « Trimestre gratuit » jusqu'à la date
     prévue ;
   - `/platform/subscription-grids` et `/platform/subscription-invoices` s'ouvrent (listes vides).
3. **SCHOOL_ADMIN d'une école réelle** : `/subscription` affiche le trimestre gratuit. Ne pas
   émettre de facture.
4. **DIRECTOR ou ACCOUNTANT** : `/subscription` en consultation seule.
5. **TEACHER** : pas de menu « Abonnement ».
6. **Non-régression** :
   - `/payments` et `/notifications` s'ouvrent ;
   - le prochain paiement réel, enregistré par un comptable ou un administrateur, passe comme
     avant (aucune caisse n'est exigée de ces rôles) ;
   - l'application mobile (parents, enseignants) affiche ses notifications.

Le parcours complet (facture, paiement manuel, reçu PDF) n'est **pas** rejoué en production avec
de fausses données. Chaque facture consomme un numéro de la série sans trou `EL-AAAA-NNNNNN`. Ce
parcours est couvert par la CI ; suivre la première facture réelle avec `phase29-state.sql`.

Caisse : rien ne change tant qu'aucun compte `CAISSIER` n'est créé. Avant d'en créer un, former le
caissier : il doit ouvrir sa caisse avant tout encaissement en espèces. Suivre ensuite le §5 du
runbook du lot 3.

## 9. Étape 8 — Grille de prix réelle (quand les montants sont décidés)

1. Ouvrir `/platform/subscription-grids` avec PLATFORM_OWNER.
2. Créer une grille avec, pour chaque durée (3, 6 et 12 mois) :
   - le montant de base (tranche 1 à 100 élèves) ;
   - le supplément des tranches 101–250, 251–500 et 501–1000.
3. Relire les montants, puis activer la grille. Une seule grille est active à la fois ; la
   précédente est archivée.
4. Contrôler avec `phase29-state.sql`, section 3 : une grille `ACTIVE` avec 12 lignes.

Au-delà de 1000 élèves, la facture passe par un devis saisi par la plateforme.

## 10. Retour arrière

### 10.1 Retour arrière applicatif (recommandé : schéma conservé, aucune perte)

**Avant tout retour arrière, lire la section 6 de `phase29-state.sql`.** L'API d'avant la Phase 29
ne connaît pas les types `SUBSCRIPTION_*`. Elle échoue (erreur 500) sur la liste des notifications
de tout compte qui en a reçu une. Avec une date de lancement récente, aucune n'existe pendant les
deux premiers mois environ : le premier rappel J-30 tombe 30 jours avant la fin des trimestres.

```sh
sudo systemctl disable --now edusphere-subscription-reminders.timer edusphere-grant-free-quarters.timer
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -v ON_ERROR_STOP=1 -f -' \
  < scripts/release/phase29-state.sql       # section 6 : total_notifications_abonnement
docker compose stop api web
git checkout <COMMIT_PROD>
docker tag edusphere-api:avant-phase29 edusphere-api:latest
docker tag edusphere-web:avant-phase29 edusphere-web:latest
docker compose up -d --no-build api web
```

Si `total_notifications_abonnement > 0`, deux possibilités :
- préférable : **ne pas revenir en arrière** et corriger par une nouvelle version ;
- seulement sur décision explicite et après un dump : supprimer ces notifications, qui ne sont
  qu'informatives (`DELETE FROM notifications WHERE type LIKE 'SUBSCRIPTION\_%'`).
  Cette suppression est irréversible.

Les lignes `SUBSCRIPTION_*` de `.env` sont ignorées par l'ancienne version.

### 10.2 Downgrade du schéma (seulement sans données réelles)

**À ne faire que si `phase29-state.sql` montre :**
- `comptes_caissier`, `sessions`, `mouvements` et `comptages` à 0 ;
- aucune facture, aucun paiement d'abonnement, aucun rappel ;
- aucune notification d'abonnement.

Les trimestres gratuits peuvent être perdus : ils sont recréés à l'identique par la tâche (§0.3).
Le downgrade doit être lancé avec la **nouvelle** image, car l'ancienne ne connaît pas les
migrations 0024 à 0028. Il se fait donc **avant** `git checkout` et les commandes `docker tag`
du §10.1. Enchaînement :
1. les trois premières commandes du §10.1 : désactiver les minuteries, lire l'état, arrêter
   `api` et `web` ;
2. le downgrade :
   ```sh
   docker compose run --rm --no-deps api alembic downgrade <REV_PROD>
   ```
3. la suite du §10.1, à partir de `git checkout <COMMIT_PROD>`.

Le downgrade supprime :
- les tables et données de caisse et d'abonnement ;
- la colonne `payments.cash_session_id` ;
- le rôle `CAISSIER`, avec ses attributions ;
- les index uniques de `user_roles`.

Le détail est au §6.2 du runbook du lot 3 et dans les docstrings de `0027` et `0028`. Les entrées
d'audit restent.

### 10.3 Restauration du dump

En dernier recours seulement : toute donnée créée depuis la fenêtre de maintenance serait perdue.
Il faut une décision explicite et un plan d'extraction préalable de ces données (même principe
que le §7 du runbook du lot 3).

## 11. Critères GO / NO-GO

**GO** seulement si tous les points sont vrais :
- [ ] CI GitHub verte sur le commit exact déployé (`git log -1` de l'étape 2) ;
- [ ] `COMMIT_PROD`, `REV_PROD` et les noms d'images notés (étape 1) ;
- [ ] doublons `user_roles` à 0, si `0024` est en attente (étape 2) ;
- [ ] images de retour arrière `:avant-phase29` présentes, nouvelles images construites
      (étape 3) ;
- [ ] sauvegarde restaurée dans une autre instance, comptages identiques ou écarts expliqués
      (§5.2) ;
- [ ] migration de la copie : 20 contrôles OK, durée compatible avec la fenêtre (§5.3) ;
- [ ] tâches répétées sur la copie avec la date décidée : résultats attendus (§5.4) ;
- [ ] retour arrière testé sur la copie (§5.5) ;
- [ ] date de lancement décidée, ou choix assumé de la laisser vide (§1) ;
- [ ] dump de répétition copié hors du serveur, empreinte notée ;
- [ ] fenêtre annoncée aux écoles.

**NO-GO** si un seul point est faux, inconnu ou non prouvé.

## 12. Après la mise en production

- Pendant la première semaine, chaque matin : `journalctl -u edusphere-subscription-reminders.service --since today`
  et `systemctl list-timers 'edusphere-*'`.
- Relancer `phase29-postcheck.sql` à tout moment (il ne lit que la structure) et
  `phase29-state.sql` pour suivre les trimestres, factures et rappels.
- Conserver le dump final hors du serveur jusqu'à la première facture réelle payée et vérifiée.
- Supprimer les images `:avant-phase29` après deux semaines sans incident :
  `docker image rm edusphere-api:avant-phase29 edusphere-web:avant-phase29`.
- Activer la grille réelle au moins 30 jours avant la fin des premiers trimestres (étape 8).

### Limites connues

- L'application mobile affiche le code brut d'un type de notification qu'elle ne connaît pas. Les
  rappels d'abonnement ne visent que SCHOOL_ADMIN et DIRECTOR, qui utilisent le web.
- Les reçus d'abonnement ne portent pas de mentions légales ni de TVA : la question Q8 du cadrage
  est toujours ouverte.

## 13. Journal d'exécution (2026-11-13)

L'exploitant a exécuté la procédure depuis la console web de l'hébergeur, en `root`, sur le serveur
`srv1965166` (Ubuntu 26.04.1 LTS). Chaque sortie a été relue avant l'étape suivante.

| Étape | Heure (UTC) | Constat |
|---|---|---|
| 1. Inventaire | 20:30 | `COMMIT_PROD` = `7593a5b` (PR #24) ; `REV_PROD` = `0024` ; images `edusphere-api` et `edusphere-web` ; utilisateur et base `edusphere` ; 47 Go libres, 7,7 Go de mémoire, 2 processeurs. Minuteries en place : sauvegarde vers 02:40, rappels de frais à 06:00. |
| 2. Code et contrôle | 20:38 | `git fetch origin` refusé (pas de clé SSH), donc récupération par HTTPS (§3) ; avance rapide de `7593a5b` à `3c6796a` (CI verte). Contrôle préalable : objets de `0026` à `0028` absents, aucun doublon, 0 paiement. Comptages : 2 organisations, 3 écoles, 8 comptes, 8 attributions de rôle, 15 élèves, 0 notification, 4 entrées d'audit. |
| 3. Images | 20:40–20:46 | Images de retour arrière : `edusphere-api:avant-phase29` (`bba96e0e11bc`), `edusphere-web:avant-phase29` (`fa46b3f2ee08`). Nouvelles images : `27649fa17932` et `e29274add7ef`. Construction : code 0. |
| 4. Répétition | 20:47–20:51 | Sauvegardes : `edulinkage_20261113T204703Z.dump` (292 Ko, SHA-256 `7df4349e32b7ae19d8d3e580798b8560490908e03f4b3ecb2e88b455e95335fe`) et `storage_20261113T204705Z.tar.gz` (4,5 Mo, 10 fichiers). Restauration : code 0, copie identique hormis la taille de `payments` (§5.2). Migration : 3,3 s, 20 contrôles OK. 3 trimestres attribués, du 2026-11-13 au 2027-02-12, et 0 rappel. Downgrade vers `0024` : 2,6 s, puis 20 OK après la nouvelle migration. Copie supprimée. |
| 5. Coupure | 21:00–21:01 | Arrêt de `web` et `api`. Sauvegarde finale `edulinkage_20261113T210018Z.dump` (292 Ko, intégrité vérifiée). `0024` → `0028` : code 0, 20 contrôles OK. Ajout à `.env` de `SUBSCRIPTION_INVOICE_VALIDITY_DAYS=30` et `SUBSCRIPTION_LAUNCH_DATE=2026-11-13`, puis redémarrage. `/health` : ok ; `/ready` : `database`, `redis`, `storage` et `email` à ok. |
| 6. Tâches | 21:02 | Unités installées. Trimestres : 3 attribués ; rappels : 0. Minuteries actives : trimestres toutes les heures, rappels d'abonnement à 06:30. État : 3 écoles, 3 trimestres, aucune école sans trimestre. |
| 7. Contrôle externe | 21:02 | Routes de caisse et d'abonnement : `401` au lieu de `404`. Web : `/`, `/login`, `/subscription` et `/cashier` répondent `200`. CSP : `connect-src 'self' https://api.edulinkage.com`. |

Écarts et points restants :
- **Copie hors du serveur** (critère GO) : elle n'était pas faite au moment de la coupure, et les
  deux dumps ne se trouvaient alors que sur le serveur. À faire.
- **Vérifications d'interface** (§8, points 2 à 6) : à faire par l'exploitant avec des comptes
  réels.
- `git status` sur le serveur montre `backup-all.sh`, `db-backup.sh` et `storage-backup.sh`
  modifiés. Seul leur droit d'exécution a changé (mode `100755`), leur contenu est identique.
  Ces modifications ont été conservées.
- Ubuntu signale « System restart required » (48 mises à jour en attente) : le redémarrage du
  serveur est à planifier séparément.
