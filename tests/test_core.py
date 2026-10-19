import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aegml.cli import main
from aegml.config import Settings
from aegml.contracts import TaskSpec, parse_plan
from aegml.profiling import profile_csv
from aegml.providers import MockProvider, ProviderError
from aegml.runner import run


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.task = self.root / "task.json"
        self.task.write_text(json.dumps({"task_id": "demo", "goal": "Plan only"}), encoding="utf-8")
        self.data = self.root / "data.csv"
        self.data.write_bytes(b"a,b\n1,private-row-value\n2, \n")

    def test_profile_counts_missing_and_hashes_exact_bytes(self):
        profile, digest = profile_csv(self.data)
        self.assertEqual(profile["row_count"], 2)
        self.assertEqual(profile["column_count"], 2)
        self.assertEqual(profile["columns"], [{"name": "a", "missing_count": 0}, {"name": "b", "missing_count": 1}])
        self.assertEqual(digest, hashlib.sha256(self.data.read_bytes()).hexdigest())

    def test_profile_rejects_bad_shapes_empty_and_missing_target(self):
        for raw in (b"a,a\n1,2\n", b"a,b\n1\n", b"a, \n1,2\n", b"a,b\n", b"", b'a,b\n1,"unterminated'):
            with self.subTest(raw=raw):
                self.data.write_bytes(raw)
                with self.assertRaises(ValueError):
                    profile_csv(self.data)
        self.data.write_bytes(b"a,b\n1,2\n")
        with self.assertRaisesRegex(ValueError, "target_column"):
            profile_csv(self.data, "absent")

    def test_profile_accepts_bom_and_quoted_newline(self):
        self.data.write_bytes(b'\xef\xbb\xbfa,b\r\n1,"two\nlines"\r\n')
        profile, _ = profile_csv(self.data)
        self.assertEqual(profile["row_count"], 1)
        self.assertEqual(profile["columns"][0]["name"], "a")

    def test_contract_rejects_invalid_types_extra_fields_and_fake_plan(self):
        invalid = [{}, {"task_id": "x", "goal": "x", "seed": True}, {"task_id": "x", "goal": "x", "extra": 1}]
        invalid += [{"task_id": "x", "goal": "x", "task_type": value} for value in ([], {}, None, True)]
        for task in invalid:
            with self.subTest(task=task), self.assertRaises(ValueError):
                TaskSpec.from_dict(task)
        for raw in ('not json', '{}', '[]', '{"summary":"x","steps":[],"assumptions":[],"questions":[]}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_plan(raw)
        self.assertTrue(parse_plan(MockProvider().complete([]))["steps"])

    def test_mock_runs_leave_unique_traceable_artifacts_and_no_raw_rows(self):
        outputs = self.root / "runs"
        settings = Settings(api_key="never-save-this-key")
        first = run(self.task, self.data, outputs, settings)
        before = {p.name: p.read_bytes() for p in first.iterdir()}
        second = run(self.task, self.data, outputs, settings)
        self.assertNotEqual(first, second)
        self.assertEqual(before, {p.name: p.read_bytes() for p in first.iterdir()})
        manifest = json.loads((first / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["mode"], "demo")
        self.assertIs(manifest["executed_training"], False)
        self.assertEqual(manifest["task_sha256"], hashlib.sha256(self.task.read_bytes()).hexdigest())
        self.assertEqual(manifest["data_sha256"], hashlib.sha256(self.data.read_bytes()).hexdigest())
        for name, digest in manifest["artifact_sha256"].items():
            self.assertEqual(digest, hashlib.sha256((first / name).read_bytes()).hexdigest())
        all_text = "\n".join(p.read_text(encoding="utf-8") for p in first.iterdir())
        self.assertNotIn("never-save-this-key", all_text)
        self.assertNotIn("private-row-value", all_text)
        request = json.loads((first / "request.json").read_text(encoding="utf-8"))
        self.assertEqual(json.loads(request["messages"][1]["content"])["csv_profile"]["row_count"], 2)
        self.assertEqual(json.loads((first / "plan.json").read_text(encoding="utf-8")), json.loads((second / "plan.json").read_text(encoding="utf-8")))

    def test_task_without_dataset(self):
        result = run(self.task, None, self.root / "runs", Settings())
        self.assertIsNone(json.loads((result / "profile.json").read_text(encoding="utf-8")))

    def test_deep_json_is_reported_as_invalid_input_or_plan(self):
        deep = "[" * 10000 + "]" * 10000
        with self.assertRaises(ValueError):
            parse_plan(deep)
        self.task.write_text(deep, encoding="utf-8")
        err = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(err):
            self.assertEqual(main(["run", "--task", str(self.task)]), 1)
        self.assertIn("Ошибка", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_provider_and_schema_failures_persist_failed_run(self):
        for failure in (ProviderError("unavailable"), "not-json", "[" * 10000 + "]" * 10000):
            provider = Mock()
            if isinstance(failure, Exception):
                provider.complete.side_effect = failure
            else:
                provider.complete.return_value = failure
            output = self.root / str(len(list(self.root.iterdir())))
            with patch("aegml.runner.build_provider", return_value=provider):
                with self.assertRaises(ValueError):
                    run(self.task, self.data, output, Settings())
            run_dir = next(output.iterdir())
            manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "failed")
            self.assertFalse((run_dir / "plan.json").exists())
            self.assertIn('"event": "run_failed"', (run_dir / "events.jsonl").read_text())

    def test_config_offline_default_and_endpoint_validation(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Settings.from_env().provider, "mock")
        for endpoint in ("http://example.com/v1", "https://user:secret@example.com/v1", "https://example.com/v1?token=secret", "file:///tmp/x", "https://example.com:bad/v1"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                Settings(provider="chat_completions", model="test", base_url=endpoint)
        for endpoint in ("http://localhost:11434/v1", "http://127.0.0.1:8000/v1", "http://[::1]:8000/v1", "https://example.com/v1"):
            Settings(provider="chat_completions", model="test", base_url=endpoint)
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                Settings(timeout_seconds=timeout)
        self.assertNotIn("secret-key", repr(Settings(api_key="secret-key")))

    def test_cli_machine_readable_success_and_nonzero_error(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(main(["run", "--task", str(self.task), "--output-dir", str(self.root / "runs")]), 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "completed")
        self.assertEqual(err.getvalue(), "")
        for value in ([], {}, None, True):
            self.task.write_text(json.dumps({"task_id": "x", "goal": "x", "task_type": value}), encoding="utf-8")
            err = io.StringIO()
            with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(err):
                self.assertEqual(main(["run", "--task", str(self.task)]), 1)
            self.assertIn("Ошибка", err.getvalue())
            self.assertNotIn("Traceback", err.getvalue())
