"""工具执行器：权限校验、超时、只读重试与统一错误结构。"""

from __future__ import annotations

import contextvars
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

from app.core.db import SessionLocal
from app.core.errors import AppError
from app.core.logging import logger
from app.services.permission_service import Principal, require_permission
from app.tools.registry import TOOLS


def _error(code: int | str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "data": None,
        "source": {},
        "message": message,
        "error_code": str(code),
    }


def execute_tool(
    name: str,
    args: dict[str, Any],
    principal: Principal,
    *,
    timeout_s: float = 5.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """返回 (工具结果, 调用元信息)；元信息用于写 agent_logs。"""
    started = time.perf_counter()
    spec = TOOLS.get(name)
    if spec is None:
        result = _error(3000, "工具未注册，不可调用")
        return result, _meta(name, started, result)

    try:
        require_permission(principal, *spec.required_permission)
    except AppError as exc:
        result = _error(exc.code, "无权限执行该操作")
        return result, _meta(name, started, result)

    def _call() -> dict[str, Any]:
        db = SessionLocal()
        try:
            return spec.handler(db, principal, args)
        finally:
            db.close()

    attempts = 1 if spec.is_write else max(1, spec.max_retries + 1)
    result: dict[str, Any] = _error(5000, "工具调用失败")
    for attempt in range(attempts):
        context = contextvars.copy_context()
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(context.run, _call)
        try:
            result = future.result(timeout=timeout_s)
            break
        except FutureTimeoutError:
            result = _error(4002, "工具调用超时，请稍后重试或改用表单入口")
            break
        except AppError as exc:
            result = _error(exc.code, exc.message)
            break
        except Exception:  # noqa: BLE001
            logger.exception("agent tool failed", extra={"tool": name, "attempt": attempt})
            result = _error(4000, "系统繁忙，请稍后重试或改用表单入口")
        finally:
            pool.shutdown(wait=False)

    return result, _meta(name, started, result)


def _meta(name: str, started: float, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "tool",
        "name": name,
        "success": bool(result.get("ok")),
        "error_code": result.get("error_code"),
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }
