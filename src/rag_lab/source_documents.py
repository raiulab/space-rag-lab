from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol

from .models import Chunk
from .text import normalize_text, split_sentences


ContentKind = Literal["text", "heading", "table", "figure"]


@dataclass(frozen=True)
class ContentBlock:
    """A single extracted unit before it is split into retrieval chunks."""

    block_id: str
    kind: ContentKind
    text: str
    section: str
    extraction_method: str
    confidence: float | None = None
    bbox: tuple[float, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourcePage:
    """Extracted content for one source page. Page numbers are one-based."""

    page: int
    blocks: list[ContentBlock] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "blocks": [block.to_dict() for block in self.blocks],
        }


@dataclass(frozen=True)
class SourceDocument:
    """Format-neutral document produced by an ingestion adapter."""

    document_id: str
    title: str
    source: str
    media_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    pages: list[SourcePage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "source": self.source,
            "media_type": self.media_type,
            "metadata": self.metadata,
            "pages": [page.to_dict() for page in self.pages],
        }


class SourceAdapter(Protocol):
    """Contract implemented by format-specific extractors."""

    def supports(self, media_type: str, filename: str) -> bool: ...

    def extract(self, *args: Any, **kwargs: Any) -> SourceDocument: ...


def _split_oversized_part(part: str, chunk_size: int) -> list[str]:
    return [part[start : start + chunk_size] for start in range(0, len(part), chunk_size)]


def split_block_text(text: str, chunk_size: int) -> list[str]:
    """Split normalized text deterministically without losing oversized sentences."""

    if chunk_size < 1:
        raise ValueError("chunk_size は1以上で指定してください")

    normalized = normalize_text(text)
    if not normalized:
        return []

    parts: list[str] = []
    for sentence in split_sentences(normalized):
        parts.extend(_split_oversized_part(sentence, chunk_size))

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for part in parts:
        added = len(part) + (1 if current else 0)
        if current and current_length + added > chunk_size:
            chunks.append("\n".join(current))
            current = []
            current_length = 0
        current.append(part)
        current_length += len(part) + (1 if len(current) > 1 else 0)
    if current:
        chunks.append("\n".join(current))
    return chunks


def chunk_source_document(document: SourceDocument, chunk_size: int = 650) -> list[Chunk]:
    """Convert a format-neutral source document into existing ``Chunk`` records."""

    chunks: list[Chunk] = []
    sequence = 1
    for page in document.pages:
        for block in page.blocks:
            block_metadata = {
                **document.metadata,
                "media_type": document.media_type,
                "content_kind": block.kind,
                "source_block_id": block.block_id,
                "extraction_method": block.extraction_method,
            }
            if block.confidence is not None:
                block_metadata["confidence"] = block.confidence
            if block.bbox is not None:
                block_metadata["bbox"] = block.bbox

            for text in split_block_text(block.text, chunk_size):
                chunks.append(
                    Chunk(
                        chunk_id=(
                            f"{document.document_id}:p{page.page}:{sequence:03d}"
                        ),
                        document_id=document.document_id,
                        title=document.title,
                        page=page.page,
                        section=block.section,
                        text=text,
                        source=document.source,
                        metadata=block_metadata,
                    )
                )
                sequence += 1
    return chunks
