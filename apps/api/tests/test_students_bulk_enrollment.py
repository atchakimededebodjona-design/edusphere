"""POST /api/v1/students/bulk-enrollment — affectation en masse des élèves à une classe.

Respecte strictement UNIQUE(student_id, academic_year_id) sur StudentEnrollment : jamais de
nouvelle ligne pour un élève déjà inscrit cette année, seulement une mise à jour (class_id +
status) de la ligne existante. Catégorisation : created / reassigned / unchanged (jamais mélangées).
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.students.models import StudentEnrollment
from tests.conftest import assign_role, register_school
from tests.test_students import _create_student, _login


async def _setup_school(client: AsyncClient, prefix: str) -> dict:
    data = await register_school(client, prefix)
    token = await _login(client, data["user"]["email"])
    headers = {"Authorization": f"Bearer {token}"}
    school_id = data["school"]["id"]
    organization_id = data["organization"]["id"]
    return {"data": data, "headers": headers, "school_id": school_id, "organization_id": organization_id}


async def _create_year(client: AsyncClient, setup: dict, name: str = "2026-2027", is_current: bool = False) -> dict:
    response = await client.post(
        "/api/v1/academic-years",
        json={
            "school_id": setup["school_id"], "name": name,
            "start_date": "2026-09-01", "end_date": "2027-06-30", "is_current": is_current,
        },
        headers=setup["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_level(client: AsyncClient, setup: dict, name: str = "CM1") -> dict:
    response = await client.post(
        "/api/v1/education-levels", json={"school_id": setup["school_id"], "name": name}, headers=setup["headers"]
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_class(
    client: AsyncClient, setup: dict, year_id: str, level_id: str, name: str = "A", capacity: int | None = None
) -> dict:
    payload: dict[str, object] = {"academic_year_id": year_id, "education_level_id": level_id, "name": name}
    if capacity is not None:
        payload["capacity"] = capacity
    response = await client.post("/api/v1/classes", json=payload, headers=setup["headers"])
    assert response.status_code == 201, response.text
    return response.json()


async def _students(client: AsyncClient, setup: dict, prefix: str, count: int) -> list[dict]:
    return [
        await _create_student(client, setup["headers"], setup["school_id"], matricule=f"{prefix}-{i:03d}")
        for i in range(count)
    ]


async def _enrollment_count_for_class(class_id: str) -> int:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        result = await db.execute(
            select(StudentEnrollment).where(
                StudentEnrollment.class_id == uuid.UUID(class_id), StudentEnrollment.status == "ACTIVE"
            )
        )
        return len(result.scalars().all())


async def _bulk_enroll(
    client: AsyncClient, setup: dict, student_ids: list[str], year_id: str, class_id: str,
    enrollment_date: str = "2026-09-01", dry_run: bool = False,
):
    return await client.post(
        f"/api/v1/students/bulk-enrollment?dry_run={'true' if dry_run else 'false'}",
        json={
            "student_ids": student_ids, "academic_year_id": year_id, "class_id": class_id,
            "enrollment_date": enrollment_date,
        },
        headers=setup["headers"],
    )


# --- A : nouveaux élèves ---------------------------------------------------------------------------
async def test_bulk_enrollment_creates_new_enrollments(client: AsyncClient) -> None:
    setup = await _setup_school(client, "benrollnew")
    year = await _create_year(client, setup)
    level = await _create_level(client, setup)
    school_class = await _create_class(client, setup, year["id"], level["id"])
    students = await _students(client, setup, "NEW", 5)

    response = await _bulk_enroll(client, setup, [s["id"] for s in students], year["id"], school_class["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created_count"] == 5
    assert body["reassigned_count"] == 0
    assert body["unchanged_count"] == 0
    assert body["selected_count"] == 5
    assert await _enrollment_count_for_class(school_class["id"]) == 5


# --- B : réaffectation ------------------------------------------------------------------------------
async def test_bulk_enrollment_reassigns_without_duplicate_row(client: AsyncClient) -> None:
    setup = await _setup_school(client, "benrollreassign")
    year = await _create_year(client, setup)
    level = await _create_level(client, setup)
    class_a = await _create_class(client, setup, year["id"], level["id"], name="A")
    class_b = await _create_class(client, setup, year["id"], level["id"], name="B")
    student = (await _students(client, setup, "REAS", 1))[0]

    first = await _bulk_enroll(client, setup, [student["id"]], year["id"], class_a["id"])
    assert first.status_code == 200, first.text

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        result = await db.execute(
            select(StudentEnrollment).where(StudentEnrollment.student_id == uuid.UUID(student["id"]))
        )
        enrollment_id_a = str(result.scalar_one().id)

    second = await _bulk_enroll(client, setup, [student["id"]], year["id"], class_b["id"])
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["created_count"] == 0
    assert body["reassigned_count"] == 1
    assert body["unchanged_count"] == 0

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        result = await db.execute(
            select(StudentEnrollment).where(StudentEnrollment.student_id == uuid.UUID(student["id"]))
        )
        rows = result.scalars().all()
        assert len(rows) == 1, "Une seule ligne StudentEnrollment pour cette année, jamais une deuxième"
        assert str(rows[0].id) == enrollment_id_a
        assert str(rows[0].class_id) == class_b["id"]
        assert rows[0].status == "ACTIVE"


# --- C : déjà dans la classe cible --------------------------------------------------------------------
async def test_bulk_enrollment_unchanged_when_already_in_target_class(client: AsyncClient) -> None:
    setup = await _setup_school(client, "benrollunchanged")
    year = await _create_year(client, setup)
    level = await _create_level(client, setup)
    school_class = await _create_class(client, setup, year["id"], level["id"])
    student = (await _students(client, setup, "UNCH", 1))[0]

    await _bulk_enroll(client, setup, [student["id"]], year["id"], school_class["id"])
    second = await _bulk_enroll(client, setup, [student["id"]], year["id"], school_class["id"])
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["created_count"] == 0
    assert body["reassigned_count"] == 0
    assert body["unchanged_count"] == 1


# --- D : mix nouveaux + réaffectés + inchangés -------------------------------------------------------
async def test_bulk_enrollment_mixed_categories(client: AsyncClient) -> None:
    setup = await _setup_school(client, "benrollmix")
    year = await _create_year(client, setup)
    level = await _create_level(client, setup)
    class_a = await _create_class(client, setup, year["id"], level["id"], name="A")
    class_b = await _create_class(client, setup, year["id"], level["id"], name="B")
    new_student, already_in_a, already_in_b = await _students(client, setup, "MIX", 3)

    await _bulk_enroll(client, setup, [already_in_a["id"]], year["id"], class_a["id"])
    await _bulk_enroll(client, setup, [already_in_b["id"]], year["id"], class_b["id"])

    response = await _bulk_enroll(
        client, setup, [new_student["id"], already_in_a["id"], already_in_b["id"]], year["id"], class_a["id"]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created_count"] == 1
    assert body["reassigned_count"] == 1  # already_in_b -> class_a
    assert body["unchanged_count"] == 1  # already_in_a déjà dans class_a


# --- E : capacité -------------------------------------------------------------------------------------
async def test_bulk_enrollment_succeeds_at_exact_capacity(client: AsyncClient) -> None:
    setup = await _setup_school(client, "benrollcapexact")
    year = await _create_year(client, setup)
    level = await _create_level(client, setup)
    school_class = await _create_class(client, setup, year["id"], level["id"], capacity=3)
    students = await _students(client, setup, "CAPEX", 3)

    response = await _bulk_enroll(client, setup, [s["id"] for s in students], year["id"], school_class["id"])
    assert response.status_code == 200, response.text
    assert response.json()["created_count"] == 3


async def test_bulk_enrollment_rejects_when_capacity_insufficient(client: AsyncClient) -> None:
    setup = await _setup_school(client, "benrollcapfull")
    year = await _create_year(client, setup)
    level = await _create_level(client, setup)
    school_class = await _create_class(client, setup, year["id"], level["id"], capacity=3)
    students = await _students(client, setup, "CAPFULL", 5)

    response = await _bulk_enroll(client, setup, [s["id"] for s in students], year["id"], school_class["id"])
    assert response.status_code == 409, response.text
    assert await _enrollment_count_for_class(school_class["id"]) == 0  # rollback total, rien n'est affecté


async def test_bulk_enrollment_capacity_accounts_for_already_enrolled_not_consuming_new_seat(
    client: AsyncClient,
) -> None:
    """3 places, 2 déjà occupées par des élèves de la sélection elle-même (donc ne consomment pas
    une nouvelle place) + 1 nouvel élève = 1 place nécessaire, largement suffisant."""
    setup = await _setup_school(client, "benrollcapown")
    year = await _create_year(client, setup)
    level = await _create_level(client, setup)
    school_class = await _create_class(client, setup, year["id"], level["id"], capacity=3)
    already_there = await _students(client, setup, "CAPOWN-IN", 2)
    new_one = (await _students(client, setup, "CAPOWN-NEW", 1))[0]

    await _bulk_enroll(client, setup, [s["id"] for s in already_there], year["id"], school_class["id"])

    response = await _bulk_enroll(
        client, setup, [s["id"] for s in already_there] + [new_one["id"]], year["id"], school_class["id"]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["unchanged_count"] == 2
    assert body["created_count"] == 1


# --- F : classe d'une autre année ----------------------------------------------------------------------
async def test_bulk_enrollment_rejects_class_from_another_academic_year(client: AsyncClient) -> None:
    setup = await _setup_school(client, "benrollwrongyear")
    year_a = await _create_year(client, setup, name="2026-2027")
    year_b = await _create_year(client, setup, name="2027-2028")
    level = await _create_level(client, setup)
    class_in_b = await _create_class(client, setup, year_b["id"], level["id"])
    student = (await _students(client, setup, "WYEAR", 1))[0]

    response = await _bulk_enroll(client, setup, [student["id"]], year_a["id"], class_in_b["id"])
    assert response.status_code == 400


# --- G : classe d'une autre école ------------------------------------------------------------------------
async def test_bulk_enrollment_rejects_students_from_another_school(client: AsyncClient) -> None:
    setup_a = await _setup_school(client, "benrollschoola")
    setup_b = await _setup_school(client, "benrollschoolb")
    year_a = await _create_year(client, setup_a)
    level_a = await _create_level(client, setup_a)
    class_a = await _create_class(client, setup_a, year_a["id"], level_a["id"])
    student_b = (await _students(client, setup_b, "OSCHOOL", 1))[0]

    response = await _bulk_enroll(client, setup_a, [student_b["id"]], year_a["id"], class_a["id"])
    # L'élève de l'autre organisation est invisible sous RLS pour l'appelant : traité comme
    # manquant (404), jamais comme une fuite cross-organization — même garantie que PATCH /students/bulk.
    assert response.status_code == 404


# --- H : tenant isolation ----------------------------------------------------------------------------
async def test_bulk_enrollment_rejects_cross_organization_student(client: AsyncClient) -> None:
    setup_a = await _setup_school(client, "benrolltenanta")
    setup_b = await _setup_school(client, "benrolltenantb")
    year_a = await _create_year(client, setup_a)
    level_a = await _create_level(client, setup_a)
    class_a = await _create_class(client, setup_a, year_a["id"], level_a["id"])
    student_a = (await _students(client, setup_a, "TENA", 1))[0]
    student_b = (await _students(client, setup_b, "TENB", 1))[0]

    response = await _bulk_enroll(
        client, setup_a, [student_a["id"], student_b["id"]], year_a["id"], class_a["id"]
    )
    assert response.status_code == 404
    assert await _enrollment_count_for_class(class_a["id"]) == 0


# --- I : RBAC ------------------------------------------------------------------------------------------
async def test_bulk_enrollment_requires_students_manage(client: AsyncClient) -> None:
    setup = await _setup_school(client, "benrollrbac")
    year = await _create_year(client, setup)
    level = await _create_level(client, setup)
    school_class = await _create_class(client, setup, year["id"], level["id"])
    student = (await _students(client, setup, "RBAC", 1))[0]

    teacher_data = await register_school(client, "benrollrbacteacher")
    await assign_role(
        teacher_data["user"]["id"], "TEACHER",
        organization_id=setup["organization_id"], school_id=setup["school_id"],
    )
    teacher_headers = {"Authorization": f"Bearer {await _login(client, teacher_data['user']['email'])}"}

    response = await client.post(
        "/api/v1/students/bulk-enrollment",
        json={
            "student_ids": [student["id"]], "academic_year_id": year["id"], "class_id": school_class["id"],
            "enrollment_date": "2026-09-01",
        },
        headers=teacher_headers,
    )
    assert response.status_code == 403
    assert await _enrollment_count_for_class(school_class["id"]) == 0


# --- J : atomicité ---------------------------------------------------------------------------------------
async def test_bulk_enrollment_is_atomic_on_unknown_student_id(client: AsyncClient) -> None:
    setup = await _setup_school(client, "benrollatomic")
    year = await _create_year(client, setup)
    level = await _create_level(client, setup)
    school_class = await _create_class(client, setup, year["id"], level["id"])
    students = await _students(client, setup, "ATOMIC", 10)
    ids = [s["id"] for s in students] + [str(uuid.uuid4())]

    response = await _bulk_enroll(client, setup, ids, year["id"], school_class["id"])
    assert response.status_code == 404
    assert await _enrollment_count_for_class(school_class["id"]) == 0


# --- K : doublons -----------------------------------------------------------------------------------------
async def test_bulk_enrollment_deduplicates_repeated_student_ids(client: AsyncClient) -> None:
    setup = await _setup_school(client, "benrolldup")
    year = await _create_year(client, setup)
    level = await _create_level(client, setup)
    school_class = await _create_class(client, setup, year["id"], level["id"])
    student = (await _students(client, setup, "DUP", 1))[0]

    response = await _bulk_enroll(
        client, setup, [student["id"], student["id"], student["id"]], year["id"], school_class["id"]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["selected_count"] == 1
    assert body["created_count"] == 1
    assert await _enrollment_count_for_class(school_class["id"]) == 1


# --- L : grande sélection ----------------------------------------------------------------------------------
async def test_bulk_enrollment_rejects_over_500_students(client: AsyncClient) -> None:
    setup = await _setup_school(client, "benrolllimit")
    year = await _create_year(client, setup)
    level = await _create_level(client, setup)
    school_class = await _create_class(client, setup, year["id"], level["id"])
    too_many = [str(uuid.uuid4()) for _ in range(501)]

    response = await _bulk_enroll(client, setup, too_many, year["id"], school_class["id"])
    assert response.status_code == 422


async def test_bulk_enrollment_rejects_empty_list(client: AsyncClient) -> None:
    setup = await _setup_school(client, "benrollempty")
    year = await _create_year(client, setup)
    level = await _create_level(client, setup)
    school_class = await _create_class(client, setup, year["id"], level["id"])

    response = await _bulk_enroll(client, setup, [], year["id"], school_class["id"])
    assert response.status_code == 422


# --- Aperçu (dry_run) -------------------------------------------------------------------------------------
async def test_bulk_enrollment_dry_run_does_not_mutate(client: AsyncClient) -> None:
    setup = await _setup_school(client, "benrolldry")
    year = await _create_year(client, setup)
    level = await _create_level(client, setup)
    school_class = await _create_class(client, setup, year["id"], level["id"], capacity=10)
    students = await _students(client, setup, "DRY", 4)

    response = await _bulk_enroll(
        client, setup, [s["id"] for s in students], year["id"], school_class["id"], dry_run=True
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created_count"] == 4
    assert body["capacity"] == 10
    assert body["available_places"] == 10
    assert body["students"] == []
    assert await _enrollment_count_for_class(school_class["id"]) == 0  # rien écrit en base


async def test_bulk_enrollment_dry_run_reports_capacity_shortage_without_mutating(client: AsyncClient) -> None:
    setup = await _setup_school(client, "benrolldryfull")
    year = await _create_year(client, setup)
    level = await _create_level(client, setup)
    school_class = await _create_class(client, setup, year["id"], level["id"], capacity=2)
    students = await _students(client, setup, "DRYFULL", 5)

    response = await _bulk_enroll(
        client, setup, [s["id"] for s in students], year["id"], school_class["id"], dry_run=True
    )
    assert response.status_code == 409
    assert await _enrollment_count_for_class(school_class["id"]) == 0


# --- Capacité illimitée -------------------------------------------------------------------------------------
async def test_bulk_enrollment_unlimited_capacity_never_rejects(client: AsyncClient) -> None:
    setup = await _setup_school(client, "benrollnolimit")
    year = await _create_year(client, setup)
    level = await _create_level(client, setup)
    school_class = await _create_class(client, setup, year["id"], level["id"])  # capacity=None
    students = await _students(client, setup, "NOLIMIT", 50)

    response = await _bulk_enroll(client, setup, [s["id"] for s in students], year["id"], school_class["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available_places"] is None
    assert body["created_count"] == 50


# --- GET /students : colonne Classe (enrichissement) + filtre "Non affectés" -------------------------------
async def test_list_students_shows_current_class_for_current_academic_year(client: AsyncClient) -> None:
    setup = await _setup_school(client, "blistclass")
    year = await _create_year(client, setup, is_current=True)
    level = await _create_level(client, setup)
    school_class = await _create_class(client, setup, year["id"], level["id"], name="CM1 A")
    enrolled, unassigned = await _students(client, setup, "LISTCLASS", 2)
    await _bulk_enroll(client, setup, [enrolled["id"]], year["id"], school_class["id"])

    response = await client.get(f"/api/v1/students?school_id={setup['school_id']}", headers=setup["headers"])
    assert response.status_code == 200, response.text
    by_id = {s["id"]: s for s in response.json()}
    assert by_id[enrolled["id"]]["current_class_id"] == school_class["id"]
    assert by_id[enrolled["id"]]["current_class_name"] == "CM1 A"
    assert by_id[unassigned["id"]]["current_class_id"] is None
    assert by_id[unassigned["id"]]["current_class_name"] is None


async def test_list_students_current_class_null_without_current_academic_year(client: AsyncClient) -> None:
    setup = await _setup_school(client, "blistnoyear")
    year = await _create_year(client, setup, is_current=False)  # aucune année marquée courante
    level = await _create_level(client, setup)
    school_class = await _create_class(client, setup, year["id"], level["id"])
    student = (await _students(client, setup, "NOYEAR", 1))[0]
    await _bulk_enroll(client, setup, [student["id"]], year["id"], school_class["id"])

    response = await client.get(f"/api/v1/students?school_id={setup['school_id']}", headers=setup["headers"])
    assert response.status_code == 200, response.text
    assert response.json()[0]["current_class_name"] is None


async def test_list_students_unassigned_only_filter(client: AsyncClient) -> None:
    setup = await _setup_school(client, "blistunassigned")
    year = await _create_year(client, setup, is_current=True)
    level = await _create_level(client, setup)
    school_class = await _create_class(client, setup, year["id"], level["id"])
    enrolled, unassigned = await _students(client, setup, "UNASSIGNED", 2)
    await _bulk_enroll(client, setup, [enrolled["id"]], year["id"], school_class["id"])

    response = await client.get(
        f"/api/v1/students?school_id={setup['school_id']}&unassigned_only=true", headers=setup["headers"]
    )
    assert response.status_code == 200, response.text
    ids = {s["id"] for s in response.json()}
    assert ids == {unassigned["id"]}
