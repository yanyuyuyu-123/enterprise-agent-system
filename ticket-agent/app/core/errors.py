from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import logger


class AppError(Exception):
    """业务错误统一出口；HTTP 状态码只表语义，细分靠 code。"""

    def __init__(self, code: int, message: str, http_status: int = 400) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


def _body(code: int, message: str, request_id: str, data: Any = None) -> dict[str, Any]:
    return {"code": code, "message": message, "data": data, "request_id": request_id}


def _rid(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=_body(exc.code, exc.message, _rid(request)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_body(1000, "参数校验失败", _rid(request)),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = 2000 if exc.status_code == 401 else 5000
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(code, str(exc.detail), _rid(request)),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error", extra={"request_id": _rid(request)})
        return JSONResponse(
            status_code=500,
            content=_body(5000, "内部错误", _rid(request)),
        )
