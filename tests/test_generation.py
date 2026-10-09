from __future__ import annotations

import unittest
from types import ModuleType
from unittest import mock

from rag_lab.generation import BedrockGenerator, render_grounded_prompt
from rag_lab.models import Chunk, SearchResult


class FakeBedrockClient:
    def __init__(self) -> None:
        self.request = None

    def converse(self, **request):
        self.request = request
        return {
            "output": {
                "message": {
                    "content": [{"text": "根拠に基づく回答 [mars:1]"}]
                }
            }
        }


class GenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = SearchResult(
            chunk=Chunk(
                chunk_id="mars:1",
                document_id="mars",
                title="火星報告",
                page=2,
                section="砂嵐",
                text="太陽電池出力は32 %まで低下した。",
            ),
            score=1.0,
            rank=1,
            method="hybrid",
        )

    def test_rendered_prompt_contains_question_and_traceable_context(self) -> None:
        prompt = render_grounded_prompt(
            "出力は？",
            [self.result],
            "資料:\n{context}\n質問:{question}",
        )

        self.assertIn("chunk_id=mars:1", prompt)
        self.assertIn("page=2", prompt)
        self.assertIn("太陽電池出力は32 %", prompt)
        self.assertIn("質問:出力は？", prompt)

    def test_bedrock_generator_supports_injected_client_without_aws_setup(self) -> None:
        client = FakeBedrockClient()
        generator = BedrockGenerator(model_id="test-model", client=client)

        text, answerable = generator.generate(
            "出力は？",
            [self.result],
            "資料:\n{context}\n質問:{question}",
        )

        self.assertTrue(answerable)
        self.assertIn("根拠に基づく回答", text)
        self.assertEqual(client.request["modelId"], "test-model")
        sent_prompt = client.request["messages"][0]["content"][0]["text"]
        self.assertIn("chunk_id=mars:1", sent_prompt)
        self.assertEqual(
            client.request["inferenceConfig"],
            {"temperature": 0.0, "maxTokens": 800},
        )

    def test_bedrock_generator_rejects_empty_response(self) -> None:
        class EmptyClient:
            def converse(self, **request):
                del request
                return {"output": {"message": {"content": [{"text": ""}]}}}

        generator = BedrockGenerator(model_id="test-model", client=EmptyClient())

        with self.assertRaisesRegex(RuntimeError, "empty response"):
            generator.generate("質問", [self.result], "{context}\n{question}")

    def test_bedrock_client_has_bounded_timeouts_and_retries(self) -> None:
        boto3_module = ModuleType("boto3")
        botocore_module = ModuleType("botocore")
        config_module = ModuleType("botocore.config")
        client = FakeBedrockClient()
        boto3_module.client = mock.Mock(return_value=client)
        config_module.Config = mock.Mock(return_value="bounded-config")

        with mock.patch.dict(
            "sys.modules",
            {
                "boto3": boto3_module,
                "botocore": botocore_module,
                "botocore.config": config_module,
            },
        ):
            generator = BedrockGenerator(
                model_id="test-model",
                region="ap-northeast-1",
                read_timeout_seconds=12,
                max_attempts=3,
            )

        config_module.Config.assert_called_once_with(
            connect_timeout=5,
            read_timeout=12,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        boto3_module.client.assert_called_once_with(
            "bedrock-runtime",
            region_name="ap-northeast-1",
            config="bounded-config",
        )
        self.assertIs(generator.client, client)


if __name__ == "__main__":
    unittest.main()
