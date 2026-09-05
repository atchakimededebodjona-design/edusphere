import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.permissions import CurrentUser, DbSession, ensure_permission, require_permission
from app.modules.organizations.models import Organization
from app.modules.organizations.schemas import OrganizationOut, OrganizationUpdate

router = APIRouter()


@router.get(
    "",
    response_model=list[OrganizationOut],
    dependencies=[Depends(require_permission("organizations.read"))],
)
async def list_organizations(db: DbSession) -> list[Organization]:
    result = await db.execute(select(Organization).order_by(Organization.name))
    return list(result.scalars().all())


@router.get("/{organization_id}", response_model=OrganizationOut)
async def get_organization(organization_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> Organization:
    organization = await db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    await ensure_permission(db, current_user, "organizations.read", organization_id=organization.id)
    return organization


@router.patch("/{organization_id}", response_model=OrganizationOut)
async def update_organization(
    organization_id: uuid.UUID, payload: OrganizationUpdate, db: DbSession, current_user: CurrentUser
) -> Organization:
    organization = await db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    await ensure_permission(db, current_user, "organizations.manage", organization_id=organization.id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(organization, field, value)

    # Phase 20 — refresh() AVANT commit : `organizations` a désormais RLS (FORCE ROW LEVEL
    # SECURITY), la ligne n'est visible que le temps de la transaction courante (le contexte
    # tenant posé par apply_tenant_context/SET LOCAL expire au commit). Un refresh() après commit
    # échouait silencieusement dès que RLS était active — même piège déjà documenté dans
    # app/modules/schools/router.py::update_school et app/modules/auth/service.py::register.
    await db.flush()
    await db.refresh(organization)
    await db.commit()
    return organization
