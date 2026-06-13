from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class ChunkStrategy(StrEnum):
    MARKDOWN_HEADING = "md_heading"
    CODE_FUNCTION = "code_function"
    PARAGRAPH = "paragraph"
    TOKEN_CAP = "token_cap"


@dataclass
class Chunk:
    content: str
    token_count: int
    metadata: dict = field(default_factory=dict)


def _count_tokens(text: str) -> int:
    return max(1, len(text) // 4)


_PARA_BREAK = re.compile(r"\n\s*\n")


def _split_by_paragraph(text: str) -> list[str]:
    parts = _PARA_BREAK.split(text)
    return [p.strip() for p in parts if p.strip()]


_HEADING = re.compile(r"^(#{1,6}\s)", re.MULTILINE)


def _split_by_markdown_heading(text: str) -> list[str]:
    matches = list(_HEADING.finditer(text))
    if not matches:
        return _split_by_paragraph(text)
    out: list[str] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        piece = text[start:end].strip()
        if piece:
            out.append(piece)
    return out


_CODE_DEF = re.compile(
    r"^(def |class |func |func\s*\(|function |public\s+|private\s+|protected\s+)",
    re.MULTILINE,
)


def _split_by_code_function(text: str) -> list[str]:
    matches = list(_CODE_DEF.finditer(text))
    if not matches:
        return _split_by_paragraph(text)
    out: list[str] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        piece = text[start:end].strip()
        if piece:
            out.append(piece)
    return out


_PRIMARY_BY_FILE_TYPE: dict[str, ChunkStrategy] = {
    "md": ChunkStrategy.MARKDOWN_HEADING,
    "py": ChunkStrategy.CODE_FUNCTION,
    "go": ChunkStrategy.CODE_FUNCTION,
    "java": ChunkStrategy.CODE_FUNCTION,
    "js": ChunkStrategy.CODE_FUNCTION,
    "ts": ChunkStrategy.CODE_FUNCTION,
}


def _split_by_tokens(text: str, max_tokens: int, overlap: int) -> list[str]:
    if not text.strip():
        return []
    # Use the same char/4 heuristic as _count_tokens to stay aligned.
    char_budget = max_tokens * 4
    overlap_chars = overlap * 4
    if len(text) <= char_budget:
        return [text]
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(i + char_budget, n)
        # Try to break on a whitespace if not at the boundary
        if end < n:
            ws = text.rfind(" ", i, end)
            if ws > i:
                end = ws
        piece = text[i:end]
        if piece.strip():
            out.append(piece)
        if end >= n:
            break
        i = end - overlap_chars if overlap_chars > 0 else end
        if i <= 0:
            i = end
    return out


@dataclass
class HybridChunker:
    max_tokens: int = 800
    overlap_tokens: int = 100
    primary: ChunkStrategy | None = None
    fallback: ChunkStrategy = ChunkStrategy.TOKEN_CAP

    def chunk(self, text: str, *, file_type: str) -> list[Chunk]:
        if not text.strip():
            return []
        strategy = self.primary or _PRIMARY_BY_FILE_TYPE.get(file_type, ChunkStrategy.PARAGRAPH)
        if strategy == ChunkStrategy.MARKDOWN_HEADING:
            pieces = _split_by_markdown_heading(text)
        elif strategy == ChunkStrategy.CODE_FUNCTION:
            pieces = _split_by_code_function(text)
        elif strategy == ChunkStrategy.PARAGRAPH:
            pieces = _split_by_paragraph(text)
        else:
            pieces = _split_by_tokens(text, self.max_tokens, 0)

        # 任一片超 max_tokens → 用 fallback 再切
        out: list[str] = []
        for p in pieces:
            if _count_tokens(p) > self.max_tokens:
                out.extend(_split_by_tokens(p, self.max_tokens, self.overlap_tokens))
            else:
                out.append(p)
        return [
            Chunk(content=p, token_count=_count_tokens(p), metadata={"strategy": strategy.value})
            for p in out
            if p.strip()
        ]
