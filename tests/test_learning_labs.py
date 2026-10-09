from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from rag_lab.learning.datasets import (
    LearningDatasetError,
    bundled_dataset,
    list_saved_datasets,
    load_saved_dataset,
)
from rag_lab.learning.lab1 import prepare_bundled_data, save_prepared_bundled
from rag_lab.learning.lab2 import (
    evaluate_lab2,
    run_lab2_experiment,
    save_lab2_experiment,
)
from rag_lab.learning.lab3 import (
    evaluate_lab3,
    run_lab3_experiment,
    save_lab3_experiment,
)
from rag_lab.learning.lab4 import (
    evaluate_lab4,
    run_lab4_experiment,
    save_lab4_experiment,
)
from rag_lab.learning.lab5 import (
    evaluate_lab5,
    run_lab5_experiment,
    save_lab5_experiment,
)
from rag_lab.learning.lab6 import (
    Lab6Configuration,
    evaluate_lab6,
    run_lab6_experiment,
    save_lab6_experiment,
)
from rag_lab.learning.lab7 import (
    analyze_prompt,
    evaluate_jsonl_outputs,
    evaluate_lab7,
    run_lab7_experiment,
    save_lab7_experiment,
)
from rag_lab.learning.lab8 import (
    analyze_sam_template,
    evaluate_lab8,
    run_lab8_readiness,
    save_lab8_experiment,
)


ROOT = Path(__file__).parents[1]
RAW_DIR = ROOT / "data" / "raw"
GOLD_PATH = ROOT / "data" / "evaluation" / "gold.jsonl"


class LearningDatasetTests(unittest.TestCase):
    def test_saved_lab1_dataset_can_be_loaded_without_source_paths(self) -> None:
        prepared = prepare_bundled_data(RAW_DIR)
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / ".rag_lab"
            saved = save_prepared_bundled(
                workspace,
                prepared,
                prediction="20チャンクと予想",
                observation="出典を保持した",
            )

            options = list_saved_datasets(workspace)
            loaded = load_saved_dataset(workspace, saved.dataset_id)

        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].dataset_id, saved.dataset_id)
        self.assertEqual(len(loaded.chunks), 20)
        self.assertEqual(loaded.source_kind, "bundled_markdown_text")

    def test_unsafe_dataset_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(LearningDatasetError, "不正"):
                load_saved_dataset(Path(directory), "../outside")


class Lab2LearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = bundled_dataset(RAW_DIR)

    def test_three_search_modes_and_benchmark_are_comparable(self) -> None:
        experiment = run_lab2_experiment(
            self.dataset,
            query="火星の砂嵐で太陽電池出力は何%まで低下しましたか？",
            top_k=5,
            dimension=384,
            gold_path=GOLD_PATH,
        )

        self.assertEqual(set(experiment.results), {"dense", "bm25", "hybrid"})
        self.assertTrue(all(len(rows) == 5 for rows in experiment.results.values()))
        self.assertEqual(experiment.benchmark_questions, 8)
        self.assertTrue(all(rate >= 0.8 for rate in experiment.hit_rates.values()))
        self.assertEqual(experiment.results["bm25"][0].chunk.document_id, "mars_power_2026")

    def test_completion_requires_prediction_and_observation(self) -> None:
        experiment = run_lab2_experiment(
            self.dataset,
            query="太陽電池出力",
            top_k=3,
            dimension=64,
        )

        incomplete = evaluate_lab2(experiment, prediction="", observation="")
        complete = evaluate_lab2(
            experiment,
            prediction="BM25が上位になると予想",
            observation="BM25は完全一致語を上位にした",
        )

        self.assertEqual(incomplete.status, "in_progress")
        self.assertEqual(complete.status, "completed")

    def test_saved_run_contains_metrics_but_not_chunk_text_or_secret(self) -> None:
        experiment = run_lab2_experiment(
            self.dataset,
            query="太陽電池出力",
            top_k=3,
            dimension=64,
            gold_path=GOLD_PATH,
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / ".rag_lab"
            with mock.patch.dict(
                os.environ, {"AWS_SECRET_ACCESS_KEY": "do-not-persist"}
            ):
                saved = save_lab2_experiment(
                    workspace,
                    experiment,
                    prediction="hybridを予想",
                    observation="順位差を確認した",
                )
            value = json.loads(saved.path.read_text(encoding="utf-8"))
            saved_text = saved.path.read_text(encoding="utf-8")
            progress = json.loads(
                (workspace / "progress.json").read_text(encoding="utf-8")
            )

        self.assertEqual(value["lab_id"], "lab2")
        self.assertEqual(value["status"], "completed")
        self.assertIn("hit_rates", value["summary"])
        self.assertNotIn(self.dataset.chunks[0].text, saved_text)
        self.assertNotIn("do-not-persist", saved_text)
        self.assertEqual(progress["labs"]["lab2"]["status"], "completed")


class Lab3LearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = bundled_dataset(RAW_DIR)
        self.prompt = ROOT / "prompts" / "answer_v2_grounded.txt"

    def test_answer_can_be_traced_to_retrieved_chunks(self) -> None:
        experiment = run_lab3_experiment(
            self.dataset,
            question="火星の砂嵐で太陽電池出力は何%まで低下しましたか？",
            expected_answerable=True,
            prompt_path=self.prompt,
        )
        completion = evaluate_lab3(
            experiment,
            prediction="火星文書が検索され32%と答える",
            observation="回答と引用から火星文書へ戻れた",
        )

        self.assertTrue(experiment.answer.answerable)
        self.assertIn("32 %", experiment.answer.text)
        self.assertEqual(experiment.answer.citations[0].document_id, "mars_power_2026")
        self.assertEqual(completion.status, "completed")

    def test_supported_refusal_has_no_citations(self) -> None:
        experiment = run_lab3_experiment(
            self.dataset,
            question="penguin feather count",
            expected_answerable=False,
            prompt_path=self.prompt,
        )
        completion = evaluate_lab3(
            experiment,
            prediction="回答不能になる",
            observation="共通語がなく拒否した",
        )

        self.assertFalse(experiment.answer.answerable)
        self.assertEqual(experiment.answer.citations, [])
        self.assertEqual(completion.status, "completed")

    def test_wrong_answerability_prediction_needs_review(self) -> None:
        experiment = run_lab3_experiment(
            self.dataset,
            question="月面基地で生活する乗員は何人ですか？",
            expected_answerable=False,
            prompt_path=self.prompt,
        )
        completion = evaluate_lab3(
            experiment,
            prediction="文書にないため回答不能になる",
            observation="対象外という文を回答として選んでしまった",
        )

        self.assertTrue(experiment.answer.answerable)
        self.assertEqual(completion.status, "needs_review")
        failed = {check.code for check in completion.checks if not check.passed}
        self.assertEqual(failed, {"answerability_matches_prediction"})

    def test_saved_run_omits_answer_and_source_body(self) -> None:
        experiment = run_lab3_experiment(
            self.dataset,
            question="火星の太陽電池出力は？",
            expected_answerable=True,
            prompt_path=self.prompt,
            search_mode="hybrid",
            top_k=3,
            dimension=64,
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / ".rag_lab"
            saved = save_lab3_experiment(
                workspace,
                experiment,
                prediction="火星文書から回答する",
                observation="引用を確認した",
            )
            saved_text = saved.path.read_text(encoding="utf-8")
            value = json.loads(saved_text)
            progress = json.loads(
                (workspace / "progress.json").read_text(encoding="utf-8")
            )

        self.assertNotIn(experiment.answer.text, saved_text)
        self.assertNotIn(self.dataset.chunks[0].text, saved_text)
        self.assertTrue(value["summary"]["predicted_answerable"])
        self.assertEqual(value["settings"]["prompt_version"], "answer_v2_grounded.txt")
        self.assertEqual(progress["labs"]["lab3"]["status"], "completed")


class Lab4LearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = bundled_dataset(RAW_DIR)
        self.prompt = ROOT / "prompts" / "answer_v2_grounded.txt"
        self.question = "火星の砂嵐で太陽電池出力は何%まで低下しましたか？"

    def test_offline_simulator_compares_same_evidence_and_records_metrics(self) -> None:
        times = iter((10.0, 10.125))
        experiment = run_lab4_experiment(
            self.dataset,
            question=self.question,
            expected_external_success=True,
            prompt_path=self.prompt,
            provider="simulated",
            simulation_scenario="success",
            clock=lambda: next(times),
        )
        completion = evaluate_lab4(
            experiment,
            prediction="模擬APIは成功する",
            observation="同じ根拠を使い送信文字数と時間を記録した",
        )

        self.assertEqual(experiment.external_call.status, "success")
        self.assertEqual(experiment.external_call.latency_ms, 125.0)
        self.assertGreater(experiment.external_call.input_chars, 0)
        self.assertIn("32 %", experiment.baseline_answer.text)
        self.assertIsNotNone(experiment.external_call.answer)
        self.assertIn("32 %", experiment.external_call.answer.text)
        self.assertEqual(
            [item.chunk.chunk_id for item in experiment.baseline_answer.retrieved],
            [item.chunk.chunk_id for item in experiment.external_call.answer.retrieved],
        )
        self.assertEqual(completion.status, "completed")

    def test_simulated_failure_is_safely_classified_and_can_complete(self) -> None:
        with self.assertLogs("rag_lab.learning.lab4", level="WARNING"):
            experiment = run_lab4_experiment(
                self.dataset,
                question=self.question,
                expected_external_success=False,
                prompt_path=self.prompt,
                provider="simulated",
                simulation_scenario="throttling",
            )
        completion = evaluate_lab4(
            experiment,
            prediction="スロットリングとして安全に失敗する",
            observation="例外全文ではなく失敗分類が表示された",
        )

        self.assertEqual(experiment.external_call.status, "failed")
        self.assertEqual(experiment.external_call.failure_type, "throttling")
        self.assertIsNone(experiment.external_call.answer)
        self.assertNotIn("simulated external", experiment.external_call.safe_message)
        self.assertEqual(completion.status, "completed")

    def test_bedrock_failure_and_saved_run_omit_secrets_and_bodies(self) -> None:
        sensitive_error = "credential-like-detail-must-not-leak"
        sensitive_model_id = (
            "arn:aws:bedrock:ap-northeast-1:123456789012:"
            "inference-profile/private-profile"
        )

        class FakeClientError(Exception):
            response = {"Error": {"Code": "AccessDeniedException"}}

        class FailingGenerator:
            def generate(self, question, results, prompt_template):
                del question, results, prompt_template
                raise FakeClientError(sensitive_error)

        with self.assertLogs("rag_lab.learning.lab4", level="WARNING") as logs:
            experiment = run_lab4_experiment(
                self.dataset,
                question=self.question,
                expected_external_success=False,
                prompt_path=self.prompt,
                provider="bedrock",
                model_id=sensitive_model_id,
                region="ap-northeast-1",
                bedrock_factory=lambda **settings: FailingGenerator(),
            )

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / ".rag_lab"
            saved = save_lab4_experiment(
                workspace,
                experiment,
                prediction="権限不足として失敗する",
                observation="安全な分類だけを確認した",
            )
            saved_text = saved.path.read_text(encoding="utf-8")
            value = json.loads(saved_text)
            progress = json.loads(
                (workspace / "progress.json").read_text(encoding="utf-8")
            )

        self.assertEqual(experiment.external_call.failure_type, "authorization")
        self.assertNotIn(sensitive_error, "\n".join(logs.output))
        self.assertNotIn(sensitive_model_id, "\n".join(logs.output))
        self.assertNotIn(sensitive_error, saved_text)
        self.assertNotIn(sensitive_model_id, saved_text)
        self.assertNotIn(experiment.baseline_answer.text, saved_text)
        self.assertNotIn(self.dataset.chunks[0].text, saved_text)
        self.assertEqual(value["summary"]["failure_type"], "authorization")
        self.assertEqual(progress["labs"]["lab4"]["status"], "completed")

    def test_live_configuration_is_validated_before_call(self) -> None:
        with self.assertRaisesRegex(ValueError, "モデルID"):
            run_lab4_experiment(
                self.dataset,
                question=self.question,
                expected_external_success=True,
                prompt_path=self.prompt,
                provider="bedrock",
                model_id="",
            )
        with self.assertRaisesRegex(ValueError, "リージョン"):
            run_lab4_experiment(
                self.dataset,
                question=self.question,
                expected_external_success=True,
                prompt_path=self.prompt,
                provider="bedrock",
                model_id="valid-model",
                region="bad region",
            )


class Lab5LearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = bundled_dataset(RAW_DIR)
        self.prompt = ROOT / "prompts" / "answer_v2_grounded.txt"

    def _experiment(self):
        return run_lab5_experiment(
            self.dataset,
            search_query="低電力時の安全モード",
            summary_document_id="mars_power_2026",
            qa_question="蓄電池の設計目標との差は何時間ですか？",
            prompt_path=self.prompt,
        )

    def test_search_summary_and_qa_have_distinct_traceable_outputs(self) -> None:
        experiment = self._experiment()

        self.assertEqual(len(experiment.search_results), 5)
        self.assertTrue(all(result.chunk.chunk_id for result in experiment.search_results))
        self.assertTrue(experiment.summary_answerable)
        self.assertIn("mars_power_2026", experiment.summary_source_chunk_ids[0])
        self.assertIn("6時間", experiment.qa_answer.text)
        self.assertTrue(experiment.qa_answer.citations)

    def test_completion_requires_prediction_and_observation(self) -> None:
        experiment = self._experiment()

        incomplete = evaluate_lab5(experiment, prediction="", observation="")
        complete = evaluate_lab5(
            experiment,
            prediction="検索は候補、要約は1文書、QAは回答を返す",
            observation="3機能で出力と根拠の単位が異なった",
        )

        self.assertEqual(incomplete.status, "in_progress")
        self.assertEqual(complete.status, "completed")

    def test_saved_run_omits_generated_and_source_bodies(self) -> None:
        experiment = self._experiment()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / ".rag_lab"
            saved = save_lab5_experiment(
                workspace,
                experiment,
                prediction="3機能の出力形式が異なる",
                observation="検索結果、要約元、QA引用を確認した",
            )
            saved_text = saved.path.read_text(encoding="utf-8")
            value = json.loads(saved_text)
            progress = json.loads(
                (workspace / "progress.json").read_text(encoding="utf-8")
            )

        self.assertNotIn(experiment.summary_text, saved_text)
        self.assertNotIn(experiment.qa_answer.text, saved_text)
        self.assertNotIn(self.dataset.chunks[0].text, saved_text)
        self.assertIn("summary_source_chunk_ids", value["summary"])
        self.assertEqual(progress["labs"]["lab5"]["status"], "completed")

    def test_question_length_is_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "500文字以下"):
            run_lab5_experiment(
                self.dataset,
                search_query="検索語",
                summary_document_id="mars_power_2026",
                qa_question="あ" * 501,
                prompt_path=self.prompt,
            )
        with self.assertRaisesRegex(ValueError, "document_id"):
            run_lab5_experiment(
                self.dataset,
                search_query="検索語",
                summary_document_id="missing-document",
                qa_question="有効な質問",
                prompt_path=self.prompt,
            )


class Lab6LearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = bundled_dataset(RAW_DIR)
        self.prompt = ROOT / "prompts" / "answer_v2_grounded.txt"
        self.baseline = Lab6Configuration()
        self.candidate = Lab6Configuration(dimension=64)

    def _experiment(self):
        return run_lab6_experiment(
            self.dataset,
            baseline_configuration=self.baseline,
            candidate_configuration=self.candidate,
            changed_parameter="dimension",
            gold_path=GOLD_PATH,
            prompt_path=self.prompt,
        )

    def test_same_ten_cases_are_compared_after_one_parameter_change(self) -> None:
        experiment = self._experiment()

        self.assertEqual(experiment.baseline_report.summary["examples"], 10)
        self.assertEqual(experiment.candidate_report.summary["examples"], 10)
        self.assertEqual(
            {case.case_id for case in experiment.baseline_report.cases},
            {case.case_id for case in experiment.candidate_report.cases},
        )
        self.assertEqual(experiment.comparison.metric_deltas["keyword_recall"], -0.1)
        self.assertEqual(experiment.comparison.new_failure_case_ids, ("europa-01",))

    def test_exactly_one_declared_parameter_must_change(self) -> None:
        with self.assertRaisesRegex(ValueError, "1項目"):
            run_lab6_experiment(
                self.dataset,
                baseline_configuration=self.baseline,
                candidate_configuration=self.baseline,
                changed_parameter="dimension",
                gold_path=GOLD_PATH,
                prompt_path=self.prompt,
            )
        with self.assertRaisesRegex(ValueError, "1項目"):
            run_lab6_experiment(
                self.dataset,
                baseline_configuration=self.baseline,
                candidate_configuration=Lab6Configuration(
                    search_mode="dense",
                    dimension=64,
                ),
                changed_parameter="dimension",
                gold_path=GOLD_PATH,
                prompt_path=self.prompt,
            )

    def test_completion_requires_hypothesis_regression_and_next_action(self) -> None:
        experiment = self._experiment()

        incomplete = evaluate_lab6(
            experiment,
            prediction="低次元で精度が下がる",
            hypothesis="",
            observation="",
            regression_note="",
            next_action="",
        )
        complete = evaluate_lab6(
            experiment,
            prediction="低次元で必須語再現率が下がる",
            hypothesis="衝突が増え根拠文の選択が変わる",
            observation="必須語再現率が10ポイント低下した",
            regression_note="europa-01が新しく失敗した",
            next_action="次は検索方式だけを変える",
        )

        self.assertEqual(incomplete.status, "in_progress")
        self.assertEqual(complete.status, "completed")

    def test_saved_run_has_metrics_but_omits_answers_and_source_bodies(self) -> None:
        experiment = self._experiment()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / ".rag_lab"
            saved = save_lab6_experiment(
                workspace,
                experiment,
                prediction="低次元で精度が下がる",
                hypothesis="ハッシュ衝突が増える",
                observation="必須語再現率が低下した",
                regression_note="europa-01が新しく失敗した",
                next_action="検索方式だけを変える",
            )
            saved_text = saved.path.read_text(encoding="utf-8")
            value = json.loads(saved_text)
            progress = json.loads(
                (workspace / "progress.json").read_text(encoding="utf-8")
            )

        self.assertEqual(value["summary"]["baseline"]["metrics"]["examples"], 10)
        self.assertEqual(value["summary"]["new_failure_case_ids"], ["europa-01"])
        self.assertNotIn("火星の砂嵐で太陽電池出力", saved_text)
        self.assertNotIn(self.dataset.chunks[0].text, saved_text)
        self.assertEqual(progress["labs"]["lab6"]["status"], "completed")


class Lab7LearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.v1 = ROOT / "prompts" / "answer_v1.txt"
        self.v2 = ROOT / "prompts" / "answer_v2_grounded.txt"
        self.draft = self.v2.read_text(encoding="utf-8") + """

7. 出力はJSONオブジェクトのみにする。
8. 必須キーはanswer文字列、answerable真偽値、citationsのchunk_id文字列配列とする。
"""
        self.outputs = """{"answer":"根拠あり","answerable":true,"citations":["doc:p1:001"]}
{"answer":"提供された文書では確認できません。","answerable":false,"citations":[]}"""

    def _experiment(self):
        return run_lab7_experiment(
            prompt_v1_path=self.v1,
            prompt_v2_path=self.v2,
            draft_text=self.draft,
            jsonl_outputs=self.outputs,
        )

    def test_v1_v2_and_v3_contracts_are_distinguished(self) -> None:
        experiment = self._experiment()
        v1_checks = {
            check.code: check.passed for check in experiment.prompt_v1_analysis.checks
        }
        v2_checks = {
            check.code: check.passed for check in experiment.prompt_v2_analysis.checks
        }

        self.assertFalse(v1_checks["evidence_only"])
        self.assertFalse(v1_checks["document_instructions_untrusted"])
        self.assertTrue(v2_checks["document_instructions_untrusted"])
        self.assertFalse(v2_checks["json_contract"])
        self.assertTrue(experiment.draft_analysis.passed)
        self.assertIn("それまでの指示を無視", experiment.rendered_preview)

    def test_json_contract_counts_syntax_and_schema_errors(self) -> None:
        metrics = evaluate_jsonl_outputs(
            '{"answer":"ok","answerable":true,"citations":[]}\n'
            '{bad json}\n'
            '{"answer":"missing types","answerable":"yes","citations":[]}\n'
            '{"answer":"ok","answerable":true,"citations":[],"score":NaN}'
        )

        self.assertEqual(metrics.examples, 4)
        self.assertEqual(metrics.syntax_errors, 2)
        self.assertEqual(metrics.schema_errors, 1)
        self.assertEqual(metrics.error_rate, 0.75)

    def test_unescaped_json_braces_are_reported_safely(self) -> None:
        invalid = self.draft + '\n例: {"answer": "value"}'

        with self.assertRaisesRegex(ValueError, "波括弧"):
            run_lab7_experiment(
                prompt_v1_path=self.v1,
                prompt_v2_path=self.v2,
                draft_text=invalid,
                jsonl_outputs=self.outputs,
            )

    def test_completion_and_save_preserve_old_versions_and_omit_prompt_body(self) -> None:
        experiment = self._experiment()
        completion = evaluate_lab7(
            experiment,
            prediction="v3はすべての構造検査を通過する",
            change_reason="後続処理でJSON解析するため",
            targeted_failure="出力形式が一定しない",
            observation="JSON契約エラー率0%を確認した",
        )
        original_v2 = self.v2.read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / ".rag_lab"
            saved = save_lab7_experiment(
                workspace,
                experiment,
                prediction="v3はすべての構造検査を通過する",
                change_reason="後続処理でJSON解析するため",
                targeted_failure="出力形式が一定しない",
                observation="JSON契約エラー率0%を確認した",
            )
            run_text = saved.run.path.read_text(encoding="utf-8")
            prompt_text = saved.prompt_path.read_text(encoding="utf-8")
            progress = json.loads(
                (workspace / "progress.json").read_text(encoding="utf-8")
            )

        self.assertEqual(completion.status, "completed")
        self.assertEqual(prompt_text.strip(), self.draft.strip())
        self.assertNotIn("あなたは宇宙技術文書", run_text)
        self.assertEqual(self.v2.read_text(encoding="utf-8"), original_v2)
        self.assertEqual(progress["labs"]["lab7"]["status"], "completed")

    def test_missing_prompt_contract_is_detected_without_executing_it(self) -> None:
        analysis = analyze_prompt(
            "unsafe.json",
            "{context}\n{question}\n{unknown:format}",
        )

        self.assertFalse(analysis.passed)
        placeholder = next(
            check
            for check in analysis.checks
            if check.code == "required_placeholders"
        )
        self.assertFalse(placeholder.passed)


class Lab8LearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = bundled_dataset(RAW_DIR)
        self.template = ROOT / "infra" / "template.yaml"
        self.prompt = ROOT / "prompts" / "answer_v2_grounded.txt"

    def _experiment(self):
        return run_lab8_readiness(
            self.dataset,
            template_path=self.template,
            prompt_path=self.prompt,
        )

    def test_local_lambda_smoke_and_template_findings_are_separate(self) -> None:
        experiment = self._experiment()
        findings = {item.code: item.status for item in experiment.findings}

        self.assertEqual(experiment.smoke_status_code, 200)
        self.assertTrue(experiment.smoke_answerable)
        self.assertTrue(experiment.smoke_citation_ids)
        self.assertEqual(findings["no_embedded_credentials"], "passed")
        self.assertEqual(findings["bounded_concurrency"], "passed")
        self.assertEqual(findings["http_authentication"], "review")
        self.assertEqual(findings["bedrock_resource_scope"], "review")
        self.assertEqual(findings["budget_guardrail"], "review")

    def test_completion_requires_gap_acknowledgement_and_three_plans(self) -> None:
        experiment = self._experiment()
        incomplete = evaluate_lab8(
            experiment,
            prediction="認証と予算が要対応になる",
            observation="ローカルHTTP応答200を確認",
            iam_plan="",
            cost_plan="",
            cleanup_plan="",
            acknowledged_finding_codes=(),
        )
        complete = evaluate_lab8(
            experiment,
            prediction="認証と予算が要対応になる",
            observation="ローカルHTTP応答200と引用を確認",
            iam_plan="利用モデルARNだけに限定する",
            cost_plan="予算1000円で通知し、超過前に停止する",
            cleanup_plan="sam delete後にログとS3を確認する",
            acknowledged_finding_codes=experiment.review_finding_codes,
        )

        self.assertEqual(incomplete.status, "needs_review")
        self.assertEqual(complete.status, "completed")

    def test_saved_run_omits_answer_body_and_credentials(self) -> None:
        experiment = self._experiment()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / ".rag_lab"
            with mock.patch.dict(
                os.environ,
                {"AWS_SECRET_ACCESS_KEY": "must-not-be-saved"},
            ):
                saved = save_lab8_experiment(
                    workspace,
                    experiment,
                    prediction="認証と予算を要確認と予想",
                    observation="HTTP 200と引用を確認",
                    iam_plan="モデルARNを限定",
                    cost_plan="予算通知後に停止",
                    cleanup_plan="スタックと周辺リソースを削除",
                    acknowledged_finding_codes=experiment.review_finding_codes,
                )
            saved_text = saved.path.read_text(encoding="utf-8")
            value = json.loads(saved_text)
            progress = json.loads(
                (workspace / "progress.json").read_text(encoding="utf-8")
            )

        self.assertNotIn("must-not-be-saved", saved_text)
        self.assertNotIn("模擬砂嵐の最も厳しい6時間", saved_text)
        self.assertFalse(value["settings"]["external_aws_call"])
        self.assertEqual(value["summary"]["smoke_status_code"], 200)
        self.assertEqual(progress["labs"]["lab8"]["status"], "completed")

    def test_embedded_credentials_and_missing_limits_are_flagged(self) -> None:
        findings = analyze_sam_template(
            "AWS_SECRET_ACCESS_KEY: example\nResources: {}\n"
        )
        statuses = {item.code: item.status for item in findings}

        self.assertEqual(statuses["no_embedded_credentials"], "review")
        self.assertEqual(statuses["bounded_timeout"], "review")
        self.assertEqual(statuses["bounded_concurrency"], "review")


if __name__ == "__main__":
    unittest.main()
