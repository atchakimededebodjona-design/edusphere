import uuid
from datetime import date

import pytest
from httpx import AsyncClient

from tests.conftest import assign_role, register_school


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


async def _setup_class_with_students(client: AsyncClient, headers: dict, school_id: str, n_students: int = 2) -> dict:
    """Année scolaire + période + niveau + classe + matière (nécessaire pour affecter un
    enseignant via TeacherAssignment) + élèves inscrits. Retourne tout ce qu'il faut pour les
    tests de présence.

    Suffixe unique sur les noms/matricules contraints par UniqueConstraint(school_id, ...) — permet
    d'appeler ce helper plusieurs fois pour la MÊME école (ex. tester deux classes distinctes d'une
    même école), ce qu'aucun test existant (`test_grades.py`) n'avait besoin de faire jusqu'ici."""
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
    term = (
        await client.post(
            "/api/v1/academic-terms",
            json={
                "academic_year_id": year["id"],
                "name": "Trimestre 1",
                "start_date": str(date(2026, 9, 1)),
                "end_date": str(date(2026, 12, 20)),
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

    subject = (
        await client.post("/api/v1/subjects", json={"school_id": school_id, "name": f"Mathématiques-{suffix}"}, headers=headers)
    ).json()
    class_subject = (
        await client.post(
            f"/api/v1/classes/{school_class['id']}/subjects",
            json={"subject_id": subject["id"], "coefficient": 1},
            headers=headers,
        )
    ).json()

    students = []
    for i in range(n_students):
        student = (
            await client.post(
                "/api/v1/students",
                json={
                    "school_id": school_id,
                    "matricule": f"S{suffix}{i:03d}",
                    "first_name": f"Student{i}",
                    "last_name": "Test",
                    "date_of_birth": str(date(2015, 1, 1)),
                    "sex": "M" if i % 2 == 0 else "F",
                },
                headers=headers,
            )
        ).json()
        await client.post(
            f"/api/v1/students/{student['id']}/enrollments",
            json={"class_id": school_class["id"], "enrollment_date": str(date(2026, 9, 1))},
            headers=headers,
        )
        students.append(student)

    return {
        "year": year,
        "term": term,
        "level": level,
        "class": school_class,
        "subject": subject,
        "class_subject": class_subject,
        "students": students,
    }


async def _create_session(client: AsyncClient, headers: dict, ctx: dict, session_date: date) -> dict:
    response = await client.post(
        "/api/v1/attendance-sessions",
        json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "session_date": str(session_date)},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- Création de présences/absences/retards -------------------------------------
async def test_create_present_record(client: AsyncClient) -> None:
    data = await register_school(client, "attpresent")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_class_with_students(client, headers, data["school"]["id"])
    session = await _create_session(client, headers, ctx, date(2026, 10, 1))

    response = await client.post(
        "/api/v1/attendance-records",
        json={"session_id": session["id"], "records": [{"student_id": ctx["students"][0]["id"], "status": "PRESENT"}]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    record = response.json()[0]
    assert record["status"] == "PRESENT"
    assert record["justified"] is False
    assert record["reason"] is None


async def test_create_absent_record_with_justification_and_reason(client: AsyncClient) -> None:
    data = await register_school(client, "attabsent")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_class_with_students(client, headers, data["school"]["id"])
    session = await _create_session(client, headers, ctx, date(2026, 10, 1))

    response = await client.post(
        "/api/v1/attendance-records",
        json={
            "session_id": session["id"],
            "records": [
                {
                    "student_id": ctx["students"][0]["id"],
                    "status": "ABSENT",
                    "justified": True,
                    "reason": "Certificat médical",
                }
            ],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    record = response.json()[0]
    assert record["status"] == "ABSENT"
    assert record["justified"] is True
    assert record["reason"] == "Certificat médical"


async def test_create_absent_record_without_reason_is_valid(client: AsyncClient) -> None:
    data = await register_school(client, "attabsentnoreason")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_class_with_students(client, headers, data["school"]["id"])
    session = await _create_session(client, headers, ctx, date(2026, 10, 1))

    response = await client.post(
        "/api/v1/attendance-records",
        json={"session_id": session["id"], "records": [{"student_id": ctx["students"][0]["id"], "status": "ABSENT"}]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    record = response.json()[0]
    assert record["justified"] is False
    assert record["reason"] is None


async def test_create_late_record(client: AsyncClient) -> None:
    data = await register_school(client, "attlate")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_class_with_students(client, headers, data["school"]["id"])
    session = await _create_session(client, headers, ctx, date(2026, 10, 1))

    response = await client.post(
        "/api/v1/attendance-records",
        json={"session_id": session["id"], "records": [{"student_id": ctx["students"][0]["id"], "status": "LATE"}]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()[0]["status"] == "LATE"


# --- Idempotence / doublon ---------------------------------------------------------
async def test_submitting_twice_upserts_without_duplicate(client: AsyncClient) -> None:
    data = await register_school(client, "attupsert")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_class_with_students(client, headers, data["school"]["id"])
    session = await _create_session(client, headers, ctx, date(2026, 10, 1))
    student_id = ctx["students"][0]["id"]

    first = await client.post(
        "/api/v1/attendance-records",
        json={"session_id": session["id"], "records": [{"student_id": student_id, "status": "ABSENT"}]},
        headers=headers,
    )
    assert first.status_code == 201
    first_record_id = first.json()[0]["id"]

    # Même soumission, statut différent : doit mettre à jour la même ligne, pas en créer une seconde.
    second = await client.post(
        "/api/v1/attendance-records",
        json={"session_id": session["id"], "records": [{"student_id": student_id, "status": "PRESENT"}]},
        headers=headers,
    )
    assert second.status_code == 201
    second_record_id = second.json()[0]["id"]
    assert second_record_id == first_record_id
    assert second.json()[0]["status"] == "PRESENT"

    # Répétition exacte de la même opération (mode offline : renvoi après reconnexion) : aucun
    # nouvel enregistrement, même id, même état.
    third = await client.post(
        "/api/v1/attendance-records",
        json={"session_id": session["id"], "records": [{"student_id": student_id, "status": "PRESENT"}]},
        headers=headers,
    )
    assert third.status_code == 201
    assert third.json()[0]["id"] == first_record_id

    listing = await client.get(f"/api/v1/attendance-records?session_id={session['id']}", headers=headers)
    matching = [r for r in listing.json() if r["student_id"] == student_id]
    assert len(matching) == 1


# --- Permissions / RBAC -------------------------------------------------------------
async def test_staff_cannot_write_attendance(client: AsyncClient) -> None:
    data = await register_school(client, "attstaff")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_class_with_students(client, headers_admin, data["school"]["id"])
    session = await _create_session(client, headers_admin, ctx, date(2026, 10, 1))

    staff_data = await register_school(client, "attstaff-staff")
    await assign_role(
        staff_data["user"]["id"], "STAFF", organization_id=data["organization"]["id"], school_id=data["school"]["id"]
    )
    headers_staff = {"Authorization": f"Bearer {await _login(client, staff_data['user']['email'])}"}

    response = await client.post(
        "/api/v1/attendance-records",
        json={"session_id": session["id"], "records": [{"student_id": ctx["students"][0]["id"], "status": "PRESENT"}]},
        headers=headers_staff,
    )
    assert response.status_code == 403


# --- TeacherAssignment (scoping enseignant) -----------------------------------------
async def test_teacher_assigned_to_class_can_take_attendance(client: AsyncClient) -> None:
    data = await register_school(client, "attteacherok")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    organization_id = data["organization"]["id"]
    ctx = await _setup_class_with_students(client, headers_admin, school_id)

    teacher_data = await register_school(client, "attteacherok-teacher")
    teacher_user_id = teacher_data["user"]["id"]
    await assign_role(teacher_user_id, "TEACHER", organization_id=organization_id, school_id=school_id)
    assign_response = await client.post(
        f"/api/v1/classes/{ctx['class']['id']}/teachers",
        json={"user_id": teacher_user_id, "subject_id": ctx["subject"]["id"]},
        headers=headers_admin,
    )
    assert assign_response.status_code == 201

    headers_teacher = {"Authorization": f"Bearer {await _login(client, teacher_data['user']['email'])}"}
    response = await client.post(
        "/api/v1/attendance-sessions",
        json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "session_date": str(date(2026, 10, 1))},
        headers=headers_teacher,
    )
    assert response.status_code == 201, response.text


async def test_teacher_not_assigned_to_class_cannot_take_attendance(client: AsyncClient) -> None:
    data = await register_school(client, "attteacherko")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    organization_id = data["organization"]["id"]
    ctx = await _setup_class_with_students(client, headers_admin, school_id)

    teacher_data = await register_school(client, "attteacherko-teacher")
    teacher_user_id = teacher_data["user"]["id"]
    # Rôle TEACHER attribué à l'école, mais aucune TeacherAssignment sur une matière de la classe.
    await assign_role(teacher_user_id, "TEACHER", organization_id=organization_id, school_id=school_id)

    headers_teacher = {"Authorization": f"Bearer {await _login(client, teacher_data['user']['email'])}"}
    response = await client.post(
        "/api/v1/attendance-sessions",
        json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "session_date": str(date(2026, 10, 1))},
        headers=headers_teacher,
    )
    assert response.status_code == 403


# --- Tenant isolation ----------------------------------------------------------------
async def test_cross_tenant_cannot_read_or_write_session(client: AsyncClient) -> None:
    school_a = await register_school(client, "attisoa")
    school_b = await register_school(client, "attisob")
    headers_a = {"Authorization": f"Bearer {await _login(client, school_a['user']['email'])}"}
    headers_b = {"Authorization": f"Bearer {await _login(client, school_b['user']['email'])}"}

    ctx_b = await _setup_class_with_students(client, headers_b, school_b["school"]["id"])
    session_b = await _create_session(client, headers_b, ctx_b, date(2026, 10, 1))

    read_response = await client.get(f"/api/v1/attendance-sessions/{session_b['id']}", headers=headers_a)
    assert read_response.status_code in (403, 404)

    write_response = await client.post(
        "/api/v1/attendance-records",
        json={"session_id": session_b["id"], "records": [{"student_id": ctx_b["students"][0]["id"], "status": "PRESENT"}]},
        headers=headers_a,
    )
    assert write_response.status_code in (403, 404)

    # Forger le class_id de B dans le corps de la requête de création de session ne fonctionne pas
    # non plus : la classe de B est invisible pour A (RLS + permission scopée).
    forged_session_response = await client.post(
        "/api/v1/attendance-sessions",
        json={"class_id": ctx_b["class"]["id"], "academic_term_id": ctx_b["term"]["id"], "session_date": str(date(2026, 10, 1))},
        headers=headers_a,
    )
    assert forged_session_response.status_code in (403, 404)


# --- Élève hors périmètre (école / classe) --------------------------------------------
async def test_student_from_another_school_rejected(client: AsyncClient) -> None:
    school_a = await register_school(client, "attstudentschoola")
    school_b = await register_school(client, "attstudentschoolb")
    headers_a = {"Authorization": f"Bearer {await _login(client, school_a['user']['email'])}"}
    headers_b = {"Authorization": f"Bearer {await _login(client, school_b['user']['email'])}"}

    ctx_a = await _setup_class_with_students(client, headers_a, school_a["school"]["id"])
    ctx_b = await _setup_class_with_students(client, headers_b, school_b["school"]["id"])
    session_a = await _create_session(client, headers_a, ctx_a, date(2026, 10, 1))

    response = await client.post(
        "/api/v1/attendance-records",
        json={"session_id": session_a["id"], "records": [{"student_id": ctx_b["students"][0]["id"], "status": "PRESENT"}]},
        headers=headers_a,
    )
    assert response.status_code == 404


async def test_student_from_another_class_same_school_rejected(client: AsyncClient) -> None:
    data = await register_school(client, "attstudentclass")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    ctx = await _setup_class_with_students(client, headers, school_id)
    session = await _create_session(client, headers, ctx, date(2026, 10, 1))

    # Élève inscrit dans une AUTRE classe de la même école.
    other_ctx = await _setup_class_with_students(client, headers, school_id, n_students=1)

    response = await client.post(
        "/api/v1/attendance-records",
        json={"session_id": session["id"], "records": [{"student_id": other_ctx["students"][0]["id"], "status": "PRESENT"}]},
        headers=headers,
    )
    assert response.status_code == 404


# --- Dates / période académique -------------------------------------------------------
async def test_session_date_within_term_accepted(client: AsyncClient) -> None:
    data = await register_school(client, "attdatein")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_class_with_students(client, headers, data["school"]["id"])

    response = await client.post(
        "/api/v1/attendance-sessions",
        json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "session_date": str(date(2026, 10, 15))},
        headers=headers,
    )
    assert response.status_code == 201


async def test_session_date_outside_term_rejected(client: AsyncClient) -> None:
    data = await register_school(client, "attdateout")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_class_with_students(client, headers, data["school"]["id"])

    response = await client.post(
        "/api/v1/attendance-sessions",
        json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "session_date": str(date(2027, 1, 15))},
        headers=headers,
    )
    assert response.status_code == 400


async def test_future_session_date_within_term_is_allowed(client: AsyncClient) -> None:
    """Décision validée : une date future est autorisée tant qu'elle appartient à la période
    académique concernée — pas de blocage sur la date du jour."""
    data = await register_school(client, "attdatefuture")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_class_with_students(client, headers, data["school"]["id"])

    # 2026-12-15 est postérieur à la date réelle d'exécution des tests, et reste dans le
    # trimestre (2026-09-01 -> 2026-12-20).
    response = await client.post(
        "/api/v1/attendance-sessions",
        json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "session_date": str(date(2026, 12, 15))},
        headers=headers,
    )
    assert response.status_code == 201


# --- Statistiques ----------------------------------------------------------------------
async def test_student_attendance_summary_and_rate(client: AsyncClient) -> None:
    data = await register_school(client, "attsummary")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_class_with_students(client, headers, data["school"]["id"], n_students=1)
    student_id = ctx["students"][0]["id"]

    session1 = await _create_session(client, headers, ctx, date(2026, 10, 1))
    session2 = await _create_session(client, headers, ctx, date(2026, 10, 2))
    session3 = await _create_session(client, headers, ctx, date(2026, 10, 3))

    await client.post(
        "/api/v1/attendance-records",
        json={"session_id": session1["id"], "records": [{"student_id": student_id, "status": "PRESENT"}]},
        headers=headers,
    )
    await client.post(
        "/api/v1/attendance-records",
        json={
            "session_id": session2["id"],
            "records": [{"student_id": student_id, "status": "ABSENT", "justified": True, "reason": "Maladie"}],
        },
        headers=headers,
    )
    await client.post(
        "/api/v1/attendance-records",
        json={"session_id": session3["id"], "records": [{"student_id": student_id, "status": "LATE"}]},
        headers=headers,
    )

    response = await client.get(
        f"/api/v1/students/{student_id}/attendance-summary?academic_term_id={ctx['term']['id']}", headers=headers
    )
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["total_sessions"] == 3
    assert summary["present_count"] == 1
    assert summary["absent_count"] == 1
    assert summary["late_count"] == 1
    assert summary["justified_absence_count"] == 1
    # (présents + retards) / total × 100 = (1 + 1) / 3 × 100
    assert summary["attendance_rate"] == pytest.approx(66.67, abs=0.01)


async def test_class_attendance_statistics(client: AsyncClient) -> None:
    data = await register_school(client, "attclassstats")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_class_with_students(client, headers, data["school"]["id"], n_students=2)
    session = await _create_session(client, headers, ctx, date(2026, 10, 1))

    await client.post(
        "/api/v1/attendance-records",
        json={
            "session_id": session["id"],
            "records": [
                {"student_id": ctx["students"][0]["id"], "status": "PRESENT"},
                {"student_id": ctx["students"][1]["id"], "status": "ABSENT"},
            ],
        },
        headers=headers,
    )

    response = await client.get(
        f"/api/v1/classes/{ctx['class']['id']}/attendance-statistics?academic_term_id={ctx['term']['id']}", headers=headers
    )
    assert response.status_code == 200, response.text
    students_stats = response.json()["students"]
    assert len(students_stats) == 2
    present_entry = next(s for s in students_stats if s["student_id"] == ctx["students"][0]["id"])
    absent_entry = next(s for s in students_stats if s["student_id"] == ctx["students"][1]["id"])
    assert present_entry["present_count"] == 1
    assert absent_entry["absent_count"] == 1


# --- Verrouillage ----------------------------------------------------------------------
async def test_locked_session_blocks_teacher_write(client: AsyncClient) -> None:
    data = await register_school(client, "attlockteacher")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    organization_id = data["organization"]["id"]
    ctx = await _setup_class_with_students(client, headers_admin, school_id)
    session = await _create_session(client, headers_admin, ctx, date(2026, 10, 1))

    teacher_data = await register_school(client, "attlockteacher-teacher")
    teacher_user_id = teacher_data["user"]["id"]
    await assign_role(teacher_user_id, "TEACHER", organization_id=organization_id, school_id=school_id)
    await client.post(
        f"/api/v1/classes/{ctx['class']['id']}/teachers",
        json={"user_id": teacher_user_id, "subject_id": ctx["subject"]["id"]},
        headers=headers_admin,
    )
    headers_teacher = {"Authorization": f"Bearer {await _login(client, teacher_data['user']['email'])}"}

    lock_response = await client.patch(f"/api/v1/attendance-sessions/{session['id']}", json={"locked": True}, headers=headers_admin)
    assert lock_response.status_code == 200
    assert lock_response.json()["locked"] is True

    write_response = await client.post(
        "/api/v1/attendance-records",
        json={"session_id": session["id"], "records": [{"student_id": ctx["students"][0]["id"], "status": "PRESENT"}]},
        headers=headers_teacher,
    )
    assert write_response.status_code == 403


async def test_admin_can_write_locked_session(client: AsyncClient) -> None:
    data = await register_school(client, "attlockadmin")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_class_with_students(client, headers_admin, data["school"]["id"])
    session = await _create_session(client, headers_admin, ctx, date(2026, 10, 1))

    await client.patch(f"/api/v1/attendance-sessions/{session['id']}", json={"locked": True}, headers=headers_admin)

    write_response = await client.post(
        "/api/v1/attendance-records",
        json={"session_id": session["id"], "records": [{"student_id": ctx["students"][0]["id"], "status": "PRESENT"}]},
        headers=headers_admin,
    )
    assert write_response.status_code == 201


async def test_teacher_cannot_unlock_session(client: AsyncClient) -> None:
    data = await register_school(client, "attunlockteacher")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    organization_id = data["organization"]["id"]
    ctx = await _setup_class_with_students(client, headers_admin, school_id)
    session = await _create_session(client, headers_admin, ctx, date(2026, 10, 1))
    await client.patch(f"/api/v1/attendance-sessions/{session['id']}", json={"locked": True}, headers=headers_admin)

    teacher_data = await register_school(client, "attunlockteacher-teacher")
    teacher_user_id = teacher_data["user"]["id"]
    await assign_role(teacher_user_id, "TEACHER", organization_id=organization_id, school_id=school_id)
    await client.post(
        f"/api/v1/classes/{ctx['class']['id']}/teachers",
        json={"user_id": teacher_user_id, "subject_id": ctx["subject"]["id"]},
        headers=headers_admin,
    )
    headers_teacher = {"Authorization": f"Bearer {await _login(client, teacher_data['user']['email'])}"}

    unlock_response = await client.patch(
        f"/api/v1/attendance-sessions/{session['id']}", json={"locked": False}, headers=headers_teacher
    )
    assert unlock_response.status_code == 403


async def test_school_admin_can_unlock_session(client: AsyncClient) -> None:
    data = await register_school(client, "attunlockadmin")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_class_with_students(client, headers_admin, data["school"]["id"])
    session = await _create_session(client, headers_admin, ctx, date(2026, 10, 1))
    await client.patch(f"/api/v1/attendance-sessions/{session['id']}", json={"locked": True}, headers=headers_admin)

    unlock_response = await client.patch(
        f"/api/v1/attendance-sessions/{session['id']}", json={"locked": False}, headers=headers_admin
    )
    assert unlock_response.status_code == 200
    assert unlock_response.json()["locked"] is False
