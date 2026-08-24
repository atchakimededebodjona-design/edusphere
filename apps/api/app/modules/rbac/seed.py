"""Catalogue RBAC initial (Phase 1). Source unique utilisée par la migration Alembic.

Les permissions listées ici couvrent uniquement le périmètre Phase 1 (organizations, schools,
users, roles). Les modules futurs (élèves, académique, finance...) ajouteront leurs propres
permissions et enrichiront ce mapping via de nouvelles migrations, sans modifier celle-ci.
"""

ROLE_NAMES: dict[str, str] = {
    "SUPER_ADMIN": "Super administrateur plateforme",
    "PLATFORM_SUPPORT": "Support plateforme",
    "PARTNER_ADMIN": "Administrateur partenaire",
    "SCHOOL_ADMIN": "Administrateur d'école",
    "DIRECTOR": "Directeur",
    "ACCOUNTANT": "Comptable",
    "TEACHER": "Enseignant",
    "STAFF": "Personnel",
    "PARENT": "Parent / tuteur",
    "STUDENT": "Élève",
}

PERMISSIONS: dict[str, str] = {
    "organizations.read": "Consulter les informations d'une organisation",
    "organizations.manage": "Modifier les informations d'une organisation",
    "schools.read": "Consulter les informations d'une école",
    "schools.manage": "Créer/modifier les écoles d'une organisation",
    "users.read": "Consulter les comptes utilisateurs",
    "users.manage": "Gérer les comptes utilisateurs",
    "roles.read": "Consulter le catalogue des rôles et permissions",
}

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "SUPER_ADMIN": list(PERMISSIONS.keys()),
    "PLATFORM_SUPPORT": ["organizations.read", "schools.read", "users.read", "roles.read"],
    "PARTNER_ADMIN": [],
    "SCHOOL_ADMIN": [
        "organizations.read",
        "organizations.manage",
        "schools.read",
        "schools.manage",
        "users.read",
        "users.manage",
        "roles.read",
    ],
    "DIRECTOR": ["organizations.read", "schools.read", "users.read", "roles.read"],
    "ACCOUNTANT": ["schools.read"],
    "TEACHER": ["schools.read"],
    "STAFF": ["schools.read"],
    "PARENT": [],
    "STUDENT": [],
}
