import logging

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

    # Rate limiting reset-password (Phase 22 — gap identifié en Discovery : seul endpoint
    # d'authentification pré-connexion sans aucune limite, contrairement à login/forgot-password/
    # register/refresh). Clé IP (endpoint non authentifié, pas d'email dans le payload) — même
    # motif que register/report-card-verify. Le jeton lui-même a 384 bits d'entropie
    # (generate_opaque_token) donc le brute-force reste infaisable indépendamment de cette limite ;
    # son rôle est de borner un abus/DoS applicatif sur cet endpoint. Seuil plus généreux que
    # forgot-password (3/900s) puisqu'aucun email n'est envoyé ici (coût nettement plus faible).
    reset_password_rate_limit_max_attempts: int = 10
    reset_password_rate_limit_window_seconds: int = 900

    # Rate limiting des mutations financières (Phase 22 — POST /payments et /payments/{id}/cancel,
    # même compteur partagé : même surface d'abus, même acteur authentifié). Clé user_id (comme
    # refresh) — protégé avant tout par RBAC (payments.manage), cette limite est une défense en
    # profondeur contre un compte compromis/un script buggy mutant des paiements en rafale, pas
    # une contrainte sur l'usage normal (un comptable saisissant plusieurs dizaines de paiements
    # lors d'une journée d'inscription reste largement sous ce seuil).
    payments_rate_limit_max_attempts: int = 60
    payments_rate_limit_window_seconds: int = 60

    # Rate limiting des annonces (Phase 22 — POST /announcements, diffusion de masse). Clé
    # user_id. 10/heure reste largement au-dessus de l'usage réel d'une école (quelques annonces
    # par jour au plus) tout en bornant un abus par un compte admin compromis.
    announcements_rate_limit_max_attempts: int = 10
    announcements_rate_limit_window_seconds: int = 3600

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


class ProductionConfigError(RuntimeError):
    """Levée au démarrage si `environment=production` avec un secret par défaut de
    développement encore en place — voir `validate_production_config`."""


# Phase 22 — gap identifié en Discovery : rien n'empêchait jusqu'ici un déploiement "production"
# de démarrer avec ces identifiants de développement, publics (présents dans ce fichier
# versionné). Recherche par SOUS-CHAÎNE (le mot de passe connu), pas par égalité de l'URL
# complète : un déploiement peut légitimement changer l'hôte (ex. `db` au lieu de `localhost`
# sous docker-compose) tout en oubliant de changer le mot de passe — une égalité stricte sur
# l'URL entière manquerait exactement ce cas. Jamais la valeur réelle n'est journalisée ou
# incluse dans un message d'erreur, seule la présence/absence du marqueur est signalée.
_DANGEROUS_SECRET_MARKERS: dict[str, str] = {
    "jwt_secret_key": "replace_with_a_long_random_secret",
    "database_url": "changeme_local_only",
    "app_database_url": "changeme_app_role_local_only",
}

# Phase 23 — gap identifié en Discovery Phase 23 : `validate_production_config` ne couvrait que
# les 3 secrets ci-dessus. Une URL PUBLIQUE (celle qu'on donne à un navigateur/QR code/CORS) qui
# contiendrait encore une adresse locale en production serait un échec silencieux (pas de crash,
# juste une app inutilisable depuis un vrai domaine, ou des liens de bulletin cassés envoyés aux
# parents) — donc traitée avec la même sévérité (refus au démarrage), pas seulement un
# avertissement. Trois marqueurs, pas un seul : `localhost` et `127.0.0.1` sont des adresses de
# boucle locale, `0.0.0.0` est une adresse de écoute "toutes interfaces" jamais valide comme URL
# qu'on communique à un tiers — les trois sont donc concernés par cette même règle. Vérification
# par sous-chaîne, comme pour les secrets ci-dessus (`cors_allowed_origins` est une liste
# séparée par virgules, pas une URL unique — un `in` simple couvre les deux cas sans sur-analyser
# la valeur).
_LOCAL_URL_MARKERS: tuple[str, ...] = ("localhost", "127.0.0.1", "0.0.0.0")
_PUBLIC_URL_FIELDS: tuple[str, ...] = ("cors_allowed_origins", "public_base_url", "public_web_base_url")


def validate_production_config(config: "Settings") -> None:
    """Échoue vite et explicitement si `config.environment == "production"` et qu'un des champs
    ci-dessus contient encore son marqueur de développement (secret) ou une adresse locale (URL
    publique). Ne s'applique à aucun autre environnement (development/test), donc sans impact sur
    le développement local ni la CI.

    Vérifie aussi la configuration SMTP en production, mais avec une sévérité différente et
    volontairement documentée : `email_provider=smtp` avec des identifiants vides produit un
    `logger.critical` (l'envoi d'email échouera silencieusement sinon) sans jamais faire échouer
    le démarrage — contrairement aux deux vérifications ci-dessus. `email_provider=local` reste un
    choix de déploiement valide (ce projet n'impose aucun fournisseur SMTP) : seulement un
    `logger.warning` rappelant qu'aucun email réel ne sera envoyé, jamais un refus."""
    if config.environment != "production":
        return

    unsafe_fields = sorted(
        name for name, marker in _DANGEROUS_SECRET_MARKERS.items() if marker in getattr(config, name)
    )
    unsafe_fields += sorted(
        name for name in _PUBLIC_URL_FIELDS if any(marker in getattr(config, name) for marker in _LOCAL_URL_MARKERS)
    )
    if unsafe_fields:
        raise ProductionConfigError(
            "Configuration de production invalide : les variables suivantes utilisent encore leur "
            "valeur par défaut de développement ou une adresse locale, et doivent être définies "
            f"explicitement avant le démarrage : {', '.join(sorted(set(unsafe_fields)))}."
        )

    logger = logging.getLogger(__name__)
    if config.email_provider == "smtp" and (not config.smtp_username or not config.smtp_password):
        logger.critical(
            "Configuration de production : EMAIL_PROVIDER=smtp mais SMTP_USERNAME/SMTP_PASSWORD "
            "sont vides — l'envoi d'email échouera silencieusement tant que ce n'est pas corrigé."
        )
    elif config.email_provider == "local":
        logger.warning(
            "Configuration de production : EMAIL_PROVIDER=local — aucun email réel ne sera envoyé "
            "(choix de déploiement valide, mais à confirmer intentionnellement)."
        )


settings = Settings()
validate_production_config(settings)
