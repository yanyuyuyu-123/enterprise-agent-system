"""按字符数分块，保留页码/工作表行号/段落号定位。"""

from __future__ import annotations

from dataclasses import dataclass

from app.rag.parser import TextBlock


@dataclass(slots=True)
class ChunkData:
    content: str
    chunk_index: int
    heading: str | None = None
    page_no: int | None = None
    sheet_name: str | None = None
    row_no: int | None = None
    paragraph_no: int | None = None
    start_ms: int | None = None
    end_ms: int | None = None


def _windows(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]
    step = max(size - overlap, 1)
    return [text[start : start + size] for start in range(0, len(text), step)]


def split_blocks(blocks: list[TextBlock], size: int, overlap: int) -> list[ChunkData]:
    size = max(size, 50)
    overlap = max(min(overlap, size - 1), 0)
    chunks: list[ChunkData] = []
    current: list[str] = []
    current_len = 0
    locator: TextBlock | None = None
    last_block: TextBlock | None = None
    carry = ""

    def emit() -> None:
        nonlocal current, current_len, locator, carry, last_block
        if not current:
            return
        content = "\n".join(current).strip()
        body = f"{carry}\n{content}".strip() if carry else content
        if body:
            chunks.append(
                ChunkData(
                    content=body,
                    chunk_index=len(chunks),
                    heading=locator.heading if locator else None,
                    page_no=locator.page_no if locator else None,
                    sheet_name=locator.sheet_name if locator else None,
                    row_no=locator.row_no if locator else None,
                    paragraph_no=locator.paragraph_no if locator else None,
                    start_ms=locator.start_ms if locator else None,
                    end_ms=last_block.end_ms if last_block else None,
                )
            )
            carry = body[-overlap:] if overlap else ""
        current = []
        current_len = 0
        locator = None
        last_block = None

    for block in blocks:
        for piece in _windows(block.content, size, overlap):
            if current and current_len + len(piece) + 1 > size:
                emit()
            if not current:
                locator = block
            current.append(piece)
            last_block = block
            current_len += len(piece) + 1
    emit()
    return chunks
