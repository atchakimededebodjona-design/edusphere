"""Tests unitaires PURS du garde-fou de l'environnement de tests isolé (Phase 2).

Aucune base, aucun Redis, aucun import de `app.*` : exécutables sans conftest
(python -m pytest --noconftest tests/test_edusphere_test_guard.py), avant même que l'environnement
Docker de test existe. Les mots de passe ci-dessous sont fictifs.
"""

import builtins
import io
import os
import pathlib
import tempfile
import types

import pytest

import edusphere_test_guard as guard

pytest_plugins = ("pytester",)

PW = "S3cr3t-Fictif-Jamais-Affiche"
LOCAL_APP = f"postgresql+asyncpg://edusphere_app:{PW}@127.0.0.1:55432/edusphere_test"
LOCAL_CLEAN = f"postgresql+asyncpg://edusphere_test_cleaner:{PW}@127.0.0.1:55432/edusphere_test"
DOCKER_APP = f"postgresql+asyncpg://edusphere_app:{PW}@db-test:5432/edusphere_test"


def _refused(func, *args, **kwargs) -> str:
    with pytest.raises(guard.EnvironmentRefused) as excinfo:
        func(*args, **kwargs)
    message = str(excinfo.value)
    assert PW not in message
    return message


# --- URL PostgreSQL ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        (f"postgresql+asyncpg://edusphere_app:{PW}@127.0.0.1:55432/edusphere", "base"),
        (f"postgresql+asyncpg://edusphere_app:{PW}@127.0.0.1:55432/edusphere_test2", "base"),
        (f"postgresql+asyncpg://edusphere_app:{PW}@db:5432/edusphere_test", "destination"),
        (f"postgresql+asyncpg://edusphere_app:{PW}@localhost:5432/edusphere_test", "destination"),
        (f"postgresql+asyncpg://edusphere_app:{PW}@127.0.0.1:55433/edusphere_test", "destination"),
        (f"postgresql+asyncpg://edusphere_test_admin:{PW}@127.0.0.1:55432/edusphere_test", "rôle"),
    ],
)
def test_local_mode_refuses_non_test_postgres_targets(url: str, reason: str) -> None:
    target = guard.parse_pg_url(url, "APP_DATABASE_URL")
    message = _refused(guard.check_pg_target, target, "local", guard.APP_ROLE, "APP_DATABASE_URL")
    assert reason in message


@pytest.mark.parametrize(
    "url",
    [
        f"postgresql+asyncpg://edusphere_app:{PW}@db:5432/edusphere_test",
        f"postgresql+asyncpg://edusphere_app:{PW}@127.0.0.1:55432/edusphere_test",
        f"postgresql+asyncpg://edusphere_app:{PW}@db-test:5432/edusphere",
    ],
)
def test_docker_mode_refuses_dev_host_local_ports_and_dev_database(url: str) -> None:
    target = guard.parse_pg_url(url, "APP_DATABASE_URL")
    _refused(guard.check_pg_target, target, "docker", guard.APP_ROLE, "APP_DATABASE_URL")


def test_allowed_postgres_targets_are_accepted() -> None:
    for url, mode in (
        (LOCAL_APP, "local"),
        (LOCAL_APP.replace("127.0.0.1", "localhost"), "local"),
        (DOCKER_APP, "docker"),
    ):
        guard.check_pg_target(guard.parse_pg_url(url, "X"), mode, guard.APP_ROLE, "X")


@pytest.mark.parametrize(
    "url",
    [
        f"postgresql://edusphere_app:{PW}@127.0.0.1:55432/edusphere_test",
        "postgresql+asyncpg://edusphere_app@127.0.0.1:55432/edusphere_test",
        f"postgresql+asyncpg://edusphere_app:{PW}@127.0.0.1:55432/",
        f"postgresql+asyncpg://edusphere_app:{PW}@127.0.0.1/edusphere_test",
        "",
    ],
)
def test_parse_pg_url_refuses_other_schemes_and_incomplete_urls(url: str) -> None:
    _refused(guard.parse_pg_url, url, "APP_DATABASE_URL")


def test_pg_target_repr_never_contains_the_password() -> None:
    target = guard.parse_pg_url(LOCAL_APP, "APP_DATABASE_URL")
    assert PW not in repr(target)
    assert PW not in target.describe()


# --- Redis ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "mode"),
    [
        ("redis://redis:6379/0", "local"),
        ("redis://redis:6379/0", "docker"),
        ("redis://localhost:6379/0", "local"),
        ("redis://127.0.0.1:56379/1", "local"),
        ("redis://127.0.0.1:56379/0", "docker"),
        ("redis://redis-test:6379/0", "local"),
    ],
)
def test_redis_targets_refused(url: str, mode: str) -> None:
    host, port, db = guard.parse_redis_url(url)
    _refused(guard.check_redis_target, host, port, db, mode)


def test_redis_targets_accepted() -> None:
    for url, mode in (
        ("redis://127.0.0.1:56379/0", "local"),
        ("redis://localhost:56379/0", "local"),
        ("redis://redis-test:6379/0", "docker"),
    ):
        guard.check_redis_target(*guard.parse_redis_url(url), mode)


# --- Mode d'exécution ----------------------------------------------------------------------------


def test_resolve_mode(tmp_path: pathlib.Path) -> None:
    absent = tmp_path / "absent-dockerenv"
    present = tmp_path / ".dockerenv"
    present.touch()
    assert guard.resolve_mode({}, dockerenv=absent, platform="win32") == "local"
    assert guard.resolve_mode(
        {"EDUSPHERE_TEST_MODE": "local"}, dockerenv=absent, platform="win32"
    ) == "local"
    assert guard.resolve_mode(
        {"EDUSPHERE_TEST_MODE": "docker"}, dockerenv=present, platform="linux"
    ) == "docker"
    assert guard.resolve_mode(
        {"EDUSPHERE_TEST_MODE": "migrator"}, dockerenv=present, platform="linux"
    ) == "migrator"


@pytest.mark.parametrize(
    ("environ", "dockerenv_present", "platform"),
    [
        ({"EDUSPHERE_TEST_MODE": "docker"}, True, "win32"),
        ({"EDUSPHERE_TEST_MODE": "docker"}, False, "linux"),
        ({"EDUSPHERE_TEST_MODE": "migrator"}, False, "win32"),
        ({"EDUSPHERE_TEST_MODE": "production"}, False, "win32"),
        ({}, True, "linux"),
    ],
)
def test_resolve_mode_refusals(
    tmp_path: pathlib.Path, environ: dict, dockerenv_present: bool, platform: str
) -> None:
    dockerenv = tmp_path / ".dockerenv"
    if dockerenv_present:
        dockerenv.touch()
    _refused(guard.resolve_mode, environ, dockerenv=dockerenv, platform=platform)


# --- Fusion de .env.test (mode local) ------------------------------------------------------------


def _file_values(**overrides: str | None) -> dict[str, str]:
    values: dict[str, str | None] = {
        "EDUSPHERE_TEST_MODE": "local",
        "DATABASE_URL": LOCAL_APP,
        "APP_DATABASE_URL": LOCAL_APP,
        "TEST_CLEANUP_DATABASE_URL": LOCAL_CLEAN,
        "REDIS_URL": "redis://127.0.0.1:56379/0",
    }
    values.update(overrides)
    return {key: value for key, value in values.items() if value is not None}


def test_merge_local_env_applies_values_absent_from_the_process(tmp_path: pathlib.Path) -> None:
    result = guard.merge_local_env(_file_values(), {}, repo_root=tmp_path / "repo")
    assert set(result) == set(guard.RUNNER_REQUIRED_KEYS)


def test_merge_local_env_accepts_an_identical_preexisting_value(tmp_path: pathlib.Path) -> None:
    environ = {"APP_DATABASE_URL": LOCAL_APP}
    guard.merge_local_env(_file_values(), environ, repo_root=tmp_path / "repo")


def test_merge_local_env_refuses_a_conflicting_shell_value(tmp_path: pathlib.Path) -> None:
    stale = "postgresql+asyncpg://refus@127.0.0.1:5432/edusphere"
    message = _refused(
        guard.merge_local_env,
        _file_values(),
        {"APP_DATABASE_URL": stale},
        repo_root=tmp_path / "repo",
    )
    assert "APP_DATABASE_URL" in message
    assert stale not in message


@pytest.mark.parametrize(
    "overrides",
    [
        {"REDIS_URL": None},
        {"EDUSPHERE_TEST_MODE": "docker"},
        {"EDUSPHERE_TEST_PG_ADMIN_PASSWORD": PW},
    ],
)
def test_merge_local_env_refusals(tmp_path: pathlib.Path, overrides: dict) -> None:
    _refused(guard.merge_local_env, _file_values(**overrides), {}, repo_root=tmp_path / "repo")


def test_merge_local_env_refuses_an_admin_secret_inside_the_repository(
    tmp_path: pathlib.Path,
) -> None:
    repo = tmp_path / "repo"
    inside = str(repo / "apps" / "api" / "pg_admin_password")
    _refused(
        guard.merge_local_env,
        _file_values(EDUSPHERE_TEST_ADMIN_SECRET_FILE=inside),
        {},
        repo_root=repo,
    )


def test_local_configuration_never_opens_the_admin_secret_file(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = tmp_path / "outside" / "pg_admin_password"
    secret.parent.mkdir()
    secret.write_text("NE-DOIT-JAMAIS-ETRE-LU", encoding="ascii")
    env_file = tmp_path / ".env.test"
    lines = [f"{key}={value}" for key, value in _file_values().items()]
    lines.append(f'EDUSPHERE_TEST_ADMIN_SECRET_FILE="{secret.as_posix()}"')
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    opened: list[str] = []
    secret_abs = os.path.normcase(os.path.abspath(secret))

    def _record(path) -> None:
        if isinstance(path, (str, os.PathLike)):
            if os.path.normcase(os.path.abspath(os.fspath(path))) == secret_abs:
                opened.append(os.fspath(path))

    real_open = builtins.open
    real_read_text = pathlib.Path.read_text
    real_read_bytes = pathlib.Path.read_bytes

    def spy_open(file, *args, **kwargs):
        _record(file)
        return real_open(file, *args, **kwargs)

    def spy_read_text(self, *args, **kwargs):
        _record(self)
        return real_read_text(self, *args, **kwargs)

    def spy_read_bytes(self, *args, **kwargs):
        _record(self)
        return real_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(io, "open", spy_open)
    monkeypatch.setattr(pathlib.Path, "read_text", spy_read_text)
    monkeypatch.setattr(pathlib.Path, "read_bytes", spy_read_bytes)

    values = guard.read_env_test(env_file)
    guard.merge_local_env(values, {}, repo_root=tmp_path / "repo")

    assert values["EDUSPHERE_TEST_ADMIN_SECRET_FILE"] == secret.as_posix()
    assert opened == []


# --- Variables et réglages réservés --------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["PGPASSWORD", "POSTGRES_PASSWORD", "POSTGRES_PASSWORD_FILE", "PGPASSFILE", "X_ADMIN_PASSWORD"],
)
def test_forbidden_environment_names_are_refused(name: str) -> None:
    message = _refused(guard.check_forbidden_env_names, {name: PW})
    assert name in message


def test_clean_environment_is_accepted() -> None:
    guard.check_forbidden_env_names(
        {"PATH": "x", "EDUSPHERE_TEST_ADMIN_SECRET_FILE": "C:/hors-depot/pg_admin_password"}
    )


def test_guard_owned_settings_are_applied(tmp_path: pathlib.Path) -> None:
    environ: dict[str, str] = {}
    values = guard.compute_safety_settings(tmp_path)
    guard.apply_guard_owned(values, environ)
    assert environ == values
    assert environ["ENVIRONMENT"] == "test"
    assert pathlib.Path(environ["STORAGE_LOCAL_PATH"]).parent == tmp_path


@pytest.mark.parametrize(
    "environ",
    [{"STORAGE_LOCAL_PATH": "C:/ailleurs"}, {"ENVIRONMENT": "production"}, {"SMS_ENABLED": "true"}],
)
def test_guard_owned_settings_refuse_preexisting_incompatible_values(
    tmp_path: pathlib.Path, environ: dict
) -> None:
    _refused(guard.apply_guard_owned, guard.compute_safety_settings(tmp_path), environ)


def test_guard_owned_settings_accept_identical_values(tmp_path: pathlib.Path) -> None:
    environ = {"ENVIRONMENT": "test", "SMS_ENABLED": "False"}
    guard.apply_guard_owned(guard.compute_safety_settings(tmp_path), environ)


def test_isolation_root_outside_protected_tree() -> None:
    root = guard.make_isolation_root("local")
    try:
        assert root.is_dir()
        assert not guard._is_within(root, guard.REPO_ROOT)
    finally:
        root.rmdir()


def test_isolation_root_refused_inside_protected_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    # gettempdir() renvoie la forme courte 8.3 sous Windows, mkdtemp + resolve() la forme longue :
    # c'est exactement le cas réel du défaut corrigé dans _is_within.
    monkeypatch.setattr(guard, "protected_root", lambda mode: pathlib.Path(tempfile.gettempdir()))
    created: list[str] = []
    real_mkdtemp = tempfile.mkdtemp

    def recording_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created.append(path)
        return path

    monkeypatch.setattr(tempfile, "mkdtemp", recording_mkdtemp)
    try:
        _refused(guard.make_isolation_root, "local")
    finally:
        # Nettoyage limité aux SEULS dossiers créés par cet appel (jamais un dossier préexistant
        # ou appartenant à un autre processus), même si le refus attendu ne se produit pas.
        for path in created:
            if os.path.isdir(path):
                os.rmdir(path)
    assert created and not any(os.path.exists(path) for path in created)


def test_is_within_compares_canonical_paths(tmp_path: pathlib.Path) -> None:
    short_temp = tempfile.gettempdir()
    long_temp = pathlib.Path(short_temp).resolve()
    # Formes courte (8.3) et longue du même dossier, dans les deux sens, chemin inexistant compris.
    assert guard._is_within(long_temp / "inexistant" / "x", short_temp)
    assert guard._is_within(pathlib.Path(short_temp) / "inexistant", long_temp)
    assert guard._is_within(short_temp, long_temp)
    # Jonction (Windows) ou lien symbolique (POSIX) vers un dossier réel.
    real = tmp_path / "reel"
    real.mkdir()
    link = tmp_path / "lien"
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(real), str(link))
    else:
        link.symlink_to(real, target_is_directory=True)
    try:
        assert guard._is_within(link / "fichier", real)
        assert guard._is_within(real / "fichier", link)
        assert not guard._is_within(tmp_path / "autre", link)
    finally:
        if os.name == "nt":
            os.rmdir(link)  # supprime la jonction elle-même, jamais la cible
        else:
            link.unlink()
    # Un dossier voisin au nom préfixe n'est jamais considéré comme contenu.
    assert not guard._is_within(tmp_path / "reel-voisin", real)


# --- Fichiers de développement, imports, cache D2 ------------------------------------------------


def test_dev_files_snapshot_detects_changes(tmp_path: pathlib.Path) -> None:
    (tmp_path / "storage").mkdir()
    (tmp_path / "storage" / "a.txt").write_text("x", encoding="utf-8")
    watch = ("storage", "emails")
    before = guard.dev_files_snapshot(tmp_path, watch=watch, include_git=False)
    unchanged = guard.dev_files_snapshot(tmp_path, watch=watch, include_git=False)
    assert guard.diff_snapshots(before, unchanged) == []
    (tmp_path / "emails").mkdir()
    after = guard.dev_files_snapshot(tmp_path, watch=watch, include_git=False)
    assert guard.diff_snapshots(before, after) == ["emails"]


def test_app_already_imported_detection() -> None:
    assert guard.app_already_imported({"pytest": object()}) is False
    assert guard.app_already_imported({"apple": object()}) is False
    assert guard.app_already_imported({"app": object()}) is True
    assert guard.app_already_imported({"app.core.config": object()}) is True


def test_reset_suite_caches() -> None:
    module = types.SimpleNamespace(_PLATFORM_ADMIN_EMAIL="admin@example.tg")
    guard.reset_suite_caches({"tests.conftest": module})
    assert module._PLATFORM_ADMIN_EMAIL is None
    guard.reset_suite_caches({})
    _refused(guard.reset_suite_caches, {"tests.conftest": types.SimpleNamespace()})


def test_safe_error_redacts_secrets() -> None:
    message = guard._safe_error(RuntimeError(f"échec avec {PW}"), [PW])
    assert PW not in message
    assert "***" in message


# --- Validation du schéma ------------------------------------------------------------------------

_ORM = frozenset({"roles", "permissions", "role_permissions", "users", "schools"})
_ROLES = ("SUPER_ADMIN", "TEACHER")


def _report(**overrides) -> guard.SchemaReport:
    values = dict(
        public_tables=(
            "_bootstrap_check",
            "alembic_version",
            "permissions",
            "role_permissions",
            "roles",
            "schools",
            "users",
        ),
        other_schema_tables=(),
        alembic_version="0026",
        role_codes=frozenset(_ROLES),
        permission_count=10,
        truncate_privileges={
            "users": True,
            "schools": True,
            "roles": False,
            "permissions": False,
            "role_permissions": False,
            "alembic_version": False,
            "_bootstrap_check": False,
        },
        foreign_keys=(("schools", "users"), ("role_permissions", "roles")),
        owned_sequences=(("_bootstrap_check_id_seq", "_bootstrap_check"),),
    )
    values.update(overrides)
    return guard.SchemaReport(**values)


def test_evaluate_schema_returns_the_sorted_cleanup_set() -> None:
    assert guard.evaluate_schema(_report(), _ORM, "0026", _ROLES) == ("schools", "users")


@pytest.mark.parametrize(
    "overrides",
    [
        {"public_tables": _report().public_tables + ("inconnue",)},
        {"public_tables": tuple(t for t in _report().public_tables if t != "schools")},
        {"alembic_version": "0025"},
        {"role_codes": frozenset({"SUPER_ADMIN"})},
        {"permission_count": 0},
        {"truncate_privileges": {**_report().truncate_privileges, "users": False}},
        {"truncate_privileges": {**_report().truncate_privileges, "roles": True}},
        {"foreign_keys": (("roles", "users"),)},
        {"owned_sequences": (("users_id_seq", "users"),)},
        {"other_schema_tables": ("audit.events",)},
    ],
)
def test_evaluate_schema_refusals(overrides: dict) -> None:
    _refused(guard.evaluate_schema, _report(**overrides), _ORM, "0026", _ROLES)


# --- Comportement de pytest utilisé par apps/api/conftest.py -------------------------------------


def test_pytest_honours_an_exitstatus_set_in_sessionfinish(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(
        "import pytest\n\n\n"
        "def pytest_sessionfinish(session, exitstatus):\n"
        "    session.exitstatus = pytest.ExitCode.TESTS_FAILED\n"
    )
    pytester.makepyfile("def test_ok():\n    assert True\n")
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    assert result.ret == pytest.ExitCode.TESTS_FAILED
