import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.core.permissions import CurrentUser, DbSession, ensure_permission
from app.core.rate_limit import ensure_announcements_not_rate_limited, register_announcements_attempt
from app.modules.notifications import service
from app.modules.notifications.schemas import (
    AnnouncementCreate,
    AnnouncementHistoryEntry,
    AnnouncementHistoryOut,
    AnnouncementResult,
    NotificationListOut,
    NotificationOut,
    UnreadCountOut,
)
from app.modules.schools.models import School

router = APIRouter()


async def _get_school_or_404(db: DbSession, school_id: uuid.UUID) -> School:
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    return school


# --- Notifications (auto-scopées à l'utilisateur courant, aucune permission requise — même
# motif que GET /auth/me et GET /auth/sessions) -------------------------------------------------
@router.get("/notifications", response_model=NotificationListOut)
async def list_notifications(
    db: DbSession,
    current_user: CurrentUser,
    before: datetime | None = Query(None),
    limit: int = Query(service.DEFAULT_PAGE_SIZE, ge=1, le=service.MAX_PAGE_SIZE),
) -> NotificationListOut:
    items, next_before = await service.list_notifications(db, current_user.id, before, limit)
    return NotificationListOut(items=[NotificationOut.model_validate(n) for n in items], next_before=next_before)


@router.get("/notifications/unread-count", response_model=UnreadCountOut)
async def get_unread_count(db: DbSession, current_user: CurrentUser) -> UnreadCountOut:
    count = await service.count_unread(db, current_user.id)
    return UnreadCountOut(count=count)


@router.post("/notifications/mark-all-read", response_model=UnreadCountOut)
async def mark_all_notifications_read(db: DbSession, current_user: CurrentUser) -> UnreadCountOut:
    await service.mark_all_read(db, current_user.id)
    return UnreadCountOut(count=0)


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_read(notification_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> NotificationOut:
    notification = await service.mark_read(db, current_user.id, notification_id)
    return NotificationOut.model_validate(notification)


# --- Annonces (SCHOOL_ADMIN/DIRECTOR uniquement) ------------------------------------------------
@router.post("/announcements", response_model=AnnouncementResult, status_code=status.HTTP_201_CREATED)
async def create_announcement(payload: AnnouncementCreate, db: DbSession, current_user: CurrentUser) -> AnnouncementResult:
    await ensure_announcements_not_rate_limited(current_user.id)
    school = await _get_school_or_404(db, payload.school_id)
    await ensure_permission(
        db, current_user, "announcements.manage", organization_id=school.organization_id, school_id=school.id
    )
    await register_announcements_attempt(current_user.id)

    count = await service.create_announcement(
        db,
        school_id=school.id,
        organization_id=school.organization_id,
        title=payload.title,
        body=payload.body,
        target_type=payload.target_type,
        class_ids=payload.class_ids,
    )
    return AnnouncementResult(recipient_count=count)


@router.get("/announcements", response_model=AnnouncementHistoryOut)
async def list_announcements(
    db: DbSession,
    current_user: CurrentUser,
    school_id: uuid.UUID = Query(...),
    before: datetime | None = Query(None),
    limit: int = Query(service.DEFAULT_PAGE_SIZE, ge=1, le=service.MAX_PAGE_SIZE),
) -> AnnouncementHistoryOut:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(
        db, current_user, "announcements.manage", organization_id=school.organization_id, school_id=school.id
    )

    items, next_before = await service.list_school_announcements(db, school.id, school.organization_id, before, limit)
    return AnnouncementHistoryOut(
        items=[AnnouncementHistoryEntry(**entry) for entry in items], next_before=next_before
    )
