import uuid
from datetime import date

from httpx import AsyncClient

from tests.conftest import assign_role, register_school, unique_email

MINIMAL_TEMPLATE = """
<html><body>
<h1>{{ school.name }}</h1>
<p>{{ student.first_name }} {{ student.last_name }}</p>
<p>Moyenne generale: {{ general_average }} - Rang: {{ general_rank }}</p>
<img src="{{ qr_code_data_uri }}" width="80" />
</body></html>
"""


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


async def _setup_child_context(client: AsyncClient, headers_admin: dict, school_id: str) -> dict:
    """Année/période/niveau/classe/matière + 1 élève inscrit, noté, avec une session de présence
    et un modèle de bulletin — le minimum pour exercer les 3 domaines exposés au parent
    (assiduité, notes, bulletins). Suffixe unique pour permettre plusieurs appels dans la même
    école (cf. test_attendance.py::_setup_class_with_students, même contrainte)."""
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
            headers=headers_admin,
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
            headers=headers_admin,
        )
    ).json()
    level = (
        await client.post("/api/v1/education-levels", json={"school_id": school_id, "name": f"CE1-{suffix}"}, headers=headers_admin)
    ).json()
    school_class = (
        await client.post(
            "/api/v1/classes",
            json={"academic_year_id": year["id"], "education_level_id": level["id"], "name": "A"},
            headers=headers_admin,
        )
    ).json()
    subject = (
        await client.post("/api/v1/subjects", json={"school_id": school_id, "name": f"Mathematiques-{suffix}"}, headers=headers_admin)
    ).json()
    class_subject = (
        await client.post(
            f"/api/v1/classes/{school_class['id']}/subjects",
            json={"subject_id": subject["id"], "coefficient": 1},
            headers=headers_admin,
        )
    ).json()
    assessment_type = (
        await client.post("/api/v1/assessment-types", json={"school_id": school_id, "name": f"Devoir-{suffix}"}, headers=headers_admin)
    ).json()

    student = (
        await client.post(
            "/api/v1/students",
            json={
                "school_id": school_id,
                "matricule": f"P{suffix}",
                "first_name": "Kofi",
                "last_name": "Enfant",
                "date_of_birth": str(date(2015, 1, 1)),
                "sex": "M",
            },
            headers=headers_admin,
        )
    ).json()
    await client.post(
        f"/api/v1/students/{student['id']}/enrollments",
        json={"class_id": school_class["id"], "enrollment_date": str(date(2026, 9, 1))},
        headers=headers_admin,
    )

    # Note.
    assessment = (
        await client.post(
            "/api/v1/assessments",
            json={
                "class_subject_id": class_subject["id"],
                "academic_term_id": term["id"],
                "assessment_type_id": assessment_type["id"],
                "name": "Devoir 1",
                "assessment_date": str(date(2026, 10, 1)),
            },
            headers=headers_admin,
        )
    ).json()
    await client.post(
        "/api/v1/results",
        json={"assessment_id": assessment["id"], "results": [{"student_id": student["id"], "score": 15}]},
        headers=headers_admin,
    )

    # Présence.
    session = (
        await client.post(
            "/api/v1/attendance-sessions",
            json={"class_id": school_class["id"], "academic_term_id": term["id"], "session_date": str(date(2026, 10, 1))},
            headers=headers_admin,
        )
    ).json()
    await client.post(
        "/api/v1/attendance-records",
        json={"session_id": session["id"], "records": [{"student_id": student["id"], "status": "PRESENT"}]},
        headers=headers_admin,
    )

    # Bulletin (généré en DRAFT, publié séparément par les tests qui en ont besoin).
    template = (
        await client.post(
            "/api/v1/report-card-templates",
            json={"school_id": school_id, "name": f"Standard-{suffix}", "html_content": MINIMAL_TEMPLATE},
            headers=headers_admin,
        )
    ).json()

    return {"year": year, "term": term, "class": school_class, "student": student, "template": template}


async def _create_parent_user(client: AsyncClient, headers_admin: dict, school_id: str, email: str) -> dict:
    """Crée un compte PARENT via /users (endpoint générique déjà existant, Phase 5) puis fixe
    son mot de passe via le dev_reset_token — même mécanisme que pour un enseignant, cf.
    test_attendance.py."""
    response = await client.post(
        "/api/v1/users",
        json={"email": email, "full_name": "Parent Test", "school_id": school_id, "role_code": "PARENT"},
        headers=headers_admin,
    )
    assert response.status_code == 201, response.text
    data = response.json()
    reset = await client.post(
        "/api/v1/auth/reset-password", json={"token": data["dev_reset_token"], "new_password": "ParentPass123"}
    )
    assert reset.status_code == 204
    return data["user"]


async def _create_guardian(client: AsyncClient, headers_admin: dict, school_id: str) -> dict:
    response = await client.post(
        "/api/v1/guardians",
        json={"school_id": school_id, "full_name": "Tuteur Test", "relationship_type": "father"},
        headers=headers_admin,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _attach_guardian(client: AsyncClient, headers_admin: dict, student_id: str, guardian_id: str) -> None:
    response = await client.post(
        f"/api/v1/students/{student_id}/guardians", json={"guardian_id": guardian_id}, headers=headers_admin
    )
    assert response.status_code == 201, response.text


async def _setup_linked_parent(client: AsyncClient, headers_admin: dict, school_id: str, email_prefix: str) -> dict:
    """Contexte complet : élève noté/présent/bulletinable + parent réellement lié (Guardian.user_id
    valide, StudentGuardian attaché) + token du parent — le cas nominal réutilisé par la plupart
    des tests."""
    email = unique_email(email_prefix)
    ctx = await _setup_child_context(client, headers_admin, school_id)
    parent_user = await _create_parent_user(client, headers_admin, school_id, email)
    guardian = await _create_guardian(client, headers_admin, school_id)
    link = await client.patch(
        f"/api/v1/guardians/{guardian['id']}", json={"user_id": parent_user["id"]}, headers=headers_admin
    )
    assert link.status_code == 200, link.text
    await _attach_guardian(client, headers_admin, ctx["student"]["id"], guardian["id"])

    parent_token = await _login(client, email, "ParentPass123")
    ctx["parent_user"] = parent_user
    ctx["guardian"] = guardian
    ctx["parent_headers"] = {"Authorization": f"Bearer {parent_token}"}
    return ctx


# --- A/B/C/D — Liaison Guardian -> PARENT ---------------------------------------------
async def test_link_guardian_to_valid_parent_succeeds(client: AsyncClient) -> None:
    data = await register_school(client, "parentlinkok")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    parent_user = await _create_parent_user(client, headers_admin, school_id, unique_email("parent.linkok"))
    guardian = await _create_guardian(client, headers_admin, school_id)

    response = await client.patch(
        f"/api/v1/guardians/{guardian['id']}", json={"user_id": parent_user["id"]}, headers=headers_admin
    )
    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == parent_user["id"]


async def test_link_guardian_rejects_non_parent_user(client: AsyncClient) -> None:
    data = await register_school(client, "parentlinkbadrole")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    organization_id = data["organization"]["id"]

    staff_data = await register_school(client, "parentlinkbadrole-staff")
    await assign_role(staff_data["user"]["id"], "STAFF", organization_id=organization_id, school_id=school_id)
    guardian = await _create_guardian(client, headers_admin, school_id)

    response = await client.patch(
        f"/api/v1/guardians/{guardian['id']}", json={"user_id": staff_data["user"]["id"]}, headers=headers_admin
    )
    assert response.status_code == 400


async def test_link_guardian_rejects_user_from_another_tenant(client: AsyncClient) -> None:
    school_a = await register_school(client, "parentlinktenanta")
    school_b = await register_school(client, "parentlinktenantb")
    headers_a = {"Authorization": f"Bearer {await _login(client, school_a['user']['email'])}"}

    parent_b = await _create_parent_user(
        client,
        {"Authorization": f"Bearer {await _login(client, school_b['user']['email'])}"},
        school_b["school"]["id"],
        unique_email("parent.tenantb"),
    )
    guardian_a = await _create_guardian(client, headers_a, school_a["school"]["id"])

    response = await client.patch(
        f"/api/v1/guardians/{guardian_a['id']}", json={"user_id": parent_b["id"]}, headers=headers_a
    )
    assert response.status_code == 400


async def test_link_guardian_rejects_duplicate_in_same_school(client: AsyncClient) -> None:
    data = await register_school(client, "parentlinkdup")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    parent_user = await _create_parent_user(client, headers_admin, school_id, unique_email("parent.dup"))
    guardian_1 = await _create_guardian(client, headers_admin, school_id)
    guardian_2 = await _create_guardian(client, headers_admin, school_id)

    first = await client.patch(f"/api/v1/guardians/{guardian_1['id']}", json={"user_id": parent_user["id"]}, headers=headers_admin)
    assert first.status_code == 200

    second = await client.patch(f"/api/v1/guardians/{guardian_2['id']}", json={"user_id": parent_user["id"]}, headers=headers_admin)
    assert second.status_code == 409


# --- E/F/G/H — « mes enfants » et isolation ----------------------------------------
async def test_parent_sees_exactly_their_children(client: AsyncClient) -> None:
    data = await register_school(client, "parentchildren")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    ctx = await _setup_linked_parent(client, headers_admin, school_id, "parent.children")
    # Un élève tiers, non rattaché à ce parent.
    other = await _setup_child_context(client, headers_admin, school_id)

    response = await client.get("/api/v1/parent/children", headers=ctx["parent_headers"])
    assert response.status_code == 200
    ids = [c["id"] for c in response.json()]
    assert ids == [ctx["student"]["id"]]
    assert other["student"]["id"] not in ids


async def test_parent_a_cannot_see_child_of_parent_b(client: AsyncClient) -> None:
    data = await register_school(client, "parentcrossab")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    ctx_a = await _setup_linked_parent(client, headers_admin, school_id, "parent.crossa")
    ctx_b = await _setup_linked_parent(client, headers_admin, school_id, "parent.crossb")

    response = await client.get(
        f"/api/v1/parent/children/{ctx_b['student']['id']}/attendance-summary?academic_term_id={ctx_b['term']['id']}",
        headers=ctx_a["parent_headers"],
    )
    assert response.status_code == 404


async def test_parent_a_cannot_see_grades_of_parent_b(client: AsyncClient) -> None:
    data = await register_school(client, "parentcrossgrades")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    ctx_a = await _setup_linked_parent(client, headers_admin, school_id, "parent.gradesa")
    ctx_b = await _setup_linked_parent(client, headers_admin, school_id, "parent.gradesb")

    response = await client.get(f"/api/v1/parent/children/{ctx_b['student']['id']}/grades", headers=ctx_a["parent_headers"])
    assert response.status_code == 404


async def test_parent_cross_tenant_isolation(client: AsyncClient) -> None:
    school_a = await register_school(client, "parenttenanta")
    school_b = await register_school(client, "parenttenantb")
    headers_a = {"Authorization": f"Bearer {await _login(client, school_a['user']['email'])}"}
    headers_b = {"Authorization": f"Bearer {await _login(client, school_b['user']['email'])}"}

    ctx_a = await _setup_linked_parent(client, headers_a, school_a["school"]["id"], "parent.crosstenanta")
    ctx_b = await _setup_linked_parent(client, headers_b, school_b["school"]["id"], "parent.crosstenantb")

    response = await client.get("/api/v1/parent/children", headers=ctx_a["parent_headers"])
    ids = [c["id"] for c in response.json()]
    assert ctx_b["student"]["id"] not in ids

    forged = await client.get(
        f"/api/v1/parent/children/{ctx_b['student']['id']}/attendance-summary?academic_term_id={ctx_b['term']['id']}",
        headers=ctx_a["parent_headers"],
    )
    assert forged.status_code == 404


# --- I/J — Présence -----------------------------------------------------------------
async def test_child_attendance_summary_for_authorized_child(client: AsyncClient) -> None:
    data = await register_school(client, "parentattok")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_linked_parent(client, headers_admin, data["school"]["id"], "parent.attok")

    response = await client.get(
        f"/api/v1/parent/children/{ctx['student']['id']}/attendance-summary?academic_term_id={ctx['term']['id']}",
        headers=ctx["parent_headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["present_count"] == 1


async def test_child_attendance_summary_for_unauthorized_child_404(client: AsyncClient) -> None:
    data = await register_school(client, "parentattko")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    ctx = await _setup_linked_parent(client, headers_admin, school_id, "parent.attko")
    other = await _setup_child_context(client, headers_admin, school_id)

    response = await client.get(
        f"/api/v1/parent/children/{other['student']['id']}/attendance-summary?academic_term_id={other['term']['id']}",
        headers=ctx["parent_headers"],
    )
    assert response.status_code == 404


# --- K/L — Notes ---------------------------------------------------------------------
async def test_child_grades_for_authorized_child(client: AsyncClient) -> None:
    data = await register_school(client, "parentgradesok")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_linked_parent(client, headers_admin, data["school"]["id"], "parent.gradesok")

    response = await client.get(f"/api/v1/parent/children/{ctx['student']['id']}/grades", headers=ctx["parent_headers"])
    assert response.status_code == 200, response.text
    assert len(response.json()["subject_averages"]) == 1


async def test_child_grades_for_unauthorized_child_404(client: AsyncClient) -> None:
    data = await register_school(client, "parentgradesko")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    ctx = await _setup_linked_parent(client, headers_admin, school_id, "parent.gradesko")
    other = await _setup_child_context(client, headers_admin, school_id)

    response = await client.get(f"/api/v1/parent/children/{other['student']['id']}/grades", headers=ctx["parent_headers"])
    assert response.status_code == 404


# --- M/N/O/P/Q — Bulletins -----------------------------------------------------------
async def test_published_report_card_visible_and_downloadable(client: AsyncClient) -> None:
    data = await register_school(client, "parentrcpub")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_linked_parent(client, headers_admin, data["school"]["id"], "parent.rcpub")

    generate = await client.post(
        "/api/v1/report-cards/generate",
        json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "template_id": ctx["template"]["id"]},
        headers=headers_admin,
    )
    report_card = generate.json()[0]
    await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=headers_admin)

    listing = await client.get(f"/api/v1/parent/children/{ctx['student']['id']}/report-cards", headers=ctx["parent_headers"])
    assert listing.status_code == 200
    assert [rc["id"] for rc in listing.json()] == [report_card["id"]]

    pdf = await client.get(
        f"/api/v1/parent/children/{ctx['student']['id']}/report-cards/{report_card['id']}/pdf", headers=ctx["parent_headers"]
    )
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"


async def test_draft_report_card_invisible_and_not_downloadable(client: AsyncClient) -> None:
    data = await register_school(client, "parentrcdraft")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_linked_parent(client, headers_admin, data["school"]["id"], "parent.rcdraft")

    generate = await client.post(
        "/api/v1/report-cards/generate",
        json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "template_id": ctx["template"]["id"]},
        headers=headers_admin,
    )
    report_card = generate.json()[0]
    # Jamais publié.

    listing = await client.get(f"/api/v1/parent/children/{ctx['student']['id']}/report-cards", headers=ctx["parent_headers"])
    assert listing.status_code == 200
    assert listing.json() == []

    pdf = await client.get(
        f"/api/v1/parent/children/{ctx['student']['id']}/report-cards/{report_card['id']}/pdf", headers=ctx["parent_headers"]
    )
    assert pdf.status_code == 404


async def test_report_card_pdf_of_another_child_inaccessible(client: AsyncClient) -> None:
    data = await register_school(client, "parentrccross")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    ctx_a = await _setup_linked_parent(client, headers_admin, school_id, "parent.rccrossa")
    ctx_b = await _setup_linked_parent(client, headers_admin, school_id, "parent.rccrossb")

    generate_b = await client.post(
        "/api/v1/report-cards/generate",
        json={"class_id": ctx_b["class"]["id"], "academic_term_id": ctx_b["term"]["id"], "template_id": ctx_b["template"]["id"]},
        headers=headers_admin,
    )
    report_card_b = generate_b.json()[0]
    await client.post(f"/api/v1/report-cards/{report_card_b['id']}/publish", headers=headers_admin)

    # Parent A tente de télécharger le bulletin PUBLIÉ de l'enfant du parent B.
    pdf = await client.get(
        f"/api/v1/parent/children/{ctx_b['student']['id']}/report-cards/{report_card_b['id']}/pdf",
        headers=ctx_a["parent_headers"],
    )
    assert pdf.status_code == 404


# --- R — Plusieurs enfants -----------------------------------------------------------
async def test_parent_with_multiple_children(client: AsyncClient) -> None:
    data = await register_school(client, "parentmulti")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    email = unique_email("parent.multi")
    parent_user = await _create_parent_user(client, headers_admin, school_id, email)

    ctx_1 = await _setup_child_context(client, headers_admin, school_id)
    ctx_2 = await _setup_child_context(client, headers_admin, school_id)

    guardian_1 = await _create_guardian(client, headers_admin, school_id)
    await client.patch(f"/api/v1/guardians/{guardian_1['id']}", json={"user_id": parent_user["id"]}, headers=headers_admin)
    await _attach_guardian(client, headers_admin, ctx_1["student"]["id"], guardian_1["id"])

    # Deuxième enfant, MÊME Guardian (un tuteur peut avoir plusieurs enfants) — pas besoin d'un
    # second Guardian, StudentGuardian est déjà many-to-many.
    await _attach_guardian(client, headers_admin, ctx_2["student"]["id"], guardian_1["id"])

    parent_token = await _login(client, email, "ParentPass123")
    parent_headers = {"Authorization": f"Bearer {parent_token}"}

    response = await client.get("/api/v1/parent/children", headers=parent_headers)
    assert response.status_code == 200
    ids = {c["id"] for c in response.json()}
    assert ids == {ctx_1["student"]["id"], ctx_2["student"]["id"]}
