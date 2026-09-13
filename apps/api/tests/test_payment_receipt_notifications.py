"""Sprint 1.7 — audit et fiabilisation des flux email : reçu de paiement par email.

Ce flux (`fees/service.py::_prepare_payment_notifications` / `send_payment_notifications`,
déclenché par `POST /payments`) n'avait jusqu'ici AUCUNE couverture de test dédiée — seul le
téléchargement du reçu PDF était testé (`test_fees.py`). Ce fichier comble ce manque, à l'échelle
proportionnée à ce qui manquait réellement (pas une réplique du dépôt exhaustif déjà existant
pour les bulletins, `test_report_cards_notifications.py`, dont le motif est repris ici).

`LocalEmailProvider` isolée par test via `tmp_path` + `monkeypatch`, même convention que
`test_email.py`/`test_report_cards_notifications.py`.
"""

from pathlib import Path

import pytest
from httpx import AsyncClient

import app.core.email as email_module
from app.core.email import LocalEmailProvider
from tests.conftest import unique_email
from tests.test_fees import _full_fee_setup, _payment_payload


def _read_emails(directory: Path) -> list[str]:
    return [f.read_text(encoding="utf-8") for f in directory.glob("*.txt")]


async def _add_guardian_with_email(client: AsyncClient, ctx: dict, *, full_name: str, email: str | None) -> dict:
    guardian = (
        await client.post(
            "/api/v1/guardians",
            json={"school_id": ctx["school"]["id"], "full_name": full_name, "relationship_type": "mother", "email": email},
            headers=ctx["admin_headers"],
        )
    ).json()
    await client.post(
        f"/api/v1/students/{ctx['student']['id']}/guardians",
        json={"guardian_id": guardian["id"]},
        headers=ctx["admin_headers"],
    )
    return guardian


# --- A : tuteur avec email -> reçu envoyé, contenu correct ------------------------------------------------
async def test_payment_notifies_guardian_with_email_and_correct_content(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    ctx = await _full_fee_setup(client, "payrcpt-a")
    guardian_email = unique_email("guardian.payrcpt-a")
    await _add_guardian_with_email(client, ctx, full_name="Maman Reçu", email=guardian_email)

    response = await client.post(
        "/api/v1/payments", json=_payment_payload(ctx, 50000), headers=ctx["admin_headers"]
    )
    assert response.status_code == 201, response.text
    payment = response.json()

    emails = _read_emails(tmp_path)
    assert len(emails) == 1
    body = emails[0]
    assert f"To: {guardian_email}" in body
    assert "50000" in body  # montant correct
    assert payment["receipt_number"] in body  # référence correcte
    assert ctx["student"]["first_name"] in body and ctx["student"]["last_name"] in body


# --- B : tuteur sans email -> aucun envoi, paiement toujours enregistré ------------------------------------
async def test_payment_sends_nothing_for_guardian_without_email(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    ctx = await _full_fee_setup(client, "payrcpt-b")
    await _add_guardian_with_email(client, ctx, full_name="Sans Email", email=None)

    response = await client.post(
        "/api/v1/payments", json=_payment_payload(ctx, 50000), headers=ctx["admin_headers"]
    )
    assert response.status_code == 201, response.text
    assert _read_emails(tmp_path) == []


# --- C : échec du provider email -> le paiement reste enregistré (best-effort) -----------------------------
async def test_payment_succeeds_even_when_email_provider_fails(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingProvider:
        async def send(self, to: str, subject: str, body: str) -> None:
            raise RuntimeError("SMTP down (simulé)")

    monkeypatch.setattr(email_module, "email_provider", FailingProvider())
    ctx = await _full_fee_setup(client, "payrcpt-c")
    await _add_guardian_with_email(client, ctx, full_name="Maman Test", email=unique_email("guardian.payrcpt-c"))

    response = await client.post(
        "/api/v1/payments", json=_payment_payload(ctx, 50000), headers=ctx["admin_headers"]
    )
    # Le paiement (donnée métier déjà committée avant tout envoi) n'est jamais affecté par un
    # échec d'envoi — best-effort, voir fees/service.py::record_payment (commit puis envoi).
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "COMPLETED"


# --- D : isolation tenant — jamais de fuite entre écoles ----------------------------------------------------
async def test_payment_never_notifies_guardians_of_another_school(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    ctx_a = await _full_fee_setup(client, "payrcpt-d-a")
    ctx_b = await _full_fee_setup(client, "payrcpt-d-b")
    email_a = unique_email("guardian.payrcpt-d-a")
    email_b = unique_email("guardian.payrcpt-d-b")
    await _add_guardian_with_email(client, ctx_a, full_name="Parent A", email=email_a)
    await _add_guardian_with_email(client, ctx_b, full_name="Parent B", email=email_b)

    await client.post("/api/v1/payments", json=_payment_payload(ctx_a, 10000), headers=ctx_a["admin_headers"])
    await client.post("/api/v1/payments", json=_payment_payload(ctx_b, 20000), headers=ctx_b["admin_headers"])

    emails = _read_emails(tmp_path)
    assert len(emails) == 2
    email_to_a = next(e for e in emails if email_a in e)
    email_to_b = next(e for e in emails if email_b in e)
    assert "10000" in email_to_a and "20000" not in email_to_a
    assert "20000" in email_to_b and "10000" not in email_to_b
    assert email_b not in email_to_a
    assert email_a not in email_to_b


# --- E : resoumission avec la même idempotency_key -> pas de second envoi -----------------------------------
async def test_duplicate_payment_submission_does_not_send_a_second_email(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    ctx = await _full_fee_setup(client, "payrcpt-e")
    await _add_guardian_with_email(client, ctx, full_name="Maman Test", email=unique_email("guardian.payrcpt-e"))
    payload = _payment_payload(ctx, 50000)

    first = await client.post("/api/v1/payments", json=payload, headers=ctx["admin_headers"])
    assert first.status_code == 201, first.text
    assert len(_read_emails(tmp_path)) == 1

    # Même idempotency_key : `record_payment` renvoie le paiement déjà existant sans nouvelle
    # notification (voir fees/service.py — liste de notifications vide sur ce chemin).
    second = await client.post("/api/v1/payments", json=payload, headers=ctx["admin_headers"])
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]
    assert len(_read_emails(tmp_path)) == 1
