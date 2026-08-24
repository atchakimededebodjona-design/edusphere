import csv
import io
import uuid
from datetime import date, datetime

import openpyxl
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.students.models import Student
from app.modules.students.schemas import StudentImportReport, StudentImportRowError

REQUIRED_COLUMNS = ["matricule", "first_name", "last_name", "date_of_birth", "sex"]


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
