"""H04 trusted data/evaluator checks on synthetic temporary CSV fixtures only."""

import argparse
from contextlib import contextmanager
import csv
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import shutil
import sys
import tempfile
from time import monotonic, monotonic_ns
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
SOURCES = ("aegml_training_data.py", "scripts/check_h04_training_data.py",
           "aegml_contracts.py", "aegml_input.py", "aegml_schemas.py",
           "aegml_preprocessing.py", "aegml_validation.py", "aegml_metrics.py")
CASES = []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def fixture(task_type="regression", metric=None):
    with tempfile.TemporaryDirectory(prefix="aegml-h04-training-data-") as temporary:
        directory = Path(temporary)
        classification = task_type == "classification"
        targets = ["NA", "null", "001"] * 3 if classification else [str(10 * i) for i in range(1, 7)]
        rows = [["row_" + str(i), str(i + 1), target, "group_" + str(i)]
                for i, target in enumerate(targets)]
        metric = metric or ("Macro F1" if classification else "RMSE")

        def save():
            files = (
                ("train.csv", ["row_key", "value", "response", "group"], rows),
                ("test.csv", ["row_key", "value", "group"],
                 [["001", "11", "unseen"], ["NA", "12", "new"]]),
                ("sample_submission.csv", ["row_key", "response"], [["NA", "0"], ["001", "0"]]),
                ("data_dictionary.csv", ["feature", "role", "dtype"],
                 [["row_key", "id", "string"], ["value", "feature", "numeric"],
                  ["response", "target", "numeric"], ["group", "feature", "category"]]),
            )
            for name, header, values in files:
                with (directory / name).open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(header)
                    writer.writerows(values)
            (directory / "task.md").write_text(
                "Task type: " + task_type + "\nTarget: response\nID: row_key\nMetric: " + metric
                + "\nOutput order: test\n## Data\n- `train.csv`\n- `test.csv`\n"
                  "- `data_dictionary.csv`\n- `sample_submission.csv`\n", encoding="utf-8")

        def prepare(*, attach=True):
            shared = C.RunBudget(monotonic_ns(), 180, 1)
            contract = C.build_task_contract(directory / "task.md", budget=shared)
            bundle = I.discover_inputs(directory / "task.md", shared)
            schema = P.schema_from_kinds(contract, {"value": "numeric", "group": "categorical"})
            size = 3 if classification else 2
            plan = V.SplitPlan(tuple(range(size)), tuple(range(size, 2 * size)),
                tuple(range(2 * size, 3 * size)), len(rows), bundle.source_sha256["train"],
                "h04_training_data_fixture", schema_sha256=schema.schema_sha256,
                source_items=tuple(bundle.source_sha256.items()))
            if attach:
                contract = C.attach_split_plan(contract, plan, budget=shared)
            return bundle, contract, plan, schema, shared

        save()
        yield directory, rows, save, prepare


class Checks(unittest.TestCase):
    def passed(self, name):
        CASES.append({"case": name, "status": "PASS", "method": self.id()})

    def rejects(self, code, operation):
        with self.assertRaises(TD.TrainingDataError) as captured:
            operation()
        self.assertEqual(captured.exception.code, code)

    def test_fit_targets_bound_and_repr_private(self):
        with fixture() as (_, _, _, prepare):
            bundle, contract, plan, _, budget = prepare()
            batch = TD.load_fit_targets(bundle, contract, plan, budget=budget)
            self.assertEqual(batch.values, (10.0, 20.0))
            self.assertEqual(batch.row_indices, plan.fit_indices)
            self.assertEqual(batch.source_sha256, bundle.source_sha256["train"])
            self.assertEqual(batch.partition_sha256, plan.partition_sha256)
            self.assertEqual(batch.phase, "search_fit_targets")
            self.assertEqual(batch.audit()["rows"], 2)
            self.assertFalse(batch.audit()["os_boundary_verified"])
            self.assertNotIn("values=", repr(batch))
            self.assertNotIn("row_indices=", repr(batch))
            self.passed("H04_TD_fit_targets_bound")
        canary = "H04_TARGET_REPR_CANARY_SECRET_SYNTHETIC"
        batch = TD.TargetBatch((canary,), (0,), "a" * 64, "b" * 64, task_type="classification")
        self.assertNotIn(canary, repr(batch))
        self.assertNotIn(canary, json.dumps(batch.audit()))
        self.passed("H04_TD_repr_and_audit_no_target")

    def test_lexical_classes_and_numeric_adapter_compatibility(self):
        with fixture("classification") as (_, _, _, prepare):
            bundle, contract, plan, _, budget = prepare()
            batch = TD.load_fit_targets(bundle, contract, plan, budget=budget)
            self.assertEqual(batch.values, ("NA", "null", "001"))
            self.assertEqual(batch.task_type, "classification")
            self.passed("H04_TD_lexical_classes_numeric_dtype")
        batch = TD.TargetBatch((0.25, 1.5, 9.75), (0, 1, 2), "a" * 64, "b" * 64,
                               task_type="classification")
        self.assertEqual(batch.values, (0.25, 1.5, 9.75))
        for values, code in [(("001", 1), "mixed_class_target_types"),
                             ((True,), "invalid_class_target"),
                             ((float("nan"),), "invalid_class_target"),
                             (("",), "invalid_class_target")]:
            self.rejects(code, lambda: TD.TargetBatch(values, tuple(range(len(values))),
                "a" * 64, "b" * 64, task_type="classification"))
        self.passed("H04_TD_typed_finite_class_guards")

    def test_inner_features_keep_canonical_rows_and_feature_order(self):
        with fixture() as (_, _, _, prepare):
            bundle, contract, plan, schema, budget = prepare()
            frame = TD.load_inner_features(bundle, contract, plan, schema=schema, budget=budget)
            self.assertEqual(tuple(frame.columns), ("value", "group"))
            self.assertEqual(tuple(frame.index), plan.inner_indices)
            self.assertEqual(frame["value"].tolist(), ["3", "4"])
            self.assertFalse(any(name in frame for name in ("row_key", "response")))
            self.passed("H04_TD_inner_features_not_targets_or_ids")

    def test_outer_poison_cannot_change_fit_or_inner_quality(self):
        with fixture() as (_, rows, save, prepare):
            bundle, contract, plan, schema, budget = prepare()
            first = TD.load_fit_targets(bundle, contract, plan, budget=budget)
            prediction = TD.PredictionBatch((28.0, 44.0), plan.inner_indices)
            first_eval = TD.evaluate_inner_predictions(bundle, contract, plan, prediction, budget=budget)
            view = P.load_train_fit_view(bundle, contract, plan, schema=schema, budget=budget)
            prep, _ = P.fit_transform(view, budget=budget)
            for index in plan.outer_indices:
                rows[index][1:] = ["INVALID_OUTER_FEATURE", "NaN", "NEW_OUTER_ONLY_CATEGORY"]
            save()
            bundle, contract, plan, schema, budget = prepare()
            second = TD.load_fit_targets(bundle, contract, plan, budget=budget)
            second_eval = TD.evaluate_inner_predictions(bundle, contract, plan, prediction, budget=budget)
            second_view = P.load_train_fit_view(bundle, contract, plan, schema=schema, budget=budget)
            second_prep, _ = P.fit_transform(second_view, budget=budget)
            self.assertEqual(first.values, second.values)
            self.assertEqual(first_eval.metric_report, second_eval.metric_report)
            self.assertEqual(first_eval.diagnostics, second_eval.diagnostics)
            self.assertNotEqual(first.source_sha256, second.source_sha256)
            self.assertEqual(prep.statistics_sha256, second_prep.statistics_sha256)
            self.passed("H04_TD_outer_poison_fit_eval_and_preprocessing_invariant")

    def test_inner_targets_change_only_evaluation(self):
        with fixture() as (_, rows, save, prepare):
            bundle, contract, plan, schema, budget = prepare()
            targets = TD.load_fit_targets(bundle, contract, plan, budget=budget)
            frame = TD.load_inner_features(bundle, contract, plan, schema=schema, budget=budget)
            prediction = TD.PredictionBatch((28.0, 44.0), plan.inner_indices)
            before = TD.evaluate_inner_predictions(bundle, contract, plan, prediction, budget=budget)
            rows[2][2], rows[3][2] = "300", "400"
            save()
            bundle, contract, plan, schema, budget = prepare()
            after_targets = TD.load_fit_targets(bundle, contract, plan, budget=budget)
            after_frame = TD.load_inner_features(bundle, contract, plan, schema=schema, budget=budget)
            after = TD.evaluate_inner_predictions(bundle, contract, plan, prediction, budget=budget)
            self.assertEqual(targets.values, after_targets.values)
            self.assertTrue(frame.equals(after_frame))
            self.assertNotEqual(before.metric_report["value"], after.metric_report["value"])
            self.passed("H04_TD_inner_y_only_evaluator_feedback")

    def test_regression_metric_and_aggregate_diagnostics(self):
        with fixture() as (_, _, _, prepare):
            bundle, contract, plan, _, budget = prepare()
            result = TD.evaluate_inner_predictions(bundle, contract, plan,
                TD.PredictionBatch((28.0, 44.0), plan.inner_indices), budget=budget)
            self.assertAlmostEqual(result.metric_report["value"], math.sqrt(10))
            diagnostic = result.diagnostics
            self.assertEqual(diagnostic["rows"], 2)
            self.assertEqual(diagnostic["mae"], 3.0)
            self.assertEqual(diagnostic["bias"], 1.0)
            self.assertEqual(diagnostic["absolute_error_quantiles"]["p50"], 3.0)
            self.assertAlmostEqual(diagnostic["absolute_error_quantiles"]["p95"], 3.9)
            report = result.to_dict()
            self.assertFalse(report["raw_inner_targets_returned"])
            self.assertFalse(report["outer_quality_evaluated"])
            self.assertNotIn("row_indices", report)
            detached = result.metric_report
            detached["value"] = -1
            self.assertGreater(result.metric_report["value"], 0)
            json.dumps(report, allow_nan=False)
            self.passed("H04_TD_regression_diagnostics_and_detached_result")

    def test_classification_metric_confusion_and_bounded_partial_report(self):
        with fixture("classification") as (_, _, _, prepare):
            bundle, contract, plan, _, budget = prepare()
            prediction = TD.PredictionBatch(("NA", "NA", "NA"), plan.inner_indices)
            result = TD.evaluate_inner_predictions(bundle, contract, plan, prediction, budget=budget)
            self.assertAlmostEqual(result.metric_report["value"], 1 / 6)
            diagnostic = result.diagnostics
            na = next(item for item in diagnostic["per_class"] if item["label"] == "NA")
            self.assertEqual((na["TP"], na["FP"], na["FN"], na["support"]), (1, 2, 0, 1))
            self.assertAlmostEqual(na["precision"], 1 / 3)
            self.assertTrue(diagnostic["confusion_complete"])
            self.assertEqual(sum(item["count"] for item in diagnostic["confusion"]), 3)
            self.passed("H04_TD_macro_f1_and_perclass_confusion")
            limited = TD.evaluate_inner_predictions(bundle, contract, plan, prediction, budget=budget,
                limits=TD.TrainingDataLimits(max_diagnostic_classes=1, max_confusion_pairs=1)).diagnostics
            self.assertEqual(limited["classes_included"], 1)
            self.assertEqual(limited["classes_omitted"], 2)
            self.assertFalse(limited["confusion_complete"])
            self.assertEqual(limited["unretained_pair_occurrences"], 2)
            self.assertEqual(limited["confusion_scope"], "retained_first_seen_pairs_only")
            self.passed("H04_TD_bounded_partial_confusion_explicit")

    def test_posthoc_rank_error_bands_manual_tail_and_zero(self):
        budget = C.RunBudget(monotonic_ns(), 180, 1)
        with fixture() as (_, _, _, prepare):
            _, contract, _, _, _ = prepare()
            metric = contract.to_dict()["metric"]
        result = TD._regression_diagnostics((0., 0., 0., 0.), (0., 0., 0., 10.), metric, budget)
        bands = {item["band"]: item for item in result["error_rank_bands"]}
        self.assertEqual(bands["best_50pct"]["rows"], 2)
        self.assertEqual(bands["next_40pct"]["rows"], 1)
        self.assertEqual(bands["worst_10pct"]["rows"], 1)
        self.assertEqual(bands["worst_10pct"]["sse_share"], 1.)
        self.assertEqual(bands["worst_10pct"]["mae"], 10.)
        self.assertEqual(bands["worst_10pct"]["rmse"], 10.)
        self.assertEqual(bands["worst_10pct"]["bias"], 10.)
        self.assertTrue(result["posthoc_error_slices_not_independent_quality"])
        self.passed("H04_TD_manual_rank_tail_all_SSE_in_worst_band")
        zero = TD._regression_diagnostics((0.,) * 4, (0.,) * 4, metric, budget)
        self.assertEqual(sum(item["rows"] for item in zero["error_rank_bands"]), 4)
        self.assertTrue(all(item["sse_share"] == 0. for item in zero["error_rank_bands"]))
        self.assertTrue(all(item["rmse"] == 0. for item in zero["error_rank_bands"]))
        json.dumps(zero, allow_nan=False)
        self.passed("H04_TD_rank_zero_SSE_no_NaN")

    def test_posthoc_rank_error_bands_extreme_finite_and_budget(self):
        budget = C.RunBudget(monotonic_ns(), 180, 1)
        with fixture() as (_, _, _, prepare):
            _, contract, _, _, _ = prepare()
            metric = contract.to_dict()["metric"]
        result = TD._regression_diagnostics((1e308, 0., 0., 0.), (-1e308, 0., 0., 0.), metric, budget)
        worst = result["error_rank_bands"][-1]
        self.assertEqual(worst["sse_share"], 1.)
        self.assertIsNone(worst["rmse"])
        self.assertIsNone(worst["mae"])
        self.assertEqual(worst["numeric_status"], "partial_overflow_unavailable")
        self.assertEqual(result["nonrepresentable_individual_residuals"], 1)
        json.dumps(result, allow_nan=False)
        self.passed("H04_TD_rank_extreme_finite_residual_overflow_explicit")
        exhausted = C.RunBudget(0, 10, 1, clock=lambda: 11_000_000_000)
        with self.assertRaises(C.BudgetExpired):
            TD._regression_diagnostics((0.,) * 4, (0.,) * 4, metric, exhausted)
        self.passed("H04_TD_rank_diagnostics_budget_required")

    def test_prediction_wrapper_order_and_constructor_guards(self):
        with fixture() as (_, _, _, prepare):
            bundle, contract, plan, _, budget = prepare()
            for prediction in [(28.0, 44.0), TD.PredictionBatch((44.0, 28.0), (3, 2))]:
                self.rejects("inner_prediction_row_order_mismatch", lambda:
                    TD.evaluate_inner_predictions(bundle, contract, plan, prediction, budget=budget))
            self.passed("H04_TD_exact_prediction_row_order")
        for rows in [(0, 0), (True,), (), [0], (-1,)]:
            self.rejects("invalid_target_row_indices", lambda: TD.PredictionBatch(tuple(range(len(rows))), rows))
        self.rejects("invalid_prediction_batch", lambda: TD.PredictionBatch((1,), (0, 1)))
        self.rejects("invalid_fit_target_batch", lambda: TD.TargetBatch((1, 2), (1, 0), "a" * 64, "b" * 64))
        self.passed("H04_TD_wrapper_shape_phase_and_index_guards")

    def test_source_and_active_partition_binding(self):
        with fixture() as (directory, _, _, prepare):
            bundle, contract, plan, _, budget = prepare()
            wrong = replace(plan, fit_indices=plan.outer_indices, outer_indices=plan.fit_indices)
            self.rejects("active_split_policy_mismatch", lambda:
                TD.load_fit_targets(bundle, contract, wrong, budget=budget))
            self.passed("H04_TD_plan_A_contract_plan_B_rejected")
            unbuilt = C.build_task_contract(directory / "task.md", budget=budget)
            self.rejects("active_split_policy_required", lambda:
                TD.load_fit_targets(bundle, unbuilt, plan, budget=budget))
            self.passed("H04_TD_not_built_rejected")
            source = directory / "train.csv"
            before = source.stat()
            content = source.read_bytes()
            source.write_bytes(content.replace(b"row_0", b"raw_0", 1))
            os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
            self.rejects("source_bytes_changed", lambda:
                TD.load_fit_targets(bundle, contract, plan, budget=budget))
            self.passed("H04_TD_same_size_mtime_source_drift_rejected")

    def test_all_sources_task_and_destination_binding(self):
        with fixture() as (directory, _, _, prepare):
            bundle, contract, plan, _, budget = prepare()
            payload = contract.to_dict()
            payload["output_path"] = str(directory / "other.csv")
            forged = C.TaskContract(payload, contract.alignment)
            self.rejects("training_task_path_mismatch", lambda:
                TD.load_fit_targets(bundle, forged, plan, budget=budget))
            self.passed("H04_TD_destination_binding")
            with tempfile.TemporaryDirectory(prefix="aegml-h04-copy-") as other:
                other_path = Path(other)
                for item in directory.iterdir():
                    if item.is_file():
                        shutil.copyfile(item, other_path / item.name)
                copied = I.discover_inputs(other_path / "task.md", budget)
            self.rejects("source_contract_identity_mismatch", lambda:
                    TD.load_fit_targets(copied, contract, plan, budget=budget))
            self.passed("H04_TD_identical_bytes_different_task_rejected")
            wrong_sources = dict(plan.source_sha256)
            wrong_sources["test"] = "0" * 64
            wrong_plan = replace(plan, source_items=tuple(wrong_sources.items()))
            self.rejects("training_split_source_mismatch", lambda:
                TD.load_fit_targets(bundle, contract, wrong_plan, budget=budget))
            self.passed("H04_TD_all_five_plan_sources_bound")

    def test_selected_invalid_targets_are_not_dropped(self):
        with fixture() as (_, rows, save, prepare):
            for target, code in [("", "invalid_selected_target"), ("wrong", "invalid_regression_target"),
                                 ("NaN", "nonfinite_regression_target"), ("Inf", "nonfinite_regression_target"),
                                 ("1e9999", "nonfinite_regression_target")]:
                rows[0][2] = target
                save()
                bundle, contract, plan, _, budget = prepare()
                self.rejects(code, lambda: TD.load_fit_targets(bundle, contract, plan, budget=budget))
            self.passed("H04_TD_invalid_selected_regression_targets_rejected")
        with fixture("classification") as (_, rows, save, prepare):
            rows[0][2] = " "
            save()
            bundle, contract, plan, _, budget = prepare()
            self.rejects("invalid_selected_target", lambda:
                TD.load_fit_targets(bundle, contract, plan, budget=budget))
            self.passed("H04_TD_blank_selected_class_rejected")

    def test_invalid_predictions_fail_before_scoring(self):
        with fixture() as (_, _, _, prepare):
            bundle, contract, plan, _, budget = prepare()
            for value in (True, "28", float("nan"), float("inf")):
                self.rejects("invalid_numeric_prediction", lambda:
                    TD.evaluate_inner_predictions(bundle, contract, plan,
                        TD.PredictionBatch((value, 44), plan.inner_indices), budget=budget))
            self.passed("H04_TD_nonfinite_or_non_numeric_prediction_rejected")
        with fixture("classification") as (_, _, _, prepare):
            bundle, contract, plan, _, budget = prepare()
            for value in (True, 1, "", " "):
                self.rejects("invalid_class_prediction", lambda:
                    TD.evaluate_inner_predictions(bundle, contract, plan,
                        TD.PredictionBatch((value, "null", "001"), plan.inner_indices), budget=budget))
            self.rejects("unknown_class_label", lambda:
                TD.evaluate_inner_predictions(bundle, contract, plan,
                    TD.PredictionBatch(("unknown", "null", "001"), plan.inner_indices),
                    budget=budget, allowed_labels=("NA", "null", "001")))
            self.passed("H04_TD_lexical_prediction_and_allowed_labels_guards")

    def test_budget_and_retention_limits(self):
        with fixture() as (_, _, _, prepare):
            bundle, contract, plan, schema, budget = prepare()
            self.rejects("budget_required", lambda: TD.load_fit_targets(bundle, contract, plan, budget=None))
            exhausted = C.RunBudget(0, 10, 1, clock=lambda: 11_000_000_000)
            with self.assertRaises(C.BudgetExpired):
                TD.load_fit_targets(bundle, contract, plan, budget=exhausted)
            self.passed("H04_TD_mandatory_and_expired_shared_budget")
            for limits, code, features in [
                (TD.TrainingDataLimits(max_retained_target_chars=1), "training_target_character_limit", False),
                (TD.TrainingDataLimits(max_feature_chars=1), "training_feature_character_limit", True),
                (TD.TrainingDataLimits(max_feature_cells=1), "training_feature_cell_limit", True)]:
                call = (lambda: TD.load_inner_features(bundle, contract, plan, schema=schema,
                    budget=budget, limits=limits)) if features else (lambda:
                    TD.load_fit_targets(bundle, contract, plan, budget=budget, limits=limits))
                self.rejects(code, call)
            self.passed("H04_TD_bounded_selected_labels_features_cells")
            self.rejects("inner_diagnostic_output_limit", lambda:
                TD.evaluate_inner_predictions(bundle, contract, plan,
                    TD.PredictionBatch((28., 44.), plan.inner_indices), budget=budget,
                    limits=TD.TrainingDataLimits(max_diagnostic_bytes=1)))
            self.rejects("invalid_training_data_limits", lambda: TD.TrainingDataLimits(max_feature_cells=True))
            self.passed("H04_TD_finite_bounded_diagnostic_json")

    def test_other_registry_metrics_are_explicitly_unsupported_h04(self):
        for task_type, metric in [("regression", "MAE"), ("classification", "Accuracy")]:
            with fixture(task_type, metric) as (_, _, _, prepare):
                bundle, contract, plan, _, budget = prepare()
                self.rejects("unsupported_h04_metric", lambda:
                    TD.load_fit_targets(bundle, contract, plan, budget=budget))
        self.passed("H04_TD_unsupported_metrics_explicit_no_silent_substitution")

    def test_no_network_evaluation_path(self):
        with fixture() as (_, _, _, prepare):
            bundle, contract, plan, _, budget = prepare()
            with patch("socket.socket", side_effect=AssertionError("network_forbidden")), \
                    patch("socket.create_connection", side_effect=AssertionError("network_forbidden")):
                result = TD.evaluate_inner_predictions(bundle, contract, plan,
                    TD.PredictionBatch((28., 44.), plan.inner_indices), budget=budget)
            self.assertEqual(result.phase, "inner_score_evaluation")
            self.passed("H04_TD_no_network_evaluation_path")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if os.path.lexists(args.receipt):
        parser.error("receipt exists; choose a new path")
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    initial = {name: sha(ROOT / name) for name in SOURCES}
    started = monotonic()
    receipt = {"phase": "H04_trusted_training_data", "status": "NOT_RUN",
        "python": platform.python_version(), "source_sha256": initial,
        "scope": "synthetic source-bound fit targets, inner-only features and trusted aggregate evaluation",
        "predictive_estimator_fit_calls": 0, "public_dataset_model_fits": 0,
        "live_api_calls": 0, "provider_configuration_read": False,
        "package_installation_executed": False, "outer_quality_evaluated": False,
        "os_isolation_verified": False, "preprocessing_fit_scope": "tiny synthetic fixtures only"}
    if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
        receipt.update(status="BLOCKED_WRONG_CHECK_ENVIRONMENT", test_methods_run=0, behavior_cases_checked=0)
        code = 2
    else:
        global C, I, P, TD, V
        import aegml_contracts as C
        import aegml_input as I
        import aegml_preprocessing as P
        import aegml_training_data as TD
        import aegml_validation as V

        outcome = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
        final = {name: sha(ROOT / name) for name in SOURCES}
        stable = initial == final
        passed = outcome.wasSuccessful() and stable
        receipt.update(status="PASS_H04_TRAINING_DATA_SYNTHETIC_ONLY" if passed else "FAIL_H04_TRAINING_DATA",
            test_methods_run=outcome.testsRun, behavior_cases_checked=len(CASES), cases=CASES,
            source_sha256_after=final, source_unchanged_during_check=stable,
            unittest_failures=[{"test": test.id(), "detail": detail} for test, detail in outcome.failures],
            unittest_errors=[{"test": test.id(), "detail": detail} for test, detail in outcome.errors])
        code = 0 if passed else 1
    receipt.update(elapsed_seconds=monotonic() - started,
                   peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
                   rss_scope="whole Linux checker including imports and tiny synthetic preprocessing")
    with args.receipt.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": receipt["status"], "test_methods_run": receipt["test_methods_run"],
                      "behavior_cases_checked": receipt["behavior_cases_checked"],
                      "receipt": str(args.receipt)}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
