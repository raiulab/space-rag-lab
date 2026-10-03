from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..ingest import collect_chunks, load_chunks
from ..models import Chunk


DATASET_ID_RE = re.compile(r"^(?:bundled|ds_[A-Za-z0-9_-]{1,64})$")


class LearningDatasetError(ValueError):
    """Raised when a Lab 1 dataset cannot safely be reused."""


@dataclass(frozen=True)
class LearningDataset:
    dataset_id: str
    label: str
    source_kind: str
    chunks: tuple[Chunk, ...]


@dataclass(frozen=True)
class DatasetOption:
    dataset_id: str
    label: str
    source_kind: str
    chunk_count: int


def bundled_dataset(raw_dir: Path, *, chunk_size: int = 650) -> LearningDataset:
    chunks = tuple(collect_chunks(raw_dir, chunk_size=chunk_size))
    if not chunks:
        raise LearningDatasetError("付属データからチャンクを作成できません")
    return LearningDataset(
        dataset_id="bundled",
        label="付属の宇宙技術レポート",
        source_kind="bundled_markdown_text",
        chunks=chunks,
    )


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LearningDatasetError("datasetのmanifestを読み取れません") from error
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise LearningDatasetError("対応していないdataset schemaです")
    return value


def _dataset_label(dataset_id: str, manifest: dict[str, Any]) -> str:
    display = (
        manifest.get("original_filename")
        or manifest.get("document_id")
        or ", ".join(manifest.get("document_ids", [])[:2])
        or dataset_id
    )
    return f"保存済み: {display}"


def list_saved_datasets(workspace: Path) -> list[DatasetOption]:
    datasets_root = workspace / "datasets"
    if not datasets_root.is_dir():
        return []
    options: list[DatasetOption] = []
    for dataset_path in sorted(datasets_root.iterdir()):
        dataset_id = dataset_path.name
        if not dataset_path.is_dir() or not DATASET_ID_RE.fullmatch(dataset_id):
            continue
        try:
            manifest = _read_manifest(dataset_path / "manifest.json")
            chunks = load_chunks(dataset_path / "processed" / "chunks.jsonl")
        except (LearningDatasetError, OSError, ValueError, KeyError, TypeError):
            continue
        if not chunks:
            continue
        options.append(
            DatasetOption(
                dataset_id=dataset_id,
                label=_dataset_label(dataset_id, manifest),
                source_kind=str(manifest.get("source_kind", "pdf")),
                chunk_count=len(chunks),
            )
        )
    return options


def load_saved_dataset(workspace: Path, dataset_id: str) -> LearningDataset:
    if not DATASET_ID_RE.fullmatch(dataset_id) or dataset_id == "bundled":
        raise LearningDatasetError("dataset IDが不正です")
    dataset_path = workspace / "datasets" / dataset_id
    try:
        manifest = _read_manifest(dataset_path / "manifest.json")
        chunks = tuple(load_chunks(dataset_path / "processed" / "chunks.jsonl"))
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise LearningDatasetError("datasetのチャンクを読み取れません") from error
    if not chunks:
        raise LearningDatasetError("datasetにチャンクがありません")
    return LearningDataset(
        dataset_id=dataset_id,
        label=_dataset_label(dataset_id, manifest),
        source_kind=str(manifest.get("source_kind", "pdf")),
        chunks=chunks,
    )
