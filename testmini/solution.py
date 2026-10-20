"""Technical probe: required API gate by default, not the AutoResearch agent.

Run: python solution.py [task.md]
Only the Python standard library is used. Output is next to task.md.
"""

import csv
import hashlib
import json
import math
import os
import platform
import re
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from http.client import HTTPException
from itertools import zip_longest
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ProbeError(ValueError):
    pass


def event(name, **values):
    print(json.dumps({"probe": "testmini-v3", "event": name, **values}, ensure_ascii=False), flush=True)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def probe_api():
    """One bounded request; never store credentials or execute the response."""
    names = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL")
    settings = {name: os.environ.get(name, "").strip() for name in names}
    missing = [name for name in names if not settings[name]]
    if len(missing) == len(names):
        return {"status": "skipped_not_configured", "attempted": False, "missing": missing}
    if missing:
        return {"status": "configuration_error", "attempted": False, "missing": missing}
    try:
        address = urlsplit(settings["OPENAI_BASE_URL"])
        local_http = address.scheme == "http" and address.hostname in {"localhost", "127.0.0.1", "::1"}
        if (address.scheme != "https" and not local_http) or not address.netloc or address.username is not None or address.password is not None or address.query or address.fragment:
            return {"status": "configuration_error", "attempted": False, "reason": "invalid_base_url"}
        url = settings["OPENAI_BASE_URL"].rstrip("/") + "/chat/completions"
        payload = json.dumps({"model": settings["OPENAI_MODEL"], "messages": [
            {"role": "user", "content": "Connectivity check only. Reply with OK."}
        ], "max_tokens": 128}).encode("utf-8")
        request = Request(url, data=payload, headers={
            "Authorization": "Bearer " + settings["OPENAI_API_KEY"],
            "Content-Type": "application/json",
        }, method="POST")
    except (ValueError, UnicodeError):
        return {"status": "configuration_error", "attempted": False, "reason": "invalid_configuration"}
    try:
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                return {"status": "invalid_response", "attempted": True, "reason": "response_too_large"}
            result = json.loads(raw)
        choices = result.get("choices") if isinstance(result, dict) else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return {"status": "invalid_response", "attempted": True, "reason": "missing_choices"}
        message = choices[0].get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            return {"status": "invalid_response", "attempted": True, "reason": "missing_assistant_message"}
        has_content = isinstance(message.get("content"), str) and bool(message["content"].strip())
        has_reasoning = isinstance(message.get("reasoning_content"), str) and bool(message["reasoning_content"].strip())
        return {"status": "success" if has_content else "responded_without_final_text", "attempted": True,
                "assistant_content_received": has_content, "reasoning_received": has_reasoning}
    except HTTPError as error:
        code = error.code
        error.close()
        return {"status": "http_error", "attempted": True, "http_status": code}
    except (URLError, OSError, ValueError, UnicodeError, HTTPException, RecursionError) as error:
        return {"status": "request_failed", "attempted": True, "error_type": type(error).__name__}


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def resolve_input(directory, task, name):
    """Accept the stated nested path or the supplied flat layout, without guessing."""
    candidates = set()
    for reference in re.findall(r"`([^`\r\n]+\.csv)`", task):
        reference_path = Path(reference)
        if reference_path.name != name or reference_path.is_absolute():
            continue
        candidate = (directory / reference_path).resolve()
        if candidate.is_relative_to(directory) and candidate.is_file():
            candidates.add(candidate)
    flat = (directory / name).resolve()
    if flat.is_relative_to(directory) and flat.is_file():
        candidates.add(flat)
    if len(candidates) != 1:
        raise ProbeError(f"Нужен один однозначный входной файл {name}; найдено {len(candidates)}")
    result = candidates.pop()
    if result.stat().st_size > 512 * 1024 * 1024:
        raise ProbeError("Один CSV превышает предел технического пробника 512 MiB")
    return result


def header(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        fields = next(csv.reader(source, strict=True), None)
    if not fields or any(not field.strip() for field in fields) or len(fields) != len(set(fields)):
        raise ProbeError(f"Неверный или повторяющийся заголовок {path.name}")
    return fields


def rows(path, started):
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, strict=True)
        for number, row in enumerate(reader, 1):
            if number > 2_000_000:
                raise ProbeError("Превышен предел технического пробника 2 млн записей")
            if None in row or any(value is None for value in row.values()):
                raise ProbeError(f"Неверное число полей в {path.name}, запись {number}")
            if number % 1024 == 0 and time.monotonic() - started > 120:
                raise ProbeError("Превышен мягкий 120-секундный бюджет технического пробника")
            yield row


def run(task_path):
    started = time.monotonic()
    event("started", python=platform.python_version())
    if sys.version_info < (3, 11):
        raise ProbeError("Техническому пробнику нужен Python 3.11+; конкурс требует 3.12")
    task_path = task_path.resolve(strict=True)
    directory = task_path.parent
    api_mode = os.environ.get("TESTMINI_API_MODE", "required").strip().casefold()
    if api_mode not in {"required", "off"}:
        raise ProbeError("TESTMINI_API_MODE должен быть required или off")
    api_required = api_mode == "required"
    api_probe = probe_api() if api_required else {
        "status": "disabled_for_local_check", "attempted": False, "api_not_checked": True,
    }
    event("api_probe", required=api_required, **api_probe)
    if api_required and api_probe["status"] != "success":
        report = {
            "probe_version": "testmini-v3", "mode": "technical_probe_strict_api",
            "status": "failed_api_gate", "python": platform.python_version(),
            "api_required": True, "api_used": api_probe["attempted"], "api_probe": api_probe,
            "csv_created_in_this_run": False, "existing_submission_preserved": (directory / "submission.csv").exists(),
            "quality_assessed": False, "autoresearch_performed": False,
            "elapsed_seconds": round(time.monotonic() - started, 4),
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        (directory / "mini_diagnostics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        event("failed_api_gate", api_status=api_probe["status"], csv_created_in_this_run=False)
        raise ProbeError("Обязательная проверка API не пройдена: " + api_probe["status"])
    if task_path.stat().st_size > 512 * 1024:
        raise ProbeError("task.md превышает предел технического пробника 512 KiB")
    task = task_path.read_text(encoding="utf-8-sig")
    inputs = {name: resolve_input(directory, task, name) for name in (
        "train.csv", "test.csv", "data_dictionary.csv", "sample_submission.csv"
    )}
    original_sha = {name: digest(path) for name, path in inputs.items()}
    original_sha["task.md"] = digest(task_path)
    dictionary = list(rows(inputs["data_dictionary.csv"], started))
    if not dictionary or not {"feature", "role"}.issubset(dictionary[0]):
        raise ProbeError("В data_dictionary.csv нужны feature и role")
    target_fields = [row["feature"] for row in dictionary if row["role"].strip().casefold() == "target"]
    id_fields = [row["feature"] for row in dictionary if row["role"].strip().casefold() == "id"]
    if len(target_fields) != 1 or len(id_fields) != 1:
        raise ProbeError("Пробник поддерживает один target и один id из словаря")
    target, identifier = target_fields[0], id_fields[0]
    regression = bool(re.search(r"\bRMSE\b", task, re.I))
    classification = bool(re.search(r"\bMacro\s+F1\b", task, re.I))
    if regression == classification:
        raise ProbeError("Пробник ожидает одну метрику: RMSE или Macro F1")
    train_fields = header(inputs["train.csv"])
    test_fields = header(inputs["test.csv"])
    if target not in train_fields or identifier not in train_fields or identifier not in test_fields:
        raise ProbeError("Входы не согласованы с ролями target/id")
    if target in test_fields or set(test_fields) != set(train_fields) - {target}:
        raise ProbeError("Схемы train/test должны отличаться только наличием target")
    if header(inputs["sample_submission.csv"]) != [identifier, target]:
        raise ProbeError("В sample_submission ожидаются ровно id и target в указанном порядке")
    event("inputs_loaded", target=target, id_column=identifier,
          task_type="regression" if regression else "classification")
    count = 0
    total = 0.0
    labels = Counter()
    for row in rows(inputs["train.csv"], started):
        value = row[target]
        if not value.strip():
            raise ProbeError("В train отсутствует значение target")
        count += 1
        if regression:
            try:
                number = float(value)
            except ValueError:
                raise ProbeError("Нечисловой target в регрессии") from None
            if not math.isfinite(number):
                raise ProbeError("Неконечный target в регрессии")
            total += number
        else:
            labels[value] += 1
            if len(labels) > 10000:
                raise ProbeError("Слишком много классов для технического пробника")
    if not count:
        raise ProbeError("Обучающий CSV пуст")
    prediction = total / count if regression else min(labels, key=lambda label: (-labels[label], label))
    if regression and not math.isfinite(prediction):
        raise ProbeError("Получено неконечное среднее target")
    event("constant_baseline_fitted", train_rows=count, model="mean" if regression else "majority",
          features_used=False, quality_assessed=False)
    output = directory / "submission.csv"
    temporary_path = None
    test_count = 0
    identifiers = set()
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=directory,
                                         prefix=".testmini-", suffix=".tmp", delete=False) as stream:
            temporary_path = Path(stream.name)
            writer = csv.writer(stream)
            writer.writerow([identifier, target])
            for test_row, sample_row in zip_longest(rows(inputs["test.csv"], started), rows(inputs["sample_submission.csv"], started)):
                if test_row is None or sample_row is None:
                    raise ProbeError("Количество строк sample/test различается")
                row_id = test_row[identifier]
                if not row_id.strip() or row_id in identifiers:
                    raise ProbeError("Пустой или повторяющийся id в test")
                if sample_row[identifier] != row_id:
                    raise ProbeError("Порядок id sample/test различается")
                identifiers.add(row_id)
                test_count += 1
                writer.writerow([row_id, format(prediction, ".17g") if regression else prediction])
            if not test_count:
                raise ProbeError("Тестовый CSV пуст")
            stream.flush()
            os.fsync(stream.fileno())
        written = 0
        for prediction_row, test_row in zip_longest(rows(temporary_path, started), rows(inputs["test.csv"], started)):
            if prediction_row is None or test_row is None or prediction_row[identifier] != test_row[identifier]:
                raise ProbeError("Повторная проверка CSV: число/порядок строк не совпадает")
            if regression and not math.isfinite(float(prediction_row[target])):
                raise ProbeError("Повторная проверка CSV: неконечное предсказание")
            if classification and prediction_row[target] not in labels:
                raise ProbeError("Повторная проверка CSV: неизвестный класс")
            written += 1
        if written != test_count:
            raise ProbeError("Повторная проверка CSV: неверное число записей")
        if any(digest(inputs[name]) != original_sha[name] for name in inputs) or digest(task_path) != original_sha["task.md"]:
            raise ProbeError("Входные файлы изменились во время проверки")
        os.replace(temporary_path, output)
        temporary_path = None
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    event("submission_validated", rows=test_count, output="submission.csv", sha256=digest(output))
    report = {
        "probe_version": "testmini-v3", "mode": "technical_probe_strict_api", "status": "completed_format_only",
        "python": platform.python_version(), "task_type": "regression" if regression else "classification",
        "id_column": identifier, "target": target, "train_rows": count, "test_rows": test_count,
        "model": "constant_mean" if regression else "constant_majority", "features_used": False,
        "api_required": api_required, "api_used": api_probe["attempted"], "api_probe": api_probe,
        "csv_created_in_this_run": True,
        "autoresearch_performed": False, "quality_assessed": False,
        "third_party_imports_checked": False, "input_sha256": original_sha,
        "submission_sha256": digest(output), "output_columns": [identifier, target],
        "elapsed_seconds": round(time.monotonic() - started, 4),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (directory / "mini_diagnostics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    event("completed_format_only", diagnostics="mini_diagnostics.json", quality_assessed=False,
          api_status=api_probe["status"])


def main():
    try:
        run(Path(sys.argv[1] if len(sys.argv) > 1 else "task.md"))
        return 0
    except (ProbeError, OSError, UnicodeError, csv.Error, ValueError) as error:
        event("failed", error_type=type(error).__name__, message=str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
