"""Trusted H03 integration acceptance; no estimator training or LLM/API calls.

Run Linux Python 3.12 with --receipt NEW.json. TEMPROOT may name a writable
scratch directory (e.g. /work/h03-tmp in the local Docker harness). All writes
use temporary fixture/copy roots. Original public inputs stay read-only.
Numerical scores below are hand-authored synthetic examples only. Public CSVs
receive diagnostic constants, not a trained solution or a quality claim.
"""

import argparse
import copy
from contextlib import contextmanager
import csv
from dataclasses import FrozenInstanceError
import hashlib
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import resource
import shutil
import sys
import tempfile
from time import monotonic, monotonic_ns
import unittest


STARTED_NS = monotonic_ns()
ROOT = Path(__file__).resolve().parents[1]
INPUTS = ("task.md", "train.csv", "test.csv", "data_dictionary.csv", "sample_submission.csv")
SOURCES = ("solution.py", "aegml_contracts.py", "aegml_input.py", "aegml_schemas.py",
    "aegml_profile.py", "aegml_preprocessing.py", "aegml_metrics.py", "aegml_validation.py",
    "aegml_submission.py", "requirements.txt", "scripts/check_h023_contract.py",
    "scripts/check_h03_integration.py")
CASES, REGISTRY_CHECKS, ACTUAL, PRIVACY_CONTROLS = [], [], [], []
C = I = T = F = P = M = V = S = FIXTURE = SHARED_ACTUAL = None
SCRATCH = None
EXPECTED_REQUIREMENTS_SHA = "9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6"
METRICS = {
    "rmse": ("root mean squared error", "regression", "minimize", "numeric"),
    "mae": ("mean absolute error", "regression", "minimize", "numeric"),
    "accuracy": ("Accuracy", "classification", "maximize", "label"),
    "macro_f1": ("F1 macro", "classification", "maximize", "label"),
    "weighted_f1": ("weighted_f1", "classification", "maximize", "label"),
    "binary_f1": ("F1 binary", "classification", "maximize", "label"),
    "log_loss": ("cross-entropy", "classification", "minimize", "probability"),
    "roc_auc": ("ROC_AUC", "classification", "maximize", "probability"),
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def value_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def unit_budget():
    return C.RunBudget(monotonic_ns(), 120, 10)


def assert_private_sequence_equal(case, actual, expected, *, kind):
    """Compare protected sequences without putting their repr into a failure."""
    messages = {"id_order": "public lexical ID order mismatch; values omitted",
                "row_index_order": "source row index order mismatch; values omitted"}
    if kind not in messages:
        raise ValueError("unknown_private_sequence_check")
    case.assertTrue(actual == expected, messages[kind])


def load_modules():
    global C, I, T, F, P, M, V, S, FIXTURE
    sys.path.insert(0, str(ROOT))
    C, I, T, F, P, M, V, S = [importlib.import_module(name) for name in (
        "aegml_contracts", "aegml_input", "aegml_schemas", "aegml_profile",
        "aegml_preprocessing", "aegml_metrics", "aegml_validation", "aegml_submission")]
    for module in (C, I, T, F, P, M, V, S):
        if Path(module.__file__).resolve().parent != ROOT:
            raise RuntimeError("unexpected_project_import_location")
    C.configure_threads(8)  # Before preprocessing performs its lazy ML imports.
    helper_path = ROOT / "scripts/check_h023_contract.py"
    spec = importlib.util.spec_from_file_location("h03_shared_synthetic_fixture", helper_path)
    helper = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = helper
    spec.loader.exec_module(helper)
    FIXTURE = helper.Fixture


def rename_target(fixture, target):
    prior = fixture.target
    for role, columns in fixture.headers.items():
        fixture.headers[role] = [target if name == prior else name for name in columns]
    for row in fixture.dictionary:
        if row[0] == prior:
            row[0] = target
    fixture.target = target


def registry_fixture(root, name, *, order=None):
    alias, family, _, _ = METRICS[name]
    fixture = FIXTURE(root, kind=family)
    rename_target(fixture, "unrelated_response" if family == "regression" else "arbitrary_label")
    fixture.metric = alias
    target_position = fixture.headers["train"].index(fixture.target)
    values = ["1", "3", "5"] if family == "regression" else ["yes", "no", "yes"]
    for row, value in zip(fixture.rows["train"], values):
        row[target_position] = value
    for row in fixture.dictionary:
        if row[0] == fixture.target:
            row[2] = "numeric" if family == "regression" else "category"
    if name in {"binary_f1", "roc_auc"}:
        fixture.extra = "Positive label: yes"
    if name == "log_loss":
        classes = order or ["yes", "no"]
        fixture.extra = "Class order: " + json.dumps(classes)
        ids = [row[fixture.headers["sample_submission"].index("id")]
               for row in fixture.rows["sample_submission"]]
        value_columns = ["probability_" + str(index) for index in range(len(classes))]
        fixture.headers["sample_submission"] = value_columns[:1] + ["id"] + value_columns[1:]
        fixture.rows["sample_submission"] = [[0, identifier] + [0] * (len(classes) - 1) for identifier in ids]
        if order is not None:
            for index, row in enumerate(fixture.rows["train"]):
                row[target_position] = classes[index % len(classes)]
    fixture.output_order = "sample" if name in {"mae", "weighted_f1", "log_loss"} else "test"
    fixture.save()
    return fixture


def temporal_fixture(root):
    fixture = registry_fixture(root, "rmse")
    left = fixture.headers["train"].index("left")
    for index, row in enumerate(fixture.rows["train"]):
        row[left] = str(index)
    fixture.save()
    return fixture


def bind_fixture(fixture, shared):
    task = C.build_task_contract(fixture.task, budget=shared)
    bundle = I.discover_inputs(fixture.task, shared)
    plan = V.build_split_plan(bundle, task, strategy="temporal", budget=shared,
        time_column="left", fit_periods=(0,), inner_periods=(1,), outer_periods=(2,))
    return bundle, task, plan, C.attach_split_plan(task, plan, budget=shared)


def feature_schema(bundle, contract):
    payload = contract.to_dict()
    rows = {row["feature"]: row for row in bundle.dictionary_rows}
    mapping = {"numeric": "numeric", "binary": "numeric", "category": "categorical", "text": "text"}
    kinds = {}
    for name in payload["feature_columns"]:
        if name not in rows or rows[name]["dtype"] not in mapping:
            raise RuntimeError("explicit_dictionary_kind_required")
        kinds[name] = mapping[rows[name]["dtype"]]
    return P.schema_from_kinds(contract, kinds)


def public_inventory():
    source = ROOT / "drive-download-20261019T181414Z-1-001"
    return {str(path.relative_to(source)): sha(path)
            for path in sorted(source.rglob("*")) if path.is_file()} if source.is_dir() else {}


class IntegrationChecks(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aegml-h03-integration-", dir=SCRATCH)
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)

    @contextmanager
    def case(self, name):
        entry = {"test": self.id(), "case": name, "status": "RUNNING"}
        CASES.append(entry)
        try:
            yield
        except unittest.SkipTest:
            entry["status"] = "SKIP"
            raise
        except BaseException:
            entry["status"] = "FAIL"
            raise
        else:
            entry["status"] = "PASS"

    def build(self, fixture, shared):
        task = C.build_task_contract(fixture.task, budget=shared)
        bundle = I.discover_inputs(fixture.task, shared)
        T.validate_task_contract(task.to_dict())
        return bundle, task

    def check_written_order(self, schema, predictions, fixture=None):
        with schema.output_path.open("r", encoding="utf-8", newline="") as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(tuple(rows[0]), schema.columns)
        self.assertEqual(len(rows) - 1, schema.row_count)
        id_positions = [schema.columns.index(name) for name in schema.id_columns]
        positions = [schema.columns.index(name) for name in schema.value_columns]
        if fixture is not None:
            test_header = fixture.headers["test"]
            test_keys = [tuple(row[test_header.index(name)] for name in schema.id_columns)
                         for row in fixture.rows["test"]]
            role = "test" if fixture.output_order == "test" else "sample_submission"
            source_header = fixture.headers[role]
            expected_keys = [tuple(row[source_header.index(name)] for name in schema.id_columns)
                             for row in fixture.rows[role]]
            independent_mapping = tuple(test_keys.index(key) for key in expected_keys)
            assert_private_sequence_equal(self, schema.output_to_test, independent_mapping, kind="row_index_order")
        else:
            expected_keys, independent_mapping = schema.expected_ids, schema.output_to_test
        for index, row in enumerate(rows[1:]):
            assert_private_sequence_equal(self, tuple(row[position] for position in id_positions),
                                          expected_keys[index], kind="id_order")
            expected = predictions[independent_mapping[index]]
            expected = list(expected) if schema.metric_name == "log_loss" else [expected]
            for position, value in zip(positions, expected):
                if schema.kind == "label":
                    self.assertEqual(row[position], value)
                else:
                    self.assertAlmostEqual(float(row[position]), float(value), places=13)

    def test_all_eight_generic_metric_contract_to_numeric_adapter_and_writer(self):
        for name, (_, family, direction, kind) in METRICS.items():
            with self.subTest(metric=name), self.case("eight_registry_builder_metric_writer_" + name):
                shared = unit_budget()
                fixture = registry_fixture(self.base / name, name)
                before = {path.name: sha(path) for path in fixture.source_paths()}
                bundle, task = self.build(fixture, shared)
                payload = task.to_dict()
                metric = payload["metric"]
                self.assertEqual((metric["name"], metric["direction"], metric["prediction_kind"]), (name, direction, kind))
                self.assertEqual(metric["adapter_version"], M.ADAPTER_VERSION)
                self.assertNotIn(payload["target_columns"][0], {"site_eui", "attack_cat"})
                extra = {}
                if family == "regression":
                    truth, predictions = [1.0, 3.0, 5.0], [1.0, 2.0, 4.0]
                    expected = math.sqrt(2/3) if name == "rmse" else 2/3
                elif name == "log_loss":
                    truth = ["yes", "no", "yes"]
                    reverse = [[.2, .8], [.7, .3], [.4, .6]]
                    reordered = M.validate_probabilities(reverse, n_rows=3, class_order=metric["class_order"],
                        prediction_class_order=["no", "yes"], budget=shared)
                    predictions = reordered
                    extra["prediction_class_order"] = metric["class_order"]
                    expected = -(math.log(.8) + math.log(.7) + math.log(.6)) / 3
                    # The metric can explicitly map model columns; writer gets
                    # already canonical columns, never a silent permutation.
                    alternate = M.evaluate_metric(metric, truth, reverse, prediction_class_order=["no", "yes"], budget=shared)
                    self.assertAlmostEqual(alternate.value, expected)
                elif name == "roc_auc":
                    truth, predictions, expected = ["yes", "no", "yes"], [.8, .2, .6], 1.0
                    extra["prediction_positive_label"] = "yes"
                else:
                    truth, predictions = ["yes", "no", "yes"], ["yes", "yes", "no"]
                    expected = {"accuracy": 1/3, "macro_f1": .25, "weighted_f1": 1/3, "binary_f1": .5}[name]
                result = M.evaluate_metric(metric, truth, predictions, budget=shared)
                self.assertAlmostEqual(result.value, expected)
                schema = S.build_submission_schema(bundle, task, budget=shared,
                    allowed_labels=["yes", "no"] if kind == "label" else None)
                self.assertEqual(schema.limits.probability_tolerance, M.PROBABILITY_SUM_ATOL)
                published = S.write_submission(predictions, schema, budget=shared, **extra)
                validated = S.validate_submission(schema.output_path, schema, budget=shared, expected_sha256=published["sha256"])
                self.assertEqual(validated["row_count"], 3)
                self.assertEqual(validated["sha256"], sha(schema.output_path))
                self.check_written_order(schema, predictions, fixture)
                self.assertEqual(before, {path.name: sha(path) for path in fixture.source_paths()})
                REGISTRY_CHECKS.append({"metric": name, "direction": direction, "prediction_kind": kind,
                    "adapter_version": metric["adapter_version"], "synthetic_value": result.value,
                    "hand_expected": expected, "output_order": payload["prediction_schema"]["output_order"],
                    "row_count": validated["row_count"], "csv_sha256": validated["sha256"],
                    "numeric_result_is_synthetic_not_public_quality": True})

    def test_unknown_formulas_missing_positive_and_missing_classorder_refused(self):
        variants = (("rmse", "RMSLE", "unsupported_metric"), ("rmse", "MAPE", "unsupported_metric"),
                    ("rmse", "RMSE + 2", "unsupported_metric"),
                    ("binary_f1", None, "missing_positive_label"),
                    ("roc_auc", None, "missing_positive_label"),
                    ("log_loss", None, "missing_class_order"))
        for index, (name, alias, code) in enumerate(variants):
            with self.subTest(name=name, alias=alias), self.case("builder_reject_unsupported_or_missing_" + str(index)):
                fixture = registry_fixture(self.base / ("bad-" + str(index)), name)
                if alias is None:
                    fixture.extra = ""
                else:
                    fixture.metric = alias
                fixture.save()
                with self.assertRaises(C.ContractError) as caught:
                    C.build_task_contract(fixture.task, budget=unit_budget())
                self.assertEqual(caught.exception.code, code)
                self.assertFalse((fixture.root / ".aegml_runs").exists())
                self.assertFalse((fixture.root / "submission.csv").exists())
        with self.case("metric_formula_is_data_never_eval"):
            fixture = registry_fixture(self.base / "no-eval", "rmse")
            canary = fixture.root / "UNEXECUTED_CANARY"
            fixture.metric = "__import__('pathlib').Path(" + repr(str(canary)) + ").touch()"
            fixture.save()
            with self.assertRaises(C.ContractError):
                C.build_task_contract(fixture.task, budget=unit_budget())
            self.assertFalse(canary.exists())

    def test_built_schema_copy_source_identity_and_phase_metadata(self):
        with self.case("BUILT_copy_schema_and_phase_grants_not_a_refit"):
            shared = unit_budget()
            fixture = temporal_fixture(self.base / "binding")
            bundle, original, plan, enriched = bind_fixture(fixture, shared)
            self.assertEqual(original.to_dict()["split_policy"]["status"], "NOT_BUILT")
            payload = enriched.to_dict()
            T.validate_task_contract(payload)
            self.assertEqual(payload["split_policy"]["status"], "BUILT")
            self.assertEqual(payload["split_policy"]["partition_sha256"], plan.partition_sha256)
            self.assertEqual(payload["split_policy"]["train_sha256"], bundle.source_sha256["train"])
            search = V.phase_grant(plan, "search")
            self.assertEqual(search.train_indices, plan.fit_indices)
            self.assertTrue(search.feedback_allowed)
            recipe = V.freeze_recipe(plan, code_sha256="a" * 64, config_sha256="b" * 64,
                preprocessing_sha256="c" * 64, iterations=5)
            refit = V.phase_grant(plan, "frozen_refit", recipe=recipe)
            self.assertEqual(refit.train_indices, plan.development_indices)
            self.assertFalse(set(refit.train_indices) & set(plan.outer_indices))
            self.assertFalse(refit.feedback_allowed)
            self.assertFalse(refit.refit_performed)
            with self.assertRaises(FrozenInstanceError):
                recipe.iterations = 6
            self.assertFalse((fixture.root / ".aegml_runs").exists())
        mutations = ("count_sum", "train_sha", "bool_rows", "bool_seed", "bool_part_count",
                     "unknown_field", "unknown_status", "bad_partition_sha", "mixed_states")
        for name in mutations:
            with self.subTest(name=name), self.case("BUILT_schema_reject_" + name):
                altered = copy.deepcopy(payload)
                split = altered["split_policy"]
                if name == "count_sum": split["row_counts"]["fit"] += 1
                elif name == "train_sha": split["train_sha256"] = "9" * 64
                elif name == "bool_rows": split["train_rows"] = True
                elif name == "bool_seed": split["seed"] = True
                elif name == "bool_part_count": split["row_counts"]["outer"] = True
                elif name == "unknown_field": split["labels"] = ["FORBIDDEN"]
                elif name == "unknown_status": split["status"] = "MAYBE"
                elif name == "bad_partition_sha": split["partition_sha256"] = "not-a-sha"
                else: split["status"] = "NOT_BUILT"
                with self.assertRaises(T.SchemaError):
                    T.validate_task_contract(altered)

    def test_probability_tolerance_shared_and_orientation_errors_preserve_csv(self):
        import numpy as np
        shared = unit_budget()
        order = ["C" + str(index) for index in range(10)]
        fixture = registry_fixture(self.base / "float32", "log_loss", order=order)
        bundle, task = self.build(fixture, shared)
        metric = task.to_dict()["metric"]
        schema = S.build_submission_schema(bundle, task, budget=shared)
        values = np.full((3, 10), .1, dtype=np.float32)
        with self.case("writer_and_evaluator_accept_float32_roundoff_without_normalizing"):
            self.assertEqual(S.SubmissionLimits().probability_tolerance, M.PROBABILITY_SUM_ATOL)
            self.assertEqual(M.PROBABILITY_SUM_ATOL, 1e-6)
            value = M.evaluate_metric(metric, order[:3], values, budget=shared).value
            self.assertAlmostEqual(value, -math.log(float(values[0, 0])))
            result = S.write_submission(values, schema, budget=shared, prediction_class_order=order)
            S.validate_submission(schema.output_path, schema, budget=shared, expected_sha256=result["sha256"])
            self.check_written_order(schema, values, fixture)
        prior = (sha(schema.output_path), schema.output_path.stat().st_mtime_ns)
        with self.case("writer_and_evaluator_refuse_excess_sum_and_keep_previous_csv"):
            bad = [[.1000002] * 10] * 3
            with self.assertRaises(M.MetricError):
                M.evaluate_metric(metric, order[:3], bad, budget=shared)
            with self.assertRaises(S.SubmissionError):
                S.write_submission(bad, schema, budget=shared, prediction_class_order=order)
            self.assertEqual(prior, (sha(schema.output_path), schema.output_path.stat().st_mtime_ns))
        with self.case("wrong_model_probability_order_never_silently_written"):
            with self.assertRaises(S.SubmissionError):
                S.write_submission(values, schema, budget=shared, prediction_class_order=list(reversed(order)))
            self.assertEqual(prior, (sha(schema.output_path), schema.output_path.stat().st_mtime_ns))

    def test_private_sequence_failure_text_omits_id_canary(self):
        with self.case("H03-QA-RAW-ID-001_synthetic_failure_canary_not_logged"):
            canary = "H03_SYNTHETIC_ID_FAILURE_CANARY_91da"
            actual, expected = (canary,), ("reference",)

            class LegacyComparison(unittest.TestCase):
                def runTest(self):
                    self.assertEqual(actual, expected)

            before = unittest.TestResult()
            LegacyComparison().run(before)
            self.assertEqual(len(before.failures), 1)
            before_text = before.failures[0][1]
            self.assertTrue(canary in before_text, "legacy assertEqual leak fixture did not reproduce")
            for kind in ("id_order", "row_index_order"):
                class PrivateComparison(unittest.TestCase):
                    def runTest(self):
                        assert_private_sequence_equal(self, actual, expected, kind=kind)

                after = unittest.TestResult()
                PrivateComparison().run(after)
                self.assertEqual(len(after.failures), 1)
                self.assertEqual(after.errors, [])
                after_text = after.failures[0][1]
                self.assertFalse(canary in after_text, "private comparison leaked a synthetic ID; value omitted")
                self.assertIn("values omitted", after_text)
                PRIVACY_CONTROLS.append({"finding": "H03-QA-RAW-ID-001", "kind": kind,
                    "scope": "test failure reporting only; synthetic dummy TestCases, not a product failure",
                    "legacy_dummy_failures": len(before.failures), "after_dummy_failures": len(after.failures),
                    "legacy_failure_contains_synthetic_id": True, "after_failure_contains_synthetic_id": False,
                    "raw_failure_text_or_canary_in_receipt": False,
                    "legacy_failure_text_sha256": hashlib.sha256(before_text.encode()).hexdigest(),
                    "after_failure_text_sha256": hashlib.sha256(after_text.encode()).hexdigest()})
    def test_synthetic_text_numeric_category_full_chain(self):
        with self.case("full_chain_tiny_text_dictionary_schema_fit_transform_writer"):
            fixture = temporal_fixture(self.base / "mixed")
            fixture.headers["train"].append("message")
            fixture.headers["test"].append("message")
            for index, row in enumerate(fixture.rows["train"]):
                row.append("fitword alpha" if index == 0 else "protectedword beta")
            for row in fixture.rows["test"]:
                row.append("unseenword gamma")
            fixture.dictionary.append(["message", "feature", "text"])
            fixture.save()
            shared = unit_budget()
            bundle, _, plan, task = bind_fixture(fixture, shared)
            scope = F.ProfileScope(plan.fit_indices, plan.protected_indices, plan.train_rows,
                                   plan.train_sha256, plan.policy_id)
            profile = F.profile_task(bundle, task, scope, budget=shared)
            self.assertNotIn("protectedword", profile["prompt"])
            schema = feature_schema(bundle, task)
            view = P.load_train_fit_view(bundle, task, plan, schema=schema, budget=shared)
            test = P.load_test_features(bundle, task, schema=schema, budget=shared)
            fitted, train_ready = P.fit_transform(view, budget=shared)
            state = fitted.statistics_sha256
            ready = fitted.transform(test, budget=shared)
            self.assertEqual(state, fitted.statistics_sha256)
            self.assertEqual(train_ready.matrix.shape[0], 1)
            self.assertEqual(ready.matrix.shape[0], 3)
            self.assertNotIn("protectedword", json.dumps(fitted.statistics()))
            output = S.build_submission_schema(bundle, task, budget=shared)
            result = S.write_submission([0.0] * 3, output, budget=shared)
            self.assertEqual(S.validate_submission(output.output_path, output, budget=shared)["sha256"], result["sha256"])

    def actual_chain(self, kind, folder):
        with self.case("actual_" + kind + "_full_H03_chain_diagnostic_predictions_only"):
            original = ROOT / "drive-download-20261019T181414Z-1-001" / folder
            if not all((original / name).is_file() for name in INPUTS):
                ACTUAL.append({"dataset": kind, "status": "SKIP_SOURCE_ABSENT"})
                self.skipTest("public source directory absent")
            started = monotonic()
            shared = SHARED_ACTUAL
            shared.require()
            fixed_deadline = shared.deadline_ns
            original_hashes = {name: sha(original / name) for name in INPUTS}
            original_csv = original / "submission.csv"
            csv_before = (sha(original_csv), original_csv.stat().st_mtime_ns) if original_csv.is_file() else None
            work = self.base / "public-copy"
            work.mkdir()
            for name in INPUTS:
                shared.require()
                shutil.copyfile(original / name, work / name)
            self.assertEqual(original_hashes, {name: sha(work / name) for name in INPUTS})
            task = C.build_task_contract(work / "task.md", budget=shared)
            original_payload = task.to_dict()
            bundle = I.discover_inputs(work / "task.md", shared)
            plan = V.build_split_plan(bundle, task, strategy="temporal" if kind == "regression" else "stratified",
                time_column="Year_Factor" if kind == "regression" else None, budget=shared, seed=42)
            task = C.attach_split_plan(task, plan, budget=shared)
            self.assertEqual(original_payload["split_policy"]["status"], "NOT_BUILT")
            T.validate_task_contract(task.to_dict())
            expected_counts = {"fit": 22054, "inner": 12946, "outer": 18308} if kind == "regression" else {
                "fit": 56108, "inner": 14028, "outer": 17534}
            self.assertEqual(plan.to_dict()["counts"], expected_counts)
            scope = F.ProfileScope(plan.fit_indices, plan.protected_indices, plan.train_rows,
                                   plan.train_sha256, plan.policy_id)
            profile = F.profile_task(bundle, task, scope, budget=shared)
            self.assertEqual(profile["provenance"]["scope"]["fit_count"], len(plan.fit_indices))
            self.assertEqual(profile["provenance"]["scope"]["protected_count"], len(plan.protected_indices))
            self.assertLessEqual(profile["prompt_bytes"], profile["limits"]["max_prompt_bytes"])
            schema = feature_schema(bundle, task)
            view = P.load_train_fit_view(bundle, task, plan, schema=schema, budget=shared)
            assert_private_sequence_equal(self, view.row_indices, plan.fit_indices, kind="row_index_order")
            self.assertEqual(view.source_binding, "verified_csv_bytes_and_explicit_partition")
            self.assertFalse(set(schema.feature_columns) & set(task.to_dict()["target_columns"] + task.to_dict()["id_columns"]))
            test = P.load_test_features(bundle, task, schema=schema, budget=shared)
            fitted, prepared = P.fit_transform(view, budget=shared)
            witness = fitted.statistics_sha256
            transformed = fitted.transform(test, budget=shared)
            self.assertEqual(fitted.statistics_sha256, witness)
            self.assertEqual(prepared.matrix.shape[0], len(plan.fit_indices))
            self.assertEqual(transformed.matrix.shape[0], len(test))
            expected_test = 22449 if kind == "regression" else 41166
            self.assertEqual(len(test), expected_test)
            assert_private_sequence_equal(self, tuple(test.index), tuple(range(expected_test)), kind="row_index_order")
            self.assertEqual(prepared.matrix.shape[1], transformed.matrix.shape[1])
            if kind == "classification":
                self.assertIn("Normal", bundle.task_text, "diagnostic label must be explicitly declared by source task")
                predictions = ["Normal"] * expected_test
                known_labels = M.PUBLIC_DIAGNOSTIC_LABELS
            else:
                predictions, known_labels = [0.0] * expected_test, None
            output = S.build_submission_schema(bundle, task, budget=shared, allowed_labels=known_labels)
            self.assertEqual(output.limits.probability_tolerance, M.PROBABILITY_SUM_ATOL)
            self.assertEqual(output.output_path.parent, work.resolve())
            written = S.write_submission(predictions, output, budget=shared)
            validated = S.validate_submission(output.output_path, output, budget=shared, expected_sha256=written["sha256"])
            self.assertEqual(validated["sha256"], sha(output.output_path))
            self.assertEqual(validated["row_count"], expected_test)
            # Independently compare lexical ID order to test.csv, rather than
            # reusing SubmissionSchema's expected-ID/map implementation.
            compared_rows = 0
            with (work / "test.csv").open("r", encoding="utf-8-sig", newline="") as test_stream, \
                    output.output_path.open("r", encoding="utf-8", newline="") as output_stream:
                test_reader, output_reader = csv.reader(test_stream), csv.reader(output_stream)
                test_header, output_header = next(test_reader), next(output_reader)
                test_positions = [test_header.index(name) for name in output.id_columns]
                output_positions = [output_header.index(name) for name in output.id_columns]
                for test_row, output_row in zip(test_reader, output_reader):
                    if compared_rows % 256 == 0:
                        shared.require()
                    assert_private_sequence_equal(self, tuple(test_row[position] for position in test_positions),
                        tuple(output_row[position] for position in output_positions), kind="id_order")
                    compared_rows += 1
            self.assertEqual(compared_rows, expected_test)
            artifacts = C.publish_task_contract(task, budget=shared)
            saved_path = Path(artifacts["task_contract_path"])
            saved = json.loads(saved_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["split_policy"]["status"], "BUILT")
            self.assertEqual(saved["split_policy"]["partition_sha256"], plan.partition_sha256)
            self.assertEqual(saved["metric"]["adapter_version"], M.ADAPTER_VERSION)
            self.assertEqual(sha(saved_path), artifacts["task_contract_sha256"])
            self.assertEqual(sha(Path(artifacts["alignment_path"])), artifacts["alignment_sha256"])
            self.assertEqual(len(list((work / ".aegml_runs").glob("*/*.json"))), 2)
            self.assertEqual(original_hashes, {name: sha(original / name) for name in INPUTS})
            self.assertEqual(original_hashes, {name: sha(work / name) for name in INPUTS})
            csv_after = (sha(original_csv), original_csv.stat().st_mtime_ns) if original_csv.is_file() else None
            self.assertEqual(csv_before, csv_after)
            self.assertEqual(fixed_deadline, shared.deadline_ns)
            V.verify_split_source(plan, bundle, budget=shared)
            ACTUAL.append({"dataset": kind, "status": "PASS_FULL_H03_CHAIN_ONLY",
                "source_sha256": bundle.source_sha256, "schema_sha256": schema.schema_sha256,
                "split_schema_sha256": plan.schema_sha256, "split_sha256": plan.partition_sha256,
                "partition_counts": expected_counts, "source_rows": plan.train_rows,
                "test_rows_retained": len(test), "fit_shape": list(prepared.matrix.shape),
                "test_shape": list(transformed.matrix.shape), "fit_values_sha256": view.fit_values_sha256,
                "trained_preprocessing_statistics_sha256": witness, "profile_schema_sha256": profile["provenance"]["schema_sha256"],
                "profile_prompt_bytes": profile["prompt_bytes"], "profile_prompt_sha256": hashlib.sha256(profile["prompt"].encode()).hexdigest(),
                "protected_rows_not_retained_in_fit_view": True, "target_or_id_features_retained": False,
                "csv_sha256": validated["sha256"], "csv_rows": validated["row_count"],
                "test_id_order_independently_compared": True,
                "contract_sha256": artifacts["task_contract_sha256"], "alignment_sha256": artifacts["alignment_sha256"],
                "published_contract_split_status": saved["split_policy"]["status"],
                "source_files_unchanged": True, "original_csv_preserved_or_absent": True,
                "budget_started_ns": shared.started_ns, "budget_deadline_ns": shared.deadline_ns,
                "same_actual_budget_object_used": shared is SHARED_ACTUAL,
                "elapsed_seconds": monotonic() - started,
                "process_peak_rss_mib_so_far": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
                "rss_scope": "whole integration process peak, includes earlier tests/tasks; not isolated task peak",
                "prediction_scope": "DIAGNOSTIC_CONSTANT_ONLY_NO_TRAINED_MODEL",
                "model_fitted": False, "outer_quality_evaluated": False, "official_score": None,
                "raw_ids_targets_or_csv_rows_in_receipt": False})

    def test_actual_public_classification_full_chain(self):
        self.actual_chain("classification", "Многоклассовая классификация")

    def test_actual_public_regression_full_chain(self):
        self.actual_chain("regression", "Регрессия")


def main():
    global SHARED_ACTUAL, SCRATCH
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if os.path.lexists(args.receipt):
        parser.error("receipt exists; select a fresh path")
    configured_scratch = os.environ.get("TEMPROOT")
    if configured_scratch:
        SCRATCH = Path(configured_scratch).resolve()
        SCRATCH.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x", encoding="utf-8") as stream:
        before = {name: sha(ROOT / name) for name in SOURCES}
        receipt = {"phase": "H03_INTEGRATION_H035", "status": "NOT_RUN", "python": platform.python_version(),
            "scope": "synthetic eight-metric registry/writer plus two full public H03 chains using diagnostic constant predictions",
            "source_sha256": before, "model_fit_calls": 0, "live_api_calls": 0,
            "preprocessing_fitted": True, "generated_code_executed": False,
            "official_image_verified": False, "full_H05_accepted": False,
            "public_quality_evaluated": False, "outer_quality_evaluated": False,
            "temporary_roots_only_for_writes": True, "scratch_environment_variable": "TEMPROOT",
            "python_interpreter_startup_before_STARTED_NS": "NOT_MEASURED"}
        code = 1
        if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
            receipt.update(status="BLOCKED_WRONG_CHECK_ENVIRONMENT", test_methods_run=0, behavior_cases_checked=0)
            code = 2
        else:
            try:
                load_modules()
                SHARED_ACTUAL = C.RunBudget(STARTED_NS, 300, 30)
                public_before = public_inventory()
                if before["requirements.txt"] != EXPECTED_REQUIREMENTS_SHA:
                    raise RuntimeError("provided_requirements_sha_mismatch")
                result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(IntegrationChecks))
                after = {name: sha(ROOT / name) for name in SOURCES}
                public_after = public_inventory()
                stable = before == after and public_before == public_after
                all_actual = len(ACTUAL) == 2 and all(entry["status"] == "PASS_FULL_H03_CHAIN_ONLY" for entry in ACTUAL)
                passed = result.wasSuccessful() and stable and len(REGISTRY_CHECKS) == 8 and all_actual
                status = "FAIL_H03_INTEGRATION"
                if passed:
                    status = "PASS_H03_INTEGRATION_ONLY"
                receipt.update(status=status, test_methods_run=result.testsRun, behavior_cases_checked=len(CASES),
                    behavior_cases_passed=sum(entry["status"] == "PASS" for entry in CASES), cases=CASES,
                    registry_checks=REGISTRY_CHECKS, actual_public_checks=ACTUAL,
                    privacy_failure_controls=PRIVACY_CONTROLS,
                    source_sha256_after=after, source_unchanged_during_check=before == after,
                    public_source_file_count=len(public_before), public_source_sha256=public_before,
                    public_sources_unchanged=public_before == public_after,
                    all_requested_public_chains_verified=all_actual,
                    probability_sum_tolerance=M.PROBABILITY_SUM_ATOL,
                    single_shared_actual_budget={"constructions": 1, "started_ns": SHARED_ACTUAL.started_ns,
                        "deadline_ns": SHARED_ACTUAL.deadline_ns, "total_seconds": 300, "reserve_seconds": 30,
                        "scope": "both actual public chains, including source copies and metadata publication; no reset"},
                    unittest_failures=[{"test": test.id(), "detail": detail} for test, detail in result.failures],
                    unittest_errors=[{"test": test.id(), "detail": detail} for test, detail in result.errors],
                    unittest_skips=[{"test": test.id(), "reason": reason} for test, reason in result.skipped])
                code = 0 if passed else 1
            except Exception as exc:
                receipt.update(status="FAIL_H03_INTEGRATION_SETUP", error_type=type(exc).__name__,
                    error_code=getattr(exc, "code", None), test_methods_run=0, behavior_cases_checked=len(CASES))
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": receipt["status"], "test_methods_run": receipt["test_methods_run"],
                     "behavior_cases_checked": receipt["behavior_cases_checked"], "receipt": str(args.receipt)}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
