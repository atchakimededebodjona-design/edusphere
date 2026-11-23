import uuid

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import CurrentUser, DbSession, ensure_permission
from app.modules.schools.models import School
from app.modules.users import photo, service
from app.modules.users.schemas import (
    RoleAssignmentOut,
    UserCreateRequest,
    UserCreateResponse,
    UserOut,
    UserUpdateRequest,
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

    user, roles, dev_reset_token = await service.create_or_attach_user(db, school, payload, current_user.id)
    return UserCreateResponse(
        user=UserOut.model_validate(user),
        roles=[RoleAssignmentOut(role_code=r.role_code, organization_id=r.organization_id, school_id=r.school_id) for r in roles],
        dev_reset_token=dev_reset_token,
    )


@router.patch("/{user_id}", response_model=UserWithRolesOut)
async def update_user(
    user_id: uuid.UUID, payload: UserUpdateRequest, db: DbSession, current_user: CurrentUser
) -> UserWithRolesOut:
    school = await _get_school_or_404(db, payload.school_id)
    await ensure_permission(db, current_user, "users.manage", organization_id=school.organization_id, school_id=school.id)

    user, roles = await service.update_user_in_school(db, school, user_id, payload, current_user.id)
    return UserWithRolesOut(
        user=UserOut.model_validate(user),
        roles=[RoleAssignmentOut(role_code=r.role_code, organization_id=r.organization_id, school_id=r.school_id) for r in roles],
    )


# --- Photo d'identité d'un membre du personnel (2026-11-19, migration 0036) ---------------------
# Lecture : `users.read` de l'école ; mise et retrait : `users.manage`, mêmes règles d'autorité que
# la modification d'un compte (users/service.py::load_school_member). Le compte lui-même passe par
# /auth/me/photo.
@router.post("/{user_id}/photo", response_model=UserOut)
async def upload_user_photo(
    user_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    school_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
) -> UserOut:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "users.manage", organization_id=school.organization_id, school_id=school.id)
    user = await service.load_school_member(db, school, user_id, current_user.id, modify=True)
    content = await file.read()
    return UserOut.model_validate(await photo.replace_user_photo(db, user, content, file.filename))


@router.get("/{user_id}/photo")
async def get_user_photo(
    user_id: uuid.UUID, db: DbSession, current_user: CurrentUser, school_id: uuid.UUID = Query(...)
) -> Response:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "users.read", organization_id=school.organization_id, school_id=school.id)
    user = await service.load_school_member(db, school, user_id, current_user.id, modify=False)
    return await photo.user_photo_response(user)


@router.delete("/{user_id}/photo", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_photo(
    user_id: uuid.UUID, db: DbSession, current_user: CurrentUser, school_id: uuid.UUID = Query(...)
) -> None:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "users.manage", organization_id=school.organization_id, school_id=school.id)
    user = await service.load_school_member(db, school, user_id, current_user.id, modify=True)
    await photo.remove_user_photo(db, user)
