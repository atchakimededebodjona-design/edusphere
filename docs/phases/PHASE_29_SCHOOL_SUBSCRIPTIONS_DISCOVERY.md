# Phase 29 Discovery — Abonnements des écoles et paiement Mobile Money (PayGate Global)

- **Statut** : cadrage. **Aucun code, aucune migration, aucun test** n'a été écrit ou exécuté.
- **Date** : 2026-11-12.
- **Mise à jour** : 2026-11-12, ajout du trimestre gratuit (§5.4 bis).
- **Numéro de phase** : provisoire. Le code existant appelle ce chantier « PR #18 ». Or la PR #18 réellement fusionnée sur GitHub (commit `0befcce`) portait sur le comptage des élèves. Ce document propose donc un nom propre.
- **Emplacement** : provisoire, sur D:, tant que le dépôt et Docker sont sur C:, qui se dégrade. Ce fichier pourra ensuite être copié dans `docs/phases/`.

## 1. Résumé

**Objectif.** Chaque école s'abonne à EduLinkage pour 3, 6 ou 12 mois et paie en ligne par Mobile Money (Flooz, T-Money), via PayGate Global.

**Calcul du prix.** Le prix vient d'une grille : un forfait de base, plus un supplément selon la tranche d'effectif. L'effectif et le prix sont figés sur la facture.

**Trimestre gratuit.** Chaque école reçoit, une seule fois, une première période gratuite de 3 mois, sans facture (§5.4 bis).

**En cas d'impayé.** L'application affiche l'état de l'abonnement et envoie des rappels. Elle ne bloque jamais l'accès.

**Commissions des partenaires.** Elles sont reportées à un chantier ultérieur.

**Constats.**

1. **Des pièces existent déjà, mais aucune logique.** Le dépôt contient :
   - la permission `platform.subscriptions.read` ;
   - le nombre d'élèves actifs par école ;
   - la source d'acquisition de chaque école ;
   - une abstraction de paiement, limitée au paiement manuel.

   Il n'y a ni table, ni endpoint, ni écran d'abonnement. Un test vérifie même leur absence (§3).
2. **La documentation technique de PayGate Global n'est pas publique.** Elle se trouve dans le « guide d'intégration » du tableau de bord marchand. Les détails d'API cités ici viennent de sources tierces **non vérifiées**. Il faut les confirmer avant le lot B (§4).
3. **La confirmation de paiement de PayGate n'est pas signée,** d'après les sources consultées. Un paiement ne sera donc jamais considéré comme acquis sur la seule foi de cette notification. Le serveur interroge toujours lui-même PayGate (§5.5, §9).
4. **Pas d'environnement de test chez PayGate,** d'après une source tierce, **et pas de remboursement par l'API.** Les tests automatiques utiliseront un faux fournisseur. La validation réelle se fera en production, sur un petit montant et avec autorisation (§15).
5. **Un plafond de montant par transaction est probable,** de l'ordre de 1 000 000 FCFA d'après les sources tierces. Une facture annuelle de grande école pourrait le dépasser. Un paiement manuel de secours est donc nécessaire (§5.6).

**Découpage recommandé en trois lots** (§17) :
- **A** : grille, factures, trimestre gratuit, périodes et paiement manuel, sans PayGate ;
- **B** : paiement PayGate ;
- **C** : rappels et reçus.

## 2. Décisions déjà prises

| Sujet | Décision | Source |
| --- | --- | --- |
| Qui s'abonne | L'école, pas l'organisation | Utilisateur, 2026-11-12 |
| Modèle de prix | Forfait de base + supplément par tranche d'effectif | Grille du 2026-11-09 |
| Tranches | 1 à 100 : base ; 101 à 250 : base + tranche 1 ; 251 à 500 : base + tranche 2 ; 501 à 1 000 : base + tranche 3 ; plus de 1 000 : tarif adapté | Grille du 2026-11-09 |
| Durées | 3, 6 ou 12 mois | Grille du 2026-11-09 |
| Figé sur la facture | Effectif et prix | Grille du 2026-11-09 |
| Montants | **Fictifs, non définitifs** | Grille du 2026-11-09 |
| Moyen de paiement | En ligne, par Mobile Money | Utilisateur, 2026-11-12 |
| Fournisseur | PayGate Global | Utilisateur, 2026-11-12 |
| Impayé | Rappels seulement, aucun blocage | Utilisateur, 2026-11-12 |
| Commissions partenaires | Plus tard, chantier séparé | Utilisateur, 2026-11-12 |
| Gratuité | Un trimestre gratuit (3 mois) par école, une seule fois | Utilisateur, 2026-11-12 |
| Écoles déjà en service | Elles ont aussi droit au trimestre gratuit, à partir de la date de lancement de la facturation | Utilisateur, 2026-11-12 |

## 3. État réel du dépôt (lecture du 2026-11-12, branche `main`, commit `9e6c990`)

### 3.1 Ce qui existe

**Permissions et rôles**
- Permission `platform.subscriptions.read` : « Consulter les abonnements SaaS des organisations ». Elle est attribuée à SUPER_ADMIN et PLATFORM_OWNER, sans aucun endpoint (`apps/api/app/modules/rbac/seed.py:209`, migration `0023`).
- `platform.commissions.read` et `partner.commissions.read` sont réservées aux commissions et restent hors de ce chantier.
- Rôles d'école existants (`seed.py:8-19`) : SCHOOL_ADMIN, DIRECTOR, ACCOUNTANT, TEACHER, STAFF, PARENT, STUDENT. S'y ajoute CAISSIER (migration `0025`).
- Rôles plateforme (`rbac/models.py:18`) : SUPER_ADMIN, PLATFORM_SUPPORT, PLATFORM_OWNER.

**Données disponibles**
- **Effectif.** `active_student_count` par école est déjà calculé côté plateforme, par simple comptage. Il reprend exactement la définition du tableau de bord d'école (`Student.status == "ACTIVE"`). Le code le désigne explicitement comme « base envisagée pour la tarification SaaS » (`apps/api/app/modules/platform/schemas.py:119-124`, `platform/service.py::student_counts_by_school`).
- **Origine de l'école.** `partner_school_enrollments` (migration `0023`) donne pour chaque école sa source (`PLATFORM_OWNER` ou `PARTNER`) et `commission_eligible`. Ce sera utile au futur chantier des commissions ; rien n'y est modifié ici.
- **Devise et fuseau.** `School.currency` et `Organization.currency` valent `XOF` par défaut. `School.timezone` vaut `Africa/Lome` par défaut.

**Briques techniques réutilisables**
- **Paiement.** `apps/api/app/core/payment.py` définit `PaymentProvider` avec une seule implémentation, `ManualPaymentProvider`. Il n'existe aucune intégration Mobile Money. Son interface (`record(amount, method, reference)`) acte un paiement déjà saisi. Elle ne convient pas à un paiement en ligne asynchrone (§5.5).
- **Isolation entre organisations.** Chaque table d'école porte `school_id` et `organization_id`, avec la politique RLS générique `{table}_tenant_isolation`. Le modèle le plus récent est la migration `0026` (caisse).
- **Contexte plateforme.** `core/tenancy.py::set_platform_wide_context` est réservé aux opérations système sans utilisateur authentifié, ou aux lectures `/partner/*` filtrées par une liste blanche.
- **Configuration.** `core/config.py` fournit :
  - un coupe-circuit sur le modèle de `sms_enabled=False` ;
  - un fournisseur HTTP générique, `sms_http_*` ;
  - `public_base_url` ;
  - un contrôle au démarrage qui refuse les secrets par défaut et les URL locales en production.
- **Notifications et rappels.**
  - Les notifications internes à l'application (`notifications`) ont un `type` libre, sans contrainte CHECK en base (migration `0013`).
  - Les rappels idempotents par étape suivent le modèle des frais en retard (migration `0021`).
  - Les tâches planifiées suivent `app/jobs/overdue_fee_reminders.py`, avec le timer systemd `deploy/systemd/edusphere-overdue-reminders.timer`.
- **Reçus.** Les reçus des frais sont générés en HTML (`apps/api/app/modules/fees/service.py:444`, `_render_receipt_html` ; `fees/router.py:326`, `download_receipt`).
- **Journal d'audit.** Module `audit` : `action` et `entity_type` sont des chaînes libres (migration `0020`).
- **Écrans web.** Ils sont dans `apps/web/app/(app)/` : `platform/` (comptes, organisations, partenaires, écoles), `partner/`, `school/`, `fees/`, `cashier/`.
- **Client HTTP.** `httpx` figure déjà dans `apps/api/pyproject.toml`.

**Production**
- `https://api.edulinkage.com` répond en HTTPS derrière nginx, d'après une vérification externe du 2026-10-18 (`docs/deployment/PRODUCTION_CONFIGURATION.md`).
- La configuration interne de nginx n'a pas été inspectée.

### 3.2 Ce qui manque ou bloque

**Ce qu'il faut construire**
- Les tables, endpoints, écrans et tâches planifiées de l'abonnement.
- Toute notion de statut d'école ou d'organisation. Ce n'est pas un problème ici, puisque l'impayé ne bloque rien.

**Le test de garde existant**
- `apps/api/tests/test_pr17_hardening.py:690`, `test_no_commission_engine_tables_or_routes_exist`, vérifie qu'aucune table ni route ne contient `subscription`, `commission`, `payout` ou `ledger`.
- Il échouera dès le lot A. Il faudra le **remplacer par un contrôle plus précis**, sans l'affaiblir (§16).

**Un manque de cohérence**
- Phase 19 a explicitement exclu « l'abonnement SaaS d'EduSphere envers l'école elle-même » (`docs/phases/PHASE_19_DISCOVERY.md`, §31). Il doit rester **séparé** du module `fees`, qui concerne l'école facturant ses élèves.
- Aucune table de `fees` ni de `cash` n'est réutilisée pour l'abonnement.

## 4. PayGate Global : ce qui est établi et ce qui reste à confirmer

### 4.1 Sources officielles (site public `paygateglobal.com`, lu le 2026-11-12)

**Le service**
- Éditeur : BHK Konsulting SARL, à Lomé.
- Paiement par **Flooz et T-Money uniquement**, en **FCFA uniquement**. La carte bancaire est annoncée « en cours ».
- Ouverture de compte et accès à l'API gratuits.

**Coûts et versements**
- Commission : **2,5 % sur Flooz, 3 % sur T-Money**. PayGate peut modifier ses commissions unilatéralement (CGU A.8).
- Solde Flooz disponible à J+1 depuis le tableau de bord.
- Solde T-Money versé par PayGate **tous les 10 jours**, net de frais.

**L'intégration**
- Activation : le compte doit fournir une carte d'entreprise ou une carte fiscale, une pièce d'identité, une description du projet et un « lien de retour ».
- **Les URL de l'API et les méthodes d'intégration se trouvent dans le « guide d'intégration » du tableau de bord marchand,** pas sur le site public.
- Il existe deux mécanismes :
  - une URL de **retour**, qui ramène le client vers l'application ;
  - une URL de **rappel** (« Callback URL »), qui envoie la confirmation au serveur du marchand sans être montrée au client.

**Conditions générales**
- Le marchand indemnise PayGate pour les annulations après coup, les trop-perçus et les erreurs (B.4).
- Le service est fourni « en l'état », sans garantie de disponibilité. Des maintenances des opérateurs sont possibles (B.5).
- PayGate peut retenir une réserve sur les paiements (B.6).

### 4.2 Sources tierces (non vérifiées, à confirmer dans le guide d'intégration)

**Méthodes d'intégration**
- Deux méthodes existent :
  - **v1, paiement direct** : le serveur envoie une requête POST avec le numéro du payeur et le réseau ;
  - **v2, page de paiement hébergée par PayGate** : le client est redirigé, puis ramené par l'URL de retour.
- D'après une source, la notification de paiement (rappel) n'est envoyée **qu'en v2**.

**Contenu de la notification et vérification**
- Champs de la notification : `tx_reference`, `identifier`, `payment_reference`, `amount`, `datetime`, `phone_number`, `payment_method`.
- **Aucune signature, aucun secret ni liste d'adresses IP n'est documenté.** Une source indique « contrôle de présence des champs, pas de HMAC ».
- Il existe une vérification d'état par `tx_reference` ou par `identifier`, l'identifiant choisi par le marchand.

**Limites**
- Montant : de 1 ou 100 FCFA à 1 000 000 FCFA, selon la source.
- **Pas d'environnement de test** (« PayGate does not have sandbox »).
- **Pas de remboursement ni d'annulation par l'API** : ils se font manuellement depuis le tableau de bord.
- Numéros au format `228` suivi de 8 chiffres.

**Codes d'état**
- Une source publie 0 (succès), 2, 4 et 6. Son tableau est **incohérent** : la même ligne mélange des états (« en attente », « expiré », « annulé ») et des erreurs (« jeton invalide », « paramètres invalides », « doublon »).
- Il ne faut **rien coder** sur ces valeurs avant lecture du guide officiel.

### 4.3 À lire dans le guide d'intégration avant le lot B (bloquant)

1. URL, méthodes HTTP et noms exacts des paramètres pour v1 et pour v2.
2. **En v2 : le jeton marchand apparaît-il dans l'URL de la page hébergée ?** Si oui, il serait visible dans le navigateur de l'école, son historique et les journaux intermédiaires.
   - **Critère éliminatoire** : le jeton ne doit jamais sortir du serveur. Dans ce cas, il faut utiliser v1.
3. Où se configure l'URL de notification : dans le tableau de bord ou dans chaque requête ? La notification existe-t-elle en v1 ?
4. Liste exacte des états et codes de retour, pour le paiement et pour la vérification d'état.
5. Règles d'unicité de `identifier` : longueur et caractères admis.
6. Plafond par transaction, et plafonds éventuels des portefeuilles des payeurs.
7. Durée de validité d'une demande de paiement avant expiration.
8. Une éventuelle signature, un secret ou une liste d'adresses IP pour les notifications.

## 5. Modèle métier

### 5.1 Grille de prix

- Elle est **stockée en base** et modifiable par le propriétaire de la plateforme (PLATFORM_OWNER), **sans modification de code.** Les montants fictifs seront remplacés par les vrais.
- Elle est **versionnée** :
  - une grille ACTIVE à la fois ;
  - les anciennes sont ARCHIVÉES, jamais modifiées ni supprimées ;
  - une grille DRAFT reste modifiable.

  Une facture référence la version qui a servi à la calculer.
- Elle contient une ligne par couple (tranche, durée), soit **4 tranches × 3 durées = 12 lignes**. Chaque ligne indique :
  - les bornes d'effectif ;
  - le montant de base pour cette durée ;
  - le supplément de la tranche pour cette durée, à 0 pour la tranche de base.
- Avoir des montants distincts par durée permet une remise sur 6 ou 12 mois, si vous le souhaitez, sans formule. Voir la question Q1.
- Au-delà de 1 000 élèves, aucune ligne ne s'applique : la facture passe en **devis** (§5.2).
- Montants en **FCFA entiers** : le XOF n'a pas de centimes, et PayGate ne traite que le FCFA. Une contrainte CHECK impose des montants entiers.

### 5.2 Calcul d'une facture

**Entrées**
- L'école, choisie par l'utilisateur et vérifiée par le serveur.
- La durée choisie, parmi 3, 6 et 12.
- **Rien d'autre ne vient du client.** Le montant n'est jamais transmis par le navigateur.

**Calcul**
1. Effectif : nombre d'élèves `ACTIVE` de l'école au moment de l'émission. C'est la définition existante (§3.1).
2. Tranche :

   | Effectif | Tranche |
   | --- | --- |
   | 0 à 100 | 0 (base) |
   | 101 à 250 | 1 |
   | 251 à 500 | 2 |
   | 501 à 1 000 | 3 |
   | Plus de 1 000 | Devis |

   Une école sans élève actif paie le forfait de base.
3. Si la tranche donne un prix : `total = base[durée] + supplément[tranche][durée]`.
4. Pour un devis, la facture est créée au statut `QUOTE_REQUIRED`. Le propriétaire de la plateforme saisit ensuite le montant ; l'école ne peut pas payer avant.

**Données figées sur la facture**
- l'effectif et la tranche ;
- la version de la grille ;
- la base, le supplément et le total ;
- la durée et la devise `XOF`.

Un changement d'effectif en cours de période ne modifie rien. Il sera pris en compte au renouvellement, comme décidé.

**Validité de la facture**
- Une facture émise et non payée **expire après 30 jours** par défaut (question Q6), puisque l'effectif y est figé. L'école en émet alors une nouvelle.
- Pour éviter les doublons, il ne peut y avoir **qu'une facture ouverte par école** : statut `ISSUED` ou `QUOTE_REQUIRED`. Une contrainte UNIQUE partielle le garantit.

### 5.3 Cycle de vie d'une facture

```
QUOTE_REQUIRED --(montant saisi par la plateforme)--> ISSUED
ISSUED --(paiement confirmé)--> PAID
ISSUED --(30 jours sans paiement)--> EXPIRED
ISSUED | QUOTE_REQUIRED --(annulation par la plateforme, motif obligatoire)--> CANCELLED
```

- Une facture payée n'est jamais annulée ni modifiée. Une correction après paiement relève d'un traitement manuel ; les avoirs sont hors périmètre.
- **Numérotation** : séquentielle, unique et sans trou, par exemple `EL-2026-000001`, attribuée à l'émission. Les mentions légales et la TVA restent à valider (question Q8).

### 5.4 Période d'abonnement et état de l'école

**Création d'une période payée**
- Elle est créée **une seule fois**, au moment où le paiement est confirmé.
- **Début** :
  - sans période en cours, c'est la date de confirmation ;
  - sinon, c'est le lendemain de la fin de la période en cours, qu'elle soit payée ou gratuite. Un renouvellement anticipé ne fait donc rien perdre.
- **Fin** : début + N mois − 1 jour. Elle est calculée dans le fuseau de l'école (`School.timezone`).
- **Fin de mois** : si le jour n'existe pas dans le mois d'arrivée, on prend le dernier jour du mois. Par exemple, le 31 janvier + 1 mois donne le 28 ou le 29 février. Cette règle doit être couverte par des tests.

**État affiché de l'école**

| État | Condition |
| --- | --- |
| `NONE` | Aucune période : trimestre gratuit pas encore attribué |
| `TRIAL` | La date du jour est dans le trimestre gratuit |
| `ACTIVE` | La date du jour est dans une période payée |
| `EXPIRING_SOON` | La période en cours, gratuite ou payée, se termine dans 30 jours ou moins, sans période suivante déjà payée |
| `EXPIRED` | Plus aucune période en cours |

- Cet état est **calculé à la lecture**, sans colonne de statut stockée.
- **Il ne bloque rien**, conformément à la décision « rappels seulement ».

### 5.4 bis Trimestre gratuit

Décision du 2026-11-12 : chaque école a droit à un trimestre gratuit.

**Règles** (validées le 2026-11-12 ; seule la date de lancement reste à fixer, voir la question Q7)
- **Une seule fois par école**, jamais renouvelé. Une contrainte UNIQUE partielle le garantit en base.
- **Durée** : 3 mois. Les règles de dates sont celles d'une période payée : fin = début + 3 mois − 1 jour, fuseau de l'école, fins de mois.
- **Date de début** :
  - **école déjà en service** : la date de lancement de la facturation (`SUBSCRIPTION_LAUNCH_DATE`), que vous fixez. Une école ancienne ne perd donc pas son trimestre gratuit du seul fait de son ancienneté ;
  - **école créée après cette date** : sa date de création.

  Autrement dit : début = la plus tardive des deux dates.
- **Ni facture, ni effectif figé, ni paiement.** C'est une période de type `FREE_TRIAL`, sans `invoice_id`.
- **Paiement anticipé possible.** Une école peut s'abonner pendant son trimestre gratuit. Sa période payée commence alors le lendemain de la fin du trimestre gratuit (règle de continuité ci-dessus).
- **Fin du trimestre gratuit** : mêmes rappels qu'une période payée (§5.7), aucun blocage.

**Attribution sans modifier la création d'école**
- Une école peut être créée par plusieurs chemins : par la plateforme, par un partenaire, ou dans une organisation à plusieurs écoles. Plutôt que de modifier chacun d'eux, une commande idempotente, `app/jobs/grant_free_quarters.py`, attribue le trimestre gratuit à toute école qui n'en a pas encore.
- Elle s'exécute au déploiement du lot A, puis toutes les heures (§13). Une école qui vient d'être créée peut donc afficher l'état `NONE` pendant une heure au plus.
- La date de début ne dépend pas du moment de l'exécution. Relancer la commande ne change rien, car la contrainte UNIQUE l'empêche et une période attribuée n'est jamais modifiée.

### 5.5 Paiement en ligne PayGate (lot B)

La méthode exacte, v1 ou v2, sera choisie à la lecture du guide (§4.3, point 2). Le flux ci-dessous vaut pour les deux.

1. **Lancement.** Un utilisateur qui a `subscriptions.pay` ouvre une facture `ISSUED` et clique sur « Payer par Mobile Money ».
2. **Contrôles du serveur.**
   - Permission et école vérifiées.
   - Facture `ISSUED` et non expirée.
   - Montant inférieur ou égal au plafond (`PAYGATE_MAX_AMOUNT`).
   - Coupe-circuit actif.
   - **Aucune autre tentative en cours** pour cette facture. Si une tentative récente existe, elle est renvoyée au lieu d'en créer une seconde.
3. **Création de la tentative.** Le serveur crée `subscription_payments` au statut `INITIATED`, avec un `identifier` unique tiré au hasard côté serveur. Ce n'est ni un numéro devinable ni l'identifiant de la facture.
4. **Appel à PayGate.**
   - **v1** : le serveur appelle PayGate avec le jeton, le numéro et le réseau saisis par l'utilisateur, le montant de la facture et `identifier`. Le payeur reçoit une demande de confirmation sur son téléphone.
   - **v2** : le serveur renvoie l'URL de la page PayGate, seulement si cette URL ne contient pas le jeton.
   - Dans les deux cas, la tentative passe en `PENDING`.
5. **Retour du navigateur** (v2) : simple affichage « paiement en cours de vérification ». **Ce retour ne change jamais l'état du paiement.**
6. **Notification de PayGate**, sur l'endpoint public, non authentifié et limité en débit :
   - elle est enregistrée sous une forme minimale ;
   - elle ne sert **qu'à déclencher une vérification**.
7. **Vérification par le serveur.** Il interroge l'API d'état de PayGate avec `identifier` ou `tx_reference`. Il confirme le paiement **seulement si les quatre conditions suivantes sont réunies** :
   - PayGate indique un paiement réussi ;
   - le montant est égal au total de la facture ;
   - la devise est le FCFA ;
   - `identifier` correspond à cette tentative.
8. **Confirmation, en une seule transaction**, avec verrouillage de la facture (`SELECT … FOR UPDATE`) :
   - paiement `SUCCEEDED` ;
   - facture `PAID` ;
   - création de la période ;
   - notification interne ;
   - entrée au journal d'audit.
9. **Rapprochement périodique.** Une tâche (§13) vérifie les tentatives `INITIATED` et `PENDING` sans réponse. Elle couvre les notifications perdues et la v1, qui n'en envoie peut-être pas. Elle passe une tentative en `EXPIRED` après le délai PayGate (à confirmer), puis la vérifie encore une fois à J+1 pour détecter un succès tardif.

**Nouvelle abstraction.** Il faut un `OnlinePaymentProvider`, avec `initiate(...)` et `check_status(...)`. Il est distinct de `PaymentProvider`, qui reste inchangé pour le module `fees`. Il a deux implémentations :
- `PayGateProvider` ;
- `FakeOnlinePaymentProvider`, pour les tests et le développement. Il ne fait aucun appel réseau, sur le modèle de `LocalSmsProvider`.

### 5.6 Paiement manuel de secours (lot A)

Le propriétaire de la plateforme peut enregistrer un paiement reçu hors application : virement, espèces, Mobile Money sur un numéro marchand, etc.

**Cas d'usage**
- montant supérieur au plafond PayGate ;
- devis au-delà de 1 000 élèves ;
- école hors de la zone Flooz / T-Money ou dont la devise n'est pas le XOF ;
- panne de PayGate ;
- **toute la période qui précède le lot B.**

**Règles**
- Même table de paiements que PayGate, avec le fournisseur `MANUAL`.
- Le montant est obligatoirement égal au total de la facture.
- La référence est obligatoire.
- L'opération est inscrite au journal d'audit.
- Elle produit le même effet que le paiement en ligne (§5.5, étape 8).

### 5.7 Rappels (lot C)

- **Destinataires** : les utilisateurs SCHOOL_ADMIN de l'école, et DIRECTOR selon la question Q10.
- **Échéances** :
  - **J-30 et J-7** avant la fin de la période ;
  - **J0** à l'expiration ;
  - J-3 avant l'expiration d'une facture émise et non payée.
- **Canal** : notification interne à l'application, avec nouveaux types (`SUBSCRIPTION_RENEWAL_DUE`, `SUBSCRIPTION_EXPIRED`). Aucune migration de contrainte n'est nécessaire (§3.1). L'e-mail est facultatif, via `EmailProvider`.
- **Idempotence** : une table `subscription_reminders` avec une contrainte UNIQUE sur (période, étape), sur le modèle de la migration `0021`.
- Aucun SMS dans cette phase. Aucun blocage.

### 5.8 Cas anormaux (sans remboursement par l'API)

| Cas | Traitement |
| --- | --- |
| Notification pour un `identifier` inconnu | Enregistrée et ignorée, sans erreur visible pour l'appelant |
| PayGate confirme un montant différent du total | Paiement `ANOMALY` (montant), facture inchangée, signalé à la plateforme |
| Succès tardif d'une tentative déjà `EXPIRED`, facture encore `ISSUED` | Confirmé normalement (§5.5, étape 8) |
| Succès d'une tentative alors que la facture est déjà `PAID`, `CANCELLED` ou `EXPIRED` | Paiement `ANOMALY` (double paiement) ; remboursement manuel depuis le tableau de bord PayGate, avec trace dans le journal d'audit |
| PayGate indisponible | Message clair à l'école ; paiement manuel possible (§5.6) |

## 6. Modèle de données (migration `0027`, strictement additive)

Ces tables suivent les conventions du dépôt : UUID, `created_at` et `updated_at`, `Numeric(12,2)` avec contrainte d'entier, statuts contrôlés par CHECK.

| Table | Rôle | Colonnes principales | RLS |
| --- | --- | --- | --- |
| `subscription_price_grids` | Versions de la grille | `label`, `currency` (`XOF`), `status` (`DRAFT`/`ACTIVE`/`ARCHIVED`), `activated_at`, `created_by` ; UNIQUE partiel : une seule ligne `ACTIVE` | Lecture ouverte, écriture plateforme seulement |
| `subscription_price_lines` | Une ligne par couple (tranche, durée) | `grid_id`, `tier` (0 à 3), `min_students`, `max_students`, `period_months` (3/6/12), `base_amount`, `supplement_amount` (0 si tranche 0) ; UNIQUE (`grid_id`, `tier`, `period_months`) | Idem |
| `subscription_invoices` | Factures figées | `number` UNIQUE, `school_id`, `organization_id`, `grid_id` (nul pour un devis), `period_months`, `student_count`, `tier` (nul pour un devis), `base_amount`, `supplement_amount`, `total_amount`, `currency`, `status`, `issued_at`, `issued_by`, `expires_at`, `paid_at`, `quote_amount_set_by`, `cancelled_by`, `cancel_reason`, `idempotency_key` ; UNIQUE partiel : une facture ouverte par école | Générique `{table}_tenant_isolation` |
| `subscription_payments` | Tentatives et paiements | `invoice_id`, `school_id`, `organization_id`, `provider` (`PAYGATE`/`MANUAL`), `method` (`FLOOZ`, `TMONEY`, `BANK_TRANSFER`, `CASH`, `OTHER`), `amount`, `currency`, `status` (`INITIATED`, `PENDING`, `SUCCEEDED`, `FAILED`, `EXPIRED`, `ANOMALY`), `identifier` UNIQUE, `tx_reference` UNIQUE nullable, `payment_reference`, `payer_phone_last4`, `initiated_by`, `recorded_by`, `confirmed_at`, `last_checked_at`, `provider_status_code` ; UNIQUE partiel : un seul `SUCCEEDED` par facture et une seule tentative `INITIATED`/`PENDING` par facture | Générique |
| `school_subscription_periods` | Périodes payées et trimestre gratuit | `school_id`, `organization_id`, `kind` (`FREE_TRIAL`/`PAID`), `invoice_id` UNIQUE et nullable, `starts_on`, `ends_on` ; CHECK : une période `PAID` a une facture, une période `FREE_TRIAL` n'en a pas ; CHECK `ends_on >= starts_on` ; UNIQUE partiel : un seul `FREE_TRIAL` par école | Générique |
| `subscription_reminders` (lot C) | Idempotence des rappels | `period_id` ou `invoice_id`, `stage`, `sent_at` ; UNIQUE (cible, étape) | Générique |
| `payment_provider_callbacks` (lot B) | Journal brut minimal des notifications | `provider`, `received_at`, `identifier`, `tx_reference`, `source_ip`, `result` ; pas de numéro complet, pas de corps intégral | Plateforme seulement, comme `partners_platform_only` |

**Ce que la migration ne touche pas**
- Aucune colonne ajoutée à une table existante.
- Aucune table de `fees`, de `cash` ni de `partners` modifiée.
- Aucune contrainte existante modifiée.

**Écart volontaire à la règle « toutes les tables tenant ont la politique générique ».** La grille n'appartient à aucune organisation. Elle a donc ses propres politiques :
- `FOR SELECT USING (true)` : le prix n'est pas une donnée sensible, et l'école doit pouvoir calculer son aperçu ;
- `FOR INSERT/UPDATE/DELETE` réservé à `app.is_platform_wide = 'true'`.

## 7. API proposée

Les endpoints d'école suivent le motif de `cashier/router.py` : `school_id` en paramètre, puis vérification par la dépendance de permission propre à l'école. Le préfixe est `settings.api_v1_prefix`.

| Méthode et chemin | Permission | Effet |
| --- | --- | --- |
| `GET /school-subscription?school_id=` | `subscriptions.read` | État, période en cours, effectif actuel, tranche, aperçu des prix 3/6/12 (non figé) |
| `GET /school-subscription/invoices?school_id=` | `subscriptions.read` | Liste des factures |
| `GET /school-subscription/invoices/{id}` | `subscriptions.read` | Détail d'une facture et de ses tentatives |
| `POST /school-subscription/invoices` | `subscriptions.pay` | Corps : `school_id`, `period_months`, `idempotency_key`. Émet la facture figée |
| `POST /school-subscription/invoices/{id}/payments` (lot B) | `subscriptions.pay` | Lance un paiement PayGate. Renvoie l'URL de redirection (v2) ou l'état « en attente » (v1) |
| `GET /school-subscription/payments/{id}` (lot B) | `subscriptions.read` | État d'une tentative, pour le rafraîchissement de l'écran |
| `GET /school-subscription/invoices/{id}/receipt` (lot C) | `subscriptions.read` | Reçu, seulement si la facture est `PAID` |
| `GET /platform/subscription-grids` | `platform.subscriptions.read` | Grilles et lignes |
| `POST /platform/subscription-grids`, `PUT …/{id}` (DRAFT seulement), `POST …/{id}/activate` | `platform.subscriptions.manage` | Gestion des versions de la grille |
| `GET /platform/subscriptions` | `platform.subscriptions.read` | État par école, échéances, filtres |
| `GET /platform/subscription-invoices` | `platform.subscriptions.read` | Factures, avec filtres sur le statut et les anomalies |
| `POST /platform/subscription-invoices/{id}/quote` | `platform.subscriptions.manage` | Saisit le montant d'un devis (passage à `ISSUED`) |
| `POST /platform/subscription-invoices/{id}/cancel` | `platform.subscriptions.manage` | Annule une facture non payée (motif obligatoire) |
| `POST /platform/subscription-invoices/{id}/manual-payments` | `platform.subscriptions.manage` | Enregistre un paiement manuel (§5.6) |
| `POST /payment-providers/paygate/callback` (lot B) | Aucune (public) | Enregistre la notification, déclenche une vérification et répond `200` sans détail |

## 8. RBAC

Les nouvelles permissions sont déclarées dans des dictionnaires **dédiés** de `rbac/seed.py`, lus seulement par la migration `0027`. C'est la même règle que pour la caisse, `seed.py:232`. Aucune permission existante n'est retirée.

| Permission | Rôles | Remarque |
| --- | --- | --- |
| `subscriptions.read` | SCHOOL_ADMIN, DIRECTOR, ACCOUNTANT, SUPER_ADMIN | Consultation pour l'école |
| `subscriptions.pay` | SCHOOL_ADMIN, SUPER_ADMIN | Émettre une facture et payer (question Q4) |
| `platform.subscriptions.read` | Existante : SUPER_ADMIN, PLATFORM_OWNER | Enfin reliée à des endpoints |
| `platform.subscriptions.manage` | SUPER_ADMIN, PLATFORM_OWNER | Grille, devis, annulation, paiement manuel |

- Aucune permission pour PARTNER_ADMIN dans cette phase ; ce sera pour le chantier des commissions.
- TEACHER, STAFF, PARENT, STUDENT et CAISSIER n'ont aucun accès.

## 9. Sécurité

**Côté serveur**
- **Calcul serveur uniquement.** Le montant, l'effectif et la tranche ne sont jamais transmis par le navigateur. Le frontend n'est pas une frontière de sécurité.
- **Isolation.** Contrôle applicatif de l'école, puis RLS en seconde ligne. Les tests d'isolation existants (`test_tenant_isolation.py`) ne sont ni modifiés ni affaiblis ; de nouveaux tests couvrent les nouvelles tables.

**La notification PayGate n'est pas signée**
- Elle ne fait jamais foi : seule la vérification d'état faite par le serveur confirme un paiement (§5.5, étape 7).
- L'endpoint est limité en débit (motif `core/rate_limit.py`, Redis). Sa réponse est uniforme et ne révèle pas si un `identifier` existe.
- Il ne prend en compte que les tentatives connues et en cours.
- `identifier` est aléatoire et non devinable, ce qui empêche de viser une facture précise.

**Le jeton PayGate**
- Variable d'environnement `PAYGATE_AUTH_TOKEN`, présente **seulement sur le serveur de production**.
- Jamais dans le dépôt, les journaux, les rapports ni les messages d'erreur.
- Jamais envoyé au navigateur ; c'est un critère éliminatoire pour la v2 (§4.3).
- Ajouté aux contrôles de démarrage (§11).
- En cas de fuite, il est renouvelé depuis le tableau de bord PayGate.

**Données personnelles**
- Seuls les 4 derniers chiffres du numéro du payeur sont conservés.
- Ni nom ni numéro complet dans `payment_provider_callbacks`.

**Endpoint public**
- La notification reçue en `POST` est traitée comme une donnée non fiable.
- Taille du corps limitée ; champs validés par un schéma strict ; aucun champ réutilisé tel quel dans une requête SQL non paramétrée.

**Audit**
- Chaque action humaine sur la grille, un devis, une annulation ou un paiement manuel est inscrite au journal d'audit, ainsi que chaque confirmation système (§14).

## 10. Idempotence et concurrence

- **Émission de facture.** `idempotency_key` est fourni par le client et contrôlé côté serveur, avec la même règle que la correction `c85348b` de la caisse : une clé réutilisée avec des données différentes est rejetée. S'y ajoute l'UNIQUE partiel « une facture ouverte par école ».
- **Lancement de paiement.** UNIQUE partiel : une seule tentative `INITIATED` ou `PENDING` par facture. Deux clics simultanés donnent donc une seule tentative.
- **Confirmation.** Verrouillage de la facture (`FOR UPDATE`). L'UNIQUE partiel « un seul `SUCCEEDED` par facture » et l'UNIQUE sur `school_subscription_periods.invoice_id` empêchent toute double période, même si la notification et la tâche planifiée arrivent en même temps.
- **Notifications répétées.** Elles sont sans effet après la première confirmation.

## 11. Configuration et secrets

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `SUBSCRIPTION_ONLINE_PAYMENT_ENABLED` | `false` | Coupe-circuit du paiement en ligne, sur le modèle de `SMS_ENABLED`. Désactivé, seul le paiement manuel est proposé |
| `PAYMENT_ONLINE_PROVIDER` | `fake` | `fake` en développement et en test ; `paygate` en production |
| `PAYGATE_AUTH_TOKEN` | vide | **Secret.** Obligatoire au démarrage en production si le coupe-circuit est actif |
| `PAYGATE_API_BASE_URL` | vide | Tirée du guide d'intégration |
| `PAYGATE_TIMEOUT_SECONDS` | 10 | Délai des appels à PayGate |
| `PAYGATE_MAX_AMOUNT` | à confirmer | Plafond par transaction (§4.3) |
| `SUBSCRIPTION_INVOICE_VALIDITY_DAYS` | 30 | Validité d'une facture émise |
| `SUBSCRIPTION_LAUNCH_DATE` | vide | Date de lancement de la facturation : début du trimestre gratuit des écoles déjà en service. Tant qu'elle est vide, la commande d'attribution ne fait rien |

- L'URL de notification est construite à partir de `PUBLIC_BASE_URL` : `https://api.edulinkage.com/api/v1/payment-providers/paygate/callback`. Vous l'enregistrez dans le tableau de bord PayGate, si c'est là qu'elle se configure.
- Appels HTTP : `httpx` en asynchrone, déjà présent dans le projet. Il n'y a **aucun** SDK tiers PayGate et aucune nouvelle dépendance.
- Documentation à mettre à jour : `docs/deployment/PRODUCTION_CONFIGURATION.md`.

## 12. Écrans web

**École : page « Abonnement » dans `apps/web/app/(app)/school/`**
- **État actuel** : trimestre gratuit jusqu'au …, actif jusqu'au …, expire bientôt, expiré ou jamais abonnée.
- **Effectif actuel et tranche.**
- **Trois offres (3, 6, 12 mois)** avec leur prix calculé par le serveur, et un bouton « S'abonner » ou « Renouveler ». Ce bouton est réservé à `subscriptions.pay` et ouvre une confirmation qui rappelle que l'effectif et le prix seront figés.
- **Facture ouverte** : montant, date d'expiration, bouton « Payer par Mobile Money » (lot B), puis écran « paiement en cours de vérification » qui se rafraîchit seul.
- **Historique** des factures et des reçus.
- **Devis** au-delà de 1 000 élèves : message « tarif adapté, en attente de devis ».

**Plateforme : nouvelles pages dans `apps/web/app/(app)/platform/`**
- **Grilles** : brouillon, édition des 12 lignes, activation avec confirmation, historique.
- **Abonnements par école** : état (dont trimestre gratuit), échéance, effectif de la dernière facture, filtres « expire bientôt » et « expiré ».
- **Factures** : devis à chiffrer, annulation, paiement manuel, **anomalies** (§5.8).

Les écrans mobiles sont hors périmètre.

## 13. Tâches planifiées

- **`app/jobs/grant_free_quarters.py`** (lot A), au déploiement puis toutes les heures. Il attribue le trimestre gratuit (§5.4 bis). Il est idempotent et ne fait rien tant que `SUBSCRIPTION_LAUNCH_DATE` est vide.
- **`app/jobs/subscription_payments_reconcile.py`** (lot B), toutes les 10 minutes. Il vérifie les tentatives en cours, les passe en `EXPIRED`, et fait une dernière vérification à J+1. Il est idempotent et s'arrête si le coupe-circuit est inactif.
- **`app/jobs/subscription_reminders.py`** (lot C), une fois par jour. Il traite les rappels (§5.7) et passe en `EXPIRED` les factures dont la validité est dépassée.
- **Timers systemd** dans `deploy/systemd/`, sur le modèle de `edusphere-overdue-reminders.timer`.
- **Lacune déjà connue** : aucune alerte en cas d'échec d'un timer (`OnFailure=`). Elle concerne aussi ces nouvelles tâches.

## 14. Journal d'audit

Les actions sont inscrites dans le module `audit` existant, sans migration :
- `subscription_grid.created`, `.updated`, `.activated` ;
- `subscription_invoice.issued`, `.quote_set`, `.cancelled`, `.expired` ;
- `subscription_payment.manual_recorded`, `.confirmed` (acteur système), `.anomaly` ;
- `subscription_period.free_quarter_granted` (acteur système).

## 15. Tests

**Calcul (tests unitaires)**
- Bornes 0, 1, 100, 101, 250, 251, 500, 501, 1 000 et 1 001 (devis).
- Chacune des trois durées.
- Montants entiers.
- Grille DRAFT ignorée ; une seule grille ACTIVE.

**Périodes**
- Premier abonnement.
- Renouvellement anticipé : continuité sans chevauchement.
- Renouvellement après expiration.
- Fins de mois : 31 janvier, 29 février, 31 août.
- Fuseau de l'école.

**Trimestre gratuit**
- Un seul par école : seconde exécution de la commande, exécutions simultanées, insertion directe refusée par la contrainte UNIQUE.
- Date de début : école créée avant la date de lancement, puis après.
- Date de lancement vide : aucune attribution.
- Paiement pendant le trimestre gratuit : la période payée commence le lendemain de sa fin.
- Création d'école par chacun des chemins existants (plateforme, partenaire, organisation multi-écoles) : trimestre attribué à l'exécution suivante.

**Factures**
- Figement : un élève ajouté après l'émission ne change rien.
- Une seule facture ouverte par école ; clé d'idempotence réutilisée avec d'autres données.
- Expiration après 30 jours.
- Devis → `ISSUED`.
- Annulation interdite après paiement.

**Permissions et isolation**
- Chaque rôle face à chaque endpoint.
- Une école A ne lit ni ne paie une facture de l'école B : contrôle applicatif **et** RLS, en requête directe sous le rôle `edusphere_app`.
- PARTNER_ADMIN n'a aucun accès.

**Paiement en ligne** (avec `FakeOnlinePaymentProvider` et un stub HTTP de PayGate)
- Succès par notification ; succès par la tâche de rapprochement sans notification.
- Notification falsifiée : `identifier` inconnu, ou état réel non payé.
- Montant différent → `ANOMALY`.
- Notification répétée.
- Notification et tâche simultanées : une seule période.
- Succès tardif après `EXPIRED`.
- Double paiement.
- Coupe-circuit inactif.
- Montant supérieur au plafond.
- Jeton absent du navigateur et des journaux, par une recherche dans les sorties capturées.

**Autres**
- Paiement manuel : effet identique, référence obligatoire, audit.
- Rappels : idempotence par étape et destinataires.

**Test de garde** : remplacement décrit en §16.

**Validation réelle** (lot B), seulement avec votre autorisation : un paiement réel de petit montant en production, via une grille de test ou une facture dédiée. Il n'existe pas d'environnement de test PayGate, et il n'y a pas de remboursement par l'API.

## 16. Migration et test de garde

**Migration `0027` (lot A)**
- Elle est strictement additive : tables, index, RLS et permissions, sur le modèle de `0026`.
- Son retour arrière se fait dans l'ordre inverse.
- Les tables des lots B et C arrivent dans des migrations suivantes, `0028` et `0029`, pour que chaque lot reste déployable seul.

**Test de garde** (`apps/api/tests/test_pr17_hardening.py:690`)

Il sera remplacé par un test qui vérifie que :
- **aucune** table ni route ne contient `commission`, `payout` ou `ledger` : c'est inchangé, puisque les commissions restent hors périmètre ;
- les seules tables contenant `subscription` sont **exactement** celles prévues par ce document ;
- la seule colonne contenant `commission` reste `partner_school_enrollments.commission_eligible`.

Ce remplacement sera soumis à votre accord, conformément à la règle « ne jamais supprimer ou affaiblir un test ».

## 17. Plan d'implémentation par lots

Chaque lot suit la même méthode :
1. vérification de ce cadrage contre le code à jour ;
2. branche dédiée depuis `main` ;
3. implémentation ;
4. tests ;
5. validation réelle ;
6. rapport ;
7. PR.

Un lot ne commence qu'après votre autorisation explicite.

| Lot | Contenu | Utilisable sans PayGate | Dépend de |
| --- | --- | --- | --- |
| **A — Abonnements sans paiement en ligne** | Grille, calcul, factures, devis, périodes, trimestre gratuit, paiement manuel, écrans école et plateforme, migration `0027`, remplacement du test de garde | **Oui** : l'abonnement fonctionne avec un paiement enregistré par la plateforme | Préalables §18.1 |
| **B — Paiement PayGate** | `OnlinePaymentProvider`, PayGate, endpoint de notification, tâche de rapprochement, coupe-circuit, anomalies, migration `0028` | — | Lot A ; guide d'intégration lu (§4.3) ; jeton en place sur le serveur |
| **C — Rappels et reçus** | Rappels internes (et e-mail), reçu d'abonnement, expiration automatique des factures, migration `0029` | Oui | Lot A |
| Plus tard | Commissions des partenaires ; restriction éventuelle en cas d'impayé ; écrans mobiles | — | Décisions séparées |

## 18. Préalables

### 18.1 Avant le lot A

1. **Environnement de test.** Les tests d'intégration exigent PostgreSQL dans Docker. Aujourd'hui, Docker est arrêté et ses données sont sur C:, qui se dégrade (projet S7 inachevé). Il faut décider : finir le déplacement vers D: d'abord, ou accepter explicitement le risque.
2. **Dépôt sur C:.** Toute écriture dans le dépôt est une écriture sur C:. Elle exige votre autorisation.
3. **Arbre de travail.** Il contient des modifications non commitées (infrastructure de test : `conftest.py`, `edusphere_test_guard.py`, `pyproject.toml`, `requirements-dev.txt`, et quatre fichiers de tests), ainsi qu'un dossier `storage/` non suivi. Il faut décider de leur sort avant de créer la branche.

### 18.2 Avant le lot B

1. Compte marchand PayGate activé.
2. **Contenu du guide d'intégration** (§4.3), transmis **sans jeton ni identifiant**.
3. Jeton créé et placé **par vous** dans la configuration du serveur de production. Il ne doit jamais m'être transmis.
4. URL de notification enregistrée dans le tableau de bord PayGate.
5. Plafond par transaction connu.
6. La rotation des secrets en attente depuis la récupération du 8 novembre est indépendante, mais à garder en tête.

## 19. Hors périmètre

Ce chantier n'inclut pas :
- les commissions des partenaires ;
- la restriction, la lecture seule ou la suspension en cas d'impayé ;
- la carte bancaire ;
- le remboursement automatique et les avoirs ;
- le calcul automatique de la TVA ;
- le multi-devise : XOF uniquement ;
- les rappels par SMS ;
- les écrans mobiles ;
- les écrans partenaires ;
- le prorata et le changement de tranche en cours de période ;
- toute gratuité autre que le trimestre gratuit (prolongation, code promotionnel, remise ponctuelle) ;
- toute modification des modules `fees`, `cash` et `partners`.

## 20. Risques

| Risque | Atténuation |
| --- | --- |
| Notification PayGate non signée (falsification) | Confirmation uniquement par la vérification d'état du serveur ; `identifier` aléatoire ; limitation de débit |
| Pas d'environnement de test PayGate | Faux fournisseur et stub dans les tests ; un seul paiement réel de petit montant, autorisé |
| Jeton exposé si la page hébergée l'exige dans l'URL | Critère éliminatoire ; utiliser alors la v1 |
| Plafond par transaction | Paiement manuel de secours ; question Q3 |
| Double paiement sans remboursement par l'API | Une seule tentative en cours par facture ; anomalies visibles ; remboursement manuel tracé |
| Commissions de PayGate (2,5 à 3 %) modifiables unilatéralement | Question Q2 ; aucun montant de commission codé en dur |
| Versement T-Money tous les 10 jours ; réserves possibles (CGU B.6) | Point de trésorerie pour vous, sans impact sur le code |
| Indisponibilité de PayGate ou des opérateurs (CGU B.5) | Paiement manuel ; aucun blocage d'accès |
| Numérotation et mentions des factures non conformes | Question Q8, à valider avec un comptable |
| Disque C: qui se dégrade | Préalables §18.1 |

## 21. Questions nécessitant votre décision

Chaque question a une valeur par défaut. Elle sera appliquée si vous la validez.

| N° | Question | Valeur par défaut proposée |
| --- | --- | --- |
| Q1 | Prix par durée : un montant distinct pour 3, 6 et 12 mois (remise possible), ou 6 mois = 2 × 3 mois ? | Montant distinct par durée |
| Q2 | Les commissions de PayGate (2,5 % Flooz, 3 % T-Money) sont-elles absorbées par EduLinkage ou ajoutées à la facture ? | Absorbées. Le montant facturé reste égal au montant payé, quel que soit le réseau |
| Q3 | Une facture au-dessus du plafond PayGate se paie comment ? | Paiement manuel (virement), enregistré par la plateforme |
| Q4 | Qui peut émettre une facture et payer dans l'école ? | SCHOOL_ADMIN seulement |
| Q5 | Début de période : à la confirmation du paiement, ou à une date choisie (rentrée) ? | À la confirmation, ou dans la continuité de la période en cours |
| Q6 | Durée de validité d'une facture non payée ? | 30 jours |
| Q7 | Trimestre gratuit : **décidé** (un par école, écoles déjà en service comprises, 2026-11-12). Reste à fixer : la date de lancement de la facturation | Pas de valeur par défaut. Elle n'est pas nécessaire pour coder le lot A : c'est un réglage de production (`SUBSCRIPTION_LAUNCH_DATE`), à fixer avant la mise en service |
| Q8 | Facture : numérotation, mentions légales, TVA ? | Numérotation `EL-AAAA-NNNNNN` ; document sans TVA calculée, à valider avec un comptable |
| Q9 | Méthode PayGate : v1 (paiement direct) ou v2 (page hébergée) ? | Choix après lecture du guide ; v1 si la v2 expose le jeton |
| Q10 | Destinataires et échéances des rappels ? | SCHOOL_ADMIN et DIRECTOR ; J-30, J-7, J0 |
| Q11 | Montants réels de la grille ? | Saisis par vous dans l'écran plateforme ; aucun montant dans le code |

## 22. Sources

**Officielles**
- https://www.paygateglobal.com/ : services, commissions, versements, activation, guide d'intégration, FAQ retour et notification.
- https://paygateglobal.com/cgu : conditions générales.

**Tierces, non vérifiées**
- https://alldotpy.github.io/EasySwitch/integrations/paygate : SDK EasySwitch (limites, absence d'environnement de test, notification sans HMAC, tableau d'états incohérent).
- https://pub.dev/documentation/flutter_paygateglobal : package Flutter (v1 et v2, champs de la notification, notification en v2 seulement, montant de 1 à 1 000 000).

**Dépôt EduLinkage, lu le 2026-11-12**
- Les fichiers cités en §3.
- `docs/phases/PHASE_19_DISCOVERY.md` : §24 (architecture Mobile Money future) et §31 (hors périmètre).
