"""Platform entrypoint. H02.2 bootstraps only; no ML/API completion is claimed."""

from time import monotonic_ns as _monotonic_ns

_STARTED_NS = _monotonic_ns()

# Deliberately after the run's only start mark; these imports consume its budget.
import sys

from aegml_contracts import bootstrap, emit_outcome


def main(argv=None):
    outcome = bootstrap(
        sys.argv[1:] if argv is None else argv,
        started_ns=_STARTED_NS,
        clock=_monotonic_ns,
        inspect_task=True,
    )
    if outcome is None:  # --help is CLI assistance, not agent success.
        return 0
    emit_outcome(outcome)
    return outcome.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
