"""Trusted numerical metric adapters, H03.3/H03.5; no model/code execution.

Inputs must already be aligned data-only predictions. Row/ID/CSV validation and
OS isolation belong to their own layers. No metric formula from task text is
evaluated. Labels are never inferred from public target/column names.
log_loss uses explicit column order and float64 epsilon clipping, matching the
numerical policy of scikit-learn 1.5.2 on valid normalized float64 probabilities:
https://github.com/scikit-learn/scikit-learn/blob/1.5.2/sklearn/metrics/_classification.py
"""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
import math
from numbers import Integral, Real
import sys
from types import MappingProxyType


ADAPTER_VERSION = "metrics.v1"
MAX_METRIC_ROWS = 2_000_000
MAX_CLASSES = 4096
PROBABILITY_SUM_ATOL = 1e-6
FLOAT64_EPSILON = sys.float_info.epsilon
PUBLIC_DIAGNOSTIC_LABELS = ("Normal", "Generic", "Exploits", "Fuzzers", "DoS",
                            "Reconnaissance", "Analysis", "Backdoor", "Shellcode", "Worms")


class MetricError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class UndefinedMetric(MetricError):
    pass


def _require(condition, code):
    if not condition:
        raise MetricError(code)


def _tick(budget):
    if budget is not None:
        budget.require()


@dataclass(frozen=True)
class MetricSpec:
    name: str
    task_type: str
    direction: str
    prediction_kind: str


METRIC_REGISTRY = MappingProxyType({
    name: MetricSpec(name, family, direction, kind)
    for name, family, direction, kind in (
        ("rmse", "regression", "minimize", "numeric"),
        ("mae", "regression", "minimize", "numeric"),
        ("accuracy", "classification", "maximize", "label"),
        ("macro_f1", "classification", "maximize", "label"),
        ("weighted_f1", "classification", "maximize", "label"),
        ("binary_f1", "classification", "maximize", "label"),
        ("log_loss", "classification", "minimize", "probability"),
        ("roc_auc", "classification", "maximize", "probability"),
    )
})


def metric_spec(name):
    if not isinstance(name, str) or name not in METRIC_REGISTRY:
        raise MetricError("unsupported_metric")
    return METRIC_REGISTRY[name]


@dataclass(frozen=True)
class MetricResult:
    name: str
    value: float
    direction: str
    prediction_kind: str
    n_rows: int
    warnings: tuple[str, ...] = ()

    def to_dict(self):
        return {"name": self.name, "value": self.value, "direction": self.direction,
                "prediction_kind": self.prediction_kind, "n_rows": self.n_rows,
                "adapter_version": ADAPTER_VERSION, "warnings": list(self.warnings),
                "official_score": None,
                "probability_policy": {"row_sum_atol": PROBABILITY_SUM_ATOL,
                    "normalization": "none", "arithmetic_dtype": "float64",
                    "log_loss_clip_epsilon": FLOAT64_EPSILON} if self.prediction_kind == "probability" else None}


def _vector(values, code="invalid_metric_vector"):
    _require(not isinstance(values, (str, bytes, Mapping)), code)
    try:
        length = len(values)
    except (TypeError, OverflowError):
        raise MetricError(code) from None
    _require(type(length) is int and 0 < length <= MAX_METRIC_ROWS, code)
    return list(values)


def _number(value):
    _require(not isinstance(value, bool) and isinstance(value, Real), "invalid_numeric_value")
    try:
        converted = float(value)
    except (ValueError, OverflowError, TypeError):
        raise MetricError("invalid_numeric_value") from None
    _require(math.isfinite(converted), "nonfinite_metric_input")
    return converted


def _label(value):
    if isinstance(value, str):
        _require(bool(value.strip()) and len(value) <= 4096, "invalid_class_label")
        return value
    if not isinstance(value, bool) and isinstance(value, Integral):
        result = int(value)
        _require(result.bit_length() <= 4096, "invalid_class_label")
        return result
    if not isinstance(value, bool) and isinstance(value, Real):
        # Explicit classification semantics come from MetricContract. Finite
        # fractional codes can be class labels; numeric dtype alone is not a
        # reason to reinterpret them as regression or probability predictions.
        return _number(value)
    raise MetricError("invalid_class_label")


def _labels(values):
    result = [_label(value) for value in _vector(values)]
    _require(len({isinstance(value, str) for value in result}) == 1, "mixed_label_types")
    return result


def _label_order(values, *, minimum=1):
    result = tuple(_labels(values))
    _require(minimum <= len(result) <= MAX_CLASSES and len(set(result)) == len(result), "invalid_class_order")
    return result


def _paired_labels(y_true, y_pred, allowed_labels=None):
    truth, pred = _labels(y_true), _labels(y_pred)
    _require(len(truth) == len(pred), "metric_row_count_mismatch")
    _require(isinstance(truth[0], str) == isinstance(pred[0], str), "mixed_label_types")
    labels = set(truth) | set(pred)
    _require(len(labels) <= MAX_CLASSES, "class_limit_exceeded")
    if allowed_labels is not None:
        allowed = set(_label_order(allowed_labels))
        _require(labels <= allowed, "unknown_class_label")
    return truth, pred


def _numeric_errors(y_true, y_pred, budget):
    truth, pred = _vector(y_true), _vector(y_pred)
    _require(len(truth) == len(pred), "metric_row_count_mismatch")
    errors, scale = [], 0.0
    for index, (actual, predicted) in enumerate(zip(truth, pred)):
        if index % 1024 == 0:
            _tick(budget)
        actual, predicted = _number(actual), _number(predicted)
        error = actual - predicted
        if math.isfinite(error):
            scale = max(scale, abs(error))
            errors.append(abs(error))
        else:
            # The residual can overflow even if the aggregate is representable.
            # Save operands and subtract after scaling in that case only;
            # finite residuals retain their direct-subtraction precision.
            scale = max(scale, abs(actual), abs(predicted))
            errors.append((actual, predicted))
    if scale == 0:
        return [0.0] * len(errors), 0.0
    normalized = [abs(error[0] / scale - error[1] / scale) if isinstance(error, tuple)
                  else error / scale for error in errors]
    return normalized, scale


def _f1(truth, pred, *, average, positive=None, labels=None):
    selected = tuple(sorted(set(truth) | set(pred))) if labels is None else _label_order(labels)
    if average == "binary":
        _require(positive is not None, "missing_positive_label")
        positive = _label(positive)
        _require(len(set(truth) | set(pred)) <= 2, "binary_metric_requires_two_classes")
        _require(positive in set(truth) | set(pred) or len(set(truth) | set(pred)) == 1,
                 "positive_label_not_present")
        selected = (positive,)
    tp, actual, predicted = Counter(), Counter(truth), Counter(pred)
    for y, p in zip(truth, pred):
        if y == p:
            tp[y] += 1
    scores, supports, undefined = [], [], False
    for label in selected:
        denominator = actual[label] + predicted[label]
        scores.append(2 * tp[label] / denominator if denominator else 0.0)
        supports.append(actual[label])
        undefined |= denominator == 0
    if average == "weighted":
        value = math.fsum(score * support for score, support in zip(scores, supports)) / len(truth)
    else:
        value = math.fsum(scores) / len(scores)
    return value, undefined


def macro_f1_fixed10(y_true, y_pred, *, budget=None):
    """Named public diagnostic only; never selected as primary registry metric."""
    _tick(budget)
    truth, pred = _paired_labels(y_true, y_pred, PUBLIC_DIAGNOSTIC_LABELS)
    value, _ = _f1(truth, pred, average="macro", labels=PUBLIC_DIAGNOSTIC_LABELS)
    return MetricResult("macro_f1_fixed10", value, "maximize", "label", len(truth))


def validate_probabilities(y_pred, *, n_rows, class_order, prediction_class_order=None, budget=None):
    """Return immutable rows reordered by explicit labels, never normalize silently."""
    target_order = _label_order(class_order, minimum=2)
    supplied_order = target_order if prediction_class_order is None else _label_order(prediction_class_order, minimum=2)
    _require(set(target_order) == set(supplied_order), "probability_class_order_mismatch")
    rows = _vector(y_pred, "invalid_probability_shape")
    _require(len(rows) == n_rows, "metric_row_count_mismatch")
    projection = tuple(supplied_order.index(label) for label in target_order)
    result = []
    for index, row in enumerate(rows):
        if index % 1024 == 0:
            _tick(budget)
        _require(not isinstance(row, (str, bytes, Mapping, Real)), "invalid_probability_shape")
        try:
            _require(len(row) == len(target_order), "invalid_probability_shape")
            values = tuple(_number(value) for value in row)
        except TypeError:
            raise MetricError("invalid_probability_shape") from None
        _require(len(values) == len(target_order), "invalid_probability_shape")
        _require(all(0 <= value <= 1 for value in values), "probability_out_of_range")
        _require(math.isclose(math.fsum(values), 1.0, rel_tol=0, abs_tol=PROBABILITY_SUM_ATOL),
                 "probability_row_sum_invalid")
        result.append(tuple(values[position] for position in projection))
    return tuple(result)


def binary_roc_auc(y_true, scores, *, positive_label, budget=None):
    """Numerical primitive accepts finite decision scores; explicit orientation."""
    _tick(budget)
    _require(positive_label is not None, "missing_positive_label")
    truth = _labels(y_true)
    positive = _label(positive_label)
    labels = set(truth)
    if len(labels) < 2:
        raise UndefinedMetric("roc_auc_single_class")
    _require(len(labels) == 2 and positive in labels, "invalid_binary_class_contract")
    values = [_number(value) for value in _vector(scores)]
    _require(len(values) == len(truth), "metric_row_count_mismatch")
    ordered = sorted(zip(values, (label == positive for label in truth)))
    positive_count = sum(label == positive for label in truth)
    rank_sum, start = 0.0, 0
    while start < len(ordered):
        _tick(budget)
        end = start + 1
        while end < len(ordered) and ordered[end][0] == ordered[start][0]:
            end += 1
        rank_sum += (start + 1 + end) / 2 * sum(flag for _, flag in ordered[start:end])
        start = end
    return (rank_sum - positive_count * (positive_count + 1) / 2) / (positive_count * (len(truth) - positive_count))


def aggregate_oof_rmse(fold_sse_counts, *, budget=None):
    """Global sqrt(sum SSE / sum n), not the mean of per-fold roots."""
    entries = _vector(fold_sse_counts, "invalid_oof_statistics")
    squared_errors, counts = [], []
    for item in entries:
        _tick(budget)
        _require(isinstance(item, (tuple, list)) and len(item) == 2, "invalid_oof_statistics")
        sse, count = item
        sse = _number(sse)
        _require(sse >= 0 and type(count) is int and count > 0, "invalid_oof_statistics")
        squared_errors.append(sse)
        counts.append(count)
    try:
        # Each finite fold SSE can be valid although their raw sum overflows.
        # Scale before summation and take roots before restoring the scale.
        scale = max(squared_errors)
        value = (math.sqrt(scale) * math.sqrt(math.fsum(sse / scale for sse in squared_errors) / sum(counts))
                 if scale else 0.0)
    except (ValueError, OverflowError):
        raise MetricError("metric_overflow") from None
    _require(math.isfinite(value), "metric_overflow")
    _tick(budget)
    return value


def evaluate_metric(metric_contract, y_true, y_pred, *, prediction_class_order=None,
                    allowed_labels=None, budget=None):
    _tick(budget)
    _require(isinstance(metric_contract, Mapping), "invalid_metric_contract")
    spec = metric_spec(metric_contract.get("name"))
    _require(metric_contract.get("direction") == spec.direction and
             metric_contract.get("prediction_kind") == spec.prediction_kind and
             metric_contract.get("finite_policy") == "finite_only" and
             metric_contract.get("target_scale") == "original", "metric_contract_mismatch")
    parameters = metric_contract.get("parameters", {})
    expected = {"average": "macro", "labels": None} if spec.name == "macro_f1" else (
        {"average": "weighted", "labels": None} if spec.name == "weighted_f1" else {})
    _require(parameters == expected, "unsupported_metric_parameters")
    if spec.name in {"macro_f1", "weighted_f1"}:
        _require(metric_contract.get("label_policy") == "sklearn_labels_none", "unsupported_label_policy")
    warnings = ()
    if spec.task_type == "regression":
        errors, scale = _numeric_errors(y_true, y_pred, budget)
        if scale == 0:
            value = 0.0
        elif spec.name == "rmse":
            value = scale * math.sqrt(math.fsum(error**2 for error in errors) / len(errors))
        else:
            value = scale * (math.fsum(errors) / len(errors))
        count = len(errors)
    elif spec.prediction_kind == "label":
        permitted = allowed_labels if allowed_labels is not None else metric_contract.get("class_order")
        truth, pred = _paired_labels(y_true, y_pred, permitted)
        count = len(truth)
        if spec.name == "accuracy":
            value = sum(y == p for y, p in zip(truth, pred)) / count
        else:
            average = {"macro_f1": "macro", "weighted_f1": "weighted", "binary_f1": "binary"}[spec.name]
            positive = metric_contract.get("positive_label")
            value, undefined = _f1(truth, pred, average=average, positive=positive)
            if undefined:
                warnings = ("undefined_f1_zero_division_0",)
    else:
        truth = _labels(y_true)
        count = len(truth)
        order = metric_contract.get("class_order")
        if spec.name == "log_loss":
            _require(order is not None, "missing_class_order")
            order = _label_order(order, minimum=2)
            _require(set(truth) <= set(order), "unknown_class_label")
            probabilities = validate_probabilities(y_pred, n_rows=count, class_order=order,
                prediction_class_order=prediction_class_order, budget=budget)
            positions = {label: index for index, label in enumerate(order)}
            value = math.fsum(-math.log(min(1 - FLOAT64_EPSILON, max(FLOAT64_EPSILON, row[positions[label]])))
                              for label, row in zip(truth, probabilities)) / count
        else:
            positive = metric_contract.get("positive_label")
            _require(positive is not None, "missing_positive_label")
            positive = _label(positive)
            # A declared vocabulary constrains truth for both score vectors and
            # two-column matrices; shape must not change class validation.
            if order is not None:
                order = _label_order(order, minimum=2)
                _require(len(order) == 2 and positive in order and set(truth) <= set(order),
                         "invalid_binary_class_contract")
            predictions = _vector(y_pred)
            if isinstance(predictions[0], Real):
                _require(prediction_class_order is None, "unexpected_probability_class_order")
                scores = [_number(value) for value in predictions]
                _require(all(0 <= value <= 1 for value in scores), "probability_out_of_range")
            else:
                _require(order is not None, "missing_class_order")
                probabilities = validate_probabilities(predictions, n_rows=count, class_order=order,
                    prediction_class_order=prediction_class_order, budget=budget)
                position = order.index(positive)
                scores = [row[position] for row in probabilities]
            value = binary_roc_auc(truth, scores, positive_label=positive, budget=budget)
    _tick(budget)
    _require(math.isfinite(value), "metric_overflow")
    return MetricResult(spec.name, float(value), spec.direction, spec.prediction_kind, count, warnings)
