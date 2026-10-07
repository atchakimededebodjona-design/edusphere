"""PATCH /api/v1/students/bulk — modification en masse du statut uniquement.

Réutilise exactement les règles de `update_student` (historique StudentStatusHistory créé
seulement si le statut change réellement) et `students.manage`. Transaction atomique : soit tout
le lot est appliqué, soit rien ne l'est.
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.students.models import Student, StudentStatusHistory
from tests.conftest import assign_role, register_school
from tests.test_students import _create_student, _login


async def _setup_students(client: AsyncClient, prefix: str, count: int = 3) -> dict:
    data = await register_school(client, prefix)
    token = await _login(client, data["user"]["email"])
    headers = {"Authorization": f"Bearer {token}"}
    school_id = data["school"]["id"]
    students = [
        await _create_student(client, headers, school_id, matricule=f"{prefix}-{i:03d}", first_name=f"Eleve{i}")
        for i in range(count)
    ]
    return {"data": data, "headers": headers, "school_id": school_id, "students": students}


async def _history_count(student_id: str) -> int:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        result = await db.execute(
            select(func.count()).select_from(StudentStatusHistory).where(
                StudentStatusHistory.student_id == uuid.UUID(student_id)
            )
        )
        return result.scalar_one()


async def _get_student_row(student_id: str) -> Student:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        student = await db.get(Student, uuid.UUID(student_id))
        assert student is not None
        return student


async def test_bulk_update_single_student(client: AsyncClient) -> None:
    setup = await _setup_students(client, "bulkone", count=1)
    student = setup["students"][0]

    response = await client.patch(
        "/api/v1/students/bulk",
        json={"student_ids": [student["id"]], "status": "INACTIVE", "status_change_reason": "Pause"},
        headers=setup["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["updated_count"] == 1
    assert body["unchanged_count"] == 0
    assert body["students"][0]["status"] == "INACTIVE"
    assert await _history_count(student["id"]) == 1


async def test_bulk_update_several_students(client: AsyncClient) -> None:
    setup = await _setup_students(client, "bulkmany", count=3)
    ids = [s["id"] for s in setup["students"]]

    response = await client.patch(
        "/api/v1/students/bulk",
        json={"student_ids": ids, "status": "ACTIVE", "status_change_reason": "Inscription nouvelle annee"},
        headers=setup["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["updated_count"] == 0  # les élèves créés sont déjà ACTIVE par défaut
    assert body["unchanged_count"] == 3
    assert {s["status"] for s in body["students"]} == {"ACTIVE"}


async def test_bulk_update_changes_status_and_creates_history(client: AsyncClient) -> None:
    setup = await _setup_students(client, "bulkhist", count=2)
    ids = [s["id"] for s in setup["students"]]

    response = await client.patch(
        "/api/v1/students/bulk",
        json={"student_ids": ids, "status": "WITHDRAWN", "status_change_reason": "Changement d'ecole"},
        headers=setup["headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["updated_count"] == 2
    for student_id in ids:
        assert await _history_count(student_id) == 1


async def test_bulk_update_no_history_when_status_unchanged(client: AsyncClient) -> None:
    setup = await _setup_students(client, "bulknohist", count=2)
    ids = [s["id"] for s in setup["students"]]

    response = await client.patch(
        "/api/v1/students/bulk",
        json={"student_ids": ids, "status": "ACTIVE"},
        headers=setup["headers"],
    )
    assert response.status_code == 200
    assert response.json()["unchanged_count"] == 2
    for student_id in ids:
        assert await _history_count(student_id) == 0


async def test_bulk_update_individual_fields_remain_unchanged(client: AsyncClient) -> None:
    setup = await _setup_students(client, "bulkfields", count=1)
    student = setup["students"][0]

    await client.patch(
        "/api/v1/students/bulk",
        json={"student_ids": [student["id"]], "status": "GRADUATED"},
        headers=setup["headers"],
    )
    row = await _get_student_row(student["id"])
    assert row.matricule == student["matricule"]
    assert row.first_name == student["first_name"]
    assert row.last_name == student["last_name"]
    assert str(row.date_of_birth) == student["date_of_birth"]
    assert row.sex == student["sex"]


async def test_bulk_update_is_atomic_on_unknown_id(client: AsyncClient) -> None:
    setup = await _setup_students(client, "bulkatomic", count=2)
    ids = [s["id"] for s in setup["students"]] + [str(uuid.uuid4())]

    response = await client.patch(
        "/api/v1/students/bulk",
        json={"student_ids": ids, "status": "TRANSFERRED"},
        headers=setup["headers"],
    )
    assert response.status_code == 404
    for student_id in [s["id"] for s in setup["students"]]:
        assert await _history_count(student_id) == 0
        row = await _get_student_row(student_id)
        assert row.status == "ACTIVE"


async def test_bulk_update_rejects_students_from_another_school(client: AsyncClient) -> None:
    setup_a = await _setup_students(client, "bulkxschoola", count=1)
    setup_b = await _setup_students(client, "bulkxschoolb", count=1)
    ids = [setup_a["students"][0]["id"], setup_b["students"][0]["id"]]

    response = await client.patch(
        "/api/v1/students/bulk",
        json={"student_ids": ids, "status": "INACTIVE"},
        headers=setup_a["headers"],
    )
    assert response.status_code in (400, 404)
    for student_id in ids:
        row = await _get_student_row(student_id)
        assert row.status == "ACTIVE"


async def test_bulk_update_rejects_cross_organization_uuid(client: AsyncClient) -> None:
    setup_a = await _setup_students(client, "bulkxorga", count=1)
    other = await register_school(client, "bulkxorgb")
    token_b = await _login(client, other["user"]["email"])
    headers_b = {"Authorization": f"Bearer {token_b}"}
    student_b = await _create_student(client, headers_b, other["school"]["id"], matricule="BXORG-001")

    response = await client.patch(
        "/api/v1/students/bulk",
        json={"student_ids": [setup_a["students"][0]["id"], student_b["id"]], "status": "INACTIVE"},
        headers=setup_a["headers"],
    )
    # L'élève de l'autre organisation est invisible sous RLS pour l'appelant : traité comme
    # manquant (404), jamais comme une fuite cross-organization.
    assert response.status_code == 404
    row = await _get_student_row(setup_a["students"][0]["id"])
    assert row.status == "ACTIVE"


async def test_bulk_update_requires_students_manage(client: AsyncClient) -> None:
    setup = await _setup_students(client, "bulkrbac", count=1)
    teacher_data = await register_school(client, "bulkrbacteacher")
    await assign_role(
        teacher_data["user"]["id"], "TEACHER",
        organization_id=setup["data"]["organization"]["id"], school_id=setup["school_id"],
    )
    teacher_token = await _login(client, teacher_data["user"]["email"])
    teacher_headers = {"Authorization": f"Bearer {teacher_token}"}

    response = await client.patch(
        "/api/v1/students/bulk",
        json={"student_ids": [setup["students"][0]["id"]], "status": "INACTIVE"},
        headers=teacher_headers,
    )
    assert response.status_code == 403


async def test_bulk_update_rejects_empty_list(client: AsyncClient) -> None:
    setup = await _setup_students(client, "bulkempty", count=1)
    response = await client.patch(
        "/api/v1/students/bulk",
        json={"student_ids": [], "status": "INACTIVE"},
        headers=setup["headers"],
    )
    assert response.status_code == 422


async def test_bulk_update_rejects_over_limit(client: AsyncClient) -> None:
    setup = await _setup_students(client, "bulklimit", count=1)
    too_many = [str(uuid.uuid4()) for _ in range(501)]
    response = await client.patch(
        "/api/v1/students/bulk",
        json={"student_ids": too_many, "status": "INACTIVE"},
        headers=setup["headers"],
    )
    assert response.status_code == 422
