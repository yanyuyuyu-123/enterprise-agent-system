from pathlib import Path

from app.core.config import settings


class LocalStorage:
    """本地文件存储，路径一律相对 `STORAGE_ROOT`，禁止用原始文件名拼路径。"""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _resolve(self, relative_path: str) -> Path:
        target = (self.root / relative_path).resolve()
        if not target.is_relative_to(self.root.resolve()):
            raise ValueError("非法存储路径")
        return target

    def path(self, relative_path: str) -> Path:
        return self._resolve(relative_path)

    def save(self, relative_path: str, data: bytes) -> None:
        path = self._resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, relative_path: str) -> bytes:
        return self._resolve(relative_path).read_bytes()

    def delete(self, relative_path: str) -> None:
        self._resolve(relative_path).unlink(missing_ok=True)


def get_storage() -> LocalStorage:
    if settings.storage_backend != "local":
        raise RuntimeError(f"V1 仅支持 local 存储，当前为 {settings.storage_backend}")
    return LocalStorage(Path(settings.storage_root))
