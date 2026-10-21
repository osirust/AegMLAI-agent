"""H04 trusted CPU baseline; no provider calls or generated-code execution."""

from collections import Counter
from dataclasses import asdict
import hashlib
import math
from pathlib import Path
import random
import re
import time


class BaselineError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _source_identity():
    root = Path(__file__).resolve().parent
    names = ["solution.py", "requirements.txt", *sorted(p.name for p in root.glob("aegml_*.py"))]
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}


def _feature_schema(bundle, contract):
    from aegml_preprocessing import schema_from_kinds
    rows = {row["feature"]: row for row in bundle.dictionary_rows}
    mapping = {"numeric": "numeric", "binary": "numeric", "category": "categorical", "text": "text"}
    kinds = {}
    for column in contract.to_dict()["feature_columns"]:
        if column not in rows or rows[column]["dtype"] not in mapping:
            raise BaselineError("explicit_dictionary_kind_required")
        kinds[column] = mapping[rows[column]["dtype"]]
    return schema_from_kinds(contract, kinds)


def _temporal_column(bundle, payload):
    """Read declared roles, never a dataset/target name or numeric correlation."""
    from aegml_contracts import _directive
    columns = payload["feature_columns"]
    candidates = set()
    for value, _ in _directive(bundle.task_text, r"time\s*column|temporal\s*column|столбец\s+времени"):
        match = re.fullmatch(r"`?([^`\s]+)`?", value.strip())
        if match is None or match[1] not in columns:
            raise BaselineError("unsupported_temporal_declaration")
        candidates.add(match[1])
    for line in bundle.task_text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 3:
            name = cells[0].strip("` ")
            if re.search(r"код\s+периода|observation\s+period|temporal\s+(?:index|feature)", cells[1], re.I):
                if name not in columns:
                    raise BaselineError("unsupported_temporal_declaration")
                candidates.add(name)
    if len(candidates) > 1:
        raise BaselineError("ambiguous_temporal_declaration")
    if candidates:
        return next(iter(candidates))
    if re.search(r"time[- ]series|временн\w+\s+(?:ряд|разбиен)|temporal\s+split", bundle.task_text, re.I):
        raise BaselineError("temporal_column_not_resolved")
    return None


def build_baseline_split(bundle, contract, *, budget, seed=42):
    import aegml_validation as V
    from aegml_input import MAX_CSV_BYTES, _csv_reader
    payload = contract.to_dict()
    if payload["task_type"] == "classification":
        return V.build_split_plan(bundle, contract, strategy="stratified", budget=budget, seed=seed)
    column = _temporal_column(bundle, payload)
    if column is not None:
        periods = set()
        with _csv_reader(bundle.files["train"], bundle.task_path.parent, "train", MAX_CSV_BYTES,
                         budget, expected_sha=bundle.source_sha256["train"]) as (reader, header):
            position = header.index(column)
            for index, row in enumerate(reader):
                if index % 256 == 0:
                    budget.require()
                if len(row) != len(header):
                    raise BaselineError("temporal_csv_width")
                try:
                    value = float(row[position])
                except (TypeError, ValueError, OverflowError):
                    raise BaselineError("invalid_temporal_value") from None
                if not math.isfinite(value):
                    raise BaselineError("invalid_temporal_value")
                periods.add(value)
                if len(periods) > 64:
                    raise BaselineError("too_many_baseline_periods")
        ordered = sorted(periods)
        if len(ordered) < 3:
            raise BaselineError("insufficient_temporal_periods")
        return V.build_split_plan(bundle, contract, strategy="temporal", budget=budget, seed=seed,
                                  time_column=column, fit_periods=tuple(ordered[:-2]),
                                  inner_periods=(ordered[-2],), outer_periods=(ordered[-1],))
    # No temporal declaration: explicit, recorded IID policy, never silently
    # substituted for an unresolved declared time split.
    _, schema_sha = V._metadata(bundle, contract)
    n = payload["provenance"]["row_mapping"]["row_counts"]["train"]
    if n < 5:
        raise BaselineError("insufficient_iid_regression_rows")
    order = list(range(n))
    random.Random(seed).shuffle(order)
    outer_n = math.ceil(n * .2)
    inner_n = math.ceil((n - outer_n) * .2)
    plan = V.SplitPlan(tuple(order[outer_n + inner_n:]), tuple(order[outer_n:outer_n + inner_n]),
                       tuple(order[:outer_n]), n, bundle.source_sha256["train"], "iid_nested_regression_v1",
                       seed, "explicit", schema_sha, tuple(bundle.source_sha256.items()))
    V.verify_split_source(plan, bundle, budget=budget)
    return plan


def _constant(targets):
    if targets.task_type == "regression":
        value = math.fsum(v / len(targets.values) for v in targets.values)
        if not math.isfinite(value):
            raise BaselineError("nonfinite_constant_mean")
        return "fit_mean", value
    counts = Counter(targets.values)
    return "fit_majority", min(counts, key=lambda value: (-counts[value], value))


def _versions():
    from importlib.metadata import version
    import platform
    return {"python": platform.python_version(), **{name: version(name) for name in
            ("numpy", "pandas", "scipy", "scikit-learn", "catboost")}}


def run_baseline(config, *, estimator_config=None, progress=None):
    """Run one fixed search-fit baseline and preserve a valid early output.

    Both constant and feature model use T_fit only. Inner is independently
    scored, outer is not scored/refitted, and test labels do not exist here.
    """
    import aegml_artifacts as A
    import aegml_contracts as C
    import aegml_estimators as E
    import aegml_input as I
    import aegml_preprocessing as P
    import aegml_profile as F
    import aegml_submission as S
    import aegml_training_data as T

    budget = config.budget
    if progress is not None and (type(progress) is not dict or progress):
        raise BaselineError("fresh_progress_container_required")
    def note(**fields):
        if progress is not None:
            progress.update(fields)
    budget.require()
    sources = _source_identity()
    contract = C.build_task_contract(config.task_path, budget=budget, threads=config.threads,
                                     time_limit_seconds=budget.total_seconds)
    note(contract_valid=True, progress_phase="contract_built")
    bundle = I.discover_inputs(config.task_path, budget)
    payload = contract.to_dict()
    if payload["metric"]["name"] not in {"rmse", "macro_f1"}:
        raise BaselineError("baseline_metric_not_yet_supported")
    plan = build_baseline_split(bundle, contract, budget=budget)
    contract = C.attach_split_plan(contract, plan, budget=budget)
    schema = _feature_schema(bundle, contract)
    artifacts = A.create_run_artifacts(config.task_path, run_id=payload["run_id"], budget=budget)
    artifacts.write_json("task-contract.json", contract.to_dict())
    artifacts.write_json("split.json", plan.to_dict())
    # Metadata is capped independently of dataset size. Full memberships are
    # private, bounded data-only CSVs, not a huge JSON array or target values.
    for phase, indices in (("fit", plan.fit_indices), ("inner", plan.inner_indices), ("outer", plan.outer_indices)):
        artifacts.write_predictions(phase + "-membership.csv", (phase,) * len(indices), indices)
    model_config = E.EstimatorConfig(threads=config.threads) if estimator_config is None else estimator_config
    if model_config.threads != config.threads:
        raise BaselineError("estimator_thread_config_mismatch")
    artifacts.write_json("config.json", {"estimator": asdict(model_config), "source_code_sha256": sources,
                                        "protocol": "H04_FIXED_SEARCH_FIT_ONLY", "test_refit_performed": False})
    targets = T.load_fit_targets(bundle, contract, plan, budget=budget)
    allowed = tuple(sorted(set(targets.values))) if targets.task_type == "classification" else None
    constant_name, constant_value = _constant(targets)
    n_test = payload["provenance"]["row_mapping"]["row_counts"]["test"]
    constant_inner = T.PredictionBatch((constant_value,) * len(plan.inner_indices), plan.inner_indices)
    constant_test = T.PredictionBatch((constant_value,) * n_test, tuple(range(n_test)))
    constant_eval = T.evaluate_inner_predictions(bundle, contract, plan, constant_inner,
                                                  budget=budget, allowed_labels=allowed)
    submission_schema = S.build_submission_schema(bundle, contract, budget=budget, allowed_labels=allowed)
    early_submission = S.write_submission(constant_test.values, submission_schema, budget=budget)
    note(submission_valid=True, submission_sha256=early_submission["sha256"],
         submission_rows=early_submission["row_count"], progress_phase="early_constant_published")
    artifacts.write_predictions("constant-inner.csv", constant_inner.values, constant_inner.row_indices)
    artifacts.write_predictions("constant-test.csv", constant_test.values, constant_test.row_indices)
    artifacts.write_json("early-output.json", {"constant_kind": constant_name, "evaluation": constant_eval.to_dict(),
                                               "submission": early_submission, "timer": budget.snapshot()})

    scope = F.ProfileScope(plan.fit_indices, plan.protected_indices, plan.train_rows, plan.train_sha256, plan.policy_id)
    profile = F.profile_task(bundle, contract, scope, budget=budget)
    artifacts.write_json("profile.json", profile)
    recipe = P.PreprocessingRecipe(categorical_strategy="onehot" if schema.text_columns else "native")
    fit_view = P.load_train_fit_view(bundle, contract, plan, schema=schema, budget=budget)
    fitted, prepared_fit = E.prepare_fit_matrix(fit_view, recipe, budget=budget)
    inner_X = T.load_inner_features(bundle, contract, plan, schema=schema, budget=budget)
    prepared_inner = fitted.transform(inner_X, budget=budget)
    del inner_X
    test_X = P.load_test_features(bundle, contract, schema=schema, budget=budget)
    prepared_test = fitted.transform(test_X, budget=budget)
    del test_X, fit_view
    preprocess_audit = fitted.audit()
    artifacts.write_json("preprocessing.json", preprocess_audit)
    budget.require()
    model = E.fit_estimator(prepared_fit, targets, task_type=payload["task_type"], config=model_config,
                            budget=budget, fit_audit=preprocess_audit)
    note(feature_model_fitted=True, progress_phase="feature_model_fitted")
    inner_predictions = model.predict(prepared_inner, budget=budget)
    candidate_eval = T.evaluate_inner_predictions(bundle, contract, plan, inner_predictions,
                                                  budget=budget, allowed_labels=allowed)
    test_predictions = model.predict(prepared_test, budget=budget)
    if test_predictions.row_indices != tuple(range(n_test)):
        raise BaselineError("model_test_row_alignment")
    artifacts.write_predictions("model-inner.csv", inner_predictions.values, inner_predictions.row_indices)
    artifacts.write_predictions("model-test.csv", test_predictions.values, test_predictions.row_indices)
    candidate_metric = candidate_eval.metric_report["value"]
    constant_metric = constant_eval.metric_report["value"]
    gain = (constant_metric - candidate_metric if payload["metric"]["direction"] == "minimize"
            else candidate_metric - constant_metric)
    selected = "feature_model" if gain > 1e-12 else constant_name
    if _source_identity() != sources:
        raise BaselineError("source_code_changed_during_baseline")
    final_submission = (S.write_submission(test_predictions.values, submission_schema, budget=budget)
                        if selected == "feature_model" else early_submission)
    # The writer has already validated and committed this exact snapshot.
    # Diagnostics/another validation may still fail; never retain the SHA of a
    # replaced constant file as the current published version.
    note(submission_valid=True, submission_sha256=final_submission["sha256"],
         submission_rows=final_submission["row_count"], progress_phase="selected_output_committed")
    independently = S.validate_submission(config.output_path, submission_schema, budget=budget,
                                           expected_sha256=final_submission["sha256"], finalizing=True)
    note(submission_valid=True, submission_sha256=independently["sha256"],
         submission_rows=independently["row_count"], progress_phase="final_output_validated")
    importance = model.feature_importance(budget=budget)
    report = {
        "schema_version": "baseline_report.v1", "status": "PASS_H04_FIXED_BASELINE_ONLY",
        "protocol": "H04_FIXED_SEARCH_FIT_ONLY", "task_type": payload["task_type"],
        "metric_contract": payload["metric"], "constant": {"kind": constant_name, "evaluation": constant_eval.to_dict()},
        "feature_model": {"evaluation": candidate_eval.to_dict(), "audit": model.audit(),
                          "feature_importance": importance},
        "improvement_over_constant": gain, "selected": selected, "selection_tolerance": 1e-12,
        "preprocessing": preprocess_audit, "split": plan.to_dict(), "source_sha256": bundle.source_sha256,
        "source_code_sha256": sources, "feature_schema": asdict(schema), "versions": _versions(),
        "submission": independently, "early_submission": early_submission,
        "phase_access": {"estimator_labels": "T_fit_only", "inner_labels": "trusted_evaluator_only",
                         "outer_targets_retained_or_scored": False, "test_targets_available": False,
                         "frozen_refit_performed": False, "os_worker_boundary_verified": False},
        "timer": budget.snapshot(), "model_fit_calls": 1, "constant_fit_calls": 1,
        "live_api_calls": 0, "official_baseline_value": None, "official_score": None,
        "official_image_verified": False, "autoresearch_performed": False,
        "resource_scope": "process cumulative RSS; shared monotonic budget; CPU thread settings are not H05 enforcement",
    }
    artifacts.write_json("baseline-report.json", report)
    manifest = artifacts.manifest()
    manifest_record = artifacts.write_json("manifest.json", manifest)
    note(progress_phase="baseline_completed")
    return {"report": report, "artifact_root": artifacts.rootpath,
            "manifest": manifest, "manifest_record": manifest_record}
