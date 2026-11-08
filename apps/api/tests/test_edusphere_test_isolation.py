"""Validation de l'infrastructure d'isolation (Phase 2) — tests synchrones ET asynchrones.

Tests VOLONTAIREMENT SÉQUENTIELS : ils observent les effets du nettoyage d'un test sur le suivant
et doivent être exécutés comme un tout (python -m pytest tests/test_edusphere_test_isolation.py).
Ils démontrent, avec asyncio_mode = "auto" (aucun marqueur asyncio) :
- le nettoyage PostgreSQL et Redis avant ET après chaque test, synchrone comme asynchrone ;
- la réinitialisation du cache de session _PLATFORM_ADMIN_EMAIL (décision D2) ;
- l'absence de conflit de boucle : nettoyage sur un thread dédié, boucle de session intacte et
  pool AsyncSessionLocal toujours utilisable après les nettoyages.

Tests 05-06 (Phases 3.3-C3 puis 3.3-C5) : scénario EXPÉRIMENTAL et contrôlé de tâche asyncio
orpheline, exécuté UNIQUEMENT en mode EDUSPHERE_TASK_GUARD=enforce (ignoré en observe : sans
règlement, l'orpheline ne serait jamais terminée). La tâche n'accède à aucun service (ni PostgreSQL,
ni Redis, ni fichier) : elle attend un asyncio.Event jamais envoyé. Le test 05 (marqueur
edusphere_expected_orphan) la laisse volontairement active ; le règlement de apps/api/conftest.py
l'annule après le test 05, AVANT le nettoyage ; le test 06 vérifie l'annulation effective, la
réception de CancelledError et l'absence de reprise ; la fixture de module le vérifie à nouveau.
"""

import asyncio
import threading
from typing import Any

import pytest
import pytest_asyncio
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


# --- Phase 3.3-C5 : tâche orpheline volontaire, réglée en mode enforce ---------------------------

_ORPHAN_NAME = "edusphere-intentional-orphan"
_ENFORCE_ONLY = pytest.mark.skipif(
    guard.task_guard_mode() != "enforce",
    reason="scénario d'orpheline volontaire : uniquement avec EDUSPHERE_TASK_GUARD=enforce",
)


async def _intentional_orphan(release: asyncio.Event, slot: dict[str, Any]) -> str:
    """Aucun effet de bord : attend un signal jamais envoyé ; consigne la réception de
    CancelledError (puis la relance) et une éventuelle reprise (qui ne doit jamais avoir lieu)."""
    try:
        await release.wait()
    except asyncio.CancelledError as exc:
        slot["cancelled_received"] = exc.args
        raise
    slot["resumed"] = True
    return "released"


async def _loop_probe() -> str:
    return "ok"


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def _intentional_orphan_slot():
    """Ne libère JAMAIS la tâche : sa finalisation vérifie qu'elle a été annulée par le règlement
    (terminée, annulée, CancelledError reçue, aucune reprise)."""
    slot: dict[str, Any] = {
        "release": asyncio.Event(),
        "task": None,
        "cancelled_received": None,
        "resumed": False,
    }
    yield slot
    task = slot["task"]
    if task is None:
        return
    assert task.done(), f"{_ORPHAN_NAME} toujours active en fin de module"
    assert task.cancelled()
    assert slot["cancelled_received"] is not None and slot["resumed"] is False
    assert not slot["release"].is_set()
    print(
        f"[{_ORPHAN_NAME}] annulée par le règlement : done={task.done()}, "
        f"cancelled={task.cancelled()}, CancelledError={slot['cancelled_received']!r}, "
        f"reprise={slot['resumed']}"
    )


@_ENFORCE_ONLY
@pytest.mark.edusphere_expected_orphan
async def test_05_intentional_orphan_is_left_active_for_the_settlement(
    _intentional_orphan_slot: dict[str, Any],
) -> None:
    task = asyncio.create_task(
        _intentional_orphan(_intentional_orphan_slot["release"], _intentional_orphan_slot),
        name=_ORPHAN_NAME,
    )
    _intentional_orphan_slot["task"] = task
    await asyncio.sleep(0)  # un tour de boucle : la tâche démarre et se suspend sur release.wait()
    assert not task.done()
    # Le test se termine SANS attendre ni annuler la tâche : le règlement s'en charge.


@_ENFORCE_ONLY
async def test_06_orphan_was_cancelled_without_resuming_and_loop_usable(
    _intentional_orphan_slot: dict[str, Any], request: pytest.FixtureRequest
) -> None:
    task = _intentional_orphan_slot["task"]
    if task is None:
        pytest.skip("scénario séquentiel : à exécuter après test_05")
    origin = _sibling(request, "test_05_intentional_orphan_is_left_active_for_the_settlement")
    entries = _entries()
    assert entries.index(("après", origin)) < entries.index(("avant", request.node.nodeid))
    # Réglée après le test 05 (avant son nettoyage) : terminée, annulée, CancelledError reçue avec
    # le message du règlement, et jamais reprise.
    assert task.done() and task.cancelled()
    received = _intentional_orphan_slot["cancelled_received"]
    assert received is not None and "tâche orpheline" in received[0]
    assert _intentional_orphan_slot["resumed"] is False
    assert not _intentional_orphan_slot["release"].is_set()
    # Boucle de session intacte et utilisable.
    loop = asyncio.get_running_loop()
    assert task.get_loop() is loop
    assert await asyncio.create_task(_loop_probe()) == "ok"
    # Aucun effet résiduel sur le cache de suite (remis à zéro par l'isolation).
    assert suite_conftest._PLATFORM_ADMIN_EMAIL is None
