"""GET /api/v1/teacher/announcements — annonces réellement destinées à l'enseignant : école
entière, ou une classe où il a une TeacherAssignment ET un rôle TEACHER actif rattaché à cette
même organisation/école. Jamais une autre école, jamais une classe non affectée, jamais
`recipient_count` (réservé à l'historique SCHOOL_ADMIN/DIRECTOR), jamais un rôle révoqué ou un
compte inactif/platform admin — la seule TeacherAssignment ne suffit plus
(notifications/service.py::resolve_class_teacher_user_ids)."""

import uuid

from httpx import AsyncClient
from sqlalchemy import delete, func, select

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.academics.models import TeacherAssignment
from app.modules.notifications.models import Notification
from app.modules.rbac.models import Role, UserRole
from app.modules.users.models import User
from tests.test_teacher_portal import _portal_setup, _teacher_in_school


async def _post_announcement(client: AsyncClient, setup: dict, **payload) -> dict:
    response = await client.post(
        "/api/v1/announcements",
        json={"school_id": setup["school_id"], **payload},
        headers=setup["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _notification_count_for(user_id: str, title: str) -> int:
    """Vérifie directement en base : indépendant de l'accès au portail (qui refuse déjà un rôle
    révoqué ou un compte inactif — on veut ici vérifier l'ABSENCE de notification, pas un 403)."""
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        result = await db.execute(
            select(func.count()).select_from(Notification).where(
                Notification.recipient_user_id == uuid.UUID(user_id), Notification.title == title
            )
        )
        return result.scalar_one()


async def test_teacher_sees_school_wide_announcement(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "annteacherschool")
    await _post_announcement(client, setup, title="Rentrée", body="Reprise lundi", target_type="SCHOOL")

    response = await client.get("/api/v1/teacher/announcements", headers=setup["teacher_headers"])
    assert response.status_code == 200, response.text
    titles = [a["title"] for a in response.json()]
    assert "Rentrée" in titles
    assert "recipient_count" not in response.json()[0]


async def test_teacher_sees_announcement_targeted_at_assigned_class(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "annteacherclassok")
    await _post_announcement(
        client, setup, title="Sortie CM2-A", body="Sortie scolaire", target_type="CLASS", class_ids=[setup["class_a"]["id"]]
    )

    response = await client.get("/api/v1/teacher/announcements", headers=setup["teacher_headers"])
    assert response.status_code == 200
    assert "Sortie CM2-A" in [a["title"] for a in response.json()]


async def test_teacher_does_not_see_announcement_of_unassigned_class(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "annteacherclassno")
    await _post_announcement(
        client, setup, title="Reunion CM2-B", body="Reunion parents", target_type="CLASS", class_ids=[setup["class_b"]["id"]]
    )

    response = await client.get("/api/v1/teacher/announcements", headers=setup["teacher_headers"])
    assert response.status_code == 200
    assert "Reunion CM2-B" not in [a["title"] for a in response.json()]


async def test_teacher_does_not_see_other_school_announcement(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "annteacherxschool")
    other = await _portal_setup(client, "annteacherxschoolother")
    await _post_announcement(client, other, title="Annonce autre ecole", body="x", target_type="SCHOOL")

    response = await client.get("/api/v1/teacher/announcements", headers=setup["teacher_headers"])
    assert response.status_code == 200
    assert "Annonce autre ecole" not in [a["title"] for a in response.json()]


async def test_unassigned_teacher_does_not_receive_class_announcement(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "annteacherunassigned")
    other_teacher_id, _ = await _teacher_in_school(client, setup, "annteacherunassignedacct")

    await _post_announcement(
        client, setup, title="Annonce non affecte", body="x", target_type="CLASS", class_ids=[setup["class_a"]["id"]]
    )
    assert await _notification_count_for(setup["teacher_id"], "Annonce non affecte") == 1
    assert await _notification_count_for(other_teacher_id, "Annonce non affecte") == 0


async def test_teacher_role_revoked_stops_receiving_class_announcement(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "annteacherrevoked")
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        await db.execute(
            delete(UserRole).where(
                UserRole.user_id == uuid.UUID(setup["teacher_id"]),
                UserRole.role_id.in_(select(Role.id).where(Role.code == "TEACHER")),
            )
        )
        await db.commit()

    # La TeacherAssignment survit au retrait du rôle (aucune suppression en cascade) : elle ne
    # doit plus suffire à recevoir l'annonce.
    await _post_announcement(
        client, setup, title="Apres revocation", body="x", target_type="CLASS", class_ids=[setup["class_a"]["id"]]
    )
    assert await _notification_count_for(setup["teacher_id"], "Apres revocation") == 0


async def test_inactive_teacher_stops_receiving_class_announcement(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "annteacherinactive")
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        user = await db.get(User, uuid.UUID(setup["teacher_id"]))
        user.is_active = False
        await db.commit()

    await _post_announcement(
        client, setup, title="Apres desactivation", body="x", target_type="CLASS", class_ids=[setup["class_a"]["id"]]
    )
    assert await _notification_count_for(setup["teacher_id"], "Apres desactivation") == 0


async def test_teacher_of_another_school_does_not_receive_despite_stale_assignment(client: AsyncClient) -> None:
    """Une TeacherAssignment peut survivre à un transfert d'école (aucune suppression en cascade) :
    un enseignant dont le rôle TEACHER actif est désormais dans une AUTRE école ne doit jamais
    devenir destinataire via cette affectation périmée — la seule TeacherAssignment ne suffit pas."""
    setup = await _portal_setup(client, "annteacherxschool2")
    other_school = await client.post(
        "/api/v1/schools",
        json={"organization_id": setup["organization_id"], "name": "Autre ecole annonce", "slug": "autre-annonce"},
        headers=setup["headers"],
    )
    assert other_school.status_code == 201, other_school.text
    other_teacher_id, _ = await _teacher_in_school(
        client,
        {"organization_id": setup["organization_id"], "school_id": other_school.json()["id"]},
        "annteacherxschool2acct",
    )
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        db.add(
            TeacherAssignment(
                id=uuid.uuid4(),
                school_id=uuid.UUID(setup["school_id"]),
                organization_id=uuid.UUID(setup["organization_id"]),
                user_id=uuid.UUID(other_teacher_id),
                class_subject_id=uuid.UUID(setup["cs_maths"]["id"]),
            )
        )
        await db.commit()

    await _post_announcement(
        client, setup, title="Annonce ecole X", body="x", target_type="CLASS", class_ids=[setup["class_a"]["id"]]
    )
    assert await _notification_count_for(other_teacher_id, "Annonce ecole X") == 0
    assert await _notification_count_for(setup["teacher_id"], "Annonce ecole X") == 1


async def test_teacher_cannot_publish_announcement(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "annteacherrbac")
    response = await client.post(
        "/api/v1/announcements",
        json={"school_id": setup["school_id"], "title": "x", "body": "x", "target_type": "SCHOOL"},
        headers=setup["teacher_headers"],
    )
    assert response.status_code == 403
