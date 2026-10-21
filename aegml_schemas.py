"""Embedded task.v1 schemas; validation performs no I/O, imports, or code from inputs.

jsonschema is imported only inside validate_task_contract, after the entrypoint
has started its common timer. These contracts express intended policy; they do
not verify OS isolation, model quality, or a completed train/validation split.
"""

from __future__ import annotations

import math
from pathlib import PurePosixPath, PureWindowsPath


_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 100_000
_MAX_STRING_CHARACTERS = 1_000_000
_MAX_INTEGER_BITS = 4096

_METRIC_RULES = {
    "rmse": ("regression", "minimize", "numeric"),
    "mae": ("regression", "minimize", "numeric"),
    "accuracy": ("classification", "maximize", "label"),
    "macro_f1": ("classification", "maximize", "label"),
    "weighted_f1": ("classification", "maximize", "label"),
    "binary_f1": ("classification", "maximize", "label"),
    "log_loss": ("classification", "minimize", "probability"),
    "roc_auc": ("classification", "maximize", "probability"),
}

_NONBLANK_STRING = {"type": "string", "minLength": 1, "pattern": r"\S"}
_LABEL = {"anyOf": [_NONBLANK_STRING, {"type": "number"}]}
_JSON_VALUE = {
    "anyOf": [
        {"type": "null"},
        {"type": "boolean"},
        {"type": "number"},
        {"type": "string"},
        {"type": "array", "items": {"$ref": "#/$defs/json_value"}},
        {"type": "object", "additionalProperties": {"$ref": "#/$defs/json_value"}},
    ]
}
_JSON_OBJECT = {
    "type": "object",
    "additionalProperties": {"$ref": "#/$defs/json_value"},
}
_NAMES = {
    "type": "array",
    "items": _NONBLANK_STRING,
    "uniqueItems": True,
}
_ONE_TARGET = {**_NAMES, "minItems": 1, "maxItems": 1}
_NONEMPTY_NAMES = {**_NAMES, "minItems": 1}

_METRIC_PROPERTIES = {
    "name": {"enum": list(_METRIC_RULES)},
    "direction": {"enum": ["minimize", "maximize"]},
    "prediction_kind": {"enum": ["numeric", "label", "probability"]},
    "parameters": _JSON_OBJECT,
    "label_policy": {"anyOf": [_NONBLANK_STRING, {"type": "null"}]},
    "positive_label": {"anyOf": [_LABEL, {"type": "null"}]},
    "class_order": {
        "anyOf": [
            {"type": "array", "items": _LABEL, "uniqueItems": True},
            {"type": "null"},
        ]
    },
    "target_scale": _NONBLANK_STRING,
    "finite_policy": {"const": "finite_only"},
    "adapter_version": _NONBLANK_STRING,
    "evidence": {"type": "array", "items": _JSON_OBJECT},
}
_METRIC_CONDITIONS = [
    {
        "if": {"properties": {"name": {"const": name}}, "required": ["name"]},
        "then": {
            "properties": {
                "direction": {"const": direction},
                "prediction_kind": {"const": kind},
            }
        },
    }
    for name, (_, direction, kind) in _METRIC_RULES.items()
]
_METRIC_CONDITIONS.extend(
    [
        {
            "if": {
                "properties": {"name": {"enum": ["binary_f1", "roc_auc"]}},
                "required": ["name"],
            },
            "then": {"properties": {"positive_label": _LABEL}},
        },
        {
            "if": {
                "properties": {"name": {"const": "log_loss"}},
                "required": ["name"],
            },
            "then": {
                "properties": {
                    "class_order": {
                        "type": "array",
                        "items": _LABEL,
                        "uniqueItems": True,
                        "minItems": 2,
                    }
                }
            },
        },
    ]
)
_METRIC_OBJECT = {
    "type": "object",
    "required": list(_METRIC_PROPERTIES),
    "additionalProperties": False,
    "properties": _METRIC_PROPERTIES,
    "allOf": _METRIC_CONDITIONS,
}
_SHARED_DEFS = {
    "json_value": _JSON_VALUE,
    "metric_contract": _METRIC_OBJECT,
}

METRIC_CONTRACT_SCHEMA = {
    "$schema": _DIALECT,
    "$defs": _SHARED_DEFS,
    **_METRIC_OBJECT,
}

_INPUT_PROPERTIES = {
    role: _NONBLANK_STRING
    for role in ("train", "test", "data_dictionary", "sample_submission")
}
_PREDICTION_PROPERTIES = {
    "columns": _NONEMPTY_NAMES,
    "id_columns": _NAMES,
    "target_columns": _ONE_TARGET,
    "kind": {"enum": ["numeric", "label", "probability"]},
    "output_order": {"enum": ["test", "sample"]},
    "id_policy": _JSON_OBJECT,
}
_SPLIT_PROPERTIES = {
    "status": {"const": "NOT_BUILT"},
    "strategy": {"const": "deferred_to_H03"},
    "source": {"const": "project_policy"},
}
_BUILT_SPLIT_PROPERTIES = {
    "status": {"const": "BUILT"},
    "strategy": {"enum": ["temporal", "stratified", "explicit"]},
    "source": {"const": "trusted_validation.v1"},
    "policy_id": _NONBLANK_STRING,
    "partition_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "schema_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "train_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "train_rows": {"type": "integer", "minimum": 3, "maximum": 2_000_000},
    "seed": {"type": "integer", "minimum": 0, "maximum": 4_294_967_295},
    "row_counts": {
        "type": "object", "additionalProperties": False,
        "required": ["fit", "inner", "outer"],
        "properties": {name: {"type": "integer", "minimum": 1, "maximum": 2_000_000}
                       for name in ("fit", "inner", "outer")},
    },
}
_CONSTRAINT_PROPERTIES = {
    "time_limit_seconds": {
        "type": "number",
        "exclusiveMinimum": 0,
        "maximum": 10_800,
    },
    "threads": {"type": "integer", "minimum": 1, "maximum": 8},
    "no_network_except_provider": {"type": "boolean"},
}
_PROVENANCE_PROPERTIES = {
    name: {"$ref": "#/$defs/json_value"}
    for name in ("task", "files", "fields", "source_sha256", "row_mapping")
}
_TASK_PROPERTIES = {
    "schema_version": {"const": "task.v1"},
    "run_id": _NONBLANK_STRING,
    "task_path": _NONBLANK_STRING,
    "input_paths": {
        "type": "object",
        "required": list(_INPUT_PROPERTIES),
        "additionalProperties": False,
        "properties": _INPUT_PROPERTIES,
    },
    "output_path": _NONBLANK_STRING,
    "target_columns": _ONE_TARGET,
    "id_columns": _NAMES,
    "feature_columns": _NONEMPTY_NAMES,
    "task_type": {"enum": ["regression", "classification"]},
    "metric": {"$ref": "#/$defs/metric_contract"},
    "prediction_schema": {
        "type": "object",
        "required": list(_PREDICTION_PROPERTIES),
        "additionalProperties": False,
        "properties": _PREDICTION_PROPERTIES,
    },
    "split_policy": {
        "oneOf": [
            {"type": "object", "required": list(properties),
             "additionalProperties": False, "properties": properties}
            for properties in (_SPLIT_PROPERTIES, _BUILT_SPLIT_PROPERTIES)
        ],
    },
    "constraints": {
        "type": "object",
        "required": list(_CONSTRAINT_PROPERTIES),
        "additionalProperties": False,
        "properties": _CONSTRAINT_PROPERTIES,
    },
    "provenance": {
        "type": "object",
        "required": list(_PROVENANCE_PROPERTIES),
        "additionalProperties": False,
        "properties": _PROVENANCE_PROPERTIES,
    },
    "conflicts": {"type": "array", "maxItems": 0},
}
TASK_CONTRACT_SCHEMA = {
    "$schema": _DIALECT,
    "$defs": _SHARED_DEFS,
    "type": "object",
    "required": list(_TASK_PROPERTIES),
    "additionalProperties": False,
    "properties": _TASK_PROPERTIES,
}


class SchemaError(Exception):
    """A fixed public code; no payload value or validator message is exposed."""

    code = "invalid_task_contract"

    def __init__(self) -> None:
        super().__init__(self.code)


def _require_finite_json(payload: object) -> None:
    """Bounded walk rejects non-JSON objects and non-finite numbers globally."""
    stack = [(payload, 0)]
    nodes = 0
    characters = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if depth > _MAX_JSON_DEPTH or nodes > _MAX_JSON_NODES:
            raise SchemaError()
        kind = type(value)
        if value is None or kind is bool:
            continue
        if kind is int:
            if value.bit_length() > _MAX_INTEGER_BITS:
                raise SchemaError()
        elif kind is float:
            if not math.isfinite(value):
                raise SchemaError()
        elif kind is str:
            characters += len(value)
        elif kind is list:
            if len(value) > _MAX_JSON_NODES - nodes:
                raise SchemaError()
            stack.extend((item, depth + 1) for item in value)
        elif kind is dict:
            if len(value) > _MAX_JSON_NODES - nodes:
                raise SchemaError()
            for name, item in value.items():
                if type(name) is not str:
                    raise SchemaError()
                characters += len(name)
                stack.append((item, depth + 1))
        else:
            raise SchemaError()
        if characters > _MAX_STRING_CHARACTERS:
            raise SchemaError()


def _require_cross_field_consistency(payload: dict) -> None:
    metric = payload["metric"]
    split = payload["split_policy"]
    if split["status"] == "BUILT":
        if (type(split["train_rows"]) is not int or type(split["seed"]) is not int
                or any(type(n) is not int for n in split["row_counts"].values())
                or sum(split["row_counts"].values()) != split["train_rows"]
                or split["train_sha256"] != payload["provenance"]["source_sha256"].get("train")
                or split["train_rows"] != payload["provenance"]["row_mapping"]["row_counts"]["train"]):
            raise SchemaError()
    expected_type, expected_direction, expected_kind = _METRIC_RULES[metric["name"]]
    if (
        payload["task_type"] != expected_type
        or metric["direction"] != expected_direction
        or metric["prediction_kind"] != expected_kind
    ):
        raise SchemaError()

    targets = payload["target_columns"]
    identifiers = payload["id_columns"]
    features = payload["feature_columns"]
    if (
        set(targets) & set(identifiers)
        or set(targets) & set(features)
        or set(identifiers) & set(features)
    ):
        raise SchemaError()
    prediction = payload["prediction_schema"]
    if (
        prediction["target_columns"] != targets
        or prediction["id_columns"] != identifiers
        or prediction["kind"] != expected_kind
    ):
        raise SchemaError()
    if (
        expected_kind != "probability" or metric["name"] == "roc_auc"
    ) and set(prediction["columns"]) != set(identifiers + targets):
        raise SchemaError()

    # Probability class-column mapping is a separate explicit contract. Do not
    # infer it by concatenating the target name or stringifying class labels.
    order = metric["class_order"]
    positive = metric["positive_label"]
    if metric["name"] in ("binary_f1", "roc_auc"):
        if positive is None or (order is not None and len(order) != 2):
            raise SchemaError()
        if order is not None and positive not in order:
            raise SchemaError()
    if metric["name"] == "log_loss" and (order is None or len(order) < 2):
        raise SchemaError()
    if metric["name"] == "log_loss" and (
        not set(identifiers).issubset(prediction["columns"])
        or len(prediction["columns"]) != len(identifiers) + len(order)
    ):
        raise SchemaError()
    if metric["name"] == "macro_f1" and (
        metric["label_policy"] != "sklearn_labels_none"
        or metric["parameters"].get("average") != "macro"
        or "labels" not in metric["parameters"]
        or metric["parameters"]["labels"] is not None
    ):
        raise SchemaError()

    # JSON Schema permits 1.0 as an integer; the operational thread count must
    # be an actual JSON/Python int, not a bool or float.
    if type(payload["constraints"]["threads"]) is not int:
        raise SchemaError()
    for path in payload["input_paths"].values():
        if "://" in path or not (
            PurePosixPath(path).is_absolute() or PureWindowsPath(path).is_absolute()
        ):
            raise SchemaError()


def validate_task_contract(payload: object) -> None:
    """Validate task.v1 shape and consistency, returning None or a static error."""
    try:
        _require_finite_json(payload)
        from jsonschema import Draft202012Validator

        if not Draft202012Validator(TASK_CONTRACT_SCHEMA).is_valid(payload):
            raise SchemaError()
        _require_cross_field_consistency(payload)
    except Exception:
        raise SchemaError() from None
