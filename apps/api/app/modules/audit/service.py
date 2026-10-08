import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog
from app.modules.audit.schemas import AuditLogFilters, AuditLogOut, AuditLogsOut
from app.modules.users.models import User

# --- Valeurs documentées de `action`/`entity_type` (PR #14) ------------------------------------
# Catalogue fermé CÔTÉ CODE (pas de contrainte CHECK en base, voir models.py) : toute nouvelle
# action instrumentée dans une future PR doit ajouter sa constante ici plutôt qu'écrire une
# chaîne littérale à l'appel — garantit qu'un seul endroit liste exhaustivement ce qui est tracé.
ACTION_PAYMENT_CANCELLED = "payment.cancelled"
ACTION_STUDENT_FEE_AMOUNT_ADJUSTED = "student_fee.amount_due_adjusted"
ACTION_USER_ROLE_CHANGED = "user.role_changed"
ACTION_USER_STATUS_CHANGED = "user.status_changed"
ACTION_REPORT_CARD_PUBLISHED = "report_card.published"
ACTION_STUDENTS_BULK_PROMOTED = "students.bulk_promoted"
ACTION_STUDENTS_BULK_ASSIGNED = "students.bulk_assigned"

ENTITY_PAYMENT = "Payment"
ENTITY_STUDENT_FEE = "StudentFee"
ENTITY_USER = "User"
ENTITY_REPORT_CARD = "ReportCard"
ENTITY_STUDENT_PROMOTION = "StudentPromotion"
ENTITY_STUDENT_ASSIGNMENT = "StudentAssignment"


async def record_audit_event(
    db: AsyncSession,
    *,
    school_id: uuid.UUID,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    summary: str,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Prépare UNE entrée d'audit et l'ajoute à la session courante — ne fait JAMAIS son propre
    `flush`/`commit`.

    Choix architectural (voir AUDIT EDULINKAGE / PR #14 §5) : plutôt qu'un enregistrement
    "best-effort" séparé après coup (qui permettrait à l'action métier de réussir sans laisser de
    trace si l'écriture d'audit échouait ou était oubliée), ou qu'une table d'outbox dédiée
    (complexité et latence supplémentaires injustifiées : ce dépôt n'a ni worker de traitement
    différé ni file de messages, voir AUDIT EDULINKAGE §6), cette fonction se contente d'un
    `db.add()` sur l'unique session déjà ouverte par l'appelant. Chaque point d'instrumentation
    (fees/service.py::cancel_payment, fees/router.py::update_student_fee,
    users/service.py::update_user_in_school, report_cards/router.py::publish_report_card,
    students/service.py::bulk_promote_students/bulk_assign_students_to_class) appelle CETTE
    fonction juste avant son `await db.commit()` final déjà existant, dans la MÊME transaction que
    la mutation métier qu'elle décrit : succès et trace sont donc committés ensemble, ou annulés
    ensemble en cas de rollback — jamais l'un sans l'autre, sans worker ni polling supplémentaire.
    Une levée d'exception AVANT ce point (échec de validation métier) ne produit donc jamais de
    faux audit de succès, par construction (le code n'atteint simplement jamais cette ligne).

    `actor_user_id` peut être `None` (ex. action système) ; sinon son email est résolu ici une
    fois et figé dans `audit_metadata.actor_email` — jamais recalculé après coup — pour que
    l'identité de l'acteur reste lisible même si son compte est supprimé plus tard (FK
    `ON DELETE SET NULL`, voir models.py)."""
    actor_email: str | None = None
    if actor_user_id is not None:
        actor_email = await db.scalar(select(User.email).where(User.id == actor_user_id))

    entry = AuditLog(
        id=uuid.uuid4(),
        school_id=school_id,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary[:500],
        audit_metadata={"actor_email": actor_email, **(metadata or {})},
    )
    db.add(entry)
    return entry


async def list_audit_logs(
    db: AsyncSession,
    *,
    school_id: uuid.UUID,
    filters: AuditLogFilters,
    page: int,
    page_size: int,
) -> AuditLogsOut:
    """Lecture seule stricte (aucun `db.add`/`flush`/`commit`) — même structure à deux requêtes
    (comptage puis page, jamais de N+1) que `fees/service.py::list_overdue_fees`."""
    conditions = [AuditLog.school_id == school_id]
    if filters.date_from is not None:
        conditions.append(func.date(AuditLog.created_at) >= filters.date_from)
    if filters.date_to is not None:
        conditions.append(func.date(AuditLog.created_at) <= filters.date_to)
    if filters.actor_user_id is not None:
        conditions.append(AuditLog.actor_user_id == filters.actor_user_id)
    if filters.action is not None:
        conditions.append(AuditLog.action == filters.action)
    if filters.entity_type is not None:
        conditions.append(AuditLog.entity_type == filters.entity_type)
    if filters.entity_id is not None:
        conditions.append(AuditLog.entity_id == filters.entity_id)

    count_stmt = select(func.count()).select_from(AuditLog).where(*conditions)
    total = (await db.execute(count_stmt)).scalar_one()

    page_stmt = (
        select(AuditLog, User.email)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(page_stmt)).all()

    items = [
        AuditLogOut(
            id=entry.id,
            school_id=entry.school_id,
            actor_user_id=entry.actor_user_id,
            # Compte encore existant -> email à jour via la jointure ; sinon, repli sur le cliché
            # pris au moment de l'action (voir record_audit_event) — jamais sur une valeur
            # recalculée après coup, qui n'existerait plus de toute façon (FK SET NULL).
            actor_email=live_email or (entry.audit_metadata or {}).get("actor_email"),
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            summary=entry.summary,
            metadata=entry.audit_metadata,
            created_at=entry.created_at,
        )
        for entry, live_email in rows
    ]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return AuditLogsOut(items=items, page=page, page_size=page_size, total=total, total_pages=total_pages)
