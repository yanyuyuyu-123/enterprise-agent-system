from redis import Redis

from app.core.config import settings

# 缓存、Celery broker/backend、Agent 确认令牌、refresh 黑名单共用
redis_client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
