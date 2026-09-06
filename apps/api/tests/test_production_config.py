"""Phase 22 — validation de la configuration de production (secrets), étendue en Phase 23 aux
URLs publiques/CORS et à la configuration SMTP.

`validate_production_config` est appelée au chargement du module (voir app/core/config.py) : ces
tests l'exercent directement sur des instances `Settings` construites en mémoire plutôt qu'en
manipulant l'environnement réel du process de test, pour rester rapides et sans effet de bord.

Note Phase 23 : cet environnement de test (docker-compose/.env) définit réellement
`CORS_ALLOWED_ORIGINS`/`PUBLIC_BASE_URL`/`PUBLIC_WEB_BASE_URL` à des valeurs `localhost` (valeurs
de dev normales) — tout comme `JWT_SECRET_KEY` y est déjà réel (voir Phase 22). Chaque test qui
veut prouver un cas "tout est sûr, ne doit pas lever" doit donc surcharger explicitement CES
valeurs aussi, pas seulement les secrets — sinon le test masquerait un vrai bug en absorbant
silencieusement les valeurs `localhost` ambiantes du conteneur au lieu de les tester.
"""

import pytest

from app.core.config import ProductionConfigError, Settings, validate_production_config

_SAFE_SECRETS = {
    "jwt_secret_key": "a-real-random-secret-generated-for-this-deployment",
    "database_url": "postgresql+asyncpg://real_role:real_password@dbhost:5432/edusphere",
    "app_database_url": "postgresql+asyncpg://real_app_role:real_password@dbhost:5432/edusphere",
}
_SAFE_PUBLIC_URLS = {
    "cors_allowed_origins": "https://app.edusphere.example",
    "public_base_url": "https://api.edusphere.example",
    "public_web_base_url": "https://app.edusphere.example",
}


def test_production_rejects_default_jwt_secret() -> None:
    config = Settings(environment="production", jwt_secret_key="replace_with_a_long_random_secret")
    with pytest.raises(ProductionConfigError) as exc_info:
        validate_production_config(config)
    assert "jwt_secret_key" in str(exc_info.value)


def test_production_rejects_default_database_url() -> None:
    config = Settings(
        environment="production",
        jwt_secret_key="a-real-random-secret-generated-for-this-deployment",
        database_url="postgresql+asyncpg://edusphere:changeme_local_only@localhost:5432/edusphere",
        app_database_url="postgresql+asyncpg://real_app_role:real_password@dbhost:5432/edusphere",
    )
    with pytest.raises(ProductionConfigError) as exc_info:
        validate_production_config(config)
    assert "database_url" in str(exc_info.value)
    assert "app_database_url" not in str(exc_info.value)


def test_production_rejects_default_app_database_url() -> None:
    config = Settings(
        environment="production",
        jwt_secret_key="a-real-random-secret-generated-for-this-deployment",
        database_url="postgresql+asyncpg://real_role:real_password@dbhost:5432/edusphere",
        app_database_url="postgresql+asyncpg://edusphere_app:changeme_app_role_local_only@localhost:5432/edusphere",
    )
    with pytest.raises(ProductionConfigError) as exc_info:
        validate_production_config(config)
    assert "app_database_url" in str(exc_info.value)


def test_production_reports_all_unsafe_fields_at_once() -> None:
    # Les 3 marqueurs forcés explicitement plutôt que de compter sur les défauts de classe : cet
    # environnement de test (docker-compose) définit déjà un JWT_SECRET_KEY réel dans son .env,
    # ce qui masquerait ce cas si on se contentait de `Settings(environment="production")`.
    config = Settings(
        environment="production",
        jwt_secret_key="replace_with_a_long_random_secret",
        database_url="postgresql+asyncpg://edusphere:changeme_local_only@db:5432/edusphere",
        app_database_url="postgresql+asyncpg://edusphere_app:changeme_app_role_local_only@db:5432/edusphere",
    )
    with pytest.raises(ProductionConfigError) as exc_info:
        validate_production_config(config)
    message = str(exc_info.value)
    assert "jwt_secret_key" in message
    assert "database_url" in message
    assert "app_database_url" in message


def test_production_accepts_fully_overridden_secrets() -> None:
    config = Settings(environment="production", **_SAFE_SECRETS, **_SAFE_PUBLIC_URLS)
    validate_production_config(config)  # ne doit pas lever


def test_non_production_environments_are_never_checked() -> None:
    for environment in ("development", "test", "staging"):
        config = Settings(environment=environment, jwt_secret_key="replace_with_a_long_random_secret")
        validate_production_config(config)  # ne doit jamais lever hors "production"


def test_production_config_error_never_includes_the_secret_value() -> None:
    """Règle du projet : ne jamais afficher la valeur d'un secret, seulement son nom."""
    config = Settings(environment="production", jwt_secret_key="replace_with_a_long_random_secret")
    with pytest.raises(ProductionConfigError) as exc_info:
        validate_production_config(config)
    assert "replace_with_a_long_random_secret" not in str(exc_info.value)


# === Phase 23 — URLs publiques / CORS ===========================================================
def test_production_rejects_localhost_public_base_url() -> None:
    config = Settings(
        environment="production",
        **_SAFE_SECRETS,
        **{**_SAFE_PUBLIC_URLS, "public_base_url": "http://localhost:8000"},
    )
    with pytest.raises(ProductionConfigError) as exc_info:
        validate_production_config(config)
    assert "public_base_url" in str(exc_info.value)


def test_production_rejects_localhost_cors_allowed_origins() -> None:
    config = Settings(
        environment="production",
        **_SAFE_SECRETS,
        **{**_SAFE_PUBLIC_URLS, "cors_allowed_origins": "http://localhost:3000"},
    )
    with pytest.raises(ProductionConfigError) as exc_info:
        validate_production_config(config)
    assert "cors_allowed_origins" in str(exc_info.value)


def test_production_rejects_cors_allowed_origins_mixing_a_real_domain_with_localhost() -> None:
    """`cors_allowed_origins` est une liste séparée par virgules — un seul membre encore local
    suffit à refuser le démarrage (recherche par sous-chaîne sur la valeur brute complète)."""
    config = Settings(
        environment="production",
        **_SAFE_SECRETS,
        **{**_SAFE_PUBLIC_URLS, "cors_allowed_origins": "https://app.edusphere.example,http://localhost:3000"},
    )
    with pytest.raises(ProductionConfigError) as exc_info:
        validate_production_config(config)
    assert "cors_allowed_origins" in str(exc_info.value)


@pytest.mark.parametrize("field", ["public_base_url", "public_web_base_url", "cors_allowed_origins"])
@pytest.mark.parametrize("local_value_template", ["http://127.0.0.1:{port}", "http://0.0.0.0:{port}"])
def test_production_rejects_loopback_and_bind_all_addresses(field: str, local_value_template: str) -> None:
    """127.0.0.1 (boucle locale) et 0.0.0.0 (toutes interfaces) sont aussi peu valides que
    `localhost` comme URL publique communiquée à un tiers (navigateur, QR code, en-tête CORS)."""
    local_value = local_value_template.format(port=8000)
    config = Settings(environment="production", **_SAFE_SECRETS, **{**_SAFE_PUBLIC_URLS, field: local_value})
    with pytest.raises(ProductionConfigError) as exc_info:
        validate_production_config(config)
    assert field in str(exc_info.value)


def test_production_accepts_real_public_urls_and_cors() -> None:
    config = Settings(environment="production", **_SAFE_SECRETS, **_SAFE_PUBLIC_URLS)
    validate_production_config(config)  # ne doit pas lever


def test_dev_and_test_environments_accept_localhost_public_urls() -> None:
    for environment in ("development", "test"):
        config = Settings(environment=environment)
        validate_production_config(config)  # jamais vérifié hors production


# === Phase 23 — SMTP en production ==============================================================
def test_production_smtp_missing_credentials_logs_critical_but_does_not_raise(caplog: pytest.LogCaptureFixture) -> None:
    config = Settings(
        environment="production",
        **_SAFE_SECRETS,
        **_SAFE_PUBLIC_URLS,
        email_provider="smtp",
        smtp_username="",
        smtp_password="",
    )
    with caplog.at_level("CRITICAL", logger="app.core.config"):
        validate_production_config(config)  # ne doit pas lever
    assert any(record.levelname == "CRITICAL" and "SMTP" in record.message for record in caplog.records)


def test_production_smtp_missing_only_password_still_logs_critical(caplog: pytest.LogCaptureFixture) -> None:
    config = Settings(
        environment="production",
        **_SAFE_SECRETS,
        **_SAFE_PUBLIC_URLS,
        email_provider="smtp",
        smtp_username="real-smtp-user",
        smtp_password="",
    )
    with caplog.at_level("CRITICAL", logger="app.core.config"):
        validate_production_config(config)
    assert any(record.levelname == "CRITICAL" for record in caplog.records)


def test_production_smtp_with_valid_credentials_raises_no_critical(caplog: pytest.LogCaptureFixture) -> None:
    config = Settings(
        environment="production",
        **_SAFE_SECRETS,
        **_SAFE_PUBLIC_URLS,
        email_provider="smtp",
        smtp_username="real-smtp-user",
        smtp_password="real-smtp-password",
    )
    with caplog.at_level("CRITICAL", logger="app.core.config"):
        validate_production_config(config)
    assert not any(record.levelname == "CRITICAL" for record in caplog.records)


def test_production_smtp_credentials_never_appear_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    config = Settings(
        environment="production",
        **_SAFE_SECRETS,
        **_SAFE_PUBLIC_URLS,
        email_provider="smtp",
        smtp_username="",
        smtp_password="super-secret-smtp-password-value",
    )
    with caplog.at_level("CRITICAL", logger="app.core.config"):
        validate_production_config(config)
    assert "super-secret-smtp-password-value" not in caplog.text


def test_production_email_local_logs_warning_but_does_not_raise(caplog: pytest.LogCaptureFixture) -> None:
    config = Settings(environment="production", **_SAFE_SECRETS, **_SAFE_PUBLIC_URLS, email_provider="local")
    with caplog.at_level("WARNING", logger="app.core.config"):
        validate_production_config(config)  # ne doit pas lever
    assert any("EMAIL_PROVIDER=local" in record.message for record in caplog.records)


def test_dev_and_test_never_evaluate_smtp_or_email_provider_warnings(caplog: pytest.LogCaptureFixture) -> None:
    for environment in ("development", "test"):
        config = Settings(environment=environment, email_provider="local")
        with caplog.at_level("WARNING", logger="app.core.config"):
            validate_production_config(config)
        assert not any(record.name == "app.core.config" for record in caplog.records)
