"""P1-1 — unicité des attributions de rôle (migration 0024) et concurrence de POST /users.

La base garantit désormais qu'une attribution (user, rôle, portée) n'existe qu'une fois, par trois
index UNIQUE partiels (global / organisation / école). Le service garde sa vérification rapide
(attribution déjà présente => 201 idempotent, inchangé) ; une requête concurrente perdante obtient
un 409 contrôlé, sans état partiel ni email.
"""

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.auth.models import PasswordResetToken
from app.modules.rbac.models import Role, UserRole
from app.modules.users.models import User
from tests.conftest import add_school_to_organization, assign_role, register_school, unique_email
from tests.pr17_helpers import auth

CONFLICT = "This account or role assignment was modified concurrently; please retry"


async def _new_user() -> str:
    from app.core.security import hash_password

    user_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        db.add(User(id=user_id, email=unique_email("uq"), full_name="Unicité", hashed_password=hash_password("SuperSecret123")))
        await db.commit()
    return str(user_id)


async def _count(user_id: str, role_code: str, organization_id: str | None, school_id: str | None) -> int:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        stmt = (
            select(func.count())
            .select_from(UserRole)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == uuid.UUID(user_id), Role.code == role_code)
        )
        stmt = stmt.where(
            UserRole.organization_id.is_(None) if organization_id is None else UserRole.organization_id == uuid.UUID(organization_id)
        )
        stmt = stmt.where(UserRole.school_id.is_(None) if school_id is None else UserRole.school_id == uuid.UUID(school_id))
        return int((await db.execute(stmt)).scalar_one())


# === Index présents, exactement ===========================================================
async def test_partial_unique_indexes_exist_with_exact_predicates() -> None:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'user_roles' AND indexname LIKE 'uq_user_roles_%'")
            )
        ).all()
    defs = {name: definition for name, definition in rows}
    assert set(defs) == {"uq_user_roles_global", "uq_user_roles_org", "uq_user_roles_school"}
    assert all("UNIQUE" in d for d in defs.values())
    assert "(user_id, role_id)" in defs["uq_user_roles_global"]
    assert "organization_id IS NULL" in defs["uq_user_roles_global"] and "school_id IS NULL" in defs["uq_user_roles_global"]
    assert "(user_id, role_id, organization_id)" in defs["uq_user_roles_org"]
    assert "organization_id IS NOT NULL" in defs["uq_user_roles_org"] and "school_id IS NULL" in defs["uq_user_roles_org"]
    assert "(user_id, role_id, school_id)" in defs["uq_user_roles_school"]
    assert "school_id IS NOT NULL" in defs["uq_user_roles_school"]


# === A / B / C — doublons refusés par la base, pour chaque portée ==================================
async def test_a_global_duplicate_is_refused() -> None:
    user_id = await _new_user()
    await assign_role(user_id, "SUPER_ADMIN", None, None)
    with pytest.raises(IntegrityError):
        await assign_role(user_id, "SUPER_ADMIN", None, None)
    assert await _count(user_id, "SUPER_ADMIN", None, None) == 1


async def test_b_org_wide_duplicate_is_refused(client: AsyncClient) -> None:
    org = await register_school(client, "uqorg")
    user_id = await _new_user()
    await assign_role(user_id, "DIRECTOR", org["organization"]["id"], None)
    with pytest.raises(IntegrityError):
        await assign_role(user_id, "DIRECTOR", org["organization"]["id"], None)
    assert await _count(user_id, "DIRECTOR", org["organization"]["id"], None) == 1


async def test_c_school_duplicate_is_refused(client: AsyncClient) -> None:
    org = await register_school(client, "uqschool")
    user_id = await _new_user()
    await assign_role(user_id, "TEACHER", org["organization"]["id"], org["school"]["id"])
    with pytest.raises(IntegrityError):
        await assign_role(user_id, "TEACHER", org["organization"]["id"], org["school"]["id"])
    assert await _count(user_id, "TEACHER", org["organization"]["id"], org["school"]["id"]) == 1


# === D / E — attributions distinctes toujours permises ============================================
async def test_d_same_user_different_schools_allowed(client: AsyncClient) -> None:
    org = await register_school(client, "uqd")
    headers = auth(org["tokens"]["access_token"])
    second = await add_school_to_organization(
        client, org["organization"]["id"], "Seconde ecole", "seconde", headers
    )
    user_id = await _new_user()
    await assign_role(user_id, "TEACHER", org["organization"]["id"], org["school"]["id"])
    await assign_role(user_id, "TEACHER", org["organization"]["id"], second["id"])
    assert await _count(user_id, "TEACHER", org["organization"]["id"], org["school"]["id"]) == 1
    assert await _count(user_id, "TEACHER", org["organization"]["id"], second["id"]) == 1


async def test_e_same_user_same_org_different_roles_allowed(client: AsyncClient) -> None:
    org = await register_school(client, "uqe")
    org_id, school_id = org["organization"]["id"], org["school"]["id"]
    user_id = await _new_user()
    await assign_role(user_id, "SCHOOL_ADMIN", org_id, None)
    await assign_role(user_id, "DIRECTOR", org_id, None)
    await assign_role(user_id, "TEACHER", org_id, school_id)
    await assign_role(user_id, "STAFF", org_id, school_id)
    # Même rôle org-wide ET scopé école : portées différentes, deux index distincts — permis.
    await assign_role(user_id, "SCHOOL_ADMIN", org_id, school_id)
    for role_code, school in (("SCHOOL_ADMIN", None), ("DIRECTOR", None), ("TEACHER", school_id), ("STAFF", school_id), ("SCHOOL_ADMIN", school_id)):
        assert await _count(user_id, role_code, org_id, school) == 1


# === Sémantique séquentielle inchangée : réattacher = 201 idempotent, une seule ligne ================
async def test_sequential_duplicate_attach_stays_idempotent(client: AsyncClient) -> None:
    org = await register_school(client, "uqseq")
    headers = auth(org["tokens"]["access_token"])
    email = unique_email("uqseq")
    payload = {"email": email, "full_name": "Ens", "school_id": org["school"]["id"], "role_code": "TEACHER"}
    first = await client.post("/api/v1/users", json=payload, headers=headers)
    second = await client.post("/api/v1/users", json=payload, headers=headers)
    assert (first.status_code, second.status_code) == (201, 201)
    assert second.json()["dev_reset_token"] is None
    assert await _count(first.json()["user"]["id"], "TEACHER", org["organization"]["id"], org["school"]["id"]) == 1


# === F — concurrence =================================================================================
async def test_f_concurrent_attach_same_role_deterministic_race(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Course FORCÉE au point exact du flush, sans modifier le code applicatif.

    Barrière posée sur `AsyncSession.flush`, déclenchée UNIQUEMENT pour une session dont les objets
    en attente (`session.new`) contiennent la UserRole visée (ce compte, cette école). Dans
    `create_or_attach_user`, cet objet n'existe qu'APRÈS le SELECT d'idempotence et le
    `db.add(UserRole(...))`, juste avant le `await db.flush()` explicite qui suit. Séquence garantie :
    1. les deux requêtes ont fait leur SELECT (aucune attribution trouvée) ;
    2. chacune a ajouté sa UserRole en mémoire (pré-flush) ;
    3. les deux atteignent la barrière ;
    4. seulement alors, les deux sont libérées vers le flush ;
    5. l'index unique `uq_user_roles_school` départage (le second INSERT attend le commit du
       premier puis échoue) : jamais l'ordre imposé par le test.
    Résultat attendu : exactement [201, 409] et une seule attribution."""
    org = await register_school(client, "uqrace")
    headers = auth(org["tokens"]["access_token"])
    email = unique_email("uqrace")
    created = await client.post(
        "/api/v1/users", json={"email": email, "full_name": "Ens", "school_id": org["school"]["id"], "role_code": "TEACHER"}, headers=headers
    )
    assert created.status_code == 201
    user_id = uuid.UUID(created.json()["user"]["id"])
    school_id = uuid.UUID(org["school"]["id"])

    barrier = asyncio.Barrier(2)
    reached: list[str] = []
    original_flush = AsyncSession.flush

    def _holds_target_role(session: AsyncSession) -> bool:
        return any(
            isinstance(obj, UserRole) and obj.user_id == user_id and obj.school_id == school_id
            for obj in session.sync_session.new
        )

    async def flush_with_barrier(self: AsyncSession, objects=None) -> None:  # type: ignore[no-untyped-def]
        if _holds_target_role(self):
            reached.append("ready")
            # Les deux requêtes doivent arriver ici (SELECT fait + UserRole ajoutée) avant tout INSERT.
            await asyncio.wait_for(barrier.wait(), timeout=15)
        await original_flush(self, objects)

    monkeypatch.setattr(AsyncSession, "flush", flush_with_barrier)
    payload = {"email": email, "full_name": "Ens", "school_id": org["school"]["id"], "role_code": "STAFF"}
    results = await asyncio.gather(
        client.post("/api/v1/users", json=payload, headers=headers),
        client.post("/api/v1/users", json=payload, headers=headers),
    )
    monkeypatch.undo()
    assert reached == ["ready", "ready"], "les deux requêtes doivent avoir atteint la barrière pré-flush"
    statuses = sorted(r.status_code for r in results)
    assert statuses == [201, 409], [r.text for r in results]
    loser = next(r for r in results if r.status_code == 409)
    assert loser.json()["detail"] == CONFLICT
    assert await _count(str(user_id), "STAFF", org["organization"]["id"], org["school"]["id"]) == 1


async def test_f_concurrent_creation_same_new_email(client: AsyncClient) -> None:
    """Création concurrente d'un MÊME nouvel email : un seul compte, une seule attribution, aucun
    token de réinitialisation orphelin ; chaque réponse est 201 (gagnant ou réutilisation après
    commit du gagnant) ou 409 contrôlé (perdant) — jamais 500."""
    org = await register_school(client, "uqnew")
    headers = auth(org["tokens"]["access_token"])
    email = unique_email("uqnew")
    payload = {"email": email, "full_name": "Nouveau", "school_id": org["school"]["id"], "role_code": "TEACHER"}
    results = await asyncio.gather(*[client.post("/api/v1/users", json=payload, headers=headers) for _ in range(3)])
    assert all(r.status_code in (201, 409) for r in results), [r.text for r in results]
    assert any(r.status_code == 201 for r in results)
    for r in results:
        if r.status_code == 409:
            assert r.json()["detail"] == CONFLICT
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        users = (await db.execute(select(User).where(User.email == email))).scalars().all()
        assert len(users) == 1
        tokens = (
            await db.execute(select(func.count()).select_from(PasswordResetToken).where(PasswordResetToken.user_id == users[0].id))
        ).scalar_one()
    assert tokens == 1  # un seul token : celui du gagnant (les perdants ont été annulés)
    assert await _count(str(users[0].id), "TEACHER", org["organization"]["id"], org["school"]["id"]) == 1


# === Migration défensive : échec explicite en présence de doublons historiques ======================
def test_migration_refuses_historical_duplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    """La détection de doublons s'exécute AVANT toute création d'index et échoue explicitement
    (l'échec réel sur une base contenant des doublons est démontré séparément sur base neuve)."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0024_user_roles_unique_scopes.py"
    spec = importlib.util.spec_from_file_location("migration_0024", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    # Détection simulée : 2 groupes de doublons sur la portée école. L'erreur est levée AVANT la
    # boucle de création des index (hors contexte Alembic, toute création aurait elle-même échoué).
    monkeypatch.setattr(migration, "_duplicate_groups", lambda columns, predicate: 2 if predicate == "school_id IS NOT NULL" else 0)
    with pytest.raises(RuntimeError, match="uq_user_roles_school: 2 groupe"):
        migration.upgrade()
