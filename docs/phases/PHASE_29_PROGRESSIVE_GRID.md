# Phase 29 — Grille tarifaire complète (tranches jusqu'à 1 000 élèves et paliers au-delà)

- **Décision** : 2026-11-15. L'exploitant restitue la grille validée le 2026-11-09 et choisit d'activer d'abord une grille provisoire, puis d'adapter le code.
- **Branche** : `feat/subscriptions-progressive-grid`, partie de `main` (`143a29c`).
- **Statut** : **en production depuis le 2026-11-15** (`0367a71`, migration `0030`). La grille complète « Grille EduLinkage 2026-11 complète » est active, et la grille provisoire est archivée. Journal : §6.
- **Grille provisoire** (active du 2026-11-15 jusqu'à la mise en service) : « Grille EduLinkage 2026-11 (501-1000 provisoire) ». Elle était exacte jusqu'à 750 élèves, facturait 751 à 1 000 élèves au prix de 501 à 750, et plaçait au-delà de 1 000 élèves en devis.

## 1. La grille validée le 2026-11-09

| Élèves actifs | Trimestriel | Semestriel | Annuel |
|---|---|---|---|
| 1 à 100 | 30 000 | 57 000 | 108 000 |
| 101 à 250 | 40 000 | 76 000 | 144 000 |
| 251 à 500 | 55 000 | 104 500 | 198 000 |
| 501 à 750 | 75 000 | 142 500 | 270 000 |
| 751 à 1 000 | 100 000 | 190 000 | 360 000 |
| 1 001 à 1 250 | 125 000 | 237 500 | 450 000 |
| 1 251 à 1 500 | 150 000 | 285 000 | 540 000 |
| 1 501 à 1 750 | 175 000 | 332 500 | 630 000 |
| Au-delà | +25 000 par tranche de 250 élèves | mêmes réductions | mêmes réductions |

Le semestriel vaut le trimestriel × 2 × 95 %, et l'annuel le trimestriel × 4 × 90 %.

## 2. Ce qui change

- **Tranches fixées dans le code** (`subscriptions/pricing.py`) :
  - 0 : 1 à 100 ;
  - 1 : 101 à 250 ;
  - 2 : 251 à 500 ;
  - 3 : **501 à 750** (au lieu de 501 à 1 000) ;
  - 4 : **751 à 1 000** (nouvelle).
- **Au-delà de 1 000 élèves** : une ligne **facultative** de palier (tranche 5) porte le supplément **par tranche de 250 élèves commencée**. Le prix est alors : forfait de base + supplément de 751 à 1 000 + nombre de paliers × supplément par palier. Exemple : 1 251 élèves, soit 2 paliers.
- **Sans palier**, l'école de plus de 1 000 élèves reçoit un **devis**, exactement comme au lot A. La grille provisoire continue donc de fonctionner.
- **Factures déjà émises** : inchangées, leurs montants sont figés.
- **Migration `0030`** : elle élargit seulement la contrainte des tranches de 0..3 à 0..5. Aucune donnée n'est réécrite. Le retour arrière refuse de s'exécuter, sans rien supprimer, s'il existe des lignes de tranche 4 ou de palier.
- **Écran « Grille tarifaire »** :
  - nouvelles lignes « 501 à 750 », « 751 à 1 000 » et « Au-delà de 1 000 élèves : supplément par tranche de 250 élèves (vide = devis) » ;
  - les cases manquantes sont signalées **en français avant l'envoi**, au lieu des messages de validation techniques en anglais.
- **Page « Abonnement »** : la tranche s'affiche en clair, par exemple « 751 à 1 000 élèves ».
- **Reçu** : au-delà de 1 000 élèves, la ligne du supplément indique le nombre de paliers.
- **Activation d'une grille** : elle exige les tranches 0 à 4 pour les trois durées, et le palier pour les trois durées ou pour aucune.

## 3. La grille à saisir après le déploiement

Une nouvelle grille préremplie avec la grille active n'a plus que deux lignes à compléter, la tranche 751 à 1 000 et le palier :

| Ligne de l'écran | 3 mois | 6 mois | 12 mois |
|---|---|---|---|
| Forfait de base (jusqu'à 100 élèves) | 30000 | 57000 | 108000 |
| Supplément 101 à 250 élèves | 10000 | 19000 | 36000 |
| Supplément 251 à 500 élèves | 25000 | 47500 | 90000 |
| Supplément 501 à 750 élèves | 45000 | 85500 | 162000 |
| **Supplément 751 à 1 000 élèves** | **70000** | **133000** | **252000** |
| **Au-delà de 1 000 élèves : par tranche de 250 élèves** | **25000** | **47500** | **90000** |

Un test unitaire (`test_the_validated_grid_is_reproduced_exactly`) vérifie que ces montants redonnent **exactement** la grille du §1 pour les trois durées, y compris les exemples au-delà de 1 750 élèves.

## 4. Tests

- `tests/test_subscriptions_pricing.py` (15 tests) :
  - nouvelles bornes ;
  - paliers (1 001 donne 1 palier, 1 251 en donne 2…) ;
  - grille validée reproduite ;
  - absence de prix sans palier ou avec une grille antérieure.
- `tests/test_subscriptions.py` :
  - **inchangés** : les tests existants. Seule la grille de test reçoit la tranche 4 et un palier, et le test du devis active une grille **sans** palier, ses assertions restant les mêmes ;
  - **ajoutés** : la validation de la grille (tranche 4 obligatoire, palier sur les trois durées ou aucune) et le prix progressif (800 élèves en tranche 4 ; 1 251 élèves avec 2 paliers, facture émise sans devis).
- Lots B et C, et test de garde : ils sont rejoués.

## 5. Mise en service

Elle suit la même procédure que le lot B (`PHASE_29_LOT_B_IMPLEMENTATION.md`, §8), dans la console du serveur depuis `/opt/edusphere`.

1. **Code et images**, sans effet sur le site :
   ```sh
   git fetch https://github.com/atchakimededebodjona-design/edusphere.git main:refs/remotes/origin/main
   git merge --ff-only origin/main
   docker tag edusphere-api:latest edusphere-api:avant-grille
   docker tag edusphere-web:latest edusphere-web:avant-grille
   docker compose build api web > /tmp/build-grille.log 2>&1; echo "construction : code $?"
   ```
2. **Coupure** d'environ une minute :
   ```sh
   docker compose stop web api
   scripts/db-backup.sh
   docker compose run --rm --no-deps api alembic upgrade head; echo "migration : code $?"
   docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -At' <<'SQL'
   SELECT version_num FROM alembic_version;
   SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_subscription_price_line_tier';
   SQL
   docker compose up -d api web
   ```
   Attendu : `0030`, puis `CHECK (((tier >= 0) AND (tier <= 5)))`.
3. **Nouvelle grille**, depuis l'écran « Grille tarifaire » :
   - cliquer sur « Nouvelle grille », qui est préremplie avec la grille active ;
   - libellé `Grille EduLinkage 2026-11 complète` ;
   - compléter les deux lignes en gras du §3, puis enregistrer ;
   - vérifier la grille, puis l'**activer**. La grille provisoire est alors archivée.

   Entre les étapes 2 et 3, une école de 751 à 1 000 élèves ne pourrait pas émettre de facture (409, « pas de prix »). Aucune n'existe aujourd'hui.

## 6. Journal de mise en service (2026-11-15)

Exécuté par l'exploitant depuis la console web de l'hébergeur (`root`, `srv1965166`), selon le §5.

| Étape | Heure (UTC) | Constat |
|---|---|---|
| CI | 15:46, puis vers 16:15 | Verte sur la PR #33 (`214ec3d`), puis sur `main` (`0367a71`). |
| 1. Code et images | 16:05 | `143a29c` → `0367a71` en avance rapide. Images de retour arrière : `edusphere-api:avant-grille` (`1edba8e76f65`) et `edusphere-web:avant-grille` (`fd831e4822b3`). Construction : code 0. |
| 2. Coupure | 16:18 | Sauvegarde `edulinkage_20261115T161825Z.dump` (364 Ko, intégrité vérifiée). `0029` → `0030` : code 0. Contrainte `CHECK (((tier >= 0) AND (tier <= 5)))`. API `healthy`, `/health` et `/ready` à `ok`. Paiement en ligne toujours actif (`true`, `paygate`). |
| 3. Grille complète | après 16:20 | Nouvelle grille préremplie depuis la grille active, libellé « Grille EduLinkage 2026-11 complète ». Les 18 montants du §3 ont été vérifiés sur capture avant activation. Après activation, la grille provisoire est archivée. Page Abonnement de l'école de test : « tranche 1 à 100 élèves (forfait de base) », offres à 30 000, 57 000 et 108 000 FCFA. |

Le nouvel écran a signalé les cases manquantes en français, comme prévu.
