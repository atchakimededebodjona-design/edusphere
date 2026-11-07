"""Validation de l'infrastructure d'isolation (Phase 2) — tests synchrones ET asynchrones.

Tests VOLONTAIREMENT SÉQUENTIELS : ils observent les effets du nettoyage d'un test sur le suivant
et doivent être exécutés comme un tout (python -m pytest tests/test_edusphere_test_isolation.py).
Ils démontrent, avec asyncio_mode = "auto" (aucun marqueur asyncio) :
- le nettoyage PostgreSQL et Redis avant ET après chaque test, synchrone comme asynchrone ;
- la réinitialisation du cache de session _PLATFORM_ADMIN_EMAIL (décision D2) ;
- l'absence de conflit de boucle : nettoyage sur un thread dédié, boucle de session intacte et
  pool AsyncSessionLocal toujours utilisable après les nettoyages.
"""

import asyncio
import threading

import pytest
from httpx import AsyncClient
from sqlalchemy import text

import edusphere_test_guard as guard
from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from tests import conftest as suite_conftest
from tests.conftest import register_school

_PROBE_KEY = "edusphere:isolation-probe"
_SEEN: dict[str, object] = {}


def _entries() -> list[tuple[str, str]]:
    return [(entry["phase"], entry["nodeid"]) for entry in guard.ISOLATION_LOG]


def _sibling(request: pytest.FixtureRequest, name: str) -> str:
    return f"{request.node.nodeid.split('::')[0]}::{name}"


async def _count_organizations() -> int:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        return (await db.execute(text("SELECT count(*) FROM organizations"))).scalar_one()


async def test_01_async_writes_db_redis_and_suite_cache(
    client: AsyncClient, request: pytest.FixtureRequest
) -> None:
    last = guard.ISOLATION_LOG[-1]
    assert (last["phase"], last["nodeid"]) == ("avant", request.node.nodeid)
    assert last["thread"] != threading.current_thread().name
    _SEEN["session_loop"] = asyncio.get_running_loop()

    await register_school(client, "isoa")
    assert suite_conftest._PLATFORM_ADMIN_EMAIL is not None
    assert await _count_organizations() == 1
    guard.current_state().redis_data.set(_PROBE_KEY, "A")


def test_02_sync_sees_clean_state(request: pytest.FixtureRequest) -> None:
    entries = _entries()
    me = request.node.nodeid
    first = _sibling(request, "test_01_async_writes_db_redis_and_suite_cache")
    assert entries[-1] == ("avant", me)
    assert entries.index(("après", first)) < entries.index(("avant", me))
    assert suite_conftest._PLATFORM_ADMIN_EMAIL is None
    assert guard.count_rows_platform_wide("organizations") == 0
    redis_data = guard.current_state().redis_data
    assert redis_data.exists(_PROBE_KEY) == 0
    assert redis_data.dbsize() == 0
    redis_data.set(_PROBE_KEY, "B")


async def test_03_async_reuses_session_loop_and_pool(
    client: AsyncClient, request: pytest.FixtureRequest
) -> None:
    assert guard.current_state().redis_data.exists(_PROBE_KEY) == 0
    assert asyncio.get_running_loop() is _SEEN["session_loop"]
    assert await _count_organizations() == 0
    await register_school(client, "isoc")
    assert await _count_organizations() == 1


def test_04_sync_final_assertions(request: pytest.FixtureRequest) -> None:
    third = _sibling(request, "test_03_async_reuses_session_loop_and_pool")
    assert ("après", third) in _entries()
    assert guard.count_rows_platform_wide("organizations") == 0
    assert request.config.getini("asyncio_mode") == "auto"
    assert threading.current_thread() is threading.main_thread()
    threads = {entry["thread"] for entry in guard.ISOLATION_LOG}
    assert threads and all(name.startswith("edusphere-test-isolation") for name in threads)
