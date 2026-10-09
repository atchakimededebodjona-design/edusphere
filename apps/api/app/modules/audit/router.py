import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, Query, status

from app.core.permissions import CurrentUser, DbSession, ensure_permission
from app.modules.audit import service
from app.modules.audit.schemas import AuditLogFilters, AuditLogsOut
from app.modules.schools.models import School

router = APIRouter()


async def _get_school_or_404(db: DbSession, school_id: uuid.UUID) -> School:
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    return school


@router.get("/audit-logs", response_model=AuditLogsOut)
async def list_audit_logs(
    db: DbSession,
    current_user: CurrentUser,
    school_id: uuid.UUID = Query(...),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    actor_user_id: uuid.UUID | None = Query(None),
    action: str | None = Query(None),
    entity_type: str | None = Query(None),
    entity_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> AuditLogsOut:
    """Lecture seule — réservée à `audit.read` (SUPER_ADMIN/PLATFORM_SUPPORT/SCHOOL_ADMIN/DIRECTOR
    uniquement, voir rbac/seed.py::AUDIT_ROLE_PERMISSIONS). Même motif que
    `GET /fees/overdue` : `school_id` résolu et autorisé AVANT toute lecture du journal, jamais un
    `school_id` de filtre appliqué après coup — la policy RLS de `audit_logs` (scoping par
    organisation, voir migration 0020) reste une seconde ligne de défense, pas la seule."""
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "audit.read", organization_id=school.organization_id, school_id=school.id)

    filters = AuditLogFilters(
        date_from=date_from,
        date_to=date_to,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    return await service.list_audit_logs(db, school_id=school_id, filters=filters, page=page, page_size=page_size)
