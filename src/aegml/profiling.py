"""Bounded CSV inspection. No inference about feature types or ML quality."""

import csv
import hashlib
import io
from pathlib import Path

MAX_CSV_BYTES = 20 * 1024 * 1024


def profile_csv(path: Path, target_column: str | None = None) -> tuple[dict, str]:
    with path.open("rb") as source:
        raw = source.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise ValueError("CSV превышает лимит 20 MiB для стартового профилировщика")
    digest = hashlib.sha256(raw).hexdigest()
    try:
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        header = next(reader, None)
        if not header or any(not name.strip() for name in header):
            raise ValueError("CSV должен содержать непустые названия колонок")
        if len(header) != len(set(header)):
            raise ValueError("В CSV повторяются названия колонок")
        if target_column is not None and target_column not in header:
            raise ValueError("target_column отсутствует в заголовке CSV")
        missing = [0] * len(header)
        rows = 0
        for row in reader:
            if len(row) != len(header):
                raise ValueError(f"CSV: запись {rows + 2} имеет неверное число полей")
            rows += 1
            for index, value in enumerate(row):
                missing[index] += not value.strip()
    except (UnicodeDecodeError, csv.Error):
        raise ValueError("Нужен корректный CSV в UTF-8 с разделителем запятая") from None
    if rows == 0:
        raise ValueError("CSV содержит заголовок, но не содержит записей")
    return {
        "row_count": rows,
        "column_count": len(header),
        "columns": [
            {"name": name, "missing_count": missing[index]}
            for index, name in enumerate(header)
        ],
        "missing_definition": "empty or whitespace-only cell; no semantic NA inference",
    }, digest
