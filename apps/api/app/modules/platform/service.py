from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.schools.models import School
from app.modules.students.models import Student
from app.modules.users.models import User


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
