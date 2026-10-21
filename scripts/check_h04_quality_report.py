"""Synthetic aggregate-method checks: no measured dataset quality or fitting."""

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/build_h04_quality_report.py"
spec = importlib.util.spec_from_file_location("quality_builder", BUILDER)
Q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(Q)
CASES = []
SOURCES = {"solution.py": "a" * 64, "requirements.txt": "b" * 64, "aegml_fixture.py": "c" * 64}


def fixture(task_type):
    """Intentionally fake frozen aggregates; no feature model is invoked."""
    classification = task_type == "classification"
    source = {key: str(index + 1) * 64 for index, key in enumerate(sorted(Q.SOURCE_ROLES))}
    train, partition, statistics = source["train"], "6" * 64, "7" * 64
    n = 4

    def evaluation(feature):
        score = (1 / 3 if feature else 1 / 5) if classification else (5. if feature else 10.)
        metric = {"name": "macro_f1" if classification else "rmse", "value": score,
            "direction": "maximize" if classification else "minimize",
            "prediction_kind": "label" if classification else "numeric", "n_rows": n,
            "adapter_version": "metrics.v1", "official_score": None}
        if classification:
            # Four rows: true A,A,B,B; model A,B,A,B; constant A,A,A,A.
            classes = ([{"label": "A", "support": 2, "TP": 1, "FP": 1, "FN": 1,
                         "precision": .5, "recall": .5, "f1": .5},
                        {"label": "B", "support": 2, "TP": 1, "FP": 1, "FN": 1,
                         "precision": .5, "recall": .5, "f1": .5}] if feature else
                       [{"label": "A", "support": 2, "TP": 2, "FP": 2, "FN": 0,
                         "precision": .5, "recall": 1., "f1": 2 / 3},
                        {"label": "B", "support": 2, "TP": 0, "FP": 0, "FN": 2,
                         "precision": 0., "recall": 0., "f1": 0.}])
            # Primary metric follows the reported complete per-class F1 exactly.
            score = metric["value"] = .5 if feature else 1 / 3
            confusion = ([{"actual": a, "predicted": b, "count": 1} for a in ("A", "B") for b in ("A", "B")]
                         if feature else [{"actual": "A", "predicted": "A", "count": 2},
                                          {"actual": "B", "predicted": "A", "count": 2}])
            diagnostic = {"kind": "classification", "rows": n, "average": "macro",
                "labels_policy": "sklearn_labels_none", "raw_row_targets_returned": False,
                "per_class": classes, "classes_total": 2, "classes_included": 2, "classes_omitted": 0,
                "confusion": confusion, "confusion_complete": True, "unretained_pair_occurrences": 0}
        else:
            diagnostic = {"kind": "regression", "rows": n, "raw_residuals_or_targets_returned": False,
                "posthoc_error_slices_not_independent_quality": True, "mae": 2.5 if feature else 5.,
                "bias": 2.5 if feature else 5.,
                "absolute_error_quantiles": {"p50": 0., "p90": 7., "p95": 8.5, "p99": 9.7},
                "maximum_absolute_error": 10., "error_rank_bands": [
                    {"band": "best_50pct", "rows": 2, "mae": 0., "rmse": 0., "bias": 0.,
                     "sse_share": 0., "numeric_status": "finite"},
                    {"band": "next_40pct", "rows": 1, "mae": 0., "rmse": 0., "bias": 0.,
                     "sse_share": 0., "numeric_status": "finite"},
                    {"band": "worst_10pct", "rows": 1, "mae": 10., "rmse": 10., "bias": 10.,
                     "sse_share": 1., "numeric_status": "finite"}]}
        return {"phase": "inner_score_evaluation", "source_sha256": train, "partition_sha256": partition,
            "inner_row_indices_sha256": "d" * 64,
            "raw_inner_targets_returned": False, "outer_quality_evaluated": False,
            "metric_report": metric, "diagnostics": diagnostic}

    constant, feature = evaluation(False), evaluation(True)
    gain = (feature["metric_report"]["value"] - constant["metric_report"]["value"] if classification
            else constant["metric_report"]["value"] - feature["metric_report"]["value"])
    return {"schema_version": "baseline_report.v1", "status": "PASS_H04_FIXED_BASELINE_ONLY",
        "synthetic_method_fixture": True, "protocol": "H04_FIXED_SEARCH_FIT_ONLY", "task_type": task_type,
        "metric_contract": {"name": "macro_f1" if classification else "rmse",
            "direction": "maximize" if classification else "minimize",
            "prediction_kind": "label" if classification else "numeric", "finite_policy": "finite_only",
            "target_scale": "original", "parameters": {"average": "macro", "labels": None} if classification else {}},
        "model_fit_calls": 1, "constant_fit_calls": 1, "live_api_calls": 0,
        "phase_access": {"estimator_labels": "T_fit_only", "inner_labels": "trusted_evaluator_only",
            "outer_targets_retained_or_scored": False, "test_targets_available": False,
            "frozen_refit_performed": False, "os_worker_boundary_verified": False},
        "source_code_sha256": SOURCES.copy(), "source_sha256": source,
        "split": {"source_sha256": source.copy(), "train_sha256": train, "partition_sha256": partition,
            "counts": {"fit": 4, "inner": 4, "outer": 4}, "train_rows": 12, "seed": 42,
            "policy_id": "synthetic_method_fixture", "strategy": "explicit"},
        "preprocessing": {"phase": "search_fit", "source_sha256": train, "split_sha256": partition,
            "fit_rows": 4, "trained_statistics_sha256": statistics, "recipe_sha256": "8" * 64,
            "feature_order_sha256": "9" * 64, "feature_count": 2, "categorical_strategy": "native",
            "missing_policy": "literal_empty_only"},
        "constant": {"kind": "fit_majority" if classification else "fit_mean", "evaluation": constant},
        "feature_model": {"evaluation": feature, "audit": {
            "estimator_fitted": True, "eval_set_used": False, "refit_performed": False,
            "fit_scope": "NO_REFIT_SEARCH_ONLY", "source_sha256": train, "partition_sha256": partition,
            "preprocessing_statistics_sha256": statistics, "tree_count": 300,
            "requested_parameters": {**Q.FIXED_PARAMETERS, "loss_function": "Logloss" if classification else "RMSE"},
            "fit_seconds": 1., "predict_seconds": .1}},
        "improvement_over_constant": gain, "selected": "feature_model", "selection_tolerance": 1e-12,
        "versions": {"python": "3.12.3", "numpy": "1.26.4", "pandas": "2.2.3", "scipy": "1.12.0",
                     "scikit-learn": "1.5.2", "catboost": "1.2.8"},
        "timer": {"total_seconds": 120., "reserve_seconds": 10., "elapsed_seconds": 3.},
        "official_baseline_value": None, "official_score": None, "autoresearch_performed": False,
        "unknown_extra_private_path": "/SYNTHETIC_PRIVATE_PATH_CANARY/do_not_copy",
        "unknown_extra_raw_predictions": ["SYNTHETIC_ROW_PREDICTION_CANARY"]}


def pair():
    return [(fixture("regression"), "a" * 64), (fixture("classification"), "b" * 64)]


def build(inputs):
    with patch.object(Q, "current_source_map", return_value=SOURCES.copy()):
        return Q.build_summary(inputs, synthetic=True)


class Checks(unittest.TestCase):
    def passed(self, name):
        CASES.append({"case": name, "status": "PASS", "method": self.id()})

    def rejects(self, code, operation):
        with self.assertRaises(Q.QualityReportError) as captured:
            operation()
        self.assertEqual(captured.exception.code, code)

    def test_directions_observations_and_not_measured_quality(self):
        result = build(pair())
        self.assertEqual(result["status"], "PASS_SYNTHETIC_QUALITY_METHOD_CHECK_ONLY")
        reg, cls = result["observations"]["regression"], result["observations"]["classification"]
        self.assertEqual(reg["improvement_over_constant"], 5.)
        self.assertAlmostEqual(cls["improvement_over_constant"], 1 / 6)
        self.assertEqual(reg["diagnostics"]["feature_model"]["worst_10pct_SSE_share"], 1.)
        self.assertEqual(cls["diagnostics"]["constant"]["weak_classes_ranked_by_inner_F1_then_support"][0]["label"], "B")
        self.assertIsNone(result["official_score"])
        self.assertFalse(result["future_improvement_claimed"])
        self.passed("H04_QUALITY_synthetic_directions_and_tail_weakclass_observations")

    def test_negative_and_zero_improvements_not_omitted(self):
        inputs = pair()
        reg = inputs[0][0]
        reg["feature_model"]["evaluation"]["metric_report"]["value"] = 12.
        reg["improvement_over_constant"], reg["selected"] = -2., "fit_mean"
        cls = inputs[1][0]
        cls["feature_model"]["evaluation"] = copy.deepcopy(cls["constant"]["evaluation"])
        cls["improvement_over_constant"], cls["selected"] = 0., "fit_majority"
        result = build(inputs)
        self.assertEqual(result["observations"]["regression"]["result_vs_constant"], "degradation")
        self.assertEqual(result["observations"]["classification"]["result_vs_constant"], "no_measurable_change")
        self.assertEqual(len(result["preregistered_hypotheses"]), 4)
        self.passed("H04_QUALITY_negative_and_zero_gain_preserved")

    def test_preregistration_single_changes_MEI_and_no_leakage_claim(self):
        result = build(pair())
        hypotheses = {item["id"]: item for item in result["preregistered_hypotheses"]}
        self.assertEqual(set(hypotheses), {"HYP-R01", "HYP-R02", "HYP-C01", "HYP-C02"})
        self.assertEqual(hypotheses["HYP-R01"]["minimum_effect"]["relative"], .005)
        self.assertEqual(hypotheses["HYP-C01"]["minimum_effect"]["absolute"], .003)
        self.assertTrue(all(item["candidate_fit_calls"] == 0 for item in hypotheses.values()))
        self.assertIn("T_fit", hypotheses["HYP-C01"]["T_fit_weight_recipe"])
        self.assertTrue(result["comparison_protocol"]["adaptive_inner_overfitting_risk"])
        text = json.dumps(result)
        self.assertNotIn("PRIVATE_PATH_CANARY", text)
        self.assertNotIn("ROW_PREDICTION_CANARY", text)
        self.passed("H04_QUALITY_preregistered_MEI_Tfit_only_and_allowlisted_output")

    def test_phase_call_count_source_and_config_refusals(self):
        for code, mutate in [
            ("baseline_phase_access_mismatch", lambda report: report["phase_access"].update(outer_targets_retained_or_scored=True)),
            ("baseline_call_count_mismatch", lambda report: report.update(live_api_calls=1)),
            ("source_code_sha_mismatch", lambda report: report["source_code_sha256"].update({"solution.py": "0" * 64})),
            ("fixed_estimator_config_mismatch", lambda report: report["feature_model"]["audit"]["requested_parameters"].update(iterations=200)),
            ("evaluation_scope_mismatch", lambda report: report["constant"]["evaluation"].update(partition_sha256="0" * 64)),
            ("reported_gain_mismatch", lambda report: report.update(improvement_over_constant=999)),
        ]:
            inputs = pair()
            mutate(inputs[0][0])
            self.rejects(code, lambda: build(inputs))
        self.passed("H04_QUALITY_phase_counts_source_config_eval_gain_refusals")

    def test_cross_task_pair_and_versions_and_fixed_not_accuracy(self):
        inputs = pair()
        inputs[1][0]["versions"]["catboost"] = "9.9.9"
        self.rejects("cross_task_config_or_version_mismatch", lambda: build(inputs))
        self.rejects("duplicate_quality_task", lambda: build([pair()[0], pair()[0]]))
        inputs = pair()
        inputs[1][0]["metric_contract"]["name"] = "accuracy"
        self.rejects("primary_metric_mismatch", lambda: build(inputs))
        with patch.object(Q, "current_source_map", return_value=SOURCES.copy()):
            self.rejects("synthetic_report_scope_mismatch", lambda: Q.build_summary(pair()))
        self.passed("H04_QUALITY_cross_task_consistency_MacroF1_and_synthetic_CLI_gate")

    def test_diagnostic_contracts_refuse_missing_bands_bad_confusion(self):
        inputs = pair()
        inputs[0][0]["feature_model"]["evaluation"]["diagnostics"]["error_rank_bands"] = []
        self.rejects("regression_rank_bands_missing", lambda: build(inputs))
        inputs = pair()
        inputs[1][0]["feature_model"]["evaluation"]["diagnostics"]["confusion"][0]["count"] = 2
        self.rejects("confusion_row_count_mismatch", lambda: build(inputs))
        self.passed("H04_QUALITY_diagnostic_shape_integrity")

    def test_strict_reader_bytecap_duplicate_NaN_and_symlink(self):
        with tempfile.TemporaryDirectory(prefix="h04-quality-method-") as temporary:
            path = Path(temporary) / "report.json"
            path.write_text('{"a":1,"a":2}', encoding="utf-8")
            self.rejects("duplicate_report_json_key", lambda: Q.read_report(path))
            for text in ('{"value":NaN}', '{"value":1e9999}'):
                path.write_text(text, encoding="utf-8")
                self.rejects("nonfinite_report_number", lambda: Q.read_report(path))
            path.write_bytes(b" " * (Q.MAX_BYTES + 1))
            self.rejects("report_byte_limit", lambda: Q.read_report(path))
            path.write_text('{"bounded":true}', encoding="utf-8")
            value, source = Q.read_report(path)
            self.assertEqual(value, {"bounded": True})
            self.assertEqual(source, hashlib.sha256(path.read_bytes()).hexdigest())
            link = Path(temporary) / "link.json"
            link.symlink_to(path)
            self.rejects("invalid_report_file", lambda: Q.read_report(link))
            self.passed("H04_QUALITY_strict_bounded_source_reader")

    def test_new_atomic_output_preserved_on_repeat_and_no_temp(self):
        with tempfile.TemporaryDirectory(prefix="h04-quality-method-") as temporary:
            path = Path(temporary) / "quality.json"
            result = build(pair())
            record = Q.publish_new(path, result)
            original = path.read_bytes()
            self.assertEqual(record["sha256"], hashlib.sha256(original).hexdigest())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.rejects("quality_output_exists", lambda: Q.publish_new(path, result))
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(list(path.parent.glob(".quality-tmp-*")))
            self.passed("H04_QUALITY_atomic_exclusive_private_output")

    def test_actual_current_source_hash_and_failure_stdout_no_private_paths(self):
        sources = Q.current_source_map()
        self.assertEqual(sources["aegml_training_data.py"], hashlib.sha256((ROOT / "aegml_training_data.py").read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory(prefix="h04-quality-method-") as temporary:
            path = Path(temporary) / "SYNTHETIC_PRIVATE_PATH_CANARY.json"
            command = [sys.executable, "-I", "-B", str(BUILDER), "--report", str(path), "--report", str(path),
                       "--output", str(Path(temporary) / "output.json")]
            child = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
                                   env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"}, text=True)
            self.assertEqual(child.returncode, 1)
            self.assertNotIn("PRIVATE_PATH_CANARY", child.stdout + child.stderr)
            self.assertEqual(json.loads(child.stdout)["status"], "FAIL_H04_QUALITY_REPORT")
            self.assertFalse((Path(temporary) / "output.json").exists())
        self.passed("H04_QUALITY_current_source_hash_and_fixed_cli_failure")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if os.path.lexists(args.receipt):
        parser.error("receipt exists; choose a new path")
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    before = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in (BUILDER, Path(__file__))}
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    after = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in before}
    stable = before == after
    passed = result.wasSuccessful() and stable
    receipt = {"status": "PASS_SYNTHETIC_QUALITY_METHOD_CHECKS_ONLY" if passed else "FAIL_QUALITY_METHOD_CHECKS",
        "scope": "synthetic aggregate fixtures; NOT measured model quality or an actual dataset comparison",
        "python": platform.python_version(), "test_methods_run": result.testsRun,
        "behavior_cases_checked": len(CASES), "cases": CASES, "source_sha256": before,
        "source_sha256_after": after, "source_unchanged": stable,
        "new_training_calls": 0, "live_api_calls": 0,
        "failures": [{"test": test.id(), "detail": detail} for test, detail in result.failures],
        "errors": [{"test": test.id(), "detail": detail} for test, detail in result.errors]}
    with args.receipt.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({key: receipt[key] for key in ("status", "test_methods_run", "behavior_cases_checked")}, allow_nan=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
