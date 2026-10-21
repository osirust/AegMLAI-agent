"""Meaningful data-only H04 artifact checks, Linux Python3.12, no estimator/API."""
from __future__ import annotations

import argparse
from array import array
from contextlib import contextmanager, redirect_stdout, redirect_stderr
import csv
import hashlib
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
A = C = None
CASES = []
SOURCES = ("aegml_artifacts.py", "scripts/check_h04_artifacts.py", "aegml_contracts.py", "requirements.txt")
EXPECTED_REQUIREMENTS = "9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ArtifactChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aegml-h04-artifacts-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.task = self.base / "task.md"
        self.task.write_text("Task type: regression\nTarget: y\nMetric: RMSE\n", encoding="utf-8")
        self.input_csv = self.base / "train.csv"
        self.input_csv.write_bytes(b"x,y\n1,2\n")
        self.previous = self.base / "submission.csv"
        self.previous.write_bytes(b"id,y\n001,123\n")
        self.inputs = {p.name: (sha(p), p.stat().st_mtime_ns) for p in (self.task, self.input_csv, self.previous)}
        self.now = [0]
        self.shared = C.RunBudget(0, 100, 10, clock=lambda: self.now[0])
        self.store = A.create_run_artifacts(self.task, run_id="a" * 32, budget=self.shared)

    def tearDown(self):
        for path in (self.task, self.input_csv, self.previous):
            self.assertEqual((sha(path), path.stat().st_mtime_ns), self.inputs[path.name],
                             "original input or prior submission changed")

    @contextmanager
    def case(self, name):
        record = {"test": self.id(), "case": name, "status": "RUNNING"}
        CASES.append(record)
        try:
            yield
        except BaseException:
            record["status"] = "FAIL"
            raise
        else:
            record["status"] = "PASS"

    def refusal(self, function, code=None):
        with self.assertRaises(A.ArtifactError) as caught:
            function()
        if code:
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(list(self.store.rootpath.glob(".tmp-*")), [], "failed write left temporary payload")
        return caught.exception

    def read_predictions(self, name):
        with (self.store.rootpath / name).open("r", encoding="utf-8", newline="") as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows[0], ["row_index", "prediction_json"])
        return [(int(row[0]), json.loads(row[1], parse_constant=lambda _: self.fail("nonfinite JSON"))) for row in rows[1:]]

    def test_fresh_task_local_private_directory_and_no_resume(self):
        with self.case("fresh_task_local_run_and_private_modes"):
            self.assertEqual(self.store.rootpath.parent, self.base.resolve())
            self.assertEqual(self.store.rootpath.name, ".aegml-run-" + "a" * 32)
            self.assertEqual(stat.S_IMODE(self.store.rootpath.stat().st_mode), 0o700)
            self.store.write_json("status.json", {"phase": "started"})
            self.assertEqual(stat.S_IMODE((self.store.rootpath / "status.json").stat().st_mode), 0o600)
        with self.case("existing_run_refused_without_touching_owned_file"):
            path = self.store.rootpath / "status.json"
            before = sha(path), path.stat().st_mtime_ns
            self.refusal(lambda: A.create_run_artifacts(self.task, run_id="a" * 32, budget=self.shared), "run_exists")
            self.assertEqual((sha(path), path.stat().st_mtime_ns), before)

    def test_run_id_and_task_sources_are_validated_before_creation(self):
        for name, value in (("traversal", "../outside"), ("uppercase", "A" * 32), ("empty", ""), ("suffix", "a" * 32 + "/x")):
            with self.subTest(name=name), self.case("invalid_run_id_" + name):
                before = set(self.base.iterdir())
                self.refusal(lambda: A.create_run_artifacts(self.task, run_id=value, budget=self.shared), "invalid_run_id")
                self.assertEqual(set(self.base.iterdir()), before)
        with self.case("missing_task_is_static_error_and_no_new_run"):
            self.refusal(lambda: A.create_run_artifacts(self.base / "missing", run_id="b" * 32, budget=self.shared))
            self.assertFalse((self.base / (".aegml-run-" + "b" * 32)).exists())
        with self.case("directory_task_refused"):
            self.refusal(lambda: A.create_run_artifacts(self.base, run_id="b" * 32, budget=self.shared), "invalid_task_source")
        with self.case("oversize_task_refused_before_run_creation"):
            large = self.base / "large.md"
            large.write_bytes(b"x" * ((1 << 20) + 1))
            self.refusal(lambda: A.create_run_artifacts(large, run_id="b" * 32, budget=self.shared), "invalid_task_source")
            self.assertFalse((self.base / (".aegml-run-" + "b" * 32)).exists())

    def test_canonical_json_and_complete_provenance_survive_roundtrip(self):
        with self.case("canonical_utf8_json_code_config_split_prediction_provenance"):
            payload = {"phase": "inner_scored", "source_sha256": {"train": "1" * 64},
                       "code_sha256": "2" * 64, "config_sha256": "3" * 64,
                       "split_sha256": "4" * 64, "prediction_sha256": "5" * 64,
                       "elapsed_seconds": 1.25, "versions": {"python": "3.12.3"}, "note": "проверка"}
            record = self.store.write_json("experiment.json", payload)
            path = self.store.rootpath / "experiment.json"
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), payload)
            self.assertEqual(path.read_bytes(), (json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":"), allow_nan=False) + "\n").encode())
            self.assertEqual((record["sha256"], record["bytes"]), (sha(path), path.stat().st_size))
            self.assertEqual(self.store.record(path), record)
            record["sha256"] = "0" * 64
            self.assertEqual(self.store.record("experiment.json")["sha256"], sha(path))

    def test_json_exclusive_and_only_owned_record_update(self):
        path = self.store.rootpath / "status.json"
        self.store.write_json("status.json", {"status": "running"})
        before = sha(path), path.stat().st_mtime_ns
        with self.case("exclusive_json_preserves_old_bytes_and_mtime"):
            self.refusal(lambda: self.store.write_json("status.json", {"status": "other"}), "artifact_exists")
            self.assertEqual((sha(path), path.stat().st_mtime_ns), before)
        with self.case("owned_unchanged_json_update_is_explicit_and_atomic"):
            record = self.store.write_json("status.json", {"status": "complete"}, exclusive=False)
            self.assertEqual(json.loads(path.read_text()), {"status": "complete"})
            self.assertEqual(record["sha256"], sha(path))
        with self.case("unregistered_existing_json_cannot_be_adopted_or_overwritten"):
            foreign = self.store.rootpath / "foreign.json"
            foreign.write_bytes(b"sentinel")
            info = sha(foreign), foreign.stat().st_mtime_ns
            self.refusal(lambda: self.store.write_json("foreign.json", {}, exclusive=False), "unregistered_artifact")
            self.assertEqual((sha(foreign), foreign.stat().st_mtime_ns), info)

    def test_invalid_json_refuses_before_any_publication(self):
        circular = []
        circular.append(circular)
        cases = (("nan", {"metric": float("nan")}), ("positive_inf", float("inf")),
                 ("negative_inf", float("-inf")), ("object", object()),
                 ("nonstring_key", {1: "x"}), ("cycle", circular), ("huge_integer", 1 << 5000))
        for name, payload in cases:
            with self.subTest(name=name), self.case("invalid_json_" + name):
                self.refusal(lambda: self.store.write_json("invalid.json", payload))
                self.assertFalse((self.store.rootpath / "invalid.json").exists())

    def test_utf8_metadata_cap_count_total_bytes_and_limits(self):
        with self.case("utf8_byte_cap_uses_bytes_not_codepoints"):
            small = A.create_run_artifacts(self.task, run_id="b" * 32, budget=self.shared,
                                           limits=A.ArtifactLimits(max_json_bytes=64))
            with self.assertRaises(A.ArtifactError):
                small.write_json("large.json", {"text": "я" * 40})
            self.assertFalse((small.rootpath / "large.json").exists())
            self.assertEqual(list(small.rootpath.glob(".tmp-*")), [])
        with self.case("per_run_count_limit_keeps_prior_record"):
            small = A.create_run_artifacts(self.task, run_id="c" * 32, budget=self.shared,
                                           limits=A.ArtifactLimits(max_files=1))
            first = small.write_json("one.json", {"x": 1})
            with self.assertRaises(A.ArtifactError):
                small.write_json("two.json", {})
            self.assertEqual(small.record("one.json"), first)
            small.write_json("one.json", {"x": 2}, exclusive=False)
        with self.case("aggregate_run_bytes_cap_counts_previous_artifacts"):
            small = A.create_run_artifacts(self.task, run_id="d" * 32, budget=self.shared,
                                           limits=A.ArtifactLimits(max_total_bytes=20))
            first = small.write_json("one.json", {"x": "123456"})
            with self.assertRaises(A.ArtifactError):
                small.write_json("two.json", {"x": "123456"})
            self.assertEqual(small.record("one.json"), first)
            self.assertFalse((small.rootpath / "two.json").exists())
        for name, kwargs in (("bool", {"max_files": True}), ("zero", {"max_rows": 0}),
                             ("over_cap", {"max_json_bytes": (1 << 20) + 1})):
            with self.subTest(name=name), self.case("invalid_limits_" + name):
                with self.assertRaises(A.ArtifactError):
                    A.ArtifactLimits(**kwargs)

    def test_safe_names_symlinks_and_outside_record(self):
        for name in ("../status.json", "sub/status.json", "sub\\status.json", "/tmp/escape.json", ".hidden.json", "Status.json"):
            with self.subTest(name=name), self.case("unsafe_artifact_name_" + str(len(CASES))):
                self.refusal(lambda: self.store.write_json(name, {}))
        with self.case("existing_output_symlink_cannot_modify_external_file"):
            target = self.base / "outside.json"
            target.write_bytes(b"sentinel")
            (self.store.rootpath / "linked.json").symlink_to(target)
            self.refusal(lambda: self.store.write_json("linked.json", {}), "artifact_exists")
            self.assertEqual(target.read_bytes(), b"sentinel")
        with self.case("record_outside_run_refused_even_when_file_exists"):
            self.refusal(lambda: self.store.record(self.previous), "artifact_outside_run")
        with self.case("run_directory_symlink_replacement_refused"):
            root = self.store.rootpath
            moved = self.base / "moved-own-run"
            root.rename(moved)
            external = self.base / "external"
            external.mkdir()
            root.symlink_to(external, target_is_directory=True)
            self.refusal(lambda: self.store.write_json("status.json", {}), "run_directory_changed")
            self.assertFalse((external / "status.json").exists())
            root.unlink()
            moved.rename(root)

    def test_record_detects_content_replacement_symlink_and_hardlink(self):
        with self.case("same_size_modified_json_cannot_be_updated"):
            self.store.write_json("status.json", {"x": "a"})
            path = self.store.rootpath / "status.json"
            path.write_bytes(path.read_bytes().replace(b'"a"', b'"b"'))
            self.refusal(lambda: self.store.write_json("status.json", {}, exclusive=False), "artifact_changed")
        with self.case("registered_file_replaced_by_symlink_is_refused"):
            self.store.write_json("linktest.json", {})
            path = self.store.rootpath / "linktest.json"
            path.unlink()
            path.symlink_to(self.previous)
            self.refusal(lambda: self.store.record(path), "artifact_changed")
        with self.case("registered_file_external_hardlink_is_refused"):
            self.store.write_json("hardlink.json", {})
            path = self.store.rootpath / "hardlink.json"
            A.os.link(path, self.base / "extra-link")
            self.refusal(lambda: self.store.record(path), "artifact_changed")

    def test_exclusive_publication_race_preserves_racer(self):
        with self.case("destination_created_during_write_is_not_overwritten"):
            real_link = A.os.link
            def raced(source, destination, **kwargs):
                Path(destination).write_bytes(b"racing-owner-sentinel")
                return real_link(source, destination, **kwargs)
            with patch.object(A.os, "link", side_effect=raced):
                self.refusal(lambda: self.store.write_json("race.json", {"new": 1}), "artifact_exists")
            self.assertEqual((self.store.rootpath / "race.json").read_bytes(), b"racing-owner-sentinel")

    def test_precommit_fsync_failure_and_expiry_preserve_previous(self):
        path = self.store.rootpath / "status.json"
        self.store.write_json("status.json", {"status": "old"})
        before = sha(path), path.stat().st_mtime_ns
        with self.case("file_fsync_failure_preserves_old_valid_record"):
            with patch.object(A.os, "fsync", side_effect=OSError("SYNTHETIC_SECRET_CANARY")):
                error = self.refusal(lambda: self.store.write_json("status.json", {"status": "new"}, exclusive=False), "artifact_write_failed")
            self.assertNotIn("SYNTHETIC_SECRET_CANARY", str(error))
            self.assertEqual((sha(path), path.stat().st_mtime_ns), before)
        with self.case("shared_deadline_expiring_before_publish_preserves_old_record"):
            real_fsync = A.os.fsync
            def expired(fd):
                real_fsync(fd)
                self.now[0] = 90_000_000_000
            with patch.object(A.os, "fsync", side_effect=expired), self.assertRaises(C.BudgetExpired):
                self.store.write_json("status.json", {"status": "new"}, exclusive=False)
            self.assertEqual((sha(path), path.stat().st_mtime_ns), before)
            self.assertEqual(list(self.store.rootpath.glob(".tmp-*")), [])

    def test_finalizing_reserve_and_same_shared_clock(self):
        self.now[0] = 91_000_000_000
        with self.case("work_exhaustion_refuses_before_file_creation"):
            with self.assertRaises(C.BudgetExpired):
                self.store.write_json("work.json", {})
            self.assertFalse((self.store.rootpath / "work.json").exists())
        with self.case("explicit_finalizing_can_use_original_reserve_without_reset"):
            self.store.write_json("final.json", {"complete": True}, finalizing=True)
            manifest = self.store.manifest(finalizing=True)
            self.assertEqual(manifest["timer"]["elapsed_seconds"], 91)
            self.assertEqual(self.shared.deadline_ns, 100_000_000_000)
        with self.case("final_deadline_exhaustion_still_refuses_finalizing"):
            self.now[0] = 100_000_000_000
            with self.assertRaises(C.BudgetExpired):
                self.store.write_json("late.json", {}, finalizing=True)

    def test_numeric_label_and_vector_data_only_predictions(self):
        for name, values, indices, kind in (("numeric.csv", [1.0, -2, 1e308], [7, 1, 99], "numeric"),
                    ("labels.csv", ["001", "NA", "null", "привет,\nмир"], [9, 4, 3, 2], "label"),
                    ("vectors.csv", [array("d", [.1, .9]), array("d", [.7, .3])], [1, 0], "vector")):
            with self.subTest(name=name), self.case("prediction_roundtrip_" + kind):
                result = self.store.write_predictions(name, values, indices)
                actual = self.read_predictions(name)
                expected = [(i, list(v) if isinstance(v, array) else v) for i, v in zip(indices, values)]
                self.assertEqual(actual, expected)
                self.assertEqual(result["prediction_kind"], kind)
                self.assertEqual(result["row_count"], len(values))
                self.assertEqual(result["sha256"], sha(self.store.rootpath / name))
        with self.case("prediction_artifact_is_immutable"):
            path = self.store.rootpath / "numeric.csv"
            before = sha(path), path.stat().st_mtime_ns
            self.refusal(lambda: self.store.write_predictions("numeric.csv", [0], [0]), "artifact_exists")
            self.assertEqual((sha(path), path.stat().st_mtime_ns), before)

    def test_prediction_shape_indices_finiteness_and_row_caps(self):
        cases = (("empty", [], []), ("mismatch", [1, 2], [0]), ("duplicate", [1, 2], [0, 0]),
                 ("bool_index", [1], [True]), ("negative_index", [1], [-1]),
                 ("float_index", [1], [1.0]), ("overflow_index", [1], [2**63]),
                 ("nan", [float("nan")], [0]), ("inf", [[float("inf"), 0]], [0]),
                 ("mixed", [1, "a"], [0, 1]), ("ragged", [[1, 2], [1]], [0, 1]),
                 ("bool_value", [True], [0]), ("dict_vector", [{0: 1}], [0]),
                 ("empty_vector", [[]], [0]), ("string_vector", [["a"]], [0]),
                 ("empty_label", [""], [0]), ("nul_label", ["a\x00b"], [0]))
        for name, values, indices in cases:
            with self.subTest(name=name), self.case("invalid_prediction_" + name):
                self.refusal(lambda: self.store.write_predictions("invalid.csv", values, indices))
                self.assertFalse((self.store.rootpath / "invalid.csv").exists())
        with self.case("prediction_row_limit_refuses_instead_of_truncating"):
            small = A.create_run_artifacts(self.task, run_id="b" * 32, budget=self.shared,
                                           limits=A.ArtifactLimits(max_rows=2))
            small.write_predictions("fits.csv", [1, 2], [0, 1])
            with self.assertRaises(A.ArtifactError):
                small.write_predictions("excess.csv", [1, 2, 3], [0, 1, 2])
            self.assertFalse((small.rootpath / "excess.csv").exists())
        with self.case("prediction_byte_limit_cleans_partial_private_file"):
            small = A.create_run_artifacts(self.task, run_id="c" * 32, budget=self.shared,
                                           limits=A.ArtifactLimits(max_prediction_bytes=32))
            with self.assertRaises(A.ArtifactError):
                small.write_predictions("excess.csv", ["long" * 20], [0])
            self.assertFalse((small.rootpath / "excess.csv").exists())
            self.assertEqual(list(small.rootpath.glob(".tmp-*")), [])

    def test_no_budget_reset_or_credential_metadata_or_payload_logging(self):
        with self.case("different_budget_instance_cannot_reset_prediction_deadline"):
            other = C.RunBudget(0, 200, 10, clock=lambda: 0)
            self.refusal(lambda: self.store.write_predictions("pred.csv", [1], [0], budget=other), "different_shared_budget")
        with self.case("missing_shared_budget_refuses_before_new_directory"):
            self.refusal(lambda: A.create_run_artifacts(self.task, run_id="b" * 32, budget=None), "missing_shared_budget")
        with self.case("credential_keys_refused_static_errors_and_no_stdout_payload"):
            canary = "SYNTHETIC_SECRET_CANARY"
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                error = self.refusal(lambda: self.store.write_json("secret.json", {"nested": {"API_KEY": canary}}), "credential_metadata_forbidden")
            self.assertEqual(stdout.getvalue() + stderr.getvalue(), "")
            self.assertNotIn(canary, repr(error))
            self.assertNotIn(str(self.base), repr(self.store))

    def test_manifest_hashes_private_records_without_label_values_or_absolute_paths(self):
        with self.case("manifest_has_verified_hashes_shared_timer_and_no_raw_predictions"):
            label = "PRIVATE_LABEL_FIXTURE_ONLY"
            self.store.write_predictions("inner_predictions.csv", [label], [17])
            manifest = self.store.manifest()
            self.assertEqual(manifest["task_sha256"], sha(self.task))
            self.assertEqual(manifest["records"][0], self.store.record("inner_predictions.csv"))
            self.assertTrue(manifest["data_only"])
            self.assertFalse(manifest["os_boundary_verified"])
            self.assertEqual(manifest["timer"]["total_seconds"], 100)
            encoded = json.dumps(manifest, ensure_ascii=False)
            self.assertNotIn(label, encoded)
            self.assertNotIn(str(self.base), encoded)
            self.store.write_json("manifest.json", manifest)
            self.assertEqual(json.loads((self.store.rootpath / "manifest.json").read_text()), manifest)

    def test_post_link_unlink_failure_once_keeps_registered_commit(self):
        with self.case("H04_ARTIFACT_COMMIT_001_unlink_once_committed_and_cleanup_verified"):
            real_unlink, failures = Path.unlink, []
            def once(path, *args, **kwargs):
                if path.parent == self.store.rootpath and path.name.startswith(".tmp-") and not failures:
                    failures.append(True)
                    raise OSError("synthetic_post_link_unlink_failure")
                return real_unlink(path, *args, **kwargs)
            with patch.object(Path, "unlink", new=once):
                record = self.store.write_json("committed.json", {"status": "complete"})
            self.assertEqual(len(failures), 1)
            self.assertTrue(record["temporary_cleanup_warning"])
            self.assertTrue(record["temporary_cleanup_verified"])
            self.assertEqual(record["sha256"], sha(self.store.rootpath / "committed.json"))
            self.assertEqual(self.store.record("committed.json"), record)
            self.assertEqual(self.store.manifest()["records"], [record])
            self.assertEqual(list(self.store.rootpath.glob(".tmp-*")), [])
            self.refusal(lambda: self.store.write_json("committed.json", {}), "artifact_exists")

    def test_persistent_temporary_cleanup_failure_is_explicit_and_reconcilable(self):
        with self.case("H04_ARTIFACT_COMMIT_001_two_cleanup_failures_never_accept_empty_manifest"):
            real_unlink, failures = Path.unlink, []
            def persist(path, *args, **kwargs):
                if path.parent == self.store.rootpath and path.name.startswith(".tmp-"):
                    failures.append(True)
                    raise OSError("synthetic_persistent_temporary_unlink_failure")
                return real_unlink(path, *args, **kwargs)
            with patch.object(Path, "unlink", new=persist):
                record = self.store.write_json("pending.json", {"status": "complete"})
                self.assertEqual(len(failures), 2, "cleanup retry must be bounded")
                self.assertTrue(record["temporary_cleanup_warning"])
                self.assertFalse(record["temporary_cleanup_verified"])
                self.assertIn("pending.json", self.store._records)
                self.assertEqual(json.loads((self.store.rootpath / "pending.json").read_text()), {"status": "complete"})
                with self.assertRaises(A.ArtifactError) as caught:
                    self.store.manifest()
                self.assertEqual(caught.exception.code, "artifact_cleanup_unverified")
                self.assertEqual(len(failures), 4, "reconciliation must also use bounded retries")
            manifest = self.store.manifest()
            self.assertEqual(len(manifest["records"]), 1)
            reconciled = manifest["records"][0]
            self.assertTrue(reconciled["temporary_cleanup_verified"])
            self.assertTrue(reconciled["temporary_cleanup_warning"])
            self.assertEqual(reconciled["sha256"], sha(self.store.rootpath / "pending.json"))
            self.assertEqual(list(self.store.rootpath.glob(".tmp-*")), [])
            self.assertEqual((self.store.rootpath / "pending.json").stat().st_nlink, 1)

    def test_post_commit_lstat_failure_keeps_known_owned_inode_registration(self):
        for update in (False, True):
            with self.subTest(update=update), self.case("H04_ARTIFACT_COMMIT_001_postcommit_lstat_" + ("replace" if update else "link")):
                name = "replace.json" if update else "link.json"
                destination = self.store.rootpath / name
                if update:
                    self.store.write_json(name, {"version": 1})
                real_lstat, real_commit = Path.lstat, A.os.replace if update else A.os.link
                committed = [False]
                def commit(*args, **kwargs):
                    result = real_commit(*args, **kwargs)
                    committed[0] = True
                    return result
                def lstat(path, *args, **kwargs):
                    if path == destination and committed[0]:
                        raise OSError("synthetic_destination_lstat_failure_after_commit")
                    return real_lstat(path, *args, **kwargs)
                with patch.object(A.os, "replace" if update else "link", side_effect=commit), \
                        patch.object(Path, "lstat", new=lstat):
                    record = self.store.write_json(name, {"version": 2}, exclusive=not update)
                    self.assertEqual(self.store._records[name]["sha256"], record["sha256"])
                    self.assertIn(name, self.store._file_identities)
                    with self.assertRaises(A.ArtifactError) as caught:
                        self.store.record(name)
                    self.assertEqual(caught.exception.code, "artifact_unavailable")
                self.assertEqual(json.loads(destination.read_text()), {"version": 2})
                self.assertEqual(self.store.record(name)["sha256"], sha(destination))
                self.assertTrue(any(item["path"] == name for item in self.store.manifest()["records"]))

    def test_directory_fsync_failure_after_commit_is_separate_warning(self):
        for update in (False, True):
            with self.subTest(update=update), self.case("H04_ARTIFACT_COMMIT_001_directory_fsync_warning_" + ("replace" if update else "link")):
                name = "fsync-update.json" if update else "fsync-new.json"
                if update:
                    self.store.write_json(name, {"version": 1})
                real_fsync = A.os.fsync
                def fsync(fd):
                    if stat.S_ISDIR(A.os.fstat(fd).st_mode):
                        raise OSError("synthetic_postcommit_directory_fsync_failure")
                    return real_fsync(fd)
                with patch.object(A.os, "fsync", side_effect=fsync):
                    record = self.store.write_json(name, {"version": 2}, exclusive=not update)
                self.assertTrue(record["directory_fsync_warning"])
                self.assertEqual(json.loads((self.store.rootpath / name).read_text()), {"version": 2})
                self.assertEqual(self.store.record(name), record)
                self.assertTrue(any(item["path"] == name for item in self.store.manifest()["records"]))

    def test_postcommit_cleanup_never_unlinks_replaced_foreign_inode(self):
        with self.case("H04_ARTIFACT_COMMIT_001_cleanup_refuses_foreign_replaced_inode"):
            real_unlink, replaced = Path.unlink, []
            def replace_once(path, *args, **kwargs):
                if path.parent == self.store.rootpath and path.name.startswith(".tmp-") and not replaced:
                    real_unlink(path)
                    path.write_bytes(b"synthetic_foreign_file_preserve")
                    replaced.append(path)
                    raise OSError("synthetic_cleanup_inode_replaced")
                return real_unlink(path, *args, **kwargs)
            with patch.object(Path, "unlink", new=replace_once):
                record = self.store.write_json("owned.json", {"status": "complete"})
            self.assertFalse(record["temporary_cleanup_verified"])
            self.assertEqual(replaced[0].read_bytes(), b"synthetic_foreign_file_preserve")
            with self.assertRaises(A.ArtifactError) as caught:
                self.store.manifest()
            self.assertEqual(caught.exception.code, "artifact_cleanup_unverified")
            self.assertEqual(replaced[0].read_bytes(), b"synthetic_foreign_file_preserve")
            # Only the trusted fixture owner removes its deliberately injected file.
            real_unlink(replaced[0])
            self.assertEqual(self.store.manifest()["records"][0]["sha256"], sha(self.store.rootpath / "owned.json"))


def main():
    global A, C
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
        parser.error("requires Linux Python3.12")
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    # Claim receipt before module imports/tests; old receipts are never overwritten.
    with args.receipt.open("x", encoding="utf-8") as stream:
        before = {name: sha(ROOT / name) for name in SOURCES}
        receipt = {"status": "FAIL_H04_ARTIFACTS_ONLY", "scope": "synthetic trusted artifact filesystem/data-only component",
                   "python": sys.version.split()[0], "source_sha256": before,
                   "model_fit_calls": 0, "live_api_calls": 0, "network_used": False,
                   "generated_code_executed": False, "full_H05_accepted": False,
                   "official_image_verified": False, "test_methods_run": 0}
        code = 1
        try:
            if before["requirements.txt"] != EXPECTED_REQUIREMENTS:
                raise RuntimeError("provided_requirements_changed")
            import aegml_artifacts as A
            import aegml_contracts as C
            result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ArtifactChecks))
            after = {name: sha(ROOT / name) for name in SOURCES}
            passed = result.wasSuccessful() and before == after
            receipt.update(status="PASS_H04_ARTIFACTS_ONLY" if passed else "FAIL_H04_ARTIFACTS_ONLY",
                test_methods_run=result.testsRun, behavior_cases_checked=len(CASES),
                behavior_cases_passed=sum(c["status"] == "PASS" for c in CASES), cases=CASES,
                source_sha256_after=after, source_unchanged=before == after,
                unittest_failures=[{"test": t.id(), "detail": text} for t, text in result.failures],
                unittest_errors=[{"test": t.id(), "detail": text} for t, text in result.errors],
                unittest_skips=[{"test": t.id(), "reason": reason} for t, reason in result.skipped])
            code = 0 if passed else 1
        except Exception as exc:
            receipt.update(error_type=type(exc).__name__, error_code=getattr(exc, "code", "component_check_failed"))
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k: receipt.get(k) for k in ("status", "test_methods_run", "behavior_cases_checked")}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
