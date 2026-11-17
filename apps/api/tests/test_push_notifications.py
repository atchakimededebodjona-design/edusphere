"""Notifications téléphone (Web Push) des annonces — 2026-11-17.

- sans clés VAPID : rien n'est proposé ni envoyé ;
- un appareil ne s'enregistre que chez un service de notification connu, en HTTPS ;
- une annonce envoie la notification aux seuls appareils de ses destinataires, après la réponse ;
- un appareil disparu (404/410) est retiré ; un même navigateur ne sert qu'un compte ;
- les clés générées et le chiffrement fonctionnent réellement avec la bibliothèque d'envoi.
"""

import base64
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.tenancy import apply_tenant_context, set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.jobs.generate_push_keys import generate_key_pair
from app.modules.notifications import push
from app.modules.notifications.models import PushDevice
from tests.test_notifications import (
    _create_class,
    _create_student_in_class,
    _create_user_with_role,
    _link_parent,
    _setup_school,
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _browser_keys() -> dict[str, str]:
    """Clés d'un vrai navigateur abonné : point public P-256 et secret d'authentification."""
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"p256dh": _b64url(public), "auth": _b64url(uuid.uuid4().bytes)}


def _endpoint(tag: str) -> str:
    return f"https://fcm.googleapis.com/fcm/send/{tag}-{uuid.uuid4().hex}"


@pytest.fixture
def push_keys(monkeypatch: pytest.MonkeyPatch) -> str:
    public_key, private_key = generate_key_pair()
    monkeypatch.setattr(settings, "web_push_vapid_public_key", public_key)
    monkeypatch.setattr(settings, "web_push_vapid_private_key", private_key)
    monkeypatch.setattr(settings, "web_push_subject", "mailto:contact@edulinkage.test")
    return public_key


async def _register(client: AsyncClient, headers: dict, endpoint: str) -> int:
    response = await client.post("/api/v1/push/devices", json={"endpoint": endpoint, "keys": _browser_keys()}, headers=headers)
    return response.status_code


async def _devices() -> dict[str, uuid.UUID]:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        rows = (await db.execute(select(PushDevice.endpoint, PushDevice.user_id))).all()
        return {row.endpoint: row.user_id for row in rows}


async def test_without_keys_nothing_is_offered(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "pushoff")
    config = await client.get("/api/v1/push/config", headers=ctx["admin_headers"])
    assert config.status_code == 200 and config.json() == {"enabled": False, "public_key": None}
    assert await _register(client, ctx["admin_headers"], _endpoint("off")) == 409
    assert (await client.get("/api/v1/push/config")).status_code == 401


async def test_device_registration_only_accepts_known_push_services(client: AsyncClient, push_keys: str) -> None:
    ctx = await _setup_school(client, "pushreg")
    config = (await client.get("/api/v1/push/config", headers=ctx["admin_headers"])).json()
    assert config == {"enabled": True, "public_key": push_keys}
    for good in (
        _endpoint("chrome"),
        f"https://updates.push.services.mozilla.com/wpush/v2/{uuid.uuid4().hex}",
        f"https://web.push.apple.com/{uuid.uuid4().hex}",
        f"https://wns2-par02p.notify.windows.com/w/?token={uuid.uuid4().hex}",
    ):
        assert await _register(client, ctx["admin_headers"], good) == 204, good
    for bad in (
        "http://fcm.googleapis.com/fcm/send/x",  # pas de HTTPS
        "https://evil.example.com/fcm.googleapis.com/x",
        "https://fcm.googleapis.com.evil.example/x",
        "https://user:pass@fcm.googleapis.com/fcm/send/x",
        "https://fcm.googleapis.com:8443/fcm/send/x",
        "https://127.0.0.1/fcm/send/x",
        "https://api:8000/api/v1/health",
    ):
        assert await _register(client, ctx["admin_headers"], bad) == 422, bad


async def test_one_browser_serves_one_account_and_can_be_forgotten(client: AsyncClient, push_keys: str) -> None:
    ctx = await _setup_school(client, "pushmove")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "teacher.pushmove")
    endpoint = _endpoint("shared")
    assert await _register(client, ctx["admin_headers"], endpoint) == 204
    assert await _register(client, teacher["headers"], endpoint) == 204  # même poste, autre compte
    assert (await _devices())[endpoint] == uuid.UUID(teacher["user"]["id"])

    # L'administrateur ne peut pas retirer l'appareil d'un autre compte.
    await client.post("/api/v1/push/devices/remove", json={"endpoint": endpoint}, headers=ctx["admin_headers"])
    assert endpoint in await _devices()
    removed = await client.post("/api/v1/push/devices/remove", json={"endpoint": endpoint}, headers=teacher["headers"])
    assert removed.status_code == 204 and endpoint not in await _devices()


async def test_row_level_security_hides_other_accounts_devices(client: AsyncClient, push_keys: str) -> None:
    ctx = await _setup_school(client, "pushrls")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "teacher.pushrls")
    teacher_endpoint = _endpoint("rls")
    assert await _register(client, teacher["headers"], teacher_endpoint) == 204
    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(ctx["admin_user_id"]))  # même école, autre compte
        rows = (await db.execute(select(PushDevice).where(PushDevice.endpoint == teacher_endpoint))).all()
        assert rows == []
        await db.rollback()


async def test_announcement_pushes_only_to_recipients_and_drops_gone_devices(
    client: AsyncClient, push_keys: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = await _setup_school(client, "pushsend")
    school_class = await _create_class(client, ctx, "ps1")
    student = await _create_student_in_class(client, ctx, school_class, "ps1")
    parent = await _link_parent(client, ctx, student, "parent.pushsend")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "teacher.pushsend")
    teacher_phone, teacher_old_phone, parent_phone = _endpoint("tphone"), _endpoint("told"), _endpoint("pphone")
    for headers, endpoint in ((teacher["headers"], teacher_phone), (teacher["headers"], teacher_old_phone), (parent["headers"], parent_phone)):
        assert await _register(client, headers, endpoint) == 204

    calls: list[tuple[str, str]] = []

    def fake_deliver(endpoint: str, p256dh: str, auth: str, data: str) -> int:
        calls.append((endpoint, data))
        return 410 if endpoint == teacher_old_phone else 201

    monkeypatch.setattr(push, "_deliver", fake_deliver)
    response = await client.post(
        "/api/v1/announcements",
        json={"school_id": ctx["school"]["id"], "title": "Conseil de classe", "body": "Jeudi 15 h", "target_type": "SCHOOL", "audience": "TEACHERS"},
        headers=ctx["admin_headers"],
    )
    assert response.status_code == 201 and response.json() == {"recipient_count": 1}
    assert sorted(endpoint for endpoint, _ in calls) == sorted([teacher_phone, teacher_old_phone])  # jamais le parent
    assert '"title": "Nouvelle annonce — ' in calls[0][1] and "Conseil de classe — Jeudi 15 h" in calls[0][1]
    devices = await _devices()
    assert teacher_old_phone not in devices  # 410 : appareil retiré
    assert teacher_phone in devices and parent_phone in devices
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        sent_at = await db.scalar(select(PushDevice.last_sent_at).where(PushDevice.endpoint == teacher_phone))
        assert sent_at is not None


async def test_generated_keys_really_sign_and_encrypt(monkeypatch: pytest.MonkeyPatch, push_keys: str) -> None:
    """Sans réseau : la bibliothèque d'envoi chiffre avec les clés du navigateur et signe avec la clé
    VAPID générée ; on intercepte la requête au service de notification."""
    import pywebpush

    captured: dict = {}

    class FakeResponse:
        status_code = 201
        reason = "Created"
        headers: dict[str, str] = {}
        text = ""

    def fake_post(url: str, data=None, headers=None, timeout=None, **_kwargs):
        captured.update(url=url, data=data, headers=headers, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(pywebpush.requests, "post", fake_post)
    endpoint = _endpoint("real")
    keys = _browser_keys()
    status = push._deliver(endpoint, keys["p256dh"], keys["auth"], '{"title": "x", "body": "y"}')
    assert status == 201
    assert captured["url"] == endpoint
    assert captured["headers"]["content-encoding"] == "aes128gcm"
    assert str(captured["headers"]["ttl"]) == str(push.PUSH_TTL_SECONDS)
    assert f"k={push_keys}" in captured["headers"]["authorization"]
    assert b"title" not in captured["data"]  # contenu chiffré, jamais en clair


def test_payload_is_short_and_points_to_the_inbox() -> None:
    payload = push.announcement_payload("Collège Lumière", "Réunion", "x" * 500)
    assert payload["title"] == "Nouvelle annonce — Collège Lumière"
    assert len(payload["body"]) == push.PUSH_BODY_MAX_CHARS and payload["body"].endswith("…")
    assert payload["url"] == "/open-notifications"


def test_generate_push_keys_writes_nothing_when_keys_exist(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from app.jobs import generate_push_keys

    monkeypatch.setenv("WEB_PUSH_VAPID_PUBLIC_KEY", "deja-la")
    assert generate_push_keys.main() == 0
    assert capsys.readouterr().out == ""
    monkeypatch.delenv("WEB_PUSH_VAPID_PUBLIC_KEY")
    monkeypatch.delenv("WEB_PUSH_VAPID_PRIVATE_KEY", raising=False)
    assert generate_push_keys.main() == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("WEB_PUSH_")]
    assert [line.split("=", 1)[0] for line in lines] == ["WEB_PUSH_VAPID_PUBLIC_KEY", "WEB_PUSH_VAPID_PRIVATE_KEY"]
    assert len(base64.urlsafe_b64decode(lines[0].split("=", 1)[1] + "==")) == 65
