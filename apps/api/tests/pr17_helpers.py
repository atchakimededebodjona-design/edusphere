"""Helpers partagés par les tests PR #17 (Platform Owner & Partner isolation).

Module non collecté par pytest (pas de préfixe `test_`). Même motif que tests/conftest.py :
un compte PLATFORM_OWNER n'a, par conception, aucun flux produit de création (attribution hors
bande) — il est donc créé directement en base, exactement comme `create_platform_admin`.
"""

import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import hash_password
from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.partners.models import Partner, PartnerSchoolEnrollment
from app.modules.users.models import User
from tests.conftest import _clear_shared_ip_rate_limits, assign_role, register_school, unique_email, unique_slug

PASSWORD = "SuperSecret123"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def login(client: AsyncClient, email: str, password: str = PASSWORD) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return auth(response.json()["access_token"])


async def create_platform_owner(client: AsyncClient, prefix: str = "owner") -> dict:
    """Compte PLATFORM_OWNER pur : `is_platform_admin=True` (réutilise /platform/dashboard et
    POST /platform/organizations, voir décision #3) + UserRole PLATFORM_OWNER globale."""
    user_id = uuid.uuid4()
    email = unique_email(prefix)
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        db.add(
            User(
                id=user_id,
                email=email,
                full_name=f"Platform Owner {prefix}",
                hashed_password=hash_password(PASSWORD),
                is_active=True,
                is_platform_admin=True,
            )
        )
        await db.commit()
    await assign_role(str(user_id), "PLATFORM_OWNER", organization_id=None, school_id=None)
    await _clear_shared_ip_rate_limits()
    return {"user_id": str(user_id), "email": email, "headers": await login(client, email)}


async def create_partner(client: AsyncClient, owner_headers: dict[str, str], prefix: str = "partner") -> dict:
    """Crée un partenaire via POST /platform/partners, active son compte via le lien de
    réinitialisation (dev_reset_token), puis le connecte."""
    email = unique_email(prefix)
    response = await client.post(
        "/api/v1/platform/partners",
        json={"display_name": f"Partenaire {prefix}", "full_name": f"Contact {prefix}", "email": email},
        headers=owner_headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    reset = await client.post(
        "/api/v1/auth/reset-password", json={"token": body["dev_reset_token"], "new_password": PASSWORD}
    )
    assert reset.status_code == 204, reset.text
    return {
        "partner": body["partner"],
        "user_id": body["partner"]["user_id"],
        "email": email,
        "headers": await login(client, email),
    }


def enrollment_payload(prefix: str, admin_email: str | None = None) -> dict:
    return {
        "organization": {"name": f"{prefix} Group", "slug": unique_slug(prefix), "country_code": "TG"},
        "school": {"name": f"{prefix} School", "slug": "principale"},
        "admin": {
            "full_name": f"Admin {prefix}",
            "email": admin_email or unique_email(f"admin.{prefix}"),
            "password": PASSWORD,
        },
    }


async def enroll_school_as_partner(client: AsyncClient, partner_headers: dict[str, str], prefix: str) -> dict:
    payload = enrollment_payload(prefix)
    response = await client.post("/api/v1/partner/schools", json=payload, headers=partner_headers)
    assert response.status_code == 201, response.text
    body = response.json()
    body["admin_headers"] = await login(client, payload["admin"]["email"])
    return body


async def enrollment_for_school(school_id: str) -> PartnerSchoolEnrollment | None:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        result = await db.execute(
            select(PartnerSchoolEnrollment).where(PartnerSchoolEnrollment.school_id == uuid.UUID(school_id))
        )
        return result.scalar_one_or_none()


async def partner_row_for_user(user_id: str) -> Partner | None:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        result = await db.execute(select(Partner).where(Partner.user_id == uuid.UUID(user_id)))
        return result.scalar_one_or_none()


async def school_with_student(client: AsyncClient, prefix: str) -> dict:
    """École (inscrite par la plateforme via conftest.register_school) avec un élève réel, pour
    viser des endpoints de données scolaires qui exigent un identifiant existant."""
    data = await register_school(client, prefix)
    admin_headers = auth(data["tokens"]["access_token"])
    student = await client.post(
        "/api/v1/students",
        json={
            "school_id": data["school"]["id"],
            "matricule": f"S{uuid.uuid4().hex[:8]}",
            "first_name": "Eleve",
            "last_name": "Test",
            "date_of_birth": str(date(2015, 1, 1)),
            "sex": "M",
        },
        headers=admin_headers,
    )
    assert student.status_code == 201, student.text
    data["student"] = student.json()
    data["admin_headers"] = admin_headers
    return data


def school_data_endpoints(school_id: str, student_id: str) -> list[str]:
    """Un endpoint représentatif (lecture) par domaine de données scolaires."""
    return [
        f"/api/v1/students?school_id={school_id}",  # students
        f"/api/v1/students/{student_id}",  # students (ressource ciblée)
        f"/api/v1/assessment-types?school_id={school_id}",  # grades
        f"/api/v1/students/{student_id}/averages",  # grades (ressource ciblée)
        f"/api/v1/students/{student_id}/attendance-summary?academic_term_id={uuid.uuid4()}",  # attendance
        f"/api/v1/report-card-templates?school_id={school_id}",  # report_cards
        f"/api/v1/fee-categories?school_id={school_id}",  # fees
        f"/api/v1/fees/summary?school_id={school_id}",  # fees
        f"/api/v1/students/{student_id}/financial-summary",  # fees (ressource ciblée)
        f"/api/v1/payments?school_id={school_id}",  # payments
    ]


PLATFORM_GET_ENDPOINTS = [
    "/api/v1/platform/dashboard",
    "/api/v1/platform/organizations",
    "/api/v1/platform/schools",
    "/api/v1/platform/accounts",
    "/api/v1/platform/partners",
]

PARTNER_GET_ENDPOINTS = [
    "/api/v1/partner/dashboard",
    "/api/v1/partner/schools",
    "/api/v1/partner/accounts",
]

SCHOOL_DOMAIN_PREFIXES = (
    "students.",
    "grades.",
    "attendance.",
    "report_cards.",
    "fees.",
    "payments.",
    "academics.",
    "organizations.",
    "schools.",
    "users.",
    "roles.",
    "announcements.",
    "audit.",
)
