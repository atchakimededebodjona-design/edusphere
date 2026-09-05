"""Tableau de bord opérationnel admin (Phase 10) — GET /schools/{id}/dashboard.

Chaque métrique réutilise une définition déjà existante (voir docs/phases/PHASE_10_IMPLEMENTATION.md) :
- effectif : Student.status == "ACTIVE" (champ déjà existant, déjà filtré ailleurs par
  students/router.py::list_students) ;
- présence : même formule que attendance/service.py::_summarize (Phase 6), agrégée à l'échelle
  de l'école pour le terme courant ;
- complétude des notes : résultats attendus (inscriptions actives × évaluations du terme) vs
  résultats saisis (assessment_results) ;
- bulletins publiés : ReportCard.published_at IS NOT NULL (même filtre que
  parent/router.py::list_child_report_cards).

Le "terme courant" est résolu dynamiquement (année marquée is_current, terme dont la période
couvre la date du jour) — les dates de test sont donc calculées par rapport à `date.today()`,
pas des dates fixes comme dans la plupart des autres tests de ce projet.
"""

from datetime import date, timedelta

from httpx import AsyncClient

from tests.conftest import register_school, unique_email


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


async def _setup_school_with_data(
    client: AsyncClient, prefix: str, *, with_attendance: bool = True, with_grades: bool = True
) -> dict:
    """École avec : année/terme courants (couvrant aujourd'hui), 1 classe, 2 élèves activement
    inscrits, éventuellement une session de présence (1 présent, 1 absent) et une évaluation
    notée pour un seul des deux élèves (complétude partielle volontaire, 50%), un bulletin
    publié et un non publié."""
    data = await register_school(client, prefix)
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    today = date.today()
    year = (
        await client.post(
            "/api/v1/academic-years",
            json={
                "school_id": school_id,
                "name": f"Annee-{prefix}",
                "start_date": str(today - timedelta(days=180)),
                "end_date": str(today + timedelta(days=180)),
                "is_current": True,
            },
            headers=headers,
        )
    ).json()
    term = (
        await client.post(
            "/api/v1/academic-terms",
            json={
                "academic_year_id": year["id"],
                "name": f"Terme-{prefix}",
                "start_date": str(today - timedelta(days=30)),
                "end_date": str(today + timedelta(days=30)),
            },
            headers=headers,
        )
    ).json()
    level = (
        await client.post("/api/v1/education-levels", json={"school_id": school_id, "name": "CE1"}, headers=headers)
    ).json()
    school_class = (
        await client.post(
            "/api/v1/classes",
            json={"academic_year_id": year["id"], "education_level_id": level["id"], "name": "A"},
            headers=headers,
        )
    ).json()
    subject = (
        await client.post("/api/v1/subjects", json={"school_id": school_id, "name": "Mathematiques"}, headers=headers)
    ).json()
    class_subject = (
        await client.post(
            f"/api/v1/classes/{school_class['id']}/subjects",
            json={"subject_id": subject["id"], "coefficient": 1},
            headers=headers,
        )
    ).json()

    students = []
    for i in range(2):
        student = (
            await client.post(
                "/api/v1/students",
                json={
                    "school_id": school_id,
                    "matricule": f"{prefix.upper()}{i}",
                    "first_name": f"Eleve{i}",
                    "last_name": prefix,
                    "date_of_birth": "2015-01-01",
                    "sex": "F",
                },
                headers=headers,
            )
        ).json()
        await client.post(
            f"/api/v1/students/{student['id']}/enrollments",
            json={"class_id": school_class["id"], "enrollment_date": str(today - timedelta(days=10))},
            headers=headers,
        )
        students.append(student)

    if with_attendance:
        session = (
            await client.post(
                "/api/v1/attendance-sessions",
                json={"class_id": school_class["id"], "academic_term_id": term["id"], "session_date": str(today)},
                headers=headers,
            )
        ).json()
        await client.post(
            "/api/v1/attendance-records",
            json={
                "session_id": session["id"],
                "records": [
                    {"student_id": students[0]["id"], "status": "PRESENT"},
                    {"student_id": students[1]["id"], "status": "ABSENT"},
                ],
            },
            headers=headers,
        )

    if with_grades:
        assessment_type = (
            await client.post("/api/v1/assessment-types", json={"school_id": school_id, "name": "Devoir"}, headers=headers)
        ).json()
        assessment = (
            await client.post(
                "/api/v1/assessments",
                json={
                    "class_subject_id": class_subject["id"],
                    "academic_term_id": term["id"],
                    "assessment_type_id": assessment_type["id"],
                    "name": "Devoir 1",
                    "assessment_date": str(today),
                },
                headers=headers,
            )
        ).json()
        # Un seul des deux élèves noté -> complétude attendue de 50%.
        await client.post(
            "/api/v1/results",
            json={"assessment_id": assessment["id"], "results": [{"student_id": students[0]["id"], "score": 15}]},
            headers=headers,
        )

    template = (
        await client.post(
            "/api/v1/report-card-templates",
            json={"school_id": school_id, "name": "Standard", "html_content": "<p>{{ student.first_name }}</p>"},
            headers=headers,
        )
    ).json()
    generated = (
        await client.post(
            "/api/v1/report-cards/generate",
            json={"class_id": school_class["id"], "academic_term_id": term["id"], "template_id": template["id"]},
            headers=headers,
        )
    ).json()
    # Publie un seul des deux bulletins générés.
    await client.post(f"/api/v1/report-cards/{generated[0]['id']}/publish", headers=headers)

    return {"headers": headers, "school_id": school_id, "organization_id": data["organization"]["id"], "data": data}


# --- 1/2/3/4 — dashboard accessible, métriques correctes sur une école peuplée ------------------
async def test_dashboard_returns_real_metrics_for_populated_school(client: AsyncClient) -> None:
    ctx = await _setup_school_with_data(client, "dashfull")

    response = await client.get(f"/api/v1/schools/{ctx['school_id']}/dashboard", headers=ctx["headers"])
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["active_student_count"] == 2
    assert body["attendance_rate"] == 50.0  # 1 présent + 0 retard / 2 = 50%
    assert body["grade_completeness_rate"] == 50.0  # 1 résultat saisi / 2 attendus = 50%
    assert body["published_report_card_count"] == 1
    assert body["current_term_id"] is not None
    assert body["current_term_name"] == "Terme-dashfull"


# --- 6 — école vide ------------------------------------------------------------------------------
async def test_dashboard_empty_school_shows_zero_and_no_data(client: AsyncClient) -> None:
    data = await register_school(client, "dashempty")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}

    response = await client.get(f"/api/v1/schools/{data['school']['id']}/dashboard", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["active_student_count"] == 0
    assert body["attendance_rate"] is None
    assert body["grade_completeness_rate"] is None
    assert body["published_report_card_count"] == 0
    assert body["current_term_id"] is None


# --- 7 — absence de données de présence -----------------------------------------------------------
async def test_dashboard_no_attendance_data_shows_none(client: AsyncClient) -> None:
    ctx = await _setup_school_with_data(client, "dashnoatt", with_attendance=False)

    response = await client.get(f"/api/v1/schools/{ctx['school_id']}/dashboard", headers=ctx["headers"])
    assert response.status_code == 200
    body = response.json()

    assert body["attendance_rate"] is None
    assert body["grade_completeness_rate"] == 50.0  # les notes, elles, existent toujours


# --- 8 — absence de données de notes ---------------------------------------------------------------
async def test_dashboard_no_grades_data_shows_none(client: AsyncClient) -> None:
    ctx = await _setup_school_with_data(client, "dashnograde", with_grades=False)

    response = await client.get(f"/api/v1/schools/{ctx['school_id']}/dashboard", headers=ctx["headers"])
    assert response.status_code == 200
    body = response.json()

    assert body["grade_completeness_rate"] is None
    assert body["attendance_rate"] == 50.0  # la présence, elle, existe toujours


# --- 9 — isolation entre écoles -------------------------------------------------------------------
async def test_dashboard_tenant_isolation(client: AsyncClient) -> None:
    school_a = await register_school(client, "dashisoa")
    headers_a = {"Authorization": f"Bearer {await _login(client, school_a['user']['email'])}"}
    ctx_b = await _setup_school_with_data(client, "dashisob")

    # Le dashboard de A ne reflète jamais les données de B.
    response_a = await client.get(f"/api/v1/schools/{school_a['school']['id']}/dashboard", headers=headers_a)
    assert response_a.status_code == 200
    body_a = response_a.json()
    assert body_a["active_student_count"] == 0
    assert body_a["published_report_card_count"] == 0

    # A ne peut pas non plus consulter directement le dashboard de B.
    forged = await client.get(f"/api/v1/schools/{ctx_b['school_id']}/dashboard", headers=headers_a)
    assert forged.status_code in (403, 404)


# --- 10 — permission refusée ------------------------------------------------------------------------
async def test_dashboard_permission_denied_for_accountant(client: AsyncClient) -> None:
    """ACCOUNTANT n'a, dans le catalogue RBAC actuel, aucune des 4 permissions de lecture
    requises (students/attendance/grades/report_cards.read) — seulement schools.read."""
    data = await register_school(client, "dashperm")
    admin_headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    accountant_email = unique_email("accountant.dashperm")
    created = (
        await client.post(
            "/api/v1/users",
            json={
                "email": accountant_email,
                "full_name": "Comptable Test",
                "school_id": school_id,
                "role_code": "ACCOUNTANT",
            },
            headers=admin_headers,
        )
    ).json()
    await client.post(
        "/api/v1/auth/reset-password",
        json={"token": created["dev_reset_token"], "new_password": "AccountantPass123"},
    )
    accountant_headers = {"Authorization": f"Bearer {await _login(client, accountant_email, 'AccountantPass123')}"}

    response = await client.get(f"/api/v1/schools/{school_id}/dashboard", headers=accountant_headers)
    assert response.status_code == 403
