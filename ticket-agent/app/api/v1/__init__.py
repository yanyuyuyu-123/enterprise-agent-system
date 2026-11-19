from fastapi import APIRouter

from app.api.v1 import (
    agent,
    alerts,
    attachments,
    auth,
    business,
    knowledge,
    logs,
    notifications,
    reports,
    stats,
    voice,
    work_orders,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(agent.router)
api_router.include_router(work_orders.router)
api_router.include_router(business.router)
api_router.include_router(knowledge.router)
api_router.include_router(attachments.router)
api_router.include_router(notifications.router)
api_router.include_router(logs.router)
api_router.include_router(stats.router)
api_router.include_router(voice.router)
api_router.include_router(reports.router)
api_router.include_router(alerts.router)
