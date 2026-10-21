"""Offline H03.1 behavior checks; no API, fitting, or package installation.

Use --actual-inputs for two isolated read-only public-data child checks. Their
scopes come from the separately checked H03.3 implementation; this checker
verifies the SplitPlan-to-ProfileScope bridge, not all H03.3 behavior again.
"""

import argparse
import copy
import csv
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from aegml_contracts import BudgetExpired, RunBudget, TaskContract, build_task_contract
from aegml_input import discover_inputs
from aegml_profile import ProfileError, ProfileLimits, ProfileScope, profile_task
from aegml_validation import build_split_plan

SOURCES = ("aegml_profile.py", "aegml_input.py", "aegml_contracts.py", "aegml_schemas.py",
           "aegml_validation.py", "aegml_metrics.py", "requirements.txt", "scripts/check_h031_profile.py")
CASES = []
ACTUAL = []
INCLUDE_ACTUAL = False
PUBLIC = {"regression": "Регрессия", "classification": "Многоклассовая классификация"}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def budget():
    return RunBudget(time.monotonic_ns(), 180, 1)


def csv_write(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


class Fixture:
    def __init__(self, root, classification=False):
        self.root = root
        root.mkdir()
        self.task = root / "task.md"
        self.header = ["row_key", "feature", "outcome", "category", "text", "unknown", "ignored"]
        self.test_header = ["category", "row_key", "unknown", "feature", "text", "ignored"]
        self.train = [["private-train-0", "1", "10", "NA", "first", "1", "private-ignore"],
                      ["private-train-1", "2", "20", "null", "second", "2", "private-ignore"],
                      ["private-train-2", "3", "30", "NA", "third", "3", "private-ignore"],
                      ["private-protected-3", "999", "999", "hidden", "hidden", "999", "hidden"],
                      ["private-protected-4", "888", "888", "hidden", "hidden", "888", "hidden"]]
        self.test = [["NA", "private-test-0", "4", "4", "fourth", "private-ignore"],
                     ["new", "private-test-1", "5", "5", "fifth", "private-ignore"]]
        self.dictionary = [[name, "id" if name == "row_key" else "target" if name == "outcome" else
                            "ignore" if name == "ignored" else "feature", dtype]
                           for name, dtype in zip(self.header, ["string", "numeric", "numeric", "category", "text", "auto", "text"])]
        self.kind = "classification" if classification else "regression"
        self.save()

    def save(self):
        csv_write(self.root / "train.csv", self.header, self.train)
        csv_write(self.root / "test.csv", self.test_header, self.test)
        csv_write(self.root / "data_dictionary.csv", ["feature", "role", "dtype"], self.dictionary)
        csv_write(self.root / "sample_submission.csv", ["row_key", "outcome"],
                  [[row[self.test_header.index("row_key")], "0"] for row in self.test])
        metric = "Macro F1" if self.kind == "classification" else "RMSE"
        self.task.write_text("Task type: " + self.kind + "\nTarget: outcome\nID: row_key\nMetric: " + metric
                             + "\nOutput order: test\n## Data\n- `train.csv`\n- `test.csv`\n"
                             "- `data_dictionary.csv`\n- `sample_submission.csv`\n", encoding="utf-8")

    def prepare(self, fit=(0, 1, 2)):
        shared = budget()
        contract = build_task_contract(self.task, budget=shared)
        bundle = discover_inputs(self.task, shared)
        scope = ProfileScope(tuple(fit), tuple(i for i in range(len(self.train)) if i not in fit),
                             len(self.train), bundle.source_sha256["train"], "explicit_fixture_not_H033")
        return bundle, contract, scope


def columns(result):
    return {col["name"]: col for col in result["research"]["columns"]}


class ProfileChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aegml-h031-")
        self.addCleanup(self.temp.cleanup)
        self.fixture = Fixture(Path(self.temp.name) / "fixture")

    @contextmanager
    def case(self, label):
        record = {"test": self.id(), "case": label, "status": "RUNNING"}
        CASES.append(record)
        try:
            yield
        except unittest.SkipTest:
            record["status"] = "SKIP"
            raise
        except BaseException:
            record["status"] = "FAIL"
            raise
        else:
            record["status"] = "PASS"

    def profile(self, prepared=None, **kwargs):
        return profile_task(*(prepared or self.fixture.prepare()), budget=kwargs.pop("budget", budget()), **kwargs)

    def rejects(self, code, action):
        with self.assertRaises(ProfileError) as caught:
            action()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)

    def test_exact_fit_statistics_and_test_diagnostics(self):
        with self.case("fit_mean_std_and_numeric_test_shift_known_values"):
            result = self.profile()
            data = columns(result)
            self.assertEqual(data["feature"]["fit"]["numeric"]["mean"], 2.0)
            self.assertEqual(data["feature"]["fit"]["numeric"]["sample_std"], 1.0)
            self.assertEqual(data["outcome"]["fit"]["numeric"]["mean"], 20.0)
            self.assertIsNone(data["outcome"]["test"])
            self.assertEqual(data["feature"]["shift"]["mean_delta"], 2.5)
            self.assertEqual(data["category"]["shift"]["unseen_count"], 1)
            self.assertEqual(data["unknown"]["kind"], "numeric")
            self.assertEqual(result["research"]["rows"], {"fit": 3, "test": 2})

    def test_protected_values_do_not_change_research_or_prompt(self):
        for kind in ("regression", "classification"):
            with self.case("protected_X_y_poison_invariant_" + kind):
                self.fixture.kind = kind
                self.fixture.train[3][1:] = ["999", "999", "hidden", "hidden", "999", "hidden"]
                self.fixture.train[4][1:] = ["888", "888", "hidden", "hidden", "888", "hidden"]
                self.fixture.save()
                original = self.profile()
                for index in (3, 4):
                    self.fixture.train[index][1:] = ["NaN", "private-new-class", "new-secret", "long-secret", "-Inf", "private-ignore"]
                self.fixture.save()
                poisoned = self.profile()
                self.assertEqual(poisoned["research"], original["research"])
                self.assertEqual(poisoned["prompt"], original["prompt"])
                self.assertNotEqual(poisoned["provenance"]["source_sha256"]["train"], original["provenance"]["source_sha256"]["train"])
                self.assertEqual(poisoned["provenance"]["schema_sha256"], original["provenance"]["schema_sha256"])
                self.assertNotIn("private-new-class", canonical(poisoned))

    def test_test_values_cannot_change_fit_statistics_or_kind(self):
        with self.case("test_X_shift_changes_only_test_diagnostics"):
            original = columns(self.profile())
            self.fixture.test[0][2:5] = ["not-numeric", "10000", "different"]
            self.fixture.save()
            shifted = columns(self.profile())
            for name in original:
                self.assertEqual(original[name]["fit"], shifted[name]["fit"])
                self.assertEqual(original[name]["kind"], shifted[name]["kind"])
            self.assertNotEqual(original["feature"]["shift"], shifted["feature"]["shift"])

    def test_missing_literals_and_redacted_ids(self):
        with self.case("empty_only_missing_NA_null_values_and_no_raw_ID"):
            self.fixture.train[0][1] = ""
            self.fixture.train[1][1] = "NA"
            self.fixture.train[2][1] = "null"
            self.fixture.save()
            result = self.profile()
            data = columns(result)
            self.assertEqual(data["feature"]["fit"]["missing"], 1)
            self.assertEqual(data["feature"]["fit"]["numeric"]["invalid"], 2)
            self.assertEqual(data["category"]["fit"]["missing"], 0)
            self.assertEqual(data["category"]["fit"]["categories"]["distinct_count"], 2)
            self.assertEqual(data["row_key"]["kind"], "redacted")
            self.assertNotIn("private-", canonical(result))

    def test_numeric_class_labels_are_categories(self):
        with self.case("classification_target_numeric_dtype_stays_categorical"):
            self.fixture.kind = "classification"
            for index, value in enumerate(("1", "2", "1")):
                self.fixture.train[index][2] = value
            self.fixture.save()
            target = columns(self.profile())["outcome"]
            self.assertEqual(target["kind"], "categorical")
            self.assertNotIn("numeric", target["fit"])
            self.assertEqual(target["fit"]["categories"]["top"], [{"value": "1", "count": 2}, {"value": "2", "count": 1}])

    def test_nonfinite_and_arithmetic_overflow_are_explicit(self):
        with self.case("NaN_Inf_literal_overflow_excluded_from_finite_moments"):
            for index, value in enumerate(("NaN", "Inf", "1e309")):
                self.fixture.train[index][1] = value
            self.fixture.save()
            data = columns(self.profile())["feature"]["fit"]["numeric"]
            self.assertEqual(data["nonfinite"], 3)
            self.assertEqual(data["finite"], 0)
            self.assertIsNone(data["mean"])
        with self.case("finite_extremes_overflow_moments_without_non_JSON_values"):
            for index, value in enumerate(("-1e308", "1e308", "0")):
                self.fixture.train[index][1] = value
            self.fixture.save()
            result = self.profile()
            data = columns(result)["feature"]["fit"]["numeric"]
            self.assertEqual(data["finite"], 3)
            self.assertEqual(data["moments_status"], "overflow_unavailable")
            self.assertIsNone(data["mean"])
            json.loads(canonical(result))

    def test_category_caps_do_not_claim_exact_top_or_unseen(self):
        with self.case("bounded_first_seen_is_not_global_top_or_exact_distinct"):
            for index, value in enumerate(("a", "b", "c", "c", "c")):
                self.fixture.train[index][3] = value
            self.fixture.save()
            result = self.profile(self.fixture.prepare(tuple(range(5))),
                                  limits=ProfileLimits(max_categories_per_column=2, top_k=2))
            cat = columns(result)["category"]
            self.assertEqual(cat["fit"]["categories"]["retained_categories"], 2)
            self.assertIsNone(cat["fit"]["categories"]["distinct_count"])
            self.assertFalse(cat["fit"]["categories"]["global_top_exact"])
            self.assertEqual(cat["fit"]["categories"]["unretained_occurrences"], 3)
            self.assertIsNone(cat["shift"]["unseen_count"])
            self.assertFalse(cat["shift"]["unseen_exact"])
        with self.case("overlong_values_not_truncated_into_same_category"):
            self.fixture.train[0][3], self.fixture.train[1][3] = "a" * 129, "a" * 128 + "b"
            self.fixture.save()
            result = self.profile(limits=ProfileLimits(max_total_category_chars=8))
            self.assertLessEqual(result["research"]["retained_category_characters"], 8)
            cat = columns(result)["category"]["fit"]["categories"]
            self.assertFalse(cat["retention_complete"])
            self.assertGreaterEqual(cat["unretained_occurrences"], 2)

    def test_scope_validation_and_normalization(self):
        good = self.fixture.prepare()[2]
        with self.case("scope_unsorted_tuple_normalized"):
            self.assertEqual(replace(good, fit_indices=(2, 0, 1)).fit_indices, (0, 1, 2))
        changes = ({"fit_indices": (False, 1, 2)}, {"fit_indices": (0, 0, 1, 2)},
                   {"protected_indices": (2, 3, 4)}, {"protected_indices": (4,)},
                   {"fit_indices": ()}, {"fit_indices": (-1, 0, 1, 2)},
                   {"train_rows": True}, {"fit_indices": [0, 1, 2]}, {"train_sha256": "bad"})
        for number, change in enumerate(changes):
            with self.case("scope_invalid_partition_" + str(number)):
                self.rejects("invalid_scope", lambda: replace(good, **change))

    def test_scope_contract_and_schema_guards(self):
        bundle, contract, scope = self.fixture.prepare()
        with self.case("scope_SHA_mismatch"):
            self.rejects("scope_source_mismatch", lambda: self.profile((bundle, contract, replace(scope, train_sha256="0" * 64))))
        with self.case("contract_source_SHA_mismatch"):
            payload = contract.to_dict()
            payload["provenance"]["source_sha256"]["train"] = "0" * 64
            self.rejects("contract_source_mismatch", lambda: self.profile((bundle, TaskContract(payload, contract.alignment), scope)))
        with self.case("dictionary_object_must_match_authenticated_bytes"):
            changed = list(copy.deepcopy(bundle.dictionary_rows))
            changed[1]["dtype"] = "text"
            forged = replace(bundle, dictionary_rows=tuple(changed))
            self.rejects("schema_mismatch", lambda: self.profile((forged, contract, scope)))

    def refreshed_metadata(self, prepared, role):
        bundle, contract, scope = prepared
        paths = {"task": bundle.task_path, **bundle.files}
        identity = dict(bundle.source_sha256)
        identity[role] = sha(paths[role])
        provenance = copy.deepcopy(bundle.provenance)
        stat = paths[role].stat()
        provenance[role]["stat"] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        bundle = replace(bundle, source_sha256=identity, provenance=provenance)
        payload = contract.to_dict()
        payload["provenance"]["source_sha256"] = identity
        return bundle, TaskContract(payload, contract.alignment), replace(scope, train_sha256=identity["train"])

    def test_changed_source_and_malformed_rows_fail_closed(self):
        for role in ("task", "train", "test", "data_dictionary", "sample_submission"):
            with self.case("source_stat_drift_" + role):
                prepared = self.fixture.prepare()
                path = self.fixture.task if role == "task" else self.fixture.root / (role + ".csv")
                with path.open("a", encoding="utf-8") as stream:
                    stream.write("\n")
                self.rejects("source_changed", lambda: self.profile(prepared))
                self.fixture.save()
        with self.case("malformed_protected_row_structural_error_not_silently_skipped"):
            prepared = self.fixture.prepare()
            self.fixture.train[4].append("extra-field")
            csv_write(self.fixture.root / "train.csv", self.fixture.header, self.fixture.train)
            refreshed = self.refreshed_metadata(prepared, "train")
            self.rejects("csv_field_count", lambda: self.profile(refreshed))
        self.fixture.train[4].pop()
        self.fixture.save()
        with self.case("bad_header_rejected_by_own_reader"):
            prepared = self.fixture.prepare()
            self.fixture.header[1] = "changed_feature"
            csv_write(self.fixture.root / "train.csv", self.fixture.header, self.fixture.train)
            refreshed = self.refreshed_metadata(prepared, "train")
            self.rejects("schema_mismatch", lambda: self.profile(refreshed))

    def test_content_hash_guard_and_invalid_utf8(self):
        with self.case("same_size_same_mtime_content_drift_still_rejected"):
            prepared = self.fixture.prepare()
            path = self.fixture.root / "train.csv"
            original = path.read_bytes()
            stat = path.stat()
            modified = original.replace(b"private-train-0,1,", b"private-train-0,9,", 1)
            self.assertNotEqual(modified, original)
            path.write_bytes(modified)
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            self.assertEqual(path.stat().st_size, stat.st_size)
            self.rejects("source_changed", lambda: self.profile(prepared))
        self.fixture.save()
        with self.case("invalid_utf8_source_rejected_without_raw_content"):
            prepared = self.fixture.prepare()
            path = self.fixture.root / "train.csv"
            path.write_bytes(path.read_bytes() + b"\xff\n")
            refreshed = self.refreshed_metadata(prepared, "train")
            self.rejects("invalid_csv", lambda: self.profile(refreshed))

    def test_limits_are_hard_caps(self):
        for name, value in (("max_categories_per_column", 65), ("max_category_chars", 129),
                            ("max_total_category_chars", 262145), ("top_k", 11),
                            ("max_prompt_bytes", 32769), ("max_report_bytes", 262145),
                            ("max_record_chars", (1 << 20) + 1),
                            ("max_rows", 2_000_001), ("max_columns", 4097),
                            ("max_csv_bytes", (1 << 30) + 1), ("top_k", True)):
            with self.case("hard_limit_rejected_" + name + "_" + str(value)):
                self.rejects("invalid_limits", lambda: ProfileLimits(**{name: value}))

    def test_logical_record_bound_precedes_width_materialization(self):
        with self.case("H031-CSV-RECORD-001_many_small_multiline_fields_rejected_early"):
            prepared = self.fixture.prepare()
            path = self.fixture.root / "train.csv"
            # The old reader assembled 100002 fields before its width check;
            # each physical fragment and individual field remains very small.
            header = (",".join(self.fixture.header) + "\n").encode("utf-8")
            path.write_bytes(header + b'"a\nb",' * 100000 + b"x,y\n")
            refreshed = self.refreshed_metadata(prepared, "train")
            import aegml_input as inputs
            original = inputs._binary
            read_bytes = [0]

            class Monitored:
                def __init__(self, stream):
                    self.stream = stream
                def read(self, size=-1):
                    data = self.stream.read(size)
                    read_bytes[0] += len(data)
                    return data
                def __getattr__(self, name):
                    return getattr(self.stream, name)

            @contextmanager
            def monitored(path_, root, role, maximum):
                with original(path_, root, role, maximum) as stream:
                    yield Monitored(stream) if role == "train" else stream

            inputs._binary = monitored
            try:
                self.rejects("csv_record_limit", lambda: self.profile(
                    refreshed, limits=ProfileLimits(max_record_chars=64)))
            finally:
                inputs._binary = original
            # TextIO buffering may prefetch one block. It must not read the
            # full 600 kB record or materialize the full field list.
            self.assertGreater(read_bytes[0], 0)
            self.assertLessEqual(read_bytes[0], 16384)
            self.assertLess(read_bytes[0], path.stat().st_size // 10)
        self.fixture.save()
        with self.case("H031-CSV-RECORD-001_valid_multiline_record_below64_preserved"):
            # Only small lexical cells, with a valid newline in one category.
            for index, row in enumerate(self.fixture.train):
                row[:] = ["r" + str(index), "1", "2", "a\nb", "t", "3", "i"]
            for index, row in enumerate(self.fixture.test):
                row[:] = ["a\nb", "s" + str(index), "3", "1", "t", "i"]
            self.fixture.save()
            result = self.profile(limits=ProfileLimits(max_record_chars=64))
            cat = columns(result)["category"]["fit"]["categories"]
            self.assertEqual(cat["distinct_count"], 1)
            self.assertEqual(cat["top"], [{"value": "a\nb", "count": 3}])
            self.assertEqual(result["research"]["rows"], {"fit": 3, "test": 2})

    def test_missing_and_expired_shared_budget(self):
        prepared = self.fixture.prepare()
        with self.case("budget_is_mandatory"):
            self.rejects("budget_required", lambda: self.profile(prepared, budget=None))
        with self.case("expired_RunBudget_propagates_without_replacement"):
            exhausted = RunBudget(0, 1, 0, clock=lambda: 2_000_000_000)
            with self.assertRaises(BudgetExpired):
                self.profile(prepared, budget=exhausted)
        with self.case("same_budget_checked_during_stream_and_serialization"):
            class CountingBudget:
                calls = 0
                def require(self):
                    self.calls += 1
                    if self.calls > 30:
                        raise BudgetExpired("fixture_budget_exhausted")
            current = CountingBudget()
            with self.assertRaises(BudgetExpired):
                self.profile(prepared, budget=current)
            self.assertEqual(current.calls, 31)

    def test_report_and_prompt_UTF8_budgets_determinism_wide_schema(self):
        with self.case("4096_columns_valid_and_explicitly_truncated_under_UTF8_caps"):
            feature_names = ["измерение_" + str(i) for i in range(4094)]
            self.fixture.header = ["row_key", "outcome", *feature_names]
            self.fixture.test_header = ["row_key", *feature_names]
            self.fixture.train = [["train-" + str(i), str(i), *(["я🙂" * 16] * len(feature_names))] for i in range(2)]
            self.fixture.test = [["test-" + str(i), *(["новое"] * len(feature_names))] for i in range(2)]
            self.fixture.dictionary = [["row_key", "id", "string"], ["outcome", "target", "numeric"],
                                       *[[name, "feature", "text"] for name in feature_names]]
            self.fixture.save()
            prepared = self.fixture.prepare((0,))
            limits = ProfileLimits(max_prompt_bytes=2048, max_report_bytes=16384)
            result = self.profile(prepared, limits=limits)
            repeated = self.profile(prepared, limits=limits)
            self.assertEqual(result, repeated)
            self.assertEqual(result["report_bytes"], len(canonical(result).encode("utf-8")))
            self.assertLessEqual(result["report_bytes"], 16384)
            self.assertLessEqual(len(result["prompt"].encode("utf-8")), 2048)
            self.assertTrue(result["truncation"]["research"]["truncated"])
            self.assertTrue(result["truncation"]["prompt"]["truncated"])
            self.assertNotIn("source_sha256", result["prompt"])
            self.assertNotIn("run_id", result["prompt"])
            self.assertNotIn("protected_count", result["prompt"])
            # Source-size/stat changes cannot decide which research columns fit.
            self.fixture.train[1][2] = "protected-new-longer-value"
            self.fixture.save()
            poisoned = self.profile(self.fixture.prepare((0,)), limits=limits)
            self.assertEqual(poisoned["research"], result["research"])
            self.assertEqual(poisoned["prompt"], result["prompt"])

    def test_readonly_and_full_file_above_twenty_MiB(self):
        with self.case("full_21MiB_stream_reads_last_fit_row_without_cutoff"):
            self.fixture.header = ["row_key", "feature", "outcome", "text"]
            self.fixture.test_header = ["row_key", "feature", "text"]
            size = 22 * 1024
            self.fixture.train = [["train-" + str(i), "7" if i == size - 1 else "1", "2", "x" * 1024] for i in range(size)]
            self.fixture.test = [["test-0", "1", "short"], ["test-1", "2", "short"]]
            self.fixture.dictionary = [["row_key", "id", "string"], ["feature", "feature", "numeric"],
                                       ["outcome", "target", "numeric"], ["text", "feature", "text"]]
            self.fixture.save()
            self.assertGreater((self.fixture.root / "train.csv").stat().st_size, 20 << 20)
            prepared = self.fixture.prepare((size - 1,))
            paths = [self.fixture.task, *prepared[0].files.values()]
            before = {str(path): (sha(path), path.stat().st_mtime_ns) for path in paths}
            result = self.profile(prepared)
            self.assertEqual(columns(result)["feature"]["fit"]["numeric"]["mean"], 7.0)
            self.assertEqual({str(path): (sha(path), path.stat().st_mtime_ns) for path in paths}, before)
            self.assertFalse((self.fixture.root / "submission.csv").exists())
            self.assertFalse((self.fixture.root / ".aegml_runs").exists())

    def test_actual_public_regression(self):
        self.actual("regression")

    def test_actual_public_classification(self):
        self.actual("classification")

    def actual(self, kind):
        with self.case("actual_public_" + kind + "_isolated_readonly_profile"):
            if not INCLUDE_ACTUAL:
                self.skipTest("--actual-inputs not requested")
            result = subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--worker", kind],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    encoding="utf-8", timeout=180, check=False,
                                    env={"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONUTF8": "1"})
            self.assertEqual(result.returncode, 0, "public profile child failed; raw output suppressed")
            self.assertLess(len(result.stdout.encode("utf-8")), 16384)
            self.assertEqual(result.stderr, "", "public child stderr suppressed")
            record = json.loads(result.stdout)
            self.assertEqual(record["status"], "PASS_READONLY_EXPLICIT_SCOPE_ONLY")
            self.assertTrue(record["source_unchanged"])
            self.assertFalse(record["final_H033_split_accepted"])
            self.assertTrue(record["profile_split_bridge_checked"])
            self.assertLessEqual(record["prompt_bytes"], 32768)
            self.assertLessEqual(record["report_bytes"], 262144)
            self.assertEqual(record["profiled_fit_count"], record["scope_fit_count"])
            if kind == "regression":
                self.assertGreater(record["train_bytes"], 20 << 20)
                self.assertEqual(record["scope_counts"], {"fit": 22054, "inner": 12946, "outer": 18308})
            else:
                self.assertEqual(record["scope_counts"], {"fit": 56108, "inner": 14028, "outer": 17534})
            ACTUAL.append(record)


def public_worker(kind):
    started = time.monotonic()
    root = ROOT / "drive-download-20261019T181414Z-1-001" / PUBLIC[kind]
    paths = [root / name for name in ("task.md", "train.csv", "test.csv", "data_dictionary.csv", "sample_submission.csv")]
    before = {path.name: (sha(path), path.stat().st_mtime_ns) for path in paths}
    shared = budget()
    contract = build_task_contract(root / "task.md", budget=shared)
    bundle = discover_inputs(root / "task.md", shared)
    rows = contract.to_dict()["provenance"]["row_mapping"]["row_counts"]["train"]
    plan = build_split_plan(bundle, contract, strategy="temporal" if kind == "regression" else "stratified",
                            time_column="Year_Factor" if kind == "regression" else None, budget=shared)
    fit, protected = plan.fit_indices, plan.inner_indices + plan.outer_indices
    policy = plan.policy_id
    scope = ProfileScope(tuple(fit), tuple(protected), rows, bundle.source_sha256["train"], policy)
    profile_started = time.monotonic()
    result = profile_task(bundle, contract, scope, budget=shared)
    elapsed = time.monotonic() - profile_started
    after = {path.name: (sha(path), path.stat().st_mtime_ns) for path in paths}
    if before != after:
        raise RuntimeError("actual_source_changed")
    peak = None
    if sys.platform.startswith("linux"):
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(canonical({"dataset": kind, "status": "PASS_READONLY_EXPLICIT_SCOPE_ONLY",
                     "scope_policy": policy, "final_H033_split_accepted": False,
                     "profile_split_bridge_checked": True,
                     "scope_counts": {"fit": len(plan.fit_indices), "inner": len(plan.inner_indices), "outer": len(plan.outer_indices)},
                     "partition_sha256": plan.partition_sha256,
                     "train_bytes": (root / "train.csv").stat().st_size,
                     "source_sha256": bundle.source_sha256, "source_unchanged": before == after,
                     "schema_sha256": result["provenance"]["schema_sha256"],
                     "scope_fit_count": len(fit), "scope_protected_count": len(protected),
                     "profiled_fit_count": result["research"]["rows"]["fit"],
                     "prompt_bytes": result["prompt_bytes"], "report_bytes": result["report_bytes"],
                     "profile_elapsed_seconds": round(elapsed, 6),
                     "end_to_end_elapsed_seconds": round(time.monotonic() - started, 6),
                     "process_peak_RSS_MiB": peak, "API_calls": 0, "model_fits": 0}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--actual-inputs", action="store_true")
    parser.add_argument("--worker", choices=tuple(PUBLIC))
    args = parser.parse_args()
    # Fail immediately if any imported future helper tries a socket operation.
    def deny_network(event, _):
        if event in {"socket.connect", "socket.getaddrinfo"}:
            raise RuntimeError("offline_check_network_forbidden")
    sys.addaudithook(deny_network)
    if args.worker:
        public_worker(args.worker)
        return 0
    global INCLUDE_ACTUAL
    INCLUDE_ACTUAL = args.actual_inputs
    before = {name: sha(ROOT / name) for name in SOURCES}
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProfileChecks)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    after = {name: sha(ROOT / name) for name in SOURCES}
    receipt = {"phase": "H03.1", "status": "PASS_H03_1_PROFILE_ONLY" if result.wasSuccessful() and before == after else "FAIL",
               "python": platform.python_version(), "platform": platform.platform(),
               "test_methods_run": result.testsRun, "behavior_cases": len(CASES),
               "passed_cases": sum(item["status"] == "PASS" for item in CASES),
               "skipped_cases": sum(item["status"] == "SKIP" for item in CASES),
               "failures": len(result.failures), "errors": len(result.errors), "cases": CASES,
               "actual_inputs": ACTUAL, "source_sha256": before, "source_sha256_after": after,
               "source_unchanged": before == after, "API_calls": 0, "model_fits": 0,
               "H033_final_split_accepted": False, "entrypoint_connected": False}
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        with args.receipt.open("x", encoding="utf-8") as stream:
            stream.write(canonical(receipt) + "\n")
    print(canonical({key: receipt[key] for key in ("status", "test_methods_run", "behavior_cases", "passed_cases", "skipped_cases", "failures", "errors", "source_unchanged")}))
    return 0 if receipt["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
