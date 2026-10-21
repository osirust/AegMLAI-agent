"""H03.4 bounded validator/atomic writer acceptance; Linux Python 3.12 only."""
import argparse
from contextlib import contextmanager
from dataclasses import replace
import csv
import errno
import hashlib
import importlib.util
import json
from pathlib import Path
import resource
import shutil
import sys
import tempfile
import tracemalloc
from time import monotonic, monotonic_ns
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CASES, ACTUAL = [], []
S = C = I = FIXTURE = None


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def budget():
    return C.RunBudget(monotonic_ns(), 120, 10)


def write_csv(p, columns, rows):
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(columns)
        w.writerows(rows)


class SubmissionChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aegml-h034-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.output = self.base / "submission.csv"

    @contextmanager
    def case(self, label):
        record = {"test": self.id(), "case": label, "status": "RUNNING"}
        CASES.append(record)
        try:
            yield
        except BaseException:
            record["status"] = "FAIL"
            raise
        else:
            record["status"] = "PASS"

    def schema(self, *, kind="numeric", order=(0, 1, 2), ids=(("001",), ("NA",), ("1",)), limits=None):
        label = kind == "label"
        probability = kind == "probability"
        return S.SubmissionSchema(self.output, ("id", "pA", "pB") if probability else ("id", "y"),
                ("id",), ("pA", "pB") if probability else ("y",), kind,
                "log_loss" if probability else "macro_f1" if label else "rmse",
                ("B", "A") if probability else (), None,
                frozenset({"A", "B", "NA"}) if label else frozenset(), tuple(ids), tuple(order),
                (("train", "0" * 64),), limits or S.SubmissionLimits())

    def assert_old_preserved(self, action, code=None):
        sentinel = b"id,y\n001,123\nNA,456\n1,789\n"
        self.output.write_bytes(sentinel)
        before = (sha(self.output), self.output.stat().st_mtime_ns)
        with self.assertRaises((S.SubmissionError, C.BudgetExpired)) as caught:
            action()
        if code:
            self.assertEqual(getattr(caught.exception, "code", None), code)
        self.assertEqual((sha(self.output), self.output.stat().st_mtime_ns), before)
        self.assertEqual(list(self.base.glob(".aegml-submission-*")), [])

    def test_valid_fresh_atomic_numeric_and_sha(self):
        with self.case("numeric_full_publication_and_independent_sha"):
            schema = self.schema()
            result = S.write_submission([1.25, -3.5, 4], schema, budget=budget())
            self.assertTrue(result["published"])
            self.assertEqual(result["row_count"], 3)
            self.assertEqual(result["sha256"], sha(self.output))
            self.assertEqual(S.validate_submission(self.output, schema, budget=budget())["sha256"], result["sha256"])
            self.assertEqual(list(csv.reader(self.output.open()))[1:], [["001", "1.25"], ["NA", "-3.5"], ["1", "4"]])

    def test_invalid_csv_matrix(self):
        schema = self.schema()
        cases = {"empty": b"", "header_only": b"id,y\n", "extra_index": b",id,y\n0,001,1\n1,NA,2\n2,1,3\n",
                 "wrong_order": b"id,y\nNA,1\n001,2\n1,3\n", "normalized_id": b"id,y\n1,1\nNA,2\n1,3\n",
                 "duplicate_id": b"id,y\n001,1\n001,2\n1,3\n", "missing_row": b"id,y\n001,1\nNA,2\n",
                 "extra_row": b"id,y\n001,1\nNA,2\n1,3\n2,4\n", "extra_cell": b"id,y\n001,1,2\nNA,2\n1,3\n",
                 "nan": b"id,y\n001,NaN\nNA,2\n1,3\n", "infinity": b"id,y\n001,Inf\nNA,2\n1,3\n",
                 "empty_prediction": b"id,y\n001,\nNA,2\n1,3\n", "invalid_utf8": b"id,y\n001,\xff\nNA,2\n1,3\n",
                 "malformed_quote": b'id,y\n001,"1\nNA,2\n1,3\n', "nul": b"id,y\n001,1\x00\nNA,2\n1,3\n"}
        for name, raw in cases.items():
            with self.subTest(name=name), self.case("reject_" + name):
                self.output.write_bytes(raw)
                with self.assertRaises(S.SubmissionError):
                    S.validate_submission(self.output, schema, budget=budget())

    def test_label_vocabulary_and_literal_NA(self):
        with self.case("literal_NA_valid_class_and_unicode_raw_id"):
            schema = self.schema(kind="label", ids=(("001",), ("NA",), ("ключ,\n二",)))
            result = S.write_submission(["A", "NA", "B"], schema, budget=budget())
            self.assertTrue(result["published"])
            self.assertEqual(S.validate_submission(self.output, schema, budget=budget())["row_count"], 3)
        for item in ("unknown", None, True, float("nan")):
            with self.subTest(item=str(item)), self.case("label_rejected_" + str(item)):
                self.assert_old_preserved(lambda: S.write_submission(["A", item, "B"], self.schema(kind="label"), budget=budget()))

    def test_probability_mapping_and_range(self):
        schema = self.schema(kind="probability")
        with self.case("explicit_class_order_probability_publication"):
            result = S.write_submission([[.2, .8], [.5, .5], [1, 0]], schema, budget=budget(), prediction_class_order=["B", "A"])
            self.assertTrue(result["published"])
        for name, matrix, order in [
            ("wrong_class_order", [[.2, .8]] * 3, ["A", "B"]),
            ("unspecified_class_order", [[.2, .8]] * 3, None),
            ("bad_sum", [[.2, .9]] * 3, ["B", "A"]),
            ("out_of_range", [[-.2, 1.2]] * 3, ["B", "A"]),
            ("nonfinite", [[float("nan"), 1]] * 3, ["B", "A"]),
            ("wrong_width", [[1]] * 3, ["B", "A"]),
            ("boolean", [[False, True]] * 3, ["B", "A"]),
        ]:
            with self.subTest(name=name), self.case("probability_reject_" + name):
                self.assert_old_preserved(lambda: S.write_submission(matrix, schema, budget=budget(), prediction_class_order=order))

    def test_binary_probability_positive_label(self):
        schema = replace(self.schema(), kind="probability", metric_name="roc_auc", positive_label="yes")
        with self.case("positive_probability_requires_explicit_orientation"):
            self.assert_old_preserved(lambda: S.write_submission([.2, .4, .8], schema, budget=budget()), "prediction_positive_label_mismatch")
        with self.case("correct_binary_positive_probability"):
            self.assertTrue(S.write_submission([.2, .4, .8], schema, budget=budget(), prediction_positive_label="yes")["published"])

    def test_numpy_class_order_accepted(self):
        import numpy as np
        with self.case("numpy_estimator_classes_order_not_boolean_tested"):
            schema = self.schema(kind="probability")
            out = S.write_submission(np.array([[.2, .8], [.5, .5], [1, 0]]), schema,
                                     budget=budget(), prediction_class_order=np.array(["B", "A"]))
            self.assertTrue(out["published"])

    def test_summary_streaming_memory_and_budget(self):
        with self.case("large_ID_summary_avoids_full_JSON_allocation"):
            count = 6000
            ids = tuple((str(i) + "x" * 2040,) for i in range(count))
            schema = self.schema(ids=ids, order=tuple(range(count)))
            tracemalloc.start()
            try:
                out = schema.summary(budget=budget())
                peak = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
            self.assertEqual(out["row_count"], count)
            self.assertLess(peak, 4 << 20)
            self.assertEqual(out["expected_ids_sha256"], hashlib.sha256(json.dumps(ids, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest())
        with self.case("expiry_during_summary_cannot_return_VALID"):
            schema = self.schema()
            self.output.write_text("id,y\n001,1\nNA,2\n1,3\n")
            clock = [0]
            shared = C.RunBudget(0, 10, 1, clock=lambda: clock[0])
            original = S.SubmissionSchema.summary
            def late(obj, **kwargs):
                clock[0] = 20_000_000_000
                return original(obj, **kwargs)
            with patch.object(S.SubmissionSchema, "summary", late):
                with self.assertRaises(C.BudgetExpired):
                    S.validate_submission(self.output, schema, budget=shared)

    def test_prediction_shape_types_and_schema_rejection(self):
        for name, values in [("missing", [1, 2]), ("extra", [1, 2, 3, 4]), ("generator", iter([1, 2, 3])),
                             ("strings", ["1", 2, 3]), ("boolean", [True, 2, 3]), ("nonfinite", [float("inf"), 2, 3])]:
            with self.subTest(name=name), self.case("predict_reject_" + name):
                self.assert_old_preserved(lambda: S.write_submission(values, self.schema(), budget=budget()))
        for name, changes in [("empty", {"output_to_test": (), "expected_ids": ()}),
                              ("repeated_map", {"output_to_test": (0, 0, 2)}),
                              ("bool_map", {"output_to_test": (False, 1, 2)}),
                              ("wrong_ids", {"expected_ids": (("1",),)}),
                              ("mutable", {"columns": ["id", "y"]})]:
            with self.subTest(name=name), self.case("schema_reject_" + name):
                with self.assertRaises(S.SubmissionError):
                    replace(self.schema(), **changes)

    def test_size_record_and_deadline_limits(self):
        with self.case("writer_byte_limit_preserves_old"):
            schema = self.schema(limits=S.SubmissionLimits(max_bytes=10))
            self.assert_old_preserved(lambda: S.write_submission([1, 2, 3], schema, budget=budget()), "submission_too_large")
        with self.case("logical_multiline_record_bound"):
            self.output.write_text('id,y\n"001' + '\n' * 80 + '",1\nNA,2\n1,3\n')
            schema = self.schema(limits=S.SubmissionLimits(max_record_chars=64))
            with self.assertRaises(S.SubmissionError) as caught:
                S.validate_submission(self.output, schema, budget=budget())
            self.assertEqual(caught.exception.code, "csv_record_too_large")
        with self.case("shared_deadline_expiry_keeps_old"):
            expired = C.RunBudget(0, 10, 1, clock=lambda: 20_000_000_000)
            self.assert_old_preserved(lambda: S.write_submission([1, 2, 3], self.schema(), budget=expired))
        with self.case("missing_budget_rejected"):
            self.assert_old_preserved(lambda: S.write_submission([1, 2, 3], self.schema(), budget=None), "missing_shared_budget")

    def test_io_failure_before_replace_preserves_old(self):
        for name, method in [("fsync_failure", "fsync"), ("replace_failure", "replace")]:
            with self.subTest(name=name), self.case(name):
                with patch.object(S.os, method, side_effect=OSError(errno.ENOSPC, "synthetic disk full")):
                    self.assert_old_preserved(lambda: S.write_submission([1, 2, 3], self.schema(), budget=budget()), "submission_publication_io_error")
        with self.case("directory_fsync_failure_after_valid_commit_is_explicit"):
            with patch.object(S.os, "fsync", side_effect=[None, OSError(errno.EIO, "synthetic dir fsync")]):
                result = S.write_submission([4, 5, 6], self.schema(), budget=budget())
            self.assertTrue(result["published"])
            self.assertFalse(result["directory_fsynced"])
            self.assertIsNotNone(result["warning"])
            self.assertEqual(result["sha256"], sha(self.output))
            S.validate_submission(self.output, self.schema(), budget=budget())

    def test_symlink_and_external_candidate_rejected(self):
        outside = self.base / "outside.csv"
        outside.write_bytes(b"preserve this file")
        with self.case("existing_output_symlink_not_followed"):
            self.output.symlink_to(outside)
            with self.assertRaises(S.SubmissionError):
                S.write_submission([1, 2, 3], self.schema(), budget=budget())
            self.assertEqual(outside.read_bytes(), b"preserve this file")
            self.output.unlink()
        other = self.base / "other"
        other.mkdir()
        candidate = other / "candidate.csv"
        write_csv(candidate, ["id", "y"], [["001", 1], ["NA", 2], ["1", 3]])
        with self.case("external_candidate_rejected"):
            with self.assertRaises(S.SubmissionError) as caught:
                S.validate_submission(candidate, self.schema(), budget=budget())
            self.assertEqual(caught.exception.code, "external_submission_path")

    def test_contract_sample_permutation_and_target_first(self):
        fixture = FIXTURE.Fixture(self.base / "sample")
        fixture.output_order = "sample"
        fixture.reorder("sample_submission", ["y", "id"])
        fixture.save()
        with self.case("task_sample_order_targets_first_raw_ID_permutation"):
            shared = budget()
            contract = C.build_task_contract(fixture.task, budget=shared)
            bundle = I.discover_inputs(fixture.task, shared)
            schema = S.build_submission_schema(bundle, contract, budget=shared)
            result = S.write_submission([10, 20, 30], schema, budget=shared)
            rows = list(csv.reader(schema.output_path.open()))
            self.assertEqual(rows, [["y", "id"], ["30", "1"], ["10", "001"], ["20", "NA"]])
            self.assertEqual(result["row_count"], 3)
        with self.case("source_hash_change_before_schema_refused"):
            original = fixture.files["test"].read_text()
            fixture.files["test"].write_text(original.replace("cat", "rat"))
            with self.assertRaises(S.SubmissionError) as caught:
                S.build_submission_schema(bundle, contract, budget=budget())
            self.assertEqual(caught.exception.code, "source_changed")

    def test_positional_output_only_ids(self):
        fixture = FIXTURE.Fixture(self.base / "positional")
        fixture.row_mapping = "positional"
        fixture.headers["test"] = ["right", "left"]
        fixture.rows["test"] = [["cat", "0"], ["dog", "1"], ["cat", "0"]]
        fixture.save()
        with self.case("explicit_positional_output_only_template_IDs"):
            shared = budget()
            contract = C.build_task_contract(fixture.task, budget=shared)
            schema = S.build_submission_schema(I.discover_inputs(fixture.task, shared), contract, budget=shared)
            result = S.write_submission([7, 8, 9], schema, budget=shared)
            self.assertTrue(result["published"])
            self.assertEqual(list(csv.reader(schema.output_path.open()))[1:], [["1", "7"], ["001", "8"], ["NA", "9"]])

    def test_review_mapping_bound_to_contract_and_actual_ids(self):
        fixture = FIXTURE.Fixture(self.base / "mapping-bind")
        fixture.save()
        shared = budget()
        contract = C.build_task_contract(fixture.task, budget=shared)
        bundle = I.discover_inputs(fixture.task, shared)
        output = Path(contract.to_dict()["output_path"])
        sentinel = b"id,y\n001,7\nNA,8\n1,9\n"
        for name in ("stale_output_digest", "forged_digest_test_nonidentity", "sample_map_wrong_actual_ids",
                     "wrong_count", "wrong_order", "bool_mapping"):
            with self.subTest(name=name), self.case("mapping_bind_" + name):
                payload, sidecar = contract.to_dict(), contract.alignment
                if name in {"stale_output_digest", "forged_digest_test_nonidentity"}:
                    sidecar["output_to_test"] = [2, 0, 1]
                elif name == "sample_map_wrong_actual_ids":
                    sidecar["sample_to_test"] = [1, 2, 0]
                elif name == "wrong_count":
                    sidecar["row_counts"]["test"] = 4
                elif name == "wrong_order":
                    sidecar["output_order"] = "sample"
                else:
                    sidecar["sample_to_test"] = [False, 1, 2]
                if name in {"forged_digest_test_nonidentity", "sample_map_wrong_actual_ids"}:
                    field = "output_to_test" if name.startswith("forged") else "sample_to_test"
                    payload["provenance"]["row_mapping"][field]["sha256"] = hashlib.sha256(C._json_bytes(sidecar[field])).hexdigest()
                output.write_bytes(sentinel)
                with self.assertRaises(S.SubmissionError):
                    S.build_submission_schema(bundle, C.TaskContract(payload, sidecar), budget=budget())
                self.assertEqual(output.read_bytes(), sentinel)
                self.assertEqual(list(output.parent.glob(".aegml-submission-*")), [])
        with self.case("mapping_bind_valid_TEST_identity_with_permuted_sample"):
            schema = S.build_submission_schema(bundle, contract, budget=shared)
            self.assertEqual(schema.output_to_test, (0, 1, 2))
            self.assertTrue(S.write_submission([10, 20, 30], schema, budget=shared)["published"])
        fixture.output_order = "sample"
        fixture.save()
        contract = C.build_task_contract(fixture.task, budget=shared)
        bundle = I.discover_inputs(fixture.task, shared)
        with self.case("mapping_bind_valid_SAMPLE_actual_nonidentity"):
            schema = S.build_submission_schema(bundle, contract, budget=shared)
            self.assertEqual(schema.output_to_test, (2, 0, 1))
        with self.case("mapping_bind_SAMPLE_rehashed_wrong_map"):
            payload, sidecar = contract.to_dict(), contract.alignment
            sidecar["output_to_test"] = [0, 1, 2]
            payload["provenance"]["row_mapping"]["output_to_test"]["sha256"] = hashlib.sha256(C._json_bytes(sidecar["output_to_test"])).hexdigest()
            with self.assertRaises(S.SubmissionError) as caught:
                S.build_submission_schema(bundle, C.TaskContract(payload, sidecar), budget=budget())
            self.assertEqual(caught.exception.code, "mapping_output_order_mismatch")

    def test_review_destination_is_current_task_not_same_bytes_elsewhere(self):
        fixture = FIXTURE.Fixture(self.base / "original-task")
        fixture.save()
        copied = self.base / "current-task"
        shutil.copytree(fixture.root, copied)
        shared = budget()
        old_contract = C.build_task_contract(fixture.task, budget=shared)
        bundle = I.discover_inputs(copied / "task.md", shared)
        previous = fixture.root / "submission.csv"
        previous.write_bytes(b"id,y\n001,7\nNA,8\n1,9\n")
        before = (sha(previous), previous.stat().st_mtime_ns)
        with self.case("same_source_bytes_different_task_destination_refused"):
            self.assertEqual(old_contract.to_dict()["provenance"]["source_sha256"], bundle.source_sha256)
            with self.assertRaises(S.SubmissionError) as caught:
                S.build_submission_schema(bundle, old_contract, budget=shared)
            self.assertEqual(caught.exception.code, "contract_task_destination_mismatch")
            self.assertEqual((sha(previous), previous.stat().st_mtime_ns), before)
            self.assertFalse((copied / "submission.csv").exists())
        local = C.build_task_contract(copied / "task.md", budget=shared)
        with self.case("current_task_contract_publishes_only_current_directory"):
            schema = S.build_submission_schema(bundle, local, budget=shared)
            self.assertTrue(S.write_submission([10, 20, 30], schema, budget=shared)["published"])
            self.assertEqual(schema.output_path.parent, copied)
            self.assertEqual((sha(previous), previous.stat().st_mtime_ns), before)
        for field in ("task_path", "input_paths", "output_path"):
            with self.subTest(field=field), self.case("explicit_destination_field_mismatch_" + field):
                payload = local.to_dict()
                payload[field] = old_contract.to_dict()[field]
                with self.assertRaises(S.SubmissionError) as caught:
                    S.build_submission_schema(bundle, C.TaskContract(payload, local.alignment), budget=shared)
                self.assertEqual(caught.exception.code, "contract_task_destination_mismatch")
                self.assertEqual((sha(previous), previous.stat().st_mtime_ns), before)

    def test_actual_public_full_synthetic_predictions_only(self):
        for folder in ("Регрессия", "Многоклассовая классификация"):
            with self.subTest(dataset=folder), self.case("actual_full_writer_" + folder):
                source = ROOT / "drive-download-20261019T181414Z-1-001" / folder
                stage = self.base / folder
                stage.mkdir()
                names = ["task.md", "train.csv", "test.csv", "data_dictionary.csv", "sample_submission.csv"]
                before = {n: sha(source / n) for n in names}
                for name in names:
                    shutil.copyfile(source / name, stage / name)
                started = monotonic()
                shared = budget()
                contract = C.build_task_contract(stage / "task.md", budget=shared)
                bundle = I.discover_inputs(stage / "task.md", shared)
                payload = contract.to_dict()
                classification = payload["task_type"] == "classification"
                if classification:
                    self.assertIn("Normal", bundle.task_text)
                schema = S.build_submission_schema(bundle, contract, budget=shared, allowed_labels=["Normal"] if classification else None)
                predictions = ["Normal" if classification else 0.0] * schema.row_count
                result = S.write_submission(predictions, schema, budget=shared)
                independently = S.validate_submission(schema.output_path, schema, budget=shared)
                self.assertEqual(independently["sha256"], result["sha256"])
                self.assertEqual({n: sha(source / n) for n in names}, before)
                self.assertEqual(result["row_count"], 41166 if classification else 22449)
                ACTUAL.append({"dataset": folder, "status": "PASS_WRITER_FIXTURE_ONLY", "row_count": schema.row_count,
                               "bytes": result["bytes"], "submission_sha256": result["sha256"],
                               "source_sha256_preserved": True, "seconds": monotonic()-started,
                               "peak_rss_mib_process": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
                               "predictions_origin": "synthetic constants for format checks, NOT trained baseline",
                               "quality_metric_computed": False, "original_input_directory_written": False})


def main():
    global S, C, I, FIXTURE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
        parser.error("requires Linux Python3.12")
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    stream = args.receipt.open("x", encoding="utf-8")
    sources = ["aegml_submission.py", "scripts/check_h034_submission.py", "aegml_contracts.py", "aegml_input.py", "aegml_schemas.py"]
    before = {n: sha(ROOT / n) for n in sources}
    import aegml_submission as S
    import aegml_contracts as C
    import aegml_input as I
    spec = importlib.util.spec_from_file_location("h023_fixture", ROOT / "scripts/check_h023_contract.py")
    FIXTURE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(FIXTURE)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SubmissionChecks))
    after = {n: sha(ROOT / n) for n in sources}
    passed = result.wasSuccessful() and before == after and len(ACTUAL) == 2
    receipt = {"status": "PASS_H03_4_SUBMISSION_COMPONENT_ONLY" if passed else "FAIL_H03_4_SUBMISSION_COMPONENT",
               "python": sys.version, "test_methods_run": result.testsRun,
               "behavior_cases_checked": len(CASES), "behavior_cases_passed": sum(c["status"] == "PASS" for c in CASES),
               "cases": CASES, "actual_public": ACTUAL, "source_sha256": before, "source_sha256_after": after,
               "source_unchanged": before == after, "failures": [{"test": t.id(), "detail": e} for t,e in result.failures],
               "errors": [{"test": t.id(), "detail": e} for t,e in result.errors], "skips": len(result.skipped),
               "live_api_calls": 0, "model_fit_calls": 0, "official_platform_image_verified": False,
               "H05_boundary_accepted": False, "new_official_submission": False}
    with stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k: receipt[k] for k in ("status", "test_methods_run", "behavior_cases_checked", "behavior_cases_passed")}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
