"""Frozen trusted split/phase metadata for H03.3, no training or label publishing.

The controller reads labels once for stratification. SplitPlan stores indices
and provenance, never labels. This Python API is not an OS access boundary;
worker/evaluator isolation is still H05. Public summary excludes row indices,
period values and per-class control statistics. No split is built implicitly.
"""

from collections import defaultdict
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import random
import re

from aegml_input import (InputError, MAX_CSV_BYTES, MAX_DICTIONARY_BYTES, MAX_ROWS,
                         MAX_TASK_BYTES, _csv_reader, _sha256)


SPLIT_VERSION = "validation.v1"


class ValidationError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _require(condition, code):
    if not condition:
        raise ValidationError(code)


def _tick(budget):
    if budget is not None:
        budget.require()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _digest(value):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
             "invalid_source_sha256")
    return value


def _indices(values, total, code="invalid_partition_indices"):
    _require(isinstance(values, (tuple, list)), code)
    _require(all(type(index) is int and 0 <= index < total for index in values), code)
    _require(len(values) == len(set(values)), code)
    return tuple(sorted(values))


@dataclass(frozen=True)
class SplitPlan:
    fit_indices: tuple[int, ...]
    inner_indices: tuple[int, ...]
    outer_indices: tuple[int, ...]
    train_rows: int
    train_sha256: str
    policy_id: str
    seed: int = 42
    strategy: str = "explicit"
    schema_sha256: str = "0" * 64
    source_items: tuple[tuple[str, str], ...] = ()
    outer_fraction: float = 0.2
    inner_fraction: float = 0.2
    time_values: tuple[float, ...] = field(default=(), repr=False)

    def __post_init__(self):
        _require(type(self.train_rows) is int and 3 <= self.train_rows <= MAX_ROWS, "invalid_train_rows")
        _digest(self.train_sha256)
        _digest(self.schema_sha256)
        _require(isinstance(self.policy_id, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", self.policy_id), "invalid_split_policy")
        _require(type(self.seed) is int and 0 <= self.seed < 2**32, "invalid_split_seed")
        _require(self.strategy in {"explicit", "temporal", "stratified"}, "unsupported_split_strategy")
        parts = []
        for name in ("fit_indices", "inner_indices", "outer_indices"):
            values = _indices(getattr(self, name), self.train_rows)
            _require(bool(values), "empty_split_partition")
            object.__setattr__(self, name, values)
            parts.append(set(values))
        _require(not (parts[0] & parts[1] or parts[0] & parts[2] or parts[1] & parts[2]), "split_partition_overlap")
        _require(sum(map(len, parts)) == self.train_rows, "split_partition_incomplete")
        for value in (self.outer_fraction, self.inner_fraction):
            _require(type(value) in (float, int) and math.isfinite(value) and 0 < value < 1, "invalid_split_fraction")
        _require(isinstance(self.source_items, (list, tuple)) and all(
            isinstance(item, (list, tuple)) and len(item) == 2 and isinstance(item[0], str)
            for item in self.source_items), "invalid_source_manifest")
        sources = tuple(sorted(tuple(item) for item in self.source_items))
        _require(len({item[0] for item in sources}) == len(sources), "invalid_source_manifest")
        for item in sources:
            _require(len(item) == 2 and isinstance(item[0], str), "invalid_source_manifest")
            _digest(item[1])
        _require(not sources or dict(sources).get("train") == self.train_sha256, "source_manifest_mismatch")
        object.__setattr__(self, "source_items", sources)
        _require(isinstance(self.time_values, (tuple, list)), "invalid_temporal_values")
        times = tuple(self.time_values)
        if self.strategy == "temporal":
            _require(len(times) == self.train_rows and all(type(value) in (int, float) and math.isfinite(value) for value in times), "invalid_temporal_values")
            _require(max(times[index] for index in self.fit_indices) < min(times[index] for index in self.inner_indices)
                     and max(times[index] for index in self.inner_indices) < min(times[index] for index in self.outer_indices),
                     "temporal_chronology_violation")
        else:
            _require(not times, "unexpected_temporal_values")
        object.__setattr__(self, "time_values", times)

    @property
    def development_indices(self):
        return tuple(sorted(self.fit_indices + self.inner_indices))

    @property
    def protected_indices(self):
        return tuple(sorted(self.inner_indices + self.outer_indices))

    @property
    def source_sha256(self):
        return dict(self.source_items)

    @property
    def partition_sha256(self):
        return canonical_sha({"version": SPLIT_VERSION, "train_sha256": self.train_sha256,
            "train_rows": self.train_rows, "schema_sha256": self.schema_sha256,
            "policy_id": self.policy_id, "strategy": self.strategy, "seed": self.seed,
            "fit_indices": self.fit_indices, "inner_indices": self.inner_indices,
            "outer_indices": self.outer_indices, "outer_fraction": self.outer_fraction,
            "inner_fraction": self.inner_fraction})

    def to_dict(self, *, include_indices=False):
        """Trusted manifest. No y/labels exist; indices require explicit opt-in."""
        result = {"version": SPLIT_VERSION, "policy_id": self.policy_id,
            "strategy": self.strategy, "seed": self.seed, "train_rows": self.train_rows,
            "train_sha256": self.train_sha256, "source_sha256": self.source_sha256,
            "schema_sha256": self.schema_sha256, "partition_sha256": self.partition_sha256,
            "counts": {"fit": len(self.fit_indices), "inner": len(self.inner_indices), "outer": len(self.outer_indices)},
            "outer_fraction_requested": self.outer_fraction, "inner_fraction_requested": self.inner_fraction,
            "indices_internal_to_trusted_controller": True, "os_boundary_verified": False,
            "training_executed": False}
        if include_indices:
            result.update(fit_indices=list(self.fit_indices), inner_indices=list(self.inner_indices), outer_indices=list(self.outer_indices))
        return result


def _metadata(bundle, contract):
    payload = contract.to_dict() if hasattr(contract, "to_dict") else contract
    _require(isinstance(payload, dict), "invalid_split_contract")
    _require(payload.get("provenance", {}).get("source_sha256") == bundle.source_sha256,
             "split_contract_source_mismatch")
    schema = {"headers": {role: list(header) for role, header in bundle.headers.items()},
        "dictionary": list(bundle.dictionary_rows), "features": payload["feature_columns"],
        "targets": payload["target_columns"], "ids": payload["id_columns"], "task_type": payload["task_type"]}
    return payload, canonical_sha(schema)


def _read_values(bundle, column, budget, *, numeric):
    _require(column in bundle.headers["train"], "split_column_missing")
    position = bundle.headers["train"].index(column)
    values = []
    try:
        with _csv_reader(bundle.files["train"], bundle.task_path.parent, "train", MAX_CSV_BYTES,
                         budget, bundle.source_sha256["train"]) as (reader, header):
            _require(tuple(header) == tuple(bundle.headers["train"]), "split_header_changed")
            for index, row in enumerate(reader):
                if index % 1024 == 0:
                    _tick(budget)
                _require(index < MAX_ROWS and len(row) == len(header), "invalid_split_csv_shape")
                raw = row[position]
                _require(bool(raw.strip()) and len(raw) <= 4096, "invalid_split_value")
                if numeric:
                    try:
                        value = float(raw)
                    except (ValueError, OverflowError):
                        raise ValidationError("invalid_temporal_value") from None
                    _require(math.isfinite(value), "invalid_temporal_value")
                else:
                    value = raw  # Literal NA/null and zero-padded labels are data.
                values.append(value)
    except InputError as exc:
        raise ValidationError(exc.code) from None
    _require(len(values) >= 3, "insufficient_split_rows")
    return values


def _periods(values):
    _require(isinstance(values, (tuple, list)) and bool(values), "invalid_period_declaration")
    _require(all(type(value) in (int, float) and math.isfinite(value) for value in values), "invalid_period_declaration")
    _require(len(values) == len(set(values)), "invalid_period_declaration")
    return set(values)


def _allocate(counts, desired, lower, upper):
    """Largest-deficit integer apportionment with explicit class-presence bounds."""
    total = sum(counts)
    _require(sum(lower) <= desired <= sum(upper), "rare_class_split_infeasible")
    ideals = [count * desired / total for count in counts]
    result = [min(max(math.floor(ideal), lo), hi) for ideal, lo, hi in zip(ideals, lower, upper)]
    while sum(result) < desired:
        candidates = [index for index in range(len(counts)) if result[index] < upper[index]]
        index = max(candidates, key=lambda item: (ideals[item] - result[item], -item))
        result[index] += 1
    while sum(result) > desired:
        candidates = [index for index in range(len(counts)) if result[index] > lower[index]]
        index = max(candidates, key=lambda item: (result[item] - ideals[item], -item))
        result[index] -= 1
    return result


def build_split_plan(bundle, contract, *, strategy, budget, seed=42, time_column=None,
                     fit_periods=(1, 2, 3), inner_periods=(4,), outer_periods=(5,),
                     outer_fraction=0.2, inner_fraction=0.2):
    _require(budget is not None and callable(getattr(budget, "require", None)), "budget_required")
    _tick(budget)
    _require(type(seed) is int and 0 <= seed < 2**32, "invalid_split_seed")
    _require(strategy in {"temporal", "stratified"}, "unsupported_split_strategy")
    for fraction in (outer_fraction, inner_fraction):
        _require(type(fraction) in (float, int) and math.isfinite(fraction) and 0 < fraction < 1, "invalid_split_fraction")
    payload, schema_sha = _metadata(bundle, contract)
    if strategy == "temporal":
        _require(payload["task_type"] == "regression", "split_task_type_mismatch")
        _require(isinstance(time_column, str) and time_column in payload["feature_columns"], "missing_temporal_column")
        periods = [_periods(values) for values in (fit_periods, inner_periods, outer_periods)]
        _require(not (periods[0] & periods[1] or periods[0] & periods[2] or periods[1] & periods[2]), "temporal_period_overlap")
        _require(max(periods[0]) < min(periods[1]) and max(periods[1]) < min(periods[2]), "temporal_chronology_violation")
        values = _read_values(bundle, time_column, budget, numeric=True)
        _require(set(values) == set.union(*periods), "temporal_period_coverage_mismatch")
        parts = [tuple(index for index, value in enumerate(values) if value in part) for part in periods]
        policy, time_values = "temporal_periods_v1", tuple(values)
    else:
        _require(payload["task_type"] == "classification", "split_task_type_mismatch")
        _require(len(payload["target_columns"]) == 1, "split_requires_single_target")
        values = _read_values(bundle, payload["target_columns"][0], budget, numeric=False)
        buckets = defaultdict(list)
        for index, label in enumerate(values):
            buckets[label].append(index)
        labels = sorted(buckets)
        _require(2 <= len(labels) <= 4096 and min(map(len, buckets.values())) >= 3, "rare_class_split_infeasible")
        counts = [len(buckets[label]) for label in labels]
        outer_n = math.ceil(len(values) * outer_fraction)
        outer_counts = _allocate(counts, outer_n, [1] * len(labels), [count - 2 for count in counts])
        development_counts = [count - holdout for count, holdout in zip(counts, outer_counts)]
        inner_n = math.ceil((len(values) - outer_n) * inner_fraction)
        inner_counts = _allocate(development_counts, inner_n, [1] * len(labels), [count - 1 for count in development_counts])
        fit, inner, outer = [], [], []
        for label, n_outer, n_inner in zip(labels, outer_counts, inner_counts):
            _tick(budget)
            indices = list(buckets[label])
            random.Random(canonical_sha({"seed": seed, "label": label, "version": SPLIT_VERSION})).shuffle(indices)
            outer.extend(indices[:n_outer])
            inner.extend(indices[n_outer:n_outer + n_inner])
            fit.extend(indices[n_outer + n_inner:])
        parts = (tuple(fit), tuple(inner), tuple(outer))
        policy, time_values = "stratified_nested_v1", ()
    _tick(budget)
    plan = SplitPlan(*parts, len(values), bundle.source_sha256["train"], policy, seed, strategy,
                     schema_sha, tuple(bundle.source_sha256.items()), outer_fraction, inner_fraction, time_values)
    verify_split_source(plan, bundle, budget=budget)
    return plan


def verify_split_source(plan, bundle, *, budget):
    _require(budget is not None and callable(getattr(budget, "require", None)), "budget_required")
    _tick(budget)
    _require(isinstance(plan, SplitPlan) and bundle.source_sha256.get("train") == plan.train_sha256
             and plan.source_sha256 == bundle.source_sha256,
             "split_source_mismatch")
    try:
        paths = {"task": bundle.task_path, **bundle.files}
        for role, expected in plan.source_items:
            _tick(budget)
            limit = MAX_TASK_BYTES if role == "task" else MAX_DICTIONARY_BYTES if role == "data_dictionary" else MAX_CSV_BYTES
            actual = _sha256(paths[role], bundle.task_path.parent, role, limit, budget)
            _require(actual == expected, "source_changed")
    except InputError as exc:
        raise ValidationError(exc.code) from None
    return True


@dataclass(frozen=True)
class EarlyStopPlan:
    train_indices: tuple[int, ...]
    stop_indices: tuple[int, ...]
    split_sha256: str

    def __post_init__(self):
        _digest(self.split_sha256)
        for name in ("train_indices", "stop_indices"):
            values = getattr(self, name)
            _require(isinstance(values, (list, tuple)) and bool(values) and
                     all(type(value) is int and value >= 0 for value in values)
                     and len(values) == len(set(values)), "invalid_early_stop_partition")
            object.__setattr__(self, name, tuple(sorted(values)))
        _require(not set(self.train_indices) & set(self.stop_indices), "invalid_early_stop_partition")

    @property
    def partition_sha256(self):
        return canonical_sha({"split_sha256": self.split_sha256,
            "train_indices": self.train_indices, "stop_indices": self.stop_indices})


def build_early_stop_plan(plan, *, train_indices, stop_indices):
    _require(isinstance(plan, SplitPlan), "invalid_split_plan")
    train = _indices(train_indices, plan.train_rows)
    stop = _indices(stop_indices, plan.train_rows)
    _require(bool(train) and bool(stop) and not set(train) & set(stop)
             and set(train) | set(stop) == set(plan.fit_indices), "early_stop_outside_fit")
    if plan.strategy == "temporal":
        _require(max(plan.time_values[index] for index in train) < min(plan.time_values[index] for index in stop),
                 "early_stop_chronology_violation")
    return EarlyStopPlan(train, stop, plan.partition_sha256)


@dataclass(frozen=True)
class FrozenRecipe:
    code_sha256: str
    config_sha256: str
    preprocessing_sha256: str
    iterations: int
    selection_split_sha256: str
    iteration_source: str = "fixed"
    early_stop_partition_sha256: str | None = None

    def __post_init__(self):
        for value in (self.code_sha256, self.config_sha256, self.preprocessing_sha256, self.selection_split_sha256):
            _digest(value)
        _require(type(self.iterations) is int and 0 < self.iterations <= 1_000_000_000, "invalid_frozen_iterations")
        _require(self.iteration_source in {"fixed", "fit_early_stop"}, "invalid_iteration_source")
        if self.iteration_source == "fit_early_stop":
            _digest(self.early_stop_partition_sha256)
        else:
            _require(self.early_stop_partition_sha256 is None, "unexpected_early_stop_provenance")

    @property
    def recipe_sha256(self):
        return canonical_sha({"code": self.code_sha256, "config": self.config_sha256,
            "preprocessing": self.preprocessing_sha256, "iterations": self.iterations,
            "selection_split_sha256": self.selection_split_sha256,
            "iteration_source": self.iteration_source, "early_stop_partition_sha256": self.early_stop_partition_sha256})


def freeze_recipe(plan, *, code_sha256, config_sha256, preprocessing_sha256,
                  iterations, iteration_source="fixed", early_stop_plan=None):
    _require(isinstance(plan, SplitPlan), "invalid_split_plan")
    if iteration_source == "fit_early_stop":
        _require(isinstance(early_stop_plan, EarlyStopPlan) and
                 early_stop_plan.split_sha256 == plan.partition_sha256, "early_stop_outside_fit")
        checked = build_early_stop_plan(plan, train_indices=early_stop_plan.train_indices,
                                       stop_indices=early_stop_plan.stop_indices)
        stop_sha = checked.partition_sha256
    else:
        _require(early_stop_plan is None, "unexpected_early_stop_provenance")
        stop_sha = None
    return FrozenRecipe(code_sha256, config_sha256, preprocessing_sha256, iterations,
                        plan.partition_sha256, iteration_source, stop_sha)


@dataclass(frozen=True)
class PhaseGrant:
    phase: str
    train_indices: tuple[int, ...]
    predict_indices: tuple[int, ...]
    evaluator_indices: tuple[int, ...]
    feedback_allowed: bool
    partition_sha256: str
    recipe_sha256: str | None
    refit_performed: bool = field(default=False, init=False)

    def __post_init__(self):
        _digest(self.partition_sha256)
        _require(self.phase in {"search", "frozen_refit"}, "unsupported_validation_phase")
        for name in ("train_indices", "predict_indices", "evaluator_indices"):
            values = getattr(self, name)
            _require(isinstance(values, (tuple, list)) and bool(values) and
                     all(type(index) is int and index >= 0 for index in values)
                     and len(values) == len(set(values)), "invalid_phase_indices")
            object.__setattr__(self, name, tuple(sorted(values)))
        _require(not set(self.train_indices) & set(self.evaluator_indices) and
                 self.predict_indices == self.evaluator_indices, "invalid_phase_access")
        _require(type(self.feedback_allowed) is bool and self.feedback_allowed == (self.phase == "search"),
                 "invalid_phase_feedback_policy")
        if self.phase == "frozen_refit":
            _digest(self.recipe_sha256)
        else:
            _require(self.recipe_sha256 is None, "unexpected_frozen_recipe")


def phase_grant(plan, phase, *, recipe=None):
    """Grant trusted row roles only; never claim that a fit/refit actually ran."""
    _require(isinstance(plan, SplitPlan), "invalid_split_plan")
    if phase == "search":
        _require(recipe is None, "unexpected_frozen_recipe")
        return PhaseGrant(phase, plan.fit_indices, plan.inner_indices, plan.inner_indices,
                          True, plan.partition_sha256, None)
    _require(phase == "frozen_refit", "unsupported_validation_phase")
    _require(isinstance(recipe, FrozenRecipe), "frozen_recipe_required")
    _require(recipe.selection_split_sha256 == plan.partition_sha256, "frozen_iteration_split_mismatch")
    return PhaseGrant(phase, plan.development_indices, plan.outer_indices, plan.outer_indices,
                      False, plan.partition_sha256, recipe.recipe_sha256)
