"""Mock-only H02.4 trusted CLI-checker regressions; no Docker/API/ML.

Run under the authorized Linux Python 3.12 environment with --receipt NEW.json.
Optionally pass --before-checker historical.py for the fixed historical SHA.
All checker invocations use synthetic temporary ROOTs and a subprocess.run
double inside a separate Python interpreter, including explicit -O coverage.
No production source, real dataset, private configuration or container is edited.
"""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts/check_h024_platform_cli.py"
BEFORE_SHA = "01cfba293a37f15ab4dc060ffafbee16ef57848fa083b171fe676fda5d875e1a"
BEFORE_CHECKER = None
CASES, INVOCATIONS = [], []
IMAGE = "sha256:" + "9" * 64
SOURCES = ("solution.py", "aegml_contracts.py", "aegml_input.py", "aegml_schemas.py", "requirements.txt")
SENTINEL = b'{"fixture":"prior-receipt-must-survive"}\n'


DRIVER = r'''
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

root, scenario, receipt = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
checker = root / "scripts/check_h024_platform_cli.py"
IMAGE = "sha256:" + "9" * 64
SENTINEL = b'{"fixture":"prior-receipt-must-survive"}\n'
RealCompletedProcess = subprocess.CompletedProcess
RealCalledProcessError = subprocess.CalledProcessError


class FakeDocker:
    def __init__(self):
        self.actions = []
        self.containers = {}
        self.starts = 0
        self.created = 0
        self.race_snapshot = None
        self.foreign_id = "f" * 64

    def answer(self, command, rc=0, stdout="", stderr="", **kwargs):
        text = bool(kwargs.get("text") or kwargs.get("universal_newlines") or kwargs.get("encoding"))
        if not text:
            stdout, stderr = stdout.encode(), stderr.encode()
        if kwargs.get("check") and rc:
            raise RealCalledProcessError(rc, command, output=stdout, stderr=stderr)
        return RealCompletedProcess(command, rc, stdout, stderr)

    def inspect_data(self, item):
        return {
            "Id": item["id"], "Name": "/" + item["name"], "Image": IMAGE,
            "Owner": item["labels"].get("org.aegml.h024.cli.owner", ""),
            "id": item["id"], "name": "/" + item["name"],
            "owner": item["labels"].get("org.aegml.h024.cli.owner", ""),
            "Config": {"Labels": item["labels"], "User": "1000:1000"},
            "HostConfig": {"Memory": 20 * 1024**3, "MemorySwap": 20 * 1024**3,
                "NanoCpus": 8 * 10**9, "PidsLimit": 256, "NetworkMode": "none",
                "ReadonlyRootfs": True, "Privileged": False, "CapDrop": ["ALL"],
                "CapAdd": None, "SecurityOpt": ["no-new-privileges=true"],
                "Binds": None, "Tmpfs": {"/tmp": "rw,nosuid,nodev,size=64m,mode=1777"}},
            "State": {"Status": "exited" if item.get("started") else "created", "ExitCode": 3},
            "Mounts": [{"Type": "bind", "Source": str(item["work"]),
                        "Destination": "/work", "RW": True}],
        }

    def get(self, target):
        return next((item for item in self.containers.values()
                     if target in (item["name"], item["id"])), None)

    def materialize(self, item):
        self.starts += 1
        item["started"] = True
        work = item["work"]
        artifacts = work / ".aegml_runs" / ("a" * 31 + str(self.starts))
        artifacts.mkdir(parents=True)
        contract = {"prediction_schema": {"output_order": "test"},
                    "metric": {"name": "rmse" if self.starts == 1 else "macro_f1"}}
        (artifacts / "task_contract.json").write_text(json.dumps(contract), encoding="utf-8")
        (artifacts / "row_alignment.json").write_text('{"output_to_test":[0]}', encoding="utf-8")
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts.iterdir()}
        outcome = {"phase": "H02.3", "contract_valid": True,
                   "termination_reason": "implementation_incomplete", "api_verified": False,
                   "tools_verified": False, "research_completed": False, "submission_valid": False,
                   "experiments_completed": 0, "artifact_sha": hashes}
        if scenario == "bad_flags":
            outcome["api_verified"] = True
        if scenario == "root_changed" and self.starts == 2:
            path = root / "solution.py"
            path.write_bytes(path.read_bytes() + b"\n# synthetic concurrent root mutation\n")
        if scenario == "absent_after_run":
            self.containers.pop(item["name"], None)
        return 0 if scenario == "bad_exit" else 3, json.dumps(outcome)

    def __call__(self, command, *args, **kwargs):
        command = list(command)
        # The double never delegates an unrecognised command to the OS.
        if not command or Path(str(command[0])).name != "docker":
            raise RuntimeError("unexpected_non_docker_command_blocked")
        tokens = command[1:]
        if tokens[:1] == ["--host"]:
            tokens = tokens[2:]
        if tokens[:1] == ["container"]:
            tokens = tokens[1:]
        action = tokens[0] if tokens else ""
        self.actions.append({"action": action, "argv": command})
        if action in ("create", "run"):
            name = tokens[tokens.index("--name") + 1]
            mount = tokens[tokens.index("--mount") + 1]
            source = next(part[7:] for part in mount.split(",") if part.startswith("source="))
            labels = {}
            for index, token in enumerate(tokens):
                if token == "--label":
                    key, value = tokens[index + 1].split("=", 1)
                    labels[key] = value
                elif token.startswith("--label="):
                    key, value = token[len("--label="):].split("=", 1)
                    labels[key] = value
            if scenario == "collision":
                self.containers[name] = {"name": name, "id": self.foreign_id,
                                         "labels": {"fixture.foreign-owner": "foreign"}, "work": Path(source)}
                return self.answer(command, 125, stderr="Conflict: container name already in use", **kwargs)
            self.created += 1
            item = {"name": name, "id": format(self.created, "064x"),
                    "labels": labels, "work": Path(source)}
            self.containers[name] = item
            if "--cidfile" in tokens:
                Path(tokens[tokens.index("--cidfile") + 1]).write_text(item["id"] + "\n", encoding="utf-8")
            if action == "run":
                rc, output = self.materialize(item)
                return self.answer(command, rc, output, **kwargs)
            return self.answer(command, stdout=item["id"] + "\n", **kwargs)
        if action == "inspect":
            target = tokens[-1]
            if scenario == "inspect_error" and self.starts:
                return self.answer(command, 1, stderr="Cannot connect to the Docker daemon", **kwargs)
            item = self.get(target)
            if item is None:
                return self.answer(command, 1, stderr="Error: No such container: " + target, **kwargs)
            data = self.inspect_data(item)
            if "--format" in tokens:
                return self.answer(command, stdout=json.dumps(data), **kwargs)
            return self.answer(command, stdout=json.dumps([data]), **kwargs)
        if action in ("ps", "ls"):
            if scenario == "inspect_error" and self.starts:
                return self.answer(command, 1, stderr="Cannot connect to the Docker daemon", **kwargs)
            items = list(self.containers.values())
            for index, token in enumerate(tokens):
                if token != "--filter":
                    continue
                key, value = tokens[index + 1].split("=", 1)
                if key == "name":
                    name = value.lstrip("^").lstrip("/").rstrip("$")
                    items = [item for item in items if item["name"] == name]
                elif key == "id":
                    items = [item for item in items if item["id"] == value]
            return self.answer(command, stdout="".join(item["id"] + "\n" for item in items), **kwargs)
        if action == "start":
            item = self.get(tokens[-1])
            if item is None:
                return self.answer(command, 1, stderr="No such container", **kwargs)
            rc, output = self.materialize(item)
            return self.answer(command, rc, output, **kwargs)
        if action in ("rm", "remove"):
            target = tokens[-1]
            item = self.get(target)
            if scenario == "rm_failure":
                return self.answer(command, 1, stderr="Cannot connect to the Docker daemon", **kwargs)
            if item is None:
                return self.answer(command, 1, stderr="Error: No such container: " + target, **kwargs)
            self.containers.pop(item["name"], None)
            return self.answer(command, stdout=target + "\n", **kwargs)
        raise RuntimeError("unexpected_docker_action_blocked:" + action)


fake = FakeDocker()
# Simulate the real receipt TOCTOU: another writer wins after exists() but
# before exclusive open. This never alters an already-reserved receipt inode.
original_path_open = Path.open
def racing_path_open(path, mode="r", *args, **kwargs):
    if scenario == "receipt_race" and Path(path) == receipt and "x" in mode and fake.race_snapshot is None:
        with original_path_open(path, "wb") as stream:
            stream.write(SENTINEL)
        os.utime(path, ns=(1_600_000_000_000_000_000,) * 2)
        fake.race_snapshot = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                              "mtime_ns": path.stat().st_mtime_ns}
    return original_path_open(path, mode, *args, **kwargs)
Path.open = racing_path_open
spec = importlib.util.spec_from_file_location("h024_fixture_checker", checker)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
exit_code, error_type = 0, None
try:
    spec.loader.exec_module(module)
    module.ROOT = root
    module.os.chown = lambda *args, **kwargs: None
    module.subprocess.run = fake
    sys.argv = [str(checker), "--image", IMAGE, "--receipt", str(receipt)]
    # Do not let the checker's ordinary stdout mix with this driver's JSON.
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        returned = module.main()
    exit_code = returned if type(returned) is int else 0
except SystemExit as exc:
    exit_code = exc.code if type(exc.code) is int else 1
    error_type = "SystemExit"
except BaseException as exc:
    exit_code, error_type = 1, type(exc).__name__
payload = None
if receipt.is_file():
    try:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        pass
print(json.dumps({"exit_code": exit_code, "error_type": error_type, "optimize": sys.flags.optimize,
    "receipt": payload, "receipt_exists": receipt.exists(), "actions": fake.actions,
    "remaining": [{"name": item["name"], "id": item["id"], "labels": item["labels"]}
                  for item in fake.containers.values()],
    "race_snapshot": fake.race_snapshot,
    "receipt_snapshot": {"sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
                         "mtime_ns": receipt.stat().st_mtime_ns} if receipt.is_file() else None},
    ensure_ascii=False, allow_nan=False))
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def has_pass(outcome):
    payload = outcome.get("receipt")
    return isinstance(payload, dict) and str(payload.get("status", "")).startswith("PASS_")


class CliCheckerChecks(unittest.TestCase):
    @contextmanager
    def case(self, name, finding, *, historical=False):
        record = {"test": self.id(), "case": name, "finding": finding,
                  "historical_before": historical, "status": "RUNNING"}
        CASES.append(record)
        try:
            yield record
        except BaseException:
            record["status"] = "FAIL"
            raise
        else:
            record["status"] = "PASS_EXPECTED_OLD_BEHAVIOR" if historical else "PASS"

    def invoke(self, scenario="normal", *, optimize=False, existing=False, before=False):
        source = BEFORE_CHECKER if before else CHECKER
        self.assertIsNotNone(source)
        with tempfile.TemporaryDirectory(prefix="aegml-h024-mock-") as temporary:
            base = Path(temporary)
            root = base / "synthetic root"
            scripts = root / "scripts"
            scripts.mkdir(parents=True)
            shutil.copyfile(source, scripts / CHECKER.name)
            executed_checker_sha = sha(scripts / CHECKER.name)
            for filename in SOURCES:
                content = "# Synthetic fixture only; never executed.\n" if filename.endswith(".py") else "fixture-package==0\n"
                (root / filename).write_text(content, encoding="utf-8")
            for folder in ("Регрессия", "Многоклассовая классификация"):
                task = root / "drive-download-20261019T181414Z-1-001" / folder
                task.mkdir(parents=True)
                for filename in ("task.md", "train.csv", "test.csv", "data_dictionary.csv", "sample_submission.csv"):
                    (task / filename).write_text("# synthetic fixture\n" if filename == "task.md" else "id,y\n001,0\n", encoding="utf-8")
            driver = base / "driver.py"
            driver.write_text(DRIVER, encoding="utf-8")
            receipt = base / "proof" / "checker.json"
            receipt.parent.mkdir()
            sentinel_snapshot = None
            if existing:
                receipt.write_bytes(SENTINEL)
                os.utime(receipt, ns=(1_600_000_000_000_000_000,) * 2)
                sentinel_snapshot = {"sha256": sha(receipt), "mtime_ns": receipt.stat().st_mtime_ns}
            before_hash = sha(root / "solution.py")
            command = [sys.executable, "-B"] + (["-O"] if optimize else []) + [str(driver), str(root), scenario, str(receipt)]
            env = {"PATH": str(Path(sys.executable).parent), "PYTHONDONTWRITEBYTECODE": "1",
                   "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
            child = subprocess.run(command, capture_output=True, text=True, timeout=15, env=env, cwd=base)
            self.assertEqual(child.returncode, 0, "fixture driver failed; no Docker was delegated")
            self.assertLess(len(child.stdout), 262144)
            self.assertEqual(child.stderr, "", "fixture driver emitted unexpected stderr")
            outcome = json.loads(child.stdout)
            self.assertEqual(outcome["optimize"], int(optimize), "actual child optimization mode differs")
            outcome["root_changed"] = sha(root / "solution.py") != before_hash
            outcome["sentinel_snapshot"] = sentinel_snapshot
            INVOCATIONS.append({"scenario": scenario, "historical_before": before, "optimize": optimize,
                "observed_optimize": outcome["optimize"],
                "checker_sha256": executed_checker_sha, "driver_python_exit": child.returncode,
                "checker_exit": outcome["exit_code"], "checker_status": (outcome.get("receipt") or {}).get("status"),
                "mock_actions": outcome["actions"], "real_docker_actions": 0,
                "root_changed_inside_synthetic_fixture": outcome["root_changed"]})
            return outcome

    def assert_failed(self, outcome):
        self.assertNotEqual(outcome["exit_code"], 0)
        self.assertFalse(has_pass(outcome), "invalid fixture obtained overall PASS")

    def test_unchanged_control_passes(self):
        with self.case("unchanged_two_task_snapshot_control", "H024-CLI-SOURCE-001"):
            outcome = self.invoke()
            self.assertEqual(outcome["exit_code"], 0)
            self.assertTrue(has_pass(outcome))
            self.assertFalse(outcome["root_changed"])
            self.assertEqual(len(outcome["receipt"]["cases"]), 2)
            self.assertEqual(outcome["receipt"]["unresolved_resources"], [])
            self.assertTrue(all(item["verified"] for item in outcome["receipt"]["cleanup"]))
            removals = [item["argv"][-1] for item in outcome["actions"] if item["action"] in ("rm", "remove")]
            self.assertEqual(len(removals), 2)
            self.assertTrue(all(len(value) == 64 and all(char in "0123456789abcdef" for char in value)
                                for value in removals), "owned cleanup must address full IDs, never names")

    def test_foreign_name_collision_never_removed(self):
        with self.case("foreign_collision_no_delete", "H024-CLI-OWN-001"):
            outcome = self.invoke("collision")
            self.assert_failed(outcome)
            self.assertFalse(any(item["action"] in ("rm", "remove") for item in outcome["actions"]))
            self.assertEqual([item["id"] for item in outcome["remaining"]], ["f" * 64])

    def test_cleanup_inspect_daemon_error_is_not_absence(self):
        with self.case("cleanup_inspect_error_is_unknown_and_fails", "H024-CLI-OWN-001"):
            outcome = self.invoke("inspect_error")
            self.assert_failed(outcome)
            self.assertTrue(outcome["remaining"])
            self.assertIsNotNone(outcome["receipt"], "failure needs a new diagnostic receipt")
            self.assertTrue(outcome["receipt"]["unresolved_resources"])
            self.assertTrue(any(not item["verified"] for item in outcome["receipt"]["cleanup"]))
            self.assertFalse(any(item["action"] in ("rm", "remove") for item in outcome["actions"]))

    def test_confirmed_absence_after_run_is_allowed(self):
        with self.case("confirmed_auto_removed_container_not_false_failure", "H024-CLI-OWN-001"):
            outcome = self.invoke("absent_after_run")
            self.assertEqual(outcome["exit_code"], 0)
            self.assertTrue(has_pass(outcome))
            self.assertEqual(outcome["remaining"], [])
            self.assertTrue(all(item["verified"] for item in outcome["receipt"]["cleanup"]))

    def test_rm_failure_retains_unresolved_cleanup(self):
        with self.case("owned_rm_failure_recorded_and_fails", "H024-CLI-OWN-001"):
            outcome = self.invoke("rm_failure")
            self.assert_failed(outcome)
            self.assertTrue(outcome["remaining"])
            self.assertTrue(any(item["action"] in ("rm", "remove") for item in outcome["actions"]))
            self.assertTrue(outcome["receipt"]["unresolved_resources"])
            self.assertTrue(any(not item["verified"] for item in outcome["receipt"]["cleanup"]))

    def test_invalid_exit_normal_and_optimized(self):
        for optimized in (False, True):
            with self.subTest(optimize=optimized), self.case("invalid_exit_rejected_optimize_" + str(optimized), "H024-CLI-ASSERT-001"):
                outcome = self.invoke("bad_exit", optimize=optimized)
                self.assert_failed(outcome)

    def test_invalid_flags_normal_and_optimized(self):
        for optimized in (False, True):
            with self.subTest(optimize=optimized), self.case("invalid_flags_rejected_optimize_" + str(optimized), "H024-CLI-ASSERT-001"):
                outcome = self.invoke("bad_flags", optimize=optimized)
                self.assert_failed(outcome)

    def test_existing_receipt_preserved_before_docker(self):
        with self.case("existing_receipt_bytes_mtime_and_zero_actions", "H024-CLI-RECEIPT-001"):
            outcome = self.invoke(existing=True)
            self.assert_failed(outcome)
            self.assertEqual(outcome["actions"], [])
            self.assertEqual(outcome["receipt_snapshot"], outcome["sentinel_snapshot"])

    def test_receipt_race_never_overwrites_new_owner(self):
        with self.case("raced_receipt_creation_preserves_bytes_and_mtime", "H024-CLI-RECEIPT-001"):
            outcome = self.invoke("receipt_race")
            self.assert_failed(outcome)
            self.assertIsNotNone(outcome["race_snapshot"])
            self.assertEqual(outcome["receipt_snapshot"], outcome["race_snapshot"])
            self.assertEqual(outcome["actions"], [], "lost receipt reservation must fail before Docker")

    def test_root_mutated_after_second_staging_is_not_pass(self):
        with self.case("root_drift_after_last_staging_nonpass", "H024-CLI-SOURCE-001"):
            outcome = self.invoke("root_changed")
            self.assertTrue(outcome["root_changed"], "mutation fixture did not execute")
            self.assert_failed(outcome)
            payload = outcome["receipt"]
            self.assertNotEqual(payload["source_sha256"], payload["source_sha256_after"])
            self.assertTrue(payload["root_source_changed"])

    def test_historical_before_counterexamples(self):
        if BEFORE_CHECKER is None:
            self.skipTest("historical checker not supplied; before evidence NOT_RUN")
        self.assertEqual(sha(BEFORE_CHECKER), BEFORE_SHA)
        for scenario in ("collision", "bad_exit", "existing_receipt", "root_changed", "rm_failure"):
            optimized = scenario == "bad_exit"
            with self.subTest(scenario=scenario), self.case("historical_counterexample_" + scenario,
                    {"collision": "H024-CLI-OWN-001", "bad_exit": "H024-CLI-ASSERT-001",
                     "existing_receipt": "H024-CLI-RECEIPT-001", "root_changed": "H024-CLI-SOURCE-001",
                     "rm_failure": "H024-CLI-OWN-001"}[scenario], historical=True):
                outcome = self.invoke(scenario, optimize=optimized, before=True, existing=scenario == "existing_receipt")
                if scenario == "collision":
                    self.assertTrue(any(item["action"] in ("rm", "remove") for item in outcome["actions"]))
                    self.assertEqual(outcome["remaining"], [])
                elif scenario == "existing_receipt":
                    self.assertNotEqual(outcome["receipt_snapshot"], outcome["sentinel_snapshot"])
                    self.assertTrue(has_pass(outcome))
                else:
                    self.assertTrue(has_pass(outcome), "historical counterexample no longer reproduced")
                    if scenario == "root_changed":
                        self.assertTrue(outcome["root_changed"])


def main():
    global BEFORE_CHECKER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--before-checker", type=Path)
    args = parser.parse_args()
    if args.receipt.exists():
        parser.error("receipt already exists; select a fresh receipt path")
    if args.before_checker is not None:
        BEFORE_CHECKER = args.before_checker.resolve()
        if not BEFORE_CHECKER.is_file() or sha(BEFORE_CHECKER) != BEFORE_SHA:
            parser.error("before-checker must have the declared historical SHA256")
    source_paths = (CHECKER, Path(__file__).resolve())
    initial = {str(path.relative_to(ROOT)): sha(path) for path in source_paths}
    receipt = {"phase": "H02.4", "status": "NOT_RUN", "python": platform.python_version(),
        "scope": "mock-only trusted Docker CLI-checker regression; synthetic temporary ROOTs only",
        "source_sha256": initial, "before_checker_sha256": sha(BEFORE_CHECKER) if BEFORE_CHECKER else None,
        "before_coverage": "REQUESTED" if BEFORE_CHECKER else "NOT_RUN",
        "real_docker_commands": 0, "live_api_calls": 0, "fit_calls": 0,
        "package_installation_executed": False, "real_project_mutation": False,
        "official_platform_image_verified": False, "full_H05_accepted": False,
        "child_environment_controlled": True,
        "notes": ["subprocess.run is replaced inside each isolated fixture Python process; it never delegates Docker.",
                  "Python -O is exercised in a separate process, not simulated by changing __debug__.",
                  "Mock filesystem artifacts are hand-authored and do not execute production solution.py.",
                  "Historic expected-defect observations are separate from fixed-checker acceptance."]}
    if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
        receipt.update(status="BLOCKED_WRONG_CHECK_ENVIRONMENT", test_methods_run=0,
                       behavior_cases_checked=0, checker_invocations=0)
        code = 2
    else:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CliCheckerChecks))
        final = {str(path.relative_to(ROOT)): sha(path) for path in source_paths}
        stable = initial == final
        passed = result.wasSuccessful() and stable
        receipt.update(status="PASS_H024_CLI_MOCK_REGRESSIONS_ONLY" if passed else "FAIL_H024_CLI_MOCK_REGRESSIONS",
            test_methods_run=result.testsRun, behavior_cases_checked=len(CASES),
            behavior_cases_passed=sum(case["status"].startswith("PASS") for case in CASES),
            checker_invocations=len(INVOCATIONS), cases=CASES, invocations=INVOCATIONS,
            source_sha256_after=final, source_unchanged_during_check=stable,
            before_coverage="OBSERVED" if BEFORE_CHECKER else "NOT_RUN",
            unittest_failures=[{"test": test.id(), "detail": detail} for test, detail in result.failures],
            unittest_errors=[{"test": test.id(), "detail": detail} for test, detail in result.errors],
            unittest_skips=[{"test": test.id(), "reason": reason} for test, reason in result.skipped])
        code = 0 if passed else 1
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": receipt["status"], "receipt": str(args.receipt),
        "test_methods_run": receipt["test_methods_run"], "behavior_cases_checked": receipt["behavior_cases_checked"],
        "checker_invocations": receipt["checker_invocations"]}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
