# Running AegML locally

The entry point is `solution.py`. The published version trains a CatBoost baseline for tabular regression or classification.

## Setup

Use Linux and Python 3.12. From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The task description and CSV files must follow the track's task format. `task.md` specifies data paths, the target column, the evaluation metric, and the prediction format. A feature dictionary and sample submission are also used.

## Run

Change to the task directory and run the code from the repository:

```bash
cd /path/to/task
/path/to/AegMLAI-agent/.venv/bin/python /path/to/AegMLAI-agent/solution.py task.md
```

Replace the example paths with your own. The working directory matters: this is where `submission.csv` is created.

In the competition environment, the solution code is placed alongside the task description:

```bash
python3 solution.py task.md
```

The agent prints a JSON run report with the status, evaluation, and prediction file details. Input format errors are also reported there.

## Reading the code

1. `solution.py` — execution flow and error handling.
2. `aegml_input.py`, `aegml_contracts.py` — task description and input files.
3. `aegml_preprocessing.py` — feature preparation.
4. `aegml_baseline.py`, `aegml_estimators.py` — model training.
5. `aegml_metrics.py`, `aegml_validation.py` — evaluation.
6. `aegml_submission.py` — output CSV.

## Development notes

The `docs/` directory contains architecture, validation, experiment, and Qwen research notes. Development logs describe the code versions they were written for. Qwen is a research direction; the published default CLI runs the CatBoost baseline.

- [Mathematics and validation](MATHEMATICS_AND_VALIDATION.md)
- [Pipeline inputs and outputs](BACKEND_CONTRACT.md)
- [Qwen research loop](QWEN_HARNESS_DESIGN.md)
- [ML research sources](RESEARCH_SOURCES.md)
