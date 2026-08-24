import io
from datetime import date

from httpx import AsyncClient

from tests.conftest import assign_role, register_school


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


async def _create_student(
    client: AsyncClient, headers: dict, school_id: str, matricule: str = "M0001", first_name: str = "Awa"
) -> dict:
    response = await client.post(
        "/api/v1/students",
        json={
            "school_id": school_id,
            "matricule": matricule,
            "first_name": first_name,
            "last_name": "Koffi",
            "date_of_birth": str(date(2015, 3, 12)),
            "sex": "F",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_and_search_student(client: AsyncClient) -> None:
    data = await register_school(client, "studentcreate")
    token = await _login(client, data["user"]["email"])
    headers = {"Authorization": f"Bearer {token}"}
    school_id = data["school"]["id"]

    student = await _create_student(client, headers, school_id)
    assert student["status"] == "ACTIVE"

    search_response = await client.get(f"/api/v1/students?school_id={school_id}&search=awa", headers=headers)
    assert search_response.status_code == 200
    assert any(s["id"] == student["id"] for s in search_response.json())

    no_match = await client.get(f"/api/v1/students?school_id={school_id}&search=zzzznotfound", headers=headers)
    assert no_match.json() == []


async def test_duplicate_matricule_conflicts(client: AsyncClient) -> None:
    data = await register_school(client, "studentdup")
    token = await _login(client, data["user"]["email"])
    headers = {"Authorization": f"Bearer {token}"}
    school_id = data["school"]["id"]

    await _create_student(client, headers, school_id, matricule="DUP1")
    response = await client.post(
        "/api/v1/students",
        json={
            "school_id": school_id,
            "matricule": "DUP1",
            "first_name": "Other",
            "last_name": "Person",
            "date_of_birth": str(date(2016, 1, 1)),
            "sex": "M",
        },
        headers=headers,
    )
    assert response.status_code == 409


async def test_status_update_records_history(client: AsyncClient) -> None:
    data = await register_school(client, "studentstatus")
    token = await _login(client, data["user"]["email"])
    headers = {"Authorization": f"Bearer {token}"}
    school_id = data["school"]["id"]

    student = await _create_student(client, headers, school_id)
    response = await client.patch(
        f"/api/v1/students/{student['id']}",
        json={"status": "WITHDRAWN", "status_change_reason": "Déménagement"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "WITHDRAWN"


async def test_guardian_attach_and_detach(client: AsyncClient) -> None:
    data = await register_school(client, "studentguardian")
    token = await _login(client, data["user"]["email"])
    headers = {"Authorization": f"Bearer {token}"}
    school_id = data["school"]["id"]

    student = await _create_student(client, headers, school_id)
    guardian_response = await client.post(
        "/api/v1/guardians",
        json={
            "school_id": school_id,
            "full_name": "Mariam Koffi",
            "relationship_type": "mother",
            "phone": "+22890000000",
            "is_emergency_contact": True,
        },
        headers=headers,
    )
    assert guardian_response.status_code == 201
    guardian = guardian_response.json()

    attach_response = await client.post(
        f"/api/v1/students/{student['id']}/guardians",
        json={"guardian_id": guardian["id"], "is_primary_contact": True},
        headers=headers,
    )
    assert attach_response.status_code == 201
    link = attach_response.json()

    list_response = await client.get(f"/api/v1/students/{student['id']}/guardians", headers=headers)
    assert len(list_response.json()) == 1

    detach_response = await client.delete(
        f"/api/v1/students/{student['id']}/guardians/{link['id']}", headers=headers
    )
    assert detach_response.status_code == 204

    list_after = await client.get(f"/api/v1/students/{student['id']}/guardians", headers=headers)
    assert list_after.json() == []


async def test_enrollment_flow(client: AsyncClient) -> None:
    data = await register_school(client, "studentenroll")
    token = await _login(client, data["user"]["email"])
    headers = {"Authorization": f"Bearer {token}"}
    school_id = data["school"]["id"]

    year_response = await client.post(
        "/api/v1/academic-years",
        json={
            "school_id": school_id,
            "name": "2026-2027",
            "start_date": str(date(2026, 9, 1)),
            "end_date": str(date(2027, 6, 30)),
        },
        headers=headers,
    )
    year = year_response.json()
    level_response = await client.post(
        "/api/v1/education-levels", json={"school_id": school_id, "name": "CE1"}, headers=headers
    )
    level = level_response.json()
    class_response = await client.post(
        "/api/v1/classes",
        json={"academic_year_id": year["id"], "education_level_id": level["id"], "name": "A"},
        headers=headers,
    )
    school_class = class_response.json()

    student = await _create_student(client, headers, school_id)

    enroll_response = await client.post(
        f"/api/v1/students/{student['id']}/enrollments",
        json={"class_id": school_class["id"], "enrollment_date": str(date(2026, 9, 1))},
        headers=headers,
    )
    assert enroll_response.status_code == 201
    enrollment = enroll_response.json()
    assert enrollment["academic_year_id"] == year["id"]

    # Deuxième inscription pour la même année scolaire -> conflit.
    duplicate_response = await client.post(
        f"/api/v1/students/{student['id']}/enrollments",
        json={"class_id": school_class["id"], "enrollment_date": str(date(2026, 9, 1))},
        headers=headers,
    )
    assert duplicate_response.status_code == 409

    filtered = await client.get(f"/api/v1/students?school_id={school_id}&class_id={school_class['id']}", headers=headers)
    assert any(s["id"] == student["id"] for s in filtered.json())

    update_response = await client.patch(
        f"/api/v1/enrollments/{enrollment['id']}", json={"status": "TRANSFERRED"}, headers=headers
    )
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "TRANSFERRED"


async def test_photo_and_document_upload(client: AsyncClient) -> None:
    data = await register_school(client, "studentdocs")
    token = await _login(client, data["user"]["email"])
    headers = {"Authorization": f"Bearer {token}"}
    school_id = data["school"]["id"]

    student = await _create_student(client, headers, school_id)

    photo_response = await client.post(
        f"/api/v1/students/{student['id']}/photo",
        headers=headers,
        files={"file": ("photo.jpg", io.BytesIO(b"fake-jpeg-bytes"), "image/jpeg")},
    )
    assert photo_response.status_code == 200
    assert photo_response.json()["photo_path"] is not None

    doc_response = await client.post(
        f"/api/v1/students/{student['id']}/documents",
        headers=headers,
        data={"document_type": "birth_certificate"},
        files={"file": ("certificate.pdf", io.BytesIO(b"fake-pdf-bytes"), "application/pdf")},
    )
    assert doc_response.status_code == 201
    document = doc_response.json()

    list_response = await client.get(f"/api/v1/students/{student['id']}/documents", headers=headers)
    assert len(list_response.json()) == 1

    delete_response = await client.delete(
        f"/api/v1/students/{student['id']}/documents/{document['id']}", headers=headers
    )
    assert delete_response.status_code == 204


async def test_csv_import_with_duplicates_and_errors(client: AsyncClient) -> None:
    data = await register_school(client, "studentimport")
    token = await _login(client, data["user"]["email"])
    headers = {"Authorization": f"Bearer {token}"}
    school_id = data["school"]["id"]

    await _create_student(client, headers, school_id, matricule="EXIST1", first_name="Existing")

    csv_content = (
        "matricule,first_name,last_name,date_of_birth,sex\n"
        "IMP001,Jean,Dupont,2014-05-01,M\n"
        "IMP002,Awa,Traore,2015-07-15,F\n"
        "EXIST1,Existing,Koffi,2015-03-12,F\n"  # doublon matricule (déjà existant)
        "IMP001,Jean,Dupont,2014-05-01,M\n"  # doublon dans le même fichier
        "IMP004,,Missing,2014-01-01,M\n"  # champ requis manquant
        "IMP005,Bad,Date,not-a-date,M\n"  # date invalide
    )

    response = await client.post(
        "/api/v1/students/import",
        headers=headers,
        data={"school_id": school_id},
        files={"file": ("students.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["total_rows"] == 6
    assert report["created"] == 2
    assert report["duplicates_skipped"] == 2
    assert len(report["errors"]) == 2

    list_response = await client.get(f"/api/v1/students?school_id={school_id}", headers=headers)
    matricules = {s["matricule"] for s in list_response.json()}
    assert {"EXIST1", "IMP001", "IMP002"}.issubset(matricules)


async def test_xlsx_import(client: AsyncClient) -> None:
    import openpyxl

    data = await register_school(client, "studentimportxlsx")
    token = await _login(client, data["user"]["email"])
    headers = {"Authorization": f"Bearer {token}"}
    school_id = data["school"]["id"]

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["matricule", "first_name", "last_name", "date_of_birth", "sex"])
    sheet.append(["XLS001", "Kofi", "Mensah", "2013-11-20", "M"])
    sheet.append(["XLS002", "Ama", "Owusu", "2014-02-10", "F"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    response = await client.post(
        "/api/v1/students/import",
        headers=headers,
        data={"school_id": school_id},
        files={
            "file": (
                "students.xlsx",
                buffer,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["total_rows"] == 2
    assert report["created"] == 2
    assert report["errors"] == []


async def test_students_tenant_isolation(client: AsyncClient) -> None:
    school_a = await register_school(client, "studentisoa")
    school_b = await register_school(client, "studentisob")
    token_a = await _login(client, school_a["user"]["email"])
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {await _login(client, school_b['user']['email'])}"}

    student_b = await _create_student(client, headers_b, school_b["school"]["id"], matricule="ISOB1")

    get_response = await client.get(f"/api/v1/students/{student_b['id']}", headers=headers_a)
    assert get_response.status_code == 404

    list_response = await client.get(f"/api/v1/students?school_id={school_b['school']['id']}", headers=headers_a)
    assert list_response.status_code == 404

    update_response = await client.patch(
        f"/api/v1/students/{student_b['id']}", json={"first_name": "Hacked"}, headers=headers_a
    )
    assert update_response.status_code == 404


async def test_teacher_cannot_manage_students(client: AsyncClient) -> None:
    data = await register_school(client, "studentteacher")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    organization_id = data["organization"]["id"]

    teacher_data = await register_school(client, "studentteacher-teacher")
    await assign_role(teacher_data["user"]["id"], "TEACHER", organization_id=organization_id, school_id=school_id)
    headers_teacher = {"Authorization": f"Bearer {await _login(client, teacher_data['user']['email'])}"}

    student = await _create_student(client, headers_admin, school_id)

    read_response = await client.get(f"/api/v1/students/{student['id']}", headers=headers_teacher)
    assert read_response.status_code == 200

    manage_response = await client.patch(
        f"/api/v1/students/{student['id']}", json={"address": "New address"}, headers=headers_teacher
    )
    assert manage_response.status_code == 403
