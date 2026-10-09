# PR #16 — Canal SMS pour les rappels de frais en retard

Ajoute un canal SMS à la cadence de relance J0/J7/J30 (PR #15) pour les tuteurs sans compte
utilisateur disposant d'un numéro de téléphone valide — prioritaire sur l'email pour ces tuteurs,
jamais les deux pour un même palier. Aucun nouveau scheduler, aucun nouveau worker : le canal
s'insère dans le job quotidien existant (`app/jobs/overdue_fee_reminders.py`, invoqué par
`deploy/systemd/edusphere-overdue-reminders.timer`).

## 1. Architecture

```
fees/overdue_reminders.py::send_overdue_fee_reminders
  │
  ├─ tuteurs AVEC compte          → notification in-app (inchangé depuis PR #15)
  │
  └─ tuteurs SANS compte          → _route_guardians_without_account()
        │                              │
        │                              ├─ téléphone normalisable + SMS_ENABLED → candidat SMS
        │                              ├─ sinon email renseigné                → candidat email
        │                              └─ sinon                                → NO_CHANNEL
        │
        ├─ candidats SMS   → _prepare_overdue_sms()   → fee_overdue_sms_reminders   (ATTEMPTED)
        └─ candidats email → _prepare_overdue_emails() → fee_overdue_email_reminders (ATTEMPTED)

  (après commit, sessions séparées)
  send_overdue_fee_reminder_sms()   → app/core/sms.py   → transport_status réel
  send_overdue_fee_reminder_emails() → app/core/email.py → transport_status réel
```

Même structure exacte que le canal email introduit en PR #15 Sprint 1.3 : préparation
(idempotence écrite EN BASE, dans la transaction métier) puis envoi réseau découplé (après
commit, best-effort, jamais d'exception remontée à l'appelant).

## 2. Choix du "provider"

`SmsProvider` (`app/core/sms.py`) est une interface abstraite, comme `EmailProvider`/
`StorageProvider` déjà existantes :

- `LocalSmsProvider` : écrit chaque SMS en fichier texte (dev/tests), aucun envoi réel.
- `HttpSmsProvider` : un simple POST JSON (`{"to", "body", "sender_id"}`) vers une URL HTTP
  configurable, avec un en-tête `Authorization: Bearer <token>` — compatible avec la plupart des
  passerelles SMS REST. Utilise `urllib.request` (bibliothèque standard), même choix déjà fait
  pour `SmtpEmailProvider` (`smtplib`) : aucune nouvelle dépendance HTTP pour ce seul besoin.

**Aucun SDK de fournisseur SMS particulier n'est importé.** Si un fournisseur réel retenu exige un
format de requête différent, il s'implémente comme un nouveau `SmsProvider` (une classe de plus
dans `app/core/sms.py`, ou un module séparé), sans toucher au code métier (`overdue_reminders.py`)
qui ne connaît que l'interface.

## 3. Format de téléphone

`Guardian.phone` reste un `String(32)` libre, jamais contraint en base — la normalisation a lieu
au moment de l'envoi, jamais à la saisie (`app/core/phone.py::normalize_phone_to_e164`), via la
bibliothèque `phonenumbers` (portage Python de libphonenumber de Google, pure Python, référence
de facto pour ce problème — ajoutée à `requirements.txt`, aucune autre dépendance disponible dans
ce dépôt pour ce besoin).

- Jamais de région figée en dur : `Organization.country_code` de l'organisation du frais concerné
  est utilisé comme région par défaut pour interpréter un numéro saisi sans indicatif explicite.
- Un numéro invalide, vide ou absent retourne `None` — **jamais une exception** : un seul tuteur
  mal renseigné ne fait jamais échouer le lot (potentiellement des milliers de frais).
- **`guardian_id` reste l'unique identité pour l'idempotence, jamais le numéro.** Un tuteur qui
  corrige son numéro entre deux exécutions reste le même destinataire pour la cadence — testé
  explicitement (`test_phone_change_between_runs_does_not_break_idempotence`).

## 4. Table `fee_overdue_sms_reminders`

Migration `0022_fee_overdue_sms_reminders.py` (additive, ne modifie aucune migration
précédente) :

| Colonne | Type | Note |
|---|---|---|
| `id` | UUID PK | |
| `school_id`, `organization_id` | UUID FK | RLS tenant, même policy que toutes les tables existantes |
| `student_fee_id` | UUID FK | |
| `guardian_id` | UUID FK | identité d'idempotence — jamais le numéro |
| `reminder_stage` | String(8) | "J0"/"J7"/"J30" |
| `transport_status` | String(32) | "ATTEMPTED" (défaut) / "TRANSPORT_ACCEPTED" / "TRANSPORT_FAILED" |
| `transport_checked_at` | DateTime nullable | |
| `provider_message_id` | String(128) nullable | opaque, jamais un secret, jamais une clé d'idempotence |
| `created_at` | DateTime | |

Contrainte unique **en base** : `(student_fee_id, guardian_id, reminder_stage)` — garantie
d'idempotence réelle, jamais seulement applicative (voir §5).

## 5. Idempotence et concurrence

Même discipline exacte que l'email (PR #15/Sprint 1.6) :

- Chaque ligne est écrite sous son propre `SAVEPOINT` (`db.begin_nested()`) — une collision sur
  la contrainte unique n'annule que CETTE ligne, jamais le lot entier.
- Testé avec une exécution réellement concurrente du job (`asyncio.gather`) : au plus une ligne
  par (frais, tuteur, palier), quel que soit le nombre de processus qui tentent d'écrire en même
  temps.
- Un redémarrage entre deux exécutions (deux sessions DB fraîches successives) ne produit jamais
  de doublon — la contrainte unique est l'autorité, pas un simple pré-filtrage en mémoire.

## 6. Comportement en cas d'échec

Décision explicite, cohérente avec l'architecture déjà en place pour l'email :

> **Un SMS `TRANSPORT_FAILED` n'est JAMAIS retenté automatiquement pour le MÊME palier.** La
> ligne de suivi existe déjà dès la préparation (avant même la tentative réseau) — pour
> `_next_stage_to_send` (la logique de cadence J0/J7/J30, **inchangée** depuis PR #15), ce palier
> est "tenté", point final. Seul le palier SUIVANT (ex. J7 après un J0 en échec) sera tenté
> normalement au prochain passage du job, indépendamment du résultat du précédent.

Aucun retry automatique, aucune queue — exactement comme pour l'email. Testé explicitement
(`test_sms_transport_failed_at_j0_never_retried_but_j7_proceeds`). Un échec SMS individuel
n'affecte jamais les autres SMS du même lot, ni le job dans son ensemble
(`test_one_failing_sms_does_not_block_others_in_the_same_run`).

## 7. Priorité SMS / email

Pour un tuteur sans compte utilisateur (voir `_route_guardians_without_account`) :

1. Numéro de téléphone normalisable en E.164 **et** `SMS_ENABLED=true` → **SMS**, prioritaire.
2. Sinon, adresse email renseignée → **email**, en repli.
3. Sinon → aucun canal (`NO_CHANNEL`, visible dans `/fees/overdue`).

Jamais les deux canaux pour le même tuteur et le même palier. Un tuteur AVEC compte utilisateur
ne reçoit jamais de SMS (ni d'email) — uniquement sa notification in-app existante, même si un
numéro de téléphone est renseigné.

**Limite connue et documentée** : le routage est réévalué à chaque exécution depuis l'état
courant du tuteur — il n'existe pas de vérification croisée entre les trois tables de suivi
(`notifications`/`fee_overdue_email_reminders`/`fee_overdue_sms_reminders`, délibérément
indépendantes). Si le canal préféré d'un tuteur change entre deux exécutions (numéro ajouté,
`SMS_ENABLED` activé après coup), le nouveau canal démarre sa propre cadence depuis J0,
indépendamment de l'historique de l'ancien canal. Voir
`test_channel_switch_after_email_history_starts_fresh_sms_cadence` pour le comportement exact.

## 8. Configuration / variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `SMS_ENABLED` | `false` | Coupe-circuit dédié — le canal SMS reste désactivé même si `SMS_PROVIDER=http` est configuré |
| `SMS_PROVIDER` | `local` | `local` (dev/tests) ou `http` (réel, générique) |
| `SMS_LOCAL_PATH` | `./sms` | Répertoire d'écriture du provider local |
| `SMS_HTTP_URL` | _(vide)_ | Obligatoire si `SMS_PROVIDER=http` |
| `SMS_HTTP_AUTH_TOKEN` | _(vide)_ | Obligatoire si `SMS_PROVIDER=http` — jamais journalisé |
| `SMS_HTTP_TIMEOUT_SECONDS` | `10` | |
| `SMS_SENDER_ID` | _(vide)_ | Optionnel, jamais un secret |

**`SMS_PROVIDER=http` sans `SMS_HTTP_URL`/`SMS_HTTP_AUTH_TOKEN` fait échouer le démarrage de
l'application** (`ValueError` explicite, voir `app/core/sms.py::get_sms_provider`) — en
développement comme en production, jamais une erreur silencieuse au premier envoi réel.

## 9. Procédure de test local

```bash
# Dans le conteneur api (ou un environnement local avec les dépendances installées) :
SMS_ENABLED=true SMS_PROVIDER=local python -m app.jobs.overdue_fee_reminders
# Les SMS "envoyés" apparaissent comme fichiers texte sous SMS_LOCAL_PATH (./sms par défaut).

# Tests automatisés dédiés :
pytest tests/test_phone.py tests/test_sms_provider.py tests/test_fee_reminder_sms.py
```

## 10. Activation en production

1. Choisir un fournisseur SMS réel exposant une API HTTP (ou écrire un `SmsProvider` dédié si son
   format diffère de `HttpSmsProvider`).
2. Définir `SMS_PROVIDER=http`, `SMS_HTTP_URL`, `SMS_HTTP_AUTH_TOKEN` (et `SMS_SENDER_ID` si le
   fournisseur l'exige) dans l'environnement de production.
3. Définir `SMS_ENABLED=true` **seulement après** avoir vérifié que `SMS_HTTP_URL`/
   `SMS_HTTP_AUTH_TOKEN` sont corrects (un `GET /api/v1/ready` ne couvre pas le provider SMS — à
   valider manuellement, ex. en relançant le job une fois sur un frais de test).
4. Aucune modification de `deploy/systemd/edusphere-overdue-reminders.{service,timer}` n'est
   nécessaire — le même timer quotidien couvre désormais aussi le canal SMS.

## 11. Rollback / désactivation

Désactivation immédiate et réversible, sans migration ni redéploiement de code : définir
`SMS_ENABLED=false` (ou retirer la variable, c'est le défaut) et redémarrer le conteneur `api`.
Le job revient alors exactement au comportement de PR #15 (email pour les tuteurs sans compte,
quel que soit leur numéro de téléphone) — aucune table ni ligne existante n'est affectée, les
lignes `fee_overdue_sms_reminders` déjà créées restent en base (historique) mais plus aucune
n'est ajoutée.
