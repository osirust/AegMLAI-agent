"""Synthetic tiny CPU fits for the fixed H04 adapter; never public training.

The explicit test configuration uses 10 iterations, not the production default
of 300. Real H03 CSV/preprocessing/split contracts feed the tiny adapter tests.
"""

import argparse
from contextlib import contextmanager
from dataclasses import replace
import csv
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import tempfile
from time import monotonic_ns
import unittest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SOURCES = ("aegml_estimators.py", "scripts/check_h04_estimators.py", "aegml_training_data.py",
           "aegml_preprocessing.py", "aegml_validation.py", "aegml_metrics.py",
           "aegml_contracts.py", "aegml_input.py", "aegml_schemas.py", "requirements.txt")
CASES = []
FITS = []
E = P = TD = C = I = V = None


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def budget():
    return C.RunBudget(monotonic_ns(), 120, 1)


def write_csv(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def corrupted_target(batch, **changes):
    """Exercise adapter guards independently of TargetBatch's own constructor."""
    result = copy.copy(batch)
    for name, value in changes.items():
        object.__setattr__(result, name, value)
    return result


class Fixture:
    def __init__(self, root, kind="regression", text=False, numeric_labels=False, binary=False, equal_rows=False):
        self.root, self.kind, self.numeric_labels = root, kind, numeric_labels
        root.mkdir()
        self.task = root / "task.md"
        header = ["record_key", "measurement", "category", "response", "period"]
        self.train = []
        for index in range(5 if equal_rows else 30):
            label = str(index * 1.75 + 2) if kind == "regression" else (
                str((0.25, 1.5, 9.75)[index % 3]) if numeric_labels else
                ("no", "yes")[index % 2] if binary else ("001", "NA", "Ω")[index % 3])
            self.train.append(["train-" + str(index), str(index % 9), "abc"[index % 3], label,
                               str(index + 1 if equal_rows else index // 6 + 1)])
        test = [["001", "", "new-category", "6"], ["NA", "2", "a", "6"], ["Ω", "8", "b", "6"]]
        if equal_rows:
            for index, row in enumerate(test):
                row[1] = str(101 + index)
        if text:
            header.append("words")
            for index, row in enumerate(self.train):
                row.append(("alpha beta", "beta gamma", "gamma delta")[index % 3])
            test = [row + ["unseen alpha"] for row in test]
        test_header = [name for name in header if name != "response"]
        dictionary = [[name, "id" if name == "record_key" else "target" if name == "response" else "feature",
                       "category" if name == "category" else "string" if name == "record_key" else
                       "text" if name == "words" else "numeric"] for name in header]
        write_csv(root / "train.csv", header, self.train)
        write_csv(root / "test.csv", test_header, test)
        write_csv(root / "sample_submission.csv", ["response", "record_key"], [["0", row[0]] for row in test])
        write_csv(root / "data_dictionary.csv", ["feature", "role", "dtype"], dictionary)
        self.task.write_text("Task type: " + kind + "\nTarget: response\nID: record_key\nMetric: "
                             + ("RMSE" if kind == "regression" else "Macro F1")
                             + "\nOutput order: test\n## Data\n- `train.csv`\n- `test.csv`\n"
                               "- `sample_submission.csv`\n- `data_dictionary.csv`\n", encoding="utf-8")
        self.shared = budget()
        contract = C.build_task_contract(self.task, budget=self.shared)
        self.bundle = I.discover_inputs(self.task, self.shared)
        self.plan = V.build_split_plan(self.bundle, contract, strategy="temporal" if kind == "regression" else "stratified",
                                      time_column="period" if kind == "regression" else None, budget=self.shared)
        self.contract = C.attach_split_plan(contract, self.plan, budget=self.shared)
        kinds = {"measurement": "numeric", "category": "categorical", "period": "numeric"}
        if text:
            kinds["words"] = "text"
        schema = P.schema_from_kinds(self.contract, kinds)
        self.fit_view = P.load_train_fit_view(self.bundle, self.contract, self.plan, schema=schema, budget=self.shared)
        self.recipe = P.PreprocessingRecipe(categorical_strategy="onehot" if text else "native")
        self.preprocessor, self.fit_matrix = E.prepare_fit_matrix(self.fit_view, self.recipe, budget=self.shared)
        self.prepared = self.fit_matrix.data
        test_x = P.load_test_features(self.bundle, self.contract, schema=schema, budget=self.shared)
        self.test = self.preprocessor.transform(test_x, budget=self.shared)
        labels = tuple(self.train[index][3] for index in self.plan.fit_indices)
        if numeric_labels or kind == "regression":
            labels = tuple(float(value) for value in labels)
        # Synthetic fixture supplies known fit-side labels directly. The real
        # TargetBatch CSV loader has its own separately owned acceptance tests.
        self.targets = TD.TargetBatch(values=labels, row_indices=self.plan.fit_indices,
                                      source_sha256=self.bundle.source_sha256["train"],
                                      partition_sha256=self.plan.partition_sha256, task_type=kind)
        self.fit_audit = self.preprocessor.audit()

    def fit(self):
        before = {p.name: (sha(p), p.stat().st_mtime_ns) for p in self.root.iterdir() if p.is_file()}
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            fitted = E.fit_estimator(self.fit_matrix, self.targets, task_type=self.kind,
                                     config=E.EstimatorConfig(iterations=10), budget=self.shared,
                                     fit_audit=self.fit_audit)
        finally:
            os.chdir(previous)
        after = {p.name: (sha(p), p.stat().st_mtime_ns) for p in self.root.iterdir() if p.is_file()}
        if before != after or any(p.is_dir() for p in self.root.iterdir()):
            raise RuntimeError("tiny_source_or_directory_mutated")
        report = fitted.audit()
        FITS.append({"task_type": self.kind, "format": self.prepared.format, "iterations": report["tree_count"],
                     "fit_seconds": report["fit_seconds"], "fit_rows": len(self.targets.values),
                     "effective_parameters_sha256": report["effective_parameters_sha256"],
                     "model_sha256": report["model_sha256"], "source_unchanged": True,
                     "synthetic_only": True, "no_public_model_fit": True})
        return fitted


class EstimatorChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aegml-h04-estimator-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

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

    def rejects(self, code, function):
        with self.assertRaises(E.EstimatorError) as caught:
            function()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)

    def test_real_regression_native_fit_predict_and_parameters(self):
        with self.case("tiny_regression_real10trees_native_finite_nonconstant_predictions"):
            fixture = Fixture(self.base / "reg")
            fitted = fixture.fit()
            result = fitted.predict(fixture.test, budget=fixture.shared)
            self.assertIsInstance(result, TD.PredictionBatch)
            self.assertEqual(result.row_indices, fixture.test.row_indices)
            self.assertEqual(len(result.values), 3)
            self.assertTrue(all(type(v) is float and math.isfinite(v) for v in result.values))
            self.assertGreater(len(set(result.values)), 1)
            report = fitted.audit()
            self.assertEqual(report["tree_count"], 10)
            self.assertEqual(report["requested_parameters"]["task_type"], "CPU")
            self.assertEqual(report["requested_parameters"]["counter_calc_method"], "SkipTest")
            self.assertFalse(report["requested_parameters"]["use_best_model"])
            self.assertFalse(report["requested_parameters"]["allow_writing_files"])
            self.assertFalse(report["eval_set_used"])
            self.assertFalse(report["refit_performed"])
            self.assertEqual(E.EstimatorConfig().to_dict()["iterations"], 300)
            self.assertEqual(len(fitted.feature_importance(budget=fixture.shared)["values"]), len(fixture.test.feature_names))

    def test_multiclass_labels_probabilities_and_roworder(self):
        with self.case("tiny_multiclass_restores_001_NA_unicode_and_explicit_probability_order"):
            fixture = Fixture(self.base / "multi", "classification")
            fitted = fixture.fit()
            predictions = fitted.predict(fixture.test, budget=fixture.shared)
            probabilities = fitted.predict_proba(fixture.test, budget=fixture.shared)
            self.assertEqual(set(fitted.class_order), {"001", "NA", "Ω"})
            self.assertTrue(set(predictions.values).issubset(set(fitted.class_order)))
            self.assertEqual(probabilities.class_order, fitted.class_order)
            self.assertEqual(probabilities.row_indices, fixture.test.row_indices)
            self.assertTrue(all(len(row) == 3 and abs(sum(row) - 1) <= 1e-6 for row in probabilities.values))
            for pred, row in zip(predictions.values, probabilities.values):
                self.assertEqual(pred, fitted.class_order[max(range(3), key=lambda i: row[i])])
            reordered = replace(fixture.test, matrix=fixture.test.matrix.iloc[[2, 0, 1]], row_indices=(2, 0, 1))
            reordered_predictions = fitted.predict(reordered, budget=fixture.shared)
            self.assertEqual(reordered_predictions.row_indices, (2, 0, 1))
            self.assertEqual(reordered_predictions.values, tuple(predictions.values[i] for i in (2, 0, 1)))

    def test_fractional_numeric_class_labels_are_restored(self):
        with self.case("tiny_fractional_class_codes_are_encoded_and_restored"):
            fixture = Fixture(self.base / "numeric-label", "classification", numeric_labels=True)
            fitted = fixture.fit()
            predictions = fitted.predict(fixture.test, budget=fixture.shared)
            self.assertEqual(fitted.class_order, (0.25, 1.5, 9.75))
            self.assertTrue(set(predictions.values).issubset(set(fitted.class_order)))

    def test_binary_classifier_loss_and_probability_orientation(self):
        with self.case("tiny_binary_Logloss_and_original_class_order"):
            fixture = Fixture(self.base / "binary", "classification", binary=True)
            fitted = fixture.fit()
            self.assertEqual(fitted.parameters["loss_function"], "Logloss")
            self.assertEqual(fitted.class_order, ("no", "yes"))
            probabilities = fitted.predict_proba(fixture.test, budget=fixture.shared)
            predictions = fitted.predict(fixture.test, budget=fixture.shared)
            self.assertEqual(probabilities.class_order, ("no", "yes"))
            self.assertEqual(len(probabilities.values), 3)
            self.assertTrue(set(predictions.values).issubset({"no", "yes"}))

    def test_sparse_text_route_without_densification(self):
        with self.case("tiny_CSR_TFIDF_real_fit_preserves_sparse_input"):
            from scipy import sparse
            fixture = Fixture(self.base / "text", "classification", text=True)
            before = (fixture.prepared.matrix.nnz, fixture.prepared.matrix.shape)
            fitted = fixture.fit()
            self.assertTrue(sparse.isspmatrix_csr(fixture.prepared.matrix))
            self.assertEqual((fixture.prepared.matrix.nnz, fixture.prepared.matrix.shape), before)
            self.assertEqual(len(fitted.predict(fixture.test, budget=fixture.shared).values), 3)
            self.assertEqual(fitted.categorical_feature_indices, ())

    def test_unknown_category_and_explicit_numeric_nan(self):
        with self.case("native_unknown_category_and_numeric_NaN_supported"):
            import numpy as np
            fixture = Fixture(self.base / "nan")
            fitted = fixture.fit()
            changed = fixture.test.matrix.copy(deep=True)
            changed.iloc[0, 0] = np.nan
            changed.iloc[0, fixture.test.categorical_feature_indices[0]] = "v:another-new-category"
            result = fitted.predict(replace(fixture.test, matrix=changed), budget=fixture.shared)
            self.assertTrue(all(math.isfinite(value) for value in result.values))

    def test_fit_provenance_and_targets_fail_before_backend_fit(self):
        fixture = Fixture(self.base / "guard")
        def fit(targets=fixture.targets, audit=fixture.fit_audit, prepared=fixture.fit_matrix):
            from unittest.mock import patch
            import catboost
            with patch.object(catboost.CatBoostRegressor, "fit", side_effect=AssertionError("unauthorized_backend_fit")):
                return E.fit_estimator(prepared, targets, task_type="regression", config=E.EstimatorConfig(iterations=10),
                                       budget=fixture.shared, fit_audit=audit)
        changes = ({"source_sha256": "f" * 64}, {"partition_sha256": "f" * 64},
                   {"phase": "inner_score_targets"}, {"task_type": "classification"},
                   {"row_indices": tuple(reversed(fixture.targets.row_indices))})
        for index, change in enumerate(changes):
            with self.case("target_provenance_mismatch_" + str(index)):
                self.rejects("fit_provenance_mismatch", lambda: fit(corrupted_target(fixture.targets, **change)))
        for key, value in (("active_split_binding", "NOT_BUILT"), ("source_file_bytes_verified", False),
                           ("trained_statistics_sha256", "f" * 64), ("feature_order_sha256", "f" * 64)):
            with self.case("preprocessing_audit_mismatch_" + key):
                self.rejects("fit_provenance_mismatch", lambda: fit(audit={**fixture.fit_audit, key: value}))
        with self.case("raw_target_vector_cannot_bypass_TargetBatch"):
            self.rejects("trusted_fit_targets_required", lambda: fit(fixture.targets.values))
        for value, code in ((float("nan"), "nonfinite_regression_target"), (True, "invalid_regression_target")):
            with self.case("bad_regression_target_" + code):
                changed = corrupted_target(fixture.targets, values=(value, *fixture.targets.values[1:]))
                self.rejects(code, lambda: fit(changed))

    def test_prepared_schema_and_state_tampering(self):
        fixture = Fixture(self.base / "tamper")
        fitted = fixture.fit()
        for prepared, code in (
                (replace(fixture.test, matrix=fixture.test.matrix.iloc[:, ::-1]), "prepared_feature_order_mismatch"),
                (replace(fixture.test, trained_statistics_sha256="f" * 64), "prediction_preprocessing_mismatch"),
                (replace(fixture.test, row_indices=(0, 0, 2)), "invalid_prepared_row_indices"),
                (replace(fixture.test, categorical_feature_indices=(False,)), "invalid_prepared_schema")):
            with self.case("prepared_tamper_" + code):
                self.rejects(code, lambda: fitted.predict(prepared, budget=fixture.shared))
        with self.case("numeric_infinity_refused_before_CatBoost"):
            bad = fixture.test.matrix.copy(deep=True)
            bad.iloc[0, 0] = float("inf")
            self.rejects("nonfinite_prepared_feature", lambda: fitted.predict(replace(fixture.test, matrix=bad), budget=fixture.shared))
        with self.case("learned_leaf_mutation_changes_model_state_digest"):
            leaves = fitted._model.get_leaf_values()
            fitted._model.set_leaf_values(leaves + 0.25)
            self.rejects("fitted_estimator_state_changed", lambda: fitted.predict(fixture.test, budget=fixture.shared))

    def test_class_mapping_mutation_and_defensive_metadata(self):
        fixture = Fixture(self.base / "class-map", "classification")
        fitted = fixture.fit()
        with self.case("metadata_properties_are_defensive_copies"):
            parameters = fitted.parameters
            parameters["depth"] = 12
            effective = fitted.effective_parameters
            effective["depth"] = 14
            self.assertEqual(fitted.parameters["depth"], 6)
            self.assertEqual(fitted.effective_parameters["depth"], 6)
            fitted.predict(fixture.test, budget=fixture.shared)
        with self.case("class_map_mutation_rejected_before_decoding"):
            fitted.class_order = tuple(reversed(fitted.class_order))
            self.rejects("fitted_estimator_state_changed", lambda: fitted.predict(fixture.test, budget=fixture.shared))

    def test_budget_config_and_sparse_structure_guards(self):
        fixture = Fixture(self.base / "budget", "classification", text=True)
        with self.case("mandatory_shared_budget"):
            self.rejects("budget_required", lambda: E.fit_estimator(fixture.fit_matrix, fixture.targets,
                         task_type=fixture.kind, config=E.EstimatorConfig(iterations=10), budget=None, fit_audit=fixture.fit_audit))
        with self.case("expired_budget_propagates_without_fit"):
            expired = C.RunBudget(0, 1, 0, clock=lambda: 2_000_000_000)
            with self.assertRaises(C.BudgetExpired):
                E.fit_estimator(fixture.fit_matrix, fixture.targets, task_type=fixture.kind,
                                config=E.EstimatorConfig(iterations=10), budget=expired, fit_audit=fixture.fit_audit)
        for change in (dict(iterations=0), dict(iterations=301), dict(threads=9), dict(threads=True), dict(seed=-1)):
            with self.case("bad_config_" + next(iter(change)) + "_" + str(next(iter(change.values())))):
                self.rejects("invalid_estimator_config", lambda: E.EstimatorConfig(**change))
        with self.case("corrupt_CSR_indices_refused_before_native_backend"):
            bad = fixture.prepared.matrix.copy()
            bad.indices[0] = bad.shape[1] + 2
            self.rejects("invalid_prepared_sparse_matrix", lambda: E.fit_estimator(
                replace(fixture.fit_matrix, data=replace(fixture.prepared, matrix=bad)), fixture.targets, task_type=fixture.kind,
                config=E.EstimatorConfig(iterations=10), budget=fixture.shared, fit_audit=fixture.fit_audit))

    def test_pool_construction_expiry_denies_actual_fit(self):
        with self.case("H04-ESTIMATOR-ADMISSION-001_expired_after_Pool_never_starts_fit"):
            from unittest.mock import patch
            import catboost
            fixture = Fixture(self.base / "admission")
            clock = [0]
            shared = C.RunBudget(0, 10, 0, clock=lambda: clock[0])
            original_pool = catboost.Pool

            def pool_then_expire(*args, **kwargs):
                result = original_pool(*args, **kwargs)
                clock[0] = 11_000_000_000
                return result

            with patch.object(catboost, "Pool", pool_then_expire), patch.object(
                    catboost.CatBoostRegressor, "fit", side_effect=AssertionError("unauthorized_backend_fit")) as fit_spy:
                with self.assertRaises(C.BudgetExpired):
                    E.fit_estimator(fixture.fit_matrix, fixture.targets, task_type="regression",
                                    config=E.EstimatorConfig(iterations=10), budget=shared,
                                    fit_audit=fixture.fit_audit)
                self.assertEqual(fit_spy.call_count, 0)

    def test_fit_matrix_binding_equal_fit_test_size(self):
        from unittest.mock import patch
        import catboost
        fixture = Fixture(self.base / "matrix-equal", equal_rows=True)
        self.assertEqual(fixture.prepared.row_indices, (0, 1, 2))
        self.assertEqual(fixture.test.row_indices, fixture.prepared.row_indices)
        self.assertFalse(fixture.test.matrix.equals(fixture.prepared.matrix))
        with self.case("H04-FIT-MATRIX-BIND-001_correct_equal_N_fit_real_tiny_positive"):
            fitted = fixture.fit()
            self.assertEqual(fitted.audit()["tree_count"], 10)
            self.assertEqual(fitted.audit()["fit_binding"]["prepared_matrix_content_sha256"],
                             fixture.fit_matrix.content_sha256)
        with patch.object(catboost, "Pool", side_effect=AssertionError("unauthorized_pool")) as pool_spy, patch.object(
                catboost.CatBoostRegressor, "fit", side_effect=AssertionError("unauthorized_fit")) as fit_spy:
            for name, candidate in (("raw_test_equal_N", fixture.test), ("raw_fit", fixture.prepared),
                    ("missing_factory_token", replace(fixture.fit_matrix, _factory_token=None))):
                with self.case("H04-FIT-MATRIX-BIND-001_" + name + "_refused_before_Pool"):
                    self.rejects("fit_matrix_envelope_required", lambda: E.fit_estimator(candidate, fixture.targets,
                        task_type=fixture.kind, config=E.EstimatorConfig(iterations=10),
                        budget=fixture.shared, fit_audit=fixture.fit_audit))
            with self.case("H04-FIT-MATRIX-BIND-001_swapped_test_data_refused_before_Pool"):
                self.rejects("fit_matrix_content_changed", lambda: E.fit_estimator(
                    replace(fixture.fit_matrix, data=fixture.test), fixture.targets, task_type=fixture.kind,
                    config=E.EstimatorConfig(iterations=10), budget=fixture.shared, fit_audit=fixture.fit_audit))
            with self.case("H04-FIT-MATRIX-BIND-001_changed_category_refused_before_Pool"):
                changed = fixture.prepared.matrix.copy(deep=True)
                changed.iloc[0, fixture.prepared.categorical_feature_indices[0]] = "v:changed-category"
                candidate = replace(fixture.fit_matrix, data=replace(fixture.prepared, matrix=changed))
                self.rejects("fit_matrix_content_changed", lambda: E.fit_estimator(candidate, fixture.targets,
                    task_type=fixture.kind, config=E.EstimatorConfig(iterations=10),
                    budget=fixture.shared, fit_audit=fixture.fit_audit))
            with self.case("H04-FIT-MATRIX-BIND-001_wrong_row_space_refused_before_Pool"):
                self.rejects("fit_matrix_binding_mismatch", lambda: E.fit_estimator(
                    replace(fixture.fit_matrix, train_row_space="test_source_0_based"), fixture.targets,
                    task_type=fixture.kind, config=E.EstimatorConfig(iterations=10),
                    budget=fixture.shared, fit_audit=fixture.fit_audit))
            with self.case("H04-FIT-MATRIX-BIND-001_in_place_numeric_mutation_refused_before_Pool"):
                fixture.fit_matrix.data.matrix.iloc[0, 0] += 100
                self.rejects("fit_matrix_content_changed", lambda: E.fit_estimator(fixture.fit_matrix, fixture.targets,
                    task_type=fixture.kind, config=E.EstimatorConfig(iterations=10),
                    budget=fixture.shared, fit_audit=fixture.fit_audit))
            self.assertEqual(pool_spy.call_count, 0)
            self.assertEqual(fit_spy.call_count, 0)

    def test_fit_matrix_binding_sparse_mutation_and_factory_guards(self):
        from unittest.mock import patch
        import catboost
        from scipy import sparse
        fixture = Fixture(self.base / "matrix-csr", "classification", text=True)
        with self.case("H04-FIT-MATRIX-BIND-001_CSR_witness_without_toarray"):
            with patch.object(sparse.csr_matrix, "toarray", side_effect=AssertionError("densification_forbidden")):
                _, envelope = E.prepare_fit_matrix(fixture.fit_view, fixture.recipe, budget=fixture.shared)
                self.assertEqual(envelope.content_sha256, fixture.fit_matrix.content_sha256)
        with self.case("H04-FIT-MATRIX-BIND-001_mutated_CSR_data_refused_before_Pool"):
            fixture.fit_matrix.data.matrix.data[0] += 0.25
            with patch.object(catboost, "Pool", side_effect=AssertionError("unauthorized_pool")) as pool_spy:
                self.rejects("fit_matrix_content_changed", lambda: E.fit_estimator(fixture.fit_matrix, fixture.targets,
                    task_type=fixture.kind, config=E.EstimatorConfig(iterations=10),
                    budget=fixture.shared, fit_audit=fixture.fit_audit))
                self.assertEqual(pool_spy.call_count, 0)
        for name, view in (("raw_test_frame", fixture.test.matrix),
                ("caller_asserted_view", replace(fixture.fit_view, source_binding="caller_asserted_dataframe")),
                ("unbound_split", replace(fixture.fit_view, active_split_binding="NOT_BUILT"))):
            with self.case("H04-FIT-MATRIX-BIND-001_factory_rejects_" + name):
                self.rejects("source_bound_fit_view_required",
                             lambda: E.prepare_fit_matrix(view, fixture.recipe, budget=fixture.shared))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
        parser.error("requires Linux Python3.12")
    if args.receipt.exists():
        parser.error("receipt_exists")
    def offline(event, _):
        if event in {"socket.connect", "socket.getaddrinfo"}:
            raise RuntimeError("offline_check_network_forbidden")
    sys.addaudithook(offline)
    global E, P, TD, C, I, V
    import aegml_estimators as E
    import aegml_preprocessing as P
    import aegml_training_data as TD
    import aegml_contracts as C
    import aegml_input as I
    import aegml_validation as V
    import catboost
    before = {name: sha(ROOT / name) for name in SOURCES}
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EstimatorChecks))
    after = {name: sha(ROOT / name) for name in SOURCES}
    import resource
    receipt = {"status": "PASS_H04_ESTIMATOR_TINY_ONLY" if result.wasSuccessful() and before == after else "FAIL",
               "python": platform.python_version(), "catboost": catboost.__version__,
               "test_methods_run": result.testsRun, "cases_checked": len(CASES),
               "cases_passed": sum(record["status"] == "PASS" for record in CASES), "cases": CASES,
               "failures": [{"test": test.id(), "detail": error} for test, error in result.failures],
               "errors": [{"test": test.id(), "detail": error} for test, error in result.errors],
               "tiny_fits": FITS, "source_sha256": before, "source_sha256_after": after,
               "source_unchanged": before == after, "API_calls": 0, "public_dataset_model_fits": 0,
               "tiny_iterations": 10, "production_default_iterations": 300,
               "model_quality_claimed": False, "refit_executed": False, "H05_boundary_verified": False,
               "peak_RSS_MiB_process": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({key: receipt[key] for key in ("status", "test_methods_run", "cases_checked", "cases_passed", "source_unchanged")}))
    return 0 if receipt["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
