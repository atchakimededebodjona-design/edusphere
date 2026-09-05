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

    # Rate limiting login (Phase 7.2 — durcissement pré-pilote). Compteur par email (pas par IP :
    # une école entière peut partager une IP, un compteur par IP bloquerait des utilisateurs
    # légitimes) — voir app/core/rate_limit.py.
    login_rate_limit_max_attempts: int = 5
    login_rate_limit_window_seconds: int = 300

    # Rate limiting mot de passe oublié (Phase 10.1 — depuis la Phase 9, cet endpoint déclenche
    # un vrai envoi d'email : sans limite c'est un vecteur d'email bombing). Seuil plus bas et
    # fenêtre plus longue que le login : un envoi d'email coûte plus cher qu'une vérification de
    # mot de passe, et une vraie demande de réinitialisation est un événement rare pour un
    # utilisateur légitime.
    forgot_password_rate_limit_max_attempts: int = 3
    forgot_password_rate_limit_window_seconds: int = 900

    jwt_secret_key: str = "replace_with_a_long_random_secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    storage_provider: str = "local"
    storage_local_path: str = "./storage"

    # Email transactionnel (Phase 9 — invitation de compte / réinitialisation de mot de passe).
    # "local" en dev/tests : rien n'est réellement envoyé, chaque email est écrit en fichier sous
    # email_local_path (voir app/core/email.py) — même principe que StorageProvider.
    email_provider: str = "local"
    email_local_path: str = "./emails"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_address: str = "no-reply@edusphere.local"
    smtp_use_tls: bool = True
    # Phase 16 — configurable pour permettre aux tests de vérifier un dépassement de délai en
    # quelques secondes plutôt que d'attendre la valeur de production ; 10s reste la valeur par
    # défaut (comportement inchangé si la variable n'est pas définie).
    smtp_timeout_seconds: int = 10

    # URL de base utilisée pour construire les liens de vérification QR des bulletins (Phase 5).
    # Aucun hébergeur n'est encore choisi (règle Phase 0) — reste configurable via env var.
    public_base_url: str = "http://localhost:8000"

    # URL de base de l'app web (Next.js) — le QR des bulletins pointe vers sa page de
    # vérification publique (/verify/{code}), pas directement vers l'endpoint API JSON.
    public_web_base_url: str = "http://localhost:3000"


settings = Settings()
