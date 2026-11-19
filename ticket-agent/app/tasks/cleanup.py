"""日志清理与归档：Agent 90 天、系统日志按配置、操作日志到期归档后删除。"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.storage import get_storage
from app.models.misc import AgentLog, OperationLog
from app.models.voice import VoiceFile, VoiceTranscript
from app.services.flow_service import get_config_int
from app.services.log_service import write_log_safely
from app.tasks.celery_app import celery_app
from app.tasks.common import log_task, retry_delay

ARCHIVE_DIR = "archive/operation"

# log_level → (保留期配置键, 默认天数)
OPERATION_RETENTION: dict[str, tuple[str, int]] = {
    "normal": ("log.retention.operation_normal_days", 180),
    "important": ("log.retention.operation_important_days", 730),
    "critical": ("log.retention.operation_critical_days", 1095),
}


def _cleanup_agent_logs(db: Session) -> int:
    days = get_config_int(db, "log.retention.agent_days", 90)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    deleted = db.execute(delete(AgentLog).where(AgentLog.created_at < cutoff)).rowcount or 0
    log_task(db, action="cleanup_agent_logs", detail={"deleted": deleted, "days": days})
    db.commit()
    return deleted


def _cleanup_system_logs(db: Session) -> int:
    days = get_config_int(db, "log.retention.system_days", 180)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    deleted = (
        db.execute(
            delete(OperationLog).where(
                OperationLog.log_type == "system",
                OperationLog.created_at < cutoff,
            )
        ).rowcount
        or 0
    )
    log_task(db, action="cleanup_system_logs", detail={"deleted": deleted, "days": days})
    db.commit()
    return deleted


def _log_line(row: OperationLog) -> str:
    payload: dict[str, Any] = {
        "id": row.id,
        "log_type": row.log_type,
        "log_level": row.log_level,
        "user_id": row.user_id,
        "user_name_snapshot": row.user_name_snapshot,
        "department_id": row.department_id,
        "resource": row.resource,
        "action": row.action,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "result": row.result,
        "request_id": row.request_id,
        "ip": row.ip,
        "detail": row.detail,
        "sensitive_detail": None
        if row.sensitive_detail is None
        else base64.b64encode(row.sensitive_detail).decode("ascii"),
        "created_at": row.created_at.isoformat(),
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _write_archive(rows: list[OperationLog]) -> tuple[str, int]:
    """追加写入本月归档文件，回读校验条数与校验和；返回路径与新写入条数。"""
    if not rows:
        return "", 0
    storage = get_storage()
    month = datetime.now(UTC).strftime("%Y-%m")
    path = f"{ARCHIVE_DIR}/{month}.jsonl.gz"

    try:
        existing = gzip.decompress(storage.read(path)).decode("utf-8").splitlines()
    except FileNotFoundError:
        existing = []
    lines = [line for line in existing if line]
    lines.extend(_log_line(row) for row in rows)

    data = gzip.compress(("\n".join(lines) + "\n").encode("utf-8"), mtime=0)
    storage.save(path, data)

    written = storage.read(path)
    if written != data or len(gzip.decompress(written).decode("utf-8").splitlines()) != len(lines):
        raise RuntimeError("归档文件校验失败")
    checksum = hashlib.sha256(data).hexdigest()
    storage.save(f"{path}.sha256", f"{checksum}\n".encode("ascii"))
    return path, len(rows)


def _archive_operation_logs(db: Session) -> dict[str, int | str]:
    now = datetime.now(UTC)
    archive_rows: list[OperationLog] = []
    delete_ids: list[int] = []
    counts: dict[str, int] = {}

    for level, (key, default_days) in OPERATION_RETENTION.items():
        days = get_config_int(db, key, default_days)
        cutoff = now - timedelta(days=days)
        rows = db.scalars(
            select(OperationLog).where(
                OperationLog.log_type == "operation",
                OperationLog.log_level == level,
                OperationLog.created_at < cutoff,
            )
        ).all()
        counts[level] = len(rows)
        if level == "normal":
            # 普通日志不归档，到期直接删除
            delete_ids.extend(row.id for row in rows)
        else:
            archive_rows.extend(rows)
            delete_ids.extend(row.id for row in rows)

    path, archived = _write_archive(archive_rows)
    if delete_ids:
        db.execute(
            delete(OperationLog)
            .where(OperationLog.id.in_(delete_ids))
            .execution_options(synchronize_session=False)
        )
    log_task(
        db,
        action="archive_operation_logs",
        detail={
            "deleted": len(delete_ids),
            "archived": archived,
            "archive_file": path,
            "normal": counts.get("normal", 0),
            "important": counts.get("important", 0),
            "critical": counts.get("critical", 0),
        },
    )
    db.commit()
    return {"deleted": len(delete_ids), "archived": archived, "archive_file": path}


def _cleanup_voice_files(db: Session) -> int:
    """录音与播报文件 7 天到期，转写文本按配置保留更久。"""
    now = datetime.now(UTC)
    storage = get_storage()
    rows = db.scalars(select(VoiceFile).where(VoiceFile.expires_at < now)).all()
    for row in rows:
        storage.delete(row.file_path)
        db.delete(row)
    log_task(db, action="cleanup_voice_files", detail={"deleted": len(rows)})
    db.commit()
    return len(rows)


def _cleanup_voice_transcripts(db: Session) -> int:
    retention_days = get_config_int(db, "voice.transcript.retention_days", 90)
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    rows = db.scalars(select(VoiceTranscript).where(VoiceTranscript.created_at < cutoff)).all()
    for row in rows:
        db.delete(row)
    log_task(db, action="cleanup_voice_transcripts", detail={"deleted": len(rows)})
    db.commit()
    return len(rows)


@celery_app.task(bind=True, name="cleanup_agent_logs", max_retries=3)
def cleanup_agent_logs(self) -> dict[str, int]:
    try:
        with SessionLocal() as db:
            return {"deleted": _cleanup_agent_logs(db)}
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as db:
            write_log_safely(
                db,
                log_type="system",
                resource="task",
                action="cleanup_agent_logs",
                user_name="系统",
                result="failure",
                detail={"error": str(exc)[:500], "retry_count": self.request.retries},
            )
            db.commit()
        raise self.retry(exc=exc, countdown=retry_delay(self.request.retries)) from exc


@celery_app.task(bind=True, name="cleanup_system_logs", max_retries=3)
def cleanup_system_logs(self) -> dict[str, int]:
    try:
        with SessionLocal() as db:
            return {"deleted": _cleanup_system_logs(db)}
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as db:
            write_log_safely(
                db,
                log_type="system",
                resource="task",
                action="cleanup_system_logs",
                user_name="系统",
                result="failure",
                detail={"error": str(exc)[:500], "retry_count": self.request.retries},
            )
            db.commit()
        raise self.retry(exc=exc, countdown=retry_delay(self.request.retries)) from exc


@celery_app.task(bind=True, name="cleanup_voice_files", max_retries=3)
def cleanup_voice_files(self) -> dict[str, int]:
    try:
        with SessionLocal() as db:
            deleted_transcripts = _cleanup_voice_transcripts(db)
            deleted_files = _cleanup_voice_files(db)
            return {"deleted_files": deleted_files, "deleted_transcripts": deleted_transcripts}
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as db:
            write_log_safely(
                db,
                log_type="system",
                resource="task",
                action="cleanup_voice_files",
                user_name="系统",
                result="failure",
                detail={"error": str(exc)[:500], "retry_count": self.request.retries},
            )
            db.commit()
        raise self.retry(exc=exc, countdown=retry_delay(self.request.retries)) from exc


@celery_app.task(bind=True, name="archive_operation_logs", max_retries=3)
def archive_operation_logs(self) -> dict[str, int | str]:
    try:
        with SessionLocal() as db:
            return _archive_operation_logs(db)
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as db:
            write_log_safely(
                db,
                log_type="system",
                resource="task",
                action="archive_operation_logs",
                user_name="系统",
                result="failure",
                detail={"error": str(exc)[:500], "retry_count": self.request.retries},
            )
            db.commit()
        raise self.retry(exc=exc, countdown=retry_delay(self.request.retries)) from exc
