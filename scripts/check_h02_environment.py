"""H02.1 import/ABI/config smoke only: no training and no external API requests."""
import importlib
import importlib.metadata
import io
import json
import math
import os
import platform
import sys
from pathlib import Path

assert sys.platform == "linux" and sys.version_info[:2] == (3, 12)
assert Path(sys.prefix) == Path("/home/aegml/venvs/aegml-ml-py312")
root = Path(__file__).resolve().parent.parent
proof = Path("/home/aegml/checks/h02-latest-proof.txt").read_text().strip()
proof = Path(proof)
expected = {}
for row in (root / "requirements-h02.txt").read_text().splitlines():
    if row and not row.startswith("#"):
        name, version = row.split("==")
        expected[name] = version
modules = {"scikit-learn": "sklearn", "setuptools": None}
imports = {}
for name, version in expected.items():
    assert importlib.metadata.version(name) == version, name
    module_name = modules.get(name, name)
    module = importlib.import_module(module_name) if module_name else None
    file = Path(module.__file__).resolve() if module else Path(importlib.metadata.distribution(name).locate_file(""))
    assert file.is_relative_to(Path(sys.prefix)), (name, str(file))
    imports[name] = {"version": version, "path": str(file)}

import numpy as np
import scipy.linalg
import scipy.sparse
import pandas as pd
from sklearn.metrics import f1_score, root_mean_squared_error
from catboost import CatBoostClassifier, CatBoostRegressor, Pool
import httpx
import openai
from pydantic import BaseModel, ConfigDict, ValidationError
from jsonschema import Draft202012Validator
import psutil

checks = []
def passed(name):
    checks.append({"id": name, "status": "PASS_H02_SMOKE_ONLY"})
assert np.array_equal(np.array([[1, 2], [3, 4]]) @ np.array([2, 1]), [4, 10])
passed("numpy_dot")
assert np.allclose(scipy.linalg.solve([[2.0, 0.0], [0.0, 4.0]], [4.0, 8.0]), [2, 2])
assert np.array_equal(scipy.sparse.csr_matrix([[0, 2], [3, 0]]) @ np.array([2, 1]), [2, 6])
passed("scipy_linalg_sparse_abi")
frame = pd.read_csv(io.StringIO("id,text,value\n001,тест,1.5\n002,мир,\n"), dtype={"id": str})
roundtrip = pd.read_csv(io.StringIO(frame.to_csv(index=False)), dtype={"id": str})
assert roundtrip.id.tolist() == ["001", "002"] and roundtrip.text.tolist() == ["тест", "мир"]
assert pd.isna(roundtrip.value.iloc[1])
passed("pandas_csv_unicode_ids_missing")
assert math.isclose(root_mean_squared_error([0, 2], [0, 0]), math.sqrt(2))
assert math.isclose(f1_score(["A", "A", "B", "B"], ["A"] * 4, average="macro"), 1 / 3)
assert f1_score(["A", "A"], ["A", "A"], average="macro") == 1
assert f1_score(["A", "A"], ["A", "A"], labels=["A"] + [str(x) for x in range(9)], average="macro", zero_division=0) == .1
passed("sklearn_metrics_package_only_not_H03")
pool = Pool([[1.0, 2.0], [3.0, 4.0]], label=[0, 1])
assert pool.num_row() == 2 and pool.num_col() == 2
assert CatBoostClassifier(iterations=2, thread_count=1, verbose=False).get_params()["iterations"] == 2
assert CatBoostRegressor(iterations=2, thread_count=1, verbose=False).get_params()["thread_count"] == 1
passed("catboost_import_pool_constructors_no_fit")
class Shape(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    rows: int
assert Shape(rows=2).rows == 2
try:
    Shape(rows="2")
except ValidationError:
    pass
else:
    raise AssertionError("strict Pydantic accepted string")
schema = {"type": "object", "properties": {"rows": {"type": "integer"}}, "required": ["rows"], "additionalProperties": False}
validator = Draft202012Validator(schema)
assert validator.is_valid({"rows": 2}) and not validator.is_valid({"rows": "2"})
passed("pydantic_jsonschema_strict_positive_negative")
transport = httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError("No HTTP request allowed in smoke")))
http_client = httpx.Client(transport=transport, trust_env=False)
client = openai.OpenAI(api_key="dummy-h02-not-a-real-key", base_url="https://invalid.example/v1", http_client=http_client, max_retries=0)
client.close()
passed("openai_httpx_construction_close_no_request")
assert psutil.Process(os.getpid()).memory_info().rss > 0
passed("psutil_self_process")
all_packages = {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}
assert "mcp" not in {n.casefold() for n in all_packages}
passed("mcp_absent")
report = {"status": "PASS_H02_1_LOCAL_SUBSET_ONLY", "python": platform.python_version(), "executable": sys.executable,
          "venv": sys.prefix, "base_prefix": sys.base_prefix, "platform": platform.platform(), "uid": os.getuid(),
          "expected_direct_versions": expected, "imports": imports, "all_installed_distributions": all_packages,
          "checks": checks, "self_rss_bytes_after_imports": psutil.Process().memory_info().rss,
          "model_fit_calls": 0, "real_api_requests": 0, "user_datasets_loaded": False,
          "future_metric_adapter_accepted": False, "platform_image_verified": False,
          "historical_stdlib_venv_modified": False}
(proof / "smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": report["status"], "smoke_checks": len(checks), "direct_pins": len(expected), "installed_distributions": len(all_packages), "proof_dir": str(proof)}))
