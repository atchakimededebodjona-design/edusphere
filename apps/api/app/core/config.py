from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "info"

    api_v1_prefix: str = "/api/v1"
    cors_allowed_origins: str = "http://localhost:3000"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    database_url: str = "postgresql+asyncpg://edusphere:changeme_local_only@localhost:5432/edusphere"
    app_database_url: str = "postgresql+asyncpg://edusphere_app:changeme_app_role_local_only@localhost:5432/edusphere"

    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "replace_with_a_long_random_secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    storage_provider: str = "local"
    storage_local_path: str = "./storage"

    # URL de base utilisée pour construire les liens de vérification QR des bulletins (Phase 5).
    # Aucun hébergeur n'est encore choisi (règle Phase 0) — reste configurable via env var.
    public_base_url: str = "http://localhost:8000"

    # URL de base de l'app web (Next.js) — le QR des bulletins pointe vers sa page de
    # vérification publique (/verify/{code}), pas directement vers l'endpoint API JSON.
    public_web_base_url: str = "http://localhost:3000"


settings = Settings()
