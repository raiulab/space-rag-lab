from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from .models import Chunk
from .text import normalize_text


PAGE_MARKER_RE = re.compile(r"<!--\s*page:\s*(\d+)\s*-->", re.IGNORECASE)
HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$")


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    metadata: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip().strip('"')
    return metadata, text[end + 5 :]


def split_pages(text: str) -> list[tuple[int, str]]:
    matches = list(PAGE_MARKER_RE.finditer(text))
    if not matches:
        return [(1, text)]
    pages: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        pages.append((int(match.group(1)), text[start:end]))
    return pages


def _page_blocks(page_text: str) -> list[tuple[str, str]]:
    section = "本文"
    blocks: list[tuple[str, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        block = normalize_text("\n".join(buffer))
        if block:
            blocks.append((section, block))
        buffer = []

    for line in page_text.splitlines():
        heading = HEADING_RE.match(line.strip())
        if heading:
            flush()
            section = heading.group(1).strip()
        elif line.strip():
            buffer.append(line.strip())
        else:
            flush()
    flush()
    return blocks


def chunk_document(path: Path, chunk_size: int = 650) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")
    metadata, body = parse_front_matter(raw)
    document_id = metadata.get("document_id", path.stem)
    title = metadata.get("title", path.stem.replace("_", " "))
    source = metadata.get("source", path.name)
    extra = {
        key: value
        for key, value in metadata.items()
        if key not in {"document_id", "title", "source"}
    }

    chunks: list[Chunk] = []
    sequence = 1
    for page, page_text in split_pages(body):
        for section, block in _page_blocks(page_text):
            paragraphs = [part.strip() for part in block.split("\n") if part.strip()]
            current: list[str] = []
            current_length = 0
            for paragraph in paragraphs:
                added = len(paragraph) + (1 if current else 0)
                if current and current_length + added > chunk_size:
                    chunks.append(
                        Chunk(
                            chunk_id=f"{document_id}:p{page}:{sequence:03d}",
                            document_id=document_id,
                            title=title,
                            page=page,
                            section=section,
                            text="\n".join(current),
                            source=source,
                            metadata=extra,
                        )
                    )
                    sequence += 1
                    current = []
                    current_length = 0
                current.append(paragraph)
                current_length += added
            if current:
                chunks.append(
                    Chunk(
                        chunk_id=f"{document_id}:p{page}:{sequence:03d}",
                        document_id=document_id,
                        title=title,
                        page=page,
                        section=section,
                        text="\n".join(current),
                        source=source,
                        metadata=extra,
                    )
                )
                sequence += 1
    return chunks


def collect_chunks(raw_dir: Path, chunk_size: int = 650) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(raw_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
            chunks.extend(chunk_document(path, chunk_size=chunk_size))
    return chunks


def write_chunks(chunks: Iterable[Chunk], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")


def load_chunks(path: Path) -> list[Chunk]:
    with path.open(encoding="utf-8") as handle:
        return [Chunk.from_dict(json.loads(line)) for line in handle if line.strip()]
