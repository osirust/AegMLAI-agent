"""Build the single-file probe without datasets, packages, keys or generated CSV."""
import hashlib
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
source = root / "testmini/solution.py"
output = root / "dist/testmini.zip"
output.parent.mkdir(exist_ok=True)
entry = zipfile.ZipInfo("solution.py", date_time=(2026, 10, 20, 0, 0, 0))
entry.external_attr = 0o100644 << 16
entry.compress_type = zipfile.ZIP_DEFLATED
with zipfile.ZipFile(output, "w") as archive:
    archive.writestr(entry, source.read_bytes())
with zipfile.ZipFile(output) as archive:
    assert archive.namelist() == ["solution.py"]
    assert archive.testzip() is None
assert output.stat().st_size < 128_000_000
report = {"zip": str(output), "bytes": output.stat().st_size,
          "zip_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
          "solution_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
          "entries": ["solution.py"], "mode": "technical_probe_optional_api",
          "platform_submitted": False}
(output.parent / "testmini-build.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report))
