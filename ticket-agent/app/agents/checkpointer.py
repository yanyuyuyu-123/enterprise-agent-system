"""LangGraph checkpointer 单例：会话状态存 agent_state schema，不写业务库。"""

from __future__ import annotations

import threading
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver

from app.core.config import settings

_saver: PostgresSaver | None = None
_lock = threading.Lock()


def _dsn() -> str:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["options"] = "-csearch_path=agent_state"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def get_checkpointer() -> PostgresSaver:
    global _saver
    if _saver is None:
        with _lock:
            if _saver is None:
                conn = psycopg.Connection.connect(_dsn(), autocommit=True)
                saver = PostgresSaver(conn)
                saver.setup()
                _saver = saver
    return _saver
