import logging
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import send_email_best_effort
from app.core.tenancy import apply_tenant_context
from app.modules.academics.models import AcademicTerm, ClassSubject, SchoolClass, TeacherAssignment
from app.modules.attendance.models import AttendanceAbsenceEmailReminder, AttendanceRecord, AttendanceSession
from app.modules.notifications.service import (
    existing_absence_emailed_guardian_ids,
    notify_student_absent,
    resolve_guardian_emails_without_account_for_student,
)
from app.modules.schools.models import School
from app.modules.students.models import Student, StudentEnrollment

logger = logging.getLogger(__name__)

EmailTuple = tuple[uuid.UUID, str, str, str, str | None, str | None, uuid.UUID | None]


async def is_teacher_assigned_to_class(db: AsyncSession, user_id: uuid.UUID, class_id: uuid.UUID) -> bool:
    """Un enseignant peut faire l'appel d'une classe s'il a au moins une TeacherAssignment sur une
    matière de cette classe — même règle que academics/router.py::list_classes, sans introduire de
    notion de professeur principal (décision validée, PHASE_6_ATTENDANCE_PLAN.md §6)."""
    result = await db.execute(
        select(TeacherAssignment.id)
        .join(ClassSubject, ClassSubject.id == TeacherAssignment.class_subject_id)
        .where(ClassSubject.class_id == class_id, TeacherAssignment.user_id == user_id)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def validate_session_date(school_class: SchoolClass, academic_term: AcademicTerm, session_date: date) -> None:
    """Cohérence classe <-> période, puis appartenance de la date à la période — les dates futures
    sont explicitement autorisées tant que la date reste dans la période académique (décision
    validée, PHASE_6_ATTENDANCE_PLAN.md §9, §23)."""
    if academic_term.academic_year_id != school_class.academic_year_id:
        raise ValueError("Academic term does not belong to the class's academic year")
    if not (academic_term.start_date <= session_date <= academic_term.end_date):
        raise ValueError("Session date is outside the academic term period")


async def student_in_class_scope(db: AsyncSession, student: Student, class_id: uuid.UUID) -> bool:
    """Vérifie qu'un élève est activement inscrit dans la classe de la session — École ET Classe,
    pas seulement l'école (renforcement validé vs. ce que fait `grades` aujourd'hui)."""
    result = await db.execute(
        select(StudentEnrollment.id).where(
            StudentEnrollment.student_id == student.id,
            StudentEnrollment.class_id == class_id,
            StudentEnrollment.status == "ACTIVE",
        )
    )
    return result.scalar_one_or_none() is not None


def _format_absence_email_body(student: Student, school_name: str, absence_date: date) -> str:
    where = f" à {school_name}" if school_name else ""
    return f"{student.first_name} {student.last_name} a été marqué(e) absent(e) le {absence_date.isoformat()}{where}."


async def _prepare_absence_emails(
    db: AsyncSession, *, student: Student, record: AttendanceRecord, session: AttendanceSession
) -> list[EmailTuple]:
    """Sprint 1.8 — pendant, pour les absences, de `fees/overdue_reminders.py::
    _prepare_overdue_emails` : LECTURE + enregistrement du suivi d'idempotence (dans la transaction
    en cours), pour les tuteurs SANS compte utilisateur de cet élève. L'envoi réseau réel n'a lieu
    qu'après le commit de l'appelant (voir `send_absence_reminder_emails`), même découplage.

    Chaque ligne de suivi est écrite dans un SAVEPOINT dédié (`db.begin_nested`) : une écriture
    concurrente (ex. resoumission simultanée) qui gagnerait la course sur la contrainte unique
    (student_id, guardian_id, absence_date) ne doit annuler que CET envoi, jamais la transaction
    entière (qui contient aussi la notification in-app déjà flush-ée)."""
    candidates = await resolve_guardian_emails_without_account_for_student(db, student.id, record.school_id)
    if not candidates:
        return []

    already_emailed = await existing_absence_emailed_guardian_ids(db, student.id, session.session_date)
    school = await db.get(School, record.school_id)
    school_name = school.name if school is not None else ""
    subject = f"Absence signalée — {student.first_name} {student.last_name}"
    body = _format_absence_email_body(student, school_name, session.session_date)
    # Phase 24B — réutilise `school` déjà chargé ci-dessus (aucun second accès DB) pour
    # l'identité d'expéditeur, partagée par tous les tuteurs de cette même absence/école.
    from_name = school.name if school is not None else None
    reply_to = school.email if school is not None else None
    email_school_id = school.id if school is not None else None

    emails: list[EmailTuple] = []
    for guardian_id, full_name, email in candidates:
        if guardian_id in already_emailed:
            continue
        reminder_id = uuid.uuid4()
        try:
            async with db.begin_nested():
                db.add(
                    AttendanceAbsenceEmailReminder(
                        id=reminder_id,
                        school_id=record.school_id,
                        organization_id=record.organization_id,
                        student_id=student.id,
                        guardian_id=guardian_id,
                        attendance_id=record.id,
                        absence_date=session.session_date,
                        transport_status="ATTEMPTED",
                    )
                )
                await db.flush()
        except IntegrityError:
            logger.warning(
                "attendance_absence_email: email déjà tracé pour (student_id=%s, guardian_id=%s, "
                "absence_date=%s), ignoré.",
                student.id,
                guardian_id,
                session.session_date,
            )
            continue
        emails.append(
            (
                reminder_id,
                email,
                subject,
                f"Bonjour {full_name},\n\n{body}\n\n"
                "Cet email a été envoyé via EduLinkage, plateforme de gestion scolaire.",
                from_name,
                reply_to,
                email_school_id,
            )
        )

    return emails


async def send_absence_reminder_emails(db: AsyncSession, current_user_id: uuid.UUID, emails: list[EmailTuple]) -> None:
    """Étape d'ENVOI, à appeler APRÈS le commit de `upsert_records`/`attendance/router.py::
    update_record` (même motif de découplage que `fees/overdue_reminders.py::
    send_overdue_fee_reminder_emails`) : la transaction métier (absence, notification in-app,
    lignes de suivi créées à ATTEMPTED) est déjà close et ne dépend jamais du résultat de ce qui
    suit — un échec d'envoi ne peut jamais annuler l'absence déjà enregistrée.

    Contrairement au job batch équivalent des frais (session sans contexte tenant, élargie en
    `set_platform_wide_context`), cette fonction s'exécute dans le contexte d'une requête HTTP
    authentifiée normale. `db.commit()` termine la transaction Postgres et réinitialise donc les
    variables de session posées par `SET LOCAL` (voir app/core/tenancy.py — vérifié empiriquement :
    `current_setting` redevient vide juste après un commit sur la même session) : sans réappliquer
    le contexte, l'UPDATE ci-dessous affecterait silencieusement 0 ligne sous RLS. `apply_tenant_context`
    (plutôt que `set_platform_wide_context`) restaure le scope tenant précis de l'utilisateur
    courant — pas un accès plateforme entière non nécessaire ici. Réappliqué À CHAQUE itération
    (pas une seule fois avant la boucle) car le commit par ligne ci-dessous réinitialise
    systématiquement ce contexte après chaque itération.

    Commit PAR LIGNE (jamais un commit unique pour tout le lot) — même garantie que Sprint 1.6 :
    une interruption n'affecte donc jamais plus d'UNE ligne, qui reste alors à `ATTEMPTED`."""
    for reminder_id, to, subject, body, from_name, reply_to, email_school_id in emails:
        accepted = await send_email_best_effort(
            to, subject, body, from_name=from_name, reply_to=reply_to, school_id=email_school_id
        )
        await apply_tenant_context(db, current_user_id)
        await db.execute(
            update(AttendanceAbsenceEmailReminder)
            .where(AttendanceAbsenceEmailReminder.id == reminder_id)
            .values(
                transport_status="TRANSPORT_ACCEPTED" if accepted else "TRANSPORT_FAILED",
                transport_checked_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()


async def maybe_notify_absence(
    db: AsyncSession, record: AttendanceRecord, previous_status: str | None, session: AttendanceSession
) -> list[EmailTuple]:
    """Phase 27 Sprint 1 — notifie les tuteurs UNIQUEMENT quand le statut DEVIENT ABSENT :
    - création directe en ABSENT (`previous_status is None`) -> notifie ;
    - PRESENT/LATE -> ABSENT -> notifie ;
    - ABSENT -> ABSENT (resoumission idempotente de l'appel, ou correction de `justified`/`reason`
      seule) -> ne notifie PAS une seconde fois (anti-spam, règle explicite du sprint) ;
    - ABSENT -> PRESENT/LATE, ou tout statut qui n'est pas ABSENT -> ne notifie jamais.
    Appelée pour CHAQUE écriture d'un AttendanceRecord (création, resoumission en masse, correction
    unitaire) — voir les deux points d'appel : `upsert_records` ci-dessous et
    `attendance/router.py::update_record`.

    Sprint 1.8 — prépare EN PLUS, pour les mêmes conditions, les emails destinés aux tuteurs SANS
    compte utilisateur (voir `_prepare_absence_emails`) ; les retourne pour que l'appelant les
    envoie APRÈS son commit (jamais avant, voir `send_absence_reminder_emails`)."""
    if record.status != "ABSENT" or previous_status == "ABSENT":
        return []
    student = await db.get(Student, record.student_id)
    if student is None:
        return []
    await notify_student_absent(db, student, record)
    return await _prepare_absence_emails(db, student=student, record=record, session=session)


async def upsert_records(
    db: AsyncSession,
    session: AttendanceSession,
    entries: list[tuple[uuid.UUID, str, bool, str | None]],
    recorded_by: uuid.UUID | None,
) -> tuple[list[AttendanceRecord], list[EmailTuple]]:
    """Upsert idempotent par (session_id, student_id) : une resoumission identique laisse le même
    état final, sans erreur ni duplication — propriété requise pour un futur mode offline (décision
    validée, PHASE_6_ATTENDANCE_PLAN.md §9).

    Sprint 1.8 — retourne désormais aussi les emails préparés (tuteurs SANS compte, voir
    `maybe_notify_absence`/`_prepare_absence_emails`) pour que l'appelant les envoie APRÈS son
    commit (voir `attendance/router.py::submit_records` + `send_absence_reminder_emails`)."""
    saved: list[AttendanceRecord] = []
    previous_statuses: dict[uuid.UUID, str | None] = {}
    for student_id, status, justified, reason in entries:
        result = await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.session_id == session.id, AttendanceRecord.student_id == student_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = AttendanceRecord(
                id=uuid.uuid4(),
                school_id=session.school_id,
                organization_id=session.organization_id,
                session_id=session.id,
                student_id=student_id,
            )
            db.add(row)
            previous_statuses[row.id] = None
        else:
            previous_statuses[row.id] = row.status
        row.status = status
        row.justified = justified
        row.reason = reason
        row.recorded_by = recorded_by
        saved.append(row)

    await db.flush()
    # refresh() AVANT commit : ces tables ont RLS activée, leurs lignes ne sont visibles que le
    # temps de la transaction courante (même piège documenté dans grades/service.py).
    for row in saved:
        await db.refresh(row)
    # Notifications d'absence — APRÈS refresh (état final connu), AVANT commit : même contrainte
    # que create_notifications (le contexte RLS élargi via set_platform_wide_context doit vivre
    # dans CETTE transaction, voir notifications/service.py).
    emails: list[EmailTuple] = []
    for row in saved:
        emails.extend(await maybe_notify_absence(db, row, previous_statuses[row.id], session))
    await db.commit()
    return saved, emails


def _summarize(rows: list[tuple[str, bool]]) -> dict:
    """(présents + retards) / total × 100 — un retard compte comme une présence pour le taux
    (décision validée, PHASE_6_ATTENDANCE_PLAN.md §16/§23)."""
    total = len(rows)
    present = sum(1 for status, _ in rows if status == "PRESENT")
    absent = sum(1 for status, _ in rows if status == "ABSENT")
    late = sum(1 for status, _ in rows if status == "LATE")
    justified_absences = sum(1 for status, justified in rows if status == "ABSENT" and justified)
    rate = round((present + late) / total * 100, 2) if total > 0 else None
    return {
        "total_sessions": total,
        "present_count": present,
        "absent_count": absent,
        "late_count": late,
        "justified_absence_count": justified_absences,
        "attendance_rate": rate,
    }


async def compute_student_summary(
    db: AsyncSession, student_id: uuid.UUID, academic_term_id: uuid.UUID | None = None
) -> dict:
    """`academic_term_id=None` agrège toutes les sessions de l'élève, toutes périodes confondues
    — élargissement rétrocompatible (Phase 7) pour le module `parent`, qui n'impose pas de
    sélecteur de période sur mobile ; le endpoint existant (`attendance/router.py`) continue de
    toujours fournir un `academic_term_id` concret, comportement inchangé."""
    stmt = select(AttendanceRecord.status, AttendanceRecord.justified).join(
        AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id
    ).where(AttendanceRecord.student_id == student_id)
    if academic_term_id is not None:
        stmt = stmt.where(AttendanceSession.academic_term_id == academic_term_id)
    result = await db.execute(stmt)
    return _summarize([(status, justified) for status, justified in result.all()])


async def compute_school_summary(db: AsyncSession, school_id: uuid.UUID, academic_term_id: uuid.UUID) -> dict:
    """Même formule que `compute_student_summary`/`compute_class_statistics` (Phase 6), agrégée
    à l'échelle de l'école pour une période — utilisé par le tableau de bord admin (Phase 10),
    aucune nouvelle règle métier."""
    result = await db.execute(
        select(AttendanceRecord.status, AttendanceRecord.justified)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .where(AttendanceRecord.school_id == school_id, AttendanceSession.academic_term_id == academic_term_id)
    )
    return _summarize([(status, justified) for status, justified in result.all()])


async def compute_class_statistics(db: AsyncSession, class_id: uuid.UUID, academic_term_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(AttendanceRecord.student_id, AttendanceRecord.status, AttendanceRecord.justified)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .where(AttendanceSession.class_id == class_id, AttendanceSession.academic_term_id == academic_term_id)
    )
    by_student: dict[uuid.UUID, list[tuple[str, bool]]] = {}
    for student_id, status, justified in result.all():
        by_student.setdefault(student_id, []).append((status, justified))

    return [{"student_id": student_id, **_summarize(entries)} for student_id, entries in by_student.items()]
