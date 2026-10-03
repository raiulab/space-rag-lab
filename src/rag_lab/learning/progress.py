from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Sequence

from .checks import Lab1Completion


SCHEMA_VERSION = 1


class ProgressStoreError(Exception):
    """Raised when local learning progress cannot be read or saved safely."""


def write_json_atomic(path: Path, value: Any) -> None:
    """Write JSON through a sibling temporary file, then replace atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


class ProgressStore:
    def __init__(self, workspace: Path) -> None:
        self.path = workspace / "progress.json"

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "schema_version": SCHEMA_VERSION,
                "labs": {"lab1": {"status": "not_started"}},
            }
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProgressStoreError("学習進捗を読み取れません") from error
        if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
            raise ProgressStoreError("対応していない学習進捗schemaです")
        if not isinstance(value.get("labs", {}), dict):
            raise ProgressStoreError("学習進捗のlabs形式が不正です")
        return value

    def update_lab1(
        self,
        *,
        completion: Lab1Completion,
        run_id: str,
        updated_at: str,
        prediction: str,
        observation: str,
        confirmed_warning_ids: Sequence[str],
    ) -> dict[str, Any]:
        value = self.load()
        labs = value.setdefault("labs", {})
        existing = labs.get("lab1", {})
        if not isinstance(existing, dict):
            raise ProgressStoreError("Lab 1の進捗形式が不正です")
        labs["lab1"] = {
            **existing,
            "status": completion.status,
            "last_run_id": run_id,
            "updated_at": updated_at,
            "prediction": prediction,
            "observation": observation,
            "confirmed_warning_ids": list(confirmed_warning_ids),
        }
        try:
            write_json_atomic(self.path, value)
        except OSError as error:
            raise ProgressStoreError("学習進捗を保存できません") from error
        return value
