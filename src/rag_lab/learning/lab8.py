from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..aws_handler import handle_request
from ..generation import ExtractiveGenerator
from ..pipeline import RAGPipeline
from .checks import LabCompletion, make_check
from .datasets import LearningDataset
from .experiments import SavedLearningRun, save_learning_run
from .lab2 import build_retriever


MAX_TEMPLATE_BYTES = 1024 * 1024
FindingStatus = Literal["passed", "review"]


class InfrastructureReadinessError(ValueError):
    """Raised when the local infrastructure source cannot be inspected safely."""


@dataclass(frozen=True)
class InfrastructureFinding:
    code: str
    category: str
    status: FindingStatus
    message: str


@dataclass(frozen=True)
class Lab8Experiment:
    dataset: LearningDataset
    template_name: str
    template_sha256: str
    findings: tuple[InfrastructureFinding, ...]
    smoke_status_code: int
    smoke_answerable: bool
    smoke_citation_ids: tuple[str, ...]

    @property
    def review_finding_codes(self) -> tuple[str, ...]:
        return tuple(
            finding.code for finding in self.findings if finding.status == "review"
        )


def _integer_setting(template: str, name: str) -> int | None:
    match = re.search(rf"(?m)^\s*{re.escape(name)}:\s*[\"']?(\d+)", template)
    return int(match.group(1)) if match else None


def analyze_sam_template(template: str) -> tuple[InfrastructureFinding, ...]:
    timeout = _integer_setting(template, "Timeout")
    concurrency = _integer_setting(template, "ReservedConcurrentExecutions")
    retention = _integer_setting(template, "RetentionInDays")
    lowered = template.casefold()
    credential_pattern = re.compile(
        r"AKIA[0-9A-Z]{16}|aws_secret_access_key|secretaccesskey",
        re.IGNORECASE,
    )

    findings = (
        InfrastructureFinding(
            "no_embedded_credentials",
            "secrets",
            "passed" if not credential_pattern.search(template) else "review",
            (
                "アクセスキーや秘密鍵の埋め込みは検出されませんでした"
                if not credential_pattern.search(template)
                else "認証情報らしい文字列があります。デプロイ前に除去してください"
            ),
        ),
        InfrastructureFinding(
            "bounded_timeout",
            "cost_and_reliability",
            "passed" if timeout is not None and 1 <= timeout <= 60 else "review",
            (
                f"Lambda timeoutは{timeout}秒です"
                if timeout is not None
                else "Lambda timeoutを確認できません"
            ),
        ),
        InfrastructureFinding(
            "bounded_concurrency",
            "cost_and_reliability",
            (
                "passed"
                if concurrency is not None and 1 <= concurrency <= 10
                else "review"
            ),
            (
                f"予約同時実行数は{concurrency}です"
                if concurrency is not None
                else "予約同時実行数を確認できません"
            ),
        ),
        InfrastructureFinding(
            "bounded_log_retention",
            "logging",
            "passed" if retention is not None and 1 <= retention <= 30 else "review",
            (
                f"ログ保持期間は{retention}日です"
                if retention is not None
                else "ログ保持期間を確認できません"
            ),
        ),
        InfrastructureFinding(
            "tracing_enabled",
            "logging",
            "passed" if "tracing: active" in lowered else "review",
            (
                "Lambda tracingは有効です"
                if "tracing: active" in lowered
                else "Lambda tracingが有効か確認してください"
            ),
        ),
        InfrastructureFinding(
            "http_authentication",
            "access_control",
            "passed" if re.search(r"(?m)^\s+Auth:\s*$", template) else "review",
            (
                "HTTP APIの認証設定があります"
                if re.search(r"(?m)^\s+Auth:\s*$", template)
                else "HTTP API認証は未設定です。公開用途では認証を追加してください"
            ),
        ),
        InfrastructureFinding(
            "bedrock_resource_scope",
            "least_privilege",
            (
                "review"
                if "foundation-model/*" in template
                or "inference-profile/*" in template
                else "passed"
            ),
            (
                "Bedrock Resourceにワイルドカードがあります。利用モデルへ絞ってください"
                if "foundation-model/*" in template
                or "inference-profile/*" in template
                else "Bedrock Resourceは特定モデルへ限定されています"
            ),
        ),
        InfrastructureFinding(
            "budget_guardrail",
            "cost",
            "passed" if "AWS::Budgets::Budget" in template else "review",
            (
                "予算リソースがテンプレートにあります"
                if "AWS::Budgets::Budget" in template
                else "予算通知はテンプレート外です。デプロイ前に別途設定してください"
            ),
        ),
    )
    return findings


def _local_smoke_response(
    dataset: LearningDataset,
    prompt_path: Path,
) -> dict[str, object]:
    retriever = build_retriever(dataset.chunks, 384)
    pipeline = RAGPipeline(
        retriever=retriever,
        generator=ExtractiveGenerator(),
        prompt_path=prompt_path,
        search_mode="hybrid",
        top_k=5,
    )
    response = handle_request(
        {
            "body": json.dumps(
                {
                    "question": (
                        "火星の砂嵐で太陽電池出力は何%まで低下しましたか？"
                    )
                },
                ensure_ascii=False,
            )
        },
        lambda: pipeline,
    )
    try:
        body = json.loads(str(response["body"]))
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise InfrastructureReadinessError(
            "ローカルLambda応答の形式が不正です"
        ) from error
    return {"status_code": int(response["statusCode"]), "body": body}


def run_lab8_readiness(
    dataset: LearningDataset,
    *,
    template_path: Path,
    prompt_path: Path,
) -> Lab8Experiment:
    if not template_path.is_file() or template_path.is_symlink():
        raise InfrastructureReadinessError("SAMテンプレートが見つかりません")
    try:
        if template_path.stat().st_size > MAX_TEMPLATE_BYTES:
            raise InfrastructureReadinessError(
                "SAMテンプレートは1 MB以下にしてください"
            )
        template_bytes = template_path.read_bytes()
        template = template_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise InfrastructureReadinessError(
            "SAMテンプレートを読み取れません"
        ) from error
    if not prompt_path.is_file():
        raise InfrastructureReadinessError("プロンプトが見つかりません")

    smoke = _local_smoke_response(dataset, prompt_path)
    body = smoke["body"]
    if not isinstance(body, dict):
        raise InfrastructureReadinessError("ローカルLambda bodyが不正です")
    citations = body.get("citations", [])
    if not isinstance(citations, list):
        raise InfrastructureReadinessError("ローカルLambdaの引用形式が不正です")
    citation_ids = tuple(
        str(item.get("chunk_id", ""))
        for item in citations
        if isinstance(item, dict) and item.get("chunk_id")
    )
    return Lab8Experiment(
        dataset=dataset,
        template_name=template_path.name,
        template_sha256=hashlib.sha256(template_bytes).hexdigest(),
        findings=analyze_sam_template(template),
        smoke_status_code=int(smoke["status_code"]),
        smoke_answerable=bool(body.get("answerable")),
        smoke_citation_ids=citation_ids,
    )


def evaluate_lab8(
    experiment: Lab8Experiment,
    *,
    prediction: str,
    observation: str,
    iam_plan: str,
    cost_plan: str,
    cleanup_plan: str,
    acknowledged_finding_codes: tuple[str, ...],
) -> LabCompletion:
    findings = {finding.code: finding for finding in experiment.findings}
    hard_codes = (
        "no_embedded_credentials",
        "bounded_timeout",
        "bounded_concurrency",
        "bounded_log_retention",
        "tracing_enabled",
    )
    hard_checks_pass = all(
        findings.get(code) is not None and findings[code].status == "passed"
        for code in hard_codes
    )
    acknowledged = set(acknowledged_finding_codes)
    review_codes = set(experiment.review_finding_codes)
    data_checks = (
        make_check(
            "local_lambda_smoke",
            experiment.smoke_status_code == 200
            and experiment.smoke_answerable
            and bool(experiment.smoke_citation_ids),
            "抽出式生成器でローカルLambda相当のHTTP処理が成功しました",
            "ローカルLambda相当の応答または引用を確認してください",
        ),
        make_check(
            "template_safety_baseline",
            hard_checks_pass,
            "秘密情報・上限・ログの基礎設定を確認しました",
            "SAMテンプレートの秘密情報・上限・ログ設定を見直してください",
        ),
        make_check(
            "review_findings_acknowledged",
            review_codes.issubset(acknowledged),
            "本番前に対応する要確認項目をすべて確認しました",
            "認証・最小権限・予算の要確認項目をすべて確認してください",
        ),
    )
    learning_checks = (
        make_check(
            "prediction_recorded",
            bool(prediction.strip()),
            "実行前の予想を記録しました",
            "実行前の予想が未記録です",
        ),
        make_check(
            "observation_recorded",
            bool(observation.strip()),
            "ローカル確認結果を観察しました",
            "実行後の観察が未記録です",
        ),
        make_check(
            "iam_plan_recorded",
            bool(iam_plan.strip()),
            "IAMを利用モデルへ絞る計画を記録しました",
            "IAMの最小権限化計画が未記録です",
        ),
        make_check(
            "cost_plan_recorded",
            bool(cost_plan.strip()),
            "料金監視と停止条件を記録しました",
            "予算通知と停止条件が未記録です",
        ),
        make_check(
            "cleanup_plan_recorded",
            bool(cleanup_plan.strip()),
            "スタックと周辺リソースの削除手順を記録しました",
            "実習後の削除手順が未記録です",
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


def save_lab8_experiment(
    workspace: Path,
    experiment: Lab8Experiment,
    *,
    prediction: str,
    observation: str,
    iam_plan: str,
    cost_plan: str,
    cleanup_plan: str,
    acknowledged_finding_codes: tuple[str, ...],
) -> SavedLearningRun:
    completion = evaluate_lab8(
        experiment,
        prediction=prediction,
        observation=observation,
        iam_plan=iam_plan,
        cost_plan=cost_plan,
        cleanup_plan=cleanup_plan,
        acknowledged_finding_codes=acknowledged_finding_codes,
    )
    return save_learning_run(
        workspace,
        lab_id="lab8",
        dataset_id=experiment.dataset.dataset_id,
        completion=completion,
        prediction=prediction,
        observation=observation,
        settings={
            "template_name": experiment.template_name,
            "template_sha256": experiment.template_sha256,
            "generator": "extractive",
            "external_aws_call": False,
            "iam_plan": iam_plan,
            "cost_plan": cost_plan,
            "cleanup_plan": cleanup_plan,
            "acknowledged_finding_codes": list(acknowledged_finding_codes),
        },
        summary={
            "findings": [
                {
                    "code": finding.code,
                    "category": finding.category,
                    "status": finding.status,
                }
                for finding in experiment.findings
            ],
            "smoke_status_code": experiment.smoke_status_code,
            "smoke_answerable": experiment.smoke_answerable,
            "smoke_citation_ids": list(experiment.smoke_citation_ids),
        },
    )
