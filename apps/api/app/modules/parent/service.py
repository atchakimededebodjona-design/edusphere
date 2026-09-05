import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.students.models import Guardian, Student, StudentGuardian


async def list_children(db: AsyncSession, user_id: uuid.UUID) -> list[Student]:
    """Élèves dont l'utilisateur courant est un tuteur lié (Guardian.user_id) — toutes écoles
    confondues : un même compte parent peut être lié à des Guardian dans plusieurs écoles
    (ex. fratrie répartie sur deux établissements), le modèle ne l'interdit pas."""
    result = await db.execute(
        select(Student)
        .join(StudentGuardian, StudentGuardian.student_id == Student.id)
        .join(Guardian, Guardian.id == StudentGuardian.guardian_id)
        .where(Guardian.user_id == user_id)
        .order_by(Student.last_name, Student.first_name)
    )
    return list(result.scalars().unique().all())


async def get_child(db: AsyncSession, user_id: uuid.UUID, student_id: uuid.UUID) -> Student | None:
    """Seul point de contrôle d'accès du module `parent` : renvoie l'élève UNIQUEMENT s'il est
    un enfant de l'utilisateur courant (via Guardian.user_id -> StudentGuardian), sinon `None`.
    Le routeur doit systématiquement convertir `None` en 404 sans jamais révéler si l'élève
    existe réellement — un parent ne doit jamais pouvoir distinguer « cet élève n'existe pas »
    de « cet élève n'est pas le mien », même en connaissant l'ID."""
    result = await db.execute(
        select(Student)
        .join(StudentGuardian, StudentGuardian.student_id == Student.id)
        .join(Guardian, Guardian.id == StudentGuardian.guardian_id)
        .where(Guardian.user_id == user_id, Student.id == student_id)
    )
    return result.scalar_one_or_none()
