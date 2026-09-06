"""Phase 22 — Pilot Operations & Data Integrity Hardening.

Couvre les sujets qui n'ont pas déjà leur propre fichier de tests dédié : RLS `user_sessions` /
`password_reset_tokens` (gap identifié en Discovery Phase 22, migration 0012), et rate limiting
des 4 endpoints identifiés comme insuffisamment protégés (reset-password, payments, payments/
cancel, announcements). La correction IDOR de `grades` a ses tests dans test_grades.py, la
gestion des comptes dans test_users.py, l'historique des annonces dans test_notifications.py, la
validation de configuration production dans test_production_config.py.
"""

import asyncio
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis

import app.core.rate_limit as rate_limit_module
from app.core.config import settings
from app.core.rate_limit import _get_client
from tests.conftest import register_school, unique_email


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _clear_pattern(pattern: str) -> None:
    client = _get_client()
    async for key in client.scan_iter(match=pattern):
        await client.delete(key)


# === RLS — user_sessions =========================================================================
async def test_user_sessions_relrowsecurity_and_force_are_set() -> None:
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'user_sessions'")
        )
        row = result.one()
        assert row.relrowsecurity is True
        assert row.relforcerowsecurity is True


async def test_user_sessions_policy_exists() -> None:
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT polname FROM pg_policy WHERE polrelid = 'user_sessions'::regclass"))
        names = {row[0] for row in result.all()}
        assert "user_sessions_self_isolation" in names


async def test_row_level_security_hides_other_users_session(client: AsyncClient) -> None:
    """Preuve RLS brute : sous le contexte tenant de l'utilisateur A, la session de B est
    invisible même via une requête directe qui ne filtre pas explicitement par user_id."""
    from sqlalchemy import select

    from app.core.tenancy import apply_tenant_context
    from app.db.session import AsyncSessionLocal
    from app.modules.auth.models import UserSession

    data_a = await register_school(client, "sessrlsa")
    data_b = await register_school(client, "sessrlsb")

    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(data_a["user"]["id"]))
        result = await db.execute(select(UserSession).where(UserSession.user_id == uuid.UUID(data_b["user"]["id"])))
        assert result.scalar_one_or_none() is None

        own = await db.execute(select(UserSession).where(UserSession.user_id == uuid.UUID(data_a["user"]["id"])))
        assert own.scalar_one_or_none() is not None
        await db.rollback()


async def test_login_refresh_logout_still_work_under_user_sessions_rls(client: AsyncClient) -> None:
    """Non-régression explicite (Phase 22) : les 3 flux pré-authentifiés qui écrivent/lisent
    `user_sessions` sans contexte tenant préalable doivent continuer à fonctionner (bypass
    explicite ajouté dans auth/service.py::_issue_tokens/_get_active_session)."""
    data = await register_school(client, "sessrlsflow")
    refresh_token = data["tokens"]["refresh_token"]

    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refreshed.status_code == 200, refreshed.text
    new_refresh_token = refreshed.json()["refresh_token"]

    login_again = await client.post(
        "/api/v1/auth/login", json={"email": data["user"]["email"], "password": "SuperSecret123"}
    )
    assert login_again.status_code == 200

    logout_response = await client.post("/api/v1/auth/logout", json={"refresh_token": new_refresh_token})
    assert logout_response.status_code == 204

    reused_after_logout = await client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh_token})
    assert reused_after_logout.status_code == 401


# === RLS — password_reset_tokens =================================================================
async def test_password_reset_tokens_relrowsecurity_and_force_are_set() -> None:
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'password_reset_tokens'")
        )
        row = result.one()
        assert row.relrowsecurity is True
        assert row.relforcerowsecurity is True


async def test_password_reset_tokens_policy_exists() -> None:
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("SELECT polname FROM pg_policy WHERE polrelid = 'password_reset_tokens'::regclass")
        )
        names = {row[0] for row in result.all()}
        assert "password_reset_tokens_self_isolation" in names


async def test_row_level_security_hides_other_users_reset_token(client: AsyncClient) -> None:
    from sqlalchemy import select

    from app.core.tenancy import apply_tenant_context
    from app.db.session import AsyncSessionLocal
    from app.modules.auth.models import PasswordResetToken

    data_a = await register_school(client, "resetrlsa")
    data_b = await register_school(client, "resetrlsb")

    forgot_a = await client.post("/api/v1/auth/forgot-password", json={"email": data_a["user"]["email"]})
    assert forgot_a.status_code == 202

    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(data_b["user"]["id"]))
        result = await db.execute(
            select(PasswordResetToken).where(PasswordResetToken.user_id == uuid.UUID(data_a["user"]["id"]))
        )
        assert result.scalar_one_or_none() is None
        await db.rollback()


async def test_forgot_password_reset_password_flow_still_works_under_rls(client: AsyncClient) -> None:
    """Non-régression explicite (Phase 22) : la création du token (INSERT, autorisé sans
    condition) puis sa consultation/consommation (SELECT/UPDATE, bypassés explicitement dans
    auth/service.py::reset_password, unauthenticated) doivent continuer à fonctionner."""
    data = await register_school(client, "resetrlsflow")
    email = data["user"]["email"]

    forgot = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert forgot.status_code == 202
    dev_token = forgot.json()["dev_token"]
    assert dev_token is not None

    reset = await client.post(
        "/api/v1/auth/reset-password", json={"token": dev_token, "new_password": "BrandNewPass123"}
    )
    assert reset.status_code == 204

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "BrandNewPass123"})
    assert login.status_code == 200


async def test_invite_new_user_reset_token_creation_still_works_under_rls(client: AsyncClient) -> None:
    """Non-régression explicite : `users/service.py::create_or_attach_user` insère un
    PasswordResetToken pour un utilisateur AUTRE que l'admin appelant — doit rester possible
    (policy INSERT inconditionnelle) sans élargir le contexte tenant de la transaction (la
    lecture des rôles qui suit doit rester filtrée par RLS, voir test_users.py)."""
    data = await register_school(client, "resetrlsinvite")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}

    response = await client.post(
        "/api/v1/users",
        json={
            "email": unique_email("invitee.resetrlsinvite"),
            "full_name": "Invité Test",
            "school_id": data["school"]["id"],
            "role_code": "TEACHER",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["dev_reset_token"] is not None


# === Rate limiting — reset-password ==============================================================
def _register_payload(prefix: str) -> dict:
    return {
        "organization_name": f"{prefix} Group",
        "organization_slug": f"{prefix}-{uuid.uuid4().hex[:8]}",
        "country_code": "TG",
        "school_name": f"{prefix} School",
        "school_slug": "principale",
        "admin_full_name": f"Admin {prefix}",
        "admin_email": unique_email(f"admin.{prefix}"),
        "admin_password": "SuperSecret123",
    }


async def test_reset_password_below_threshold_allowed(client: AsyncClient) -> None:
    await _clear_pattern("reset_password_attempts:*")
    for _ in range(settings.reset_password_rate_limit_max_attempts):
        response = await client.post(
            "/api/v1/auth/reset-password", json={"token": "not-a-real-token", "new_password": "WhateverPass123"}
        )
        assert response.status_code == 400  # jeton inconnu, mais jamais bloqué avant le seuil


async def test_reset_password_threshold_exceeded_returns_429(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "reset_password_rate_limit_max_attempts", 3)
    await _clear_pattern("reset_password_attempts:*")

    for _ in range(3):
        await client.post(
            "/api/v1/auth/reset-password", json={"token": "not-a-real-token", "new_password": "WhateverPass123"}
        )

    blocked = await client.post(
        "/api/v1/auth/reset-password", json={"token": "not-a-real-token", "new_password": "WhateverPass123"}
    )
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


async def test_reset_password_window_expires(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "reset_password_rate_limit_max_attempts", 1)
    monkeypatch.setattr(settings, "reset_password_rate_limit_window_seconds", 1)
    await _clear_pattern("reset_password_attempts:*")

    await client.post("/api/v1/auth/reset-password", json={"token": "x", "new_password": "WhateverPass123"})
    blocked = await client.post("/api/v1/auth/reset-password", json={"token": "x", "new_password": "WhateverPass123"})
    assert blocked.status_code == 429

    await asyncio.sleep(1.5)

    recovered = await client.post("/api/v1/auth/reset-password", json={"token": "x", "new_password": "WhateverPass123"})
    assert recovered.status_code == 400  # de nouveau autorisé (toujours un jeton inconnu)


async def test_reset_password_redis_unavailable_fails_open(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    unreachable_client = Redis.from_url("redis://localhost:1/0", decode_responses=True, socket_connect_timeout=1)
    monkeypatch.setattr(rate_limit_module, "_redis_client", unreachable_client)

    response = await client.post(
        "/api/v1/auth/reset-password", json={"token": "not-a-real-token", "new_password": "WhateverPass123"}
    )
    assert response.status_code == 400  # jamais 429, jamais 500


async def test_reset_password_legitimate_flow_unaffected_by_rate_limit(client: AsyncClient) -> None:
    await _clear_pattern("reset_password_attempts:*")
    data = await register_school(client, "resetrlok")
    forgot = await client.post("/api/v1/auth/forgot-password", json={"email": data["user"]["email"]})
    dev_token = forgot.json()["dev_token"]

    reset = await client.post("/api/v1/auth/reset-password", json={"token": dev_token, "new_password": "NewPass1234"})
    assert reset.status_code == 204


# === Rate limiting — payments =====================================================================
async def _fee_setup_for_payment(client: AsyncClient, prefix: str) -> dict:
    data = await register_school(client, prefix)
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    suffix = uuid.uuid4().hex[:8]

    year = (
        await client.post(
            "/api/v1/academic-years",
            json={
                "school_id": school_id,
                "name": f"AnPmt-{suffix}",
                "start_date": str(date(2026, 9, 1)),
                "end_date": str(date(2027, 6, 30)),
            },
            headers=headers,
        )
    ).json()
    level = (
        await client.post("/api/v1/education-levels", json={"school_id": school_id, "name": f"NivPmt-{suffix}"}, headers=headers)
    ).json()
    school_class = (
        await client.post(
            "/api/v1/classes",
            json={"academic_year_id": year["id"], "education_level_id": level["id"], "name": "A"},
            headers=headers,
        )
    ).json()
    student = (
        await client.post(
            "/api/v1/students",
            json={
                "school_id": school_id,
                "matricule": f"P{suffix}",
                "first_name": "Test",
                "last_name": "Payment",
                "date_of_birth": str(date(2015, 1, 1)),
                "sex": "M",
            },
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/students/{student['id']}/enrollments",
        json={"class_id": school_class["id"], "enrollment_date": str(date(2026, 9, 1))},
        headers=headers,
    )
    category = (
        await client.post("/api/v1/fee-categories", json={"school_id": school_id, "name": f"Cat-{suffix}"}, headers=headers)
    ).json()
    schedule = (
        await client.post(
            "/api/v1/fee-schedules",
            json={
                "school_id": school_id,
                "fee_category_id": category["id"],
                "academic_year_id": year["id"],
                "name": "Frais",
                "amount": "100000",
                "scope_type": "SCHOOL",
            },
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/fee-schedules/{schedule['id']}/generate", headers=headers)
    summary = await client.get(f"/api/v1/students/{student['id']}/financial-summary", headers=headers)
    student_fee_id = summary.json()["fees"][0]["id"]

    return {"headers": headers, "student_id": student["id"], "student_fee_id": student_fee_id}


def _payment_payload(ctx: dict, amount: str = "1000") -> dict:
    return {
        "student_id": ctx["student_id"],
        "amount": amount,
        "method": "CASH",
        "paid_at": str(date(2026, 10, 1)),
        "idempotency_key": str(uuid.uuid4()),
        "allocations": [{"student_fee_id": ctx["student_fee_id"], "amount": amount}],
    }


async def test_payments_below_threshold_allowed(client: AsyncClient) -> None:
    await _clear_pattern("payments_attempts:*")
    ctx = await _fee_setup_for_payment(client, "paymentsrlok")
    for _ in range(settings.payments_rate_limit_max_attempts):
        response = await client.post("/api/v1/payments", json=_payment_payload(ctx), headers=ctx["headers"])
        assert response.status_code == 201, response.text


async def test_payments_threshold_exceeded_returns_429(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "payments_rate_limit_max_attempts", 2)
    await _clear_pattern("payments_attempts:*")
    ctx = await _fee_setup_for_payment(client, "paymentsrlmax")

    for _ in range(2):
        response = await client.post("/api/v1/payments", json=_payment_payload(ctx), headers=ctx["headers"])
        assert response.status_code == 201

    blocked = await client.post("/api/v1/payments", json=_payment_payload(ctx), headers=ctx["headers"])
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


async def test_payments_cancel_shares_the_same_rate_limit(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un même compteur par utilisateur couvre POST /payments ET /payments/{id}/cancel — deux
    endpoints de mutation financière, même surface d'abus."""
    monkeypatch.setattr(settings, "payments_rate_limit_max_attempts", 2)
    await _clear_pattern("payments_attempts:*")
    ctx = await _fee_setup_for_payment(client, "paymentsrlcancel")

    payment = await client.post("/api/v1/payments", json=_payment_payload(ctx), headers=ctx["headers"])
    assert payment.status_code == 201

    cancel = await client.post(
        f"/api/v1/payments/{payment.json()['id']}/cancel", json={"reason": "Erreur de saisie"}, headers=ctx["headers"]
    )
    assert cancel.status_code == 200

    blocked = await client.post("/api/v1/payments", json=_payment_payload(ctx), headers=ctx["headers"])
    assert blocked.status_code == 429


async def test_payments_redis_unavailable_fails_open(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = await _fee_setup_for_payment(client, "paymentsrldown")
    unreachable_client = Redis.from_url("redis://localhost:1/0", decode_responses=True, socket_connect_timeout=1)
    monkeypatch.setattr(rate_limit_module, "_redis_client", unreachable_client)

    response = await client.post("/api/v1/payments", json=_payment_payload(ctx), headers=ctx["headers"])
    assert response.status_code == 201


# === Rate limiting — announcements ================================================================
async def test_announcements_below_threshold_allowed(client: AsyncClient) -> None:
    await _clear_pattern("announcements_attempts:*")
    data = await register_school(client, "annrlok")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    for _ in range(settings.announcements_rate_limit_max_attempts):
        response = await client.post(
            "/api/v1/announcements",
            json={"school_id": data["school"]["id"], "title": "x", "body": "x", "target_type": "SCHOOL"},
            headers=headers,
        )
        assert response.status_code == 201, response.text


async def test_announcements_threshold_exceeded_returns_429(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "announcements_rate_limit_max_attempts", 2)
    await _clear_pattern("announcements_attempts:*")
    data = await register_school(client, "annrlmax")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}

    for _ in range(2):
        response = await client.post(
            "/api/v1/announcements",
            json={"school_id": data["school"]["id"], "title": "x", "body": "x", "target_type": "SCHOOL"},
            headers=headers,
        )
        assert response.status_code == 201

    blocked = await client.post(
        "/api/v1/announcements",
        json={"school_id": data["school"]["id"], "title": "x", "body": "x", "target_type": "SCHOOL"},
        headers=headers,
    )
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


async def test_announcements_redis_unavailable_fails_open(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    data = await register_school(client, "annrldown")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    unreachable_client = Redis.from_url("redis://localhost:1/0", decode_responses=True, socket_connect_timeout=1)
    monkeypatch.setattr(rate_limit_module, "_redis_client", unreachable_client)

    response = await client.post(
        "/api/v1/announcements",
        json={"school_id": data["school"]["id"], "title": "x", "body": "x", "target_type": "SCHOOL"},
        headers=headers,
    )
    assert response.status_code == 201
