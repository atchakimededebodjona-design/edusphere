import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import CurrentUser, DbSession, ensure_permission
from app.modules.schools.models import School
from app.modules.users import service
from app.modules.users.schemas import (
    RoleAssignmentOut,
    UserCreateRequest,
    UserCreateResponse,
    UserOut,
    UserWithRolesOut,
)

router = APIRouter()


async def _get_school_or_404(db: AsyncSession, school_id: uuid.UUID) -> School:
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    return school


@router.get("", response_model=list[UserWithRolesOut])
async def list_users(db: DbSession, current_user: CurrentUser, school_id: uuid.UUID = Query(...)) -> list[UserWithRolesOut]:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "users.read", organization_id=school.organization_id, school_id=school.id)

    rows = await service.list_users_for_school(db, school)
    return [
        UserWithRolesOut(
            user=UserOut.model_validate(user),
            roles=[
                RoleAssignmentOut(role_code=r.role_code, organization_id=r.organization_id, school_id=r.school_id)
                for r in roles
            ],
        )
        for user, roles in rows
    ]


@router.post("", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreateRequest, db: DbSession, current_user: CurrentUser) -> UserCreateResponse:
    school = await _get_school_or_404(db, payload.school_id)
    await ensure_permission(db, current_user, "users.manage", organization_id=school.organization_id, school_id=school.id)

    user, roles, dev_reset_token = await service.create_or_attach_user(db, school, payload)
    return UserCreateResponse(
        user=UserOut.model_validate(user),
        roles=[RoleAssignmentOut(role_code=r.role_code, organization_id=r.organization_id, school_id=r.school_id) for r in roles],
        dev_reset_token=dev_reset_token,
    )
