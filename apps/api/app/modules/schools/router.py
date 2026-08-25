import uuid

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.permissions import CurrentUser, DbSession, ensure_permission
from app.core.storage import storage
from app.modules.schools.models import School
from app.modules.schools.schemas import SchoolCreate, SchoolOut, SchoolUpdate

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


@router.post("", response_model=SchoolOut, status_code=status.HTTP_201_CREATED)
async def create_school(payload: SchoolCreate, db: DbSession, current_user: CurrentUser) -> School:
    await ensure_permission(db, current_user, "schools.manage", organization_id=payload.organization_id)

    school = School(**payload.model_dump())
    db.add(school)
    try:
        # refresh() AVANT commit : `schools` a RLS activé, la ligne n'est visible que le temps
        # de la transaction courante (contexte tenant posé par apply_tenant_context / SET LOCAL
        # via set_config, qui expire au commit). Voir app/modules/auth/service.py::register
        # pour la même remarque détaillée.
        await db.flush()
        await db.refresh(school)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A school with this slug already exists in this organization"
        ) from exc
    return school


@router.get("/{school_id}", response_model=SchoolOut)
async def get_school(school_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> School:
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    await ensure_permission(
        db, current_user, "schools.read", organization_id=school.organization_id, school_id=school.id
    )
    return school


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
    storage_path = f"schools/{school.id}/logo_{uuid.uuid4().hex}_{file.filename}"
    await storage.upload(storage_path, content)

    school.logo_path = storage_path
    await db.flush()
    await db.refresh(school)
    await db.commit()
    return school
