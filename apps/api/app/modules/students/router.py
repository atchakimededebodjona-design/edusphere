import logging
import mimetypes
import uuid

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import CurrentUser, DbSession, ensure_permission, is_teacher_only
from app.core.storage import safe_filename, storage
from app.modules.academics.models import AcademicYear, ClassSubject, SchoolClass, TeacherAssignment
from app.modules.rbac.models import Role, UserRole
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
    StudentBulkEnrollmentCreate,
    StudentBulkEnrollmentOut,
    StudentBulkStatusUpdate,
    StudentBulkUpdateOut,
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
from app.modules.users.models import User

logger = logging.getLogger(__name__)

router = APIRouter()


async def _delete_storage_file_best_effort(path: str, *, context: str) -> None:
    """Supprime un fichier de stockage dont la base de données n'a PLUS aucune référence (la ligne
    DB a déjà été supprimée/mise à jour et committée avec succès avant cet appel — c'est elle
    l'autorité). Un échec ici laisse au pire un fichier orphelin sur le disque, jamais une
    référence DB cassée : on ne fait donc jamais échouer la requête pour autant, mais on ne
    masque pas non plus l'erreur — elle est journalisée avec le contexte nécessaire pour qu'un
    nettoyage manuel ou une alerte opérationnelle reste possible."""
    try:
        await storage.delete(path)
    except Exception:
        logger.error("Échec de suppression du fichier de stockage (%s) : path=%s", context, path, exc_info=True)


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
async def _teacher_enrolled_class_ids(
    db: AsyncSession, current_user: User, organization_id: uuid.UUID, school_id: uuid.UUID
) -> set[uuid.UUID] | None:
    """None = rôle administratif (DIRECTOR, SCHOOL_ADMIN, STAFF...), aucune restriction de lecture.
    Sinon, l'ensemble des classes où cet enseignant a une TeacherAssignment dans cette école — la
    même règle que grades/router.py::_teacher_assignment_scope, appliquée ici à `students.read`."""
    if not await is_teacher_only(db, current_user, organization_id, school_id):
        return None
    result = await db.execute(
        select(ClassSubject.class_id)
        .join(TeacherAssignment, TeacherAssignment.class_subject_id == ClassSubject.id)
        .where(TeacherAssignment.user_id == current_user.id, ClassSubject.school_id == school_id)
    )
    return {row[0] for row in result.all()}


async def _current_academic_year(db: AsyncSession, school_id: uuid.UUID) -> AcademicYear | None:
    result = await db.execute(
        select(AcademicYear).where(AcademicYear.school_id == school_id, AcademicYear.is_current.is_(True))
    )
    return result.scalars().first()


@router.get("/students", response_model=list[StudentOut])
async def list_students(
    db: DbSession,
    current_user: CurrentUser,
    school_id: uuid.UUID = Query(...),
    search: str | None = Query(None),
    class_id: uuid.UUID | None = Query(None),
    student_status: str | None = Query(None, alias="status"),
    unassigned_only: bool = Query(False),
) -> list[Student]:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "students.read", organization_id=school.organization_id, school_id=school.id)
    teacher_scope = await _teacher_enrolled_class_ids(db, current_user, school.organization_id, school.id)
    if teacher_scope is not None and class_id is not None and class_id not in teacher_scope:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not assigned to this class")

    current_year = await _current_academic_year(db, school_id)
    if unassigned_only and current_year is None:
        # "Non affectés" n'a de sens QUE relativement à une année scolaire courante. Sans elle, le
        # concept n'existe pas : renvoyer la liste complète serait trompeur (ferait croire que TOUS
        # les élèves sont non affectés). Le frontend désactive aussi ce filtre dans ce cas — ceci
        # est une seconde ligne de défense explicite côté backend, jamais une liste non filtrée.
        return []

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
    elif teacher_scope is not None:
        # Aucune classe demandée explicitement : un enseignant ne voit que les élèves de SES
        # classes affectées, jamais la liste complète de l'école (voir Phase "portail enseignant").
        stmt = stmt.join(StudentEnrollment, StudentEnrollment.student_id == Student.id).where(
            StudentEnrollment.class_id.in_(teacher_scope), StudentEnrollment.status == "ACTIVE"
        )
    if unassigned_only:
        # "Non affectés" = aucune inscription ACTIVE pour l'année scolaire courante de l'école.
        assert current_year is not None  # retour anticipé ci-dessus sinon — pour le vérificateur de types
        enrolled_ids = select(StudentEnrollment.student_id).where(
            StudentEnrollment.academic_year_id == current_year.id, StudentEnrollment.status == "ACTIVE"
        )
        stmt = stmt.where(Student.id.notin_(enrolled_ids))

    result = await db.execute(stmt)
    students = list(result.scalars().all())

    if students and current_year is not None:
        # Classe courante par élève, en UNE requête groupée — jamais un GET par élève (N+1).
        class_rows = await db.execute(
            select(StudentEnrollment.student_id, SchoolClass.id, SchoolClass.name)
            .join(SchoolClass, SchoolClass.id == StudentEnrollment.class_id)
            .where(
                StudentEnrollment.academic_year_id == current_year.id,
                StudentEnrollment.status == "ACTIVE",
                StudentEnrollment.student_id.in_([s.id for s in students]),
            )
        )
        class_by_student = {student_id: (cid, cname) for student_id, cid, cname in class_rows.all()}
        for student in students:
            class_id_name = class_by_student.get(student.id)
            if class_id_name is not None:
                student.current_class_id, student.current_class_name = class_id_name  # type: ignore[attr-defined]

    # Tri naturel par matricule (EL-CM1-002 avant EL-CM1-010) — voir service.py::natural_sort_key.
    # Fait côté Python plutôt qu'en SQL : aucune hypothèse sur le format exact du matricule, et
    # reste compatible avec tous les filtres ci-dessus (ils s'appliquent avant, en SQL).
    return sorted(students, key=lambda s: service.natural_sort_key(s.matricule))


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


@router.patch("/students/bulk", response_model=StudentBulkUpdateOut)
async def bulk_update_student_status(
    payload: StudentBulkStatusUpdate, db: DbSession, current_user: CurrentUser
) -> StudentBulkUpdateOut:
    """Modification en masse — STATUT UNIQUEMENT (cas d'usage : après un import, faire passer
    plusieurs élèves à ACTIVE/INACTIVE/...). Les champs individuels (identité, date de naissance,
    sexe) ne sont jamais proposés ici, par construction du schéma d'entrée.

    Tous les élèves doivent appartenir à LA MÊME école ; `students.manage` est vérifié sur cette
    école avant toute écriture. Un id hors du tenant de l'appelant est invisible sous RLS — il
    apparaît comme manquant, jamais comme une fuite cross-organization. Transaction atomique :
    un seul commit final, comme `update_student` ci-dessous.

    IMPORTANT (ordre de déclaration) : doit rester déclarée AVANT `/students/{student_id}` — ce
    paramètre n'est pas typé `{student_id:uuid}` dans le chemin, FastAPI ne valide donc le format
    UUID qu'après avoir fait correspondre la route par structure de chemin seule ; une déclaration
    après aurait fait matcher "bulk" comme student_id et échoué en 422 avant d'atteindre ce code."""
    unique_ids = list(dict.fromkeys(payload.student_ids))

    result = await db.execute(select(Student).where(Student.id.in_(unique_ids)))
    found = {student.id: student for student in result.scalars().all()}
    missing = [student_id for student_id in unique_ids if student_id not in found]
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more students were not found")

    students_to_update = [found[student_id] for student_id in unique_ids]
    school_ids = {student.school_id for student in students_to_update}
    if len(school_ids) > 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="All students must belong to the same school")
    school_id = school_ids.pop()
    organization_id = students_to_update[0].organization_id
    await ensure_permission(db, current_user, "students.manage", organization_id=organization_id, school_id=school_id)

    updated_count = 0
    unchanged_count = 0
    for student in students_to_update:
        if student.status != payload.status:
            db.add(
                StudentStatusHistory(
                    id=uuid.uuid4(),
                    school_id=student.school_id,
                    organization_id=student.organization_id,
                    student_id=student.id,
                    previous_status=student.status,
                    new_status=payload.status,
                    reason=payload.status_change_reason,
                    changed_by=current_user.id,
                )
            )
            student.status = payload.status
            updated_count += 1
        else:
            unchanged_count += 1

    await db.flush()
    for student in students_to_update:
        await db.refresh(student)
    await db.commit()
    return StudentBulkUpdateOut(
        updated_count=updated_count,
        unchanged_count=unchanged_count,
        students=[StudentOut.model_validate(student) for student in students_to_update],
    )


@router.post("/students/bulk-enrollment", response_model=StudentBulkEnrollmentOut)
async def bulk_enroll_students(
    payload: StudentBulkEnrollmentCreate, db: DbSession, current_user: CurrentUser, dry_run: bool = Query(False)
) -> StudentBulkEnrollmentOut:
    """Affecte en masse une liste d'élèves à une classe pour une année scolaire — voir
    service.py::bulk_assign_students_to_class pour la logique de catégorisation (nouveaux /
    réaffectés / inchangés) et la vérification de capacité.

    `dry_run=true` (query param) : calcule et renvoie exactement la même réponse SANS écrire en
    base — utilisé par le panneau d'affectation pour afficher un aperçu (capacité, répartition)
    avant que l'administrateur ne confirme.

    IMPORTANT (ordre de déclaration) : même raison que PATCH /students/bulk ci-dessus — doit
    rester déclarée AVANT /students/{student_id} pour ne pas être avalée par ce paramètre de
    chemin non typé `{student_id:uuid}`."""
    school_class = await db.get(SchoolClass, payload.class_id)
    if school_class is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    academic_year = await db.get(AcademicYear, payload.academic_year_id)
    if academic_year is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Academic year not found")
    if school_class.academic_year_id != academic_year.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Class does not belong to the requested academic year"
        )
    if academic_year.school_id != school_class.school_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Academic year does not belong to this class's school"
        )

    await ensure_permission(
        db, current_user, "students.manage",
        organization_id=school_class.organization_id, school_id=school_class.school_id,
    )

    try:
        return await service.bulk_assign_students_to_class(
            db,
            school_id=school_class.school_id,
            organization_id=school_class.organization_id,
            student_ids=payload.student_ids,
            school_class=school_class,
            enrollment_date=payload.enrollment_date,
            dry_run=dry_run,
        )
    except IntegrityError as exc:
        # Course très improbable (double soumission concurrente sur la même sélection) — la
        # pré-validation ci-dessus élimine déjà le cas attendu (élève déjà inscrit cette année).
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Concurrent modification detected, please retry"
        ) from exc


async def _ensure_student_in_teacher_scope(db: AsyncSession, current_user: User, student: Student) -> None:
    """Même garantie que GET /students/{student_id} : un TEACHER sans TeacherAssignment active sur
    la classe de cet élève ne doit jamais pouvoir confirmer son existence — 404, jamais 403, pour
    ne jamais révéler qu'un élève hors périmètre existe. Rôles administratifs (teacher_scope is
    None) : aucune restriction, comportement inchangé. Réutilisé par toutes les routes photo/
    documents pour appliquer EXACTEMENT le même périmètre que la fiche élève elle-même."""
    teacher_scope = await _teacher_enrolled_class_ids(db, current_user, student.organization_id, student.school_id)
    if teacher_scope is None:
        return
    enrolled = await db.execute(
        select(StudentEnrollment.id).where(
            StudentEnrollment.student_id == student.id,
            StudentEnrollment.status == "ACTIVE",
            StudentEnrollment.class_id.in_(teacher_scope),
        )
    )
    if enrolled.first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")


@router.get("/students/{student_id}", response_model=StudentOut)
async def get_student(student_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> Student:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(db, current_user, "students.read", organization_id=student.organization_id, school_id=student.school_id)
    await _ensure_student_in_teacher_scope(db, current_user, student)
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
    service.validate_photo_upload(content, file.filename)

    previous_photo_path = student.photo_path
    storage_path = f"students/{student.id}/photo_{uuid.uuid4().hex}_{safe_filename(file.filename)}"
    await storage.upload(storage_path, content)

    try:
        student.photo_path = storage_path
        await db.flush()
        await db.refresh(student)
        await db.commit()
    except Exception:
        await db.rollback()
        # Le nouveau fichier n'a JAMAIS été référencé en base (le commit a échoué) : sa suppression
        # est un nettoyage d'orphelin, pas une correction de référence cassée. Si elle échoue aussi,
        # l'erreur d'origine (DB) reste celle remontée au client — journalisée séparément ici pour
        # qu'un nettoyage manuel reste possible, jamais masquée.
        try:
            await storage.delete(storage_path)
        except Exception:
            logger.error(
                "Échec de nettoyage du fichier après échec d'upload photo : path=%s", storage_path, exc_info=True
            )
        raise

    # La nouvelle photo est sauvegardée en base : on ne supprime l'ancien fichier qu'APRÈS ce
    # commit réussi, jamais avant (sinon un échec de commit laisserait l'élève sans photo du tout).
    if previous_photo_path and previous_photo_path != storage_path:
        await _delete_storage_file_best_effort(previous_photo_path, context="remplacement de photo élève")
    return student


@router.get("/students/{student_id}/photo")
async def get_student_photo(student_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> Response:
    student = await _get_student_or_404(db, student_id)
    if student.photo_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student photo not found")
    await ensure_permission(db, current_user, "students.read", organization_id=student.organization_id, school_id=student.school_id)
    await _ensure_student_in_teacher_scope(db, current_user, student)

    content = await storage.download(student.photo_path)
    media_type = mimetypes.guess_type(student.photo_path)[0] or "application/octet-stream"
    return Response(content=content, media_type=media_type)


@router.delete("/students/{student_id}/photo", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student_photo(student_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> None:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(db, current_user, "students.manage", organization_id=student.organization_id, school_id=student.school_id)
    await _ensure_student_in_teacher_scope(db, current_user, student)

    photo_path = student.photo_path
    if photo_path is None:
        # Idempotent : supprimer une photo déjà absente n'est pas une erreur.
        return

    student.photo_path = None
    await db.flush()
    await db.commit()
    await _delete_storage_file_best_effort(photo_path, context="suppression de photo élève")


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
    await _ensure_student_in_teacher_scope(db, current_user, student)

    document_type = document_type.strip()
    if not document_type or len(document_type) > 64:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="document_type est requis et doit faire au plus 64 caractères.",
        )

    content = await file.read()
    detected_mime = service.validate_document_upload(content, file.filename)

    storage_path = f"students/{student.id}/documents/{uuid.uuid4().hex}_{safe_filename(file.filename)}"
    await storage.upload(storage_path, content)

    document = StudentDocument(
        id=uuid.uuid4(),
        school_id=student.school_id,
        organization_id=student.organization_id,
        student_id=student.id,
        document_type=document_type,
        file_path=storage_path,
        original_filename=file.filename or "document",
        mime_type=detected_mime,
        file_size=len(content),
        uploaded_by=current_user.id,
    )
    db.add(document)
    try:
        await db.flush()
        await db.refresh(document)
        await db.commit()
    except Exception:
        await db.rollback()
        # Même raisonnement que upload_student_photo ci-dessus : ce fichier n'a jamais été
        # référencé en base, son nettoyage est best-effort et ne doit jamais masquer l'erreur
        # DB d'origine, qui reste celle remontée au client.
        try:
            await storage.delete(storage_path)
        except Exception:
            logger.error(
                "Échec de nettoyage du fichier après échec d'upload document : path=%s", storage_path, exc_info=True
            )
        raise
    return document


@router.get("/students/{student_id}/documents", response_model=list[StudentDocumentOut])
async def list_student_documents(student_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> list[StudentDocument]:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(db, current_user, "students.read", organization_id=student.organization_id, school_id=student.school_id)
    await _ensure_student_in_teacher_scope(db, current_user, student)
    result = await db.execute(select(StudentDocument).where(StudentDocument.student_id == student_id))
    return list(result.scalars().all())


@router.get("/students/{student_id}/documents/{document_id}")
async def download_student_document(
    student_id: uuid.UUID, document_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> Response:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(db, current_user, "students.read", organization_id=student.organization_id, school_id=student.school_id)
    await _ensure_student_in_teacher_scope(db, current_user, student)

    document = await db.get(StudentDocument, document_id)
    if document is None or document.student_id != student_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    content = await storage.download(document.file_path)
    media_type = document.mime_type or mimetypes.guess_type(document.original_filename)[0] or "application/octet-stream"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{document.original_filename}"'},
    )


@router.delete("/students/{student_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student_document(
    student_id: uuid.UUID, document_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> None:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(db, current_user, "students.manage", organization_id=student.organization_id, school_id=student.school_id)
    await _ensure_student_in_teacher_scope(db, current_user, student)

    document = await db.get(StudentDocument, document_id)
    if document is None or document.student_id != student_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    file_path = document.file_path
    # Supprime d'abord la ligne en base, puis le fichier physique : si le commit échouait après
    # une suppression du fichier, la ligne resterait en base en pointant vers un fichier disparu.
    # L'ordre inverse ne laisse au pire qu'un fichier orphelin sur le disque, jamais une 404 surprise.
    await db.delete(document)
    await db.commit()
    await _delete_storage_file_best_effort(file_path, context="suppression de document élève")


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


async def _ensure_valid_guardian_user_link(db: AsyncSession, guardian: Guardian, user_id: uuid.UUID) -> None:
    """Un Guardian ne peut être lié qu'à un compte existant, ayant réellement un rôle PARENT
    dans l'école de ce Guardian (Phase 7 — décision validée : aucune permission RBAC nouvelle,
    le lien lui-même EST le contrôle d'accès). Le doublon (school_id, user_id) est laissé à la
    contrainte d'unicité partielle de la migration 0008, remontée en 409 par l'appelant."""
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

    result = await db.execute(
        select(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user_id, Role.code == "PARENT", UserRole.school_id == guardian.school_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not have a PARENT role in this guardian's school",
        )


@router.patch("/guardians/{guardian_id}", response_model=GuardianOut)
async def update_guardian(
    guardian_id: uuid.UUID, payload: GuardianUpdate, db: DbSession, current_user: CurrentUser
) -> Guardian:
    guardian = await _get_guardian_or_404(db, guardian_id)
    await ensure_permission(db, current_user, "students.manage", organization_id=guardian.organization_id, school_id=guardian.school_id)

    update_data = payload.model_dump(exclude_unset=True)
    if "user_id" in update_data and update_data["user_id"] is not None:
        await _ensure_valid_guardian_user_link(db, guardian, update_data["user_id"])

    for field, value in update_data.items():
        setattr(guardian, field, value)

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This user is already linked to a guardian in this school"
        ) from exc
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
