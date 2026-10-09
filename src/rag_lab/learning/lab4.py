from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from ..generation import (
    BedrockGenerator,
    ExtractiveGenerator,
    Generator,
    render_grounded_prompt,
)
from ..models import Answer, Citation, SearchResult
from .checks import LabCompletion, make_check
from .datasets import LearningDataset
from .experiments import SavedLearningRun, save_learning_run
from .lab2 import SEARCH_MODES, build_retriever


LOGGER = logging.getLogger(__name__)
PROVIDERS = ("simulated", "bedrock")
SIMULATION_SCENARIOS = ("success", "throttling", "timeout", "invalid_model")
MIN_QUESTION_LENGTH = 2
MAX_QUESTION_LENGTH = 500
MAX_MODEL_ID_LENGTH = 512
REGION_RE = re.compile(r"^[a-z0-9-]{3,64}$")

FAILURE_MESSAGES = {
    "authentication": "AWS認証情報を確認できませんでした。認証方法を見直してください。",
    "authorization": "Bedrockを呼び出す権限がありません。IAM権限を確認してください。",
    "throttling": "呼び出し回数が制限されました。間隔を空けて再試行してください。",
    "timeout": "制限時間内に応答がありませんでした。通信状態や設定を確認してください。",
    "model_configuration": "モデルIDまたはリージョンの設定を確認してください。",
    "service_unavailable": "外部サービスへ接続できませんでした。時間を空けて確認してください。",
    "dependency": "AWS機能を使うには `python -m pip install -e '.[aws]'` が必要です。",
    "invalid_response": "外部APIの応答形式を確認できませんでした。",
    "unknown": "外部API呼び出しに失敗しました。詳細は秘密情報を除いたログで確認してください。",
}


@dataclass(frozen=True)
class ExternalCallResult:
    provider: str
    scenario: str
    status: str
    latency_ms: float
    input_chars: int
    output_chars: int
    answer: Answer | None
    failure_type: str | None
    safe_message: str | None


@dataclass(frozen=True)
class Lab4Experiment:
    dataset: LearningDataset
    question: str
    expected_external_success: bool
    search_mode: str
    top_k: int
    dimension: int
    prompt_version: str
    baseline_answer: Answer
    external_call: ExternalCallResult
    region: str


class SimulatedExternalError(Exception):
    def __init__(self, failure_type: str) -> None:
        super().__init__("simulated external API failure")
        self.failure_type = failure_type


class SimulatedExternalGenerator(Generator):
    """Offline test double for learning API success and failure paths."""

    def __init__(self, scenario: str) -> None:
        if scenario not in SIMULATION_SCENARIOS:
            raise ValueError("模擬APIのシナリオが不正です")
        self.scenario = scenario

    def generate(
        self,
        question: str,
        results: tuple[SearchResult, ...] | list[SearchResult],
        prompt_template: str,
    ) -> tuple[str, bool]:
        if self.scenario != "success":
            failure_type = {
                "throttling": "throttling",
                "timeout": "timeout",
                "invalid_model": "model_configuration",
            }[self.scenario]
            raise SimulatedExternalError(failure_type)
        return ExtractiveGenerator().generate(question, results, prompt_template)


def _client_error_code(error: Exception) -> str:
    response = getattr(error, "response", None)
    if not isinstance(response, Mapping):
        return ""
    error_value = response.get("Error", {})
    if not isinstance(error_value, Mapping):
        return ""
    code = error_value.get("Code", "")
    return str(code)


def classify_external_error(error: Exception) -> str:
    """Classify an external failure without copying its potentially secret message."""

    if isinstance(error, SimulatedExternalError):
        return error.failure_type

    code = _client_error_code(error)
    name = type(error).__name__
    combined = f"{code} {name}".lower()
    if any(token in combined for token in ("nocredentials", "partialcredentials", "credentialretrieval")):
        return "authentication"
    if any(token in combined for token in ("accessdenied", "unauthorized", "unrecognizedclient")):
        return "authorization"
    if any(token in combined for token in ("throttl", "toomanyrequests", "limitexceeded")):
        return "throttling"
    if any(token in combined for token in ("timeout", "timedout")):
        return "timeout"
    if any(token in combined for token in ("validation", "resourcenotfound", "modelnotready")):
        return "model_configuration"
    if any(token in combined for token in ("serviceunavailable", "endpointconnection", "connectionerror")):
        return "service_unavailable"
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        return "dependency"
    if isinstance(error, RuntimeError):
        message = str(error)
        if "Install the AWS extra" in message:
            return "dependency"
        if "BEDROCK_MODEL_ID" in message:
            return "model_configuration"
        if "response" in message.lower():
            return "invalid_response"
    return "unknown"


def _make_answer(
    question: str,
    text: str,
    answerable: bool,
    results: tuple[SearchResult, ...],
) -> Answer:
    citations: list[Citation] = []
    if answerable:
        citations = [
            Citation(
                chunk_id=result.chunk.chunk_id,
                document_id=result.chunk.document_id,
                title=result.chunk.title,
                page=result.chunk.page,
            )
            for result in results[:3]
        ]
    return Answer(
        question=question,
        text=text,
        citations=citations,
        answerable=answerable,
        retrieved=list(results),
    )


def _validate_model_configuration(model_id: str, region: str) -> tuple[str, str]:
    cleaned_model_id = model_id.strip()
    cleaned_region = region.strip()
    if not cleaned_model_id or len(cleaned_model_id) > MAX_MODEL_ID_LENGTH:
        raise ValueError("モデルIDを1文字以上512文字以下で入力してください")
    if any(ord(character) < 32 for character in cleaned_model_id):
        raise ValueError("モデルIDに制御文字は使用できません")
    if not REGION_RE.fullmatch(cleaned_region):
        raise ValueError("AWSリージョンの形式が不正です")
    return cleaned_model_id, cleaned_region


def run_lab4_experiment(
    dataset: LearningDataset,
    *,
    question: str,
    expected_external_success: bool,
    prompt_path: Path,
    provider: str = "simulated",
    simulation_scenario: str = "success",
    model_id: str = "",
    region: str = "ap-northeast-1",
    search_mode: str = "hybrid",
    top_k: int = 5,
    dimension: int = 384,
    bedrock_factory: Callable[..., Generator] | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> Lab4Experiment:
    cleaned_question = question.strip()
    if not MIN_QUESTION_LENGTH <= len(cleaned_question) <= MAX_QUESTION_LENGTH:
        raise ValueError("質問は2文字以上500文字以下で入力してください")
    if provider not in PROVIDERS:
        raise ValueError("外部API種別が不正です")
    if simulation_scenario not in SIMULATION_SCENARIOS:
        raise ValueError("模擬APIのシナリオが不正です")
    if search_mode not in SEARCH_MODES:
        raise ValueError("検索方式が不正です")
    if not 1 <= top_k <= 20:
        raise ValueError("top_kは1から20で指定してください")
    if dimension <= 0:
        raise ValueError("Embedding次元は1以上で指定してください")
    if not prompt_path.is_file():
        raise ValueError("プロンプトファイルが見つかりません")

    cleaned_region = ""
    cleaned_model_id = ""
    if provider == "bedrock":
        cleaned_model_id, cleaned_region = _validate_model_configuration(
            model_id, region
        )

    retriever = build_retriever(dataset.chunks, dimension)
    results = tuple(
        retriever.search(cleaned_question, top_k=top_k, mode=search_mode)
    )
    prompt_template = prompt_path.read_text(encoding="utf-8")
    baseline_text, baseline_answerable = ExtractiveGenerator().generate(
        cleaned_question,
        results,
        prompt_template,
    )
    baseline_answer = _make_answer(
        cleaned_question,
        baseline_text,
        baseline_answerable,
        results,
    )
    input_chars = len(
        render_grounded_prompt(cleaned_question, results, prompt_template)
    )

    started = clock()
    try:
        if provider == "simulated":
            generator: Generator = SimulatedExternalGenerator(simulation_scenario)
            scenario = simulation_scenario
        else:
            factory = bedrock_factory or BedrockGenerator
            generator = factory(model_id=cleaned_model_id, region=cleaned_region)
            scenario = "live"
        external_text, external_answerable = generator.generate(
            cleaned_question,
            results,
            prompt_template,
        )
        external_answer = _make_answer(
            cleaned_question,
            external_text,
            external_answerable,
            results,
        )
        elapsed_ms = round(max(clock() - started, 0.0) * 1000, 2)
        call = ExternalCallResult(
            provider=provider,
            scenario=scenario,
            status="success",
            latency_ms=elapsed_ms,
            input_chars=input_chars,
            output_chars=len(external_text),
            answer=external_answer,
            failure_type=None,
            safe_message=None,
        )
        LOGGER.info(
            "external_generation provider=%s status=success latency_ms=%.2f input_chars=%d output_chars=%d",
            provider,
            elapsed_ms,
            input_chars,
            len(external_text),
        )
    except Exception as error:
        elapsed_ms = round(max(clock() - started, 0.0) * 1000, 2)
        failure_type = classify_external_error(error)
        call = ExternalCallResult(
            provider=provider,
            scenario=simulation_scenario if provider == "simulated" else "live",
            status="failed",
            latency_ms=elapsed_ms,
            input_chars=input_chars,
            output_chars=0,
            answer=None,
            failure_type=failure_type,
            safe_message=FAILURE_MESSAGES[failure_type],
        )
        LOGGER.warning(
            "external_generation provider=%s status=failed failure_type=%s "
            "exception_type=%s latency_ms=%.2f input_chars=%d output_chars=0",
            provider,
            failure_type,
            type(error).__name__,
            elapsed_ms,
            input_chars,
        )

    return Lab4Experiment(
        dataset=dataset,
        question=cleaned_question,
        expected_external_success=expected_external_success,
        search_mode=search_mode,
        top_k=top_k,
        dimension=dimension,
        prompt_version=prompt_path.name,
        baseline_answer=baseline_answer,
        external_call=call,
        region=cleaned_region,
    )


def evaluate_lab4(
    experiment: Lab4Experiment,
    *,
    prediction: str,
    observation: str,
) -> LabCompletion:
    retrieved = experiment.baseline_answer.retrieved
    retrieved_ids = {result.chunk.chunk_id for result in retrieved}
    call = experiment.external_call
    if call.answer is None:
        external_safe = (
            call.status == "failed"
            and call.failure_type in FAILURE_MESSAGES
            and call.safe_message == FAILURE_MESSAGES[call.failure_type]
            and call.output_chars == 0
        )
    else:
        citation_ids = {citation.chunk_id for citation in call.answer.citations}
        external_safe = call.status == "success" and (
            (call.answer.answerable and bool(citation_ids) and citation_ids.issubset(retrieved_ids))
            or (not call.answer.answerable and not citation_ids)
        )

    data_checks = (
        make_check(
            "retrieval_traceable",
            bool(retrieved)
            and all(
                result.chunk.document_id
                and result.chunk.chunk_id
                and result.chunk.page >= 1
                for result in retrieved
            ),
            "外部APIへ渡す根拠から元文書とページへ戻れます",
            "検索根拠の出典情報が不足しています",
        ),
        make_check(
            "call_metrics_recorded",
            call.input_chars > 0
            and call.output_chars >= 0
            and call.latency_ms >= 0
            and call.status in {"success", "failed"},
            "入力文字数、出力文字数、応答時間、成否を記録しました",
            "外部API呼び出しの観測値が不足しています",
        ),
        make_check(
            "external_result_safe",
            external_safe,
            "成功結果または安全に分類した失敗を確認しました",
            "外部APIの回答・引用または失敗分類を確認してください",
        ),
        make_check(
            "outcome_matches_prediction",
            (call.status == "success") == experiment.expected_external_success,
            "外部APIの成否予想と実際が一致しました",
            "外部APIの成否予想と実際が異なります",
        ),
    )
    learning_checks = (
        make_check(
            "prediction_recorded",
            bool(prediction.strip()),
            "外部APIの成否と出力を予想しました",
            "実行前の予想が未記録です",
        ),
        make_check(
            "observation_recorded",
            bool(observation.strip()),
            "抽出式と外部API、または失敗処理を観察しました",
            "実行後の観察が未記録です",
        ),
    )
    checks = data_checks + learning_checks
    if not all(check.passed for check in data_checks):
        status = "needs_review"
    elif not all(check.passed for check in learning_checks):
        status = "in_progress"
    else:
        status = "completed"
    return LabCompletion(status=status, checks=checks)


def save_lab4_experiment(
    workspace: Path,
    experiment: Lab4Experiment,
    *,
    prediction: str,
    observation: str,
) -> SavedLearningRun:
    completion = evaluate_lab4(
        experiment,
        prediction=prediction,
        observation=observation,
    )
    call = experiment.external_call
    external_citations = (
        [citation.to_dict() for citation in call.answer.citations]
        if call.answer is not None
        else []
    )
    return save_learning_run(
        workspace,
        lab_id="lab4",
        dataset_id=experiment.dataset.dataset_id,
        completion=completion,
        prediction=prediction,
        observation=observation,
        settings={
            "question": experiment.question,
            "expected_external_success": experiment.expected_external_success,
            "search_mode": experiment.search_mode,
            "top_k": experiment.top_k,
            "embedding_model": f"hash-embedding-v1-{experiment.dimension}",
            "provider": call.provider,
            "scenario": call.scenario,
            "region": experiment.region,
            "prompt_version": experiment.prompt_version,
        },
        summary={
            "retrieved": [
                {
                    "rank": result.rank,
                    "chunk_id": result.chunk.chunk_id,
                    "document_id": result.chunk.document_id,
                    "page": result.chunk.page,
                }
                for result in experiment.baseline_answer.retrieved
            ],
            "baseline_answerable": experiment.baseline_answer.answerable,
            "baseline_citations": [
                citation.to_dict()
                for citation in experiment.baseline_answer.citations
            ],
            "external_status": call.status,
            "external_answerable": (
                call.answer.answerable if call.answer is not None else None
            ),
            "external_citations": external_citations,
            "latency_ms": call.latency_ms,
            "input_chars": call.input_chars,
            "output_chars": call.output_chars,
            "failure_type": call.failure_type,
        },
    )
