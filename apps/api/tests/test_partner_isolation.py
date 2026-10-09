"""PR #17 — isolation des partenaires : aucun accès aux données scolaires ni plateforme, aucune
fuite entre partenaires, aucune visibilité RLS implicite, et catalogue de permissions strictement
disjoint du domaine scolaire (pour PARTNER_ADMIN comme pour PLATFORM_OWNER)."""

import uuid

from httpx import AsyncClient
from sqlalchemy import text

from app.core.permissions import get_all_permission_codes, get_scoped_permission_codes
from app.core.tenancy import apply_tenant_context, set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.rbac.models import Role, UserRole
from app.modules.rbac.seed import PR17_PARTNER_PERMISSIONS, PR17_PLATFORM_PERMISSIONS
from app.modules.users.models import User
from tests.conftest import assign_role, register_school, unique_email
from tests.pr17_helpers import (
    PLATFORM_GET_ENDPOINTS,
    SCHOOL_DOMAIN_PREFIXES,
    create_partner,
    create_platform_owner,
    enroll_school_as_partner,
    enrollment_payload,
    school_data_endpoints,
    school_with_student,
)


async def _owner_and_partner(client: AsyncClient, prefix: str) -> tuple[dict, dict]:
    owner = await create_platform_owner(client, f"{prefix}owner")
    partner = await create_partner(client, owner["headers"], f"{prefix}partner")
    return owner, partner


async def _add_student(client: AsyncClient, admin_headers: dict[str, str], school_id: str) -> dict:
    response = await client.post(
        "/api/v1/students",
        json={
            "school_id": school_id,
            "matricule": f"S{uuid.uuid4().hex[:8]}",
            "first_name": "Eleve",
            "last_name": "Partenaire",
            "date_of_birth": "2015-01-01",
            "sex": "F",
        },
        headers=admin_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# === C.1 — aucune donnée scolaire, aucune donnée plateforme ===========================================
async def test_partner_cannot_read_school_data_of_any_school(client: AsyncClient) -> None:
    """Y compris les écoles que CE partenaire a lui-même inscrites. Statut 403 (RBAC) ou 404 :
    pour un partenaire, RLS masque déjà l'école/l'élève lui-même (`tenant_org_ids` vide, voir
    core/tenancy.py) avant même le contrôle de permission — défense en profondeur, jamais 200."""
    _, partner = await _owner_and_partner(client, "c1")
    own = await enroll_school_as_partner(client, partner["headers"], "c1own")
    own_student = await _add_student(client, own["admin_headers"], own["school"]["id"])
    other = await school_with_student(client, "c1other")

    targets = [(own["school"]["id"], own_student["id"]), (other["school"]["id"], other["student"]["id"])]
    for school_id, student_id in targets:
        for path in school_data_endpoints(school_id, student_id):
            response = await client.get(path, headers=partner["headers"])
            assert response.status_code in (403, 404), (path, response.status_code, response.text)
            assert student_id not in response.text


async def test_partner_cannot_write_school_data(client: AsyncClient) -> None:
    _, partner = await _owner_and_partner(client, "c1write")
    own = await enroll_school_as_partner(client, partner["headers"], "c1writeown")
    student = await _add_student(client, own["admin_headers"], own["school"]["id"])
    response = await client.patch(
        f"/api/v1/students/{student['id']}", json={"first_name": "Pirate"}, headers=partner["headers"]
    )
    assert response.status_code in (403, 404)
    response = await client.post(
        "/api/v1/users",
        json={
            "email": unique_email("c1write"),
            "full_name": "Intrus",
            "school_id": own["school"]["id"],
            "role_code": "SCHOOL_ADMIN",
        },
        headers=partner["headers"],
    )
    assert response.status_code in (403, 404)


async def test_partner_gets_403_on_every_platform_endpoint(client: AsyncClient) -> None:
    _, partner = await _owner_and_partner(client, "c1platform")
    for path in PLATFORM_GET_ENDPOINTS:
        response = await client.get(path, headers=partner["headers"])
        assert response.status_code == 403, (path, response.text)
    response = await client.post(
        "/api/v1/platform/organizations", json=enrollment_payload("c1platform"), headers=partner["headers"]
    )
    assert response.status_code == 403
    response = await client.post(
        "/api/v1/platform/partners",
        json={"display_name": "Sous-partenaire", "full_name": "Sous", "email": unique_email("c1sub")},
        headers=partner["headers"],
    )
    assert response.status_code == 403


async def test_partner_cannot_list_or_read_organizations_and_schools_via_tenant_endpoints(client: AsyncClient) -> None:
    _, partner = await _owner_and_partner(client, "c1tenant")
    own = await enroll_school_as_partner(client, partner["headers"], "c1tenantown")
    assert (await client.get("/api/v1/organizations", headers=partner["headers"])).status_code == 403
    response = await client.get(f"/api/v1/organizations/{own['organization']['id']}", headers=partner["headers"])
    assert response.status_code in (403, 404)
    response = await client.get(f"/api/v1/schools/{own['school']['id']}", headers=partner["headers"])
    assert response.status_code in (403, 404)
    response = await client.get(f"/api/v1/users?school_id={own['school']['id']}", headers=partner["headers"])
    assert response.status_code in (403, 404)


# === C.2 — isolation entre partenaires (écoles) =========================================================
async def test_partner_schools_are_strictly_isolated(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "c2owner")
    partner_a = await create_partner(client, owner["headers"], "c2a")
    partner_b = await create_partner(client, owner["headers"], "c2b")
    school_a = await enroll_school_as_partner(client, partner_a["headers"], "c2schoola")
    school_b = await enroll_school_as_partner(client, partner_b["headers"], "c2schoolb")
    platform_school = await register_school(client, "c2platform")

    list_a = (await client.get("/api/v1/partner/schools", headers=partner_a["headers"])).json()
    list_b = (await client.get("/api/v1/partner/schools", headers=partner_b["headers"])).json()
    assert [s["school_id"] for s in list_a] == [school_a["school"]["id"]]
    assert [s["school_id"] for s in list_b] == [school_b["school"]["id"]]
    assert platform_school["school"]["id"] not in {s["school_id"] for s in list_a + list_b}

    dash_a = (await client.get("/api/v1/partner/dashboard", headers=partner_a["headers"])).json()
    assert dash_a == {"school_count": 1, "organization_count": 1}


async def test_partner_lookups_ignore_query_parameters(client: AsyncClient) -> None:
    """Aucun paramètre client n'est jamais lu pour choisir le partenaire."""
    owner = await create_platform_owner(client, "c2query")
    partner_a = await create_partner(client, owner["headers"], "c2qa")
    partner_b = await create_partner(client, owner["headers"], "c2qb")
    school_b = await enroll_school_as_partner(client, partner_b["headers"], "c2qschoolb")

    for path in ("/api/v1/partner/schools", "/api/v1/partner/accounts"):
        response = await client.get(
            f"{path}?partner_id={partner_b['partner']['id']}&user_id={partner_b['user_id']}",
            headers=partner_a["headers"],
        )
        assert response.status_code == 200
        assert response.json() == []
    assert school_b["school"]["id"]


# === C.3 — isolation entre partenaires (comptes) ==========================================================
async def test_partner_accounts_are_strictly_isolated(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "c3owner")
    partner_a = await create_partner(client, owner["headers"], "c3a")
    partner_b = await create_partner(client, owner["headers"], "c3b")
    school_a = await enroll_school_as_partner(client, partner_a["headers"], "c3schoola")
    school_b = await enroll_school_as_partner(client, partner_b["headers"], "c3schoolb")
    platform_school = await register_school(client, "c3platform")

    # Un enseignant dans l'école de A, un dans l'école de B.
    teacher_ids = {}
    for key, school in (("a", school_a), ("b", school_b)):
        created = await client.post(
            "/api/v1/users",
            json={
                "email": unique_email(f"c3teacher{key}"),
                "full_name": f"Enseignant {key}",
                "school_id": school["school"]["id"],
                "role_code": "TEACHER",
            },
            headers=school["admin_headers"],
        )
        assert created.status_code == 201, created.text
        teacher_ids[key] = created.json()["user"]["id"]

    accounts_a = (await client.get("/api/v1/partner/accounts", headers=partner_a["headers"])).json()
    ids_a = {a["id"] for a in accounts_a}
    assert ids_a == {school_a["admin"]["id"], teacher_ids["a"]}
    assert school_b["admin"]["id"] not in ids_a
    assert teacher_ids["b"] not in ids_a
    assert platform_school["user"]["id"] not in ids_a
    # Jamais les comptes plateforme/partenaire eux-mêmes.
    assert not ids_a & {owner["user_id"], partner_a["user_id"], partner_b["user_id"]}
    for account in accounts_a:
        assert set(account.keys()) == {"id", "email", "full_name", "is_active", "created_at", "role_codes"}

    accounts_b = (await client.get("/api/v1/partner/accounts", headers=partner_b["headers"])).json()
    assert {a["id"] for a in accounts_b} == {school_b["admin"]["id"], teacher_ids["b"]}


async def test_partner_accounts_hide_roles_outside_partner_scope(client: AsyncClient) -> None:
    """Un compte rattaché à une école de A ET à une école tierce : seul le rôle dans le
    périmètre de A est exposé, jamais le rattachement tiers."""
    owner = await create_platform_owner(client, "c3scope")
    partner_a = await create_partner(client, owner["headers"], "c3scopea")
    school_a = await enroll_school_as_partner(client, partner_a["headers"], "c3scopeschool")
    other = await register_school(client, "c3scopeother")

    teacher = await client.post(
        "/api/v1/users",
        json={
            "email": unique_email("c3scopeteacher"),
            "full_name": "Enseignant mixte",
            "school_id": school_a["school"]["id"],
            "role_code": "TEACHER",
        },
        headers=school_a["admin_headers"],
    )
    teacher_id = teacher.json()["user"]["id"]
    await assign_role(teacher_id, "ACCOUNTANT", other["organization"]["id"], other["school"]["id"])

    accounts = (await client.get("/api/v1/partner/accounts", headers=partner_a["headers"])).json()
    entry = next(a for a in accounts if a["id"] == teacher_id)
    assert entry["role_codes"] == ["TEACHER"]


async def test_partner_accounts_never_list_a_partner_admin_attached_to_its_school(client: AsyncClient) -> None:
    """Même si un compte partenaire se retrouvait (état anormal, direct en base) avec un rôle
    scopé à une école de A, il n'apparaît jamais dans les comptes de A."""
    owner = await create_platform_owner(client, "c3self")
    partner_a = await create_partner(client, owner["headers"], "c3selfa")
    partner_b = await create_partner(client, owner["headers"], "c3selfb")
    school_a = await enroll_school_as_partner(client, partner_a["headers"], "c3selfschool")
    await assign_role(partner_b["user_id"], "TEACHER", school_a["organization"]["id"], school_a["school"]["id"])
    await assign_role(owner["user_id"], "TEACHER", school_a["organization"]["id"], school_a["school"]["id"])

    ids = {a["id"] for a in (await client.get("/api/v1/partner/accounts", headers=partner_a["headers"])).json()}
    assert partner_b["user_id"] not in ids
    assert owner["user_id"] not in ids


# === C.4 — comptes plateforme/partenaire jamais dans les listes d'utilisateurs d'une école ===============
async def test_owner_and_partner_never_listed_in_school_users(client: AsyncClient) -> None:
    owner, partner = await _owner_and_partner(client, "c4")
    partner_school = await enroll_school_as_partner(client, partner["headers"], "c4partnerschool")
    platform_school = await register_school(client, "c4platformschool")
    platform_school["admin_headers"] = {"Authorization": f"Bearer {platform_school['tokens']['access_token']}"}

    # État « coïncident » : une seconde UserRole globale (organization_id ET school_id NULL) pour
    # chacun — ne doit toujours jamais matcher une école précise (NULL n'égale jamais un UUID).
    await assign_role(owner["user_id"], "PLATFORM_OWNER", organization_id=None, school_id=None)
    await assign_role(partner["user_id"], "PARTNER_ADMIN", organization_id=None, school_id=None)

    for school in (partner_school, platform_school):
        response = await client.get(f"/api/v1/users?school_id={school['school']['id']}", headers=school["admin_headers"])
        assert response.status_code == 200, response.text
        listed_ids = {entry["user"]["id"] for entry in response.json()}
        assert owner["user_id"] not in listed_ids
        assert partner["user_id"] not in listed_ids
        listed_codes = {role["role_code"] for entry in response.json() for role in entry["roles"]}
        assert not listed_codes & {"PLATFORM_OWNER", "PARTNER_ADMIN"}


# === C.5 — RLS : zéro visibilité implicite pour un partenaire =============================================
async def test_partner_session_has_no_rls_visibility_on_tenant_tables(client: AsyncClient) -> None:
    _, partner = await _owner_and_partner(client, "c5")
    own = await enroll_school_as_partner(client, partner["headers"], "c5own")
    own_student = await _add_student(client, own["admin_headers"], own["school"]["id"])
    other = await school_with_student(client, "c5other")

    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(partner["user_id"]))
        settings_row = (
            await db.execute(
                text(
                    "SELECT current_setting('app.is_platform_wide', true), "
                    "current_setting('app.tenant_org_ids', true)"
                )
            )
        ).one()
        assert tuple(settings_row) == ("false", "")

        org_ids = [own["organization"]["id"], other["organization"]["id"]]
        school_ids = [own["school"]["id"], other["school"]["id"]]
        student_ids = [own_student["id"], other["student"]["id"]]
        checks = [
            ("SELECT count(*) FROM organizations WHERE id = ANY(CAST(:ids AS uuid[]))", org_ids),
            ("SELECT count(*) FROM schools WHERE id = ANY(CAST(:ids AS uuid[]))", school_ids),
            ("SELECT count(*) FROM students WHERE id = ANY(CAST(:ids AS uuid[]))", student_ids),
            ("SELECT count(*) FROM partner_school_enrollments WHERE school_id = ANY(CAST(:ids AS uuid[]))", school_ids),
            ("SELECT count(*) FROM partners WHERE user_id = ANY(CAST(:ids AS uuid[]))", [partner["user_id"]]),
        ]
        for sql, ids in checks:
            assert (await db.execute(text(sql), {"ids": ids})).scalar_one() == 0, sql
        # Sans aucun filtre non plus.
        for table in ("organizations", "schools", "students", "partner_school_enrollments", "partners"):
            assert (await db.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0, table
        await db.rollback()

    # Contrôle positif : ces lignes existent bien (contexte platform-wide explicite).
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        count = (
            await db.execute(text("SELECT count(*) FROM schools WHERE id = ANY(CAST(:ids AS uuid[]))"), {"ids": school_ids})
        ).scalar_one()
        assert count == 2
        await db.rollback()


async def test_partner_tables_have_forced_rls_and_expected_policies() -> None:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname IN ('partners', 'partner_school_enrollments')"
                )
            )
        ).all()
        assert {row.relname: (row.relrowsecurity, row.relforcerowsecurity) for row in rows} == {
            "partners": (True, True),
            "partner_school_enrollments": (True, True),
        }
        policies = {
            row[0]
            for row in (
                await db.execute(
                    text(
                        "SELECT polname FROM pg_policy WHERE polrelid IN "
                        "('partners'::regclass, 'partner_school_enrollments'::regclass)"
                    )
                )
            ).all()
        }
        assert policies == {"partners_platform_only", "partner_school_enrollments_tenant_isolation"}


async def test_school_admin_sees_own_enrollment_row_only(client: AsyncClient) -> None:
    """La policy générique s'applique aussi à partner_school_enrollments : un SCHOOL_ADMIN ne voit
    que la ligne de sa propre organisation, jamais celle d'une autre."""
    school_a = await register_school(client, "c5rlsa")
    school_b = await register_school(client, "c5rlsb")
    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(school_a["user"]["id"]))
        rows = (
            await db.execute(
                text("SELECT school_id::text FROM partner_school_enrollments WHERE school_id = ANY(CAST(:ids AS uuid[]))"),
                {"ids": [school_a["school"]["id"], school_b["school"]["id"]]},
            )
        ).all()
        assert {row[0] for row in rows} == {school_a["school"]["id"]}
        assert (await db.execute(text("SELECT count(*) FROM partners"))).scalar_one() == 0
        await db.rollback()


# === C.6 — permissions strictement disjointes ==============================================================
async def _permission_sets(user_id: str, organization_id: str, school_id: str) -> tuple[set[str], set[str]]:
    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(user_id))
        user = await db.get(User, uuid.UUID(user_id))
        assert user is not None
        all_codes = await get_all_permission_codes(db, user)
        scoped = await get_scoped_permission_codes(
            db, user, organization_id=uuid.UUID(organization_id), school_id=uuid.UUID(school_id)
        )
        await db.rollback()
    return all_codes, scoped


async def test_partner_permissions_are_exclusively_partner_codes(client: AsyncClient) -> None:
    _, partner = await _owner_and_partner(client, "c6partner")
    school = await enroll_school_as_partner(client, partner["headers"], "c6partnerschool")
    all_codes, scoped = await _permission_sets(partner["user_id"], school["organization"]["id"], school["school"]["id"])
    assert all_codes == set(PR17_PARTNER_PERMISSIONS)
    assert scoped == set(PR17_PARTNER_PERMISSIONS)
    assert all(code.startswith("partner.") for code in all_codes)
    assert not any(code.startswith(SCHOOL_DOMAIN_PREFIXES) for code in all_codes)
    assert not any(code.startswith("platform.") for code in all_codes)


async def test_platform_owner_permissions_are_exclusively_platform_codes(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "c6owner")
    school = await register_school(client, "c6ownerschool")
    all_codes, scoped = await _permission_sets(owner["user_id"], school["organization"]["id"], school["school"]["id"])
    assert all_codes == set(PR17_PLATFORM_PERMISSIONS)
    assert scoped == set(PR17_PLATFORM_PERMISSIONS)
    assert all(code.startswith("platform.") for code in all_codes)
    assert not any(code.startswith(SCHOOL_DOMAIN_PREFIXES) for code in all_codes)
    assert not any(code.startswith("partner.") for code in all_codes)


async def test_rbac_catalog_grants_new_roles_nothing_else() -> None:
    """Vérifié directement sur le catalogue en base (role_permissions), indépendamment de tout
    compte : aucune permission hors `platform.*`/`partner.*` pour ces deux rôles."""
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT r.code, p.code FROM role_permissions rp JOIN roles r ON r.id = rp.role_id "
                    "JOIN permissions p ON p.id = rp.permission_id WHERE r.code IN ('PLATFORM_OWNER', 'PARTNER_ADMIN')"
                )
            )
        ).all()
    by_role: dict[str, set[str]] = {}
    for role_code, perm_code in rows:
        by_role.setdefault(role_code, set()).add(perm_code)
    assert by_role == {"PLATFORM_OWNER": set(PR17_PLATFORM_PERMISSIONS), "PARTNER_ADMIN": set(PR17_PARTNER_PERMISSIONS)}


async def test_school_roles_never_receive_platform_or_partner_codes() -> None:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT DISTINCT r.code FROM role_permissions rp JOIN roles r ON r.id = rp.role_id "
                    "JOIN permissions p ON p.id = rp.permission_id "
                    "WHERE p.code LIKE 'platform.%' OR p.code LIKE 'partner.%'"
                )
            )
        ).all()
    assert {row[0] for row in rows} == {"SUPER_ADMIN", "PLATFORM_OWNER", "PARTNER_ADMIN"}


async def test_role_model_constants_classify_partner_as_non_platform() -> None:
    from app.modules.rbac.models import ALL_ROLE_CODES, NON_SCHOOL_ROLE_CODES, PLATFORM_ROLE_CODES

    assert PLATFORM_ROLE_CODES == {"SUPER_ADMIN", "PLATFORM_SUPPORT", "PLATFORM_OWNER"}
    assert "PARTNER_ADMIN" not in PLATFORM_ROLE_CODES
    assert NON_SCHOOL_ROLE_CODES == PLATFORM_ROLE_CODES | {"PARTNER_ADMIN"}
    assert "PLATFORM_OWNER" in ALL_ROLE_CODES
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        from sqlalchemy import select

        codes = {row[0] for row in (await db.execute(select(Role.code))).all()}
    assert set(ALL_ROLE_CODES) == codes
    assert UserRole.__doc__ is not None and "PARTNER_ADMIN" in UserRole.__doc__
