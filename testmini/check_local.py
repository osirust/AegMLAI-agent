"""Run only the explicitly requested technical probe on disposable task copies."""
import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from collections import Counter
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path

repo = Path(__file__).resolve().parent.parent
sources = repo / "drive-download-20261019T181414Z-1-001"
proof_root = repo / "runs/testmini" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
proof_root.mkdir(parents=True)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

original_identity = {str(path.relative_to(sources)): digest(path) for path in sources.rglob("*") if path.is_file()}
subprocess.run([sys.executable, str(repo / "testmini/build_zip.py")], check=True, cwd=repo)
archive_path = repo / "dist/testmini.zip"
with zipfile.ZipFile(archive_path) as archive:
    assert archive.namelist() == ["solution.py"]
    assert archive.testzip() is None

def execute(directory, explicit_argument):
    command = [sys.executable, "-I", "solution.py"]
    if explicit_argument:
        command.append("task.md")
    environment = os.environ.copy()
    for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
        environment.pop(name, None)
    result = subprocess.run(command, cwd=directory, env=environment, capture_output=True, timeout=180)
    (directory / "stdout.jsonl").write_bytes(result.stdout)
    raw_err = result.stderr
    err = raw_err.decode("utf-16-le" if b"\x00" in raw_err else "utf-8", errors="replace")
    (directory / "stderr.txt").write_text(err, encoding="utf-8", newline="\n")
    events = [json.loads(line) for line in result.stdout.decode("utf-8").splitlines() if line.strip()]
    return result.returncode, events

def extract_solution(directory):
    with zipfile.ZipFile(archive_path) as archive:
        (directory / "solution.py").write_bytes(archive.read("solution.py"))

def table(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))

def write_csv(path, header, records):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(records)

results = []
for source_name, local_name, target, expected_train, expected_test in (
    ("Регрессия", "regression", "site_eui", 53308, 22449),
    ("Многоклассовая классификация", "classification", "attack_cat", 87670, 41166),
):
    directory = proof_root / local_name
    directory.mkdir()
    for name in ("task.md", "train.csv", "test.csv", "data_dictionary.csv", "sample_submission.csv"):
        shutil.copy2(sources / source_name / name, directory / name)
    extract_solution(directory)
    exit_code, events = execute(directory, explicit_argument=(local_name == "regression"))
    assert exit_code == 0, {"case": local_name, "events": events, "exit": exit_code}
    report = json.loads((directory / "mini_diagnostics.json").read_text(encoding="utf-8"))
    assert report["status"] == "completed_format_only" and not report["api_used"] and not report["quality_assessed"]
    assert report["api_probe"]["status"] == "skipped_not_configured"
    assert report["train_rows"] == expected_train and report["test_rows"] == expected_test
    assert not report["features_used"] and not report["autoresearch_performed"]
    output_rows = table(directory / "submission.csv")
    test_rows = table(directory / "test.csv")
    assert len(output_rows) == expected_test
    assert list(output_rows[0]) == ["id", target]
    assert [row["id"] for row in output_rows] == [row["id"] for row in test_rows]
    train_rows = table(directory / "train.csv")
    if local_name == "regression":
        reference = math.fsum(float(row[target]) for row in train_rows) / len(train_rows)
        assert all(math.isfinite(float(row[target])) and math.isclose(float(row[target]), reference, rel_tol=1e-10, abs_tol=1e-9) for row in output_rows)
    else:
        counts = Counter(row[target] for row in train_rows)
        reference = min(counts, key=lambda label: (-counts[label], label))
        assert all(row[target] == reference for row in output_rows)
    assert events[-1]["event"] == "completed_format_only"
    results.append({"check_id": "MC-PUBLIC-REG" if local_name == "regression" else "MC-PUBLIC-CLS",
                    "status": "PASS", "scope": "input/constant baseline/format only", "train_rows": expected_train,
                    "output_rows": expected_test, "elapsed_seconds": report["elapsed_seconds"],
                    "submission_sha256": digest(directory / "submission.csv"), "cwd": str(directory)})
    print(json.dumps(results[-1]), flush=True)

fixture = proof_root / "fixture"
fixture.mkdir()
(fixture / "task.md").write_text("Metric: Macro F1. Files: `train.csv`, `test.csv`, `data_dictionary.csv`, `sample_submission.csv`.\n", encoding="utf-8")
write_csv(fixture / "data_dictionary.csv", ["feature", "role"], [("row_key", "id"), ("renamed_target", "target"), ("feature", "feature")])
write_csv(fixture / "train.csv", ["renamed_target", "feature", "row_key"], [("A", "", "1"), ("A", "x", "2"), ("B", "y", "3")])
write_csv(fixture / "test.csv", ["feature", "row_key"], [("", "001"), ("unknown", "002")])
write_csv(fixture / "sample_submission.csv", ["row_key", "renamed_target"], [("001", "B"), ("002", "B")])
extract_solution(fixture)
exit_code, events = execute(fixture, True)
assert exit_code == 0
assert table(fixture / "submission.csv") == [{"row_key": "001", "renamed_target": "A"}, {"row_key": "002", "renamed_target": "A"}]
results.append({"check_id": "MC-RENAMED", "status": "PASS", "scope": "renamed target/id, target first, leading-zero IDs, sample placeholders ignored"})
print(json.dumps(results[-1]), flush=True)
before_output = digest(fixture / "submission.csv")
write_csv(fixture / "sample_submission.csv", ["row_key", "renamed_target"], [("002", "B"), ("001", "B")])
exit_code, events = execute(fixture, True)
assert exit_code == 1 and events[-1]["event"] == "failed"
assert digest(fixture / "submission.csv") == before_output
assert not list(fixture.glob(".testmini-*.tmp"))
results.append({"check_id": "MC-BAD-ID", "status": "PASS", "scope": "mismatched sample order rejected; last valid CSV preserved"})
print(json.dumps(results[-1]), flush=True)
assert original_identity == {str(path.relative_to(sources)): digest(path) for path in sources.rglob("*") if path.is_file()}
results.append({"check_id": "MC-ZIP", "status": "PASS", "scope": "single root solution.py extracted and executed; original input identities unchanged", "zip_bytes": archive_path.stat().st_size,
                "zip_sha256": digest(archive_path), "original_files_unchanged": len(original_identity)})
summary = {"status": "PASS_TESTMINI_LOCAL_ONLY", "mode": "technical_probe_optional_api", "proof_root": str(proof_root),
           "environment": {"python": sys.version.split()[0], "executable": sys.executable, "official_image": False},
           "checks": results, "project_49_tests_executed": False, "quality_assessed": False,
           "api_used": False, "platform_submitted": False, "official_acceptance_confirmed": False}
(proof_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
(repo / "runs/testmini/latest-result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"status": summary["status"], "checks_passed": len(results), "summary": str(proof_root / "summary.json"), "zip": str(archive_path)}), flush=True)
