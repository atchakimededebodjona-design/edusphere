"""Notification email au parent — bulletin publié (Phase 11).

`LocalEmailProvider` isolée par test via `tmp_path` + `monkeypatch` sur
`app.core.email.email_provider`, même convention que test_email.py. Chaque test crée sa propre
école/élève/tuteur (self-contained, cohérent avec les conventions déjà établies) — la base de
test n'étant pas réinitialisée entre runs.
"""

from datetime import date
from pathlib import Path

import pytest
from httpx import AsyncClient

import app.core.email as email_module
from app.core.email import LocalEmailProvider
from tests.conftest import register_school, unique_email

MINIMAL_TEMPLATE = "<html><body><h1>{{ student.first_name }}</h1></body></html>"


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _read_emails(directory: Path) -> list[str]:
    return [f.read_text(encoding="utf-8") for f in directory.glob("*.txt")]


async def _setup_school(client: AsyncClient, prefix: str) -> dict:
    data = await register_school(client, prefix)
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    year = (
        await client.post(
            "/api/v1/academic-years",
            json={
                "school_id": school_id,
                "name": f"Annee-{prefix}",
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
                "name": f"Terme-{prefix}",
                "start_date": str(date(2026, 9, 1)),
                "end_date": str(date(2026, 12, 20)),
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
    student = (
        await client.post(
            "/api/v1/students",
            json={
                "school_id": school_id,
                "matricule": f"{prefix.upper()}1",
                "first_name": f"Eleve-{prefix}",
                "last_name": "Test",
                "date_of_birth": "2015-01-01",
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
    template = (
        await client.post(
            "/api/v1/report-card-templates",
            json={"school_id": school_id, "name": "Standard", "html_content": MINIMAL_TEMPLATE},
            headers=headers,
        )
    ).json()

    return {
        "headers": headers,
        "school_id": school_id,
        "term": term,
        "class": school_class,
        "student": student,
        "template": template,
    }


async def _add_guardian(client: AsyncClient, ctx: dict, *, full_name: str, email: str | None) -> dict:
    guardian = (
        await client.post(
            "/api/v1/guardians",
            json={"school_id": ctx["school_id"], "full_name": full_name, "relationship_type": "mother", "email": email},
            headers=ctx["headers"],
        )
    ).json()
    await client.post(
        f"/api/v1/students/{ctx['student']['id']}/guardians",
        json={"guardian_id": guardian["id"], "is_primary_contact": True},
        headers=ctx["headers"],
    )
    return guardian


async def _generate_report_card(client: AsyncClient, ctx: dict) -> dict:
    generated = (
        await client.post(
            "/api/v1/report-cards/generate",
            json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "template_id": ctx["template"]["id"]},
            headers=ctx["headers"],
        )
    ).json()
    return generated[0]


# --- 1 — un tuteur avec email --------------------------------------------------------------------
async def test_publish_notifies_single_guardian_with_email(client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    ctx = await _setup_school(client, "rcn1")
    guardian_email = unique_email("guardian.rcn1")
    await _add_guardian(client, ctx, full_name="Maman Test", email=guardian_email)
    report_card = await _generate_report_card(client, ctx)

    response = await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=ctx["headers"])
    assert response.status_code == 200

    emails = _read_emails(tmp_path)
    assert len(emails) == 1
    assert guardian_email in emails[0]
    assert "Eleve-rcn1" in emails[0]


# --- 2 — plusieurs tuteurs avec email --------------------------------------------------------------
async def test_publish_notifies_multiple_guardians_with_email(client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    ctx = await _setup_school(client, "rcn2")
    email_a = unique_email("guardian.rcn2a")
    email_b = unique_email("guardian.rcn2b")
    await _add_guardian(client, ctx, full_name="Maman Test", email=email_a)
    await _add_guardian(client, ctx, full_name="Papa Test", email=email_b)
    report_card = await _generate_report_card(client, ctx)

    await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=ctx["headers"])

    emails = _read_emails(tmp_path)
    assert len(emails) == 2
    all_content = "\n".join(emails)
    assert email_a in all_content
    assert email_b in all_content


# --- 3 — tuteur sans email -----------------------------------------------------------------------
async def test_publish_sends_nothing_for_guardian_without_email(client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    ctx = await _setup_school(client, "rcn3")
    await _add_guardian(client, ctx, full_name="Sans Email", email=None)
    report_card = await _generate_report_card(client, ctx)

    response = await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=ctx["headers"])
    assert response.status_code == 200
    assert _read_emails(tmp_path) == []


# --- 4 — plusieurs tuteurs, certains sans email ------------------------------------------------
async def test_publish_notifies_only_guardians_with_email(client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    ctx = await _setup_school(client, "rcn4")
    email_with = unique_email("guardian.rcn4with")
    await _add_guardian(client, ctx, full_name="Avec Email", email=email_with)
    await _add_guardian(client, ctx, full_name="Sans Email", email=None)
    report_card = await _generate_report_card(client, ctx)

    await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=ctx["headers"])

    emails = _read_emails(tmp_path)
    assert len(emails) == 1
    assert email_with in emails[0]


# --- 5 — aucun tuteur ------------------------------------------------------------------------------
async def test_publish_with_no_guardian_succeeds_without_email(client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    ctx = await _setup_school(client, "rcn5")
    report_card = await _generate_report_card(client, ctx)

    response = await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=ctx["headers"])
    assert response.status_code == 200
    assert response.json()["published_at"] is not None
    assert _read_emails(tmp_path) == []


# --- 6/7/8 — succès/échec EmailProvider, best-effort ---------------------------------------------
async def test_publish_succeeds_even_when_email_provider_fails(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingProvider:
        async def send(self, to: str, subject: str, body: str) -> None:
            raise RuntimeError("SMTP down")

    monkeypatch.setattr(email_module, "email_provider", FailingProvider())
    ctx = await _setup_school(client, "rcn6")
    await _add_guardian(client, ctx, full_name="Maman Test", email=unique_email("guardian.rcn6"))
    report_card = await _generate_report_card(client, ctx)

    response = await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=ctx["headers"])
    # La publication réussit malgré l'échec d'envoi (best-effort) — jamais d'erreur exposée.
    assert response.status_code == 200
    assert response.json()["status"] == "PUBLISHED"
    assert response.json()["published_at"] is not None


# --- 9/10 — isolation tenant/école : jamais de fuite entre écoles --------------------------------
async def test_publish_never_notifies_guardians_of_another_school(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    ctx_a = await _setup_school(client, "rcn9a")
    ctx_b = await _setup_school(client, "rcn9b")
    email_a = unique_email("guardian.rcn9a")
    email_b = unique_email("guardian.rcn9b")
    await _add_guardian(client, ctx_a, full_name="Parent A", email=email_a)
    await _add_guardian(client, ctx_b, full_name="Parent B", email=email_b)
    report_card_a = await _generate_report_card(client, ctx_a)
    report_card_b = await _generate_report_card(client, ctx_b)

    await client.post(f"/api/v1/report-cards/{report_card_a['id']}/publish", headers=ctx_a["headers"])
    await client.post(f"/api/v1/report-cards/{report_card_b['id']}/publish", headers=ctx_b["headers"])

    emails = _read_emails(tmp_path)
    assert len(emails) == 2
    email_to_a = next(e for e in emails if email_a in e)
    email_to_b = next(e for e in emails if email_b in e)
    assert "Eleve-rcn9a" in email_to_a and "Eleve-rcn9b" not in email_to_a
    assert "Eleve-rcn9b" in email_to_b and "Eleve-rcn9a" not in email_to_b


# --- 11 — bulletin non publié : aucun email --------------------------------------------------------
async def test_generating_without_publishing_sends_no_email(client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    ctx = await _setup_school(client, "rcn11")
    await _add_guardian(client, ctx, full_name="Maman Test", email=unique_email("guardian.rcn11"))
    report_card = await _generate_report_card(client, ctx)

    assert report_card["status"] == "DRAFT"
    assert _read_emails(tmp_path) == []  # la seule génération ne déclenche jamais d'envoi


# --- 12 — le bon destinataire reçoit l'email ------------------------------------------------------
async def test_email_sent_to_correct_recipient_address(client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    ctx = await _setup_school(client, "rcn12")
    correct_email = unique_email("guardian.rcn12correct")
    await _add_guardian(client, ctx, full_name="Bon Parent", email=correct_email)
    report_card = await _generate_report_card(client, ctx)

    await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=ctx["headers"])

    emails = _read_emails(tmp_path)
    assert len(emails) == 1
    assert f"To: {correct_email}" in emails[0]


# --- 13/14 — contenu minimal, absence de données sensibles ---------------------------------------
async def test_email_content_is_minimal_and_never_contains_sensitive_data(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    ctx = await _setup_school(client, "rcn13")
    await _add_guardian(client, ctx, full_name="Parent Discret", email=unique_email("guardian.rcn13"))
    report_card = await _generate_report_card(client, ctx)

    await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=ctx["headers"])

    emails = _read_emails(tmp_path)
    assert len(emails) == 1
    body = emails[0]
    # Contenu attendu minimal.
    assert "Eleve-rcn13" in body
    assert "Parent Discret" in body
    assert "Terme-rcn13" in body
    # Jamais de contenu sensible du bulletin.
    assert "moyenne" not in body.lower()
    assert "rang" not in body.lower()
    assert "appreciation" not in body.lower()
    assert "appréciation" not in body.lower()
    assert report_card["verification_code"] not in body


# --- 15 — republication : idempotence sans nouvelle table --------------------------------------
async def test_republishing_already_published_report_card_does_not_resend_email(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    ctx = await _setup_school(client, "rcn15")
    await _add_guardian(client, ctx, full_name="Maman Test", email=unique_email("guardian.rcn15"))
    report_card = await _generate_report_card(client, ctx)

    first = await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=ctx["headers"])
    assert first.status_code == 200
    assert len(_read_emails(tmp_path)) == 1

    # Appel /publish une seconde fois sur un bulletin déjà publié : pas de second envoi.
    second = await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=ctx["headers"])
    assert second.status_code == 200
    assert len(_read_emails(tmp_path)) == 1

    # Une régénération remet published_at à None : une republication qui suit redevient un
    # "premier" envoi (le contenu a changé) — comportement documenté, pas un bug.
    await _generate_report_card(client, ctx)
    third = await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=ctx["headers"])
    assert third.status_code == 200
    assert len(_read_emails(tmp_path)) == 2
