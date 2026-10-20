"""Stdlib self-check: synthetic loopback API and tiny CSVs, never live credentials."""

import contextlib
import csv
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch


sys.dont_write_bytecode = True
_SUBJECT = None
_DUMMY_KEY = "dummy-key-for-loopback-self-check"
_PRIVATE_BODY = "synthetic-response-must-not-appear-in-report"
_ALLOWED_PORTS = set()
_REAL_CREATE_CONNECTION = socket.create_connection
_CLEAN_ENV = {
    name: os.environ[name]
    for name in ("SYSTEMROOT", "WINDIR", "SSL_CERT_FILE", "SSL_CERT_DIR", "OPENSSL_CONF")
    if name in os.environ
}
_CLEAN_ENV.update({
    name: "" for name in (
        "http_proxy", "https_proxy", "all_proxy", "ftp_proxy",
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "FTP_PROXY",
    )
})
_CLEAN_ENV.update({"no_proxy": "127.0.0.1,localhost,::1", "NO_PROXY": "127.0.0.1,localhost,::1"})


def _loopback_only(address, *args, **kwargs):
    if address[0] != "127.0.0.1" or address[1] not in _ALLOWED_PORTS:
        raise AssertionError("Self-check blocked a connection outside fixture servers")
    return _REAL_CREATE_CONNECTION(address, *args, **kwargs)


def _assistant(**message):
    return json.dumps({"choices": [{"message": {"role": "assistant", **message}}]}).encode("utf-8")


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        self.fixture_errors.append(type(sys.exception()).__name__)


class LocalServer:
    def __init__(self, body=None, status=200, headers=None, declared_length=None, chunked=False):
        self.body = _assistant(content="OK") if body is None else body
        self.status = status
        self.headers = headers or {}
        self.declared_length = declared_length
        self.chunked = chunked
        self.requests = []
        self.on_request = None
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                self.respond()

            def do_GET(self):
                self.respond()

            def respond(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                fixture.requests.append({
                    "method": self.command, "path": self.path,
                    "headers": dict(self.headers), "body": body,
                })
                if fixture.on_request is not None:
                    fixture.on_request()
                self.send_response(fixture.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Connection", "close")
                if fixture.chunked:
                    self.send_header("Transfer-Encoding", "chunked")
                else:
                    length = len(fixture.body) if fixture.declared_length is None else fixture.declared_length
                    self.send_header("Content-Length", str(length))
                for name, value in fixture.headers.items():
                    self.send_header(name, value)
                self.end_headers()
                self.close_connection = True
                try:
                    self.wfile.write(fixture.body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, format, *args):
                pass

        self.server = _Server(("127.0.0.1", 0), Handler)
        self.server.fixture_errors = []
        self.port = self.server.server_port
        self.url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )

    def __enter__(self):
        _ALLOWED_PORTS.add(self.port)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
        finally:
            _ALLOWED_PORTS.discard(self.port)
        if exc_type is None and (self.thread.is_alive() or self.server.fixture_errors):
            raise AssertionError("Fixture server did not complete cleanly")


class ApiProbeChecks(unittest.TestCase):
    def setUp(self):
        # Keep only OS/SSL runtime settings; all OPENAI_* and proxy values are replaced.
        environment = patch.dict(os.environ, _CLEAN_ENV, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        connections = patch("socket.create_connection", _loopback_only)
        connections.start()
        self.addCleanup(connections.stop)

    def configure(self, server):
        os.environ.update({
            "OPENAI_API_KEY": _DUMMY_KEY,
            "OPENAI_BASE_URL": server.url + "/v1/",
            "OPENAI_MODEL": "dummy-loopback-model",
        })

    def assert_sanitized(self, value):
        serialized = json.dumps(value)
        self.assertNotIn(_DUMMY_KEY, serialized)
        self.assertNotIn(_PRIVATE_BODY, serialized)

    def test_skipped_without_settings(self):
        result = _SUBJECT.probe_api()
        self.assertEqual(result["status"], "skipped_not_configured")
        self.assertFalse(result["attempted"])
        self.assertEqual(set(result["missing"]), {"OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"})

    def test_partial_configuration_never_connects(self):
        with LocalServer() as server:
            for missing in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
                with self.subTest(missing=missing):
                    self.configure(server)
                    os.environ.pop(missing)
                    result = _SUBJECT.probe_api()
                    self.assertEqual(result["status"], "configuration_error")
                    self.assertFalse(result["attempted"])
                    self.assertEqual(result["missing"], [missing])
            self.assertEqual(server.requests, [])

    def test_success_and_request_contract(self):
        with LocalServer() as server:
            self.configure(server)
            result = _SUBJECT.probe_api()
            self.assertEqual(result, {
                "status": "success", "attempted": True,
                "assistant_content_received": True, "reasoning_received": False,
            })
            self.assertEqual(len(server.requests), 1)
            request = server.requests[0]
            self.assertEqual((request["method"], request["path"]), ("POST", "/v1/chat/completions"))
            self.assertEqual(request["headers"]["Authorization"], "Bearer " + _DUMMY_KEY)
            self.assertEqual(request["headers"]["Content-Type"], "application/json")
            body = json.loads(request["body"])
            self.assertEqual(body["model"], "dummy-loopback-model")
            self.assertEqual(body["messages"][0]["role"], "user")
            self.assertIsInstance(body["messages"][0]["content"], str)
            self.assertEqual(body["max_tokens"], 128)
            self.assert_sanitized(result)

    def test_401_is_reported_without_retry_or_remote_body(self):
        with LocalServer(body=(_PRIVATE_BODY + _DUMMY_KEY).encode(), status=401) as server:
            self.configure(server)
            result = _SUBJECT.probe_api()
            self.assertEqual(result, {"status": "http_error", "attempted": True, "http_status": 401})
            self.assertEqual(len(server.requests), 1)
            self.assert_sanitized(result)

    def test_redirect_never_reaches_other_server_or_forwards_key(self):
        with LocalServer() as destination:
            with LocalServer(status=302, headers={"Location": destination.url + "/trap"}) as origin:
                self.configure(origin)
                result = _SUBJECT.probe_api()
                self.assertEqual(result["status"], "http_error")
                self.assertEqual(result["http_status"], 302)
                self.assertEqual(len(origin.requests), 1)
                self.assertEqual(destination.requests, [])
                self.assert_sanitized(result)

    def test_empty_malformed_and_non_utf8_response(self):
        for body in (b"", b"not-json", b"\xff"):
            with self.subTest(body_kind=body[:8]):
                with LocalServer(body=body) as server:
                    self.configure(server)
                    result = _SUBJECT.probe_api()
                    self.assertEqual(result["status"], "request_failed")
                    self.assertTrue(result["attempted"])
                    self.assert_sanitized(result)

    def test_wrong_json_shape_and_non_assistant_message(self):
        for value in (None, {}, {"choices": []}, {"choices": [None]},
                      {"choices": [{"message": {"role": "user", "content": "OK"}}]}):
            with self.subTest(shape=type(value).__name__):
                with LocalServer(body=json.dumps(value).encode()) as server:
                    self.configure(server)
                    result = _SUBJECT.probe_api()
                    self.assertEqual(result["status"], "invalid_response")
                    self.assertTrue(result["attempted"])

    def test_oversize_response_is_bounded(self):
        with LocalServer(body=b"x" * 65537) as server:
            self.configure(server)
            result = _SUBJECT.probe_api()
            self.assertEqual(result["status"], "invalid_response")
            self.assertEqual(result["reason"], "response_too_large")

    def test_reasoning_without_content_has_distinct_status(self):
        with LocalServer(body=_assistant(content=None, reasoning_content=_PRIVATE_BODY)) as server:
            self.configure(server)
            result = _SUBJECT.probe_api()
            self.assertEqual(result, {
                "status": "responded_without_final_text", "attempted": True,
                "assistant_content_received": False, "reasoning_received": True,
            })
            self.assert_sanitized(result)

    def test_truncated_content_length_does_not_raise(self):
        with LocalServer(body=b'{"choices":[', declared_length=100) as server:
            self.configure(server)
            result = _SUBJECT.probe_api()
            self.assertEqual(result["status"], "request_failed")
            self.assertTrue(result["attempted"])

    def test_truncated_chunked_response_does_not_raise(self):
        with LocalServer(body=b"10\r\nshort\r\n", chunked=True) as server:
            self.configure(server)
            result = _SUBJECT.probe_api()
            self.assertEqual(result["status"], "request_failed")
            self.assertEqual(result["error_type"], "IncompleteRead")

    def test_deep_json_does_not_raise(self):
        # JSON's C decoder can have a different limit from Python frames (3.12).
        # This remains a small 20 KiB response, below the probe's response cap.
        depth = 10000
        with LocalServer(body=b"[" * depth + b"0" + b"]" * depth) as server:
            self.configure(server)
            result = _SUBJECT.probe_api()
            self.assertEqual(result["status"], "request_failed")
            self.assertEqual(result["error_type"], "RecursionError")

    def test_tiny_run_keeps_csv_and_reports_api_error(self):
        with tempfile.TemporaryDirectory(prefix="aegml-api-selfcheck-") as temporary:
            directory = Path(temporary)
            contents = {
                "task.md": "Synthetic regression. Metric: RMSE. Use `train.csv` and `test.csv`.\n",
                "train.csv": "feature,target,id\n1,2,train-1\n2,4,train-2\n",
                "test.csv": "feature,id\n3,test-1\n4,test-2\n",
                "data_dictionary.csv": "feature,role\nfeature,feature\ntarget,target\nid,id\n",
                "sample_submission.csv": "id,target\ntest-1,0\ntest-2,0\n",
            }
            for name, content in contents.items():
                (directory / name).write_text(content, encoding="utf-8")
            original = {name: (directory / name).read_bytes() for name in contents}
            before_api = []
            with LocalServer(body=_PRIVATE_BODY.encode(), status=401) as server:
                self.configure(server)
                server.on_request = lambda: before_api.append((directory / "submission.csv").read_bytes())
                captured = io.StringIO()
                with contextlib.redirect_stdout(captured):
                    _SUBJECT.run(directory / "task.md")
                self.assertEqual(len(server.requests), 1)
            output = (directory / "submission.csv").read_bytes()
            self.assertEqual(before_api, [output])
            with (directory / "submission.csv").open(encoding="utf-8", newline="") as stream:
                records = list(csv.DictReader(stream))
            self.assertEqual(records, [{"id": "test-1", "target": "3"}, {"id": "test-2", "target": "3"}])
            report = json.loads((directory / "mini_diagnostics.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "completed_format_only")
            self.assertEqual(report["api_probe"]["status"], "http_error")
            self.assertEqual(report["api_probe"]["http_status"], 401)
            self.assertTrue(report["api_used"])
            self.assertFalse(report["autoresearch_performed"])
            self.assertFalse(report["quality_assessed"])
            self.assertEqual(report["submission_sha256"], _SUBJECT.digest(directory / "submission.csv"))
            events = [json.loads(line) for line in captured.getvalue().splitlines()]
            self.assertEqual(events[-1]["api_status"], "http_error")
            self.assert_sanitized(report)
            self.assert_sanitized(events)
            self.assertEqual(original, {name: (directory / name).read_bytes() for name in contents})


def main():
    global _SUBJECT
    try:
        spec = importlib.util.spec_from_file_location("aegml_testmini_api_subject", Path(__file__).with_name("solution.py"))
        _SUBJECT = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_SUBJECT)
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ApiProbeChecks)
        result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
        failed = [{"case": case.id().split(".")[-1], "kind": kind}
                  for kind, rows in (("failure", result.failures), ("error", result.errors))
                  for case, _ in rows]
        summary = {"check": "testmini_api_loopback", "status": "passed" if result.wasSuccessful() else "failed",
                   "python": sys.version.split()[0], "tests": result.testsRun, "failed": failed,
                   "live_api_used": False, "user_data_used": False}
        exit_code = 0 if result.wasSuccessful() else 1
    except Exception as error:
        summary = {"check": "testmini_api_loopback", "status": "failed", "stage": "selfcheck_setup",
                   "error_type": type(error).__name__, "live_api_used": False, "user_data_used": False}
        exit_code = 1
    print(json.dumps(summary, ensure_ascii=True, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
