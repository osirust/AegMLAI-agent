"""Trusted bootstrap contracts; later ML/data/worker phases are not implemented."""

import argparse
import copy
import csv
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from time import monotonic_ns
from typing import Callable, Mapping, Sequence
import uuid


MAX_TIME_SECONDS = 10_800.0
MAX_THREADS = 8
_NS = 1_000_000_000
_THREAD_ENV = (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS",
)
_API_ENV = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL")


class BootstrapError(Exception):
    """Only fixed reason codes are exposed; never echo user/env/OS messages."""

    def __init__(self, reason, budget=None):
        super().__init__(reason)
        self.budget = budget


class BudgetExpired(BootstrapError):
    pass


class ActionBudgetInsufficient(BootstrapError):
    """This action does not fit; a cheaper one can still be admitted."""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default includes unknown argv, which can contain credentials.
        raise BootstrapError("invalid_arguments")


def _number(value, reason):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise BootstrapError(reason) from None
    if not math.isfinite(result):
        raise BootstrapError(reason)
    return result


@dataclass(frozen=True)
class RunBudget:
    """One immutable monotonic deadline, shared by every phase/retry in this run.

    This is cooperative accounting, not an interrupt or an OS resource boundary.
    The platform owns process-start enforcement; Python cannot time its own startup.
    """

    started_ns: int
    total_seconds: float
    reserve_seconds: float
    clock: Callable[[], int] = field(default=monotonic_ns, repr=False, compare=False)

    def __post_init__(self):
        if not math.isfinite(self.total_seconds) or not 0 < self.total_seconds <= MAX_TIME_SECONDS:
            raise BootstrapError("invalid_time_limit")
        if int(self.total_seconds * _NS) < 1:
            raise BootstrapError("invalid_time_limit")
        if not math.isfinite(self.reserve_seconds) or not 0 <= self.reserve_seconds < self.total_seconds:
            raise BootstrapError("invalid_finalize_reserve")

    @property
    def deadline_ns(self):
        return self.started_ns + int(self.total_seconds * _NS)

    @property
    def work_deadline_ns(self):
        return self.deadline_ns - int(self.reserve_seconds * _NS)

    def elapsed_seconds(self):
        return max(0, self.clock() - self.started_ns) / _NS

    def remaining_seconds(self, *, finalizing=False):
        deadline = self.deadline_ns if finalizing else self.work_deadline_ns
        return max(0, deadline - self.clock()) / _NS

    def require(self, seconds=0.0, *, finalizing=False):
        cost = _number(seconds, "invalid_action_budget")
        if cost < 0:
            raise BootstrapError("invalid_action_budget")
        remaining = self.remaining_seconds(finalizing=finalizing)
        if remaining <= 0:
            raise BudgetExpired("deadline_exhausted" if finalizing else "work_budget_exhausted", self)
        if cost > remaining:
            raise ActionBudgetInsufficient("insufficient_action_budget", self)
        return remaining

    def snapshot(self):
        now = self.clock()
        return {
            "total_seconds": self.total_seconds,
            "reserve_seconds": self.reserve_seconds,
            "elapsed_seconds": max(0, now - self.started_ns) / _NS,
            "remaining_seconds": max(0, self.deadline_ns - now) / _NS,
            "work_remaining_seconds": max(0, self.work_deadline_ns - now) / _NS,
            "cooperative_only": True,
        }


@dataclass(frozen=True)
class BootstrapConfig:
    # Paths may themselves contain sensitive argv fragments; omit them from repr.
    task_path: Path = field(repr=False)
    output_path: Path = field(repr=False)
    budget: RunBudget
    threads: int
    api_settings_state: str


@dataclass(frozen=True)
class RunOutcome:
    status: str
    termination_reason: str
    exit_code: int
    entrypoint_ready: bool = False
    api_settings_state: str = "not_inspected"
    timer: dict = field(default_factory=dict)
    contract_valid: bool = False
    api_verified: bool = False
    tools_verified: bool = False
    experiments_completed: int = 0
    research_completed: bool = False
    submission_valid: bool = False
    phase: str = "H02.2"
    artifact_sha: dict = field(default_factory=dict)

    def public_dict(self):
        return {
            "schema_version": "bootstrap.v1",
            "phase": self.phase,
            "status": self.status,
            "termination_reason": self.termination_reason,
            "exit_code": self.exit_code,
            "entrypoint_ready": self.entrypoint_ready,
            "api_settings_state": self.api_settings_state,
            "timer": self.timer,
            "contract_valid": self.contract_valid,
            "api_verified": self.api_verified,
            "tools_verified": self.tools_verified,
            "experiments_completed": self.experiments_completed,
            "research_completed": self.research_completed,
            "submission_valid": self.submission_valid,
            "warnings": ["full_agent_not_implemented", "official_platform_image_unverified"],
            "artifact_sha": self.artifact_sha,
        }


def parse_config(argv: Sequence[str], env: Mapping[str, str], *, started_ns, clock=monotonic_ns):
    parser = _Parser(
        prog="solution.py", allow_abbrev=False,
        description="H02.2 bootstrap only; not a submission-ready ML agent.",
    )
    parser.add_argument("task", nargs="?", default="task.md")
    parser.add_argument("--time-limit-seconds")
    parser.add_argument("--finalize-reserve-seconds")
    parser.add_argument("--threads")
    args = parser.parse_args(argv)

    # Explicit argv overrides this run's allowlisted env; no generic config loading.
    total_raw = args.time_limit_seconds if args.time_limit_seconds is not None else env.get("AEGML_TIME_LIMIT_SECONDS", "10800")
    total = _number(total_raw, "invalid_time_limit")
    reserve_raw = args.finalize_reserve_seconds if args.finalize_reserve_seconds is not None else env.get("AEGML_FINALIZE_RESERVE_SECONDS")
    reserve = total / 18 if reserve_raw is None else _number(reserve_raw, "invalid_finalize_reserve")
    budget = RunBudget(started_ns, total, reserve, clock)
    budget.require(finalizing=True)  # Imports, CLI, and config have already used time.
    threads_raw = args.threads if args.threads is not None else env.get("AEGML_THREADS", "8")
    try:
        threads = int(threads_raw)
    except (TypeError, ValueError, OverflowError):
        raise BootstrapError("invalid_threads", budget) from None
    if not 1 <= threads <= MAX_THREADS:
        raise BootstrapError("invalid_threads", budget)

    try:
        task = Path(args.task).expanduser().resolve(strict=True)
        if not task.is_file():
            raise BootstrapError("invalid_task_path", budget)
    except (OSError, ValueError, RuntimeError):
        raise BootstrapError("invalid_task_path", budget) from None
    budget.require(finalizing=True)
    present = sum(bool(env.get(name, "").strip()) for name in _API_ENV)
    api_state = "missing" if present == 0 else "complete_unverified" if present == 3 else "partial_unverified"
    return BootstrapConfig(task, task.parent / "submission.csv", budget, threads, api_state)


def configure_threads(threads):
    # Set before any future ML import. These variables do not enforce CPU isolation.
    for name in _THREAD_ENV:
        os.environ[name] = str(threads)


def _safe_timer(budget, started_ns, clock):
    """Preserve failure timing without letting diagnostics mask the failure."""
    if budget is not None:
        try:
            snapshot = budget.snapshot()
            json.dumps(snapshot, allow_nan=False)
            return snapshot
        except Exception:
            pass
    try:
        elapsed = max(0, clock() - started_ns) / _NS
        if not math.isfinite(elapsed):
            raise ValueError
        return {"elapsed_seconds": elapsed, "cooperative_only": True}
    except Exception:
        return {"cooperative_only": True, "diagnostic_unavailable": True}


def bootstrap(argv, *, started_ns, clock=monotonic_ns, env=None, inspect_task=False):
    budget = None
    phase = "H02.2"
    try:
        if sys.version_info[:2] != (3, 12):
            raise BootstrapError("unsupported_python_version")
        config = parse_config(argv, os.environ if env is None else env, started_ns=started_ns, clock=clock)
        budget = config.budget
        configure_threads(config.threads)
        budget.require()
        artifact_sha = {}
        if inspect_task:
            phase = "H02.3"
            contract = build_task_contract(config.task_path, budget=budget,
                                           threads=config.threads,
                                           time_limit_seconds=budget.total_seconds)
            artifacts = publish_task_contract(contract, budget=budget)
            artifact_sha = {"task_contract.json": artifacts["task_contract_sha256"],
                            "row_alignment.json": artifacts["alignment_sha256"]}
            budget.require()
        # ML, API, CSV prediction and the research loop are still not implemented.
        return RunOutcome("failed", "implementation_incomplete", 3, True,
                          config.api_settings_state, budget.snapshot(),
                          contract_valid=bool(inspect_task), phase=phase,
                          artifact_sha=artifact_sha)
    except SystemExit as exc:
        if exc.code == 0:  # argparse --help only; parser.error never echoes argv.
            return None
        return RunOutcome("failed", "invalid_arguments", 2)
    except BudgetExpired as exc:
        return RunOutcome("failed", str(exc), 124,
                          timer=_safe_timer(exc.budget, started_ns, clock), phase=phase)
    except BootstrapError as exc:
        timer = _safe_timer(exc.budget, started_ns, clock)
        return RunOutcome("failed", str(exc), 2, timer=timer, phase=phase)
    except Exception:
        # Do not expose third-party exception messages, paths, argv, or env values.
        return RunOutcome("failed", "bootstrap_internal_error", 1,
                          timer=_safe_timer(budget, started_ns, clock), phase=phase)


def emit_outcome(outcome):
    print(json.dumps(outcome.public_dict(), ensure_ascii=False, allow_nan=False))


class ContractError(BootstrapError):
    """Unresolved input contract, with metadata available to trusted callers only."""

    def __init__(self, code, conflicts=None, budget=None):
        super().__init__(code, budget)
        self.code = code
        self.conflicts = copy.deepcopy(conflicts or [])


@dataclass(frozen=True)
class TaskContract:
    _payload: dict = field(repr=False)
    _alignment: dict = field(repr=False)

    def to_dict(self):
        return copy.deepcopy(self._payload)

    @property
    def alignment(self):
        return copy.deepcopy(self._alignment)


def _evidence(source, rule, line=None, **extra):
    value = {"source": source, "rule": rule, **extra}
    if line is not None:
        value["line"] = line
    return value


def _directive(text, names):
    pattern = re.compile(r"^\s*(?:[-*]\s*)?(?:" + names + r")\s*[:=]\s*(.*?)\s*$", re.I)
    result = []
    for number, raw in enumerate(text.splitlines(), 1):
        plain = raw.replace("**", "")
        match = pattern.match(plain)
        if match:
            result.append((match.group(1).strip().strip("`\"'"), number))
    return result


def _names(value):
    return [item.strip().strip("`\"'") for item in next(csv.reader([value])) if item.strip()]


def _declared_fields(text, *, identifiers=False):
    marker = (r"id(?:\s+columns?)?|identifier(?:\s+columns?)?|идентификатор(?:ы)?"
              if identifiers else r"target(?:\s+(?:column|variable))?|таргет|целевая\s+переменная")
    found = []
    for value, number in _directive(text, marker):
        for name in _names(value):
            found.append((name, _evidence("task", "explicit_field", number)))
    inline = re.compile(r"(?<![\w`])(?:" + marker + r")(?!\w)(?:\s*[:=—-]\s*|\s+)`([^`\r\n]+)`", re.I)
    role_word = r"идентификатор|identifier" if identifiers else r"таргет|target|целевая"
    for number, raw in enumerate(text.splitlines(), 1):
        for match in inline.finditer(raw):
            found.append((match.group(1), _evidence("task", "quoted_field", number)))
        if raw.lstrip().startswith("|"):
            cells = [cell.strip() for cell in raw.strip().strip("|").split("|")]
            if len(cells) >= 2 and re.search(role_word, cells[1], re.I):
                found.append((cells[0].strip("`"), _evidence("task", "field_table", number)))
    return found


_METRIC_ALIASES = {
    "rmse": r"\brmse\b|root\s+mean\s+squared\s+error",
    "mae": r"\bmae\b|mean\s+absolute\s+error",
    "macro_f1": r"\bmacro[ _-]*f1\b|\bf1[ _-]*macro\b|average\s*=\s*['\"]macro['\"]",
    "weighted_f1": r"\bweighted[ _-]*f1\b|\bf1[ _-]*weighted\b|average\s*=\s*['\"]weighted['\"]",
    "binary_f1": r"\bbinary[ _-]*f1\b|\bf1[ _-]*binary\b",
    "accuracy": r"\baccuracy\b",
    "log_loss": r"\blog[ _-]*loss\b|cross[ _-]*entropy",
    "roc_auc": r"\broc[ _-]*auc\b",
}
_METRIC_INFO = {
    "rmse": ("regression", "minimize", "numeric"),
    "mae": ("regression", "minimize", "numeric"),
    "accuracy": ("classification", "maximize", "label"),
    "macro_f1": ("classification", "maximize", "label"),
    "weighted_f1": ("classification", "maximize", "label"),
    "binary_f1": ("classification", "maximize", "label"),
    "log_loss": ("classification", "minimize", "probability"),
    "roc_auc": ("classification", "maximize", "probability"),
}


def _metric_name(text):
    text = re.split(r",?\s+(?:а\s+не|rather\s+than|not)\s+", text, maxsplit=1, flags=re.I)[0]
    if re.search(r"balanced[ _-]*accuracy|\brmsle\b|\br2\b|r[ -]?squared", text, re.I):
        raise ContractError("unsupported_metric")
    found = {name for name, expression in _METRIC_ALIASES.items() if re.search(expression, text, re.I)}
    if not found:
        raise ContractError("unsupported_metric")
    if len(found) != 1:
        raise ContractError("ambiguous_primary_metric")
    return found.pop()


def _metric_declarations(text, dictionary_rows):
    declarations = []
    pattern = re.compile(r"^\s*(?:#+\s*)?(?:[-*]\s*)?(?:primary\s+metric|evaluation\s+metric|metric|основная\s+метрика|метрика(?:\s+оценки)?)\s*[:=—-]\s*(.+)$", re.I)
    for number, raw in enumerate(text.splitlines(), 1):
        match = pattern.match(raw.replace("**", "").replace("`", ""))
        if match:
            if re.search(r"log1p|log\s*\(\s*y", match.group(1), re.I):
                raise ContractError("unsupported_metric_transform")
            declarations.append((_metric_name(match.group(1)), _evidence("task", "primary_metric", number)))
    if len({name for name, _ in declarations}) > 1:
        raise ContractError("ambiguous_primary_metric")
    for row in dictionary_rows:
        if row["role"] == "target" and row.get("metric", "").strip():
            declarations.append((_metric_name(row["metric"]), _evidence("data_dictionary", "target_metric")))
    names = {name for name, _ in declarations}
    if not names:
        raise ContractError("missing_primary_metric")
    if len(names) != 1:
        raise ContractError("metric_conflict", [{"field": "metric", "sources": [e for _, e in declarations]}])
    return names.pop(), [e for _, e in declarations]


def _type_declarations(text, expected):
    explicit = _directive(text, r"task\s*type|problem\s*type|тип\s+задачи")
    lines = explicit or [(re.split(r"\n\s*##\s*(?:Данные|Data)\b", text, maxsplit=1, flags=re.I)[0], None)]
    types, evidence = set(), []
    for value, number in lines:
        local_types = set()
        clean = re.sub(r"(?:not|не)\s+(?:a\s+)?(?:regression|classification|регресс\w*|классифика\w*)", "", value, flags=re.I)
        if re.search(r"regress|регресс", clean, re.I):
            local_types.add("regression")
        if re.search(r"classif|классифика|\bmulticlass\b|\bbinary\b", clean, re.I):
            local_types.add("classification")
        if explicit and not local_types:
            raise ContractError("unsupported_task_type")
        types.update(local_types)
        evidence.append(_evidence("task", "task_type" if explicit else "task_intro", number))
    if len(types) > 1 or (types and expected not in types):
        raise ContractError("task_type_conflict")
    return evidence if types else [_evidence("metric_registry", "metric_domain")]


def _output_order(text):
    found = []
    for value, number in _directive(text, r"output\s*order|row\s*order|порядок\s+(?:выходных\s+)?строк|порядок\s+вывода"):
        folded = value.casefold().strip(". ")
        order = "sample" if folded in {"sample", "sample_submission", "sample_submission.csv"} else "test" if folded in {"test", "test.csv"} else None
        if order is None:
            raise ContractError("unsupported_output_order")
        found.append((order, _evidence("task", "explicit_output_order", number)))
    lines = text.splitlines()
    for index, raw in enumerate(lines):
        if not re.search(r"поряд\w*\s+строк|row\s+order|same\s+order", raw, re.I):
            continue
        direct = re.findall(r"(?:с|with|as|of)\s+`?(test\.csv|sample_submission\.csv)`?", raw, re.I)
        if direct:
            choices = {"test" if item.casefold() == "test.csv" else "sample" for item in direct}
        else:
            window = "\n".join(lines[max(0, index - 4):index + 2])
            choices = set()
            if re.search(r"\btest\.csv\b", window, re.I):
                choices.add("test")
            if re.search(r"\bsample_submission\.csv\b", window, re.I):
                choices.add("sample")
        if len(choices) == 1:
            found.append((choices.pop(), _evidence("task", "output_order_context", index + 1)))
    orders = {item[0] for item in found}
    if len(orders) > 1:
        raise ContractError("output_order_conflict")
    return (next(iter(orders)), [item[1] for item in found]) if orders else (None, [])


def _explicit_labels(text, directive):
    values = _directive(text, directive)
    parsed = []
    for value, number in values:
        try:
            def reject_constant(_):
                raise ValueError
            labels = json.loads(value, parse_constant=reject_constant) if value.startswith("[") else _names(value)
        except (ValueError, TypeError, csv.Error):
            raise ContractError("invalid_label_declaration") from None
        if not isinstance(labels, list) or not labels or any(type(v) not in (str, int, float) for v in labels):
            raise ContractError("invalid_label_declaration")
        if any(type(v) is float and not math.isfinite(v) for v in labels):
            raise ContractError("invalid_label_declaration")
        labels = [str(v) for v in labels]
        if any(not v for v in labels) or len(set(labels)) != len(labels):
            raise ContractError("invalid_label_declaration")
        parsed.append((labels, number))
    if parsed and any(values[0] != parsed[0][0] for values in parsed):
        raise ContractError("label_declaration_conflict")
    return parsed[0][0] if parsed else None


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def build_task_contract(task_path, *, budget=None, threads=8, time_limit_seconds=10800.0):
    """Read declared metadata and row keys; no folds, transformations or fitting."""
    from aegml_input import discover_inputs, inspect_rows, InputError
    from aegml_schemas import validate_task_contract, SchemaError

    try:
        bundle = discover_inputs(Path(task_path), budget)
        headers = bundle.headers
        rows = bundle.dictionary_rows
        text = bundle.task_text
        role_map = {row["feature"]: row["role"] for row in rows}
        targets = {name for name, role in role_map.items() if role == "target"}
        explicit_targets = _declared_fields(text)
        task_targets = {name for name, _ in explicit_targets}
        if len(targets) > 1 or len(task_targets) > 1:
            raise ContractError("ambiguous_target")
        if targets and task_targets and targets != task_targets:
            raise ContractError("target_conflict")
        candidates = targets or task_targets
        if not candidates:
            candidates = set(headers["train"]) - set(headers["test"])
        if len(candidates) != 1:
            raise ContractError("ambiguous_target" if candidates else "missing_target")
        target = next(iter(candidates))
        if target not in headers["train"]:
            raise ContractError("target_missing_from_train")
        if target in headers["test"]:
            raise ContractError("target_in_test")

        name, metric_evidence = _metric_declarations(text, rows)
        task_type, direction, kind = _METRIC_INFO[name]
        type_evidence = _type_declarations(text, task_type)
        dtype = next((row["dtype"].casefold() for row in rows if row["feature"] == target), "")
        if task_type == "regression" and dtype in {"category", "categorical", "text", "string"}:
            raise ContractError("target_type_conflict")
        for value, _ in _directive(text, r"direction|направление\s+метрики"):
            explicit_direction = {"min": "minimize", "max": "maximize", "minimize": "minimize", "maximize": "maximize"}.get(value.casefold())
            if explicit_direction != direction:
                raise ContractError("metric_direction_conflict")

        raw_ids = _declared_fields(text, identifiers=True)
        no_id = any(name.casefold() in {"none", "null", "нет", "отсутствует"} for name, _ in raw_ids)
        declared_ids = [name for name, _ in raw_ids if name.casefold() not in {"none", "null", "нет", "отсутствует"}]
        dictionary_ids = [row["feature"] for row in rows if row["role"] == "id"]
        if no_id and (declared_ids or dictionary_ids):
            raise ContractError("id_conflict")
        if declared_ids and dictionary_ids and set(declared_ids) != set(dictionary_ids):
            raise ContractError("id_conflict")
        ids = dictionary_ids or list(dict.fromkeys(declared_ids))
        if not ids and not no_id:
            sample_other = [column for column in headers["sample_submission"] if column != target]
            if kind != "probability" and all(column in headers["test"] for column in sample_other):
                ids = sample_other
                if any(role_map.get(column) == "feature" for column in ids):
                    raise ContractError("id_role_conflict")
        if target in ids:
            raise ContractError("target_id_overlap")
        positional = any(value.casefold() in {"position", "positional", "по порядку", "по позиции"}
                         for value, _ in _directive(text, r"row\s*mapping|сопоставление\s+строк"))
        if not ids and not positional:
            raise ContractError("missing_id_policy")
        if any(column not in headers["sample_submission"] for column in ids):
            raise ContractError("submission_id_missing")
        if any(column not in headers["test"] for column in ids) and not positional:
            raise ContractError("id_column_missing")
        for row in rows:
            if row["feature"] not in headers["train"] and not (row["role"] == "id" and row["feature"] in ids):
                raise ContractError("dictionary_feature_missing")

        ignored = {name for name, role in role_map.items() if role == "ignore"}
        features = [column for column in headers["train"] if column not in {target, *ids, *ignored}]
        test_features = [column for column in headers["test"] if column not in {*ids, *ignored}]
        if not features or set(features) != set(test_features):
            raise ContractError("feature_schema_mismatch")
        class_order = _explicit_labels(text, r"class\s*order|порядок\s+классов")
        positive = _explicit_labels(text, r"positive\s*label|положительн\w*\s+класс")
        if positive is not None and len(positive) != 1:
            raise ContractError("ambiguous_positive_label")
        positive = positive[0] if positive else None
        if name in {"binary_f1", "roc_auc"} and positive is None:
            raise ContractError("missing_positive_label")
        if name == "log_loss" and (not class_order or len(class_order) < 2):
            raise ContractError("missing_class_order")
        sample_columns = list(headers["sample_submission"])
        if name != "log_loss" and set(sample_columns) != set(ids + [target]):
            raise ContractError("sample_prediction_schema_conflict")
        if name == "log_loss" and (not set(ids).issubset(sample_columns) or len(sample_columns) != len(ids) + len(class_order)):
            raise ContractError("sample_prediction_schema_conflict")

        order, order_evidence = _output_order(text)
        alignment = inspect_rows(bundle, ids, order or "test", positional, budget)
        if alignment["row_counts"]["train"] == 0 or alignment["row_counts"]["test"] == 0:
            raise ContractError("empty_input")
        if order is None:
            if alignment["sample_to_test"] != list(range(alignment["row_counts"]["test"])):
                raise ContractError("ambiguous_output_order")
            order = "test"
            order_evidence = [_evidence("sample_submission", "equivalent_test_sample_order")]
        alignment["feature_projection"] = {"train_order": features,
                                             "test_indices": [headers["test"].index(column) for column in features]}
        mapping_info = {"status": "computed_in_memory", "row_counts": alignment["row_counts"],
                        "output_order": order, "order_evidence": order_evidence,
                        "positional": alignment["positional"], "feature_projection": alignment["feature_projection"]}
        for key in ("sample_to_test", "output_to_test"):
            mapping_info[key] = {"count": len(alignment[key]),
                                 "sha256": hashlib.sha256(_json_bytes(alignment[key])).hexdigest()}
        parameters = {"average": "macro", "labels": None} if name == "macro_f1" else {"average": "weighted", "labels": None} if name == "weighted_f1" else {}
        payload = {
            "schema_version": "task.v1", "run_id": uuid.uuid4().hex,
            "task_path": str(bundle.task_path), "input_paths": {key: str(path) for key, path in bundle.files.items()},
            "output_path": str(bundle.task_path.parent / "submission.csv"),
            "target_columns": [target], "id_columns": ids, "feature_columns": features,
            "task_type": task_type,
            "metric": {"name": name, "direction": direction, "prediction_kind": kind,
                       "parameters": parameters, "label_policy": "sklearn_labels_none" if task_type == "classification" else None,
                       "positive_label": positive, "class_order": class_order,
                       "target_scale": "original", "adapter_version": "registry.v1_pending_H03",
                       "finite_policy": "finite_only", "evidence": metric_evidence},
            "prediction_schema": {"columns": sample_columns, "id_columns": ids, "target_columns": [target],
                                  "kind": kind, "output_order": order,
                                  "id_policy": {"storage": "raw_string", "normalization": "none", "missing_tokens": [""],
                                                "blank_is_missing": True, "literal_NA_is_value": True,
                                                "probability_columns": [column for column in sample_columns if column not in ids] if kind == "probability" else [],
                                                "mapping": "position" if alignment["positional"] else "one_to_one"}},
            "split_policy": {"status": "NOT_BUILT", "strategy": "deferred_to_H03", "source": "project_policy"},
            "constraints": {"time_limit_seconds": float(time_limit_seconds), "threads": threads,
                            "no_network_except_provider": True},
            "provenance": {"task": bundle.provenance["task"], "files": {key: bundle.provenance[key] for key in bundle.files},
                           "source_sha256": bundle.source_sha256,
                           "fields": {"target": {"column": target, "dictionary": bool(targets), "task_evidence": [item[1] for item in explicit_targets]},
                                      "identifiers": {"columns": ids, "dictionary": bool(dictionary_ids), "task_evidence": [item[1] for item in raw_ids]},
                                      "features": {"order_source": "train_header", "excluded_roles": ["target", "id", "ignore"]},
                                      "task_type": type_evidence}, "row_mapping": mapping_info},
            "conflicts": [],
        }
        validate_task_contract(payload)
        if budget is not None:
            budget.require()
        return TaskContract(payload, alignment)
    except InputError as exc:
        raise ContractError(exc.code, [{"source": "input", **exc.details}], budget) from None
    except SchemaError:
        raise ContractError("invalid_task_contract", budget=budget) from None
    except ContractError as exc:
        exc.budget = budget
        raise


def publish_task_contract(contract, *, budget=None):
    """Publish data-only metadata in a fresh owned run directory, never CSV."""
    from aegml_schemas import validate_task_contract, SchemaError
    payload = contract.to_dict()
    alignment = contract.alignment
    try:
        validate_task_contract(payload)
        if not re.fullmatch(r"[0-9a-f]{32}", payload["run_id"]):
            raise ContractError("invalid_run_id", budget=budget)
        root = Path(payload["task_path"]).parent
        if not root.is_absolute() or root.resolve() != root:
            raise ContractError("unsafe_artifact_directory", budget=budget)
        base = root / ".aegml_runs"
        run = base / payload["run_id"]
        if budget is not None:
            budget.require()
        if base.is_symlink() or (base.exists() and not base.is_dir()):
            raise ContractError("unsafe_artifact_directory", budget=budget)
        base.mkdir(mode=0o700, exist_ok=True)
        if base.resolve().parent != root:
            raise ContractError("unsafe_artifact_directory", budget=budget)
        run.mkdir(mode=0o700)
        alignment_bytes = _json_bytes(alignment)
        if len(alignment_bytes) > 128 * 1024 * 1024:
            raise ContractError("alignment_artifact_too_large", budget=budget)
        alignment_sha = hashlib.sha256(alignment_bytes).hexdigest()
        payload["provenance"]["row_mapping"].update(status="published", artifact_path=str(run / "row_alignment.json"),
                                                  artifact_sha256=alignment_sha)
        validate_task_contract(payload)
        blobs = {"row_alignment.json": alignment_bytes, "task_contract.json": _json_bytes(payload)}
        for name, data in blobs.items():
            if budget is not None:
                budget.require()
            temporary = run / (name + ".tmp")
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            with os.fdopen(os.open(temporary, flags, 0o600), "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, run / name)
        return {"task_contract_path": str(run / "task_contract.json"),
                "task_contract_sha256": hashlib.sha256(blobs["task_contract.json"]).hexdigest(),
                "alignment_path": str(run / "row_alignment.json"), "alignment_sha256": alignment_sha}
    except SchemaError:
        raise ContractError("invalid_task_contract", budget=budget) from None
    except OSError:
        raise ContractError("artifact_publication_failed", budget=budget) from None
