"""Test 1 — Isolation tenant (critique, cahier des charges §45).

« Utilisateur École A -> impossible d'accéder aux données École B. »
Vérifie les deux lignes de défense : filtrage applicatif (permissions scopées) ET
PostgreSQL Row Level Security (schools, user_roles) — même en forgeant un organization_id.
"""

from datetime import date

from httpx import AsyncClient

from tests.conftest import register_school, unique_email


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


async def test_admin_a_cannot_read_school_b(client: AsyncClient) -> None:
    school_a = await register_school(client, "isoread-a")
    school_b = await register_school(client, "isoread-b")
    token_a = await _login(client, school_a["user"]["email"])

    response = await client.get(
        f"/api/v1/schools/{school_b['school']['id']}", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert response.status_code in (403, 404)


async def test_admin_a_cannot_update_school_b(client: AsyncClient) -> None:
    school_a = await register_school(client, "isowrite-a")
    school_b = await register_school(client, "isowrite-b")
    token_a = await _login(client, school_a["user"]["email"])

    response = await client.patch(
        f"/api/v1/schools/{school_b['school']['id']}",
        json={"name": "Piraté"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code in (403, 404)

    # La donnée de B n'a réellement pas changé.
    token_b = await _login(client, school_b["user"]["email"])
    check = await client.get(
        f"/api/v1/schools/{school_b['school']['id']}", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert check.json()["name"] == school_b["school"]["name"]
    assert check.json()["name"] != "Piraté"


async def test_admin_a_cannot_list_schools_of_organization_b(client: AsyncClient) -> None:
    school_a = await register_school(client, "isolist-a")
    school_b = await register_school(client, "isolist-b")
    token_a = await _login(client, school_a["user"]["email"])

    response = await client.get(
        f"/api/v1/schools?organization_id={school_b['organization']['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 403


async def test_admin_a_cannot_read_organization_b(client: AsyncClient) -> None:
    school_a = await register_school(client, "isoorg-a")
    school_b = await register_school(client, "isoorg-b")
    token_a = await _login(client, school_a["user"]["email"])

    response = await client.get(
        f"/api/v1/organizations/{school_b['organization']['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    # Phase 20 : `organizations` a désormais RLS (comme `schools` depuis la Phase 1, voir
    # test_admin_a_cannot_read_school_b ci-dessus, qui accepte déjà les deux codes pour la même
    # raison) — la ligne de l'organisation B est invisible sous le contexte de A avant même que
    # `ensure_permission` s'exécute, donc 404 plutôt que 403. Les deux valent isolation prouvée.
    assert response.status_code in (403, 404)


async def test_admin_a_cannot_create_school_under_organization_b(client: AsyncClient) -> None:
    """Même en forgeant explicitement l'organization_id de B dans le corps de la requête."""
    school_a = await register_school(client, "isocreate-a")
    school_b = await register_school(client, "isocreate-b")
    token_a = await _login(client, school_a["user"]["email"])

    response = await client.post(
        "/api/v1/schools",
        json={
            "organization_id": school_b["organization"]["id"],
            "name": "École intruse",
            "slug": "intruse",
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 403


async def test_row_level_security_hides_school_row_even_bypassing_app_check(client: AsyncClient) -> None:
    """Vérifie directement au niveau base (rôle applicatif non-superutilisateur) que la ligne
    de l'école B est invisible sous le contexte tenant de A — la garantie RLS elle-même, pas
    seulement le contrôle applicatif au-dessus."""
    import uuid

    from sqlalchemy import select

    from app.core.tenancy import apply_tenant_context
    from app.db.session import AsyncSessionLocal
    from app.modules.schools.models import School

    school_a = await register_school(client, "isorls-a")
    school_b = await register_school(client, "isorls-b")

    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(school_a["user"]["id"]))
        result = await db.execute(select(School).where(School.id == uuid.UUID(school_b["school"]["id"])))
        assert result.scalar_one_or_none() is None

        # Contrôle positif : la même session voit bien sa propre école.
        own = await db.execute(select(School).where(School.id == uuid.UUID(school_a["school"]["id"])))
        assert own.scalar_one_or_none() is not None
        await db.rollback()


# --- Phase 24 : isolation cross-école AU SEIN d'une même organisation --------------------------
# Distinct des tests ci-dessus (organisations différentes) : ici School A et School B partagent
# la même Organization — cas où RLS (basée sur `organization_id`, pas `school_id`) ne peut PAS
# servir de seconde ligne de défense, contrairement aux tests cross-organisation ci-dessus. Le
# contrôle applicatif (`app/core/permissions.py::get_scoped_permission_codes`/`is_teacher_only`)
# est donc ici la SEULE protection réelle — bug confirmé et corrigé en Phase 24 (Discovery Phase
# 24 puis validation empirique : avant correctif, la requête ci-dessous renvoyait 200 avec les
# données réelles de l'élève de School A).
async def test_teacher_of_sibling_school_cannot_read_students_of_another_school_same_organization(
    client: AsyncClient,
) -> None:
    data = await register_school(client, "isosiblinga")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'], 'SuperSecret123')}"}
    organization_id = data["organization"]["id"]
    school_a_id = data["school"]["id"]

    school_b_response = await client.post(
        "/api/v1/schools",
        json={"organization_id": organization_id, "name": "École B Sibling", "slug": "ecole-b-isosiblinga"},
        headers=headers_admin,
    )
    assert school_b_response.status_code == 201, school_b_response.text
    school_b_id = school_b_response.json()["id"]

    teacher_email = unique_email("teacher.isosiblinga")
    create_teacher = await client.post(
        "/api/v1/users",
        json={"email": teacher_email, "full_name": "Prof École B", "school_id": school_b_id, "role_code": "TEACHER"},
        headers=headers_admin,
    )
    assert create_teacher.status_code == 201, create_teacher.text
    dev_token = create_teacher.json()["dev_reset_token"]
    reset = await client.post(
        "/api/v1/auth/reset-password", json={"token": dev_token, "new_password": "TeacherPass123"}
    )
    assert reset.status_code == 204
    headers_teacher_b = {"Authorization": f"Bearer {await _login(client, teacher_email, 'TeacherPass123')}"}

    student_response = await client.post(
        "/api/v1/students",
        json={
            "school_id": school_a_id,
            "matricule": "SIBLING001",
            "first_name": "Confidentiel",
            "last_name": "ElèveA",
            "date_of_birth": str(date(2015, 1, 1)),
            "sex": "M",
        },
        headers=headers_admin,
    )
    assert student_response.status_code == 201, student_response.text

    # Le professeur de l'école B — même organisation, aucune affectation à l'école A — ne doit
    # jamais pouvoir lister ni lire les élèves de l'école A.
    response = await client.get(f"/api/v1/students?school_id={school_a_id}", headers=headers_teacher_b)
    assert response.status_code == 403, response.text

    direct_response = await client.get(
        f"/api/v1/students/{student_response.json()['id']}", headers=headers_teacher_b
    )
    assert direct_response.status_code == 403, direct_response.text


async def test_org_wide_admin_still_has_access_to_every_school_of_the_organization(client: AsyncClient) -> None:
    """Non-régression explicite du correctif Phase 24 : un rôle réellement org-wide
    (`school_id IS NULL`, ex. le SCHOOL_ADMIN créé à l'inscription) doit continuer à fonctionner
    sur TOUTE école de son organisation, y compris une école créée après coup."""
    data = await register_school(client, "isoorgwidea")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'], 'SuperSecret123')}"}
    organization_id = data["organization"]["id"]

    school_b_response = await client.post(
        "/api/v1/schools",
        json={"organization_id": organization_id, "name": "École B OrgWide", "slug": "ecole-b-isoorgwidea"},
        headers=headers_admin,
    )
    assert school_b_response.status_code == 201, school_b_response.text
    school_b_id = school_b_response.json()["id"]

    response = await client.get(f"/api/v1/students?school_id={school_b_id}", headers=headers_admin)
    assert response.status_code == 200, response.text


async def test_cumulative_roles_stay_isolated_per_school_same_organization(client: AsyncClient) -> None:
    """Revue finale Phase 24 — scénario du cumul de rôles, point principal de la revue : un même
    utilisateur tient un rôle TEACHER dans School A (permission `students.read` seule, pas
    `students.manage` — voir rbac/seed.py PHASE3_ROLE_PERMISSIONS) ET un rôle STAFF dans School B
    de la même organisation (`students.manage` en plus). Le rôle STAFF de B ne doit JAMAIS devenir
    implicitement organization-wide et fuiter vers School A simplement parce que
    `organization_id` correspond — ce cumul est un cas légitime du modèle (ex. personnel partagé
    entre deux campus d'un même groupe scolaire), pas un cas à interdire, mais chaque rôle doit
    rester strictement isolé à son école."""
    data = await register_school(client, "isocumula")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'], 'SuperSecret123')}"}
    organization_id = data["organization"]["id"]
    school_a_id = data["school"]["id"]

    school_b_response = await client.post(
        "/api/v1/schools",
        json={"organization_id": organization_id, "name": "École B Cumul", "slug": "ecole-b-isocumula"},
        headers=headers_admin,
    )
    assert school_b_response.status_code == 201, school_b_response.text
    school_b_id = school_b_response.json()["id"]

    shared_email = unique_email("cumul.isocumula")
    create_teacher_a = await client.post(
        "/api/v1/users",
        json={"email": shared_email, "full_name": "Cumul Rôles", "school_id": school_a_id, "role_code": "TEACHER"},
        headers=headers_admin,
    )
    assert create_teacher_a.status_code == 201, create_teacher_a.text
    dev_token = create_teacher_a.json()["dev_reset_token"]
    reset = await client.post(
        "/api/v1/auth/reset-password", json={"token": dev_token, "new_password": "CumulPass123"}
    )
    assert reset.status_code == 204

    # Même compte (même email), second rôle STAFF attaché sur School B — comportement déjà
    # existant et testé par ailleurs (test_create_with_existing_email_attaches_role_without_duplicate).
    attach_staff_b = await client.post(
        "/api/v1/users",
        json={"email": shared_email, "full_name": "Cumul Rôles", "school_id": school_b_id, "role_code": "STAFF"},
        headers=headers_admin,
    )
    assert attach_staff_b.status_code == 201, attach_staff_b.text
    assert attach_staff_b.json()["user"]["id"] == create_teacher_a.json()["user"]["id"]

    headers_user = {"Authorization": f"Bearer {await _login(client, shared_email, 'CumulPass123')}"}

    # École A : le rôle est TEACHER (students.read uniquement) — la création d'élève
    # (students.manage) doit être refusée, MÊME SI ce même compte a students.manage via STAFF
    # dans l'école B de la même organisation.
    create_in_a = await client.post(
        "/api/v1/students",
        json={
            "school_id": school_a_id,
            "matricule": "CUMULA001",
            "first_name": "Ne",
            "last_name": "DoitPasExister",
            "date_of_birth": str(date(2015, 1, 1)),
            "sex": "F",
        },
        headers=headers_user,
    )
    assert create_in_a.status_code == 403, create_in_a.text

    # Lecture (students.read, accordée à TEACHER) reste autorisée dans École A.
    read_in_a = await client.get(f"/api/v1/students?school_id={school_a_id}", headers=headers_user)
    assert read_in_a.status_code == 200, read_in_a.text

    # École B : le rôle STAFF (students.manage) autorise réellement la création ici.
    create_in_b = await client.post(
        "/api/v1/students",
        json={
            "school_id": school_b_id,
            "matricule": "CUMULB001",
            "first_name": "Peut",
            "last_name": "ExisterIci",
            "date_of_birth": str(date(2015, 1, 1)),
            "sex": "F",
        },
        headers=headers_user,
    )
    assert create_in_b.status_code == 201, create_in_b.text
