"""Platform entrypoint: trusted H04 baseline, without Qwen or generated code."""

from time import monotonic_ns as _monotonic_ns

_STARTED_NS = _monotonic_ns()

# Deliberately after the run's only start mark; these imports consume its budget.
import sys
import json
import re

from aegml_contracts import (BudgetExpired, BootstrapError, parse_config,
                             configure_threads, _safe_timer)


def main(argv=None):
    import os
    config = None
    active_budget = None
    progress = {}
    result = {"schema_version": "baseline_outcome.v1", "phase": "H04", "status": "failed",
              "contract_valid": False, "submission_valid": False, "feature_model_fitted": False,
              "api_verified": False, "tools_verified": False, "research_completed": False,
              "live_api_calls": 0, "official_score": None,
              "warnings": ["fixed_baseline_only", "official_image_unverified", "H05_boundary_not_verified"]}
    code = 1
    try:
        if sys.version_info[:2] != (3, 12):
            raise BootstrapError("unsupported_python_version")
        config = parse_config(sys.argv[1:] if argv is None else argv, os.environ,
                              started_ns=_STARTED_NS, clock=_monotonic_ns)
        active_budget = config.budget
        configure_threads(config.threads)
        config.budget.require()
        # ML imports happen only after the same run's start mark/configuration.
        from aegml_baseline import run_baseline
        outcome = run_baseline(config, progress=progress)
        report = outcome["report"]
        result.update(status="baseline_completed", termination_reason="fixed_baseline_complete",
                      contract_valid=True, submission_valid=True, feature_model_fitted=True,
                      inner_metric={"name": report["metric_contract"]["name"],
                                    "constant": report["constant"]["evaluation"]["metric_report"]["value"],
                                    "feature_model": report["feature_model"]["evaluation"]["metric_report"]["value"],
                                    "improvement": report["improvement_over_constant"]},
                      selected=report["selected"], submission_sha256=report["submission"]["sha256"],
                      submission_rows=report["submission"]["row_count"],
                      run_directory=outcome["artifact_root"].name,
                      manifest_sha256=outcome["manifest_record"]["sha256"])
        code = 0
    except SystemExit as exc:
        if exc.code == 0:
            return 0  # --help is assistance, not completed ML.
        result["termination_reason"] = "invalid_arguments"
        code = 2
    except BudgetExpired as exc:
        if exc.budget is not None:
            active_budget = exc.budget
        result["termination_reason"] = "deadline_exhausted"
        code = 124
    except BootstrapError as exc:
        if exc.budget is not None:
            active_budget = exc.budget
        reason = getattr(exc, "code", str(exc))
        result["termination_reason"] = reason if re.fullmatch(r"[a-z][a-z0-9_]{0,80}", reason) else "invalid_configuration"
        code = 2
    except Exception as exc:
        reason = getattr(exc, "code", "baseline_internal_error")
        result["termination_reason"] = reason if isinstance(reason, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,80}", reason) else "baseline_internal_error"
    result["exit_code"] = code
    result.update(progress)
    result["timer"] = _safe_timer(active_budget, _STARTED_NS, _monotonic_ns)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
