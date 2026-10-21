"""H03.2 synthetic guards and optional read-only public preprocessing checks.

Run in the existing Python 3.12 ML venv. Fits preprocessing only: no estimator,
LLM, network, package installation, task commands, or prediction CSV writes.
"""

import argparse
from contextlib import contextmanager
import csv
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import sys
import tempfile
from time import monotonic_ns
from time import perf_counter
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
CASES = []
PUBLIC = []
SOURCE_SHA = "a" * 64


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def value_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Plan:
    fit_indices: tuple
    inner_indices: tuple
    outer_indices: tuple
    train_rows: int
    train_sha256: str = SOURCE_SHA
    source_items: tuple = ()

    @property
    def source_sha256(self):
        return dict(self.source_items)

    @property
    def partition_sha256(self):
        return value_sha({"source": self.train_sha256, "rows": self.train_rows,
                          "fit": self.fit_indices, "inner": self.inner_indices,
                          "outer": self.outer_indices, "scope": "H032_explicit_fixture_only"})


class Checks(unittest.TestCase):
    def setUp(self):
        self.records = []

    def tearDown(self):
        # unittest determines method outcome; individual cases are only appended
        # after their independent assertions have returned successfully.
        CASES.extend(self.records)

    def passed(self, name):
        self.records.append({"case": name, "status": "PASS", "method": self.id()})

    def make_view(self, data, schema=None, plan=None):
        frame = pd.DataFrame(data)
        schema = schema or P.FeatureSchema(tuple(frame.columns), numeric_columns=tuple(frame.columns),
                                          forbidden_columns=("target", "id"))
        plan = plan or Plan(tuple(range(len(frame) - 2)), (len(frame) - 2,), (len(frame) - 1,), len(frame))
        view = P.make_train_fit_view(frame, schema=schema, split_plan=plan,
                                     source_sha256=plan.train_sha256)
        return frame, view

    @contextmanager
    def loader_fixture(self):
        from aegml_contracts import RunBudget, attach_split_plan, build_task_contract
        from aegml_input import discover_inputs
        from aegml_validation import SplitPlan

        with tempfile.TemporaryDirectory(prefix="aegml-h032-loader-") as temporary:
            directory = Path(temporary)
            header = ["id", "y", "x", "cat", "words"]
            train_rows = [["fit-A", "10", "1", "NA", "alpha text"],
                          ["fit-B", "20", "3", "null", "beta text"],
                          ["inner-A", "30", "100", "hidden-A", "innerword"],
                          ["inner-B", "40", "200", "hidden-B", "innerword"],
                          ["outer-A", "50", "300", "hidden-C", "outerword"],
                          ["outer-B", "60", "400", "hidden-D", "outerword"]]
            test_rows = [["test-A", "", "", "testword"], ["test-B", "2", "new", "testword"]]

            def save():
                for filename, columns, rows in (
                    ("train.csv", header, train_rows),
                    ("test.csv", ["id", "x", "cat", "words"], test_rows),
                    ("sample_submission.csv", ["id", "y"], [["test-B", "0"], ["test-A", "0"]]),
                    ("data_dictionary.csv", ["feature", "role", "dtype"],
                     [["id", "id", "string"], ["y", "target", "numeric"],
                      ["x", "feature", "numeric"], ["cat", "feature", "category"],
                      ["words", "feature", "text"]]),
                ):
                    with (directory / filename).open("w", encoding="utf-8", newline="") as stream:
                        writer = csv.writer(stream)
                        writer.writerow(columns)
                        writer.writerows(rows)
                (directory / "task.md").write_text(
                    "Task type: regression\nTarget: y\nID: id\nMetric: RMSE\nOutput order: test\n"
                    "## Data\n- `train.csv`\n- `test.csv`\n- `data_dictionary.csv`\n- `sample_submission.csv`\n",
                    encoding="utf-8")

            def prepare(*, attach=True):
                shared = RunBudget(monotonic_ns(), 180, 1)
                contract = build_task_contract(directory / "task.md", budget=shared)
                bundle = discover_inputs(directory / "task.md", shared)
                schema = P.schema_from_kinds(contract, {"x": "numeric", "cat": "categorical", "words": "text"})
                plan = SplitPlan((0, 1), (2, 3), (4, 5), 6, bundle.source_sha256["train"],
                                 "h032_loader_fixture", schema_sha256=schema.schema_sha256,
                                 source_items=tuple(bundle.source_sha256.items()))
                if attach:
                    contract = attach_split_plan(contract, plan, budget=shared)
                return bundle, contract, plan, schema, shared

            save()
            yield directory, train_rows, save, prepare

    def test_fit_only_median_and_protected_poison(self):
        frame, view = self.make_view({"x": ["1", "3", "999999", "-999999"]})
        fitted, result = P.fit_transform(view)
        self.assertEqual(fitted.statistics()["numeric_medians"]["x"], 2.0)
        self.assertEqual(result.matrix.shape, (2, 2))
        frame.loc[2:, "x"] = ["NaN", "not-a-number"]
        plan = Plan((0, 1), (2,), (3,), 4, "b" * 64)
        second = P.make_train_fit_view(frame, schema=view.schema, split_plan=plan,
                                       source_sha256=plan.train_sha256)
        other, _ = P.fit_transform(second)
        self.assertEqual(fitted.statistics_sha256, other.statistics_sha256)
        self.assertNotEqual(fitted.audit()["source_sha256"], other.audit()["source_sha256"])
        self.passed("H032_fit_only_protected_poison")

    def test_numeric_missing_invalid_nonfinite_overflow(self):
        values = ["", "NA", "NaN", "Inf", "1e9999", " ", "2", "4", "900", "901"]
        _, view = self.make_view({"x": values})
        fitted, result = P.fit_transform(view)
        self.assertEqual(fitted.statistics()["numeric_medians"]["x"], 3.0)
        counts = fitted.fit_diagnostics["numeric"]["x"]
        self.assertEqual(counts, {"empty": 1, "invalid": 2, "nonfinite": 2, "overflow": 1})
        self.assertTrue(np.isfinite(result.matrix.data).all())
        self.assertEqual(result.matrix.toarray()[:6, 1].tolist(), [1.0] * 6)
        self.passed("H032_numeric_reason_counts")
        _, empty = self.make_view({"x": ["", "NA", "test", "test"]})
        all_missing, transformed = P.fit_transform(empty)
        self.assertEqual(all_missing.statistics()["numeric_medians"]["x"], 0.0)
        self.assertEqual(transformed.matrix.shape, (2, 2))
        self.passed("H032_all_missing_numeric_retained")

    def test_large_finite_median_stays_finite(self):
        for left, right, expected in [("1e308", "1e308", 1e308), ("-1e308", "1e308", 0.0),
                                       ("5e-324", "5e-324", 5e-324)]:
            _, view = self.make_view({"x": [left, right, "0", "0"]})
            fitted, _ = P.fit_transform(view)
            self.assertEqual(fitted.statistics()["numeric_medians"]["x"], expected)
        self.passed("H032_large_finite_median")

    def test_categories_literal_tokens_and_unknown_rows(self):
        schema = P.FeatureSchema(("cat",), categorical_columns=("cat",), forbidden_columns=("target", "id"))
        frame, view = self.make_view({"cat": ["NA", "null", " ", "m:", "", "new"]}, schema)
        for strategy in ("onehot", "native"):
            fitted, _ = P.fit_transform(view, P.PreprocessingRecipe(categorical_strategy=strategy))
            categories = fitted.statistics()["categories"]["cat"]
            self.assertEqual(set(categories), {"m:", "v:NA", "v:null", "v: ", "v:m:"})
            before = fitted.statistics_sha256
            result = fitted.transform(frame.iloc[4:])
            self.assertEqual(result.matrix.shape[0], 2)
            self.assertEqual(result.diagnostics["categorical_unknown"]["cat"], 1)
            self.assertEqual(fitted.statistics_sha256, before)
            if strategy == "native":
                self.assertEqual(result.matrix["c0"].tolist(), ["m:", "u:"])
                self.assertEqual(result.categorical_feature_indices, (0,))
            else:
                self.assertEqual(result.matrix.toarray()[1].sum(), 0.0)
            self.passed("H032_lexical_categories_" + strategy)

    def test_multiple_text_columns_fit_only_and_injection_is_data(self):
        schema = P.FeatureSchema(("n", "cat", "t1", "t2"), numeric_columns=("n",),
                                 categorical_columns=("cat",), text_columns=("t1", "t2"),
                                 forbidden_columns=("target", "id"))
        frame, view = self.make_view({"n": ["1", "3", "999", "0"], "cat": ["a", "b", "c", "d"],
                                     "t1": ["alpha beta", "beta gamma", "VALIDATIONTOKEN", "outerword"],
                                     "t2": ["plain text", "__import__('os').system('no_execution')", "other", "unknown"]}, schema)
        fitted, result = P.fit_transform(view)
        before = fitted.statistics_sha256
        vocabulary = {term for term, _ in fitted.statistics()["text"]["t1"]["vocabulary"]}
        self.assertEqual(vocabulary, {"alpha", "beta", "gamma"})
        self.assertNotIn("validationtoken", vocabulary)
        later = fitted.transform(frame.iloc[2:])
        self.assertEqual(later.matrix.shape[0], 2)
        self.assertEqual(later.matrix.shape[1], result.matrix.shape[1])
        self.assertEqual(before, fitted.statistics_sha256)
        self.assertTrue(sparse.isspmatrix_csr(later.matrix))
        self.passed("H032_multi_text_no_validation_vocabulary_or_execution")

    def test_empty_text_and_native_text_rejection(self):
        schema = P.FeatureSchema(("text",), text_columns=("text",), forbidden_columns=("target", "id"))
        frame, view = self.make_view({"text": ["", "a b", "newword", "outer"]}, schema)
        fitted, result = P.fit_transform(view)
        self.assertTrue(fitted.statistics()["text"]["text"]["empty_vocabulary"])
        self.assertEqual(result.matrix.shape, (2, 1))
        self.assertEqual(fitted.transform(frame.iloc[2:]).matrix.nnz, 0)
        self.passed("H032_empty_text_fixed_zero_column")
        with self.assertRaisesRegex(P.PreprocessingError, "native_text_recipe_unsupported"):
            P.fit_transform(view, P.PreprocessingRecipe(categorical_strategy="native"))
        self.passed("H032_native_text_explicit_unsupported")

    def test_recipe_limits_fail_closed(self):
        schema = P.FeatureSchema(("cat",), categorical_columns=("cat",), forbidden_columns=("target", "id"))
        _, view = self.make_view({"cat": ["a", "b", "c", "d"]}, schema)
        with self.assertRaisesRegex(P.PreprocessingError, "preprocessing_category_limit"):
            P.fit_transform(view, P.PreprocessingRecipe(max_categories_per_column=2))
        self.passed("H032_bounded_categories")
        schema = P.FeatureSchema(("t",), text_columns=("t",), forbidden_columns=("target", "id"))
        _, view = self.make_view({"t": ["alpha beta gamma", "delta epsilon", "x", "y"]}, schema)
        with self.assertRaisesRegex(P.PreprocessingError, "preprocessing_text_vocabulary_limit"):
            P.fit_transform(view, P.PreprocessingRecipe(text_max_features_per_column=1, text_candidate_terms_per_column=2))
        self.passed("H032_bounded_temporary_text_vocabulary")
        _, view = self.make_view({"x": ["1", "2", "3", "4"]})
        with self.assertRaises(P.PreprocessingError):
            P.fit_transform(view, P.PreprocessingRecipe(max_output_nnz=1))
        self.passed("H032_bounded_sparse_output")
        with self.assertRaisesRegex(P.PreprocessingError, "unknown_preprocessing_recipe"):
            P.PreprocessingRecipe(categorical_strategy="execute_this_code")
        self.passed("H032_known_recipes_only")

    def test_scope_rejection_and_no_full_train_default(self):
        schema = P.FeatureSchema(("x",), numeric_columns=("x",), forbidden_columns=("target", "id"))
        frame = pd.DataFrame({"x": ["1", "2", "3", "4"]})
        invalid = [Plan((0, 1, 2, 3), (), (), 4), Plan((0, 1), (1,), (3,), 4),
                   Plan((False, 1), (2,), (3,), 4), Plan((1, 0), (2,), (3,), 4),
                   Plan((0,), (2,), (3,), 4)]
        for plan in invalid:
            with self.assertRaises(P.PreprocessingError):
                P.make_train_fit_view(frame, schema=schema, split_plan=plan, source_sha256=SOURCE_SHA)
        with self.assertRaisesRegex(P.PreprocessingError, "fit_source_identity_mismatch"):
            P.make_train_fit_view(frame, schema=schema, split_plan=Plan((0, 1), (2,), (3,), 4),
                                  source_sha256="f" * 64)
        with self.assertRaisesRegex(P.PreprocessingError, "trusted_fit_view_required"):
            P.fit_transform(frame)
        self.passed("H032_scope_and_source_identity_required")

    def test_columns_index_and_zero_row_guards(self):
        frame, view = self.make_view({"left": ["1", "2", "3", "4"], "right": ["5", "6", "7", "8"]})
        fitted, _ = P.fit_transform(view)
        expected = fitted.transform(frame).matrix.toarray()
        np.testing.assert_array_equal(fitted.transform(frame[["right", "left"]]).matrix.toarray(), expected)
        self.passed("H032_named_column_reorder_preserves_features")
        for invalid in (frame.assign(id="001"), frame.assign(target="1"), frame[["left"]],
                        pd.DataFrame([["1", "2"]], columns=["left", "left"]), frame.iloc[:0]):
            with self.assertRaises(P.PreprocessingError):
                fitted.transform(invalid)
        invalid = frame.copy()
        invalid.index = [10, 11, 12, 13]
        with self.assertRaisesRegex(P.PreprocessingError, "noncanonical_source_row_index"):
            P.make_train_fit_view(invalid, schema=view.schema, split_plan=Plan((0, 1), (2,), (3,), 4),
                                  source_sha256=SOURCE_SHA)
        self.passed("H032_columns_ids_empty_and_row_index_guards")

    def test_copy_and_statistics_immutability(self):
        frame, view = self.make_view({"x": ["1", "3", "5", "7"]})
        frame.loc[0, "x"] = "999"
        copy = view.frame
        copy.loc[0, "x"] = "888"
        fitted, _ = P.fit_transform(view)
        external = fitted.statistics()
        external["numeric_medians"]["x"] = 999
        self.assertEqual(fitted.statistics()["numeric_medians"]["x"], 2.0)
        before = fitted.statistics_sha256
        fitted.transform(frame)
        self.assertEqual(before, fitted.statistics_sha256)
        self.assertEqual(json.loads(json.dumps(fitted.audit(), allow_nan=False))["estimator_fitted"], False)
        self.passed("H032_detached_fit_view_and_statistics")

    def test_numeric_class_and_explicit_roles(self):
        payload = {"feature_columns": ["code"], "target_columns": ["label"], "id_columns": ["id"],
                   "task_type": "classification"}
        schema = P.schema_from_kinds(payload, {"code": "categorical"})
        frame, view = self.make_view({"code": ["001", "002", "003", "004"]}, schema)
        fitted, _ = P.fit_transform(view)
        self.assertEqual(fitted.statistics()["numeric_medians"], {})
        self.assertIn("v:001", fitted.statistics()["categories"]["code"])
        with self.assertRaises(P.PreprocessingError):
            P.schema_from_kinds(payload, {"code": "numeric", "label": "numeric"})
        with self.assertRaises(P.PreprocessingError):
            P.FeatureSchema(("label",), numeric_columns=("label",), forbidden_columns=("label", "id"))
        self.passed("H032_explicit_roles_no_cardinality_target_inference")

    def test_common_budget_and_lexical_policy(self):
        class Expired:
            def require(self):
                raise RuntimeError("synthetic_budget_expired")
        _, view = self.make_view({"x": ["1", "3", "5", "7"]})
        with self.assertRaisesRegex(RuntimeError, "synthetic_budget_expired"):
            P.fit_transform(view, budget=Expired())
        with self.assertRaises(P.PreprocessingError):
            P.FeatureSchema(("x",), numeric_columns=("x",), missing_policy="pandas_default_na")
        fitted, _ = P.fit_transform(view)
        with self.assertRaisesRegex(P.PreprocessingError, "non_lexical_feature_value"):
            fitted.transform(pd.DataFrame({"x": [None]}))
        self.passed("H032_common_budget_and_explicit_lexical_policy")

    def test_authenticated_loader_and_test_feature_projection(self):
        with self.loader_fixture() as (_, _, _, prepare):
            bundle, contract, plan, schema, shared = prepare()
            view = P.load_train_fit_view(bundle, contract, plan, schema=schema, budget=shared)
            self.assertEqual(view.row_indices, (0, 1))
            self.assertEqual(tuple(view.frame.columns), ("x", "cat", "words"))
            self.assertEqual(tuple(view.frame.index), (0, 1))
            self.assertEqual(view.source_binding, "verified_csv_bytes_and_explicit_partition")
            fitted, _ = P.fit_transform(view, budget=shared)
            self.assertTrue(fitted.audit()["source_file_bytes_verified"])
            self.assertFalse(fitted.audit()["source_identity_asserted_by_trusted_loader"])
            test = P.load_test_features(bundle, contract, schema=schema, budget=shared)
            self.assertEqual(tuple(test.columns), ("x", "cat", "words"))
            self.assertEqual(test["cat"].tolist(), ["", "new"])
            self.assertEqual(tuple(test.index), (0, 1))
            self.assertEqual(fitted.transform(test, budget=shared).matrix.shape[0], 2)
            self.passed("H032_loader_authenticates_bytes_and_projects_features_only")
            outside = pd.DataFrame({"x": ["999"]})
            with self.assertRaisesRegex(P.PreprocessingError, "invalid_source_binding"):
                P.load_train_fit_view(outside, contract, plan, schema=schema, budget=shared)
            self.passed("H032_outside_dataframe_cannot_claim_csv_loader")

    def test_loader_protected_poison_fit_witness_invariant(self):
        with self.loader_fixture() as (_, train_rows, save, prepare):
            bundle, contract, plan, schema, shared = prepare()
            view = P.load_train_fit_view(bundle, contract, plan, schema=schema, budget=shared)
            fitted, _ = P.fit_transform(view, budget=shared)
            for index in range(2, 6):
                train_rows[index][1:] = ["999999", "NaN", "protected-new-category", "PROTECTEDWORD"]
            save()
            other_bundle, other_contract, other_plan, other_schema, other_budget = prepare()
            other = P.load_train_fit_view(other_bundle, other_contract, other_plan,
                                         schema=other_schema, budget=other_budget)
            other_fitted, _ = P.fit_transform(other, budget=other_budget)
            self.assertNotEqual(view.source_sha256, other.source_sha256)
            self.assertEqual(view.fit_values_sha256, other.fit_values_sha256)
            self.assertEqual(fitted.statistics_sha256, other_fitted.statistics_sha256)
            self.assertNotIn("v:protected-new-category", other_fitted.statistics()["categories"]["cat"])
            terms = dict(other_fitted.statistics()["text"]["words"]["vocabulary"])
            self.assertNotIn("protectedword", terms)
            self.passed("H032_csv_loader_protected_poison_cannot_change_fit_values_or_state")

    def test_loader_identity_limits_and_shared_budget_guards(self):
        with self.loader_fixture() as (directory, _, _, prepare):
            bundle, contract, plan, schema, shared = prepare()
            changed = directory / "train.csv"
            info = changed.stat()
            body = changed.read_bytes()
            changed.write_bytes(body.replace(b"fit-A", b"fit-Z", 1))
            os.utime(changed, ns=(info.st_atime_ns, info.st_mtime_ns))
            with self.assertRaisesRegex(P.PreprocessingError, "source_bytes_changed"):
                P.load_train_fit_view(bundle, contract, plan, schema=schema, budget=shared)
            self.passed("H032_loader_detects_same_size_same_mtime_content_change")
        with self.loader_fixture() as (_, _, _, prepare):
            bundle, contract, plan, schema, shared = prepare()
            for limits, reason in [(P.FeatureLoadLimits(max_selected_cells=5), "feature_load_cell_limit"),
                                   (P.FeatureLoadLimits(max_retained_chars=1), "feature_load_character_limit")]:
                with self.assertRaisesRegex(P.PreprocessingError, reason):
                    P.load_train_fit_view(bundle, contract, plan, schema=schema, budget=shared, limits=limits)
            self.passed("H032_loader_retention_chars_and_cells_bounded")
            with self.assertRaisesRegex(P.PreprocessingError, "budget_required"):
                P.load_test_features(bundle, contract, schema=schema, budget=None)
            with self.assertRaisesRegex(P.PreprocessingError, "trusted_fit_partition_required"):
                P.load_train_fit_view(bundle, contract, None, schema=schema, budget=shared)
            self.passed("H032_loader_budget_and_fit_partition_mandatory")
            wrong_sources = dict(plan.source_items)
            wrong_sources["test"] = "b" * 64
            mismatch = replace(plan, source_items=tuple(sorted(wrong_sources.items())))
            with self.assertRaisesRegex(P.PreprocessingError, "split_source_identity_mismatch"):
                P.load_train_fit_view(bundle, contract, mismatch, schema=schema, budget=shared)
            self.passed("H032_loader_binds_all_split_source_identities")

    def test_review_partition_bind_rejects_other_valid_plan(self):
        with self.loader_fixture() as (_, _, _, prepare):
            bundle, active, plan_a, schema, shared = prepare()
            plan_b = replace(plan_a, fit_indices=plan_a.outer_indices,
                             outer_indices=plan_a.fit_indices)
            self.assertEqual(plan_a.source_sha256, plan_b.source_sha256)
            self.assertNotEqual(plan_a.partition_sha256, plan_b.partition_sha256)
            # An incompatible active plan must fail before projecting any CSV
            # record into a retained fit frame, even though all bytes match.
            with patch("aegml_input._csv_reader", side_effect=AssertionError("projection_was_started")):
                with self.assertRaisesRegex(P.PreprocessingError, "active_split_policy_mismatch"):
                    P.load_train_fit_view(bundle, active, plan_b, schema=schema, budget=shared)
            self.passed("H032-PARTITION-BIND-001_active_A_load_B_rejected_before_projection")
            view = P.load_train_fit_view(bundle, active, plan_a, schema=schema, budget=shared)
            fitted, _ = P.fit_transform(view, budget=shared)
            self.assertEqual(view.row_indices, (0, 1))
            self.assertEqual(fitted.statistics()["numeric_medians"]["x"], 2.0)
            self.assertTrue(fitted.audit()["active_split_policy_verified"])
            self.assertEqual(fitted.audit()["active_split_binding"], "BUILT_MATCHED")
            self.passed("H032-PARTITION-BIND-001_active_A_load_A_positive_median")

    def test_review_partition_bind_checks_full_active_metadata(self):
        from aegml_contracts import TaskContract

        with self.loader_fixture() as (_, _, _, prepare):
            bundle, active, plan, schema, shared = prepare()
            mutations = {
                "seed": plan.seed + 1,
                "policy_id": "different_policy_with_same_hash",
                "schema_sha256": "b" * 64,
                "strategy": "stratified",
                "row_counts": {"fit": 1, "inner": 3, "outer": 2},
            }
            for field_name, value in mutations.items():
                payload = active.to_dict()
                payload["split_policy"][field_name] = value
                self.assertEqual(payload["split_policy"]["partition_sha256"], plan.partition_sha256)
                contradictory = TaskContract(payload, active.alignment)
                with self.assertRaisesRegex(P.PreprocessingError, "active_split_policy_mismatch"):
                    P.load_train_fit_view(bundle, contradictory, plan, schema=schema, budget=shared)
                self.passed("H032-PARTITION-BIND-001_metadata_mismatch_" + field_name)

    def test_review_partition_bind_not_built_is_explicitly_unavailable(self):
        with self.loader_fixture() as (_, train_rows, _, prepare):
            bundle, unbuilt, plan, schema, shared = prepare(attach=False)
            with self.assertRaisesRegex(P.PreprocessingError, "active_split_policy_required"):
                P.load_train_fit_view(bundle, unbuilt, plan, schema=schema, budget=shared)
            self.passed("H032-PARTITION-BIND-001_NOT_BUILT_source_loader_rejected")
            # Test-only X loading has no fit partition grant and remains usable.
            test = P.load_test_features(bundle, unbuilt, schema=schema, budget=shared)
            self.assertEqual(len(test), 2)
            # The separate low-level API never claims authenticated active-plan
            # binding. This is explicit use, never an automatic loader fallback.
            frame = pd.DataFrame([row[2:] for row in train_rows], columns=schema.feature_columns)
            asserted = P.make_train_fit_view(frame, schema=schema, split_plan=plan,
                                             source_sha256=plan.train_sha256, budget=shared)
            fitted, _ = P.fit_transform(asserted, budget=shared)
            self.assertFalse(fitted.audit()["active_split_policy_verified"])
            self.assertFalse(fitted.audit()["source_file_bytes_verified"])
            self.assertEqual(fitted.audit()["active_split_binding"], "NOT_BOUND_TRUSTED_DATAFRAME")
            self.passed("H032-PARTITION-BIND-001_low_level_assertion_and_test_X_stay_explicit")


def actual_public_checks():
    from aegml_contracts import RunBudget, attach_split_plan, build_task_contract
    from aegml_input import discover_inputs
    from aegml_validation import build_split_plan

    source_root = ROOT / "drive-download-20261019T181414Z-1-001"
    source_files = sorted(path for path in source_root.rglob("*") if path.is_file())
    if not source_root.is_dir():
        raise RuntimeError("public_sources_absent")
    before = {str(path.relative_to(source_root)): sha(path) for path in source_files}
    for folder in ("Регрессия", "Многоклассовая классификация"):
        started = perf_counter()
        directory = source_root / folder
        shared = RunBudget(monotonic_ns(), 180, 1)
        contract = build_task_contract(directory / "task.md", budget=shared)
        bundle = discover_inputs(directory / "task.md", shared)
        dictionary = bundle.dictionary_rows
        feature_rows = [row for row in dictionary if row["role"] == "feature"]
        kinds = {row["feature"]: ({"numeric": "numeric", "binary": "numeric",
                                   "category": "categorical", "text": "text"}[row["dtype"]])
                 for row in feature_rows}
        schema = P.schema_from_kinds(contract, kinds)
        columns = schema.feature_columns
        if folder == "Регрессия":
            plan = build_split_plan(bundle, contract, strategy="temporal", time_column="Year_Factor",
                                    budget=shared, seed=42)
        else:
            plan = build_split_plan(bundle, contract, strategy="stratified", budget=shared, seed=42)
        fit, inner, outer = plan.fit_indices, plan.inner_indices, plan.outer_indices
        contract = attach_split_plan(contract, plan, budget=shared)
        view = P.load_train_fit_view(bundle, contract, plan, schema=schema, budget=shared)
        test = P.load_test_features(bundle, contract, schema=schema, budget=shared)
        fitted, prepared = P.fit_transform(view, budget=shared)
        witness = fitted.statistics_sha256
        test_result = fitted.transform(test, budget=shared)
        if (prepared.matrix.shape[0] != len(fit) or view.row_indices != plan.fit_indices
                or test_result.matrix.shape[0] != len(test) or witness != fitted.statistics_sha256
                or view.source_binding != "verified_csv_bytes_and_explicit_partition"
                or view.active_split_binding != "BUILT_MATCHED"):
            raise RuntimeError("actual_preprocessing_shape_or_state_mismatch")
        PUBLIC.append({
            "dataset": folder, "status": "PASS", "scope": "source_bound_preprocessing_with_H033_split",
            "split_strategy": plan.strategy, "split_policy_id": plan.policy_id,
            "source_bytes": (directory / "train.csv").stat().st_size,
            "source_rows": plan.train_rows, "feature_columns": len(columns),
            "fit_rows": len(fit), "inner_rows": len(inner), "outer_rows_excluded": len(outer),
            "test_rows_preserved": len(test), "output_features": prepared.matrix.shape[1],
            "fit_sparse_nnz": int(prepared.matrix.nnz),
            "fit_sparse_bytes": int(prepared.matrix.data.nbytes + prepared.matrix.indices.nbytes + prepared.matrix.indptr.nbytes),
            "source_sha256": plan.train_sha256, "schema_sha256": schema.schema_sha256,
            "split_schema_sha256": plan.schema_sha256,
            "split_scope_sha256": plan.partition_sha256,
            "trained_statistics_sha256": witness,
            "fit_values_sha256": view.fit_values_sha256,
            "source_binding": view.source_binding,
            "active_split_binding": view.active_split_binding,
            "contract_partition_sha256": contract.to_dict()["split_policy"]["partition_sha256"],
            "protected_feature_frames_retained": False,
            "target_or_id_columns_retained": False,
            "elapsed_seconds": round(perf_counter() - started, 6),
            "process_max_rss_mib_so_far": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 3),
            "estimator_fitted": False, "api_used": False,
        })
        del test, view, fitted, prepared, test_result
    after = {str(path.relative_to(source_root)): sha(path) for path in source_files}
    if before != after:
        raise RuntimeError("public_sources_changed")
    return {"source_file_count": len(source_files), "source_sha256_before": before,
            "source_sha256_after": after, "source_bytes_unchanged": True}


def main():
    global P, np, pd, sparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--actual-public", action="store_true")
    args = parser.parse_args()
    if args.receipt.exists():
        parser.error("receipt already exists")
    started = perf_counter()
    import numpy as np
    import pandas as pd
    import scipy
    from scipy import sparse
    import sklearn
    import aegml_preprocessing as P

    receipt = {
        "schema_version": "h032_preprocessing_check.v1", "scope": "H03.2_preprocessing_only",
        "status": "FAIL", "python": platform.python_version(), "platform": platform.platform(),
        "versions": {"numpy": np.__version__, "pandas": pd.__version__,
                     "scipy": scipy.__version__, "scikit_learn": sklearn.__version__},
        "source_sha256": {name: sha(ROOT / name) for name in
                          ("aegml_preprocessing.py", "scripts/check_h032_preprocessing.py", "aegml_input.py",
                           "aegml_contracts.py", "aegml_schemas.py", "aegml_validation.py",
                           "aegml_metrics.py", "requirements.txt")},
        "estimator_fitted": False, "preprocessing_fitted": True,
        "api_calls": 0, "network_used": False, "generated_code_executed": False,
        "prediction_csv_written": False, "full_agent_accepted": False,
    }
    if platform.python_version_tuple()[:2] != ("3", "12"):
        receipt["reason"] = "expected_python_3_12"
        success = False
    else:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
        result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(suite)
        receipt.update(test_methods_run=result.testsRun, behavior_cases_checked=len(CASES), cases=CASES,
                       failures=[test.id() for test, _ in result.failures],
                       errors=[test.id() for test, _ in result.errors])
        success = result.wasSuccessful()
        if success and args.actual_public:
            try:
                receipt["source_preservation"] = actual_public_checks()
            except Exception as exc:
                receipt["reason"] = "actual_public_check_failed"
                receipt["error_type"] = type(exc).__name__
                if isinstance(exc, P.PreprocessingError):
                    receipt["error_code"] = exc.code
                success = False
        receipt["actual_public"] = PUBLIC
    receipt["source_sha256_after"] = {name: sha(ROOT / name) for name in receipt["source_sha256"]}
    receipt["source_unchanged"] = receipt["source_sha256_after"] == receipt["source_sha256"]
    if not receipt["source_unchanged"]:
        success = False
        receipt["reason"] = "component_source_changed"
    receipt["status"] = "PASS" if success else "FAIL"
    receipt["elapsed_seconds"] = round(perf_counter() - started, 6)
    receipt["process_max_rss_mib"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 3)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"check": "H03.2", "status": receipt["status"],
                      "methods": receipt.get("test_methods_run", 0), "cases": len(CASES),
                      "actual_public": len(PUBLIC), "estimator_fitted": False, "api_calls": 0}))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
