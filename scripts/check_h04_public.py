"""Actual H04 CPU training in fresh processes; labels stay in trusted checks.

This WSL pilot runs the exact platform CLI with a shorter declared budget.
It does not call a provider, execute generated code or upload a submission.
"""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "drive-download-20261019T181414Z-1-001"
INPUTS = ("task.md", "train.csv", "test.csv", "data_dictionary.csv", "sample_submission.csv")
TASKS = {"regression": ("Регрессия", 22449), "classification": ("Многоклассовая классификация", 41166)}


def sha(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return digest


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def strict_json(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 1 << 20, "invalid_report_file")
    return json.loads(path.read_text(), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite_json")))


def read_prediction(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 256 << 20, "invalid_prediction_artifact")
    indices, values = [], []
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        require(next(reader) == ["row_index", "prediction_json"], "prediction_header")
        for row in reader:
            require(len(row) == 2 and len(indices) < 2_000_000, "prediction_shape")
            indices.append(int(row[0])); values.append(json.loads(row[1]))
    return tuple(indices), values


def actual_sklearn_oracle(stage, run, report):
    # Read only selected inner target cells. Outer target cells are not retained
    # or scored by this independent trusted oracle.
    from sklearn.metrics import f1_score, mean_squared_error
    task = strict_json(run / "task-contract.json")
    target = task["target_columns"][0]
    inner_indices, markers = read_prediction(run / "inner-membership.csv")
    require(set(markers) == {"inner"}, "invalid_inner_membership_marker")
    wanted = set(inner_indices)
    truth = []
    with (stage / "train.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader); position = header.index(target)
        for index, row in enumerate(reader):
            if index in wanted:
                truth.append(float(row[position]) if report["task_type"] == "regression" else row[position])
    require(len(truth) == len(inner_indices), "inner_truth_count")
    results = {}
    for candidate in ("constant", "model"):
        indices, predictions = read_prediction(run / (candidate + "-inner.csv"))
        require(indices == inner_indices, "inner_prediction_indices")
        value = (math.sqrt(mean_squared_error(truth, predictions)) if report["task_type"] == "regression"
                 else f1_score(truth, predictions, average="macro", zero_division=0))
        key = "feature_model" if candidate == "model" else "constant"
        measured = report[key]["evaluation"]["metric_report"]["value"]
        require(math.isfinite(value) and math.isclose(value, measured, rel_tol=1e-12, abs_tol=1e-12), "actual_sklearn_metric_mismatch")
        results[candidate] = float(value)
    return {"status": "PASS_ACTUAL_INNER_SKLEARN_ORACLE", "values": results,
            "inner_rows": len(truth), "outer_targets_retained_or_scored": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--task", choices=(*TASKS, "both"), default="both")
    parser.add_argument("--run-root", required=True, type=Path)
    args = parser.parse_args()
    require(sys.platform == "linux" and sys.version_info[:2] == (3, 12) and os.geteuid() == 1000,
            "requires_dedicated_linux_py312_uid1000")
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    output = args.receipt.open("x", encoding="utf-8")
    args.run_root.mkdir(mode=0o700)  # A fresh directory, never resume an old run.
    sources = ["solution.py", *sorted(p.name for p in ROOT.glob("aegml_*.py")), "requirements.txt"]
    identity = {name: sha(ROOT / name) for name in sources}
    identity["scripts/check_h04_public.py"] = sha(Path(__file__))
    result = {"status": "FAIL_H04_PUBLIC_WSL", "backend": "WSL_FRESH_PROCESS", "cases": [],
              "source_sha256": identity, "live_api_calls": 0, "new_official_submission": False,
              "official_score_computed": False, "official_image_verified": False,
              "pilot_time_limit_seconds": 900, "reserve_seconds": 60, "threads": 8,
              "capture_scope": "trusted short logs, postcapture size validation; not H05 log enforcement"}
    try:
        keys = list(TASKS) if args.task == "both" else [args.task]
        for key in keys:
            folder, expected_rows = TASKS[key]
            source = DATA / folder
            before = {name: sha(source / name) for name in INPUTS}
            stage = args.run_root / key
            stage.mkdir()
            for name in INPUTS:
                shutil.copyfile(source / name, stage / name)
            for name in sources:
                shutil.copyfile(ROOT / name, stage / name)
                require(sha(stage / name) == identity[name], "stage_source_mismatch")
            env = {name: value for name, value in os.environ.items() if name in
                   {"PATH", "LANG", "LC_ALL", "HOME", "TMPDIR"}}
            env.update(AEGML_TIME_LIMIT_SECONDS="900", AEGML_FINALIZE_RESERVE_SECONDS="60", AEGML_THREADS="8",
                       OMP_NUM_THREADS="8", OPENBLAS_NUM_THREADS="8", MKL_NUM_THREADS="8",
                       PYTHONDONTWRITEBYTECODE="1")
            started = monotonic()
            child = subprocess.run([sys.executable, "solution.py", "task.md"], cwd=stage, env=env,
                                   capture_output=True, timeout=960)
            elapsed = monotonic() - started
            require(len(child.stdout) <= 512 << 10 and len(child.stderr) <= 512 << 10, "trusted_output_too_large")
            with (stage / "stdout.log").open("xb") as f: f.write(child.stdout)
            with (stage / "stderr.log").open("xb") as f: f.write(child.stderr)
            require(child.returncode == 0, "literal_cli_nonzero:" + key)
            outcome = json.loads(child.stdout.decode().strip())
            require(outcome["status"] == "baseline_completed" and outcome["feature_model_fitted"]
                    and outcome["submission_valid"] and outcome["live_api_calls"] == 0, "invalid_baseline_outcome")
            run_name = outcome["run_directory"]
            require(isinstance(run_name, str) and run_name.startswith(".aegml-run-")
                    and "/" not in run_name and "\\" not in run_name, "unsafe_run_name")
            run = stage / run_name
            report = strict_json(run / "baseline-report.json")
            require(report["status"] == "PASS_H04_FIXED_BASELINE_ONLY" and report["model_fit_calls"] == 1
                    and report["live_api_calls"] == 0 and report["source_code_sha256"] == {n: identity[n] for n in sources},
                    "report_identity_or_scope_mismatch")
            oracle = actual_sklearn_oracle(stage, run, report)
            require(outcome["submission_rows"] == expected_rows and sha(stage / "submission.csv") == outcome["submission_sha256"], "submission_identity")
            with (stage / "submission.csv").open(encoding="utf-8", newline="") as stream:
                count = sum(1 for _ in csv.reader(stream)) - 1
            require(count == expected_rows, "submission_count")
            require(before == {name: sha(source / name) for name in INPUTS}
                    == {name: sha(stage / name) for name in INPUTS}, "input_drift")
            result["cases"].append({"task_type": key, "status": "PASS_ACTUAL_H04_BASELINE_ONLY", "outcome": outcome,
                "report_path": str(run / "baseline-report.json"), "report_sha256": sha(run / "baseline-report.json"),
                "submission_path": str(stage / "submission.csv"), "submission_rows": count,
                "submission_sha256": sha(stage / "submission.csv"), "source_sha256": before,
                "elapsed_seconds_including_python_startup": elapsed, "oracle": oracle,
                "outer_quality_evaluated": False, "official_score": None})
            print(json.dumps({"task": key, "quality": oracle["values"], "elapsed_seconds": elapsed, "rows": count}), flush=True)
        require(all(sha(ROOT / name) == digest for name, digest in identity.items()), "root_source_drift")
        result.update(status="PASS_H04_ACTUAL_PUBLIC_WSL_ONLY", source_unchanged=True, original_inputs_unchanged=True)
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.TimeoutExpired) as exc:
        result["error_code"] = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
    finally:
        with output: json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False);output.write("\n")
    print(json.dumps({"status": result["status"], "cases": len(result["cases"]), "error": result.get("error_code")}))
    return 0 if result["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
