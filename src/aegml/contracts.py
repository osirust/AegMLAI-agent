"""Small versioned contracts independent of a vendor or an ML framework."""

import json
from dataclasses import asdict, dataclass

SCHEMA_VERSION = "1.0"


def _text(value: object, field: str, maximum: int = 8000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field}: нужна непустая строка не длиннее {maximum} символов")
    return value


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    goal: str
    task_type: str = "unknown"
    target_column: str | None = None
    metric: str | None = None
    seed: int = 42

    @classmethod
    def from_dict(cls, data: object) -> "TaskSpec":
        if not isinstance(data, dict):
            raise ValueError("task.json должен содержать JSON объект")
        unknown = set(data) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError("Неизвестные поля task.json: " + ", ".join(sorted(unknown)))
        for name in ("task_id", "goal"):
            _text(data.get(name), name)
        task = cls(**data)
        if not isinstance(task.task_type, str) or task.task_type not in {"unknown", "classification", "regression"}:
            raise ValueError("task_type: unknown, classification или regression")
        for name in ("target_column", "metric"):
            value = getattr(task, name)
            if value is not None:
                _text(value, name, 256)
        if type(task.seed) is not int or not 0 <= task.seed < 2**32:
            raise ValueError("seed: требуется целое число от 0 до 2**32-1")
        return task

    def to_dict(self) -> dict:
        return asdict(self)


def parse_plan(raw: str) -> dict:
    """Accept only the documented JSON object, never execute its content."""
    try:
        plan = json.loads(raw)
    except (json.JSONDecodeError, TypeError, RecursionError):
        raise ValueError("LLM должна вернуть JSON объект плана без Markdown") from None
    keys = {"summary", "steps", "assumptions", "questions"}
    if not isinstance(plan, dict) or set(plan) != keys:
        raise ValueError("План должен содержать только summary, steps, assumptions, questions")
    _text(plan["summary"], "summary")
    for field in ("steps", "assumptions", "questions"):
        items = plan[field]
        if not isinstance(items, list) or len(items) > 30:
            raise ValueError(f"{field}: требуется список до 30 строк")
        if field == "steps" and not items:
            raise ValueError("steps: нужен хотя бы один шаг")
        for item in items:
            _text(item, field, 2000)
    return plan
