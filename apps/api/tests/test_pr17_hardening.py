"""PR #17 — audit de durcissement final.

Couvre ce que les fichiers test_platform_owner/test_partners/test_partner_isolation ne couvraient
pas encore :
- balayage EXHAUSTIF de toutes les routes du domaine scolaire (GET/POST/PATCH/DELETE) avec des
  identifiants RÉELS, pour PLATFORM_OWNER et PARTNER_ADMIN : jamais de 2xx, jamais de fuite ;
- écritures ciblées avec un payload VALIDE (la refusée doit venir de l'autorisation, pas de la
  validation) ;
- paramètres falsifiés (partner_id/organization_id/school_id/user_id) et champs imbriqués ;
- impossibilité de rattacher un compte PLATFORM_OWNER/PARTNER_ADMIN existant à une école ;
- atomicité des inscriptions (plateforme ET partenaire), conflit propre entre partenaires ;
- RLS : écriture refusée au partenaire, policies exactes ;
- outil opérateur de promotion PLATFORM_OWNER (compte SUPER_ADMIN hérité) ;
- `is_platform_admin` ne rend jamais un partenaire platform-wide ;
- absence de tout moteur de commission (PR #18).
"""

import uuid
from datetime import date

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.tenancy import apply_tenant_context, set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.main import app
from app.modules.organizations.models import Organization
from app.modules.partners.models import PartnerSchoolEnrollment
from app.modules.platform.owner import PromotionRefused, promote_to_platform_owner
from app.modules.rbac.models import Role, UserRole
from app.modules.users.models import User
from tests.conftest import assign_role, create_platform_admin, register_school, unique_email
from tests.pr17_helpers import (
    auth,
    create_partner,
    create_platform_owner,
    enroll_school_as_partner,
    enrollment_payload,
    login,
)

# Préfixes des routes du domaine scolaire (tout sauf auth/santé/plateforme/partenaire/catalogue RBAC
# et portails auto-scopés traités à part).
SCHOOL_DOMAIN_ROUTE_PREFIXES = (
    "/api/v1/organizations",
    "/api/v1/schools",
    "/api/v1/academic-years",
    "/api/v1/academic-terms",
    "/api/v1/education-levels",
    "/api/v1/subjects",
    "/api/v1/rooms",
    "/api/v1/classes",
    "/api/v1/students",
    "/api/v1/student-exits",
    "/api/v1/guardians",
    "/api/v1/enrollments",
    "/api/v1/assessment-types",
    "/api/v1/assessments",
    "/api/v1/results",
    "/api/v1/student-subject-averages",
    "/api/v1/report-card-templates",
    "/api/v1/report-cards",
    "/api/v1/users",
    "/api/v1/attendance-sessions",
    "/api/v1/attendance-records",
    "/api/v1/fee-categories",
    "/api/v1/fee-schedules",
    "/api/v1/student-fees",
    "/api/v1/payments",
    "/api/v1/fees",
    "/api/v1/announcements",
    "/api/v1/audit-logs",
)
# Portails auto-scopés (lecture de SES propres données) : un 200 vide y est légitime, mais aucune
# donnée de l'école ne doit jamais y apparaître.
SELF_SCOPED_ROUTE_PREFIXES = ("/api/v1/teacher", "/api/v1/parent", "/api/v1/notifications")
# Route publique de vérification de bulletin (code opaque) : hors périmètre d'autorisation.
PUBLIC_ROUTES = {"/api/v1/report-cards/verify/{code}"}


async def _rich_school(client: AsyncClient, prefix: str) -> dict:
    """École complète : année, période, niveau, classe, matière, élève inscrit, tuteur lié,
    type d'évaluation, catégorie de frais. Retourne les identifiants réels de chaque ressource."""
    data = await register_school(client, prefix)
    headers = auth(data["tokens"]["access_token"])
    school_id = data["school"]["id"]
    suffix = uuid.uuid4().hex[:8]

    async def post(path: str, payload: dict) -> dict:
        response = await client.post(f"/api/v1{path}", json=payload, headers=headers)
        assert response.status_code in (200, 201), (path, response.text)
        return response.json()

    year = await post(
        "/academic-years",
        {"school_id": school_id, "name": f"2026-{suffix}", "start_date": "2026-09-01", "end_date": "2027-06-30"},
    )
    term = await post(
        "/academic-terms",
        {"academic_year_id": year["id"], "name": "T1", "start_date": "2026-09-01", "end_date": "2026-12-20"},
    )
    level = await post("/education-levels", {"school_id": school_id, "name": f"CE1-{suffix}"})
    school_class = await post(
        "/classes", {"academic_year_id": year["id"], "education_level_id": level["id"], "name": "A"}
    )
    subject = await post("/subjects", {"school_id": school_id, "name": f"Maths-{suffix}"})
    class_subject = await post(f"/classes/{school_class['id']}/subjects", {"subject_id": subject["id"], "coefficient": 1})
    marker = f"Secret{suffix}"
    student = await post(
        "/students",
        {
            "school_id": school_id,
            "matricule": f"M{suffix}",
            "first_name": marker,
            "last_name": marker,
            "date_of_birth": "2015-01-01",
            "sex": "F",
        },
    )
    enrollment = await post(
        f"/students/{student['id']}/enrollments", {"class_id": school_class["id"], "enrollment_date": "2026-09-01"}
    )
    guardian = await post(
        "/guardians", {"school_id": school_id, "full_name": f"Tuteur {marker}", "relationship_type": "mother"}
    )
    link = await post(f"/students/{student['id']}/guardians", {"guardian_id": guardian["id"]})
    assessment_type = await post("/assessment-types", {"school_id": school_id, "name": f"Devoir-{suffix}"})
    fee_category = await post("/fee-categories", {"school_id": school_id, "name": f"Scolarité-{suffix}"})

    return {
        "data": data,
        "headers": headers,
        "marker": marker,
        "matricule": student["matricule"],
        "ids": {
            "organization_id": data["organization"]["id"],
            "school_id": school_id,
            "year_id": year["id"],
            "academic_year_id": year["id"],
            "term_id": term["id"],
            "academic_term_id": term["id"],
            "level_id": level["id"],
            "education_level_id": level["id"],
            "class_id": school_class["id"],
            "subject_id": subject["id"],
            "class_subject_id": class_subject["id"],
            "student_id": student["id"],
            "enrollment_id": enrollment["id"],
            "guardian_id": guardian["id"],
            "link_id": link["id"],
            "assessment_type_id": assessment_type["id"],
            "fee_category_id": fee_category["id"],
            "user_id": data["user"]["id"],
        },
    }


def _school_domain_routes() -> list[tuple[str, str]]:
    routes = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or route.path in PUBLIC_ROUTES:
            continue
        if route.path.startswith(SCHOOL_DOMAIN_ROUTE_PREFIXES + SELF_SCOPED_ROUTE_PREFIXES):
            for method in sorted(route.methods):
                routes.append((method, route.path))
    return routes


def _fill(path: str, ids: dict[str, str]) -> str:
    import re

    return re.sub(r"\{(\w+)\}", lambda m: ids.get(m.group(1), str(uuid.uuid4())), path)


async def _sweep(client: AsyncClient, headers: dict[str, str], env: dict) -> dict[tuple[str, str], int]:
    ids = env["ids"]
    query = "?" + "&".join(f"{k}={v}" for k, v in ids.items()) + "&session_date=2026-10-01&date=2026-10-01"
    body = {**ids, "name": "Intrus", "title": "Intrus", "body": "Intrus", "target_type": "SCHOOL"}
    statuses: dict[tuple[str, str], int] = {}
    for method, path in _school_domain_routes():
        url = _fill(path, ids) + query
        if method == "GET":
            response = await client.get(url, headers=headers)
        elif method == "DELETE":
            response = await client.delete(url, headers=headers)
        else:
            response = await client.request(method, url, json=body, headers=headers)
        statuses[(method, path)] = response.status_code
        leaked = env["marker"] in response.text or env["matricule"] in response.text
        assert not leaked, (method, path, response.status_code, response.text[:300])
        if not path.startswith(SELF_SCOPED_ROUTE_PREFIXES):
            assert not 200 <= response.status_code < 300, (method, path, response.status_code, response.text[:300])
    return statuses


# === Balayage exhaustif — PLATFORM_OWNER ==================================================
async def test_platform_owner_school_domain_sweep_never_succeeds(client: AsyncClient) -> None:
    env = await _rich_school(client, "hdsweepowner")
    owner = await create_platform_owner(client, "hdsweepowner")
    statuses = await _sweep(client, owner["headers"], env)
    assert len(statuses) > 80  # tout le domaine scolaire a bien été balayé
    # Lectures ciblant des ressources réelles : PLATFORM_OWNER VOIT les lignes (RLS platform-wide)
    # mais le RBAC refuse — 403 explicite, jamais 2xx.
    for key in [
        ("GET", "/api/v1/students"),
        ("GET", "/api/v1/students/{student_id}"),
        ("GET", "/api/v1/students/{student_id}/guardians"),
        ("GET", "/api/v1/students/{student_id}/enrollments"),
        ("GET", "/api/v1/students/{student_id}/documents"),
        ("GET", "/api/v1/guardians"),
        ("GET", "/api/v1/assessment-types"),
        ("GET", "/api/v1/assessments"),
        ("GET", "/api/v1/attendance-sessions"),
        ("GET", "/api/v1/report-cards"),
        ("GET", "/api/v1/fee-categories"),
        ("GET", "/api/v1/payments"),
        ("GET", "/api/v1/users"),
        ("GET", "/api/v1/audit-logs"),
    ]:
        assert statuses[key] == 403, (key, statuses[key])


# === Balayage exhaustif — PARTNER_ADMIN (y compris sur SA propre école inscrite) =============
async def test_partner_school_domain_sweep_never_succeeds_even_on_own_school(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "hdsweeppartner")
    partner = await create_partner(client, owner["headers"], "hdsweeppartner")
    env = await _rich_school(client, "hdsweepother")
    statuses = await _sweep(client, partner["headers"], env)
    assert len(statuses) > 80

    # École inscrite par CE partenaire : même résultat, aucun privilège scolaire.
    own = await enroll_school_as_partner(client, partner["headers"], "hdsweepown")
    student = await client.post(
        "/api/v1/students",
        json={
            "school_id": own["school"]["id"],
            "matricule": f"P{uuid.uuid4().hex[:8]}",
            "first_name": "Propre",
            "last_name": "Ecole",
            "date_of_birth": "2015-01-01",
            "sex": "M",
        },
        headers=own["admin_headers"],
    )
    assert student.status_code == 201
    for path in (
        f"/api/v1/students?school_id={own['school']['id']}",
        f"/api/v1/students/{student.json()['id']}",
        f"/api/v1/payments?school_id={own['school']['id']}",
        f"/api/v1/users?school_id={own['school']['id']}",
    ):
        response = await client.get(path, headers=partner["headers"])
        assert response.status_code in (403, 404), (path, response.status_code)
        assert student.json()["id"] not in response.text


# === Écritures avec payload VALIDE : refus par autorisation ===================================
async def _valid_writes(env: dict) -> list[tuple[str, str, dict | None]]:
    ids = env["ids"]
    return [
        ("POST", "/api/v1/students", {
            "school_id": ids["school_id"], "matricule": f"X{uuid.uuid4().hex[:8]}", "first_name": "A",
            "last_name": "B", "date_of_birth": "2015-01-01", "sex": "M",
        }),
        ("PATCH", f"/api/v1/students/{ids['student_id']}", {"first_name": "Pirate"}),
        ("POST", "/api/v1/academic-years", {
            "school_id": ids["school_id"], "name": f"Y{uuid.uuid4().hex[:6]}",
            "start_date": "2027-09-01", "end_date": "2028-06-30",
        }),
        ("POST", "/api/v1/assessment-types", {"school_id": ids["school_id"], "name": "Pirate"}),
        ("POST", "/api/v1/attendance-sessions", {
            "class_id": ids["class_id"], "academic_term_id": ids["academic_term_id"], "session_date": str(date(2026, 10, 1)),
        }),
        ("POST", "/api/v1/report-card-templates", {"school_id": ids["school_id"], "name": "Pirate", "html_content": "<p/>"}),
        ("POST", "/api/v1/fee-categories", {"school_id": ids["school_id"], "name": "Pirate"}),
        ("POST", "/api/v1/guardians", {"school_id": ids["school_id"], "full_name": "Pirate", "relationship_type": "other"}),
        ("POST", "/api/v1/announcements", {"school_id": ids["school_id"], "title": "x", "body": "x", "target_type": "SCHOOL"}),
        ("PATCH", f"/api/v1/schools/{ids['school_id']}", {"name": "Pirate"}),
        ("PATCH", f"/api/v1/organizations/{ids['organization_id']}", {"name": "Pirate"}),
        ("DELETE", f"/api/v1/students/{ids['student_id']}/guardians/{ids['link_id']}", None),
        ("DELETE", f"/api/v1/classes/{ids['class_id']}/subjects/{ids['class_subject_id']}", None),
    ]


async def test_platform_owner_valid_writes_are_refused_403_and_nothing_changes(client: AsyncClient) -> None:
    env = await _rich_school(client, "hdwriteowner")
    owner = await create_platform_owner(client, "hdwriteowner")
    for method, path, payload in await _valid_writes(env):
        response = await client.request(method, path, json=payload, headers=owner["headers"])
        assert response.status_code == 403, (method, path, response.status_code, response.text)
    # Rien n'a été modifié : l'admin de l'école relit l'élève et son lien tuteur intacts.
    student = await client.get(f"/api/v1/students/{env['ids']['student_id']}", headers=env["headers"])
    assert student.json()["first_name"] == env["marker"]
    links = await client.get(f"/api/v1/students/{env['ids']['student_id']}/guardians", headers=env["headers"])
    assert len(links.json()) == 1


async def test_partner_valid_writes_are_refused_and_nothing_changes(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "hdwritepartner")
    partner = await create_partner(client, owner["headers"], "hdwritepartner")
    env = await _rich_school(client, "hdwritepartnerschool")
    for method, path, payload in await _valid_writes(env):
        response = await client.request(method, path, json=payload, headers=partner["headers"])
        # 404 : RLS masque déjà la ressource à un partenaire (tenant_org_ids vide) ; 403 : RBAC.
        assert response.status_code in (403, 404), (method, path, response.status_code, response.text)
    student = await client.get(f"/api/v1/students/{env['ids']['student_id']}", headers=env["headers"])
    assert student.json()["first_name"] == env["marker"]


# === Paramètres falsifiés ======================================================================
async def test_partner_endpoints_ignore_every_forged_scope_parameter(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "hdforge")
    partner_a = await create_partner(client, owner["headers"], "hdforgea")
    partner_b = await create_partner(client, owner["headers"], "hdforgeb")
    school_a = await enroll_school_as_partner(client, partner_a["headers"], "hdforgeschoola")
    school_b = await enroll_school_as_partner(client, partner_b["headers"], "hdforgeschoolb")
    forged = (
        f"?partner_id={partner_b['partner']['id']}&organization_id={school_b['organization']['id']}"
        f"&school_id={school_b['school']['id']}&user_id={partner_b['user_id']}"
    )
    dash = await client.get(f"/api/v1/partner/dashboard{forged}", headers=partner_a["headers"])
    assert dash.json() == {"school_count": 1, "organization_count": 1}
    schools = await client.get(f"/api/v1/partner/schools{forged}", headers=partner_a["headers"])
    assert [s["school_id"] for s in schools.json()] == [school_a["school"]["id"]]
    accounts = await client.get(f"/api/v1/partner/accounts{forged}", headers=partner_a["headers"])
    assert {a["id"] for a in accounts.json()} == {school_a["admin"]["id"]}


@pytest.mark.parametrize("field", ["partner_id", "organization_id", "school_id", "user_id", "enrolled_by_user_id"])
async def test_partner_enrollment_rejects_forged_top_level_ids(client: AsyncClient, field: str) -> None:
    owner = await create_platform_owner(client, f"hdtop{field[:5]}")
    partner = await create_partner(client, owner["headers"], f"hdtop{field[:5]}")
    payload = enrollment_payload("hdtop")
    payload[field] = str(uuid.uuid4())
    response = await client.post("/api/v1/partner/schools", json=payload, headers=partner["headers"])
    assert response.status_code == 422
    assert (await client.get("/api/v1/partner/schools", headers=partner["headers"])).json() == []


async def test_partner_enrollment_ignores_forged_nested_ids(client: AsyncClient) -> None:
    """Les sous-objets (organization/school/admin) ignorent tout id fourni : l'école créée
    appartient toujours à la NOUVELLE organisation, jamais à une organisation existante visée."""
    owner = await create_platform_owner(client, "hdnested")
    partner = await create_partner(client, owner["headers"], "hdnested")
    victim = await register_school(client, "hdnestedvictim")
    payload = enrollment_payload("hdnested")
    payload["organization"]["id"] = victim["organization"]["id"]
    payload["school"]["id"] = victim["school"]["id"]
    payload["school"]["organization_id"] = victim["organization"]["id"]
    payload["admin"]["id"] = victim["user"]["id"]
    response = await client.post("/api/v1/partner/schools", json=payload, headers=partner["headers"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["organization"]["id"] != victim["organization"]["id"]
    assert body["school"]["id"] != victim["school"]["id"]
    assert body["school"]["organization_id"] == body["organization"]["id"]
    assert body["admin"]["id"] != victim["user"]["id"]
    victim_enrollment = await _enrollment(victim["school"]["id"])
    assert victim_enrollment is not None and victim_enrollment.partner_id is None


async def _enrollment(school_id: str) -> PartnerSchoolEnrollment | None:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        return (
            await db.execute(
                select(PartnerSchoolEnrollment).where(PartnerSchoolEnrollment.school_id == uuid.UUID(school_id))
            )
        ).scalar_one_or_none()


# === Comptes globaux isolés jamais rattachables à une école ======================================
@pytest.mark.parametrize("kind", ["owner", "partner"])
@pytest.mark.parametrize("role_code", ["TEACHER", "SCHOOL_ADMIN", "PARENT"])
async def test_existing_owner_or_partner_cannot_be_attached_to_a_school(
    client: AsyncClient, kind: str, role_code: str
) -> None:
    owner = await create_platform_owner(client, f"hdattach{kind}")
    target = owner if kind == "owner" else await create_partner(client, owner["headers"], "hdattachp")
    school = await register_school(client, f"hdattach{kind}{role_code.lower().replace('_', '')}")
    response = await client.post(
        "/api/v1/users",
        json={"email": target["email"], "full_name": "Intrus", "school_id": school["school"]["id"], "role_code": role_code},
        headers=auth(school["tokens"]["access_token"]),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "This account cannot be attached to a school"
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        rows = (
            await db.execute(select(UserRole).where(UserRole.user_id == uuid.UUID(target["user_id"])))
        ).scalars().all()
    assert all(r.organization_id is None and r.school_id is None for r in rows)
    # Toujours non platform-wide / toujours sans tenant pour le partenaire.
    if kind == "partner":
        async with AsyncSessionLocal() as db:
            await apply_tenant_context(db, uuid.UUID(target["user_id"]))
            row = (
                await db.execute(
                    text("SELECT current_setting('app.is_platform_wide', true), current_setting('app.tenant_org_ids', true)")
                )
            ).one()
            await db.rollback()
        assert tuple(row) == ("false", "")


async def test_attach_of_ordinary_existing_user_still_works(client: AsyncClient) -> None:
    """Non-régression : le rattachement d'un compte scolaire existant à une 2e école reste permis."""
    school_a = await register_school(client, "hdattachoka")
    school_b = await register_school(client, "hdattachokb")
    email = unique_email("hdattachok")
    first = await client.post(
        "/api/v1/users",
        json={"email": email, "full_name": "Ens", "school_id": school_a["school"]["id"], "role_code": "TEACHER"},
        headers=auth(school_a["tokens"]["access_token"]),
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/users",
        json={"email": email, "full_name": "Ens", "school_id": school_b["school"]["id"], "role_code": "TEACHER"},
        headers=auth(school_b["tokens"]["access_token"]),
    )
    assert second.status_code == 201, second.text


async def test_school_user_list_contains_school_accounts_but_never_global_accounts(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "hdusers")
    partner = await create_partner(client, owner["headers"], "hdusers")
    school = await enroll_school_as_partner(client, partner["headers"], "hdusersschool")
    teacher = await client.post(
        "/api/v1/users",
        json={"email": unique_email("hdusers"), "full_name": "Ens", "school_id": school["school"]["id"], "role_code": "TEACHER"},
        headers=school["admin_headers"],
    )
    listed = await client.get(f"/api/v1/users?school_id={school['school']['id']}", headers=school["admin_headers"])
    ids = {entry["user"]["id"] for entry in listed.json()}
    assert school["admin"]["id"] in ids
    assert teacher.json()["user"]["id"] in ids
    assert owner["user_id"] not in ids and partner["user_id"] not in ids


# === Inscriptions : atomicité et conflits ========================================================
async def test_partner_enrollment_failure_rolls_back_everything(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await create_platform_owner(client, "hdrollback")
    partner = await create_partner(client, owner["headers"], "hdrollback")
    payload = enrollment_payload("hdrollback")

    def _boom(_password: str) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr("app.modules.platform.service.hash_password", _boom)
    with pytest.raises(RuntimeError):
        await client.post("/api/v1/partner/schools", json=payload, headers=partner["headers"])
    monkeypatch.undo()

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        org = (
            await db.execute(select(Organization).where(Organization.slug == payload["organization"]["slug"]))
        ).scalar_one_or_none()
        admin = (await db.execute(select(User).where(User.email == payload["admin"]["email"]))).scalar_one_or_none()
    assert org is None and admin is None
    assert (await client.get("/api/v1/partner/schools", headers=partner["headers"])).json() == []


async def test_second_partner_reusing_slug_gets_clean_409_without_partial_rows(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "hdslug")
    partner_a = await create_partner(client, owner["headers"], "hdsluga")
    partner_b = await create_partner(client, owner["headers"], "hdslugb")
    payload = enrollment_payload("hdslug")
    first = await client.post("/api/v1/partner/schools", json=payload, headers=partner_a["headers"])
    assert first.status_code == 201
    payload_b = enrollment_payload("hdslug")
    payload_b["organization"]["slug"] = payload["organization"]["slug"]
    second = await client.post("/api/v1/partner/schools", json=payload_b, headers=partner_b["headers"])
    assert second.status_code == 409
    assert (await client.get("/api/v1/partner/schools", headers=partner_b["headers"])).json() == []
    async with AsyncSessionLocal() as db:
        assert (
            await db.execute(select(User).where(User.email == payload_b["admin"]["email"]))
        ).scalar_one_or_none() is None
    enrollment = await _enrollment(first.json()["school"]["id"])
    assert enrollment is not None and str(enrollment.partner_id) == partner_a["partner"]["id"]


async def test_platform_and_partner_enrollments_create_full_tenant_atomically(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "hdatomic")
    partner = await create_partner(client, owner["headers"], "hdatomic")
    platform_created = await client.post(
        "/api/v1/platform/organizations", json=enrollment_payload("hdatomicp"), headers=owner["headers"]
    )
    partner_created = await client.post(
        "/api/v1/partner/schools", json=enrollment_payload("hdatomicq"), headers=partner["headers"]
    )
    for created, source, partner_id, eligible in (
        (platform_created.json(), "PLATFORM_OWNER", None, False),
        (partner_created.json(), "PARTNER", partner["partner"]["id"], True),
    ):
        async with AsyncSessionLocal() as db:
            await set_platform_wide_context(db)
            roles = (
                await db.execute(
                    select(UserRole, Role.code)
                    .join(Role, Role.id == UserRole.role_id)
                    .where(UserRole.user_id == uuid.UUID(created["admin"]["id"]))
                )
            ).all()
        assert [(code, str(ur.organization_id), ur.school_id) for ur, code in roles] == [
            ("SCHOOL_ADMIN", created["organization"]["id"], None)
        ]
        enrollment = await _enrollment(created["school"]["id"])
        assert enrollment is not None
        assert enrollment.acquisition_source == source
        assert (str(enrollment.partner_id) if enrollment.partner_id else None) == partner_id
        assert enrollment.commission_eligible is eligible
        assert enrollment.status == "ACTIVE" and enrollment.enrolled_at is not None


# === RLS : écritures directes refusées au partenaire ============================================
async def test_partner_session_cannot_write_partner_tables_directly(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "hdrlsw")
    partner = await create_partner(client, owner["headers"], "hdrlsw")
    school = await register_school(client, "hdrlswschool")
    from sqlalchemy.exc import DBAPIError

    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(partner["user_id"]))
        with pytest.raises(DBAPIError):
            await db.execute(
                text(
                    "INSERT INTO partner_school_enrollments (id, partner_id, organization_id, school_id, "
                    "acquisition_source, commission_eligible) VALUES (:id, :p, :o, :s, 'PARTNER', true)"
                ),
                {
                    "id": uuid.uuid4(),
                    "p": uuid.UUID(partner["partner"]["id"]),
                    "o": uuid.UUID(school["organization"]["id"]),
                    "s": uuid.uuid4(),
                },
            )
        await db.rollback()
    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(partner["user_id"]))
        updated = await db.execute(
            text("UPDATE partners SET status = 'ACTIVE' WHERE user_id = :u"), {"u": uuid.UUID(partner["user_id"])}
        )
        assert updated.rowcount == 0  # sa propre ligne lui est invisible hors élévation explicite
        await db.rollback()


async def test_new_rls_policies_are_exact() -> None:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT tablename, policyname, cmd, permissive, qual, with_check FROM pg_policies "
                    "WHERE tablename IN ('partners', 'partner_school_enrollments')"
                )
            )
        ).all()
    by_name = {row.policyname: row for row in rows}
    assert set(by_name) == {"partners_platform_only", "partner_school_enrollments_tenant_isolation"}
    partners_policy = by_name["partners_platform_only"]
    assert partners_policy.cmd == "ALL" and partners_policy.permissive == "PERMISSIVE"
    assert partners_policy.with_check is None  # USING sert aussi de WITH CHECK (commande ALL)
    assert "app.is_platform_wide" in partners_policy.qual and "tenant_org_ids" not in partners_policy.qual
    enrollments_policy = by_name["partner_school_enrollments_tenant_isolation"]
    assert enrollments_policy.cmd == "ALL"
    assert "organization_id" in enrollments_policy.qual and "tenant_org_ids" in enrollments_policy.qual
    assert "partner" not in enrollments_policy.qual  # aucun bypass spécifique partenaire


# === is_platform_admin ne rend jamais un partenaire platform-wide ================================
async def test_platform_admin_flag_alone_never_makes_partner_platform_wide(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "hdflag")
    partner = await create_partner(client, owner["headers"], "hdflag")
    async with AsyncSessionLocal() as db:
        user = await db.get(User, uuid.UUID(partner["user_id"]))
        assert user is not None
        user.is_platform_admin = True  # état anormal forcé en base
        await db.commit()
    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(partner["user_id"]))
        row = (
            await db.execute(
                text("SELECT current_setting('app.is_platform_wide', true), current_setting('app.tenant_org_ids', true)")
            )
        ).one()
        assert tuple(row) == ("false", "")
        assert (await db.execute(text("SELECT count(*) FROM schools"))).scalar_one() == 0
        await db.rollback()
    headers = await login(client, partner["email"])
    env = await register_school(client, "hdflagschool")
    response = await client.get(f"/api/v1/students?school_id={env['school']['id']}", headers=headers)
    assert response.status_code in (403, 404)


# === Outil opérateur : promotion d'un compte SUPER_ADMIN hérité en PLATFORM_OWNER ==================
async def test_legacy_super_admin_has_school_access_until_promoted(client: AsyncClient) -> None:
    """Démontre le risque (SUPER_ADMIN hérité = accès scolaire complet) puis sa correction."""
    env = await register_school(client, "hdpromote")
    legacy = await create_platform_admin(client, "hdpromote")
    legacy_headers = auth(legacy["tokens"]["access_token"])
    before = await client.get(f"/api/v1/students?school_id={env['school']['id']}", headers=legacy_headers)
    assert before.status_code == 200  # comportement hérité : SUPER_ADMIN lit les élèves

    async with AsyncSessionLocal() as db:
        simulated = await promote_to_platform_owner(db, legacy["email"], apply=False)
    assert simulated.applied is False and simulated.roles_after == ["PLATFORM_OWNER"]
    assert (await client.get(f"/api/v1/students?school_id={env['school']['id']}", headers=legacy_headers)).status_code == 200

    async with AsyncSessionLocal() as db:
        report = await promote_to_platform_owner(db, legacy["email"], apply=True)
    assert report.applied is True
    assert report.roles_before == ["SUPER_ADMIN"] and report.roles_after == ["PLATFORM_OWNER"]
    assert report.removed_role_codes == ["SUPER_ADMIN"] and report.added_platform_owner is True

    after = await client.get(f"/api/v1/students?school_id={env['school']['id']}", headers=legacy_headers)
    assert after.status_code == 403  # effet immédiat : permissions recalculées à chaque requête
    assert (await client.get("/api/v1/platform/dashboard", headers=legacy_headers)).status_code == 200
    assert (await client.get("/api/v1/platform/schools", headers=legacy_headers)).status_code == 200

    async with AsyncSessionLocal() as db:
        again = await promote_to_platform_owner(db, legacy["email"], apply=True)
    assert again.removed_role_codes == [] and again.added_platform_owner is False  # idempotent


async def test_promotion_refuses_school_attached_partner_unknown_and_inactive_accounts(client: AsyncClient) -> None:
    school = await register_school(client, "hdpromoterefuse")
    owner = await create_platform_owner(client, "hdpromoterefuse")
    partner = await create_partner(client, owner["headers"], "hdpromoterefuse")
    legacy = await create_platform_admin(client, "hdpromoterefuseattached")
    await assign_role(legacy["user_id"], "TEACHER", school["organization"]["id"], school["school"]["id"])

    for email, expected in (
        (school["user"]["email"], "rattaché"),
        (legacy["email"], "rattaché"),
        (partner["email"], "partenaire"),
        (unique_email("hdnobody"), "Aucun compte"),
    ):
        async with AsyncSessionLocal() as db:
            with pytest.raises(PromotionRefused, match=expected):
                await promote_to_platform_owner(db, email, apply=True)

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        codes = {
            row[0]
            for row in (
                await db.execute(
                    select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == uuid.UUID(legacy["user_id"]))
                )
            ).all()
        }
    assert codes == {"SUPER_ADMIN", "TEACHER"}  # refus = aucune modification


async def test_promotion_job_cli_defaults_to_dry_run(client: AsyncClient) -> None:
    from app.jobs.promote_platform_owner import _run

    legacy = await create_platform_admin(client, "hdpromotecli")
    assert await _run(legacy["email"], apply=False) == 0
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        codes = {
            row[0]
            for row in (
                await db.execute(
                    select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == uuid.UUID(legacy["user_id"]))
                )
            ).all()
        }
    assert codes == {"SUPER_ADMIN"}
    assert await _run(unique_email("hdpromotecli-missing"), apply=True) == 1


# === PR #18 hors périmètre : aucun moteur de commission =========================================
async def test_no_commission_engine_tables_or_routes_exist() -> None:
    async with AsyncSessionLocal() as db:
        tables = {
            row[0]
            for row in (
                await db.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND "
                        "(table_name LIKE '%commission%' OR table_name LIKE '%subscription%' OR table_name LIKE '%ledger%' "
                        "OR table_name LIKE '%payout%')"
                    )
                )
            ).all()
        }
        columns = {
            (row[0], row[1])
            for row in (
                await db.execute(
                    text(
                        "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public' "
                        "AND column_name LIKE '%commission%'"
                    )
                )
            ).all()
        }
    assert tables == set()
    assert columns == {("partner_school_enrollments", "commission_eligible")}
    paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    assert not any(word in path for path in paths for word in ("commission", "subscription", "payout", "ledger"))

