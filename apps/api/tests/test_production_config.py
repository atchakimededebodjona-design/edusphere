"""Phase 22 — validation de la configuration de production.

`validate_production_config` est appelée au chargement du module (voir app/core/config.py) : ces
tests l'exercent directement sur des instances `Settings` construites en mémoire plutôt qu'en
manipulant l'environnement réel du process de test, pour rester rapides et sans effet de bord.
"""

import pytest

from app.core.config import ProductionConfigError, Settings, validate_production_config


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
    config = Settings(
        environment="production",
        jwt_secret_key="a-real-random-secret-generated-for-this-deployment",
        database_url="postgresql+asyncpg://real_role:real_password@dbhost:5432/edusphere",
        app_database_url="postgresql+asyncpg://real_app_role:real_password@dbhost:5432/edusphere",
    )
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
