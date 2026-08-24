from fastapi import APIRouter
from sqlalchemy import select

from app.core.permissions import CurrentUser, DbSession
from app.modules.rbac.models import Permission, Role
from app.modules.rbac.schemas import PermissionOut, RoleOut

router = APIRouter()


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(db: DbSession, _current_user: CurrentUser) -> list[Role]:
    result = await db.execute(select(Role).order_by(Role.code))
    return list(result.scalars().all())


@router.get("/permissions", response_model=list[PermissionOut])
async def list_permissions(db: DbSession, _current_user: CurrentUser) -> list[Permission]:
    result = await db.execute(select(Permission).order_by(Permission.code))
    return list(result.scalars().all())
