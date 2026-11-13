# Phase 29 — Lot C : rappels d'abonnement, expiration automatique des factures, reçus

- **Cadrage** : `docs/phases/PHASE_29_SCHOOL_SUBSCRIPTIONS_DISCOVERY.md`, §5.7 et §13.
- **Branche** : `feat/school-subscriptions-lot-c`, partie de `feat/school-subscriptions-lot-a` (`910b0b8`). Le lot A (pull request n° 28) n'est pas encore fusionné.
- **Statut** : code écrit. Les tests de calcul et la vérification de types du web ont été exécutés localement ; la suite complète tourne dans la CI GitHub.

## 1. Ce qui est livré

### Tâche quotidienne `app/jobs/subscription_reminders.py`

Le timer `deploy/systemd/edusphere-subscription-reminders.{service,timer}` la lance chaque jour à 06:30. Pour chaque école ayant une période ou une facture émise, elle travaille dans **sa propre transaction**, sous le verrou de l'école (même ordre de verrouillage que le lot A) :
1. **Expiration automatique** : les factures `ISSUED` dont la validité est dépassée passent en `EXPIRED`, avec une entrée d'audit `subscription_invoice.expired` (acteur système).
2. **Rappels de fin de couverture** (`pricing.coverage_reminder_stage`) :
   - **J30** : entre 30 et 8 jours restants ;
   - **J7** : entre 7 et 1 jour restant ;
   - **J0** : le jour de la fin et jusqu'à 7 jours après. Au-delà, aucun rappel, ce qui évite de notifier d'anciennes échéances au premier déploiement.

   La couverture est celle de la suite **continue** de périodes, trimestre gratuit compris. Un renouvellement déjà payé repousse donc les rappels. Un seul palier, le plus avancé applicable, est envoyé à chaque passage.
3. **Rappel de facture à régler** (`INVOICE_J3`) : 3 jours avant la fin de validité d'une facture émise et non payée.

**Destinataires et canal**
- Destinataires : les comptes **actifs** `SCHOOL_ADMIN` et `DIRECTOR` de l'école (rôle propre à l'école, ou rôle d'organisation sans école). Jamais les enseignants, parents ni autres rôles.
- Canal : **notifications internes uniquement**. Trois nouveaux types : `SUBSCRIPTION_RENEWAL_DUE`, `SUBSCRIPTION_EXPIRED`, `SUBSCRIPTION_INVOICE_DUE`. Aucune migration n'est nécessaire, car `notifications.type` n'a pas de contrainte CHECK.
- Aucun blocage d'accès (décision « rappels seulement »).

**Idempotence**
- La nouvelle table `subscription_reminders` (migration `0028`, RLS générique) garde une ligne par (cible, palier), avec des index uniques partiels. Relancer la tâche ne crée jamais de doublon.
- Le paramètre `only_school_ids` limite un passage à certaines écoles (exploitation ciblée, tests).

### Reçus PDF

| Point d'accès | Permission |
| --- | --- |
| `GET /school-subscription/invoices/{invoice_id}/receipt.pdf` | `subscriptions.read` (école de la facture) |
| `GET /platform/subscription-invoices/{invoice_id}/receipt.pdf` | `platform.subscriptions.read` |

- Les reçus sont générés à la demande, avec le même outil HTML vers PDF que les reçus de frais. Rien n'est stocké.
- **Facture non payée : 409.**
- Contenu : numéro, école, durée et dates de la période, effectif retenu, base et supplément (ou devis), total, date, moyen et référence du paiement.
- **Mentions légales et TVA non incluses** : la question Q8 du cadrage est toujours ouverte. Ce document atteste un paiement, il ne prétend pas être une facture fiscale.

### Web

- **Page « Abonnement »** : colonne « Reçu » pour les factures payées.
- **Page plateforme « Factures d'abonnement »** : action « Reçu » pour les factures payées.
- **Page « Notifications »** : libellés des trois nouveaux types.

## 2. Tests

- `tests/test_subscriptions_pricing.py` : paliers de rappel (bornes 45, 31, 30, 8, 7, 1, 0, -7 et -8 jours). **Exécuté localement : 12/12.**
- `tests/test_subscriptions_lot_c.py` (4 tests d'intégration) :
  - rappels J30, J7 et J0 envoyés une seule fois par palier, à l'administrateur et au directeur seulement ;
  - aucun rappel loin de l'échéance ni longtemps après ;
  - rappel de facture puis expiration automatique, avec audit ;
  - reçu : 409 avant paiement, PDF valide après, 403 pour un enseignant et pour un compte d'école sur l'accès plateforme, 404 pour une autre organisation.
- `tests/test_pr17_hardening.py` : la liste exacte des objets « subscription » inclut maintenant la table `subscription_reminders` et les deux routes de reçu. L'interdiction des commissions est inchangée.
- **Vérification de types du web** (`tsc --noEmit`) : 0 erreur.

## 3. Mise en service (après fusion et validation)

Procédure détaillée : [`docs/deployment/PHASE_29_PRODUCTION_RUNBOOK.md`](../deployment/PHASE_29_PRODUCTION_RUNBOOK.md). En résumé :

1. `alembic upgrade head` (migration 0028).
2. Installer et activer le timer `edusphere-subscription-reminders.timer`.
3. Lancement manuel possible : `docker compose exec -T api python -m app.jobs.subscription_reminders`.
