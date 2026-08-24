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

# --- Phase 2 (administration scolaire) --------------------------------------
# Permissions et attributions ajoutées par la migration 0003, en plus de celles ci-dessus
# (déjà appliquées par la migration 0002 — on ne les réinsère pas).
PHASE2_PERMISSIONS: dict[str, str] = {
    "academics.read": "Consulter les données académiques (années, classes, matières, salles...)",
    "academics.manage": "Gérer les données académiques (années, classes, matières, salles...)",
}

PHASE2_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "SUPER_ADMIN": ["academics.read", "academics.manage"],
    "PLATFORM_SUPPORT": ["academics.read"],
    "SCHOOL_ADMIN": ["academics.read", "academics.manage"],
    "DIRECTOR": ["academics.read", "academics.manage"],
    "TEACHER": ["academics.read"],
    "STAFF": ["academics.read"],
}

# --- Phase 3 (élèves) ---------------------------------------------------------
PHASE3_PERMISSIONS: dict[str, str] = {
    "students.read": "Consulter les dossiers élèves, familles et inscriptions",
    "students.manage": "Gérer les dossiers élèves, familles, inscriptions et documents",
}

PHASE3_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "SUPER_ADMIN": ["students.read", "students.manage"],
    "PLATFORM_SUPPORT": ["students.read"],
    "SCHOOL_ADMIN": ["students.read", "students.manage"],
    "DIRECTOR": ["students.read", "students.manage"],
    "TEACHER": ["students.read"],
    "STAFF": ["students.read", "students.manage"],
}
