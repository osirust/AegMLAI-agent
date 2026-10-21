"""H03.1: read-only streaming diagnostics for an explicit trusted fit scope.

This module never chooses a split, fits preprocessing, reads protected labels
into statistics, or publishes files. Source validation reads all bytes; only
authorized fit rows and test features contribute to research diagnostics.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
import struct

from aegml_input import (InputError, MAX_CSV_BYTES, MAX_DICTIONARY_BYTES,
                         MAX_TASK_BYTES, _csv_reader, _dictionary, _sha256, _unchanged)


class ProfileError(Exception):
    """Fixed safe code, with metadata rather than source contents."""

    def __init__(self, code, details=None):
        super().__init__(code)
        self.code = code
        self.details = dict(details or {})


@dataclass(frozen=True)
class ProfileScope:
    fit_indices: tuple[int, ...]
    protected_indices: tuple[int, ...]
    train_rows: int
    train_sha256: str
    policy_id: str

    def __post_init__(self):
        if (type(self.train_rows) is not int or not 0 < self.train_rows <= 2_000_000
                or not isinstance(self.train_sha256, str)
                or re.fullmatch(r"[0-9a-f]{64}", self.train_sha256) is None
                or not isinstance(self.policy_id, str) or not self.policy_id.strip()
                or len(self.policy_id) > 128 or len(self.policy_id.encode("utf-8")) > 512):
            raise ProfileError("invalid_scope")
        parts = (self.fit_indices, self.protected_indices)
        if any(type(part) is not tuple for part in parts) or not self.fit_indices:
            raise ProfileError("invalid_scope")
        if any(type(i) is not int or not 0 <= i < self.train_rows for p in parts for i in p):
            raise ProfileError("invalid_scope")
        fit, protected = set(self.fit_indices), set(self.protected_indices)
        if (len(fit) != len(self.fit_indices) or len(protected) != len(self.protected_indices)
                or fit & protected or len(fit) + len(protected) != self.train_rows):
            raise ProfileError("invalid_scope")
        # Normalization is explicit: index order is never sampling order.
        object.__setattr__(self, "fit_indices", tuple(sorted(fit)))
        object.__setattr__(self, "protected_indices", tuple(sorted(protected)))


@dataclass(frozen=True)
class ProfileLimits:
    max_categories_per_column: int = 64
    max_category_chars: int = 128
    max_total_category_chars: int = 262144
    top_k: int = 10
    max_prompt_bytes: int = 32768
    max_report_bytes: int = 262144
    max_columns: int = 4096
    max_rows: int = 2_000_000
    max_csv_bytes: int = MAX_CSV_BYTES
    max_record_chars: int = 1 << 20

    def __post_init__(self):
        values = asdict(self)
        if any(type(v) is not int or v <= 0 for v in values.values()):
            raise ProfileError("invalid_limits")
        if (self.top_k > min(10, self.max_categories_per_column)
                or self.max_categories_per_column > 64 or self.max_category_chars > 128
                or self.max_total_category_chars > 262144
                or self.max_prompt_bytes > 32768 or self.max_report_bytes > 262144
                or self.max_record_chars > 1 << 20
                or self.max_columns > 4096
                or self.max_rows > 2_000_000 or self.max_csv_bytes > MAX_CSV_BYTES
                or self.max_prompt_bytes < 512 or self.max_report_bytes < 8192):
            raise ProfileError("invalid_limits")


def _require(budget):
    if budget is None or not callable(getattr(budget, "require", None)):
        raise ProfileError("budget_required")
    budget.require()


def _json(value, budget):
    """Canonical UTF-8 serialization checks the same work budget throughout."""
    chunks = []
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"), allow_nan=False)
    for number, chunk in enumerate(encoder.iterencode(value)):
        if number % 256 == 0:
            _require(budget)
        chunks.append(chunk)
    _require(budget)
    return "".join(chunks)


def _value_sha(value, budget):
    return hashlib.sha256(_json(value, budget).encode("utf-8")).hexdigest()


def _indices_sha(indices, budget):
    digest = hashlib.sha256(b"aegml-profile-indices-u64be-v1\0")
    for start in range(0, len(indices), 4096):
        _require(budget)
        block = indices[start:start + 4096]
        digest.update(struct.pack(">" + "Q" * len(block), *block))
    return digest.hexdigest()


class _Categories:
    def __init__(self, limits, retained):
        self.limits, self.retained = limits, retained
        self.counts = {}
        self.omitted_rows = 0

    def add(self, value):
        if value in self.counts:
            self.counts[value] += 1
        elif (len(value) <= self.limits.max_category_chars
              and len(self.counts) < self.limits.max_categories_per_column
              and self.retained[0] + len(value) <= self.limits.max_total_category_chars):
            self.counts[value] = 1
            self.retained[0] += len(value)
        else:
            # Values are not truncated into colliding synthetic categories.
            self.omitted_rows += 1

    def finish(self):
        complete = self.omitted_rows == 0
        count = len(self.counts)
        return {
            "retained_categories": count,
            "retained_characters": sum(map(len, self.counts)),
            "retention_complete": complete,
            "unretained_occurrences": self.omitted_rows,
            "distinct_count": count if complete else None,
            "distinct_count_exact": complete,
            "distinct_count_lower_bound": count + int(not complete),
            "top_scope": "all_values" if complete else "retained_first_seen_values_only",
            "global_top_exact": complete,
            "top": [{"value": key, "count": value} for key, value in
                    sorted(self.counts.items(), key=lambda item: (-item[1], item[0]))[:self.limits.top_k]],
        }


class _Column:
    def __init__(self, mode, limits, retained):
        self.mode = mode
        self.rows = self.missing = self.invalid = self.nonfinite = self.finite = 0
        self.minimum = self.maximum = self.mean = None
        self.m2, self.moments_ok = 0.0, True
        self.categories = _Categories(limits, retained) if mode in {"auto", "categorical", "text"} else None
        self.length_min = self.length_max = None

    def add(self, value):
        self.rows += 1
        if value == "":
            self.missing += 1
            return
        if self.mode == "redacted":
            return
        if self.categories is not None:
            self.categories.add(value)
            length = len(value)
            self.length_min = length if self.length_min is None else min(self.length_min, length)
            self.length_max = length if self.length_max is None else max(self.length_max, length)
        if self.mode not in {"numeric", "auto"}:
            return
        try:
            # Whitespace-only is a literal invalid numeric value, not missing.
            number = float(value)
        except (ValueError, OverflowError):
            self.invalid += 1
            return
        if not math.isfinite(number):
            self.nonfinite += 1
            return
        self.finite += 1
        self.minimum = number if self.minimum is None else min(self.minimum, number)
        self.maximum = number if self.maximum is None else max(self.maximum, number)
        if self.mean is None:
            self.mean = number
        elif self.moments_ok:
            delta = number - self.mean
            updated = self.mean + delta / self.finite
            m2 = self.m2 + delta * (number - updated)
            if all(math.isfinite(v) for v in (delta, updated, m2)):
                self.mean, self.m2 = updated, m2
            else:
                self.moments_ok = False

    def inferred_kind(self):
        if self.mode != "auto":
            return self.mode
        return "numeric" if self.rows > self.missing and self.invalid == 0 else "categorical"

    def finish(self, kind):
        result = {"rows": self.rows, "missing": self.missing,
                  "missing_rate": self.missing / self.rows if self.rows else None,
                  "nonmissing": self.rows - self.missing}
        if kind == "numeric":
            variance = self.m2 / (self.finite - 1) if self.finite > 1 and self.moments_ok else None
            result["numeric"] = {
                "finite": self.finite, "invalid": self.invalid, "nonfinite": self.nonfinite,
                "min": self.minimum, "max": self.maximum,
                "mean": self.mean if self.moments_ok else None,
                "sample_std": math.sqrt(max(0.0, variance)) if variance is not None else None,
                "moments_status": "finite" if self.moments_ok else "overflow_unavailable",
            }
        elif kind in {"categorical", "text"}:
            result["categories"] = self.categories.finish()
            result["length"] = {"min": self.length_min, "max": self.length_max}
        return result


def _finite_difference(left, right):
    if left is None or right is None:
        return None
    result = left - right
    return result if math.isfinite(result) else None


def _pack_research(base, columns, maximum, budget):
    """Prefix choice depends only on research bytes, never on source metadata."""
    def candidate(count):
        return {**base, "columns": columns[:count],
                "truncation": {"columns_total": len(columns), "columns_included": count,
                               "columns_omitted": len(columns) - count, "truncated": count < len(columns)}}

    low, high = 0, len(columns)
    if len(_json(candidate(0), budget).encode("utf-8")) > maximum:
        raise ProfileError("report_limit_too_small")
    while low < high:
        _require(budget)
        middle = (low + high + 1) // 2
        if len(_json(candidate(middle), budget).encode("utf-8")) <= maximum:
            low = middle
        else:
            high = middle - 1
    return candidate(low)


def _profile(bundle, contract, scope, budget, limits):
    _require(budget)
    if not isinstance(scope, ProfileScope) or not isinstance(limits, ProfileLimits):
        raise ProfileError("invalid_scope" if not isinstance(scope, ProfileScope) else "invalid_limits")
    payload = contract.to_dict()
    from aegml_schemas import SchemaError, validate_task_contract
    try:
        validate_task_contract(payload)
    except SchemaError:
        raise ProfileError("schema_mismatch") from None
    roles = ("task", "train", "test", "data_dictionary", "sample_submission")
    if (set(bundle.source_sha256) != set(roles)
            or payload["provenance"]["source_sha256"] != bundle.source_sha256):
        raise ProfileError("contract_source_mismatch")
    if scope.train_sha256 != bundle.source_sha256["train"]:
        raise ProfileError("scope_source_mismatch")
    if scope.train_rows > limits.max_rows:
        raise ProfileError("row_limit_exceeded")
    root = bundle.task_path.parent
    paths = {"task": bundle.task_path, **bundle.files}
    if (payload["task_path"] != str(bundle.task_path)
            or payload["input_paths"] != {role: str(path) for role, path in bundle.files.items()}):
        raise ProfileError("schema_mismatch")
    before = {}
    for role in roles:
        _require(budget)
        expected = bundle.provenance[role]["stat"]
        _unchanged(paths[role], root, role, expected)
        before[role] = dict(expected)
    headers = bundle.headers
    if any(len(header) > limits.max_columns for header in headers.values()):
        raise ProfileError("column_limit_exceeded")
    target = payload["target_columns"]
    identifiers = payload["id_columns"]
    features = payload["feature_columns"]
    declared = {row["feature"]: row for row in bundle.dictionary_rows}
    ignored = {name for name, row in declared.items() if row["role"] == "ignore"}
    expected_features = [name for name in headers["train"] if name not in {*target, *identifiers, *ignored}]
    if (features != expected_features or any(name not in headers["train"] for name in target)
            or any(name in headers["test"] for name in target)
            or set(features) != set(headers["test"]) - set(identifiers) - ignored):
        raise ProfileError("schema_mismatch")
    mapping_counts = payload["provenance"]["row_mapping"]["row_counts"]
    if mapping_counts["train"] != scope.train_rows:
        raise ProfileError("row_count_mismatch")
    schema = {"headers": {role: list(value) for role, value in headers.items()},
              "dictionary": [{key: row[key] for key in ("feature", "role", "dtype")} for row in bundle.dictionary_rows],
              "target_columns": target, "id_columns": identifiers, "feature_columns": features,
              "task_type": payload["task_type"], "metric": payload["metric"]}
    # Short metadata is fully authenticated too; sample values are never stats.
    for role, maximum in (("task", MAX_TASK_BYTES), ("data_dictionary", MAX_DICTIONARY_BYTES),
                          ("sample_submission", limits.max_csv_bytes)):
        if _sha256(paths[role], root, role, maximum, budget) != bundle.source_sha256[role]:
            raise ProfileError("source_changed", {"role": role})
    if _dictionary(paths["data_dictionary"], root, budget, bundle.source_sha256["data_dictionary"]) != bundle.dictionary_rows:
        raise ProfileError("schema_mismatch", {"role": "data_dictionary"})

    retained = [0]
    columns = []
    # Keep the target and actual model features ahead of ID/ignored metadata.
    ordered = list(dict.fromkeys([*target, *features, *headers["train"]]))
    for index, name in enumerate(ordered):
        if index % 32 == 0:
            _require(budget)
        row = declared.get(name, {})
        role = "target" if name in target else "id" if name in identifiers else row.get("role", "feature")
        dtype = row.get("dtype", "").casefold()
        if role in {"id", "ignore"}:
            mode = "redacted"
        elif role == "target":
            mode = "numeric" if payload["task_type"] == "regression" else "categorical"
        elif dtype in {"numeric", "number", "float", "float32", "float64", "int", "integer", "int32", "int64", "double"}:
            mode = "numeric"
        elif dtype in {"text", "string", "str"}:
            mode = "text"
        elif dtype in {"category", "categorical", "bool", "boolean"}:
            mode = "categorical"
        else:
            mode = "auto"
        columns.append({"name": name, "role": role, "declared_dtype": row.get("dtype", ""),
                        "mode": mode, "fit_acc": _Column(mode, limits, retained),
                        "test_acc": _Column(mode, limits, retained) if name in headers["test"] else None,
                        "not_in_retained_fit": 0})
    fit = set(scope.fit_indices)
    for role in ("train", "test"):
        projection = [(headers[role].index(col["name"]), col) for col in columns if col["name"] in headers[role]]
        count = 0
        with _csv_reader(paths[role], root, role, limits.max_csv_bytes, budget,
                         expected_sha=bundle.source_sha256[role],
                         max_record_chars=limits.max_record_chars) as (reader, header):
            if header != headers[role]:
                raise ProfileError("schema_mismatch", {"role": role})
            for index, values in enumerate(reader):
                if index % 256 == 0:
                    _require(budget)
                count += 1
                if count > limits.max_rows:
                    raise ProfileError("row_limit_exceeded", {"role": role})
                if len(values) != len(header):
                    raise ProfileError("csv_field_count", {"role": role})
                if role == "train" and index not in fit:
                    continue  # Structural audit only; no protected field is interpreted.
                for position, col in projection:
                    accumulator = col["fit_acc"] if role == "train" else col["test_acc"]
                    value = values[position]
                    accumulator.add(value)
                    categories = col["fit_acc"].categories
                    if role == "test" and categories is not None and value != "" and value not in categories.counts:
                        col["not_in_retained_fit"] += 1
        if count != (scope.train_rows if role == "train" else mapping_counts["test"]):
            raise ProfileError("row_count_mismatch", {"role": role})
    for role in roles:
        _require(budget)
        _unchanged(paths[role], root, role, before[role])

    finished = []
    for index, col in enumerate(columns):
        if index % 16 == 0:
            _require(budget)
        kind = col["fit_acc"].inferred_kind()
        fit_stats = col["fit_acc"].finish(kind)
        test_stats = col["test_acc"].finish(kind) if col["test_acc"] is not None else None
        shift = None
        if test_stats is not None and col["role"] not in {"id", "ignore"}:
            shift = {"diagnostic_only": True,
                     "missing_rate_delta": _finite_difference(test_stats["missing_rate"], fit_stats["missing_rate"])}
            if kind == "numeric":
                shift["mean_delta"] = _finite_difference(test_stats["numeric"]["mean"], fit_stats["numeric"]["mean"])
            else:
                complete = fit_stats["categories"]["retention_complete"]
                shift.update(unseen_count=col["not_in_retained_fit"] if complete else None,
                             unseen_exact=complete,
                             unseen_status="exact_fit_vocabulary" if complete else "unknown_incomplete_fit_vocabulary")
        finished.append({"name": col["name"], "role": col["role"], "declared_dtype": col["declared_dtype"],
                         "kind": kind, "fit": fit_stats, "test": test_stats, "shift": shift})
    base = {"schema_version": "profile.research.v1", "rows": {"fit": len(fit), "test": mapping_counts["test"]},
            "missing_policy": "empty_string_only", "test_use": "diagnostics_only_no_fit",
            "retained_category_characters": retained[0]}
    # Metadata gets a fixed 4 KiB reservation; changing a source SHA/stat can
    # never decide which research columns or prompt bytes survive truncation.
    prompt_budget = min(limits.max_prompt_bytes, (limits.max_report_bytes - 4096) // 4)
    research_budget = limits.max_report_bytes - 2 * prompt_budget - 4096
    research = _pack_research(base, finished, research_budget, budget)
    prompt_research = _pack_research(base, finished, prompt_budget, budget)
    prompt = _json(prompt_research, budget)
    result = {
        "schema_version": "profile.v1", "research": research, "prompt": prompt,
        "prompt_bytes": len(prompt.encode("utf-8")),
        "provenance": {"source_sha256": dict(bundle.source_sha256), "source_stat": before,
                       "schema_sha256": _value_sha(schema, budget), "contract_sha256": _value_sha(payload, budget),
                       "scope": {"policy_id": scope.policy_id, "train_rows": scope.train_rows,
                                 "fit_count": len(scope.fit_indices), "protected_count": len(scope.protected_indices),
                                 "fit_indices_sha256": _indices_sha(scope.fit_indices, budget),
                                 "protected_indices_sha256": _indices_sha(scope.protected_indices, budget)},
                       "stability": "hashes_of_consumed_sources_and_before_after_stat_guard"},
        "truncation": {"research": research["truncation"], "prompt": prompt_research["truncation"],
                       "effective_prompt_byte_limit": prompt_budget,
                       "retention_complete": all(acc.categories is None or acc.categories.omitted_rows == 0
                                                 for col in columns for acc in (col["fit_acc"], col["test_acc"])
                                                 if acc is not None)},
        "limits": asdict(limits), "report_bytes": 0,
    }
    for _ in range(8):
        _require(budget)
        size = len(_json(result, budget).encode("utf-8"))
        if size == result["report_bytes"]:
            break
        result["report_bytes"] = size
    if size > limits.max_report_bytes:
        raise ProfileError("report_limit_too_small")
    return result


def profile_task(bundle, contract, scope, *, budget, limits=ProfileLimits()):
    """Return bounded data-only diagnostics; budget exhaustion propagates.

    Scope is an input from a trusted controller, not a split inferred here.
    InputError codes stay fixed and safe; source rows never enter exceptions.
    """
    try:
        return _profile(bundle, contract, scope, budget, limits)
    except InputError as exc:
        raise ProfileError(exc.code, exc.details) from None
    except (KeyError, AttributeError, TypeError):
        raise ProfileError("schema_mismatch") from None
