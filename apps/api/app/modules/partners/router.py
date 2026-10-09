"""Endpoints partenaire commercial (PR #17) — tous sous `/partner/*`.

Chaque route exige un code `partner.*` précis (détenu seulement par PARTNER_ADMIN, et SUPER_ADMIN
par convention du catalogue) : 403 pour tout SCHOOL_ADMIN/DIRECTOR/TEACHER/PLATFORM_OWNER. Le
partenaire est TOUJOURS dérivé de l'utilisateur authentifié (jamais d'un paramètre de chemin, de
requête ou de corps) — voir partners/service.py::get_own_partner.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.permissions import DbSession, require_permission
from app.modules.auth.schemas import UserOut
from app.modules.organizations.schemas import OrganizationOut
from app.modules.partners import service
from app.modules.partners.models import ACQUISITION_SOURCE_PARTNER
from app.modules.partners.schemas import (
    PartnerAccountOut,
    PartnerDashboardOut,
    PartnerSchoolEnrollCreate,
    PartnerSchoolEnrolled,
    PartnerSchoolOut,
)
from app.modules.schools.schemas import SchoolOut
from app.modules.users.models import User

router = APIRouter()

DashboardReader = Annotated[User, Depends(require_permission("partner.dashboard.read"))]
SchoolsReader = Annotated[User, Depends(require_permission("partner.schools.read"))]
SchoolsEnroller = Annotated[User, Depends(require_permission("partner.schools.enroll"))]
AccountsReader = Annotated[User, Depends(require_permission("partner.accounts.read"))]


@router.get("/partner/dashboard", response_model=PartnerDashboardOut)
async def get_partner_dashboard(db: DbSession, current_user: DashboardReader) -> PartnerDashboardOut:
    partner = await service.get_own_partner(db, current_user.id)
    return PartnerDashboardOut(**await service.get_partner_dashboard(db, partner))


@router.get("/partner/schools", response_model=list[PartnerSchoolOut])
async def list_partner_schools(db: DbSession, current_user: SchoolsReader) -> list[PartnerSchoolOut]:
    partner = await service.get_own_partner(db, current_user.id)
    rows = await service.list_partner_schools(db, partner)
    return [
        PartnerSchoolOut(
            school_id=school.id,
            school_name=school.name,
            organization_id=organization.id,
            organization_name=organization.name,
            enrolled_at=enrollment.enrolled_at,
            status=enrollment.status,
        )
        for enrollment, school, organization in rows
    ]


@router.post("/partner/schools", response_model=PartnerSchoolEnrolled, status_code=status.HTTP_201_CREATED)
async def enroll_partner_school(
    payload: PartnerSchoolEnrollCreate, db: DbSession, current_user: SchoolsEnroller
) -> PartnerSchoolEnrolled:
    partner = await service.get_own_partner(db, current_user.id)
    organization, school, admin = await service.enroll_school(db, partner, payload, current_user.id)
    return PartnerSchoolEnrolled(
        organization=OrganizationOut.model_validate(organization),
        school=SchoolOut.model_validate(school),
        admin=UserOut.model_validate(admin),
        acquisition_source=ACQUISITION_SOURCE_PARTNER,
        commission_eligible=True,
    )


@router.get("/partner/accounts", response_model=list[PartnerAccountOut])
async def list_partner_accounts(db: DbSession, current_user: AccountsReader) -> list[PartnerAccountOut]:
    partner = await service.get_own_partner(db, current_user.id)
    rows = await service.list_partner_accounts(db, partner)
    return [
        PartnerAccountOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            created_at=user.created_at,
            role_codes=role_codes,
        )
        for user, role_codes in rows
    ]
