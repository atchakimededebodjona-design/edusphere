"""Point d'entrée pytest de l'environnement de tests isolé (Phase 2).

Chargé par pytest AVANT apps/api/tests/conftest.py (conftests initiaux importés du parent vers
l'enfant), donc avant tout import de `app.*`. Toute la vérification a lieu ICI, à l'import : en cas
de refus, le chargement de ce fichier échoue et aucun test n'est collecté ni exécuté.
"""

import edusphere_test_guard as _guard  # première instruction : aucun import de app.* au-dessus

_STATE = _guard.preflight()

import sys  # noqa: E402

import pytest  # noqa: E402


def _run_isolation(phase: str, nodeid: str) -> None:
    try:
        _guard.isolate(_STATE, phase, nodeid)
    except _guard.EnvironmentRefused as exc:
        pytest.exit(f"Isolation interrompue ({phase} {nodeid}) : {exc}", returncode=3)


@pytest.fixture(autouse=True)
def _edusphere_test_isolation(request: pytest.FixtureRequest):
    """Synchrone : identique pour les tests synchrones et asynchrones, quel que soit asyncio_mode.
    Le travail PostgreSQL s'exécute dans une boucle neuve sur un thread dédié, jamais sur la boucle
    de session des tests ; Redis et le cache D2 sont traités sans boucle."""
    _run_isolation("avant", request.node.nodeid)
    yield
    _run_isolation("après", request.node.nodeid)


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
