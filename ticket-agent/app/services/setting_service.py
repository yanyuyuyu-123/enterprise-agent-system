"""读取 system_configs 的可调参数，代码不写死默认值以外的配置。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.misc import SystemConfig


def get_value(db: Session, key: str, default: str) -> str:
    value = db.scalar(select(SystemConfig.config_value).where(SystemConfig.config_key == key))
    return value if value is not None else default


def get_int(db: Session, key: str, default: int) -> int:
    try:
        return int(get_value(db, key, str(default)))
    except ValueError:
        return default


def get_float(db: Session, key: str, default: float) -> float:
    try:
        return float(get_value(db, key, str(default)))
    except ValueError:
        return default
