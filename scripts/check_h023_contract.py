"""H02.3 TaskContract/resolver verification; unittest and synthetic CSV fixtures.

Use Python 3.12 in the authorized ML venv with --receipt PATH. No API, fit,
profiling, package installation, or commands from task text are executed here.
Actual public inputs are optional read-only checks, explicitly SKIP if absent.
"""

from contextlib import contextmanager
import copy
import csv
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
import argparse


ROOT = Path(__file__).resolve().parent.parent
ROOT_FILES = ("solution.py", "aegml_contracts.py", "aegml_input.py", "aegml_schemas.py", "requirements.txt")
EXPECTED_REQUIREMENTS_SHA = "9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6"
FILENAMES = {"train": "train.csv", "test": "test.csv", "data_dictionary": "data_dictionary.csv", "sample_submission": "sample_submission.csv"}
KEY_CANARY = "H023_DUMMY_PROVIDER_KEY_CANARY_4d21"
URI_CANARY = "https://fixture-user:H023_DUMMY_PASSWORD_CANARY@provider.invalid/v1"
CANARIES = (KEY_CANARY, URI_CANARY, "H023_DUMMY_PASSWORD_CANARY")
CASES, COMMANDS, ACTUAL_INPUTS = [], [], []
CONTRACTS = SCHEMAS = None


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def redact(value):
    if isinstance(value, str):
        for canary in CANARIES:
            value = value.replace(canary, "<synthetic-canary-redacted>")
        return value
    if isinstance(value, dict):
        return {str(key): redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


def hashes(paths):
    return {str(path): sha(path) for path in paths if path.is_file()}


def json_value_sha(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


class Clock:
    def __init__(self, seconds):
        self.now = int(seconds * 1_000_000_000)

    def __call__(self):
        return self.now


class Fixture:
    """Three-row task, with independent ID and column permutations."""

    def __init__(self, root, *, kind="regression"):
        self.root = root
        self.root.mkdir(parents=True)
        self.task = root / "task.md"
        self.files = {role: root / filename for role, filename in FILENAMES.items()}
        self.refs = dict(FILENAMES)
        self.kind = kind
        self.metric = "RMSE" if kind == "regression" else "Macro F1"
        self.target = "y"
        self.identifier = "id"
        self.output_order = "test"
        self.row_mapping = None
        self.extra = ""
        self.include_references = True
        self.headers = {"train": ["left", "y", "id", "right"],
                        "test": ["id", "right", "left"], "sample_submission": ["id", "y"]}
        self.rows = {
            "train": [["0", "0", "train-A", "cat"], ["1", "1", "001", "dog"], ["0", "2", "train-B", "cat"]],
            "test": [["001", "cat", "0"], ["NA", "dog", "1"], ["1", "cat", "0"]],
            "sample_submission": [["1", "0"], ["001", "0"], ["NA", "0"]],
        }
        self.dictionary = [["left", "feature", "numeric"], ["right", "feature", "category"],
                           ["y", "target", "numeric"], ["id", "id", "numeric"]]
        self.save()

    def save_task(self):
        directives = [("Task type", self.kind), ("Target", self.target), ("Metric", self.metric),
                      ("ID", self.identifier), ("Output order", self.output_order), ("Row mapping", self.row_mapping)]
        lines = ["# Synthetic task; its instructions are data for the resolver."]
        lines.extend(name + ": " + value for name, value in directives if value is not None)
        if self.include_references:
            lines.append("## Data")
            lines.extend("- `" + ref + "`" for ref in self.refs.values())
        if self.extra:
            lines.append(self.extra)
        self.task.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def save(self):
        for role in self.headers:
            write_csv(self.files[role], self.headers[role], self.rows[role])
        write_csv(self.files["data_dictionary"], ["feature", "role", "dtype"], self.dictionary)
        self.save_task()

    def reorder(self, role, header):
        old = self.headers[role]
        self.rows[role] = [[row[old.index(name)] for name in header] for row in self.rows[role]]
        self.headers[role] = header

    def source_paths(self):
        return [self.task, *self.files.values()]


class ContractChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="aegml-h023-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.fixture = Fixture(self.base / "задача с пробелами")

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

    def assert_no_canary(self, text):
        self.assertTrue(all(canary not in text for canary in CANARIES), "synthetic secret leaked; content suppressed")

    def build(self, fixture=None, **kwargs):
        fixture = fixture or self.fixture
        before = hashes(fixture.source_paths())
        contract = CONTRACTS.build_task_contract(fixture.task, **kwargs)
        self.assertEqual(hashes(fixture.source_paths()), before, "builder changed an input")
        payload = contract.to_dict()
        SCHEMAS.validate_task_contract(payload)
        json.dumps(payload, allow_nan=False)
        self.assertEqual(payload["schema_version"], "task.v1")
        self.assertEqual(payload["split_policy"]["status"], "NOT_BUILT")
        self.assertEqual(payload["split_policy"]["strategy"], "deferred_to_H03")
        self.assertEqual(payload["output_path"], str(fixture.task.resolve().parent / "submission.csv"))
        self.assertFalse((fixture.task.resolve().parent / "submission.csv").exists())
        return contract, payload

    def rejected(self, fixture=None, *, codes=None, **kwargs):
        fixture = fixture or self.fixture
        before = hashes(fixture.source_paths())
        with self.assertRaises(CONTRACTS.ContractError) as caught:
            CONTRACTS.build_task_contract(fixture.task, **kwargs)
        error = caught.exception
        self.assertRegex(error.code, r"^[a-z][a-z0-9_]*$")
        self.assertEqual(str(error), error.code)
        if codes is not None:
            self.assertIn(error.code, codes)
        self.assert_no_canary(str(error) + repr(getattr(error, "conflicts", None)))
        self.assertEqual(hashes(fixture.source_paths()), before, "rejection changed an input")
        self.assertFalse((fixture.task.resolve().parent / "submission.csv").exists())
        return error

    def review_fixture(self, name):
        """Exact two-row keyed-alignment basis from the independent review."""
        fixture = Fixture(self.base / name)
        fixture.include_references = False
        fixture.headers = {"train": ["id", "x", "y"], "test": ["id", "x"], "sample_submission": ["id", "y"]}
        fixture.rows = {"train": [["a", "1", "10"]], "test": [["b", "2"], ["c", "3"]],
                        "sample_submission": [["c", "0"], ["b", "0"]]}
        fixture.dictionary = [["id", "id", "string"], ["x", "feature", "float"], ["y", "target", "float"]]
        fixture.save()
        return fixture

    def test_review_role_conflicts_and_absent_role_completion(self):
        variants = (("target_ignore", "y", "ignore", "target_role_conflict"),
                    ("id_feature", "id", "feature", "id_role_conflict"),
                    ("missing_target_declaration", "y", None, None),
                    ("missing_id_declaration", "id", None, None))
        for label, column, role, code in variants:
            with self.subTest(case=label), self.case("H023-ROLE-001_" + label):
                fixture = self.review_fixture("role-" + label)
                if role is None:
                    fixture.dictionary = [row for row in fixture.dictionary if row[0] != column]
                else:
                    for row in fixture.dictionary:
                        if row[0] == column:
                            row[1] = role
                fixture.save()
                if code is None:
                    contract, payload = self.build(fixture)
                    self.assertEqual(payload["target_columns"], ["y"])
                    self.assertEqual(payload["id_columns"], ["id"])
                    self.assertEqual(contract.alignment["sample_to_test"], [1, 0])
                else:
                    error = self.rejected(fixture, codes={code})
                    details = json.dumps(error.conflicts, ensure_ascii=False)
                    self.assertIn(column, details)
                    self.assertIn(role, details)
                    self.assertIn("dictionary", details)
                    self.assertIn("task", details)
                    self.assertFalse((fixture.root / ".aegml_runs").exists())

    def test_review_rejects_unparsed_declaration_remainders(self):
        variants = (("unknown_metric_suffix", "unsupported_metric"),
                    ("unsupported_type_suffix", "unsupported_task_type"),
                    ("dictionary_metric_transform", "unsupported_metric_transform"))
        for label, code in variants:
            with self.subTest(case=label), self.case("H023-DECL-001_" + label):
                fixture = self.review_fixture("declaration-" + label)
                if label == "unknown_metric_suffix":
                    fixture.metric = "RMSE, MAPE"
                elif label == "unsupported_type_suffix":
                    fixture.kind = "regression + clustering"
                fixture.save()
                if label == "dictionary_metric_transform":
                    rows = [row + ["RMSE(log1p(y))" if row[1] == "target" else ""] for row in fixture.dictionary]
                    write_csv(fixture.files["data_dictionary"], ["feature", "role", "dtype", "metric"], rows)
                self.rejected(fixture, codes={code})
                self.assertFalse((fixture.root / ".aegml_runs").exists())

    def test_review_supported_en_ru_declarations_remain_valid(self):
        variants = ("english_full_rmse", "english_known_negation", "russian_known_negation", "native_russian_rmse_scale")
        for label in variants:
            with self.subTest(case=label), self.case("H023-DECL-001_supported_" + label):
                fixture = self.review_fixture("supported-" + label)
                expected = "rmse"
                if label == "english_full_rmse":
                    fixture.metric = "Root Mean Squared Error"
                elif label in {"english_known_negation", "russian_known_negation"}:
                    fixture.kind = "multiclass classification"
                    fixture.metric = "Macro F1, not Accuracy" if label.startswith("english") else "Macro F1, а не Accuracy"
                    expected = "macro_f1"
                fixture.save()
                if label == "russian_known_negation":
                    text = fixture.task.read_text(encoding="utf-8").replace(
                        "Task type: multiclass classification", "Тип задачи: многоклассовая классификация").replace(
                        "Metric: Macro F1, а не Accuracy", "Основная метрика — Macro F1, а не Accuracy")
                    fixture.task.write_text(text, encoding="utf-8")
                elif label == "native_russian_rmse_scale":
                    text = fixture.task.read_text(encoding="utf-8").replace(
                        "Task type: regression", "Тип задачи: регрессия").replace(
                        "Metric: RMSE", "Метрика оценки — **RMSE** на исходной шкале таргета:")
                    fixture.task.write_text(text, encoding="utf-8")
                contract, payload = self.build(fixture)
                self.assertEqual(payload["metric"]["name"], expected)
                self.assertEqual(contract.alignment["output_to_test"], [0, 1])

    def test_review_output_order_is_not_inferred_from_neighboring_filename(self):
        variants = (
            ("explicit_sample_near_input_test", "Input: `test.csv`\nRow order: sample", None, "sample"),
            ("row_order_matters_is_ambiguous", "Input: `test.csv`\nRow order matters.", "ambiguous_output_order", None),
            ("explicit_test_identity", "Output order: test", None, "test"),
            ("two_explicit_orders_conflict", "Output order: test\nRow order: sample", "output_order_conflict", None),
            ("english_same_statement", "Output rows must be in the same order as test.csv.", None, "test"),
            ("russian_same_statement", "Порядок строк должен совпадать с `test.csv`.", None, "test"),
        )
        for label, declaration, code, expected in variants:
            with self.subTest(case=label), self.case("H023-ORDER-001_" + label):
                fixture = self.review_fixture("order-" + label)
                fixture.output_order = None
                fixture.extra = declaration
                fixture.save_task()
                if code is not None:
                    self.rejected(fixture, codes={code})
                    self.assertFalse((fixture.root / ".aegml_runs").exists())
                else:
                    contract, payload = self.build(fixture)
                    self.assertEqual(contract.alignment["sample_to_test"], [1, 0])
                    self.assertEqual(contract.alignment["output_order"], expected)
                    self.assertEqual(payload["prediction_schema"]["output_order"], expected)
                    self.assertEqual(contract.alignment["output_to_test"], [1, 0] if expected == "sample" else [0, 1])

    def test_target_position_and_feature_projection(self):
        for label, order in (("nonlast", ["left", "y", "id", "right"]), ("first", ["y", "left", "id", "right"])):
            with self.subTest(case=label), self.case("target_" + label):
                self.fixture.reorder("train", order)
                self.fixture.save()
                contract, payload = self.build()
                self.assertEqual(payload["target_columns"], ["y"])
                self.assertEqual(payload["id_columns"], ["id"])
                self.assertEqual(payload["feature_columns"], ["left", "right"])
                self.assertEqual(contract.alignment["feature_projection"], {"train_order": ["left", "right"], "test_indices": [2, 1]})
                self.assertEqual(payload["metric"]["name"], "rmse")
                self.assertEqual(payload["metric"]["direction"], "minimize")

    def test_numeric_classification_and_placeholder_sample(self):
        with self.case("numeric_class_labels_are_classification_not_regression"):
            fixture = Fixture(self.base / "числовые классы", kind="classification")
            fixture.rows["sample_submission"] = [[row[0], "NOT_A_REAL_PREDICTION"] for row in fixture.rows["sample_submission"]]
            fixture.save()
            _, payload = self.build(fixture)
            self.assertEqual(payload["task_type"], "classification")
            self.assertEqual(payload["metric"]["name"], "macro_f1")
            self.assertEqual(payload["metric"]["parameters"]["average"], "macro")
            self.assertIsNone(payload["metric"]["parameters"]["labels"])
            self.assertEqual(payload["metric"]["label_policy"], "sklearn_labels_none")

    def test_generic_field_names_and_russian_directives(self):
        with self.case("renamed_id_target_features_are_not_public_name_constants"):
            names = {"id": "record_key", "y": "response_value", "left": "measure_a", "right": "category_b"}
            fixture = self.fixture
            fixture.headers = {role: [names[name] for name in header] for role, header in fixture.headers.items()}
            fixture.dictionary = [[names[row[0]], *row[1:]] for row in fixture.dictionary]
            fixture.target, fixture.identifier = "response_value", "record_key"
            fixture.save()
            _, payload = self.build()
            self.assertEqual(payload["target_columns"], ["response_value"])
            self.assertEqual(payload["id_columns"], ["record_key"])
            self.assertEqual(payload["feature_columns"], ["measure_a", "category_b"])
        with self.case("explicit_russian_directives"):
            text = fixture.task.read_text(encoding="utf-8")
            for original, translated in (("Task type: regression", "Тип задачи: регрессия"),
                                         ("Target:", "Таргет:"), ("Metric:", "Метрика:"),
                                         ("ID:", "Идентификатор:"), ("Output order: test", "Порядок вывода: test")):
                text = text.replace(original, translated)
            fixture.task.write_text(text, encoding="utf-8")
            _, payload = self.build()
            self.assertEqual((payload["task_type"], payload["metric"]["name"]), ("regression", "rmse"))

    def test_low_cardinality_numeric_does_not_decide_task_type(self):
        with self.case("explicit_rmse_numeric_target_is_regression_despite_few_values"):
            self.fixture.kind = None
            self.fixture.rows["train"][2][1] = "0"
            self.fixture.save()
            _, payload = self.build()
            self.assertEqual(payload["task_type"], "regression")
        with self.case("no_primary_metric_is_not_guessed_from_unique_target_count"):
            self.fixture.metric = None
            self.fixture.save()
            self.rejected(codes={"missing_primary_metric"})

    def test_raw_ids_and_directional_permutation(self):
        with self.case("001_NA_1_preserved_and_cyclic_sample_mapping"):
            contract, payload = self.build()
            alignment = contract.alignment
            self.assertEqual(alignment["row_counts"], {"train": 3, "test": 3, "sample_submission": 3})
            self.assertEqual(alignment["sample_to_test"], [2, 0, 1])
            self.assertEqual(alignment["output_to_test"], [0, 1, 2])
            self.assertEqual(alignment["output_order"], "test")
            self.assertFalse(alignment["positional"])
            self.assertEqual(payload["prediction_schema"]["output_order"], "test")

    def test_explicit_sample_order(self):
        with self.case("explicit_task_sample_order_changes_output_mapping"):
            self.fixture.output_order = "sample"
            self.fixture.save()
            contract, payload = self.build()
            self.assertEqual(contract.alignment["output_to_test"], [2, 0, 1])
            self.assertEqual(payload["prediction_schema"]["output_order"], "sample")

    def test_target_first_output_columns_follow_explicit_sample_format(self):
        for kind in ("regression", "classification"):
            with self.subTest(kind=kind), self.case("H023-CONTRACT-002_target_first_output_" + kind):
                fixture = Fixture(self.base / ("target-first-output-" + kind), kind=kind)
                fixture.reorder("sample_submission", ["y", "id"])
                fixture.extra = "Output format: follow the columns and column order in sample_submission.csv."
                fixture.save()
                contract, payload = self.build(fixture)
                self.assertEqual(payload["prediction_schema"]["columns"], ["y", "id"])
                self.assertEqual(payload["id_columns"], ["id"])
                self.assertEqual(payload["target_columns"], ["y"])
                self.assertEqual(contract.alignment["sample_to_test"], [2, 0, 1])
                self.assertEqual(contract.alignment["output_to_test"], [0, 1, 2])

    def test_alignment_is_defensive_copy_and_payload_is_compact(self):
        with self.case("alignment_copy_cannot_mutate_authoritative_contract"):
            contract, payload = self.build()
            baseline = copy.deepcopy(contract.alignment)
            changed = contract.alignment
            changed["sample_to_test"][0] = 999
            changed["row_counts"]["test"] = 999
            changed["feature_projection"]["test_indices"][0] = 999
            self.assertEqual(contract.alignment, baseline)
            summary = payload["provenance"]["row_mapping"]
            self.assertIsInstance(summary, dict)
            self.assertNotIsInstance(summary.get("sample_to_test"), list)
            self.assertNotIsInstance(summary.get("output_to_test"), list)
            text = json.dumps(summary)
            self.assertIn("sha256", text)
            self.assertIn("count", text)

    def test_train_test_id_overlap_is_not_object_join(self):
        for label, ids in (("overlap", ["001", "NA", "1"]), ("disjoint", ["train-X", "train-Y", "train-Z"])):
            with self.subTest(case=label), self.case("train_test_ids_" + label + "_allowed"):
                column = self.fixture.headers["train"].index("id")
                for row, identifier in zip(self.fixture.rows["train"], ids):
                    row[column] = identifier
                self.fixture.save()
                contract, _ = self.build()
                self.assertEqual(contract.alignment["sample_to_test"], [2, 0, 1])

    def test_missing_feature_values_are_not_dropped(self):
        with self.case("blank_feature_value_does_not_change_contract_row_count"):
            self.fixture.rows["test"][0][2] = ""
            self.fixture.save()
            contract, _ = self.build()
            self.assertEqual(contract.alignment["row_counts"]["test"], 3)

    def test_positional_mapping_requires_explicit_permission(self):
        fixture = self.fixture
        for role in fixture.headers:
            fixture.reorder(role, [name for name in fixture.headers[role] if name != "id"])
        fixture.dictionary = [row for row in fixture.dictionary if row[0] != "id"]
        fixture.identifier = "none"
        fixture.row_mapping = "position"
        fixture.save()
        with self.case("explicit_positional_mapping_without_synthetic_id"):
            contract, payload = self.build()
            self.assertEqual(payload["id_columns"], [])
            self.assertTrue(contract.alignment["positional"])
            self.assertEqual(contract.alignment["sample_to_test"], [0, 1, 2])
        with self.case("no_id_without_position_policy_is_rejected"):
            fixture.row_mapping = None
            fixture.save()
            self.rejected()

    def test_explicit_positional_mapping_with_output_only_ids(self):
        with self.case("explicit_positional_mapping_preserves_output_only_sample_ids"):
            fixture = self.fixture
            fixture.headers = {"train": ["y", "x", "z"], "test": ["x", "z"], "sample_submission": ["id", "y"]}
            fixture.rows = {
                "train": [["0", "1", "a"], ["1", "2", "b"], ["2", "3", "c"]],
                "test": [["4", "a"], ["5", "b"], ["6", "c"]],
                "sample_submission": [["NA", "0"], ["001", "0"], ["1", "0"]],
            }
            fixture.dictionary = [["y", "target", "numeric"], ["x", "feature", "numeric"],
                                  ["z", "feature", "category"], ["id", "id", "numeric"]]
            fixture.identifier = "id"
            fixture.row_mapping = "position"
            fixture.output_order = "test"
            fixture.save()
            contract, payload = self.build()
            alignment = contract.alignment
            self.assertEqual(payload["id_columns"], ["id"])
            self.assertEqual(payload["prediction_schema"]["columns"], ["id", "y"])
            self.assertEqual(payload["feature_columns"], ["x", "z"])
            self.assertTrue(alignment["positional"])
            self.assertEqual(alignment["sample_to_test"], [0, 1, 2])
            self.assertEqual(alignment["output_to_test"], [0, 1, 2])
            self.assertEqual(alignment["id_availability"], {"train": False, "test": False, "sample_submission": True})
            with fixture.files["sample_submission"].open(encoding="utf-8", newline="") as stream:
                self.assertEqual([row["id"] for row in csv.DictReader(stream)], ["NA", "001", "1"])

    def test_nested_explicit_reference_beats_decoy(self):
        with self.case("explicit_nested_train_selects_declared_source"):
            fixture = self.fixture
            original = fixture.files["train"]
            selected = fixture.root / "nested" / "train.csv"
            selected.parent.mkdir()
            shutil.copyfile(original, selected)
            fixture.files["train"] = selected
            fixture.refs["train"] = "nested/train.csv"
            fixture.save_task()
            _, payload = self.build()
            self.assertEqual(payload["input_paths"]["train"], str(selected.resolve()))
            self.assertEqual(payload["provenance"]["files"]["train"]["resolution"], "explicit")

    def test_missing_nested_paths_have_recorded_flat_fallback(self):
        with self.case("declared_missing_nested_unique_flat_fallback"):
            self.fixture.refs = {role: "missing/participants/" + name for role, name in FILENAMES.items()}
            self.fixture.save_task()
            _, payload = self.build()
            for role in FILENAMES:
                self.assertEqual(payload["input_paths"][role], str(self.fixture.files[role].resolve()))
                self.assertEqual(payload["provenance"]["files"][role]["resolution"], "flat_fallback")

    def test_ambiguous_files_are_not_selected_by_walk_order(self):
        with self.case("no_declared_path_two_train_candidates"):
            duplicate = self.fixture.root / "backup" / "train.csv"
            duplicate.parent.mkdir()
            shutil.copyfile(self.fixture.files["train"], duplicate)
            self.fixture.include_references = False
            self.fixture.save_task()
            self.rejected(codes={"ambiguous_input"})
        with self.case("two_existing_explicit_nested_train_references"):
            fixture = Fixture(self.base / "explicit-ambiguous")
            for directory in ("one", "two"):
                target = fixture.root / directory / "train.csv"
                target.parent.mkdir()
                shutil.copyfile(fixture.files["train"], target)
            fixture.refs["train"] = "one/train.csv"
            fixture.extra = "- `two/train.csv`"
            fixture.save_task()
            self.rejected(fixture, codes={"ambiguous_input"})

    def test_missing_dictionary(self):
        with self.case("missing_dictionary_not_replaced_by_dataset_name_guess"):
            self.fixture.files["data_dictionary"].unlink()
            self.rejected()

    def test_metric_and_target_conflicts(self):
        variants = ("contradictory_type_metric", "multiple_primary_metrics", "unknown_primary_metric", "multiple_dictionary_targets", "task_dictionary_target_conflict")
        for label in variants:
            with self.subTest(case=label), self.case(label):
                fixture = Fixture(self.base / label)
                codes = None
                if label == "contradictory_type_metric":
                    fixture.metric = "Macro F1"
                elif label == "multiple_primary_metrics":
                    fixture.extra = "Metric: MAE"
                    codes = {"ambiguous_primary_metric"}
                elif label == "unknown_primary_metric":
                    fixture.metric = "totally_unknown_metric_v99"
                    codes = {"unsupported_metric"}
                elif label == "multiple_dictionary_targets":
                    fixture.dictionary[0][1] = "target"
                else:
                    fixture.target = "left"
                fixture.save()
                self.rejected(fixture, codes=codes)

    def test_unknown_second_task_type_is_not_ignored(self):
        with self.case("H023-CONTRACT-003_unknown_second_explicit_task_type"):
            self.fixture.extra = "Task type: unsupported_banana"
            self.fixture.save_task()
            self.rejected(codes={"unsupported_task_type"})

    def test_class_order_json_nonfinite_vs_quoted_string(self):
        for constant in ("NaN", "Infinity"):
            with self.subTest(constant=constant), self.case("H023-CONTRACT-004_reject_json_" + constant):
                fixture = Fixture(self.base / ("nonfinite-label-" + constant), kind="classification")
                fixture.metric = "Accuracy"
                fixture.extra = 'Class order: [' + constant + ', "a"]'
                fixture.save_task()
                self.rejected(fixture, codes={"invalid_label_declaration"})
        overflow_cases = (("positive_overflow", "Class order: [0, 1e309]"),
                          ("negative_overflow", "Class order: [0, -1e309]"),
                          ("positive_label_overflow", "Positive label: [1e309]"))
        for label, declaration in overflow_cases:
            with self.subTest(case=label), self.case("H023-CONTRACT-004_reject_" + label):
                fixture = Fixture(self.base / label, kind="classification")
                fixture.metric = "Accuracy"
                fixture.extra = declaration
                fixture.save_task()
                self.rejected(fixture, codes={"invalid_label_declaration"})
        with self.case("H023-CONTRACT-004_quoted_NaN_is_a_string_label"):
            fixture = Fixture(self.base / "quoted-NaN-label", kind="classification")
            fixture.metric = "Accuracy"
            fixture.extra = 'Class order: ["NaN", "a"]'
            for row, label in zip(fixture.rows["train"], ("NaN", "a", "a")):
                row[fixture.headers["train"].index("y")] = label
            for row in fixture.dictionary:
                if row[0] == "y":
                    row[2] = "category"
            fixture.save()
            _, payload = self.build(fixture)
            self.assertEqual(payload["metric"]["name"], "accuracy")
            self.assertEqual(payload["metric"]["class_order"], ["NaN", "a"])
            self.assertTrue(all(type(label) is str for label in payload["metric"]["class_order"]))

    def test_duplicate_and_missing_ids(self):
        for role in ("train", "test", "sample_submission"):
            for label in ("duplicate", "blank"):
                with self.subTest(role=role, case=label), self.case(label + "_id_" + role):
                    fixture = Fixture(self.base / (role + "_" + label))
                    column = fixture.headers[role].index("id")
                    fixture.rows[role][1][column] = fixture.rows[role][0][column] if label == "duplicate" else ""
                    fixture.save()
                    self.rejected(fixture, codes={"duplicate_id" if label == "duplicate" else "invalid_id"})

    def test_mismatch_and_leading_zero_id_are_not_coerced(self):
        with self.case("unique_sample_test_id_set_mismatch"):
            self.fixture.rows["sample_submission"][1][0] = "01"
            self.fixture.save()
            self.rejected(codes={"sample_test_id_mismatch"})
        with self.case("sample_test_row_count_mismatch"):
            self.fixture.rows["sample_submission"].pop()
            self.fixture.save()
            self.rejected(codes={"sample_test_row_count_mismatch"})

    def test_duplicate_empty_headers_and_feature_mismatch(self):
        for label in ("duplicate_header", "empty_header", "missing_test_feature", "missing_id_column", "extra_test_feature", "target_in_test", "wrong_sample_target"):
            with self.subTest(case=label), self.case(label):
                fixture = Fixture(self.base / label)
                if label == "duplicate_header":
                    fixture.headers["train"][-1] = "left"
                elif label == "empty_header":
                    fixture.headers["train"][0] = ""
                elif label == "missing_test_feature":
                    fixture.reorder("test", ["id", "right"])
                elif label == "missing_id_column":
                    fixture.reorder("test", ["right", "left"])
                elif label in {"extra_test_feature", "target_in_test"}:
                    fixture.headers["test"].append("extra" if label == "extra_test_feature" else "y")
                    for row in fixture.rows["test"]:
                        row.append("0")
                else:
                    fixture.headers["sample_submission"][-1] = "different_target"
                fixture.save()
                self.rejected(fixture)

    def test_unsafe_references_are_not_followed(self):
        variants = {"traversal": "../outside/train.csv", "uri": "https://example.invalid/train.csv", "absolute": "/tmp/h023-forbidden/train.csv"}
        for label, reference in variants.items():
            with self.subTest(case=label), self.case("unsafe_reference_" + label):
                fixture = Fixture(self.base / ("unsafe_" + label))
                fixture.refs["train"] = reference
                fixture.save_task()
                self.rejected(fixture, codes={"unsafe_input_reference"})

    def test_external_input_symlink_rejected(self):
        with self.case("external_input_symlink_not_read_as_task_input"):
            external = self.base / "controlled_external.csv"
            shutil.copyfile(self.fixture.files["train"], external)
            external_sha = sha(external)
            self.fixture.files["train"].unlink()
            self.fixture.files["train"].symlink_to(external)
            self.rejected(codes={"external_input_path"})
            self.assertEqual(sha(external), external_sha)

    def test_task_symlink_anchors_to_physical_task_parent(self):
        with self.case("task_symlink_uses_resolved_physical_parent"):
            link = self.base / "task-link.md"
            link.symlink_to(self.fixture.task)
            before = hashes(self.fixture.source_paths())
            contract = CONTRACTS.build_task_contract(link)
            payload = contract.to_dict()
            self.assertEqual(payload["task_path"], str(self.fixture.task.resolve()))
            self.assertEqual(payload["output_path"], str(self.fixture.root / "submission.csv"))
            self.assertEqual(hashes(self.fixture.source_paths()), before)

    def test_task_injection_is_not_executed(self):
        with self.case("task_code_block_is_data_not_execution"):
            marker = self.fixture.root / "should-never-exist.txt"
            self.fixture.extra = "```python\nfrom pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('executed')\n```"
            self.fixture.save_task()
            self.build()
            self.assertFalse(marker.exists(), "task code block was executed")

    def test_invalid_builder_constraints_and_expired_budget(self):
        for label, kwargs in (("threads_zero", {"threads": 0}), ("threads_nine", {"threads": 9}),
                              ("time_nan", {"time_limit_seconds": float("nan")}), ("time_inf", {"time_limit_seconds": float("inf")}),
                              ("time_too_long", {"time_limit_seconds": 10801})):
            with self.subTest(case=label), self.case("invalid_builder_" + label):
                self.rejected(**kwargs)
        with self.case("expired_shared_budget_is_not_contract_error"):
            budget = CONTRACTS.RunBudget(0, 10, 1, Clock(11))
            with self.assertRaises(CONTRACTS.BudgetExpired):
                CONTRACTS.build_task_contract(self.fixture.task, budget=budget)

    def test_strict_schema_negative_payloads(self):
        contract, valid = self.build()
        mutations = ("nan", "inf", "unknown_field", "missing_finite_policy", "target_feature_overlap", "id_feature_overlap")
        for label in mutations:
            with self.subTest(case=label), self.case("schema_reject_" + label):
                payload = copy.deepcopy(valid)
                if label in {"nan", "inf"}:
                    payload["constraints"]["time_limit_seconds"] = float(label)
                elif label == "unknown_field":
                    payload["unknown_extra"] = True
                elif label == "missing_finite_policy":
                    del payload["metric"]["finite_policy"]
                elif label == "target_feature_overlap":
                    payload["feature_columns"].append(payload["target_columns"][0])
                else:
                    payload["feature_columns"].append(payload["id_columns"][0])
                with self.assertRaises(SCHEMAS.SchemaError) as caught:
                    SCHEMAS.validate_task_contract(payload)
                self.assertEqual(caught.exception.code, "invalid_task_contract")
        self.assertEqual(contract.to_dict(), valid, "mutated test payload changed the contract")

    def test_publish_fresh_sidecars_with_exact_hashes(self):
        with self.case("publish_contract_and_alignment_to_fresh_run_directory"):
            before = hashes(self.fixture.source_paths())
            contract, payload = self.build()
            alignment = contract.alignment
            metadata = CONTRACTS.publish_task_contract(contract)
            contract_path, alignment_path = Path(metadata["task_contract_path"]), Path(metadata["alignment_path"])
            run_root = self.fixture.root / ".aegml_runs"
            self.assertTrue(contract_path.is_relative_to(run_root) and alignment_path.is_relative_to(run_root))
            self.assertEqual(contract_path.parent, alignment_path.parent)
            # H023-QA-001: publication enriches a copy; the built contract stays unchanged.
            expected_published = copy.deepcopy(payload)
            expected_published["provenance"]["row_mapping"].update(
                status="published", artifact_path=str(alignment_path), artifact_sha256=sha(alignment_path))
            self.assertEqual(json.loads(contract_path.read_text(encoding="utf-8")), expected_published)
            self.assertEqual(contract.to_dict(), payload, "publisher mutated the original contract payload")
            self.assertEqual(contract.alignment, alignment, "publisher mutated original alignment")
            sidecar = json.loads(alignment_path.read_text(encoding="utf-8"))
            for key, value in alignment.items():
                self.assertEqual(sidecar[key], value)
            self.assertEqual(sha(contract_path), metadata["task_contract_sha256"])
            self.assertEqual(sha(alignment_path), metadata["alignment_sha256"])
            old = hashes([contract_path, alignment_path])
            second, _ = self.build()
            other = CONTRACTS.publish_task_contract(second)
            self.assertNotEqual(Path(other["task_contract_path"]).parent, contract_path.parent)
            self.assertEqual(hashes([contract_path, alignment_path]), old)
            self.assertEqual(hashes(self.fixture.source_paths()), before)
            self.assertFalse((self.fixture.root / "submission.csv").exists())

    def test_publisher_rejects_unsafe_run_id_before_io(self):
        with self.case("H023-ART-001_unsafe_run_id_rejected_before_directory_creation"):
            contract, payload = self.build()
            malformed = copy.deepcopy(payload)
            malformed["run_id"] = "../../escaped"
            unsafe = CONTRACTS.TaskContract(malformed, contract.alignment)
            namespace = self.fixture.root / ".aegml_runs"
            escaped = self.base / "escaped"
            self.assertFalse(namespace.exists())
            self.assertFalse(escaped.exists())
            tree_before = {str(path.relative_to(self.base)) for path in self.base.rglob("*")}
            inputs_before = hashes(self.fixture.source_paths())
            with self.assertRaises(CONTRACTS.ContractError) as caught:
                CONTRACTS.publish_task_contract(unsafe)
            self.assertEqual(caught.exception.code, "invalid_run_id")
            self.assertFalse(namespace.exists(), "publisher created namespace before checking run_id")
            self.assertFalse(escaped.exists(), "publisher wrote outside its namespace")
            self.assertEqual({str(path.relative_to(self.base)) for path in self.base.rglob("*")}, tree_before)
            self.assertEqual(hashes(self.fixture.source_paths()), inputs_before)
            self.assertEqual(contract.to_dict(), payload)

    def cli(self, args, *, expected_code=3, valid=True):
        fixture = self.fixture
        for name in ROOT_FILES:
            shutil.copyfile(ROOT / name, fixture.root / name)
        self.assertEqual(sha(fixture.root / "requirements.txt"), EXPECTED_REQUIREMENTS_SHA)
        env = {"PATH": str(Path(sys.executable).parent) + os.pathsep + os.defpath,
               "LANG": "C.UTF-8", "PYTHONUTF8": "1", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
               "OPENAI_API_KEY": KEY_CANARY, "OPENAI_BASE_URL": URI_CANARY, "OPENAI_MODEL": "dummy-h023-not-requested"}
        command = ["python3", "solution.py", *args]
        before = hashes([*fixture.source_paths(), *(fixture.root / name for name in ROOT_FILES)])
        old_csv = fixture.root / "submission.csv"
        csv_before = (sha(old_csv), old_csv.stat().st_mtime_ns) if old_csv.exists() else None
        record = {"argv": redact(command), "cwd": str(fixture.root), "selective_copy_root_files": list(ROOT_FILES),
                  "source_and_input_sha256_before": before, "timeout_seconds": 30}
        COMMANDS.append(record)
        result = subprocess.run(command, cwd=fixture.root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                encoding="utf-8", timeout=30, check=False)
        self.assert_no_canary(result.stdout + result.stderr)
        self.assertNotIn(str(fixture.root), result.stdout + result.stderr, "public CLI must not expose raw task paths")
        self.assertEqual(result.returncode, expected_code, "unexpected CLI exit; raw output suppressed")
        self.assertEqual(result.stderr, "", "unexpected stderr; raw output suppressed")
        try:
            outcome = json.loads(result.stdout)
        except ValueError:
            self.fail("CLI must emit one JSON outcome; raw output suppressed")
        self.assertNotIn(str(fixture.root), json.dumps(outcome, ensure_ascii=False), "decoded public metadata exposes raw task paths")
        self.assertEqual(outcome["exit_code"], expected_code)
        self.assertIs(outcome["contract_valid"], valid)
        for flag in ("api_verified", "tools_verified", "research_completed", "submission_valid"):
            self.assertIs(outcome[flag], False)
        self.assertEqual(outcome["experiments_completed"], 0)
        if valid:
            self.assertEqual(outcome["phase"], "H02.3")
            self.assertEqual(outcome["termination_reason"], "implementation_incomplete")
            artifacts = outcome["artifact_sha"]
            self.assertIsInstance(artifacts, dict)
            json_outputs = list((fixture.root / ".aegml_runs").glob("*/*.json"))
            self.assertEqual(len(json_outputs), 2, "valid CLI should publish only contract and alignment JSON")
            for artifact in json_outputs:
                self.assertIn(sha(artifact), artifacts.values(), "public metadata must identify the published artifact")
        self.assertEqual(hashes([*fixture.source_paths(), *(fixture.root / name for name in ROOT_FILES)]), before)
        if csv_before is None:
            self.assertFalse(old_csv.exists())
        else:
            self.assertEqual((sha(old_csv), old_csv.stat().st_mtime_ns), csv_before)
        record.update(exit_code=result.returncode, outcome=redact(outcome), source_and_input_sha256_stable=True)
        return outcome

    def test_exact_cli_selective_copy_preserves_old_csv(self):
        with self.case("literal_python3_solution_py_task_md_contract_valid_exit3"):
            output = self.fixture.root / "submission.csv"
            output.write_text("unverified old artifact\n", encoding="utf-8")
            os.utime(output, ns=(1_600_000_000_100_000_000, 1_600_000_000_100_000_000))
            self.cli(["task.md"])

    def test_cli_rejects_bad_contract_and_invalid_args(self):
        with self.case("cli_contract_error_nonzero_no_new_csv"):
            self.fixture.metric = "totally_unknown_metric_v99"
            self.fixture.save_task()
            self.cli(["task.md"], expected_code=2, valid=False)
        with self.case("cli_invalid_thread_argument_nonzero"):
            self.cli(["task.md", "--threads=9"], expected_code=2, valid=False)
        with self.case("cli_exhausted_cooperative_budget_exit124"):
            self.cli(["task.md", "--time-limit-seconds=0.000000001", "--finalize-reserve-seconds=0"], expected_code=124, valid=False)

    def actual_dataset(self, label, relative, expected):
        with self.case("actual_public_" + label + "_read_only_builder"):
            root = ROOT / "drive-download-20261019T181414Z-1-001" / relative
            paths = [root / "task.md", *(root / name for name in FILENAMES.values())]
            if not all(path.is_file() for path in paths):
                ACTUAL_INPUTS.append({"dataset": label, "status": "SKIP_INPUTS_NOT_PRESENT"})
                self.skipTest("optional ignored public inputs are not present")
            before = hashes(paths)
            old_csv = root / "submission.csv"
            csv_before = (sha(old_csv), old_csv.stat().st_mtime_ns) if old_csv.exists() else None
            contract = CONTRACTS.build_task_contract(root / "task.md")
            payload = contract.to_dict()
            SCHEMAS.validate_task_contract(payload)
            self.assertEqual(payload["target_columns"], [expected["target"]])
            self.assertEqual(payload["task_type"], expected["kind"])
            self.assertEqual(payload["metric"]["name"], expected["metric"])
            self.assertEqual(len(payload["feature_columns"]), expected["features"])
            alignment = contract.alignment
            self.assertEqual(alignment["row_counts"], expected["rows"])
            self.assertEqual(alignment["output_order"], "test")
            self.assertEqual(payload["prediction_schema"]["output_order"], alignment["output_order"])
            map_summary = {}
            for name, direction in (("sample_to_test", "sample_row_index -> original_test_row_index"),
                                    ("output_to_test", "output_row_index -> original_test_row_index")):
                values = alignment[name]
                count = len(values)
                self.assertEqual(count, expected["rows"]["test"])
                permutation = len(set(values)) == count and all(type(value) is int and 0 <= value < count for value in values)
                self.assertTrue(permutation, "resolved row map is not a full index permutation")
                digest = json_value_sha(values)
                declared = payload["provenance"]["row_mapping"][name]
                self.assertEqual(declared["sha256"], digest)
                self.assertEqual(declared["count"], count)
                map_summary[name] = {"direction": direction, "count": count, "sha256": digest,
                                     "is_permutation": permutation,
                                     "is_identity": all(index == value for index, value in enumerate(values))}
            projection = alignment["feature_projection"]
            projection_summary = {"train_feature_count": len(projection["train_order"]),
                                  "train_order_sha256": json_value_sha(projection["train_order"]),
                                  "test_indices_count": len(projection["test_indices"]),
                                  "test_indices_sha256": json_value_sha(projection["test_indices"]),
                                  "test_index_space": "full_test_header_including_identifier_columns"}
            metric_summary = {name: copy.deepcopy(payload["metric"][name]) for name in
                              ("name", "direction", "prediction_kind", "parameters", "label_policy", "target_scale", "finite_policy", "adapter_version")}
            self.assertLess(len(json.dumps(payload["provenance"]["row_mapping"])), 10_000, "payload must summarize row maps")
            self.assertEqual(hashes(paths), before)
            if csv_before is None:
                self.assertFalse(old_csv.exists())
            else:
                self.assertEqual((sha(old_csv), old_csv.stat().st_mtime_ns), csv_before)
            ACTUAL_INPUTS.append({"dataset": label, "status": "PASS_READ_ONLY_CONTRACT_ONLY",
                                  "source_sha256_before": before, "source_sha256_stable": True,
                                  "feature_count": expected["features"], "row_counts": expected["rows"],
                                  "resolved_metric": metric_summary, "output_order": alignment["output_order"],
                                  "output_order_evidence": copy.deepcopy(payload["provenance"]["row_mapping"].get("order_evidence", [])),
                                  "row_mapping_summary": map_summary, "feature_projection_summary": projection_summary,
                                  "index_hash_encoding": "UTF-8 JSON; ensure_ascii=False; sort_keys=True; compact separators; no newline",
                                  "raw_identifiers_or_target_rows_included": False,
                                  "prediction_writer_or_quality_verified": False})

    def test_actual_public_regression(self):
        self.actual_dataset("regression", "Регрессия", {"target": "site_eui", "kind": "regression", "metric": "rmse", "features": 62,
                            "rows": {"train": 53308, "test": 22449, "sample_submission": 22449}})

    def test_actual_public_classification(self):
        self.actual_dataset("classification", "Многоклассовая классификация", {"target": "attack_cat", "kind": "classification", "metric": "macro_f1", "features": 42,
                            "rows": {"train": 87670, "test": 41166, "sample_submission": 41166}})


def main():
    global CONTRACTS, SCHEMAS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    sources = (*ROOT_FILES, "scripts/check_h023_contract.py")
    before = {name: sha(ROOT / name) for name in sources}
    receipt = {"phase": "H02.3", "status": "NOT_RUN", "python": platform.python_version(), "executable": sys.executable,
               "platform": platform.platform(), "source_sha256": before, "expected_requirements_sha256": EXPECTED_REQUIREMENTS_SHA,
               "scope": "TaskContract/resolver/schema/identifier alignment/sidecars/selective-copy CLI only",
               "model_training_executed": False, "live_api_called": False, "package_installation_executed": False,
               "profiling_or_metric_evaluation_executed": False, "docker_or_os_boundary_tested": False,
               "official_platform_image_verified": False, "h03_or_full_agent_accepted": False,
               "child_environment_is_controlled_no_provider_configuration_read": True,
               "notes": ["Synthetic feature values are fixture data, not training results.",
                         "Actual data checks inspect contracts/IDs read-only and never publish in original folders.",
                         "Missing ignored public sources are explicit SKIP, never a simulated public PASS.",
                         "Production schema validation may use its installed jsonschema dependency; the runner uses stdlib unittest.",
                         "Cooperative expiry does not prove a hard timeout or a sandbox."]}
    if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
        receipt.update(status="BLOCKED_WRONG_CHECK_ENVIRONMENT", test_methods_run=0, behavior_cases_checked=0, cli_invocations=0)
        code = 2
    else:
        sys.path.insert(0, str(ROOT))
        try:
            CONTRACTS = importlib.import_module("aegml_contracts")
            SCHEMAS = importlib.import_module("aegml_schemas")
            for module in (CONTRACTS, SCHEMAS):
                if Path(module.__file__).resolve() != (ROOT / (module.__name__ + ".py")).resolve():
                    raise RuntimeError("unexpected project module path")
            result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContractChecks))
            after = {name: sha(ROOT / name) for name in sources}
            stable = before == after
            passed = result.wasSuccessful() and stable
            all_actual = len(ACTUAL_INPUTS) == 2 and all(item["status"] == "PASS_READ_ONLY_CONTRACT_ONLY" for item in ACTUAL_INPUTS)
            status = "FAIL_H02_3_CONTRACT_CHECK"
            if passed:
                status = "PASS_H02_3_CONTRACT_ONLY" if all_actual else "PASS_SYNTHETIC_H02_3_PUBLIC_INPUTS_SKIPPED"
            receipt.update(status=status,
                           test_methods_run=result.testsRun, behavior_cases_checked=len(CASES),
                           behavior_cases_passed=sum(case["status"] == "PASS" for case in CASES),
                           behavior_cases_skipped=sum(case["status"] == "SKIP" for case in CASES),
                           unittest_skips=[{"test": test.id(), "reason": reason} for test, reason in result.skipped],
                           cli_invocations=len(COMMANDS), cases=CASES, commands=COMMANDS, actual_input_checks=ACTUAL_INPUTS,
                           all_requested_actual_inputs_verified=all_actual,
                           unittest_failures=[{"test": test.id(), "detail": redact(detail)} for test, detail in result.failures],
                           unittest_errors=[{"test": test.id(), "detail": redact(detail)} for test, detail in result.errors],
                           source_unchanged_during_check=stable, source_sha256_after=after)
            code = 0 if passed else 1
        except Exception as exc:
            receipt.update(status="FAIL_CHECK_SETUP", error_type=type(exc).__name__, test_methods_run=0,
                           behavior_cases_checked=len(CASES), cli_invocations=len(COMMANDS))
            code = 1
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(redact(receipt), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "receipt": str(args.receipt), "test_methods_run": receipt["test_methods_run"],
                      "behavior_cases_checked": receipt["behavior_cases_checked"], "cli_invocations": receipt["cli_invocations"]}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
