"""Revue de sécurité du 2026-11-17 :
- un nouveau mot de passe ferme toutes les sessions ouvertes du compte ;
- les échecs de connexion sont aussi comptés par adresse IP (« password spraying ») ;
- un nouveau mot de passe fait au moins 12 caractères et n'est pas un mot de passe courant ;
- les modèles de bulletin ne peuvent plus faire charger de fichier ni d'adresse au serveur ;
- le nom d'un document téléchargé ne peut plus casser l'en-tête de téléchargement.
"""

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.passwords import password_problem
from app.modules.report_cards.service import _only_embedded_resources, html_to_pdf
from app.modules.students.router import attachment_disposition
from tests.conftest import register_school, unique_email


async def _forgot(client: AsyncClient, email: str) -> str:
    response = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert response.status_code == 202
    return response.json()["dev_token"]


async def test_password_reset_closes_every_open_session(client: AsyncClient) -> None:
    data = await register_school(client, "resetsessions")
    email = data["user"]["email"]
    second = await client.post("/api/v1/auth/login", json={"email": email, "password": "SuperSecret123"})
    assert second.status_code == 200
    stolen_refresh = second.json()["refresh_token"]
    other_token = await _forgot(client, email)
    token = await _forgot(client, email)

    reset = await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "TresLongMotDePasse9"})
    assert reset.status_code == 204
    for refresh in (data["tokens"]["refresh_token"], stolen_refresh):
        assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})).status_code == 401
    # Une autre demande de réinitialisation encore ouverte ne sert plus à rien.
    reuse = await client.post("/api/v1/auth/reset-password", json={"token": other_token, "new_password": "EncoreUnAutre9876"})
    assert reuse.status_code == 400
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "TresLongMotDePasse9"})
    assert login.status_code == 200


async def test_failed_logins_are_also_limited_per_ip(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    data = await register_school(client, "ipspray")
    monkeypatch.setattr(settings, "login_ip_rate_limit_max_failures", 3)
    # Un mot de passe courant essayé sur des comptes DIFFÉRENTS : chaque email ne voit qu'un échec.
    for _ in range(3):
        response = await client.post("/api/v1/auth/login", json={"email": unique_email("spray"), "password": "Password123"})
        assert response.status_code == 401
    blocked = await client.post("/api/v1/auth/login", json={"email": unique_email("spray"), "password": "Password123"})
    assert blocked.status_code == 429 and blocked.headers.get("retry-after")
    # Même un bon mot de passe est refusé depuis cette adresse jusqu'à la fin de la fenêtre.
    good = await client.post("/api/v1/auth/login", json={"email": data["user"]["email"], "password": "SuperSecret123"})
    assert good.status_code == 429


async def test_successful_logins_do_not_count_against_the_ip(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    data = await register_school(client, "ipok")
    monkeypatch.setattr(settings, "login_ip_rate_limit_max_failures", 2)
    for _ in range(4):
        response = await client.post("/api/v1/auth/login", json={"email": data["user"]["email"], "password": "SuperSecret123"})
        assert response.status_code == 200


@pytest.mark.parametrize(
    ("password", "accepted"),
    [
        ("Court123456", False),  # 11 caractères
        ("aaaaaaaaaaaaaaaa", False),
        ("Motdepasse123", False),
        ("AZERTYUIOP12", False),
        ("EduLinkage2026", False),
        ("x" * 129, False),
        ("CheveuxDeLune7", True),
        ("douze-car-ok", True),
    ],
)
def test_new_password_rule(password: str, accepted: bool) -> None:
    assert (password_problem(password) is None) is accepted


async def test_reset_password_refuses_weak_passwords(client: AsyncClient) -> None:
    data = await register_school(client, "weakreset")
    token = await _forgot(client, data["user"]["email"])
    for weak in ("Court123456", "Motdepasse123"):
        response = await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": weak})
        assert response.status_code == 422, weak
    accepted = await client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "CheveuxDeLune7"})
    assert accepted.status_code == 204


def test_report_card_pdf_never_loads_files_or_urls() -> None:
    for uri in ("file:///etc/passwd", "/etc/passwd", "http://169.254.169.254/latest/meta-data", "https://example.org/x.png"):
        assert _only_embedded_resources(uri, "") == "", uri
    embedded = "data:image/png;base64,iVBORw0KGgo="
    assert _only_embedded_resources(embedded, "") == embedded
    pdf = html_to_pdf('<html><body><p>Bulletin</p><img src="file:///etc/passwd"/><img src="http://127.0.0.1:1/x.png"/></body></html>')
    assert pdf.startswith(b"%PDF")


@pytest.mark.parametrize(
    ("name", "ascii_part"),
    [
        ("bulletin.pdf", 'filename="bulletin.pdf"'),
        ('a"b.pdf', 'filename="a_b.pdf"'),
        ("x\r\nSet-Cookie: pirate=1.pdf", 'filename="x__Set-Cookie: pirate=1.pdf"'),
        ("Relevé élève.pdf", 'filename="Relev_ _l_ve.pdf"'),
    ],
)
def test_attachment_disposition_is_always_a_single_safe_header(name: str, ascii_part: str) -> None:
    header = attachment_disposition(name)
    assert "\r" not in header and "\n" not in header
    assert header.startswith(f"attachment; {ascii_part}; filename*=UTF-8''")
