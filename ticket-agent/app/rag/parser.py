"""文档解析：只做文本抽取与定位，不写数据库。"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.errors import AppError

SUPPORTED_EXTENSIONS = frozenset(
    {
        "pdf",
        "docx",
        "xlsx",
        "csv",
        "md",
        "txt",
        "png",
        "jpg",
        "jpeg",
        "mp3",
        "wav",
        "mp4",
    }
)
LEGACY_EXTENSIONS = frozenset({"doc", "xls"})
IMAGE_EXTENSIONS = frozenset({"png", "jpg", "jpeg"})
MEDIA_EXTENSIONS = frozenset({"mp3", "wav", "mp4"})


@dataclass(slots=True)
class TextBlock:
    content: str
    page_no: int | None = None
    sheet_name: str | None = None
    row_no: int | None = None
    paragraph_no: int | None = None
    heading: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None


@dataclass(slots=True)
class ParseResult:
    status: str
    blocks: list[TextBlock]
    message: str | None = None
    transcript: Any | None = None
    ocr_engine: str | None = None


def media_type_of(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in {"mp3", "wav"}:
        return "audio"
    if ext == "mp4":
        return "video"
    return "document"


def parse_file(path: Path, ext: str, min_chars_per_page: int) -> ParseResult:
    ext = ext.lower().lstrip(".")
    if ext == "pdf":
        return _parse_pdf(path, min_chars_per_page)
    if ext == "docx":
        return _parse_docx(path)
    if ext == "xlsx":
        return _parse_xlsx(path)
    if ext == "csv":
        return _parse_csv(path)
    if ext == "md":
        return _parse_markdown(path)
    if ext == "txt":
        return _parse_text(path)
    if ext in IMAGE_EXTENSIONS:
        return _parse_image(path)
    if ext in MEDIA_EXTENSIONS:
        return _parse_media(path, ext)
    raise AppError(1004, "不支持的文件类型", 400)


def _parse_image(path: Path) -> ParseResult:
    from app.rag import ocr

    if not ocr.is_configured():
        return ParseResult("failed", [], "OCR 服务未配置")
    try:
        return ParseResult("ready", ocr.ocr_image(path), ocr_engine=ocr.engine_name() or "")
    except AppError as exc:
        return ParseResult("failed", [], exc.message)


def _parse_media(path: Path, ext: str) -> ParseResult:
    from app.rag import transcriber

    result, blocks = transcriber.transcribe_media(path, ext)
    return ParseResult("ready", blocks, transcript=result)


def _ready(blocks: list[TextBlock]) -> ParseResult:
    if not blocks:
        return ParseResult("failed", [], "未抽取到文本内容")
    return ParseResult("ready", blocks)


def _parse_pdf(path: Path, min_chars_per_page: int) -> ParseResult:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    blocks: list[TextBlock] = []
    total_chars = 0
    for page_no, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        total_chars += len(text)
        if text:
            blocks.append(TextBlock(content=text, page_no=page_no))
    pages = len(reader.pages)
    if pages and total_chars / pages < min_chars_per_page:
        from app.rag import ocr

        if ocr.is_configured():
            try:
                ocr_blocks = ocr.ocr_pdf(path)
            except AppError:
                ocr_blocks = []
            if ocr_blocks:
                return ParseResult("ready", ocr_blocks, ocr_engine=ocr.engine_name() or "")
        return ParseResult("need_ocr", [], "该文档为扫描件，暂不支持检索")
    if not blocks:
        from app.rag import ocr

        if ocr.is_configured():
            try:
                ocr_blocks = ocr.ocr_pdf(path)
            except AppError:
                ocr_blocks = []
            if ocr_blocks:
                return ParseResult("ready", ocr_blocks, ocr_engine=ocr.engine_name() or "")
        return ParseResult("need_ocr", [], "该文档为扫描件，暂不支持检索")
    return _ready(blocks)


def _parse_docx(path: Path) -> ParseResult:
    import docx

    document = docx.Document(str(path))
    blocks: list[TextBlock] = []
    heading: str | None = None
    for index, paragraph in enumerate(document.paragraphs, start=1):
        text = paragraph.text.strip()
        if not text:
            continue
        style = paragraph.style.name if paragraph.style is not None else ""
        if style.startswith("Heading") or style == "Title":
            heading = text
        blocks.append(TextBlock(content=text, paragraph_no=index, heading=heading))
    for table_no, table in enumerate(document.tables, start=1):
        for row_no, row in enumerate(table.rows, start=1):
            text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if text:
                blocks.append(TextBlock(content=text, sheet_name=f"表格{table_no}", row_no=row_no))
    return _ready(blocks)


def _parse_xlsx(path: Path) -> ParseResult:
    import openpyxl

    workbook = openpyxl.load_workbook(filename=str(path), read_only=True, data_only=True)
    blocks: list[TextBlock] = []
    for sheet in workbook.worksheets:
        for row_no, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            cells = [str(value) for value in row if value is not None and str(value).strip()]
            if cells:
                blocks.append(
                    TextBlock(content=" | ".join(cells), sheet_name=sheet.title, row_no=row_no)
                )
    workbook.close()
    return _ready(blocks)


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _parse_csv(path: Path) -> ParseResult:
    text = _decode(path.read_bytes())
    reader = csv.reader(io.StringIO(text))
    blocks: list[TextBlock] = []
    for row_no, row in enumerate(reader, start=1):
        cells = [cell.strip() for cell in row if cell.strip()]
        if cells:
            blocks.append(TextBlock(content=" | ".join(cells), row_no=row_no))
    return _ready(blocks)


def _parse_markdown(path: Path) -> ParseResult:
    lines = _decode(path.read_bytes()).splitlines()
    blocks: list[TextBlock] = []
    heading: str | None = None
    paragraph_no = 0
    for line in lines:
        text = line.strip()
        if not text:
            continue
        paragraph_no += 1
        if text.startswith("#"):
            heading = text.lstrip("#").strip() or None
        blocks.append(TextBlock(content=text, paragraph_no=paragraph_no, heading=heading))
    return _ready(blocks)


def _parse_text(path: Path) -> ParseResult:
    text = _decode(path.read_bytes())
    blocks: list[TextBlock] = []
    paragraph_no = 0
    for chunk in text.split("\n\n"):
        content = chunk.strip()
        if not content:
            continue
        paragraph_no += 1
        blocks.append(TextBlock(content=content, paragraph_no=paragraph_no))
    return _ready(blocks)
