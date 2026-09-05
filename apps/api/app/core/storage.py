"""Abstraction de stockage de fichiers.

Aucun fournisseur cloud n'est encore choisi pour EduSphere (voir décision
projet). Tout code métier doit dépendre de `StorageProvider`, jamais d'un
SDK cloud concret, afin de pouvoir brancher S3 / GCS / Azure Blob plus tard
sans réécrire les appelants.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import settings


class StoragePathError(ValueError):
    """Chemin de stockage refusé — sa résolution finale sortirait du répertoire autorisé
    (Phase 13 — traversée de chemin, voir LocalStorageProvider._resolve)."""


def safe_filename(name: str | None) -> str:
    """Réduit un nom de fichier fourni par l'utilisateur (upload) à un simple composant de nom,
    sans séparateur ni référence `.`/`..` — jamais vide. Ne garantit PAS à elle seule l'absence de
    traversée de chemin : c'est `LocalStorageProvider._resolve` (résolution + vérification de
    confinement) qui fait réellement autorité. Sert ici à garder un nom lisible sur le disque et à
    éviter qu'un nom de fichier contenant des séparateurs ne crée des sous-dossiers inattendus.
    `os.path.basename`/`Path.name` ne coupent que sur `/` sous POSIX (l'environnement d'exécution
    réel de ce backend) — on normalise aussi `\\` explicitement pour ne pas dépendre de cette
    spécificité de plateforme."""
    if not name:
        return "file"
    candidate = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if candidate in ("", ".", ".."):
        return "file"
    return candidate


class StorageProvider(ABC):
    @abstractmethod
    async def upload(self, path: str, content: bytes) -> str:
        """Écrit `content` sous `path` et retourne l'identifiant de stockage."""

    @abstractmethod
    async def download(self, path: str) -> bytes:
        """Lit le contenu stocké sous `path`."""

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Supprime le contenu stocké sous `path`."""

    @abstractmethod
    async def get_url(self, path: str) -> str:
        """Retourne une URL (locale ou signée) pour accéder à `path`."""


class LocalStorageProvider(StorageProvider):
    """Implémentation filesystem local, utilisée en développement."""

    def __init__(self, base_path: str) -> None:
        self._base_path = Path(base_path).resolve()
        self._base_path.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str) -> Path:
        # Phase 13 (HIGH #1 — traversée de chemin) : `path` peut contenir un nom de fichier fourni
        # par l'utilisateur (voir students/router.py, schools/router.py) et n'est pas fiable en
        # entrée. `Path.__truediv__` ne filtre RIEN — ni les séquences `..`, ni un `path` qui se
        # trouve être un chemin absolu (auquel cas cet opérateur ignore silencieusement
        # `self._base_path` et renvoie directement ce chemin absolu). Un simple retrait de
        # sous-chaîne (`replace("../", "")`) serait contournable par imbrication/chemins alternatifs
        # — la seule garantie robuste est de résoudre le chemin final réellement visé puis de
        # vérifier qu'il reste À L'INTÉRIEUR de `self._base_path`, quelle qu'ait été la forme de
        # l'entrée.
        resolved = (self._base_path / path).resolve()
        if not resolved.is_relative_to(self._base_path):
            raise StoragePathError(f"Resolved path escapes storage root: {path!r}")
        return resolved

    async def upload(self, path: str, content: bytes) -> str:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return path

    async def download(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    async def delete(self, path: str) -> None:
        target = self._resolve(path)
        if target.exists():
            target.unlink()

    async def get_url(self, path: str) -> str:
        return f"/storage/{path}"


def get_storage_provider(provider: str, local_path: str) -> StorageProvider:
    if provider == "local":
        return LocalStorageProvider(local_path)
    raise ValueError(f"Unknown storage provider: {provider}")


# Instance partagée par les modules métier (élèves, plus tard bulletins/reçus...) — évite de
# recréer un provider par requête. Reste dépendant de `settings`, jamais d'un SDK cloud direct.
storage = get_storage_provider(settings.storage_provider, settings.storage_local_path)
