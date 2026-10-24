# AegML

A machine learning agent for tabular regression and classification. We built AegML to participate in the AutoML track of the Alfa-Budushchee 2026 hackathon.

The agent takes a task description and CSV files, validates the inputs, prepares features, trains a model, and writes predictions to `submission.csv`.

## What it does

- Reads the task description, feature dictionary, and submission format.
- Checks the target column, data types, and input consistency.
- Handles numeric, categorical, and text features, including missing values.
- Creates training and validation splits, including temporal splits.
- Trains and evaluates a CatBoost baseline.
- Saves predictions and a run report.

Feature transformations are fitted on the training split. Validation data is used for evaluation.

## The benchmark tasks

| Task | Prediction | Main metric |
| --- | --- | --- |
| Regression | Annual building energy use per unit of floor area (`site_eui`) | RMSE: lower is better |
| Classification | Network traffic category, including normal traffic and different attack types (`attack_cat`) | Macro F1: higher is better |

The challenge was to build one agent that could understand a new task, prepare data, run experiments, and produce a valid submission within a CPU and time budget. The building and network datasets were benchmarks for that workflow.

### Why this is relevant to a bank

A banking ML team repeatedly works through data checks, feature engineering, model comparisons, validation, and error analysis. An agent that records experiments and proposes the next useful test could reduce manual work in that cycle. Potential applications include cybersecurity analysis, forecasting, and research on transaction anomalies or risk. These would require their own data, controls, and validation; this project evaluated the competition benchmarks.

## Research explored

During the hackathon, we explored CatBoost, LightGBM, XGBoost, ExtraTrees, and ensembles, analysed prediction errors, and tested additional features.

We also explored a research loop with Qwen: propose a change, run an experiment, and compare it with the previous candidate. Technical notes describe this approach. The default CLI in the published version runs the CatBoost baseline; it does not automatically run the Qwen research loop.

Our experiments included piecewise-linear Ridge features, directional log-ratios, repeated-context graphs, conditional-mean models, class weighting, a soft F1 objective, kernel approximations, and a neural-network blend. We tracked both corrected errors and previously correct predictions that became worse.

### Selected local measurements

- On a repeatedly used regression validation split, the fixed CatBoost/ExtraTrees composition reduced RMSE from **31.8577 to 31.2119**, equivalent to **4.0133% less squared error**. All 9,927 predictions covered by the existing history rule stayed unchanged.
- The latest local classification reference was **Macro F1 0.66943**. A separate three-fold training-side protocol used a **0.618898** control; its results are reported separately rather than compared directly with that reference.

These are local experimental measurements. The new regression composition is a research candidate, and the measurements do not establish performance on an untouched test set.

[Research notes: formulas, evaluation protocols, experiments, and findings](docs/RESEARCH.md).

## Running AegML

Use Python 3.12 and the dependencies in [requirements.txt](requirements.txt).

In the competition environment:

```bash
python3 solution.py task.md
```

Run from the task directory. Data paths are specified in `task.md`, and `submission.csv` is written to the working directory.

[Local setup and usage](docs/READ_FIRST.md).

## Repository layout

| Files | Purpose |
| --- | --- |
| `solution.py` | Entry point |
| `aegml_input.py`, `aegml_contracts.py` | Task parsing and input validation |
| `aegml_profile.py`, `aegml_preprocessing.py` | Data profiling and feature preparation |
| `aegml_baseline.py`, `aegml_estimators.py` | Baseline training |
| `aegml_metrics.py`, `aegml_validation.py` | Evaluation and validation |
| `aegml_submission.py` | Prediction validation and CSV output |
| `tests/` | Component checks |
| `docs/` | Technical notes and development documentation |

Competition data, API keys, and trained model weights are kept outside the repository.
