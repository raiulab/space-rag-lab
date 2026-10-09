from __future__ import annotations

import base64
import json
import unittest
from unittest import mock

from rag_lab.aws_handler import lambda_handler


class AwsHandlerSecurityTests(unittest.TestCase):
    def test_rejects_non_object_json(self) -> None:
        response = lambda_handler({"body": "[]"}, None)

        self.assertEqual(response["statusCode"], 400)
        self.assertEqual(
            json.loads(response["body"]),
            {"error": "JSONオブジェクトを指定してください"},
        )

    def test_rejects_invalid_base64_as_bad_request(self) -> None:
        response = lambda_handler(
            {"body": "not-valid-base64", "isBase64Encoded": True},
            None,
        )

        self.assertEqual(response["statusCode"], 400)
        self.assertEqual(
            json.loads(response["body"]),
            {"error": "JSON形式のbodyを指定してください"},
        )

    def test_base64_json_request_is_supported(self) -> None:
        raw_body = json.dumps({"question": "火星の砂嵐"}).encode("utf-8")
        event = {
            "body": base64.b64encode(raw_body).decode("ascii"),
            "isBase64Encoded": True,
        }
        expected = {"answer": "ok"}
        pipeline = mock.Mock()
        pipeline.ask.return_value.to_dict.return_value = expected

        with mock.patch("rag_lab.aws_handler._pipeline", return_value=pipeline):
            response = lambda_handler(event, None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"]), expected)

    def test_question_length_matches_local_api_limit(self) -> None:
        response = lambda_handler(
            {"body": json.dumps({"question": "あ" * 501})},
            None,
        )

        self.assertEqual(response["statusCode"], 400)
        self.assertIn("500文字以下", json.loads(response["body"])["error"])

    def test_internal_error_does_not_expose_exception_details(self) -> None:
        sensitive_detail = "credential-like-value-must-not-leak"

        with (
            mock.patch(
                "rag_lab.aws_handler._pipeline",
                side_effect=RuntimeError(sensitive_detail),
            ),
            self.assertLogs("rag_lab.aws_handler", level="ERROR"),
        ):
            response = lambda_handler(
                {"body": json.dumps({"question": "有効な質問"})},
                None,
            )

        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 500)
        self.assertEqual(body["error"], "internal_server_error")
        self.assertNotIn(sensitive_detail, response["body"])


if __name__ == "__main__":
    unittest.main()
