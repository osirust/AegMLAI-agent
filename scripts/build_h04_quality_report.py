"""Combine two source-bound H04 baseline aggregates; no training or API calls."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 1 << 20
SOURCE_ROLES = {"task", "train", "test", "data_dictionary", "sample_submission"}
SHA = re.compile(r"[0-9a-f]{64}\Z")
PARAMETER_KEYS = {"task_type", "thread_count", "iterations", "learning_rate", "depth", "l2_leaf_reg",
    "boosting_type", "bootstrap_type", "subsample", "rsm", "border_count", "one_hot_max_size",
    "max_ctr_complexity", "counter_calc_method", "nan_mode", "random_seed", "allow_writing_files",
    "use_best_model", "verbose", "loss_function"}
VERSION_KEYS = {"python", "numpy", "pandas", "scipy", "scikit-learn", "catboost"}
FIXED_PARAMETERS = {"task_type": "CPU", "thread_count": 8, "iterations": 300,
    "learning_rate": .05, "depth": 6, "l2_leaf_reg": 5, "boosting_type": "Plain",
    "bootstrap_type": "Bernoulli", "subsample": .8, "rsm": 1, "border_count": 128,
    "one_hot_max_size": 10, "max_ctr_complexity": 1, "counter_calc_method": "SkipTest",
    "nan_mode": "Min", "random_seed": 42, "allow_writing_files": False,
    "use_best_model": False, "verbose": False}


class QualityReportError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require(condition, code):
    if not condition:
        raise QualityReportError(code)


def digest(value):
    require(type(value) is str and SHA.fullmatch(value), "invalid_report_digest")
    return value


def number(value, *, nullable=False):
    if nullable and value is None:
        return None
    require(type(value) in (int, float), "invalid_report_number")
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise QualityReportError("invalid_report_number") from None
    require(math.isfinite(result), "nonfinite_report_number")
    return result


def integer(value, *, minimum=0):
    require(type(value) is int and minimum <= value <= 2_000_000, "invalid_report_count")
    return value


def plain(value, depth=0, nodes=None):
    if nodes is None:
        nodes = [0]
    nodes[0] += 1
    require(depth <= 32 and nodes[0] <= 200_000, "report_json_structure_limit")
    if value is None or type(value) in (str, bool):
        return
    if type(value) in (int, float):
        number(value)
        return
    require(type(value) in (dict, list), "invalid_report_json")
    if type(value) is dict:
        require(all(type(key) is str for key in value), "invalid_report_json")
        for item in value.values():
            plain(item, depth + 1, nodes)
    else:
        for item in value:
            plain(item, depth + 1, nodes)


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_report_json_key")
        result[key] = value
    return result


def rejected_constant(_):
    raise QualityReportError("nonfinite_report_number")


def read_report(path):
    """Read a regular, stable <=1MiB file and bind the aggregate to its SHA."""
    try:
        path = Path(path)
        before = path.lstat()
        require(stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode), "invalid_report_file")
        require(0 < before.st_size <= MAX_BYTES, "report_byte_limit")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            require((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino), "report_source_changed")
            raw = stream.read(MAX_BYTES + 1)
            after = os.fstat(stream.fileno())
        final = path.lstat()
        require(len(raw) == before.st_size and len(raw) <= MAX_BYTES, "report_byte_limit")
        require((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                == (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                and (final.st_dev, final.st_ino) == (before.st_dev, before.st_ino), "report_source_changed")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates, parse_constant=rejected_constant)
        plain(value)
        require(type(value) is dict, "invalid_report_json")
        return value, hashlib.sha256(raw).hexdigest()
    except QualityReportError:
        raise
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise QualityReportError("report_read_failed") from None


def current_source_map():
    names = ["solution.py", "requirements.txt", *sorted(path.name for path in ROOT.glob("aegml_*.py"))]
    result = {}
    for name in names:
        path = ROOT / name
        try:
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
                    and info.st_size <= MAX_BYTES, "invalid_current_source_file")
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            raise QualityReportError("current_source_unavailable") from None
    return result


def checked_evaluation(value, *, task_type, source, partition, rows):
    require(type(value) is dict and value.get("phase") == "inner_score_evaluation"
            and value.get("source_sha256") == source and value.get("partition_sha256") == partition
            and value.get("raw_inner_targets_returned") is False
            and value.get("outer_quality_evaluated") is False, "evaluation_scope_mismatch")
    metric, diagnostics = value["metric_report"], value["diagnostics"]
    name, direction, kind = (("rmse", "minimize", "numeric") if task_type == "regression"
                             else ("macro_f1", "maximize", "label"))
    require(metric.get("name") == name and metric.get("direction") == direction
            and metric.get("prediction_kind") == kind and type(metric.get("n_rows")) is int
            and metric["n_rows"] == rows
            and metric.get("adapter_version") == "metrics.v1" and metric.get("official_score") is None,
            "evaluation_metric_mismatch")
    score = number(metric["value"])
    require(score >= 0 and (task_type != "classification" or score <= 1), "invalid_metric_range")
    require(diagnostics.get("kind") == task_type and type(diagnostics.get("rows")) is int
            and diagnostics["rows"] == rows,
            "diagnostic_scope_mismatch")
    return score, diagnostics


def regression_observation(diagnostic):
    require(diagnostic.get("raw_residuals_or_targets_returned") is False
            and diagnostic.get("posthoc_error_slices_not_independent_quality") is True,
            "regression_diagnostic_scope_mismatch")
    quantiles = {key: number(diagnostic["absolute_error_quantiles"][key], nullable=True)
                 for key in ("p50", "p90", "p95", "p99")}
    bands = diagnostic["error_rank_bands"]
    require(type(bands) is list and [item.get("band") for item in bands]
            == ["best_50pct", "next_40pct", "worst_10pct"], "regression_rank_bands_missing")
    selected = []
    for item in bands:
        count = integer(item["rows"])
        share = number(item["sse_share"])
        require(0 <= share <= 1 + 1e-12, "invalid_rank_SSE_share")
        require(item.get("numeric_status") in {"finite", "empty_band", "partial_overflow_unavailable"},
                "invalid_rank_numeric_status")
        selected.append({"band": item["band"], "rows": count, "mae": number(item["mae"], nullable=True),
            "rmse": number(item["rmse"], nullable=True), "bias": number(item["bias"], nullable=True),
            "sse_share": share, "numeric_status": item["numeric_status"]})
    require(sum(item["rows"] for item in selected) == diagnostic["rows"], "rank_row_count_mismatch")
    total = math.fsum(item["sse_share"] for item in selected)
    require(math.isclose(total, 1, abs_tol=1e-10) or total == 0, "rank_SSE_share_total_mismatch")
    return {"mae": number(diagnostic["mae"]), "bias": number(diagnostic["bias"], nullable=True),
        "absolute_error_quantiles": quantiles,
        "maximum_absolute_error": number(diagnostic["maximum_absolute_error"], nullable=True),
        "rank_error_bands": selected, "worst_10pct_SSE_share": selected[-1]["sse_share"],
        "posthoc_diagnostics_not_independent_quality": True,
        "ranks_are_inner_error_feedback_not_training_weights": True}


def class_label(value):
    require(type(value) is str and bool(value.strip()) and len(value) <= 4096
            and "\x00" not in value, "invalid_aggregate_class_label")
    return value


def classification_observation(diagnostic):
    require(diagnostic.get("raw_row_targets_returned") is False
            and diagnostic.get("labels_policy") == "sklearn_labels_none"
            and diagnostic.get("average") == "macro", "classification_diagnostic_scope_mismatch")
    classes = diagnostic["per_class"]
    require(type(classes) is list and 0 < len(classes) <= 128, "invalid_aggregate_class_count")
    selected = []
    for item in classes:
        record = {"label": class_label(item["label"]),
                  **{key: integer(item[key]) for key in ("support", "TP", "FP", "FN")},
                  **{key: number(item[key]) for key in ("precision", "recall", "f1")}}
        require(record["support"] == record["TP"] + record["FN"], "class_support_mismatch")
        require(all(0 <= record[key] <= 1 for key in ("precision", "recall", "f1")), "class_rate_out_of_range")
        denominators = (record["TP"] + record["FP"], record["TP"] + record["FN"],
                        2 * record["TP"] + record["FP"] + record["FN"])
        expected_rates = [numerator / denominator if denominator else 0. for numerator, denominator in
            zip((record["TP"], record["TP"], 2 * record["TP"]), denominators)]
        require(all(math.isclose(record[key], expected, abs_tol=1e-12) for key, expected in
            zip(("precision", "recall", "f1"), expected_rates)), "class_rate_count_mismatch")
        selected.append(record)
    require(len({item["label"] for item in selected}) == len(selected), "duplicate_aggregate_class")
    confusion = diagnostic["confusion"]
    require(type(confusion) is list and len(confusion) <= 4096, "invalid_confusion_aggregate")
    pairs = [{"actual": class_label(item["actual"]), "predicted": class_label(item["predicted"]),
              "count": integer(item["count"], minimum=1)} for item in confusion]
    require(len({(item["actual"], item["predicted"]) for item in pairs}) == len(pairs), "duplicate_confusion_pair")
    total, omitted = integer(diagnostic["classes_total"], minimum=1), integer(diagnostic["classes_omitted"])
    require(total == len(selected) + omitted and diagnostic.get("classes_included") == len(selected),
            "class_aggregate_count_mismatch")
    require(type(diagnostic.get("confusion_complete")) is bool, "invalid_confusion_completeness")
    omitted_pairs = integer(diagnostic["unretained_pair_occurrences"])
    require(sum(item["count"] for item in pairs) + omitted_pairs == diagnostic["rows"]
            and diagnostic["confusion_complete"] == (omitted_pairs == 0), "confusion_row_count_mismatch")
    if omitted == 0:
        require(sum(item["support"] for item in selected) == diagnostic["rows"], "class_support_total_mismatch")
    return {"primary_metric": "MacroF1", "labels_policy": "sklearn_labels_none", "per_class": selected,
        "weak_classes_ranked_by_inner_F1_then_support": sorted(selected, key=lambda item:
            (item["f1"], item["support"], item["label"]))[:5],
        "classes_total": total, "classes_omitted": omitted,
        "confusion": pairs, "confusion_complete": diagnostic["confusion_complete"],
        "unretained_pair_occurrences": omitted_pairs,
        "weak_class_ranking_is_diagnostic_not_significance": True,
        "inner_support_must_not_set_training_weights_or_thresholds": True}


def validate_report(report, report_sha, current_sources, *, synthetic=False):
    require(report.get("schema_version") == "baseline_report.v1"
            and report.get("status") == "PASS_H04_FIXED_BASELINE_ONLY"
            and report.get("protocol") == "H04_FIXED_SEARCH_FIT_ONLY", "baseline_report_status_mismatch")
    require(report.get("synthetic_method_fixture", False) is synthetic, "synthetic_report_scope_mismatch")
    require(type(report.get("model_fit_calls")) is int and report["model_fit_calls"] == 1
            and type(report.get("constant_fit_calls")) is int and report["constant_fit_calls"] == 1
            and type(report.get("live_api_calls")) is int and report["live_api_calls"] == 0,
            "baseline_call_count_mismatch")
    access = report["phase_access"]
    require(access.get("estimator_labels") == "T_fit_only"
            and access.get("inner_labels") == "trusted_evaluator_only"
            and all(access.get(key) is False for key in ("outer_targets_retained_or_scored",
                "test_targets_available", "frozen_refit_performed", "os_worker_boundary_verified")),
            "baseline_phase_access_mismatch")
    require(report.get("official_baseline_value") is None and report.get("official_score") is None
            and report.get("autoresearch_performed") is False, "unverified_baseline_claim")
    sources = report["source_sha256"]
    require(type(sources) is dict and set(sources) == SOURCE_ROLES, "invalid_data_source_manifest")
    for value in sources.values():
        digest(value)
    code = report["source_code_sha256"]
    require(type(code) is dict and code == current_sources, "source_code_sha_mismatch")
    split, prep, audit = report["split"], report["preprocessing"], report["feature_model"]["audit"]
    partition = digest(split["partition_sha256"])
    require(split.get("source_sha256") == sources and split.get("train_sha256") == sources["train"],
            "split_source_binding_mismatch")
    counts = {key: integer(split["counts"][key], minimum=1) for key in ("fit", "inner", "outer")}
    require(sum(counts.values()) == split.get("train_rows") and split.get("seed") == 42,
            "split_count_or_seed_mismatch")
    require(prep.get("phase") == "search_fit" and prep.get("source_sha256") == sources["train"]
            and prep.get("split_sha256") == partition and prep.get("fit_rows") == counts["fit"],
            "preprocessing_phase_binding_mismatch")
    digest(prep["trained_statistics_sha256"])
    require(audit.get("estimator_fitted") is True and audit.get("eval_set_used") is False
            and audit.get("refit_performed") is False and audit.get("fit_scope") == "NO_REFIT_SEARCH_ONLY"
            and audit.get("source_sha256") == sources["train"] and audit.get("partition_sha256") == partition
            and audit.get("preprocessing_statistics_sha256") == prep["trained_statistics_sha256"],
            "estimator_binding_mismatch")
    parameters = audit["requested_parameters"]
    require(type(parameters) is dict and set(parameters) == PARAMETER_KEYS, "unknown_estimator_parameter")
    require(all(type(parameters[key]) is type(value) and parameters[key] == value
                for key, value in FIXED_PARAMETERS.items()), "fixed_estimator_config_mismatch")
    require(parameters.get("iterations") == 300 and type(parameters["iterations"]) is int
            and parameters.get("thread_count") == 8 and type(parameters["thread_count"]) is int
            and parameters.get("random_seed") == 42 and type(parameters["random_seed"]) is int
            and parameters.get("task_type") == "CPU" and parameters.get("use_best_model") is False
            and parameters.get("allow_writing_files") is False and audit.get("tree_count") == 300,
            "fixed_estimator_config_mismatch")
    task_type = report["task_type"]
    require(task_type in ("regression", "classification"), "unsupported_quality_task")
    require(report["constant"]["kind"] == ("fit_mean" if task_type == "regression" else "fit_majority"),
            "constant_kind_mismatch")
    expected_name = "rmse" if task_type == "regression" else "macro_f1"
    direction, prediction = (("minimize", "numeric") if task_type == "regression" else ("maximize", "label"))
    metric_contract = report["metric_contract"]
    require(metric_contract.get("name") == expected_name and metric_contract.get("direction") == direction
            and metric_contract.get("prediction_kind") == prediction
            and metric_contract.get("target_scale") == "original"
            and metric_contract.get("finite_policy") == "finite_only"
            and metric_contract.get("parameters") == ({"average": "macro", "labels": None}
                if task_type == "classification" else {}), "primary_metric_mismatch")
    require(parameters.get("loss_function") in ({"RMSE"} if task_type == "regression" else {"Logloss", "MultiClass"}),
            "estimator_loss_mismatch")
    versions = report["versions"]
    require(type(versions) is dict and set(versions) == VERSION_KEYS
            and all(type(value) is str and re.fullmatch(r"[A-Za-z0-9.+_-]{1,64}", value)
                    for value in versions.values()), "invalid_version_manifest")
    require(type(split.get("policy_id")) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", split["policy_id"])
            and split.get("strategy") in {"explicit", "temporal", "stratified"}, "invalid_split_summary")
    for key in ("recipe_sha256", "feature_order_sha256"):
        digest(prep[key])
    require(prep.get("categorical_strategy") in {"native", "onehot"}
            and prep.get("missing_policy") == "literal_empty_only", "invalid_preprocessing_summary")
    integer(prep["feature_count"], minimum=1)
    scores, diagnostics = {}, {}
    inner_mapping_sha = None
    for model in ("constant", "feature_model"):
        evaluation = report[model]["evaluation"]
        mapping = digest(evaluation["inner_row_indices_sha256"])
        require(inner_mapping_sha is None or mapping == inner_mapping_sha, "paired_inner_mapping_mismatch")
        inner_mapping_sha = mapping
        scores[model], raw = checked_evaluation(evaluation, task_type=task_type,
            source=sources["train"], partition=partition, rows=counts["inner"])
        diagnostics[model] = (regression_observation(raw) if task_type == "regression"
                              else classification_observation(raw))
        if task_type == "classification" and diagnostics[model]["classes_omitted"] == 0:
            macro = math.fsum(item["f1"] for item in diagnostics[model]["per_class"]) / raw["classes_total"]
            require(math.isclose(scores[model], macro, abs_tol=1e-12), "MacroF1_aggregate_mismatch")
    gain = scores["constant"] - scores["feature_model"] if task_type == "regression" else (
        scores["feature_model"] - scores["constant"])
    require(math.isclose(number(report["improvement_over_constant"]), gain, rel_tol=1e-12, abs_tol=1e-12),
            "reported_gain_mismatch")
    expected_selected = "feature_model" if gain > 1e-12 else report["constant"]["kind"]
    require(report.get("selected") == expected_selected and report.get("selection_tolerance") == 1e-12,
            "baseline_selection_mismatch")
    timer = {key: number(report["timer"][key]) for key in ("total_seconds", "reserve_seconds", "elapsed_seconds")}
    require(all(value >= 0 for value in timer.values()), "negative_timer")
    observation = {"task_type": task_type, "input_report_sha256": digest(report_sha),
        "data_source_sha256": sources, "partition_sha256": partition,
        "split": {"policy_id": split["policy_id"], "strategy": split["strategy"], "seed": 42, "counts": counts},
        "primary_metric": expected_name, "direction": "minimize" if task_type == "regression" else "maximize",
        "constant_metric": scores["constant"], "feature_model_metric": scores["feature_model"],
        "improvement_over_constant": gain, "feature_model_improves_constant": gain > 1e-12,
        "result_vs_constant": "improvement" if gain > 1e-12 else "degradation" if gain < -1e-12 else "no_measurable_change",
        "selected": expected_selected, "diagnostics": diagnostics,
        "preprocessing": {key: prep[key] for key in ("phase", "recipe_sha256", "trained_statistics_sha256",
            "feature_order_sha256", "feature_count", "categorical_strategy", "missing_policy")},
        "fixed_model_parameters": parameters, "timer": timer,
        "model_fit_seconds": number(audit["fit_seconds"]), "model_predict_seconds": number(audit["predict_seconds"]),
        "diagnostics_are_inner_feedback_not_independent_quality": True,
        "frozen_refit_performed": False, "official_baseline_value": None, "official_score": None}
    return observation


def hypotheses(observations):
    regression = observations["regression"]
    classification = observations["classification"]
    tail = regression["diagnostics"]["feature_model"]["worst_10pct_SSE_share"]
    weak = classification["diagnostics"]["feature_model"]["weak_classes_ranked_by_inner_F1_then_support"]
    common = {"status": "PREREGISTERED_NOT_IMPLEMENTED_NOT_TESTED", "candidate_fit_calls": 0,
        "control": "current fixed 300-tree feature model, same T_fit/inner membership and seed42",
        "comparison": "paired predictions on the same inner rows; same CPU8/wall-clock cap, preprocessing and 300 iterations",
        "test": "Freeze the single change before one candidate fit; report primary delta, runtime/RSS and negative results together.",
        "stop_rule": "One predeclared candidate per hypothesis. Stop on invalid output, budget overrun or missed MEI; no trial-pool expansion.",
        "inner_feedback_policy": "Aggregate feedback only; repeated comparisons can overfit inner. No independent-win claim.",
        "outer_and_test_labels": "Never available to candidate fitting, parameter choice, weights or thresholds.",
        "future_execution_gate": "H07 candidate configuration policy/version and owner-authorized stage; this builder performs no fit."}
    rows = []
    proposals = [
        ("HYP-R01", "regression", "depth: 6 -> 4; every other baseline setting unchanged",
         {"observation": "Posthoc worst-decile share of inner squared error", "value": tail},
         "Lower depth may reduce variance; concentrated errors do not prove variance is their cause."),
        ("HYP-R02", "regression", "learning_rate: 0.05 -> 0.03; still exactly 300 iterations",
         {"observation": "Inner signed bias and MAE", "bias": regression["diagnostics"]["feature_model"]["bias"],
          "mae": regression["diagnostics"]["feature_model"]["mae"]},
         "Smaller updates may regularize this recipe, but can underfit at the fixed iteration count."),
        ("HYP-C01", "classification", "class_weights: bounded inverse-sqrt T_fit frequencies instead of all ones",
         {"observation": "Lowest inner per-class F1/support aggregates", "classes": weak},
         "Reweighting may improve weak-class recall and may reduce precision; derive every weight from T_fit only."),
        ("HYP-C02", "classification", "depth: 6 -> 4; every other baseline setting unchanged",
         {"observation": "MacroF1 and aggregate confusion", "macro_f1": classification["feature_model_metric"],
          "confusion_complete": classification["diagnostics"]["feature_model"]["confusion_complete"]},
         "A smaller model may generalize better; confusion alone does not identify the cause of mistakes."),
    ]
    for identifier, task_type, change, rationale, uncertainty in proposals:
        reference = observations[task_type]["feature_model_metric"]
        row = {**common, "id": identifier, "task_type": task_type, "single_change": change,
            "observation_rationale": rationale, "uncertainty": uncertainty,
            "reference_feature_metric": reference,
            "minimum_effect": ({"metric": "rmse", "direction": "decrease", "relative": .005,
                "absolute_at_recorded_reference": reference * .005,
                "zero_reference_policy": "No lower finite nonnegative RMSE is possible; do not launch quality search."}
                if task_type == "regression" else {"metric": "macro_f1", "direction": "increase", "absolute": .003}),
            "success_rule": "Primary improvement must reach MEI within the equal budget; record secondary regressions and do not call this independent validation."}
        if identifier == "HYP-C01":
            row["T_fit_weight_recipe"] = "T_fit only: w_c=min(10,sqrt(max_fit_class_count/fit_class_count_c)); fixed mapping, no inner-support weights"
        rows.append(row)
    return rows


def build_summary(inputs, *, synthetic=False):
    require(type(inputs) is list and len(inputs) == 2, "exactly_two_baseline_reports_required")
    sources = current_source_map()
    observations = {}
    versions = None
    base_parameters = None
    for report, report_sha in inputs:
        observation = validate_report(report, report_sha, sources, synthetic=synthetic)
        task_type = observation["task_type"]
        require(task_type not in observations, "duplicate_quality_task")
        observations[task_type] = observation
        params = {key: value for key, value in observation["fixed_model_parameters"].items() if key != "loss_function"}
        if versions is None:
            versions, base_parameters = report["versions"], params
        else:
            require(report["versions"] == versions and params == base_parameters, "cross_task_config_or_version_mismatch")
    require(set(observations) == {"regression", "classification"}, "quality_task_pair_required")
    require(current_source_map() == sources, "source_code_changed_during_quality_report")
    result = {"schema_version": "h04_quality_report.v1",
        "status": "PASS_SYNTHETIC_QUALITY_METHOD_CHECK_ONLY" if synthetic else "PASS_H04_AGGREGATE_REPORT_ONLY",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "measurement_scope": "synthetic_method_fixtures_not_measured_quality" if synthetic else "two_source_bound_reported_actual_baseline_runs",
        "verification_scope": "Input report integrity, current source hashes and aggregate contracts; model fits are not independently repeated by this builder.",
        "source_code_sha256": sources, "versions": versions,
        "observations": observations, "preregistered_hypotheses": hypotheses(observations),
        "candidate_configuration_policy": "H04_FIXED_BASELINE_ONLY; future candidate changes wait for an explicit H07 version, no opaque trial pool",
        "comparison_protocol": {"splits": "same immutable T_fit/inner and independently closed outer",
            "budget": "same wall-clock/resource cap per task/control/candidate, preprocessing included",
            "seed": 42, "adaptive_inner_overfitting_risk": True,
            "outer_results_are_not_search_feedback": True, "frozen_refit_performed": False,
            "weights_thresholds_vocabulary_and_statistics_fit_from": "T_fit_only"},
        "official_baseline_value": None, "official_score": None,
        "new_training_calls": 0, "live_api_calls": 0, "outer_quality_evaluated": False,
        "full_agent_or_H05_verified": False, "future_improvement_claimed": False,
        "manual_project_target": {"date": "2026-10-21", "time": "18:00", "timezone": "Europe/Moscow",
            "kind": "manual work target; no automation, delivery/score guarantee or automatic submission"}}
    plain(result)
    return result


def publish_new(path, summary):
    """Atomic, owner-private no-clobber JSON admission on the same filesystem."""
    raw = (json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    require(len(raw) <= MAX_BYTES, "quality_report_output_limit")
    path = Path(path).absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    require(path.parent.resolve(strict=True) == path.parent, "quality_output_parent_symlink")
    require(not os.path.lexists(path), "quality_output_exists")
    temporary = path.parent / (".quality-tmp-" + uuid.uuid4().hex)
    linked = False
    warning = False
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        linked = True
        try:
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            warning = True
    except FileExistsError:
        raise QualityReportError("quality_output_exists") from None
    except OSError:
        if not linked:
            raise QualityReportError("quality_output_write_failed") from None
        warning = True
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            "directory_fsync_warning": warning}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        require(len(args.report) == 2, "exactly_two_baseline_reports_required")
        inputs = [read_report(path) for path in args.report]
        result = build_summary(inputs)
        require([read_report(path)[1] for path in args.report] == [item[1] for item in inputs],
                "report_source_changed")
        output = publish_new(args.output, result)
        print(json.dumps({"status": result["status"], "report_sha256": output["sha256"],
            "bytes": output["bytes"], "directory_fsync_warning": output["directory_fsync_warning"],
            "new_training_calls": 0, "live_api_calls": 0}, allow_nan=False))
        return 0
    except QualityReportError as exc:
        code = exc.code
    except (OSError, KeyError, TypeError, ValueError, RecursionError):
        code = "invalid_baseline_report_structure"
    print(json.dumps({"status": "FAIL_H04_QUALITY_REPORT", "code": code,
                      "new_training_calls": 0, "live_api_calls": 0}, allow_nan=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
