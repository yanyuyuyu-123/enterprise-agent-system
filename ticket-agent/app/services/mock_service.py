"""模拟数据隔离：生产环境拒绝写入 is_mock 数据。"""

from __future__ import annotations

from app.core.config import settings
from app.core.errors import AppError

PRODUCTION_ENVS = frozenset({"prod", "production"})


def ensure_mock_writable(is_mock: bool) -> None:
    if is_mock and settings.app_env.lower() in PRODUCTION_ENVS:
        raise AppError(3000, "生产环境禁止写入模拟数据", 403)
