import argparse
import json
import sys
from pathlib import Path

from .config import Settings
from .runner import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AegML: профиль CSV и план ML-эксперимента")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("run", help="Создать план без запуска обучения")
    command.add_argument("--task", required=True, type=Path)
    command.add_argument("--data", type=Path)
    command.add_argument("--output-dir", type=Path, default=Path("runs"))
    args = parser.parse_args(argv)
    try:
        result = run(args.task, args.data, args.output_dir, Settings.from_env())
    except (ValueError, OSError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "completed", "run_dir": str(result)}, ensure_ascii=False))
    return 0
