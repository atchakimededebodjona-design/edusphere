"""GET /api/v1/teacher/announcements — annonces réellement destinées à l'enseignant : école
entière, ou une classe où il a une TeacherAssignment. Jamais une autre école, jamais une classe non
affectée, jamais `recipient_count` (réservé à l'historique SCHOOL_ADMIN/DIRECTOR)."""

from httpx import AsyncClient

from tests.test_teacher_portal import _portal_setup


async def _post_announcement(client: AsyncClient, setup: dict, **payload) -> dict:
    response = await client.post(
        "/api/v1/announcements",
        json={"school_id": setup["school_id"], **payload},
        headers=setup["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


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


async def test_teacher_cannot_publish_announcement(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "annteacherrbac")
    response = await client.post(
        "/api/v1/announcements",
        json={"school_id": setup["school_id"], "title": "x", "body": "x", "target_type": "SCHOOL"},
        headers=setup["teacher_headers"],
    )
    assert response.status_code == 403
