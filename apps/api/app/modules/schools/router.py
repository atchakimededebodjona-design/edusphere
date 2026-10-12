import mimetypes
import uuid

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select

from app.core.permissions import CurrentUser, DbSession, ensure_permission
from app.core.storage import safe_filename, storage
from app.modules.schools import service
from app.modules.schools.models import School
from app.modules.schools.schemas import SchoolDashboardOut, SchoolOut, SchoolUpdate

router = APIRouter()


@router.get("", response_model=list[SchoolOut])
async def list_schools(
    db: DbSession, current_user: CurrentUser, organization_id: uuid.UUID = Query(...)
) -> list[School]:
    await ensure_permission(db, current_user, "schools.read", organization_id=organization_id)
    result = await db.execute(
        select(School).where(School.organization_id == organization_id).order_by(School.name)
    )
    return list(result.scalars().all())


# P1-2 — POST /schools n'est PLUS un point d'entrée de création d'école.
#
# Il insérait directement `School(**payload)` : aucune ligne `partner_school_enrollments` (source
# d'acquisition PR #17/#19), aucun administrateur résolu par le cœur central (PR #20), aucune
# protection de doublon de nom (PR #19). Le modèle d'acquisition ne connaît que PLATFORM_OWNER
# (inscription par la plateforme) et PARTNER (inscription par un partenaire) : une école créée par
# l'admin de l'organisation elle-même n'est ni l'une ni l'autre — lui attribuer PLATFORM_OWNER serait
# faux, hériter du partenaire de l'organisation inventerait une éligibilité à commission, et une
# troisième source n'est pas un concept validé. Toute création passe donc par le workflow
# d'enrôlement central (platform/service.py::create_organization_school_admin /
# add_school_to_organization) via :
#   - POST /api/v1/platform/organizations/{organization_id}/schools (PLATFORM_OWNER / SUPER_ADMIN)
#   - POST /api/v1/partner/organizations/{organization_id}/schools  (PARTNER_ADMIN, son périmètre)
# Réponse explicite 410 Gone (jamais un 404/405 silencieux) pour tout appelant authentifié, sans
# lire ni créer quoi que ce soit. GET / PATCH / logo de /schools restent inchangés.
SCHOOL_CREATION_MOVED_DETAIL = (
    "School creation goes through the enrollment workflow: "
    "POST /api/v1/platform/organizations/{organization_id}/schools or "
    "POST /api/v1/partner/organizations/{organization_id}/schools"
)


@router.post("", status_code=status.HTTP_410_GONE, deprecated=True)
async def create_school(_current_user: CurrentUser) -> None:
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=SCHOOL_CREATION_MOVED_DETAIL)


@router.get("/{school_id}", response_model=SchoolOut)
async def get_school(school_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> School:
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    await ensure_permission(
        db, current_user, "schools.read", organization_id=school.organization_id, school_id=school.id
    )
    return school


@router.get("/{school_id}/dashboard", response_model=SchoolDashboardOut)
async def get_school_dashboard(school_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> SchoolDashboardOut:
    """Tableau de bord admin (Phase 10) — nécessite une lecture sur les 4 domaines agrégés,
    pas de nouvelle permission (voir docs/phases/PHASE_10_IMPLEMENTATION.md)."""
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    for permission in ("students.read", "attendance.read", "grades.read", "report_cards.read"):
        await ensure_permission(
            db, current_user, permission, organization_id=school.organization_id, school_id=school.id
        )
    summary = await service.get_dashboard_summary(db, school)
    return SchoolDashboardOut(**summary)


@router.patch("/{school_id}", response_model=SchoolOut)
async def update_school(
    school_id: uuid.UUID, payload: SchoolUpdate, db: DbSession, current_user: CurrentUser
) -> School:
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    await ensure_permission(
        db, current_user, "schools.manage", organization_id=school.organization_id, school_id=school.id
    )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(school, field, value)

    # refresh() AVANT commit — voir commentaire dans create_school() ci-dessus.
    await db.flush()
    await db.refresh(school)
    await db.commit()
    return school


@router.post("/{school_id}/logo", response_model=SchoolOut)
async def upload_school_logo(
    school_id: uuid.UUID, db: DbSession, current_user: CurrentUser, file: UploadFile = File(...)
) -> School:
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    await ensure_permission(
        db, current_user, "schools.manage", organization_id=school.organization_id, school_id=school.id
    )

    content = await file.read()
    storage_path = f"schools/{school.id}/logo_{uuid.uuid4().hex}_{safe_filename(file.filename)}"
    await storage.upload(storage_path, content)

    school.logo_path = storage_path
    await db.flush()
    await db.refresh(school)
    await db.commit()
    return school


@router.get("/{school_id}/logo")
async def get_school_logo(school_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> Response:
    school = await db.get(School, school_id)
    if school is None or school.logo_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School logo not found")
    await ensure_permission(
        db, current_user, "schools.read", organization_id=school.organization_id, school_id=school.id
    )

    content = await storage.download(school.logo_path)
    media_type = mimetypes.guess_type(school.logo_path)[0] or "application/octet-stream"
    return Response(content=content, media_type=media_type)
