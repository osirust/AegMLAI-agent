"""Stdlib H02.2 checks only; no fit, provider request, installation, or task parsing.

Run under the authorized Linux Python 3.12 environment:
    python scripts/check_h02_bootstrap.py --receipt PATH

Production CLI fixtures receive only the three allowlisted root files. One test
explicitly instruments a COPY of contracts with a short import sleep. These tests
do not establish an OS sandbox, hard timeout, official-image or full-agent PASS.
"""

import argparse
import ast
from contextlib import contextmanager
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_FILES = ("solution.py", "aegml_contracts.py", "requirements.txt")
ORIGINAL_REQUIREMENTS = ROOT / "drive-download-20261019T181414Z-1-001" / "requirements.txt"
EXPECTED_REQUIREMENTS_SHA256 = "9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6"
NS = 1_000_000_000
KEY_CANARY = "H02_BOOTSTRAP_DUMMY_KEY_CANARY_87a1"
URL_PASSWORD_CANARY = "H02_BOOTSTRAP_DUMMY_URL_PASSWORD_91b2"
URL_CANARY = "https://fixture-user:" + URL_PASSWORD_CANARY + "@provider.invalid/v1"
MODEL_CANARY = "H02_BOOTSTRAP_DUMMY_MODEL_CANARY_29c3"
CANARIES = (URL_CANARY, URL_PASSWORD_CANARY, KEY_CANARY, MODEL_CANARY)
COMPLETE_API = {
    "OPENAI_API_KEY": KEY_CANARY,
    "OPENAI_BASE_URL": URL_CANARY,
    "OPENAI_MODEL": MODEL_CANARY,
}
THREAD_NAMES = (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS",
)
CASES = []
COMMANDS = []
CONTRACTS = None


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def redact(value):
    """Only synthetic canaries exist here; still keep them out of the receipt."""
    if isinstance(value, str):
        for canary in CANARIES:
            value = value.replace(canary, "<synthetic-canary-redacted>")
        return value
    if isinstance(value, dict):
        return {str(key): redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


class Clock:
    def __init__(self, seconds=0):
        self.now = int(seconds * NS)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += int(seconds * NS)


@contextmanager
def preserve_thread_environment():
    # Snapshot only thread settings, never provider configuration or all environ.
    original = {name: os.environ.get(name) for name in THREAD_NAMES}
    try:
        yield
    finally:
        for name, value in original.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class BootstrapChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="aegml-h022-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.stage = self.base / "плоский код с пробелами"
        self.stage.mkdir()
        for name in PRODUCTION_FILES:
            shutil.copyfile(ROOT / name, self.stage / name)
        self.task = self.stage / "task.md"
        self.task.write_text("Synthetic H02.2 fixture. No interpretation or dataset is required.\n", encoding="utf-8")
        self.input_hashes = {name: sha(self.stage / name) for name in (*PRODUCTION_FILES, "task.md")}

    @contextmanager
    def case(self, name):
        record = {"test": self.id(), "case": name, "status": "RUNNING"}
        CASES.append(record)
        try:
            yield
        except BaseException:
            record["status"] = "FAIL"
            raise
        else:
            record["status"] = "PASS"

    def assert_no_canary(self, text):
        # assertNotIn would print the secret-like canary and captured output.
        self.assertTrue(all(value not in text for value in CANARIES), "synthetic secret leaked; value/output suppressed")

    def child_env(self, overrides=None):
        # Never read or copy OPENAI_*, personal proxy, .env, PYTHONPATH or HOME.
        env = {
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.defpath,
            "LANG": "C.UTF-8",
            "PYTHONUTF8": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        env.update(overrides or {})
        return env

    def cli(self, args=None, *, cwd=None, env=None, reason=None, code=3, instrumented=False, entrypoint="solution.py"):
        args = ["task.md"] if args is None else args
        command = ["python3", entrypoint, *args]
        record = {
            "argv": redact(command), "cwd": str(cwd or self.stage),
            "environment_names_set": sorted(self.child_env(env)),
            "instrumented_contracts_copy": instrumented,
            "staged_source_sha256": {name: sha(self.stage / name) for name in PRODUCTION_FILES},
            "timeout_seconds": 15,
        }
        COMMANDS.append(record)
        watched = [self.stage / name for name in PRODUCTION_FILES]
        if self.task.exists():
            watched.append(self.task)
        source_before = {str(path): sha(path) for path in watched}
        csv = self.stage / "submission.csv"
        csv_before = (sha(csv), csv.stat().st_mtime_ns) if csv.exists() else None
        result = subprocess.run(command, cwd=cwd or self.stage, env=self.child_env(env),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                encoding="utf-8", timeout=15, check=False)
        record.update({"exit_code": result.returncode, "stdout_bytes_utf8": len(result.stdout.encode("utf-8")),
                       "stderr_bytes_utf8": len(result.stderr.encode("utf-8"))})
        self.assert_no_canary(result.stdout + result.stderr)
        self.assertEqual(result.returncode, code, "unexpected CLI exit code; captured output suppressed")
        self.assertEqual(result.stderr, "", "CLI stderr must be empty; captured output suppressed")
        self.assertEqual({str(path): sha(path) for path in watched}, source_before,
                         "CLI changed a staged source/input")
        if csv_before is None:
            self.assertFalse(csv.exists(), "bootstrap created a CSV before the agent exists")
        else:
            self.assertEqual((sha(csv), csv.stat().st_mtime_ns), csv_before,
                             "bootstrap changed an existing CSV")
        record["staged_sources_and_existing_csv_preserved"] = True
        if code == 0:
            return result, None
        try:
            outcome = json.loads(result.stdout)
        except (ValueError, TypeError):
            self.fail("CLI must emit one JSON outcome; captured output suppressed")
        self.assertIsInstance(outcome, dict)
        self.assertEqual(outcome.get("exit_code"), code)
        self.assertEqual(outcome.get("schema_version"), "bootstrap.v1")
        self.assertEqual(outcome.get("phase"), "H02.2")
        self.assertEqual(outcome.get("status"), "failed")
        if reason is not None:
            self.assertEqual(outcome.get("termination_reason"), reason)
        self.assert_unfinished(outcome)
        record["outcome"] = redact(outcome)
        return result, outcome

    def assert_unfinished(self, outcome):
        for name in ("contract_valid", "api_verified", "tools_verified", "research_completed", "submission_valid"):
            self.assertIs(outcome.get(name), False, name + " must not claim full-agent acceptance")
        self.assertEqual(outcome.get("experiments_completed"), 0)

    def assert_inputs_unchanged(self):
        for name, expected in self.input_hashes.items():
            self.assertEqual(sha(self.stage / name), expected, "staged source/input was modified")

    def unit_bootstrap(self, *, args=None, env=None, clock=None, started_ns=0):
        clock = Clock(1) if clock is None else clock
        # configure_threads changes only these process-local variables; restore them.
        with preserve_thread_environment():
            return CONTRACTS.bootstrap([str(self.task)] if args is None else args,
                                       started_ns=started_ns, clock=clock,
                                       env={} if env is None else env)

    def test_exact_platform_command_selective_copy(self):
        with self.case("literal_python3_solution_py_task_md"):
            self.assertEqual({p.name for p in self.stage.iterdir()}, {*PRODUCTION_FILES, "task.md"})
            self.assertEqual(sha(self.stage / "requirements.txt"), EXPECTED_REQUIREMENTS_SHA256)
            if ORIGINAL_REQUIREMENTS.is_file():
                self.assertEqual(sha(ORIGINAL_REQUIREMENTS), EXPECTED_REQUIREMENTS_SHA256)
            _, outcome = self.cli(reason="implementation_incomplete")
            self.assertTrue(outcome["entrypoint_ready"])
            self.assertEqual(outcome["api_settings_state"], "missing")
            self.assertIs(outcome["timer"]["cooperative_only"], True)
            self.assertFalse((self.stage / "submission.csv").exists())
            self.assert_inputs_unchanged()

    def test_default_task(self):
        with self.case("default_task_md_from_cwd"):
            self.cli([], reason="implementation_incomplete")
            self.assert_inputs_unchanged()

    def test_task_paths_and_config_paths(self):
        outside = self.base / "данные с пробелами"
        outside.mkdir()
        task = outside / "условие задачи.md"
        task.write_text("Synthetic path-only task fixture.\n", encoding="utf-8")
        task_sha = sha(task)
        variants = [("absolute_unicode_spaces", str(task)),
                    ("relative_unicode_spaces", os.path.relpath(task, self.stage))]
        for label, path in variants:
            with self.subTest(case=label), self.case(label):
                self.cli([path], reason="implementation_incomplete")
                cfg = CONTRACTS.parse_config([path], {}, started_ns=0, clock=Clock(1)) if Path(path).is_absolute() else None
                if cfg is not None:
                    self.assertEqual(cfg.task_path, task.resolve())
                    self.assertEqual(cfg.output_path, task.parent / "submission.csv")
                self.assertEqual(sha(task), task_sha)
                self.assertFalse((outside / "submission.csv").exists())

    def test_entrypoint_from_different_cwd(self):
        with self.case("absolute_entrypoint_from_other_cwd_no_pythonpath"):
            outside = self.base / "другая рабочая папка"
            outside.mkdir()
            task = outside / "task.md"
            task.write_text("Synthetic H02.2 alternate cwd fixture.\n", encoding="utf-8")
            initial = sha(task)
            self.cli(["task.md"], cwd=outside, entrypoint=str(self.stage / "solution.py"),
                     reason="implementation_incomplete")
            self.assertEqual(sha(task), initial)
            self.assertFalse((outside / "submission.csv").exists())

    def test_argv_overrides_allowlisted_env(self):
        with self.case("argv_precedence_over_invalid_env_values"):
            env = {"AEGML_TIME_LIMIT_SECONDS": "not-a-number", "AEGML_FINALIZE_RESERVE_SECONDS": "not-a-number",
                   "AEGML_THREADS": "not-a-number", **COMPLETE_API}
            _, outcome = self.cli(["task.md", "--time-limit-seconds", "120", "--finalize-reserve-seconds", "7", "--threads", "2"],
                                  env=env, reason="implementation_incomplete")
            self.assertEqual(outcome["timer"]["total_seconds"], 120)
            self.assertEqual(outcome["timer"]["reserve_seconds"], 7)
            self.assertEqual(outcome["api_settings_state"], "complete_unverified")

    def test_env_config_and_thread_variables(self):
        with self.case("env_budget_threads_and_nonsecret_repr"):
            env = {"AEGML_TIME_LIMIT_SECONDS": "90", "AEGML_FINALIZE_RESERVE_SECONDS": "5", "AEGML_THREADS": "3", **COMPLETE_API}
            cfg = CONTRACTS.parse_config([str(self.task)], env, started_ns=0, clock=Clock(1))
            self.assertEqual((cfg.budget.total_seconds, cfg.budget.reserve_seconds, cfg.threads), (90, 5, 3))
            self.assertEqual(cfg.output_path, self.stage / "submission.csv")
            self.assert_no_canary(repr(cfg))
            with preserve_thread_environment():
                for name in THREAD_NAMES:
                    os.environ[name] = "99"
                outcome = CONTRACTS.bootstrap([str(self.task)], started_ns=0, clock=Clock(1), env=env)
                self.assertEqual({os.environ[name] for name in THREAD_NAMES}, {"3"})
                self.assertEqual(outcome.exit_code, 3)
                self.assert_no_canary(repr(outcome) + json.dumps(outcome.public_dict()))

    def test_api_setting_states_no_verification_claim(self):
        variants = [("missing", {}), ("partial_unverified", {"OPENAI_API_KEY": KEY_CANARY}),
                    ("partial_unverified", {"OPENAI_BASE_URL": URL_CANARY, "OPENAI_MODEL": MODEL_CANARY}),
                    ("complete_unverified", COMPLETE_API),
                    ("missing", {name: "  " for name in COMPLETE_API})]
        for index, (state, env) in enumerate(variants):
            with self.subTest(case=index), self.case("api_settings_" + str(index) + "_" + state):
                _, outcome = self.cli(env=env, reason="implementation_incomplete")
                self.assertEqual(outcome["api_settings_state"], state)

    def test_unknown_argument_does_not_echo_secret(self):
        with self.case("unknown_api_key_argument_is_redacted"):
            _, outcome = self.cli(["task.md", "--api-key", KEY_CANARY], env=COMPLETE_API,
                                  code=2, reason="invalid_arguments")
            self.assertFalse(outcome["entrypoint_ready"])
            self.assertFalse((self.stage / "submission.csv").exists())

    def test_extra_argument_and_no_abbreviation(self):
        variants = [["task.md", "extra.md"], ["task.md", "--time-limit", "120"]]
        for index, args in enumerate(variants):
            with self.subTest(case=index), self.case("invalid_argv_" + str(index)):
                self.cli(args, code=2, reason="invalid_arguments")

    def test_missing_and_directory_task(self):
        for label, path in (("missing_task", self.stage / "absent.md"), ("directory_task", self.stage)):
            with self.subTest(case=label), self.case(label):
                _, outcome = self.cli([str(path)], code=2, reason="invalid_task_path")
                self.assertIn("total_seconds", outcome["timer"], "H02-BOOT-001: post-budget path error lost timer")
                self.assert_inputs_unchanged()

    def test_invalid_time_limits(self):
        for value in ("nan", "inf", "-inf", "0", "-1", "10801", "text", "1e-20"):
            with self.subTest(case=value), self.case("invalid_time_" + value):
                self.cli(["task.md", "--time-limit-seconds=" + value], code=2, reason="invalid_time_limit")

    def test_invalid_reserves(self):
        for value in ("-1", "10", "11", "nan", "inf", "text"):
            with self.subTest(case=value), self.case("invalid_reserve_" + value):
                self.cli(["task.md", "--time-limit-seconds=10", "--finalize-reserve-seconds=" + value],
                         code=2, reason="invalid_finalize_reserve")

    def test_invalid_threads_keep_budget_snapshot(self):
        for value in ("0", "9", "text", "1.5"):
            with self.subTest(case=value), self.case("invalid_threads_" + value):
                _, outcome = self.cli(["task.md", "--threads=" + value], code=2, reason="invalid_threads")
                self.assertIn("total_seconds", outcome["timer"], "H02-BOOT-001: thread error lost timer")

    def test_existing_csv_and_sources_are_preserved(self):
        with self.case("incomplete_preserves_existing_csv_bytes_and_mtime"):
            output = self.stage / "submission.csv"
            payload = b"id,prediction\nfixture-only,123\n"
            output.write_bytes(payload)
            os.utime(output, ns=(1_600_000_000_123_456_789, 1_600_000_000_123_456_789))
            before = (sha(output), output.stat().st_mtime_ns)
            self.cli(env=COMPLETE_API, reason="implementation_incomplete")
            self.assertEqual((sha(output), output.stat().st_mtime_ns), before)
            self.assert_inputs_unchanged()
            self.assertEqual({p.name for p in self.stage.iterdir()}, {*PRODUCTION_FILES, "task.md", "submission.csv"})

    def test_help_is_not_agent_success(self):
        with self.case("help_zero_without_task_or_output"):
            self.task.unlink()
            result, outcome = self.cli(["--help"], env=COMPLETE_API, code=0)
            self.assertIsNone(outcome)
            self.assertIn("bootstrap", result.stdout)
            self.assertFalse((self.stage / "submission.csv").exists())

    def test_shared_monotonic_deadlines_and_required_cost(self):
        with self.case("shared_clock_deadline_work_reserve_and_no_reset"):
            clock = Clock(100)
            budget = CONTRACTS.RunBudget(clock(), 20, 4, clock)
            original_deadline = budget.deadline_ns
            clock.advance(7)
            self.assertEqual(budget.elapsed_seconds(), 7)
            self.assertEqual(budget.remaining_seconds(), 9)
            self.assertEqual(budget.remaining_seconds(finalizing=True), 13)
            self.assertEqual(budget.require(8), 9)
            with self.assertRaises(CONTRACTS.ActionBudgetInsufficient):
                budget.require(10)
            clock.advance(9)
            with self.assertRaises(CONTRACTS.BudgetExpired):
                budget.require()
            self.assertEqual(budget.require(3, finalizing=True), 4)
            clock.advance(4)
            with self.assertRaises(CONTRACTS.BudgetExpired):
                budget.require(finalizing=True)
            self.assertEqual(budget.deadline_ns, original_deadline)
            self.assertEqual(budget.started_ns, 100 * NS)
            self.assertEqual(budget.snapshot()["remaining_seconds"], 0)

    def test_invalid_required_cost(self):
        for value in (-1, float("nan"), float("inf"), "text"):
            with self.subTest(case=str(value)), self.case("invalid_required_cost_" + str(value)):
                budget = CONTRACTS.RunBudget(0, 20, 4, Clock(1))
                with self.assertRaises(CONTRACTS.BootstrapError):
                    budget.require(value)

    def test_expiry_path_threads_snapshot_regression(self):
        variants = [
            ("expiry", [str(self.task)], {}, Clock(10801), 124, "deadline_exhausted"),
            ("path", [str(self.stage / "missing.md")], COMPLETE_API, Clock(1), 2, "invalid_task_path"),
            ("threads", [str(self.task)], {"AEGML_THREADS": "text", **COMPLETE_API}, Clock(1), 2, "invalid_threads"),
        ]
        for label, args, env, clock, code, reason in variants:
            with self.subTest(case=label), self.case("H02-BOOT-001_" + label):
                outcome = self.unit_bootstrap(args=args, env=env, clock=clock)
                self.assertEqual((outcome.exit_code, outcome.termination_reason), (code, reason))
                public = outcome.public_dict()
                self.assert_unfinished(public)
                self.assertEqual(public["timer"]["total_seconds"], 10800)
                self.assertEqual(public["timer"]["reserve_seconds"], 600)
                self.assertEqual(public["timer"]["elapsed_seconds"], 10801 if label == "expiry" else 1)
                self.assertIs(public["timer"]["cooperative_only"], True)
                self.assert_no_canary(repr(outcome) + json.dumps(public))

    def assert_internal_fault_outcome(self, outcome):
        self.assertEqual((outcome.exit_code, outcome.termination_reason), (1, "bootstrap_internal_error"))
        public = outcome.public_dict()
        self.assert_unfinished(public)
        self.assertIs(public["timer"]["cooperative_only"], True)
        encoded = json.dumps(public, allow_nan=False)
        self.assert_no_canary(repr(outcome) + encoded)
        return public

    def fault_bootstrap(self, **kwargs):
        try:
            return self.unit_bootstrap(**kwargs)
        except Exception:
            # An escaping injected exception must not reveal its canary in a traceback.
            raise AssertionError("bootstrap fault escaped; original diagnostic suppressed") from None

    def test_internal_error_keeps_timer(self):
        with self.case("H02-BOOT-002_configure_threads_internal_error_timer"):
            with mock.patch.object(CONTRACTS, "configure_threads", side_effect=RuntimeError(KEY_CANARY)):
                outcome = self.fault_bootstrap(clock=Clock(2), env=COMPLETE_API)
            public = self.assert_internal_fault_outcome(outcome)
            self.assertEqual(public["timer"]["elapsed_seconds"], 2)
            self.assertEqual(public["timer"]["total_seconds"], 10800)

    def test_snapshot_fault_uses_elapsed_fallback(self):
        with self.case("H02-BOOT-002_snapshot_fault_elapsed_fallback"):
            with mock.patch.object(CONTRACTS.RunBudget, "snapshot", side_effect=RuntimeError(KEY_CANARY)):
                outcome = self.fault_bootstrap(clock=Clock(2), env=COMPLETE_API)
            public = self.assert_internal_fault_outcome(outcome)
            self.assertEqual(public["timer"]["elapsed_seconds"], 2)

    def test_broken_clock_returns_safe_diagnostic(self):
        with self.case("H02-BOOT-002_broken_clock_safe_outcome"):
            def broken_clock():
                raise RuntimeError(KEY_CANARY)

            outcome = self.fault_bootstrap(clock=broken_clock, env=COMPLETE_API)
            public = self.assert_internal_fault_outcome(outcome)
            self.assertTrue(public["timer"].get("diagnostic_unavailable"), "missing clock-unavailable diagnostic")

    def test_action_budget_insufficient_is_not_expiry(self):
        with self.case("H02-BOOT-003_admission_reject_preserves_available_time"):
            clock = Clock(20)
            budget = CONTRACTS.RunBudget(0, 100, 10, clock)
            deadline = budget.deadline_ns
            with self.assertRaises(CONTRACTS.ActionBudgetInsufficient) as caught:
                budget.require(71)
            self.assertNotIsInstance(caught.exception, CONTRACTS.BudgetExpired)
            self.assertEqual(str(caught.exception), "insufficient_action_budget")
            self.assertIs(caught.exception.budget, budget)
            self.assertEqual(budget.require(5), 70)
            self.assertEqual(budget.deadline_ns, deadline)
            self.assertEqual(clock(), 20 * NS)
            clock.advance(70)
            with self.assertRaises(CONTRACTS.BudgetExpired):
                budget.require(0)

    def test_python_version_guard(self):
        with self.case("controlled_non312_version_guard"):
            with mock.patch.object(CONTRACTS.sys, "version_info", (3, 11, 0)):
                outcome = self.unit_bootstrap()
            self.assertEqual((outcome.exit_code, outcome.termination_reason), (2, "unsupported_python_version"))

    def test_import_time_is_included_in_budget(self):
        with self.case("instrumented_contracts_import_sleep_consumes_budget"):
            path = self.stage / "aegml_contracts.py"
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            insertion = 0
            for node in tree.body:
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and insertion == 0:
                    insertion = node.end_lineno
                elif isinstance(node, ast.ImportFrom) and node.module == "__future__":
                    insertion = node.end_lineno
                else:
                    break
            lines = source.splitlines(keepends=True)
            lines[insertion:insertion] = ["\nimport time as _h022_fixture_time\n_h022_fixture_time.sleep(0.15)\n"]
            path.write_text("".join(lines), encoding="utf-8")
            _, outcome = self.cli(["task.md", "--time-limit-seconds=0.05", "--finalize-reserve-seconds=0"],
                                  code=124, reason="deadline_exhausted", instrumented=True)
            self.assertGreaterEqual(outcome["timer"]["elapsed_seconds"], 0.10)
            self.assertEqual(outcome["timer"]["remaining_seconds"], 0)
            self.assertFalse((self.stage / "submission.csv").exists())


def main():
    global CONTRACTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    sources = (*PRODUCTION_FILES, "scripts/check_h02_bootstrap.py")
    before = {name: sha(ROOT / name) for name in sources}
    receipt = {
        "phase": "H02.2", "status": "NOT_RUN", "python": platform.python_version(),
        "executable": sys.executable, "platform": platform.platform(), "source_sha256": before,
        "provided_requirements_sha256_expected": EXPECTED_REQUIREMENTS_SHA256,
        "original_requirements_present": ORIGINAL_REQUIREMENTS.is_file(),
        "original_requirements_sha256": sha(ORIGINAL_REQUIREMENTS) if ORIGINAL_REQUIREMENTS.is_file() else None,
        "scope": "CLI/selective root copy/config/secret-canaries/cooperative timer/bootstrap outcomes only",
        "model_training_executed": False, "live_api_called": False, "package_installation_executed": False,
        "docker_or_os_boundary_tested": False, "official_platform_image_verified": False,
        "task_contract_or_metric_adapter_accepted": False,
        "instrumented_import_fixture_is_not_a_production_execution": True,
        "child_test_environment_disables_bytecode_writes": True,
        "notes": ["Synthetic task text is not interpreted; no real datasets or credentials are read.",
                  "Child environment is explicitly built and does not inherit provider configuration.",
                  "No hard timeout, process-tree, ML, live tools, sandbox or three-hour acceptance is claimed.",
                  "A production CLI fixture returns exit 3 honestly until the agent is implemented."],
    }
    if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
        receipt.update(status="BLOCKED_WRONG_CHECK_ENVIRONMENT", test_methods_run=0,
                       behavior_cases_checked=0, cli_invocations=0)
        code = 2
    else:
        sys.path.insert(0, str(ROOT))  # Development runner only; child CLI gets no PYTHONPATH.
        try:
            CONTRACTS = importlib.import_module("aegml_contracts")
            if Path(CONTRACTS.__file__).resolve() != (ROOT / "aegml_contracts.py").resolve():
                raise RuntimeError("unexpected contracts import location")
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(BootstrapChecks)
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            after = {name: sha(ROOT / name) for name in sources}
            stable = before == after
            passed = result.wasSuccessful() and stable
            receipt.update(
                status="PASS_H02_2_BOOTSTRAP_ONLY" if passed else "FAIL_H02_2_BOOTSTRAP_CHECK",
                test_methods_run=result.testsRun, behavior_cases_checked=len(CASES),
                behavior_cases_passed=sum(case["status"] == "PASS" for case in CASES),
                cli_invocations=len(COMMANDS), cases=CASES, commands=COMMANDS,
                unittest_failures=[{"test": test.id(), "detail": redact(detail)} for test, detail in result.failures],
                unittest_errors=[{"test": test.id(), "detail": redact(detail)} for test, detail in result.errors],
                source_unchanged_during_check=stable, source_sha256_after=after,
            )
            code = 0 if passed else 1
        except Exception as exc:
            receipt.update(status="FAIL_CHECK_SETUP", error_type=type(exc).__name__,
                           test_methods_run=0, behavior_cases_checked=len(CASES), cli_invocations=len(COMMANDS))
            code = 1
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(redact(receipt), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "receipt": str(args.receipt),
                      "test_methods_run": receipt["test_methods_run"],
                      "behavior_cases_checked": receipt["behavior_cases_checked"],
                      "cli_invocations": receipt["cli_invocations"]}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
