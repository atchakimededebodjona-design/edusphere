"""Sprint 1.8 — email d'absence pour les tuteurs SANS compte utilisateur.

Complète `test_attendance_notifications.py` (canal in-app, Phase 27 Sprint 1) sans le modifier —
même convention de duplication des fixtures que ce fichier (voir sa propre docstring : "aucun des
deux fichiers de test n'importe l'autre dans ce dépôt"). Réutilise le pattern déjà validé en
production pour les rappels de frais en retard (`test_overdue_fee_reminders_email.py`), adapté au
fait que ce flux est déclenché de façon synchrone dans la requête HTTP (pas un job batch) :
`POST /attendance-records` et `PATCH /attendance-records/{id}` envoient l'email directement,
aucune étape "_run_job_with_emails" séparée n'est nécessaire ici.

Un tuteur SANS compte utilisateur (`Guardian.user_id IS NULL`) mais avec une adresse email
renseignée reçoit un email quand un élève est marqué ABSENT — au maximum UN par
(student, guardian, absence_date). Un tuteur AVEC compte ne reçoit jamais d'email en plus de sa
notification in-app existante — canaux mutuellement exclusifs (même règle que les frais).
"""

import uuid
from datetime import date
from pathlib import Path

import pytest
from httpx import AsyncClient

import app.core.email as email_module
import app.modules.attendance.service as attendance_service
from app.core.email import LocalEmailProvider
from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.attendance.models import AttendanceAbsenceEmailReminder
from tests.conftest import register_school, unique_email

STANDARD_PASSWORD = "SuperSecret123"


async def _login(client: AsyncClient, email: str, password: str = STANDARD_PASSWORD) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _setup_class_with_students(client: AsyncClient, headers: dict, school_id: str, n_students: int = 1) -> dict:
    """Même contenu que test_attendance_notifications.py::_setup_class_with_students (dupliqué,
    même convention que ce fichier vis-à-vis de test_attendance.py)."""
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

    students = []
    for i in range(n_students):
        student = (
            await client.post(
                "/api/v1/students",
                json={
                    "school_id": school_id,
                    "matricule": f"S{suffix}{i:03d}",
                    "first_name": f"Eleve{i}",
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

    return {"year": year, "term": term, "level": level, "class": school_class, "students": students}


async def _create_session(client: AsyncClient, headers: dict, ctx: dict, session_date: date) -> dict:
    response = await client.post(
        "/api/v1/attendance-sessions",
        json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "session_date": str(session_date)},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _submit_record(client: AsyncClient, headers: dict, session_id: str, student_id: str, status: str) -> dict:
    response = await client.post(
        "/api/v1/attendance-records",
        json={"session_id": session_id, "records": [{"student_id": student_id, "status": status}]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()[0]


async def _patch_record(client: AsyncClient, headers: dict, record_id: str, **fields) -> dict:
    response = await client.patch(f"/api/v1/attendance-records/{record_id}", json=fields, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _setup(client: AsyncClient, prefix: str) -> dict:
    data = await register_school(client, prefix)
    admin_headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_class_with_students(client, admin_headers, data["school"]["id"])
    session = await _create_session(client, admin_headers, ctx, date(2026, 10, 1))
    return {
        "admin_headers": admin_headers,
        "school_id": data["school"]["id"],
        "organization_id": data["organization"]["id"],
        "ctx": ctx,
        "session": session,
    }


async def _link_parent(client: AsyncClient, env: dict, student_id: str, email_prefix: str, *, with_guardian_email: bool = False) -> dict:
    """Tuteur AVEC compte utilisateur — même pattern que test_attendance_notifications.py::
    _link_parent. `with_guardian_email=True` renseigne en plus `Guardian.email` (vérifie que le
    canal email n'intervient jamais pour ce cas, même règle de rigueur que
    test_overdue_fee_reminders_email.py::_link_parent_with_guardian_email)."""
    email = unique_email(email_prefix)
    parent = await client.post(
        "/api/v1/users",
        json={"email": email, "full_name": "Parent Test", "school_id": env["school_id"], "role_code": "PARENT"},
        headers=env["admin_headers"],
    )
    assert parent.status_code == 201, parent.text
    parent_data = parent.json()
    reset = await client.post(
        "/api/v1/auth/reset-password", json={"token": parent_data["dev_reset_token"], "new_password": "ParentPass123"}
    )
    assert reset.status_code == 204

    guardian_payload = {"school_id": env["school_id"], "full_name": "Tuteur Test", "relationship_type": "father"}
    if with_guardian_email:
        guardian_payload["email"] = unique_email(f"{email_prefix}.guardianemail")
    guardian = (
        await client.post("/api/v1/guardians", json=guardian_payload, headers=env["admin_headers"])
    ).json()
    link = await client.patch(
        f"/api/v1/guardians/{guardian['id']}", json={"user_id": parent_data["user"]["id"]}, headers=env["admin_headers"]
    )
    assert link.status_code == 200, link.text
    attach = await client.post(
        f"/api/v1/students/{student_id}/guardians", json={"guardian_id": guardian["id"]}, headers=env["admin_headers"]
    )
    assert attach.status_code == 201, attach.text

    token = await _login(client, email, "ParentPass123")
    return {"user": parent_data["user"], "guardian": guardian, "headers": {"Authorization": f"Bearer {token}"}}


async def _create_guardian_with_email(client: AsyncClient, env: dict, student_id: str, email_prefix: str) -> dict:
    """Tuteur SANS compte utilisateur mais avec une adresse email — cible du canal email."""
    email = unique_email(email_prefix)
    guardian = (
        await client.post(
            "/api/v1/guardians",
            json={"school_id": env["school_id"], "full_name": "Tuteur Email Test", "relationship_type": "mother", "email": email},
            headers=env["admin_headers"],
        )
    ).json()
    attach = await client.post(
        f"/api/v1/students/{student_id}/guardians", json={"guardian_id": guardian["id"]}, headers=env["admin_headers"]
    )
    assert attach.status_code == 201, attach.text
    return {"guardian": guardian, "email": email}


async def _create_guardian_without_account_or_email(client: AsyncClient, env: dict, student_id: str) -> dict:
    guardian = (
        await client.post(
            "/api/v1/guardians",
            json={"school_id": env["school_id"], "full_name": "Sans Rien", "relationship_type": "mother"},
            headers=env["admin_headers"],
        )
    ).json()
    await client.post(
        f"/api/v1/students/{student_id}/guardians", json={"guardian_id": guardian["id"]}, headers=env["admin_headers"]
    )
    return guardian


async def _list_notifications(client: AsyncClient, headers: dict) -> list[dict]:
    response = await client.get("/api/v1/notifications", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _read_emails(directory: Path) -> list[str]:
    return [f.read_text(encoding="utf-8") for f in directory.glob("*.txt")]


def _absence_emails(directory: Path) -> list[str]:
    """Filtre les emails d'absence (sujet `Absence signalée — ...`) parmi tous les fichiers écrits
    — d'autres helpers (ex. `_link_parent` crée un compte) déclenchent légitimement leurs propres
    emails (bienvenue), sans rapport avec ce canal."""
    return [content for content in _read_emails(directory) if "Subject: Absence signalée" in content]


async def _fetch_reminder_row(school_id: str, student_id: str, guardian_id: str, absence_date: date) -> AttendanceAbsenceEmailReminder:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        from sqlalchemy import select

        result = await db.execute(
            select(AttendanceAbsenceEmailReminder).where(
                AttendanceAbsenceEmailReminder.school_id == uuid.UUID(school_id),
                AttendanceAbsenceEmailReminder.student_id == uuid.UUID(student_id),
                AttendanceAbsenceEmailReminder.guardian_id == uuid.UUID(guardian_id),
                AttendanceAbsenceEmailReminder.absence_date == absence_date,
            )
        )
        return result.scalar_one()


# --- 1 : tuteur sans compte + email -> email envoyé ------------------------------------------------
async def test_guardian_without_account_with_email_receives_absence_email(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup(client, "absnemail-a")
    student = env["ctx"]["students"][0]
    guardian = await _create_guardian_with_email(client, env, student["id"], "guardian.absnemail-a")

    await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")

    emails = _absence_emails(tmp_path)
    assert len(emails) == 1
    assert guardian["email"] in emails[0]


# --- 2 : contenu email correct ----------------------------------------------------------------------
async def test_absence_email_content_is_correct(client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup(client, "absnemail-b")
    student = env["ctx"]["students"][0]
    guardian = await _create_guardian_with_email(client, env, student["id"], "guardian.absnemail-b")

    await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")

    emails = _absence_emails(tmp_path)
    assert len(emails) == 1
    body = emails[0]
    assert f"To: {guardian['email']}" in body
    assert "Eleve0" in body and "Test" in body
    assert "2026-10-01" in body
    assert "absent" in body.lower()


# --- 3 : tuteur sans compte ET sans email -> aucun email -------------------------------------------
async def test_guardian_without_account_and_without_email_receives_no_email(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup(client, "absnemail-c")
    student = env["ctx"]["students"][0]
    await _create_guardian_without_account_or_email(client, env, student["id"])

    response = await client.post(
        "/api/v1/attendance-records",
        json={"session_id": env["session"]["id"], "records": [{"student_id": student["id"], "status": "ABSENT"}]},
        headers=env["admin_headers"],
    )
    assert response.status_code == 201, response.text
    assert _absence_emails(tmp_path) == []


# --- 4 : tuteur avec compte -> notification in-app uniquement --------------------------------------
async def test_guardian_with_account_receives_only_in_app_notification(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup(client, "absnemail-d")
    student = env["ctx"]["students"][0]
    parent = await _link_parent(client, env, student["id"], "parent.absnemail-d", with_guardian_email=True)

    await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")

    items = await _list_notifications(client, parent["headers"])
    assert len(items) == 1
    assert items[0]["type"] == "STUDENT_ABSENT"


# --- 5 : tuteur avec compte -> aucun email, même avec Guardian.email renseigné ----------------------
async def test_guardian_with_account_receives_no_email(client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup(client, "absnemail-e")
    student = env["ctx"]["students"][0]
    await _link_parent(client, env, student["id"], "parent.absnemail-e", with_guardian_email=True)

    await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")

    assert _absence_emails(tmp_path) == []


# --- 6 : PRESENT -> ABSENT -> un email --------------------------------------------------------------
async def test_present_to_absent_transition_sends_one_email(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup(client, "absnemail-f")
    student = env["ctx"]["students"][0]
    await _create_guardian_with_email(client, env, student["id"], "guardian.absnemail-f")

    record = await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "PRESENT")
    assert _absence_emails(tmp_path) == []

    await _patch_record(client, env["admin_headers"], record["id"], status="ABSENT")

    assert len(_absence_emails(tmp_path)) == 1


# --- 7 : ABSENT -> ABSENT (resoumission) -> aucun doublon -------------------------------------------
async def test_resubmitting_same_absent_status_does_not_duplicate_email(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup(client, "absnemail-g")
    student = env["ctx"]["students"][0]
    await _create_guardian_with_email(client, env, student["id"], "guardian.absnemail-g")

    await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")
    assert len(_absence_emails(tmp_path)) == 1

    await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")

    assert len(_absence_emails(tmp_path)) == 1


# --- 8 : ABSENT -> PRESENT -> aucun nouvel email ----------------------------------------------------
async def test_absent_to_present_sends_no_new_email(client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup(client, "absnemail-h")
    student = env["ctx"]["students"][0]
    await _create_guardian_with_email(client, env, student["id"], "guardian.absnemail-h")

    record = await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")
    assert len(_absence_emails(tmp_path)) == 1

    await _patch_record(client, env["admin_headers"], record["id"], status="PRESENT")

    assert len(_absence_emails(tmp_path)) == 1


# --- 9 : absence à une autre date -> nouvel email autorisé ------------------------------------------
async def test_absence_on_different_date_sends_new_email(client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup(client, "absnemail-i")
    student = env["ctx"]["students"][0]
    await _create_guardian_with_email(client, env, student["id"], "guardian.absnemail-i")

    await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")
    assert len(_absence_emails(tmp_path)) == 1

    other_session = await _create_session(client, env["admin_headers"], env["ctx"], date(2026, 10, 2))
    await _submit_record(client, env["admin_headers"], other_session["id"], student["id"], "ABSENT")

    assert len(_absence_emails(tmp_path)) == 2


# --- 10 : échec du provider SMTP -> l'absence reste enregistrée -------------------------------------
async def test_provider_failure_does_not_prevent_absence_recording(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingProvider:
        async def send(self, to: str, subject: str, body: str) -> None:
            raise RuntimeError("SMTP down (simulé)")

    monkeypatch.setattr(email_module, "email_provider", FailingProvider())
    env = await _setup(client, "absnemail-j")
    student = env["ctx"]["students"][0]
    await _create_guardian_with_email(client, env, student["id"], "guardian.absnemail-j")

    response = await client.post(
        "/api/v1/attendance-records",
        json={"session_id": env["session"]["id"], "records": [{"student_id": student["id"], "status": "ABSENT"}]},
        headers=env["admin_headers"],
    )
    assert response.status_code == 201, response.text
    assert response.json()[0]["status"] == "ABSENT"


# --- 11 : transport ACCEPTED correctement enregistré ------------------------------------------------
async def test_tracking_row_becomes_transport_accepted_on_successful_send(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup(client, "absnemail-k")
    student = env["ctx"]["students"][0]
    guardian = await _create_guardian_with_email(client, env, student["id"], "guardian.absnemail-k")

    await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")

    row = await _fetch_reminder_row(env["school_id"], student["id"], guardian["guardian"]["id"], date(2026, 10, 1))
    assert row.transport_status == "TRANSPORT_ACCEPTED"
    assert row.transport_checked_at is not None


# --- 12 : transport FAILED correctement enregistré --------------------------------------------------
async def test_tracking_row_becomes_transport_failed_on_provider_exception(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingProvider:
        async def send(self, to: str, subject: str, body: str) -> None:
            raise RuntimeError("SMTP down (simulé)")

    monkeypatch.setattr(email_module, "email_provider", FailingProvider())
    env = await _setup(client, "absnemail-l")
    student = env["ctx"]["students"][0]
    guardian = await _create_guardian_with_email(client, env, student["id"], "guardian.absnemail-l")

    await client.post(
        "/api/v1/attendance-records",
        json={"session_id": env["session"]["id"], "records": [{"student_id": student["id"], "status": "ABSENT"}]},
        headers=env["admin_headers"],
    )

    row = await _fetch_reminder_row(env["school_id"], student["id"], guardian["guardian"]["id"], date(2026, 10, 1))
    assert row.transport_status == "TRANSPORT_FAILED"
    assert row.transport_checked_at is not None


# --- 13 : idempotence avec répétition (même ligne, jamais recréée) ---------------------------------
async def test_repeated_submission_reuses_same_tracking_row(client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup(client, "absnemail-m")
    student = env["ctx"]["students"][0]
    guardian = await _create_guardian_with_email(client, env, student["id"], "guardian.absnemail-m")

    await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")
    row_first = await _fetch_reminder_row(env["school_id"], student["id"], guardian["guardian"]["id"], date(2026, 10, 1))

    await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")
    row_second = await _fetch_reminder_row(env["school_id"], student["id"], guardian["guardian"]["id"], date(2026, 10, 1))

    assert row_second.id == row_first.id
    assert len(_absence_emails(tmp_path)) == 1


# --- 14 : concurrence -> IntegrityError absorbée par le SAVEPOINT, jamais propagée ------------------
async def test_concurrent_duplicate_reminder_is_handled_via_savepoint(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Simule une course où la vérification applicative (`existing_absence_emailed_guardian_ids`)
    ne voit pas encore une ligne concurrente déjà présente en base (ex. deux requêtes quasi
    simultanées) : neutralisée ici pour forcer ce cas alors qu'une ligne existe déjà réellement
    (créée par une première soumission légitime) — seule la contrainte UNIQUE doit alors empêcher
    le doublon, absorbée par le SAVEPOINT (`_prepare_absence_emails`), jamais une exception
    propagée à l'appelant."""
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup(client, "absnemail-n")
    student = env["ctx"]["students"][0]
    await _create_guardian_with_email(client, env, student["id"], "guardian.absnemail-n")

    record = await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")
    assert len(_absence_emails(tmp_path)) == 1

    async def _always_empty(*args: object, **kwargs: object) -> set:
        return set()

    monkeypatch.setattr(attendance_service, "existing_absence_emailed_guardian_ids", _always_empty)

    # PRESENT puis ABSENT à nouveau : re-déclenche maybe_notify_absence (la règle anti-spam
    # ABSENT->ABSENT ne s'applique pas ici), avec la vérification applicative neutralisée.
    await _patch_record(client, env["admin_headers"], record["id"], status="PRESENT")
    response = await client.patch(
        f"/api/v1/attendance-records/{record['id']}", json={"status": "ABSENT"}, headers=env["admin_headers"]
    )
    assert response.status_code == 200, response.text  # jamais d'exception propagée

    # Toujours un seul email au total : la tentative de doublon a été absorbée silencieusement.
    assert len(_absence_emails(tmp_path)) == 1


# --- 15 : isolation tenant -------------------------------------------------------------------------
async def test_absence_email_never_crosses_tenants(client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env_a = await _setup(client, "absnemail-o-a")
    env_b = await _setup(client, "absnemail-o-b")
    student_a = env_a["ctx"]["students"][0]
    student_b = env_b["ctx"]["students"][0]
    guardian_a = await _create_guardian_with_email(client, env_a, student_a["id"], "guardian.absnemail-o-a")
    guardian_b = await _create_guardian_with_email(client, env_b, student_b["id"], "guardian.absnemail-o-b")

    await _submit_record(client, env_a["admin_headers"], env_a["session"]["id"], student_a["id"], "ABSENT")

    emails = _absence_emails(tmp_path)
    assert len(emails) == 1
    assert guardian_a["email"] in emails[0]
    assert guardian_b["email"] not in emails[0]

    # École B jamais touchée par une absence déclarée dans l'école A : aucune ligne de suivi créée.
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        from sqlalchemy import select

        result = await db.execute(
            select(AttendanceAbsenceEmailReminder).where(
                AttendanceAbsenceEmailReminder.school_id == uuid.UUID(env_b["school_id"])
            )
        )
        assert result.scalars().all() == []
