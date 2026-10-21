"""H03.3/H03.5 numerical metrics and trusted split metadata acceptance.

Python 3.12 Linux only. Synthetic hand calculations and installed sklearn 1.5.2
oracles perform no fit. Optional actual public checks read source CSVs in fresh
Python children, build splits and verify counts/SHA, never evaluate outer quality.
No provider configuration, API, downloaded data or executable task content.
"""

import argparse
from collections import Counter
from contextlib import contextmanager
import csv
from dataclasses import FrozenInstanceError, asdict, replace
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import tempfile
from time import monotonic_ns
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("aegml_metrics.py", "aegml_validation.py", "aegml_input.py", "aegml_contracts.py",
           "aegml_schemas.py", "requirements.txt", "scripts/check_h033_metrics_validation.py")
INPUTS = ("task.md", "train.csv", "test.csv", "data_dictionary.csv", "sample_submission.csv")
CASES, PUBLIC_CHECKS, ORACLES, CHILDREN = [], [], [], []
M = V = C = I = None
RULES = {"rmse": ("minimize", "numeric"), "mae": ("minimize", "numeric"),
         "accuracy": ("maximize", "label"), "macro_f1": ("maximize", "label"),
         "weighted_f1": ("maximize", "label"), "binary_f1": ("maximize", "label"),
         "log_loss": ("minimize", "probability"), "roc_auc": ("maximize", "probability")}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def budget():
    return C.RunBudget(monotonic_ns(), 120, 0)


def contract(name, **changes):
    direction, kind = RULES[name]
    params = {"average": "macro", "labels": None} if name == "macro_f1" else (
        {"average": "weighted", "labels": None} if name == "weighted_f1" else {})
    result = {"name": name, "direction": direction, "prediction_kind": kind,
        "parameters": params, "label_policy": "sklearn_labels_none" if name.endswith("f1") else None,
        "positive_label": None, "class_order": None, "target_scale": "original",
        "finite_policy": "finite_only", "adapter_version": "metrics.v1", "evidence": []}
    result.update(changes)
    return result


def write_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


class Fixture:
    def __init__(self, root, *, classification=False, labels=None):
        self.root = root
        root.mkdir(parents=True)
        self.classification = classification
        if classification:
            labels = labels if labels is not None else ["A", "B"] * 20
            self.rows = [["train-" + str(index), label, (index % 5) + 1, index]
                         for index, label in enumerate(labels)]
        else:
            self.rows = [["train-" + str(index), index + 0.5, (index % 5) + 1, index]
                         for index in range(15)]
        self.task = root / "task.md"
        self.task.write_text("Task type: " + ("classification" if classification else "regression") +
            "\nTarget: y\nID: id\nMetric: " + ("Macro F1" if classification else "RMSE") +
            "\nOutput order: test\n" + "".join("- `" + name + "`\n" for name in INPUTS[1:]), encoding="utf-8")
        write_csv(root / "train.csv", ["id", "y", "Year_Factor", "value"], self.rows)
        write_csv(root / "test.csv", ["value", "id", "Year_Factor"], [[1, "test-001", 6], [2, "test-NA", 6]])
        write_csv(root / "sample_submission.csv", ["y", "id"], [[0, "test-NA"], [0, "test-001"]])
        write_csv(root / "data_dictionary.csv", ["feature", "role", "dtype"],
            [["id", "id", "string"], ["y", "target", "category" if classification else "numeric"],
             ["Year_Factor", "feature", "numeric"], ["value", "feature", "numeric"]])

    def inputs(self):
        return I.discover_inputs(self.task, budget()), C.build_task_contract(self.task, budget=budget())


class Checks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="aegml-h033-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

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

    def metric(self, name, truth, predictions, **kwargs):
        fields = kwargs.pop("fields", {})
        return M.evaluate_metric(contract(name, **fields), truth, predictions, **kwargs)

    def plan(self, fixture, **kwargs):
        bundle, task = fixture.inputs()
        return V.build_split_plan(bundle, task, strategy="stratified" if fixture.classification else "temporal",
            budget=budget(), time_column=None if fixture.classification else "Year_Factor", **kwargs)

    def test_exact_eight_registry_and_immutable_specs(self):
        with self.case("exact_eight_no_silent_RMSLE_MAPE_or_alias"):
            self.assertEqual(set(M.METRIC_REGISTRY), set(RULES))
            for name, expected in RULES.items():
                self.assertEqual((M.metric_spec(name).direction, M.metric_spec(name).prediction_kind), expected)
            with self.assertRaises(TypeError):
                M.METRIC_REGISTRY["rmse"] = None
            with self.assertRaises(FrozenInstanceError):
                M.metric_spec("rmse").direction = "maximize"
            for name in ("rmsle", "mape", "binary_roc_auc", "__import__('os')", None):
                with self.subTest(name=name), self.assertRaises(M.MetricError):
                    M.metric_spec(name)

    def test_hand_regression_and_global_oof(self):
        with self.case("RMSE_sqrt2_MAE1_and_SSE_weighted_OOF"):
            self.assertAlmostEqual(self.metric("rmse", [0, 2], [0, 0]).value, math.sqrt(2))
            self.assertEqual(self.metric("mae", [0, 2], [0, 0]).value, 1)
            global_rmse = M.aggregate_oof_rmse([(0, 1), (12, 3)])
            self.assertAlmostEqual(global_rmse, math.sqrt(3))
            self.assertNotAlmostEqual(global_rmse, (0 + 2) / 2)
            self.assertEqual(self.metric("rmse", [1e308, 1e308], [0, 0]).value, 1e308)
            self.assertEqual(self.metric("mae", [1e308, 1e308], [0, 0]).value, 1e308)
            self.assertAlmostEqual(self.metric("rmse", [1e308, 0], [-1e308, 0]).value / 1e308, math.sqrt(2))
            self.assertEqual(self.metric("mae", [1e308, 0], [-1e308, 0]).value, 1e308)

    def test_macro_weighted_accuracy_binary_are_distinct(self):
        for name, expected, fields in (("accuracy", 3/4, {}), ("macro_f1", 3/7, {}),
                ("weighted_f1", 9/14, {}), ("binary_f1", 0, {"positive_label": "B"}),
                ("binary_f1", 6/7, {"positive_label": "A"})):
            with self.subTest(name=name, fields=fields), self.case("hand_" + name + "_" + str(fields.get("positive_label", "union"))):
                self.assertAlmostEqual(self.metric(name, ["A", "A", "A", "B"], ["A"] * 4, fields=fields).value, expected)

    def test_primary_union_and_fixed10_diagnostic(self):
        with self.case("primary_labels_None_not_fixed10_or_micro"):
            self.assertEqual(self.metric("macro_f1", ["Normal"] * 3, ["Normal"] * 3).value, 1)
            self.assertEqual(M.macro_f1_fixed10(["Normal"] * 3, ["Normal"] * 3).value, .1)
            self.assertEqual(self.metric("macro_f1", ["Normal"], ["Normal"],
                fields={"class_order": list(M.PUBLIC_DIAGNOSTIC_LABELS)}).value, 1)
            self.assertAlmostEqual(self.metric("macro_f1", ["A", "A"], ["A", "B"]).value, 1/3)
            with self.assertRaises(M.MetricError):
                self.metric("macro_f1", ["A"], ["unknown"], allowed_labels=["A", "B"])

    def test_literal_and_numeric_class_labels(self):
        with self.case("NA_null_001_literals_and_numeric_labels_preserved"):
            values = ["NA", "null", "001", "1"]
            self.assertEqual(self.metric("macro_f1", values, values).value, 1)
            self.assertEqual(self.metric("accuracy", [2**60, 2**60 + 1], [2**60, 2**60 + 1]).value, 1)
            self.assertEqual(self.metric("accuracy", [0, 1], [1, 1]).value, .5)
            for invalid in ([""], [" "], [float("nan")], [float("inf")], [True], ["1", 1]):
                with self.subTest(invalid=repr(invalid)), self.assertRaises(M.MetricError):
                    self.metric("accuracy", invalid, invalid)

    def test_fractional_class_codes_follow_explicit_classification_contract(self):
        from sklearn import metrics as oracle
        with self.case("H033-METRIC-LABEL-001_fractional_codes_are_discrete_labels"):
            truth, pred = [1.5, 2.5], [1.5, 1.5]
            # sklearn's target-type heuristic calls raw floats continuous;
            # the explicit task contract supplies their categorical meaning.
            # Encode that declared vocabulary for an independent oracle.
            order = [2.5, 1.5]
            encoded_y = [order.index(value) for value in truth]
            encoded_p = [order.index(value) for value in pred]
            for name, expected, fields in (
                    ("accuracy", oracle.accuracy_score(encoded_y, encoded_p), {}),
                    ("macro_f1", oracle.f1_score(encoded_y, encoded_p, average="macro"), {}),
                    ("binary_f1", oracle.f1_score(encoded_y, encoded_p, pos_label=1), {"positive_label": 1.5})):
                actual = self.metric(name, truth, pred, fields=fields).value
                self.assertAlmostEqual(actual, float(expected))
                ORACLES.append({"metric": name, "own": actual, "sklearn": float(expected),
                    "encoding": "explicit finite fractional class vocabulary -> discrete index",
                    "finding": "H033-METRIC-LABEL-001", "fit_executed": False})
            self.assertAlmostEqual(self.metric("log_loss", truth, [[.25, .75], [.75, .25]],
                fields={"class_order": order}).value, -math.log(.75))

    def test_regression_invalid_finite_shape_and_contract(self):
        variants = (([], []), ([1], []), ([1, 2], [1]), ([True], [0]), (["1"], [1]),
                    ([float("nan")], [0]), ([0], [float("inf")]), ([1e308], [-1e308]), ([[1]], [[1]]))
        for number, (truth, pred) in enumerate(variants):
            with self.subTest(number=number), self.case("bad_regression_input_" + str(number)):
                with self.assertRaises(M.MetricError):
                    self.metric("rmse", truth, pred)
        for fields in ({"direction": "maximize"}, {"target_scale": "log1p"}, {"finite_policy": None},
                       {"prediction_kind": "label"}, {"parameters": {"formula": "eval"}}):
            with self.subTest(fields=fields), self.case("reject_metric_contract_" + next(iter(fields))):
                with self.assertRaises(M.MetricError):
                    self.metric("rmse", [0], [0], fields=fields)

    def test_probability_order_logloss_and_auc_orientation(self):
        with self.case("explicit_probability_class_order_and_positive_label"):
            fields = {"class_order": ["B", "A"]}
            self.assertAlmostEqual(self.metric("log_loss", ["A", "B"], [[.25, .75], [.75, .25]], fields=fields).value, -math.log(.75))
            self.assertAlmostEqual(self.metric("log_loss", ["A", "B"], [[.75, .25], [.25, .75]], fields=fields,
                prediction_class_order=["A", "B"]).value, -math.log(.75))
            self.assertEqual(self.metric("roc_auc", ["A", "B"], [.9, .1], fields={"positive_label": "A"}).value, 1)
            self.assertEqual(self.metric("roc_auc", ["A", "B"], [.9, .1], fields={"positive_label": "B"}).value, 0)
            self.assertEqual(self.metric("roc_auc", ["A", "B"], [[.9, .1], [.1, .9]],
                fields={"positive_label": "A", "class_order": ["A", "B"]}).value, 1)
            self.assertEqual(M.binary_roc_auc([0, 1], [-8, 9], positive_label=1), 1)
            self.assertEqual(M.binary_roc_auc([0, 1], [.5, .5], positive_label=1), .5)

    def test_probability_rejections_and_undefined_auc(self):
        bad = ([[.3, .3], [.2, .8]], [[1.1, -.1], [.2, .8]], [[float("nan"), 0], [.2, .8]],
               [[.2, .8]], [[.2, .3, .5], [.2, .3, .5]], [0.2, 0.8])
        for number, pred in enumerate(bad):
            with self.subTest(number=number), self.case("reject_bad_probability_" + str(number)):
                with self.assertRaises(M.MetricError):
                    self.metric("log_loss", ["A", "B"], pred, fields={"class_order": ["A", "B"]})
        for fields in ({}, {"class_order": ["A", "A"]}, {"class_order": ["A", "C"]}):
            with self.subTest(fields=fields), self.case("reject_missing_duplicate_or_unknown_class_order_" + str(len(fields))):
                with self.assertRaises(M.MetricError):
                    self.metric("log_loss", ["A", "B"], [[.2, .8], [.4, .6]], fields=fields)
        with self.case("AUC_single_class_is_undefined_not_zero"):
            with self.assertRaises(M.UndefinedMetric) as caught:
                self.metric("roc_auc", ["A", "A"], [.1, .9], fields={"positive_label": "A"})
            self.assertEqual(caught.exception.code, "roc_auc_single_class")
            with self.assertRaises(M.MetricError):
                self.metric("roc_auc", ["A", "B"], [.1, .9])
            with self.assertRaises(M.MetricError):
                self.metric("roc_auc", ["A", "B"], [-1, 2], fields={"positive_label": "B"})

    def test_review_auc_declared_classes_checked_in_every_shape(self):
        fields = {"class_order": ["neg", "pos"], "positive_label": "pos"}
        for label, predictions in (("1D", [.1, .9]), ("2D", [[.9, .1], [.1, .9]])):
            with self.subTest(shape=label), self.case("H035-AUC-CLASS-001_unknown_truth_" + label):
                with self.assertRaises(M.MetricError) as caught:
                    self.metric("roc_auc", ["other", "pos"], predictions, fields=fields)
                self.assertEqual(caught.exception.code, "invalid_binary_class_contract")
        with self.case("H035-AUC-CLASS-001_declared_1D_valid_control"):
            self.assertEqual(self.metric("roc_auc", ["neg", "pos"], [.1, .9], fields=fields).value, 1.0)
        with self.case("H035-AUC-CLASS-001_no_declared_order_explicit_positive_still_allowed"):
            self.assertEqual(self.metric("roc_auc", ["other", "pos"], [.1, .9],
                fields={"positive_label": "pos"}).value, 1.0)
        with self.case("H035-AUC-CLASS-001_reordered_2D_valid_control"):
            self.assertEqual(self.metric("roc_auc", ["neg", "pos"], [[.1, .9], [.9, .1]],
                fields=fields, prediction_class_order=["pos", "neg"]).value, 1.0)
        for label, predictions in (("1D", [.1, .9]), ("2D", [[.9, .1], [.1, .9]])):
            with self.subTest(shape=label), self.case("H035-AUC-CLASS-001_known_single_class_undefined_" + label):
                with self.assertRaises(M.UndefinedMetric) as caught:
                    self.metric("roc_auc", ["neg", "neg"], predictions, fields=fields)
                self.assertEqual(caught.exception.code, "roc_auc_single_class")

    def test_review_oof_finite_sum_overflow_scale_safe(self):
        with self.case("H033-OOF-FINITE-001_finite_fold_sum_overflow_has_finite_RMSE"):
            actual = M.aggregate_oof_rmse([(1e308, 1), (1e308, 1)])
            self.assertAlmostEqual(actual / 1e154, 1.0)
            self.assertTrue(math.isfinite(actual))
        with self.case("H033-OOF-FINITE-001_zero_SSE_control"):
            self.assertEqual(M.aggregate_oof_rmse([(0.0, 1), (0.0, 3)]), 0.0)
        with self.case("H033-OOF-FINITE-001_overflowing_SSE_sum_unequal_count_weighting"):
            actual = M.aggregate_oof_rmse([(1e308, 1), (1e308, 3)])
            self.assertAlmostEqual(actual / 1e154, math.sqrt(.5))
        invalid = ([], [(-1, 1)], [(float("inf"), 1)], [(float("nan"), 1)],
                   [(1, 0)], [(1, True)], [(1, 1.5)], [(1,)])
        for number, values in enumerate(invalid):
            with self.subTest(number=number), self.case("H033-OOF-FINITE-001_invalid_fold_stats_" + str(number)):
                with self.assertRaises(M.MetricError):
                    M.aggregate_oof_rmse(values)
        with self.case("H033-OOF-FINITE-001_shared_expired_budget_control"):
            expired = C.RunBudget(0, 1, 0, lambda: 2_000_000_000)
            with self.assertRaises(C.BudgetExpired):
                M.aggregate_oof_rmse([(1e308, 1), (1e308, 1)], budget=expired)

    def test_logloss_clipping_is_float64_explicit_and_finite(self):
        with self.case("logloss_float64_endpoint_clipping_not_silent_normalization"):
            result = self.metric("log_loss", ["A", "B"], [[0, 1], [1, 0]], fields={"class_order": ["A", "B"]})
            self.assertAlmostEqual(result.value, -math.log(sys.float_info.epsilon))
            self.assertIsNone(result.to_dict()["official_score"])
            json.dumps(result.to_dict(), allow_nan=False)

    def test_probability_float32_roundoff_and_shared_tolerance(self):
        import numpy as np
        order = ["C" + str(index) for index in range(10)]
        row = np.full(10, .1, dtype=np.float32)
        with self.case("float32_softmax_roundoff_accepted_without_normalizing"):
            self.assertGreater(abs(math.fsum(float(value) for value in row) - 1), 1e-8)
            result = self.metric("log_loss", ["C0"], [row], fields={"class_order": order})
            self.assertAlmostEqual(result.value, -math.log(float(row[0])), places=13)
            self.assertEqual(result.to_dict()["probability_policy"]["row_sum_atol"], 1e-6)
            self.assertEqual(result.to_dict()["probability_policy"]["normalization"], "none")
        with self.case("probability_sum_beyond_shared_tolerance_refused"):
            with self.assertRaises(M.MetricError) as caught:
                self.metric("log_loss", ["C0"], [[.1000002] * 10], fields={"class_order": order})
            self.assertEqual(caught.exception.code, "probability_row_sum_invalid")

    def test_installed_sklearn_oracles_without_fit(self):
        import numpy as np
        import sklearn
        from sklearn import metrics as oracle
        with self.case("pinned_sklearn152_metric_oracles_no_fit"):
            self.assertEqual(sklearn.__version__, "1.5.2")
            rng = random.Random(933)
            truth = [rng.uniform(-5, 5) for _ in range(51)]
            pred = [rng.uniform(-5, 5) for _ in truth]
            examples = [("rmse", truth, pred, {}, oracle.root_mean_squared_error(truth, pred)),
                        ("mae", truth, pred, {}, oracle.mean_absolute_error(truth, pred))]
            labels = ["A", "B", "C"]
            y = [rng.choice(labels) for _ in range(61)]
            p = [rng.choice(labels) for _ in y]
            examples.extend((name, y, p, {}, function(y, p, **parameters)) for name, function, parameters in (
                ("accuracy", oracle.accuracy_score, {}),
                ("macro_f1", oracle.f1_score, {"average": "macro", "zero_division": 0}),
                ("weighted_f1", oracle.f1_score, {"average": "weighted", "zero_division": 0})))
            binary = [0, 1] * 21
            binary_pred = [rng.randrange(2) for _ in binary]
            examples.append(("binary_f1", binary, binary_pred, {"positive_label": 0},
                             oracle.f1_score(binary, binary_pred, pos_label=0)))
            scores = [rng.random() for _ in binary]
            examples.append(("roc_auc", binary, scores, {"positive_label": 0},
                             oracle.roc_auc_score([value == 0 for value in binary], scores)))
            order = ["C", "A", "B"]
            raw = [[rng.random() for _ in order] for _ in y]
            probabilities = [[value / sum(row) for value in row] for row in raw]
            encoded = [order.index(value) for value in y]
            examples.append(("log_loss", y, probabilities, {"class_order": order},
                oracle.log_loss(encoded, np.asarray(probabilities, dtype=np.float64), labels=list(range(3)))))
            for name, actual, predictions, fields, expected in examples:
                measured = self.metric(name, actual, predictions, fields=fields).value
                self.assertAlmostEqual(measured, float(expected), places=13)
                ORACLES.append({"metric": name, "own": measured, "sklearn": float(expected),
                                "sklearn_version": sklearn.__version__, "fit_executed": False})

    def test_temporal_plan_chronology_full_partition_and_identity(self):
        with self.case("temporal_public_rule_123_4_5_no_random_substitution"):
            fixture = Fixture(self.base / "temporal")
            plan = self.plan(fixture)
            self.assertEqual(plan.fit_indices, tuple(index for index, row in enumerate(fixture.rows) if row[2] <= 3))
            self.assertEqual(plan.inner_indices, tuple(index for index, row in enumerate(fixture.rows) if row[2] == 4))
            self.assertEqual(plan.outer_indices, tuple(index for index, row in enumerate(fixture.rows) if row[2] == 5))
            repeated = self.plan(fixture)
            self.assertEqual(plan.partition_sha256, repeated.partition_sha256)
            self.assertEqual(plan.train_sha256, sha(fixture.root / "train.csv"))
            self.assertNotIn("fit_indices", plan.to_dict())
            self.assertNotIn("time_values", plan.to_dict(include_indices=True))
            with self.assertRaises(FrozenInstanceError):
                plan.fit_indices = ()
            bundle, _ = fixture.inputs()
            self.assertTrue(V.verify_split_source(plan, bundle, budget=budget()))

    def test_stratified_nested_reproducible_and_every_class_present(self):
        with self.case("stratified_exact_counts_seed_repeat_and_all_classes"):
            fixture = Fixture(self.base / "classes", classification=True, labels=["NA"] * 21 + ["001"] * 14 + ["null"] * 10)
            plan = self.plan(fixture)
            self.assertEqual(len(plan.outer_indices), math.ceil(len(fixture.rows) * .2))
            self.assertEqual(len(plan.inner_indices), math.ceil((len(fixture.rows) - len(plan.outer_indices)) * .2))
            for part in (plan.fit_indices, plan.inner_indices, plan.outer_indices):
                self.assertEqual({fixture.rows[index][1] for index in part}, {"NA", "001", "null"})
            self.assertEqual(plan.partition_sha256, self.plan(fixture).partition_sha256)
            self.assertNotEqual(plan.outer_indices, self.plan(fixture, seed=81).outer_indices)
            self.assertEqual(set(plan.fit_indices) | set(plan.inner_indices) | set(plan.outer_indices), set(range(len(fixture.rows))))
            manifest = json.dumps(plan.to_dict(include_indices=True))
            self.assertNotIn('"NA"', manifest)
            self.assertNotIn('"null"', manifest)

    def test_rare_class_refusal_never_drops_labels(self):
        for labels in (["A"] * 20 + ["B"] * 2, ["A"] * 3 + ["B"] * 3, ["A"] * 15):
            with self.subTest(n=len(labels)), self.case("rare_class_infeasible_" + str(len(labels))):
                fixture = Fixture(self.base / ("rare-" + str(len(labels))), classification=True, labels=labels)
                with self.assertRaises(V.ValidationError) as caught:
                    self.plan(fixture)
                self.assertEqual(caught.exception.code, "rare_class_split_infeasible")

    def test_invalid_partition_rejected(self):
        fixture = Fixture(self.base / "partition")
        plan = self.plan(fixture)
        replacements = ({"fit_indices": (True,)}, {"fit_indices": (0.0,)}, {"fit_indices": (0, 0)},
            {"fit_indices": (-1,)}, {"fit_indices": (100,)}, {"fit_indices": ()},
            {"fit_indices": plan.fit_indices + plan.inner_indices}, {"fit_indices": plan.fit_indices[:-1]},
            {"train_sha256": "bad"}, {"seed": True}, {"outer_fraction": float("nan")})
        for number, changes in enumerate(replacements):
            with self.subTest(number=number), self.case("invalid_partition_" + str(number)):
                with self.assertRaises(V.ValidationError):
                    replace(plan, **changes)

    def test_temporal_bad_period_policy_no_unknown_coverage(self):
        for changes in ({"fit_periods": (1, 2, 4), "inner_periods": (3,)}, {"inner_periods": (3, 4)},
                        {"outer_periods": (6,)}, {"fit_periods": (True, 2, 3)}):
            with self.subTest(changes=changes), self.case("invalid_temporal_policy_" + next(iter(changes))):
                fixture = Fixture(self.base / ("periods-" + str(len(CASES))))
                with self.assertRaises(V.ValidationError):
                    self.plan(fixture, **changes)
        with self.case("temporal_requires_explicit_column_no_public_name_guess"):
            fixture = Fixture(self.base / "no-column")
            bundle, task = fixture.inputs()
            with self.assertRaises(V.ValidationError):
                V.build_split_plan(bundle, task, strategy="temporal", budget=budget())

    def test_source_change_and_shared_expired_budget(self):
        with self.case("source_changed_rejected_and_no_new_timer_on_expiry"):
            fixture = Fixture(self.base / "source")
            bundle, task = fixture.inputs()
            plan = V.build_split_plan(bundle, task, strategy="temporal", budget=budget(), time_column="Year_Factor")
            for name in ("train.csv", "task.md"):
                path = fixture.root / name
                prior = path.read_bytes()
                path.write_bytes(prior + b"\n")
                with self.assertRaises(V.ValidationError) as caught:
                    V.verify_split_source(plan, bundle, budget=budget())
                self.assertEqual(caught.exception.code, "source_changed")
                path.write_bytes(prior)
            expired = C.RunBudget(0, 1, 0, lambda: 2_000_000_000)
            with self.assertRaises(C.BudgetExpired):
                V.build_split_plan(bundle, task, strategy="temporal", budget=expired, time_column="Year_Factor")
            with self.assertRaises(C.BudgetExpired):
                M.evaluate_metric(contract("rmse"), [1], [1], budget=expired)
            with self.assertRaises(V.ValidationError):
                V.build_split_plan(bundle, task, strategy="temporal", budget=None, time_column="Year_Factor")

    def test_early_stop_only_within_fit_and_temporal_order(self):
        with self.case("early_stop_12_train_3_holdout_excludes_4_5"):
            fixture = Fixture(self.base / "early")
            plan = self.plan(fixture)
            train = tuple(index for index in plan.fit_indices if fixture.rows[index][2] <= 2)
            stop = tuple(index for index in plan.fit_indices if fixture.rows[index][2] == 3)
            early = V.build_early_stop_plan(plan, train_indices=train, stop_indices=stop)
            self.assertEqual(set(early.train_indices) | set(early.stop_indices), set(plan.fit_indices))
            self.assertEqual(early.split_sha256, plan.partition_sha256)
            for wrong_train, wrong_stop in ((train, plan.inner_indices), (train, plan.outer_indices),
                                            (stop, train), (train, train)):
                with self.assertRaises(V.ValidationError):
                    V.build_early_stop_plan(plan, train_indices=wrong_train, stop_indices=wrong_stop)

    def test_phase_grants_freeze_iterations_and_refit_not_claimed(self):
        with self.case("search_fit_only_then_frozen_development_no_outer_feedback"):
            plan = self.plan(Fixture(self.base / "phases"))
            search = V.phase_grant(plan, "search")
            self.assertEqual(search.train_indices, plan.fit_indices)
            self.assertTrue(search.feedback_allowed)
            with self.assertRaises(V.ValidationError):
                V.phase_grant(plan, "frozen_refit")
            recipe = V.freeze_recipe(plan, code_sha256="a" * 64, config_sha256="b" * 64,
                preprocessing_sha256="c" * 64, iterations=25)
            refit = V.phase_grant(plan, "frozen_refit", recipe=recipe)
            self.assertEqual(refit.train_indices, plan.development_indices)
            self.assertFalse(set(refit.train_indices) & set(plan.outer_indices))
            self.assertEqual(refit.evaluator_indices, plan.outer_indices)
            self.assertFalse(refit.feedback_allowed)
            self.assertFalse(refit.refit_performed, "metadata grant is not an executed refit")
            self.assertNotIn("y", asdict(refit))
            with self.assertRaises(FrozenInstanceError):
                recipe.iterations = 26
            with self.assertRaises(V.ValidationError):
                V.phase_grant(replace(plan, seed=100), "frozen_refit", recipe=recipe)
            for iterations in (True, 0, -1, 1.5):
                with self.assertRaises(V.ValidationError):
                    V.freeze_recipe(plan, code_sha256="a" * 64, config_sha256="b" * 64,
                        preprocessing_sha256="c" * 64, iterations=iterations)

    def test_frozen_early_stop_provenance_revalidated(self):
        with self.case("frozen_iterations_bind_to_fit_side_early_stop_partition"):
            fixture = Fixture(self.base / "freeze-early")
            plan = self.plan(fixture)
            train = tuple(index for index in plan.fit_indices if fixture.rows[index][2] <= 2)
            stop = tuple(index for index in plan.fit_indices if fixture.rows[index][2] == 3)
            early = V.build_early_stop_plan(plan, train_indices=train, stop_indices=stop)
            recipe = V.freeze_recipe(plan, code_sha256="a" * 64, config_sha256="b" * 64,
                preprocessing_sha256="c" * 64, iterations=17, iteration_source="fit_early_stop", early_stop_plan=early)
            self.assertEqual(recipe.early_stop_partition_sha256, early.partition_sha256)
            self.assertFalse(V.phase_grant(plan, "frozen_refit", recipe=recipe).refit_performed)
            forged = V.EarlyStopPlan(plan.fit_indices, plan.inner_indices, plan.partition_sha256)
            with self.assertRaises(V.ValidationError):
                V.freeze_recipe(plan, code_sha256="a" * 64, config_sha256="b" * 64,
                    preprocessing_sha256="c" * 64, iterations=17, iteration_source="fit_early_stop", early_stop_plan=forged)

    def test_h035_contract_split_binding_copy_and_source_identity(self):
        with self.case("H035_numeric_registry_and_split_binding_without_mutating_resolver_contract"):
            fixture = Fixture(self.base / "binding")
            bundle, task = fixture.inputs()
            original = task.to_dict()
            plan = V.build_split_plan(bundle, task, strategy="temporal", time_column="Year_Factor", budget=budget())
            enriched = C.attach_split_plan(task, plan, budget=budget())
            self.assertEqual(task.to_dict(), original)
            self.assertEqual(original["split_policy"]["status"], "NOT_BUILT")
            payload = enriched.to_dict()
            self.assertEqual(payload["split_policy"]["status"], "BUILT")
            self.assertEqual(payload["split_policy"]["partition_sha256"], plan.partition_sha256)
            self.assertEqual(payload["split_policy"]["row_counts"], plan.to_dict()["counts"])
            self.assertEqual(payload["metric"]["adapter_version"], M.ADAPTER_VERSION)
            self.assertNotIn("fit_indices", payload["split_policy"])
            self.assertNotIn("labels", payload["split_policy"])
            self.assertFalse((fixture.root / ".aegml_runs").exists())
            other_fixture = Fixture(self.base / "binding-other", classification=True)
            _, other_task = other_fixture.inputs()
            with self.assertRaises(C.ContractError) as caught:
                C.attach_split_plan(other_task, plan, budget=budget())
            self.assertEqual(caught.exception.code, "split_contract_source_mismatch")

    def actual_public(self, kind, folder):
        with self.case("actual_public_" + kind + "_split_only_no_outer_quality"):
            task = ROOT / "drive-download-20261019T181414Z-1-001" / folder / "task.md"
            if not task.is_file():
                PUBLIC_CHECKS.append({"dataset": kind, "status": "SKIP_SOURCE_ABSENT"})
                self.skipTest("ignored public task sources are absent")
            command = [sys.executable, "-B", str(Path(__file__).resolve()), "--public-child", str(task), "--kind", kind]
            env = {"PATH": str(Path(sys.executable).parent), "PYTHONDONTWRITEBYTECODE": "1",
                   "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
            child = subprocess.run(command, capture_output=True, text=True, timeout=90, env=env)
            CHILDREN.append({"dataset": kind, "exit_code": child.returncode,
                             "scope": "full public read-only split metadata; no outer quality"})
            if child.returncode:
                try:
                    CHILDREN[-1]["safe_child_failure"] = json.loads(child.stdout)
                except (ValueError, UnicodeError):
                    CHILDREN[-1]["safe_child_failure"] = {"status": "INVALID_CHILD_DIAGNOSTIC"}
            self.assertEqual(child.returncode, 0, "public split child failed; stderr retained only if safe")
            self.assertEqual(child.stderr, "")
            self.assertLess(len(child.stdout), 65536)
            data = json.loads(child.stdout)
            self.assertEqual(data["status"], "PASS_PUBLIC_SPLIT_ONLY")
            self.assertTrue(data["source_unchanged"])
            self.assertFalse(data["outer_quality_evaluated"])
            self.assertEqual(data["row_count"], 53308 if kind == "regression" else 87670)
            self.assertEqual(data["row_count"], sum(data["partition_counts"].values()))
            if kind == "regression":
                self.assertGreater(data["train_bytes"], 20 * 1024**2)
                self.assertEqual(data["periods"], {"fit": [1, 2, 3], "inner": [4], "outer": [5]})
            else:
                self.assertEqual(data["class_count"], 10)
                self.assertGreaterEqual(data["minimum_class_support_each_partition"], 1)
                self.assertEqual(data["partition_counts"]["outer"], math.ceil(87670 * .2))
                self.assertEqual(data["partition_counts"]["inner"], math.ceil((87670 - data["partition_counts"]["outer"]) * .2))
            PUBLIC_CHECKS.append(data)

    def test_actual_public_regression_split(self):
        self.actual_public("regression", "Регрессия")

    def test_actual_public_classification_split(self):
        self.actual_public("classification", "Многоклассовая классификация")


def load_modules():
    global M, V, C, I
    import importlib
    sys.path.insert(0, str(ROOT))
    M = importlib.import_module("aegml_metrics")
    V = importlib.import_module("aegml_validation")
    C = importlib.import_module("aegml_contracts")
    I = importlib.import_module("aegml_input")
    for module in (M, V, C, I):
        if Path(module.__file__).resolve().parent != ROOT:
            raise RuntimeError("unexpected_project_import_path")


def public_child(task, kind):
    import resource
    import time
    started = time.monotonic()
    load_modules()
    task = Path(task).resolve()
    source_before = {name: sha(task.parent / name) for name in INPUTS}
    prior_csv = task.parent / "submission.csv"
    csv_before = (sha(prior_csv), prior_csv.stat().st_mtime_ns) if prior_csv.is_file() else None
    allowance = budget()
    bundle = I.discover_inputs(task, allowance)
    task_contract = C.build_task_contract(task, budget=allowance)
    split_start = time.monotonic()
    plan = V.build_split_plan(bundle, task_contract, strategy="temporal" if kind == "regression" else "stratified",
        time_column="Year_Factor" if kind == "regression" else None, budget=allowance)
    split_seconds = time.monotonic() - split_start
    result = {"dataset": kind, "status": "PASS_PUBLIC_SPLIT_ONLY", "row_count": plan.train_rows,
        "partition_counts": plan.to_dict()["counts"], "partition_sha256": plan.partition_sha256,
        "source_sha256": plan.source_sha256, "schema_sha256": plan.schema_sha256,
        "train_bytes": (task.parent / "train.csv").stat().st_size,
        "split_elapsed_seconds": split_seconds, "seed": plan.seed, "strategy": plan.strategy,
        "outer_quality_evaluated": False, "raw_identifiers_or_target_rows_included": False,
        "model_fit_calls": 0, "live_api_calls": 0, "os_boundary_verified": False}
    if kind == "regression":
        result["periods"] = {name: sorted({int(plan.time_values[index]) for index in getattr(plan, name + "_indices")})
                             for name in ("fit", "inner", "outer")}
    else:
        labels = []
        with (task.parent / "train.csv").open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            target = task_contract.to_dict()["target_columns"][0]
            labels = [row[target] for row in reader]
        classes = set(labels)
        result["class_count"] = len(classes)
        result["minimum_class_support_each_partition"] = min(
            Counter(labels[index] for index in part)[label] for part in
            (plan.fit_indices, plan.inner_indices, plan.outer_indices) for label in classes)
    source_after = {name: sha(task.parent / name) for name in INPUTS}
    result["source_unchanged"] = source_before == source_after
    result["source_sha256_before"] = source_before
    csv_after = (sha(prior_csv), prior_csv.stat().st_mtime_ns) if prior_csv.is_file() else None
    if not result["source_unchanged"] or csv_before != csv_after:
        raise RuntimeError("original_source_or_csv_changed")
    result["old_csv_preserved_or_absent"] = True
    result["elapsed_seconds"] = time.monotonic() - started
    result["peak_rss_mib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    result["rss_scope"] = "whole fresh Linux child: imports, contracts, full-source reads, partition checks; ru_maxrss KiB / 1024"
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0


def main():
    if "--public-child" in sys.argv:
        parser = argparse.ArgumentParser()
        parser.add_argument("--public-child", required=True)
        parser.add_argument("--kind", required=True, choices=("regression", "classification"))
        args = parser.parse_args()
        if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
            return 2
        try:
            return public_child(args.public_child, args.kind)
        except Exception as exc:
            print(json.dumps({"status": "FAIL_PUBLIC_SPLIT_CHILD", "error_type": type(exc).__name__,
                              "code": getattr(exc, "code", None)}, allow_nan=False))
            return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if os.path.lexists(args.receipt):
        parser.error("receipt exists; choose a fresh path")
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x", encoding="utf-8") as receipt_stream:
        initial = {name: sha(ROOT / name) for name in SOURCES}
        receipt = {"phase": "H03.3/H03.5", "status": "NOT_RUN", "python": platform.python_version(),
            "scope": "eight numerical metrics, frozen trusted splits, phase/iteration metadata; no fitted model or outer quality",
            "source_sha256": initial, "fit_calls": 0, "live_api_calls": 0,
            "package_installation_executed": False, "official_image_verified": False,
            "full_H05_accepted": False, "refit_executed": False,
            "child_environment_controlled_no_provider_config_read": True}
        if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
            receipt.update(status="BLOCKED_WRONG_CHECK_ENVIRONMENT", test_methods_run=0, behavior_cases_checked=0)
            code = 2
        else:
            load_modules()
            result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
            final = {name: sha(ROOT / name) for name in SOURCES}
            stable = initial == final
            all_public = len(PUBLIC_CHECKS) == 2 and all(item["status"] == "PASS_PUBLIC_SPLIT_ONLY" for item in PUBLIC_CHECKS)
            passed = result.wasSuccessful() and stable
            status = "FAIL_H033_METRICS_VALIDATION"
            if passed:
                status = "PASS_H033_METRICS_VALIDATION_ONLY" if all_public else "PASS_SYNTHETIC_H033_PUBLIC_SKIPPED"
            receipt.update(status=status, test_methods_run=result.testsRun, behavior_cases_checked=len(CASES),
                behavior_cases_passed=sum(item["status"] == "PASS" for item in CASES), cases=CASES,
                public_input_checks=PUBLIC_CHECKS, all_requested_public_sources_verified=all_public,
                metric_oracles=ORACLES, public_child_invocations=CHILDREN,
                source_sha256_after=final, source_unchanged_during_check=stable,
                unittest_failures=[{"test": test.id(), "detail": detail} for test, detail in result.failures],
                unittest_errors=[{"test": test.id(), "detail": detail} for test, detail in result.errors],
                unittest_skips=[{"test": test.id(), "reason": reason} for test, reason in result.skipped])
            code = 0 if passed else 1
        json.dump(receipt, receipt_stream, ensure_ascii=False, indent=2, allow_nan=False)
        receipt_stream.write("\n")
    print(json.dumps({"status": receipt["status"], "test_methods_run": receipt["test_methods_run"],
                      "behavior_cases_checked": receipt["behavior_cases_checked"], "receipt": str(args.receipt)}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
