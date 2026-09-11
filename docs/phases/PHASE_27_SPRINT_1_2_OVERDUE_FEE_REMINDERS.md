# Phase 27 Sprint 1.2 — Rappels automatiques de frais scolaires en retard

Ajoute un rappel automatique (notification in-app, type `FEE_OVERDUE`) envoyé aux tuteurs
disposant d'un compte utilisateur, lorsqu'un `StudentFee` de leur enfant est en retard de
paiement. Aucun Celery/RQ, aucun nouveau service Docker permanent : un job Python explicite,
déclenché quotidiennement par un timer systemd en production (préparé, pas installé
automatiquement — voir plus bas), et exécutable manuellement en développement.

## Règle d'éligibilité

Un `StudentFee` déclenche un rappel s'il remplit **toutes** ces conditions :

1. `status != 'CANCELLED'` ;
2. `due_date` non nul ;
3. `due_date < date.today()` (strictement dans le passé) ;
4. solde réel strictement positif — **toujours recalculé** à partir des `PaymentAllocation`
   liées à des `Payment` `COMPLETED` (`fees/service.py::compute_remaining_balances`), jamais
   déduit du seul champ `StudentFee.status` mis en cache.

Seuls les tuteurs (`Guardian`) dont `user_id` est renseigné sont notifiés — réutilise
`notifications/service.py::resolve_guardian_user_ids_for_student`, la même règle que pour les
notifications de bulletin publié, paiement enregistré et absence. Un élève avec plusieurs
tuteurs à compte reçoit une notification par tuteur.

## Idempotence

Un seul rappel par couple **(`StudentFee`, destinataire)**, jamais par correspondance de texte :

- `notifications.student_fee_id` (nullable, migration `0013`) relie une notification `FEE_OVERDUE`
  à sa `StudentFee` d'origine.
- Avant de créer une notification, le job lit les destinataires déjà notifiés pour cette
  `StudentFee` (`notifications/service.py::existing_fee_overdue_recipient_ids`) et les exclut.
- Un index unique **partiel** `uq_notifications_fee_overdue_recipient` sur
  `(recipient_user_id, student_fee_id) WHERE type = 'FEE_OVERDUE'` constitue la dernière ligne
  de défense en base contre une double exécution concurrente — le contrôle applicatif ci-dessus
  suffit dans l'usage normal (un seul timer, exécutions séquentielles).

Une exécution répétée du job (même jour, jours suivants) ne crée donc jamais de doublon pour un
frais déjà notifié ; si le solde redevient nul (paiement complet), aucun frais n'est plus
éligible et aucune notification supplémentaire n'est créée pour lui — mais celles déjà envoyées
ne sont pas rétractées (pas de mécanisme d'annulation de notification dans ce dépôt, cohérent
avec les 4 types existants).

## Lancer le job manuellement

```bash
# Développement (docker compose local)
docker compose exec -T api python -m app.jobs.overdue_fee_reminders

# Résultat : code de sortie 0 (succès, log JSON avec les compteurs) ou 1 (échec, transaction
# annulée — aucune notification partielle n'est committée).
```

## Timer systemd (production)

Fichiers **préparés** dans ce dépôt (`deploy/systemd/edusphere-overdue-reminders.service` et
`.timer`), **non installés automatiquement** — à copier manuellement sur l'hôte de production,
indépendamment de `edusphere-backup.service`/`.timer` existants (ni modifiés, ni remplacés) :

```bash
sudo cp deploy/systemd/edusphere-overdue-reminders.service /etc/systemd/system/
sudo cp deploy/systemd/edusphere-overdue-reminders.timer /etc/systemd/system/
# Adapter WorkingDirectory / User / Group dans le .service au chemin et à l'utilisateur réels
# de ce déploiement (mêmes valeurs que celles déjà utilisées pour le backup, par cohérence).
sudo systemctl daemon-reload
sudo systemctl enable --now edusphere-overdue-reminders.timer
```

Fréquence : quotidienne, `06:00` (heure serveur) — après la fenêtre de backup (`02:00`), hors
heures ouvrables typiques d'une école. `Persistent=true` : un rappel manqué parce que le serveur
était éteint à 06:00 s'exécute dès le redémarrage suivant plutôt que d'attendre le jour suivant.

### Vérifier le timer

```bash
systemctl status edusphere-overdue-reminders.timer
systemctl list-timers edusphere-overdue-reminders.timer   # prochaine exécution planifiée
systemctl status edusphere-overdue-reminders.service       # résultat de la dernière exécution
```

### Consulter les logs

```bash
journalctl -u edusphere-overdue-reminders.service --since "1 day ago"
```

Chaque exécution produit une ligne JSON structurée (même format que le reste de l'API, voir
`app/core/logging_config.py`) avec le nombre de frais éligibles, de notifications créées et de
frais distincts notifiés — jamais de donnée personnelle (nom d'élève, montant) dans ce log de
synthèse, uniquement des compteurs.

### Désactiver le timer en cas d'incident

```bash
sudo systemctl disable --now edusphere-overdue-reminders.timer
```

N'affecte ni `edusphere-backup.service`/`.timer`, ni l'API elle-même (les notifications
existantes restent lisibles normalement) — seule la création de **nouveaux** rappels s'arrête.

## Fichiers

| Fichier | Rôle |
|---|---|
| `apps/api/app/modules/fees/overdue_reminders.py` | Logique métier : sélection des frais éligibles, calcul du solde réel, notification par tuteur avec compte |
| `apps/api/app/jobs/overdue_fee_reminders.py` | Point d'entrée `python -m` — ouvre la session DB, gère commit/rollback et le code de sortie |
| `apps/api/app/modules/notifications/service.py` | `notify_fee_overdue`, `existing_fee_overdue_recipient_ids` — idempotence et création des notifications |
| `apps/api/app/modules/fees/service.py` | `compute_remaining_balances` — réutilise le calcul de solde déjà existant, aucune seconde logique |
| `apps/api/alembic/versions/0013_fee_overdue_reminders.py` | `notifications.student_fee_id` + index unique partiel |
| `deploy/systemd/edusphere-overdue-reminders.{service,timer}` | Unités systemd préparées (non installées) |
| `apps/api/tests/test_overdue_fee_reminders.py` | Suite de tests (12 scénarios, voir Discovery) |
