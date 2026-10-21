"""H04 tiny trusted orchestration checks: synthetic data only, no public fit/API.

Ten-tree direct tests and one 300-tree literal CLI fixture are distinct scopes.
Before probes are preserved separately in runs/h04/h04-20261021/before-peer-fixes.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stdout
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from time import monotonic_ns
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PRODUCTION = ("solution.py", "aegml_artifacts.py", "aegml_baseline.py", "aegml_contracts.py",
              "aegml_estimators.py", "aegml_input.py", "aegml_metrics.py", "aegml_preprocessing.py",
              "aegml_profile.py", "aegml_schemas.py", "aegml_submission.py", "aegml_training_data.py",
              "aegml_validation.py", "requirements.txt")
SOURCES = (*PRODUCTION, "scripts/check_h04_baseline.py")
INPUT_NAMES = ("task.md", "train.csv", "test.csv", "data_dictionary.csv", "sample_submission.csv")
EXPECTED_REQUIREMENTS = "9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6"
CASES, FITS, CLI, NETWORK_EVENTS = [], [], [], []
A = B = C = E = I = S = T = SOLUTION = None


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshots(root, names=INPUT_NAMES):
    return {name: {"sha256": sha(root / name), "mtime_ns": (root / name).stat().st_mtime_ns}
            for name in names}


def write_csv(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def env_controlled():
    return {"PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin", "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1", "AEGML_TIME_LIMIT_SECONDS": "120",
            "AEGML_FINALIZE_RESERVE_SECONDS": "10", "AEGML_THREADS": "2"}


class Fixture:
    def __init__(self, root, kind="regression", *, temporal=True, order="sample", renamed=False,
                 poison_outer=False):
        self.root, self.kind = root, kind
        self.target = "renamed_goal" if renamed else "response"
        self.period = "cycle_step" if renamed else "period"
        self.key = "row_key"
        self.order = order
        self.labels = ("001", "NA", "Ω")
        self.header = [self.target, self.period, self.key, "category", "measurement"]
        self.test_header = ["category", self.key, "measurement", self.period]
        self.train = []
        for index in range(60):
            period = index // 10 + 1
            label = self.labels[index % 3]
            target = str(3 * (index % 10) + period * 2) if kind == "regression" else label
            if poison_outer and period == 6:
                target = "1000000000000"
            self.train.append([target, str(period), "train-" + str(index),
                               "category-" + str(index % 3), str(index % 10)])
        self.test = [["category-0", "001", "2", "7"], ["category-1", "NA", "7", "7"],
                     ["unknown-category", "third", "5", "7"]]
        self.sample_to_test = (2, 0, 1)
        root.mkdir()
        task_lines = ["Task type: " + kind, "Target: " + self.target, "ID: " + self.key,
                      "Metric: " + ("RMSE" if kind == "regression" else "Macro F1"),
                      "Output order: " + order]
        if temporal and kind == "regression":
            task_lines.append("Time column: " + self.period)
        task_lines += ["## Data", "- `train.csv`", "- `test.csv`", "- `data_dictionary.csv`",
                       "- `sample_submission.csv`"]
        (root / "task.md").write_text("\n".join(task_lines) + "\n", encoding="utf-8")
        write_csv(root / "train.csv", self.header, self.train)
        write_csv(root / "test.csv", self.test_header, self.test)
        write_csv(root / "sample_submission.csv", [self.target, self.key],
                  [["0", self.test[index][1]] for index in self.sample_to_test])
        write_csv(root / "data_dictionary.csv", ["feature", "role", "dtype"],
                  [[self.target, "target", "category" if kind == "classification" else "numeric"],
                   [self.period, "feature", "numeric"], [self.key, "id", "string"],
                   ["category", "feature", "category"], ["measurement", "feature", "numeric"]])
        self.before = snapshots(root)

    @property
    def task(self):
        return self.root / "task.md"

    def config(self):
        config = C.parse_config([str(self.task), "--time-limit-seconds", "120",
                                 "--finalize-reserve-seconds", "10", "--threads", "2"],
                                {}, started_ns=monotonic_ns(), clock=monotonic_ns)
        C.configure_threads(config.threads)
        return config

    def binding(self):
        config = self.config()
        contract = C.build_task_contract(self.task, budget=config.budget)
        bundle = I.discover_inputs(self.task, config.budget)
        plan = B.build_baseline_split(bundle, contract, budget=config.budget)
        return config, contract, bundle, plan


class BaselineChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aegml-h04-baseline-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.fixtures = []

    def fixture(self, name, kind="regression", **kwargs):
        fixture = Fixture(self.base / name, kind, **kwargs)
        self.fixtures.append(fixture)
        return fixture

    def tearDown(self):
        for fixture in self.fixtures:
            self.assertTrue(snapshots(fixture.root) == fixture.before, "synthetic source bytes/mtime changed")

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

    def run_real(self, fixture):
        config, progress = fixture.config(), {}
        original = E.fit_estimator
        def observed(*args, **kwargs):
            item = {"scope": "synthetic_only", "task_type": kwargs["task_type"],
                    "rows": len(args[1].values), "iterations": kwargs["config"].iterations,
                    "threads": kwargs["config"].threads, "status": "STARTED"}
            FITS.append(item)
            fitted = original(*args, **kwargs)
            item.update(status="PASS", model_sha256=fitted.audit()["model_sha256"])
            return fitted
        with patch.object(E, "fit_estimator", side_effect=observed):
            result = B.run_baseline(config, estimator_config=E.EstimatorConfig(iterations=10, threads=2),
                                    progress=progress)
        return result, progress

    def assert_output(self, fixture, result):
        report = result["report"]
        config = fixture.config()
        contract = C.build_task_contract(fixture.task, budget=config.budget)
        bundle = I.discover_inputs(fixture.task, config.budget)
        schema = S.build_submission_schema(bundle, contract, budget=config.budget,
                  allowed_labels=fixture.labels if fixture.kind == "classification" else None)
        validated = S.validate_submission(fixture.root / "submission.csv", schema, budget=config.budget,
                                          expected_sha256=report["submission"]["sha256"])
        self.assertEqual(validated["row_count"], 3)
        with (fixture.root / "submission.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows[0], [fixture.target, fixture.key])
        expected = fixture.sample_to_test if fixture.order == "sample" else (0, 1, 2)
        self.assertTrue([row[1] for row in rows[1:]] == [fixture.test[index][1] for index in expected],
                        "output ID order differs from confirmed contract")
        return rows

    def fake(self, fixture, mode):
        def factory(prepared_fit, targets, **kwargs):
            constant = B._constant(targets)[1]
            class Model:
                calls = 0
                def predict(model, prepared, *, budget):
                    budget.require()
                    model.calls += 1
                    if mode == "prediction_failure":
                        raise E.EstimatorError("synthetic_prediction_failed")
                    if model.calls == 1:
                        if mode == "better":
                            values = tuple(float(fixture.train[index][0]) for index in prepared.row_indices)
                        else:
                            values = (constant + (1000 if mode == "worse" else 0),) * len(prepared.row_indices)
                    else:
                        values = (11.0, 22.0, 33.0)
                    return T.PredictionBatch(values, prepared.row_indices)
                def feature_importance(model, *, budget):
                    budget.require()
                    return {"method": "synthetic_stub", "values": []}
                def audit(model):
                    return {"estimator_fitted": True, "synthetic_stub": True, "tree_count": 0}
            return Model()
        return factory

    def solution_call(self, fixture, *, fit_failure=False, prediction_failure=False):
        stdout = io.StringIO()
        config = fixture.config()
        before_writes = []
        original = S.write_submission
        def observed(*args, **kwargs):
            result = original(*args, **kwargs)
            path = fixture.root / "submission.csv"
            before_writes.append((sha(path), path.stat().st_mtime_ns))
            return result
        failure = E.EstimatorError("synthetic_fit_failed") if fit_failure else self.fake(fixture, "prediction_failure")
        option = {"side_effect": failure}
        with patch.dict(os.environ, env_controlled(), clear=True), patch.object(S, "write_submission", side_effect=observed), \
                patch.object(E, "fit_estimator", **option), patch.object(SOLUTION, "_STARTED_NS", monotonic_ns()), \
                redirect_stdout(stdout):
            code = SOLUTION.main([str(fixture.task), "--time-limit-seconds", "120",
                                  "--finalize-reserve-seconds", "10", "--threads", "2"])
        outcome = json.loads(stdout.getvalue())
        self.assertEqual(len(before_writes), 1)
        path = fixture.root / "submission.csv"
        self.assertEqual((sha(path), path.stat().st_mtime_ns), before_writes[0])
        return code, outcome

    def test_real_regression_full_chain_temporal_and_provenance(self):
        with self.case("real_tiny10_regression_inner_metrics_and_published_csv"):
            fixture = self.fixture("regression")
            result, progress = self.run_real(fixture)
            report = result["report"]
            self.assert_output(fixture, result)
            self.assertEqual(report["split"]["strategy"], "temporal")
            self.assertEqual(report["feature_model"]["audit"]["tree_count"], 10)
            self.assertEqual(report["feature_model"]["audit"]["requested_parameters"]["thread_count"], 2)
            self.assertFalse(report["phase_access"]["frozen_refit_performed"])
            self.assertFalse(report["phase_access"]["outer_targets_retained_or_scored"])
            self.assertEqual(report["live_api_calls"], 0)
            self.assertTrue(progress["contract_valid"] and progress["submission_valid"] and progress["feature_model_fitted"])
            self.assertEqual(progress["submission_sha256"], report["submission"]["sha256"])
            self.assertTrue(math.isfinite(report["improvement_over_constant"]))

    def test_real_classification_restores_literal_labels_and_output_schema(self):
        with self.case("real_tiny10_macroF1_restores_001_NA_unicode_labels"):
            fixture = self.fixture("classification", "classification")
            result, progress = self.run_real(fixture)
            report = result["report"]
            rows = self.assert_output(fixture, result)
            self.assertEqual(set(report["feature_model"]["audit"]["learned_class_order"]), set(fixture.labels))
            self.assertEqual(report["metric_contract"]["parameters"], {"average": "macro", "labels": None})
            self.assertTrue(all(row[0] in fixture.labels for row in rows[1:]))
            self.assertEqual(report["split"]["strategy"], "stratified")
            self.assertTrue(progress["submission_valid"])
            self.assertTrue(0 <= report["feature_model"]["evaluation"]["metric_report"]["value"] <= 1)

    def test_generic_temporal_renaming_iid_and_unresolved_time_refusal(self):
        with self.case("renamed_six_period_regression_exact_chronological_partition"):
            fixture = self.fixture("renamed", renamed=True)
            _, _, _, plan = fixture.binding()
            self.assertEqual(plan.fit_indices, tuple(range(40)))
            self.assertEqual(plan.inner_indices, tuple(range(40, 50)))
            self.assertEqual(plan.outer_indices, tuple(range(50, 60)))
        with self.case("no_time_declaration_has_explicit_named_iid_policy"):
            fixture = self.fixture("iid", temporal=False)
            _, _, _, plan = fixture.binding()
            self.assertEqual(plan.policy_id, "iid_nested_regression_v1")
            self.assertEqual((len(plan.fit_indices), len(plan.inner_indices), len(plan.outer_indices)), (38, 10, 12))
        with self.case("declared_unresolved_temporal_split_does_not_fall_back_iid"):
            fixture = self.fixture("unresolved", temporal=False)
            with fixture.task.open("a", encoding="utf-8") as stream:
                stream.write("Use a temporal split.\n")
            fixture.before = snapshots(fixture.root)
            with self.assertRaises(B.BaselineError) as caught:
                fixture.binding()
            self.assertEqual(caught.exception.code, "temporal_column_not_resolved")

    def test_real_outer_target_poison_does_not_change_search_or_predictions(self):
        with self.case("real_tiny10_outer_y_poison_invariant_fit_inner_test_predictions"):
            original = self.fixture("clean")
            poison = self.fixture("poison", poison_outer=True)
            first, _ = self.run_real(original)
            second, _ = self.run_real(poison)
            a, b = first["report"], second["report"]
            self.assertNotEqual(a["source_sha256"]["train"], b["source_sha256"]["train"])
            self.assertEqual(a["preprocessing"]["fit_values_sha256"], b["preprocessing"]["fit_values_sha256"])
            self.assertEqual(a["preprocessing"]["trained_statistics_sha256"], b["preprocessing"]["trained_statistics_sha256"])
            for name in ("constant-inner.csv", "model-inner.csv", "model-test.csv"):
                self.assertTrue((first["artifact_root"] / name).read_bytes() == (second["artifact_root"] / name).read_bytes(),
                                "closed outer target changed search predictions")
            self.assertEqual(a["feature_model"]["evaluation"]["metric_report"]["value"],
                             b["feature_model"]["evaluation"]["metric_report"]["value"])

    def test_worse_and_tied_feature_candidates_preserve_constant_bytes_and_mtime(self):
        for mode in ("worse", "tie"):
            with self.subTest(mode=mode), self.case("mock_" + mode + "_keeps_early_constant_sha_and_mtime"):
                fixture = self.fixture(mode)
                writes = []
                original = S.write_submission
                def observed(*args, **kwargs):
                    published = original(*args, **kwargs)
                    path = fixture.root / "submission.csv"
                    writes.append((sha(path), path.stat().st_mtime_ns))
                    return published
                with patch.object(E, "fit_estimator", side_effect=self.fake(fixture, mode)), \
                        patch.object(S, "write_submission", side_effect=observed):
                    result = B.run_baseline(fixture.config(), estimator_config=E.EstimatorConfig(iterations=10, threads=2))
                self.assertEqual(result["report"]["selected"], "fit_mean")
                self.assertEqual(len(writes), 1)
                path = fixture.root / "submission.csv"
                self.assertEqual((sha(path), path.stat().st_mtime_ns), writes[0])
                self.assertLessEqual(result["report"]["improvement_over_constant"], 1e-12)

    def test_better_mock_candidate_applies_mapping_exactly_once(self):
        for order in ("sample", "test"):
            with self.subTest(order=order), self.case("mock_better_distinct_predictions_mapping_once_" + order):
                fixture = self.fixture("mapping-" + order, order=order)
                with patch.object(E, "fit_estimator", side_effect=self.fake(fixture, "better")):
                    result = B.run_baseline(fixture.config(), estimator_config=E.EstimatorConfig(iterations=10, threads=2))
                self.assertEqual(result["report"]["selected"], "feature_model")
                rows = self.assert_output(fixture, result)
                self.assertEqual([float(row[0]) for row in rows[1:]], [33, 11, 22] if order == "sample" else [11, 22, 33])

    def test_failure_progress_is_factual_and_early_output_remains_valid(self):
        for phase in ("fit", "prediction"):
            with self.subTest(phase=phase), self.case("H04_CLI_PROGRESS_failure_after_early_" + phase):
                fixture = self.fixture("failure-" + phase)
                code, outcome = self.solution_call(fixture, fit_failure=phase == "fit", prediction_failure=phase == "prediction")
                self.assertEqual(code, 1)
                self.assertEqual(outcome["status"], "failed")
                self.assertTrue(outcome["contract_valid"] and outcome["submission_valid"])
                self.assertEqual(outcome["feature_model_fitted"], phase == "prediction")
                self.assertEqual(outcome["submission_sha256"], sha(fixture.root / "submission.csv"))
                self.assertEqual(outcome["submission_rows"], 3)
                self.assertEqual(outcome["live_api_calls"], 0)
                self.assertFalse(outcome["research_completed"])

    def test_parse_failure_and_expiry_keep_original_shared_budget(self):
        fixture = self.fixture("timer")
        for failure in ("threads", "path"):
            with self.subTest(failure=failure), self.case("H04_CLI_TIMER_original_budget_after_parse_" + failure):
                output = io.StringIO()
                task = str(fixture.task if failure == "threads" else fixture.root / "missing-task.md")
                with patch.object(SOLUTION, "_STARTED_NS", 10_000_000_000), \
                        patch.object(SOLUTION, "_monotonic_ns", lambda: 12_000_000_000), \
                        patch.dict(os.environ, env_controlled(), clear=True), redirect_stdout(output):
                    code = SOLUTION.main([task, "--time-limit-seconds", "120", "--finalize-reserve-seconds", "10",
                                          "--threads", "0" if failure == "threads" else "2"])
                result = json.loads(output.getvalue())
                self.assertEqual(code, 2)
                self.assertEqual(result["timer"]["total_seconds"], 120)
                self.assertEqual(result["timer"]["reserve_seconds"], 10)
                self.assertEqual(result["timer"]["elapsed_seconds"], 2)
        with self.case("H04_CLI_TIMER_budget_exception_without_returned_config_uses_exc_budget"):
            shared = C.RunBudget(10_000_000_000, 120, 10, clock=lambda: 121_000_000_000)
            output = io.StringIO()
            with patch.object(SOLUTION, "parse_config", side_effect=C.BudgetExpired("work_budget_exhausted", shared)), \
                    patch.object(SOLUTION, "_STARTED_NS", 10_000_000_000), \
                    patch.object(SOLUTION, "_monotonic_ns", lambda: 121_000_000_000), redirect_stdout(output):
                code = SOLUTION.main([str(fixture.task)])
            result = json.loads(output.getvalue())
            self.assertEqual(code, 124)
            self.assertEqual(result["timer"]["total_seconds"], 120)
            self.assertEqual(result["timer"]["elapsed_seconds"], 111)
            self.assertEqual(result["timer"]["remaining_seconds"], 9)

    def test_split_metadata_and_membership_data_files_are_bounded(self):
        with self.case("H04_SPLIT_ARTIFACT_metadata_only_plus_three_membership_csvs"):
            fixture = self.fixture("split-metadata")
            with patch.object(E, "fit_estimator", side_effect=self.fake(fixture, "tie")):
                result = B.run_baseline(fixture.config(), estimator_config=E.EstimatorConfig(iterations=10, threads=2))
            root = result["artifact_root"]
            payload = json.loads((root / "split.json").read_text())
            self.assertFalse(any(key in payload for key in ("fit_indices", "inner_indices", "outer_indices")))
            self.assertLess((root / "split.json").stat().st_size, 1 << 20)
            all_indices = []
            for phase in ("fit", "inner", "outer"):
                path = root / (phase + "-membership.csv")
                with path.open(encoding="utf-8", newline="") as stream:
                    rows = list(csv.DictReader(stream))
                self.assertTrue(all(json.loads(row["prediction_json"]) == phase for row in rows))
                all_indices.extend(int(row["row_index"]) for row in rows)
            self.assertEqual(sorted(all_indices), list(range(60)))
            self.assertEqual(len(all_indices), len(set(all_indices)))
        with self.case("H04_SPLIT_ARTIFACT_200k_membership_stream_fits_without_large_json"):
            fixture = self.fixture("large-membership")
            shared = C.RunBudget(monotonic_ns(), 120, 10)
            store = A.create_run_artifacts(fixture.task, run_id="e" * 32, budget=shared)
            record = store.write_predictions("fit-membership.csv", ("fit" for _ in range(200000)), range(200000))
            self.assertEqual(record["row_count"], 200000)
            self.assertGreater(record["bytes"], 1 << 20)
            self.assertLess(record["bytes"], 256 << 20)
            self.assertEqual(record["sha256"], sha(store.rootpath / "fit-membership.csv"))

    def test_source_mismatch_refuses_before_new_target_retention(self):
        with self.case("source_bytes_changed_after_contract_are_rejected_by_target_loader"):
            fixture = self.fixture("source-change")
            config, contract, bundle, plan = fixture.binding()
            bound = C.attach_split_plan(contract, plan, budget=config.budget)
            path = fixture.root / "train.csv"
            original = path.read_bytes()
            path.write_bytes(original.replace(b"train-0", b"train-X", 1))
            fixture.before = snapshots(fixture.root)
            with self.assertRaises((T.TrainingDataError, I.InputError)) as caught:
                T.load_fit_targets(bundle, bound, plan, budget=config.budget)
            self.assertEqual(caught.exception.code, "source_changed")

    def test_progress_cannot_be_reused_from_another_run(self):
        with self.case("nonempty_progress_is_not_accepted_as_prior_success"):
            fixture = self.fixture("stale-progress")
            with self.assertRaises(B.BaselineError):
                B.run_baseline(fixture.config(), progress={"submission_valid": True})
            self.assertFalse((fixture.root / "submission.csv").exists())

    def test_external_temporal_table_unknown_column_never_becomes_IID(self):
        for mixed in (False, True):
            with self.case("external_unresolved_temporal_table_" + str(mixed)):
                fixture = self.fixture("missing-period-" + str(mixed), temporal=False)
                table = "\n| field | role | dtype |\n| missing_period | observation period | numeric |\n"
                if mixed:
                    table += "| period | observation period | numeric |\n"
                fixture.task.write_text(fixture.task.read_text() + table)
                fixture.before = snapshots(fixture.root)
                with self.assertRaises(B.BaselineError) as caught:
                    fixture.binding()
                self.assertEqual(caught.exception.code, "unsupported_temporal_declaration")
        with self.case("external_valid_temporal_table_still_temporal"):
            fixture = self.fixture("valid-table", temporal=False)
            fixture.task.write_text(fixture.task.read_text() + "\n| field | role | dtype |\n| period | observation period | numeric |\n")
            fixture.before = snapshots(fixture.root)
            self.assertEqual(fixture.binding()[3].strategy, "temporal")
        with self.case("external_absent_temporal_declaration_still_explicit_IID"):
            fixture = self.fixture("no-table", temporal=False)
            self.assertEqual(fixture.binding()[3].policy_id, "iid_nested_regression_v1")

    def test_external_last_published_SHA_survives_postcommit_errors(self):
        for mode in ("work_expired", "validation_failure", "precommit_failure"):
            with self.subTest(mode=mode), self.case("external_current_published_sha_" + mode):
                fixture = self.fixture("commit-" + mode)
                clock, writes, schema = [0], [], [None]
                original_write, original_validate = S.write_submission, S.validate_submission
                def observed(*args, **kwargs):
                    if mode == "precommit_failure" and len(writes) == 1:
                        raise S.SubmissionError("synthetic_precommit_failure")
                    value = original_write(*args, **kwargs)
                    writes.append(value["sha256"])
                    schema[0] = args[1]
                    if mode == "work_expired" and len(writes) == 2:
                        clock[0] = 91_000_000_000
                    return value
                def validate(path, *args, **kwargs):
                    if mode == "validation_failure" and len(writes) == 2 and Path(path).name == "submission.csv":
                        raise S.SubmissionError("synthetic_postcommit_validation_failure")
                    return original_validate(path, *args, **kwargs)
                stdout = io.StringIO()
                with patch.dict(os.environ, env_controlled(), clear=True), \
                        patch.object(E, "fit_estimator", side_effect=self.fake(fixture, "better")), \
                        patch.object(S, "write_submission", side_effect=observed), \
                        patch.object(S, "validate_submission", side_effect=validate), \
                        patch.object(SOLUTION, "_STARTED_NS", 0), \
                        patch.object(SOLUTION, "_monotonic_ns", lambda: clock[0]), redirect_stdout(stdout):
                    code = SOLUTION.main([str(fixture.task), "--time-limit-seconds", "100",
                                          "--finalize-reserve-seconds", "10", "--threads", "2"])
                outcome = json.loads(stdout.getvalue())
                actual = sha(fixture.root / "submission.csv")
                self.assertNotEqual(code, 0)
                self.assertTrue(outcome["submission_valid"] and outcome["feature_model_fitted"])
                self.assertEqual(outcome["submission_sha256"], actual)
                self.assertEqual(actual, writes[-1])
                if mode == "precommit_failure":
                    self.assertEqual(len(writes), 1)
                else:
                    self.assertEqual(len(writes), 2)
                    self.assertNotEqual(writes[0], writes[1])
                checked = original_validate(fixture.root / "submission.csv", schema[0],
                                            budget=C.RunBudget(0, 100, 10, clock=lambda: clock[0]), finalizing=True)
                self.assertEqual(checked["sha256"], actual)

    def test_literal_platform_cli_fresh_flat_root_with_one_tiny300_model(self):
        with self.case("literal_python3_solution_task_cold_flatcopy_300trees_synthetic_classification"):
            fixture = self.fixture("literal-cli", "classification")
            for name in PRODUCTION:
                shutil.copyfile(ROOT / name, fixture.root / name)
            before = snapshots(fixture.root, (*INPUT_NAMES, *PRODUCTION))
            environment = env_controlled()
            run = subprocess.run(["python3", "solution.py", "task.md"], cwd=fixture.root, env=environment,
                                 capture_output=True, text=True, timeout=120)
            try:
                outcome = json.loads(run.stdout)
            except (ValueError, TypeError):
                self.fail("literal CLI did not return one strict JSON outcome")
            CLI.append({"command": "python3 solution.py task.md", "synthetic_only": True,
                        "exit_code": run.returncode, "status": outcome.get("status"),
                        "source_and_inputs_unchanged": before == snapshots(fixture.root, (*INPUT_NAMES, *PRODUCTION)),
                        "stderr_bytes": len(run.stderr.encode()), "actual_model_fit_calls": 1 if run.returncode == 0 else None})
            self.assertEqual(run.returncode, 0, "literal CLI failed; inspect outcome in preserved receipt")
            self.assertEqual(outcome["status"], "baseline_completed")
            self.assertTrue(outcome["contract_valid"] and outcome["submission_valid"] and outcome["feature_model_fitted"])
            self.assertFalse(outcome["api_verified"] or outcome["research_completed"])
            self.assertEqual(snapshots(fixture.root, (*INPUT_NAMES, *PRODUCTION)), before)
            run_root = fixture.root / outcome["run_directory"]
            report = json.loads((run_root / "baseline-report.json").read_text())
            self.assertEqual(report["feature_model"]["audit"]["tree_count"], 300)
            self.assertEqual(report["feature_model"]["audit"]["requested_parameters"]["thread_count"], 2)
            self.assertEqual(outcome["submission_sha256"], sha(fixture.root / "submission.csv"))
            self.assertEqual(outcome["manifest_sha256"], sha(run_root / "manifest.json"))
            self.assert_output(fixture, {"report": report})


def main():
    global A, B, C, E, I, S, T, SOLUTION
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
        parser.error("requires Linux Python3.12")
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    def offline(event, arguments):
        if event in {"socket.connect", "socket.getaddrinfo", "urllib.Request"}:
            NETWORK_EVENTS.append(event)
            raise RuntimeError("network_forbidden_in_synthetic_H04_check")
    sys.addaudithook(offline)
    with args.receipt.open("x", encoding="utf-8") as stream:
        before = {name: sha(ROOT / name) for name in SOURCES}
        receipt = {"status": "FAIL_H04_BASELINE_SYNTHETIC_ONLY", "python": sys.version.split()[0],
                   "source_sha256": before, "scope": "synthetic trusted fixed-baseline orchestration, no public fit",
                   "public_model_fit_calls": 0, "live_api_calls": 0, "generated_code_executed": False,
                   "official_image_verified": False, "full_H05_accepted": False, "test_methods_run": 0}
        code = 1
        try:
            if before["requirements.txt"] != EXPECTED_REQUIREMENTS:
                raise RuntimeError("provided_requirements_changed")
            import aegml_artifacts as A
            import aegml_baseline as B
            import aegml_contracts as C
            import aegml_estimators as E
            import aegml_input as I
            import aegml_submission as S
            import aegml_training_data as T
            spec = importlib.util.spec_from_file_location("h04_solution_under_test", ROOT / "solution.py")
            SOLUTION = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(SOLUTION)
            result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BaselineChecks))
            after = {name: sha(ROOT / name) for name in SOURCES}
            passed = result.wasSuccessful() and before == after and not NETWORK_EVENTS
            receipt.update(status="PASS_H04_BASELINE_SYNTHETIC_ONLY" if passed else "FAIL_H04_BASELINE_SYNTHETIC_ONLY",
                test_methods_run=result.testsRun, behavior_cases_checked=len(CASES),
                behavior_cases_passed=sum(c["status"] == "PASS" for c in CASES), cases=CASES,
                source_sha256_after=after, source_unchanged=before == after,
                direct_actual_synthetic_fits=FITS, literal_cli_checks=CLI,
                direct_actual_synthetic_fit_calls=len(FITS), literal_cli_invocations=len(CLI),
                network_events=NETWORK_EVENTS,
                unittest_failures=[{"test": t.id(), "detail": text} for t,text in result.failures],
                unittest_errors=[{"test": t.id(), "detail": text} for t,text in result.errors],
                unittest_skips=[{"test": t.id(), "reason": reason} for t,reason in result.skipped])
            code = 0 if passed else 1
        except Exception as exc:
            receipt.update(error_type=type(exc).__name__, error_code=getattr(exc, "code", "checker_setup_failed"))
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({name: receipt.get(name) for name in ("status", "test_methods_run", "behavior_cases_checked")}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
