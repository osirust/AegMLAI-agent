"""Trusted bootstrap contracts; later ML/data/worker phases are not implemented."""

import argparse
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import sys
from time import monotonic_ns
from typing import Callable, Mapping, Sequence


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

    def public_dict(self):
        return {
            "schema_version": "bootstrap.v1",
            "phase": "H02.2",
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
            "artifact_sha": {},
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


def bootstrap(argv, *, started_ns, clock=monotonic_ns, env=None):
    budget = None
    try:
        if sys.version_info[:2] != (3, 12):
            raise BootstrapError("unsupported_python_version")
        config = parse_config(argv, os.environ if env is None else env, started_ns=started_ns, clock=clock)
        budget = config.budget
        configure_threads(config.threads)
        budget.require()
        # No TaskContract, CSV, API, or worker is implemented in this subsection.
        return RunOutcome("failed", "implementation_incomplete", 3, True,
                          config.api_settings_state, budget.snapshot())
    except SystemExit as exc:
        if exc.code == 0:  # argparse --help only; parser.error never echoes argv.
            return None
        return RunOutcome("failed", "invalid_arguments", 2)
    except BudgetExpired as exc:
        return RunOutcome("failed", str(exc), 124,
                          timer=_safe_timer(exc.budget, started_ns, clock))
    except BootstrapError as exc:
        timer = _safe_timer(exc.budget, started_ns, clock)
        return RunOutcome("failed", str(exc), 2, timer=timer)
    except Exception:
        # Do not expose third-party exception messages, paths, argv, or env values.
        return RunOutcome("failed", "bootstrap_internal_error", 1,
                          timer=_safe_timer(budget, started_ns, clock))


def emit_outcome(outcome):
    print(json.dumps(outcome.public_dict(), ensure_ascii=False, allow_nan=False))
