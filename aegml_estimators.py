"""Trusted fixed CatBoost 1.2.8 CPU adapter; no source, API or worker access.

Only search-fit targets and already prepared feature matrices enter this API.
The caller owns the shared deadline and source loader. Checks are cooperative;
this repository adapter does not claim a generated-code OS boundary.
"""

from dataclasses import asdict, dataclass, field
import copy
import hashlib
import json
import math
from numbers import Integral, Real
import re
import struct
from time import monotonic


class EstimatorError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class EstimatorConfig:
    iterations: int = 300
    threads: int = 8
    seed: int = 42
    max_rows: int = 2_000_000
    max_features: int = 100000
    max_input_bytes: int = 512 << 20
    max_model_bytes: int = 256 << 20

    def __post_init__(self):
        if any(type(value) is not int for value in asdict(self).values()):
            raise EstimatorError("invalid_estimator_config")

        if (not 1 <= self.iterations <= 300 or not 1 <= self.threads <= 8
                or not 0 <= self.seed <= 2**31 - 1 or not 0 < self.max_rows <= 2_000_000
                or not 0 < self.max_features <= 100000 or not 0 < self.max_input_bytes <= 512 << 20
                or not 0 < self.max_model_bytes <= 256 << 20):
            raise EstimatorError("invalid_estimator_config")

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class EstimatorProbabilityBatch:
    values: tuple[tuple[float, ...], ...] = field(repr=False)
    row_indices: tuple[int, ...] = field(repr=False)
    class_order: tuple


_FIT_MATRIX_TOKEN = object()


@dataclass(frozen=True)
class FitMatrixEnvelope:
    """Trusted assembly binding, not an OS boundary or a caller phase label."""
    data: object = field(repr=False)
    train_rows: int
    source_sha256: str
    split_sha256: str
    fit_indices_sha256: str
    preprocessing_sha256: str
    fit_audit_sha256: str
    content_sha256: str
    train_row_space: str = "train_source_0_based"
    _factory_token: object = field(default=None, repr=False, compare=False)

    @property
    def matrix(self):
        return self.data.matrix

    @property
    def row_indices(self):
        return self.data.row_indices

    @property
    def feature_names(self):
        return self.data.feature_names

    @property
    def format(self):
        return self.data.format

    @property
    def categorical_feature_indices(self):
        return self.data.categorical_feature_indices

    @property
    def trained_statistics_sha256(self):
        return self.data.trained_statistics_sha256


def _require(budget):
    if budget is None or not callable(getattr(budget, "require", None)):
        raise EstimatorError("budget_required")
    budget.require()


def _sha(value, budget):
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    for index, part in enumerate(encoder.iterencode(value)):
        if index % 256 == 0:
            _require(budget)
        digest.update(part.encode("utf-8"))
    _require(budget)
    return digest.hexdigest()


def _valid_sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _indices(values, n):
    if (type(values) is not tuple or len(values) != n
            or any(type(index) is not int or not 0 <= index < 2_000_000 for index in values)
            or len(set(values)) != n):
        raise EstimatorError("invalid_prepared_row_indices")
    return values


def _prepared(prepared, config, budget):
    from aegml_preprocessing import PreparedData
    import numpy as np
    import pandas as pd
    from scipy import sparse

    _require(budget)
    if not isinstance(prepared, PreparedData):
        raise EstimatorError("prepared_data_required")
    names = prepared.feature_names
    cats = prepared.categorical_feature_indices
    if (type(names) is not tuple or not names or len(names) > config.max_features
            or any(not isinstance(name, str) or not name or len(name) > 256 for name in names)
            or len(set(names)) != len(names) or not _valid_sha(prepared.trained_statistics_sha256)
            or type(cats) is not tuple or any(type(i) is not int or not 0 <= i < len(names) for i in cats)
            or tuple(sorted(set(cats))) != cats):
        raise EstimatorError("invalid_prepared_schema")
    matrix = prepared.matrix
    if prepared.format == "native_dataframe":
        if not isinstance(matrix, pd.DataFrame) or tuple(matrix.columns) != names:
            raise EstimatorError("prepared_feature_order_mismatch")
        n = len(matrix)
        rows = _indices(prepared.row_indices, n)
        if tuple(matrix.index) != rows:
            raise EstimatorError("prepared_row_order_mismatch")
        size = int(matrix.memory_usage(index=True, deep=True).sum())
        for position, name in enumerate(names):
            _require(budget)
            values = matrix[name].array
            if position in cats:
                if any(not isinstance(v, str) or not v or len(v) > (1 << 20) for v in values):
                    raise EstimatorError("invalid_prepared_category")
            else:
                if matrix[name].dtype.kind not in "fiu":
                    raise EstimatorError("invalid_prepared_numeric_dtype")
                numeric = matrix[name].to_numpy(dtype=np.float64)
                if np.isinf(numeric).any():
                    raise EstimatorError("nonfinite_prepared_feature")
        # Numeric NaN is an explicit supported CatBoost nan_mode input.
    elif prepared.format == "csr":
        if not sparse.isspmatrix_csr(matrix) or cats or matrix.dtype.kind not in "fiu":
            raise EstimatorError("invalid_prepared_sparse_matrix")
        if matrix.ndim != 2 or matrix.shape[1] != len(names):
            raise EstimatorError("prepared_feature_order_mismatch")
        try:
            matrix.check_format(full_check=True)
        except (ValueError, TypeError):
            raise EstimatorError("invalid_prepared_sparse_matrix") from None
        if not matrix.has_canonical_format:
            raise EstimatorError("invalid_prepared_sparse_matrix")
        n = matrix.shape[0]
        rows = _indices(prepared.row_indices, n)
        size = matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes
        if matrix.nnz > 20_000_000 or not np.isfinite(matrix.data).all():
            raise EstimatorError("invalid_prepared_sparse_values")
    else:
        raise EstimatorError("unsupported_prepared_format")
    if not 0 < n <= config.max_rows or size > config.max_input_bytes:
        raise EstimatorError("prepared_resource_limit")
    _require(budget)
    return matrix, names, cats, rows


def _matrix_witness(prepared, budget):
    """Hash all matrix values in bounded chunks; CSR is never densified."""
    _require(budget)
    digest = hashlib.sha256()
    metadata = {"format": prepared.format, "features": prepared.feature_names,
                "rows": prepared.row_indices, "cats": prepared.categorical_feature_indices,
                "preprocessing": prepared.trained_statistics_sha256}
    digest.update(_sha(metadata, budget).encode("ascii"))
    matrix = prepared.matrix
    if prepared.format == "native_dataframe":
        for name in prepared.feature_names:
            _require(budget)
            digest.update(str(matrix[name].dtype).encode("ascii"))
            for index, value in enumerate(matrix[name].array):
                if index % 256 == 0:
                    _require(budget)
                if isinstance(value, str):
                    encoded = value.encode("utf-8")
                    digest.update(b"s" + len(encoded).to_bytes(8, "big"))
                    digest.update(encoded)
                elif isinstance(value, Integral):
                    encoded = str(int(value)).encode("ascii")
                    digest.update(b"i" + len(encoded).to_bytes(8, "big") + encoded)
                else:
                    # Numeric NaN is an explicit native CatBoost input. Binary
                    # float encoding also preserves signed zero without JSON NaN.
                    digest.update(b"f" + struct.pack("!d", float(value)))
    else:
        digest.update(_sha(matrix.shape, budget).encode("ascii"))
        for array in (matrix.data, matrix.indices, matrix.indptr):
            digest.update(str(array.dtype).encode("ascii"))
            digest.update(len(array).to_bytes(8, "big"))
            for start in range(0, len(array), 65536):
                _require(budget)
                digest.update(array[start:start + 65536].tobytes(order="C"))
    _require(budget)
    return digest.hexdigest()


def prepare_fit_matrix(fit_view, recipe, *, budget):
    """Assemble fit-only preprocessing and its matrix from a source-bound view."""
    from aegml_preprocessing import TrainFitView, fit_transform
    _require(budget)
    if (not isinstance(fit_view, TrainFitView) or fit_view.phase != "search_fit"
            or fit_view.source_binding != "verified_csv_bytes_and_explicit_partition"
            or fit_view.active_split_binding != "BUILT_MATCHED"
            or type(fit_view.source_row_count) is not int or fit_view.source_row_count <= 0
            or not _valid_sha(fit_view.source_sha256) or not _valid_sha(fit_view.split_sha256)):
        raise EstimatorError("source_bound_fit_view_required")
    # fit_transform independently checks the loader's opaque view token and the
    # fit-side values witness. A test transform never enters this factory.
    fitted, prepared = fit_transform(fit_view, recipe, budget=budget)
    _prepared(prepared, EstimatorConfig(), budget)
    audit = fitted.audit()
    if (prepared.row_indices != fit_view.row_indices
            or any(index >= fit_view.source_row_count for index in prepared.row_indices)
            or audit.get("source_file_bytes_verified") is not True
            or audit.get("active_split_policy_verified") is not True):
        raise EstimatorError("fit_matrix_binding_mismatch")
    envelope = FitMatrixEnvelope(prepared, fit_view.source_row_count, fit_view.source_sha256,
                                fit_view.split_sha256, _sha(prepared.row_indices, budget),
                                prepared.trained_statistics_sha256, _sha(audit, budget),
                                _matrix_witness(prepared, budget), _factory_token=_FIT_MATRIX_TOKEN)
    return fitted, envelope


def _unwrap_fit_matrix(envelope, audit, config, budget):
    _require(budget)
    if not isinstance(envelope, FitMatrixEnvelope) or envelope._factory_token is not _FIT_MATRIX_TOKEN:
        raise EstimatorError("fit_matrix_envelope_required")
    if (not isinstance(audit, dict) or type(envelope.train_rows) is not int
            or not 0 < envelope.train_rows <= 2_000_000 or envelope.train_row_space != "train_source_0_based"
            or any(not _valid_sha(value) for value in (envelope.source_sha256, envelope.split_sha256,
                envelope.fit_indices_sha256, envelope.preprocessing_sha256, envelope.fit_audit_sha256,
                envelope.content_sha256))):
        raise EstimatorError("fit_matrix_binding_mismatch")
    prepared = envelope.data
    _prepared(prepared, config, budget)
    if (any(index >= envelope.train_rows for index in prepared.row_indices)
            or envelope.source_sha256 != audit.get("source_sha256")
            or envelope.split_sha256 != audit.get("split_sha256")
            or envelope.fit_indices_sha256 != _sha(prepared.row_indices, budget)
            or envelope.preprocessing_sha256 != prepared.trained_statistics_sha256
            or envelope.fit_audit_sha256 != _sha(audit, budget)):
        raise EstimatorError("fit_provenance_mismatch")
    if envelope.content_sha256 != _matrix_witness(prepared, budget):
        raise EstimatorError("fit_matrix_content_changed")
    return prepared


def _label(value):
    if isinstance(value, str):
        if not value.strip() or len(value) > 4096 or "\x00" in value:
            raise EstimatorError("invalid_class_label")
        return value, "text"
    if isinstance(value, bool) or not isinstance(value, Real):
        raise EstimatorError("invalid_class_label")
    if isinstance(value, Integral):
        result = int(value)
        if result.bit_length() > 4096:
            raise EstimatorError("invalid_class_label")
        return result, "numeric"
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        raise EstimatorError("invalid_class_label") from None
    if not math.isfinite(result):
        raise EstimatorError("invalid_class_label")
    return result, "numeric"


def _targets(batch, prepared, audit, task_type, budget):
    from aegml_training_data import TargetBatch
    if not isinstance(batch, TargetBatch) or not isinstance(audit, dict):
        raise EstimatorError("trusted_fit_targets_required")
    if any(not _valid_sha(audit.get(name)) for name in ("schema_sha256", "fit_values_sha256")):
        raise EstimatorError("fit_provenance_mismatch")
    rows = prepared.row_indices
    if (batch.phase != "search_fit_targets" or batch.task_type != task_type
            or type(batch.values) is not tuple or batch.row_indices != rows
            or len(batch.values) != len(rows) or audit.get("phase") != "search_fit"
            or audit.get("source_sha256") != batch.source_sha256
            or audit.get("split_sha256") != batch.partition_sha256
            or not _valid_sha(batch.source_sha256) or not _valid_sha(batch.partition_sha256)
            or audit.get("fit_rows") != len(rows)
            or audit.get("feature_count") != len(prepared.feature_names)
            or audit.get("fit_indices_sha256") != _sha(rows, budget)
            or audit.get("trained_statistics_sha256") != prepared.trained_statistics_sha256
            or audit.get("feature_order_sha256") != _sha(prepared.feature_names, budget)
            or audit.get("source_file_bytes_verified") is not True
            or audit.get("active_split_policy_verified") is not True
            or audit.get("active_split_binding") != "BUILT_MATCHED"
            or audit.get("source_binding") != "verified_csv_bytes_and_explicit_partition"
            or audit.get("categorical_strategy") != ("native" if prepared.format == "native_dataframe" else "onehot")):
        raise EstimatorError("fit_provenance_mismatch")
    values = []
    kinds = set()
    for index, value in enumerate(batch.values):
        if index % 256 == 0:
            _require(budget)
        if task_type == "regression":
            if isinstance(value, bool) or not isinstance(value, (str, Real)):
                raise EstimatorError("invalid_regression_target")
            try:
                number = float(value)
            except (ValueError, TypeError, OverflowError):
                raise EstimatorError("invalid_regression_target") from None
            if not math.isfinite(number):
                raise EstimatorError("nonfinite_regression_target")
            values.append(number)
        else:
            result, kind = _label(value)
            kinds.add(kind)
            values.append(result)
    if task_type == "classification":
        if len(kinds) != 1:
            raise EstimatorError("mixed_class_label_types")
        order = tuple(sorted(set(values)))
        if not 2 <= len(order) <= 4096:
            raise EstimatorError("invalid_fit_class_count")
        mapping = {value: index for index, value in enumerate(order)}
        return [mapping[value] for value in values], order
    return values, ()


def _parameters(config, task_type, class_count):
    return {"task_type": "CPU", "thread_count": config.threads,
            "iterations": config.iterations, "learning_rate": 0.05, "depth": 6,
            "l2_leaf_reg": 5, "boosting_type": "Plain", "bootstrap_type": "Bernoulli",
            "subsample": 0.8, "rsm": 1, "border_count": 128, "one_hot_max_size": 10,
            "max_ctr_complexity": 1, "counter_calc_method": "SkipTest", "nan_mode": "Min",
            "random_seed": config.seed, "allow_writing_files": False, "use_best_model": False,
            "verbose": False, "loss_function": "RMSE" if task_type == "regression" else
            "Logloss" if class_count == 2 else "MultiClass"}


def _model_sha(model, config, budget):
    # Pinned 1.2.8 core exposes _serialize_model; hashing bytes stays in memory.
    # This uses no pickle, save_model, files, source paths, or model downloads.
    _require(budget)
    from catboost import CatBoostError
    try:
        blob = model._serialize_model()
    except CatBoostError:
        raise EstimatorError("estimator_state_unavailable") from None
    if not isinstance(blob, bytes) or len(blob) > config.max_model_bytes:
        raise EstimatorError("model_state_resource_limit")
    digest = hashlib.sha256(blob).hexdigest()
    _require(budget)
    return digest


class FittedEstimator:
    def __init__(self, model, task_type, config, prepared, audit, parameters, class_order, seconds, budget,
                 fit_matrix_sha256):
        self._model = model
        self.task_type = task_type
        self.config = config
        self.feature_names = prepared.feature_names
        self.categorical_feature_indices = prepared.categorical_feature_indices
        self.prepared_format = prepared.format
        self.preprocessing_sha256 = prepared.trained_statistics_sha256
        self.class_order = class_order
        self.fit_seconds = seconds
        self.predict_seconds = 0.0
        self.predict_calls = 0
        self._requested = copy.deepcopy(parameters)
        self._effective = json.loads(json.dumps(model.get_all_params(), ensure_ascii=False, allow_nan=False))
        self._effective_sha = _sha(self._effective, budget)
        self._model_sha = _model_sha(model, config, budget)
        self._fit_binding = {name: copy.deepcopy(audit[name]) for name in
                             ("source_sha256", "split_sha256", "schema_sha256", "fit_values_sha256",
                              "fit_rows", "fit_indices_sha256", "trained_statistics_sha256", "feature_order_sha256")}
        self._fit_binding["prepared_matrix_content_sha256"] = fit_matrix_sha256
        self._binding_sha = _sha(self._binding(), budget)

    def _binding(self):
        return {"task_type": self.task_type, "config": asdict(self.config),
                "features": self.feature_names, "cats": self.categorical_feature_indices,
                "format": self.prepared_format, "preprocessing_sha256": self.preprocessing_sha256,
                "class_order": self.class_order, "fit_binding": self._fit_binding,
                "parameters": self._requested}

    @property
    def parameters(self):
        return copy.deepcopy(self._requested)

    @property
    def effective_parameters(self):
        return copy.deepcopy(self._effective)

    def audit(self):
        return {"adapter_version": "catboost_cpu.v1", "catboost_version": "1.2.8",
                "task_type": self.task_type, "requested_parameters": self.parameters,
                "effective_parameters": self.effective_parameters,
                "effective_parameters_sha256": self._effective_sha, "model_sha256": self._model_sha,
                "state_binding_sha256": self._binding_sha,
                "source_sha256": self._fit_binding["source_sha256"],
                "partition_sha256": self._fit_binding["split_sha256"],
                "preprocessing_statistics_sha256": self.preprocessing_sha256,
                "fit_binding": copy.deepcopy(self._fit_binding), "learned_class_order": list(self.class_order),
                "fit_matrix_binding": "source_bound_factory_and_complete_content_witness",
                "feature_names": list(self.feature_names), "prepared_format": self.prepared_format,
                "categorical_feature_indices": list(self.categorical_feature_indices),
                "tree_count": int(self._model.tree_count_), "fit_seconds": self.fit_seconds,
                "predict_seconds": self.predict_seconds, "predict_calls": self.predict_calls,
                "estimator_fitted": True, "eval_set_used": False, "refit_performed": False,
                "fit_scope": "NO_REFIT_SEARCH_ONLY", "os_boundary_verified": False,
                "cooperative_budget_only": True}

    def _pool(self, prepared, budget):
        from catboost import Pool
        if _sha(self._binding(), budget) != self._binding_sha:
            raise EstimatorError("fitted_estimator_state_changed")
        matrix, names, cats, rows = _prepared(prepared, self.config, budget)
        if (names != self.feature_names or cats != self.categorical_feature_indices
                or prepared.format != self.prepared_format
                or prepared.trained_statistics_sha256 != self.preprocessing_sha256):
            raise EstimatorError("prediction_preprocessing_mismatch")
        if (_model_sha(self._model, self.config, budget) != self._model_sha
                or _sha(self._model.get_all_params(), budget) != self._effective_sha):
            raise EstimatorError("fitted_estimator_state_changed")
        pool = Pool(matrix, cat_features=list(cats), feature_names=list(names), thread_count=self.config.threads)
        _require(budget)
        return pool, rows

    def _predict(self, prepared, budget, probability):
        from catboost import CatBoostError
        from aegml_training_data import PredictionBatch
        import numpy as np

        _require(budget)
        if probability and self.task_type != "classification":
            raise EstimatorError("probability_requires_classification")
        started = monotonic()
        try:
            pool, rows = self._pool(prepared, budget)
            if probability and (len(rows) * len(self.class_order) > 20_000_000
                                or len(rows) * len(self.class_order) * 8 > self.config.max_input_bytes):
                raise EstimatorError("probability_resource_limit")
            raw = np.asarray(self._model.predict_proba(pool, thread_count=self.config.threads) if probability
                             else self._model.predict(pool, thread_count=self.config.threads))
        except CatBoostError:
            raise EstimatorError("estimator_prediction_failed") from None
        _require(budget)
        if probability:
            if (raw.shape != (len(rows), len(self.class_order)) or not np.isfinite(raw).all()
                    or (raw < 0).any() or (raw > 1).any()
                    or not np.all(np.abs(raw.sum(axis=1) - 1.0) <= 1e-6)):
                raise EstimatorError("invalid_probability_prediction")
            result = EstimatorProbabilityBatch(tuple(tuple(float(v) for v in row) for row in raw), rows, self.class_order)
        else:
            if raw.shape == (len(rows), 1):
                raw = raw[:, 0]
            if raw.shape != (len(rows),):
                raise EstimatorError("prediction_shape_mismatch")
            values = []
            for index, value in enumerate(raw):
                if index % 256 == 0:
                    _require(budget)
                if not isinstance(value, Real) or isinstance(value, bool) or not math.isfinite(float(value)):
                    raise EstimatorError("nonfinite_prediction")
                if self.task_type == "classification":
                    code = int(value)
                    if code != value or not 0 <= code < len(self.class_order):
                        raise EstimatorError("unknown_predicted_class_code")
                    values.append(self.class_order[code])
                else:
                    values.append(float(value))
            result = PredictionBatch(tuple(values), rows)
        if _model_sha(self._model, self.config, budget) != self._model_sha:
            raise EstimatorError("fitted_estimator_state_changed")
        self.predict_seconds += monotonic() - started
        self.predict_calls += 1
        _require(budget)
        return result

    def predict(self, prepared, *, budget):
        return self._predict(prepared, budget, False)

    def predict_proba(self, prepared, *, budget):
        return self._predict(prepared, budget, True)

    def feature_importance(self, *, budget):
        from catboost import CatBoostError
        _require(budget)
        if (_sha(self._binding(), budget) != self._binding_sha
                or _model_sha(self._model, self.config, budget) != self._model_sha):
            raise EstimatorError("fitted_estimator_state_changed")
        try:
            values = self._model.get_feature_importance(type="PredictionValuesChange",
                                                       thread_count=self.config.threads)
        except CatBoostError:
            raise EstimatorError("estimator_importance_failed") from None
        if len(values) != len(self.feature_names) or any(not math.isfinite(float(v)) for v in values):
            raise EstimatorError("invalid_feature_importance")
        _require(budget)
        return {"method": "PredictionValuesChange", "causal_interpretation": False,
                "values": [{"feature": name, "importance": float(value)}
                           for name, value in zip(self.feature_names, values)]}


def fit_estimator(prepared_fit, fit_targets, *, task_type, config, budget, fit_audit):
    """Fit only the fixed trusted CPU recipe on explicitly bound search-fit rows."""
    _require(budget)
    if (not isinstance(task_type, str) or task_type not in {"regression", "classification"}
            or not isinstance(config, EstimatorConfig)):
        raise EstimatorError("invalid_estimator_request")
    envelope = prepared_fit
    prepared_fit = _unwrap_fit_matrix(envelope, fit_audit, config, budget)
    encoded, class_order = _targets(fit_targets, prepared_fit, fit_audit, task_type, budget)
    import catboost
    if catboost.__version__ != "1.2.8":
        raise EstimatorError("unsupported_catboost_version")
    _require(budget)
    parameters = _parameters(config, task_type, len(class_order))
    started = monotonic()
    try:
        pool = catboost.Pool(prepared_fit.matrix, label=encoded,
                             cat_features=list(prepared_fit.categorical_feature_indices),
                             feature_names=list(prepared_fit.feature_names), thread_count=config.threads)
        model = (catboost.CatBoostRegressor if task_type == "regression" else catboost.CatBoostClassifier)(**parameters)
        # No eval_set, callbacks, early stopping, source loader or inner labels.
        # Pool construction/imports spend the SAME budget: admit fit only now.
        _require(budget)
        model.fit(pool)
    except catboost.CatBoostError:
        raise EstimatorError("estimator_fit_failed") from None
    _require(budget)
    if not model.is_fitted() or int(model.tree_count_) != config.iterations:
        raise EstimatorError("incomplete_estimator_fit")
    if class_order and tuple(model.classes_) != tuple(range(len(class_order))):
        raise EstimatorError("model_class_order_mismatch")
    fitted = FittedEstimator(model, task_type, config, prepared_fit, fit_audit,
                             parameters, class_order, monotonic() - started, budget, envelope.content_sha256)
    _require(budget)
    return fitted
