"""Bounded, read-only CSV discovery and row/identifier checks for H02.3.

No model, metric inference, API, or data transformation belongs in this module.
The optional budget is duck typed so importing input helpers does not import the
controller. InputError messages contain fixed codes, never input contents.
"""

from contextlib import contextmanager
import csv
from dataclasses import dataclass, field
import hashlib
import io
import os
from pathlib import Path, PureWindowsPath
import re
import stat
from typing import Sequence


MAX_TASK_BYTES = 1 << 20
MAX_DICTIONARY_BYTES = 4 << 20
MAX_CSV_BYTES = 1 << 30
MAX_ROWS = 2_000_000
MAX_DISCOVERY_ENTRIES = 100_000
MAX_HEADER_COLUMNS = 4096
MAX_HEADER_NAME_CHARS = 256
MAX_HEADER_CHARS = 1 << 20
MAX_CSV_LINE_CHARS = 4 << 20
MAX_CSV_RECORD_CHARS = 1 << 20
MAX_ID_CHARS = 4096
MAX_RETAINED_ID_CHARS = 128 << 20
_CHUNK_BYTES = 1 << 16
_FILENAMES = {
    "train": "train.csv",
    "test": "test.csv",
    "data_dictionary": "data_dictionary.csv",
    "sample_submission": "sample_submission.csv",
}
_BASENAME_ROLE = {name: role for role, name in _FILENAMES.items()}
_DICTIONARY_ROLES = frozenset({"feature", "target", "id", "ignore", "group", "time"})
_BACKTICK_REF = re.compile(r"`([^`\r\n]+\.csv(?:[?#][^`\r\n]*)?)`")
_MARKDOWN_REF = re.compile(r"\]\(\s*(?:<([^>\r\n]+)>|([^\s)]+))(?:\s+[^)]*)?\)")


class InputError(Exception):
    """Safe reason code; details are metadata, never a row or raw task text."""

    def __init__(self, code: str, details=None):
        super().__init__(code)
        self.code = code
        self.details = dict(details or {})


@dataclass(frozen=True)
class InputBundle:
    task_path: Path
    task_text: str = field(repr=False)
    files: dict[str, Path]
    headers: dict[str, tuple[str, ...]]
    dictionary_rows: tuple[dict[str, str], ...] = field(repr=False)
    provenance: dict[str, dict]
    source_sha256: dict[str, str]


def _require(budget):
    if budget is not None:
        budget.require()


def _within(path: Path, root: Path) -> bool:
    return path.is_relative_to(root)


def _stat_data(info):
    return {"size": info.st_size, "mtime_ns": info.st_mtime_ns}


def _source_stat(path, root, role):
    real = _regular(path, root, role)
    try:
        return _stat_data(real.stat())
    except OSError:
        raise InputError("unreadable_input", {"role": role}) from None


def _unchanged(path, root, role, expected):
    try:
        actual = _source_stat(path, root, role)
    except InputError:
        raise InputError("source_changed", {"role": role}) from None
    if actual != expected:
        raise InputError("source_changed", {"role": role})


def _regular(path: Path, root: Path, role: str) -> Path:
    """Resolve and stat before opening: in particular never open a FIFO."""
    try:
        real = path.resolve(strict=True)
        if not _within(real, root):
            raise InputError("external_input_path", {"role": role})
        if not stat.S_ISREG(real.stat().st_mode):
            raise InputError("non_regular_input", {"role": role})
        return real
    except (OSError, ValueError, RuntimeError):
        raise InputError("unreadable_input", {"role": role}) from None


@contextmanager
def _binary(path: Path, root: Path, role: str, limit: int):
    _regular(path, root, role)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    # O_NONBLOCK prevents a concurrently substituted FIFO from blocking open().
    flags |= getattr(os, "O_NONBLOCK", 0)
    descriptor = None
    try:
        descriptor = os.open(path, flags)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise InputError("non_regular_input", {"role": role})
        if info.st_size > limit:
            raise InputError("input_too_large", {"role": role, "limit_bytes": limit})
        stream = os.fdopen(descriptor, "rb")
        descriptor = None
        with stream:
            yield stream
    except OSError:
        raise InputError("unreadable_input", {"role": role}) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_small(path, root, role, limit, budget):
    parts = []
    digest = hashlib.sha256()
    total = 0
    with _binary(path, root, role, limit) as stream:
        initial_stat = _stat_data(os.fstat(stream.fileno()))
        while True:
            _require(budget)
            block = stream.read(min(_CHUNK_BYTES, limit - total + 1))
            if not block:
                break
            total += len(block)
            if total > limit:
                raise InputError("input_too_large", {"role": role, "limit_bytes": limit})
            digest.update(block)
            parts.append(block)
        if _stat_data(os.fstat(stream.fileno())) != initial_stat:
            raise InputError("source_changed", {"role": role})
    try:
        return b"".join(parts).decode("utf-8-sig"), digest.hexdigest()
    except UnicodeError:
        raise InputError("invalid_utf8", {"role": role}) from None


def _sha256(path, root, role, limit, budget):
    digest = hashlib.sha256()
    total = 0
    with _binary(path, root, role, limit) as stream:
        initial_stat = _stat_data(os.fstat(stream.fileno()))
        while True:
            _require(budget)
            block = stream.read(min(_CHUNK_BYTES, limit - total + 1))
            if not block:
                break
            total += len(block)
            if total > limit:
                raise InputError("input_too_large", {"role": role, "limit_bytes": limit})
            digest.update(block)
        if _stat_data(os.fstat(stream.fileno())) != initial_stat:
            raise InputError("source_changed", {"role": role})
    return digest.hexdigest()


def _reference(raw: str, role: str) -> str:
    value = raw.strip().replace("\\", "/")
    if (not value or any(ord(char) < 32 for char in value) or "\x7f" in value
            or value.startswith("/") or PureWindowsPath(value).drive
            or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value)
            or any(char in value for char in ("?", "#", "%", "\x00"))
            or ".." in value.split("/")):
        raise InputError("unsafe_input_reference", {"role": role})
    return value


def _references(task_text: str):
    found = {role: [] for role in _FILENAMES}
    captures = []
    for match in _BACKTICK_REF.finditer(task_text):
        line_start = task_text.rfind("\n", 0, match.start()) + 1
        prefix = task_text[line_start:match.start()]
        # P0 syntax: a backtick filename starting a Markdown list item declares
        # an input location. An inline basename in prose is only a mention.
        file_list = bool(re.fullmatch(r"[ \t]*(?:[-+*]|[0-9]+[.)])[ \t]+", prefix))
        captures.append((match.group(1), file_list))
    captures.extend((match.group(1) or match.group(2), True)
                    for match in _MARKDOWN_REF.finditer(task_text))
    for raw, declared_flat in captures:
        basename = raw.strip().replace("\\", "/").split("/")[-1]
        basename = re.split(r"[?#]", basename, maxsplit=1)[0]
        role = _BASENAME_ROLE.get(basename)
        if role is None:
            continue
        ref = _reference(raw, role)
        # Bare inline basenames also occur in explanatory prose. A nested path
        # or actual Markdown link/list entry is an explicit location.
        explicit = "/" in ref or declared_flat
        item = (ref, explicit)
        if item not in found[role]:
            found[role].append(item)
    return found


def _candidates(root: Path, budget):
    result = {role: {} for role in _FILENAMES}
    stack = [root]
    entries_seen = 0
    while stack:
        directory = stack.pop()
        _require(budget)
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    entries_seen += 1
                    if entries_seen > MAX_DISCOVERY_ENTRIES:
                        raise InputError("discovery_limit_exceeded")
                    if entries_seen % 1000 == 0:
                        _require(budget)
                    # Do not follow directory symlinks or recurse into cycles.
                    # Explicit references through internal symlinks still work.
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.name in _BASENAME_ROLE:
                        role = _BASENAME_ROLE[entry.name]
                        real = _regular(Path(entry.path), root, role)
                        result[role].setdefault(real, Path(entry.path))
        except OSError:
            raise InputError("input_discovery_failed") from None
    return result


def _choose_files(root: Path, references, budget):
    chosen, provenance, unresolved = {}, {}, []
    for role, refs in references.items():
        _require(budget)
        explicit_refs = [ref for ref, explicit in refs if explicit]
        # A nested path is stronger than generic basename Markdown links.
        nested_refs = [ref for ref in explicit_refs if "/" in ref]
        declared = nested_refs or explicit_refs
        existing = {}
        for ref in declared:
            candidate = root / ref
            try:
                if not _within(candidate.resolve(strict=False), root):
                    raise InputError("external_input_path", {"role": role})
                real = candidate.resolve(strict=True)
            except FileNotFoundError:
                continue
            except (OSError, ValueError, RuntimeError):
                raise InputError("unreadable_input", {"role": role}) from None
            real = _regular(real, root, role)
            existing.setdefault(real, ref)
        if len(existing) > 1:
            raise InputError("ambiguous_input", {"role": role})
        if existing:
            real, ref = next(iter(existing.items()))
            chosen[role] = real
            provenance[role] = {"resolution": "explicit", "declared_reference": ref,
                                "relative_path": real.relative_to(root).as_posix()}
        else:
            unresolved.append((role, declared))
    candidates = _candidates(root, budget) if unresolved else None
    for role, declared in unresolved:
        options = candidates[role]
        if len(options) > 1:
            raise InputError("ambiguous_input", {"role": role})
        if not options:
            raise InputError("missing_input", {"role": role})
        real, logical = next(iter(options.items()))
        if declared and logical.parent != root:
            raise InputError("declared_input_missing", {"role": role})
        chosen[role] = real
        provenance[role] = {
            "resolution": "flat_fallback" if declared else "canonical_unique",
            "declared_references": list(declared),
            "relative_path": real.relative_to(root).as_posix(),
        }
    return chosen, provenance


def _header(values, role):
    if not values or len(values) > MAX_HEADER_COLUMNS:
        raise InputError("invalid_csv_header", {"role": role})
    if (any(not value or not value.strip() or len(value) > MAX_HEADER_NAME_CHARS
            or "\x00" in value or "\n" in value or "\r" in value for value in values)
            or len(set(values)) != len(values)
            or sum(map(len, values)) > MAX_HEADER_CHARS):
        raise InputError("invalid_csv_header", {"role": role})
    return tuple(values)


@contextmanager
def _csv_reader(path, root, role, limit, budget, expected_sha=None,
                max_record_chars=MAX_CSV_RECORD_CHARS):
    # TextIOWrapper newline='' preserves CSV's own newline/quoted-field rules.
    _require(budget)
    if type(max_record_chars) is not int or not 0 < max_record_chars <= MAX_CSV_RECORD_CHARS:
        raise InputError("invalid_csv_record_limit", {"role": role})
    try:
        with _binary(path, root, role, limit) as binary:
            checked = _CheckedReader(binary, role, limit, budget)
            with io.TextIOWrapper(io.BufferedReader(checked), encoding="utf-8-sig", newline="") as text:
                first_line = text.readline(MAX_HEADER_CHARS + 1)
                if not first_line:
                    raise InputError("empty_csv", {"role": role})
                if len(first_line) > MAX_HEADER_CHARS:
                    raise InputError("invalid_csv_header", {"role": role})
                try:
                    header = _header(next(csv.reader([first_line], delimiter=",", strict=True)), role)
                except StopIteration:
                    raise InputError("empty_csv", {"role": role}) from None
                lines = _LogicalRecordLines(text, role, max_record_chars, budget)
                reader = _BoundedCSVRows(csv.reader(lines, delimiter=",", strict=True), lines)
                yield reader, header
                if expected_sha is not None and checked.digest.hexdigest() != expected_sha:
                    raise InputError("source_changed", {"role": role})
    except (UnicodeError, csv.Error):
        raise InputError("invalid_csv", {"role": role}) from None


class _CheckedReader(io.RawIOBase):
    """Bound every read, check the same work budget and hash bytes actually read."""

    def __init__(self, stream, role, limit, budget):
        super().__init__()
        self.stream, self.role, self.limit, self.budget = stream, role, limit, budget
        self.count = 0
        self.digest = hashlib.sha256()

    def readable(self):
        return True

    def readinto(self, buffer):
        _require(self.budget)
        block = self.stream.read(min(len(buffer), self.limit - self.count + 1))
        self.count += len(block)
        if self.count > self.limit:
            raise InputError("input_too_large", {"role": self.role, "limit_bytes": self.limit})
        self.digest.update(block)
        buffer[:len(block)] = block
        return len(block)


def _lines(text, role):
    while True:
        line = text.readline(MAX_CSV_LINE_CHARS + 1)
        if not line:
            return
        if len(line) > MAX_CSV_LINE_CHARS:
            raise InputError("csv_line_limit", {"role": role})
        yield line


class _LogicalRecordLines:
    """Bound all physical fragments consumed for one logical CSV record.

    A record with many tiny quoted multiline fields must fail before the CSV
    parser can allocate an arbitrarily long list of fields. Header size has
    its own separate bound in _csv_reader.
    """

    def __init__(self, text, role, maximum, budget):
        self.text, self.role, self.maximum, self.budget = text, role, maximum, budget
        self.characters = 0

    def __iter__(self):
        return self

    def __next__(self):
        _require(self.budget)
        remaining = self.maximum - self.characters
        physical_limit = min(MAX_CSV_LINE_CHARS, remaining)
        line = self.text.readline(physical_limit + 1)
        if not line:
            raise StopIteration
        if len(line) > remaining:
            raise InputError("csv_record_limit", {"role": self.role, "limit_chars": self.maximum})
        if len(line) > MAX_CSV_LINE_CHARS:
            raise InputError("csv_line_limit", {"role": self.role})
        self.characters += len(line)
        return line


class _BoundedCSVRows:
    def __init__(self, reader, lines):
        self.reader, self.lines = reader, lines

    def __iter__(self):
        return self

    def __next__(self):
        self.lines.characters = 0
        return next(self.reader)


def _dictionary(path, root, budget, expected_sha):
    rows = []
    features = set()
    with _csv_reader(path, root, "data_dictionary", MAX_DICTIONARY_BYTES, budget,
                     expected_sha=expected_sha) as (reader, header):
        if not {"feature", "role", "dtype"}.issubset(header):
            raise InputError("invalid_dictionary_header", {"role": "data_dictionary"})
        for index, values in enumerate(reader):
            if index % 1000 == 0:
                _require(budget)
            if index >= MAX_ROWS:
                raise InputError("row_limit_exceeded", {"role": "data_dictionary"})
            if len(values) != len(header):
                raise InputError("csv_field_count", {"role": "data_dictionary"})
            row = dict(zip(header, values))
            feature = row["feature"]
            if not feature.strip() or not row["dtype"].strip() or feature in features:
                raise InputError("invalid_dictionary_feature", {"role": "data_dictionary"})
            if row["role"] not in _DICTIONARY_ROLES:
                raise InputError("unknown_dictionary_role", {"role": "data_dictionary"})
            features.add(feature)
            rows.append(row)
    if not rows:
        raise InputError("empty_dictionary", {"role": "data_dictionary"})
    return tuple(rows)


def discover_inputs(task_path: Path, budget=None) -> InputBundle:
    """Find four canonical CSV roles without depending on any dataset name."""
    _require(budget)
    try:
        task = Path(task_path).expanduser().resolve(strict=True)
    except (OSError, ValueError, RuntimeError, TypeError):
        raise InputError("invalid_task_path") from None
    root = task.parent
    task = _regular(task, root, "task")
    task_stat = _source_stat(task, root, "task")
    task_text, task_sha = _read_small(task, root, "task", MAX_TASK_BYTES, budget)
    _unchanged(task, root, "task", task_stat)
    files, provenance = _choose_files(root, _references(task_text), budget)
    provenance["task"] = {"resolution": "task_argument", "relative_path": task.name,
                           "stat": task_stat}
    headers, source_sha256 = {}, {"task": task_sha}
    for role in _FILENAMES:
        limit = MAX_DICTIONARY_BYTES if role == "data_dictionary" else MAX_CSV_BYTES
        source_stat = _source_stat(files[role], root, role)
        source_sha256[role] = _sha256(files[role], root, role, limit, budget)
        _unchanged(files[role], root, role, source_stat)
        with _csv_reader(files[role], root, role, limit, budget) as (_, header):
            headers[role] = header
        _unchanged(files[role], root, role, source_stat)
        provenance[role]["stat"] = source_stat
    dictionary_rows = _dictionary(files["data_dictionary"], root, budget,
                                  source_sha256["data_dictionary"])
    # Role consistency is decided by the contract builder: an explicitly
    # positional submission identifier may exist only in the output template.
    for role, path in {"task": task, **files}.items():
        _unchanged(path, root, role, provenance[role]["stat"])
    return InputBundle(task, task_text, files, headers, dictionary_rows, provenance, source_sha256)


def inspect_rows(bundle: InputBundle, id_columns: Sequence[str], output_order: str = "test",
                 allow_positional: bool = False, budget=None) -> dict:
    """Stream counts and raw string ID keys; never return target/statistics."""
    _require(budget)
    if not isinstance(output_order, str) or output_order not in {"test", "sample"}:
        raise InputError("invalid_output_order")
    if not isinstance(allow_positional, bool):
        raise InputError("invalid_positional_policy")
    if isinstance(id_columns, (str, bytes)):
        raise InputError("invalid_id_columns")
    try:
        columns = tuple(id_columns)
    except TypeError:
        raise InputError("invalid_id_columns") from None
    if (any(not isinstance(column, str) or not column for column in columns)
            or len(set(columns)) != len(columns)):
        raise InputError("invalid_id_columns")
    if not columns and not allow_positional:
        raise InputError("positional_mapping_not_allowed")
    counts, indices, id_availability = {}, {}, {}
    retained_chars = 0
    root = bundle.task_path.parent
    source_paths = {"task": bundle.task_path, **bundle.files}
    for role, path in source_paths.items():
        _require(budget)
        _unchanged(path, root, role, bundle.provenance[role]["stat"])
    for role in ("train", "test", "sample_submission"):
        positions, count, keys = None, 0, {}
        with _csv_reader(bundle.files[role], root, role, MAX_CSV_BYTES, budget,
                         expected_sha=bundle.source_sha256[role]) as (reader, header):
            if header != bundle.headers[role]:
                raise InputError("input_header_changed", {"role": role})
            complete_key = all(column in header for column in columns)
            id_availability[role] = complete_key and bool(columns)
            if not complete_key and role != "train" and not (role == "test" and allow_positional):
                raise InputError("id_column_missing", {"role": role})
            positions = tuple(header.index(column) for column in columns) if complete_key else ()
            for values in reader:
                if count % 1000 == 0:
                    _require(budget)
                if count >= MAX_ROWS:
                    raise InputError("row_limit_exceeded", {"role": role})
                if len(values) != len(header):
                    raise InputError("csv_field_count", {"role": role})
                if positions:
                    key = tuple(values[position] for position in positions)
                    if any(not value.strip() or len(value) > MAX_ID_CHARS or "\x00" in value for value in key):
                        raise InputError("invalid_id", {"role": role})
                    if key in keys:
                        raise InputError("duplicate_id", {"role": role})
                    retained_chars += sum(map(len, key))
                    if retained_chars > MAX_RETAINED_ID_CHARS:
                        raise InputError("id_memory_limit")
                    keys[key] = count
                count += 1
        counts[role], indices[role] = count, keys
    if counts["test"] != counts["sample_submission"]:
        raise InputError("sample_test_row_count_mismatch")
    keyed_mapping = bool(columns) and id_availability["test"] and id_availability["sample_submission"]
    if keyed_mapping:
        test_keys, sample_keys = indices["test"], indices["sample_submission"]
        if test_keys.keys() != sample_keys.keys():
            raise InputError("sample_test_id_mismatch")
        sample_to_test = [test_keys[key] for key in sample_keys]
    else:
        sample_to_test = list(range(counts["test"]))
    for role, path in source_paths.items():
        _require(budget)
        _unchanged(path, root, role, bundle.provenance[role]["stat"])
    _require(budget)
    return {"row_counts": counts, "id_columns": list(columns), "output_order": output_order,
            "sample_to_test": sample_to_test,
            "output_to_test": list(range(counts["test"])) if output_order == "test" else sample_to_test.copy(),
            "positional": not keyed_mapping, "id_availability": id_availability}
