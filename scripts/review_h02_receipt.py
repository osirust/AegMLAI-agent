"""Read-only metadata review; never install, fit, call an LLM, or accept full-agent tests."""
import ast
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def pins(path):
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, version = line.split("==")
        name = re.sub(r"\[.*\]", "", name).lower().replace("_", "-")
        assert name not in result
        result[name] = version
    return result


def main():
    historical = read_json(ROOT / "docs/DOC_REVIEW_RECEIPT.json")
    source_checks = {}
    for name, members in historical["named_source_sets"].items():
        assert len(members) == {"download12": 12, "extended14": 14}[name]
        for entry in members:
            assert digest(ROOT / entry["path"]) == entry["sha256"], entry["path"]
        source_checks[name] = len(members)
    for path, expected in historical["unchanged_application_source_sha256"].items():
        assert digest(ROOT / path) == expected, path

    manifest = read_json(ROOT / "docs/SOURCE_MANIFEST.json")
    source = manifest["sources"]["SRC-PLATFORM-TXT-20261020"]
    assert digest(Path(source["file"])) == source["sha256"]
    official = ROOT / "requirements.txt"
    assert (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines() == [
        "* text=auto eol=lf", "/requirements.txt -text"]
    assert digest(official) == "9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6"
    provided = pins(official)
    assert len(provided) == 37
    assert pins(ROOT / "constraints-platform.txt") == provided
    subset = pins(ROOT / "requirements-h02.txt")
    assert len(subset) == 13
    assert all(provided[name] == version for name, version in subset.items())

    lock = read_json(ROOT / "docs/environment-lock.json")
    assert lock["status"] == "PASS_H02_1_LOCAL_SUBSET_ONLY"
    assert lock["direct_pins"] == subset
    installed = {k.lower().replace("_", "-"): v for k, v in lock["installed_distributions"].items()}
    assert len(installed) == 45
    assert all(installed[name] == version for name, version in subset.items())
    assert all(installed[name] == version for name, version in provided.items() if name in installed)
    assert len(lock["wheel_artifacts"]["wheels"]) == 44
    bootstrap = lock["wheel_artifacts"]["bootstrap"]
    assert bootstrap["sha256"] == bootstrap["pypi_expected_sha256"]
    assert lock["pip_check"] == "PASS"
    assert len(lock["smoke_checks"]) == 9
    assert all(item["status"] == "PASS_H02_SMOKE_ONLY" for item in lock["smoke_checks"])
    for name in ("model_fit_calls", "real_api_requests", "historical_stdlib_distributions_after"):
        assert lock[name] == 0
    for name in ("full_platform_image_verified", "historical_stdlib_venv_modified",
                 "global_wsl_memory_or_cpu_changed", "docker_installed"):
        assert lock[name] is False

    # Raw exported evidence is optional in a fresh clone and never fabricated.
    raw_dir = Path(lock["proof_dir"])
    raw_verified = raw_dir.is_dir()
    if raw_verified:
        raw = read_json(raw_dir / "smoke.json")
        assert raw["checks"] == lock["smoke_checks"]
        assert raw["all_installed_distributions"] == lock["installed_distributions"]
        assert "No broken requirements found" in (raw_dir / "pip-check.log").read_text(encoding="utf-8")
        assert read_json(raw_dir / "wheels.json") == lock["wheel_artifacts"]

    work = read_json(ROOT / "docs/WORK_PLAN.json")["blocks"]
    ids = [entry["id"] for entry in work]
    assert len(ids) == len(set(ids)) == 50
    block_md = (ROOT / "docs/WORK_BLOCKS.md").read_text(encoding="utf-8")
    before = json_bytes_from_git("8e80944", "docs/WORK_PLAN.json")["blocks"]
    assert [(b["id"], b["depends_on"]) for b in before] == [(b["id"], b["depends_on"]) for b in work]
    for entry in work:
        section = re.search(r"^### " + re.escape(entry["id"]) + r" .*?(?=^### |\Z)", block_md, re.M | re.S)
        assert section and "`" + entry["status"] + "`" in section.group(), entry["id"]
    by_id = {b["id"]: b for b in work}
    assert by_id["H02.1"]["status"] == "PASS_H02_1_LOCAL_SUBSET_ONLY"
    assert by_id["H02.2"]["status"] == by_id["H02.3"]["status"] == "NOT_RUN"

    spec = (ROOT / "docs/TECHNICAL_SPEC.md").read_text(encoding="utf-8")
    matrix = (ROOT / "docs/TEST_MATRIX.md").read_text(encoding="utf-8")
    main_rows = re.findall(r"^\| T-[^\n]+", spec, re.M)
    assert len(main_rows) == 74
    assert all(row.rstrip().endswith("NOT_RUN |") and row in matrix for row in main_rows)
    harness = (ROOT / "docs/QWEN_HARNESS_DESIGN.md").read_text(encoding="utf-8")
    detail_rows = re.findall(r"^\| HARN-T\d+[^\n]+", harness, re.M)
    assert len(detail_rows) == 17 and all("NOT_RUN" in row for row in detail_rows)
    assert "SPEC-DOC-009" in spec and "100 000 000" in spec
    assert not (ROOT / "solution.py").exists()
    for path in (ROOT / "scripts").glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    checked_links = 0
    markdown = [ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "PROJECT_STATE.md", ROOT / "testmini/README.md"]
    markdown += sorted((ROOT / "docs").glob("*.md"))
    for path in markdown:
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", target) or target.startswith("#"):
                continue
            target = target.split("#", 1)[0]
            assert (path.parent / target).exists(), (str(path), target)
            checked_links += 1
    return {"status": "PASS_H02_1_RECEIPT_AND_DOCUMENT_SCOPE_ONLY",
            "named_source_sets_unchanged": source_checks,
            "application_files_unchanged": len(historical["unchanged_application_source_sha256"]),
            "root_requirements_sha256": digest(official), "provided_pins": 37,
            "direct_pins": 13, "distributions": 45, "dependency_wheels": 44,
            "package_smoke_passed": 9, "raw_exported_proof_rechecked": raw_verified,
            "work_blocks": 50, "ids_dependencies_preserved": True,
            "main_future_scenarios_NOT_RUN": 74, "harness_future_details_NOT_RUN": 17,
            "markdown_files": len(markdown), "local_links": checked_links,
            "model_fit_calls": 0, "real_llm_calls": 0, "entrypoint_implemented": False,
            "scope": "metadata and document review; no environment reinstall, ML, API, or full-agent acceptance"}


def json_bytes_from_git(revision, path):
    import subprocess
    return json.loads(subprocess.check_output(["git", "show", revision + ":" + path], cwd=ROOT))


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))
