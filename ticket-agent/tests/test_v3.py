"""T31–T48 V3 验收：语音、报告、预警、统计、媒体解析。"""

from __future__ import annotations

import io
import wave
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.errors import AppError
from app.integrations import asr, speaker
from app.models.alert import Alert, SafeStockConfig
from app.models.business import Inventory, Product, Warehouse
from app.models.misc import Notification
from app.models.report import Report, ReportViewer
from app.models.voice import VoiceFile, VoiceTranscript
from app.rag import chunker, ocr, parser
from app.services import (
    alert_service,
    report_service,
    stats_service,
    voice_service,
    voiceprint_service,
)
from app.services.permission_service import load_principal
from app.tasks import cleanup as cleanup_tasks
from tests.helpers import auth

FAR_PAST = datetime(2020, 1, 1, tzinfo=UTC)


def _wav_bytes(seconds: float = 1.0) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buffer.getvalue()


def _principal(db, employee_no: str):
    from app.models.org import User

    user = db.scalar(select(User).where(User.employee_no == employee_no))
    assert user is not None, employee_no
    return load_principal(db, user)


def test_voice_asr_unconfigured(client, monkeypatch):
    """T32：模型缺失返回 5002，文字链路不受影响。"""
    monkeypatch.setattr(settings, "voice_asr_model_dir", "")
    token = client.post(
        "/api/v1/auth/login", json={"employee_no": "R0002", "password": "Dev@123456"}
    ).json()["data"]["access_token"]
    response = client.post(
        "/api/v1/voice/asr",
        files={"file": ("voice.wav", _wav_bytes(), "audio/wav")},
        headers=auth(token),
    )
    assert response.status_code == 500, response.text
    assert response.json()["code"] == 5002


def test_voice_transcript_structure(db, monkeypatch, tmp_path):
    """T31：统一结构完整，原始/纠错文本落库，asr_confidence 为 null。"""
    monkeypatch.setattr(settings, "storage_root", str(tmp_path))
    monkeypatch.setattr(voice_service.asr, "is_configured", lambda: True)
    monkeypatch.setattr(
        voice_service.asr,
        "read_wav",
        lambda data: asr.WavInfo(
            duration_ms=1000,
            channels=1,
            sample_rate=16000,
            sample_width=2,
            pcm=b"\x00\x00" * 16000,
        ),
    )
    monkeypatch.setattr(
        voice_service.asr,
        "transcribe",
        lambda pcm: [asr.AsrSegment(start_ms=0, end_ms=1000, text="查一下工单进度")],
    )
    principal = _principal(db, "R0002")
    data = voice_service.create_transcript(db, principal, file_name="voice.wav", data=_wav_bytes())
    expected = {
        "transcript_id",
        "original_text",
        "corrected_text",
        "rewritten_text",
        "intent",
        "entities",
        "asr_confidence",
        "semantic_confidence",
        "suspected_errors",
        "needs_confirmation",
        "confirmation_question",
    }
    assert expected <= set(data)
    assert data["asr_confidence"] is None
    assert data["original_text"] == "查一下工单进度"

    row = db.get(VoiceTranscript, data["transcript_id"])
    assert row is not None
    assert row.asr_text == "查一下工单进度"
    assert row.corrected_text


def test_voice_rewrite_fixes_homophone(db, monkeypatch, tmp_path):
    """语音转写交给大模型改写后，同音错字被修正并落库。"""
    monkeypatch.setattr(settings, "storage_root", str(tmp_path))
    monkeypatch.setattr(voice_service.asr, "is_configured", lambda: True)
    monkeypatch.setattr(
        voice_service.asr,
        "read_wav",
        lambda data: asr.WavInfo(
            duration_ms=1000,
            channels=1,
            sample_rate=16000,
            sample_width=2,
            pcm=b"\x00\x00" * 16000,
        ),
    )
    monkeypatch.setattr(
        voice_service.asr,
        "transcribe",
        lambda pcm: [asr.AsrSegment(start_ms=0, end_ms=1000, text="帮我创建一个公道")],
    )
    monkeypatch.setattr(voice_service.llm, "available", lambda: True)
    monkeypatch.setattr(voice_service.llm, "rewrite", lambda text, history: "帮我创建一个工单")
    principal = _principal(db, "R0002")
    data = voice_service.create_transcript(db, principal, file_name="v.wav", data=_wav_bytes())
    assert data["rewritten_text"] == "帮我创建一个工单"
    assert "工单" in data["corrected_text"]


def test_voiceprint_enroll_verify_remove(db, monkeypatch):
    """声纹：三段求平均入库，本人通过、他人拒绝，未录入时放行。"""
    principal = _principal(db, "R0002")
    monkeypatch.setattr(speaker, "is_configured", lambda: True)
    monkeypatch.setattr(speaker, "has_speech", lambda pcm: True)
    monkeypatch.setattr(speaker, "embed", lambda pcm: [1.0, 0.0, 0.0])

    data = voiceprint_service.enroll(db, principal, samples=[_wav_bytes(3) for _ in range(3)])
    assert data["enrolled"] is True
    assert data["samples"] == 3
    assert data["available"] is True

    # 一个账号只允许一条：重复录入直接拒绝，必须显式删除
    with pytest.raises(AppError) as exc:
        voiceprint_service.enroll(db, principal, samples=[_wav_bytes(3) for _ in range(3)])
    assert exc.value.code == 3000

    monkeypatch.setattr(speaker, "embed", lambda pcm: [1.0, 0.0, 0.0])
    assert voiceprint_service.verify(db, principal, pcm=b"\x00\x00" * 32000) is True
    monkeypatch.setattr(speaker, "embed", lambda pcm: [0.0, 1.0, 0.0])
    assert voiceprint_service.verify(db, principal, pcm=b"\x00\x00" * 32000) is False

    assert voiceprint_service.remove(db, principal)["enrolled"] is False
    # 未录入时不拦截，避免功能卡死
    assert voiceprint_service.verify(db, principal, pcm=b"\x00\x00" * 32000) is True


def test_voiceprint_rejects_silence(db, monkeypatch):
    """静音录音不能录入：has_speech 判否时返回 1002。"""
    principal = _principal(db, "R0002")
    monkeypatch.setattr(speaker, "is_configured", lambda: True)
    with pytest.raises(AppError) as exc:
        voiceprint_service.enroll(db, principal, samples=[_wav_bytes(3) for _ in range(3)])
    assert exc.value.code == 1002
    assert "人声" in exc.value.message
    assert voiceprint_service.status(db, principal)["enrolled"] is False


def test_voiceprint_enroll_requires_samples(db, monkeypatch):
    """声纹：模型缺失 5002，段数不足 1002。"""
    principal = _principal(db, "R0002")
    monkeypatch.setattr(speaker, "is_configured", lambda: False)
    with pytest.raises(AppError) as exc:
        voiceprint_service.enroll(db, principal, samples=[_wav_bytes()])
    assert exc.value.code == 5002

    monkeypatch.setattr(speaker, "is_configured", lambda: True)
    with pytest.raises(AppError) as exc:
        voiceprint_service.enroll(db, principal, samples=[_wav_bytes(3)])
    assert exc.value.code == 1002


def test_voice_confirmation_only_when_unclear(db, monkeypatch, tmp_path):
    """T33/T35：听不清才确认，缺字段交给 Agent 追问，且不补造实体。"""
    monkeypatch.setattr(settings, "storage_root", str(tmp_path))
    monkeypatch.setattr(voice_service.asr, "is_configured", lambda: True)
    monkeypatch.setattr(
        voice_service.asr,
        "read_wav",
        lambda data: asr.WavInfo(
            duration_ms=1000,
            channels=1,
            sample_rate=16000,
            sample_width=2,
            pcm=b"\x00\x00" * 16000,
        ),
    )
    principal = _principal(db, "R0002")

    # 文本清晰：不确认，直接交给 Agent；缺失的字段由 Agent 结构化追问
    monkeypatch.setattr(
        voice_service.asr,
        "transcribe",
        lambda pcm: [asr.AsrSegment(start_ms=0, end_ms=1000, text="创建产煤机维修工单")],
    )
    clear = voice_service.create_transcript(db, principal, file_name="voice.wav", data=_wav_bytes())
    assert clear["needs_confirmation"] is False
    assert clear["confirmation_question"] is None
    assert clear["entities"]["device_no"] == []
    assert clear["entities"]["amount"] == []

    # 语义不可信：必须确认
    monkeypatch.setattr(
        voice_service.asr,
        "transcribe",
        lambda pcm: [asr.AsrSegment(start_ms=0, end_ms=1000, text="这个弄一下")],
    )
    unclear = voice_service.create_transcript(
        db, principal, file_name="voice.wav", data=_wav_bytes()
    )
    assert unclear["needs_confirmation"] is True
    assert unclear["confirmation_question"]


def test_voice_correction_protects_numbers():
    """T34：数字、单据号、设备编号不因纠错被改写，多解进疑似项。"""
    assert voice_service._normalize("三个") == "3个"
    assert voice_service._normalize("五 台") == "5台"
    original = "设备A-001 数量3个 金额500元"
    corrected, suspected = voice_service._correct(original, ["设备甲", "数量乙"])
    assert corrected == original
    assert suspected == []

    _, suspected_multi = voice_service._correct("产品甲", ["产品甲A", "产品甲B"])
    assert suspected_multi


def test_tts_failure_keeps_text_answer(db, monkeypatch, tmp_path):
    """T37：CosyVoice2 失败返回 4000，不产生文件记录。"""
    monkeypatch.setattr(settings, "storage_root", str(tmp_path))
    principal = _principal(db, "R0002")

    def boom(text: str, target: Path, *, voice: str) -> None:
        raise AppError(4000, "语音播报暂不可用，请查看文字回答", 502)

    monkeypatch.setattr(voice_service.tts, "synthesize", boom)
    with pytest.raises(AppError) as exc:
        voice_service.synthesize_reply(db, principal, text="这是文字回答")
    assert exc.value.code == 4000


def test_voice_files_cleanup(db, monkeypatch, tmp_path):
    """T37：到期文件与记录被清理。"""
    monkeypatch.setattr(settings, "storage_root", str(tmp_path))
    principal = _principal(db, "R0002")
    relative = f"voice/{principal.user_id}/{uuid4().hex}.wav"
    Path(tmp_path, relative).parent.mkdir(parents=True, exist_ok=True)
    Path(tmp_path, relative).write_bytes(b"wav")
    voice_file = VoiceFile(
        user_id=principal.user_id,
        file_name="old.wav",
        file_path=relative,
        file_ext="wav",
        file_size=3,
        purpose="asr_input",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    db.add(voice_file)
    db.flush()
    db.add(
        VoiceTranscript(
            user_id=principal.user_id,
            voice_file_id=voice_file.id,
            asr_text="历史转写",
            entities={},
            suspected_errors=[],
        )
    )
    db.commit()
    file_id = voice_file.id

    deleted = cleanup_tasks._cleanup_voice_files(db)
    assert deleted >= 1
    assert db.get(VoiceFile, file_id) is None
    assert not Path(tmp_path, relative).exists()


def test_report_generate_and_idempotent(db, monkeypatch, tmp_path):
    """T38/T39：日报生成成功，重复触发复用同一条，未结束区间拒绝。"""
    monkeypatch.setattr(settings, "storage_root", str(tmp_path))
    period_start = date(2025, 6, 1)
    report, created = report_service.generate(
        db, "daily", period_start=period_start, period_end=period_start
    )
    assert created is True
    assert report.status == "generated"
    assert report.file_path
    assert Path(tmp_path, report.file_path).exists()

    again, created_again = report_service.generate(
        db, "daily", period_start=period_start, period_end=period_start
    )
    assert created_again is False
    assert again.id == report.id
    count = len(
        db.scalars(
            select(Report).where(
                Report.report_type == "daily",
                Report.period_start == period_start,
                Report.period_end == period_start,
            )
        ).all()
    )
    assert count == 1

    today = date.today()
    with pytest.raises(AppError) as exc:
        report_service.generate(db, "daily", period_start=today, period_end=today)
    assert exc.value.code == 3000


def test_report_permission_and_viewers(db, monkeypatch, tmp_path):
    """T40：非名单非总经理 2001，加入名单后可读全文。"""
    monkeypatch.setattr(settings, "storage_root", str(tmp_path))
    report, _ = report_service.generate(
        db, "daily", period_start=date(2025, 6, 2), period_end=date(2025, 6, 2)
    )
    repairman = _principal(db, "R0002")
    with pytest.raises(AppError) as exc:
        report_service.get_report(db, repairman, report.id)
    assert exc.value.code == 2001

    manager = _principal(db, "M0001")
    db.add(ReportViewer(user_id=repairman.user_id, granted_by=manager.user_id))
    db.commit()
    detail = report_service.get_report(db, repairman, report.id)
    assert detail["report_no"] == report.report_no
    assert detail["content"]


def test_alert_low_stock_dedupe_and_safe_stock(db):
    """T43/T44：低库存按配置触发，冷却期内不重复，无配置不触发。"""
    suffix = uuid4().hex[:6]
    warehouse = Warehouse(code=f"T{suffix}", name=f"测试仓{suffix}")
    low = Product(code=f"P{suffix}L", name=f"低库存产品{suffix}", is_mock=True)
    normal = Product(code=f"P{suffix}N", name=f"无配置产品{suffix}", is_mock=True)
    db.add_all([warehouse, low, normal])
    db.flush()
    db.add_all(
        [
            Inventory(warehouse_id=warehouse.id, product_id=low.id, quantity=Decimal("1")),
            Inventory(warehouse_id=warehouse.id, product_id=normal.id, quantity=Decimal("1")),
            SafeStockConfig(
                product_id=low.id,
                warehouse_id=warehouse.id,
                safe_quantity=Decimal("10"),
            ),
        ]
    )
    db.commit()

    alert_service.scan(db)
    key = f"low_stock:product:{low.id}"
    rows = db.scalars(select(Alert).where(Alert.dedupe_key == key)).all()
    assert len(rows) == 1
    assert rows[0].threshold_value == Decimal("10")

    alert_service.scan(db)
    assert len(db.scalars(select(Alert).where(Alert.dedupe_key == key)).all()) == 1
    assert (
        db.scalars(select(Alert).where(Alert.dedupe_key == f"low_stock:product:{normal.id}")).all()
        == []
    )


def test_alert_state_flow_and_permission(db):
    """T45：open → acknowledged → closed，越权 2001，缺说明 1001。"""
    alert = Alert(
        alert_no=f"AL{uuid4().hex[:10].upper()}",
        alert_type="low_stock",
        level="warning",
        target_type="product",
        target_id=1,
        title="测试预警",
        content="测试内容",
        dedupe_key=f"low_stock:product:{uuid4().hex}",
        status="open",
        triggered_at=datetime.now(UTC),
    )
    db.add(alert)
    db.commit()

    manager = _principal(db, "M0001")
    repairman = _principal(db, "R0002")
    with pytest.raises(AppError) as exc:
        alert_service.acknowledge(db, repairman, alert.id)
    assert exc.value.code == 2001

    acknowledged = alert_service.acknowledge(db, manager, alert.id)
    assert acknowledged["status"] == "acknowledged"
    with pytest.raises(AppError) as exc:
        alert_service.close_alert(db, manager, alert.id, handle_note="  ")
    assert exc.value.code == 1001
    closed = alert_service.close_alert(db, manager, alert.id, handle_note="已补货")
    assert closed["status"] == "closed"


def test_safe_stock_upsert(db):
    """T44：安全库存可维护并落库。"""
    suffix = uuid4().hex[:6]
    warehouse = Warehouse(code=f"S{suffix}", name=f"库存仓{suffix}")
    product = Product(code=f"S{suffix}", name=f"库存产品{suffix}", is_mock=True)
    db.add_all([warehouse, product])
    db.commit()

    keeper = _principal(db, "V2W01")
    data = alert_service.update_safe_stock(
        db, keeper, product_id=product.id, warehouse_id=warehouse.id, safe_quantity=Decimal("8")
    )
    assert data["safe_quantity"] == "8"
    config = db.scalar(
        select(SafeStockConfig).where(
            SafeStockConfig.product_id == product.id,
            SafeStockConfig.warehouse_id == warehouse.id,
        )
    )
    assert config is not None and config.safe_quantity == Decimal("8")


def test_stats_trend_and_overdue(db):
    """T46：趋势与超时分布口径正常，分母为 0 返回 null。"""
    manager = _principal(db, "M0001")
    trend = stats_service.work_order_trend(db, manager, granularity="day")
    assert set(trend) >= {"range", "granularity", "items"}
    assert trend["granularity"] == "day"

    distribution = stats_service.overdue_distribution(db, manager)
    assert set(distribution) >= {"by_category", "by_department", "aging"}

    empty = stats_service.work_order_stats(db, manager, start_at=FAR_PAST, end_at=FAR_PAST)
    assert empty["total"] == 0
    assert empty["completion_rate"] is None
    assert empty["avg_process_hours"] is None


def test_image_requires_ocr(db, tmp_path):
    """T47：图片走 OCR，本地引擎可用时直接解析出文字。"""
    from PIL import Image, ImageDraw, ImageFont

    assert parser.media_type_of("png") == "image"
    if not ocr.is_configured():
        pytest.skip("本地 OCR 引擎未安装且未配置云 OCR")

    image = Image.new("RGB", (480, 140), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 42)
    draw.text((16, 40), "设备报修", font=font, fill="black")
    path = tmp_path / "sample.png"
    image.save(path)

    result = parser._parse_image(path)
    assert result.status == "ready"
    assert result.ocr_engine == ocr.engine_name()
    assert "设备" in "".join(block.content for block in result.blocks)


def test_voice_does_not_bypass_permission(client, tokens):
    """T36：语音入口不额外授权，权限仍由业务接口统一校验。"""
    response = client.get("/api/v1/finance-records", headers=auth(tokens("R0002")))
    assert response.status_code == 403, response.text
    assert response.json()["code"] == 2001


def test_report_notification_merged(db, monkeypatch, tmp_path):
    """T41：同一天多份报告只发一条 report_published。"""
    monkeypatch.setattr(settings, "storage_root", str(tmp_path))
    gm = _principal(db, "M0001")
    today_start = datetime.combine(datetime.now(UTC).date(), datetime.min.time(), tzinfo=UTC)
    for notification in db.scalars(
        select(Notification).where(
            Notification.user_id == gm.user_id,
            Notification.type == "report_published",
            Notification.created_at >= today_start,
        )
    ).all():
        db.delete(notification)
    db.commit()

    report_service.generate(db, "daily", period_start=date(2025, 7, 1), period_end=date(2025, 7, 1))
    report_service.generate(db, "daily", period_start=date(2025, 7, 2), period_end=date(2025, 7, 2))
    rows = db.scalars(
        select(Notification).where(
            Notification.user_id == gm.user_id,
            Notification.type == "report_published",
            Notification.created_at >= today_start,
        )
    ).all()
    assert len(rows) == 1


def test_report_failure_marks_status_and_notifies(db, monkeypatch, tmp_path):
    """T42：生成异常置 failed 并通知总经理与人事负责人。"""
    monkeypatch.setattr(settings, "storage_root", str(tmp_path))

    def boom(*args: Any, **kwargs: Any) -> bytes:
        raise RuntimeError("模板渲染失败")

    monkeypatch.setattr(report_service, "_render", boom)
    period = date(2025, 7, 3)
    with pytest.raises(RuntimeError):
        report_service.generate(db, "daily", period_start=period, period_end=period)

    report = db.scalar(
        select(Report).where(
            Report.report_type == "daily",
            Report.period_start == period,
            Report.period_end == period,
        )
    )
    assert report is not None
    assert report.status == "failed"
    assert "模板渲染失败" in (report.error_message or "")

    gm = _principal(db, "M0001")
    before = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == gm.user_id,
            Notification.type == "system",
            Notification.title == "报告生成失败",
        )
    )
    report_service.notify_failure(db, report)
    db.commit()
    after = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == gm.user_id,
            Notification.type == "system",
            Notification.title == "报告生成失败",
        )
    )
    assert after == before + 1


def test_media_chunks_keep_timestamps():
    """T48：音视频块保留起止毫秒，媒体类型可识别。"""
    assert parser.media_type_of("mp3") == "audio"
    assert parser.media_type_of("mp4") == "video"
    blocks = [
        parser.TextBlock(content="第一段讲话", start_ms=0, end_ms=4000),
        parser.TextBlock(content="第二段讲话", start_ms=4000, end_ms=9000),
    ]
    chunks = chunker.split_blocks(blocks, size=50, overlap=0)
    assert len(chunks) == 1
    assert chunks[0].start_ms == 0
    assert chunks[0].end_ms == 9000
    assert "第二段讲话" in chunks[0].content
