"""Bounded data-only artifacts for a trusted H04 controller; not an OS sandbox.

Prediction files are CSV with an integer source-row index and a strict JSON value
cell. No pickle, model loading, credentials, network, or source-row logging.
Callers must pass aggregate/provenance-only metadata, never credentials or labels
intended for closed evaluation. Files are private runtime artifacts, not ZIP assets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import csv
import hashlib
import json
import math
import numbers
import os
from pathlib import Path
import platform
import re
import stat
from itertools import zip_longest
import uuid

from aegml_contracts import BootstrapError


FORMAT_VERSION = "aegml_artifacts.v1"
_NAME = re.compile(r"[a-z][a-z0-9_-]{0,79}\.(?:json|csv)\Z")
_RUN_ID = re.compile(r"[0-9a-f]{32}\Z")
_CREDENTIAL_KEYS = frozenset({"api_key", "authorization", "access_token", "password", "secret"})


class ArtifactError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ArtifactLimits:
    max_json_bytes: int = 1 << 20
    max_prediction_bytes: int = 256 << 20
    max_total_bytes: int = 512 << 20
    max_rows: int = 2_000_000
    max_label_chars: int = 4096
    max_vector_width: int = 4096
    max_files: int = 128
    max_json_depth: int = 32

    def __post_init__(self):
        for name, value in vars(self).items():
            if type(value) is not int or value <= 0:
                raise ArtifactError("invalid_artifact_limits")
        defaults = {"max_json_bytes": 1 << 20, "max_prediction_bytes": 256 << 20,
                    "max_total_bytes": 512 << 20,
                    "max_rows": 2_000_000, "max_label_chars": 4096,
                    "max_vector_width": 4096, "max_files": 128, "max_json_depth": 32}
        if any(getattr(self, name) > limit for name, limit in defaults.items()):
            raise ArtifactError("invalid_artifact_limits")


def _require(budget, finalizing=False):
    if budget is None or not callable(getattr(budget, "require", None)):
        raise ArtifactError("missing_shared_budget")
    budget.require(finalizing=finalizing)


def _identity(info):
    return info.st_dev, info.st_ino


def _plain_json(value, limits, budget, finalizing=False, depth=0, state=None):
    if state is None:
        state = [0]
    state[0] += 1
    if state[0] % 256 == 1:
        _require(budget, finalizing)
    if state[0] > limits.max_json_bytes:
        raise ArtifactError("json_node_limit")
    if depth > limits.max_json_depth:
        raise ArtifactError("json_depth_limit")
    if type(value) is str:
        if len(value) > limits.max_json_bytes:
            raise ArtifactError("artifact_byte_limit")
        return
    if type(value) is int:
        if value.bit_length() > 4096:
            raise ArtifactError("invalid_json_value")
        return
    if value is None or type(value) is bool:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ArtifactError("nonfinite_json")
        return
    if type(value) in (list, tuple):
        for item in value:
            _plain_json(item, limits, budget, finalizing, depth + 1, state)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ArtifactError("invalid_json_key")
            if len(key) > limits.max_json_bytes:
                raise ArtifactError("artifact_byte_limit")
            if key.casefold() in _CREDENTIAL_KEYS:
                raise ArtifactError("credential_metadata_forbidden")
            _plain_json(item, limits, budget, finalizing, depth + 1, state)
        return
    raise ArtifactError("invalid_json_value")


class _BoundedOutput:
    def __init__(self, stream, cap, budget, finalizing):
        self.stream, self.cap, self.budget, self.finalizing = stream, cap, budget, finalizing
        self.count, self.digest = 0, hashlib.sha256()

    def write(self, text):
        _require(self.budget, self.finalizing)
        block = text.encode("utf-8")
        if self.count + len(block) > self.cap:
            raise ArtifactError("artifact_byte_limit")
        self.stream.write(block)
        self.digest.update(block)
        self.count += len(block)
        return len(text)


@dataclass(repr=False)
class RunArtifacts:
    rootpath: Path = field(repr=False)
    run_id: str
    _budget: object = field(repr=False)
    _root_identity: tuple = field(repr=False)
    _parent_identity: tuple = field(repr=False)
    _task_sha256: str = field(repr=False)
    limits: ArtifactLimits = field(default_factory=ArtifactLimits)
    _records: dict = field(default_factory=dict, repr=False)
    _file_identities: dict = field(default_factory=dict, repr=False)
    _pending_temporary: dict = field(default_factory=dict, repr=False)

    def __repr__(self):
        return f"RunArtifacts(run_id={self.run_id!r}, records={len(self._records)})"

    def _guard(self):
        try:
            root = self.rootpath.lstat()
            parent = self.rootpath.parent.lstat()
            if (not stat.S_ISDIR(root.st_mode) or stat.S_ISLNK(root.st_mode)
                    or _identity(root) != self._root_identity
                    or _identity(parent) != self._parent_identity
                    or self.rootpath.resolve(strict=True) != self.rootpath):
                raise ArtifactError("run_directory_changed")
        except OSError:
            raise ArtifactError("run_directory_unavailable") from None

    def _path(self, name):
        if type(name) is not str or not _NAME.fullmatch(name):
            raise ArtifactError("invalid_artifact_name")
        self._guard()
        return self.rootpath / name

    def _verified_record(self, name, budget, finalizing=False):
        path = self._path(name)
        if name not in self._records:
            raise ArtifactError("unregistered_artifact")
        _require(budget, finalizing)
        if name in self._pending_temporary:
            temporary, identity = self._pending_temporary[name]
            cleanup = self._cleanup_temporary(temporary, identity)
            self._records[name]["temporary_cleanup_verified"] = cleanup["verified"]
            if not cleanup["verified"]:
                raise ArtifactError("artifact_cleanup_unverified")
            del self._pending_temporary[name]
        expected = self._records[name]
        try:
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or info.st_nlink != 1 or _identity(info) != self._file_identities[name]
                    or info.st_size != expected["bytes"]):
                raise ArtifactError("artifact_changed")
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                if _identity(before) != self._file_identities[name]:
                    raise ArtifactError("artifact_changed")
                digest, size = hashlib.sha256(), 0
                while block := stream.read(65536):
                    _require(budget, finalizing)
                    size += len(block)
                    if size > expected["bytes"]:
                        raise ArtifactError("artifact_changed")
                    digest.update(block)
                after = os.fstat(stream.fileno())
            if (size != expected["bytes"] or digest.hexdigest() != expected["sha256"]
                    or before.st_mtime_ns != after.st_mtime_ns
                    or _identity(path.lstat()) != self._file_identities[name]):
                raise ArtifactError("artifact_changed")
        except OSError:
            raise ArtifactError("artifact_unavailable") from None
        _require(budget, finalizing)
        return dict(expected)

    def record(self, path, *, finalizing=False):
        """Hash an existing registered artifact, never a path outside this run."""
        _require(self._budget, finalizing)
        try:
            candidate = Path(path)
        except (TypeError, ValueError):
            raise ArtifactError("invalid_artifact_name") from None
        if candidate.is_absolute():
            if candidate.parent != self.rootpath:
                raise ArtifactError("artifact_outside_run")
            name = candidate.name
        elif candidate.parent == Path("."):
            name = candidate.name
        else:
            raise ArtifactError("artifact_outside_run")
        return self._verified_record(name, self._budget, finalizing)

    @staticmethod
    def _cleanup_temporary(path, expected_identity):
        """At most two attempts; never unlink an unknown/replaced inode."""
        warning = False
        if expected_identity is None:
            return {"verified": False, "warning": True}
        for _ in range(2):
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or _identity(info) != expected_identity:
                    return {"verified": False, "warning": True}
                path.unlink()
                try:
                    path.lstat()
                except FileNotFoundError:
                    return {"verified": True, "warning": warning}
                warning = True
            except FileNotFoundError:
                return {"verified": True, "warning": warning}
            except OSError:
                warning = True
        return {"verified": False, "warning": True}

    def _publish(self, name, emit, *, cap, metadata, exclusive, budget, finalizing):
        _require(budget, finalizing)
        if type(exclusive) is not bool:
            raise ArtifactError("invalid_exclusive_policy")
        destination = self._path(name)
        used = sum(record["bytes"] for key, record in self._records.items() if key != name)
        cap = min(cap, self.limits.max_total_bytes - used)
        if cap <= 0:
            raise ArtifactError("artifact_total_byte_limit")
        if name not in self._records and len(self._records) >= self.limits.max_files:
            raise ArtifactError("artifact_count_limit")
        if exclusive:
            if destination.exists() or destination.is_symlink():
                raise ArtifactError("artifact_exists")
        else:
            self._verified_record(name, budget, finalizing)
            if self._records[name]["format"] != "json":
                raise ArtifactError("immutable_prediction_artifact")
        temporary = self.rootpath / (".tmp-" + uuid.uuid4().hex)
        published = False
        temporary_identity = None
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(temporary, flags, 0o600)
            with os.fdopen(fd, "wb") as stream:
                temporary_identity = _identity(os.fstat(stream.fileno()))
                output = _BoundedOutput(stream, cap, budget, finalizing)
                extra = emit(output)
                stream.flush()
                os.fsync(stream.fileno())
            _require(budget, finalizing)
            self._guard()
            record = {"path": name, "sha256": output.digest.hexdigest(), "bytes": output.count,
                      "format": metadata, **(extra or {})}
            if exclusive:
                # Atomic no-clobber admission, including destination-creation races.
                os.link(temporary, destination, follow_symlinks=False)
            else:
                self._verified_record(name, budget, finalizing)
                os.replace(temporary, destination)
            # Successful link/replace is the commit point. Register its known
            # owned inode before fallible cleanup, lstat, or directory fsync.
            published = True
            self._records[name] = record
            self._file_identities[name] = temporary_identity
            cleanup = self._cleanup_temporary(temporary, temporary_identity)
            if cleanup["warning"]:
                record["temporary_cleanup_warning"] = True
                record["temporary_cleanup_verified"] = cleanup["verified"]
            if not cleanup["verified"]:
                self._pending_temporary[name] = temporary, temporary_identity
            # Durability warning after a valid publish is separate from acceptance.
            try:
                directory_fd = os.open(self.rootpath, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                record["directory_fsync_warning"] = True
            return dict(record)
        except FileExistsError:
            raise ArtifactError("artifact_exists") from None
        except BootstrapError:
            raise
        except ArtifactError:
            raise
        except Exception:
            raise ArtifactError("artifact_write_failed") from None
        finally:
            if not published and temporary_identity is not None:
                self._cleanup_temporary(temporary, temporary_identity)

    def write_json(self, name, payload, exclusive=True, finalizing=False):
        if not isinstance(name, str) or not name.endswith(".json"):
            raise ArtifactError("invalid_json_artifact_name")
        _require(self._budget, finalizing)
        _plain_json(payload, self.limits, self._budget, finalizing)
        def emit(output):
            encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":"), allow_nan=False)
            for chunk in encoder.iterencode(payload):
                output.write(chunk)
            output.write("\n")
        return self._publish(name, emit, cap=self.limits.max_json_bytes, metadata="json",
                             exclusive=exclusive, budget=self._budget, finalizing=finalizing)

    def write_predictions(self, name, values, row_indices, *, budget=None, finalizing=False):
        """Save private predictions and row positions; no IDs or true labels needed."""
        if not isinstance(name, str) or not name.endswith(".csv"):
            raise ArtifactError("invalid_prediction_artifact_name")
        shared = self._budget if budget is None else budget
        if shared is not self._budget:
            raise ArtifactError("different_shared_budget")
        _require(shared, finalizing)
        if isinstance(values, (str, bytes, dict, set, frozenset)) or isinstance(row_indices, (str, bytes, dict, set, frozenset)):
            raise ArtifactError("invalid_prediction_sequence")
        def scalar(value):
            if isinstance(value, str):
                if not value or len(value) > self.limits.max_label_chars or "\x00" in value:
                    raise ArtifactError("invalid_prediction_label")
                return value, "label", 1
            if isinstance(value, numbers.Integral) and not isinstance(value, bool):
                if int(value).bit_length() > 1024:
                    raise ArtifactError("invalid_prediction_value")
                return int(value), "numeric", 1
            if isinstance(value, numbers.Real) and not isinstance(value, bool):
                number = float(value)
                if not math.isfinite(number):
                    raise ArtifactError("nonfinite_prediction")
                return number, "numeric", 1
            raise ArtifactError("invalid_prediction_value")
        def normalized(value):
            if isinstance(value, (str, numbers.Real)):
                return scalar(value)
            if isinstance(value, (dict, set, frozenset, bytes, bytearray)):
                raise ArtifactError("invalid_prediction_value")
            try:
                vector = []
                for item in value:
                    if len(vector) >= self.limits.max_vector_width:
                        raise ArtifactError("prediction_width_limit")
                    normalized_item, kind, _ = scalar(item)
                    if kind != "numeric":
                        raise ArtifactError("invalid_prediction_vector")
                    vector.append(normalized_item)
            except TypeError:
                raise ArtifactError("invalid_prediction_value") from None
            if not vector:
                raise ArtifactError("empty_prediction_vector")
            return vector, "vector", len(vector)
        def emit(output):
            writer = csv.writer(output, lineterminator="\n")
            writer.writerow(("row_index", "prediction_json"))
            seen, kind_width, rows = set(), None, 0
            marker = object()
            try:
                iterator = zip_longest(values, row_indices, fillvalue=marker)
                for value, index in iterator:
                    _require(shared, finalizing)
                    if value is marker or index is marker:
                        raise ArtifactError("prediction_row_count_mismatch")
                    if rows >= self.limits.max_rows:
                        raise ArtifactError("prediction_row_limit")
                    if (not isinstance(index, numbers.Integral) or isinstance(index, bool)
                            or index < 0 or index > 2**63 - 1 or int(index) in seen):
                        raise ArtifactError("invalid_prediction_row_index")
                    seen.add(int(index))
                    clean, kind, width = normalized(value)
                    if kind_width is None:
                        kind_width = kind, width
                    if (kind, width) != kind_width:
                        raise ArtifactError("inconsistent_prediction_shape")
                    writer.writerow((str(int(index)), json.dumps(clean, ensure_ascii=False,
                                         separators=(",", ":"), allow_nan=False)))
                    rows += 1
            except TypeError:
                raise ArtifactError("invalid_prediction_sequence") from None
            if not rows:
                raise ArtifactError("empty_predictions")
            return {"row_count": rows, "prediction_kind": kind_width[0], "width": kind_width[1]}
        return self._publish(name, emit, cap=self.limits.max_prediction_bytes,
                             metadata="csv_json_predictions_v1", exclusive=True,
                             budget=shared, finalizing=finalizing)

    def manifest(self, *, finalizing=False):
        """A private local manifest snapshot; caller controls provenance contents."""
        _require(self._budget, finalizing)
        records = [self._verified_record(name, self._budget, finalizing) for name in sorted(self._records)]
        snapshot = getattr(self._budget, "snapshot", None)
        timer = snapshot() if callable(snapshot) else {"available": False}
        rss = None
        try:
            import resource
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if platform.system() != "Darwin":
                rss *= 1024
        except (ImportError, OSError):
            pass
        result = {"format_version": FORMAT_VERSION, "run_id": self.run_id,
                  "task_sha256": self._task_sha256, "records": records,
                  "timer": timer, "python_version": platform.python_version(),
                  "process_high_water_rss_bytes": rss, "rss_scope": "process_cumulative",
                  "data_only": True, "os_boundary_verified": False,
                  "prediction_files_private_not_llm_feedback": True}
        _plain_json(result, self.limits, self._budget, finalizing)
        _require(self._budget, finalizing)
        return result


def create_run_artifacts(task_path, *, run_id, budget, limits=ArtifactLimits()):
    """Create a fresh task-local run directory; never resume or overwrite a run."""
    _require(budget)
    if type(run_id) is not str or not _RUN_ID.fullmatch(run_id):
        raise ArtifactError("invalid_run_id")
    if not isinstance(limits, ArtifactLimits):
        raise ArtifactError("invalid_artifact_limits")
    try:
        task = Path(task_path).resolve(strict=True)
        if not task.is_file() or task.stat().st_size > (1 << 20):
            raise ArtifactError("invalid_task_source")
        with task.open("rb") as stream:
            before = os.fstat(stream.fileno())
            digest, total = hashlib.sha256(), 0
            while block := stream.read(65536):
                _require(budget)
                total += len(block)
                if total > 1 << 20:
                    raise ArtifactError("invalid_task_source")
                digest.update(block)
            after = os.fstat(stream.fileno())
        if (_identity(before) != _identity(after) or before.st_mtime_ns != after.st_mtime_ns
                or before.st_size != total or _identity(task.stat()) != _identity(before)):
            raise ArtifactError("task_source_changed")
        parent_identity = _identity(task.parent.stat())
        root = task.parent / (".aegml-run-" + run_id)
        _require(budget)
        root.mkdir(mode=0o700)
        result = RunArtifacts(root, run_id, budget, _identity(root.lstat()),
                              parent_identity, digest.hexdigest(), limits)
        result._guard()
        return result
    except FileExistsError:
        raise ArtifactError("run_exists") from None
    except (OSError, TypeError, ValueError):
        raise ArtifactError("artifact_run_creation_failed") from None
