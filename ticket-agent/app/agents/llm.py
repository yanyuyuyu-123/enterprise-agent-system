"""DeepSeek 调用封装：只做语言理解（改写、意图、实体），不碰业务数据。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

# 记录最近 6 条消息（3 轮），避免上下文无限增长
HISTORY_LIMIT = 6


class LLMError(Exception):
    """模型不可用、超时或返回无法解析；调用方走规则降级。"""

    def __init__(self, message: str, *, timeout: bool = False) -> None:
        super().__init__(message)
        self.timeout = timeout


@lru_cache(maxsize=16)
def load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def available() -> bool:
    return bool(settings.deepseek_api_key)


def _history_text(history: list[dict[str, str]] | None) -> str:
    if not history:
        return "（无历史对话）"
    lines = []
    for item in history[-HISTORY_LIMIT:]:
        role = "用户" if item.get("role") == "user" else "助手"
        lines.append(f"{role}：{item.get('content', '')}")
    return "\n".join(lines)


def _post(system: str, user: str, *, json_mode: bool, timeout_s: float = 20.0) -> str:
    if not available():
        raise LLMError("未配置 DEEPSEEK_API_KEY")

    payload: dict[str, Any] = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(
                f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
    except httpx.TimeoutException as exc:
        raise LLMError("模型服务超时", timeout=True) from exc
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise LLMError(f"模型服务失败：{exc}") from exc


def _parse_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise LLMError("模型返回不是 JSON")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError("模型返回 JSON 解析失败") from exc
    if not isinstance(data, dict):
        raise LLMError("模型返回结构不是对象")
    return data


def rewrite(text: str, history: list[dict[str, str]] | None) -> str:
    system = load_prompt("rewrite.v1.md")
    user = f"历史对话：\n{_history_text(history)}\n\n用户输入：{text}\n\n改写结果："
    result = _post(system, user, json_mode=False).strip()
    return result or text


def converse(question: str, history: list[dict[str, str]] | None, context: str) -> str:
    """基于历史对话与系统查询结果，组织自然语言的回答。"""
    system = load_prompt("domain_chat.v1.md")
    user = (
        f"历史对话：\n{_history_text(history)}\n\n"
        f"当前问题：{question}\n\n"
        f"系统查询结果：\n{context}\n\n回答："
    )
    return _post(system, user, json_mode=False).strip()


def screen(text: str, history: list[dict[str, str]] | None) -> dict[str, Any]:
    """判断问题是否属于公司业务范围，并把追问补全为完整问题。"""
    system = load_prompt("screen.v1.md")
    user = f"历史对话：\n{_history_text(history)}\n\n用户输入：{text}"
    return _parse_json(_post(system, user, json_mode=True))


def classify(text: str, history: list[dict[str, str]] | None) -> dict[str, Any]:
    system = load_prompt("classify.v1.md")
    user = f"历史对话：\n{_history_text(history)}\n\n用户输入：{text}"
    return _parse_json(_post(system, user, json_mode=True))


def extract(prompt_name: str, text: str, history: list[dict[str, str]] | None) -> dict[str, Any]:
    system = load_prompt(prompt_name)
    user = f"历史对话：\n{_history_text(history)}\n\n用户输入：{text}"
    return _parse_json(_post(system, user, json_mode=True))


def generate(prompt_name: str, user: str) -> str:
    """用指定提示词生成一段自然语言内容（如报告）。"""
    return _post(load_prompt(prompt_name), user, json_mode=False).strip()
