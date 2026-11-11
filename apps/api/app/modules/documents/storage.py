"""Object storage abstraction. Keys are opaque server-generated identifiers; storage paths are
never exposed via the API. The local backend writes outside any static-served directory."""

import os
import re
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings

_KEY_RE = re.compile(r"^[a-f0-9]{2}/[a-f0-9]{32}$")


class ObjectStorage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalFileStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        if not _KEY_RE.match(key):
            raise ValueError("Invalid storage key")
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("Invalid storage key")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


def make_key(hex_id: str) -> str:
    return f"{hex_id[:2]}/{hex_id}"


_storage: ObjectStorage | None = None


def get_storage() -> ObjectStorage:
    global _storage
    if _storage is None:
        _storage = LocalFileStorage(get_settings().storage_root)
    return _storage


def set_storage(storage: ObjectStorage | None) -> None:
    global _storage
    _storage = storage
