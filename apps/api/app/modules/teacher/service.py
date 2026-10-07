"""Périmètre enseignant : source de vérité côté serveur pour tout le portail TEACHER.

Un enseignant n'accède qu'aux classes pour lesquelles il possède une TeacherAssignment, et seulement
si le rôle TEACHER est rattaché à l'école de cette classe (même organisation, même école). Un compte
Platform Admin n'est jamais enseignant ici, même s'il porte un rôle TEACHER.
"""

import uuid
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academics.models import ClassSubject, EducationLevel, SchoolClass, Subject, TeacherAssignment
from app.modules.rbac.models import Role, UserRole
from app.modules.schools.models import School
from app.modules.users.models import User


@dataclass
class TeacherScope:
    school_ids: set[uuid.UUID] = field(default_factory=set)
    # class_subject_id -> class_id, pour toutes les affectations valides de l'enseignant.
    class_subject_to_class: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)
    class_ids: set[uuid.UUID] = field(default_factory=set)


async def _teacher_school_ids(db: AsyncSession, user: User) -> set[uuid.UUID]:
    result = await db.execute(
        select(UserRole.school_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user.id, Role.code == "TEACHER", UserRole.school_id.isnot(None))
    )
    return {row[0] for row in result.all()}


async def ensure_teacher(db: AsyncSession, user: User) -> TeacherScope:
    """Accès au portail : compte actif, non Platform Admin, porteur d'un rôle TEACHER scopé à une
    école. Renvoie le périmètre (vide si aucune affectation). Sinon 403."""
    if not user.is_active or user.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Teacher portal is reserved to teachers")
    school_ids = await _teacher_school_ids(db, user)
    if not school_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Teacher portal is reserved to teachers")
    return await teacher_scope(db, user, school_ids)


async def teacher_scope(db: AsyncSession, user: User, school_ids: set[uuid.UUID] | None = None) -> TeacherScope:
    """_get_teacher_assignment_scope : affectations de l'enseignant, limitées aux écoles où il porte
    le rôle TEACHER. Une affectation dont le rôle TEACHER a été retiré disparaît du périmètre."""
    if school_ids is None:
        school_ids = await _teacher_school_ids(db, user)
    scope = TeacherScope(school_ids=set(school_ids))
    if not school_ids:
        return scope
    result = await db.execute(
        select(ClassSubject.id, ClassSubject.class_id)
        .join(TeacherAssignment, TeacherAssignment.class_subject_id == ClassSubject.id)
        .where(TeacherAssignment.user_id == user.id, ClassSubject.school_id.in_(school_ids))
    )
    for class_subject_id, class_id in result.all():
        scope.class_subject_to_class[class_subject_id] = class_id
        scope.class_ids.add(class_id)
    return scope


async def ensure_class_access(db: AsyncSession, user: User, class_id: uuid.UUID) -> SchoolClass:
    """_ensure_teacher_class_access : la classe doit faire partie du périmètre. Une classe hors
    périmètre répond exactement comme une classe inexistante (404), pour ne rien révéler."""
    scope = await ensure_teacher(db, user)
    if class_id not in scope.class_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    school_class = await db.get(SchoolClass, class_id)
    if school_class is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    return school_class


async def ensure_class_subject_access(db: AsyncSession, user: User, class_subject_id: uuid.UUID) -> ClassSubject:
    """_ensure_teacher_class_subject_access : matière de classe affectée à cet enseignant."""
    scope = await ensure_teacher(db, user)
    if class_subject_id not in scope.class_subject_to_class:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class subject not found")
    class_subject = await db.get(ClassSubject, class_subject_id)
    if class_subject is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class subject not found")
    return class_subject


async def class_subjects_for_scope(
    db: AsyncSession, scope: TeacherScope, class_id: uuid.UUID
) -> list[tuple[ClassSubject, Subject]]:
    """Lignes (class_subject, subject) de la classe, restreintes aux matières affectées."""
    if class_id not in scope.class_ids:
        return []
    allowed = [cs for cs, cid in scope.class_subject_to_class.items() if cid == class_id]
    result = await db.execute(
        select(ClassSubject, Subject)
        .join(Subject, Subject.id == ClassSubject.subject_id)
        .where(ClassSubject.id.in_(allowed))
        .order_by(Subject.name)
    )
    return [(cs, subject) for cs, subject in result.all()]


async def level_name(db: AsyncSession, school_class: SchoolClass) -> str | None:
    level = await db.get(EducationLevel, school_class.education_level_id)
    return level.name if level else None


async def school_name(db: AsyncSession, school_id: uuid.UUID) -> str:
    school = await db.get(School, school_id)
    return school.name if school else ""
