"""POST /api/v1/students/bulk-promotion — dispositions de sortie de l'établissement.

Une classe SOURCE sans correspondance dans class_mappings peut être déclarée explicitement en
"sortie de l'établissement" (exit_dispositions) plutôt que d'être silencieusement comptée comme
un élève oublié. Jamais de classe fictive créée ; l'inscription SOURCE n'est jamais modifiée.
"""

import asyncio
import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.students.models import StudentExit
from tests.conftest import assign_role, register_school
from tests.test_students import _login
from tests.test_students_bulk_promotion import (
    _create_class,
    _create_level,
    _create_year,
    _enroll,
    _enrollments_for_year,
    _setup_school,
    _students,
)


async def _promote(
    client: AsyncClient,
    setup: dict,
    source_year_id: str,
    target_year_id: str,
    class_mappings: list[dict],
    exit_dispositions: list[dict],
    student_ids: list[str],
    enrollment_date: str = "2027-09-01",
    dry_run: bool = False,
):
    return await client.post(
        f"/api/v1/students/bulk-promotion?dry_run={'true' if dry_run else 'false'}",
        json={
            "source_academic_year_id": source_year_id, "target_academic_year_id": target_year_id,
            "class_mappings": class_mappings, "exit_dispositions": exit_dispositions,
            "student_ids": student_ids, "enrollment_date": enrollment_date,
        },
        headers=setup["headers"],
    )


async def _exits_for_year(student_id: str, year_id: str) -> list[StudentExit]:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        result = await db.execute(
            select(StudentExit).where(
                StudentExit.student_id == uuid.UUID(student_id), StudentExit.academic_year_id == uuid.UUID(year_id)
            )
        )
        return list(result.scalars().all())


async def _setup_terminal_class(client: AsyncClient, prefix: str) -> dict:
    """Une école avec une seule classe SOURCE (terminale), aucune classe cible dans l'année
    suivante — exactement le cas CM2 sans correspondance."""
    setup = await _setup_school(client, prefix)
    source_year = await _create_year(client, setup, "2026")
    target_year = await _create_year(client, setup, "2027")
    level = await _create_level(client, setup, "CM2")
    source_class = await _create_class(client, setup, source_year["id"], level["id"], "CM2")
    return {**setup, "source_year": source_year, "target_year": target_year, "source_class": source_class}


# --- 1-4 : les quatre types de sortie --------------------------------------------------------------
async def test_exit_graduated(client: AsyncClient) -> None:
    ctx = await _setup_terminal_class(client, "exitgraduated")
    student = (await _students(client, ctx, "EXITGRAD", 1))[0]
    await _enroll(client, ctx, [student["id"]], ctx["source_year"]["id"], ctx["source_class"]["id"])

    response = await _promote(
        client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [],
        [{"source_class_id": ctx["source_class"]["id"], "exit_type": "GRADUATED", "reason": "Fin de cycle"}],
        [student["id"]],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["exit_count"] == 1
    assert body["exit_counts_by_type"] == {"GRADUATED": 1}

    exits = await _exits_for_year(student["id"], ctx["source_year"]["id"])
    assert len(exits) == 1
    assert exits[0].exit_type == "GRADUATED"
    assert exits[0].reason == "Fin de cycle"


async def test_exit_transferred(client: AsyncClient) -> None:
    ctx = await _setup_terminal_class(client, "exittransferred")
    student = (await _students(client, ctx, "EXITTRANS", 1))[0]
    await _enroll(client, ctx, [student["id"]], ctx["source_year"]["id"], ctx["source_class"]["id"])

    response = await _promote(
        client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [],
        [{"source_class_id": ctx["source_class"]["id"], "exit_type": "TRANSFERRED"}], [student["id"]],
    )
    assert response.status_code == 200, response.text
    assert response.json()["exit_counts_by_type"] == {"TRANSFERRED": 1}
    assert (await _exits_for_year(student["id"], ctx["source_year"]["id"]))[0].exit_type == "TRANSFERRED"


async def test_exit_withdrawn(client: AsyncClient) -> None:
    ctx = await _setup_terminal_class(client, "exitwithdrawn")
    student = (await _students(client, ctx, "EXITWITH", 1))[0]
    await _enroll(client, ctx, [student["id"]], ctx["source_year"]["id"], ctx["source_class"]["id"])

    response = await _promote(
        client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [],
        [{"source_class_id": ctx["source_class"]["id"], "exit_type": "WITHDRAWN"}], [student["id"]],
    )
    assert response.status_code == 200, response.text
    assert response.json()["exit_counts_by_type"] == {"WITHDRAWN": 1}
    assert (await _exits_for_year(student["id"], ctx["source_year"]["id"]))[0].exit_type == "WITHDRAWN"


async def test_exit_other(client: AsyncClient) -> None:
    ctx = await _setup_terminal_class(client, "exitother")
    student = (await _students(client, ctx, "EXITOTHER", 1))[0]
    await _enroll(client, ctx, [student["id"]], ctx["source_year"]["id"], ctx["source_class"]["id"])

    response = await _promote(
        client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [],
        [{"source_class_id": ctx["source_class"]["id"], "exit_type": "OTHER", "reason": "Déménagement"}],
        [student["id"]],
    )
    assert response.status_code == 200, response.text
    assert response.json()["exit_counts_by_type"] == {"OTHER": 1}


# --- 5-6 : aucune inscription cible, inscription source intacte -------------------------------------
async def test_exit_creates_no_target_enrollment(client: AsyncClient) -> None:
    ctx = await _setup_terminal_class(client, "exitnotarget")
    student = (await _students(client, ctx, "EXITNOTARGET", 1))[0]
    await _enroll(client, ctx, [student["id"]], ctx["source_year"]["id"], ctx["source_class"]["id"])

    await _promote(
        client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [],
        [{"source_class_id": ctx["source_class"]["id"], "exit_type": "GRADUATED"}], [student["id"]],
    )
    assert await _enrollments_for_year(student["id"], ctx["target_year"]["id"]) == []


async def test_exit_preserves_source_enrollment(client: AsyncClient) -> None:
    ctx = await _setup_terminal_class(client, "exitsourceintact")
    student = (await _students(client, ctx, "EXITSOURCE", 1))[0]
    await _enroll(client, ctx, [student["id"]], ctx["source_year"]["id"], ctx["source_class"]["id"])
    before = await _enrollments_for_year(student["id"], ctx["source_year"]["id"])
    assert len(before) == 1
    source_enrollment_id = before[0].id

    await _promote(
        client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [],
        [{"source_class_id": ctx["source_class"]["id"], "exit_type": "GRADUATED"}], [student["id"]],
    )

    after = await _enrollments_for_year(student["id"], ctx["source_year"]["id"])
    assert len(after) == 1
    assert after[0].id == source_enrollment_id
    assert str(after[0].class_id) == ctx["source_class"]["id"]
    assert after[0].status == "ACTIVE"


# --- 7-8 : dry_run --------------------------------------------------------------------------------
async def test_exit_dry_run_creates_nothing(client: AsyncClient) -> None:
    ctx = await _setup_terminal_class(client, "exitdry")
    student = (await _students(client, ctx, "EXITDRY", 1))[0]
    await _enroll(client, ctx, [student["id"]], ctx["source_year"]["id"], ctx["source_class"]["id"])

    response = await _promote(
        client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [],
        [{"source_class_id": ctx["source_class"]["id"], "exit_type": "GRADUATED"}], [student["id"]], dry_run=True,
    )
    assert response.status_code == 200, response.text
    assert response.json()["exit_count"] == 1  # 8 : le compte est correct même sans mutation
    assert await _exits_for_year(student["id"], ctx["source_year"]["id"]) == []  # 7 : rien créé


# --- 9 : doublon StudentExit non créé ---------------------------------------------------------------
async def test_exit_does_not_duplicate_existing_studentexit(client: AsyncClient) -> None:
    ctx = await _setup_terminal_class(client, "exitnodup")
    student = (await _students(client, ctx, "EXITNODUP", 1))[0]
    await _enroll(client, ctx, [student["id"]], ctx["source_year"]["id"], ctx["source_class"]["id"])
    dispositions = [{"source_class_id": ctx["source_class"]["id"], "exit_type": "GRADUATED"}]

    first = await _promote(client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [], dispositions, [student["id"]])
    assert first.status_code == 200, first.text
    second = await _promote(client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [], dispositions, [student["id"]])
    assert second.status_code == 200, second.text
    assert second.json()["exit_count"] == 1  # reconnu comme déjà traité, pas d'erreur

    exits = await _exits_for_year(student["id"], ctx["source_year"]["id"])
    assert len(exits) == 1  # jamais de doublon


# --- 10-11 : non traité / confirmation bloquée -------------------------------------------------------
async def test_unmapped_class_without_disposition_is_unprocessed(client: AsyncClient) -> None:
    ctx = await _setup_terminal_class(client, "exitunprocessed")
    student = (await _students(client, ctx, "UNPROCESSED", 1))[0]
    await _enroll(client, ctx, [student["id"]], ctx["source_year"]["id"], ctx["source_class"]["id"])

    response = await _promote(
        client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [], [], [student["id"]], dry_run=True,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["unprocessed_no_target_class_count"] == 1
    assert body["exit_count"] == 0
    assert body["no_target_class_count"] == 1


async def test_confirmation_blocked_when_unprocessed_students_remain(client: AsyncClient) -> None:
    ctx = await _setup_terminal_class(client, "exitblocked")
    student = (await _students(client, ctx, "BLOCKED", 1))[0]
    await _enroll(client, ctx, [student["id"]], ctx["source_year"]["id"], ctx["source_class"]["id"])

    response = await _promote(
        client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [], [], [student["id"]], dry_run=False,
    )
    assert response.status_code == 409, response.text
    assert await _enrollments_for_year(student["id"], ctx["target_year"]["id"]) == []
    assert await _exits_for_year(student["id"], ctx["source_year"]["id"]) == []


# --- 12 : déjà inscrit jamais transformé en sortant --------------------------------------------------
async def test_already_enrolled_student_never_becomes_exit(client: AsyncClient) -> None:
    ctx = await _setup_terminal_class(client, "exitalreadyenrolled")
    other_target_class = await _create_class(
        client, ctx, ctx["target_year"]["id"],
        (await _create_level(client, ctx, "CM2-bis"))["id"], "CM2-bis",
    )
    student = (await _students(client, ctx, "ALREADYEXIT", 1))[0]
    await _enroll(client, ctx, [student["id"]], ctx["source_year"]["id"], ctx["source_class"]["id"])
    await _enroll(client, ctx, [student["id"]], ctx["target_year"]["id"], other_target_class["id"])

    response = await _promote(
        client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [],
        [{"source_class_id": ctx["source_class"]["id"], "exit_type": "GRADUATED"}], [student["id"]],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["already_enrolled_count"] == 1
    assert body["exit_count"] == 0
    assert await _exits_for_year(student["id"], ctx["source_year"]["id"]) == []


# --- 13-14 : tenant / RBAC ---------------------------------------------------------------------------
async def test_exit_rejects_cross_organization_student(client: AsyncClient) -> None:
    ctx = await _setup_terminal_class(client, "exittenanta")
    other = await _setup_school(client, "exittenantb")
    other_student = (await _students(client, other, "TENANTB", 1))[0]

    response = await _promote(
        client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [],
        [{"source_class_id": ctx["source_class"]["id"], "exit_type": "GRADUATED"}], [other_student["id"]],
    )
    assert response.status_code == 404


async def test_exit_requires_students_manage(client: AsyncClient) -> None:
    ctx = await _setup_terminal_class(client, "exitrbac")
    student = (await _students(client, ctx, "EXITRBAC", 1))[0]
    await _enroll(client, ctx, [student["id"]], ctx["source_year"]["id"], ctx["source_class"]["id"])

    teacher_data = await register_school(client, "exitrbacteacher")
    await assign_role(
        teacher_data["user"]["id"], "TEACHER",
        organization_id=ctx["organization_id"], school_id=ctx["school_id"],
    )
    teacher_headers = {"Authorization": f"Bearer {await _login(client, teacher_data['user']['email'])}"}

    response = await client.post(
        "/api/v1/students/bulk-promotion",
        json={
            "source_academic_year_id": ctx["source_year"]["id"], "target_academic_year_id": ctx["target_year"]["id"],
            "class_mappings": [],
            "exit_dispositions": [{"source_class_id": ctx["source_class"]["id"], "exit_type": "GRADUATED"}],
            "student_ids": [student["id"]], "enrollment_date": "2027-09-01",
        },
        headers=teacher_headers,
    )
    assert response.status_code == 403
    assert await _exits_for_year(student["id"], ctx["source_year"]["id"]) == []


# --- 15-16 : atomicité / mélange de catégories ---------------------------------------------------------
async def test_exit_mixed_with_promoted_repeated_already_enrolled_and_unprocessed(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "exitmixed")
    source_year = await _create_year(client, ctx, "2026")
    target_year = await _create_year(client, ctx, "2027")
    level_cm1 = await _create_level(client, ctx, "CM1")
    level_cm2 = await _create_level(client, ctx, "CM2")
    level_cp = await _create_level(client, ctx, "CP")

    cm1_source = await _create_class(client, ctx, source_year["id"], level_cm1["id"], "CM1")
    cm2_target = await _create_class(client, ctx, target_year["id"], level_cm2["id"], "CM2")
    cm2_source_terminal = await _create_class(client, ctx, source_year["id"], level_cm2["id"], "CM2-term")
    cp_source_repeat = await _create_class(client, ctx, source_year["id"], level_cp["id"], "CP")
    cp_target_repeat = await _create_class(client, ctx, target_year["id"], level_cp["id"], "CP-bis")
    unprocessed_source = await _create_class(client, ctx, source_year["id"], level_cm1["id"], "CM1-unprocessed")
    already_target_class = await _create_class(client, ctx, target_year["id"], level_cm1["id"], "CM1-already")

    promoted_student, repeated_student, exit_student, already_student, unprocessed_student = await _students(
        client, ctx, "MIXEXIT", 5
    )
    await _enroll(client, ctx, [promoted_student["id"]], source_year["id"], cm1_source["id"])
    await _enroll(client, ctx, [repeated_student["id"]], source_year["id"], cp_source_repeat["id"])
    await _enroll(client, ctx, [exit_student["id"]], source_year["id"], cm2_source_terminal["id"])
    await _enroll(client, ctx, [already_student["id"]], source_year["id"], cm1_source["id"])
    await _enroll(client, ctx, [already_student["id"]], target_year["id"], already_target_class["id"])
    await _enroll(client, ctx, [unprocessed_student["id"]], source_year["id"], unprocessed_source["id"])

    response = await _promote(
        client, ctx, source_year["id"], target_year["id"],
        [
            {"source_class_id": cm1_source["id"], "target_class_id": cm2_target["id"]},
            {"source_class_id": cp_source_repeat["id"], "target_class_id": cp_target_repeat["id"]},
        ],
        [{"source_class_id": cm2_source_terminal["id"], "exit_type": "GRADUATED"}],
        [s["id"] for s in [promoted_student, repeated_student, exit_student, already_student, unprocessed_student]],
        dry_run=True,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["selected_count"] == 5
    assert body["promoted_count"] == 1
    assert body["repeated_count"] == 1
    assert body["already_enrolled_count"] == 1
    assert body["exit_count"] == 1
    assert body["unprocessed_no_target_class_count"] == 1
    assert body["no_target_class_count"] == 2  # exit_count + unprocessed_no_target_class_count


async def test_exit_operation_is_atomic_on_unknown_student_id(client: AsyncClient) -> None:
    ctx = await _setup_terminal_class(client, "exitatomic")
    student = (await _students(client, ctx, "EXITATOMIC", 1))[0]
    await _enroll(client, ctx, [student["id"]], ctx["source_year"]["id"], ctx["source_class"]["id"])

    response = await _promote(
        client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [],
        [{"source_class_id": ctx["source_class"]["id"], "exit_type": "GRADUATED"}],
        [student["id"], str(uuid.uuid4())],
    )
    assert response.status_code == 404
    assert await _exits_for_year(student["id"], ctx["source_year"]["id"]) == []


# --- 17 : capacité insuffisante -> aucune mutation, aucun StudentExit --------------------------------
async def test_exit_capacity_insufficient_creates_no_exit(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "exitcapacity")
    source_year = await _create_year(client, ctx, "2026")
    target_year = await _create_year(client, ctx, "2027")
    level_a = await _create_level(client, ctx, "CM1")
    level_b = await _create_level(client, ctx, "CM2")
    level_term = await _create_level(client, ctx, "CM2-term")
    source_class = await _create_class(client, ctx, source_year["id"], level_a["id"], "CM1")
    target_class = await _create_class(client, ctx, target_year["id"], level_b["id"], "CM2", capacity=1)
    terminal_class = await _create_class(client, ctx, source_year["id"], level_term["id"], "CM2-term")

    students = await _students(client, ctx, "EXITCAP", 3)
    await _enroll(client, ctx, [s["id"] for s in students], source_year["id"], source_class["id"])
    exit_student = (await _students(client, ctx, "EXITCAPGRAD", 1))[0]
    await _enroll(client, ctx, [exit_student["id"]], source_year["id"], terminal_class["id"])

    response = await _promote(
        client, ctx, source_year["id"], target_year["id"],
        [{"source_class_id": source_class["id"], "target_class_id": target_class["id"]}],
        [{"source_class_id": terminal_class["id"], "exit_type": "GRADUATED"}],
        [s["id"] for s in students] + [exit_student["id"]],
    )
    assert response.status_code == 409, response.text
    for s in students:
        assert await _enrollments_for_year(s["id"], target_year["id"]) == []
    assert await _exits_for_year(exit_student["id"], source_year["id"]) == []


# --- 18 : UNIQUE(student_id, academic_year_id) sur StudentExit ----------------------------------------
async def test_studentexit_unique_constraint_per_student_and_year(client: AsyncClient) -> None:
    ctx = await _setup_terminal_class(client, "exitunique")
    student = (await _students(client, ctx, "EXITUNIQUE", 1))[0]
    await _enroll(client, ctx, [student["id"]], ctx["source_year"]["id"], ctx["source_class"]["id"])

    await _promote(
        client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [],
        [{"source_class_id": ctx["source_class"]["id"], "exit_type": "GRADUATED"}], [student["id"]],
    )
    exits = await _exits_for_year(student["id"], ctx["source_year"]["id"])
    assert len(exits) == 1

    # Re-déclencher la même disposition pour le même élève/année ne doit jamais créer de doublon
    # (contrainte UNIQUE respectée, voir test_exit_does_not_duplicate_existing_studentexit) — ici
    # on vérifie en plus la robustesse sous concurrence (deux requêtes simultanées).
    results = await asyncio.gather(
        _promote(
            client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [],
            [{"source_class_id": ctx["source_class"]["id"], "exit_type": "GRADUATED"}], [student["id"]],
        ),
        _promote(
            client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [],
            [{"source_class_id": ctx["source_class"]["id"], "exit_type": "GRADUATED"}], [student["id"]],
        ),
    )
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert len(await _exits_for_year(student["id"], ctx["source_year"]["id"])) == 1


# --- Endpoints de lecture --------------------------------------------------------------------------
async def test_list_student_exits_endpoint(client: AsyncClient) -> None:
    ctx = await _setup_terminal_class(client, "exitreadstudent")
    student = (await _students(client, ctx, "EXITREAD", 1))[0]
    await _enroll(client, ctx, [student["id"]], ctx["source_year"]["id"], ctx["source_class"]["id"])
    await _promote(
        client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [],
        [{"source_class_id": ctx["source_class"]["id"], "exit_type": "GRADUATED", "reason": "Fin de cycle"}],
        [student["id"]],
    )

    response = await client.get(f"/api/v1/students/{student['id']}/exits", headers=ctx["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["exit_type"] == "GRADUATED"
    assert body[0]["reason"] == "Fin de cycle"
    assert body[0]["created_by"] is not None


async def test_list_school_student_exits_endpoint_tenant_isolation(client: AsyncClient) -> None:
    ctx = await _setup_terminal_class(client, "exitreadschoola")
    other = await _setup_school(client, "exitreadschoolb")
    student = (await _students(client, ctx, "EXITREADSCHOOL", 1))[0]
    await _enroll(client, ctx, [student["id"]], ctx["source_year"]["id"], ctx["source_class"]["id"])
    await _promote(
        client, ctx, ctx["source_year"]["id"], ctx["target_year"]["id"], [],
        [{"source_class_id": ctx["source_class"]["id"], "exit_type": "WITHDRAWN"}], [student["id"]],
    )

    own = await client.get(f"/api/v1/student-exits?school_id={ctx['school_id']}", headers=ctx["headers"])
    assert own.status_code == 200, own.text
    assert len(own.json()) == 1

    # Un utilisateur d'une AUTRE école ne doit jamais voir ces sorties (ni via son propre
    # school_id, trivialement vide, ni en forçant le school_id de ctx — RLS l'en empêche).
    cross = await client.get(f"/api/v1/student-exits?school_id={ctx['school_id']}", headers=other["headers"])
    assert cross.status_code == 404
