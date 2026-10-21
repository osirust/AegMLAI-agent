"""Trusted H04 search-phase data access and aggregate inner evaluation.

Fit labels and inner features are separate capabilities of trusted repository
code. The estimator never receives inner targets from this API. These Python
interfaces are not an OS isolation boundary; generated workers remain H05.
"""

from collections import Counter
from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from numbers import Integral, Real
import re


class TrainingDataError(Exception):
    """Only fixed codes escape; no target, identifier, path or raw traceback."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _tick(budget):
    if budget is None or not callable(getattr(budget, "require", None)):
        raise TrainingDataError("budget_required")
    budget.require()


def _indices(values):
    if (type(values) is not tuple or not 0 < len(values) <= 2_000_000
            or any(type(index) is not int or not 0 <= index < 2_000_000 for index in values)
            or len(set(values)) != len(values)):
        raise TrainingDataError("invalid_target_row_indices")
    return values


def _digest(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise TrainingDataError("invalid_target_provenance")
    return value


def _finite_value(value, code):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TrainingDataError(code)
    try:
        number = float(value)
    except (ValueError, OverflowError, TypeError):
        raise TrainingDataError(code) from None
    if not math.isfinite(number):
        raise TrainingDataError(code)
    return number


def _indices_sha(values):
    return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


def _class_targets(values):
    text = [isinstance(value, str) for value in values]
    if all(text):
        if any(not value.strip() or len(value) > 4096 for value in values):
            raise TrainingDataError("invalid_class_target")
        return values
    if any(text):
        raise TrainingDataError("mixed_class_target_types")
    normalized = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TrainingDataError("invalid_class_target")
        if isinstance(value, Integral):
            number = int(value)
            if number.bit_length() > 4096:
                raise TrainingDataError("invalid_class_target")
        else:
            number = _finite_value(value, "invalid_class_target")
        normalized.append(number)
    return tuple(normalized)


@dataclass(frozen=True)
class TargetBatch:
    values: tuple = field(repr=False)
    row_indices: tuple[int, ...] = field(repr=False)
    source_sha256: str
    partition_sha256: str
    phase: str = "search_fit_targets"
    task_type: str = "regression"

    def __post_init__(self):
        _indices(self.row_indices)
        _digest(self.source_sha256)
        _digest(self.partition_sha256)
        if (type(self.values) is not tuple or len(self.values) != len(self.row_indices)
                or self.row_indices != tuple(sorted(self.row_indices))
                or self.phase != "search_fit_targets"
                or self.task_type not in {"regression", "classification"}):
            raise TrainingDataError("invalid_fit_target_batch")
        if self.task_type == "regression":
            object.__setattr__(self, "values", tuple(_finite_value(value, "invalid_regression_target")
                                                     for value in self.values))
        else:
            object.__setattr__(self, "values", _class_targets(self.values))

    def audit(self):
        return {"phase": self.phase, "task_type": self.task_type, "rows": len(self.values),
                "source_sha256": self.source_sha256, "partition_sha256": self.partition_sha256,
                "row_indices_sha256": _indices_sha(self.row_indices),
                "raw_target_values_exposed": False, "os_boundary_verified": False}


@dataclass(frozen=True)
class PredictionBatch:
    values: tuple = field(repr=False)
    row_indices: tuple[int, ...] = field(repr=False)

    def __post_init__(self):
        _indices(self.row_indices)
        if type(self.values) is not tuple or len(self.values) != len(self.row_indices):
            raise TrainingDataError("invalid_prediction_batch")


@dataclass(frozen=True)
class TrainingDataLimits:
    max_target_chars: int = 4096
    max_retained_target_chars: int = 32 << 20
    max_feature_chars: int = 128 << 20
    max_feature_cells: int = 8_000_000
    max_diagnostic_classes: int = 128
    max_confusion_pairs: int = 4096
    max_diagnostic_bytes: int = 256 << 10

    def __post_init__(self):
        maximum = {"max_target_chars": 4096, "max_retained_target_chars": 32 << 20,
                   "max_feature_chars": 128 << 20, "max_feature_cells": 8_000_000,
                   "max_diagnostic_classes": 128, "max_confusion_pairs": 4096,
                   "max_diagnostic_bytes": 256 << 10}
        if any(type(value) is not int or not 0 < value <= maximum[name]
               for name, value in asdict(self).items()):
            raise TrainingDataError("invalid_training_data_limits")


def _bound(bundle, contract, plan, budget, schema=None):
    _tick(budget)
    import aegml_preprocessing as P

    try:
        payload = contract.to_dict()
        if schema is None:
            # P._bound_sources only needs a names/roles projection here. These
            # categorical placeholders never inspect or transform feature X.
            features = tuple(payload["feature_columns"])
            schema = P.FeatureSchema(features, categorical_columns=features,
                                     forbidden_columns=tuple(payload["target_columns"] + payload["id_columns"]))
        payload, root, paths, snapshots = P._bound_sources(bundle, contract, schema, budget)
        if payload["output_path"] != str(root / "submission.csv"):
            raise TrainingDataError("training_task_path_mismatch")
        P._validated_plan(plan, bundle.source_sha256["train"],
                          payload["provenance"]["row_mapping"]["row_counts"]["train"])
        P._verify_active_split_policy(payload, plan, budget)
        if plan.source_sha256 != bundle.source_sha256:
            raise TrainingDataError("training_split_source_mismatch")
        if ((payload["task_type"], payload["metric"]["name"]) not in
                {("regression", "rmse"), ("classification", "macro_f1")}):
            raise TrainingDataError("unsupported_h04_metric")
        _tick(budget)
        return payload, root, paths, snapshots
    except P.PreprocessingError as exc:
        raise TrainingDataError(exc.code) from None
    except (KeyError, AttributeError, TypeError):
        raise TrainingDataError("invalid_training_data_binding") from None


def _read_selected(bundle, payload, plan, indices, root, paths, snapshots, budget, limits,
                   *, features=None):
    from aegml_input import InputError, MAX_CSV_BYTES, _csv_reader, _unchanged

    _tick(budget)
    if not isinstance(limits, TrainingDataLimits):
        raise TrainingDataError("invalid_training_data_limits")
    if features is not None and len(indices) * len(features) > limits.max_feature_cells:
        raise TrainingDataError("training_feature_cell_limit")
    selected, retained_chars, pointer, count = [], 0, 0, 0
    try:
        with _csv_reader(paths["train"], root, "train", MAX_CSV_BYTES, budget,
                         expected_sha=bundle.source_sha256["train"]) as (reader, header):
            if header != bundle.headers["train"]:
                raise TrainingDataError("training_header_mismatch")
            if features is None:
                if len(payload["target_columns"]) != 1 or payload["target_columns"][0] not in header:
                    raise TrainingDataError("training_target_missing")
                positions = (header.index(payload["target_columns"][0]),)
            else:
                if tuple(features) != tuple(payload["feature_columns"]) or not set(features).issubset(header):
                    raise TrainingDataError("training_features_mismatch")
                positions = tuple(header.index(name) for name in features)
            for index, row in enumerate(reader):
                if index % 256 == 0:
                    _tick(budget)
                count += 1
                if count > plan.train_rows or len(row) != len(header):
                    raise TrainingDataError("training_csv_shape_mismatch")
                if pointer >= len(indices) or index != indices[pointer]:
                    continue  # No nonselected X/y cell is interpreted or retained.
                if features is not None:
                    value = [row[position] for position in positions]
                    retained_chars += sum(map(len, value))
                    if retained_chars > limits.max_feature_chars:
                        raise TrainingDataError("training_feature_character_limit")
                else:
                    raw = row[positions[0]]
                    if not raw.strip() or len(raw) > limits.max_target_chars:
                        raise TrainingDataError("invalid_selected_target")
                    retained_chars += len(raw)
                    if retained_chars > limits.max_retained_target_chars:
                        raise TrainingDataError("training_target_character_limit")
                    if payload["task_type"] == "classification":
                        value = raw  # Literal NA/null/001 remain distinct labels.
                    else:
                        try:
                            value = float(raw)
                        except (ValueError, OverflowError):
                            raise TrainingDataError("invalid_regression_target") from None
                        if not math.isfinite(value):
                            raise TrainingDataError("nonfinite_regression_target")
                selected.append(value)
                pointer += 1
        if count != plan.train_rows or pointer != len(indices):
            raise TrainingDataError("training_row_count_mismatch")
        for role, snapshot in snapshots.items():
            _tick(budget)
            _unchanged(paths[role], root, role, snapshot)
    except InputError as exc:
        raise TrainingDataError(exc.code) from None
    _tick(budget)
    return selected


def load_fit_targets(bundle, contract, plan, *, budget, limits=TrainingDataLimits()):
    """Return only T_fit y, source/active-partition bound, never inner/outer y."""
    payload, root, paths, snapshots = _bound(bundle, contract, plan, budget)
    values = _read_selected(bundle, payload, plan, plan.fit_indices, root, paths, snapshots,
                            budget, limits)
    batch = TargetBatch(tuple(values), plan.fit_indices, plan.train_sha256,
                        plan.partition_sha256, task_type=payload["task_type"])
    _tick(budget)
    return batch


def load_inner_features(bundle, contract, plan, *, schema, budget, limits=TrainingDataLimits()):
    """Return lexical inner X only, in canonical source-row order; never fit it."""
    payload, root, paths, snapshots = _bound(bundle, contract, plan, budget, schema)
    values = _read_selected(bundle, payload, plan, plan.inner_indices, root, paths, snapshots,
                            budget, limits, features=schema.feature_columns)
    _tick(budget)
    import pandas as pd

    frame = pd.DataFrame(values, columns=list(schema.feature_columns), index=list(plan.inner_indices))
    _tick(budget)
    return frame


def _encode(value, budget, maximum):
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    chunks, size = [], 0
    for index, chunk in enumerate(encoder.iterencode(value)):
        if index % 128 == 0:
            _tick(budget)
        size += len(chunk.encode("utf-8"))
        if size > maximum:
            raise TrainingDataError("inner_diagnostic_output_limit")
        chunks.append(chunk)
    _tick(budget)
    return "".join(chunks)


@dataclass(frozen=True)
class InnerEvaluation:
    _payload_json: str = field(repr=False)
    source_sha256: str
    partition_sha256: str
    phase: str = "inner_score_evaluation"

    @property
    def metric_report(self):
        return json.loads(self._payload_json)["metric_report"]

    @property
    def diagnostics(self):
        return json.loads(self._payload_json)["diagnostics"]

    def to_dict(self):
        return {**json.loads(self._payload_json), "source_sha256": self.source_sha256,
                "partition_sha256": self.partition_sha256, "phase": self.phase,
                "raw_inner_targets_returned": False, "outer_quality_evaluated": False,
                "os_boundary_verified": False}


def _finite_result(value):
    return value if math.isfinite(value) else None


def _rank_error_bands(normalized_errors, scale, budget):
    """Posthoc inner-error ranks only: no feature cuts or independent quality.

    The worst ceil(10% * n) observations are always retained as the tail;
    best floor(50% * n) observations form the first band, with the remainder
    in the middle. Stable sorting resolves equal errors by source-row order.
    """
    _tick(budget)
    ordered = sorted(normalized_errors, key=abs)
    total_squared = math.fsum(value * value for value in ordered)
    first_end = len(ordered) // 2
    second_end = len(ordered) - max(1, math.ceil(len(ordered) / 10))
    bands = []
    for name, start, stop in (("best_50pct", 0, first_end),
                             ("next_40pct", first_end, second_end),
                             ("worst_10pct", second_end, len(ordered))):
        _tick(budget)
        part = ordered[start:stop]
        squared, absolute, signed = [], [], []
        for index, value in enumerate(part):
            if index % 256 == 0:
                _tick(budget)
            squared.append(value * value)
            absolute.append(abs(value))
            signed.append(value)
        sse = math.fsum(squared)
        count = len(part)
        mae = _finite_result(scale * (math.fsum(absolute) / count)) if count else None
        rmse = _finite_result(scale * math.sqrt(sse / count)) if count else None
        bias = _finite_result(scale * (math.fsum(signed) / count)) if count else None
        bands.append({"band": name, "rows": count, "mae": mae, "rmse": rmse, "bias": bias,
            "sse_share": sse / total_squared if total_squared else 0.0,
            "numeric_status": ("empty_band" if not count else "finite" if
                all(value is not None for value in (mae, rmse, bias)) else "partial_overflow_unavailable")})
    _tick(budget)
    return bands


def _regression_diagnostics(truth, predictions, metric, budget):
    import aegml_metrics as M

    errors, scale, unrepresentable = [], 0.0, 0
    for index, (actual, predicted) in enumerate(zip(truth, predictions)):
        if index % 256 == 0:
            _tick(budget)
        error = predicted - actual
        if math.isfinite(error):
            errors.append(error)
            scale = max(scale, abs(error))
        else:
            errors.append((actual, predicted))
            scale = max(scale, abs(actual), abs(predicted))
            unrepresentable += 1
    if scale:
        normalized = [value[1] / scale - value[0] / scale if isinstance(value, tuple)
                      else value / scale for value in errors]
    else:
        normalized = [0.0] * len(errors)
    ordered = sorted(map(abs, normalized))

    def quantile(probability):
        position = (len(ordered) - 1) * probability
        low, high = math.floor(position), math.ceil(position)
        fraction = position - low
        normalized_value = ordered[low] * (1 - fraction) + ordered[high] * fraction
        return _finite_result(scale * normalized_value)

    mae_contract = {**metric, "name": "mae", "direction": "minimize", "prediction_kind": "numeric",
                    "parameters": {}}
    mae = M.evaluate_metric(mae_contract, truth, predictions, budget=budget).value
    bias = _finite_result(scale * (math.fsum(normalized) / len(normalized)))
    quantiles = {"p50": quantile(0.5), "p90": quantile(0.9),
                 "p95": quantile(0.95), "p99": quantile(0.99)}
    maximum = quantile(1.0)
    bands = _rank_error_bands(normalized, scale, budget)
    _tick(budget)
    return {"kind": "regression", "rows": len(truth), "error_definition": "prediction_minus_target",
            "mae": mae, "bias": bias, "absolute_error_quantiles": quantiles,
            "maximum_absolute_error": maximum,
            "nonrepresentable_individual_residuals": unrepresentable,
            "numeric_status": "finite" if all(value is not None for value in
                [bias, maximum, *quantiles.values()]) else "partial_overflow_unavailable",
            "quantile_method": "linear_interpolation_of_sorted_absolute_residuals",
            "error_rank_bands": bands,
            "error_rank_band_policy": "best_floor_50pct_middle_remainder_worst_ceil_10pct_stable_source_order_ties",
            "sse_share_zero_total_policy": "zero_when_all_errors_zero",
            "posthoc_error_slices_not_independent_quality": True,
            "rank_slices_use": "inner_diagnostics_only_no_HPO_or_independent_quality_claim",
            "raw_residuals_or_targets_returned": False}


def _classification_diagnostics(truth, predictions, budget, limits):
    actual, predicted, tp = Counter(truth), Counter(predictions), Counter()
    confusion, omitted = {}, 0
    for index, (label, prediction) in enumerate(zip(truth, predictions)):
        if index % 256 == 0:
            _tick(budget)
        if label == prediction:
            tp[label] += 1
        pair = (label, prediction)
        if pair in confusion:
            confusion[pair] += 1
        elif len(confusion) < limits.max_confusion_pairs:
            confusion[pair] = 1
        else:
            omitted += 1
    labels = sorted(set(actual) | set(predicted))
    per_class = []
    for label in labels[:limits.max_diagnostic_classes]:
        true_positive = tp[label]
        false_positive = predicted[label] - true_positive
        false_negative = actual[label] - true_positive
        precision = true_positive / predicted[label] if predicted[label] else 0.0
        recall = true_positive / actual[label] if actual[label] else 0.0
        denominator = 2 * true_positive + false_positive + false_negative
        per_class.append({"label": label, "support": actual[label], "TP": true_positive,
                          "FP": false_positive, "FN": false_negative, "precision": precision,
                          "recall": recall, "f1": 2 * true_positive / denominator if denominator else 0.0})
    return {"kind": "classification", "rows": len(truth), "average": "macro", "labels_policy": "sklearn_labels_none",
            "classes_total": len(labels), "classes_included": len(per_class),
            "classes_omitted": len(labels) - len(per_class), "class_selection": "lexical_prefix",
            "per_class": per_class,
            "confusion": [{"actual": pair[0], "predicted": pair[1], "count": count}
                          for pair, count in sorted(confusion.items())],
            "confusion_scope": "all_pairs" if omitted == 0 else "retained_first_seen_pairs_only",
            "confusion_complete": omitted == 0, "unretained_pair_occurrences": omitted,
            "raw_row_targets_returned": False}


def evaluate_inner_predictions(bundle, contract, plan, predictions, *, budget,
                               allowed_labels=None, limits=TrainingDataLimits()):
    """Score canonical inner predictions; inner y never leaves this evaluator.

    Returned diagnostics are aggregate feedback. They do not establish an OS
    boundary or immunity to adaptive overfitting on the inner control.
    """
    _tick(budget)
    if not isinstance(limits, TrainingDataLimits):
        raise TrainingDataError("invalid_training_data_limits")
    import aegml_metrics as M

    payload, root, paths, snapshots = _bound(bundle, contract, plan, budget)
    if (not isinstance(predictions, PredictionBatch)
            or predictions.row_indices != plan.inner_indices):
        raise TrainingDataError("inner_prediction_row_order_mismatch")
    if payload["task_type"] == "regression":
        predicted = tuple(_finite_value(value, "invalid_numeric_prediction") for value in predictions.values)
    else:
        if any(not isinstance(value, str) or not value.strip() or len(value) > limits.max_target_chars
               for value in predictions.values):
            raise TrainingDataError("invalid_class_prediction")
        predicted = predictions.values
    truth = _read_selected(bundle, payload, plan, plan.inner_indices, root, paths, snapshots,
                           budget, limits)
    try:
        result = M.evaluate_metric(payload["metric"], truth, predicted, allowed_labels=allowed_labels, budget=budget)
        diagnostics = (_regression_diagnostics(truth, predicted, payload["metric"], budget)
                       if payload["task_type"] == "regression" else
                       _classification_diagnostics(truth, predicted, budget, limits))
    except M.MetricError as exc:
        raise TrainingDataError(exc.code) from None
    report = {"metric_report": result.to_dict(), "diagnostics": diagnostics,
              "inner_row_indices_sha256": _indices_sha(plan.inner_indices),
              "diagnostics_scope": "aggregate_inner_only"}
    encoded = _encode(report, budget, limits.max_diagnostic_bytes)
    _tick(budget)
    return InnerEvaluation(encoded, plan.train_sha256, plan.partition_sha256)
