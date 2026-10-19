"""Exercise real HTTP requests against an ephemeral loopback server."""

from __future__ import annotations

import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from aegml.config import Settings
from aegml.providers import (
    MAX_RESPONSE_BYTES,
    ChatCompletionsProvider,
    MockProvider,
    ProviderError,
    build_provider,
)


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.requests.append((self.path, dict(self.headers), body))
        self.send_response(self.server.status)
        if self.server.redirect:
            self.send_header("Location", self.server.redirect)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.server.body)))
        self.end_headers()
        self.wfile.write(self.server.body)

    def log_message(self, format, *args):
        pass


class ProvidersTest(unittest.TestCase):
    def test_deep_json_response_is_wrapped(self):
        self.server.body = b"[" * 10000 + b"]" * 10000
        with self.assertRaises(ProviderError):
            ChatCompletionsProvider(self.settings()).complete([])

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        self.server.requests = []
        self.server.status = 200
        self.server.redirect = None
        self.set_body({"choices": [{"message": {"content": "Ответ модели"}}]})

    def set_body(self, value):
        self.server.body = json.dumps(value, ensure_ascii=False).encode("utf-8")

    def settings(self, **overrides):
        values = {
            "provider": "chat_completions",
            "base_url": f"http://127.0.0.1:{self.server.server_port}/v1/",
            "model": "test-model",
            "api_key": "test-secret-do-not-print",
            "timeout_seconds": 2.0,
            "max_tokens": 128,
        }
        values.update(overrides)
        return Settings(**values)

    def test_request_path_headers_body_and_response(self):
        messages = [{"role": "user", "content": "Составь план"}]
        result = build_provider(self.settings()).complete(messages)
        self.assertEqual(result, "Ответ модели")
        self.assertEqual(len(self.server.requests), 1)
        path, headers, body = self.server.requests[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer test-secret-do-not-print")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(
            json.loads(body),
            {"model": "test-model", "messages": messages, "max_tokens": 128},
        )

    def test_api_key_is_optional(self):
        ChatCompletionsProvider(self.settings(api_key="")).complete([])
        self.assertNotIn("Authorization", self.server.requests[0][1])

    def test_empty_and_malformed_json(self):
        for body in (b"", b"not json", b"\xff"):
            with self.subTest(body=body):
                self.server.body = body
                with self.assertRaisesRegex(ProviderError, "JSON"):
                    build_provider(self.settings()).complete([])

    def test_response_shape_errors(self):
        for value in (
            None,
            [],
            {},
            {"choices": {}},
            {"choices": []},
            {"choices": [None]},
            {"choices": [{"message": {}}]},
            {"choices": [{"message": {"content": None}}]},
            {"choices": [{"message": {"content": [{"text": "no"}]}}]},
        ):
            with self.subTest(value=value):
                self.set_body(value)
                with self.assertRaisesRegex(ProviderError, "choices"):
                    build_provider(self.settings()).complete([])

    def test_http_error_does_not_expose_remote_body_or_key_and_has_no_retry(self):
        self.server.status = 429
        self.server.body = b"remote private body test-secret-do-not-print"
        with self.assertRaises(ProviderError) as caught:
            build_provider(self.settings()).complete([])
        self.assertIn("429", str(caught.exception))
        self.assertNotIn("private", str(caught.exception))
        self.assertNotIn("test-secret", str(caught.exception))
        self.assertEqual(len(self.server.requests), 1)

    def test_redirect_is_rejected_without_follow_up_request(self):
        self.server.status = 307
        self.server.redirect = (
            f"http://127.0.0.1:{self.server.server_port}/must-not-receive-secret"
        )
        with self.assertRaisesRegex(ProviderError, "307"):
            build_provider(self.settings()).complete([])
        self.assertEqual(len(self.server.requests), 1)

    def test_response_size_limit(self):
        self.server.body = b"x" * (MAX_RESPONSE_BYTES + 1)
        with self.assertRaisesRegex(ProviderError, "1 MiB"):
            build_provider(self.settings()).complete([])

    def test_connection_error_is_wrapped_without_credentials(self):
        # Reserve a loopback port without listening: no dependency on the internet.
        with socket.socket() as unused_port:
            unused_port.bind(("127.0.0.1", 0))
            settings = self.settings(
                base_url=f"http://127.0.0.1:{unused_port.getsockname()[1]}/v1"
            )
            with self.assertRaises(ProviderError) as caught:
                build_provider(settings).complete([])
        self.assertNotIn("test-secret", str(caught.exception))

    def test_timeout_is_passed_to_the_http_client(self):
        # Never return headers until the client has timed out.
        accepted = threading.Event()
        release = threading.Event()

        class StallHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                accepted.set()
                release.wait(timeout=2)

            def log_message(self, format, *args):
                pass

        stalled_server = HTTPServer(("127.0.0.1", 0), StallHandler)
        thread = threading.Thread(target=stalled_server.serve_forever, daemon=True)
        thread.start()
        try:
            settings = self.settings(
                base_url=f"http://127.0.0.1:{stalled_server.server_port}/v1",
                timeout_seconds=0.05,
            )
            with self.assertRaises(ProviderError):
                build_provider(settings).complete([])
            self.assertTrue(accepted.is_set())
        finally:
            release.set()
            stalled_server.shutdown()
            stalled_server.server_close()
            thread.join(timeout=2)

    def test_mock_is_deterministic_and_honest(self):
        provider = build_provider(self.settings(provider="mock"))
        self.assertIsInstance(provider, MockProvider)
        first = provider.complete([])
        self.assertEqual(first, provider.complete([{"role": "user", "content": "other"}]))
        result = json.loads(first)
        self.assertEqual(set(result), {"summary", "steps", "assumptions", "questions"})
        self.assertIsInstance(result["summary"], str)
        for key in ("steps", "assumptions", "questions"):
            self.assertIsInstance(result[key], list)
            self.assertTrue(all(isinstance(item, str) for item in result[key]))
        self.assertTrue(result["steps"])
        self.assertIn("не обучались", result["summary"])
        self.assertIn("не запускались", result["summary"])
        self.assertEqual(self.server.requests, [])


if __name__ == "__main__":
    unittest.main()
