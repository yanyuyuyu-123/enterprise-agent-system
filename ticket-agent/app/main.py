import threading
import uuid

from fastapi import FastAPI, Request, Response

from app.api.v1 import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.rag import embedder
from app.services.log_service import set_request_id


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    register_exception_handlers(app)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        set_request_id(request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.on_event("startup")
    def _warmup() -> None:
        # 本地 embedding 首次加载较慢，放到后台线程预热，不阻塞启动
        threading.Thread(target=embedder.warmup, daemon=True).start()

    @app.get("/health", tags=["ops"])
    def health() -> dict:
        return {
            "code": 0,
            "message": "ok",
            "data": {"status": "up"},
            "request_id": "",
        }

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
