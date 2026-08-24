import uuid

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import CurrentUser, DbSession, ensure_permission
from app.core.storage import storage
from app.modules.academics.models import SchoolClass
from app.modules.schools.models import School
from app.modules.students import service
from app.modules.students.models import (
    Guardian,
    Student,
    StudentDocument,
    StudentEnrollment,
    StudentGuardian,
    StudentStatusHistory,
)
from app.modules.students.schemas import (
    GuardianCreate,
    GuardianOut,
    GuardianUpdate,
    StudentCreate,
    StudentDocumentOut,
    StudentEnrollmentCreate,
    StudentEnrollmentOut,
    StudentEnrollmentUpdate,
    StudentGuardianCreate,
    StudentGuardianOut,
    StudentImportReport,
    StudentOut,
    StudentUpdate,
)

router = APIRouter()


# --- Helpers -----------------------------------------------------------------
async def _get_school_or_404(db: AsyncSession, school_id: uuid.UUID) -> School:
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    return school


async def _get_student_or_404(db: AsyncSession, student_id: uuid.UUID) -> Student:
    student = await db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


async def _get_guardian_or_404(db: AsyncSession, guardian_id: uuid.UUID) -> Guardian:
    guardian = await db.get(Guardian, guardian_id)
    if guardian is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guardian not found")
    return guardian


# --- Students ------------------------------------------------------------------
@router.get("/students", response_model=list[StudentOut])
async def list_students(
    db: DbSession,
    current_user: CurrentUser,
    school_id: uuid.UUID = Query(...),
    search: str | None = Query(None),
    class_id: uuid.UUID | None = Query(None),
    student_status: str | None = Query(None, alias="status"),
) -> list[Student]:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "students.read", organization_id=school.organization_id, school_id=school.id)

    stmt = select(Student).where(Student.school_id == school_id)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                Student.first_name.ilike(pattern),
                Student.last_name.ilike(pattern),
                Student.matricule.ilike(pattern),
            )
        )
    if student_status:
        stmt = stmt.where(Student.status == student_status)
    if class_id:
        stmt = stmt.join(StudentEnrollment, StudentEnrollment.student_id == Student.id).where(
            StudentEnrollment.class_id == class_id, StudentEnrollment.status == "ACTIVE"
        )

    result = await db.execute(stmt.order_by(Student.last_name, Student.first_name))
    return list(result.scalars().all())


@router.post("/students", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
async def create_student(payload: StudentCreate, db: DbSession, current_user: CurrentUser) -> Student:
    school = await _get_school_or_404(db, payload.school_id)
    await ensure_permission(db, current_user, "students.manage", organization_id=school.organization_id, school_id=school.id)

    student = Student(
        id=uuid.uuid4(),
        school_id=school.id,
        organization_id=school.organization_id,
        matricule=payload.matricule,
        first_name=payload.first_name,
        last_name=payload.last_name,
        date_of_birth=payload.date_of_birth,
        sex=payload.sex,
        place_of_birth=payload.place_of_birth,
        address=payload.address,
    )
    db.add(student)
    try:
        await db.flush()
        await db.refresh(student)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A student with this matricule already exists") from exc
    return student


@router.get("/students/{student_id}", response_model=StudentOut)
async def get_student(student_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> Student:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(db, current_user, "students.read", organization_id=student.organization_id, school_id=student.school_id)
    return student


@router.patch("/students/{student_id}", response_model=StudentOut)
async def update_student(
    student_id: uuid.UUID, payload: StudentUpdate, db: DbSession, current_user: CurrentUser
) -> Student:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(db, current_user, "students.manage", organization_id=student.organization_id, school_id=student.school_id)

    updates = payload.model_dump(exclude_unset=True, exclude={"status_change_reason"})
    new_status = updates.get("status")
    if new_status and new_status != student.status:
        db.add(
            StudentStatusHistory(
                id=uuid.uuid4(),
                school_id=student.school_id,
                organization_id=student.organization_id,
                student_id=student.id,
                previous_status=student.status,
                new_status=new_status,
                reason=payload.status_change_reason,
                changed_by=current_user.id,
            )
        )

    for field, value in updates.items():
        setattr(student, field, value)

    await db.flush()
    await db.refresh(student)
    await db.commit()
    return student


@router.post("/students/import", response_model=StudentImportReport)
async def import_students(
    db: DbSession,
    current_user: CurrentUser,
    school_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
) -> StudentImportReport:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "students.manage", organization_id=school.organization_id, school_id=school.id)
    return await service.import_students(db, school.id, school.organization_id, file)


# --- Photo -----------------------------------------------------------------------
@router.post("/students/{student_id}/photo", response_model=StudentOut)
async def upload_student_photo(
    student_id: uuid.UUID, db: DbSession, current_user: CurrentUser, file: UploadFile = File(...)
) -> Student:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(db, current_user, "students.manage", organization_id=student.organization_id, school_id=student.school_id)

    content = await file.read()
    storage_path = f"students/{student.id}/photo_{uuid.uuid4().hex}_{file.filename}"
    await storage.upload(storage_path, content)

    student.photo_path = storage_path
    await db.flush()
    await db.refresh(student)
    await db.commit()
    return student


# --- Documents ---------------------------------------------------------------------
@router.post("/students/{student_id}/documents", response_model=StudentDocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_student_document(
    student_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    document_type: str = Form(...),
    file: UploadFile = File(...),
) -> StudentDocument:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(db, current_user, "students.manage", organization_id=student.organization_id, school_id=student.school_id)

    content = await file.read()
    storage_path = f"students/{student.id}/documents/{uuid.uuid4().hex}_{file.filename}"
    await storage.upload(storage_path, content)

    document = StudentDocument(
        id=uuid.uuid4(),
        school_id=student.school_id,
        organization_id=student.organization_id,
        student_id=student.id,
        document_type=document_type,
        file_path=storage_path,
        original_filename=file.filename or "document",
        uploaded_by=current_user.id,
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)
    await db.commit()
    return document


@router.get("/students/{student_id}/documents", response_model=list[StudentDocumentOut])
async def list_student_documents(student_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> list[StudentDocument]:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(db, current_user, "students.read", organization_id=student.organization_id, school_id=student.school_id)
    result = await db.execute(select(StudentDocument).where(StudentDocument.student_id == student_id))
    return list(result.scalars().all())


@router.delete("/students/{student_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student_document(
    student_id: uuid.UUID, document_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> None:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(db, current_user, "students.manage", organization_id=student.organization_id, school_id=student.school_id)

    document = await db.get(StudentDocument, document_id)
    if document is None or document.student_id != student_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    await storage.delete(document.file_path)
    await db.delete(document)
    await db.commit()


# --- Guardians -----------------------------------------------------------------
@router.get("/guardians", response_model=list[GuardianOut])
async def list_guardians(db: DbSession, current_user: CurrentUser, school_id: uuid.UUID = Query(...)) -> list[Guardian]:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "students.read", organization_id=school.organization_id, school_id=school.id)
    result = await db.execute(select(Guardian).where(Guardian.school_id == school_id).order_by(Guardian.full_name))
    return list(result.scalars().all())


@router.post("/guardians", response_model=GuardianOut, status_code=status.HTTP_201_CREATED)
async def create_guardian(payload: GuardianCreate, db: DbSession, current_user: CurrentUser) -> Guardian:
    school = await _get_school_or_404(db, payload.school_id)
    await ensure_permission(db, current_user, "students.manage", organization_id=school.organization_id, school_id=school.id)

    guardian = Guardian(
        id=uuid.uuid4(),
        school_id=school.id,
        organization_id=school.organization_id,
        full_name=payload.full_name,
        relationship_type=payload.relationship_type,
        phone=payload.phone,
        email=payload.email,
        address=payload.address,
        is_emergency_contact=payload.is_emergency_contact,
    )
    db.add(guardian)
    await db.flush()
    await db.refresh(guardian)
    await db.commit()
    return guardian


@router.patch("/guardians/{guardian_id}", response_model=GuardianOut)
async def update_guardian(
    guardian_id: uuid.UUID, payload: GuardianUpdate, db: DbSession, current_user: CurrentUser
) -> Guardian:
    guardian = await _get_guardian_or_404(db, guardian_id)
    await ensure_permission(db, current_user, "students.manage", organization_id=guardian.organization_id, school_id=guardian.school_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(guardian, field, value)

    await db.flush()
    await db.refresh(guardian)
    await db.commit()
    return guardian


@router.post("/students/{student_id}/guardians", response_model=StudentGuardianOut, status_code=status.HTTP_201_CREATED)
async def attach_guardian(
    student_id: uuid.UUID, payload: StudentGuardianCreate, db: DbSession, current_user: CurrentUser
) -> StudentGuardian:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(db, current_user, "students.manage", organization_id=student.organization_id, school_id=student.school_id)

    guardian = await _get_guardian_or_404(db, payload.guardian_id)
    if guardian.school_id != student.school_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Guardian does not belong to this school")

    link = StudentGuardian(
        id=uuid.uuid4(),
        school_id=student.school_id,
        organization_id=student.organization_id,
        student_id=student.id,
        guardian_id=guardian.id,
        is_primary_contact=payload.is_primary_contact,
    )
    db.add(link)
    try:
        await db.flush()
        await db.refresh(link)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This guardian is already attached to this student") from exc
    return link


@router.get("/students/{student_id}/guardians", response_model=list[StudentGuardianOut])
async def list_student_guardians(student_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> list[StudentGuardian]:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(db, current_user, "students.read", organization_id=student.organization_id, school_id=student.school_id)
    result = await db.execute(select(StudentGuardian).where(StudentGuardian.student_id == student_id))
    return list(result.scalars().all())


@router.delete("/students/{student_id}/guardians/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_guardian(student_id: uuid.UUID, link_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> None:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(db, current_user, "students.manage", organization_id=student.organization_id, school_id=student.school_id)

    link = await db.get(StudentGuardian, link_id)
    if link is None or link.student_id != student_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guardian link not found")

    await db.delete(link)
    await db.commit()


# --- Enrollments ---------------------------------------------------------------
@router.post("/students/{student_id}/enrollments", response_model=StudentEnrollmentOut, status_code=status.HTTP_201_CREATED)
async def create_enrollment(
    student_id: uuid.UUID, payload: StudentEnrollmentCreate, db: DbSession, current_user: CurrentUser
) -> StudentEnrollment:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(db, current_user, "students.manage", organization_id=student.organization_id, school_id=student.school_id)

    school_class = await db.get(SchoolClass, payload.class_id)
    if school_class is None or school_class.school_id != student.school_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Class does not belong to this school")

    enrollment = StudentEnrollment(
        id=uuid.uuid4(),
        school_id=student.school_id,
        organization_id=student.organization_id,
        student_id=student.id,
        class_id=school_class.id,
        academic_year_id=school_class.academic_year_id,
        enrollment_date=payload.enrollment_date,
    )
    db.add(enrollment)
    try:
        await db.flush()
        await db.refresh(enrollment)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This student is already enrolled for this academic year") from exc
    return enrollment


@router.get("/students/{student_id}/enrollments", response_model=list[StudentEnrollmentOut])
async def list_enrollments(student_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> list[StudentEnrollment]:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(db, current_user, "students.read", organization_id=student.organization_id, school_id=student.school_id)
    result = await db.execute(
        select(StudentEnrollment).where(StudentEnrollment.student_id == student_id).order_by(StudentEnrollment.enrollment_date.desc())
    )
    return list(result.scalars().all())


@router.patch("/enrollments/{enrollment_id}", response_model=StudentEnrollmentOut)
async def update_enrollment(
    enrollment_id: uuid.UUID, payload: StudentEnrollmentUpdate, db: DbSession, current_user: CurrentUser
) -> StudentEnrollment:
    enrollment = await db.get(StudentEnrollment, enrollment_id)
    if enrollment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")
    await ensure_permission(
        db, current_user, "students.manage", organization_id=enrollment.organization_id, school_id=enrollment.school_id
    )

    enrollment.status = payload.status
    await db.flush()
    await db.refresh(enrollment)
    await db.commit()
    return enrollment
