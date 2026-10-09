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

# --- Phase 4 (académique — évaluations et notes) -------------------------------
PHASE4_PERMISSIONS: dict[str, str] = {
    "grades.read": "Consulter les évaluations, notes, moyennes et classements",
    "grades.manage": "Saisir des évaluations/notes (un enseignant reste limité à ses classes affectées)",
}

PHASE4_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "SUPER_ADMIN": ["grades.read", "grades.manage"],
    "PLATFORM_SUPPORT": ["grades.read"],
    "SCHOOL_ADMIN": ["grades.read", "grades.manage"],
    "DIRECTOR": ["grades.read", "grades.manage"],
    "TEACHER": ["grades.read", "grades.manage"],
    "STAFF": ["grades.read"],
}

# --- Phase 5 (bulletins) --------------------------------------------------------
PHASE5_PERMISSIONS: dict[str, str] = {
    "report_cards.read": "Consulter et télécharger les bulletins",
    "report_cards.manage": "Créer des modèles, générer et publier les bulletins",
}

PHASE5_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "SUPER_ADMIN": ["report_cards.read", "report_cards.manage"],
    "PLATFORM_SUPPORT": ["report_cards.read"],
    "SCHOOL_ADMIN": ["report_cards.read", "report_cards.manage"],
    "DIRECTOR": ["report_cards.read", "report_cards.manage"],
    "TEACHER": ["report_cards.read"],
    "STAFF": ["report_cards.read"],
}

# --- Phase 6 (présence / assiduité) ---------------------------------------------
PHASE6_PERMISSIONS: dict[str, str] = {
    "attendance.read": "Consulter les présences, absences et retards",
    "attendance.manage": "Faire l'appel et corriger les présences (un enseignant reste limité aux classes où il a une affectation)",
}

PHASE6_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "SUPER_ADMIN": ["attendance.read", "attendance.manage"],
    "PLATFORM_SUPPORT": ["attendance.read"],
    "SCHOOL_ADMIN": ["attendance.read", "attendance.manage"],
    "DIRECTOR": ["attendance.read", "attendance.manage"],
    "TEACHER": ["attendance.read", "attendance.manage"],
    "STAFF": ["attendance.read"],
}

# --- Phase 19 (frais scolaires / paiements) -------------------------------------
# Décision produit validée : SCHOOL_ADMIN et DIRECTOR configurent les frais ET gèrent les
# paiements ; ACCOUNTANT (jusqu'ici sans permission de domaine, voir PHASE_13_DISCOVERY.md)
# gère les paiements mais ne configure pas les barèmes — voir PHASE_19_DISCOVERY.md §18.
PHASE19_PERMISSIONS: dict[str, str] = {
    "fees.read": "Consulter les catégories, barèmes et obligations financières des élèves",
    "fees.manage": "Configurer les catégories/barèmes de frais et ajuster une obligation financière",
    "payments.read": "Consulter les paiements et les reçus",
    "payments.manage": "Enregistrer et annuler des paiements",
}

PHASE19_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "SUPER_ADMIN": ["fees.read", "fees.manage", "payments.read", "payments.manage"],
    "PLATFORM_SUPPORT": ["fees.read", "payments.read"],
    "SCHOOL_ADMIN": ["fees.read", "fees.manage", "payments.read", "payments.manage"],
    "DIRECTOR": ["fees.read", "fees.manage", "payments.read", "payments.manage"],
    "ACCOUNTANT": ["fees.read", "payments.read", "payments.manage"],
}

# --- Phase 21 (communications / annonces) ---------------------------------------
# Décision produit validée : seuls SCHOOL_ADMIN/DIRECTOR publient des annonces. ACCOUNTANT/
# TEACHER/STAFF ne publient pas mais reçoivent normalement leurs propres notifications (aucune
# permission requise pour lire SES notifications — auto-scopé par recipient_user_id, même motif
# que /auth/me — voir PHASE_21_DISCOVERY.md §10). Pas de permission `notifications.*` : rien à
# gérer côté RBAC pour la simple lecture de ses propres notifications.
PHASE21_PERMISSIONS: dict[str, str] = {
    "announcements.manage": "Publier une annonce scolaire (toute l'école ou une/plusieurs classes)",
}

PHASE21_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "SUPER_ADMIN": ["announcements.manage"],
    "SCHOOL_ADMIN": ["announcements.manage"],
    "DIRECTOR": ["announcements.manage"],
}

# --- PR #14 (journal d'audit administratif) --------------------------------------
# Pas de numéro de "Phase" ici : le projet est passé à un suivi par PR depuis la Phase 21. Décision
# produit validée (voir AUDIT EDULINKAGE §13) : seuls les rôles qui supervisent une école/
# organisation peuvent consulter ce journal. ACCOUNTANT/TEACHER/STAFF manipulent des ressources
# sensibles (paiements, notes...) mais ne supervisent pas — ils n'ont jamais `audit.read`.
AUDIT_PERMISSIONS: dict[str, str] = {
    "audit.read": "Consulter le journal des actions administratives sensibles",
}

AUDIT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "SUPER_ADMIN": ["audit.read"],
    "PLATFORM_SUPPORT": ["audit.read"],
    "SCHOOL_ADMIN": ["audit.read"],
    "DIRECTOR": ["audit.read"],
}

# --- PR #17 (Platform Owner & Partner isolation) --------------------------------
# Nouveau rôle PLATFORM_OWNER, déclaré dans un dict DISTINCT de `ROLE_NAMES` (volontairement) :
# `ROLE_NAMES` est importé tel quel par la migration 0002 au moment de son exécution — y ajouter
# PLATFORM_OWNER ferait insérer ce rôle par 0002 sur toute base créée from scratch (modifiant
# rétroactivement le comportement d'une migration déjà appliquée), puis 0023 tenterait de
# l'insérer une seconde fois (violation d'unicité sur `roles.code`). Seule la migration 0023 lit
# ce dict.
PR17_ROLE_NAMES: dict[str, str] = {
    "PLATFORM_OWNER": "Propriétaire de la plateforme",
}

# Permissions plateforme (métadonnées uniquement) et partenaire. Construites pour ne JAMAIS
# recouvrir un code du domaine scolaire (students.*, grades.*, attendance.*, report_cards.*,
# fees.*, payments.*, academics.*, organizations.*, schools.*, users.*, roles.*, announcements.*,
# audit.*) : `get_scoped_permission_codes` applique sans condition les permissions d'une UserRole
# globale à n'importe quelle portée demandée — PLATFORM_OWNER/PARTNER_ADMIN ne doivent donc
# jamais en détenir aucune (voir tests/test_partner_isolation.py). `platform.organizations.read`/
# `platform.schools.read` sont des codes DISTINCTS de `organizations.read`/`schools.read` (qui
# signifient « lire MON organisation/école » pour SCHOOL_ADMIN/DIRECTOR) : jamais d'alias.
# `*.subscriptions.read`/`*.commissions.read` sont réservés à la PR #18 (moteur financier de
# commissions) : aucun endpoint, aucune table, aucune logique derrière dans cette PR.
PR17_PLATFORM_PERMISSIONS: dict[str, str] = {
    "platform.dashboard.read": "Consulter le tableau de bord plateforme (organisations, écoles, comptes, partenaires)",
    "platform.organizations.read": "Consulter la liste et les métadonnées de toutes les organisations",
    "platform.schools.read": "Consulter la liste et les métadonnées de toutes les écoles",
    "platform.schools.enroll": "Inscrire une nouvelle organisation/école sur la plateforme",
    "platform.accounts.read": "Consulter les comptes utilisateurs de la plateforme (métadonnées uniquement)",
    "platform.partners.read": "Consulter la liste des partenaires commerciaux",
    "platform.partners.manage": "Créer/gérer un compte partenaire commercial",
    "platform.subscriptions.read": "Consulter les abonnements SaaS des organisations (réservé PR #18, aucun endpoint dans cette PR)",
    "platform.commissions.read": "Consulter les commissions dues aux partenaires (réservé PR #18, aucun endpoint dans cette PR)",
}

PR17_PLATFORM_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "SUPER_ADMIN": list(PR17_PLATFORM_PERMISSIONS.keys()),
    "PLATFORM_OWNER": list(PR17_PLATFORM_PERMISSIONS.keys()),
}

PR17_PARTNER_PERMISSIONS: dict[str, str] = {
    "partner.dashboard.read": "Consulter le tableau de bord du partenaire (ses propres écoles inscrites)",
    "partner.schools.read": "Consulter les écoles inscrites par ce partenaire",
    "partner.schools.enroll": "Inscrire une nouvelle organisation/école via ce partenaire",
    "partner.accounts.read": "Consulter les comptes utilisateurs des écoles inscrites par ce partenaire (métadonnées uniquement)",
    "partner.commissions.read": "Consulter les commissions de ce partenaire (réservé PR #18, aucun endpoint dans cette PR)",
}

PR17_PARTNER_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "SUPER_ADMIN": list(PR17_PARTNER_PERMISSIONS.keys()),
    "PARTNER_ADMIN": list(PR17_PARTNER_PERMISSIONS.keys()),
}
