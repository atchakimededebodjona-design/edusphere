# Phase 30 — Reçus d'abonnement : mentions légales et détail de la TVA

- **Demande** : 2026-11-15, « mentions légales et TVA des reçus ».
- **Branche** : `feat/subscription-receipt-legal`, partie de `main` (`de6b86a`).
- **Migration** : aucune. Le taux de TVA est déjà figé sur chaque facture (`subscription_invoices.vat_rate`, migration `0031`).
- **Statut** : **en production depuis le 2026-11-15** (`465de4e`, PR #36). Journal : §6.

## 1. Décisions (2026-11-15)

| Sujet | Décision |
|---|---|
| TVA | D'abord « assujettie, 18 % », puis **révisée le soir même** : l'entreprise relève de la **TPU** (carte unique de création d'entreprise) et **ne facture pas de TVA**. `SUBSCRIPTION_VAT_RATE` est vidé et la grille revient aux prix HT. Le détail HT, TVA et TTC reste prêt pour un passage au régime réel. |
| Document | **Reçu enrichi** : identité de l'entreprise, régime fiscal, client, détail des montants. Il atteste un paiement. |
| Facture normalisée | Délivrée **séparément** ; le reçu le mentionne et ne prétend pas la remplacer. |
| Identité de l'entreprise | Réglages `BILLING_*` du **serveur**, jamais dans le dépôt (public). |

## 2. Ce qui change

**Le reçu PDF** (`GET /school-subscription/invoices/{id}/receipt.pdf` et `GET /platform/subscription-invoices/{id}/receipt.pdf`, inchangés) affiche désormais :
- en tête, le nom commercial (`BILLING_TRADE_NAME`, « EduLinkage » par défaut) ;
- l'entreprise : raison sociale, forme juridique, adresse du siège, NIF, RCCM, régime fiscal (`BILLING_TAX_REGIME`, « TPU »), téléphone, e-mail ; un réglage vide n'est pas imprimé ;
- le client : nom de l'école, avec son adresse, son téléphone et son e-mail s'ils sont renseignés ;
- la facture, sa date d'émission, la période d'abonnement et l'effectif retenu ;
- le détail :
  - **facture avec taux de TVA figé** : lignes en HT, puis Total HT, TVA au taux de la facture et Total TTC ;
  - **facture sans taux de TVA** (entreprise à la TPU, ou `EL-2026-000001`) : lignes et total aux montants payés, sans aucune mention de TVA ;
- le montant payé, sa date, le moyen en clair (« T-Money (Mobile Money) », « espèces »…) et les références (référence saisie, transaction PayGate, référence de l'opérateur) ;
- la mention : « Ce reçu atteste le paiement de la facture n° … Il ne tient pas lieu de facture normalisée : celle-ci est délivrée séparément. »

Les montants sont en francs entiers, avec une espace entre les milliers (`47 200`).

**Calcul du HT** (`service.receipt_amounts`). Le Total HT est celui de la commission des partenaires (`pricing.amount_excl_vat`, au franc près). Chaque ligne est convertie au même taux. La dernière ligne absorbe l'arrondi, si bien que les lignes HT font exactement le Total HT. Avec une grille TTC égale aux prix HT × 1,18, comme celle du 2026-11-15, il n'y a aucun arrondi : 35 400 + 11 800 TTC donnent 30 000 + 10 000 HT, soit 7 200 de TVA.

**Supplément d'effectif** : libellé avec les bornes de la tranche (« 101 à 250 élèves »), à condition que l'effectif de la facture s'y trouve. Avant le 2026-11-15, la tranche 3 couvrait 501 à 1 000 élèves.

## 3. Tests

`tests/test_subscription_receipts.py` (sans base de données) :
- HT, TVA et TTC à partir des montants de la grille, avec le même HT que la commission ;
- arrondi absorbé par la dernière ligne ;
- facture sans taux de TVA : aucune mention de TVA, pas de ligne de supplément à 0 ;
- entreprise à la TPU : « Régime fiscal : TPU » à côté du NIF et du RCCM, aucune mention HT, TVA ou TTC ;
- libellés : devis, paliers au-delà de 1 000 élèves, tranche ;
- identité de l'entreprise et nom de l'école échappés, réglage vide non imprimé ;
- rendu PDF.

L'accès au reçu (facture payée seulement, école et plateforme, refus des autres) reste couvert par `test_subscriptions_lot_c.py`.

## 4. Mise en service

Sans migration ni coupure : seule l'API redémarre, quelques secondes. Dans la console du serveur, depuis `/opt/edusphere` :

1. **Code et image** :
   ```sh
   git fetch https://github.com/atchakimededebodjona-design/edusphere.git main:refs/remotes/origin/main
   git merge --ff-only origin/main
   docker tag edusphere-api:latest edusphere-api:avant-recus
   docker compose build api > /tmp/build-recus.log 2>&1; echo "construction : code $?"
   ```
2. **Identité de l'entreprise** : ajouter au `.env` les lignes `BILLING_*`. Une valeur avec des espaces s'écrit entre guillemets doubles. Ensuite :
   ```sh
   docker compose up -d api
   ```
   Un NIF ou un RCCM connu plus tard s'ajoute de la même façon, puis `docker compose up -d api`.
3. **Vérification** : télécharger, depuis la page plateforme des factures, le reçu de `EL-2026-000001`. Il doit porter l'identité de l'entreprise et, cette facture étant antérieure à la TVA, aucune ligne de TVA.

**Retour arrière** : `docker tag edusphere-api:avant-recus edusphere-api:latest`, puis `docker compose up -d api`. Les lignes `BILLING_*` peuvent rester : l'ancienne version les ignore.

## 5. À faire valider par un comptable

- Le régime fiscal en vigueur, la carte unique de création d'entreprise étant à renouveler. Un passage au régime réel avec TVA demanderait de remettre `SUBSCRIPTION_VAT_RATE` et une grille TTC au même moment, comme dans `PHASE_30_PARTNER_COMMISSIONS.md`, §4.
- Le contenu du reçu, et la délivrance de la facture normalisée (vignette de l'OTR) à chaque paiement ou sur demande.
- L'adéquation des activités déclarées au registre avec la vente d'abonnements à un logiciel en ligne.

## 6. Journal de mise en service (2026-11-15, soir)

Exécuté par l'exploitant depuis la console web de l'hébergeur (`root`, `srv1965166`), après la fusion de la PR #36 (21:14 UTC), dont la CI était verte.

| Étape | Constat |
|---|---|
| Retrait de la TVA | Grille « 2026-11 HT (TPU) » activée. `SUBSCRIPTION_VAT_RATE` vidé et lignes `BILLING_*` ajoutées au `.env` (les valeurs restent sur le serveur), puis redémarrage de l'API, encore en `de6b86a` : `healthy`, taux de TVA `None`, aucune facture émise dans les trois heures précédentes. Détail : `PHASE_30_PARTNER_COMMISSIONS.md`, §6. |
| Code et image | `de6b86a` → `465de4e` en avance rapide. Image de retour arrière : `edusphere-api:avant-recus`. Construction : code 0. API redémarrée : `healthy` ; les réglages `BILLING_*` sont lus, et le taux de TVA vaut `None`. |
| Vérification | Le reçu PDF de `EL-2026-000001`, téléchargé depuis l'espace plateforme, porte la raison sociale, la forme juridique, l'adresse, le NIF, le RCCM, « Régime fiscal : TPU », le téléphone et l'e-mail. Il porte aussi le bloc client de l'école, les montants sans aucune mention de TVA, le paiement T-Money avec ses références et la mention de la facture normalisée. |

Images de retour arrière présentes sur le serveur : `avant-phase29`, `avant-lot-b`, `avant-grille`, `avant-commissions` et `avant-recus`, à supprimer vers le 2026-11-29 si aucun incident.
