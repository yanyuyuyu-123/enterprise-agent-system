"""T24–T27 知识库：解析、扫描件、检索、权限隔离。"""

from __future__ import annotations

import io
import time
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, update

from app.core.config import settings
from app.core.db import SessionLocal
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.rag import embedder
from app.tasks.celery_app import celery_app
from tests.helpers import auth

DIM = 1024
WRITER = "K0001"  # 人事负责人：知识库唯一写入岗位之一


@pytest.fixture(scope="module", autouse=True)
def clean_documents():
    """清理历史运行留下的知识文档，避免旧数据影响检索断言。"""
    db = SessionLocal()
    try:
        db.execute(delete(KnowledgeChunk))
        db.execute(delete(KnowledgeDocument))
        db.commit()
    finally:
        db.close()
    yield


def ok(response) -> dict[str, Any]:
    assert response.status_code in (200, 201), response.text
    payload = response.json()
    assert payload["code"] == 0, payload
    return payload["data"]


def fail(response, status_code: int, code: int) -> None:
    assert response.status_code == status_code, response.text
    assert response.json()["code"] == code, response.text


def _fake_embed(texts: list[str], batch_size: int = 16) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        vector = [0.0] * DIM
        for char in text:
            if not char.isspace():
                vector[ord(char) % DIM] += 1.0
        norm = sum(value * value for value in vector) ** 0.5
        vectors.append([value / norm for value in vector])
    return vectors


@pytest.fixture()
def knowledge_env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "embedding_api_key", "test-key")
    monkeypatch.setattr(settings, "storage_root", str(tmp_path))
    monkeypatch.setattr(embedder, "embed_texts", _fake_embed)
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield


def _pdf_bytes(text: str) -> bytes:
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = "%PDF-1.4\n"
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n{body}\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n"
    output += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n" f"startxref\n{xref}\n%%EOF\n"
    return output.encode("latin-1")


def _docx_bytes(text: str) -> bytes:
    import docx

    document = docx.Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _xlsx_bytes(rows: list[list[str]]) -> bytes:
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "制度"
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _upload(
    client,
    token: str,
    *,
    file_name: str,
    data: bytes,
    title: str,
    visibility_scope: str = "department",
) -> dict[str, Any]:
    return ok(
        client.post(
            "/api/v1/knowledge/documents",
            data={
                "title": title,
                "category": "policy",
                "visibility_scope": visibility_scope,
            },
            files={"file": (file_name, data, "application/octet-stream")},
            headers=auth(token),
        )
    )


def _search(client, token: str, query: str) -> dict[str, Any]:
    return ok(client.post("/api/v1/knowledge/search", json={"query": query}, headers=auth(token)))


def _wait_status(
    client, token: str, document_id: int, *, expected: str, timeout: float = 20.0
) -> dict[str, Any]:
    """解析在后台线程执行，轮询到终态再断言，避免竞态。"""
    deadline = time.monotonic() + timeout
    detail: dict[str, Any] = {}
    while time.monotonic() < deadline:
        detail = ok(client.get(f"/api/v1/knowledge/documents/{document_id}", headers=auth(token)))
        if detail["status"] == expected:
            return detail
        if detail["status"] not in ("pending", "parsing"):
            return detail
        time.sleep(0.05)
    return detail


def test_t24_documents_parse_ready(client, tokens, knowledge_env) -> None:
    long_text = (
        "Company travel reimbursement policy requires invoices and approval "
        "before payment is released to employees."
    )
    samples = [
        ("pdf", _pdf_bytes(long_text)),
        ("docx", _docx_bytes("差旅报销制度：报销需提供发票与审批单。")),
        ("xlsx", _xlsx_bytes([["制度名称", "差旅报销制度"], ["审批人", "财务负责人"]])),
        ("md", "# 报销制度\n差旅报销需在出差结束后十个工作日内提交。".encode()),
        ("csv", "制度,差旅报销制度\n审批人,财务负责人\n".encode("utf-8-sig")),
    ]
    for ext, data in samples:
        document = _upload(
            client,
            tokens(WRITER),
            file_name=f"{uuid4().hex}.{ext}",
            data=data,
            title=f"解析样例-{ext}",
            visibility_scope="company",
        )
        detail = _wait_status(client, tokens(WRITER), document["id"], expected="ready")
        assert detail["status"] == "ready", detail
        assert detail["chunk_count"] > 0

    # 定位信息：PDF 页码、CSV 行号
    pdf_hit = _search(client, tokens("V2B01"), "reimbursement policy invoices")
    assert pdf_hit["found"] is True
    assert pdf_hit["items"][0]["file_name"].endswith(".pdf")
    assert pdf_hit["items"][0]["page_no"] == 1

    csv_hit = _search(client, tokens("V2B01"), "差旅报销制度")
    assert csv_hit["found"] is True
    assert any(item["row_no"] for item in csv_hit["items"])


def test_t25_scanned_pdf_need_ocr(client, tokens, knowledge_env) -> None:
    document = _upload(
        client,
        tokens(WRITER),
        file_name=f"{uuid4().hex}.pdf",
        data=_pdf_bytes("scan"),
        title="扫描件样例",
        visibility_scope="company",
    )
    detail = _wait_status(client, tokens(WRITER), document["id"], expected="need_ocr")
    assert detail["status"] == "need_ocr"
    assert detail["chunk_count"] == 0
    assert "扫描件" in detail["error_message"]

    result = _search(client, tokens("V2B01"), "scan")
    assert all(item["document_id"] != document["id"] for item in result["items"])


def test_t26_rag_sources_and_misses(client, tokens, knowledge_env) -> None:
    document = _upload(
        client,
        tokens(WRITER),
        file_name="travel-policy.md",
        data="# 差旅报销流程\n差旅报销流程规范：先审批后出行，回程后提交发票。".encode(),
        title="差旅报销流程",
        visibility_scope="company",
    )
    _wait_status(client, tokens(WRITER), document["id"], expected="ready")
    hit = _search(client, tokens("V2C01"), "差旅报销流程")
    assert hit["found"] is True
    assert hit["items"][0]["file_name"] == "travel-policy.md"
    assert hit["items"][0]["locator"]
    assert hit["message"] is None

    miss = _search(client, tokens("V2C01"), "火星天气预报")
    assert miss["found"] is False
    assert miss["items"] == []
    assert miss["message"] == "未在企业文档中找到依据"


def test_t27_department_isolation_and_delete(client, tokens, knowledge_env) -> None:
    document = _upload(
        client,
        tokens(WRITER),
        file_name="dept-secret.md",
        data="# 部门内部制度\n机密内部制度XYZ仅限本部门传阅。".encode(),
        title="部门内部制度",
    )
    _wait_status(client, tokens(WRITER), document["id"], expected="ready")
    # 其他部门看不到
    other = _search(client, tokens("V2F01"), "机密内部制度")
    assert all(item["document_id"] != document["id"] for item in other["items"])
    own = _search(client, tokens(WRITER), "机密内部制度")
    assert any(item["document_id"] == document["id"] for item in own["items"])

    # 删除后不可检索
    ok(
        client.delete(
            f"/api/v1/knowledge/documents/{document['id']}",
            headers=auth(tokens(WRITER)),
        )
    )
    after_delete = _search(client, tokens(WRITER), "机密内部制度")
    assert all(item["document_id"] != document["id"] for item in after_delete["items"])

    # 停用后不可检索
    disabled = _upload(
        client,
        tokens(WRITER),
        file_name="disabled.md",
        data="# 停用制度\n停用文档ABCD不应被检索。".encode(),
        title="停用文档",
    )
    _wait_status(client, tokens(WRITER), disabled["id"], expected="ready")
    db = SessionLocal()
    try:
        db.execute(
            update(KnowledgeDocument)
            .where(KnowledgeDocument.id == disabled["id"])
            .values(status="disabled")
        )
        db.commit()
    finally:
        db.close()
    after_disabled = _search(client, tokens(WRITER), "停用文档ABCD")
    assert all(item["document_id"] != disabled["id"] for item in after_disabled["items"])


def test_t28_only_hr_head_and_gm_can_write(client, tokens, knowledge_env) -> None:
    """知识库上传与删除只允许人事负责人和总经理操作。"""
    hr_doc = _upload(
        client,
        tokens(WRITER),
        file_name="hr-only.md",
        data="# 人事制度\n仅人事负责人可维护。".encode(),
        title="人事权限样例",
        visibility_scope="company",
    )
    _wait_status(client, tokens(WRITER), hr_doc["id"], expected="ready")

    gm_doc = _upload(
        client,
        tokens("M0001"),
        file_name="gm-only.md",
        data="# 总经理制度\n仅总经理可维护。".encode(),
        title="总经理权限样例",
        visibility_scope="company",
    )
    _wait_status(client, tokens("M0001"), gm_doc["id"], expected="ready")

    # 其他岗位既不能上传，也不能删除
    forbidden = client.post(
        "/api/v1/knowledge/documents",
        data={"title": "越权上传", "category": "policy", "visibility_scope": "company"},
        files={"file": ("forbidden.md", "# 越权\n不应成功。".encode(), "text/markdown")},
        headers=auth(tokens("V2B01")),
    )
    fail(forbidden, 403, 2001)
    fail(
        client.delete(
            f"/api/v1/knowledge/documents/{hr_doc['id']}",
            headers=auth(tokens("V2B01")),
        ),
        403,
        2001,
    )
