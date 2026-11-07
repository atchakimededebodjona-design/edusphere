"""Audit d'exposition des secrets de l'environnement de tests isolé EduLinkage (Phase 2).

Outil OPÉRATEUR, exécuté sur l'hôte Windows, jamais par pytest (hors de apps/api : invisible dans
api-test et jamais collecté) :

    apps/api/.venv/Scripts/python.exe -I infrastructure/docker/test/audit_secret_exposure.py \
        --sources files[,config,inspect,logs,env-api,env-db,shell] [--captures DOSSIER]

Charge en mémoire le mot de passe administrateur (fichier secret hors dépôt) et les mots de passe
applicatif et de nettoyage (apps/api/.env.test), capture chaque source par subprocess — aucun secret
n'est passé en argument — et n'affiche QUE des nombres d'occurrences.

Codes de sortie : 0 = aucune occurrence interdite ; 1 = occurrence interdite ; 2 = audit incomplet.
Bibliothèque standard uniquement.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_TEST = REPO_ROOT / "apps" / "api" / ".env.test"
COMPOSE = [
    "docker",
    "compose",
    "-f",
    "docker-compose.test.yml",
    "-p",
    "edusphere-test",
    "--env-file",
    "apps/api/.env.test",
]
KINDS = ("admin", "app", "cleaner")
ADMIN_ONLY = ("admin",)

CREATED_FILES = (
    "docker-compose.test.yml",
    "apps/api/Dockerfile.test",
    "infrastructure/docker/test/postgres-init/01-edusphere-test.sh",
    "infrastructure/docker/test/audit_secret_exposure.py",
    "apps/api/.env.test",
    "apps/api/env.test.example",
    "apps/api/edusphere_test_guard.py",
    "apps/api/conftest.py",
    "apps/api/tests/test_edusphere_test_guard.py",
    "apps/api/tests/test_edusphere_test_isolation.py",
)
MODIFIED_FILES = (
    ".dockerignore",
    "apps/api/.dockerignore",
    "apps/api/tests/test_storage_security.py",
)
# apps/api/.env.test contient légitimement les mots de passe applicatif et de nettoyage.
FILES_WITH_TEST_PASSWORDS = ("apps/api/.env.test",)


class AuditUnavailable(Exception):
    """Source impossible à capturer (message sans secret)."""


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_secrets() -> dict[str, str]:
    if not ENV_TEST.is_file():
        raise AuditUnavailable("apps/api/.env.test absent")
    env = parse_env_file(ENV_TEST)
    secret_path = env.get("EDUSPHERE_TEST_ADMIN_SECRET_FILE")
    if not secret_path or not Path(secret_path).is_file():
        raise AuditUnavailable("fichier secret administrateur introuvable")
    loaded = {
        "admin": Path(secret_path).read_text(encoding="ascii").rstrip("\r\n"),
        "app": env.get("EDUSPHERE_TEST_APP_PASSWORD", ""),
        "cleaner": env.get("EDUSPHERE_TEST_CLEANER_PASSWORD", ""),
    }
    empty = [kind for kind, value in loaded.items() if len(value) < 16]
    if empty:
        raise AuditUnavailable("secret vide ou trop court : " + ", ".join(empty))
    return loaded


def decode(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    if len(raw) > 1 and raw.count(b"\x00") > len(raw) // 4:
        return raw.decode("utf-16-le", errors="replace")
    return raw.decode("utf-8", errors="replace")


def run(command: list[str]) -> bytes:
    try:
        done = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        raise AuditUnavailable(f"commande impossible ({type(exc).__name__})") from None
    if done.returncode != 0:
        raise AuditUnavailable(f"commande en échec (code {done.returncode})")
    return done.stdout + b"\n" + done.stderr


# Chaque source renvoie une liste de (libellé, contenu, types de secrets interdits).
Capture = list[tuple[str, bytes, tuple[str, ...]]]


def source_files(_captures: Path | None) -> Capture:
    result: Capture = []
    for relative in CREATED_FILES + MODIFIED_FILES:
        path = REPO_ROOT / relative
        if not path.is_file():
            raise AuditUnavailable(f"fichier attendu absent : {relative}")
        kinds = ADMIN_ONLY if relative in FILES_WITH_TEST_PASSWORDS else KINDS
        result.append((f"fichier {relative}", path.read_bytes(), kinds))
    return result


def source_config(_captures: Path | None) -> Capture:
    rendered = run(COMPOSE + ["--profile", "admin", "config"])
    return [("rendu compose config", rendered, ADMIN_ONLY)]


def source_inspect(_captures: Path | None) -> Capture:
    listing = run(
        ["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=edusphere-test"]
    )
    ids = [line for line in decode(listing).split() if line]
    if not ids:
        raise AuditUnavailable("aucun conteneur du projet edusphere-test")
    return [("docker inspect (conteneurs edusphere-test)", run(["docker", "inspect", *ids]), ADMIN_ONLY)]


def source_logs(_captures: Path | None) -> Capture:
    logs = run(COMPOSE + ["--profile", "admin", "logs", "--no-color"])
    return [("journaux compose (tous services)", logs, KINDS)]


def source_env_api(_captures: Path | None) -> Capture:
    script = 'tr "\\0" "\\n" < /proc/1/environ; env'
    output = run(COMPOSE + ["exec", "-T", "api-test", "sh", "-c", script])
    return [("environnement api-test (PID 1 et exec)", output, ADMIN_ONLY)]


def source_env_db(_captures: Path | None) -> Capture:
    output = run(
        COMPOSE + ["exec", "-T", "-u", "postgres", "db-test", "sh", "-c", 'tr "\\0" "\\n" < /proc/1/environ']
    )
    return [("environnement serveur db-test (PID 1)", output, ADMIN_ONLY)]


def source_shell(_captures: Path | None) -> Capture:
    lines = "\n".join(f"{key}={value}" for key, value in os.environ.items())
    return [("environnement du shell courant", lines.encode("utf-8"), KINDS)]


def source_captures(captures: Path | None) -> Capture:
    if captures is None or not captures.is_dir():
        raise AuditUnavailable("dossier de captures absent")
    files = sorted(path for path in captures.rglob("*") if path.is_file())
    return [(f"capture {path.name}", path.read_bytes(), KINDS) for path in files]


SOURCES: dict[str, Callable[[Path | None], Capture]] = {
    "files": source_files,
    "config": source_config,
    "inspect": source_inspect,
    "logs": source_logs,
    "env-api": source_env_api,
    "env-db": source_env_db,
    "shell": source_shell,
}


def count(text: str, secret: str) -> int:
    return text.count(secret)


def format_row(label: str, cells: Iterable[str]) -> str:
    return f"{label[:58]:<58} " + " ".join(f"{cell:>9}" for cell in cells)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit d'exposition des secrets (nombres seulement)")
    parser.add_argument("--sources", default="", help="liste séparée par des virgules")
    parser.add_argument("--captures", type=Path, default=None, help="dossier de sorties capturées")
    args = parser.parse_args(argv)

    requested = [name for name in args.sources.split(",") if name]
    unknown = [name for name in requested if name not in SOURCES]
    if unknown or (not requested and args.captures is None):
        print("sources valides : " + ", ".join(SOURCES) + " (et/ou --captures DOSSIER)")
        return 2

    try:
        loaded = load_secrets()
    except AuditUnavailable as exc:
        print(f"AUDIT IMPOSSIBLE : {exc}")
        return 2
    print("3 secrets chargés en mémoire (valeurs jamais affichées)")
    print(format_row("source", ("admin", "app", "nettoyage")))

    forbidden_found = 0
    unavailable = 0
    providers = [(name, SOURCES[name]) for name in requested]
    if args.captures is not None:
        providers.append(("captures", source_captures))
    for name, provider in providers:
        try:
            captured = provider(args.captures)
        except AuditUnavailable as exc:
            unavailable += 1
            print(format_row(f"{name} : INDISPONIBLE ({exc})", ("?", "?", "?")))
            continue
        for label, raw, kinds in captured:
            text = decode(raw)
            cells = []
            for kind in KINDS:
                if kind in kinds:
                    occurrences = count(text, loaded[kind])
                    forbidden_found += occurrences
                    cells.append(str(occurrences))
                else:
                    cells.append("—")
            print(format_row(label, cells))
        if name == "env-db":
            lines = decode(captured[0][1]).splitlines()
            leaked = sum(
                1 for line in lines if line.startswith(("POSTGRES_PASSWORD=", "PGPASSWORD="))
            )
            forbidden_found += leaked
            print(format_row("variables POSTGRES_PASSWORD/PGPASSWORD (db-test PID 1)", (str(leaked), "", "")))

    if forbidden_found:
        print(f"RÉSULTAT : {forbidden_found} occurrence(s) interdite(s) — ÉCHEC")
        return 1
    if unavailable:
        print(f"RÉSULTAT : aucune occurrence interdite, mais {unavailable} source(s) indisponible(s)")
        return 2
    print("RÉSULTAT : aucune occurrence interdite (0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
