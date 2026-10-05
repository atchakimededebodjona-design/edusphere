import uuid

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.permissions import CurrentUser, DbSession, get_all_permission_codes
from app.core.rate_limit import (
    ensure_forgot_password_not_rate_limited,
    ensure_login_not_rate_limited,
    ensure_reset_password_not_rate_limited,
    register_failed_login_attempt,
    register_forgot_password_attempt,
    register_reset_password_attempt,
    reset_login_attempts,
)
from app.modules.auth import service
from app.modules.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    MeOut,
    RefreshRequest,
    ResetPasswordRequest,
    RoleAssignmentOut,
    SessionOut,
    TokenPair,
)
from app.modules.rbac.models import Role, UserRole

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# Pas de POST /register : la création d'une organisation est réservée aux platform admins, voir
# app/modules/platform/router.py::create_platform_organization.


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, request: Request, db: DbSession) -> TokenPair:
    await ensure_login_not_rate_limited(payload.email)
    try:
        tokens = await service.login(
            db,
            email=payload.email,
            password=payload.password,
            device_id=payload.device_id,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            # Même comptage que le compte existe ou non (cf. `authenticate()` — le 401 est
            # identique dans les deux cas), donc le rate limiting ne révèle jamais d'information
            # sur l'existence d'un compte.
            await register_failed_login_attempt(payload.email)
        raise
    await reset_login_attempts(payload.email)
    return tokens


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, request: Request, db: DbSession) -> TokenPair:
    return await service.refresh(
        db, payload.refresh_token, ip=_client_ip(request), user_agent=request.headers.get("user-agent")
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: LogoutRequest, db: DbSession) -> None:
    await service.logout(db, payload.refresh_token)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(payload: ForgotPasswordRequest, db: DbSession) -> dict:
    await ensure_forgot_password_not_rate_limited(payload.email)
    dev_token = await service.request_password_reset(db, payload.email)
    # Comptée après chaque demande, que le compte existe ou non (Phase 10.1 — voir
    # app/core/rate_limit.py::register_forgot_password_attempt) : limite l'abus d'envoi d'email
    # sans jamais révéler si un compte existe.
    await register_forgot_password_attempt(payload.email)
    # dev_token n'est renseigné que hors environnement "production" (email non intégré
    # en Phase 1) — voir app/modules/auth/service.py::request_password_reset.
    return {"detail": "If this email exists, a reset link has been sent.", "dev_token": dev_token}


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(payload: ResetPasswordRequest, request: Request, db: DbSession) -> None:
    ip = _client_ip(request)
    await ensure_reset_password_not_rate_limited(ip)
    await register_reset_password_attempt(ip)
    await service.reset_password(db, payload.token, payload.new_password)


@router.get("/me", response_model=MeOut)
async def me(current_user: CurrentUser, db: DbSession) -> MeOut:
    result = await db.execute(
        select(UserRole, Role.code)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == current_user.id)
    )
    roles = [
        RoleAssignmentOut(role_code=role_code, organization_id=user_role.organization_id, school_id=user_role.school_id)
        for user_role, role_code in result.all()
    ]
    permissions = sorted(await get_all_permission_codes(db, current_user))

    return MeOut(user=current_user, roles=roles, permissions=permissions)  # type: ignore[arg-type]


@router.get("/sessions", response_model=list[SessionOut])
async def sessions(current_user: CurrentUser, db: DbSession) -> list[SessionOut]:
    user_sessions = await service.list_sessions(db, current_user.id)
    return [SessionOut.model_validate(s, from_attributes=True) for s in user_sessions]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await service.revoke_session(db, current_user.id, session_id)
