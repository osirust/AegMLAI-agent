"""Trusted bounded CSV validation/publication. No model or provider calls.

Internal predictions are indexed in original test order. The trusted contract
alone selects output order and raw-string IDs; sample values are never answers.
"""

from dataclasses import dataclass, field
import csv
import hashlib
import io
import json
import math
import numbers
import os
from pathlib import Path
import stat
import tempfile

from aegml_input import MAX_CSV_BYTES, MAX_ROWS, InputError, _csv_reader


class SubmissionError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SubmissionLimits:
    max_bytes: int = 1 << 30
    max_rows: int = 2_000_000
    max_record_chars: int = 1 << 20
    max_value_chars: int = 4096
    max_id_chars: int = 128 << 20
    probability_tolerance: float = 1e-6

    def __post_init__(self):
        for name in ("max_bytes", "max_rows", "max_record_chars", "max_value_chars", "max_id_chars"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise SubmissionError("invalid_submission_limits")
        if (type(self.probability_tolerance) not in (int, float)
                or not 0 <= self.probability_tolerance <= 1e-3 or not math.isfinite(self.probability_tolerance)):
            raise SubmissionError("invalid_submission_limits")


@dataclass(frozen=True)
class SubmissionSchema:
    output_path: Path = field(repr=False)
    columns: tuple[str, ...]
    id_columns: tuple[str, ...]
    value_columns: tuple[str, ...]
    kind: str
    metric_name: str
    class_order: tuple
    positive_label: object
    allowed_label_tokens: frozenset[str] = field(repr=False)
    expected_ids: tuple[tuple[str, ...], ...] = field(repr=False)
    output_to_test: tuple[int, ...] = field(repr=False)
    source_sha256: tuple[tuple[str, str], ...]
    limits: SubmissionLimits = field(default_factory=SubmissionLimits)

    def __post_init__(self):
        if not isinstance(self.limits, SubmissionLimits) or not isinstance(self.output_path, Path):
            raise SubmissionError("invalid_submission_schema")
        for name in ("columns", "id_columns", "value_columns", "class_order", "expected_ids", "output_to_test", "source_sha256"):
            if not isinstance(getattr(self, name), tuple):
                raise SubmissionError("invalid_submission_schema")
        if not isinstance(self.allowed_label_tokens, frozenset):
            raise SubmissionError("invalid_submission_schema")
        if not self.output_path.is_absolute() or self.output_path.name != "submission.csv":
            raise SubmissionError("invalid_submission_schema")
        if (not self.columns or len(set(self.columns)) != len(self.columns)
                or any(not isinstance(c, str) or not c for c in self.columns)
                or set(self.id_columns) & set(self.value_columns)
                or set(self.columns) != set(self.id_columns + self.value_columns)):
            raise SubmissionError("invalid_submission_schema")
        n = len(self.output_to_test)
        if (not 0 < n <= self.limits.max_rows or len(self.expected_ids) != n
                or any(type(i) is not int for i in self.output_to_test)
                or set(self.output_to_test) != set(range(n))
                or any(len(key) != len(self.id_columns) or any(not isinstance(v, str) or not v.strip()
                       or len(v) > self.limits.max_value_chars or "\x00" in v for v in key) for key in self.expected_ids)):
            raise SubmissionError("invalid_submission_schema")
        if self.id_columns and len(set(self.expected_ids)) != n:
            raise SubmissionError("invalid_submission_schema")
        expected_kind = ("numeric" if self.metric_name in {"rmse", "mae"} else "probability"
                         if self.metric_name in {"log_loss", "roc_auc"} else "label"
                         if self.metric_name in {"accuracy", "macro_f1", "weighted_f1", "binary_f1"} else None)
        if self.kind != expected_kind or not self.value_columns:
            raise SubmissionError("invalid_submission_schema")
        if self.metric_name == "log_loss":
            if len(self.class_order) != len(self.value_columns) or len(self.class_order) < 2:
                raise SubmissionError("invalid_submission_schema")
        elif len(self.value_columns) != 1:
            raise SubmissionError("invalid_submission_schema")
        if self.kind == "label" and not self.allowed_label_tokens:
            raise SubmissionError("missing_fit_label_vocabulary")
        if self.metric_name == "roc_auc" and self.positive_label is None:
            raise SubmissionError("missing_positive_label")

    @property
    def row_count(self):
        return len(self.output_to_test)

    def summary(self, *, budget, finalizing=False):
        _require(budget, finalizing)
        digest = hashlib.sha256()
        encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        for index, chunk in enumerate(encoder.iterencode(self.expected_ids)):
            if index % 256 == 0:
                _require(budget, finalizing)
            digest.update(chunk.encode("utf-8"))
        _require(budget, finalizing)
        return {"columns": list(self.columns), "id_columns": list(self.id_columns),
                "value_columns": list(self.value_columns), "kind": self.kind,
                "row_count": self.row_count, "expected_ids_sha256": digest.hexdigest(),
                "class_order": list(self.class_order), "positive_label": self.positive_label,
                "source_sha256": dict(self.source_sha256)}


def _require(budget, finalizing=False):
    if budget is None or not callable(getattr(budget, "require", None)):
        raise SubmissionError("missing_shared_budget")
    budget.require(finalizing=finalizing)


def _token(value, limits):
    if isinstance(value, str):
        token = value
    elif isinstance(value, numbers.Integral) and not isinstance(value, (bool,)):
        token = str(int(value))
    elif isinstance(value, numbers.Real) and not isinstance(value, (bool,)):
        number = float(value)
        if not math.isfinite(number):
            raise SubmissionError("nonfinite_prediction")
        token = str(number)
    else:
        raise SubmissionError("invalid_label_type")
    if not token.strip() or len(token) > limits.max_value_chars or "\x00" in token:
        raise SubmissionError("invalid_label_value")
    return token


def _mapping_digest(values, budget):
    """Match TaskContract canonical JSON without materializing another array."""
    digest = hashlib.sha256()
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"), allow_nan=False)
    for index, chunk in enumerate(encoder.iterencode(values)):
        if index % 256 == 0:
            _require(budget)
        digest.update(chunk.encode("utf-8"))
    _require(budget)
    return digest.hexdigest()


def build_submission_schema(bundle, contract, *, budget, allowed_labels=None,
                            limits=SubmissionLimits()):
    """Read only test/sample IDs; caller supplies fit-side label vocabulary."""
    _require(budget)
    if not isinstance(limits, SubmissionLimits):
        raise SubmissionError("invalid_submission_limits")
    payload, alignment = contract.to_dict(), contract.alignment
    from aegml_schemas import validate_task_contract
    validate_task_contract(payload)
    if payload["provenance"]["source_sha256"] != bundle.source_sha256:
        raise SubmissionError("contract_source_mismatch")
    if (payload["task_path"] != str(bundle.task_path)
            or payload["input_paths"] != {role: str(path) for role, path in bundle.files.items()}
            or payload["output_path"] != str(bundle.task_path.parent / "submission.csv")):
        raise SubmissionError("contract_task_destination_mismatch")
    ids = tuple(payload["id_columns"])
    prediction = payload["prediction_schema"]
    columns = tuple(prediction["columns"])
    values = tuple(c for c in columns if c not in ids)
    name = payload["metric"]["name"]
    kind = prediction["kind"]
    class_order = tuple(payload["metric"]["class_order"] or ())
    mapping = tuple(alignment["output_to_test"])
    n = alignment["row_counts"]["test"]
    if (type(n) is not int or not 0 < n <= min(limits.max_rows, MAX_ROWS)
            or len(mapping) != n or any(type(i) is not int for i in mapping)
            or set(mapping) != set(range(n))):
        raise SubmissionError("invalid_output_mapping")
    provenance = payload["provenance"]["row_mapping"]
    order = prediction["output_order"]
    if (alignment["row_counts"] != provenance["row_counts"]
            or any(type(v) is not int or v <= 0 for v in alignment["row_counts"].values())
            or alignment["id_columns"] != list(ids)
            or alignment["output_order"] != order or provenance["output_order"] != order
            or type(alignment["positional"]) is not bool
            or alignment["positional"] != provenance["positional"]
            or prediction["id_policy"]["mapping"] != ("position" if alignment["positional"] else "one_to_one")):
        raise SubmissionError("mapping_contract_mismatch")
    for key in ("sample_to_test", "output_to_test"):
        candidate = alignment[key]
        if (not isinstance(candidate, (list, tuple)) or len(candidate) != n
                or any(type(i) is not int for i in candidate) or set(candidate) != set(range(n))
                or provenance[key]["count"] != n
                or _mapping_digest(candidate, budget) != provenance[key]["sha256"]):
            raise SubmissionError("mapping_provenance_mismatch")
    if order == "test" and any(index != value for index, value in enumerate(mapping)):
        raise SubmissionError("mapping_output_order_mismatch")
    if not columns or len(set(columns)) != len(columns) or not values:
        raise SubmissionError("invalid_output_schema")
    if (kind != "probability" or name == "roc_auc") and values != tuple(payload["target_columns"]):
        raise SubmissionError("invalid_output_schema")
    if name == "log_loss" and (len(class_order) < 2 or len(values) != len(class_order)):
        raise SubmissionError("missing_probability_class_mapping")
    retained, loaded = 0, {}
    root = bundle.task_path.parent
    try:
        for role in ("test", "sample_submission"):
            keys = []
            with _csv_reader(bundle.files[role], root, role, MAX_CSV_BYTES, budget,
                             expected_sha=bundle.source_sha256[role]) as (reader, header):
                if header != bundle.headers[role]:
                    raise SubmissionError("input_header_changed")
                positions = [header.index(c) for c in ids] if all(c in header for c in ids) else None
                for row in reader:
                    if len(keys) % 256 == 0:
                        _require(budget)
                    if len(row) != len(header) or len(keys) >= n:
                        raise SubmissionError("input_shape_changed")
                    key = tuple(row[i] for i in positions) if positions is not None else None
                    if key is not None and any(not t.strip() or "\x00" in t or len(t) > limits.max_value_chars for t in key):
                        raise SubmissionError("invalid_source_id")
                    retained += sum(map(len, key or ()))
                    if retained > limits.max_id_chars:
                        raise SubmissionError("id_memory_limit")
                    keys.append(key)
            if len(keys) != n:
                raise SubmissionError("input_shape_changed")
            loaded[role] = keys
    except InputError as exc:
        raise SubmissionError(exc.code) from None
    if any(k is None for k in loaded["sample_submission"]):
        raise SubmissionError("missing_output_id")
    keyed = bool(ids) and all(k is not None for k in loaded["test"])
    if keyed == alignment["positional"]:
        raise SubmissionError("mapping_id_policy_mismatch")
    if keyed:
        test_index = {}
        for index, key in enumerate(loaded["test"]):
            if index % 256 == 0:
                _require(budget)
            if key in test_index:
                raise SubmissionError("duplicate_source_id")
            test_index[key] = index
        sample_keys = loaded["sample_submission"]
        if len(set(sample_keys)) != n or set(sample_keys) != set(test_index):
            raise SubmissionError("sample_test_id_mismatch")
        actual_sample = tuple(test_index[key] for key in sample_keys)
        test_keys = loaded["test"]
    else:
        if not alignment["positional"]:
            raise SubmissionError("missing_output_id")
        # Positional mode is explicitly approved by TaskContract, never inferred.
        test_keys = loaded["sample_submission"]
        actual_sample = tuple(range(n))
    if tuple(alignment["sample_to_test"]) != actual_sample:
        raise SubmissionError("mapping_source_ids_mismatch")
    if order == "sample" and mapping != actual_sample:
        raise SubmissionError("mapping_output_order_mismatch")
    output_ids = tuple(test_keys[i] for i in mapping)
    if ids and len(set(output_ids)) != n:
        raise SubmissionError("duplicate_output_id")
    allowed = frozenset()
    if kind == "label":
        if isinstance(allowed_labels, (str, bytes)):
            raise SubmissionError("invalid_fit_label_vocabulary")
        labels = class_order if allowed_labels is None else tuple(allowed_labels)
        if not labels:
            raise SubmissionError("missing_fit_label_vocabulary")
        allowed = frozenset(_token(v, limits) for v in labels)
        if len(allowed) != len(labels):
            raise SubmissionError("ambiguous_label_serialization")
    _require(budget)
    return SubmissionSchema(Path(payload["output_path"]), columns, ids, values, kind, name,
                            class_order, payload["metric"]["positive_label"], allowed,
                            output_ids, mapping, tuple(sorted(bundle.source_sha256.items())), limits)


class _HashReader(io.RawIOBase):
    def __init__(self, source, limit, budget, finalizing):
        self.source, self.limit, self.budget, self.finalizing = source, limit, budget, finalizing
        self.total = 0
        self.digest = hashlib.sha256()

    def readable(self):
        return True

    def readinto(self, buffer):
        _require(self.budget, self.finalizing)
        block = self.source.read(min(len(buffer), self.limit - self.total + 1))
        self.total += len(block)
        if self.total > self.limit:
            raise SubmissionError("submission_too_large")
        self.digest.update(block)
        buffer[:len(block)] = block
        return len(block)


class _RecordLines:
    def __init__(self, text, limit, budget, finalizing):
        self.text, self.limit, self.budget, self.finalizing = text, limit, budget, finalizing
        self.chars = 0

    def __iter__(self):
        return self

    def __next__(self):
        _require(self.budget, self.finalizing)
        line = self.text.readline(self.limit + 1)
        if not line:
            raise StopIteration
        self.chars += len(line)
        if self.chars > self.limit:
            raise SubmissionError("csv_record_too_large")
        return line


def _number_text(value):
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        raise SubmissionError("invalid_numeric_prediction") from None
    if not math.isfinite(number):
        raise SubmissionError("nonfinite_prediction")
    return number


def _validate_values(values, schema):
    if any(not isinstance(v, str) or not v.strip() or len(v) > schema.limits.max_value_chars or "\x00" in v for v in values):
        raise SubmissionError("invalid_prediction_value")
    if schema.kind == "label":
        if values[0] not in schema.allowed_label_tokens:
            raise SubmissionError("unknown_class")
        return
    numbers_ = [_number_text(v) for v in values]
    if schema.kind == "probability":
        if any(v < 0 or v > 1 for v in numbers_):
            raise SubmissionError("probability_out_of_range")
        if schema.metric_name == "log_loss" and abs(math.fsum(numbers_) - 1) > schema.limits.probability_tolerance:
            raise SubmissionError("probability_sum_mismatch")


def validate_submission(path, schema, *, budget, expected_sha256=None, finalizing=False):
    """Independent bounded parser, returning metadata without IDs or predictions."""
    _require(budget, finalizing)
    path = Path(path)
    if path.parent.resolve() != schema.output_path.parent.resolve():
        raise SubmissionError("external_submission_path")
    descriptor = None
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise SubmissionError("non_regular_submission")
        if not 0 < info.st_size <= schema.limits.max_bytes:
            raise SubmissionError("empty_submission" if info.st_size == 0 else "submission_too_large")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino) or not stat.S_ISREG(opened.st_mode):
            raise SubmissionError("submission_changed")
        with os.fdopen(descriptor, "rb") as binary:
            descriptor = None
            checked = _HashReader(binary, schema.limits.max_bytes, budget, finalizing)
            with io.TextIOWrapper(io.BufferedReader(checked), encoding="utf-8-sig", newline="") as text:
                lines = _RecordLines(text, schema.limits.max_record_chars, budget, finalizing)
                reader = csv.reader(lines, strict=True)
                header = tuple(next(reader, ()))
                if header != schema.columns:
                    raise SubmissionError("submission_header_mismatch")
                id_pos = [header.index(c) for c in schema.id_columns]
                value_pos = [header.index(c) for c in schema.value_columns]
                count = 0
                while True:
                    lines.chars = 0
                    row = next(reader, None)
                    if row is None:
                        break
                    if count >= schema.row_count or len(row) != len(header):
                        raise SubmissionError("submission_row_count_or_width")
                    if tuple(row[i] for i in id_pos) != schema.expected_ids[count]:
                        raise SubmissionError("submission_id_order_mismatch")
                    _validate_values([row[i] for i in value_pos], schema)
                    count += 1
                final_stat = os.fstat(binary.fileno())
                digest, size = checked.digest.hexdigest(), checked.total
            if count != schema.row_count:
                raise SubmissionError("submission_row_count_mismatch")
        now = path.lstat()
        initial_identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if any((v.st_dev, v.st_ino, v.st_size, v.st_mtime_ns, v.st_ctime_ns) != initial_identity for v in (final_stat, now)):
            raise SubmissionError("submission_changed")
        if expected_sha256 is not None and digest != expected_sha256:
            raise SubmissionError("submission_sha_mismatch")
        _require(budget, finalizing)
        return {"status": "VALID_SUBMISSION_SNAPSHOT", "row_count": count, "bytes": size,
                "sha256": digest, "schema": schema.summary(budget=budget, finalizing=finalizing)}
    except (OSError, UnicodeError, csv.Error):
        raise SubmissionError("submission_io_or_csv_error") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _remove_owned(path, identity):
    try:
        current = path.lstat()
        if stat.S_ISREG(current.st_mode) and (current.st_dev, current.st_ino) == identity:
            path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def write_submission(predictions, schema, *, budget, prediction_class_order=None,
                     prediction_positive_label=None):
    """Validate a fresh file then atomically replace submission.csv.

    Last valid output survives pre-publication errors. Directory-fsync failure
    after a successful replace is recorded as a durability warning: the newly
    published, already validated file remains valid; no unsafe rollback occurs.
    """
    _require(budget, True)
    if not hasattr(predictions, "__len__") or not hasattr(predictions, "__getitem__") or len(predictions) != schema.row_count:
        raise SubmissionError("prediction_row_count_mismatch")
    if schema.metric_name == "log_loss" and tuple(() if prediction_class_order is None else prediction_class_order) != schema.class_order:
        raise SubmissionError("prediction_class_order_mismatch")
    if schema.metric_name == "roc_auc" and prediction_positive_label != schema.positive_label:
        raise SubmissionError("prediction_positive_label_mismatch")
    target = schema.output_path
    if target.name != "submission.csv" or target.is_symlink():
        raise SubmissionError("unsafe_submission_output")
    temporary = None
    identity = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=".aegml-submission-", suffix=".csv", dir=target.parent)
        temporary = Path(name)
        owned = os.fstat(descriptor)
        identity = (owned.st_dev, owned.st_ino)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(schema.columns)
            for output_index, test_index in enumerate(schema.output_to_test):
                if output_index % 128 == 0:
                    _require(budget, True)
                item = predictions[test_index]
                if schema.metric_name == "log_loss":
                    if not hasattr(item, "__len__") or len(item) != len(schema.value_columns):
                        raise SubmissionError("prediction_probability_width")
                    if any(isinstance(v, (str, bytes, bool)) or not isinstance(v, numbers.Real) for v in item):
                        raise SubmissionError("invalid_numeric_prediction_type")
                    cells = [format(_number_text(v), ".17g") for v in item]
                elif schema.kind == "label":
                    cells = [_token(item, schema.limits)]
                else:
                    if isinstance(item, (str, bytes, bool)) or not isinstance(item, numbers.Real):
                        raise SubmissionError("invalid_numeric_prediction_type")
                    cells = [format(_number_text(item), ".17g")]
                _validate_values(cells, schema)
                values = dict(zip(schema.id_columns, schema.expected_ids[output_index]))
                values.update(zip(schema.value_columns, cells))
                writer.writerow([values[c] for c in schema.columns])
                if stream.tell() > schema.limits.max_bytes:
                    raise SubmissionError("submission_too_large")
            stream.flush()
            os.fsync(stream.fileno())
        snapshot = validate_submission(temporary, schema, budget=budget, finalizing=True)
        _require(budget, True)
        os.replace(temporary, target)
        warning = None
        directory = None
        try:
            directory = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            os.fsync(directory)
        except OSError:
            warning = "directory_fsync_unconfirmed_after_valid_replace"
        finally:
            if directory is not None:
                os.close(directory)
        return {**snapshot, "status": "PUBLISHED_VALID_SUBMISSION", "published": True,
                "file_fsynced": True, "directory_fsynced": warning is None,
                "warning": warning, "prediction_input_order": "test",
                "source_sha256": dict(schema.source_sha256)}
    except OSError:
        raise SubmissionError("submission_publication_io_error") from None
    finally:
        if temporary is not None:
            _remove_owned(temporary, identity)
