"""Phase 20 — Security & Pre-Pilot Hardening.

Couvre les 4 sujets du périmètre : rate limiting (register/refresh/verify-by-code), RLS
`organizations`, et traçabilité des ajustements `StudentFee`. Même Redis réel du docker-compose
que test_auth_rate_limit.py/test_forgot_password_rate_limit.py — pas de mock.
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
from tests.conftest import register_school, unique_email, unique_slug


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _clear_pattern(pattern: str) -> None:
    client = _get_client()
    async for key in client.scan_iter(match=pattern):
        await client.delete(key)


def _register_payload(prefix: str) -> dict:
    return {
        "organization_name": f"{prefix} Group",
        "organization_slug": unique_slug(prefix),
        "country_code": "TG",
        "school_name": f"{prefix} School",
        "school_slug": "principale",
        "admin_full_name": f"Admin {prefix}",
        "admin_email": unique_email(f"admin.{prefix}"),
        "admin_password": "SuperSecret123",
    }


# === A. Rate limiting — /auth/register =========================================================
async def test_register_below_threshold_allowed(client: AsyncClient) -> None:
    await _clear_pattern("register_attempts:*")
    for _ in range(settings.register_rate_limit_max_attempts):
        response = await client.post("/api/v1/auth/register", json=_register_payload("regrl"))
        assert response.status_code == 201, response.text


async def test_register_threshold_exceeded_returns_429(client: AsyncClient) -> None:
    await _clear_pattern("register_attempts:*")
    for _ in range(settings.register_rate_limit_max_attempts):
        await client.post("/api/v1/auth/register", json=_register_payload("regrlmax"))

    blocked = await client.post("/api/v1/auth/register", json=_register_payload("regrlmax"))
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


async def test_register_rate_limit_window_expires(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "register_rate_limit_max_attempts", 2)
    monkeypatch.setattr(settings, "register_rate_limit_window_seconds", 1)
    await _clear_pattern("register_attempts:*")

    for _ in range(2):
        await client.post("/api/v1/auth/register", json=_register_payload("regrlwin"))
    blocked = await client.post("/api/v1/auth/register", json=_register_payload("regrlwin"))
    assert blocked.status_code == 429

    await asyncio.sleep(1.5)

    recovered = await client.post("/api/v1/auth/register", json=_register_payload("regrlwin"))
    assert recovered.status_code == 201


async def test_register_redis_unavailable_fails_open(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    unreachable_client = Redis.from_url("redis://localhost:1/0", decode_responses=True, socket_connect_timeout=1)
    monkeypatch.setattr(rate_limit_module, "_redis_client", unreachable_client)

    response = await client.post("/api/v1/auth/register", json=_register_payload("regrldown"))
    assert response.status_code == 201


async def test_register_invalid_payload_returns_422_not_blocked_by_rate_limit(client: AsyncClient) -> None:
    """Une requête mal formée (validation Pydantic) échoue avant même d'atteindre la logique
    métier — ne doit ni planter ni être confondue avec un 429."""
    await _clear_pattern("register_attempts:*")
    response = await client.post("/api/v1/auth/register", json={"organization_name": "Incomplet"})
    assert response.status_code == 422


# === B. Rate limiting — /auth/refresh ===========================================================
async def test_refresh_below_threshold_allowed(client: AsyncClient) -> None:
    data = await register_school(client, "refreshrlok")
    refresh_token = data["tokens"]["refresh_token"]
    await _clear_pattern("refresh_attempts:*")

    for _ in range(settings.refresh_rate_limit_max_attempts - 1):
        response = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert response.status_code == 200, response.text
        refresh_token = response.json()["refresh_token"]  # rotation : réutiliser le nouveau jeton


async def test_refresh_threshold_exceeded_returns_429(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "refresh_rate_limit_max_attempts", 2)
    data = await register_school(client, "refreshrlmax")
    refresh_token = data["tokens"]["refresh_token"]
    await _clear_pattern("refresh_attempts:*")

    for _ in range(2):
        response = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert response.status_code == 200
        refresh_token = response.json()["refresh_token"]

    blocked = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


async def test_refresh_rate_limit_window_expires(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "refresh_rate_limit_max_attempts", 1)
    monkeypatch.setattr(settings, "refresh_rate_limit_window_seconds", 1)
    data = await register_school(client, "refreshrlwin")
    refresh_token = data["tokens"]["refresh_token"]
    await _clear_pattern("refresh_attempts:*")

    first = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert first.status_code == 200
    refresh_token = first.json()["refresh_token"]

    blocked = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert blocked.status_code == 429

    await asyncio.sleep(1.5)

    recovered = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert recovered.status_code == 200


async def test_refresh_rate_limit_isolated_between_users(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "refresh_rate_limit_max_attempts", 1)
    data_a = await register_school(client, "refreshrlisoa")
    data_b = await register_school(client, "refreshrlisob")
    await _clear_pattern("refresh_attempts:*")

    # Premier appel : autorisé (compteur passe à 1), le jeton présenté tourne (rotation déjà en
    # place) — le second appel doit utiliser le NOUVEAU jeton, l'ancien étant déjà révoqué.
    first_a = await client.post("/api/v1/auth/refresh", json={"refresh_token": data_a["tokens"]["refresh_token"]})
    assert first_a.status_code == 200
    blocked_a = await client.post("/api/v1/auth/refresh", json={"refresh_token": first_a.json()["refresh_token"]})
    assert blocked_a.status_code == 429

    # L'utilisateur B, jamais rafraîchi, n'est pas affecté par le blocage de A.
    ok_b = await client.post("/api/v1/auth/refresh", json={"refresh_token": data_b["tokens"]["refresh_token"]})
    assert ok_b.status_code == 200


async def test_refresh_invalid_token_returns_401_never_consumes_rate_limit(client: AsyncClient) -> None:
    """Un jeton invalide échoue à la résolution de session, avant tout comptage de rate limit —
    confirmé indirectement : de nombreux essais invalides ne doivent jamais bloquer un vrai
    utilisateur (aucune clé user_id à incrémenter puisque l'utilisateur n'est jamais résolu)."""
    for _ in range(50):
        response = await client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
        assert response.status_code == 401

    data = await register_school(client, "refreshrlinvalid")
    ok = await client.post("/api/v1/auth/refresh", json={"refresh_token": data["tokens"]["refresh_token"]})
    assert ok.status_code == 200


async def test_refresh_redis_unavailable_fails_open(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Inscription AVANT de casser Redis : seul le comportement de `refresh` face à un Redis
    # injoignable est sous test ici, pas celui de `register_school()`.
    data = await register_school(client, "refreshrldown")

    unreachable_client = Redis.from_url("redis://localhost:1/0", decode_responses=True, socket_connect_timeout=1)
    monkeypatch.setattr(rate_limit_module, "_redis_client", unreachable_client)

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": data["tokens"]["refresh_token"]})
    assert response.status_code == 200


# === C. Rate limiting — GET /report-cards/verify/{code} ========================================
async def test_report_card_verify_below_threshold_allowed(client: AsyncClient) -> None:
    await _clear_pattern("report_card_verify_attempts:*")
    for _ in range(settings.report_card_verify_rate_limit_max_attempts):
        response = await client.get("/api/v1/report-cards/verify/does-not-exist")
        assert response.status_code == 404  # code inconnu, mais requête non bloquée


async def test_report_card_verify_threshold_exceeded_returns_429(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "report_card_verify_rate_limit_max_attempts", 3)
    await _clear_pattern("report_card_verify_attempts:*")

    for _ in range(3):
        await client.get("/api/v1/report-cards/verify/scan-attempt")

    blocked = await client.get("/api/v1/report-cards/verify/scan-attempt")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


async def test_report_card_verify_window_expires(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "report_card_verify_rate_limit_max_attempts", 1)
    monkeypatch.setattr(settings, "report_card_verify_rate_limit_window_seconds", 1)
    await _clear_pattern("report_card_verify_attempts:*")

    await client.get("/api/v1/report-cards/verify/x")
    blocked = await client.get("/api/v1/report-cards/verify/x")
    assert blocked.status_code == 429

    await asyncio.sleep(1.5)

    recovered = await client.get("/api/v1/report-cards/verify/x")
    assert recovered.status_code == 404  # de nouveau autorisé (code toujours inconnu, mais pas 429)


async def test_report_card_verify_redis_unavailable_fails_open(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    unreachable_client = Redis.from_url("redis://localhost:1/0", decode_responses=True, socket_connect_timeout=1)
    monkeypatch.setattr(rate_limit_module, "_redis_client", unreachable_client)

    response = await client.get("/api/v1/report-cards/verify/whatever")
    assert response.status_code == 404  # jamais 429, jamais 500


# === Security headers ===========================================================================
async def test_security_headers_present_on_every_response(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "permissions-policy" in response.headers


async def test_security_headers_present_on_error_responses_too(client: AsyncClient) -> None:
    response = await client.get("/api/v1/organizations/00000000-0000-0000-0000-000000000000")
    assert response.status_code in (401, 403, 404)
    assert response.headers["x-content-type-options"] == "nosniff"


# === D. RLS — organizations =====================================================================
async def test_row_level_security_hides_organization_row_even_bypassing_app_check(client: AsyncClient) -> None:
    """Même preuve que test_tenant_isolation.py, appliquée à `organizations` (Phase 20)."""
    from sqlalchemy import select

    from app.core.tenancy import apply_tenant_context
    from app.db.session import AsyncSessionLocal
    from app.modules.organizations.models import Organization

    school_a = await register_school(client, "orgrlsa")
    school_b = await register_school(client, "orgrlsb")

    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(school_a["user"]["id"]))
        result = await db.execute(select(Organization).where(Organization.id == uuid.UUID(school_b["organization"]["id"])))
        assert result.scalar_one_or_none() is None

        own = await db.execute(select(Organization).where(Organization.id == uuid.UUID(school_a["organization"]["id"])))
        assert own.scalar_one_or_none() is not None
        await db.rollback()


async def test_organizations_relrowsecurity_and_force_are_set() -> None:
    """Vérifie directement le catalogue PostgreSQL (`pg_class`), pas seulement le comportement
    applicatif — `relrowsecurity`/`relforcerowsecurity` doivent être vrais pour `organizations`."""
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'organizations'")
        )
        row = result.one()
        assert row.relrowsecurity is True
        assert row.relforcerowsecurity is True


async def test_organizations_policy_exists() -> None:
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("SELECT polname FROM pg_policy WHERE polrelid = 'organizations'::regclass")
        )
        names = {row[0] for row in result.all()}
        assert "organizations_tenant_isolation" in names


async def test_school_admin_can_still_read_and_update_own_organization(client: AsyncClient) -> None:
    """Non-régression explicite (§14) : la RLS ne doit jamais empêcher un admin légitime de lire/
    modifier SA PROPRE organisation."""
    data = await register_school(client, "orgownok")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    organization_id = data["organization"]["id"]

    get_response = await client.get(f"/api/v1/organizations/{organization_id}", headers=headers)
    assert get_response.status_code == 200

    patch_response = await client.patch(
        f"/api/v1/organizations/{organization_id}", json={"name": "Nouveau nom"}, headers=headers
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Nouveau nom"


async def test_registration_still_creates_organization_under_rls(client: AsyncClient) -> None:
    """Non-régression (§14) : la création (register, contexte platform-wide explicite) continue
    de fonctionner avec RLS active sur `organizations`."""
    data = await register_school(client, "orgcreateok")
    assert data["organization"]["id"]
    assert data["school"]["organization_id"] == data["organization"]["id"]


# === E. Traçabilité financière — StudentFee.updated_by =========================================
async def _fee_setup(client: AsyncClient, prefix: str) -> dict:
    data = await register_school(client, prefix)
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    suffix = uuid.uuid4().hex[:8]

    year = (
        await client.post(
            "/api/v1/academic-years",
            json={
                "school_id": school_id,
                "name": f"2026-2027-{suffix}",
                "start_date": str(date(2026, 9, 1)),
                "end_date": str(date(2027, 6, 30)),
            },
            headers=headers,
        )
    ).json()
    level = (
        await client.post("/api/v1/education-levels", json={"school_id": school_id, "name": f"CE1-{suffix}"}, headers=headers)
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
                "matricule": f"T{suffix}",
                "first_name": "Test",
                "last_name": "Fee",
                "date_of_birth": str(date(2015, 1, 1)),
                "sex": "F",
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
        await client.post("/api/v1/fee-categories", json={"school_id": school_id, "name": "Scolarité"}, headers=headers)
    ).json()
    schedule = (
        await client.post(
            "/api/v1/fee-schedules",
            json={
                "school_id": school_id,
                "fee_category_id": category["id"],
                "academic_year_id": year["id"],
                "name": "Frais annuels",
                "amount": "50000",
                "scope_type": "SCHOOL",
            },
            headers=headers,
        )
    ).json()
    await client.post(f"/api/v1/fee-schedules/{schedule['id']}/generate", headers=headers)
    summary = await client.get(f"/api/v1/students/{student['id']}/financial-summary", headers=headers)
    student_fee = summary.json()["fees"][0]

    return {"headers": headers, "admin_id": data["user"]["id"], "student_fee": student_fee}


async def test_amount_adjustment_without_note_rejected(client: AsyncClient) -> None:
    ctx = await _fee_setup(client, "feetraceno")
    response = await client.patch(
        f"/api/v1/student-fees/{ctx['student_fee']['id']}", json={"amount_due": "45000"}, headers=ctx["headers"]
    )
    assert response.status_code == 422


async def test_amount_adjustment_with_blank_note_rejected(client: AsyncClient) -> None:
    ctx = await _fee_setup(client, "feetraceblank")
    response = await client.patch(
        f"/api/v1/student-fees/{ctx['student_fee']['id']}",
        json={"amount_due": "45000", "note": "   "},
        headers=ctx["headers"],
    )
    assert response.status_code == 422


async def test_amount_adjustment_with_note_succeeds_and_records_updated_by(client: AsyncClient) -> None:
    ctx = await _fee_setup(client, "feetraceok")
    response = await client.patch(
        f"/api/v1/student-fees/{ctx['student_fee']['id']}",
        json={"amount_due": "45000", "note": "Bourse partielle accordée par le directeur"},
        headers=ctx["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["amount_due"] == "45000.00"
    assert body["updated_by"] == ctx["admin_id"]


async def test_note_only_change_also_records_updated_by(client: AsyncClient) -> None:
    """Toute modification (même sans changer le montant) doit être attribuée."""
    ctx = await _fee_setup(client, "feetracenoteonly")
    response = await client.patch(
        f"/api/v1/student-fees/{ctx['student_fee']['id']}",
        json={"note": "Commentaire administratif, aucun changement de montant"},
        headers=ctx["headers"],
    )
    assert response.status_code == 200
    assert response.json()["updated_by"] == ctx["admin_id"]


async def test_no_adjustment_leaves_updated_by_null(client: AsyncClient) -> None:
    """Une StudentFee générée automatiquement (jamais ajustée manuellement) n'a pas d'auteur —
    ce n'est pas un défaut, c'est la sémantique attendue (voir fees/models.py::StudentFee)."""
    ctx = await _fee_setup(client, "feetracenull")
    assert ctx["student_fee"]["updated_by"] is None


