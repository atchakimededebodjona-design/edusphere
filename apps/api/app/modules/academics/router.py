import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import CurrentUser, DbSession, ensure_permission, is_teacher_only
from app.modules.academics.models import (
    AcademicTerm,
    AcademicYear,
    ClassSubject,
    EducationLevel,
    Room,
    SchoolClass,
    Subject,
    TeacherAssignment,
)
from app.modules.academics.schemas import (
    AcademicTermCreate,
    AcademicTermOut,
    AcademicTermUpdate,
    AcademicYearCreate,
    AcademicYearOut,
    AcademicYearUpdate,
    ClassSubjectCreate,
    ClassSubjectOut,
    EducationLevelCreate,
    EducationLevelOut,
    EducationLevelUpdate,
    RoomCreate,
    RoomOut,
    RoomUpdate,
    SchoolClassCreate,
    SchoolClassOut,
    SchoolClassUpdate,
    SubjectCreate,
    SubjectOut,
    SubjectUpdate,
    TeacherAssignmentCreate,
    TeacherAssignmentOut,
)
from app.modules.schools.models import School

router = APIRouter()


# --- Helpers -----------------------------------------------------------------
async def _get_school_or_404(db: AsyncSession, school_id: uuid.UUID) -> School:
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    return school


async def _get_academic_year_or_404(db: AsyncSession, academic_year_id: uuid.UUID) -> AcademicYear:
    year = await db.get(AcademicYear, academic_year_id)
    if year is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Academic year not found")
    return year


async def _get_class_or_404(db: AsyncSession, class_id: uuid.UUID) -> SchoolClass:
    school_class = await db.get(SchoolClass, class_id)
    if school_class is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    return school_class


# --- Academic years ------------------------------------------------------------
@router.get("/academic-years", response_model=list[AcademicYearOut])
async def list_academic_years(
    db: DbSession, current_user: CurrentUser, school_id: uuid.UUID = Query(...)
) -> list[AcademicYear]:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "academics.read", organization_id=school.organization_id, school_id=school.id)
    result = await db.execute(
        select(AcademicYear).where(AcademicYear.school_id == school_id).order_by(AcademicYear.start_date.desc())
    )
    return list(result.scalars().all())


@router.post("/academic-years", response_model=AcademicYearOut, status_code=status.HTTP_201_CREATED)
async def create_academic_year(payload: AcademicYearCreate, db: DbSession, current_user: CurrentUser) -> AcademicYear:
    school = await _get_school_or_404(db, payload.school_id)
    await ensure_permission(db, current_user, "academics.manage", organization_id=school.organization_id, school_id=school.id)

    year = AcademicYear(
        id=uuid.uuid4(),
        school_id=school.id,
        organization_id=school.organization_id,
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_current=payload.is_current,
    )
    db.add(year)
    try:
        await db.flush()
        await db.refresh(year)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An academic year with this name already exists") from exc
    return year


@router.patch("/academic-years/{year_id}", response_model=AcademicYearOut)
async def update_academic_year(
    year_id: uuid.UUID, payload: AcademicYearUpdate, db: DbSession, current_user: CurrentUser
) -> AcademicYear:
    year = await _get_academic_year_or_404(db, year_id)
    await ensure_permission(db, current_user, "academics.manage", organization_id=year.organization_id, school_id=year.school_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(year, field, value)

    await db.flush()
    await db.refresh(year)
    await db.commit()
    return year


# --- Academic terms -------------------------------------------------------------
@router.get("/academic-terms", response_model=list[AcademicTermOut])
async def list_academic_terms(
    db: DbSession, current_user: CurrentUser, academic_year_id: uuid.UUID = Query(...)
) -> list[AcademicTerm]:
    year = await _get_academic_year_or_404(db, academic_year_id)
    await ensure_permission(db, current_user, "academics.read", organization_id=year.organization_id, school_id=year.school_id)
    result = await db.execute(
        select(AcademicTerm)
        .where(AcademicTerm.academic_year_id == academic_year_id)
        .order_by(AcademicTerm.order_index)
    )
    return list(result.scalars().all())


@router.post("/academic-terms", response_model=AcademicTermOut, status_code=status.HTTP_201_CREATED)
async def create_academic_term(payload: AcademicTermCreate, db: DbSession, current_user: CurrentUser) -> AcademicTerm:
    year = await _get_academic_year_or_404(db, payload.academic_year_id)
    await ensure_permission(db, current_user, "academics.manage", organization_id=year.organization_id, school_id=year.school_id)

    term = AcademicTerm(
        id=uuid.uuid4(),
        academic_year_id=year.id,
        school_id=year.school_id,
        organization_id=year.organization_id,
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        order_index=payload.order_index,
    )
    db.add(term)
    await db.flush()
    await db.refresh(term)
    await db.commit()
    return term


@router.patch("/academic-terms/{term_id}", response_model=AcademicTermOut)
async def update_academic_term(
    term_id: uuid.UUID, payload: AcademicTermUpdate, db: DbSession, current_user: CurrentUser
) -> AcademicTerm:
    term = await db.get(AcademicTerm, term_id)
    if term is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Academic term not found")
    await ensure_permission(db, current_user, "academics.manage", organization_id=term.organization_id, school_id=term.school_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(term, field, value)

    await db.flush()
    await db.refresh(term)
    await db.commit()
    return term


# --- Education levels ------------------------------------------------------------
@router.get("/education-levels", response_model=list[EducationLevelOut])
async def list_education_levels(
    db: DbSession, current_user: CurrentUser, school_id: uuid.UUID = Query(...)
) -> list[EducationLevel]:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "academics.read", organization_id=school.organization_id, school_id=school.id)
    result = await db.execute(
        select(EducationLevel).where(EducationLevel.school_id == school_id).order_by(EducationLevel.order_index)
    )
    return list(result.scalars().all())


@router.post("/education-levels", response_model=EducationLevelOut, status_code=status.HTTP_201_CREATED)
async def create_education_level(
    payload: EducationLevelCreate, db: DbSession, current_user: CurrentUser
) -> EducationLevel:
    school = await _get_school_or_404(db, payload.school_id)
    await ensure_permission(db, current_user, "academics.manage", organization_id=school.organization_id, school_id=school.id)

    level = EducationLevel(
        id=uuid.uuid4(),
        school_id=school.id,
        organization_id=school.organization_id,
        name=payload.name,
        order_index=payload.order_index,
    )
    db.add(level)
    try:
        await db.flush()
        await db.refresh(level)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An education level with this name already exists") from exc
    return level


@router.patch("/education-levels/{level_id}", response_model=EducationLevelOut)
async def update_education_level(
    level_id: uuid.UUID, payload: EducationLevelUpdate, db: DbSession, current_user: CurrentUser
) -> EducationLevel:
    level = await db.get(EducationLevel, level_id)
    if level is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Education level not found")
    await ensure_permission(db, current_user, "academics.manage", organization_id=level.organization_id, school_id=level.school_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(level, field, value)

    await db.flush()
    await db.refresh(level)
    await db.commit()
    return level


# --- Subjects ---------------------------------------------------------------------
@router.get("/subjects", response_model=list[SubjectOut])
async def list_subjects(db: DbSession, current_user: CurrentUser, school_id: uuid.UUID = Query(...)) -> list[Subject]:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "academics.read", organization_id=school.organization_id, school_id=school.id)
    result = await db.execute(select(Subject).where(Subject.school_id == school_id).order_by(Subject.name))
    return list(result.scalars().all())


@router.post("/subjects", response_model=SubjectOut, status_code=status.HTTP_201_CREATED)
async def create_subject(payload: SubjectCreate, db: DbSession, current_user: CurrentUser) -> Subject:
    school = await _get_school_or_404(db, payload.school_id)
    await ensure_permission(db, current_user, "academics.manage", organization_id=school.organization_id, school_id=school.id)

    subject = Subject(
        id=uuid.uuid4(), school_id=school.id, organization_id=school.organization_id, name=payload.name, code=payload.code
    )
    db.add(subject)
    try:
        await db.flush()
        await db.refresh(subject)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A subject with this name already exists") from exc
    return subject


@router.patch("/subjects/{subject_id}", response_model=SubjectOut)
async def update_subject(
    subject_id: uuid.UUID, payload: SubjectUpdate, db: DbSession, current_user: CurrentUser
) -> Subject:
    subject = await db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
    await ensure_permission(db, current_user, "academics.manage", organization_id=subject.organization_id, school_id=subject.school_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(subject, field, value)

    await db.flush()
    await db.refresh(subject)
    await db.commit()
    return subject


# --- Rooms -------------------------------------------------------------------------
@router.get("/rooms", response_model=list[RoomOut])
async def list_rooms(db: DbSession, current_user: CurrentUser, school_id: uuid.UUID = Query(...)) -> list[Room]:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "academics.read", organization_id=school.organization_id, school_id=school.id)
    result = await db.execute(select(Room).where(Room.school_id == school_id).order_by(Room.name))
    return list(result.scalars().all())


@router.post("/rooms", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
async def create_room(payload: RoomCreate, db: DbSession, current_user: CurrentUser) -> Room:
    school = await _get_school_or_404(db, payload.school_id)
    await ensure_permission(db, current_user, "academics.manage", organization_id=school.organization_id, school_id=school.id)

    room = Room(
        id=uuid.uuid4(),
        school_id=school.id,
        organization_id=school.organization_id,
        name=payload.name,
        capacity=payload.capacity,
    )
    db.add(room)
    try:
        await db.flush()
        await db.refresh(room)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A room with this name already exists") from exc
    return room


@router.patch("/rooms/{room_id}", response_model=RoomOut)
async def update_room(room_id: uuid.UUID, payload: RoomUpdate, db: DbSession, current_user: CurrentUser) -> Room:
    room = await db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    await ensure_permission(db, current_user, "academics.manage", organization_id=room.organization_id, school_id=room.school_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(room, field, value)

    await db.flush()
    await db.refresh(room)
    await db.commit()
    return room


# --- Classes -----------------------------------------------------------------------
@router.get("/classes", response_model=list[SchoolClassOut])
async def list_classes(
    db: DbSession, current_user: CurrentUser, school_id: uuid.UUID = Query(...)
) -> list[SchoolClass]:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "academics.read", organization_id=school.organization_id, school_id=school.id)

    stmt = select(SchoolClass).where(SchoolClass.school_id == school_id)
    if await is_teacher_only(db, current_user, school.organization_id, school.id):
        stmt = (
            stmt.join(ClassSubject, ClassSubject.class_id == SchoolClass.id)
            .join(TeacherAssignment, TeacherAssignment.class_subject_id == ClassSubject.id)
            .where(TeacherAssignment.user_id == current_user.id)
            .distinct()
        )
    result = await db.execute(stmt.order_by(SchoolClass.name))
    return list(result.scalars().all())


@router.post("/classes", response_model=SchoolClassOut, status_code=status.HTTP_201_CREATED)
async def create_class(payload: SchoolClassCreate, db: DbSession, current_user: CurrentUser) -> SchoolClass:
    year = await _get_academic_year_or_404(db, payload.academic_year_id)
    await ensure_permission(db, current_user, "academics.manage", organization_id=year.organization_id, school_id=year.school_id)

    level = await db.get(EducationLevel, payload.education_level_id)
    if level is None or level.school_id != year.school_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Education level does not belong to this school")

    school_class = SchoolClass(
        id=uuid.uuid4(),
        school_id=year.school_id,
        organization_id=year.organization_id,
        academic_year_id=year.id,
        education_level_id=level.id,
        name=payload.name,
        capacity=payload.capacity,
    )
    db.add(school_class)
    try:
        await db.flush()
        await db.refresh(school_class)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A class with this name already exists for this level and year") from exc
    return school_class


@router.get("/classes/{class_id}", response_model=SchoolClassOut)
async def get_class(class_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> SchoolClass:
    school_class = await _get_class_or_404(db, class_id)
    await ensure_permission(
        db, current_user, "academics.read", organization_id=school_class.organization_id, school_id=school_class.school_id
    )
    return school_class


@router.patch("/classes/{class_id}", response_model=SchoolClassOut)
async def update_class(
    class_id: uuid.UUID, payload: SchoolClassUpdate, db: DbSession, current_user: CurrentUser
) -> SchoolClass:
    school_class = await _get_class_or_404(db, class_id)
    await ensure_permission(
        db, current_user, "academics.manage", organization_id=school_class.organization_id, school_id=school_class.school_id
    )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(school_class, field, value)

    await db.flush()
    await db.refresh(school_class)
    await db.commit()
    return school_class


# --- Class <-> Subject ----------------------------------------------------------------
@router.post("/classes/{class_id}/subjects", response_model=ClassSubjectOut, status_code=status.HTTP_201_CREATED)
async def add_class_subject(
    class_id: uuid.UUID, payload: ClassSubjectCreate, db: DbSession, current_user: CurrentUser
) -> ClassSubject:
    school_class = await _get_class_or_404(db, class_id)
    await ensure_permission(
        db, current_user, "academics.manage", organization_id=school_class.organization_id, school_id=school_class.school_id
    )

    subject = await db.get(Subject, payload.subject_id)
    if subject is None or subject.school_id != school_class.school_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subject does not belong to this school")

    class_subject = ClassSubject(
        id=uuid.uuid4(),
        school_id=school_class.school_id,
        organization_id=school_class.organization_id,
        class_id=school_class.id,
        subject_id=subject.id,
        coefficient=payload.coefficient,
    )
    db.add(class_subject)
    try:
        await db.flush()
        await db.refresh(class_subject)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This subject is already attached to this class") from exc
    return class_subject


@router.get("/classes/{class_id}/subjects", response_model=list[ClassSubjectOut])
async def list_class_subjects(class_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> list[ClassSubject]:
    school_class = await _get_class_or_404(db, class_id)
    await ensure_permission(
        db, current_user, "academics.read", organization_id=school_class.organization_id, school_id=school_class.school_id
    )
    result = await db.execute(select(ClassSubject).where(ClassSubject.class_id == class_id))
    return list(result.scalars().all())


@router.delete("/classes/{class_id}/subjects/{class_subject_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_class_subject(
    class_id: uuid.UUID, class_subject_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> None:
    school_class = await _get_class_or_404(db, class_id)
    await ensure_permission(
        db, current_user, "academics.manage", organization_id=school_class.organization_id, school_id=school_class.school_id
    )

    class_subject = await db.get(ClassSubject, class_subject_id)
    if class_subject is None or class_subject.class_id != class_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class subject not found")

    await db.delete(class_subject)
    await db.commit()


# --- Teacher assignments -----------------------------------------------------------
@router.post("/classes/{class_id}/teachers", response_model=TeacherAssignmentOut, status_code=status.HTTP_201_CREATED)
async def assign_teacher(
    class_id: uuid.UUID, payload: TeacherAssignmentCreate, db: DbSession, current_user: CurrentUser
) -> TeacherAssignment:
    school_class = await _get_class_or_404(db, class_id)
    await ensure_permission(
        db, current_user, "academics.manage", organization_id=school_class.organization_id, school_id=school_class.school_id
    )

    result = await db.execute(
        select(ClassSubject).where(ClassSubject.class_id == class_id, ClassSubject.subject_id == payload.subject_id)
    )
    class_subject = result.scalar_one_or_none()
    if class_subject is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This subject must be attached to the class before assigning a teacher",
        )

    assignment = TeacherAssignment(
        id=uuid.uuid4(),
        school_id=school_class.school_id,
        organization_id=school_class.organization_id,
        user_id=payload.user_id,
        class_subject_id=class_subject.id,
    )
    db.add(assignment)
    try:
        await db.flush()
        await db.refresh(assignment)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This teacher is already assigned to this class subject") from exc
    return assignment


@router.get("/classes/{class_id}/teachers", response_model=list[TeacherAssignmentOut])
async def list_teacher_assignments(class_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> list[TeacherAssignment]:
    school_class = await _get_class_or_404(db, class_id)
    await ensure_permission(
        db, current_user, "academics.read", organization_id=school_class.organization_id, school_id=school_class.school_id
    )
    result = await db.execute(
        select(TeacherAssignment)
        .join(ClassSubject, ClassSubject.id == TeacherAssignment.class_subject_id)
        .where(ClassSubject.class_id == class_id)
    )
    return list(result.scalars().all())


@router.delete("/classes/{class_id}/teachers/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_teacher_assignment(
    class_id: uuid.UUID, assignment_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> None:
    school_class = await _get_class_or_404(db, class_id)
    await ensure_permission(
        db, current_user, "academics.manage", organization_id=school_class.organization_id, school_id=school_class.school_id
    )

    assignment = await db.get(TeacherAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher assignment not found")

    await db.delete(assignment)
    await db.commit()
