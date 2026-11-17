"""Annonces — choix des destinataires (2026-11-17), en plus de la portée école entière / classes :
tout le monde (comme avant), parents, enseignants, personnel de l'école (école entière seulement)."""

from httpx import AsyncClient

from tests.test_notifications import (
    _create_class,
    _create_student_in_class,
    _create_user_with_role,
    _link_parent,
    _list_notifications,
    _setup_school,
)
from tests.test_teacher_portal import _portal_setup


async def _announce(client: AsyncClient, school_id: str, headers: dict, **payload) -> dict:
    response = await client.post(
        "/api/v1/announcements",
        json={"school_id": school_id, "title": payload.pop("title", "Info"), "body": "Contenu", **payload},
        headers=headers,
    )
    return {"status": response.status_code, "body": response.json()}


async def _titles(client: AsyncClient, headers: dict) -> list[str]:
    return [item["title"] for item in await _list_notifications(client, headers)]


async def test_whole_school_audiences_reach_only_the_chosen_people(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "audschool")
    other = await _setup_school(client, "audother")
    school_id = ctx["school"]["id"]
    school_class = await _create_class(client, ctx, "aud1")
    student = await _create_student_in_class(client, ctx, school_class, "aud1")
    parent = await _link_parent(client, ctx, student, "parent.aud")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], school_id, "TEACHER", "teacher.aud")
    accountant = await _create_user_with_role(client, ctx["admin_headers"], school_id, "ACCOUNTANT", "acc.aud")
    other_class = await _create_class(client, other, "audo")
    other_student = await _create_student_in_class(client, other, other_class, "audo")
    other_parent = await _link_parent(client, other, other_student, "parent.audother")
    other_teacher = await _create_user_with_role(client, other["admin_headers"], other["school"]["id"], "TEACHER", "teacher.audother")

    parents = await _announce(client, school_id, ctx["admin_headers"], title="Aux parents", target_type="SCHOOL", audience="PARENTS")
    assert parents == {"status": 201, "body": {"recipient_count": 1}}
    teachers = await _announce(client, school_id, ctx["admin_headers"], title="Aux enseignants", target_type="SCHOOL", audience="TEACHERS")
    assert teachers == {"status": 201, "body": {"recipient_count": 1}}
    staff = await _announce(client, school_id, ctx["admin_headers"], title="Au personnel", target_type="SCHOOL", audience="STAFF")
    assert staff == {"status": 201, "body": {"recipient_count": 2}}  # administrateur + comptable
    everyone = await _announce(client, school_id, ctx["admin_headers"], title="A tous", target_type="SCHOOL")
    assert everyone == {"status": 201, "body": {"recipient_count": 4}}  # sans `audience` : comme avant

    assert sorted(await _titles(client, parent["headers"])) == ["A tous", "Aux parents"]
    assert sorted(await _titles(client, teacher["headers"])) == ["A tous", "Aux enseignants"]
    assert sorted(await _titles(client, accountant["headers"])) == ["A tous", "Au personnel"]
    assert sorted(await _titles(client, ctx["admin_headers"])) == ["A tous", "Au personnel"]
    # Jamais l'autre école.
    assert await _titles(client, other_parent["headers"]) == []
    assert await _titles(client, other_teacher["headers"]) == []


async def test_class_audiences_split_parents_and_teachers(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "audclass")
    ctx = {"school": {"id": setup["school_id"]}, "admin_headers": setup["headers"]}
    parent_a = await _link_parent(client, ctx, setup["student_a"], "parent.audclassa")
    parent_b = await _link_parent(client, ctx, setup["student_b"], "parent.audclassb")
    class_a = [setup["class_a"]["id"]]

    parents = await _announce(
        client, setup["school_id"], setup["headers"], title="Parents CM2-A", target_type="CLASS", class_ids=class_a, audience="PARENTS"
    )
    assert parents == {"status": 201, "body": {"recipient_count": 1}}
    teachers = await _announce(
        client, setup["school_id"], setup["headers"], title="Enseignants CM2-A", target_type="CLASS", class_ids=class_a, audience="TEACHERS"
    )
    assert teachers == {"status": 201, "body": {"recipient_count": 1}}
    everyone = await _announce(client, setup["school_id"], setup["headers"], title="Tous CM2-A", target_type="CLASS", class_ids=class_a)
    assert everyone == {"status": 201, "body": {"recipient_count": 2}}

    assert sorted(await _titles(client, parent_a["headers"])) == ["Parents CM2-A", "Tous CM2-A"]
    assert sorted(await _titles(client, setup["teacher_headers"])) == ["Enseignants CM2-A", "Tous CM2-A"]
    assert await _titles(client, parent_b["headers"]) == []  # autre classe


async def test_staff_audience_is_refused_for_classes(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "audstaffclass")
    school_class = await _create_class(client, ctx, "asc")
    refused = await _announce(
        client, ctx["school"]["id"], ctx["admin_headers"], target_type="CLASS", class_ids=[school_class["id"]], audience="STAFF"
    )
    assert refused["status"] == 400
    assert refused["body"]["detail"] == "The STAFF audience is only available for the whole school"
    unknown = await _announce(client, ctx["school"]["id"], ctx["admin_headers"], target_type="SCHOOL", audience="STUDENTS")
    assert unknown["status"] == 422
