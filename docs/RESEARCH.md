# Research notes

AegML was developed for the AutoML track of Alfa-Budushchee 2026.
The task was to turn a task description and data files into a valid prediction CSV,
using the same code across unfamiliar tabular tasks.
We explored both model engineering and an experiment loop that could retain previous results.

## The two benchmark tasks

**Regression:** predict `site_eui`, annual building energy use per unit of floor area.
This is an intensity target, not total building energy consumption.
The public training table has 62 features, an identifier, and the target.

**Classification:** predict `attack_cat`, a network intrusion category.
The table has 42 features, an identifier, and the target.
These are benchmark datasets, not bank customer, transaction, or credit data.

## What the metrics mean

For numeric targets, root mean squared error is

$$
\operatorname{RMSE}=\sqrt{\frac{1}{n}\sum_{i=1}^{n}(y_i-\hat y_i)^2}.
$$

Lower is better. Squared error makes large misses particularly influential.
We also tracked the sum of squared errors, $\operatorname{SSE}=\sum_i(y_i-\hat y_i)^2$.
On the same rows, relative SSE reduction is $1-\operatorname{SSE}_E/\operatorname{SSE}_C$.
An SSE reduction is not the same percentage reduction in RMSE.

For classification, each class has its own precision, recall, and F1:

$$
P_c=\frac{TP_c}{TP_c+FP_c},\qquad
R_c=\frac{TP_c}{TP_c+FN_c},\qquad
F1_c=\frac{2TP_c}{2TP_c+FP_c+FN_c}.
$$

$$
\operatorname{MacroF1}=\frac{1}{K}\sum_{c=1}^{K}F1_c.
$$

Undefined class scores use the evaluation protocol's zero-score convention.
Higher is better. Each class contributes equally, so better accuracy can coexist with worse Macro F1.
We therefore inspected class confusion counts and fold changes alongside the pooled score.

## Three evaluation settings that must remain separate

1. **Training-side regression research:** 22,054 authorized training rows,
   with two chronological prediction folds of 9,058 and 10,879 rows.
   This gives 19,937 out-of-fit predictions; the earliest 2,117 rows have no past fold.
2. **Training-side classification research:** 56,108 authorized rows and three OOF folds.
   The cached weighted XGBoost control had Macro F1 **0.618898151982**.
3. **Separate task-specific local inner splits:** the RC3 references measured RMSE **31.85772288**
   and classification F1 **0.66942945**. These splits were repeatedly used during research.

The classification values in settings 2 and 3 are not directly comparable.
These are local research measurements, not platform scores or an untouched final test.
Repeated comparison makes an inner split adaptive, even when each model fit excludes its evaluation labels.

## Regression: complementary models and selective composition

On the chronological training-side protocol, the CatBoost control had RMSE **52.345351755**.
An equal mean of CatBoost and ExtraTrees reached **50.870374917**, with **5.55616%** less SSE.
The pair was chosen after four-family results: this was exploratory and adaptive.
The 0.5 weight was fixed before combining cached predictions.

The separate current-split experiment kept the existing history predictions on covered rows.
This fresh paired transfer was preregistered; only cold rows used the CatBoost/ExtraTrees mean:

$$
\hat y(x)=
\begin{cases}
C_A^{\mathrm{final}}(x), & \text{if the frozen history rule covers }x,\\
\tfrac12 C_A^{\mathrm{raw}}(x)+\tfrac12 ET_A(x), & \text{otherwise}.
\end{cases}
$$

Here $C_A^{\mathrm{final}}$ includes the existing history procedure, learned only from permitted training data.
Across 12,946 inner rows, RMSE changed from **31.85772288** to **31.21190003**,
a **4.0133%** SSE reduction. All 9,927 warm predictions stayed bit-exact;
the remaining 3,019 rows were cold.
This was a research candidate, not an automatic change to the published CLI or a platform result.

## Distributional conditional means

We also tested a classifier over target bins with conditional mean regressors.
For a bin variable $B$ defined using training-only quantiles,

$$
\mathbb E[Y\mid X=x]
=\sum_b P(B=b\mid X=x)\,\mathbb E[Y\mid X=x,B=b].
$$

The identity requires conditional arithmetic means, not constant bin representatives or naive inverse-log predictions.
Our fixed cuts were the training median and 90th percentile.
An unweighted classifier estimated bin probabilities; a shared masked-output regressor estimated the means.
Its chronological RMSE **51.167601113** improved on CatBoost alone, but not on the stronger Cat/ET mean.
A separate current-split transfer measured **31.48599861**, worse than **31.21190003**.
The mathematical identity did not guarantee that finite fitted components would transfer well.

## Other structural methods explored

**Ridge-hat:** a piecewise-linear basis with quantile knots fitted only on training features,
followed by an L2-regularized linear model:

$$
\hat\beta=\arg\min_\beta\|y_A-\Phi_A\beta\|_2^2+\lambda\|\beta\|_2^2.
$$

**Directional unit geometry:** compatible nonnegative feature pairs received log-ratio,
log-sum, and balance channels, such as $\log(1+a)-\log(1+b)$ and $(a-b)/(1+a+b)$.
The goal was to expose useful relationships without replacing original values or missing indicators.

**Repeated-context graphs:** X-only matching explored repeated entities across contexts.
Each entity-period pair required a unique query context; at least two entity bridges had to agree on one component.
Query labels did not create links.
These were guarded matching hypotheses, not verified real-world entity identifiers.

## Classification: improvements need more than one pooled number

The Soft F1 experiment reached **0.621087716248** against the OOF control's **0.618898151982**,
but did not satisfy the fixed class/fold safeguards.
A soft surrogate is $L_{\mathrm{soft}}=1-\frac1K\sum_c\frac{2\sum_i y_{ic}p_{ic}}{\sum_i y_{ic}+\sum_i p_{ic}}$.
The research combined a soft term with cross-entropy; it is distinct from discrete Macro F1 after argmax.
Other tested candidates were not retained: deeper XGBoost with 1,000 trees/depth 8 (**0.595697**),
an RBF kernel approximation (**0.435886**), and the fixed MLP probability blend (**0.587490**).
These results belong to the training-side OOF setting, not the separate **0.66942945** inner evaluation.

## What the diagnostics revealed

In regression, the worst 1% of prediction errors contributed **53.24%** of SSE.
That identifies where error concentrates; it does not prove that those cases are predictable from X.
Better average error can also hide harm to a previously accurate subgroup.

In classification, 1,336 exact-X groups contained conflicting labels across 9,402 rows.
Such training-snapshot conflicts do not establish a Bayes error bound or a test-set quality ceiling.
Across all 56,108 cached control predictions there were 10,786 errors:
7,654 had the true class ranked second, 1,059 third, and 2,073 fourth or lower.
Those ranks use known labels for diagnosis; they are not an attainable oracle classifier.

## Experimental discipline and scope

Preprocessing statistics were fitted on A; held-out features were transformed without fitting on them.
Chronological features used permitted past information, and training-side choices excluded held-out labels.
Predictions and their row mappings were sealed before evaluator feedback.
Held-out labels were not inputs to feature fitting, model fitting, or per-row routing.
No external answer files were used. Reused validation feedback remains explicitly adaptive.
SPQP1 and PTS1 remained source-only proposals: their proposed training trials were cancelled before execution.
They are not reported as tested improvements.

## Why this could matter to a bank

The potential value is the experiment workflow: repeatable task intake, model comparisons,
error analysis, and less manual iteration for analysts.
Related applications could include cybersecurity traffic analysis, transaction anomaly research,
demand forecasting, and support for risk analysis, using appropriate bank-specific data and validation.
These are possible applications, not claims of a deployed banking system or customer-data evaluation.

See the [project overview](../README.md) and [local usage guide](READ_FIRST.md).
