"""Abstraction de stockage de fichiers.

Aucun fournisseur cloud n'est encore choisi pour EduSphere (voir décision
projet). Tout code métier doit dépendre de `StorageProvider`, jamais d'un
SDK cloud concret, afin de pouvoir brancher S3 / GCS / Azure Blob plus tard
sans réécrire les appelants.
"""

from abc import ABC, abstractmethod
from pathlib import Path


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
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str) -> Path:
        return self._base_path / path

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
