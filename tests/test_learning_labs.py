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
from rag_lab.learning.lab5 import (
    evaluate_lab5,
    run_lab5_experiment,
    save_lab5_experiment,
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


if __name__ == "__main__":
    unittest.main()
