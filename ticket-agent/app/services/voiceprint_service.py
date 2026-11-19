"""声纹录入与本人校验：CAM++ 向量入库，唤醒时按阈值比对。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.integrations import asr, speaker
from app.models.voice import Voiceprint
from app.services.log_service import write_log_safely
from app.services.permission_service import Principal, require_permission
from app.services.setting_service import get_float

MIN_SAMPLES = 3
MAX_SAMPLES = 5
MIN_SECONDS = 2.0
MAX_SECONDS = 10.0
DEFAULT_THRESHOLD = 0.62


def _row(db: Session, user_id: int) -> Voiceprint | None:
    return db.scalar(select(Voiceprint).where(Voiceprint.user_id == user_id))


def status(db: Session, principal: Principal) -> dict:
    require_permission(principal, "voice", "create")
    row = _row(db, principal.user_id)
    return {
        "enrolled": row is not None,
        "available": speaker.is_configured(),
        "samples": row.samples if row else 0,
        "updated_at": row.updated_at.isoformat() if row else None,
        "threshold": get_float(db, "voice.sv.threshold", DEFAULT_THRESHOLD),
    }


def enroll(db: Session, principal: Principal, *, samples: list[bytes]) -> dict:
    """录入：3 段录音各提一次向量，取平均后覆盖旧声纹。"""
    require_permission(principal, "voice", "create")
    if not speaker.is_configured():
        raise AppError(5002, "声纹模型未配置，无法录入", 500)
    if not MIN_SAMPLES <= len(samples) <= MAX_SAMPLES:
        raise AppError(1002, f"请上传 {MIN_SAMPLES} 段录音", 422)
    if _row(db, principal.user_id) is not None:
        raise AppError(3000, "该账号已绑定声纹，如需更换请先删除", 409)

    vectors: list[list[float]] = []
    for data in samples:
        wav = asr.read_wav(data)
        seconds = wav.duration_ms / 1000
        if seconds < MIN_SECONDS:
            raise AppError(1002, "每段录音至少 2 秒，请重录", 422)
        if seconds > MAX_SECONDS:
            raise AppError(1001, "单段录音不能超过 10 秒", 422)
        if not speaker.has_speech(wav.pcm):
            raise AppError(1002, "没有检测到人声，请重新朗读", 422)
        vector = speaker.embed(wav.pcm)
        if vector is None:
            raise AppError(1002, "录音太短或没有声音，请重录", 422)
        vectors.append(vector)

    merged = speaker.average(vectors)
    # 同一人不同录音之间应保持较高相似度，过低说明录音质量差
    baseline = min(speaker.cosine(vectors[0], item) for item in vectors[1:])
    if baseline < 0.45:
        raise AppError(3000, "三段录音差异过大，请在安静环境重录", 422)

    row = _row(db, principal.user_id)
    now = datetime.now(UTC)
    if row is None:
        row = Voiceprint(user_id=principal.user_id, model=speaker.ENGINE, embedding=merged)
        db.add(row)
    else:
        row.model = speaker.ENGINE
        row.embedding = merged
        row.updated_at = now
    row.samples = len(vectors)
    db.flush()
    write_log_safely(
        db,
        resource="voice",
        action="enroll",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        target_type="voiceprint",
        target_id=row.id,
        detail={"samples": len(vectors), "baseline": round(baseline, 3)},
    )
    db.commit()
    return status(db, principal)


def remove(db: Session, principal: Principal) -> dict:
    require_permission(principal, "voice", "create")
    row = _row(db, principal.user_id)
    if row is not None:
        db.delete(row)
        write_log_safely(
            db,
            resource="voice",
            action="delete",
            user_id=principal.user_id,
            user_name=principal.name,
            department_id=principal.department_id,
            target_type="voiceprint",
            target_id=row.id,
            detail=None,
        )
        db.commit()
    return status(db, principal)


def verify(db: Session, principal: Principal, *, pcm: bytes) -> bool:
    """本人校验；未录入或模型缺失时一律放行，避免把功能卡死。"""
    row = _row(db, principal.user_id)
    if row is None or not speaker.is_configured():
        return True
    vector = speaker.embed(pcm)
    if vector is None:
        return True
    threshold = get_float(db, "voice.sv.threshold", DEFAULT_THRESHOLD)
    return speaker.cosine(row.embedding, vector) >= threshold
