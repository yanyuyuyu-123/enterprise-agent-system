"""语音处理编排：转写 → 归一化 → 词典纠错 → 改写 → 意图/实体 → 确认判断。"""

from __future__ import annotations

import difflib
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import llm
from app.core.errors import AppError
from app.core.storage import get_storage
from app.integrations import asr, tts
from app.models.business import Customer, Product, Supplier
from app.models.org import Department, Position, User
from app.models.voice import VoiceFile, VoiceTranscript
from app.models.work_order import Device
from app.services import voiceprint_service
from app.services.log_service import write_log_safely
from app.services.permission_service import Principal, require_permission
from app.services.setting_service import get_float, get_int, get_value

VOICE_RETENTION_DAYS = 7
_DICTIONARY_CACHE: dict[str, Any] = {"expires_at": None, "values": []}

_DEVICE_NO_RE = re.compile(r"[A-Za-z]{1,4}-?\d{2,}[A-Za-z0-9-]*")
_AMOUNT_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:元|块|万元)")
_DATE_RE = re.compile(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?")
# 只匹配前后都不是英文/数字的纯中文词，避免把“设备A-001”里的“设备”纠坏
_CJK_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])[\u4e00-\u9fa5]{2,}(?![A-Za-z0-9])")

_NORMALIZE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"（"), "("),
    (re.compile(r"）"), ")"),
    (re.compile(r"[，、]"), ","),
    (re.compile(r"[。！？]"), "。"),
    (re.compile(r"\s+"), " "),
)

_NUM_UNIT_RE = re.compile(
    r"([零一二三四五六七八九十百千万两]+)\s*(个|台|件|套|箱|号|元|天|小时|分钟)"
)
_DIGITS = "零一二三四五六七八九"


def _chinese_number(text: str) -> int | None:
    """只处理 100 以内的中文数字，超出范围保持原样，避免改错数量。"""
    if not text or len(text) > 5:
        return None
    if text == "两":
        return 2
    total = 0
    current = 0
    for char in text:
        if char in _DIGITS:
            current = _DIGITS.index(char)
        elif char == "十":
            total += (current or 1) * 10
            current = 0
        elif char == "百":
            total += (current or 1) * 100
            current = 0
        else:
            return None
    return total + current


def _normalize(text: str) -> str:
    normalized = text
    for pattern, replacement in _NORMALIZE_RULES:
        normalized = pattern.sub(replacement, normalized)

    def replace_number(match: re.Match[str]) -> str:
        value = _chinese_number(match.group(1))
        return match.group(0) if value is None else f"{value}{match.group(2)}"

    return _NUM_UNIT_RE.sub(replace_number, normalized).strip()


def _dictionary(db: Session) -> list[str]:
    ttl_minutes = get_int(db, "voice.dictionary.ttl_minutes", 10)
    now = datetime.now(UTC)
    expires_at = _DICTIONARY_CACHE["expires_at"]
    if expires_at is not None and expires_at > now:
        return list(_DICTIONARY_CACHE["values"])

    values: set[str] = set()
    for column in (Device.device_no, Device.device_name):
        values.update(value for value in db.scalars(select(column)).all() if value)
    for _model, columns in (
        (Product, (Product.code, Product.name)),
        (Customer, (Customer.code, Customer.name)),
        (Supplier, (Supplier.code, Supplier.name)),
        (User, (User.name,)),
        (Department, (Department.name,)),
        (Position, (Position.name,)),
    ):
        for column in columns:
            values.update(value for value in db.scalars(select(column)).all() if value)

    ordered = sorted({value.strip() for value in values if len(value.strip()) >= 2})
    _DICTIONARY_CACHE["values"] = ordered
    _DICTIONARY_CACHE["expires_at"] = now + timedelta(minutes=ttl_minutes)
    return ordered


def _correct(text: str, dictionary: list[str]) -> tuple[str, list[str]]:
    """只纠正纯中文词；含数字的词一律不动（数量、金额、日期、单据号、设备编号）。"""
    suspected: list[str] = []
    corrected = text
    for token in set(_CJK_TOKEN_RE.findall(text)):
        if any(char.isdigit() for char in token):
            continue
        if token in dictionary:
            continue
        matches = difflib.get_close_matches(token, dictionary, n=2, cutoff=0.8)
        if not matches:
            continue
        if len(matches) > 1:
            suspected.append(f"{token}（候选：{'、'.join(matches)}）")
            continue
        corrected = corrected.replace(token, matches[0])
    return corrected, suspected


_INTENTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("work_order_create", ("创建", "报修", "报销", "巡查", "运输异常", "提交工单", "故障")),
    ("work_order_assign", ("分配", "改派")),
    ("work_order_submit", ("提交处理", "处理结果")),
    ("knowledge_query", ("制度", "流程", "手册", "合同", "报价", "规定")),
    ("operations_query", ("采购", "销售", "库存", "供应商", "客户")),
    ("finance_query", ("利润", "收入", "成本", "应收", "应付", "资金")),
    ("work_order_query", ("查", "进度", "状态", "多少", "什么时候")),
)


def _extract(text: str, pattern: re.Pattern[str]) -> list[str]:
    return sorted(set(pattern.findall(text)))


def _intent_and_entities(text: str) -> tuple[str, dict[str, Any]]:
    intent = "work_order_query"
    for name, keywords in _INTENTS:
        if any(keyword in text for keyword in keywords):
            intent = name
            break
    return intent, {
        "device_no": _extract(text, _DEVICE_NO_RE),
        "amount": _extract(text, _AMOUNT_RE),
        "date": _extract(text, _DATE_RE),
    }


def _semantic_score(
    intent: str, entities: dict[str, Any], suspected: list[str], text: str
) -> float:
    score = 0.55
    if intent != "work_order_query":
        score += 0.15
    if entities["device_no"] or entities["amount"] or entities["date"]:
        score += 0.15
    if len(text) >= 6:
        score += 0.10
    if suspected:
        score -= 0.25
    return round(min(max(score, 0.2), 0.95), 4)


def _confirmation(
    suspected: list[str],
    score: float,
    threshold: float,
    text: str,
) -> tuple[bool, str | None]:
    """只在听不准/有歧义时要求确认；缺字段交给 Agent 结构化追问。"""
    if suspected:
        return True, f"以下内容有多个候选，请确认：{'；'.join(suspected)}"
    if score < threshold:
        return True, f"我没完全听清，请确认：{text}"
    return False, None


def _write_file(principal: Principal, data: bytes, *, suffix: str, purpose: str) -> VoiceFile:
    now = datetime.now(UTC)
    relative = f"voice/{principal.user_id}/{uuid.uuid4().hex}.{suffix}"
    get_storage().save(relative, data)
    return VoiceFile(
        user_id=principal.user_id,
        file_name=f"voice-{now:%Y%m%d%H%M%S}.{suffix}",
        file_path=relative,
        file_ext=suffix,
        file_size=len(data),
        duration_ms=None,
        purpose=purpose,
        expires_at=now + timedelta(days=VOICE_RETENTION_DAYS),
    )


_REWRITE_PREFIX_RE = re.compile(r"^(改写结果|改写后|结果)\s*[:：]\s*")


def _rewrite_text(text: str) -> str:
    """语音文本再走一遍大模型改写，修正同音错字；模型不可用时原样返回。"""
    if len(text) < 3 or not llm.available():
        return text
    try:
        rewritten = llm.rewrite(text, None)
    except Exception:
        return text
    rewritten = _REWRITE_PREFIX_RE.sub("", rewritten.strip()).strip().strip("\"'“”")
    return rewritten or text


def _analyze(db: Session, text: str, *, rewrite: bool = False) -> dict[str, Any]:
    """归一化 + 纠错 + 意图/实体 + 语义可信度，转写与唤醒共用。

    rewrite=True 时先让大模型改写一遍同音错字，再跑词表纠错。
    """
    normalized = _normalize(text)
    rewritten = _rewrite_text(normalized) if rewrite else normalized
    corrected, suspected = _correct(rewritten, _dictionary(db))
    intent, entities = _intent_and_entities(corrected)
    threshold = get_float(db, "voice.semantic.confidence_threshold", 0.60)
    score = _semantic_score(intent, entities, suspected, corrected)
    needs_confirmation, question = _confirmation(suspected, score, threshold, corrected)
    return {
        "corrected_text": corrected,
        "rewritten_text": rewritten,
        "suspected_errors": suspected,
        "intent": intent,
        "entities": entities,
        "semantic_confidence": score,
        "needs_confirmation": needs_confirmation,
        "confirmation_question": question,
    }


def create_transcript(
    db: Session, principal: Principal, *, file_name: str, data: bytes
) -> dict[str, Any]:
    require_permission(principal, "voice", "create")
    max_mb = get_int(db, "voice.file.max_size_mb", 10)
    if len(data) > max_mb * 1024 * 1024:
        raise AppError(1001, f"语音文件不能超过 {max_mb}MB", 400)
    if not asr.is_configured():
        raise AppError(5002, "语音识别模型未配置", 500)

    wav = asr.read_wav(data)
    max_seconds = get_int(db, "voice.record.max_duration_seconds", 60)
    if wav.duration_ms > max_seconds * 1000:
        raise AppError(1001, f"单次录音不能超过 {max_seconds} 秒", 400)

    if not voiceprint_service.verify(db, principal, pcm=wav.pcm):
        raise AppError(3000, "声纹与当前账号不匹配，请用本人声音重新录入", 403)

    voice_file = _write_file(principal, data, suffix="wav", purpose="asr_input")
    voice_file.file_name = file_name[:255] or voice_file.file_name
    voice_file.duration_ms = wav.duration_ms
    db.add(voice_file)
    db.flush()

    segments = asr.transcribe(wav.pcm)
    asr_text = "".join(segment.text for segment in segments).strip()
    if not asr_text:
        raise AppError(3000, "没有识别到语音内容，请重说一遍", 400)

    analysis = _analyze(db, asr_text, rewrite=True)
    corrected = analysis["corrected_text"]
    suspected = analysis["suspected_errors"]
    intent = analysis["intent"]
    entities = analysis["entities"]
    score = analysis["semantic_confidence"]
    needs_confirmation = analysis["needs_confirmation"]
    question = analysis["confirmation_question"]

    transcript = VoiceTranscript(
        user_id=principal.user_id,
        voice_file_id=voice_file.id,
        asr_text=asr_text,
        corrected_text=corrected,
        rewritten_text=analysis["rewritten_text"],
        intent=intent,
        entities=entities,
        asr_confidence=None,
        semantic_confidence=Decimal(str(score)),
        suspected_errors=suspected,
        needs_confirmation=needs_confirmation,
        confirmation_question=question,
    )
    db.add(transcript)
    db.flush()
    write_log_safely(
        db,
        resource="voice",
        action="asr",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        target_type="voice_transcript",
        target_id=transcript.id,
        detail={
            "transcript_id": transcript.id,
            "duration_ms": wav.duration_ms,
            "semantic_confidence": score,
            "needs_confirmation": needs_confirmation,
        },
    )
    db.commit()
    return _payload(transcript)


def confirm_transcript(
    db: Session, principal: Principal, *, transcript_id: int, final_text: str | None
) -> dict[str, Any]:
    require_permission(principal, "voice", "create")
    transcript = db.scalar(
        select(VoiceTranscript).where(
            VoiceTranscript.id == transcript_id,
            VoiceTranscript.user_id == principal.user_id,
        )
    )
    if transcript is None:
        raise AppError(3003, "转写记录不存在或不可见", 404)
    if transcript.confirmed:
        return _payload(transcript)

    text = (final_text or transcript.corrected_text or transcript.asr_text or "").strip()
    if not text:
        raise AppError(1001, "确认文本不能为空", 400)
    transcript.final_text = text
    transcript.confirmed = True
    transcript.confirmed_at = datetime.now(UTC)
    write_log_safely(
        db,
        resource="voice",
        action="confirm",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        target_type="voice_transcript",
        target_id=transcript.id,
        detail={"transcript_id": transcript.id},
    )
    db.commit()
    return _payload(transcript)


def _payload(transcript: VoiceTranscript) -> dict[str, Any]:
    return {
        "transcript_id": transcript.id,
        "original_text": transcript.asr_text,
        "corrected_text": transcript.corrected_text,
        "rewritten_text": transcript.rewritten_text,
        "intent": transcript.intent,
        "entities": transcript.entities or {},
        "asr_confidence": None
        if transcript.asr_confidence is None
        else float(transcript.asr_confidence),
        "semantic_confidence": None
        if transcript.semantic_confidence is None
        else float(transcript.semantic_confidence),
        "suspected_errors": transcript.suspected_errors or [],
        "needs_confirmation": transcript.needs_confirmation,
        "confirmation_question": transcript.confirmation_question,
        "final_text": transcript.final_text,
        "confirmed": transcript.confirmed,
    }


_MASK_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"1[3-9]\d{9}"), "1**********"),
    (re.compile(r"\d{17}[\dXx]"), "******************"),
    (re.compile(r"\b\d{16,19}\b"), "**** **** **** ****"),
)


def mask_sensitive(text: str) -> str:
    """播报前脱敏：手机号、身份证、银行卡。"""
    masked = text
    for pattern, replacement in _MASK_RULES:
        masked = pattern.sub(replacement, masked)
    return masked


def synthesize_reply(db: Session, principal: Principal, *, text: str) -> dict[str, Any]:
    require_permission(principal, "voice", "create")
    enabled = str(get_value(db, "voice.tts.enabled", "true")).lower() == "true"
    if not enabled:
        raise AppError(3001, "语音播报已关闭", 400)

    max_chars = get_int(db, "voice.tts.max_chars", 500)
    content = text.strip()
    if not content:
        raise AppError(1001, "播报文本不能为空", 400)
    truncated = len(content) > max_chars
    if truncated:
        content = f"{content[:max_chars]}（内容较长，已截断）"

    voice = get_value(db, "voice.tts.voice", "中文女")
    now = datetime.now(UTC)
    relative = f"voice/{principal.user_id}/{uuid.uuid4().hex}.wav"
    target = get_storage().path(relative)
    tts.synthesize(mask_sensitive(content), target, voice=voice)

    voice_file = VoiceFile(
        user_id=principal.user_id,
        file_name=f"reply-{now:%Y%m%d%H%M%S}.wav",
        file_path=relative,
        file_ext="wav",
        file_size=target.stat().st_size,
        duration_ms=None,
        purpose="tts_output",
        expires_at=now + timedelta(days=VOICE_RETENTION_DAYS),
    )
    db.add(voice_file)
    db.flush()
    write_log_safely(
        db,
        resource="voice",
        action="tts",
        user_id=principal.user_id,
        user_name=principal.name,
        department_id=principal.department_id,
        target_type="voice_file",
        target_id=voice_file.id,
        detail={"voice_file_id": voice_file.id, "truncated": truncated, "chars": len(content)},
    )
    db.commit()
    return {
        "voice_file_id": voice_file.id,
        "download_url": f"/api/v1/voice/files/{voice_file.id}/download",
        "truncated": truncated,
    }


def get_voice_file(db: Session, principal: Principal, file_id: int) -> VoiceFile:
    require_permission(principal, "voice", "create")
    voice_file = db.scalar(
        select(VoiceFile).where(
            VoiceFile.id == file_id,
            VoiceFile.user_id == principal.user_id,
        )
    )
    if voice_file is None:
        raise AppError(3003, "语音文件不存在或不可见", 404)
    return voice_file
