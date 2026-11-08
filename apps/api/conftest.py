"""Point d'entrée pytest de l'environnement de tests isolé (Phase 2).

Chargé par pytest AVANT apps/api/tests/conftest.py (conftests initiaux importés du parent vers
l'enfant), donc avant tout import de `app.*`. Toute la vérification a lieu ICI, à l'import : en cas
de refus, le chargement de ce fichier échoue et aucun test n'est collecté ni exécuté.
"""

import edusphere_test_guard as _guard  # première instruction : aucun import de app.* au-dessus

_STATE = _guard.preflight()

import asyncio  # noqa: E402
import sys  # noqa: E402
import weakref  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import TYPE_CHECKING  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

if TYPE_CHECKING:  # pytest 8.2 n'exporte pas TerminalReporter : annotation seulement
    from _pytest.terminal import TerminalReporter


def _run_isolation(phase: str, nodeid: str) -> None:
    try:
        _guard.isolate(_STATE, phase, nodeid)
    except _guard.EnvironmentRefused as exc:
        pytest.exit(f"Isolation interrompue ({phase} {nodeid}) : {exc}", returncode=3)


# --- Tâches asyncio orphelines (Phases 3.3-C1 observation, 3.3-C5 règlement) ----------------------
# La boucle asyncio est partagée par toute la session (asyncio_default_*_loop_scope = "session") et
# pytest-asyncio n'annule jamais les tâches restantes en fin de test : une tâche laissée active (ex.
# enfant d'asyncio.gather() dont un frère a levé) reprendrait pendant le test asynchrone suivant,
# APRÈS son nettoyage.
# - observe (défaut) : DÉTECTER et SIGNALER ; aucune tâche n'est annulée, la boucle n'est jamais
#   exécutée (aucune tâche ne progresse) ; seuls des attributs de tâches et de cadres sont lus.
# - enforce (EDUSPHERE_TASK_GUARD=enforce) : en plus, les tâches apparues pendant le test sont
#   RÉGLÉES (edusphere_test_guard.settle_tasks : grâce, annulation, attente effective, seconde
#   annulation) AVANT le nettoyage « après » ; orpheline réglée → erreur du test (sauf marqueur
#   edusphere_expected_orphan) ; tâche toujours active → arrêt de session (code 3).
# Tâches internes légitimes : edusphere_test_guard.is_legitimate_internal_task (nom ET provenance).
_TASK_GUARD_MODE = _guard.task_guard_mode()
_TASK_FRAME_DEPTH = 12
_API_DIR = Path(__file__).resolve().parent
_TASK_REPORTS: list[dict[str, str]] = []
# Test d'origine de chaque tâche déjà signalée (références faibles : aucune tâche n'est retenue).
_TASK_ORIGIN: weakref.WeakKeyDictionary[asyncio.Task, str] = weakref.WeakKeyDictionary()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def _edusphere_session_loop() -> asyncio.AbstractEventLoop:
    """Référence à la boucle de session via l'API PUBLIQUE de pytest-asyncio (aucune fixture
    privée) : la boucle qui exécute cette fixture est celle des tests et fixtures asynchrones."""
    return asyncio.get_running_loop()


def _pending_tasks(loop: asyncio.AbstractEventLoop) -> set[asyncio.Task] | None:
    """Tâches non terminées de la boucle de session, ou None si l'observation est impossible.
    Appelée depuis une fixture SYNCHRONE : la boucle est alors à l'arrêt et aucune tâche n'est
    « courante » ; la tâche courante éventuelle est néanmoins exclue par prudence."""
    if loop.is_closed() or loop.is_running():
        return None
    current = asyncio.current_task(loop)
    return {task for task in asyncio.all_tasks(loop) if task is not current}


def _awaitable_frames(task: asyncio.Task) -> list[tuple[str, str, int]]:
    """Chaîne d'attente de la tâche, de la coroutine racine vers l'attente la plus interne :
    (nom qualifié, fichier, ligne). Lecture seule de cr_frame/cr_await et équivalents."""
    frames: list[tuple[str, str, int]] = []
    current: object = task.get_coro()
    while current is not None and len(frames) < _TASK_FRAME_DEPTH:
        frame = None
        following = None
        for frame_attr, await_attr in (
            ("cr_frame", "cr_await"),
            ("ag_frame", "ag_await"),
            ("gi_frame", "gi_yieldfrom"),
        ):
            if hasattr(current, frame_attr):
                frame = getattr(current, frame_attr)
                following = getattr(current, await_attr, None)
                break
        if frame is None:
            break
        name = getattr(current, "__qualname__", type(current).__name__)
        frames.append((name, frame.f_code.co_filename, frame.f_lineno))
        current = following
    return frames


def _is_project_file(filename: str) -> bool:
    try:
        relative = Path(filename).resolve().relative_to(_API_DIR)
    except (OSError, ValueError):
        return False
    return relative.parts[:1] in (("app",), ("tests",))


def _describe_task(task: asyncio.Task, nodeid: str, kind: str) -> dict[str, str]:
    coro = task.get_coro()
    frames = _awaitable_frames(task)

    def _where(entry: tuple[str, str, int] | None) -> str:
        return f"{entry[0]} ({entry[1]}:{entry[2]})" if entry else "indisponible"

    project = next((entry for entry in frames if _is_project_file(entry[1])), None)
    return {
        "test": nodeid,
        "kind": kind,
        "task": task.get_name(),
        "coroutine": getattr(coro, "__qualname__", type(coro).__name__),
        "root": _where(frames[0] if frames else None),
        "project": _where(project),
        "innermost": _where(frames[-1] if frames else None),
    }


def _observe_new_tasks(
    loop: asyncio.AbstractEventLoop, before: set[asyncio.Task] | None, nodeid: str
) -> set[asyncio.Task] | None:
    """Signale les tâches apparues pendant le test et les retourne (None : observation impossible).
    Lecture seule : aucune annulation, la boucle n'est pas exécutée."""
    after = _pending_tasks(loop)
    if before is None or after is None:
        _TASK_REPORTS.append(
            {"test": nodeid, "kind": "observation impossible (boucle fermée ou en cours)"}
        )
        return None
    # Seules les tâches APPARUES pendant le test lui sont attribuées ; celles déjà présentes avant
    # (orphelines d'un test précédent, déjà signalées) ne sont pas réattribuées.
    new_tasks = after - before
    for task in sorted(new_tasks, key=lambda t: t.get_name()):
        legitimate = _guard.is_legitimate_internal_task(task)
        kind = "légitime (transitoire)" if legitimate else "résiduelle"
        _TASK_ORIGIN[task] = nodeid
        _TASK_REPORTS.append(_describe_task(task, nodeid, kind))
    # Orphelines déjà signalées et toujours actives : même diagnostic que ci-dessus (tâche,
    # coroutine, emplacements), complété par leur test d'origine ; « test » = test où on les retrouve.
    for task in sorted(after & before, key=lambda t: t.get_name()):
        origin = _TASK_ORIGIN.get(task)
        if origin is not None:
            report = _describe_task(task, nodeid, "orpheline héritée toujours active")
            report["origin"] = origin
            _TASK_REPORTS.append(report)
    return new_tasks


def _blocked_task_summary(outcome: "_guard.TaskOutcome", nodeid: str) -> str:
    where = _describe_task(outcome.task, nodeid, outcome.status)
    return (
        f"{outcome.name} [{outcome.coroutine}] {outcome.status} ({outcome.detail}) — "
        f"projet : {where['project']} — attente : {where['innermost']}"
    )


def _settle_new_tasks(
    loop: asyncio.AbstractEventLoop,
    new_tasks: set[asyncio.Task],
    known: set[asyncio.Task],
    request: pytest.FixtureRequest,
) -> tuple[str | None, str | None]:
    """Mode enforce. Retourne (erreur du test, arrêt de session)."""
    nodeid = request.node.nodeid
    expected = request.node.get_closest_marker("edusphere_expected_orphan") is not None
    settlement = _guard.settle_tasks(
        loop, new_tasks, known, cancel_message=f"edusphere : tâche orpheline de {nodeid}"
    )
    for outcome in settlement.outcomes:
        attendue = expected and not outcome.legitimate
        _TASK_REPORTS.append(
            {
                "test": nodeid,
                "kind": "règlement (orpheline attendue)" if attendue else "règlement",
                "task": outcome.name,
                "coroutine": outcome.coroutine,
                "status": outcome.status,
                "detail": outcome.detail or "-",
                "cancels": str(outcome.cancel_requests),
            }
        )
    if settlement.blocked:
        blocked = "; ".join(_blocked_task_summary(o, nodeid) for o in settlement.blocked)
        return None, (
            f"tâche(s) asyncio toujours active(s) après annulation et délais ({nodeid}) : "
            f"{blocked}. LIMITE : à la fermeture de la session, pytest-asyncio exécute encore la "
            "boucle (shutdown_asyncgens) et ces tâches peuvent alors reprendre ; l'isolation N'EST "
            "PAS garantie pour cette session (la session suivante videra la base avant son premier "
            "test). Ne relancer aucun test dans ce processus."
        )
    if settlement.residual and not expected:
        residual = "; ".join(
            f"{o.name} [{o.coroutine}] {o.status}" + (f" — {o.detail}" if o.detail else "")
            for o in settlement.residual
        )
        return f"tâche(s) asyncio orpheline(s) réglée(s) après {nodeid} : {residual}", None
    return None, None


@pytest.fixture(autouse=True)
def _edusphere_test_isolation(
    request: pytest.FixtureRequest, _edusphere_session_loop: asyncio.AbstractEventLoop
):
    """Synchrone : identique pour les tests synchrones et asynchrones, quel que soit asyncio_mode.
    Le travail PostgreSQL s'exécute dans une boucle neuve sur un thread dédié, jamais sur la boucle
    de session des tests ; Redis et le cache D2 sont traités sans boucle. Ordre après le test :
    observation des tâches → règlement (enforce) → nettoyage « après » (TOUJOURS, même si le
    règlement échoue) → arrêt de session ou erreur du test selon le bilan. L'exception éventuelle
    du test lui-même reste rapportée par pytest (phase d'appel), distincte de cette phase."""
    nodeid = request.node.nodeid
    loop = _edusphere_session_loop
    _run_isolation("avant", nodeid)
    tasks_before = _pending_tasks(loop)
    if _TASK_GUARD_MODE == "enforce":
        if tasks_before is None:
            pytest.exit(f"tâches asyncio : observation impossible avant {nodeid}", returncode=3)
        if tasks_before:
            active = "; ".join(
                f"{t.get_name()} [{_guard.task_coroutine_origin(t)[0]}]" for t in tasks_before
            )
            pytest.exit(
                f"tâche(s) asyncio déjà active(s) au début de {nodeid} : {active}", returncode=3
            )
    yield
    failure: str | None = None
    stop: str | None = None
    try:
        new_tasks = _observe_new_tasks(loop, tasks_before, nodeid)
        if _TASK_GUARD_MODE == "enforce":
            if new_tasks is None:
                stop = f"tâches asyncio : observation impossible après {nodeid}"
            elif new_tasks:
                failure, stop = _settle_new_tasks(loop, new_tasks, tasks_before or set(), request)
    except _guard.EnvironmentRefused as exc:
        stop = f"règlement des tâches refusé ({nodeid}) : {exc}"
    except Exception as exc:
        stop = f"règlement des tâches impossible ({nodeid}) : {type(exc).__name__}: {exc}"
    finally:
        _run_isolation("après", nodeid)
    if stop is not None:
        pytest.exit(stop, returncode=3)
    if failure is not None:
        pytest.fail(failure, pytrace=False)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "edusphere_expected_orphan: le test laisse VOLONTAIREMENT une tâche asyncio orpheline "
        "(scénario de validation) ; en mode enforce elle est réglée sans erreur de test",
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    changed = _guard.dev_files_changed(_STATE)
    if changed:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        print(
            "\nGARDE-FOU : fichiers de développement modifiés pendant la session : "
            + ", ".join(changed),
            file=sys.stderr,
        )
    _guard.remove_own_isolation_root(_STATE)


def pytest_terminal_summary(terminalreporter: "TerminalReporter") -> None:
    """Rapport : n'affecte jamais le code de sortie (en enforce, les erreurs et arrêts sont produits
    par la fixture d'isolation, pas par ce rapport)."""
    if not _TASK_REPORTS:
        return
    residual = sum(1 for report in _TASK_REPORTS if report.get("kind") == "résiduelle")
    terminalreporter.section(f"EduSphere — tâches asyncio (mode {_TASK_GUARD_MODE})")
    terminalreporter.line(f"tâches résiduelles signalées : {residual}")
    for report in _TASK_REPORTS:
        terminalreporter.line(f"- [{report['kind']}] {report['test']}")
        keys = ("task", "coroutine", "status", "detail", "cancels", "root", "project", "innermost")
        for key in (*keys, "origin"):
            if key in report:
                terminalreporter.line(f"    {key:<10}: {report[key]}")
