"""Garde-fou de l'environnement de tests isolé EduLinkage (Phase 2).

Importé en tout premier par apps/api/conftest.py, AVANT tout import de `app.*` : ce module
n'importe rien de l'application au niveau du module. Trois modes, toujours déclarés, jamais devinés :

- « local »    : pytest lancé sous Windows ; configuration lue dans apps/api/.env.test uniquement ;
- « docker »   : pytest lancé dans api-test ; variables injectées par docker-compose.test.yml ;
- « migrator » : opérations d'administration dans migrator-test (migrate, grant-cleanup) ;
                 pytest y est refusé.

Tout refus lève EnvironmentRefused avec un message qui nomme le contrôle et, au plus,
hôte/port/base/rôle — jamais un mot de passe.

Usage hors pytest : python -m edusphere_test_guard {check|migrate|grant-cleanup}
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Coroutine, Iterable, Mapping, MutableMapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

TEST_DB = "edusphere_test"
SENTINEL = "edusphere-test-sentinel-v1"
REDIS_MARKER_DB = 15
REDIS_MARKER_KEY = "edusphere:test_marker"

ADMIN_ROLE = "edusphere_test_admin"
APP_ROLE = "edusphere_app"
CLEANER_ROLE = "edusphere_test_cleaner"

ADMIN_SECRET_PATH = Path("/run/secrets/pg_admin_password")
DOCKERENV_PATH = Path("/.dockerenv")

ALLOWED_PG: dict[str, frozenset[tuple[str, int]]] = {
    "local": frozenset({("127.0.0.1", 55432), ("localhost", 55432)}),
    "docker": frozenset({("db-test", 5432)}),
    "migrator": frozenset({("db-test", 5432)}),
}
ALLOWED_REDIS: dict[str, frozenset[tuple[str, int]]] = {
    "local": frozenset({("127.0.0.1", 56379), ("localhost", 56379)}),
    "docker": frozenset({("redis-test", 6379)}),
}

# Tables jamais vidées : technique Alembic, données de référence RBAC (seedées par les migrations),
# table de vérification de la migration 0001 (seule table à séquence du schéma).
EXCLUDED_TABLES = (
    "alembic_version",
    "roles",
    "permissions",
    "role_permissions",
    "_bootstrap_check",
)
TECHNICAL_TABLES = ("alembic_version", "_bootstrap_check")
FINGERPRINT_TABLES = (
    ("alembic_version", "version_num"),
    ("roles", "id"),
    ("permissions", "id"),
    ("role_permissions", "role_id, permission_id"),
)

RUNNER_REQUIRED_KEYS = (
    "EDUSPHERE_TEST_MODE",
    "DATABASE_URL",
    "APP_DATABASE_URL",
    "TEST_CLEANUP_DATABASE_URL",
    "REDIS_URL",
)
FORBIDDEN_ENV_NAMES = frozenset(
    {"POSTGRES_PASSWORD", "POSTGRES_PASSWORD_FILE", "PGPASSWORD", "PGPASSFILE"}
)
SAFETY_VALUES = {
    "ENVIRONMENT": "test",
    "EMAIL_PROVIDER": "local",
    "SMS_ENABLED": "false",
    "SMS_PROVIDER": "local",
    "STORAGE_PROVIDER": "local",
}
PATH_SETTINGS = {
    "STORAGE_LOCAL_PATH": "storage",
    "EMAIL_LOCAL_PATH": "emails",
    "SMS_LOCAL_PATH": "sms",
}
DEV_WATCH_PATHS = (
    "apps/api/storage",
    "apps/api/emails",
    "apps/api/sms",
    "storage",
    "emails",
    "sms",
)
SUITE_CONFTEST_MODULE = "tests.conftest"
SUITE_CACHE_ATTRIBUTES = ("_PLATFORM_ADMIN_EMAIL",)

API_DIR = Path(__file__).resolve().parent
REPO_ROOT = API_DIR.parent.parent
ENV_TEST_PATH = API_DIR / ".env.test"

IDENTITY_SQL = (
    "SELECT current_database() AS db, current_setting('app.test_marker', true) AS marker, "
    "current_user AS usr"
)
PUBLIC_TABLES_SQL = "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
DISCOVER_SQL = (
    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
    "AND NOT (tablename = ANY($1::text[]))"
)
OTHER_SCHEMAS_SQL = (
    "SELECT schemaname, tablename FROM pg_tables "
    "WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'public')"
)
# Tables du schéma public désignées par OID (mêmes relkind que pg_tables : 'r' et 'p') : jamais de
# résolution par nom dans has_table_privilege(), dont l'ordre d'évaluation dans un WHERE n'est pas
# garanti (une table système pourrait sinon être résolue comme « public.<nom> » et lever une erreur).
PUBLIC_TABLE_OIDS_FROM = (
    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')"
)
TRUNCATE_PRIVILEGES_SQL = (
    "SELECT c.relname AS tablename, has_table_privilege(current_user, c.oid, 'TRUNCATE') "
    "AS can_truncate " + PUBLIC_TABLE_OIDS_FROM
)
FOREIGN_KEYS_SQL = (
    "SELECT src.relname AS src, dst.relname AS dst FROM pg_constraint c "
    "JOIN pg_class src ON src.oid = c.conrelid JOIN pg_class dst ON dst.oid = c.confrelid "
    "JOIN pg_namespace n ON n.oid = src.relnamespace "
    "WHERE c.contype = 'f' AND n.nspname = 'public'"
)
OWNED_SEQUENCES_SQL = (
    "SELECT s.relname AS seq, t.relname AS tbl FROM pg_class s "
    "JOIN pg_depend d ON d.objid = s.oid AND d.deptype IN ('a', 'i') "
    "JOIN pg_class t ON t.oid = d.refobjid JOIN pg_namespace n ON n.oid = t.relnamespace "
    "WHERE s.relkind = 'S' AND n.nspname = 'public'"
)

# Journal des passages d'isolation (consulté par tests/test_edusphere_test_isolation.py).
ISOLATION_LOG: list[dict[str, str]] = []


class EnvironmentRefused(RuntimeError):
    """Refus du garde-fou. Le message ne contient jamais de secret."""


def _refuse(message: str) -> EnvironmentRefused:
    return EnvironmentRefused(message)


# --- Cibles de connexion -------------------------------------------------------------------------


@dataclass(frozen=True)
class PgTarget:
    host: str
    port: int
    database: str
    username: str
    password: str = field(repr=False)

    def describe(self) -> str:
        return f"{self.username}@{self.host}:{self.port}/{self.database}"


def parse_pg_url(url: str | None, label: str) -> PgTarget:
    if not url:
        raise _refuse(f"{label} absent")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise _refuse(f"{label} : URL illisible") from None
    if parts.scheme != "postgresql+asyncpg":
        raise _refuse(f"{label} : schéma « {parts.scheme} » refusé (postgresql+asyncpg attendu)")
    database = parts.path.lstrip("/")
    if not (parts.hostname and port and parts.username and parts.password and database):
        raise _refuse(f"{label} : hôte, port, rôle, mot de passe et base sont obligatoires")
    return PgTarget(
        parts.hostname, port, database, unquote(parts.username), unquote(parts.password)
    )


def check_pg_target(target: PgTarget, mode: str, expected_role: str, label: str) -> None:
    if target.database != TEST_DB:
        raise _refuse(
            f"{label} : base « {target.database} » refusée — seule « {TEST_DB} » est autorisée"
        )
    if (target.host, target.port) not in ALLOWED_PG[mode]:
        raise _refuse(
            f"{label} : destination {target.host}:{target.port} non autorisée en mode {mode}"
        )
    if target.username != expected_role:
        raise _refuse(
            f"{label} : rôle « {target.username} » refusé — « {expected_role} » attendu"
        )


def parse_redis_url(url: str | None, label: str = "REDIS_URL") -> tuple[str, int, int]:
    if not url:
        raise _refuse(f"{label} absent")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise _refuse(f"{label} : URL illisible") from None
    if parts.scheme != "redis":
        raise _refuse(f"{label} : schéma « {parts.scheme} » refusé (redis attendu)")
    db_text = parts.path.lstrip("/") or "0"
    if not (parts.hostname and port and db_text.isdigit()):
        raise _refuse(f"{label} : hôte, port et numéro de base sont obligatoires")
    return parts.hostname, port, int(db_text)


def check_redis_target(host: str, port: int, db: int, mode: str) -> None:
    if (host, port) not in ALLOWED_REDIS.get(mode, frozenset()):
        raise _refuse(f"REDIS_URL : destination {host}:{port} non autorisée en mode {mode}")
    if db != 0:
        raise _refuse(f"REDIS_URL : base Redis {db} refusée — seule la base 0 est utilisée")


# --- Mode et configuration -----------------------------------------------------------------------


def resolve_mode(
    environ: Mapping[str, str] | None = None,
    *,
    dockerenv: Path = DOCKERENV_PATH,
    platform: str | None = None,
) -> str:
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    declared = environ.get("EDUSPHERE_TEST_MODE")
    in_container = dockerenv.exists()
    if declared in ("docker", "migrator"):
        if platform != "linux" or not in_container:
            raise _refuse(f"mode « {declared} » déclaré hors d'un conteneur Linux")
        return declared
    if declared not in (None, "local"):
        raise _refuse(f"EDUSPHERE_TEST_MODE : valeur « {declared} » inconnue")
    if in_container:
        raise _refuse("mode local détecté dans un conteneur : configuration ambiguë")
    return "local"


def protected_root(mode: str) -> Path:
    """Arborescence qui ne doit jamais recevoir d'écriture : le dépôt (local) ou /app (conteneur)."""
    return REPO_ROOT if mode == "local" else API_DIR


def _is_within(child: str | Path, parent: str | Path) -> bool:
    """Confinement sur chemins CANONIQUES : realpath résout les noms courts Windows 8.3, les
    jonctions et les liens symboliques (y compris pour la partie existante d'un chemin inexistant),
    à partir des seules métadonnées — aucun contenu de fichier n'est lu. abspath ne le fait pas."""
    child_path = Path(os.path.normcase(os.path.realpath(child)))
    parent_path = Path(os.path.normcase(os.path.realpath(parent)))
    return child_path == parent_path or child_path.is_relative_to(parent_path)


def read_env_test(path: Path = ENV_TEST_PATH) -> dict[str, str]:
    if not path.is_file():
        raise _refuse("apps/api/.env.test absent — aucun repli sur .env (mode local)")
    from dotenv import dotenv_values

    values = dotenv_values(path, interpolate=False)
    return {key: value for key, value in values.items() if value is not None}


def merge_local_env(
    file_values: Mapping[str, str],
    environ: Mapping[str, str],
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, str]:
    """Valeurs de .env.test à appliquer. Refus en cas de conflit avec une variable déjà présente
    dans le processus (ni override=True, ni override=False). Le fichier secret administrateur
    n'est jamais ouvert : seul son chemin est contrôlé."""
    if file_values.get("EDUSPHERE_TEST_MODE") != "local":
        raise _refuse("apps/api/.env.test doit déclarer EDUSPHERE_TEST_MODE=local")
    admin_keys = sorted(key for key in file_values if "ADMIN_PASSWORD" in key.upper())
    if admin_keys:
        raise _refuse(
            "apps/api/.env.test contient une clé de mot de passe administrateur : "
            + ", ".join(admin_keys)
        )
    secret_path = file_values.get("EDUSPHERE_TEST_ADMIN_SECRET_FILE")
    if secret_path and _is_within(secret_path, repo_root):
        raise _refuse("le fichier secret administrateur doit se trouver HORS du dépôt")
    to_apply: dict[str, str] = {}
    for key in RUNNER_REQUIRED_KEYS:
        value = file_values.get(key)
        if not value:
            raise _refuse(f"{key} absent de apps/api/.env.test")
        current = environ.get(key)
        if current is not None and current != value:
            raise _refuse(
                f"{key} est déjà défini dans l'environnement du processus avec une valeur "
                "différente de apps/api/.env.test — configuration ambiguë, retirer cette "
                "variable du shell"
            )
        to_apply[key] = value
    return to_apply


def check_forbidden_env_names(environ: Mapping[str, str]) -> None:
    present = sorted(
        name
        for name in environ
        if name.upper() in FORBIDDEN_ENV_NAMES or "ADMIN_PASSWORD" in name.upper()
    )
    if present:
        raise _refuse(
            "variables interdites dans un contexte d'exécution des tests : " + ", ".join(present)
        )


def compute_safety_settings(root: Path) -> dict[str, str]:
    values = dict(SAFETY_VALUES)
    for key, subdirectory in PATH_SETTINGS.items():
        values[key] = str(root / subdirectory)
    return values


def apply_guard_owned(values: Mapping[str, str], environ: MutableMapping[str, str]) -> None:
    for key, value in values.items():
        current = environ.get(key)
        if current is None:
            continue
        if key in PATH_SETTINGS:
            raise _refuse(f"{key} est réservé au garde-fou : ne pas le définir")
        if current.strip().lower() != value.lower():
            raise _refuse(f"{key} déjà défini avec une valeur incompatible avec les tests")
    environ.update(values)


def make_isolation_root(mode: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix="edusphere-test-")).resolve()
    if _is_within(root, protected_root(mode)):
        shutil.rmtree(root, ignore_errors=True)
        raise _refuse("le répertoire temporaire de session se trouve dans le code ou le dépôt")
    return root


def app_already_imported(modules: Mapping[str, Any] | None = None) -> bool:
    modules = sys.modules if modules is None else modules
    return any(name == "app" or name.startswith("app.") for name in modules)


# --- Fichiers de développement (mode local : détection, le système n'impose rien) ---------------


def dev_files_snapshot(
    repo_root: Path,
    watch: Iterable[str] = DEV_WATCH_PATHS,
    include_git: bool = True,
) -> dict[str, Any]:
    """Métadonnées uniquement (chemin, type, taille, date) — aucun contenu n'est lu."""
    paths: dict[str, Any] = {}
    for relative in watch:
        base = repo_root / relative
        if not base.exists():
            paths[relative] = None
            continue
        items = []
        for item in sorted(base.rglob("*")):
            info = item.stat()
            is_dir = item.is_dir()
            items.append(
                (
                    item.relative_to(repo_root).as_posix(),
                    is_dir,
                    0 if is_dir else info.st_size,
                    info.st_mtime_ns,
                )
            )
        paths[relative] = tuple(items)
    git_status = None
    if include_git:
        try:
            done = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            git_status = done.stdout if done.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            git_status = None
    return {"paths": paths, "git": git_status}


def diff_snapshots(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    changed = [
        relative
        for relative, value in before["paths"].items()
        if value != after["paths"].get(relative)
    ]
    if before.get("git") is not None and after.get("git") is not None:
        if before["git"] != after["git"]:
            changed.append("git status")
    return changed


# --- Exécution asynchrone isolée -----------------------------------------------------------------


class _IsolatedLoopWorker:
    """Chaque coroutine s'exécute dans une boucle NEUVE (asyncio.run), sur un thread dédié —
    jamais sur la boucle de session utilisée par les tests et par AsyncSessionLocal."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="edusphere-test-isolation"
        )

    def run(self, factory: Callable[..., Coroutine[Any, Any, Any]], *args: Any) -> Any:
        return self._executor.submit(lambda: asyncio.run(factory(*args))).result()


WORKER = _IsolatedLoopWorker()


def _safe_error(exc: BaseException, secrets: Iterable[str] = ()) -> str:
    message = f"{type(exc).__name__}: {exc}"
    for secret in secrets:
        if secret:
            message = message.replace(secret, "***")
    return message


def _sanitized_db_error(exc: BaseException) -> str:
    """Type et SQLSTATE seulement : str(exc) de SQLAlchemy inclut le texte SQL ([SQL: …]), qui
    peut contenir un mot de passe (migration 0002, ALTER ROLE)."""
    sqlstate = None
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        sqlstate = sqlstate or getattr(current, "sqlstate", None)
        sqlstate = sqlstate or getattr(getattr(current, "orig", None), "sqlstate", None)
        current = current.__cause__ or current.__context__
    return type(exc).__name__ + (f" (SQLSTATE {sqlstate})" if sqlstate else "")


def _quote_table(name: str) -> str:
    return 'public."' + name.replace('"', '""') + '"'


async def _connect(target: PgTarget) -> Any:
    import asyncpg

    try:
        return await asyncpg.connect(
            host=target.host,
            port=target.port,
            user=target.username,
            password=target.password,
            database=target.database,
            timeout=10,
            server_settings={"application_name": "edusphere-test-guard"},
        )
    except Exception as exc:
        raise _refuse(
            f"connexion impossible à {target.describe()} — {_safe_error(exc, [target.password])}"
        ) from None


async def _pg_identity(target: PgTarget) -> tuple[str, str | None, str]:
    conn = await _connect(target)
    try:
        row = await conn.fetchrow(IDENTITY_SQL)
    finally:
        await conn.close()
    return row["db"], row["marker"], row["usr"]


def verify_identity(target: PgTarget, expected_role: str) -> None:
    database, marker, user = WORKER.run(_pg_identity, target)
    if database != TEST_DB:
        raise _refuse(f"{target.describe()} : current_database() = « {database} »")
    if marker != SENTINEL:
        raise _refuse(f"{target.describe()} : marqueur app.test_marker absent ou incorrect")
    if user != expected_role:
        raise _refuse(f"{target.describe()} : current_user = « {user} »")


# --- Schéma, privilèges et empreinte -------------------------------------------------------------


@dataclass(frozen=True)
class SchemaReport:
    public_tables: tuple[str, ...]
    other_schema_tables: tuple[str, ...]
    alembic_version: str | None
    role_codes: frozenset[str]
    permission_count: int
    truncate_privileges: Mapping[str, bool]
    foreign_keys: tuple[tuple[str, str], ...]
    owned_sequences: tuple[tuple[str, str], ...]


async def _fingerprint(conn: Any) -> tuple[tuple[str, int, str], ...]:
    rows = []
    for table, order in FINGERPRINT_TABLES:
        row = await conn.fetchrow(
            f"SELECT count(*) AS n, md5(coalesce(string_agg(t::text, '|' ORDER BY {order}), "
            f"'')) AS h FROM {_quote_table(table)} t"
        )
        rows.append((table, int(row["n"]), row["h"]))
    return tuple(rows)


async def _pg_schema_report(target: PgTarget) -> tuple[SchemaReport, tuple[Any, ...]]:
    conn = await _connect(target)
    try:
        public = tuple(sorted(r["tablename"] for r in await conn.fetch(PUBLIC_TABLES_SQL)))
        others = tuple(
            sorted(f"{r['schemaname']}.{r['tablename']}" for r in await conn.fetch(OTHER_SCHEMAS_SQL))
        )
        version = None
        role_codes: frozenset[str] = frozenset()
        permission_count = 0
        if "alembic_version" in public:
            version = await conn.fetchval("SELECT version_num FROM public.alembic_version")
        if "roles" in public:
            role_codes = frozenset(r["code"] for r in await conn.fetch("SELECT code FROM public.roles"))
        if "permissions" in public:
            permission_count = int(await conn.fetchval("SELECT count(*) FROM public.permissions"))
        privileges = {
            r["tablename"]: bool(r["can_truncate"]) for r in await conn.fetch(TRUNCATE_PRIVILEGES_SQL)
        }
        foreign_keys = tuple((r["src"], r["dst"]) for r in await conn.fetch(FOREIGN_KEYS_SQL))
        sequences = tuple((r["seq"], r["tbl"]) for r in await conn.fetch(OWNED_SEQUENCES_SQL))
        fingerprint = await _fingerprint(conn)
    except EnvironmentRefused:
        raise
    except Exception as exc:
        raise _refuse(
            f"lecture du schéma impossible avec {target.describe()} — {_safe_error(exc)} "
            "(migrations ou grant-cleanup non appliqués ?)"
        ) from None
    finally:
        await conn.close()
    report = SchemaReport(
        public, others, version, role_codes, permission_count, privileges, foreign_keys, sequences
    )
    return report, fingerprint


def evaluate_schema(
    report: SchemaReport,
    orm_tables: Iterable[str],
    head: str,
    required_roles: Iterable[str],
) -> tuple[str, ...]:
    """Valide le schéma et retourne l'ensemble (trié) des tables à vider."""
    public = set(report.public_tables)
    if report.other_schema_tables:
        raise _refuse(
            "tables hors du schéma public : " + ", ".join(report.other_schema_tables)
        )
    expected = set(orm_tables) | set(TECHNICAL_TABLES)
    unknown, missing = sorted(public - expected), sorted(expected - public)
    if unknown or missing:
        raise _refuse(
            "schéma et modèles ORM divergents — inconnues : "
            f"{', '.join(unknown) or 'aucune'} ; manquantes : {', '.join(missing) or 'aucune'}"
        )
    if report.alembic_version != head:
        raise _refuse(
            f"révision Alembic « {report.alembic_version} » ≠ tête « {head} » : lancer migrate"
        )
    missing_roles = sorted(set(required_roles) - set(report.role_codes))
    if missing_roles:
        raise _refuse("rôles RBAC absents : " + ", ".join(missing_roles))
    if report.permission_count <= 0:
        raise _refuse("aucune permission RBAC en base")
    cleanup = tuple(sorted(public - set(EXCLUDED_TABLES)))
    without = [t for t in cleanup if not report.truncate_privileges.get(t)]
    if without:
        raise _refuse(
            "privilège TRUNCATE manquant pour le rôle de nettoyage (relancer grant-cleanup) : "
            + ", ".join(without)
        )
    excluded_truncatable = [
        t for t in EXCLUDED_TABLES if t in public and report.truncate_privileges.get(t)
    ]
    if excluded_truncatable:
        raise _refuse(
            "le rôle de nettoyage peut vider une table exclue : " + ", ".join(excluded_truncatable)
        )
    dangerous_fk = sorted(
        f"{src}→{dst}"
        for src, dst in report.foreign_keys
        if src in EXCLUDED_TABLES and dst not in EXCLUDED_TABLES
    )
    if dangerous_fk:
        raise _refuse(
            "une table exclue référence une table vidée (CASCADE la viderait) : "
            + ", ".join(dangerous_fk)
        )
    sequences = sorted(f"{seq} ({table})" for seq, table in report.owned_sequences if table in cleanup)
    if sequences:
        raise _refuse(
            "séquences possédées par des tables vidées (RESTART IDENTITY) : " + ", ".join(sequences)
        )
    return cleanup


def orm_tables() -> frozenset[str]:
    from app.db import model_registry  # noqa: F401
    from app.db.base import Base

    return frozenset(table.name for table in Base.metadata.tables.values())


def alembic_head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise _refuse(f"chaîne Alembic : {len(heads)} têtes (une seule attendue)")
    return heads[0]


def connect_redis(host: str, port: int) -> tuple[Any, Any]:
    import redis

    data = redis.Redis(host=host, port=port, db=0, socket_connect_timeout=5, socket_timeout=10)
    marker = redis.Redis(
        host=host,
        port=port,
        db=REDIS_MARKER_DB,
        socket_connect_timeout=5,
        socket_timeout=10,
        decode_responses=True,
    )
    try:
        data.ping()
        value = marker.get(REDIS_MARKER_KEY)
    except Exception as exc:
        raise _refuse(f"Redis {host}:{port} injoignable — {_safe_error(exc)}") from None
    if value != SENTINEL:
        raise _refuse(
            f"Redis {host}:{port} : marqueur {REDIS_MARKER_KEY} (base {REDIS_MARKER_DB}) "
            "absent ou incorrect"
        )
    return data, marker


# --- Vérification préalable (import de apps/api/conftest.py) -------------------------------------


@dataclass
class GuardState:
    mode: str
    root: Path
    app_target: PgTarget
    cleanup_target: PgTarget
    redis_endpoint: tuple[str, int]
    redis_data: Any
    redis_marker: Any
    cleanup_tables: tuple[str, ...]
    fingerprint: tuple[tuple[str, int, str], ...]
    alembic_head: str
    dev_snapshot: dict[str, Any] | None


_STATE: GuardState | None = None


def current_state() -> GuardState:
    if _STATE is None:
        raise _refuse("vérification préalable non effectuée")
    return _STATE


def check_settings(settings: Any, root: Path) -> None:
    expected = {
        "environment": "test",
        "email_provider": "local",
        "sms_provider": "local",
        "storage_provider": "local",
    }
    for attribute, value in expected.items():
        if str(getattr(settings, attribute)).lower() != value:
            raise _refuse(f"settings.{attribute} différent de « {value} »")
    if settings.sms_enabled is not False:
        raise _refuse("settings.sms_enabled doit être faux")
    for attribute in ("storage_local_path", "email_local_path", "sms_local_path"):
        path = Path(getattr(settings, attribute))
        if not path.is_absolute() or not _is_within(path, root):
            raise _refuse(f"settings.{attribute} hors du répertoire temporaire de session")


def check_provider_objects(root: Path) -> None:
    """Contrôle les singletons RÉELLEMENT utilisés (créés à l'import, mkdir immédiat)."""
    from app.core import email as email_module
    from app.core import sms as sms_module
    from app.core import storage as storage_module

    providers = (
        ("stockage", storage_module.storage, storage_module.LocalStorageProvider),
        ("email", email_module.email_provider, email_module.LocalEmailProvider),
        ("sms", sms_module.sms_provider, sms_module.LocalSmsProvider),
    )
    for label, provider, expected_type in providers:
        if type(provider) is not expected_type:
            raise _refuse(f"fournisseur {label} non local")
        base = Path(getattr(provider, "_base_path")).resolve()
        if not _is_within(base, root):
            raise _refuse(f"fournisseur {label} hors du répertoire temporaire de session")


def preflight() -> GuardState:
    """Séquence complète, AVANT toute collecte de tests. Tout échec lève EnvironmentRefused."""
    global _STATE
    if _STATE is not None:
        return _STATE

    mode = resolve_mode()
    if mode == "migrator":
        raise _refuse("pytest est interdit dans migrator-test")
    if ADMIN_SECRET_PATH.exists():
        raise _refuse("secret administrateur monté dans un contexte d'exécution des tests")
    check_forbidden_env_names(os.environ)
    if (Path.cwd() / ".env").exists():
        raise _refuse(
            "un fichier .env existe dans le répertoire courant (il serait lu par la configuration) "
            "— lancer pytest depuis apps/api"
        )
    if mode == "local":
        os.environ.update(merge_local_env(read_env_test(), os.environ))
    else:
        missing = [key for key in RUNNER_REQUIRED_KEYS if not os.environ.get(key)]
        if missing:
            raise _refuse(
                "variables non injectées par docker-compose.test.yml : " + ", ".join(missing)
            )

    root = make_isolation_root(mode)
    try:
        apply_guard_owned(compute_safety_settings(root), os.environ)
        snapshot = dev_files_snapshot(REPO_ROOT) if mode == "local" else None
        if app_already_imported():
            raise _refuse("app.* importé avant le garde-fou : ordre de chargement violé")

        from app.core.config import settings

        app_target = parse_pg_url(settings.app_database_url, "APP_DATABASE_URL")
        check_pg_target(app_target, mode, APP_ROLE, "APP_DATABASE_URL")
        if parse_pg_url(settings.database_url, "DATABASE_URL") != app_target:
            raise _refuse(
                "DATABASE_URL doit être identique à APP_DATABASE_URL (rôle applicatif) : aucun "
                "identifiant administrateur dans un contexte de tests"
            )
        cleanup_target = parse_pg_url(
            os.environ.get("TEST_CLEANUP_DATABASE_URL"), "TEST_CLEANUP_DATABASE_URL"
        )
        check_pg_target(cleanup_target, mode, CLEANER_ROLE, "TEST_CLEANUP_DATABASE_URL")
        if (cleanup_target.host, cleanup_target.port) != (app_target.host, app_target.port):
            raise _refuse("TEST_CLEANUP_DATABASE_URL et APP_DATABASE_URL visent deux serveurs")
        redis_host, redis_port, redis_db = parse_redis_url(settings.redis_url)
        check_redis_target(redis_host, redis_port, redis_db, mode)
        check_settings(settings, root)
        check_provider_objects(root)

        from app.db import session as db_session

        url = db_session.engine.url
        engine_parts = (url.host, url.port, url.database, url.username, url.password)
        expected_parts = (
            app_target.host,
            app_target.port,
            app_target.database,
            app_target.username,
            app_target.password,
        )
        if engine_parts != expected_parts:
            raise _refuse("le moteur SQLAlchemy n'utilise pas l'APP_DATABASE_URL validée")

        from app.core import rate_limit

        kwargs = rate_limit._get_client().connection_pool.connection_kwargs
        if (kwargs.get("host"), kwargs.get("port"), kwargs.get("db", 0)) != (
            redis_host,
            redis_port,
            redis_db,
        ):
            raise _refuse("le client Redis de l'application n'utilise pas la REDIS_URL validée")

        verify_identity(app_target, APP_ROLE)
        verify_identity(cleanup_target, CLEANER_ROLE)
        report, fingerprint = WORKER.run(_pg_schema_report, cleanup_target)
        from app.modules.rbac.models import ALL_ROLE_CODES

        head = alembic_head()
        cleanup_tables = evaluate_schema(report, orm_tables(), head, ALL_ROLE_CODES)
        redis_data, redis_marker = connect_redis(redis_host, redis_port)
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise

    _STATE = GuardState(
        mode=mode,
        root=root,
        app_target=app_target,
        cleanup_target=cleanup_target,
        redis_endpoint=(redis_host, redis_port),
        redis_data=redis_data,
        redis_marker=redis_marker,
        cleanup_tables=cleanup_tables,
        fingerprint=fingerprint,
        alembic_head=head,
        dev_snapshot=snapshot,
    )
    return _STATE


# --- Isolation entre tests -----------------------------------------------------------------------


async def _clean_postgres(state: GuardState, phase: str, nodeid: str) -> dict[str, str]:
    import asyncpg

    conn = await _connect(state.cleanup_target)
    try:
        try:
            async with conn.transaction():
                await conn.execute("SET LOCAL lock_timeout = '5s'")
                row = await conn.fetchrow(IDENTITY_SQL)
                if (row["db"], row["marker"], row["usr"]) != (TEST_DB, SENTINEL, CLEANER_ROLE):
                    raise _refuse("identité de la base de nettoyage incorrecte (base/marqueur/rôle)")
                tables = tuple(
                    sorted(r["tablename"] for r in await conn.fetch(DISCOVER_SQL, list(EXCLUDED_TABLES)))
                )
                if tables != state.cleanup_tables:
                    raise _refuse("l'ensemble des tables applicatives a changé en cours de session")
                if tables:
                    quoted = ", ".join(_quote_table(table) for table in tables)
                    await conn.execute(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE")
        except asyncpg.exceptions.LockNotAvailableError:
            raise _refuse(
                f"verrou non obtenu en 5 s ({phase} {nodeid}) : une transaction est probablement "
                "restée ouverte"
            ) from None
        fingerprint = await _fingerprint(conn)
    finally:
        await conn.close()
    if fingerprint != state.fingerprint:
        raise _refuse(
            f"tables de référence modifiées (détecté {phase} {nodeid}) — réinitialiser la base"
        )
    return {
        "phase": phase,
        "nodeid": nodeid,
        "thread": threading.current_thread().name,
        "loop": str(id(asyncio.get_running_loop())),
    }


def flush_redis(state: GuardState) -> None:
    kwargs = state.redis_data.connection_pool.connection_kwargs
    endpoint = (kwargs.get("host"), kwargs.get("port"))
    if (
        endpoint not in ALLOWED_REDIS[state.mode]
        or endpoint != state.redis_endpoint
        or kwargs.get("db", 0) != 0
    ):
        raise _refuse("client Redis de nettoyage hors de la destination validée")
    try:
        marker = state.redis_marker.get(REDIS_MARKER_KEY)
    except Exception as exc:
        raise _refuse(f"Redis injoignable avant FLUSHDB — {_safe_error(exc)}") from None
    if marker != SENTINEL:
        raise _refuse("marqueur Redis absent avant FLUSHDB")
    state.redis_data.flushdb()


def reset_suite_caches(modules: Mapping[str, Any] | None = None) -> None:
    """D2 : le cache de session de tests/conftest.py décrit des lignes que le nettoyage supprime."""
    modules = sys.modules if modules is None else modules
    module = modules.get(SUITE_CONFTEST_MODULE)
    if module is None:
        return
    for attribute in SUITE_CACHE_ATTRIBUTES:
        if not hasattr(module, attribute):
            raise _refuse(f"{SUITE_CONFTEST_MODULE}.{attribute} introuvable : couplage D2 rompu")
        setattr(module, attribute, None)


def isolate(state: GuardState, phase: str, nodeid: str) -> None:
    entry = WORKER.run(_clean_postgres, state, phase, nodeid)
    flush_redis(state)
    reset_suite_caches()
    ISOLATION_LOG.append(entry)


def count_rows_platform_wide(table: str) -> int:
    """Comptage avec le rôle applicatif en contexte plateforme (utilisé par le test de validation
    de l'isolation depuis un test synchrone)."""
    state = current_state()
    if table not in state.cleanup_tables:
        raise _refuse(f"table « {table} » hors de l'ensemble applicatif")

    async def _count() -> int:
        conn = await _connect(state.app_target)
        try:
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.is_platform_wide', 'true', true)")
                return int(await conn.fetchval(f"SELECT count(*) FROM {_quote_table(table)}"))
        finally:
            await conn.close()

    return int(WORKER.run(_count))


def dev_files_changed(state: GuardState) -> list[str]:
    if state.dev_snapshot is None:
        return []
    return diff_snapshots(state.dev_snapshot, dev_files_snapshot(REPO_ROOT))


def remove_own_isolation_root(state: GuardState) -> None:
    shutil.rmtree(state.root, ignore_errors=True)


# --- Commandes d'administration (migrator-test uniquement) ---------------------------------------


def _admin_bootstrap() -> tuple[PgTarget, Path]:
    mode = resolve_mode()
    if mode != "migrator":
        raise _refuse("commande réservée au conteneur migrator-test")
    if (Path.cwd() / ".env").exists():
        raise _refuse("un fichier .env existe dans le répertoire courant")
    if "DATABASE_URL" in os.environ:
        raise _refuse("DATABASE_URL ne doit pas être fourni : l'URL administrateur est construite ici")
    if app_already_imported():
        raise _refuse("app.* importé avant le garde-fou")
    app_target = parse_pg_url(os.environ.get("APP_DATABASE_URL"), "APP_DATABASE_URL")
    check_pg_target(app_target, mode, APP_ROLE, "APP_DATABASE_URL")
    if app_target.password != os.environ.get("APP_DB_PASSWORD"):
        raise _refuse("APP_DB_PASSWORD incohérent avec APP_DATABASE_URL (lu par la migration 0002)")
    if not ADMIN_SECRET_PATH.is_file():
        raise _refuse("secret administrateur non monté")
    password = ADMIN_SECRET_PATH.read_text(encoding="ascii").rstrip("\r\n")
    if not password or "%" in password:
        raise _refuse("secret administrateur vide ou invalide")
    root = make_isolation_root(mode)
    try:
        apply_guard_owned(compute_safety_settings(root), os.environ)
        admin_target = PgTarget("db-test", 5432, TEST_DB, ADMIN_ROLE, password)
        os.environ["DATABASE_URL"] = (
            f"postgresql+asyncpg://{ADMIN_ROLE}:{quote(password, safe='')}@db-test:5432/{TEST_DB}"
        )
        verify_identity(admin_target, ADMIN_ROLE)
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return admin_target, root


async def _admin_post_migration(target: PgTarget) -> tuple[str | None, frozenset[str], int, bool]:
    conn = await _connect(target)
    try:
        version = await conn.fetchval("SELECT version_num FROM public.alembic_version")
        roles = frozenset(r["code"] for r in await conn.fetch("SELECT code FROM public.roles"))
        permissions = int(await conn.fetchval("SELECT count(*) FROM public.permissions"))
        app_connect = bool(
            await conn.fetchval(
                "SELECT has_database_privilege($1, $2, 'CONNECT')", APP_ROLE, TEST_DB
            )
        )
    finally:
        await conn.close()
    return version, roles, permissions, app_connect


def command_migrate() -> int:
    admin_target, root = _admin_bootstrap()
    try:
        from alembic import command
        from alembic.config import Config

        config = Config(str(API_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(API_DIR / "alembic"))
        try:
            command.upgrade(config, "head")
        except Exception as exc:
            print(
                f"ÉCHEC migrate : {_sanitized_db_error(exc)} — voir la dernière ligne "
                "« Running upgrade » ci-dessus",
                file=sys.stderr,
            )
            return 1
        head = alembic_head()
        version, roles, permissions, app_connect = WORKER.run(_admin_post_migration, admin_target)
        from app.modules.rbac.models import ALL_ROLE_CODES

        problems = []
        if version != head:
            problems.append(f"révision {version} ≠ tête {head}")
        missing_roles = sorted(set(ALL_ROLE_CODES) - roles)
        if missing_roles:
            problems.append("rôles absents : " + ", ".join(missing_roles))
        if permissions <= 0:
            problems.append("aucune permission")
        if not app_connect:
            problems.append(f"{APP_ROLE} sans CONNECT sur {TEST_DB}")
        if problems:
            print("ÉCHEC contrôles post-migration : " + " ; ".join(problems), file=sys.stderr)
            return 1
        print(
            f"migrate OK — {admin_target.describe()} à la révision {version} (tête {head}), "
            f"{len(roles)} rôles, {permissions} permissions, CONNECT {APP_ROLE} = oui"
        )
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def _grant_cleanup(target: PgTarget) -> tuple[list[str], list[Any], int]:
    conn = await _connect(target)
    try:
        async with conn.transaction():
            row = await conn.fetchrow(IDENTITY_SQL)
            if (row["db"], row["marker"], row["usr"]) != (TEST_DB, SENTINEL, ADMIN_ROLE):
                raise _refuse("identité de la base incorrecte avant grant-cleanup")
            public = sorted(r["tablename"] for r in await conn.fetch(PUBLIC_TABLES_SQL))
            cleanup = [table for table in public if table not in EXCLUDED_TABLES]
            await conn.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {CLEANER_ROLE}")
            await conn.execute(f"GRANT USAGE ON SCHEMA public TO {CLEANER_ROLE}")
            for table in cleanup:
                await conn.execute(f"GRANT TRUNCATE ON TABLE {_quote_table(table)} TO {CLEANER_ROLE}")
            for table, _order in FINGERPRINT_TABLES:
                if table in public:
                    await conn.execute(f"GRANT SELECT ON TABLE {_quote_table(table)} TO {CLEANER_ROLE}")
        privileges = await conn.fetch(
            "SELECT c.relname AS tablename, "
            "has_table_privilege($1, c.oid, 'TRUNCATE') AS can_truncate, "
            "has_table_privilege($1, c.oid, 'SELECT') AS can_select " + PUBLIC_TABLE_OIDS_FROM,
            CLEANER_ROLE,
        )
        app_truncate = int(
            await conn.fetchval(
                "SELECT count(*) " + PUBLIC_TABLE_OIDS_FROM
                + " AND has_table_privilege($1, c.oid, 'TRUNCATE')",
                APP_ROLE,
            )
        )
    finally:
        await conn.close()
    return cleanup, list(privileges), app_truncate


def command_grant_cleanup() -> int:
    admin_target, root = _admin_bootstrap()
    try:
        cleanup, privileges, app_truncate = WORKER.run(_grant_cleanup, admin_target)
        select_tables = {table for table, _order in FINGERPRINT_TABLES}
        problems = []
        for row in privileges:
            table = row["tablename"]
            if (table in cleanup) != bool(row["can_truncate"]):
                problems.append(f"TRUNCATE inattendu sur {table}")
            if (table in select_tables) != bool(row["can_select"]):
                problems.append(f"SELECT inattendu sur {table}")
        if app_truncate:
            problems.append(f"{APP_ROLE} possède TRUNCATE sur {app_truncate} table(s)")
        if problems:
            print("ÉCHEC grant-cleanup : " + " ; ".join(problems), file=sys.stderr)
            return 1
        print(
            f"grant-cleanup OK — {CLEANER_ROLE} : TRUNCATE sur {len(cleanup)} tables applicatives, "
            f"SELECT sur {len(select_tables)} tables de référence, aucun autre privilège ; "
            f"{APP_ROLE} sans TRUNCATE"
        )
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def command_check() -> int:
    state = preflight()
    try:
        counts = ", ".join(f"{table}={count}" for table, count, _hash in state.fingerprint)
        print(f"mode                     : {state.mode}")
        print(f"APP_DATABASE_URL         : {state.app_target.describe()} (identité et marqueur OK)")
        print("DATABASE_URL             : identique à APP_DATABASE_URL (aucun identifiant admin)")
        print(f"TEST_CLEANUP_DATABASE_URL: {state.cleanup_target.describe()} (identité OK)")
        host, port = state.redis_endpoint
        print(f"REDIS_URL                : {host}:{port}/0 (marqueur base {REDIS_MARKER_DB} OK)")
        print(f"tête Alembic             : {state.alembic_head}")
        print(f"tables vidées par test   : {len(state.cleanup_tables)}")
        print(f"tables de référence      : {counts}")
        print(f"répertoire de session    : {state.root} (stockage, emails, sms)")
        print("RÉSULTAT                 : environnement de tests conforme")
    finally:
        remove_own_isolation_root(state)
    return 0


COMMANDS: dict[str, Callable[[], int]] = {
    "check": command_check,
    "migrate": command_migrate,
    "grant-cleanup": command_grant_cleanup,
}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in COMMANDS:
        print("usage : python -m edusphere_test_guard {check|migrate|grant-cleanup}", file=sys.stderr)
        return 2
    try:
        return COMMANDS[args[0]]()
    except EnvironmentRefused as exc:
        print(f"REFUS du garde-fou : {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
