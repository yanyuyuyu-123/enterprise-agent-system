from __future__ import annotations

from redis.exceptions import RedisError

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import logger
from app.core.redis import redis_client

LOGIN_WINDOW_SECONDS = 60


def check_login_rate_limit(ip: str) -> None:
    """同一 IP 每分钟最多 N 次登录尝试；Redis 不可用时放行并告警。"""
    limit = settings.login_rate_limit_per_minute
    if limit <= 0 or not ip:
        return
    key = f"login:attempt:{ip}"
    try:
        current = redis_client.incr(key)
        if current == 1:
            redis_client.expire(key, LOGIN_WINDOW_SECONDS)
        if current > limit:
            raise AppError(2000, "登录尝试过于频繁，请稍后再试", 400)
    except RedisError:
        logger.warning("redis unavailable, skip login rate limit", extra={"ip": ip})


def clear_login_rate_limit(ip: str) -> None:
    """登录成功后清零计数，避免正常切换账号被误判为暴力尝试。"""
    if not ip:
        return
    try:
        redis_client.delete(f"login:attempt:{ip}")
    except RedisError:
        logger.warning("redis unavailable, skip clearing login rate limit", extra={"ip": ip})
