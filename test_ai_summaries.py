from __future__ import annotations

import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from harvester.ai_summaries import MAX_INPUT_CHARS, summarise_bulletin


class _FakeResponse:
    def __init__(self, status: int, body: dict):
        self.status = status
        self._body = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class AiSummariesTests(unittest.TestCase):
    def test_returns_none_when_api_key_missing(self) -> None:
        result = summarise_bulletin("text", "Parish", None)
        self.assertIsNone(result)

    @patch("harvester.ai_summaries.request.urlopen")
    def test_returns_none_on_http_500(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = HTTPError(
            url="https://api.mistral.ai/v1/chat/completions",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=None,
        )
        result = summarise_bulletin("text", "Parish", "test-key")
        self.assertIsNone(result)

    @patch("harvester.ai_summaries.request.urlopen")
    def test_returns_parsed_dict_on_success(self, mock_urlopen) -> None:
        mock_urlopen.return_value = _FakeResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": "First important item\nSecond important item\nThird important item"
                        }
                    }
                ]
            },
        )
        result = summarise_bulletin("text", "Parish", "test-key")
        self.assertIsNotNone(result)
        if result is None:
            self.fail("Expected summary payload")
        self.assertEqual(
            ["First important item", "Second important item", "Third important item"],
            result["bullets"],
        )
        self.assertEqual("mistral-small", result["model"])
        self.assertIn("generated_at", result)

    @patch("harvester.ai_summaries.request.urlopen")
    def test_truncates_input_to_twelve_thousand_chars(self, mock_urlopen) -> None:
        seen_payload: dict[str, object] = {}

        def _capture(request_obj, timeout):
            self.assertEqual(20, timeout)
            seen_payload.update(json.loads(request_obj.data.decode("utf-8")))
            return _FakeResponse(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "content": "one valid bullet line\nsecond valid bullet line\nthird valid bullet line"
                            }
                        }
                    ]
                },
            )

        mock_urlopen.side_effect = _capture
        long_text = "A" * (MAX_INPUT_CHARS + 500)

        summarise_bulletin(long_text, "Parish", "test-key")

        messages = seen_payload.get("messages")
        self.assertIsInstance(messages, list)
        if not isinstance(messages, list) or not messages:
            self.fail("Expected message payload")
        content = messages[0]["content"]
        self.assertTrue(content.endswith("A" * MAX_INPUT_CHARS))


if __name__ == "__main__":
    unittest.main()
