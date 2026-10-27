import unittest
from unittest import mock

import httpx

from seo_lab import local_llm


def reply(status, content=""):
    request = httpx.Request("POST", "http://127.0.0.1:11434/api/chat")
    return httpx.Response(status, json={"message": {"content": content}}, request=request)


class OllamaJsonTests(unittest.TestCase):
    def test_server_error_falls_back_to_plain_mode_and_extracts_json(self):
        calls = []

        def fake_post(url, json=None, timeout=None):
            calls.append(json)
            return reply(500) if len(calls) == 1 else reply(200, 'Sure! ```json\n{"text": "ok", "reason": "r"}\n```')
        with mock.patch.object(local_llm.httpx, "post", side_effect=fake_post):
            out = local_llm._ollama_json("sys", "prompt")
        self.assertEqual(out, {"text": "ok", "reason": "r"})
        self.assertEqual(calls[0].get("format"), "json")
        self.assertNotIn("format", calls[1])  # the fallback is not forced-JSON

    def test_two_failures_raise_with_ollama_message(self):
        with mock.patch.object(local_llm.httpx, "post", side_effect=lambda *a, **k: reply(500, "boom")):
            with self.assertRaises(RuntimeError) as ctx:
                local_llm._ollama_json("sys", "prompt")
        self.assertIn("500", str(ctx.exception))

    def test_connection_error_is_not_retried(self):
        post = mock.Mock(side_effect=httpx.ConnectError("refused"))
        with mock.patch.object(local_llm.httpx, "post", post):
            with self.assertRaises(RuntimeError):
                local_llm._ollama_json("sys", "prompt")
        self.assertEqual(post.call_count, 1)

    def test_extract_json_ignores_surrounding_text(self):
        self.assertEqual(local_llm._extract_json('here: {"a": 1} thanks'), {"a": 1})
        with self.assertRaises(ValueError):
            local_llm._extract_json("no json here")


if __name__ == "__main__":
    unittest.main()
