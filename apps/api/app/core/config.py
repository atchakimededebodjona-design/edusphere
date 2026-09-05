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

    # Rate limiting register (Phase 20 — durcissement pré-pilote). Clé IP, pas email : contrairement
    # au login (une école légitime se connecte en continu depuis la même IP), /auth/register ne
    # crée une NOUVELLE organisation qu'une seule fois par client réel dans l'usage normal — mais
    # une même IP peut légitimement en créer plusieurs dans une même heure (QA/E2E, un partenaire
    # onboardant plusieurs écoles dans une même session, un réseau NAT partagé) : la suite
    # Playwright de ce dépôt elle-même déclenche plus de 5 inscriptions réelles depuis la même IP
    # de boucle locale en une seule exécution (constaté réellement en Phase 20 — voir
    # PHASE_20_IMPLEMENTATION.md). 20/heure reste largement supérieur à ce cas réel tout en
    # bloquant un volume réellement automatisé (voir app/core/rate_limit.py::
    # ensure_register_not_rate_limited).
    register_rate_limit_max_attempts: int = 20
    register_rate_limit_window_seconds: int = 3600

    # Rate limiting refresh (Phase 20). Clé user_id (résolu après validation du refresh token,
    # avant toute mutation) : le token de refresh tourne à chaque appel (rotation déjà en place
    # depuis la Phase 1), donc une clé basée sur le token lui-même ne verrait jamais plus d'une
    # requête par fenêtre. 30/5 min reste large au-delà du rythme normal (access token = 15 min,
    # voir jwt_access_token_expire_minutes) pour absorber les reprises après coupure réseau.
    refresh_rate_limit_max_attempts: int = 30
    refresh_rate_limit_window_seconds: int = 300

    # Rate limiting de la vérification publique de bulletin (Phase 20 — /report-cards/verify/{code}).
    # Clé IP : endpoint non authentifié, aucune autre clé disponible. Le code lui-même a 384 bits
    # d'entropie (secrets.token_urlsafe(48)) — le brute-force reste infaisable indépendamment de
    # cette limite ; son seul rôle réel est de décourager un scraping automatisé à haut débit,
    # d'où un seuil volontairement généreux (plusieurs parents d'une même école, sur le même
    # réseau, scannant chacun leur propre QR le même jour, ne doivent jamais être bloqués).
    report_card_verify_rate_limit_max_attempts: int = 30
    report_card_verify_rate_limit_window_seconds: int = 60

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
