from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


def envelope(request: Request, data: Any = None, *, message: str = "ok", code: int = 0) -> dict:
    return {
        "code": code,
        "message": message,
        "data": data,
        "request_id": getattr(request.state, "request_id", ""),
    }


def ok(request: Request, data: Any = None, *, message: str = "ok", status_code: int = 200):
    return JSONResponse(
        status_code=status_code,
        content=envelope(request, data, message=message),
    )
