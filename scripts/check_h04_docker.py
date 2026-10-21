"""Trusted H04 literal Docker pilot; run ONLY after the root's explicit signal.

Requires completed WSL results for the same frozen source. Two isolated copies
run sequentially with 900 seconds INCLUDING imports/IO/fit/write, not a fresh
budget per phase. Capture is bounded after capture for this trusted quiet CLI;
it is not H05 adversarial streaming/process-isolation acceptance.
"""

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
from time import monotonic
import uuid


ROOT = Path(__file__).resolve().parents[1]
IMAGE = "sha256:95e451e558d36beade7ffb1c64045a34cf152f9daac57336166e023c745cef0b"
HELPER_SHA = "946f940febd24f313871835f8e927f27f5c2f1c09162ba6fbb84832984c79e5b"
REQUIREMENTS_SHA = "9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6"
INPUTS = ("task.md", "train.csv", "test.csv", "data_dictionary.csv", "sample_submission.csv")
ROLES = {"task": "task.md", "train": "train.csv", "test": "test.csv",
         "data_dictionary": "data_dictionary.csv", "sample_submission": "sample_submission.csv"}
TASKS = {"regression": ("Регрессия", 22449, "rmse", "minimize"),
         "classification": ("Многоклассовая классификация", 41166, "macro_f1", "maximize")}
JSON_CAP = 1 << 20
PREDICTION_CAP = 256 << 20
PILOT_SECONDS, RESERVE_SECONDS, THREADS = 900, 60, 8
RTOL, ATOL = 1e-10, 1e-12
H = None


class CheckError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require(condition, code):
    if not condition:
        raise CheckError(code)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    def invalid(_):
        raise CheckError("nonfinite_json")
    return json.loads(text, parse_constant=invalid, object_pairs_hook=pairs)


def regular(path, maximum, *, uid=None):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            and 0 < info.st_size <= maximum, "invalid_owned_artifact")
    if uid is not None:
        require(info.st_uid == uid, "artifact_uid_mismatch")
    return info


def read_json(path, *, uid=None):
    info = regular(path, JSON_CAP, uid=uid)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        require((opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino), "artifact_replaced")
        data = stream.read(JSON_CAP + 1)
        final = os.fstat(stream.fileno())
    now = path.lstat()
    identity = lambda v: (v.st_dev, v.st_ino, v.st_size, v.st_mtime_ns, v.st_ctime_ns)
    require(len(data) == info.st_size <= JSON_CAP and identity(final) == identity(info)
            and identity(now) == identity(info), "artifact_changed")
    result = strict_json(data.decode("utf-8"))
    require(isinstance(result, dict), "expected_json_object")
    return result, hashlib.sha256(data).hexdigest()


def production_names():
    names = ["solution.py", *sorted(path.name for path in ROOT.glob("aegml_*.py")), "requirements.txt"]
    require(len(set(names)) == len(names) and len(names) >= 3, "invalid_source_allowlist")
    for name in names:
        require(name in {"solution.py", "requirements.txt"} or
                re.fullmatch(r"aegml_[a-z0-9_]+\.py", name) is not None, "invalid_source_allowlist")
        regular(ROOT / name, 4 << 20)
    require(sha(ROOT / "requirements.txt") == REQUIREMENTS_SHA, "provided_requirements_changed")
    return names


def load_helper():
    path = ROOT / "scripts/check_h024_platform_cli.py"
    require(sha(path) == HELPER_SHA, "h024_helper_source_changed")
    spec = importlib.util.spec_from_file_location("h04_frozen_h024_helper", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def nested_inputs(original, work):
    """Reproduce declared paths, rather than the download archive's flat layout.

    Use the same stdlib reference parser as the controller. Canonical filenames
    identify roles; dataset-specific directory names are never inferred here.
    """
    root_text = str(ROOT)
    sys.path.insert(0, root_text)
    try:
        import aegml_input
        references = aegml_input._references((original / "task.md").read_text(encoding="utf-8-sig"))
    finally:
        sys.path.pop(0)
    destinations = {"task": work / "task.md"}
    declared = {}
    shutil.copyfile(original / "task.md", destinations["task"])
    for role, basename in ROLES.items():
        if role == "task":
            continue
        choices = {ref for ref, explicit in references[role] if explicit and "/" in ref}
        require(len(choices) == 1, "nested_declared_input_not_unique")
        value = choices.pop()
        relative = PurePosixPath(value)
        require(not relative.is_absolute() and relative.name == basename
                and all(part not in {"", ".", ".."} for part in relative.parts)
                and ":" not in value and "\\" not in value, "unsafe_nested_declared_input")
        path = work.joinpath(*relative.parts)
        require(path.resolve().is_relative_to(work.resolve()), "nested_input_outside_work")
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original / basename, path)
        destinations[role], declared[role] = path, relative.as_posix()
    require(not any((work / name).exists() for name in INPUTS if name != "task.md"),
            "flat_input_copy_would_hide_declared_resolution")
    return destinations, declared


def docker(arguments, timeout=15):
    result = H.run_docker(arguments, timeout=timeout)
    require(not result["timed_out"], "docker_command_timeout")
    require(result["capture_valid"], "docker_capture_invalid_or_oversize")
    require(result["returncode"] == 0, "docker_command_failed")
    return result


def verify_image(image):
    result = docker(["image", "inspect", "--format", "{{json .}}", image])
    info = strict_json(result["stdout"])
    require(info.get("Id") == IMAGE and info.get("Os") == "linux"
            and info.get("Architecture") == "amd64", "unexpected_local_image")
    return {"Id": info["Id"], "Os": info["Os"], "Architecture": info["Architecture"],
            "official_platform_image_verified": False}


def verify_container(cid, name, owner, work, scratch):
    info = strict_json(docker(["inspect", "--type", "container", "--format", "{{json .}}", cid])["stdout"])
    require(info.get("Id") == cid and info.get("Name") == "/" + name and info.get("Image") == IMAGE,
            "container_identity_mismatch")
    config, host = info.get("Config", {}), info.get("HostConfig", {})
    require((config.get("Labels") or {}).get(H.OWNER_LABEL) == owner
            and (config.get("Labels") or {}).get("org.aegml.check.scope") == "H04_FIXED_BASELINE",
            "container_owner_mismatch")
    require(config.get("Cmd") == ["python3", "solution.py", "task.md"]
            and config.get("WorkingDir") == "/work" and config.get("User") == "1000:1000"
            and config.get("Entrypoint") in (None, []), "container_command_or_user_mismatch")
    require(host.get("Memory") == 20 << 30 and host.get("MemorySwap") == 20 << 30
            and host.get("NanoCpus") == 8_000_000_000 and host.get("PidsLimit") == 256
            and host.get("ReadonlyRootfs") is True and host.get("NetworkMode") == "none",
            "container_resource_profile_mismatch")
    require(set(host.get("CapDrop") or ()) == {"ALL"} and not host.get("CapAdd")
            and host.get("Privileged") is False
            and not any("seccomp=unconfined" in value for value in host.get("SecurityOpt", []))
            and any(value in {"no-new-privileges", "no-new-privileges=true"}
                    for value in host.get("SecurityOpt", [])), "container_capability_profile_mismatch")
    require((host.get("LogConfig") or {}).get("Type") == "none", "container_daemon_logging_enabled")
    mounts = info.get("Mounts", [])
    require(len(mounts) == 2, "unexpected_container_mount_count")
    actual = {item.get("Destination"): item for item in mounts}
    for destination, path in (("/work", work), ("/tmp", scratch)):
        item = actual.get(destination, {})
        require(item.get("Type") == "bind" and item.get("Source") == str(path.resolve())
                and item.get("RW") is True, "unexpected_container_mount")
    env = dict(item.split("=", 1) for item in config.get("Env", []) if "=" in item)
    require(env.get("AEGML_TIME_LIMIT_SECONDS") == str(PILOT_SECONDS)
            and env.get("AEGML_FINALIZE_RESERVE_SECONDS") == str(RESERVE_SECONDS)
            and env.get("AEGML_THREADS") == str(THREADS), "container_pilot_config_mismatch")
    require(not any(value for key, value in env.items() if key.startswith("OPENAI_")
                    or key.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}), "unexpected_provider_environment")
    require(info.get("State", {}).get("Status") == "created", "container_started_before_inspection")
    return {"container_id": cid, "profile_verified_before_start": True, "memory_bytes": 20 << 30,
            "memory_swap_bytes": 20 << 30, "cpu_quota": 8, "pids_limit": 256, "uid": 1000,
            "rootfs_readonly": True, "cap_drop_all": True, "no_new_privileges": True,
            "network": "none", "mount_destinations": ["/work", "/tmp"], "scratch": "owned_disk_backed"}


def reference(path, expected_sources):
    value, digest = read_json(path)
    require(value.get("status") == "PASS_H04_ACTUAL_PUBLIC_WSL_ONLY"
            and value.get("source_unchanged") is True, "wsl_reference_not_completed")
    identity = value.get("source_sha256", {})
    require(all(identity.get(name) == checksum for name, checksum in expected_sources.items()),
            "wsl_reference_source_mismatch")
    cases = value.get("cases", [])
    require(len(cases) == 2 and {case.get("task_type") for case in cases} == set(TASKS),
            "wsl_reference_needs_two_tasks")
    for case in cases:
        require(case.get("status") == "PASS_ACTUAL_H04_BASELINE_ONLY"
                and case.get("oracle", {}).get("status") == "PASS_ACTUAL_INNER_SKLEARN_ORACLE",
                "wsl_reference_oracle_missing")
    return {case["task_type"]: case for case in cases}, digest


def manifest_records(run, manifest):
    records = manifest.get("records")
    require(isinstance(records, list) and 0 < len(records) <= 64, "invalid_manifest_records")
    found = {}
    for record in records:
        name = record.get("path")
        require(isinstance(name, str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,79}\.(json|csv)", name)
                and name not in found, "unsafe_manifest_path")
        path = run / name
        maximum = JSON_CAP if name.endswith(".json") else PREDICTION_CAP
        info = regular(path, maximum, uid=1000)
        require(type(record.get("bytes")) is int and record["bytes"] == info.st_size
                and sha(path) == record.get("sha256"), "manifest_artifact_mismatch")
        found[name] = record
    required = {"task-contract.json", "split.json", "config.json", "baseline-report.json",
                "constant-inner.csv", "constant-test.csv", "model-inner.csv", "model-test.csv"}
    require(required.issubset(found), "manifest_missing_baseline_artifacts")
    return found


def prediction_rows(path):
    regular(path, PREDICTION_CAP)
    count = 0
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        require(next(reader, None) == ["row_index", "prediction_json"], "prediction_header_mismatch")
        for row in reader:
            require(len(row) == 2 and len(row[0]) <= 20 and len(row[1]) <= 65536
                    and re.fullmatch(r"0|[1-9][0-9]*", row[0]) is not None, "invalid_prediction_row")
            count += 1
            require(count <= 2_000_000, "prediction_row_limit")
            value = strict_json(row[1])
            require(isinstance(value, str) or type(value) in (int, float), "invalid_prediction_scalar")
            if not isinstance(value, str):
                require(math.isfinite(value), "nonfinite_prediction_scalar")
            yield int(row[0]), value


def compare_predictions(current, previous, kind):
    from itertools import zip_longest
    missing, count, largest = object(), 0, 0.0
    for left, right in zip_longest(prediction_rows(current), prediction_rows(previous), fillvalue=missing):
        require(left is not missing and right is not missing and left[0] == right[0], "repeat_prediction_row_mismatch")
        if kind == "classification":
            require(type(left[1]) is type(right[1]) and left[1] == right[1], "repeat_class_prediction_mismatch")
        else:
            require(type(left[1]) in (int, float) and type(right[1]) in (int, float)
                    and math.isclose(left[1], right[1], rel_tol=RTOL, abs_tol=ATOL), "repeat_numeric_prediction_mismatch")
            largest = max(largest, abs(left[1] - right[1]))
        count += 1
    require(count > 0, "empty_repeat_predictions")
    return {"row_count": count, "matches": True, "maximum_absolute_numeric_difference": largest,
            "relative_tolerance": RTOL, "absolute_tolerance": ATOL}


def validate_result(work, outcome, kind, expected_sources, input_hashes, ref_case, declared_paths):
    folder, expected_rows, metric, direction = TASKS[kind]
    require(outcome.get("schema_version") == "baseline_outcome.v1" and outcome.get("phase") == "H04"
            and outcome.get("status") == "baseline_completed" and type(outcome.get("exit_code")) is int
            and outcome["exit_code"] == 0 and outcome.get("termination_reason") == "fixed_baseline_complete",
            "invalid_cli_completion")
    require(all(outcome.get(key) is True for key in ("contract_valid", "feature_model_fitted", "submission_valid"))
            and all(outcome.get(key) is False for key in ("api_verified", "tools_verified", "research_completed"))
            and type(outcome.get("live_api_calls")) is int and outcome["live_api_calls"] == 0
            and outcome.get("official_score") is None, "invalid_cli_scope_flags")
    run_name = outcome.get("run_directory")
    require(isinstance(run_name, str) and re.fullmatch(r"\.aegml-run-[0-9a-f]{32}", run_name), "unsafe_run_name")
    run = work / run_name
    info = run.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 1000
            and run.resolve().parent == work.resolve(), "invalid_owned_run_directory")
    require(len(list(work.glob(".aegml-run-*"))) == 1, "unexpected_run_count")
    report, report_sha = read_json(run / "baseline-report.json", uid=1000)
    manifest, manifest_sha = read_json(run / "manifest.json", uid=1000)
    require(manifest_sha == outcome.get("manifest_sha256") and manifest.get("run_id") == run_name[11:]
            and manifest.get("task_sha256") == input_hashes["task.md"], "manifest_run_mismatch")
    records = manifest_records(run, manifest)
    require(records["baseline-report.json"]["sha256"] == report_sha, "report_manifest_mismatch")
    source_roles = {role: input_hashes[name] for role, name in ROLES.items()}
    require(report.get("status") == "PASS_H04_FIXED_BASELINE_ONLY"
            and report.get("protocol") == "H04_FIXED_SEARCH_FIT_ONLY" and report.get("task_type") == kind
            and report.get("source_code_sha256") == expected_sources
            and report.get("source_sha256") == source_roles
            and report.get("model_fit_calls") == 1 and report.get("constant_fit_calls") == 1
            and report.get("live_api_calls") == 0 and report.get("official_score") is None,
            "baseline_report_identity_mismatch")
    require(report["metric_contract"]["name"] == metric and report["metric_contract"]["direction"] == direction,
            "baseline_metric_mismatch")
    phase = report.get("phase_access", {})
    require(phase.get("outer_targets_retained_or_scored") is False
            and phase.get("frozen_refit_performed") is False and phase.get("test_targets_available") is False,
            "unexpected_closed_data_access")
    model = report["feature_model"]["audit"]
    require(model.get("tree_count") == 300 and model["requested_parameters"]["thread_count"] == 8
            and model["requested_parameters"]["task_type"] == "CPU"
            and model.get("fit_scope") == "NO_REFIT_SEARCH_ONLY", "unexpected_estimator_recipe")
    contract, _ = read_json(run / "task-contract.json", uid=1000)
    config, _ = read_json(run / "config.json", uid=1000)
    require(contract["task_path"] == "/work/task.md" and contract["output_path"] == "/work/submission.csv"
            and contract["provenance"]["source_sha256"] == source_roles
            and contract["split_policy"]["status"] == "BUILT"
            and config.get("source_code_sha256") == expected_sources, "contract_source_or_stage_mismatch")
    for role, relative in declared_paths.items():
        provenance = contract["provenance"]["files"].get(role, {})
        require(contract["input_paths"].get(role) == "/work/" + relative
                and provenance.get("resolution") == "explicit"
                and provenance.get("declared_reference") == relative
                and provenance.get("relative_path") == relative, "declared_nested_input_not_selected")
    selected = report.get("selected")
    require(selected == outcome.get("selected") and selected in {"feature_model", "fit_mean", "fit_majority"},
            "candidate_selection_mismatch")
    submission = work / "submission.csv"
    info = regular(submission, PREDICTION_CAP, uid=1000)
    submission_sha = sha(submission)
    require(submission_sha == outcome.get("submission_sha256") == report["submission"]["sha256"]
            and report["submission"]["bytes"] == info.st_size
            and outcome.get("submission_rows") == report["submission"]["row_count"] == expected_rows,
            "submission_identity_mismatch")
    with submission.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        require(next(reader, None) == contract["prediction_schema"]["columns"], "submission_header_mismatch")
        require(sum(1 for _ in reader) == expected_rows, "submission_row_count_mismatch")
    old_report, old_sha = read_json(Path(ref_case["report_path"]))
    require(old_sha == ref_case["report_sha256"] and old_report.get("source_code_sha256") == expected_sources
            and old_report.get("source_sha256") == source_roles and old_report.get("selected") == selected
            and old_report.get("split") == report.get("split")
            and old_report["feature_model"]["audit"]["requested_parameters"] == model["requested_parameters"],
            "wsl_repeat_recipe_or_split_mismatch")
    old_run = Path(ref_case["report_path"]).parent
    old_manifest, old_manifest_sha = read_json(old_run / "manifest.json", uid=1000)
    require(old_manifest_sha == ref_case["outcome"]["manifest_sha256"]
            and old_manifest.get("task_sha256") == input_hashes["task.md"], "wsl_reference_manifest_mismatch")
    old_records = manifest_records(old_run, old_manifest)
    require(old_records["baseline-report.json"]["sha256"] == old_sha, "wsl_reference_artifact_changed")
    comparisons = {}
    for name in ("constant-inner.csv", "model-inner.csv", "constant-test.csv", "model-test.csv"):
        comparisons[name] = compare_predictions(run / name, Path(ref_case["report_path"]).parent / name, kind)
    constant = report["constant"]["evaluation"]["metric_report"]
    feature = report["feature_model"]["evaluation"]["metric_report"]
    for record, name in ((constant, "constant"), (feature, "model")):
        require(record["name"] == metric and record["direction"] == direction and math.isfinite(record["value"])
                and math.isclose(record["value"], ref_case["oracle"]["values"][name], rel_tol=RTOL, abs_tol=ATOL),
                "docker_metric_differs_from_wsl_oracle")
    gain = constant["value"] - feature["value"] if direction == "minimize" else feature["value"] - constant["value"]
    inner_metric = outcome.get("inner_metric", {})
    constant_kind = "fit_mean" if kind == "regression" else "fit_majority"
    require(report["constant"]["kind"] == constant_kind and report.get("selection_tolerance") == 1e-12
            and selected == ("feature_model" if gain > 1e-12 else constant_kind)
            and inner_metric.get("name") == metric
            and inner_metric.get("constant") == constant["value"]
            and inner_metric.get("feature_model") == feature["value"]
            and math.isclose(gain, report["improvement_over_constant"], rel_tol=RTOL, abs_tol=ATOL)
            and math.isclose(gain, inner_metric.get("improvement", math.nan), rel_tol=RTOL, abs_tol=ATOL),
            "metric_or_selection_crossbinding_mismatch")
    return {"report_sha256": report_sha, "manifest_sha256": manifest_sha,
            "report_path": str(run / "baseline-report.json"), "submission_path": str(submission),
            "submission_sha256": submission_sha, "submission_rows": expected_rows,
            "input_layout": {"mode": "declared_nested", "paths_by_role": declared_paths,
                             "all_resolved_explicitly": True, "flat_fallback_used": False},
            "quality": {"metric": metric, "direction": direction, "constant": constant["value"],
                        "feature_model": feature["value"], "improvement": report["improvement_over_constant"],
                        "selected": selected, "inner_rows": feature["n_rows"],
                        "model_fit_calls": 1, "constant_fit_calls": 1, "outer_quality_evaluated": False,
                        "official_score": None},
            "wsl_repeat": {"status": "MATCHED_SOURCE_SPLIT_RECIPE_PREDICTIONS_AND_ORACLE", "predictions": comparisons,
                           "model_state_sha_comparison": "not_required_run_metadata_may_differ"}}


def run_case(kind, index, stage, image, owner, expected_sources, ref_case):
    folder, _, _, _ = TASKS[kind]
    original = ROOT / "drive-download-20261019T181414Z-1-001" / folder
    work, scratch = stage / (kind + "-work"), stage / (kind + "-scratch")
    work.mkdir(mode=0o700)
    scratch.mkdir(mode=0o700)
    # Keep the frozen helper's approved naming/label contract; the purpose is
    # additionally H04-labelled, not a modification of the old cleanup code.
    name = "aegml-h024-cli-" + owner + "-" + str(index)
    cidfile = stage / (name + ".cid")
    case = {"task_type": kind, "status": "FAIL", "container_name": name,
            "literal_container_argv": ["python3", "solution.py", "task.md"]}
    try:
        originals = {name: sha(original / name) for name in INPUTS}
        require(ref_case.get("source_sha256") == originals, "wsl_reference_input_mismatch")
        staged_inputs, declared_paths = nested_inputs(original, work)
        for item in expected_sources:
            shutil.copyfile(ROOT / item, work / item)
        require({name: sha(work / name) for name in expected_sources} == expected_sources, "staged_source_drift")
        for path in (work, scratch, *work.rglob("*")):
            os.chown(path, 1000, 1000)
        absent, _, _ = H._absence(name)
        require(absent and not os.path.lexists(cidfile), "container_name_or_cid_not_fresh")
        arguments = ["create", "--name", name, "--init", "--pull=never", "--log-driver=none",
                     "--label", H.OWNER_LABEL + "=" + owner, "--label", "org.aegml.check.scope=H04_FIXED_BASELINE",
                     "--cidfile", str(cidfile), "--network=none", "--read-only", "--cap-drop=ALL",
                     "--security-opt=no-new-privileges", "--user=1000:1000", "--memory=20g",
                     "--memory-swap=20g", "--cpus=8", "--pids-limit=256",
                     "--mount", "type=bind,source=" + str(work) + ",target=/work",
                     "--mount", "type=bind,source=" + str(scratch) + ",target=/tmp", "--workdir=/work",
                     "--env=AEGML_TIME_LIMIT_SECONDS=900", "--env=AEGML_FINALIZE_RESERVE_SECONDS=60",
                     "--env=AEGML_THREADS=8", "--env=PYTHONDONTWRITEBYTECODE=1", "--env=PYTHONNOUSERSITE=1",
                     image, "python3", "solution.py", "task.md"]
        created = docker(arguments)
        cid = created["stdout"].strip()
        require(re.fullmatch(r"[0-9a-f]{64}", cid) is not None and not cidfile.is_symlink()
                and cidfile.read_text(encoding="ascii").strip() == cid, "created_container_id_mismatch")
        case["container_profile"] = verify_container(cid, name, owner, work, scratch)
        started = monotonic()
        child = docker(["start", "-a", cid], timeout=PILOT_SECONDS + 60)
        case["elapsed_seconds_including_python_startup"] = monotonic() - started
        outcome = strict_json(child["stdout"])
        require(isinstance(outcome, dict), "invalid_cli_outcome")
        case.update(validate_result(work, outcome, kind, expected_sources, originals, ref_case, declared_paths))
        require(originals == {name: sha(original / name) for name in INPUTS}
                == {basename: sha(staged_inputs[role]) for role, basename in ROLES.items()},
                "original_or_staged_input_drift")
        require(expected_sources == {name: sha(work / name) for name in expected_sources}, "staged_source_changed")
        case.update(status="PASS_ACTUAL_H04_DOCKER_BASELINE_ONLY", outcome=outcome,
                    original_inputs_unchanged=True, staged_sources_unchanged=True)
    except CheckError as exc:
        case["reason"] = exc.code
    except H.CheckError as exc:
        case["reason"] = exc.code
    except KeyboardInterrupt:
        case["reason"] = "checker_interrupted"
    except Exception as exc:
        case.update(reason="h04_docker_check_internal_error", error_type=type(exc).__name__)
    finally:
        try:
            cleanup = H.cleanup_container(name, owner, cidfile)
        except BaseException as exc:
            cleanup = {"name": name, "container_id": None, "status": "cleanup_unverified", "verified": False,
                       "reason": "cleanup_internal_error", "error_type": type(exc).__name__}
        if not cleanup.get("verified"):
            case.update(status="FAIL", cleanup_unverified=True)
    return case, cleanup


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--wsl-reference", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.image != IMAGE:
        parser.error("use the verified immutable local dev image")
    if os.path.lexists(args.receipt):
        parser.error("receipt already exists")
    if sys.platform != "linux" or sys.version_info[:2] != (3, 12) or os.geteuid() != 0:
        parser.error("requires dedicated Linux Python3.12 root and local Docker socket")
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    try:
        output = args.receipt.open("x", encoding="utf-8")
    except FileExistsError:
        parser.error("receipt appeared before exclusive reservation")
    result = {"status": "FAIL_H04_ACTUAL_DOCKER_ONLY", "image": args.image, "cases": [], "cleanup": [],
              "unresolved_resources": [], "source_policy": "frozen_root_and_identical_staging",
              "pilot_time_limit_seconds": PILOT_SECONDS, "reserve_seconds": RESERVE_SECONDS, "threads": THREADS,
              "capture_scope": "postcapture bound for trusted quiet CLI; not H05 streaming",
              "daemon_log_driver": "none", "receipt_creation": "held_exclusive_fd_before_docker",
              "python_optimize": sys.flags.optimize, "live_api_calls": 0, "new_official_submission": False,
              "official_image_verified": False, "H05_boundary_accepted": False, "refit_executed": False}
    with output:
        try:
            global H
            H = load_helper()
            names = production_names()
            sources = {name: sha(ROOT / name) for name in names}
            result["source_sha256"] = sources
            result["checker_sha256"] = sha(Path(__file__).resolve())
            result["h024_helper_sha256"] = HELPER_SHA
            references, reference_sha = reference(args.wsl_reference, sources)
            result["wsl_reference_sha256"] = reference_sha
            result["image_inspection"] = verify_image(args.image)
            stage = args.receipt.resolve().parent / ("h04-docker-" + uuid.uuid4().hex)
            stage.mkdir(mode=0o700)
            result["stage"] = str(stage)
            owner = uuid.uuid4().hex
            for index, kind in enumerate(TASKS, 1):
                case, cleanup = run_case(kind, index, stage, args.image, owner, sources, references[kind])
                result["cases"].append(case)
                result["cleanup"].append(cleanup)
                if not cleanup.get("verified"):
                    result["unresolved_resources"].append({"name": cleanup["name"], "container_id": cleanup["container_id"]})
                if not case["status"].startswith("PASS_"):
                    break
        except CheckError as exc:
            result["failure_reason"] = exc.code
        except KeyboardInterrupt:
            result["failure_reason"] = "checker_interrupted"
        except Exception as exc:
            result.update(failure_reason="h04_checker_internal_error", error_type=type(exc).__name__)
        finally:
            try:
                after_names = production_names()
                result["source_sha256_after"] = {name: sha(ROOT / name) for name in after_names}
                result["root_source_changed"] = result.get("source_sha256") != result["source_sha256_after"]
                require(sha(Path(__file__).resolve()) == result.get("checker_sha256")
                        and sha(ROOT / "scripts/check_h024_platform_cli.py") == HELPER_SHA, "checker_source_drift")
            except Exception:
                result["root_source_changed"] = True
            if result["root_source_changed"]:
                result["failure_reason"] = "root_or_checker_source_drift"
            passed = (len(result["cases"]) == 2 and all(case["status"].startswith("PASS_") for case in result["cases"])
                      and len(result["cleanup"]) == 2 and all(item.get("verified") for item in result["cleanup"])
                      and not result["unresolved_resources"] and not result.get("failure_reason"))
            result["status"] = "PASS_H04_ACTUAL_DOCKER_ONLY" if passed else "FAIL_H04_ACTUAL_DOCKER_ONLY"
            json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.write("\n")
    print(json.dumps({"status": result["status"], "datasets": len(result["cases"]),
                      "root_source_changed": result["root_source_changed"],
                      "cleanup_verified": len(result["cleanup"]) == 2 and all(item.get("verified") for item in result["cleanup"])},
                     ensure_ascii=False))
    return 0 if result["status"] == "PASS_H04_ACTUAL_DOCKER_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
