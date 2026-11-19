from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError


def next_doc_no(db: Session, seq_type: str, prefix: str) -> str:
    """单据编号：前缀 + 业务日期 + 4 位当日序号，并发唯一靠唯一约束兜底。"""
    biz_date = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    seq = db.execute(
        text(
            """
            insert into order_no_sequences (seq_type, seq_date, current_seq)
            values (:t, :d, 1)
            on conflict (seq_type, seq_date)
            do update set current_seq = order_no_sequences.current_seq + 1, updated_at = now()
            returning current_seq
            """
        ),
        {"t": seq_type, "d": biz_date},
    ).scalar_one()
    if seq > 9999:
        raise AppError(3000, "当日单据号已用尽", 409)
    return f"{prefix}{biz_date:%Y%m%d}{int(seq):04d}"
