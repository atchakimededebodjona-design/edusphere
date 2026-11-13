# Phase 29 — Lot A : abonnements des écoles, sans paiement en ligne

- **Cadrage** : `docs/phases/PHASE_29_SCHOOL_SUBSCRIPTIONS_DISCOVERY.md` (copie du cadrage validé le 2026-11-12).
- **Branche** : `feat/school-subscriptions-lot-a`, rebasée sur `origin/main` (`09b7a94`). Le commit local `9e6c990` (garde-fou de l'environnement de tests isolé, non poussé) n'en fait pas partie ; il ne modifie aucun fichier du lot A.
- **Statut** : code écrit ; **CI GitHub verte le 2026-11-12** sur la pull request n° 28 (voir §5).

## 1. Décisions appliquées

Validées par l'utilisateur le 2026-11-12. Les questions Q1 à Q11 renvoient au §21 du cadrage.

| Sujet | Décision |
| --- | --- |
| Qui s'abonne | L'école |
| Tarif | Forfait de base + supplément par tranche (0–100, 101–250, 251–500, 501–1 000) ; au-delà de 1 000 élèves : devis |
| Durées | 3, 6 et 12 mois, avec un montant distinct par durée (Q1) |
| Figé sur la facture | Effectif d'élèves actifs, tranche, version de grille, montants |
| Validité d'une facture non payée | 30 jours (Q6) |
| Qui émet une facture | SCHOOL_ADMIN seulement (Q4) ; DIRECTOR et ACCOUNTANT consultent |
| Début d'une période payée | À la confirmation du paiement, ou le lendemain de la dernière période existante (Q5) |
| Impayé | Rappels seulement, aucun blocage ; les rappels relèvent du lot C |
| Trimestre gratuit | Un par école, à vie ; écoles déjà en service comprises, à partir de `SUBSCRIPTION_LAUNCH_DATE` ; écoles créées ensuite, à partir de leur date de création |
| Commissions des partenaires | Hors périmètre |
| Paiement | Lot A : enregistrement manuel par la plateforme. Lot B : Mobile Money via PayGate Global |
| Numérotation | `EL-AAAA-NNNNNN`, séquentielle sans trou par année (Q8 : mentions légales et TVA restent à valider avec un comptable) |

## 2. Ce qui est livré

### API (`apps/api`)

**Module `app/modules/subscriptions/`**
- `pricing.py` : règles de calcul **pures**, sans base de données : tranches, dates de période et fins de mois, état affiché, début d'une nouvelle période, début du trimestre gratuit.
- `models.py` : six tables (§3).
- `service.py` : logique métier. Elle prend un verrou par école (verrou consultatif PostgreSQL limité à la transaction), puis verrouille la ligne de la facture (`FOR UPDATE`). Elle gère :
  - l'idempotence de l'émission de facture et du paiement manuel ;
  - l'expiration différée des factures (au moment où une nouvelle facture est demandée) ;
  - la numérotation sans trou ;
  - le cycle de vie de la grille.
- `free_quarters.py` : attribution idempotente du trimestre gratuit.
- `router.py` : endpoints (§4).

**Autres fichiers**
- `app/jobs/grant_free_quarters.py` : commande d'attribution du trimestre gratuit (code de sortie 0 ou 1, comme le job des rappels de frais). Une transaction par école : le verrou de chaque école est relâché aussitôt, et une relance termine le travail en cas d'échec.
- `alembic/versions/0027_school_subscriptions.py` : migration strictement additive.
- `app/modules/rbac/seed.py` : dictionnaires dédiés `SUBSCRIPTION_*`.
- `app/modules/audit/service.py` : 7 nouvelles actions d'audit.
- `app/core/config.py` : `subscription_invoice_validity_days` et `subscription_launch_date` (une valeur vide vaut « non définie »).
- `deploy/systemd/edusphere-grant-free-quarters.{service,timer}` : exécution toutes les heures. Ces fichiers sont préparés mais **non installés**.

### Web (`apps/web`)

- **`/subscription`** (école) :
  - état de l'abonnement et périodes ;
  - effectif et tranche ;
  - offres 3, 6 et 12 mois, avec leur prix calculé par l'API ;
  - émission de facture avec confirmation et clé d'idempotence ;
  - facture ouverte et historique des factures.
- **`/platform/subscriptions`** : état de l'abonnement de chaque école, avec filtre par état.
- **`/platform/subscription-invoices`** : factures, avec filtre par statut, chiffrage des devis, paiement manuel et annulation.
- **`/platform/subscription-grids`** : grilles (brouillon, modification, activation avec confirmation, historique).
- **Navigation** (`components/app-shell/Nav.tsx`) : les liens sont affichés selon la permission. Cela ne protège rien : l'API reste l'autorité.

### Documentation

- `docs/deployment/PRODUCTION_CONFIGURATION.md` et `.env.example` : les deux nouvelles variables.

## 3. Données (migration 0027)

| Table | Isolation (RLS) | Garde-fous en base |
| --- | --- | --- |
| `subscription_price_grids` | Lecture ouverte ; écriture en contexte plateforme uniquement | Une seule grille `ACTIVE` (index unique partiel) ; activation et archivage tracés |
| `subscription_price_lines` | Idem | Montants entiers ; supplément nul pour la tranche de base ; une ligne par couple (durée, tranche) |
| `subscription_invoice_number_counters` | **Aucune** : aucune donnée d'école, et l'école doit pouvoir émettre une facture | `last_value > 0` |
| `subscription_invoices` | Générique `{table}_tenant_isolation` | Une facture ouverte par école ; champs d'émission tous renseignés ou tous vides ; total = base + supplément ; payée ⇔ `paid_at` ; annulation tracée |
| `subscription_payments` | Générique | Un `SUCCEEDED` et une tentative en cours par facture ; paiement manuel tracé (auteur, référence) ; `identifier` unique et aléatoire |
| `school_subscription_periods` | Générique | `PAID` ⇔ facture ; un seul `FREE_TRIAL` par école ; `ends_on >= starts_on` |

L'absence de chevauchement entre périodes est garantie par le service, sous le verrou de l'école. Une contrainte d'exclusion PostgreSQL aurait exigé l'extension `btree_gist`, donc un superutilisateur.

## 4. Endpoints

| Méthode et chemin | Permission |
| --- | --- |
| `GET /school-subscription?school_id=` | `subscriptions.read` |
| `GET /school-subscription/invoices?school_id=` | `subscriptions.read` |
| `GET /school-subscription/invoices/{invoice_id}` | `subscriptions.read` (sur l'école de la facture) |
| `POST /school-subscription/invoices` (corps : `school_id`, `period_months`, `idempotency_key`) | `subscriptions.pay` |
| `GET /platform/subscription-grids` | `platform.subscriptions.read` |
| `POST /platform/subscription-grids`, `PUT /platform/subscription-grids/{grid_id}`, `POST …/{grid_id}/activate` | `platform.subscriptions.manage` |
| `GET /platform/subscriptions?state=` | `platform.subscriptions.read` |
| `GET /platform/subscription-invoices?status=&school_id=`, `GET …/{invoice_id}` | `platform.subscriptions.read` |
| `POST /platform/subscription-invoices/{invoice_id}/quote`, `…/cancel`, `…/manual-payments` | `platform.subscriptions.manage` |

**Attribution des permissions**
- `subscriptions.read` : SCHOOL_ADMIN, DIRECTOR, ACCOUNTANT, SUPER_ADMIN.
- `subscriptions.pay` : SCHOOL_ADMIN, SUPER_ADMIN.
- `platform.subscriptions.manage` : SUPER_ADMIN, PLATFORM_OWNER.
- `platform.subscriptions.read` existait déjà ; seule sa description change.
- PLATFORM_OWNER et PARTNER_ADMIN ne reçoivent **aucune** permission du domaine scolaire.

## 5. Vérifications

### Effectuées le 2026-11-12, sans Docker
- **Syntaxe** : analyse de la syntaxe Python des 17 fichiers Python créés ou modifiés (sans les exécuter) : aucune erreur.
- **Calcul** : les 11 tests de `tests/test_subscriptions_pricing.py` ont été exécutés directement avec Python 3.12, sans pytest ni base de données : tous passent.
- **Web** : `tsc --noEmit` sur l'ensemble de l'application : 0 erreur.

### CI GitHub (pull request n° 28), 2026-11-12

La CI (`.github/workflows/ci.yml`) exécute `ruff check`, `mypy app`, `alembic upgrade head` et `pytest`, avec PostgreSQL 16 et Redis, ainsi que le lint, la vérification de types et le build du web.

| Commit | api | web | mobile |
| --- | --- | --- | --- |
| `dc7ec39` | Échec : 1 test sur 1 048 (`test_platform_lists_school_states_and_invoices`, école cherchée dans la seule première page) ; ruff, mypy et migration 0027 réussis | Succès | Succès |
| `28ffb5d` | **Succès** (suite complète, dont les 15 tests d'intégration du lot A) | **Succès** | **Succès** |

Dans la CI, la base n'est pas vidée entre les tests (pas de garde-fou `9e6c990`). Deux tests du lot A en tiennent compte : `test_invoice_requires_an_active_grid` archive toute grille active avant de s'exécuter, et le test de la vue plateforme parcourt toutes les pages.

### Non effectuées
- `alembic downgrade` de la migration 0027 (la CI ne fait que `upgrade`).
- Tests de bout en bout Playwright.
- Exécution dans l'environnement de test isolé (ci-dessous).

### À exécuter aussi dans l'environnement de test isolé, une fois `9e6c990` intégré
1. Appliquer les migrations : `python -m edusphere_test_guard migrate`.
2. **Redonner les droits de nettoyage** sur les nouvelles tables : `python -m edusphere_test_guard grant-cleanup`. Sinon, le garde-fou refuse la session (privilège `TRUNCATE` manquant).
3. Lancer `pytest` : suite complète.
4. Lancer `ruff check` et `mypy` sur `apps/api`.

## 6. Tests existants modifiés (aucun affaibli)

- **`tests/test_pr17_hardening.py`**
  - `test_no_commission_engine_tables_or_routes_exist` est remplacé par `test_no_commission_engine_and_only_expected_subscription_objects_exist`.
  - L'interdiction de toute table ou route `commission`, `payout` ou `ledger` est **inchangée**.
  - Les tables et routes contenant `subscription` doivent désormais être **exactement** celles de ce lot.
- **Même fichier** : `/api/v1/school-subscription` est ajouté aux préfixes du balayage exhaustif. PLATFORM_OWNER et PARTNER_ADMIN ne doivent jamais y obtenir de réponse 2xx. C'est un renforcement.
- **`tests/test_partner_isolation.py`** : l'ensemble exact attendu pour PLATFORM_OWNER inclut maintenant `platform.subscriptions.manage`. Les contrôles « uniquement des codes `platform.*` » et « aucun code du domaine scolaire » sont inchangés.
- **`tests/pr17_helpers.py`** : `subscriptions.` est ajouté aux préfixes du domaine scolaire jamais attribués aux rôles plateforme et partenaire. C'est un renforcement.

## 7. Écarts au cadrage, assumés

1. **Bornes des tranches fixées dans le code** (`pricing.TIERS`), pas en base : seuls les montants se modifient depuis l'écran. Cela évite toute grille incohérente.
2. **Actions sur la grille absentes du journal d'audit** : `audit_logs` exige une école. Elles sont tracées par `created_by`, `activated_by`, `activated_at` et `archived_at`.
3. **Compteur de numérotation sans RLS** : il ne contient aucune donnée d'école.
4. **Expiration des factures différée** (au moment où une nouvelle facture est demandée) et **calculée à la lecture** : une facture dont la validité est dépassée s'affiche « Expirée » et n'est plus payable. La tâche quotidienne relève du lot C.
5. **Paiement manuel** : il refuse une facture expirée, même si un virement est arrivé en retard ; l'école émet alors une nouvelle facture. La période commence à la date d'enregistrement, pas à la date de réception des fonds.
6. **Vue plateforme par école** : l'état étant calculé, toutes les écoles sont chargées puis paginées en mémoire. C'est adapté à l'échelle pilote, à revoir au-delà de quelques milliers d'écoles.

## 8. Mise en service (après validation des tests et sur autorisation)

Procédure détaillée, commune aux lots A et C et aux migrations 0024 à 0026 non encore déployées :
[`docs/deployment/PHASE_29_PRODUCTION_RUNBOOK.md`](../deployment/PHASE_29_PRODUCTION_RUNBOOK.md).
En résumé :

1. Sauvegarde de la base, puis `alembic upgrade head` (migration 0027).
2. Fixer `SUBSCRIPTION_LAUNCH_DATE` dans l'environnement du conteneur `api`.
3. Exécuter une première fois `python -m app.jobs.grant_free_quarters`, puis installer le timer `edusphere-grant-free-quarters.timer`.
4. Créer puis activer la grille réelle depuis `/platform/subscription-grids`. Tant qu'aucune grille n'est active, les écoles ne peuvent pas émettre de facture, sauf les devis.

## 9. Lots suivants

- **Lot B** : paiement Mobile Money via PayGate Global. Il faut d'abord lire le guide d'intégration et placer le jeton marchand sur le serveur (cadrage §4.3 et §18.2).
- **Lot C** : rappels (J-30, J-7, J0), reçus, expiration automatique des factures.
