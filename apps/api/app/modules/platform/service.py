import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.core.tenancy import set_platform_wide_context
from app.modules.organizations.models import Organization
from app.modules.platform.schemas import PlatformOrganizationCreate
from app.modules.rbac.models import Role, UserRole
from app.modules.schools.models import School
from app.modules.students.models import Student
from app.modules.users.models import User


async def create_organization_with_admin(
    db: AsyncSession, payload: PlatformOrganizationCreate
) -> tuple[Organization, School, User]:
    """Crée une organisation, son école principale et son premier SCHOOL_ADMIN (rôle
    org-wide, `school_id` NULL, comme à l'ancienne inscription publique).

    Appelé uniquement après `require_platform_admin` : l'appelant est donc déjà un compte
    plateforme, et le contexte `app.is_platform_wide` est posé explicitement pour l'écriture
    multi-tables (les lignes créées ne sont visibles que dans la transaction courante).

    Atomique : une seule transaction. Tout échec (conflit d'unicité, erreur intermédiaire)
    annule l'ensemble, sans organisation ni école orpheline. Le mot de passe n'est jamais
    stocké ni journalisé en clair — seul son hash bcrypt (app/core/security.py) est persisté.
    """
    result = await db.execute(select(Role).where(Role.code == "SCHOOL_ADMIN"))
    school_admin_role = result.scalar_one_or_none()
    if school_admin_role is None:
        raise RuntimeError("SCHOOL_ADMIN role is missing — RBAC seed data was not applied")

    await set_platform_wide_context(db)

    org_input = payload.organization
    school_input = payload.school
    admin_input = payload.admin

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

        user = User(
            id=uuid.uuid4(),
            email=str(admin_input.email).lower(),
            full_name=admin_input.full_name,
            phone=admin_input.phone,
            hashed_password=hash_password(admin_input.password),
        )
        db.add(user)
        await db.flush()

        db.add(
            UserRole(
                id=uuid.uuid4(),
                user_id=user.id,
                role_id=school_admin_role.id,
                organization_id=organization.id,
                school_id=None,
            )
        )
        await db.flush()

        await db.refresh(organization)
        await db.refresh(school)
        await db.refresh(user)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug or admin email already in use",
        ) from exc
    except Exception:
        await db.rollback()
        raise

    return organization, school, user


async def get_platform_dashboard_summary(db: AsyncSession) -> dict:
    """Comptes globaux pour le tableau de bord plateforme (aucune donnée d'exemple/fictive).

    `organizations`/`schools`/`students` ont RLS active (voir migrations 0002/0004/0010), mais
    `apply_tenant_context` (core/tenancy.py) positionne déjà `app.is_platform_wide = 'true'` pour
    tout utilisateur ayant un rôle plateforme (organization_id NULL dans user_roles) — donc pour
    quiconque atteint cet endpoint (protégé par require_platform_admin). Aucun bypass RLS
    supplémentaire n'est nécessaire ici. `users` ne porte pas de RLS (table globale, non scopée
    par tenant), un simple count() suffit.
    """
    organization_count = (await db.execute(select(func.count()).select_from(Organization))).scalar_one()
    school_count = (await db.execute(select(func.count()).select_from(School))).scalar_one()
    user_count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    student_count = (await db.execute(select(func.count()).select_from(Student))).scalar_one()
    return {
        "organization_count": organization_count,
        "school_count": school_count,
        "user_count": user_count,
        "student_count": student_count,
    }
