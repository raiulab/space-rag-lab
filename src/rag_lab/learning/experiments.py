from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .checks import LabCompletion
from .progress import ProgressStore, ProgressStoreError, SCHEMA_VERSION, write_json_atomic


LAB_ID_RE = re.compile(r"^lab[1-8]$")


class LearningRunError(Exception):
    """Raised when a learning experiment cannot be recorded safely."""


@dataclass(frozen=True)
class SavedLearningRun:
    lab_id: str
    run_id: str
    path: Path
    completion: LabCompletion


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def save_learning_run(
    workspace: Path,
    *,
    lab_id: str,
    dataset_id: str,
    completion: LabCompletion,
    prediction: str,
    observation: str,
    settings: dict[str, Any],
    summary: dict[str, Any],
) -> SavedLearningRun:
    """Save settings and metrics, but never duplicate source chunk text."""

    if not LAB_ID_RE.fullmatch(lab_id):
        raise LearningRunError("Lab IDが不正です")
    if not dataset_id or any(character in dataset_id for character in "/\\"):
        raise LearningRunError("dataset IDが不正です")

    run_id = f"run_{uuid.uuid4().hex[:16]}"
    created_at = _utc_now()
    path = workspace / "runs" / lab_id / f"{run_id}.json"
    value = {
        "schema_version": SCHEMA_VERSION,
        "lab_id": lab_id,
        "run_id": run_id,
        "dataset_id": dataset_id,
        "created_at": created_at,
        "status": completion.status,
        "prediction": prediction,
        "observation": observation,
        "settings": settings,
        "summary": summary,
        "checks": [check.to_dict() for check in completion.checks],
    }
    try:
        write_json_atomic(path, value)
        ProgressStore(workspace).update_lab(
            lab_id,
            completion=completion,
            run_id=run_id,
            updated_at=created_at,
            prediction=prediction,
            observation=observation,
            details={"dataset_id": dataset_id},
        )
    except (OSError, ProgressStoreError) as error:
        raise LearningRunError("学習記録を保存できません") from error
    return SavedLearningRun(
        lab_id=lab_id,
        run_id=run_id,
        path=path,
        completion=completion,
    )
