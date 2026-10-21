"""Trusted H03.2 fit-only preprocessing; no estimator, network, or code execution.

Frames contain lexical CSV strings. Source identity is asserted by the trusted
loader; the view additionally witnesses the exact selected feature values. A
view is a provenance check, not an OS access-control boundary.
"""

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import re


class PreprocessingError(Exception):
    """Fixed safe reason codes; raw cells/OS exceptions never enter errors."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _require(budget):
    if budget is not None:
        budget.require()


def _sha(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _names(values):
    if not isinstance(values, (tuple, list)):
        raise PreprocessingError("invalid_feature_schema")
    result = tuple(values)
    if any(not isinstance(name, str) or not name.strip() for name in result):
        raise PreprocessingError("invalid_feature_schema")
    if len(set(result)) != len(result):
        raise PreprocessingError("duplicate_feature_column")
    return result


@dataclass(frozen=True)
class FeatureSchema:
    feature_columns: tuple[str, ...]
    numeric_columns: tuple[str, ...] = ()
    categorical_columns: tuple[str, ...] = ()
    text_columns: tuple[str, ...] = ()
    forbidden_columns: tuple[str, ...] = ()
    missing_policy: str = "literal_empty_only"

    def __post_init__(self):
        for name in ("feature_columns", "numeric_columns", "categorical_columns",
                     "text_columns", "forbidden_columns"):
            object.__setattr__(self, name, _names(getattr(self, name)))
        groups = self.numeric_columns + self.categorical_columns + self.text_columns
        if (not self.feature_columns or len(set(groups)) != len(groups)
                or set(groups) != set(self.feature_columns)
                or set(self.feature_columns) & set(self.forbidden_columns)
                or self.missing_policy != "literal_empty_only"):
            raise PreprocessingError("invalid_feature_schema")

    @property
    def schema_sha256(self):
        return _sha(asdict(self))


def schema_from_kinds(contract, kinds):
    """Use authoritative features/forbidden roles, never target cardinality."""
    payload = contract.to_dict() if hasattr(contract, "to_dict") else contract
    try:
        columns = tuple(payload["feature_columns"])
        if set(kinds) != set(columns):
            raise PreprocessingError("incomplete_feature_kinds")
        if any(kinds[name] not in {"numeric", "categorical", "text"} for name in columns):
            raise PreprocessingError("unsupported_feature_kind")
        return FeatureSchema(
            columns,
            tuple(name for name in columns if kinds[name] == "numeric"),
            tuple(name for name in columns if kinds[name] == "categorical"),
            tuple(name for name in columns if kinds[name] == "text"),
            tuple(payload["target_columns"]) + tuple(payload["id_columns"]),
        )
    except (KeyError, TypeError, AttributeError):
        raise PreprocessingError("invalid_feature_schema") from None


@dataclass(frozen=True)
class PreprocessingRecipe:
    categorical_strategy: str = "onehot"
    max_categories_per_column: int = 4096
    max_total_categories: int = 20000
    text_max_features_per_column: int = 4096
    text_candidate_terms_per_column: int = 65536
    text_max_chars_per_cell: int = 8192
    max_text_columns: int = 16
    max_input_bytes: int = 512 << 20
    max_output_features: int = 100000
    max_output_nnz: int = 20000000
    max_output_bytes: int = 256 << 20

    def __post_init__(self):
        if self.categorical_strategy not in {"onehot", "native"}:
            raise PreprocessingError("unknown_preprocessing_recipe")
        for name, value in asdict(self).items():
            if name == "categorical_strategy":
                continue
            if type(value) is not int or value <= 0:
                raise PreprocessingError("invalid_preprocessing_limit")
        if self.text_max_features_per_column > self.text_candidate_terms_per_column:
            raise PreprocessingError("invalid_preprocessing_limit")


def _validate_frame(frame, schema, recipe=None, *, allow_empty=False):
    import pandas as pd

    if not isinstance(frame, pd.DataFrame):
        raise PreprocessingError("expected_feature_dataframe")
    if frame.columns.has_duplicates:
        raise PreprocessingError("duplicate_feature_column")
    columns = tuple(frame.columns)
    if set(columns) & set(schema.forbidden_columns):
        raise PreprocessingError("forbidden_target_or_id_column")
    if set(columns) != set(schema.feature_columns) or len(columns) != len(schema.feature_columns):
        raise PreprocessingError("feature_columns_mismatch")
    if not allow_empty and len(frame) == 0:
        raise PreprocessingError("empty_feature_frame")
    if recipe is not None and int(frame.memory_usage(index=True, deep=True).sum()) > recipe.max_input_bytes:
        raise PreprocessingError("preprocessing_input_memory_limit")
    for name in schema.feature_columns:
        if any(not isinstance(value, str) for value in frame[name].array):
            raise PreprocessingError("non_lexical_feature_value")


def _indices(values, n):
    if not isinstance(values, tuple):
        raise PreprocessingError("invalid_fit_partition")
    if (any(type(index) is not int or index < 0 or index >= n for index in values)
            or tuple(sorted(set(values))) != values):
        raise PreprocessingError("invalid_fit_partition")
    return values


def _frame_sha(frame, columns, budget):
    digest = hashlib.sha256()
    digest.update(json.dumps(list(columns), ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8"))
    for index, row in enumerate(frame.loc[:, list(columns)].itertuples(index=False, name=None)):
        if index % 512 == 0:
            _require(budget)
        encoded = json.dumps(row, ensure_ascii=False, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


@dataclass(frozen=True)
class TrainFitView:
    _frame: object = field(repr=False)
    schema: FeatureSchema
    row_indices: tuple[int, ...]
    source_sha256: str
    split_sha256: str
    fit_values_sha256: str
    source_row_count: int
    phase: str = "search_fit"
    source_binding: str = "caller_asserted_dataframe"
    active_split_binding: str = "NOT_BOUND_TRUSTED_DATAFRAME"
    _factory_token: object = field(default=None, repr=False, compare=False)

    @property
    def frame(self):
        return self._frame.copy(deep=True)


_FIT_VIEW_TOKEN = object()


def _validated_plan(split_plan, source_sha256, n):
    try:
        if type(split_plan.train_rows) is not int or split_plan.train_rows != n:
            raise PreprocessingError("fit_source_rows_mismatch")
        fit = _indices(split_plan.fit_indices, n)
        inner = _indices(split_plan.inner_indices, n)
        outer = _indices(split_plan.outer_indices, n)
        split_sha = split_plan.partition_sha256
        if (not all((fit, inner, outer)) or set(fit) & set(inner) or set(fit) & set(outer)
                or set(inner) & set(outer) or len(fit) + len(inner) + len(outer) != n):
            raise PreprocessingError("invalid_fit_partition")
        if (not isinstance(source_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", source_sha256)
                or source_sha256 != split_plan.train_sha256
                or not isinstance(split_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", split_sha)):
            raise PreprocessingError("fit_source_identity_mismatch")
        return fit, split_sha
    except AttributeError:
        raise PreprocessingError("invalid_fit_partition") from None


def make_train_fit_view(X_source, *, schema, split_plan, source_sha256, budget=None):
    """Select T_fit from feature-only full-source rows; never infer a split.

    Full source indices exclude the CSV header. The loader must bind this frame
    to the asserted file SHA; no byte/file identity or OS secrecy is claimed by
    accepting a DataFrame and metadata alone. No labels enter this API.
    """
    _require(budget)
    if not isinstance(schema, FeatureSchema):
        raise PreprocessingError("invalid_feature_schema")
    _validate_frame(X_source, schema, PreprocessingRecipe())
    n = len(X_source)
    fit, split_sha = _validated_plan(split_plan, source_sha256, n)
    if tuple(X_source.index) != tuple(range(n)):
        raise PreprocessingError("noncanonical_source_row_index")
    selected = X_source.iloc[list(fit)].loc[:, list(schema.feature_columns)].copy(deep=True)
    witness = _frame_sha(selected, schema.feature_columns, budget)
    _require(budget)
    return TrainFitView(selected, schema, fit, source_sha256, split_sha, witness, n,
                        _factory_token=_FIT_VIEW_TOKEN)


@dataclass(frozen=True)
class FeatureLoadLimits:
    max_retained_chars: int = 128 << 20
    max_selected_cells: int = 8_000_000

    def __post_init__(self):
        if (type(self.max_retained_chars) is not int or not 0 < self.max_retained_chars <= 128 << 20
                or type(self.max_selected_cells) is not int or not 0 < self.max_selected_cells <= 8_000_000):
            raise PreprocessingError("invalid_feature_load_limits")


def _mandatory_budget(budget):
    if budget is None or not callable(getattr(budget, "require", None)):
        raise PreprocessingError("budget_required")
    budget.require()


def _bound_sources(bundle, contract, schema, budget):
    """Authenticate all supplied identities before retaining any feature cell."""
    from aegml_input import MAX_CSV_BYTES, MAX_DICTIONARY_BYTES, MAX_TASK_BYTES, _sha256, _unchanged
    from aegml_schemas import SchemaError, validate_task_contract

    _mandatory_budget(budget)
    payload = contract.to_dict()
    try:
        validate_task_contract(payload)
    except SchemaError:
        raise PreprocessingError("source_contract_schema_mismatch") from None
    if not isinstance(schema, FeatureSchema):
        raise PreprocessingError("invalid_feature_schema")
    roles = ("task", "train", "test", "data_dictionary", "sample_submission")
    if (set(bundle.source_sha256) != set(roles)
            or payload["provenance"]["source_sha256"] != bundle.source_sha256
            or payload["task_path"] != str(bundle.task_path)
            or payload["input_paths"] != {role: str(path) for role, path in bundle.files.items()}
            or tuple(payload["feature_columns"]) != schema.feature_columns
            or not set(payload["target_columns"] + payload["id_columns"]).issubset(schema.forbidden_columns)):
        raise PreprocessingError("source_contract_identity_mismatch")
    root = bundle.task_path.parent
    paths = {"task": bundle.task_path, **bundle.files}
    snapshots = {}
    for role in roles:
        _mandatory_budget(budget)
        expected = bundle.provenance[role]["stat"]
        _unchanged(paths[role], root, role, expected)
        snapshots[role] = dict(expected)
        limit = MAX_TASK_BYTES if role == "task" else MAX_DICTIONARY_BYTES if role == "data_dictionary" else MAX_CSV_BYTES
        if _sha256(paths[role], root, role, limit, budget) != bundle.source_sha256[role]:
            raise PreprocessingError("source_bytes_changed")
    return payload, root, paths, snapshots


def _verify_active_split_policy(payload, plan, budget):
    """H032-PARTITION-BIND-001: source equality is not active split equality."""
    from aegml_validation import SplitPlan

    _mandatory_budget(budget)
    active = payload["split_policy"]
    if active["status"] != "BUILT":
        raise PreprocessingError("active_split_policy_required")
    if not isinstance(plan, SplitPlan):
        raise PreprocessingError("trusted_fit_partition_required")
    expected = {
        "status": "BUILT", "strategy": plan.strategy, "source": "trusted_validation.v1",
        "policy_id": plan.policy_id, "partition_sha256": plan.partition_sha256,
        "schema_sha256": plan.schema_sha256, "train_sha256": plan.train_sha256,
        "train_rows": plan.train_rows, "seed": plan.seed,
        "row_counts": {"fit": len(plan.fit_indices), "inner": len(plan.inner_indices),
                       "outer": len(plan.outer_indices)},
    }
    if active != expected:
        raise PreprocessingError("active_split_policy_mismatch")
    _mandatory_budget(budget)


def _source_bound_features(bundle, contract, schema, budget, limits, *, split_plan=None):
    from aegml_input import InputError, MAX_CSV_BYTES, _csv_reader, _unchanged
    import pandas as pd

    _mandatory_budget(budget)
    if not isinstance(limits, FeatureLoadLimits):
        raise PreprocessingError("invalid_feature_load_limits")
    try:
        payload, root, paths, snapshots = _bound_sources(bundle, contract, schema, budget)
        row_counts = payload["provenance"]["row_mapping"]["row_counts"]
        role = "train" if split_plan is not None else "test"
        if type(row_counts[role]) is not int or row_counts[role] <= 0:
            raise PreprocessingError("source_row_count_mismatch")
        if split_plan is not None:
            fit, split_sha = _validated_plan(split_plan, bundle.source_sha256["train"], row_counts["train"])
            _verify_active_split_policy(payload, split_plan, budget)
            if split_plan.source_sha256 != bundle.source_sha256:
                raise PreprocessingError("split_source_identity_mismatch")
            selected_count = len(fit)
        else:
            fit, split_sha = (), None
            selected_count = row_counts["test"]
        if selected_count * len(schema.feature_columns) > limits.max_selected_cells:
            raise PreprocessingError("feature_load_cell_limit")
        rows, row_indices, chars, count, next_fit = [], [], 0, 0, 0
        expected_header = bundle.headers[role]
        with _csv_reader(paths[role], root, role, MAX_CSV_BYTES, budget,
                         expected_sha=bundle.source_sha256[role]) as (reader, header):
            if header != expected_header or not set(schema.feature_columns).issubset(header):
                raise PreprocessingError("source_feature_header_mismatch")
            positions = tuple(header.index(name) for name in schema.feature_columns)
            for index, values in enumerate(reader):
                if index % 256 == 0:
                    _mandatory_budget(budget)
                count += 1
                if count > row_counts[role] or len(values) != len(header):
                    raise PreprocessingError("source_csv_rows_mismatch")
                if role == "train" and (next_fit >= len(fit) or index != fit[next_fit]):
                    # No projection, numeric parse, category collection or label
                    # access for protected rows; only structural row validation.
                    continue
                projected = [values[position] for position in positions]
                chars += sum(map(len, projected))
                if chars > limits.max_retained_chars:
                    raise PreprocessingError("feature_load_character_limit")
                rows.append(projected)
                row_indices.append(index)
                if role == "train":
                    next_fit += 1
        if count != row_counts[role] or len(rows) != selected_count:
            raise PreprocessingError("source_row_count_mismatch")
        if role == "train" and tuple(row_indices) != fit:
            raise PreprocessingError("fit_row_order_mismatch")
        for source_role, snapshot in snapshots.items():
            _mandatory_budget(budget)
            _unchanged(paths[source_role], root, source_role, snapshot)
        _mandatory_budget(budget)
        frame = pd.DataFrame(rows, columns=list(schema.feature_columns), index=row_indices)
        _mandatory_budget(budget)
        if role == "test":
            return frame
        witness = _frame_sha(frame, schema.feature_columns, budget)
        return TrainFitView(frame, schema, fit, bundle.source_sha256["train"], split_sha,
                            witness, row_counts["train"],
                            source_binding="verified_csv_bytes_and_explicit_partition",
                            active_split_binding="BUILT_MATCHED",
                            _factory_token=_FIT_VIEW_TOKEN)
    except InputError as exc:
        raise PreprocessingError(exc.code) from None
    except (KeyError, AttributeError, TypeError):
        raise PreprocessingError("invalid_source_binding") from None


def load_train_fit_view(bundle, contract, split_plan, *, schema, budget, limits=FeatureLoadLimits()):
    """Read authenticated CSV bytes; retain only explicitly permitted fit X.

    This trusted loader retains no inner/outer features or target/ID columns.
    The contract must be BUILT and match this exact SplitPlan and its metadata.
    Legacy NOT_BUILT contracts are rejected; the separate low-level DataFrame
    API is explicitly caller-asserted and never claims active split verification.
    Authentication is at consumed bytes plus before/after stat guards; it does
    not claim an OS boundary against a concurrent privileged source writer.
    """
    _mandatory_budget(budget)
    if split_plan is None:
        raise PreprocessingError("trusted_fit_partition_required")
    return _source_bound_features(bundle, contract, schema, budget, limits, split_plan=split_plan)


def load_test_features(bundle, contract, *, schema, budget, limits=FeatureLoadLimits()):
    """Read authenticated test X only, preserving lexical cells and row order."""
    _mandatory_budget(budget)
    return _source_bound_features(bundle, contract, schema, budget, limits)


@dataclass(frozen=True)
class PreparedData:
    matrix: object = field(repr=False)
    row_indices: tuple
    feature_names: tuple[str, ...]
    format: str
    diagnostics: dict
    trained_statistics_sha256: str
    categorical_feature_indices: tuple[int, ...] = ()


def _numeric(values):
    import numpy as np

    converted = np.empty(len(values), dtype=np.float64)
    flags = np.zeros(len(values), dtype=np.float64)
    counts = {"empty": 0, "invalid": 0, "nonfinite": 0, "overflow": 0}
    for index, value in enumerate(values):
        if value == "":
            counts["empty"] += 1
            number = math.nan
        else:
            try:
                number = float(value)
            except (ValueError, OverflowError):
                counts["invalid"] += 1
                number = math.nan
            else:
                if not math.isfinite(number):
                    key = "nonfinite" if value.strip().lower() in {
                        "nan", "+nan", "-nan", "inf", "+inf", "-inf",
                        "infinity", "+infinity", "-infinity"} else "overflow"
                    counts[key] += 1
        converted[index] = number
        if not math.isfinite(number):
            flags[index] = 1.0
    return converted, flags, counts


def _category(value):
    return "m:" if value == "" else "v:" + value


def _sparse_bytes(matrix):
    return matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes


class FittedPreprocessor:
    """A fitted recipe; transform never changes vocabulary or medians."""

    def __init__(self, view, recipe, medians, categories, encoder, text_models,
                 feature_names, fit_diagnostics):
        self.schema = view.schema
        self.recipe = recipe
        self._medians = dict(medians)
        self._categories = {name: tuple(values) for name, values in categories.items()}
        self._encoder = encoder
        self._text_models = dict(text_models)
        self.feature_names = tuple(feature_names)
        self.fit_diagnostics = json.loads(json.dumps(fit_diagnostics, allow_nan=False))
        self.fit_manifest = {
            "phase": view.phase, "source_sha256": view.source_sha256,
            "split_sha256": view.split_sha256,
            "fit_values_sha256": view.fit_values_sha256,
            "fit_rows": len(view.row_indices), "fit_indices_sha256": _sha(view.row_indices),
            "schema_sha256": self.schema.schema_sha256,
            "source_binding": view.source_binding,
            "source_identity_asserted_by_trusted_loader": view.source_binding == "caller_asserted_dataframe",
            "source_file_bytes_verified": view.source_binding == "verified_csv_bytes_and_explicit_partition",
            "active_split_binding": view.active_split_binding,
            "active_split_policy_verified": view.active_split_binding == "BUILT_MATCHED",
            "os_access_control_verified": False,
        }
        self.statistics_sha256 = _sha(self.statistics())

    def statistics(self):
        text = {}
        for name, model in self._text_models.items():
            text[name] = ({"empty_vocabulary": True, "vocabulary": [], "idf": []}
                          if model is None else {
                              "empty_vocabulary": False,
                              "vocabulary": sorted(model.vocabulary_.items(), key=lambda item: item[1]),
                              "idf": [float(value) for value in model.idf_],
                          })
        categories = dict(self._categories)
        if self._encoder is not None:
            categories = {name: tuple(str(value) for value in values)
                          for name, values in zip(self.schema.categorical_columns,
                                                 self._encoder.categories_)}
        return {
            "version": "preprocessing.v1", "schema": asdict(self.schema),
            "recipe": asdict(self.recipe), "numeric_medians": dict(self._medians),
            "categories": categories, "text": text,
            "feature_names": self.feature_names,
        }

    def audit(self):
        return {
            "schema_version": "preprocessing_audit.v1", **self.fit_manifest,
            "recipe_sha256": _sha(asdict(self.recipe)),
            "trained_statistics_sha256": self.statistics_sha256,
            "feature_order_sha256": _sha(self.feature_names),
            "feature_count": len(self.feature_names),
            "categorical_strategy": self.recipe.categorical_strategy,
            "missing_policy": self.schema.missing_policy,
            "fit_diagnostics": json.loads(json.dumps(self.fit_diagnostics)),
            "estimator_fitted": False, "api_used": False,
            "limits_are_cooperative_not_os_guarantees": True,
        }

    def transform(self, X_any, *, budget=None):
        import numpy as np
        import pandas as pd
        from scipy import sparse

        _require(budget)
        if _sha(self.statistics()) != self.statistics_sha256:
            raise PreprocessingError("trained_statistics_changed")
        _validate_frame(X_any, self.schema, self.recipe)
        n = len(X_any)
        diagnostics = {"rows": n, "numeric": {}, "categorical_unknown": {},
                       "text_truncated_cells": {}}
        parts, native = [], {}
        total_nnz = total_bytes = 0

        def add_part(part):
            nonlocal total_nnz, total_bytes
            part = sparse.csr_matrix(part, dtype=np.float64)
            if part.data.size and not np.isfinite(part.data).all():
                raise PreprocessingError("nonfinite_preprocessing_output")
            total_nnz += part.nnz
            total_bytes += _sparse_bytes(part)
            if total_nnz > self.recipe.max_output_nnz or total_bytes > self.recipe.max_output_bytes:
                raise PreprocessingError("preprocessing_sparse_memory_limit")
            parts.append(part)

        for index, name in enumerate(self.schema.numeric_columns):
            _require(budget)
            if n * 2 * 8 > self.recipe.max_output_bytes:
                raise PreprocessingError("preprocessing_output_memory_limit")
            values, indicator, counts = _numeric(X_any[name].tolist())
            values[indicator.astype(bool)] = self._medians[name]
            diagnostics["numeric"][name] = counts
            if self.recipe.categorical_strategy == "native":
                native[f"n{index}_value"] = values
                native[f"n{index}_missing"] = indicator
            else:
                add_part(np.column_stack((values, indicator)))

        if self.schema.categorical_columns:
            encoded_columns = []
            for index, name in enumerate(self.schema.categorical_columns):
                _require(budget)
                values = [_category(value) for value in X_any[name].array]
                known = set(self._categories[name])
                unknown = [value not in known for value in values]
                diagnostics["categorical_unknown"][name] = sum(unknown)
                if self.recipe.categorical_strategy == "native":
                    native[f"c{index}"] = ["u:" if flag else value for value, flag in zip(values, unknown)]
                else:
                    encoded_columns.append(values)
            if encoded_columns:
                add_part(self._encoder.transform(np.asarray(encoded_columns, dtype=object).T))

        for index, name in enumerate(self.schema.text_columns):
            _require(budget)
            values = X_any[name].tolist()
            diagnostics["text_truncated_cells"][name] = sum(
                len(value) > self.recipe.text_max_chars_per_cell for value in values)
            texts = [value[:self.recipe.text_max_chars_per_cell] for value in values]
            model = self._text_models[name]
            add_part(sparse.csr_matrix((n, 1), dtype=np.float64) if model is None else model.transform(texts))

        if self.recipe.categorical_strategy == "native":
            matrix = pd.DataFrame(native, index=X_any.index.copy())
            if int(matrix.memory_usage(index=True, deep=True).sum()) > self.recipe.max_output_bytes:
                raise PreprocessingError("preprocessing_output_memory_limit")
            categorical_indices = tuple(range(2 * len(self.schema.numeric_columns), matrix.shape[1]))
            format_name = "native_dataframe"
        else:
            matrix = sparse.hstack(parts, format="csr", dtype=np.float64)
            if matrix.nnz > self.recipe.max_output_nnz or _sparse_bytes(matrix) > self.recipe.max_output_bytes:
                raise PreprocessingError("preprocessing_sparse_memory_limit")
            categorical_indices = ()
            format_name = "csr"
        if matrix.shape != (n, len(self.feature_names)):
            raise PreprocessingError("preprocessing_shape_mismatch")
        if _sha(self.statistics()) != self.statistics_sha256:
            raise PreprocessingError("trained_statistics_changed")
        _require(budget)
        return PreparedData(matrix, tuple(X_any.index), self.feature_names, format_name,
                            diagnostics, self.statistics_sha256, categorical_indices)


def fit_transform(view, recipe=None, *, budget=None):
    """Fit a known preprocessing recipe exclusively on a trusted search T_fit.

    This function fits imputers/encoders/vectorizers, never an ML estimator.
    Frozen/full-development refit grants belong to a separate explicit phase.
    """
    import numpy as np
    from collections import Counter
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import OneHotEncoder

    _require(budget)
    recipe = PreprocessingRecipe() if recipe is None else recipe
    if not isinstance(recipe, PreprocessingRecipe):
        raise PreprocessingError("unknown_preprocessing_recipe")
    if (not isinstance(view, TrainFitView) or view._factory_token is not _FIT_VIEW_TOKEN
            or view.phase != "search_fit"):
        raise PreprocessingError("trusted_fit_view_required")
    if len(view.schema.text_columns) > recipe.max_text_columns:
        raise PreprocessingError("preprocessing_text_column_limit")
    if recipe.categorical_strategy == "native" and view.schema.text_columns:
        raise PreprocessingError("native_text_recipe_unsupported")
    frame = view.frame
    _validate_frame(frame, view.schema, recipe)
    if (len(frame) != len(view.row_indices)
            or _frame_sha(frame, view.schema.feature_columns, budget) != view.fit_values_sha256):
        raise PreprocessingError("fit_view_values_changed")
    medians, categories, text_models, feature_names = {}, {}, {}, []
    diagnostics = {"rows": len(frame), "numeric": {}, "all_missing_numeric": [],
                   "categorical_levels": {}, "text": {}}
    for index, name in enumerate(view.schema.numeric_columns):
        _require(budget)
        values, _, counts = _numeric(frame[name].tolist())
        finite = np.sort(values[np.isfinite(values)])
        if len(finite):
            middle = len(finite) // 2
            if len(finite) % 2:
                median = float(finite[middle])
            else:
                left, right = float(finite[middle - 1]), float(finite[middle])
                median = (left + (right - left) / 2 if (left >= 0) == (right >= 0)
                          else left / 2 + right / 2)
        else:
            median = 0.0
            diagnostics["all_missing_numeric"].append(name)
        if not math.isfinite(median):
            raise PreprocessingError("nonfinite_numeric_median")
        medians[name] = median
        diagnostics["numeric"][name] = counts
        feature_names.extend((f"n{index}_value", f"n{index}_missing"))

    total_categories = 0
    for index, name in enumerate(view.schema.categorical_columns):
        _require(budget)
        # A constant missing category is reserved even when fit has no blanks.
        # Prefixing real values avoids collisions with all reserved symbols.
        known = {"m:"}
        for value in frame[name].array:
            known.add(_category(value))
            if len(known) > recipe.max_categories_per_column:
                raise PreprocessingError("preprocessing_category_limit")
        total_categories += len(known)
        if total_categories > recipe.max_total_categories:
            raise PreprocessingError("preprocessing_category_limit")
        categories[name] = tuple(sorted(known))
        diagnostics["categorical_levels"][name] = len(known)
        feature_names.extend((f"c{index}",) if recipe.categorical_strategy == "native"
                             else (f"c{index}_{level}" for level in range(len(known))))
    encoder = None
    if view.schema.categorical_columns and recipe.categorical_strategy == "onehot":
        _require(budget)
        encoder = OneHotEncoder(categories=[list(categories[name]) for name in view.schema.categorical_columns],
                                handle_unknown="ignore", sparse_output=True, dtype=np.float64)
        values = np.asarray([[_category(value) for value in frame[name].array]
                             for name in view.schema.categorical_columns], dtype=object).T
        encoder.fit(values)

    for index, name in enumerate(view.schema.text_columns):
        _require(budget)
        raw = frame[name].tolist()
        texts = [value[:recipe.text_max_chars_per_cell] for value in raw]
        vectorizer = TfidfVectorizer(lowercase=True, ngram_range=(1, 1), dtype=np.float64)
        analyzer = vectorizer.build_analyzer()
        counts = Counter()
        for row_index, text in enumerate(texts):
            if row_index % 256 == 0:
                _require(budget)
            for term in analyzer(text):
                counts[term] += 1
                if len(counts) > recipe.text_candidate_terms_per_column:
                    raise PreprocessingError("preprocessing_text_vocabulary_limit")
        selected = [term for term, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
                    [:recipe.text_max_features_per_column]]
        vocabulary = {term: position for position, term in enumerate(sorted(selected))}
        if vocabulary:
            expected_nnz = 0
            for row_index, text in enumerate(texts):
                if row_index % 256 == 0:
                    _require(budget)
                expected_nnz += len({term for term in analyzer(text) if term in vocabulary})
                if (expected_nnz > recipe.max_output_nnz
                        or expected_nnz * 12 + (len(texts) + 1) * 4 > recipe.max_output_bytes):
                    raise PreprocessingError("preprocessing_sparse_memory_limit")
            vectorizer.set_params(vocabulary=vocabulary)
            vectorizer.fit(texts)
            text_models[name] = vectorizer
        else:
            text_models[name] = None
        diagnostics["text"][name] = {
            "candidate_terms": len(counts), "retained_terms": len(vocabulary),
            "empty_vocabulary": not bool(vocabulary),
            "truncated_cells": sum(len(value) > recipe.text_max_chars_per_cell for value in raw),
        }
        feature_names.extend(f"t{index}_{position}" for position in range(max(1, len(vocabulary))))
    if len(feature_names) > recipe.max_output_features:
        raise PreprocessingError("preprocessing_feature_limit")
    fitted = FittedPreprocessor(view, recipe, medians, categories, encoder, text_models,
                                feature_names, diagnostics)
    transformed = fitted.transform(frame, budget=budget)
    _require(budget)
    return fitted, transformed
