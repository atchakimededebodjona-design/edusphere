"""Sprint 1.2 — rappels automatiques de frais scolaires impayés/échus.

PR #15 — fait évoluer ce rappel, jusqu'ici à usage unique par (StudentFee, tuteur), en une
cadence à trois paliers (voir `app/modules/fees/models.py::REMINDER_STAGES` : "J0"/"J7"/"J30").
Voir `_next_stage_to_send` ci-dessous pour la règle de progression exacte et sa justification.

Traite TOUTES les organisations en une seule exécution (job batch plateforme, pas une requête
utilisateur scopée) : le contexte tenant est explicitement élargi via `set_platform_wide_context`
avant toute lecture, motif déjà utilisé par `notifications/service.py::list_school_announcements`.

Règle d'éligibilité à l'EXISTENCE dans le lot traité (inchangée depuis le Sprint 1.2, voir
Discovery, état production validé) :
- `status != 'CANCELLED'` ;
- `due_date` non nul et strictement dans le passé (`< date.today()`) ;
- solde réel (`amount_due` - paiements `COMPLETED` alloués, jamais le seul champ `status` mis en
  cache — voir `fees/service.py::compute_remaining_balances`) strictement positif.

Au sein de ce lot, QUEL palier envoyer à QUEL destinataire est déterminé séparément pour chacun
(voir `_next_stage_to_send`) : deux tuteurs d'un même frais peuvent légitimement se voir proposer
des paliers différents à la même exécution (ex. un tuteur ajouté récemment n'a encore reçu aucun
palier, un autre a déjà reçu J0 et J7).

Ne cible que les tuteurs dont `Guardian.user_id` est renseigné (réutilise
`notifications/service.py::resolve_guardian_user_ids_for_students`, déjà utilisé par
`notify_payment_recorded`/`notify_report_card_published`/`notify_student_absent` — même règle,
aucune logique nouvelle). Un même élève peut avoir plusieurs tuteurs avec compte : chacun reçoit
sa propre notification.

Sprint 1.3 — canal EMAIL, en complément du canal in-app ci-dessus, réservé aux tuteurs SANS
compte utilisateur (`Guardian.user_id IS NULL`) mais avec une adresse email renseignée. Un tuteur
avec compte ne reçoit jamais d'email en plus de sa notification in-app — les deux canaux sont
mutuellement exclusifs par construction (`resolve_guardian_user_ids_for_students` vs
`resolve_guardian_emails_without_account_for_students`, voir notifications/service.py).

PR #15 — l'idempotence par tuteur (table `fee_overdue_email_reminders`, et index unique partiel
pour les notifications in-app) porte maintenant sur (StudentFee, tuteur, PALIER) — au maximum UN
email/UNE notification par (StudentFee, tuteur, palier), jamais renvoyé pour un palier déjà
atteint, même si le frais reste impayé.

Sprint 1.6 — `send_overdue_fee_reminder_emails` enregistre désormais le résultat RÉEL du
transport SMTP (`TRANSPORT_ACCEPTED`/`TRANSPORT_FAILED`) sur la ligne de suivi déjà créée
(`ATTEMPTED` à la préparation), une ligne à la fois, chacune avec son propre commit — jamais un
commit unique pour tout le lot, pour qu'une interruption n'affecte jamais plus d'UNE ligne (voir
SPRINT 1.6 IMPLEMENTATION PLAN §7/§8). Aucun retry automatique, aucune queue : un
`TRANSPORT_FAILED` reste tel quel jusqu'à une décision produit explicite et distincte — et,
depuis PR #15, un `TRANSPORT_FAILED` à un palier n'empêche jamais le palier SUIVANT d'être tenté
à son tour (paliers indépendants, lignes indépendantes).

PR #16 — canal SMS, pour les mêmes tuteurs SANS compte utilisateur que le canal email ci-dessus,
mais PRIORITAIRE sur lui dès qu'un numéro de téléphone normalisable en E.164 existe (voir
`app/core/phone.py`) ET que `SMS_ENABLED=true` (voir `app/core/config.py`) : SMS et email restent
mutuellement exclusifs PAR TUTEUR — jamais les deux pour le même palier (voir
`_route_guardians_without_account` ci-dessous pour la règle de routage exacte). Si
`SMS_ENABLED=false` (valeur par défaut) ou qu'aucun numéro valide n'existe pour un tuteur donné,
le comportement retombe EXACTEMENT sur celui de PR #15 (email si disponible, sinon aucun canal) —
aucune régression du comportement existant tant que ce drapeau reste désactivé. Même discipline
d'idempotence EN BASE (table dédiée `fee_overdue_sms_reminders`, contrainte unique
`(student_fee_id, guardian_id, reminder_stage)`, `SAVEPOINT` par ligne) et même règle de retry
qu'email : un SMS `TRANSPORT_FAILED` à un palier n'est JAMAIS retenté automatiquement pour ce
MÊME palier (la ligne existe déjà, donc ce palier est "tenté" pour `_next_stage_to_send`, qui ne
regarde jamais `transport_status`) — seul le palier SUIVANT sera tenté normalement, exactement la
même décision que pour l'email, pour rester cohérent avec l'architecture déjà en place."""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email import send_email_best_effort
from app.core.phone import normalize_phone_to_e164
from app.core.sms import send_sms_best_effort
from app.core.tenancy import set_platform_wide_context
from app.modules.fees.models import REMINDER_STAGES, FeeOverdueEmailReminder, FeeOverdueSmsReminder, FeeSchedule, StudentFee
from app.modules.fees.service import compute_remaining_balances
from app.modules.notifications.models import Notification
from app.modules.notifications.service import (
    existing_fee_overdue_emailed_guardian_stages_for_fees,
    existing_fee_overdue_recipient_stages_for_fees,
    existing_fee_overdue_sms_stages_for_fees,
    resolve_guardian_user_ids_for_students,
    resolve_guardians_without_account_for_students,
)
from app.modules.organizations.models import Organization
from app.modules.schools.models import School
from app.modules.students.models import Student

logger = logging.getLogger(__name__)

# PR #15 — seuil (en jours écoulés depuis `due_date`) à partir duquel chaque palier devient
# éligible. Jamais stocké en base : toujours recalculé à la volée depuis `StudentFee.due_date` et
# `date.today()` (voir `_next_stage_to_send`) — si `due_date` est modifiée via
# `PATCH /student-fees/{id}`, les paliers encore non envoyés se recalculent donc naturellement sur
# la NOUVELLE date au prochain passage du job, sans aucune migration de données ni "nombre de
# jours de retard" à corriger quelque part.
_STAGE_THRESHOLD_DAYS: dict[str, int] = {"J0": 0, "J7": 7, "J30": 30}


def _next_stage_to_send(due_date: date, today: date, already_sent: set[str]) -> str | None:
    """Détermine le palier à envoyer AUJOURD'HUI à un destinataire donné, ou `None` si aucun
    n'est dû.

    Définition de chaque palier (seuil en jours écoulés depuis `due_date`, voir
    `_STAGE_THRESHOLD_DAYS` ci-dessus) :
    - "J0"  : premier palier — éligible dès que `due_date` est strictement dépassée (seuil 0).
    - "J7"  : éligible à partir de `due_date + 7` jours.
    - "J30" : éligible à partir de `due_date + 30` jours.

    IMPORTANT — ce que "J0" désigne RÉELLEMENT : "J0" est le nom du PREMIER palier dans l'ordre de
    progression (J0 -> J7 -> J30), **pas** une promesse que le message a été envoyé le jour civil
    même de l'échéance. Si le job tourne quotidiennement, J0 sera en pratique envoyé le lendemain
    du jour où `due_date` est dépassée (le job tourne une fois par jour, à 06:00 — voir
    `deploy/systemd/edusphere-overdue-reminders.timer`). Si le job n'a pas tourné depuis longtemps
    sur un frais donné (panne, nouvelle mise en service du produit, frais déjà ancien au moment où
    ce PR est déployé), "J0" sera le PREMIER palier jamais envoyé à ce destinataire pour ce frais,
    même si `due_date` remonte en réalité à plusieurs semaines — jamais un indicateur de date
    calendaire absolue, toujours un indicateur de PROGRESSION relative ("le palier le plus
    précoce pas encore traité"). Voir le point 2 ci-dessous pour la conséquence directe de cette
    définition sur les anciennes relances (migration 0021).

    Règle de progression (choix architectural explicite, voir cahier des charges PR #15 §2/§7) : JAMAIS plus
    d'UN palier par exécution du job et par destinataire, même si plusieurs seuils sont déjà
    dépassés. Concrètement, c'est le PREMIER palier (dans l'ordre J0 -> J7 -> J30) qui est à la
    fois (a) déjà éligible par son seuil et (b) jamais encore envoyé à ce destinataire pour ce
    frais. Les paliers suivants, même si leur seuil est également dépassé, sont volontairement
    reportés à une exécution future du job.

    Pourquoi ce choix plutôt que d'envoyer directement le palier le plus avancé déjà atteint :
    un frais resté 35 jours sans que le job n'ait jamais tourné sur lui (ex. tout premier passage
    après une longue coupure, `Persistent=true` du timer systemd ne couvrant qu'UNE exécution
    manquée) a ses trois seuils déjà dépassés dès le premier traitement. Envoyer les 3 messages
    d'un coup au même destinataire serait une rafale artificielle, jamais vue par un tuteur dont
    le frais aurait été traité au jour le jour. Ce choix garantit au contraire une progression
    IDENTIQUE, qu'elle soit étalée sur 30 jours de fonctionnement normal ou rattrapée sur 3
    exécutions consécutives après une interruption : J0 d'abord, puis J7 au prochain passage (le
    lendemain si le job tourne quotidiennement), puis J30 au passage suivant — jamais les trois
    ensemble, jamais dans le désordre.

    En cas de `due_date` déplacée (report d'échéance) : rien n'est stocké ici en dehors de
    `already_sent` (les paliers RÉELLEMENT déjà envoyés, lus depuis la base) — `elapsed` est
    recalculé à chaque appel depuis la `due_date` ACTUELLE. Un report d'échéance réduit
    simplement le nombre de paliers éligibles au prochain passage ; les paliers déjà envoyés le
    restent pour toujours (jamais "désenvoyés"), conformément à l'exigence de ne jamais perdre
    l'historique existant."""
    elapsed = (today - due_date).days
    for stage in REMINDER_STAGES:
        if elapsed < _STAGE_THRESHOLD_DAYS[stage]:
            break
        if stage not in already_sent:
            return stage
    return None


@dataclass
class OverdueReminderRunResult:
    eligible_fees: int
    notifications_created: int
    fees_with_new_notifications: int
    # PR #15 — répartition par palier, pour l'observabilité du job (voir le message de log final
    # dans app/jobs/overdue_fee_reminders.py) : ne change rien au comportement, utile pour
    # distinguer "0 nouvelle notification parce que tout est déjà à jour" de "0 parce qu'aucun
    # palier n'est encore dû".
    notifications_created_by_stage: dict[str, int] = field(default_factory=dict)
    # Sprint 1.3 — emails prêts à envoyer, déjà enregistrés comme tentés (voir
    # `_prepare_overdue_emails` ci-dessous) au moment où cette liste est renvoyée : l'envoi réseau
    # proprement dit reste la responsabilité de l'appelant, APRÈS son commit (voir
    # `send_overdue_fee_reminder_emails`). Sprint 1.6 — `reminder_id` ajouté (identifiant de la
    # ligne `FeeOverdueEmailReminder` déjà créée) pour que l'appelant puisse y reporter le
    # résultat réel du transport une fois l'envoi tenté.
    emails: list[tuple[uuid.UUID, str, str, str, str | None, str | None, uuid.UUID | None]] = field(default_factory=list)
    # PR #16 — SMS prêts à envoyer, même découplage préparation/envoi que `emails` ci-dessus (voir
    # `send_overdue_fee_reminder_sms`). Tuple : (reminder_id, numéro E.164, corps du message).
    sms: list[tuple[uuid.UUID, str, str]] = field(default_factory=list)


async def _list_eligible_overdue_fees(db: AsyncSession) -> list[tuple[StudentFee, str, str]]:
    """`StudentFee` en retard, avec le nom et la devise de leur barème (une seule requête,
    jamais de N+1 — même exigence que `fees/service.py::_allocations_by_fee`). Soutenue par
    l'index `ix_student_fees_status_due_date` (migration 0021 — PR #15)."""
    today = date.today()
    result = await db.execute(
        select(StudentFee, FeeSchedule.name, FeeSchedule.currency)
        .join(FeeSchedule, FeeSchedule.id == StudentFee.fee_schedule_id)
        .where(
            StudentFee.status != "CANCELLED",
            StudentFee.due_date.isnot(None),
            StudentFee.due_date < today,
        )
    )
    return [(row[0], row[1], row[2]) for row in result.all()]


def _format_reminder_body(student: Student, schedule_name: str, balance: Decimal, currency: str) -> str:
    return (
        f"Le paiement de {student.first_name} {student.last_name} pour « {schedule_name} » "
        f"est en retard. Montant restant : {balance} {currency}."
    )


def _format_sms_body(student: Student) -> str:
    """PR #16 — message volontairement très court et générique (cahier des charges §9) : jamais
    de montant, de solde, de nom de barème ni de lien — seul le prénom de l'élève, pour rester
    sous la longueur d'un segment SMS standard (~160 caractères GSM-7) et ne jamais exposer de
    détail financier par un canal non authentifié."""
    return (
        f"EduLinkage : le paiement scolaire de {student.first_name} est en retard. "
        "Connectez-vous à votre espace parent pour consulter votre situation."
    )


async def _create_overdue_in_app_notifications(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    school_id: uuid.UUID,
    recipient_user_ids: set[uuid.UUID],
    title: str,
    body: str,
    student_fee_id: uuid.UUID,
    reminder_stage: str,
) -> int:
    """PR #15 — remplace l'appel à `notifications/service.py::create_notifications` (qui insère
    tout le lot sous un seul `flush()`) pour CE job précis uniquement : chaque ligne est insérée
    sous son PROPRE `SAVEPOINT` (`db.begin_nested()`), exactement le même motif déjà en place
    pour le canal email ci-dessous (`_prepare_overdue_emails`).

    Pourquoi ce n'est pas un simple changement cosmétique : `notifications` porte désormais un
    index unique PARTIEL sur (recipient_user_id, student_fee_id, reminder_stage) — une exécution
    réellement concurrente du job (deux workers futurs, ou un redémarrage qui relance le job alors
    qu'une exécution précédente n'a pas fini de committer) pourrait faire gagner la course à DEUX
    processus sur la MÊME ligne. Avec un unique `add_all()`+`flush()` pour tout le lot, cette
    collision ferait échouer la transaction ENTIÈRE (y compris les destinataires légitimes du
    même lot qui n'étaient en course avec personne). Avec un `SAVEPOINT` par ligne, seule la
    ligne réellement en collision est annulée — jamais les autres, jamais la transaction globale.
    `create_notifications` lui-même reste inchangé : ses 4 autres appelants (bulletins, paiements,
    absences, annonces) n'ont aucune contrainte unique de ce genre et ne nécessitent pas cette
    protection."""
    if not recipient_user_ids:
        return 0
    created = 0
    for recipient_id in recipient_user_ids:
        try:
            async with db.begin_nested():
                db.add(
                    Notification(
                        id=uuid.uuid4(),
                        school_id=school_id,
                        organization_id=organization_id,
                        recipient_user_id=recipient_id,
                        type="FEE_OVERDUE",
                        title=title,
                        body=body,
                        student_fee_id=student_fee_id,
                        reminder_stage=reminder_stage,
                    )
                )
                await db.flush()
        except IntegrityError:
            logger.warning(
                "overdue_fee_reminders: notification déjà tracée pour "
                "(student_fee_id=%s, recipient_user_id=%s, stage=%s), ignorée.",
                student_fee_id,
                recipient_id,
                reminder_stage,
            )
            continue
        created += 1
    return created


async def _prepare_overdue_emails(
    db: AsyncSession,
    *,
    student: Student,
    fee: StudentFee,
    reminder_body: str,
    school: School | None,
    candidates: list[tuple[uuid.UUID, str, str]],
    reminder_stage: str,
) -> list[tuple[uuid.UUID, str, str, str, str | None, str | None, uuid.UUID | None]]:
    """Sprint 1.3 — enregistrement du suivi d'idempotence (dans la transaction en cours), pour les
    tuteurs SANS compte utilisateur de cet élève. L'envoi réseau réel n'a lieu qu'après le commit
    de l'appelant (voir `send_overdue_fee_reminder_emails`) — même découplage que
    `report_cards/service.py::prepare_report_card_published_notifications` /
    `send_report_card_published_notifications`.

    PR #15 — `candidates` est déjà filtré par l'appelant pour ne contenir que les tuteurs pour
    qui CE `reminder_stage` précis est le prochain palier dû (voir `send_overdue_fee_reminders`) ;
    cette fonction ne reçoit donc plus de liste `already_emailed` séparée — la garantie
    "jamais deux fois le même palier" reste néanmoins assurée EN BASE, jamais seulement par ce
    pré-filtrage en mémoire : la contrainte unique `uq_fee_overdue_email_reminder_stage`
    (migration 0021) reste la seule autorité réelle, le `SAVEPOINT` ci-dessous n'isolant qu'une
    collision par ailleurs déjà improbable (pré-filtrage déjà fait) plutôt que de faire échouer
    tout le lot.

    Phase 24B — `school` reçue déjà résolue par l'appelant (`send_overdue_fee_reminders`, via un
    lookup groupé par `school_id`) : ce job traite potentiellement des frais de PLUSIEURS écoles
    en une seule exécution, un `db.get(School, ...)` par frais individuel ici recréerait le même
    N+1 déjà évité pour `Student`.

    Chaque ligne de suivi est écrite dans un SAVEPOINT dédié (`db.begin_nested`) : une exécution
    réellement concurrente du job (hors usage normal — un seul timer, séquentiel) qui gagnerait la
    course sur la contrainte unique ne doit annuler que CET envoi, jamais la transaction entière
    (qui contient aussi les notifications in-app déjà `flush`ées pour d'autres frais).

    Sprint 1.6 — `transport_status="ATTEMPTED"` est renseigné explicitement dès la création (déjà
    la valeur par défaut en base, mais explicite ici pour rester lisible sans consulter le
    modèle) ; l'identifiant de la ligne (déjà généré, nécessaire pour l'idempotence) est renvoyé
    avec chaque email pour que l'appelant puisse y reporter le résultat réel du transport après
    la tentative d'envoi (voir `send_overdue_fee_reminder_emails`)."""
    if not candidates:
        return []

    subject = f"Paiement en retard — {student.first_name} {student.last_name}"
    from_name = school.name if school is not None else None
    reply_to = school.email if school is not None else None
    email_school_id = school.id if school is not None else None

    emails: list[tuple[uuid.UUID, str, str, str, str | None, str | None, uuid.UUID | None]] = []
    for guardian_id, full_name, email in candidates:
        reminder_id = uuid.uuid4()
        try:
            async with db.begin_nested():
                db.add(
                    FeeOverdueEmailReminder(
                        id=reminder_id,
                        school_id=fee.school_id,
                        organization_id=fee.organization_id,
                        student_fee_id=fee.id,
                        guardian_id=guardian_id,
                        transport_status="ATTEMPTED",
                        reminder_stage=reminder_stage,
                    )
                )
                await db.flush()
        except IntegrityError:
            logger.warning(
                "overdue_fee_reminders: email déjà tracé pour "
                "(student_fee_id=%s, guardian_id=%s, stage=%s), ignoré.",
                fee.id,
                guardian_id,
                reminder_stage,
            )
            continue
        emails.append(
            (
                reminder_id,
                email,
                subject,
                f"Bonjour {full_name},\n\n{reminder_body}\n\n"
                "Cet email a été envoyé via EduLinkage, plateforme de gestion scolaire.",
                from_name,
                reply_to,
                email_school_id,
            )
        )

    return emails


async def _prepare_overdue_sms(
    db: AsyncSession,
    *,
    fee: StudentFee,
    sms_body: str,
    candidates: list[tuple[uuid.UUID, str]],
    reminder_stage: str,
) -> list[tuple[uuid.UUID, str, str]]:
    """PR #16 — pendant SMS de `_prepare_overdue_emails` ci-dessus, même mécanisme exact : écrit
    une ligne `FeeOverdueSmsReminder` à `ATTEMPTED` sous son propre `SAVEPOINT` (une collision sur
    la contrainte unique n'annule que CETTE ligne, jamais le reste du lot) ; `candidates` est déjà
    filtré par l'appelant (`send_overdue_fee_reminders`, via `_route_guardians_without_account`)
    pour ne contenir que les tuteurs dont CE `reminder_stage` précis est le prochain palier dû
    PAR CE canal — la garantie "jamais deux fois le même palier" reste assurée EN BASE par la
    contrainte unique `uq_fee_overdue_sms_reminder_stage` (migration 0022), jamais seulement par
    ce pré-filtrage. `candidates` porte déjà le numéro normalisé en E.164 (voir
    `app/core/phone.py`) — jamais le numéro brut saisi par l'école."""
    if not candidates:
        return []

    sms: list[tuple[uuid.UUID, str, str]] = []
    for guardian_id, phone_e164 in candidates:
        reminder_id = uuid.uuid4()
        try:
            async with db.begin_nested():
                db.add(
                    FeeOverdueSmsReminder(
                        id=reminder_id,
                        school_id=fee.school_id,
                        organization_id=fee.organization_id,
                        student_fee_id=fee.id,
                        guardian_id=guardian_id,
                        reminder_stage=reminder_stage,
                        transport_status="ATTEMPTED",
                    )
                )
                await db.flush()
        except IntegrityError:
            logger.warning(
                "overdue_fee_reminders: SMS déjà tracé pour "
                "(student_fee_id=%s, guardian_id=%s, stage=%s), ignoré.",
                fee.id,
                guardian_id,
                reminder_stage,
            )
            continue
        sms.append((reminder_id, phone_e164, sms_body))

    return sms


def _route_guardians_without_account(
    candidates: list[tuple[uuid.UUID, str, str | None, str | None]], default_region: str
) -> tuple[list[tuple[uuid.UUID, str]], list[tuple[uuid.UUID, str, str]]]:
    """Règle de routage SMS/email pour les tuteurs SANS compte utilisateur (cahier des charges
    PR #16 §7) — appliquée AVANT toute résolution de palier, pour que SMS et email restent
    strictement mutuellement exclusifs PAR TUTEUR, jamais les deux pour un même palier :

    1. Numéro de téléphone normalisable en E.164 (et `SMS_ENABLED=true`, vérifié par l'appelant
       via `default_region` — voir `send_overdue_fee_reminders`) -> SMS, prioritaire.
    2. Sinon, adresse email renseignée -> email, en repli.
    3. Sinon -> aucun canal (NO_CHANNEL côté `/fees/overdue`, voir fees/service.py).

    Retourne deux listes déjà disjointes : `(guardian_id, phone_e164)` pour le canal SMS,
    `(guardian_id, full_name, email)` pour le canal email (même forme qu'avant ce PR, pour ne pas
    toucher `_prepare_overdue_emails`).

    LIMITE CONNUE, ACCEPTÉE ET DOCUMENTÉE (cahier des charges PR #16 §7 : "respecter les
    mécanismes d'idempotence séparés... in-app/email/SMS") : le routage est réévalué à CHAQUE
    exécution depuis l'état COURANT du tuteur (téléphone/email renseignés, `SMS_ENABLED`) — il
    n'existe PAS de vérification croisée entre les trois tables de suivi. Si un tuteur a reçu un
    palier par email avant que SMS_ENABLED ne soit activé (ou avant qu'un numéro valide ne soit
    renseigné), puis que le routage bascule vers SMS à une exécution suivante, la progression SMS
    repart de son propre J0, indépendamment de l'historique email — jamais une fusion/migration
    automatique entre canaux. Ce choix est délibéré (trois tables indépendantes, explicitement
    demandées) plutôt qu'une complexité supplémentaire de déduplication inter-canaux non demandée
    par ce PR ; voir `tests/test_fee_reminder_sms.py::test_channel_switch_after_email_history_starts_fresh_sms_cadence`
    pour le comportement exact, vérifié et documenté plutôt que fortuit."""
    sms_candidates: list[tuple[uuid.UUID, str]] = []
    email_candidates: list[tuple[uuid.UUID, str, str]] = []
    for guardian_id, full_name, email, phone in candidates:
        normalized_phone = normalize_phone_to_e164(phone, default_region) if settings.sms_enabled else None
        if normalized_phone is not None:
            sms_candidates.append((guardian_id, normalized_phone))
        elif email is not None:
            email_candidates.append((guardian_id, full_name, email))
        # sinon : NO_CHANNEL, aucun des deux canaux n'est utilisable pour ce tuteur.
    return sms_candidates, email_candidates


async def send_overdue_fee_reminders(db: AsyncSession) -> OverdueReminderRunResult:
    """Point d'entrée unique du job (voir `app/jobs/overdue_fee_reminders.py`). Commit sa propre
    transaction en fin d'exécution — même convention que `notifications/service.py::
    create_announcement` — l'appelant n'a qu'à ouvrir la session et gérer le rollback en cas
    d'exception non atteinte jusqu'ici."""
    await set_platform_wide_context(db)

    today = date.today()
    rows = await _list_eligible_overdue_fees(db)
    balances = await compute_remaining_balances(db, [row[0] for row in rows])
    overdue_rows = [(fee, schedule_name, currency) for fee, schedule_name, currency in rows if balances[fee.id] > 0]

    if not overdue_rows:
        await db.commit()
        return OverdueReminderRunResult(eligible_fees=0, notifications_created=0, fees_with_new_notifications=0)

    student_ids = {fee.student_id for fee, _, _ in overdue_rows}
    students_result = await db.execute(select(Student).where(Student.id.in_(student_ids)))
    students_by_id = {student.id: student for student in students_result.scalars().all()}

    # Phase 24B — lookup groupé par école (jamais un `db.get(School, ...)` par frais individuel,
    # ce job pouvant traiter des frais de plusieurs écoles en une seule exécution) : même motif
    # que `students_by_id` ci-dessus.
    school_ids = {fee.school_id for fee, _, _ in overdue_rows}
    schools_result = await db.execute(select(School).where(School.id.in_(school_ids)))
    schools_by_id = {school.id: school for school in schools_result.scalars().all()}

    # PR #16 — résolution de la région par défaut pour la normalisation E.164 (voir
    # app/core/phone.py) : `Organization.country_code`, jamais une valeur figée en dur. Lookup
    # groupé, même discipline anti-N+1 que `students_by_id`/`schools_by_id` ci-dessus.
    organization_ids = {fee.organization_id for fee, _, _ in overdue_rows}
    organizations_result = await db.execute(select(Organization).where(Organization.id.in_(organization_ids)))
    country_code_by_org_id = {org.id: org.country_code for org in organizations_result.scalars().all()}

    # Phase 27 Sprint 1.2bis — les lectures suivantes étaient auparavant refaites À CHAQUE frais
    # (jusqu'à ~5600 requêtes SQL confirmées par mesure pour ~1400 frais éligibles en pratique) :
    # un seul aller-retour par lookup, pour TOUS les frais de cette exécution, même discipline
    # anti-N+1 que `students_by_id`/`schools_by_id` ci-dessus. PR #15 — les lookups de suivi
    # renvoient, par destinataire, l'ENSEMBLE des paliers déjà atteints (plus un simple ensemble de
    # destinataires) — voir notifications/service.py. PR #16 —
    # `resolve_guardians_without_account_for_students` remplace l'ancienne version limitée au seul
    # canal email : elle renvoie désormais email ET téléphone, le routage SMS/email se faisant
    # ensuite par tuteur (voir `_route_guardians_without_account`).
    student_school_pairs = {(fee.student_id, fee.school_id) for fee, _, _ in overdue_rows}
    fee_ids = {fee.id for fee, _, _ in overdue_rows}
    guardian_user_ids_by_pair = await resolve_guardian_user_ids_for_students(db, student_school_pairs)
    already_notified_stages_by_fee = await existing_fee_overdue_recipient_stages_for_fees(db, fee_ids)
    guardians_without_account_by_pair = await resolve_guardians_without_account_for_students(db, student_school_pairs)
    already_emailed_stages_by_fee = await existing_fee_overdue_emailed_guardian_stages_for_fees(db, fee_ids)
    already_smsed_stages_by_fee = await existing_fee_overdue_sms_stages_for_fees(db, fee_ids)

    notifications_created = 0
    fees_with_new_notifications = 0
    notifications_created_by_stage: dict[str, int] = {}
    emails: list[tuple[uuid.UUID, str, str, str, str | None, str | None, uuid.UUID | None]] = []
    sms: list[tuple[uuid.UUID, str, str]] = []
    for fee, schedule_name, currency in overdue_rows:
        student = students_by_id.get(fee.student_id)
        if student is None:
            continue
        assert fee.due_date is not None  # garanti par `_list_eligible_overdue_fees`
        balance = balances[fee.id]
        reminder_body = _format_reminder_body(student, schedule_name, balance, currency)

        # --- Canal in-app : regroupe les destinataires par PROCHAIN palier dû (jamais deux
        # paliers dans la même exécution pour un même destinataire, voir _next_stage_to_send). ---
        recipient_ids = guardian_user_ids_by_pair.get((fee.student_id, fee.school_id), set())
        already_sent_by_recipient = already_notified_stages_by_fee.get(fee.id, {})
        recipients_by_stage: dict[str, set[uuid.UUID]] = {}
        for recipient_id in recipient_ids:
            stage = _next_stage_to_send(fee.due_date, today, already_sent_by_recipient.get(recipient_id, set()))
            if stage is not None:
                recipients_by_stage.setdefault(stage, set()).add(recipient_id)

        for stage, stage_recipients in recipients_by_stage.items():
            created = await _create_overdue_in_app_notifications(
                db,
                organization_id=fee.organization_id,
                school_id=fee.school_id,
                recipient_user_ids=stage_recipients,
                title="Paiement en retard",
                body=reminder_body,
                student_fee_id=fee.id,
                reminder_stage=stage,
            )
            notifications_created += created
            if created > 0:
                fees_with_new_notifications += 1
                notifications_created_by_stage[stage] = notifications_created_by_stage.get(stage, 0) + created

        # --- Tuteurs SANS compte utilisateur : routage SMS/email (PR #16 §7 — jamais les deux
        # pour un même tuteur), puis même principe de regroupement par palier pour chaque canal. ---
        without_account = guardians_without_account_by_pair.get((fee.student_id, fee.school_id), [])
        default_region = country_code_by_org_id.get(fee.organization_id, "TG")
        sms_route_candidates, email_route_candidates = _route_guardians_without_account(without_account, default_region)

        already_smsed_by_guardian = already_smsed_stages_by_fee.get(fee.id, {})
        sms_body = _format_sms_body(student)
        sms_candidates_by_stage: dict[str, list[tuple[uuid.UUID, str]]] = {}
        for guardian_id, phone_e164 in sms_route_candidates:
            stage = _next_stage_to_send(fee.due_date, today, already_smsed_by_guardian.get(guardian_id, set()))
            if stage is not None:
                sms_candidates_by_stage.setdefault(stage, []).append((guardian_id, phone_e164))

        for stage, stage_sms_candidates in sms_candidates_by_stage.items():
            sms.extend(
                await _prepare_overdue_sms(
                    db, fee=fee, sms_body=sms_body, candidates=stage_sms_candidates, reminder_stage=stage
                )
            )

        already_emailed_by_guardian = already_emailed_stages_by_fee.get(fee.id, {})
        email_candidates_by_stage: dict[str, list[tuple[uuid.UUID, str, str]]] = {}
        for guardian_id, full_name, email in email_route_candidates:
            stage = _next_stage_to_send(fee.due_date, today, already_emailed_by_guardian.get(guardian_id, set()))
            if stage is not None:
                email_candidates_by_stage.setdefault(stage, []).append((guardian_id, full_name, email))

        for stage, stage_email_candidates in email_candidates_by_stage.items():
            emails.extend(
                await _prepare_overdue_emails(
                    db,
                    student=student,
                    fee=fee,
                    reminder_body=reminder_body,
                    school=schools_by_id.get(fee.school_id),
                    candidates=stage_email_candidates,
                    reminder_stage=stage,
                )
            )

    await db.commit()
    return OverdueReminderRunResult(
        eligible_fees=len(overdue_rows),
        notifications_created=notifications_created,
        fees_with_new_notifications=fees_with_new_notifications,
        notifications_created_by_stage=notifications_created_by_stage,
        emails=emails,
        sms=sms,
    )


async def send_overdue_fee_reminder_emails(
    db: AsyncSession, emails: list[tuple[uuid.UUID, str, str, str, str | None, str | None, uuid.UUID | None]]
) -> None:
    """Étape d'ENVOI, à appeler APRÈS le commit de `send_overdue_fee_reminders` (voir
    `report_cards/service.py::send_report_card_published_notifications`, même motif de
    découplage) : la transaction métier (frais, notifications in-app, lignes de suivi créées à
    `ATTEMPTED`) est déjà close et ne dépend jamais du résultat de ce qui suit.

    Sprint 1.6 — `db` sert uniquement à reporter, ligne par ligne, le résultat RÉEL du transport
    SMTP (`TRANSPORT_ACCEPTED`/`TRANSPORT_FAILED`) sur la ligne `FeeOverdueEmailReminder` déjà
    créée — jamais à rouvrir ou modifier quoi que ce soit d'autre. Un commit PAR LIGNE (jamais un
    commit unique pour tout le lot) : une interruption du processus n'affecte donc jamais plus
    d'UNE ligne, qui reste alors à `ATTEMPTED` (jamais reportée comme un succès qu'elle n'a pas
    prouvé). `send_email_best_effort` ne lève jamais — un échec d'envoi n'affecte donc jamais les
    notifications in-app ni les lignes de suivi déjà committées, seul le report du résultat en
    tient compte ici. Aucun retry automatique : un `TRANSPORT_FAILED` reste tel quel jusqu'à une
    décision produit explicite, hors périmètre de ce sprint. PR #15 — un `TRANSPORT_FAILED` à un
    palier (ex. J0) n'affecte jamais la ligne, indépendante, d'un palier ultérieur (J7) : chaque
    palier a sa propre ligne, son propre `transport_status`, jamais de dépendance entre elles.

    `db` est une session neuve (voir `app/jobs/overdue_fee_reminders.py::_run`), sans contexte
    tenant encore posé sur CETTE session — `fee_overdue_email_reminders` a la policy RLS
    générique par organisation (migration 0014) : sans élargissement, l'UPDATE ci-dessous
    affecterait silencieusement 0 ligne (jamais une erreur). Même motif que
    `send_overdue_fee_reminders` : job plateforme entière, pas une requête utilisateur scopée.

    Sprint 1.8.1 — correctif d'un bug découvert lors du Sprint 1.8 : `set_platform_wide_context`
    pose une variable de session `SET LOCAL` (voir app/core/tenancy.py), valable UNIQUEMENT pour
    la transaction en cours — `db.commit()` la réinitialise. Appeler cette fonction UNE SEULE
    fois avant la boucle (comme avant ce correctif) ne protège donc que la 1ère itération : à
    partir de la 2e ligne, l'UPDATE s'exécute après un commit qui a déjà effacé le contexte,
    affectant silencieusement 0 ligne sous RLS (la ligne reste alors à `ATTEMPTED` indéfiniment,
    jamais reportée comme `TRANSPORT_ACCEPTED`/`TRANSPORT_FAILED` bien que l'email ait réellement
    été tenté). Vérifié empiriquement (`current_setting` redevient vide juste après un commit sur
    la même session). Corrigé en réappliquant le contexte à CHAQUE itération, juste avant l'UPDATE
    — même correctif déjà appliqué dès l'écriture du Sprint 1.8 pour les emails d'absence
    (voir attendance/service.py::send_absence_reminder_emails)."""
    for reminder_id, to, subject, body, from_name, reply_to, email_school_id in emails:
        accepted = await send_email_best_effort(
            to, subject, body, from_name=from_name, reply_to=reply_to, school_id=email_school_id
        )
        await set_platform_wide_context(db)
        await db.execute(
            update(FeeOverdueEmailReminder)
            .where(FeeOverdueEmailReminder.id == reminder_id)
            .values(
                transport_status="TRANSPORT_ACCEPTED" if accepted else "TRANSPORT_FAILED",
                transport_checked_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()


async def send_overdue_fee_reminder_sms(
    db: AsyncSession, sms: list[tuple[uuid.UUID, str, str]]
) -> None:
    """PR #16 — pendant SMS de `send_overdue_fee_reminder_emails` ci-dessus, même mécanisme exact
    (découplage préparation/envoi, commit PAR ligne, `set_platform_wide_context` réappliqué à
    CHAQUE itération — même correctif Sprint 1.8.1 que pour les emails, appliqué ici
    proactivement). `send_sms_best_effort` ne lève jamais — un échec d'envoi n'affecte donc jamais
    les autres lignes de ce lot ni le reste du job. Un échec (`TRANSPORT_FAILED`) n'est jamais
    retenté automatiquement pour ce MÊME palier (voir fees/models.py::FeeOverdueSmsReminder pour
    la justification complète de ce choix, cohérent avec l'email depuis PR #15) — seul le palier
    SUIVANT sera tenté normalement au prochain passage du job."""
    for reminder_id, to, body in sms:
        accepted, provider_message_id = await send_sms_best_effort(to, body)
        await set_platform_wide_context(db)
        await db.execute(
            update(FeeOverdueSmsReminder)
            .where(FeeOverdueSmsReminder.id == reminder_id)
            .values(
                transport_status="TRANSPORT_ACCEPTED" if accepted else "TRANSPORT_FAILED",
                transport_checked_at=datetime.now(timezone.utc),
                provider_message_id=provider_message_id,
            )
        )
        await db.commit()
