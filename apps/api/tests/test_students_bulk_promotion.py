"""POST /api/v1/students/bulk-promotion — réinscription/promotion en masse vers une nouvelle
année scolaire, d'après un mapping classe source -> classe cible fourni par l'appelant.

Catégories (jamais mélangées) : promoted / repeated / already_enrolled / no_target_class (lui-même
scindé en exit + unprocessed, voir test_students_exit_disposition.py pour les dispositions de
sortie). Une capacité insuffisante (par classe cible) OU des élèves "unprocessed" restants sont
bloquants — jamais de mutation partielle, dry_run ou non. L'historique académique (lignes de
l'année SOURCE) n'est jamais modifié.
"""

import asyncio
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
    return {
        "data": data, "headers": headers,
        "school_id": data["school"]["id"], "organization_id": data["organization"]["id"],
    }


async def _create_year(client: AsyncClient, setup: dict, name: str, is_current: bool = False) -> dict:
    response = await client.post(
        "/api/v1/academic-years",
        json={
            "school_id": setup["school_id"], "name": name,
            "start_date": f"{name[:4]}-09-01", "end_date": f"{int(name[:4]) + 1}-06-30", "is_current": is_current,
        },
        headers=setup["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_level(client: AsyncClient, setup: dict, name: str) -> dict:
    response = await client.post(
        "/api/v1/education-levels", json={"school_id": setup["school_id"], "name": name}, headers=setup["headers"]
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_class(
    client: AsyncClient, setup: dict, year_id: str, level_id: str, name: str, capacity: int | None = None
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


async def _enroll(client: AsyncClient, setup: dict, student_ids: list[str], year_id: str, class_id: str) -> None:
    response = await client.post(
        "/api/v1/students/bulk-enrollment",
        json={"student_ids": student_ids, "academic_year_id": year_id, "class_id": class_id, "enrollment_date": "2026-09-01"},
        headers=setup["headers"],
    )
    assert response.status_code == 200, response.text


async def _promote(
    client: AsyncClient, setup: dict, source_year_id: str, target_year_id: str,
    class_mappings: list[dict], student_ids: list[str], enrollment_date: str = "2027-09-01", dry_run: bool = False,
    exit_dispositions: list[dict] | None = None,
):
    return await client.post(
        f"/api/v1/students/bulk-promotion?dry_run={'true' if dry_run else 'false'}",
        json={
            "source_academic_year_id": source_year_id, "target_academic_year_id": target_year_id,
            "class_mappings": class_mappings, "exit_dispositions": exit_dispositions or [],
            "student_ids": student_ids, "enrollment_date": enrollment_date,
        },
        headers=setup["headers"],
    )


async def _enrollments_for_year(student_id: str, year_id: str) -> list[StudentEnrollment]:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        result = await db.execute(
            select(StudentEnrollment).where(
                StudentEnrollment.student_id == uuid.UUID(student_id),
                StudentEnrollment.academic_year_id == uuid.UUID(year_id),
            )
        )
        return list(result.scalars().all())


async def _active_count_for_class(class_id: str) -> int:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        result = await db.execute(
            select(StudentEnrollment).where(
                StudentEnrollment.class_id == uuid.UUID(class_id), StudentEnrollment.status == "ACTIVE"
            )
        )
        return len(result.scalars().all())


# --- Catégorisation : promu / redoublant ------------------------------------------------------------
async def test_promotion_creates_promoted_enrollment_for_different_level(client: AsyncClient) -> None:
    setup = await _setup_school(client, "promopromote")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level_a = await _create_level(client, setup, "CM1")
    level_b = await _create_level(client, setup, "CM2")
    source_class = await _create_class(client, setup, source_year["id"], level_a["id"], "A")
    target_class = await _create_class(client, setup, target_year["id"], level_b["id"], "A")
    student = (await _students(client, setup, "PROMOTE", 1))[0]
    await _enroll(client, setup, [student["id"]], source_year["id"], source_class["id"])

    response = await _promote(
        client, setup, source_year["id"], target_year["id"],
        [{"source_class_id": source_class["id"], "target_class_id": target_class["id"]}], [student["id"]],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["promoted_count"] == 1
    assert body["repeated_count"] == 0

    rows = await _enrollments_for_year(student["id"], target_year["id"])
    assert len(rows) == 1
    assert str(rows[0].class_id) == target_class["id"]
    assert rows[0].promotion_type == "PROMOTED"
    assert rows[0].status == "ACTIVE"


async def test_promotion_creates_repeated_enrollment_for_same_level(client: AsyncClient) -> None:
    setup = await _setup_school(client, "promorepeat")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level = await _create_level(client, setup, "CM1")
    source_class = await _create_class(client, setup, source_year["id"], level["id"], "A")
    target_class = await _create_class(client, setup, target_year["id"], level["id"], "A")
    student = (await _students(client, setup, "REPEAT", 1))[0]
    await _enroll(client, setup, [student["id"]], source_year["id"], source_class["id"])

    response = await _promote(
        client, setup, source_year["id"], target_year["id"],
        [{"source_class_id": source_class["id"], "target_class_id": target_class["id"]}], [student["id"]],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["promoted_count"] == 0
    assert body["repeated_count"] == 1

    rows = await _enrollments_for_year(student["id"], target_year["id"])
    assert rows[0].promotion_type == "REPEATED"


# --- Déjà inscrit / sans classe cible -----------------------------------------------------------------
async def test_promotion_already_enrolled_students_are_never_touched(client: AsyncClient) -> None:
    setup = await _setup_school(client, "promoalready")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level = await _create_level(client, setup, "CM1")
    source_class = await _create_class(client, setup, source_year["id"], level["id"], "A")
    target_class = await _create_class(client, setup, target_year["id"], level["id"], "A")
    other_target_class = await _create_class(client, setup, target_year["id"], level["id"], "B")
    student = (await _students(client, setup, "ALREADY", 1))[0]
    await _enroll(client, setup, [student["id"]], source_year["id"], source_class["id"])
    # Déjà inscrit manuellement dans une AUTRE classe cible avant la promotion.
    await _enroll(client, setup, [student["id"]], target_year["id"], other_target_class["id"])

    response = await _promote(
        client, setup, source_year["id"], target_year["id"],
        [{"source_class_id": source_class["id"], "target_class_id": target_class["id"]}], [student["id"]],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["already_enrolled_count"] == 1
    assert body["promoted_count"] == 0
    assert body["repeated_count"] == 0

    rows = await _enrollments_for_year(student["id"], target_year["id"])
    assert len(rows) == 1
    assert str(rows[0].class_id) == other_target_class["id"], "Jamais réaffecté par la promotion"


async def test_promotion_no_target_class_is_skipped_without_mutation(client: AsyncClient) -> None:
    """Une classe source sans correspondance n'est plus un "oubli" silencieux depuis le sprint
    sortie d'établissement (voir test_students_exit_disposition.py) : elle doit être explicitement
    déclarée en sortie pour que la confirmation reste possible. Ici, elle l'est (GRADUATED) — ses
    élèves sont comptés en "exit", jamais en inscription cible, jamais en "non traité bloquant"."""
    setup = await _setup_school(client, "promonotarget")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level = await _create_level(client, setup, "CM1")
    source_class = await _create_class(client, setup, source_year["id"], level["id"], "A")
    unmapped_source_class = await _create_class(client, setup, source_year["id"], level["id"], "B")
    target_class = await _create_class(client, setup, target_year["id"], level["id"], "A")
    mapped_student, unmapped_student = await _students(client, setup, "NOTARGET", 2)
    await _enroll(client, setup, [mapped_student["id"]], source_year["id"], source_class["id"])
    await _enroll(client, setup, [unmapped_student["id"]], source_year["id"], unmapped_source_class["id"])

    response = await _promote(
        client, setup, source_year["id"], target_year["id"],
        [{"source_class_id": source_class["id"], "target_class_id": target_class["id"]}],
        [mapped_student["id"], unmapped_student["id"]],
        exit_dispositions=[{"source_class_id": unmapped_source_class["id"], "exit_type": "GRADUATED"}],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["no_target_class_count"] == 1
    assert body["exit_count"] == 1
    assert body["unprocessed_no_target_class_count"] == 0
    assert body["promoted_count"] + body["repeated_count"] == 1

    assert await _enrollments_for_year(unmapped_student["id"], target_year["id"]) == []


async def test_promotion_mixed_categories(client: AsyncClient) -> None:
    setup = await _setup_school(client, "promomix")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level_a = await _create_level(client, setup, "CM1")
    level_b = await _create_level(client, setup, "CM2")
    source_class_a = await _create_class(client, setup, source_year["id"], level_a["id"], "A")
    source_class_c = await _create_class(client, setup, source_year["id"], level_a["id"], "C")
    target_class_promoted = await _create_class(client, setup, target_year["id"], level_b["id"], "A")
    target_class_same_level = await _create_class(client, setup, target_year["id"], level_a["id"], "A-repeat")

    new_student, repeat_student, already_student, no_target_student = await _students(client, setup, "MIX", 4)
    await _enroll(client, setup, [new_student["id"], repeat_student["id"]], source_year["id"], source_class_a["id"])
    await _enroll(client, setup, [no_target_student["id"]], source_year["id"], source_class_c["id"])
    await _enroll(client, setup, [already_student["id"]], source_year["id"], source_class_a["id"])
    # already_student est déjà inscrit pour l'année CIBLE (dans une autre classe) avant promotion.
    await _enroll(client, setup, [already_student["id"]], target_year["id"], target_class_same_level["id"])

    response = await _promote(
        client, setup, source_year["id"], target_year["id"],
        [{"source_class_id": source_class_a["id"], "target_class_id": target_class_promoted["id"]}],
        [new_student["id"], repeat_student["id"], already_student["id"], no_target_student["id"]],
        exit_dispositions=[{"source_class_id": source_class_c["id"], "exit_type": "GRADUATED"}],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["selected_count"] == 4
    assert body["promoted_count"] == 2  # new_student + repeat_student -> level_b (différent de level_a)
    assert body["repeated_count"] == 0
    assert body["already_enrolled_count"] == 1
    assert body["no_target_class_count"] == 1
    assert body["exit_count"] == 1
    assert body["unprocessed_no_target_class_count"] == 0


# --- Historique académique -----------------------------------------------------------------------------
async def test_promotion_preserves_source_year_enrollment_row(client: AsyncClient) -> None:
    setup = await _setup_school(client, "promohistory")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level = await _create_level(client, setup, "CM1")
    source_class = await _create_class(client, setup, source_year["id"], level["id"], "A")
    target_class = await _create_class(client, setup, target_year["id"], level["id"], "A")
    student = (await _students(client, setup, "HISTORY", 1))[0]
    await _enroll(client, setup, [student["id"]], source_year["id"], source_class["id"])

    source_rows_before = await _enrollments_for_year(student["id"], source_year["id"])
    assert len(source_rows_before) == 1
    source_enrollment_id = source_rows_before[0].id

    await _promote(
        client, setup, source_year["id"], target_year["id"],
        [{"source_class_id": source_class["id"], "target_class_id": target_class["id"]}], [student["id"]],
    )

    source_rows_after = await _enrollments_for_year(student["id"], source_year["id"])
    assert len(source_rows_after) == 1
    assert source_rows_after[0].id == source_enrollment_id
    assert str(source_rows_after[0].class_id) == source_class["id"]
    assert source_rows_after[0].status == "ACTIVE"  # jamais modifié


# --- Capacité --------------------------------------------------------------------------------------------
async def test_promotion_succeeds_at_exact_capacity(client: AsyncClient) -> None:
    setup = await _setup_school(client, "promocapexact")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level = await _create_level(client, setup, "CM1")
    source_class = await _create_class(client, setup, source_year["id"], level["id"], "A")
    target_class = await _create_class(client, setup, target_year["id"], level["id"], "A", capacity=3)
    students = await _students(client, setup, "CAPEXACT", 3)
    await _enroll(client, setup, [s["id"] for s in students], source_year["id"], source_class["id"])

    response = await _promote(
        client, setup, source_year["id"], target_year["id"],
        [{"source_class_id": source_class["id"], "target_class_id": target_class["id"]}],
        [s["id"] for s in students],
    )
    assert response.status_code == 200, response.text
    assert response.json()["repeated_count"] == 3


async def test_promotion_rejects_atomically_when_capacity_insufficient(client: AsyncClient) -> None:
    setup = await _setup_school(client, "promocapfull")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level = await _create_level(client, setup, "CM1")
    source_class = await _create_class(client, setup, source_year["id"], level["id"], "A")
    target_class = await _create_class(client, setup, target_year["id"], level["id"], "A", capacity=2)
    students = await _students(client, setup, "CAPFULL", 5)
    await _enroll(client, setup, [s["id"] for s in students], source_year["id"], source_class["id"])

    response = await _promote(
        client, setup, source_year["id"], target_year["id"],
        [{"source_class_id": source_class["id"], "target_class_id": target_class["id"]}],
        [s["id"] for s in students],
    )
    assert response.status_code == 409, response.text
    # Aucune mutation, même partielle : aucun des 5 élèves ne doit avoir d'inscription cible.
    for s in students:
        assert await _enrollments_for_year(s["id"], target_year["id"]) == []


async def test_promotion_concurrent_requests_never_exceed_capacity(client: AsyncClient) -> None:
    """capacity=1 sur la classe cible, deux promotions concurrentes amenant chacune 1 élève
    DIFFÉRENT vers cette même classe : une seule doit réussir, l'autre doit échouer (409), et la
    classe ne doit jamais dépasser 1 inscrit actif."""
    setup = await _setup_school(client, "promoconcurrent")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level = await _create_level(client, setup, "CM1")
    source_class_a = await _create_class(client, setup, source_year["id"], level["id"], "A")
    source_class_b = await _create_class(client, setup, source_year["id"], level["id"], "B")
    target_class = await _create_class(client, setup, target_year["id"], level["id"], "A", capacity=1)
    student_a = (await _students(client, setup, "RACEA", 1))[0]
    student_b = (await _students(client, setup, "RACEB", 1))[0]
    await _enroll(client, setup, [student_a["id"]], source_year["id"], source_class_a["id"])
    await _enroll(client, setup, [student_b["id"]], source_year["id"], source_class_b["id"])

    results = await asyncio.gather(
        _promote(
            client, setup, source_year["id"], target_year["id"],
            [{"source_class_id": source_class_a["id"], "target_class_id": target_class["id"]}], [student_a["id"]],
        ),
        _promote(
            client, setup, source_year["id"], target_year["id"],
            [{"source_class_id": source_class_b["id"], "target_class_id": target_class["id"]}], [student_b["id"]],
        ),
    )
    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409], [r.text for r in results]
    assert await _active_count_for_class(target_class["id"]) == 1


async def test_promotion_dry_run_does_not_mutate(client: AsyncClient) -> None:
    setup = await _setup_school(client, "promodry")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level = await _create_level(client, setup, "CM1")
    source_class = await _create_class(client, setup, source_year["id"], level["id"], "A")
    target_class = await _create_class(client, setup, target_year["id"], level["id"], "A", capacity=10)
    students = await _students(client, setup, "DRY", 4)
    await _enroll(client, setup, [s["id"] for s in students], source_year["id"], source_class["id"])

    response = await _promote(
        client, setup, source_year["id"], target_year["id"],
        [{"source_class_id": source_class["id"], "target_class_id": target_class["id"]}],
        [s["id"] for s in students], dry_run=True,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["repeated_count"] == 4
    assert body["students"] == []
    assert body["class_previews"][0]["available_places"] == 10
    for s in students:
        assert await _enrollments_for_year(s["id"], target_year["id"]) == []


async def test_promotion_dry_run_reports_capacity_shortage_without_mutating(client: AsyncClient) -> None:
    setup = await _setup_school(client, "promodryfull")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level = await _create_level(client, setup, "CM1")
    source_class = await _create_class(client, setup, source_year["id"], level["id"], "A")
    target_class = await _create_class(client, setup, target_year["id"], level["id"], "A", capacity=1)
    students = await _students(client, setup, "DRYFULL", 3)
    await _enroll(client, setup, [s["id"] for s in students], source_year["id"], source_class["id"])

    response = await _promote(
        client, setup, source_year["id"], target_year["id"],
        [{"source_class_id": source_class["id"], "target_class_id": target_class["id"]}],
        [s["id"] for s in students], dry_run=True,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["blocking_errors"]) == 1
    assert "place" in body["blocking_errors"][0]
    for s in students:
        assert await _enrollments_for_year(s["id"], target_year["id"]) == []


# --- Validation structurelle -------------------------------------------------------------------------------
async def test_promotion_rejects_same_source_and_target_year(client: AsyncClient) -> None:
    setup = await _setup_school(client, "promosameyear")
    year = await _create_year(client, setup, "2026")
    level = await _create_level(client, setup, "CM1")
    school_class = await _create_class(client, setup, year["id"], level["id"], "A")
    student = (await _students(client, setup, "SAMEYEAR", 1))[0]
    await _enroll(client, setup, [student["id"]], year["id"], school_class["id"])

    response = await _promote(
        client, setup, year["id"], year["id"],
        [{"source_class_id": school_class["id"], "target_class_id": school_class["id"]}], [student["id"]],
    )
    assert response.status_code == 400


async def test_promotion_rejects_years_from_different_schools(client: AsyncClient) -> None:
    setup_a = await _setup_school(client, "promodiffschoola")
    setup_b = await _setup_school(client, "promodiffschoolb")
    source_year = await _create_year(client, setup_a, "2026")
    target_year = await _create_year(client, setup_b, "2027")
    level_a = await _create_level(client, setup_a, "CM1")
    level_b = await _create_level(client, setup_b, "CM1")
    source_class = await _create_class(client, setup_a, source_year["id"], level_a["id"], "A")
    target_class = await _create_class(client, setup_b, target_year["id"], level_b["id"], "A")

    response = await _promote(
        client, setup_a, source_year["id"], target_year["id"],
        [{"source_class_id": source_class["id"], "target_class_id": target_class["id"]}], [str(uuid.uuid4())],
    )
    assert response.status_code in (400, 404)


async def test_promotion_rejects_duplicate_source_class_in_mapping(client: AsyncClient) -> None:
    setup = await _setup_school(client, "promodupmapping")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level = await _create_level(client, setup, "CM1")
    source_class = await _create_class(client, setup, source_year["id"], level["id"], "A")
    target_class_1 = await _create_class(client, setup, target_year["id"], level["id"], "A")
    target_class_2 = await _create_class(client, setup, target_year["id"], level["id"], "B")

    response = await _promote(
        client, setup, source_year["id"], target_year["id"],
        [
            {"source_class_id": source_class["id"], "target_class_id": target_class_1["id"]},
            {"source_class_id": source_class["id"], "target_class_id": target_class_2["id"]},
        ],
        [str(uuid.uuid4())],
    )
    assert response.status_code == 400


async def test_promotion_rejects_mapping_class_from_wrong_year(client: AsyncClient) -> None:
    setup = await _setup_school(client, "promowrongyearmap")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    other_year = await _create_year(client, setup, "2028")
    level = await _create_level(client, setup, "CM1")
    source_class = await _create_class(client, setup, source_year["id"], level["id"], "A")
    class_in_other_year = await _create_class(client, setup, other_year["id"], level["id"], "A")

    response = await _promote(
        client, setup, source_year["id"], target_year["id"],
        [{"source_class_id": source_class["id"], "target_class_id": class_in_other_year["id"]}],
        [str(uuid.uuid4())],
    )
    assert response.status_code == 400


async def test_promotion_rejects_student_not_actively_enrolled_in_source_year(client: AsyncClient) -> None:
    setup = await _setup_school(client, "promonotenrolled")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level = await _create_level(client, setup, "CM1")
    source_class = await _create_class(client, setup, source_year["id"], level["id"], "A")
    target_class = await _create_class(client, setup, target_year["id"], level["id"], "A")
    student = (await _students(client, setup, "NOTENROLLED", 1))[0]  # jamais inscrit nulle part

    response = await _promote(
        client, setup, source_year["id"], target_year["id"],
        [{"source_class_id": source_class["id"], "target_class_id": target_class["id"]}], [student["id"]],
    )
    assert response.status_code == 400


# --- Tenant / RBAC -----------------------------------------------------------------------------------------
async def test_promotion_rejects_cross_organization_student(client: AsyncClient) -> None:
    setup_a = await _setup_school(client, "promotenanta")
    setup_b = await _setup_school(client, "promotenantb")
    source_year = await _create_year(client, setup_a, "2026")
    target_year = await _create_year(client, setup_a, "2027")
    level = await _create_level(client, setup_a, "CM1")
    source_class = await _create_class(client, setup_a, source_year["id"], level["id"], "A")
    target_class = await _create_class(client, setup_a, target_year["id"], level["id"], "A")
    student_b = (await _students(client, setup_b, "TENANTB", 1))[0]

    response = await _promote(
        client, setup_a, source_year["id"], target_year["id"],
        [{"source_class_id": source_class["id"], "target_class_id": target_class["id"]}], [student_b["id"]],
    )
    # L'élève d'une autre organisation est invisible sous RLS : traité comme manquant (404).
    assert response.status_code == 404


async def test_promotion_requires_students_manage(client: AsyncClient) -> None:
    setup = await _setup_school(client, "promorbac")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level = await _create_level(client, setup, "CM1")
    source_class = await _create_class(client, setup, source_year["id"], level["id"], "A")
    target_class = await _create_class(client, setup, target_year["id"], level["id"], "A")
    student = (await _students(client, setup, "RBAC", 1))[0]
    await _enroll(client, setup, [student["id"]], source_year["id"], source_class["id"])

    teacher_data = await register_school(client, "promorbacteacher")
    await assign_role(
        teacher_data["user"]["id"], "TEACHER",
        organization_id=setup["organization_id"], school_id=setup["school_id"],
    )
    teacher_headers = {"Authorization": f"Bearer {await _login(client, teacher_data['user']['email'])}"}

    response = await client.post(
        "/api/v1/students/bulk-promotion",
        json={
            "source_academic_year_id": source_year["id"], "target_academic_year_id": target_year["id"],
            "class_mappings": [{"source_class_id": source_class["id"], "target_class_id": target_class["id"]}],
            "student_ids": [student["id"]], "enrollment_date": "2027-09-01",
        },
        headers=teacher_headers,
    )
    assert response.status_code == 403
    assert await _enrollments_for_year(student["id"], target_year["id"]) == []


# --- Atomicité / doublons / limites --------------------------------------------------------------------------
async def test_promotion_is_atomic_on_unknown_student_id(client: AsyncClient) -> None:
    setup = await _setup_school(client, "promoatomic")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level = await _create_level(client, setup, "CM1")
    source_class = await _create_class(client, setup, source_year["id"], level["id"], "A")
    target_class = await _create_class(client, setup, target_year["id"], level["id"], "A")
    students = await _students(client, setup, "ATOMIC", 5)
    await _enroll(client, setup, [s["id"] for s in students], source_year["id"], source_class["id"])
    ids = [s["id"] for s in students] + [str(uuid.uuid4())]

    response = await _promote(
        client, setup, source_year["id"], target_year["id"],
        [{"source_class_id": source_class["id"], "target_class_id": target_class["id"]}], ids,
    )
    assert response.status_code == 404
    for s in students:
        assert await _enrollments_for_year(s["id"], target_year["id"]) == []


async def test_promotion_deduplicates_repeated_student_ids(client: AsyncClient) -> None:
    setup = await _setup_school(client, "promodup")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level = await _create_level(client, setup, "CM1")
    source_class = await _create_class(client, setup, source_year["id"], level["id"], "A")
    target_class = await _create_class(client, setup, target_year["id"], level["id"], "A")
    student = (await _students(client, setup, "DUP", 1))[0]
    await _enroll(client, setup, [student["id"]], source_year["id"], source_class["id"])

    response = await _promote(
        client, setup, source_year["id"], target_year["id"],
        [{"source_class_id": source_class["id"], "target_class_id": target_class["id"]}],
        [student["id"], student["id"], student["id"]],
    )
    assert response.status_code == 200, response.text
    assert response.json()["selected_count"] == 1
    assert len(await _enrollments_for_year(student["id"], target_year["id"])) == 1


async def test_promotion_rejects_over_500_students(client: AsyncClient) -> None:
    setup = await _setup_school(client, "promolimit")
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level = await _create_level(client, setup, "CM1")
    source_class = await _create_class(client, setup, source_year["id"], level["id"], "A")
    target_class = await _create_class(client, setup, target_year["id"], level["id"], "A")
    too_many = [str(uuid.uuid4()) for _ in range(501)]

    response = await _promote(
        client, setup, source_year["id"], target_year["id"],
        [{"source_class_id": source_class["id"], "target_class_id": target_class["id"]}], too_many,
    )
    assert response.status_code == 422
