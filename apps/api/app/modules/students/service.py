import csv
import io
import re
import uuid
from datetime import date, datetime
from pathlib import Path

import openpyxl
from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import safe_filename
from app.modules.academics.models import SchoolClass
from app.modules.students.models import Student, StudentEnrollment
from app.modules.students.schemas import (
    StudentBulkEnrollmentOut,
    StudentImportReport,
    StudentImportRowError,
    StudentOut,
)

REQUIRED_COLUMNS = ["matricule", "first_name", "last_name", "date_of_birth", "sex"]

_DIGIT_RUN = re.compile(r"(\d+)")


def natural_sort_key(value: str) -> tuple[object, ...]:
    """Clé de tri "naturel" pour un matricule : les suites de chiffres sont comparées comme des
    nombres, pas caractère par caractère — EL-CM1-002 avant EL-CM1-010, jamais 010 avant 002 ni
    010 avant 2 (ce qu'un simple tri lexical produirait). Insensible à la casse pour la partie
    non numérique. Fonctionne quel que soit le format exact du matricule (pas de format imposé)."""
    parts = _DIGIT_RUN.split(value)
    return tuple((1, int(part)) if part.isdigit() else (0, part.lower()) for part in parts)


def _parse_rows(filename: str, content: bytes) -> list[dict]:
    lower = filename.lower()
    if lower.endswith(".csv"):
        text = content.decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(text)))

    if lower.endswith((".xlsx", ".xlsm")):
        workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = workbook.active
        rows_iter = sheet.iter_rows(values_only=True)
        header_row = next(rows_iter, None)
        if header_row is None:
            return []
        header = [str(h).strip() if h is not None else "" for h in header_row]
        rows = []
        for values in rows_iter:
            if all(v is None for v in values):
                continue
            rows.append({header[i]: values[i] for i in range(min(len(header), len(values)))})
        return rows

    raise ValueError("Unsupported file format — use .csv or .xlsx")


def _parse_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip())


async def import_students(
    db: AsyncSession, school_id: uuid.UUID, organization_id: uuid.UUID, file: UploadFile
) -> StudentImportReport:
    """Importe des élèves depuis un CSV ou Excel. Colonnes requises : matricule, first_name,
    last_name, date_of_birth (AAAA-MM-JJ), sex (M/F). Optionnelles : place_of_birth, address.

    Détecte les doublons par matricule OU par (prénom, nom, date de naissance) — aussi bien
    contre les élèves déjà en base que contre les lignes précédentes du même fichier — et
    produit un rapport d'erreurs ligne par ligne plutôt que d'échouer l'import entier.
    """
    content = await file.read()
    try:
        rows = _parse_rows(file.filename or "", content)
    except ValueError as exc:
        return StudentImportReport(
            total_rows=0, created=0, duplicates_skipped=0, errors=[StudentImportRowError(row=0, reason=str(exc))]
        )

    result = await db.execute(select(Student.matricule).where(Student.school_id == school_id))
    existing_matricules = {m for (m,) in result.all()}

    result2 = await db.execute(
        select(Student.first_name, Student.last_name, Student.date_of_birth).where(Student.school_id == school_id)
    )
    existing_identities = {(fn.lower(), ln.lower(), dob) for fn, ln, dob in result2.all()}

    seen_matricules: set[str] = set()
    seen_identities: set[tuple] = set()
    created = 0
    duplicates = 0
    errors: list[StudentImportRowError] = []

    for index, row in enumerate(rows, start=2):  # la ligne 1 est l'en-tête
        missing = [c for c in REQUIRED_COLUMNS if not row.get(c)]
        if missing:
            errors.append(StudentImportRowError(row=index, reason=f"Champs requis manquants : {', '.join(missing)}"))
            continue

        matricule = str(row["matricule"]).strip()
        first_name = str(row["first_name"]).strip()
        last_name = str(row["last_name"]).strip()
        sex = str(row["sex"]).strip().upper()

        if sex not in ("M", "F"):
            errors.append(StudentImportRowError(row=index, reason=f"Valeur sex invalide : {row['sex']!r}"))
            continue

        try:
            date_of_birth = _parse_date(row["date_of_birth"])
        except (ValueError, TypeError):
            errors.append(
                StudentImportRowError(row=index, reason=f"date_of_birth invalide : {row['date_of_birth']!r}")
            )
            continue

        identity_key = (first_name.lower(), last_name.lower(), date_of_birth)

        if matricule in existing_matricules or matricule in seen_matricules:
            duplicates += 1
            continue
        if identity_key in existing_identities or identity_key in seen_identities:
            duplicates += 1
            continue

        place_of_birth = row.get("place_of_birth")
        address = row.get("address")

        db.add(
            Student(
                id=uuid.uuid4(),
                school_id=school_id,
                organization_id=organization_id,
                matricule=matricule,
                first_name=first_name,
                last_name=last_name,
                date_of_birth=date_of_birth,
                sex=sex,
                place_of_birth=str(place_of_birth).strip() if place_of_birth else None,
                address=str(address).strip() if address else None,
            )
        )
        seen_matricules.add(matricule)
        seen_identities.add(identity_key)
        created += 1

    await db.commit()
    return StudentImportReport(total_rows=len(rows), created=created, duplicates_skipped=duplicates, errors=errors)


# --- Validation des uploads (photo / documents) ---------------------------------
# Le Content-Type envoyé par le navigateur n'est qu'une déclaration — jamais fiable seul. On
# détecte le type réel depuis le contenu (Pillow pour les images, signature de fichier pour le
# PDF) et on vérifie que l'extension déclarée est cohérente avec ce type détecté.
PHOTO_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB
DOCUMENT_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB

_PHOTO_MIME_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "image/jpeg": (".jpg", ".jpeg"),
    "image/png": (".png",),
    "image/webp": (".webp",),
}
_DOCUMENT_MIME_EXTENSIONS: dict[str, tuple[str, ...]] = {
    **_PHOTO_MIME_EXTENSIONS,
    "application/pdf": (".pdf",),
}

_IMAGE_FORMAT_TO_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


def _sniff_image_mime(content: bytes) -> str | None:
    try:
        with Image.open(io.BytesIO(content)) as img:
            img.verify()
            fmt = (img.format or "").upper()
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    return _IMAGE_FORMAT_TO_MIME.get(fmt)


def _sniff_mime(content: bytes, *, allow_pdf: bool) -> str | None:
    if allow_pdf and content[:5] == b"%PDF-":
        return "application/pdf"
    return _sniff_image_mime(content)


def _validate_upload(
    content: bytes,
    filename: str | None,
    *,
    allowed_mimes: dict[str, tuple[str, ...]],
    max_bytes: int,
    label: str,
) -> str:
    """Valide un fichier uploadé (photo ou document) et retourne son type MIME réel détecté.

    Lève HTTPException(422) avec un message précis si : fichier vide, trop volumineux, type non
    autorisé (détecté réellement, pas depuis le Content-Type déclaré), ou extension incohérente
    avec le type détecté (ex. un .png renommé en .pdf).
    """
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{label} vide.")
    if len(content) > max_bytes:
        max_mib = max_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{label} trop volumineux (maximum {max_mib} Mio).",
        )

    detected_mime = _sniff_mime(content, allow_pdf="application/pdf" in allowed_mimes)
    if detected_mime is None or detected_mime not in allowed_mimes:
        allowed_list = ", ".join(sorted(allowed_mimes))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{label} : type de fichier non autorisé (formats acceptés : {allowed_list}).",
        )

    extension = Path(safe_filename(filename or "")).suffix.lower()
    if extension and extension not in allowed_mimes[detected_mime]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{label} : l'extension du fichier ne correspond pas à son contenu réel.",
        )

    return detected_mime


def validate_photo_upload(content: bytes, filename: str | None) -> str:
    return _validate_upload(
        content, filename, allowed_mimes=_PHOTO_MIME_EXTENSIONS, max_bytes=PHOTO_MAX_BYTES, label="Photo"
    )


def validate_document_upload(content: bytes, filename: str | None) -> str:
    return _validate_upload(
        content, filename, allowed_mimes=_DOCUMENT_MIME_EXTENSIONS, max_bytes=DOCUMENT_MAX_BYTES, label="Document"
    )


# --- Affectation en masse à une classe -------------------------------------------------------------
class BulkEnrollmentError(HTTPException):
    """Erreur de validation métier (élève hors école, capacité insuffisante...) levée AVANT toute
    mutation — voir bulk_assign_students_to_class. Une sous-classe dédiée (plutôt que HTTPException
    nue) pour que le routeur n'ait besoin d'attraper qu'un seul type d'erreur attendue."""


async def bulk_assign_students_to_class(
    db: AsyncSession,
    *,
    school_id: uuid.UUID,
    organization_id: uuid.UUID,
    student_ids: list[uuid.UUID],
    school_class: SchoolClass,
    enrollment_date: date,
    dry_run: bool,
) -> StudentBulkEnrollmentOut:
    """Affecte (ou réaffecte) une liste d'élèves à `school_class`, pour l'année scolaire de cette
    classe (`school_class.academic_year_id`).

    Respecte la contrainte UNIQUE(student_id, academic_year_id) de StudentEnrollment : jamais de
    nouvelle ligne pour un élève déjà inscrit cette année-là, seulement une mise à jour de la ligne
    existante (class_id + status). Catégorisation (3 catégories disjointes, jamais mélangées) :

    - created    : aucune inscription existante pour cette année -> nouvelle ligne.
    - reassigned : inscription existante mais class_id différent, OU statut non-ACTIVE (quel que
                   soit le class_id) -> ligne existante mise à jour (réactivation incluse).
    - unchanged  : déjà dans CETTE classe avec le statut ACTIVE -> rien touché.

    Toute la validation (existence, école, capacité) est faite AVANT la moindre mutation ; la
    moindre erreur laisse la session intacte (atomicité — voir router.py pour le commit unique).
    `dry_run=True` : calcule et retourne exactement la même réponse (capacité, répartition) sans
    toucher à la session — utilisé par le panneau d'affectation pour afficher un aperçu avant
    confirmation, sans dupliquer cette logique côté frontend ou dans un second endpoint.
    """
    unique_ids = list(dict.fromkeys(student_ids))

    result = await db.execute(select(Student).where(Student.id.in_(unique_ids)))
    found = {student.id: student for student in result.scalars().all()}
    missing = [student_id for student_id in unique_ids if student_id not in found]
    if missing:
        raise BulkEnrollmentError(status_code=404, detail="One or more students were not found")

    students = [found[student_id] for student_id in unique_ids]
    wrong_school = [s.id for s in students if s.school_id != school_id]
    if wrong_school:
        raise BulkEnrollmentError(
            status_code=400, detail="All students must belong to the same school as the target class"
        )

    enrollment_result = await db.execute(
        select(StudentEnrollment).where(
            StudentEnrollment.student_id.in_(unique_ids),
            StudentEnrollment.academic_year_id == school_class.academic_year_id,
        )
    )
    existing_by_student = {e.student_id: e for e in enrollment_result.scalars().all()}

    to_create: list[Student] = []
    to_reassign: list[StudentEnrollment] = []
    unchanged_count = 0
    for student in students:
        existing = existing_by_student.get(student.id)
        if existing is None:
            to_create.append(student)
        elif existing.class_id == school_class.id and existing.status == "ACTIVE":
            unchanged_count += 1
        else:
            to_reassign.append(existing)

    # --- Capacité ------------------------------------------------------------------------------
    active_count_result = await db.execute(
        select(func.count()).select_from(StudentEnrollment).where(
            StudentEnrollment.class_id == school_class.id, StudentEnrollment.status == "ACTIVE"
        )
    )
    active_enrollment_count = active_count_result.scalar_one()

    students_needing_new_seat = len(to_create) + len(to_reassign)
    available_places: int | None = None
    capacity = school_class.capacity
    if capacity is not None:
        # Les élèves déjà ACTIVE dans CETTE classe (unchanged_count) sont déjà comptés dans
        # active_enrollment_count et ne doivent pas consommer une place supplémentaire.
        computed_available_places = capacity - active_enrollment_count + unchanged_count
        available_places = computed_available_places
        if students_needing_new_seat > computed_available_places:
            raise BulkEnrollmentError(
                status_code=409,
                detail=(
                    f"La classe {school_class.name} ne dispose que de {computed_available_places} "
                    f"place(s) disponible(s) pour {students_needing_new_seat} élève(s)."
                ),
            )

    if dry_run:
        return StudentBulkEnrollmentOut(
            target_class_id=school_class.id,
            target_class_name=school_class.name,
            academic_year_id=school_class.academic_year_id,
            capacity=school_class.capacity,
            active_enrollment_count=active_enrollment_count,
            available_places=available_places,
            selected_count=len(unique_ids),
            created_count=len(to_create),
            reassigned_count=len(to_reassign),
            unchanged_count=unchanged_count,
            students=[],
        )

    for student in to_create:
        db.add(
            StudentEnrollment(
                id=uuid.uuid4(),
                school_id=school_id,
                organization_id=organization_id,
                student_id=student.id,
                class_id=school_class.id,
                academic_year_id=school_class.academic_year_id,
                enrollment_date=enrollment_date,
            )
        )
    for enrollment in to_reassign:
        # L'enrollment_date existante n'est JAMAIS modifiée ici (seule une action explicite sur la
        # fiche élève le ferait) — seule la classe cible et la réactivation sont de cette action.
        enrollment.class_id = school_class.id
        enrollment.status = "ACTIVE"

    await db.flush()
    for student in students:
        await db.refresh(student)
    await db.commit()

    return StudentBulkEnrollmentOut(
        target_class_id=school_class.id,
        target_class_name=school_class.name,
        academic_year_id=school_class.academic_year_id,
        capacity=school_class.capacity,
        # Effectif ACTIVE mesuré avant cette opération (cohérent avec la réponse dry_run — c'est
        # ce chiffre que l'aperçu affiche comme "effectif actuel").
        active_enrollment_count=active_enrollment_count,
        available_places=available_places,
        selected_count=len(unique_ids),
        created_count=len(to_create),
        reassigned_count=len(to_reassign),
        unchanged_count=unchanged_count,
        students=[StudentOut.model_validate(student) for student in students],
    )
