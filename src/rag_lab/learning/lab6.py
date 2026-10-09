from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from ..evaluation import evaluate_pipeline
from ..generation import ExtractiveGenerator
from ..pipeline import RAGPipeline
from .checks import LabCompletion, make_check
from .datasets import LearningDataset
from .diagnostics import (
    EvaluationReport,
    ReportComparison,
    compare_reports,
    evaluation_report_from_value,
)
from .experiments import SavedLearningRun, save_learning_run
from .lab2 import SEARCH_MODES, build_retriever


CHANGEABLE_PARAMETERS = ("search_mode", "top_k", "dimension")


@dataclass(frozen=True)
class Lab6Configuration:
    search_mode: str = "hybrid"
    top_k: int = 5
    dimension: int = 384


@dataclass(frozen=True)
class Lab6Experiment:
    dataset: LearningDataset
    changed_parameter: str
    baseline_configuration: Lab6Configuration
    candidate_configuration: Lab6Configuration
    prompt_version: str
    gold_name: str
    baseline_report: EvaluationReport
    candidate_report: EvaluationReport
    comparison: ReportComparison


def _validate_configuration(configuration: Lab6Configuration) -> None:
    if configuration.search_mode not in SEARCH_MODES:
        raise ValueError("検索方式が不正です")
    if not 1 <= configuration.top_k <= 20:
        raise ValueError("top_kは1から20で指定してください")
    if configuration.dimension <= 0:
        raise ValueError("Embedding次元は1以上で指定してください")


def changed_parameters(
    baseline: Lab6Configuration,
    candidate: Lab6Configuration,
) -> tuple[str, ...]:
    return tuple(
        name
        for name in CHANGEABLE_PARAMETERS
        if getattr(baseline, name) != getattr(candidate, name)
    )


def _evaluate_configuration(
    dataset: LearningDataset,
    configuration: Lab6Configuration,
    *,
    gold_path: Path,
    prompt_path: Path,
    report_name: str,
) -> EvaluationReport:
    retriever = build_retriever(dataset.chunks, configuration.dimension)
    pipeline = RAGPipeline(
        retriever=retriever,
        generator=ExtractiveGenerator(),
        prompt_path=prompt_path,
        search_mode=configuration.search_mode,
        top_k=configuration.top_k,
    )
    value = evaluate_pipeline(pipeline, gold_path)
    return evaluation_report_from_value(report_name, value)


def run_lab6_experiment(
    dataset: LearningDataset,
    *,
    baseline_configuration: Lab6Configuration,
    candidate_configuration: Lab6Configuration,
    changed_parameter: str,
    gold_path: Path,
    prompt_path: Path,
) -> Lab6Experiment:
    if dataset.dataset_id != "bundled":
        raise ValueError(
            "Lab 6の自動評価は、正解データ付きの付属データで実行します"
        )
    if changed_parameter not in CHANGEABLE_PARAMETERS:
        raise ValueError("変更対象が不正です")
    _validate_configuration(baseline_configuration)
    _validate_configuration(candidate_configuration)
    differences = changed_parameters(
        baseline_configuration,
        candidate_configuration,
    )
    if differences != (changed_parameter,):
        raise ValueError("変更する評価条件は1項目だけにしてください")
    if not gold_path.is_file():
        raise ValueError("正解データが見つかりません")
    if not prompt_path.is_file():
        raise ValueError("プロンプトファイルが見つかりません")

    baseline_report = _evaluate_configuration(
        dataset,
        baseline_configuration,
        gold_path=gold_path,
        prompt_path=prompt_path,
        report_name="lab6-baseline.json",
    )
    candidate_report = _evaluate_configuration(
        dataset,
        candidate_configuration,
        gold_path=gold_path,
        prompt_path=prompt_path,
        report_name="lab6-candidate.json",
    )
    return Lab6Experiment(
        dataset=dataset,
        changed_parameter=changed_parameter,
        baseline_configuration=baseline_configuration,
        candidate_configuration=candidate_configuration,
        prompt_version=prompt_path.name,
        gold_name=gold_path.name,
        baseline_report=baseline_report,
        candidate_report=candidate_report,
        comparison=compare_reports(baseline_report, candidate_report),
    )


def evaluate_lab6(
    experiment: Lab6Experiment,
    *,
    prediction: str,
    hypothesis: str,
    observation: str,
    regression_note: str,
    next_action: str,
) -> LabCompletion:
    same_cases = {
        case.case_id for case in experiment.baseline_report.cases
    } == {case.case_id for case in experiment.candidate_report.cases}
    data_checks = (
        make_check(
            "one_parameter_changed",
            changed_parameters(
                experiment.baseline_configuration,
                experiment.candidate_configuration,
            )
            == (experiment.changed_parameter,),
            "評価条件を1項目だけ変更しました",
            "変更する評価条件を1項目にしてください",
        ),
        make_check(
            "same_evaluation_cases",
            same_cases and bool(experiment.baseline_report.cases),
            "変更前後を同じ問題セットで評価しました",
            "変更前後の問題IDを一致させてください",
        ),
    )
    learning_checks = (
        make_check(
            "prediction_recorded",
            bool(prediction.strip()),
            "変更後の結果を予想しました",
            "実行前の予想が未記録です",
        ),
        make_check(
            "hypothesis_recorded",
            bool(hypothesis.strip()),
            "1つの変更仮説を記録しました",
            "変更の仮説が未記録です",
        ),
        make_check(
            "observation_recorded",
            bool(observation.strip()),
            "指標と失敗例の変化を観察しました",
            "実行後の観察が未記録です",
        ),
        make_check(
            "regressions_reviewed",
            bool(regression_note.strip()),
            "悪化例の有無と理由を記録しました",
            "悪化例がない場合も、ないことと理由を記録してください",
        ),
        make_check(
            "next_action_recorded",
            bool(next_action.strip()),
            "次に変更する1項目を記録しました",
            "次に試す1項目が未記録です",
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


def _report_summary(report: EvaluationReport) -> dict[str, object]:
    return {
        "metrics": dict(report.summary),
        "failed_case_ids": [case.case_id for case in report.failed_cases],
    }


def save_lab6_experiment(
    workspace: Path,
    experiment: Lab6Experiment,
    *,
    prediction: str,
    hypothesis: str,
    observation: str,
    regression_note: str,
    next_action: str,
) -> SavedLearningRun:
    completion = evaluate_lab6(
        experiment,
        prediction=prediction,
        hypothesis=hypothesis,
        observation=observation,
        regression_note=regression_note,
        next_action=next_action,
    )
    return save_learning_run(
        workspace,
        lab_id="lab6",
        dataset_id=experiment.dataset.dataset_id,
        completion=completion,
        prediction=prediction,
        observation=observation,
        settings={
            "changed_parameter": experiment.changed_parameter,
            "baseline": asdict(experiment.baseline_configuration),
            "candidate": asdict(experiment.candidate_configuration),
            "generator": "extractive",
            "prompt_version": experiment.prompt_version,
            "gold_dataset": experiment.gold_name,
            "hypothesis": hypothesis,
            "regression_note": regression_note,
            "next_action": next_action,
        },
        summary={
            "baseline": _report_summary(experiment.baseline_report),
            "candidate": _report_summary(experiment.candidate_report),
            "metric_deltas": dict(experiment.comparison.metric_deltas),
            "resolved_case_ids": list(experiment.comparison.resolved_case_ids),
            "new_failure_case_ids": list(
                experiment.comparison.new_failure_case_ids
            ),
        },
    )
