from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

from .generation import make_generator
from .pipeline import RAGPipeline
from .retrieval import Retriever


LOGGER = logging.getLogger(__name__)
MIN_QUESTION_LENGTH = 2
MAX_QUESTION_LENGTH = 500


@lru_cache(maxsize=1)
def _pipeline() -> RAGPipeline:
    task_root = Path(__file__).resolve().parents[2]
    return RAGPipeline(
        Retriever.from_path(
            Path(os.environ.get("RAG_INDEX_PATH", task_root / "data/index/index.jsonl"))
        ),
        make_generator(os.environ.get("RAG_LAB_GENERATOR", "bedrock")),
        Path(
            os.environ.get(
                "RAG_PROMPT_PATH", task_root / "prompts/answer_v2_grounded.txt"
            )
        ),
        search_mode=os.environ.get("RAG_SEARCH_MODE", "hybrid"),
        top_k=int(os.environ.get("RAG_TOP_K", "5")),
    )


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def handle_request(
    event: dict[str, Any],
    pipeline_factory: Callable[[], RAGPipeline],
) -> dict[str, Any]:
    """Handle one API Gateway event with an injectable local pipeline factory."""

    try:
        raw_body = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            raw_body = base64.b64decode(raw_body, validate=True).decode("utf-8")
        body = json.loads(raw_body)
        if not isinstance(body, dict):
            return _response(400, {"error": "JSONオブジェクトを指定してください"})
        question = str(body.get("question", "")).strip()
        if not MIN_QUESTION_LENGTH <= len(question) <= MAX_QUESTION_LENGTH:
            return _response(
                400,
                {
                    "error": (
                        f"question は{MIN_QUESTION_LENGTH}文字以上"
                        f"{MAX_QUESTION_LENGTH}文字以下で指定してください"
                    )
                },
            )
        return _response(200, pipeline_factory().ask(question).to_dict())
    except (binascii.Error, json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return _response(400, {"error": "JSON形式のbodyを指定してください"})
    except Exception as error:
        LOGGER.error("Lambda request failed: %s", type(error).__name__)
        return _response(
            500,
            {
                "error": "internal_server_error",
                "message": "リクエスト処理に失敗しました",
            },
        )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    del context
    return handle_request(event, _pipeline)
