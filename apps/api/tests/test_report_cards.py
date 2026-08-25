from datetime import date

from httpx import AsyncClient

from tests.conftest import assign_role, register_school

MINIMAL_TEMPLATE = """
<html><body>
<h1>{{ school.name }}</h1>
<h2>Bulletin - {{ academic_term.name }}</h2>
<p>{{ student.first_name }} {{ student.last_name }} ({{ student.matricule }}) - Classe {{ school_class.name }}</p>
<table>
<tr><th>Matiere</th><th>Coef</th><th>Moyenne</th><th>Rang</th></tr>
{% for s in subjects %}
<tr><td>{{ s.name }}</td><td>{{ s.coefficient }}</td><td>{{ s.average }}</td><td>{{ s.rank }}</td></tr>
{% endfor %}
</table>
<p>Moyenne generale: {{ general_average }} - Rang: {{ general_rank }}</p>
<img src="{{ qr_code_data_uri }}" width="80" />
</body></html>
"""


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


async def _setup_graded_class(client: AsyncClient, headers: dict, school_id: str) -> dict:
    """Année/période/niveau/classe + 1 matière + 1 élève inscrit et noté — le minimum pour
    générer un bulletin exploitable."""
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
    math_cs = (
        await client.post(
            f"/api/v1/classes/{school_class['id']}/subjects",
            json={"subject_id": math["id"], "coefficient": 3},
            headers=headers,
        )
    ).json()
    assessment_type = (
        await client.post("/api/v1/assessment-types", json={"school_id": school_id, "name": "Devoir"}, headers=headers)
    ).json()
    student = (
        await client.post(
            "/api/v1/students",
            json={
                "school_id": school_id,
                "matricule": "RC001",
                "first_name": "Ama",
                "last_name": "Koffi",
                "date_of_birth": str(date(2015, 1, 1)),
                "sex": "F",
            },
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/students/{student['id']}/enrollments",
        json={"class_id": school_class["id"], "enrollment_date": str(date(2026, 9, 1))},
        headers=headers,
    )
    assessment = (
        await client.post(
            "/api/v1/assessments",
            json={
                "class_subject_id": math_cs["id"],
                "academic_term_id": term["id"],
                "assessment_type_id": assessment_type["id"],
                "name": "Devoir 1",
                "assessment_date": str(date(2026, 10, 1)),
            },
            headers=headers,
        )
    ).json()
    await client.post(
        "/api/v1/results",
        json={"assessment_id": assessment["id"], "results": [{"student_id": student["id"], "score": 15}]},
        headers=headers,
    )

    template = (
        await client.post(
            "/api/v1/report-card-templates",
            json={"school_id": school_id, "name": "Standard", "html_content": MINIMAL_TEMPLATE},
            headers=headers,
        )
    ).json()

    return {"year": year, "term": term, "class": school_class, "student": student, "template": template}


async def test_generate_and_download_report_card(client: AsyncClient) -> None:
    data = await register_school(client, "rcgenerate")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    ctx = await _setup_graded_class(client, headers, school_id)

    generate_response = await client.post(
        "/api/v1/report-cards/generate",
        json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "template_id": ctx["template"]["id"]},
        headers=headers,
    )
    assert generate_response.status_code == 200, generate_response.text
    report_cards = generate_response.json()
    assert len(report_cards) == 1
    report_card = report_cards[0]
    assert report_card["student_id"] == ctx["student"]["id"]
    assert report_card["status"] == "DRAFT"
    assert report_card["general_average"] == 15.0

    pdf_response = await client.get(f"/api/v1/report-cards/{report_card['id']}/pdf", headers=headers)
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"] == "application/pdf"
    assert pdf_response.content[:4] == b"%PDF"


async def test_publish_and_regenerate_resets_to_draft(client: AsyncClient) -> None:
    data = await register_school(client, "rcpublish")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    ctx = await _setup_graded_class(client, headers, school_id)
    generate_response = await client.post(
        "/api/v1/report-cards/generate",
        json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "template_id": ctx["template"]["id"]},
        headers=headers,
    )
    report_card = generate_response.json()[0]

    publish_response = await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=headers)
    assert publish_response.status_code == 200
    assert publish_response.json()["status"] == "PUBLISHED"
    assert publish_response.json()["published_at"] is not None

    # Régénération (ex. après correction d'une note) : repasse en DRAFT, garde le même id.
    regenerate_response = await client.post(
        "/api/v1/report-cards/generate",
        json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "template_id": ctx["template"]["id"]},
        headers=headers,
    )
    regenerated = regenerate_response.json()[0]
    assert regenerated["id"] == report_card["id"]
    assert regenerated["status"] == "DRAFT"
    assert regenerated["published_at"] is None
    assert regenerated["verification_code"] == report_card["verification_code"]


async def test_public_verification_endpoint(client: AsyncClient) -> None:
    data = await register_school(client, "rcverify")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    ctx = await _setup_graded_class(client, headers, school_id)
    generate_response = await client.post(
        "/api/v1/report-cards/generate",
        json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "template_id": ctx["template"]["id"]},
        headers=headers,
    )
    report_card = generate_response.json()[0]

    # Aucun header d'authentification — endpoint public.
    verify_response = await client.get(f"/api/v1/report-cards/verify/{report_card['verification_code']}")
    assert verify_response.status_code == 200
    body = verify_response.json()
    assert body["student_full_name"] == "Ama Koffi"
    assert body["general_average"] == 15.0
    assert body["status"] == "DRAFT"

    unknown_response = await client.get("/api/v1/report-cards/verify/not-a-real-code")
    assert unknown_response.status_code == 404


async def test_teacher_can_read_but_not_generate_or_publish(client: AsyncClient) -> None:
    data = await register_school(client, "rcteacher")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    organization_id = data["organization"]["id"]

    ctx = await _setup_graded_class(client, headers_admin, school_id)
    generate_response = await client.post(
        "/api/v1/report-cards/generate",
        json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "template_id": ctx["template"]["id"]},
        headers=headers_admin,
    )
    report_card = generate_response.json()[0]

    teacher_data = await register_school(client, "rcteacher-teacher")
    await assign_role(teacher_data["user"]["id"], "TEACHER", organization_id=organization_id, school_id=school_id)
    headers_teacher = {"Authorization": f"Bearer {await _login(client, teacher_data['user']['email'])}"}

    read_response = await client.get(f"/api/v1/report-cards/{report_card['id']}", headers=headers_teacher)
    assert read_response.status_code == 200

    generate_attempt = await client.post(
        "/api/v1/report-cards/generate",
        json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "template_id": ctx["template"]["id"]},
        headers=headers_teacher,
    )
    assert generate_attempt.status_code == 403

    publish_attempt = await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=headers_teacher)
    assert publish_attempt.status_code == 403


async def test_report_cards_tenant_isolation(client: AsyncClient) -> None:
    school_a = await register_school(client, "rcisoa")
    school_b = await register_school(client, "rcisob")
    headers_a = {"Authorization": f"Bearer {await _login(client, school_a['user']['email'])}"}
    headers_b = {"Authorization": f"Bearer {await _login(client, school_b['user']['email'])}"}

    ctx_b = await _setup_graded_class(client, headers_b, school_b["school"]["id"])
    generate_response = await client.post(
        "/api/v1/report-cards/generate",
        json={"class_id": ctx_b["class"]["id"], "academic_term_id": ctx_b["term"]["id"], "template_id": ctx_b["template"]["id"]},
        headers=headers_b,
    )
    report_card_b = generate_response.json()[0]

    get_response = await client.get(f"/api/v1/report-cards/{report_card_b['id']}", headers=headers_a)
    assert get_response.status_code == 404

    pdf_response = await client.get(f"/api/v1/report-cards/{report_card_b['id']}/pdf", headers=headers_a)
    assert pdf_response.status_code == 404
