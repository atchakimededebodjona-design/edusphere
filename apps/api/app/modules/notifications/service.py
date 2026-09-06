import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import set_platform_wide_context
from app.modules.academics.models import SchoolClass
from app.modules.fees.models import Payment
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import NotificationType
from app.modules.rbac.models import UserRole
from app.modules.report_cards.models import ReportCard
from app.modules.students.models import Guardian, Student, StudentEnrollment, StudentGuardian

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


async def create_notifications(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    school_id: uuid.UUID,
    recipient_user_ids: set[uuid.UUID],
    type_: NotificationType,
    title: str,
    body: str,
) -> int:
    """Écriture en masse (un seul lot `add_all` + `flush`), jamais une boucle de requêtes
    individuelles — voir PHASE_21_DISCOVERY.md §15. `notifications` est la seule table de ce
    projet dont la policy RLS restreint la lecture à `recipient_user_id`, pas à l'organisation
    (voir migration 0011) : sous cette policy, une INSERT pour un destinataire qui n'est pas
    l'utilisateur courant serait refusée par `FORCE ROW LEVEL SECURITY` sans ce contexte
    plateforme — motif identique à `auth/service.py::register` (créer une ligne pour un tiers,
    sans exposer aucune donnée d'un autre tenant, puisque `recipient_user_ids` a déjà été résolu
    de façon tenant-sûre par l'appelant).

    IMPORTANT : élargit le contexte tenant de la transaction courante jusqu'à son commit — à
    appeler uniquement en toute fin de traitement, jamais avant une lecture sensible restante
    dans la même transaction (voir les points d'appel `notify_report_card_published`/
    `notify_payment_recorded`/`create_announcement`, chacun l'appelle en dernier)."""
    if not recipient_user_ids:
        return 0

    await set_platform_wide_context(db)
    for user_id in recipient_user_ids:
        db.add(
            Notification(
                id=uuid.uuid4(),
                school_id=school_id,
                organization_id=organization_id,
                recipient_user_id=user_id,
                type=type_,
                title=title,
                body=body,
            )
        )
    await db.flush()
    return len(recipient_user_ids)


async def resolve_guardian_user_ids_for_student(db: AsyncSession, student_id: uuid.UUID, school_id: uuid.UUID) -> set[uuid.UUID]:
    """Tuteurs de cet élève disposant d'un compte utilisateur (`Guardian.user_id` non nul) — un
    guardian sans compte n'a par définition aucune destination pour une notification in-app
    (contrairement à l'email, qui ne nécessite qu'une adresse — voir Discovery §10.A)."""
    result = await db.execute(
        select(Guardian.user_id)
        .join(StudentGuardian, StudentGuardian.guardian_id == Guardian.id)
        .where(
            StudentGuardian.student_id == student_id,
            StudentGuardian.school_id == school_id,
            Guardian.user_id.isnot(None),
        )
    )
    return {row[0] for row in result.all()}


async def notify_report_card_published(db: AsyncSession, report_card: ReportCard) -> None:
    student = await db.get(Student, report_card.student_id)
    if student is None:
        return
    recipient_ids = await resolve_guardian_user_ids_for_student(db, student.id, report_card.school_id)
    await create_notifications(
        db,
        organization_id=report_card.organization_id,
        school_id=report_card.school_id,
        recipient_user_ids=recipient_ids,
        type_="REPORT_CARD_PUBLISHED",
        title="Bulletin disponible",
        # Jamais de moyenne/rang/appréciation dans le corps — même principe que l'email existant
        # (report_cards/service.py::prepare_report_card_published_notifications), le détail reste
        # consultable uniquement après authentification dans l'app (voir Discovery §12/§30).
        body=f"Le bulletin de {student.first_name} {student.last_name} est disponible.",
    )


async def notify_payment_recorded(db: AsyncSession, student: Student, payment: Payment) -> None:
    recipient_ids = await resolve_guardian_user_ids_for_student(db, student.id, payment.school_id)
    await create_notifications(
        db,
        organization_id=payment.organization_id,
        school_id=payment.school_id,
        recipient_user_ids=recipient_ids,
        type_="PAYMENT_RECORDED",
        title="Paiement enregistré",
        # Contenu minimal, aucun montant/détail comptable — voir Discovery §29.
        body=f"Un paiement a été enregistré pour {student.first_name} {student.last_name}.",
    )


async def resolve_school_member_user_ids(db: AsyncSession, school_id: uuid.UUID, organization_id: uuid.UUID) -> set[uuid.UUID]:
    """Tous les comptes rattachés à cette école : rôle scopé directement à cette école, OU rôle
    porté au niveau organisation SANS école précise (`school_id IS NULL` — ex. le SCHOOL_ADMIN créé
    à l'inscription, `auth/service.py::register`). Parents, enseignants, staff, administration
    inclus, puisque tous obtiennent une `UserRole` scopée de cette façon quel que soit leur rôle
    (voir PHASE_21_DISCOVERY.md §10).

    Volontairement PLUS STRICT que `users/service.py::list_users_for_school` (qui matche tout
    `organization_id` égal, sans exiger `school_id IS NULL` sur cette branche) : pour une
    fonctionnalité de diffusion de masse comme une annonce, laisser cette condition telle quelle
    inclurait aussi le personnel d'une AUTRE école de la même organisation dès lors qu'il a un
    rôle explicitement scopé à cette autre école — une fuite cross-école inacceptable pour une
    annonce, même si le risque pratique de `list_users_for_school` (un écran de gestion, pas de
    diffusion) est moindre. Non corrigé dans `list_users_for_school` lui-même : hors périmètre de
    cette phase."""
    result = await db.execute(
        select(UserRole.user_id.distinct()).where(
            or_(
                UserRole.school_id == school_id,
                and_(UserRole.organization_id == organization_id, UserRole.school_id.is_(None)),
            )
        )
    )
    return {row[0] for row in result.all()}


async def resolve_class_guardian_user_ids(db: AsyncSession, class_ids: list[uuid.UUID], school_id: uuid.UUID) -> set[uuid.UUID]:
    """Tuteurs avec compte des élèves activement inscrits dans une des classes ciblées — une
    annonce de classe s'adresse aux parents, pas aux enseignants (qui ont déjà une visibilité sur
    leurs classes via d'autres écrans) — décision documentée, Discovery §14/§21."""
    result = await db.execute(
        select(Guardian.user_id.distinct())
        .join(StudentGuardian, StudentGuardian.guardian_id == Guardian.id)
        .join(Student, Student.id == StudentGuardian.student_id)
        .join(
            StudentEnrollment,
            (StudentEnrollment.student_id == Student.id) & (StudentEnrollment.status == "ACTIVE"),
        )
        .where(
            StudentEnrollment.class_id.in_(class_ids),
            StudentGuardian.school_id == school_id,
            Guardian.user_id.isnot(None),
        )
    )
    return {row[0] for row in result.all()}


async def create_announcement(
    db: AsyncSession,
    *,
    school_id: uuid.UUID,
    organization_id: uuid.UUID,
    title: str,
    body: str,
    target_type: str,
    class_ids: list[uuid.UUID] | None,
) -> int:
    if target_type == "CLASS":
        if not class_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="class_ids is required for CLASS target")
        result = await db.execute(select(SchoolClass.id).where(SchoolClass.id.in_(class_ids), SchoolClass.school_id == school_id))
        found_ids = {row[0] for row in result.all()}
        if found_ids != set(class_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="One or more classes do not belong to this school")
        recipient_ids = await resolve_class_guardian_user_ids(db, class_ids, school_id)
    else:  # SCHOOL
        if class_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SCHOOL target must not include class_ids")
        recipient_ids = await resolve_school_member_user_ids(db, school_id, organization_id)

    count = await create_notifications(
        db,
        organization_id=organization_id,
        school_id=school_id,
        recipient_user_ids=recipient_ids,
        type_="ANNOUNCEMENT",
        title=title,
        body=body,
    )
    await db.commit()
    return count


async def list_school_announcements(
    db: AsyncSession, school_id: uuid.UUID, organization_id: uuid.UUID, before: datetime | None, limit: int
) -> tuple[list[dict], datetime | None]:
    """Phase 22 — historique en lecture seule des annonces déjà envoyées pour une école, à
    l'usage de SCHOOL_ADMIN/DIRECTOR (même permission `announcements.manage` que l'envoi).

    `notifications` est restreinte par la policy RLS `recipient_user_id` (migration 0011) : un
    administrateur n'est pas forcément destinataire de ses propres annonces ciblées CLASS (seuls
    les tuteurs le sont, voir `resolve_class_guardian_user_ids`) — une lecture sous son contexte
    tenant normal ne verrait donc jamais ces envois-là. Bypass RLS explicite et délibéré via
    `set_platform_wide_context`, même motif que `create_notifications` : la tenant-sûreté est
    garantie ici par le filtre `school_id`/`organization_id` explicite ci-dessous, pas par la
    policy. Ne renvoie JAMAIS `recipient_user_id`/`read_at` (pas d'accusé de lecture par
    destinataire — hors périmètre, voir PHASE_21_IMPLEMENTATION.md §21) : uniquement un agrégat
    (titre/corps/type/date/nombre de destinataires), déjà connu de l'auteur au moment de l'envoi
    (`recipient_count` était déjà retourné par `POST /announcements`). Les lignes d'une même
    annonce partagent exactement le même `created_at` (une seule transaction, un seul `flush` —
    `now()` PostgreSQL est stable pour toute la transaction), d'où le regroupement par
    (title, body, type, created_at) sans nouvelle colonne "announcement_id"."""
    await set_platform_wide_context(db)

    page_size = min(max(limit, 1), MAX_PAGE_SIZE)
    stmt = (
        select(
            Notification.title,
            Notification.body,
            Notification.type,
            Notification.created_at,
            func.count().label("recipient_count"),
        )
        .where(
            Notification.school_id == school_id,
            Notification.organization_id == organization_id,
            Notification.type == "ANNOUNCEMENT",
        )
        .group_by(Notification.title, Notification.body, Notification.type, Notification.created_at)
    )
    if before is not None:
        stmt = stmt.where(Notification.created_at < before)
    stmt = stmt.order_by(Notification.created_at.desc()).limit(page_size + 1)

    result = await db.execute(stmt)
    rows = result.all()

    has_more = len(rows) > page_size
    items = rows[:page_size]
    next_before = items[-1].created_at if has_more else None
    entries = [
        {
            "title": row.title,
            "body": row.body,
            "type": row.type,
            "created_at": row.created_at,
            "recipient_count": row.recipient_count,
        }
        for row in items
    ]
    return entries, next_before


# --- Lecture / non-lue ---------------------------------------------------------------------------


async def list_notifications(
    db: AsyncSession, user_id: uuid.UUID, before: datetime | None, limit: int
) -> tuple[list[Notification], datetime | None]:
    page_size = min(max(limit, 1), MAX_PAGE_SIZE)
    stmt = select(Notification).where(Notification.recipient_user_id == user_id)
    if before is not None:
        stmt = stmt.where(Notification.created_at < before)
    stmt = stmt.order_by(Notification.created_at.desc()).limit(page_size + 1)

    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    has_more = len(rows) > page_size
    items = rows[:page_size]
    next_before = items[-1].created_at if has_more else None
    return items, next_before


async def count_unread(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.recipient_user_id == user_id, Notification.read_at.is_(None))
    )
    return result.scalar_one()


async def mark_read(db: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
    notification = await db.get(Notification, notification_id)
    # RLS restreint déjà `db.get` aux notifications de `user_id` (ou contexte plateforme) — ce
    # contrôle applicatif reste une seconde ligne de défense, motif systématique de ce projet.
    if notification is None or notification.recipient_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(notification)
        await db.commit()
    return notification


async def mark_all_read(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(Notification).where(Notification.recipient_user_id == user_id, Notification.read_at.is_(None))
    )
    rows = list(result.scalars().all())
    now = datetime.now(timezone.utc)
    for row in rows:
        row.read_at = now
    await db.flush()
    await db.commit()
    return len(rows)
