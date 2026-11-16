"""Clés d'idempotence des séances d'appel et des évaluations (Phase 32, lot 2, migration 0032).

Une saisie faite hors connexion est renvoyée automatiquement au retour du réseau, parfois plusieurs
fois. Ces tests prouvent qu'un renvoi ne crée jamais de doublon, qu'une clé réutilisée pour d'autres
données est refusée, que la création SANS clé est inchangée, et que la clé est propre à chaque école.
"""

import uuid
from datetime import date

from httpx import AsyncClient

from tests.conftest import assign_role, register_school
from tests.test_attendance import _setup_class_with_students
from tests.test_grades import _setup_class_with_two_subjects


async def _headers(client: AsyncClient, email: str, password: str = "SuperSecret123") -> dict:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _session_body(ctx: dict, session_date: date, key: str | None) -> dict:
    body = {"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "session_date": str(session_date)}
    if key is not None:
        body["idempotency_key"] = key
    return body


async def _class_sessions(client: AsyncClient, headers: dict, ctx: dict) -> list[dict]:
    response = await client.get(f"/api/v1/attendance-sessions?class_id={ctx['class']['id']}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _assessment_body(ctx: dict, key: str | None, name: str = "Devoir hors connexion") -> dict:
    body = {
        "class_subject_id": ctx["math_cs"]["id"],
        "academic_term_id": ctx["term"]["id"],
        "assessment_type_id": ctx["assessment_type"]["id"],
        "name": name,
        "max_score": 20,
        "weight": 1,
        "assessment_date": str(date(2026, 10, 1)),
    }
    if key is not None:
        body["idempotency_key"] = key
    return body


async def _subject_assessments(client: AsyncClient, headers: dict, ctx: dict) -> list[dict]:
    response = await client.get(f"/api/v1/assessments?class_subject_id={ctx['math_cs']['id']}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- Séances d'appel -----------------------------------------------------------------------------------
async def test_session_resent_with_same_key_is_created_once(client: AsyncClient) -> None:
    data = await register_school(client, "idemsession")
    headers = await _headers(client, data["user"]["email"])
    ctx = await _setup_class_with_students(client, headers, data["school"]["id"])
    key = f"offline-{uuid.uuid4()}"

    first = await client.post("/api/v1/attendance-sessions", json=_session_body(ctx, date(2026, 10, 1), key), headers=headers)
    again = await client.post("/api/v1/attendance-sessions", json=_session_body(ctx, date(2026, 10, 1), key), headers=headers)

    assert first.status_code == 201, first.text
    assert again.status_code == 201, again.text
    assert again.json()["id"] == first.json()["id"]
    assert len(await _class_sessions(client, headers, ctx)) == 1


async def test_session_key_reused_for_other_data_is_refused(client: AsyncClient) -> None:
    data = await register_school(client, "idemsessionconflict")
    headers = await _headers(client, data["user"]["email"])
    ctx = await _setup_class_with_students(client, headers, data["school"]["id"])
    key = f"offline-{uuid.uuid4()}"

    first = await client.post("/api/v1/attendance-sessions", json=_session_body(ctx, date(2026, 10, 1), key), headers=headers)
    other_date = await client.post(
        "/api/v1/attendance-sessions", json=_session_body(ctx, date(2026, 10, 2), key), headers=headers
    )

    assert first.status_code == 201, first.text
    assert other_date.status_code == 409
    assert len(await _class_sessions(client, headers, ctx)) == 1


async def test_session_without_key_keeps_previous_behaviour(client: AsyncClient) -> None:
    data = await register_school(client, "idemsessionnokey")
    headers = await _headers(client, data["user"]["email"])
    ctx = await _setup_class_with_students(client, headers, data["school"]["id"])

    for _ in range(2):
        response = await client.post(
            "/api/v1/attendance-sessions", json=_session_body(ctx, date(2026, 10, 1), None), headers=headers
        )
        assert response.status_code == 201, response.text

    assert len(await _class_sessions(client, headers, ctx)) == 2


async def test_session_key_is_scoped_to_the_school(client: AsyncClient) -> None:
    key = f"offline-{uuid.uuid4()}"
    ids = []
    for prefix in ("idemsessiona", "idemsessionb"):
        data = await register_school(client, prefix)
        headers = await _headers(client, data["user"]["email"])
        ctx = await _setup_class_with_students(client, headers, data["school"]["id"])
        response = await client.post(
            "/api/v1/attendance-sessions", json=_session_body(ctx, date(2026, 10, 1), key), headers=headers
        )
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])

    assert ids[0] != ids[1]


async def test_teacher_offline_roll_call_replayed_twice_stays_single(client: AsyncClient) -> None:
    """Parcours réel du lot 2 : l'enseignant affecté envoie deux fois (séance + présences), comme
    après une coupure pendant l'envoi. Une seule séance, un seul enregistrement par élève."""
    data = await register_school(client, "idemteacher")
    headers_admin = await _headers(client, data["user"]["email"])
    school_id = data["school"]["id"]
    ctx = await _setup_class_with_students(client, headers_admin, school_id)

    teacher_data = await register_school(client, "idemteacher-teacher")
    teacher_user_id = teacher_data["user"]["id"]
    await assign_role(teacher_user_id, "TEACHER", organization_id=data["organization"]["id"], school_id=school_id)
    assigned = await client.post(
        f"/api/v1/classes/{ctx['class']['id']}/teachers",
        json={"user_id": teacher_user_id, "subject_id": ctx["subject"]["id"]},
        headers=headers_admin,
    )
    assert assigned.status_code == 201, assigned.text
    headers_teacher = await _headers(client, teacher_data["user"]["email"])

    key = f"offline-{uuid.uuid4()}"
    records = [{"student_id": s["id"], "status": "ABSENT" if i == 0 else "PRESENT"} for i, s in enumerate(ctx["students"])]
    session_ids = set()
    for _ in range(2):
        session = await client.post(
            "/api/v1/attendance-sessions", json=_session_body(ctx, date(2026, 10, 1), key), headers=headers_teacher
        )
        assert session.status_code == 201, session.text
        session_ids.add(session.json()["id"])
        submitted = await client.post(
            "/api/v1/attendance-records",
            json={"session_id": session.json()["id"], "records": records},
            headers=headers_teacher,
        )
        assert submitted.status_code == 201, submitted.text

    assert len(session_ids) == 1
    saved = await client.get(f"/api/v1/attendance-records?session_id={session_ids.pop()}", headers=headers_teacher)
    assert saved.status_code == 200
    assert sorted(r["status"] for r in saved.json()) == sorted(r["status"] for r in records)


# --- Évaluations ---------------------------------------------------------------------------------------
async def test_assessment_resent_with_same_key_is_created_once(client: AsyncClient) -> None:
    data = await register_school(client, "idemassessment")
    headers = await _headers(client, data["user"]["email"])
    ctx = await _setup_class_with_two_subjects(client, headers, data["school"]["id"])
    key = f"offline-{uuid.uuid4()}"

    first = await client.post("/api/v1/assessments", json=_assessment_body(ctx, key), headers=headers)
    again = await client.post("/api/v1/assessments", json=_assessment_body(ctx, key), headers=headers)

    assert first.status_code == 201, first.text
    assert again.status_code == 201, again.text
    assert again.json()["id"] == first.json()["id"]
    assert len(await _subject_assessments(client, headers, ctx)) == 1


async def test_assessment_key_reused_for_other_data_is_refused(client: AsyncClient) -> None:
    data = await register_school(client, "idemassessmentconflict")
    headers = await _headers(client, data["user"]["email"])
    ctx = await _setup_class_with_two_subjects(client, headers, data["school"]["id"])
    key = f"offline-{uuid.uuid4()}"

    first = await client.post("/api/v1/assessments", json=_assessment_body(ctx, key), headers=headers)
    renamed = await client.post("/api/v1/assessments", json=_assessment_body(ctx, key, name="Autre devoir"), headers=headers)

    assert first.status_code == 201, first.text
    assert renamed.status_code == 409
    assert len(await _subject_assessments(client, headers, ctx)) == 1


async def test_assessment_without_key_keeps_previous_behaviour(client: AsyncClient) -> None:
    data = await register_school(client, "idemassessmentnokey")
    headers = await _headers(client, data["user"]["email"])
    ctx = await _setup_class_with_two_subjects(client, headers, data["school"]["id"])

    for _ in range(2):
        response = await client.post("/api/v1/assessments", json=_assessment_body(ctx, None), headers=headers)
        assert response.status_code == 201, response.text

    assert len(await _subject_assessments(client, headers, ctx)) == 2


async def test_short_idempotency_key_is_rejected(client: AsyncClient) -> None:
    data = await register_school(client, "idemshortkey")
    headers = await _headers(client, data["user"]["email"])
    ctx = await _setup_class_with_two_subjects(client, headers, data["school"]["id"])

    response = await client.post("/api/v1/assessments", json=_assessment_body(ctx, "court"), headers=headers)
    assert response.status_code == 422
