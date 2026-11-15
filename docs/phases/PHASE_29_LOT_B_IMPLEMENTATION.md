# Phase 29 — Lot B : paiement des abonnements par Mobile Money (PayGate Global)

- **Cadrage** : `docs/phases/PHASE_29_SCHOOL_SUBSCRIPTIONS_DISCOVERY.md`, §4, §5.5, §5.8, §9 à §15.
- **Source PayGate** : guide d'intégration du tableau de bord marchand, transmis le 2026-11-15 **sans la clé API**.
- **Branche** : `feat/school-subscriptions-lot-b`, partie de `main` (`01c1a1c`). Les lots A et C sont en production depuis le 2026-11-13.
- **Statut** : code écrit et testé localement (§6). La mise en service se fait coupe-circuit **inactif**, puis il est activé après un vrai paiement test (§8).

## 1. Ce que le guide a tranché

| Point bloquant du cadrage (§4.3) | Réponse du guide | Décision |
|---|---|---|
| 1. URL et paramètres | Méthode directe : `POST https://paygateglobal.com/api/v1/pay`, JSON `auth_token`, `phone_number`, `amount`, `description`, `identifier`, `network` (`FLOOZ` ou `TMONEY`). | Implémentée telle quelle. |
| 2. La clé apparaît-elle dans l'URL de la page hébergée ? | **Oui** : `/v1/page?token=VOTRE_CLE_API&…`, de même pour le « Checkout » (`/checkout?token=…`). | Critère éliminatoire : **redirection et Checkout écartés**, seule la méthode directe est utilisée. La clé ne quitte jamais le serveur. |
| 3. Notification | « Callback URL » réglée **dans le profil** PayGate ; JSON `tx_reference`, `identifier`, `amount`, `payment_method`. Le guide recommande de « toujours vérifier l'état final via l'API de consultation ». | Elle ne fait jamais foi : elle déclenche seulement une vérification d'état. |
| 4. États et codes | Vérification `POST /api/v1/status` (par `tx_reference`) ou `/api/v2/status` (par `identifier`) : 0 réussi, 2 en cours, 4 expiré, 6 annulé. | `/api/v2/status` avec **notre** `identifier` : c'est la seule source de vérité. |
| 5. Règles de `identifier` | Non précisées. | `EL` + 20 caractères hexadécimaux aléatoires (80 bits), majuscules, sans séparateur. |
| 6. Plafond | Non précisé. | Réglable : `PAYGATE_MAX_AMOUNT`, 1 000 000 FCFA par défaut (valeur des intégrations existantes). |
| 7. Validité d'une demande | Non précisée (code 4 « expiré »). | Délai local réglable : `PAYGATE_PENDING_TIMEOUT_MINUTES`, 15 minutes par défaut. |
| 8. Signature, secret, liste d'adresses IP | Aucune signature pour la notification. Le guide impose une liste blanche d'adresses IP pour la consultation du solde et, si une IP est déclarée, pour le renouvellement de la clé. | Recommandation : déclarer l'adresse du serveur (`82.25.116.196`) dans le profil PayGate (§8, étape 5). |

**Non décrit par le guide officiel**, repris des intégrations existantes et **à confirmer par le premier paiement réel** (§7) :
- la réponse de `/api/v1/pay`, soit `tx_reference` et `status` (0 enregistré, 2 clé invalide, 4 paramètres invalides, 6 doublon) ;
- le format de `phone_number` : 8 chiffres locaux ;
- l'envoi de la notification pour la méthode directe : les sources se contredisent, d'où la tâche de rapprochement qui fonctionne sans elle.

## 2. Déroulement d'un paiement

1. **Lancement** par un compte `subscriptions.pay` (administrateur de l'école), depuis la page « Abonnement » : réseau (Flooz ou T-Money) et numéro. Le serveur contrôle, sous le verrou de l'école puis de la facture :
   - le coupe-circuit, l'école et la facture : émise, non expirée ;
   - le plafond ;
   - l'idempotence ;
   - l'absence de tentative en cours, sinon il la renvoie.

   Il crée ensuite la tentative `INITIATED` et **la valide en base avant d'appeler PayGate**. Une panne pendant l'appel laisse ainsi une trace, que le rapprochement retrouve.
2. **Appel `/api/v1/pay`**, hors transaction et hors verrou. Le montant est le total de la facture, fixé par le serveur.
   - Demande acceptée, ou issue inconnue (délai dépassé, réponse illisible, doublon) : la tentative passe en `PENDING`.
   - Refus définitif (clé invalide, paramètres invalides, requête rejetée en 4xx) : elle passe en `FAILED`, et l'école peut réessayer aussitôt.

   Une erreur ne produit jamais un faux échec sur un paiement qui aurait pu aboutir.
3. **Vérification d'état** (`/api/v2/status`), déclenchée de trois façons :
   - l'écran de l'école, toutes les 5 secondes pendant 3 minutes ; le serveur limite à une vérification toutes les 10 secondes ;
   - la notification de PayGate, qui lance la vérification après la réponse ;
   - la tâche de rapprochement, toutes les 5 minutes.
4. **Application**, sous le verrou de l'école, puis de la facture, puis de la tentative relue `FOR UPDATE`. C'est toujours une opération système (acteur système dans l'audit) :
   - **réussi**, montant égal (s'il est fourni) et facture toujours `ISSUED` : tentative `SUCCEEDED`, facture `PAID`, période créée, audit `subscription_payment.confirmed`, notification « Abonnement payé » à l'administrateur et au directeur. Le reçu PDF porte la référence de l'opérateur ;
   - **réussi, mais montant différent ou facture déjà payée, annulée ou expirée** : `ANOMALY`, audit `subscription_payment.anomaly`, signalement à la plateforme (§5.8 du cadrage) ;
   - **expiré ou annulé** chez PayGate : `EXPIRED` ou `FAILED` ;
   - **en cours ou inconnu** au-delà du délai local : `EXPIRED` avec le code `TIMEOUT_LOCAL`. L'école peut réessayer. La tentative reste vérifiable jusqu'à J+7, avec une dernière vérification par la tâche à J+1 ; un succès tardif est confirmé si la facture attend toujours son paiement, sinon il devient une anomalie.

Une notification et la tâche simultanées ne créent qu'**une seule** période. Le test l'exerce avec quatre vérifications concurrentes.

## 3. Ce qui est livré

**API** (`apps/api`)

| Élément | Rôle |
|---|---|
| `app/core/online_payment.py` | Abstraction `OnlinePaymentProvider`, avec deux implémentations : `PayGateProvider` (bibliothèque standard, transport injectable) et `FakeOnlinePaymentProvider` (aucun appel réseau). |
| `app/modules/subscriptions/online_payments.py` | Lancement, vérification et application, journal des notifications, rapprochement. |
| `POST /school-subscription/invoices/{invoice_id}/payments` | `subscriptions.pay`. Corps : `network`, `phone_number`, `idempotency_key`. Limité par le compteur des mutations financières. |
| `GET /school-subscription/payments/{payment_id}` | `subscriptions.read`. État d'une tentative, revérifiée si elle est en cours. |
| `POST /payment-providers/paygate/callback` | Public. Réponse toujours `{"status": "ok"}`. Limité en débit, corps limité à 8 Ko, JSON ou formulaire. |
| Migration `0029` | Table `payment_provider_callbacks` : journal minimal, RLS « plateforme seulement ». |
| `app/jobs/subscription_payments_reconcile.py` | Tâche de rapprochement, avec `deploy/systemd/edusphere-subscription-payments-reconcile.{service,timer}`, toutes les 5 minutes. |
| Notification `SUBSCRIPTION_PAYMENT_CONFIRMED` | Paiement confirmé. Aucune migration : `notifications.type` n'a pas de contrainte CHECK. |
| Audit | `subscription_payment.online_initiated`, `.confirmed`, `.failed`, `.anomaly`. |
| `SchoolSubscriptionOut` | Ajoute `online_payment_enabled` et `online_payment_max_amount`. `PaymentOut` ajoute `payer_phone_last4`. |

**Lots A et C ajustés** (`service.py`), pendant qu'une tentative est en cours :
- la facture n'est pas expirée, ni à la demande d'une nouvelle facture ni par la tâche quotidienne, puisque le paiement a été lancé pendant sa validité ;
- une nouvelle facture est refusée (409) tant que la tentative sur la facture échue n'a pas abouti ;
- l'annulation de la facture et le paiement manuel sont refusés (409).

**Web** (`apps/web`)
- **Page « Abonnement »** : panneau « Payer par Mobile Money » (`components/subscriptions/OnlinePaymentPanel.tsx`).
  - Saisie : réseau et numéro.
  - Suivi : demande envoyée au numéro se terminant par …, puis vérification automatique, reprise d'une tentative en cours au rechargement, et message adapté à l'échec, à l'anomalie ou au succès.
  - Hors panneau : un plafond dépassé renvoie au paiement par EduLinkage, et les comptes non autorisés ne voient qu'un message d'information.
- **Page plateforme « Factures d'abonnement »** : colonne « Mobile Money », avec la dernière tentative et les anomalies à traiter en rouge.
- **Notifications** : libellé « Abonnement payé ».

## 4. Sécurité

- **Clé API PayGate** : variable `PAYGATE_AUTH_TOKEN`, seulement dans le `.env` du serveur de production.
  - Elle n'est transmise à PayGate que dans le **corps** des requêtes.
  - Elle n'est jamais journalisée et ne remonte jamais dans une erreur : les erreurs deviennent des codes courts (`TIMEOUT`, `HTTP_502`…). Un test le vérifie.
  - Le démarrage est refusé en production si le coupe-circuit est actif sans clé, ou avec le fournisseur `fake`.
- **La notification n'est pas signée** : elle ne fait jamais foi. Seule la vérification d'état faite par le serveur, avec notre identifiant aléatoire, confirme un paiement.
  - La réponse est uniforme : elle ne révèle ni l'existence d'un identifiant ni un état.
  - Un identifiant inconnu est simplement journalisé.
- **Montant** : fixé par le serveur, jamais par le navigateur.
- **Données personnelles** :
  - seuls les 4 derniers chiffres du numéro sont conservés ;
  - ni numéro complet ni corps intégral de notification dans `payment_provider_callbacks` ;
  - l'adresse IP enregistrée est celle déclarée par le proxy : simple diagnostic.
- **Isolation** :
  - contrôle applicatif de l'école, puis RLS ;
  - le journal des notifications est invisible pour les comptes d'école, ce qu'un test vérifie.

## 5. Écarts au cadrage

- **Aucune dépendance de production nouvelle.** Le cadrage prévoyait `httpx`, mais celui-ci n'est installé que pour les tests (`requirements-dev.txt`). Les appels utilisent donc `urllib.request` dans un thread, comme l'envoi de SMS (`app/core/sms.py`).
- **Montant dans la vérification** : le cadrage exigeait de le comparer. Le guide officiel ne le renvoie pas. Il est comparé **s'il est présent** ; sinon, c'est le montant fixé par le serveur à l'envoi qui fait foi.
- **Délai local de 15 minutes** (réglable) au lieu du délai PayGate, que le guide ne publie pas.
- **Tâche toutes les 5 minutes** au lieu de 10, pour libérer plus vite une facture après ce délai.
- **Table `payment_provider_callbacks`** : deux colonnes ajoutées au cadrage, `declared_amount` (diagnostic) et `payment_id`.
- **Notification de confirmation** : nouveau type `SUBSCRIPTION_PAYMENT_CONFIRMED`.

## 6. Tests

| Fichier | Contenu | Exécution locale (2026-11-15) |
|---|---|---|
| `tests/test_online_payment_provider.py` (26 tests) | Requêtes exactes vers `/api/v1/pay` et `/api/v2/status` ; interprétation de chaque code et de chaque erreur (jamais de faux échec) ; clé API absente des journaux ; simulateur ; refus au démarrage en production. | **26/26** |
| `tests/test_subscriptions_lot_b.py` (15 tests) | Voir la liste ci-dessous. | **15/15** (PostgreSQL 16.16 local, migrations 0001 à 0029) |
| `tests/test_pr17_hardening.py` | Liste exacte des routes « subscription » étendue aux deux routes d'école ; interdiction des commissions inchangée. | voir §6 bis |

Cas couverts par `tests/test_subscriptions_lot_b.py` :
- coupe-circuit inactif par défaut ; numéros invalides refusés ;
- succès par la notification, une seule fois, puis notification répétée sans effet ; reçu et notification « Abonnement payé » ;
- succès par la tâche seule ; succès par le rafraîchissement de l'écran ;
- notifications falsifiées sans effet, et journal invisible pour l'école (RLS) ;
- montant différent : `ANOMALY` ;
- notification, tâche et deux vérifications simultanées : une seule période ;
- délai local, puis succès tardif à J+1 ;
- succès sur une facture déjà payée à la main : `ANOMALY` ;
- refus puis nouvel essai ; issue inconnue qui reste en cours ;
- idempotence et tentative unique ; plafond ;
- tentative en cours qui bloque l'annulation, le paiement manuel, l'expiration et une nouvelle facture ;
- droits et isolation : directeur en lecture seule, enseignant, autre organisation.

**Web** : `tsc --noEmit` et `next lint` sans erreur.

### 6 bis. Non-régression

Le 2026-11-15, sur la même base locale (migration `0029` appliquée), **55 tests sur 55 passent**. Fichiers exécutés :
- `tests/test_subscriptions.py` (lot A) ;
- `tests/test_subscriptions_lot_c.py` ;
- `tests/test_subscriptions_pricing.py` ;
- `tests/test_notifications.py` ;
- le test de garde `test_no_commission_engine_and_only_expected_subscription_objects_exist`.

La suite complète tourne dans la CI GitHub.

## 7. À confirmer par le premier paiement réel

Il n'existe ni environnement de test PayGate ni remboursement par l'API (cadrage §15). Le premier paiement réel, d'un petit montant, confirme :
1. que PayGate accepte `phone_number` sur 8 chiffres ;
2. la forme réelle de la réponse de `/api/v1/pay` : la tentative doit passer en « En attente de confirmation », et non en « Échoué » ;
3. l'arrivée de la notification. Dans `payment_provider_callbacks`, une ligne `CHECK_SCHEDULED` doit apparaître ; si rien n'arrive, la tâche confirme quand même dans les 5 minutes ;
4. la confirmation (`SUCCEEDED`), la période, le reçu et la notification ;
5. le montant effectivement reçu sur le solde PayGate, net des frais (2,5 % Flooz, 3 % T-Money).

## 8. Mise en service

À faire **après la fusion** et la CI verte, dans la console du serveur, depuis `/opt/edusphere`. Les commandes reprennent la procédure du 13 novembre (`docs/deployment/PHASE_29_PRODUCTION_RUNBOOK.md`). Le site n'est coupé qu'à l'étape 3.

1. **Code** :
   ```sh
   git fetch https://github.com/atchakimededebodjona-design/edusphere.git main:refs/remotes/origin/main
   git merge --ff-only origin/main
   docker tag edusphere-api:latest edusphere-api:avant-lot-b
   docker tag edusphere-web:latest edusphere-web:avant-lot-b
   docker compose build api web > /tmp/build-lot-b.log 2>&1; echo "construction : code $?"
   ```
2. **Sauvegarde** : `scripts/db-backup.sh`.
3. **Migration et redémarrage**, coupe-circuit **inactif**. Le `.env` ne change pas encore : les valeurs par défaut sont « désactivé » et `fake`.
   ```sh
   docker compose stop web api
   docker compose run --rm --no-deps api alembic upgrade head
   docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -v ON_ERROR_STOP=1 -f -' < scripts/release/phase29b-postcheck.sql
   docker compose up -d api web
   ```
   Le contrôle doit afficher **7 lignes OK** avant `up -d`. Sinon, ne pas redémarrer la nouvelle version : revenir aux images `avant-lot-b`. La migration est additive, et l'ancienne API ignore la nouvelle table.
4. **Tâche de rapprochement** :
   ```sh
   install -m 0644 deploy/systemd/edusphere-subscription-payments-reconcile.service deploy/systemd/edusphere-subscription-payments-reconcile.timer /etc/systemd/system/
   systemctl daemon-reload
   systemctl enable --now edusphere-subscription-payments-reconcile.timer
   ```
5. **Profil PayGate**, dans le tableau de bord marchand :
   - « Callback URL » : `https://api.edulinkage.com/api/v1/payment-providers/paygate/callback` ;
   - si le profil le permet, déclarer l'adresse IP du serveur, `82.25.116.196`.
6. **Clé et activation**. **L'exploitant seul** ajoute ces lignes au `.env`, et **ne les transmet à personne** :
   ```
   PAYMENT_ONLINE_PROVIDER=paygate
   PAYGATE_AUTH_TOKEN=<clé copiée depuis le profil PayGate>
   SUBSCRIPTION_ONLINE_PAYMENT_ENABLED=true
   ```
   Ensuite :
   - `docker compose up -d api` ;
   - `docker compose ps` doit afficher l'API `healthy`. Si l'API refuse de démarrer, la clé ou le fournisseur manque.
7. **Paiement test réel**, d'un petit montant, sur une facture dédiée. Il passe par une grille de test, ou par une facture émise pour l'école la plus petite après accord de la direction. Vérifier les points du §7, puis contrôler l'état :
   ```sh
   docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -v ON_ERROR_STOP=1 -f -' < scripts/release/phase29-state.sql
   ```
8. **En cas de problème** :
   - remettre `SUBSCRIPTION_ONLINE_PAYMENT_ENABLED=false`, puis `docker compose up -d api`. Le paiement manuel reste toujours disponible, et les tentatives en cours reprendront à la réactivation ;
   - une anomalie se règle depuis le tableau de bord PayGate (remboursement manuel), avec une trace dans le journal d'audit.
