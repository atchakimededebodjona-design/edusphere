"""Règles de connexion et de création des comptes (2026-11-24, décision produit).

- Connexion : une adresse sans compte reçoit « Compte inexistant » ; un mauvais mot de passe,
  « Mot de passe incorrect » ; un compte désactivé ne l'apprend qu'avec le BON mot de passe. Le
  statut reste 401 dans tous les cas (même comptage des échecs, voir test_auth_rate_limit.py).
- Les comptes PARENT et STUDENT sont créés (ou attribués) par l'administrateur de l'école
  uniquement. Un compte plateforme SUPER_ADMIN, malgré son droit `users.manage` global, est refusé
  pour ces deux rôles ; il garde les autres.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.auth.service import INACTIVE_ACCOUNT_DETAIL, UNKNOWN_ACCOUNT_DETAIL, WRONG_PASSWORD_DETAIL
from app.modules.users.models import User
from app.modules.users.service import SCHOOL_ADMIN_ONLY_DETAIL
from tests.conftest import create_platform_admin, register_school, unique_email

PASSWORD = "SuperSecret123"


def _auth(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _login(client: AsyncClient, email: str, password: str):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def _create(client: AsyncClient, headers: dict[str, str], school_id: str, role_code: str, email: str):
    return await client.post(
        "/api/v1/users",
        json={"email": email, "full_name": "Compte Test", "school_id": school_id, "role_code": role_code},
        headers=headers,
    )


async def _user_exists(email: str) -> bool:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        return (await db.execute(select(User.id).where(User.email == email.lower()))).first() is not None


# === Connexion ======================================================================================
async def test_unknown_email_says_the_account_does_not_exist(client: AsyncClient) -> None:
    response = await _login(client, unique_email("ghost.rules"), "whatever123")
    assert response.status_code == 401
    assert response.json() == {"detail": UNKNOWN_ACCOUNT_DETAIL}
    assert UNKNOWN_ACCOUNT_DETAIL.startswith("Compte inexistant")


async def test_wrong_password_on_an_existing_account(client: AsyncClient) -> None:
    data = await register_school(client, "ruleswrong")
    response = await _login(client, data["user"]["email"], "WrongPassword")
    assert response.status_code == 401
    assert response.json() == {"detail": WRONG_PASSWORD_DETAIL}


async def test_existing_account_logs_in_whatever_the_case_of_the_address(client: AsyncClient) -> None:
    data = await register_school(client, "rulescase")
    response = await _login(client, data["user"]["email"].upper(), PASSWORD)
    assert response.status_code == 200, response.text


async def test_inactive_account_is_announced_only_with_the_right_password(client: AsyncClient) -> None:
    data = await register_school(client, "rulesinactive")
    email = data["user"]["email"]
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        user = await db.get(User, uuid.UUID(data["user"]["id"]))
        user.is_active = False
        await db.commit()

    wrong = await _login(client, email, "WrongPassword")
    assert wrong.status_code == 401
    assert wrong.json() == {"detail": WRONG_PASSWORD_DETAIL}

    right = await _login(client, email, PASSWORD)
    assert right.status_code == 401
    assert right.json() == {"detail": INACTIVE_ACCOUNT_DETAIL}


# === Comptes des parents et des élèves : administrateur de l'école uniquement ======================
@pytest.mark.parametrize("role_code", ["PARENT", "STUDENT"])
async def test_platform_super_admin_cannot_create_parent_or_student_accounts(client: AsyncClient, role_code: str) -> None:
    school = await register_school(client, f"rulesplat{role_code[:3].lower()}")
    platform = await create_platform_admin(client, f"rulesplat{role_code[:3].lower()}")
    email = unique_email(f"rules.plat.{role_code.lower()}")

    response = await _create(client, _auth(platform["tokens"]), school["school"]["id"], role_code, email)
    assert response.status_code == 403
    assert response.json() == {"detail": SCHOOL_ADMIN_ONLY_DETAIL}
    assert await _user_exists(email) is False


async def test_platform_super_admin_keeps_creating_other_school_accounts(client: AsyncClient) -> None:
    school = await register_school(client, "rulesplatteach")
    platform = await create_platform_admin(client, "rulesplatteach")
    response = await _create(
        client, _auth(platform["tokens"]), school["school"]["id"], "TEACHER", unique_email("rules.plat.teacher")
    )
    assert response.status_code == 201, response.text


@pytest.mark.parametrize("role_code", ["PARENT", "STUDENT"])
async def test_organization_school_admin_creates_parent_and_student_accounts(client: AsyncClient, role_code: str) -> None:
    school = await register_school(client, f"rulesorg{role_code[:3].lower()}")
    email = unique_email(f"rules.org.{role_code.lower()}")
    response = await _create(client, _auth(school["tokens"]), school["school"]["id"], role_code, email)
    assert response.status_code == 201, response.text
    assert [r["role_code"] for r in response.json()["roles"]] == [role_code]


async def test_school_scoped_school_admin_creates_parent_accounts(client: AsyncClient) -> None:
    """Un administrateur rattaché à UNE école (et non à toute l'organisation) crée aussi les
    comptes des parents de son école."""
    school = await register_school(client, "rulesscoped")
    school_id = school["school"]["id"]
    admin_email = unique_email("rules.scoped.admin")
    created = await _create(client, _auth(school["tokens"]), school_id, "SCHOOL_ADMIN", admin_email)
    assert created.status_code == 201, created.text
    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": created.json()["dev_reset_token"], "new_password": PASSWORD},
    )
    assert reset.status_code == 204, reset.text
    scoped_login = await _login(client, admin_email, PASSWORD)
    assert scoped_login.status_code == 200, scoped_login.text

    response = await _create(client, _auth(scoped_login.json()), school_id, "PARENT", unique_email("rules.scoped.parent"))
    assert response.status_code == 201, response.text


async def test_role_change_to_parent_follows_the_same_rule(client: AsyncClient) -> None:
    school = await register_school(client, "rulespatch")
    school_id = school["school"]["id"]
    admin_headers = _auth(school["tokens"])
    teacher = await _create(client, admin_headers, school_id, "TEACHER", unique_email("rules.patch.teacher"))
    assert teacher.status_code == 201, teacher.text
    teacher_id = teacher.json()["user"]["id"]

    platform = await create_platform_admin(client, "rulespatch")
    refused = await client.patch(
        f"/api/v1/users/{teacher_id}",
        json={"school_id": school_id, "role_code": "PARENT"},
        headers=_auth(platform["tokens"]),
    )
    assert refused.status_code == 403
    assert refused.json() == {"detail": SCHOOL_ADMIN_ONLY_DETAIL}

    accepted = await client.patch(
        f"/api/v1/users/{teacher_id}", json={"school_id": school_id, "role_code": "PARENT"}, headers=admin_headers
    )
    assert accepted.status_code == 200, accepted.text
    assert [r["role_code"] for r in accepted.json()["roles"]] == ["PARENT"]
