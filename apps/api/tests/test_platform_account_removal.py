"""Retrait des comptes par la plateforme (2026-11-18, migration 0035) — voir platform/accounts.py.

Désactiver / réactiver (réversible) et supprimer (données personnelles effacées, historique gardé),
réservés à `platform.accounts.manage` ; jamais son propre compte ni un compte plateforme ; un
compte partenaire se désactive mais ne se supprime pas.
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.academics.models import TeacherAssignment
from app.modules.audit.models import AuditLog
from app.modules.auth.models import UserSession
from app.modules.notifications.models import Notification, PushDevice
from app.modules.platform.accounts import DELETED_ACCOUNT_NAME, DELETED_EMAIL_DOMAIN
from app.modules.rbac.models import UserRole
from app.modules.students.models import Guardian
from app.modules.users.models import User
from tests.conftest import create_platform_admin
from tests.pr17_helpers import PASSWORD, create_partner, create_platform_owner, enrollment_payload, login
from tests.test_notifications import (
    _create_class,
    _create_student_in_class,
    _create_user_with_role,
    _link_parent,
    _setup_school,
)

ACCOUNTS = "/api/v1/platform/accounts"


async def _count(model, *conditions) -> int:  # type: ignore[no-untyped-def]
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        return int((await db.execute(select(func.count()).select_from(model).where(*conditions))).scalar_one())


async def _user(user_id: str) -> User:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        user = await db.get(User, uuid.UUID(user_id))
        assert user is not None
        return user


async def _assign_teacher(client: AsyncClient, ctx: dict, school_class: dict, teacher_id: str) -> None:
    subject = await client.post(
        "/api/v1/subjects", json={"school_id": ctx["school"]["id"], "name": "Maths"}, headers=ctx["admin_headers"]
    )
    assert subject.status_code == 201, subject.text
    added = await client.post(
        f"/api/v1/classes/{school_class['id']}/subjects",
        json={"subject_id": subject.json()["id"]},
        headers=ctx["admin_headers"],
    )
    assert added.status_code == 201, added.text
    assigned = await client.post(
        f"/api/v1/classes/{school_class['id']}/teachers",
        json={"user_id": teacher_id, "subject_id": subject.json()["id"]},
        headers=ctx["admin_headers"],
    )
    assert assigned.status_code == 201, assigned.text


async def test_only_account_managers_can_remove_accounts(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "rmperm")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "rmperm.t")
    owner = await create_platform_owner(client, "rmpermowner")
    partner = await create_partner(client, owner["headers"], "rmpermpartner")
    target = teacher["user"]["id"]

    assert (await client.post(f"{ACCOUNTS}/{target}/deactivate")).status_code == 401
    for headers in (ctx["admin_headers"], teacher["headers"], partner["headers"]):
        assert (await client.post(f"{ACCOUNTS}/{target}/deactivate", headers=headers)).status_code == 403
        assert (await client.post(f"{ACCOUNTS}/{target}/reactivate", headers=headers)).status_code == 403
        response = await client.post(f"{ACCOUNTS}/{target}/delete", json={"confirm_email": "x"}, headers=headers)
        assert response.status_code == 403
    assert (await _user(target)).is_active is True


async def test_deactivation_blocks_at_once_and_reactivation_restores(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "rmdeact")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "rmdeact.t")
    owner = await create_platform_owner(client, "rmdeactowner")
    target = teacher["user"]["id"]
    email = teacher["user"]["email"]
    login_response = await client.post("/api/v1/auth/login", json={"email": email, "password": "OtherPass123"})
    refresh_token = login_response.json()["refresh_token"]
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        db.add(
            PushDevice(
                id=uuid.uuid4(),
                user_id=uuid.UUID(target),
                endpoint=f"https://fcm.googleapis.com/fcm/send/{uuid.uuid4().hex}",
                p256dh="BGLz",
                auth="abcd",
            )
        )
        await db.commit()

    response = await client.post(f"{ACCOUNTS}/{target}/deactivate", headers=owner["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_active"] is False and body["deleted_at"] is None and body["role_codes"] == ["TEACHER"]

    # Effet immédiat : jeton en cours, renouvellement et connexion refusés.
    assert (await client.get("/api/v1/auth/me", headers=teacher["headers"])).status_code == 401
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})).status_code == 401
    refused = await client.post("/api/v1/auth/login", json={"email": email, "password": "OtherPass123"})
    assert refused.status_code == 401
    assert await _count(UserSession, UserSession.user_id == uuid.UUID(target), UserSession.revoked_at.is_(None)) == 0
    assert await _count(PushDevice, PushDevice.user_id == uuid.UUID(target)) == 0

    # Désactiver à nouveau ne change rien ; réactiver rend l'accès, avec le même mot de passe et les mêmes rôles.
    assert (await client.post(f"{ACCOUNTS}/{target}/deactivate", headers=owner["headers"])).status_code == 200
    response = await client.post(f"{ACCOUNTS}/{target}/reactivate", headers=owner["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is True
    again = await client.post("/api/v1/auth/login", json={"email": email, "password": "OtherPass123"})
    assert again.status_code == 200, again.text
    # Les anciennes sessions ne reviennent pas.
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})).status_code == 401


async def test_refusals_own_platform_unknown_and_partner(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "rmrefowner")
    other_owner = await create_platform_owner(client, "rmrefother")
    legacy_admin = await create_platform_admin(client, "rmreflegacy")
    partner = await create_partner(client, owner["headers"], "rmrefpartner")

    for target in (owner["user_id"], other_owner["user_id"], legacy_admin["user_id"]):
        for action in ("deactivate", "reactivate"):
            response = await client.post(f"{ACCOUNTS}/{target}/{action}", headers=owner["headers"])
            assert response.status_code == 409, response.text
        response = await client.post(
            f"{ACCOUNTS}/{target}/delete", json={"confirm_email": (await _user(target)).email}, headers=owner["headers"]
        )
        assert response.status_code == 409, response.text
    assert "propre compte" in (await client.post(f"{ACCOUNTS}/{owner['user_id']}/deactivate", headers=owner["headers"])).json()["detail"]
    assert (await _user(other_owner["user_id"])).is_active is True

    assert (await client.post(f"{ACCOUNTS}/{uuid.uuid4()}/deactivate", headers=owner["headers"])).status_code == 404

    # Partenaire : désactivable, pas supprimable.
    response = await client.post(
        f"{ACCOUNTS}/{partner['user_id']}/delete", json={"confirm_email": partner["email"]}, headers=owner["headers"]
    )
    assert response.status_code == 409 and "partenaire" in response.json()["detail"]
    assert (await _user(partner["user_id"])).deleted_at is None
    response = await client.post(f"{ACCOUNTS}/{partner['user_id']}/deactivate", headers=owner["headers"])
    assert response.status_code == 200 and response.json()["is_active"] is False
    assert (await client.get("/api/v1/partner/dashboard", headers=partner["headers"])).status_code == 401


async def test_delete_requires_the_exact_email(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "rmconfirm")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "rmconfirm.t")
    owner = await create_platform_owner(client, "rmconfirmowner")
    target = teacher["user"]["id"]
    for wrong in ("", "autre@example.com", teacher["user"]["email"] + "x"):
        response = await client.post(f"{ACCOUNTS}/{target}/delete", json={"confirm_email": wrong}, headers=owner["headers"])
        assert response.status_code in (400, 422), response.text
    user = await _user(target)
    assert user.deleted_at is None and user.email == teacher["user"]["email"] and user.is_active is True

    # Casse et espaces autour ignorés.
    response = await client.post(
        f"{ACCOUNTS}/{target}/delete",
        json={"confirm_email": f"  {teacher['user']['email'].upper()} "},
        headers=owner["headers"],
    )
    assert response.status_code == 200, response.text


async def test_delete_erases_personal_data_and_keeps_history(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "rmerase")
    school_class = await _create_class(client, ctx, "rmerase")
    student = await _create_student_in_class(client, ctx, school_class, "rmerase")
    parent = await _link_parent(client, ctx, student, "rmerase.parent")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "rmerase.t")
    await _assign_teacher(client, ctx, school_class, teacher["user"]["id"])
    published = await client.post(
        "/api/v1/announcements",
        json={"school_id": ctx["school"]["id"], "title": "Réunion", "body": "Samedi", "target_type": "SCHOOL"},
        headers=ctx["admin_headers"],
    )
    assert published.status_code == 201, published.text
    # Une action tracée de l'administrateur (journal d'audit de l'école).
    traced = await client.patch(
        f"/api/v1/users/{teacher['user']['id']}",
        json={"school_id": ctx["school"]["id"], "is_active": True},
        headers=ctx["admin_headers"],
    )
    assert traced.status_code == 200, traced.text
    owner = await create_platform_owner(client, "rmeraseowner")
    admin_id = uuid.UUID(ctx["admin_user_id"])
    teacher_id = uuid.UUID(teacher["user"]["id"])
    parent_id = uuid.UUID(parent["user"]["id"])
    admin_history = await _count(AuditLog, AuditLog.actor_user_id == admin_id)
    assert admin_history > 0
    assert await _count(TeacherAssignment, TeacherAssignment.user_id == teacher_id) == 1

    # Enseignant : affectation, rôle et notifications retirés.
    response = await client.post(
        f"{ACCOUNTS}/{teacher_id}/delete", json={"confirm_email": teacher["user"]["email"]}, headers=owner["headers"]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["full_name"] == DELETED_ACCOUNT_NAME
    assert body["email"] == f"supprime-{teacher_id.hex}@{DELETED_EMAIL_DOMAIN}"
    assert body["is_active"] is False and body["deleted_at"] is not None and body["role_codes"] == []
    user = await _user(str(teacher_id))
    assert user.phone is None and user.deleted_by == uuid.UUID(owner["user_id"])
    assert await _count(TeacherAssignment, TeacherAssignment.user_id == teacher_id) == 0
    assert await _count(UserRole, UserRole.user_id == teacher_id) == 0
    assert await _count(Notification, Notification.recipient_user_id == teacher_id) == 0
    assert await _count(UserSession, UserSession.user_id == teacher_id) == 0
    old_login = await client.post("/api/v1/auth/login", json={"email": teacher["user"]["email"], "password": "OtherPass123"})
    assert old_login.status_code == 401

    # Parent : le tuteur reste dans le dossier de l'élève, sans compte.
    response = await client.post(
        f"{ACCOUNTS}/{parent_id}/delete", json={"confirm_email": parent["user"]["email"]}, headers=owner["headers"]
    )
    assert response.status_code == 200, response.text
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        guardian = await db.get(Guardian, uuid.UUID(parent["guardian"]["id"]))
        assert guardian is not None and guardian.user_id is None and guardian.full_name == "Tuteur Test"

    # Administrateur de l'école : son historique (journal d'audit) reste, rattaché au compte supprimé.
    admin_email = (await _user(str(admin_id))).email
    response = await client.post(
        f"{ACCOUNTS}/{admin_id}/delete", json={"confirm_email": admin_email}, headers=owner["headers"]
    )
    assert response.status_code == 200, response.text
    assert await _count(AuditLog, AuditLog.actor_user_id == admin_id) == admin_history

    # Plus aucune action sur un compte supprimé.
    for action in ("deactivate", "reactivate"):
        response = await client.post(f"{ACCOUNTS}/{teacher_id}/{action}", headers=owner["headers"])
        assert response.status_code == 409 and "déjà été supprimé" in response.json()["detail"]

    # L'email est de nouveau libre : un nouveau compte peut le prendre.
    reused = await client.post(
        "/api/v1/platform/organizations", json=enrollment_payload("rmerasereuse", admin_email), headers=owner["headers"]
    )
    assert reused.status_code == 201, reused.text
    assert (await login(client, admin_email, PASSWORD))["Authorization"].startswith("Bearer ")


async def test_accounts_search_and_deleted_marker(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "rmsearch")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "rmsearch.t")
    owner = await create_platform_owner(client, "rmsearchowner")
    email = teacher["user"]["email"]

    found = await client.get(f"{ACCOUNTS}?q={email.upper()}", headers=owner["headers"])
    assert found.status_code == 200, found.text
    assert [item["id"] for item in found.json()["items"]] == [teacher["user"]["id"]]
    assert found.json()["total"] == 1 and found.json()["items"][0]["deleted_at"] is None
    by_name = await client.get(f"{ACCOUNTS}?q=teacher test&page_size=100", headers=owner["headers"])
    assert teacher["user"]["id"] in {item["id"] for item in by_name.json()["items"]}
    assert (await client.get(f"{ACCOUNTS}?q=aucun-compte-{uuid.uuid4().hex}", headers=owner["headers"])).json()["total"] == 0

    await client.post(f"{ACCOUNTS}/{teacher['user']['id']}/delete", json={"confirm_email": email}, headers=owner["headers"])
    assert (await client.get(f"{ACCOUNTS}?q={email}", headers=owner["headers"])).json()["total"] == 0
    deleted = (await client.get(f"{ACCOUNTS}?q={teacher['user']['id'][:8]}", headers=owner["headers"])).json()["items"]
    assert any(item["id"] == teacher["user"]["id"] and item["deleted_at"] is not None for item in deleted)
