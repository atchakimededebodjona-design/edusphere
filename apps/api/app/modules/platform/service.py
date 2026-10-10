import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email import send_email_best_effort
from app.core.security import generate_opaque_token, hash_opaque_token, hash_password
from app.core.tenancy import set_platform_wide_context
from app.modules.auth.models import PasswordResetToken
from app.modules.organizations.models import Organization
from app.modules.partners.models import (
    ACQUISITION_SOURCE_PARTNER,
    ACQUISITION_SOURCE_PLATFORM_OWNER,
    Partner,
    PartnerSchoolEnrollment,
)
from app.modules.platform.schemas import (
    PlatformAdminInput,
    PlatformOrganizationCreate,
    PlatformPartnerCreate,
    PlatformSchoolAdd,
    PlatformSchoolInput,
    SchoolAdminInput,
)
from app.modules.rbac.models import NON_SCHOOL_ROLE_CODES, Role, UserRole
from app.modules.schools.models import School
from app.modules.students.models import Student
from app.modules.users.models import User

# Même durée que users/service.py::PASSWORD_RESET_TOKEN_EXPIRE_MINUTES (invitation par lien de
# réinitialisation) — pas de dépendance croisée pour une seule constante.
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 30


async def create_organization_with_admin(
    db: AsyncSession, payload: PlatformOrganizationCreate, enrolled_by_user_id: uuid.UUID
) -> tuple[Organization, School, User]:
    """Inscription directe par un compte plateforme (POST /platform/organizations) : crée
    l'organisation, l'école principale, le premier SCHOOL_ADMIN ET la ligne
    `partner_school_enrollments` correspondante (`partner_id` NULL, source "PLATFORM_OWNER",
    jamais éligible à commission) — voir `create_organization_school_admin`."""
    return await create_organization_school_admin(
        db,
        payload,
        enrolled_by_user_id=enrolled_by_user_id,
        partner_id=None,
        acquisition_source=ACQUISITION_SOURCE_PLATFORM_OWNER,
    )


async def create_organization_school_admin(
    db: AsyncSession,
    payload: PlatformOrganizationCreate,
    *,
    enrolled_by_user_id: uuid.UUID,
    partner_id: uuid.UUID | None,
    acquisition_source: str,
) -> tuple[Organization, School, User]:
    """Crée une organisation, son école principale et son premier SCHOOL_ADMIN (rôle
    org-wide, `school_id` NULL, comme à l'ancienne inscription publique), plus la ligne
    `partner_school_enrollments` qui trace la source d'acquisition de cette école.

    PR #17 — logique partagée par les DEUX points d'entrée d'inscription, chacun passant ses
    propres valeurs (jamais issues du payload client) :
    - POST /platform/organizations : `partner_id=None`, source "PLATFORM_OWNER" ;
    - POST /partner/schools : `partner_id` = partenaire résolu côté serveur depuis le compte
      appelant, source "PARTNER".
    `commission_eligible` est dérivé de la source (true uniquement pour "PARTNER"), jamais passé
    librement — aucun montant de commission n'est calculé ici (PR #18).

    L'appelant a déjà passé son contrôle d'autorisation (require_platform_admin, ou la permission
    `partner.schools.enroll`) ; le contexte `app.is_platform_wide` est posé explicitement pour
    l'écriture multi-tables (les lignes créées ne sont visibles que dans la transaction courante).

    Atomique : une seule transaction. Tout échec (conflit d'unicité, erreur intermédiaire)
    annule l'ensemble, sans organisation ni école orpheline. Le mot de passe n'est jamais
    stocké ni journalisé en clair — seul son hash bcrypt (app/core/security.py) est persisté.
    """
    school_admin_role = await _school_admin_role(db)
    await set_platform_wide_context(db)
    org_input = payload.organization

    try:
        # Flush après chaque ajout (même motif que l'ancien auth/service.py::register) : sans
        # relationship() ORM entre ces modules, l'ordre d'insertion doit être forcé.
        # refresh() avant commit car les lignes ne sont visibles que dans la transaction (RLS).
        organization = Organization(
            id=uuid.uuid4(),
            name=org_input.name,
            slug=org_input.slug,
            country_code=org_input.country_code,
            timezone=org_input.timezone,
            currency=org_input.currency,
        )
        db.add(organization)
        await db.flush()

        # Premier SCHOOL_ADMIN : rôle org-wide (`school_id` NULL), comportement historique conservé.
        # Nouvelle organisation : aucun compte existant ne peut y avoir de rôle, donc un email
        # existant est toujours refusé (409, message historique) — PR #20, voir
        # `resolve_or_create_school_admin`.
        school, resolution = await _create_school_admin_enrollment(
            db,
            organization,
            payload.school,
            payload.admin,
            school_admin_role=school_admin_role,
            admin_school_scoped=False,
            enrolled_by_user_id=enrolled_by_user_id,
            partner_id=partner_id,
            acquisition_source=acquisition_source,
            conflict_detail=ORGANIZATION_CONFLICT_DETAIL,
        )
        user = resolution.user

        await db.refresh(organization)
        await db.refresh(school)
        await db.refresh(user)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ORGANIZATION_CONFLICT_DETAIL) from exc
    except Exception:
        await db.rollback()
        raise

    return organization, school, user


async def _school_admin_role(db: AsyncSession) -> Role:
    result = await db.execute(select(Role).where(Role.code == "SCHOOL_ADMIN"))
    school_admin_role = result.scalar_one_or_none()
    if school_admin_role is None:
        raise RuntimeError("SCHOOL_ADMIN role is missing — RBAC seed data was not applied")
    return school_admin_role


ORGANIZATION_CONFLICT_DETAIL = "Organization slug or admin email already in use"
SCHOOL_CONFLICT_DETAIL = "School slug or admin email already in use"

# PR #20 — seuls les comptes détenant DÉJÀ l'un de ces rôles dans l'organisation cible peuvent être
# réutilisés comme SCHOOL_ADMIN d'une nouvelle école de cette organisation. Tout autre rôle
# (PARENT, STUDENT, TEACHER, ACCOUNTANT, STAFF) est refusé : jamais d'élévation silencieuse.
REUSABLE_ADMIN_ROLE_CODES = {"SCHOOL_ADMIN", "DIRECTOR"}

# Statut renvoyé à l'appelant (champ `admin_access` des réponses d'inscription).
ADMIN_ACCESS_NEW_ACCOUNT = "NEW_ACCOUNT"
ADMIN_ACCESS_SCHOOL_ROLE_ADDED = "SCHOOL_ROLE_ADDED"
ADMIN_ACCESS_ORGANIZATION_WIDE = "ORGANIZATION_WIDE_ROLE"


@dataclass
class SchoolAdminResolution:
    """Résultat de `resolve_or_create_school_admin` : le compte (créé ou réutilisé) et ce qui a
    réellement été fait pour lui donner l'administration de la nouvelle école."""

    user: User
    reused: bool
    access: str


async def resolve_or_create_school_admin(
    db: AsyncSession,
    *,
    organization: Organization,
    school: School,
    admin_input: PlatformAdminInput | SchoolAdminInput,
    school_admin_role: Role,
    admin_school_scoped: bool,
    conflict_detail: str,
) -> SchoolAdminResolution:
    """PR #20 — résout l'administrateur d'une NOUVELLE école : réutilise le compte existant quand
    c'est légitime, sinon le crée. Ne commite pas (transaction de l'appelant, tout ou rien) ; le
    contexte platform-wide est déjà posé par l'appelant (lecture des rôles de ce compte, toutes
    organisations confondues, filtrée explicitement par `user_id`).

    `User.email` reste UNIQUE (inchangé) : jamais deux comptes pour une même personne. Email
    normalisé (espaces retirés, minuscules) ; verrou transactionnel `pg_advisory_xact_lock` sur cet
    email pour sérialiser deux inscriptions concurrentes visant le même administrateur.

    - Aucun compte : création (nom et mot de passe obligatoires — 422 sinon), puis rôle
      SCHOOL_ADMIN (scopé à l'école si `admin_school_scoped`, org-wide pour la première école d'une
      nouvelle organisation — comportement historique).
    - Compte existant RÉUTILISABLE : actif, sans rôle plateforme/partenaire ni `is_platform_admin`,
      et détenant déjà SCHOOL_ADMIN ou DIRECTOR dans CETTE organisation. Le mot de passe et le
      profil ne sont JAMAIS lus ni modifiés (tout mot de passe envoyé est ignoré).
        * Rôle SCHOOL_ADMIN org-wide déjà détenu dans l'organisation : il couvre déjà la nouvelle
          école — AUCUN rôle ajouté (un rôle scopé en plus masquerait l'accès org-wide côté
          frontend, voir lib/auth/tenantContext.ts::resolveSchoolScopedFastPath).
        * Sinon : ajout d'UN rôle SCHOOL_ADMIN scopé à la nouvelle école (jamais org-wide), sans
          doublon.
    - Tout autre compte existant (autre organisation, inactif, rôle non éligible, compte plateforme
      ou partenaire) : 409 avec EXACTEMENT le même message générique qu'avant la PR #20 — aucun
      motif distinguable de l'extérieur, aucune école ni rôle créés (rollback de l'appelant)."""
    email = str(admin_input.email).strip().lower()
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"school-admin-email:{email}"})

    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        full_name = (admin_input.full_name or "").strip()
        password = admin_input.password or ""
        if len(full_name) < 2:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Administrator full name is required to create a new account",
            )
        if not 8 <= len(password) <= 128:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A password of 8 to 128 characters is required to create a new administrator account",
            )
        user = User(
            id=uuid.uuid4(),
            email=email,
            full_name=full_name,
            phone=admin_input.phone,
            hashed_password=hash_password(password),
        )
        db.add(user)
        await db.flush()
        db.add(
            UserRole(
                id=uuid.uuid4(),
                user_id=user.id,
                role_id=school_admin_role.id,
                organization_id=organization.id,
                school_id=school.id if admin_school_scoped else None,
            )
        )
        await db.flush()
        return SchoolAdminResolution(user=user, reused=False, access=ADMIN_ACCESS_NEW_ACCOUNT)

    refused = HTTPException(status_code=status.HTTP_409_CONFLICT, detail=conflict_detail)
    if not user.is_active or user.is_platform_admin:
        raise refused
    rows = (
        await db.execute(
            select(UserRole, Role.code).join(Role, Role.id == UserRole.role_id).where(UserRole.user_id == user.id)
        )
    ).all()
    if any(code in NON_SCHOOL_ROLE_CODES for _, code in rows):
        raise refused
    in_org = [(ur, code) for ur, code in rows if ur.organization_id == organization.id]
    if not any(code in REUSABLE_ADMIN_ROLE_CODES for _, code in in_org):
        raise refused

    if any(code == "SCHOOL_ADMIN" and ur.school_id is None for ur, code in in_org):
        return SchoolAdminResolution(user=user, reused=True, access=ADMIN_ACCESS_ORGANIZATION_WIDE)

    already = any(code == "SCHOOL_ADMIN" and ur.school_id == school.id for ur, code in in_org)
    if not already:
        db.add(
            UserRole(
                id=uuid.uuid4(),
                user_id=user.id,
                role_id=school_admin_role.id,
                organization_id=organization.id,
                school_id=school.id,
            )
        )
        await db.flush()
    return SchoolAdminResolution(user=user, reused=True, access=ADMIN_ACCESS_SCHOOL_ROLE_ADDED)


async def _create_school_admin_enrollment(
    db: AsyncSession,
    organization: Organization,
    school_input: PlatformSchoolInput,
    admin_input: PlatformAdminInput | SchoolAdminInput,
    *,
    school_admin_role: Role,
    admin_school_scoped: bool,
    enrolled_by_user_id: uuid.UUID,
    partner_id: uuid.UUID | None,
    acquisition_source: str,
    conflict_detail: str,
) -> tuple[School, SchoolAdminResolution]:
    """CŒUR MÉTIER UNIQUE (PR #19) — crée, dans l'organisation DÉJÀ résolue par l'appelant :
    l'école, son SCHOOL_ADMIN et la ligne `partner_school_enrollments`. Utilisé par les deux
    parcours (nouvelle organisation / organisation existante) et par les deux sources
    (PLATFORM_OWNER / PARTNER) — jamais dupliqué. Ne commite pas : l'appelant gère la
    transaction (tout ou rien) et la traduction des IntegrityError en 409.

    `partner_id`/`acquisition_source`/`enrolled_by_user_id` viennent TOUJOURS du serveur (compte
    authentifié), jamais du payload ; `commission_eligible` est dérivé de la source.
    `admin_school_scoped=True` (école ajoutée à une organisation existante) : le nouvel admin est
    scopé à CETTE école uniquement (`school_id` renseigné) — il n'administre jamais les autres
    établissements de l'organisation.

    PR #20 — l'administrateur est résolu par `resolve_or_create_school_admin` (création ou
    réutilisation légitime d'un compte existant de la même organisation)."""
    school = School(
        id=uuid.uuid4(),
        organization_id=organization.id,
        name=school_input.name,
        slug=school_input.slug,
        address=school_input.address,
        phone=school_input.phone,
        email=str(school_input.email) if school_input.email else None,
        timezone=school_input.timezone,
        currency=school_input.currency,
    )
    db.add(school)
    await db.flush()

    resolution = await resolve_or_create_school_admin(
        db,
        organization=organization,
        school=school,
        admin_input=admin_input,
        school_admin_role=school_admin_role,
        admin_school_scoped=admin_school_scoped,
        conflict_detail=conflict_detail,
    )

    # PR #17 — dans la MÊME transaction : l'école n'existe jamais sans sa source d'acquisition
    # (UNIQUE(school_id) en base : une école n'est inscrite qu'une fois, par une seule source).
    db.add(
        PartnerSchoolEnrollment(
            id=uuid.uuid4(),
            partner_id=partner_id,
            organization_id=organization.id,
            school_id=school.id,
            enrolled_by_user_id=enrolled_by_user_id,
            acquisition_source=acquisition_source,
            commission_eligible=acquisition_source == ACQUISITION_SOURCE_PARTNER,
        )
    )
    await db.flush()
    return school, resolution


def _normalized_name(value: str) -> str:
    return " ".join(value.split()).casefold()


async def add_school_to_organization(
    db: AsyncSession,
    organization_id: uuid.UUID,
    payload: PlatformSchoolAdd,
    *,
    enrolled_by_user_id: uuid.UUID,
    partner_id: uuid.UUID | None,
    acquisition_source: str,
) -> tuple[Organization, School, SchoolAdminResolution]:
    """PR #19 — ajoute une école (+ son SCHOOL_ADMIN + son inscription) à une organisation
    EXISTANTE. N'en crée jamais une nouvelle : organisation inconnue => 404.

    L'appelant a déjà vérifié son autorisation ET, pour un partenaire, que `organization_id`
    appartient à son périmètre (partners/service.py::get_partner_organization_or_404) — cette
    fonction ne fait confiance à aucun autre identifiant client.

    Doublons : la ligne `organizations` est verrouillée (`SELECT … FOR UPDATE`) pour sérialiser
    les ajouts concurrents dans une même organisation, puis un même nom d'école (casse/espaces
    ignorés) y est refusé (409). Le slug reste garanti en base par `uq_school_org_slug`
    (organization_id, slug) — stratégie d'unicité existante inchangée ; un conflit de slug ou
    d'email administrateur se traduit aussi en 409, transaction annulée.

    PR #20 — l'administrateur peut être un compte EXISTANT de la même organisation (voir
    `resolve_or_create_school_admin`) ; le résultat indique ce qui a été fait."""
    school_admin_role = await _school_admin_role(db)
    await set_platform_wide_context(db)
    try:
        organization = (
            await db.execute(select(Organization).where(Organization.id == organization_id).with_for_update())
        ).scalar_one_or_none()
        if organization is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

        existing_names = (
            (await db.execute(select(School.name).where(School.organization_id == organization.id))).scalars().all()
        )
        wanted = _normalized_name(payload.school.name)
        if any(_normalized_name(name) == wanted for name in existing_names):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A school with this name already exists in this organization",
            )

        school, resolution = await _create_school_admin_enrollment(
            db,
            organization,
            payload.school,
            payload.admin,
            school_admin_role=school_admin_role,
            admin_school_scoped=True,
            enrolled_by_user_id=enrolled_by_user_id,
            partner_id=partner_id,
            acquisition_source=acquisition_source,
            conflict_detail=SCHOOL_CONFLICT_DETAIL,
        )
        await db.refresh(organization)
        await db.refresh(school)
        await db.refresh(resolution.user)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=SCHOOL_CONFLICT_DETAIL) from exc
    except Exception:
        await db.rollback()
        raise

    return organization, school, resolution


async def get_platform_dashboard_summary(db: AsyncSession) -> dict:
    """Comptes globaux pour le tableau de bord plateforme (aucune donnée d'exemple/fictive).

    `organizations`/`schools`/`students` ont RLS active (voir migrations 0002/0004/0010), mais
    `apply_tenant_context` (core/tenancy.py) positionne déjà `app.is_platform_wide = 'true'` pour
    tout utilisateur ayant un rôle plateforme (code de rôle dans PLATFORM_ROLE_CODES — PR #17) —
    donc pour quiconque atteint cet endpoint (protégé par require_platform_admin). Aucun bypass RLS
    supplémentaire n'est nécessaire ici. `users` ne porte pas de RLS (table globale, non scopée
    par tenant), un simple count() suffit. PR #17 — `partners` (policy partners_platform_only) et
    `partner_school_enrollments` (policy générique) sont lisibles pour la même raison.
    """
    organization_count = (await db.execute(select(func.count()).select_from(Organization))).scalar_one()
    school_count = (await db.execute(select(func.count()).select_from(School))).scalar_one()
    user_count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    student_count = (await db.execute(select(func.count()).select_from(Student))).scalar_one()
    partner_count = (await db.execute(select(func.count()).select_from(Partner))).scalar_one()
    enrollment_count = (await db.execute(select(func.count()).select_from(PartnerSchoolEnrollment))).scalar_one()
    return {
        "organization_count": organization_count,
        "school_count": school_count,
        "user_count": user_count,
        "student_count": student_count,
        "partner_count": partner_count,
        "enrollment_count": enrollment_count,
    }


# --- PR #17 — lectures plateforme (métadonnées uniquement) ----------------------------------------
# Chaque lecture pose explicitement `set_platform_wide_context` : redondant pour un PLATFORM_OWNER/
# SUPER_ADMIN (déjà platform-wide via apply_tenant_context), mais délibérément explicite pour ne
# jamais dépendre implicitement du contexte de l'appelant. L'autorisation réelle reste la
# permission `platform.*` vérifiée par le routeur. Aucune donnée scolaire (élèves, notes,
# présences, bulletins, frais, paiements) n'est jamais lue ici. Toutes les listes sont paginées
# (page/page_size, même convention que GET /fees/overdue) : volume potentiellement très élevé.


async def _count(db: AsyncSession, model: type) -> int:
    return int((await db.execute(select(func.count()).select_from(model))).scalar_one())


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_organizations(
    db: AsyncSession, page: int, page_size: int, q: str | None = None
) -> tuple[list[Organization], int]:
    """PR #19 — `q` (optionnel) : recherche insensible à la casse sur le nom OU le slug, pour
    sélectionner une organisation existante. Sans `q` : comportement PR #17 inchangé."""
    await set_platform_wide_context(db)
    stmt = select(Organization)
    count_stmt = select(func.count()).select_from(Organization)
    term = (q or "").strip()
    if term:
        pattern = f"%{_escape_like(term)}%"
        condition = Organization.name.ilike(pattern, escape="\\") | Organization.slug.ilike(pattern, escape="\\")
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    result = await db.execute(
        stmt.order_by(Organization.created_at.desc(), Organization.id).offset((page - 1) * page_size).limit(page_size)
    )
    total = int((await db.execute(count_stmt)).scalar_one())
    return list(result.scalars().all()), total


async def list_organization_schools(
    db: AsyncSession, organization_id: uuid.UUID
) -> tuple[Organization, list[tuple[School, str | None, int, int]]]:
    """PR #19 — établissements d'UNE organisation (métadonnées + agrégats élèves COUNT
    uniquement, jamais de donnée individuelle), pour afficher l'existant avant d'ajouter une école.
    Organisation inconnue => 404."""
    await set_platform_wide_context(db)
    organization = await db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    rows = (
        await db.execute(
            select(School, PartnerSchoolEnrollment.acquisition_source)
            .outerjoin(PartnerSchoolEnrollment, PartnerSchoolEnrollment.school_id == School.id)
            .where(School.organization_id == organization.id)
            .order_by(School.created_at, School.id)
        )
    ).all()
    counts = await student_counts_by_school(db, [school.id for school, _ in rows])
    items: list[tuple[School, str | None, int, int]] = []
    for school, source in rows:
        total, active = counts.get(school.id, (0, 0))
        items.append((school, source, total, active))
    return organization, items


async def student_counts_by_school(
    db: AsyncSession, school_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    """Agrégats élèves par école : `(student_count, active_student_count)`.

    PR #17 (ajustement produit) — AGRÉGATION PURE : un seul `SELECT school_id, COUNT(*), COUNT(*)
    FILTER (status = 'ACTIVE') … GROUP BY school_id`. Aucune ligne `Student` n'est jamais chargée,
    aucune colonne individuelle (nom, matricule, date de naissance, sexe, classe…) n'est lue ni
    renvoyée. Ne dépend d'AUCUNE permission `students.*` : PLATFORM_OWNER/PARTNER_ADMIN ne
    détiennent jamais `students.read` ; c'est l'appelant (permission `platform.*`/`partner.*`
    vérifiée + liste blanche explicite `school_ids`, contexte platform-wide déjà posé) qui borne ce
    calcul. `active_student_count` reprend EXACTEMENT la définition existante du tableau de bord
    école (schools/service.py : `Student.status == "ACTIVE"`) — aucune nouvelle règle métier, et
    aucune tarification/abonnement n'est construit dessus (réservé PR #18)."""
    if not school_ids:
        return {}
    result = await db.execute(
        select(
            Student.school_id,
            func.count(),
            func.count().filter(Student.status == "ACTIVE"),
        )
        .where(Student.school_id.in_(school_ids))
        .group_by(Student.school_id)
    )
    return {school_id: (int(total), int(active)) for school_id, total, active in result.all()}


async def list_schools(
    db: AsyncSession, page: int, page_size: int
) -> tuple[list[tuple[School, str | None, int, int]], int]:
    await set_platform_wide_context(db)
    result = await db.execute(
        select(School, PartnerSchoolEnrollment.acquisition_source)
        .outerjoin(PartnerSchoolEnrollment, PartnerSchoolEnrollment.school_id == School.id)
        .order_by(School.created_at.desc(), School.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()
    counts = await student_counts_by_school(db, [school.id for school, _ in rows])
    items: list[tuple[School, str | None, int, int]] = []
    for school, source in rows:
        total, active = counts.get(school.id, (0, 0))
        items.append((school, source, total, active))
    return items, await _count(db, School)


async def role_codes_by_user(db: AsyncSession, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    """Codes de rôle (dédupliqués, triés) par utilisateur — l'appelant doit déjà avoir posé le
    contexte RLS adéquat pour lire ces `user_roles`, et borner `user_ids` (une page)."""
    if not user_ids:
        return {}
    result = await db.execute(
        select(UserRole.user_id, Role.code).join(Role, Role.id == UserRole.role_id).where(UserRole.user_id.in_(user_ids))
    )
    codes: dict[uuid.UUID, set[str]] = {}
    for user_id, code in result.all():
        codes.setdefault(user_id, set()).add(code)
    return {user_id: sorted(values) for user_id, values in codes.items()}


async def list_accounts(db: AsyncSession, page: int, page_size: int) -> tuple[list[tuple[User, list[str]]], int]:
    await set_platform_wide_context(db)
    result = await db.execute(
        select(User).order_by(User.created_at.desc(), User.id).offset((page - 1) * page_size).limit(page_size)
    )
    users = list(result.scalars().all())
    codes = await role_codes_by_user(db, [user.id for user in users])
    return [(user, codes.get(user.id, [])) for user in users], await _count(db, User)


async def list_partners(db: AsyncSession, page: int, page_size: int) -> tuple[list[tuple[Partner, int]], int]:
    await set_platform_wide_context(db)
    enrollment_counts = (
        select(PartnerSchoolEnrollment.partner_id, func.count().label("enrollment_count"))
        .where(PartnerSchoolEnrollment.partner_id.is_not(None))
        .group_by(PartnerSchoolEnrollment.partner_id)
        .subquery()
    )
    result = await db.execute(
        select(Partner, func.coalesce(enrollment_counts.c.enrollment_count, 0))
        .outerjoin(enrollment_counts, enrollment_counts.c.partner_id == Partner.id)
        .order_by(Partner.created_at.desc(), Partner.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return [(partner, int(count)) for partner, count in result.all()], await _count(db, Partner)


async def create_partner(db: AsyncSession, payload: PlatformPartnerCreate) -> tuple[Partner, User, str | None]:
    """Crée un compte partenaire : User (mot de passe aléatoire jamais communiqué + lien
    d'activation par email, même motif que users/service.py::create_or_attach_user), Partner,
    et UserRole PARTNER_ADMIN globale (organization_id ET school_id NULL), dans une seule
    transaction.

    Jamais `is_platform_admin=True` : un partenaire ne doit jamais passer
    `require_platform_admin`. Sa UserRole globale ne le rend PAS platform-wide côté RLS (code de
    rôle hors PLATFORM_ROLE_CODES, voir core/tenancy.py). Un email déjà utilisé est refusé (409)
    plutôt que rattaché : un compte scolaire existant ne devient jamais partenaire implicitement.
    """
    role_result = await db.execute(select(Role).where(Role.code == "PARTNER_ADMIN"))
    partner_role = role_result.scalar_one_or_none()
    if partner_role is None:
        raise RuntimeError("PARTNER_ADMIN role is missing — RBAC seed data was not applied")

    email = str(payload.email).lower()
    existing = await db.execute(select(User.id).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    await set_platform_wide_context(db)
    raw_token = generate_opaque_token()
    try:
        user = User(
            id=uuid.uuid4(),
            email=email,
            full_name=payload.full_name,
            phone=payload.phone,
            hashed_password=hash_password(generate_opaque_token()),
            is_platform_admin=False,
        )
        db.add(user)
        await db.flush()

        db.add(
            PasswordResetToken(
                id=uuid.uuid4(),
                user_id=user.id,
                token_hash=hash_opaque_token(raw_token),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
            )
        )
        partner = Partner(
            id=uuid.uuid4(),
            user_id=user.id,
            display_name=payload.display_name,
            phone=payload.phone,
            email=email,
        )
        db.add(partner)
        await db.flush()

        db.add(
            UserRole(
                id=uuid.uuid4(),
                user_id=user.id,
                role_id=partner_role.id,
                organization_id=None,
                school_id=None,
            )
        )
        await db.flush()
        await db.refresh(user)
        await db.refresh(partner)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use") from exc
    except Exception:
        await db.rollback()
        raise

    # Envoi APRÈS le commit (même principe que users/service.py, Sprint 1.7) : jamais d'email
    # pointant vers un compte qui n'existe pas réellement.
    await send_email_best_effort(
        user.email,
        "Bienvenue sur EduLinkage — activez votre compte partenaire",
        f"Un compte partenaire a été créé pour vous sur EduLinkage. Pour définir votre mot de passe, "
        f"ouvrez ce lien (valable {PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes) :\n"
        f"{settings.public_web_base_url}/reset-password?token={raw_token}",
    )
    dev_reset_token = None if settings.environment == "production" else raw_token
    return partner, user, dev_reset_token
