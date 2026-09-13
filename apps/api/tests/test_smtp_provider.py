"""Tests du transport SMTP (Phase 16) — `SmtpEmailProvider` et la sélection de provider.

Aucun serveur SMTP externe réel n'est disponible dans cet environnement de test : les scénarios
"connexion refusée" et "timeout" utilisent un vrai socket TCP local contrôlé par ce fichier (pas
un mock de `smtplib` — un échec réseau réel, reproductible, déterministe). Le scénario
"authentification échouée" nécessite d'atteindre l'étape `smtp.login()` du protocole, ce qu'un
socket brut ne suffit pas à simuler simplement — `smtplib.SMTP` y est remplacé par un faux
contrôlé (documenté comme tel, pas présenté comme une vraie connexion) qui lève exactement
l'exception que produirait un vrai serveur SMTP rejetant des identifiants
(`smtplib.SMTPAuthenticationError`).

RÈGLE DE VÉRITÉ : aucun de ces tests ne prouve qu'un email atteint une vraie boîte mail externe.
Voir docs/phases/PHASE_16_IMPLEMENTATION.md, section 10, pour l'affirmation explicite :
"REAL EXTERNAL SMTP DELIVERY NOT VERIFIED" dans cet environnement.
"""

import smtplib
import socket
import threading
from email.message import EmailMessage

import pytest

import app.core.email as email_module
from app.core.config import settings
from app.core.email import SmtpEmailProvider, get_email_provider, send_email_best_effort


def _unused_tcp_port() -> int:
    """Port TCP local libre au moment de l'appel — lié puis immédiatement refermé, pour que
    rien n'y écoute (garantit une connexion refusée, pas juste "probablement" libre)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _BlackholeSmtpServer:
    """Serveur TCP minimal (bibliothèque standard uniquement) qui accepte une connexion et ne
    répond jamais — force `smtplib` à dépasser son délai, pour tester un vrai timeout réseau sans
    dépendre d'un service externe indisponible dans cet environnement.

    La connexion acceptée est conservée sur `self._conn` (pas une variable locale au thread) :
    sinon CPython la ferme dès la fin de `_accept_and_hang` (garbage collection par comptage de
    références), ce qui envoie un FIN au client et produit `SMTPServerDisconnected` immédiat au
    lieu d'un vrai dépassement de délai — bug constaté et corrigé pendant l'écriture de ce test."""

    def __init__(self) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen(1)
        self.port = self._socket.getsockname()[1]
        self._conn: socket.socket | None = None
        self._thread = threading.Thread(target=self._accept_and_hang, daemon=True)
        self._thread.start()

    def _accept_and_hang(self) -> None:
        try:
            self._conn, _ = self._socket.accept()
        except OSError:
            pass  # socket fermé pendant l'attente (fin de test) — attendu, pas une erreur de test

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
        self._socket.close()


# --- Configuration invalide -----------------------------------------------------------------
def test_get_email_provider_smtp_rejects_empty_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "smtp_host", "")
    with pytest.raises(ValueError, match="SMTP_HOST"):
        get_email_provider("smtp", "./unused")


def test_get_email_provider_smtp_accepts_valid_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "smtp_host", "smtp.example-test.invalid")
    provider = get_email_provider("smtp", "./unused")
    assert isinstance(provider, SmtpEmailProvider)


# --- Serveur SMTP inaccessible (connexion refusée réelle) -----------------------------------
async def test_smtp_provider_raises_on_connection_refused() -> None:
    closed_port = _unused_tcp_port()
    provider = SmtpEmailProvider(
        host="127.0.0.1",
        port=closed_port,
        username="",
        password="",
        from_address="no-reply@example-test.invalid",
        use_tls=False,
        timeout_seconds=2,
    )
    with pytest.raises(OSError):
        await provider.send("someone@example-test.invalid", "Sujet", "Corps")


# --- Timeout SMTP (réel, via un socket qui n'accepte jamais de répondre) --------------------
async def test_smtp_provider_raises_on_timeout() -> None:
    server = _BlackholeSmtpServer()
    try:
        provider = SmtpEmailProvider(
            host="127.0.0.1",
            port=server.port,
            username="",
            password="",
            from_address="no-reply@example-test.invalid",
            use_tls=False,
            timeout_seconds=1,
        )
        # `smtplib.getreply()` capture le `TimeoutError` brut du socket et le re-lève sous forme
        # de `SMTPServerDisconnected` (comportement réel constaté, pas supposé — voir la
        # trace obtenue lors de l'écriture de ce test) : on vérifie le type réellement levé par
        # smtplib ET que le message porte bien la trace du dépassement de délai sous-jacent, pas
        # une déconnexion pour une autre raison.
        with pytest.raises(smtplib.SMTPServerDisconnected, match="timed out"):
            await provider.send("someone@example-test.invalid", "Sujet", "Corps")
    finally:
        server.close()


# --- Authentification SMTP échouée (faux SMTP contrôlé, documenté comme tel) ----------------
async def test_smtp_provider_propagates_authentication_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeSmtpRejectingAuth:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def starttls(self) -> None:
            pass

        def login(self, username: str, password: str) -> None:
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Authentication failed")

        def send_message(self, message) -> None:
            raise AssertionError("send_message ne doit jamais être atteint après un login refuse")

    monkeypatch.setattr(smtplib, "SMTP", _FakeSmtpRejectingAuth)

    provider = SmtpEmailProvider(
        host="smtp.example-test.invalid",
        port=587,
        username="test-user-placeholder",
        password="test-password-placeholder",
        from_address="no-reply@example-test.invalid",
        use_tls=True,
        timeout_seconds=2,
    )

    with pytest.raises(smtplib.SMTPAuthenticationError):
        await provider.send("someone@example-test.invalid", "Sujet", "Corps")


# --- Sprint 1.7.1 : nom d'affichage de l'expéditeur (From) ----------------------------------
class _FakeSmtpCapturingMessage:
    """Faux SMTP (même motif que `_FakeSmtpRejectingAuth` ci-dessus) qui n'échoue jamais mais
    capture le message tel qu'il serait réellement transmis sur le fil SMTP (`as_bytes()`), pour
    vérifier le header `From` sans dépendre d'un vrai serveur externe. Note : `message["From"]`
    (accès par clé) renvoie la forme décodée lisible par un humain, PAS la forme transmise —
    `EmailMessage` utilise la politique moderne (`email.policy.default`) qui ne ré-encode en RFC
    2047 qu'au moment de la sérialisation réelle (`as_bytes`/`as_string`, ce que fait
    `smtplib.send_message` en interne). Vérifier uniquement l'accès par clé masquerait un bug
    d'encodage qui n'apparaîtrait que sur le vrai fil SMTP."""

    captured_wire: str | None = None

    def __init__(self, host: str, port: int, timeout: int) -> None:
        pass

    def __enter__(self) -> "_FakeSmtpCapturingMessage":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def starttls(self) -> None:
        pass

    def login(self, username: str, password: str) -> None:
        pass

    def send_message(self, message: EmailMessage) -> None:
        type(self).captured_wire = message.as_bytes().decode("utf-8", errors="replace")


async def test_smtp_provider_from_header_uses_display_name_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP", _FakeSmtpCapturingMessage)
    provider = SmtpEmailProvider(
        host="smtp.example-test.invalid",
        port=587,
        username="",
        password="",
        from_address="no-reply@edulinkage.com",
        use_tls=True,
        timeout_seconds=2,
        from_name="EduLinkage",
    )
    await provider.send("someone@example-test.invalid", "Sujet", "Corps")

    # Format Gmail attendu explicitement (voir contexte Sprint 1.7.1) : nom d'affichage, adresse
    # réelle intacte entre chevrons — jamais l'adresse seule ni "no-reply" comme nom.
    wire = _FakeSmtpCapturingMessage.captured_wire
    assert wire is not None
    assert "From: EduLinkage <no-reply@edulinkage.com>\n" in wire


async def test_smtp_provider_from_header_falls_back_to_address_alone_without_from_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Régression : `from_name=""` (valeur par défaut, environnements existants non reconfigurés)
    doit produire l'adresse seule — jamais une reconstitution du nom d'affichage à partir de la
    partie locale de l'adresse (ex. "no-reply") ni de chevrons vides."""
    monkeypatch.setattr(smtplib, "SMTP", _FakeSmtpCapturingMessage)
    provider = SmtpEmailProvider(
        host="smtp.example-test.invalid",
        port=587,
        username="",
        password="",
        from_address="no-reply@edulinkage.com",
        use_tls=True,
        timeout_seconds=2,
    )
    await provider.send("someone@example-test.invalid", "Sujet", "Corps")

    wire = _FakeSmtpCapturingMessage.captured_wire
    assert wire is not None
    assert "From: no-reply@edulinkage.com\n" in wire
    assert "<" not in wire.split("\n", 1)[0]


async def test_smtp_provider_from_header_encodes_unicode_display_name_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    """Confirme que `formataddr` (RFC 2047), pas une concaténation manuelle, gère un nom
    d'affichage non-ASCII — pertinent si l'orthographe francophone du nom change un jour."""
    monkeypatch.setattr(smtplib, "SMTP", _FakeSmtpCapturingMessage)
    provider = SmtpEmailProvider(
        host="smtp.example-test.invalid",
        port=587,
        username="",
        password="",
        from_address="no-reply@edulinkage.com",
        use_tls=True,
        timeout_seconds=2,
        from_name="Édu Linkage",
    )
    await provider.send("someone@example-test.invalid", "Sujet", "Corps")

    wire = _FakeSmtpCapturingMessage.captured_wire
    assert wire is not None
    from_line = wire.split("\n", 1)[0]
    assert "no-reply@edulinkage.com" in from_line
    assert "Édu Linkage" not in from_line  # encodé RFC 2047, jamais les octets bruts sur le fil
    assert "=?utf-8?" in from_line.lower()


def test_get_email_provider_wires_smtp_from_name_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "smtp_host", "smtp.example-test.invalid")
    monkeypatch.setattr(settings, "smtp_from_address", "no-reply@edulinkage.com")
    monkeypatch.setattr(settings, "smtp_from_name", "EduLinkage")

    provider = get_email_provider("smtp", "./unused")

    assert isinstance(provider, SmtpEmailProvider)
    assert provider._from_name == "EduLinkage"
    assert provider._from_address == "no-reply@edulinkage.com"


# --- Aucun secret dans les logs, y compris en cas d'échec ------------------------------------
async def test_send_email_best_effort_never_logs_the_smtp_password(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    fake_password = "S3cr3t-Placeholder-Never-Real"  # noqa: S105 - placeholder de test, jamais un vrai secret
    closed_port = _unused_tcp_port()
    failing_provider = SmtpEmailProvider(
        host="127.0.0.1",
        port=closed_port,
        username="test-user-placeholder",
        password=fake_password,
        from_address="no-reply@example-test.invalid",
        use_tls=False,
        timeout_seconds=2,
    )
    monkeypatch.setattr(email_module, "email_provider", failing_provider)

    with caplog.at_level("WARNING"):
        # best-effort : ne doit jamais lever, même si la connexion échoue.
        await send_email_best_effort("someone@example-test.invalid", "Sujet", "Corps")

    assert fake_password not in caplog.text
    assert "test-user-placeholder" not in caplog.text
