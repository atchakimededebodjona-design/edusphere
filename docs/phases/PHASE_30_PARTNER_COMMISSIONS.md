# Phase 30 — Commissions des partenaires (et taux de TVA figé sur les factures)

- **Demande** : 2026-11-15. « Ils auront 20 % du montant HT d'abonnement des écoles qui les concernent, après un paiement réussi et confirmé d'un abonnement. »
- **Branche** : `feat/partner-commissions`, partie de `main` (`a78f4e2`).
- **Migration** : `0031`.
- **Statut** : **en production depuis le 2026-11-15** (`de6b86a`). La TVA à 18 % et la grille TTC, actives à 19:00 UTC, ont été retirées le soir même : l'entreprise relève de la TPU. Grille HT active et aucun taux de TVA depuis. Journal : §6.

## 1. Décisions (2026-11-15)

| Sujet | Décision |
|---|---|
| Base | Montant **HT** de chaque facture d'abonnement **payée et confirmée** (paiement manuel ou Mobile Money confirmé). |
| Écoles concernées | Celles inscrites par le partenaire (`partner_school_enrollments.commission_eligible`, inscription active). Rien pour une école inscrite par la plateforme. |
| Durée | **À chaque paiement, sans limite** : premier abonnement et tous les renouvellements. |
| Taux | **Propre à chaque partenaire**, 20 % par défaut, modifiable par la plateforme. Il est **figé** sur chaque commission : un nouveau taux ne s'applique qu'aux paiements suivants. |
| Suspension | **Aucune commission** pour un paiement confirmé pendant que le partenaire est suspendu. |
| Versement | **Manuel** : la plateforme paie le partenaire hors application (Mobile Money, virement, espèces), puis marque les commissions « versées » avec le moyen et la référence. Une commission due peut être annulée avec un motif. |
| TVA | Prix de la grille **HT**, TVA 18 % **en plus** ; la grille enregistre donc les montants **TTC** payés par l'école. Le taux de TVA est **figé sur chaque facture** à son émission (`SUBSCRIPTION_VAT_RATE`), et le HT s'en déduit au franc près : 35 400 TTC donnent 30 000 HT, soit une commission de 6 000. **Révisé le 2026-11-15 au soir** : l'entreprise relève de la TPU et ne facture pas de TVA ; `SUBSCRIPTION_VAT_RATE` est vide et la grille porte les prix HT, la commission restant de 6 000 sur un forfait de base de 30 000. |

## 2. Ce qui est livré

**Base de données** (migration `0031`, additive)
- `partners.commission_rate` : 20 par défaut, avec CHECK 0..100. S'y ajoutent `commission_rate_updated_at` et `commission_rate_updated_by` : la fiche d'un partenaire n'a pas d'école, donc pas d'entrée possible dans le journal d'audit.
- `subscription_invoices.vat_rate` : taux figé, NULL pour les factures existantes.
- Table `partner_commissions` :
  - une commission par facture et par paiement (UNIQUE) ;
  - base HT, taux et montant figés ;
  - statut `DUE`, `PAID` ou `CANCELLED`, avec traçabilité du versement (date, auteur, moyen, référence) et de l'annulation (date, auteur, motif) ;
  - RLS « plateforme seulement » : aucune école ne lit les commissions.
- Permission `platform.commissions.manage` (SUPER_ADMIN, PLATFORM_OWNER). Les descriptions de `platform.commissions.read` et `partner.commissions.read`, réservées depuis la PR #17, sont mises à jour.

**Création automatique.** Le point unique de confirmation d'un paiement d'abonnement (`_mark_paid_and_create_period`) crée la commission dans la **même transaction** que la facture `PAID` et la période. Pour un même paiement, une notification PayGate et la tâche de rapprochement simultanées ne créent qu'**une** commission. Chaque création est inscrite au journal d'audit de l'école (`partner_commission.accrued`).

**API**

| Route | Permission |
|---|---|
| `GET /platform/partner-commissions` : filtres statut et partenaire, totaux à verser et versés | `platform.commissions.read` |
| `POST /platform/partner-commissions/mark-paid` : un seul partenaire par versement ; renvoyer le même versement est sans effet | `platform.commissions.manage` |
| `POST /platform/partner-commissions/{id}/cancel` : commission due seulement, motif obligatoire | `platform.commissions.manage` |
| `PUT /platform/partners/{id}/commission-rate` | `platform.commissions.manage` |
| `GET /partner/commissions` : ses seules commissions, son taux et ses totaux | `partner.commissions.read` |

**Web**
- **Plateforme** :
  - nouvelle page « Commissions » : filtres, totaux, sélection des commissions à verser, versement avec moyen et référence, annulation avec motif ;
  - page « Partenaires » : colonne « Commission », avec le taux modifiable.
- **Partenaire** : nouvelle page « Mes commissions », avec son taux, ses totaux (à recevoir, déjà reçues) et le détail.

**Test de garde** (`test_pr17_hardening.py`) : il interdisait toute table ou route de commission depuis le 12 novembre. Il est remplacé par `test_only_expected_subscription_and_commission_objects_exist`, qui vérifie la liste **exacte** des objets de commission (une table, quatre colonnes, cinq routes). Il interdit toujours tout « ledger » et tout « payout » dans les noms de tables et de routes.

## 3. Tests

`tests/test_partner_commissions.py` couvre :
- le calcul sur le HT, avec les arrondis ;
- les 20 % sur un paiement manuel, visibles par le partenaire et par la plateforme ;
- aucune commission pour une école inscrite par la plateforme ;
- aucune commission pendant une suspension, puis de nouveau après réactivation ;
- le taux propre au partenaire, figé sur chaque commission ;
- le taux de TVA figé sur la facture, la commission portant sur le HT (35 400 TTC donnent 6 000) ;
- un seul enregistrement pour un paiement Mobile Money, même avec deux notifications et la tâche en même temps ;
- le versement, sa répétition sans effet, l'annulation, et les refus (autre référence, commission déjà versée ou annulée, plusieurs partenaires) ;
- l'isolation : chaque partenaire ne voit que les siennes ; les écoles et les partenaires n'ont aucun accès plateforme (403) ; une requête directe sous RLS d'une école renvoie 0 ligne.

Sont aussi rejoués : `test_partner_isolation.py` (le propriétaire de la plateforme détient en plus `platform.commissions.manage`), les abonnements des lots A et B, et le test de garde.

## 4. Mise en service

Elle suit la même procédure que les mises en service précédentes, dans la console du serveur depuis `/opt/edusphere`, avec une coupure d'environ une minute.

1. **Code et images** :
   ```sh
   git fetch https://github.com/atchakimededebodjona-design/edusphere.git main:refs/remotes/origin/main
   git merge --ff-only origin/main
   docker tag edusphere-api:latest edusphere-api:avant-commissions
   docker tag edusphere-web:latest edusphere-web:avant-commissions
   docker compose build api web > /tmp/build-commissions.log 2>&1; echo "construction : code $?"
   ```
2. **Coupure** :
   ```sh
   docker compose stop web api
   scripts/db-backup.sh
   docker compose run --rm --no-deps api alembic upgrade head; echo "migration : code $?"
   docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -At' <<'SQL'
   SELECT version_num FROM alembic_version;
   SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname = 'partner_commissions';
   SELECT count(*) FROM partners WHERE commission_rate IS NULL;
   SQL
   docker compose up -d api web
   ```
   Attendu : `0031`, puis `t`, puis `0`.
3. **TVA et grille TTC, au même moment.** Avant ce point, la grille contient des prix HT et la TVA n'est pas déclarée : le HT est égal au total.
   - ajouter `SUBSCRIPTION_VAT_RATE=18` au `.env`, puis lancer `docker compose up -d api` ;
   - aussitôt, activer la grille TTC : forfait de base 35 400 / 67 260 / 127 440 ; 101-250 : 11 800 / 22 420 / 42 480 ; 251-500 : 29 500 / 56 050 / 106 200 ; 501-750 : 53 100 / 100 890 / 191 160 ; 751-1 000 : 82 600 / 156 940 / 297 360 ; palier : 29 500 / 56 050 / 106 200.

   Ces montants sont les prix HT validés multipliés par 1,18.
4. **Taux des partenaires** : vérifier, ou modifier, la colonne « Commission » de la page « Partenaires ». Elle vaut 20 % par défaut.

## 5. Reste à faire

- **Reçus** : mentions légales et détail HT, TVA et TTC (décisions du 2026-11-15 : entreprise assujettie à 18 %, reçu enrichi, facture normalisée délivrée séparément). Il faut d'abord la raison sociale, l'adresse, le NIF, le RCCM et les contacts.
- **Versement automatique** par l'API de décaissement PayGate : écarté pour l'instant, à reconsidérer après une période de versements manuels.

## 6. Journal de mise en service (2026-11-15)

Exécuté par l'exploitant depuis la console web de l'hébergeur (`root`, `srv1965166`), selon le §4.

| Étape | Heure (UTC) | Constat |
|---|---|---|
| CI | 18:22, puis vers 18:47 | Verte sur la PR #35 (`8cb7e4e`), puis sur `main` (`de6b86a`). |
| 1. Code et images | 18:40 | `0367a71` → `de6b86a` en avance rapide. Images de retour arrière : `edusphere-api:avant-commissions` (`ab7ed18274fe`) et `edusphere-web:avant-commissions` (`aa726ee05b06`). Construction : code 0. |
| 2. Coupure | 18:56 | Sauvegarde `edulinkage_20261115T185638Z.dump` (368 Ko, intégrité vérifiée). `0030` → `0031` : code 0. Contrôles : `0031`, RLS activée et forcée sur `partner_commissions`, aucun partenaire sans taux, `platform.commissions.manage` attribuée à 2 rôles. API `healthy`, `/health` et `/ready` à `ok`. Partenaire existant : « Partner test », actif, 20,00 %. |
| 3. TVA et grille TTC | après 19:00 | Brouillon « Grille EduLinkage 2026-11 TTC (TVA 18 %) » ; les 18 montants du §4 ont été vérifiés sur capture. Ajout de `SUBSCRIPTION_VAT_RATE=18` au `.env`, puis redémarrage de l'API (`healthy`, `18`, paiement en ligne `true`) et activation aussitôt de la grille TTC, la grille HT étant archivée. Page Abonnement de l'école de test : offres à 35 400, 67 260 et 127 440 FCFA. |

À partir de ce moment, chaque nouvelle facture enregistre `vat_rate = 18`, et la commission d'un partenaire porte sur le HT : 6 000 F pour un trimestre à 35 400 F avec un taux de 20 %. La facture de test `EL-2026-000001` (100 FCFA), antérieure, n'a pas de taux de TVA ; son école n'a pas été inscrite par un partenaire, elle n'ouvre donc droit à aucune commission.

**Retrait de la TVA, le soir même.** La carte unique de création d'entreprise indique le régime de la TPU : l'entreprise ne facture pas de TVA. Après la fusion de la PR #36 (21:14 UTC), l'exploitant a :
- créé et activé « Grille EduLinkage 2026-11 HT (TPU) », avec les montants HT de la grille archivée « 2026-11 complète », vérifiés sur capture ; la grille TTC est archivée ;
- vidé `SUBSCRIPTION_VAT_RATE` dans le `.env`, puis redémarré l'API : `healthy`, taux de TVA `None`, paiement en ligne `true`.

La grille HT a été activée quelques minutes avant que le taux soit vidé. Aucune facture n'a été émise dans les trois heures précédant ce contrôle : aucune facture ne porte de taux de TVA. La commission d'un partenaire reste de 6 000 F pour un forfait de base de 30 000 F.
