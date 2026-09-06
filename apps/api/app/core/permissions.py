import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.log_context import user_id_var
from app.core.security import decode_access_token
from app.core.tenancy import apply_tenant_context
from app.db.session import get_db
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.users.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if token is None:
        raise CREDENTIALS_ERROR
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise CREDENTIALS_ERROR from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise CREDENTIALS_ERROR

    # Phase 23 — dès qu'une requête est authentifiée, user_id devient disponible pour la
    # corrélation de logs (voir app/core/log_context.py) : point d'entrée unique, déjà traversé
    # par la quasi-totalité des endpoints métier, pas de nouveau paramètre à ajouter ailleurs.
    user_id_var.set(str(user.id))
    await apply_tenant_context(db, user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_scoped_permission_codes(
    db: AsyncSession,
    user: User,
    organization_id: uuid.UUID | None = None,
    school_id: uuid.UUID | None = None,
) -> set[str]:
    """Permissions effectives de `user` pour la portée demandée.

    Une attribution de rôle plateforme (organization_id ET school_id NULL) s'applique partout.
    Une attribution scopée organisation s'applique si elle correspond à `organization_id` — mais
    UNIQUEMENT si cette attribution est elle-même org-wide (`school_id IS NULL`, ex. le
    SCHOOL_ADMIN créé à l'inscription — `auth/service.py::register`). Une attribution scopée à
    une école précise s'applique si elle correspond exactement à `school_id`.

    Phase 24 — corrige un bug confirmé (Discovery Phase 24, en marge du problème initialement
    signalé sur `list_users_for_school`, mais de même nature et de portée bien plus large) :
    avant ce correctif, `UserRole.organization_id == organization_id` matchait aussi une
    attribution scopée à une AUTRE école de la même organisation (`school_id` non nul), ce qui
    accordait à tort les permissions de cette autre école — vérifié empiriquement : un TEACHER
    affecté exclusivement à l'école B pouvait lister/lire les élèves de l'école A (même
    organisation) via `GET /students?school_id=<école A>`. RLS ne bloque pas ce cas non plus
    (la policy générique `{table}_tenant_isolation` est basée sur l'organisation, pas l'école) —
    ce contrôle applicatif est donc la seule ligne de défense réelle ici.
    """
    conditions = [and_(UserRole.organization_id.is_(None), UserRole.school_id.is_(None))]
    if organization_id is not None:
        conditions.append(and_(UserRole.organization_id == organization_id, UserRole.school_id.is_(None)))
    if school_id is not None:
        conditions.append(UserRole.school_id == school_id)

    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id, or_(*conditions))
    )
    result = await db.execute(stmt)
    return {row[0] for row in result.all()}


async def get_all_permission_codes(db: AsyncSession, user: User) -> set[str]:
    """Union des permissions accessibles à `user`, toutes portées confondues (utilisé par /me)."""
    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id)
    )
    result = await db.execute(stmt)
    return {row[0] for row in result.all()}


def require_permission(code: str):
    """Dependency pour les endpoints sans ressource ciblée (listes plateforme, création)."""

    async def dependency(current_user: CurrentUser, db: DbSession) -> User:
        codes = await get_scoped_permission_codes(db, current_user)
        if code not in codes:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
        return current_user

    return dependency


async def is_teacher_only(db: AsyncSession, user: User, organization_id: uuid.UUID, school_id: uuid.UUID) -> bool:
    """True si, pour cette école, le seul rôle de l'utilisateur est TEACHER — cas où la règle
    métier « un enseignant ne voit que ses classes/matières » (cahier des charges §10)
    s'applique. Un DIRECTOR/STAFF/SCHOOL_ADMIN voit toujours tout.

    Phase 24 — même correctif que `get_scoped_permission_codes` : un rôle scopé à une AUTRE école
    de la même organisation (`school_id` non nul) ne doit compter que si `school_id IS NULL`
    (rôle réellement org-wide). Sans ce garde-fou, un utilisateur tenant par ailleurs un second
    rôle (ex. STAFF) dans une autre école de l'organisation ferait basculer `role_codes` hors de
    `{"TEACHER"}` pour CETTE école, désactivant à tort la restriction stricte
    « affectation TeacherAssignment requise » alors même que son seul rôle légitime ici reste
    TEACHER."""
    result = await db.execute(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user.id,
            (UserRole.school_id == school_id)
            | (and_(UserRole.organization_id == organization_id, UserRole.school_id.is_(None)))
            | (UserRole.organization_id.is_(None) & UserRole.school_id.is_(None)),
        )
    )
    role_codes = {row[0] for row in result.all()}
    return role_codes == {"TEACHER"}


async def ensure_permission(
    db: AsyncSession,
    user: User,
    code: str,
    organization_id: uuid.UUID | None = None,
    school_id: uuid.UUID | None = None,
) -> None:
    """À appeler dans un handler après avoir chargé une ressource, pour vérifier une permission
    scopée à son organisation/école (ex. PATCH /schools/{id})."""
    codes = await get_scoped_permission_codes(db, user, organization_id=organization_id, school_id=school_id)
    if code not in codes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
