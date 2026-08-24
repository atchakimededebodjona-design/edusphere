from datetime import date

import pytest
from httpx import AsyncClient

from tests.conftest import assign_role, register_school


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


async def _setup_class_with_two_subjects(client: AsyncClient, headers: dict, school_id: str) -> dict:
    """Année scolaire + période + niveau + classe + 2 matières (coef différents) + 2 élèves
    inscrits + type d'évaluation. Retourne tout ce qu'il faut pour les tests de notes."""
    year = (
        await client.post(
            "/api/v1/academic-years",
            json={
                "school_id": school_id,
                "name": "2026-2027",
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
    level = (await client.post("/api/v1/education-levels", json={"school_id": school_id, "name": "CE1"}, headers=headers)).json()
    school_class = (
        await client.post(
            "/api/v1/classes",
            json={"academic_year_id": year["id"], "education_level_id": level["id"], "name": "A"},
            headers=headers,
        )
    ).json()

    math = (await client.post("/api/v1/subjects", json={"school_id": school_id, "name": "Mathématiques"}, headers=headers)).json()
    french = (await client.post("/api/v1/subjects", json={"school_id": school_id, "name": "Français"}, headers=headers)).json()

    math_cs = (
        await client.post(
            f"/api/v1/classes/{school_class['id']}/subjects",
            json={"subject_id": math["id"], "coefficient": 3},
            headers=headers,
        )
    ).json()
    french_cs = (
        await client.post(
            f"/api/v1/classes/{school_class['id']}/subjects",
            json={"subject_id": french["id"], "coefficient": 2},
            headers=headers,
        )
    ).json()

    assessment_type = (
        await client.post("/api/v1/assessment-types", json={"school_id": school_id, "name": "Devoir"}, headers=headers)
    ).json()

    students = []
    for i, (matricule, first_name) in enumerate([("S001", "Alpha"), ("S002", "Beta")]):
        student = (
            await client.post(
                "/api/v1/students",
                json={
                    "school_id": school_id,
                    "matricule": matricule,
                    "first_name": first_name,
                    "last_name": "Test",
                    "date_of_birth": str(date(2015, 1, 1)),
                    "sex": "M" if i == 0 else "F",
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
        "math_cs": math_cs,
        "french_cs": french_cs,
        "assessment_type": assessment_type,
        "students": students,
    }


async def test_subject_average_and_rank_single_assessment(client: AsyncClient) -> None:
    data = await register_school(client, "gradesbasic")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    ctx = await _setup_class_with_two_subjects(client, headers, school_id)
    student_a, student_b = ctx["students"]

    assessment = (
        await client.post(
            "/api/v1/assessments",
            json={
                "class_subject_id": ctx["math_cs"]["id"],
                "academic_term_id": ctx["term"]["id"],
                "assessment_type_id": ctx["assessment_type"]["id"],
                "name": "Devoir 1",
                "max_score": 20,
                "weight": 1,
                "assessment_date": str(date(2026, 10, 1)),
            },
            headers=headers,
        )
    ).json()

    submit = await client.post(
        "/api/v1/results",
        json={
            "assessment_id": assessment["id"],
            "results": [
                {"student_id": student_a["id"], "score": 16},
                {"student_id": student_b["id"], "score": 10},
            ],
        },
        headers=headers,
    )
    assert submit.status_code == 201, submit.text

    averages_a = (
        await client.get(
            f"/api/v1/students/{student_a['id']}/averages?academic_term_id={ctx['term']['id']}", headers=headers
        )
    ).json()
    subject_avg_a = next(s for s in averages_a["subject_averages"] if s["class_subject_id"] == ctx["math_cs"]["id"])
    assert subject_avg_a["average"] == pytest.approx(16.0)
    assert subject_avg_a["rank"] == 1

    averages_b = (
        await client.get(
            f"/api/v1/students/{student_b['id']}/averages?academic_term_id={ctx['term']['id']}", headers=headers
        )
    ).json()
    subject_avg_b = next(s for s in averages_b["subject_averages"] if s["class_subject_id"] == ctx["math_cs"]["id"])
    assert subject_avg_b["average"] == pytest.approx(10.0)
    assert subject_avg_b["rank"] == 2

    # Un seul devoir (French non noté) : la moyenne générale == moyenne de la seule matière notée.
    term_avg_a = next(t for t in averages_a["term_averages"] if t["academic_term_id"] == ctx["term"]["id"])
    assert term_avg_a["average"] == pytest.approx(16.0)
    assert term_avg_a["rank"] == 1


async def test_term_average_weighted_by_subject_coefficient(client: AsyncClient) -> None:
    data = await register_school(client, "gradesweighted")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    ctx = await _setup_class_with_two_subjects(client, headers, school_id)
    student_a, student_b = ctx["students"]

    math_assessment = (
        await client.post(
            "/api/v1/assessments",
            json={
                "class_subject_id": ctx["math_cs"]["id"],
                "academic_term_id": ctx["term"]["id"],
                "assessment_type_id": ctx["assessment_type"]["id"],
                "name": "Devoir Maths",
                "assessment_date": str(date(2026, 10, 1)),
            },
            headers=headers,
        )
    ).json()
    french_assessment = (
        await client.post(
            "/api/v1/assessments",
            json={
                "class_subject_id": ctx["french_cs"]["id"],
                "academic_term_id": ctx["term"]["id"],
                "assessment_type_id": ctx["assessment_type"]["id"],
                "name": "Devoir Français",
                "assessment_date": str(date(2026, 10, 2)),
            },
            headers=headers,
        )
    ).json()

    await client.post(
        "/api/v1/results",
        json={
            "assessment_id": math_assessment["id"],
            "results": [
                {"student_id": student_a["id"], "score": 16},
                {"student_id": student_b["id"], "score": 10},
            ],
        },
        headers=headers,
    )
    await client.post(
        "/api/v1/results",
        json={
            "assessment_id": french_assessment["id"],
            "results": [
                {"student_id": student_a["id"], "score": 10},
                {"student_id": student_b["id"], "score": 18},
            ],
        },
        headers=headers,
    )

    # A : (16*3 + 10*2) / 5 = 13.6   |   B : (10*3 + 18*2) / 5 = 13.2
    averages_a = (
        await client.get(f"/api/v1/students/{student_a['id']}/averages?academic_term_id={ctx['term']['id']}", headers=headers)
    ).json()
    averages_b = (
        await client.get(f"/api/v1/students/{student_b['id']}/averages?academic_term_id={ctx['term']['id']}", headers=headers)
    ).json()

    term_avg_a = next(t for t in averages_a["term_averages"] if t["academic_term_id"] == ctx["term"]["id"])
    term_avg_b = next(t for t in averages_b["term_averages"] if t["academic_term_id"] == ctx["term"]["id"])
    assert term_avg_a["average"] == pytest.approx(13.6)
    assert term_avg_b["average"] == pytest.approx(13.2)
    assert term_avg_a["rank"] == 1
    assert term_avg_b["rank"] == 2

    performance = (
        await client.get(
            f"/api/v1/classes/{ctx['class']['id']}/performance?academic_term_id={ctx['term']['id']}", headers=headers
        )
    ).json()
    assert performance["students"][0]["student_id"] == student_a["id"]
    assert performance["students"][0]["rank"] == 1


async def test_updating_result_recomputes_average(client: AsyncClient) -> None:
    data = await register_school(client, "gradesupdate")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    ctx = await _setup_class_with_two_subjects(client, headers, school_id)
    student_a = ctx["students"][0]

    assessment = (
        await client.post(
            "/api/v1/assessments",
            json={
                "class_subject_id": ctx["math_cs"]["id"],
                "academic_term_id": ctx["term"]["id"],
                "assessment_type_id": ctx["assessment_type"]["id"],
                "name": "Devoir 1",
                "assessment_date": str(date(2026, 10, 1)),
            },
            headers=headers,
        )
    ).json()
    submit_response = await client.post(
        "/api/v1/results",
        json={"assessment_id": assessment["id"], "results": [{"student_id": student_a["id"], "score": 12}]},
        headers=headers,
    )
    result = submit_response.json()[0]

    update_response = await client.patch(f"/api/v1/results/{result['id']}", json={"score": 18}, headers=headers)
    assert update_response.status_code == 200
    assert update_response.json()["score"] == 18

    averages = (
        await client.get(f"/api/v1/students/{student_a['id']}/averages?academic_term_id={ctx['term']['id']}", headers=headers)
    ).json()
    subject_avg = next(s for s in averages["subject_averages"] if s["class_subject_id"] == ctx["math_cs"]["id"])
    assert subject_avg["average"] == pytest.approx(18.0)


async def test_appreciation_update(client: AsyncClient) -> None:
    data = await register_school(client, "gradesappreciation")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    ctx = await _setup_class_with_two_subjects(client, headers, school_id)
    student_a = ctx["students"][0]

    assessment = (
        await client.post(
            "/api/v1/assessments",
            json={
                "class_subject_id": ctx["math_cs"]["id"],
                "academic_term_id": ctx["term"]["id"],
                "assessment_type_id": ctx["assessment_type"]["id"],
                "name": "Devoir 1",
                "assessment_date": str(date(2026, 10, 1)),
            },
            headers=headers,
        )
    ).json()
    await client.post(
        "/api/v1/results",
        json={"assessment_id": assessment["id"], "results": [{"student_id": student_a["id"], "score": 14}]},
        headers=headers,
    )

    averages = (
        await client.get(f"/api/v1/students/{student_a['id']}/averages?academic_term_id={ctx['term']['id']}", headers=headers)
    ).json()
    subject_avg = next(s for s in averages["subject_averages"] if s["class_subject_id"] == ctx["math_cs"]["id"])

    update_response = await client.patch(
        f"/api/v1/student-subject-averages/{subject_avg['id']}",
        json={"appreciation": "Bon travail, continue ainsi."},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["appreciation"] == "Bon travail, continue ainsi."


async def test_teacher_restricted_to_assigned_class_subject(client: AsyncClient) -> None:
    data = await register_school(client, "gradesteacher")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    organization_id = data["organization"]["id"]

    ctx = await _setup_class_with_two_subjects(client, headers_admin, school_id)

    teacher_data = await register_school(client, "gradesteacher-teacher")
    teacher_user_id = teacher_data["user"]["id"]
    await assign_role(teacher_user_id, "TEACHER", organization_id=organization_id, school_id=school_id)

    # Le prof n'est affecté qu'à la matière Maths.
    assign_response = await client.post(
        f"/api/v1/classes/{ctx['class']['id']}/teachers",
        json={"user_id": teacher_user_id, "subject_id": ctx["math_cs"]["subject_id"]},
        headers=headers_admin,
    )
    assert assign_response.status_code == 201

    headers_teacher = {"Authorization": f"Bearer {await _login(client, teacher_data['user']['email'])}"}

    math_assessment_response = await client.post(
        "/api/v1/assessments",
        json={
            "class_subject_id": ctx["math_cs"]["id"],
            "academic_term_id": ctx["term"]["id"],
            "assessment_type_id": ctx["assessment_type"]["id"],
            "name": "Interrogation",
            "assessment_date": str(date(2026, 10, 5)),
        },
        headers=headers_teacher,
    )
    assert math_assessment_response.status_code == 201

    french_assessment_response = await client.post(
        "/api/v1/assessments",
        json={
            "class_subject_id": ctx["french_cs"]["id"],
            "academic_term_id": ctx["term"]["id"],
            "assessment_type_id": ctx["assessment_type"]["id"],
            "name": "Interrogation",
            "assessment_date": str(date(2026, 10, 5)),
        },
        headers=headers_teacher,
    )
    assert french_assessment_response.status_code == 403


async def test_grades_tenant_isolation(client: AsyncClient) -> None:
    school_a = await register_school(client, "gradesisoa")
    school_b = await register_school(client, "gradesisob")
    headers_a = {"Authorization": f"Bearer {await _login(client, school_a['user']['email'])}"}
    headers_b = {"Authorization": f"Bearer {await _login(client, school_b['user']['email'])}"}

    ctx_b = await _setup_class_with_two_subjects(client, headers_b, school_b["school"]["id"])

    response = await client.get(
        f"/api/v1/assessments?class_subject_id={ctx_b['math_cs']['id']}", headers=headers_a
    )
    assert response.status_code == 404
