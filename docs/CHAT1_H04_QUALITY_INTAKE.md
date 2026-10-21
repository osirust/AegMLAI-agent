# H04: разбор предложений о первом качестве

Дата: 21.10.2026. **DOSSIER_COVERAGE_COMPLETE: prefix и запрошенное продолжение до END прочитаны. Исходное длинное сообщение byte-exact целиком не извлечено. Research-only, H04 не запущен.**

Прочитан полностью сохранённый prefix `runs/h03/h03-20261021T060520Z/chat1-h04-quality-prefix-TRUNCATED.txt`. Source message ID: `cad10ec9-eba0-43ba-a7e0-f7b5735d9c19`; это UUID сообщения, а не hash. Исходный текст содержит 20 000 символов; архив добавляет завершающий LF. SHA256 сохранённого файла: `861ac9f1c41c7661d6a73785dd2e4fab7fe90647bca35ed3e076c78e0545cef0`.

Продолжение полностью прочитано из `runs/h03/h03-20261021T060520Z/chat1-h04-quality-part2-END.txt`: source message ID `85e33a42-49eb-49ad-9fec-f2bfbed9ede9`, 6164 исходных символа и архивный LF; SHA256 файла `c9f2da0664621655c2a3b07c57df4891d3f47115fbf397f9fd584e8464f11843`. Оно заканчивает раздел4, содержит раздел5 и явный END. Покрытие содержания запроса завершено этими двумя частями; их конкатенация не объявляется byte-exact копией первоначального длинного ответа. Статус H03 брать из обновляемой [квитанции](H03_RECEIPT.md): фраза REPORTED о H03 PASS в prefix сама не является новой приёмкой текущего source.

Здесь прочитаны только документы и первичные веб-источники. Код, зависимости, конфигурации и модели не менялись; estimator-fit, case API и обращения к пользовательским чатам не выполнялись. Все предложенные рецепты и бюджеты **NOT_RUN**.

## Пять практически важных проверенных утверждений

`VERIFIED-source` означает подтверждение семантики API в указанной версии; эффективность на наших задачах остаётся UNKNOWN. Ссылки исходного prefix сохранены; для раскрытия переменных CatBoost дополнительно просмотрены официальные файлы того же tag.

| ID | Что подтверждено первичным источником | Следствие и граница |
| --- | --- | --- |
| H04Q-C1 | **CatBoost v1.2.8:** Counter CTR с Full учитывает learn и validation objects; SkipTest исключает validation objects. В шаблонах этой версии SkipTest уже указан default. [CTR parameters из prefix](https://github.com/catboost/catboost/blob/v1.2.8/catboost/docs/en/references/training-parameters/ctr.md); значения переменных раскрыты в [официальном presets.yaml](https://raw.githubusercontent.com/catboost/catboost/v1.2.8/catboost/docs/en/presets.yaml), enum — в [enums.h](https://raw.githubusercontent.com/catboost/catboost/v1.2.8/catboost/private/libs/options/enums.h). **VERIFIED-source**. | Явный `counter_calc_method="SkipTest"` закрепляет fit-only правило для этого CTR, но не доказывает отсутствие всех прочих утечек. Первый фиксированный baseline обходится без eval_set; y_inner не передаётся модели. Native categorical и Ordered boosting — разные решения; преимущество каждого надо измерять. |
| H04Q-C2 | **CatBoost v1.2.8:** автоматический learning rate для Logit/MultiClass/RMSE зависит от iterations, если не заданы leaf_estimation_iterations, leaf_estimation_method и l2_leaf_reg; в остальных случаях указан default0.03. Итерации задают верхнюю границу деревьев. [Common parameters](https://github.com/catboost/catboost/blob/v1.2.8/catboost/docs/en/references/training-parameters/common.md). **VERIFIED-source**. | Freeze сохраняет фактически разрешённый learning rate, число выполненных итераций и API-конвенцию best iteration. Предлагаемый явный0.05 убирает эту default-неопределённость, но не доказан оптимальным. Увеличение числа строк при refit не разрешает автоматически увеличивать число деревьев. |
| H04Q-C3 | **LightGBM4.6.0:** bagging требует ненулевого bagging_freq, его alias — subsample_freq; zero_as_missing=True охватывает неявные sparse-ноли. feature_pre_filter привязан к min_data_in_leaf при создании Dataset: при поиске этого параметра с повторным Dataset требуется пересоздать Dataset либо рассмотреть False. Multiclass строит num_class×num_iterations деревьев. [Parameters](https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html). **VERIFIED-source**. | OHE-ноль сохраняет исходный смысл при zero_as_missing=False; proposed subsample0.8 требует freq1. Риск pre-filter условен повторному Dataset: свежий Dataset для каждого fit не требует автоматически отключать фильтр. Изменение num_leaves — отдельная capacity-гипотеза. Одинаковые300 rounds у библиотек не означают равную работу. |
| H04Q-C4 | **sklearn1.5.2:** CalibratedClassifierCV с ensemble=False получает OOF-прогнозы через cross_val_predict, затем использует base estimator, обученный на всех переданных данных. В prefit-режиме непересечение fit/calibration обязан обеспечить вызывающий код. Документация предупреждает об isotonic при малом calibration sample. [CalibratedClassifierCV](https://scikit-learn.org/1.5/modules/generated/sklearn.calibration.CalibratedClassifierCV.html). **VERIFIED-source**. | Для нашего поиска «все данные» здесь означают только T_fit. Оборачивать полный pipeline, чтобы preprocessing также обучался внутри fold. Калибровка добавляет fit и не обещает роста Macro F1; OOF-score, по которому выбирали правило, остаётся selection score. |
| H04Q-C5 | **sklearn1.5.2:** TF‑IDF обучает vocabulary/IDF по переданному корпусу; max_features выбирает ограниченный словарь и игнорируется при явном vocabulary. SGDClassifier принимает sparse и поддерживает log_loss; Ridge с lsqr поддерживает sparse, в том числе при fit_intercept=True. [TF‑IDF](https://scikit-learn.org/1.5/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html), [SGDClassifier](https://scikit-learn.org/1.5/modules/generated/sklearn.linear_model.SGDClassifier.html), [Ridge](https://scikit-learn.org/1.5/modules/generated/sklearn.linear_model.Ridge.html). **VERIFIED-source**. | Sparse-text маршрут допустим без pretrained weights. Словарь/IDF обучать внутри T_fit/fold; существующий bounded vocabulary нельзя незаметно заменить параметром50000. Сначала согласовать новый recipe и временную память. max_features не является обещанием предела peak RAM. |

Проверка документов не подтверждает импорт/fit этих адаптеров в точном официальном образе и не меняет разрешённые pins. Веса из сети и runtime pip не предлагаются.

## Кандидаты P0 и P1

Порядок ниже предложен для будущего H04 после его отдельной команды. Маршрутизация — по разрешённой схеме и типам данных, без ветвей по public dataset/target name. Приведены лишь ключевые начальные параметры; полный manifest до запуска должен однозначно фиксировать остальные параметры и preprocessing.

| Приоритет / кандидат | Предлагаемый контроль → изменение | Что измерять и когда отвергать |
| --- | --- | --- |
| **P0: mean / majority** | Простой контроль через общий контракт → ранний валидный CSV | Original-scale RMSE / primary Macro F1, rows/classes/order/SHA, полное время. Константа проверяет цепочку и даёт fallback; не считается моделью по признакам. |
| **P0: CB-native** | Числа и категории с collision-free missing → CPU,8threads,300iterations,LR0.05,depth6,l2=5,Plain,Bernoulli/subsample0.8,SkipTest,use_best_model=False | Inner primary, разность с простым контролем, завершённые iterations, fit/predict/refit время, peak суммарной RAM. Сначала без class weights/eval_set; не подбирать несколько компонентов одновременно. |
| **P0: LGB-OHE** | Текущий fit-only numeric/OHE →300iterations,LR0.05,num_leaves31,min_child_samples40,reg_lambda5,subsample0.8/freq1,n_jobs8,zero_as_missing=False | Качество и готовность CSV при том же полном бюджете, feature count/nnz/RAM, actual parameters. Это сравнение всего recipe с CB-native; разницу нельзя приписывать одному encoder. |
| **P0 при наличии текста: sparse linear** | Текст только из fit → TF‑IDF + SGDClassifier(log_loss) либо Ridge(lsqr) | Нужны реальные завершённые fit, unknown/empty vocabulary, время/nnz/peak RAM, вклад текста относительно no-text. Предложения min_df2/max_features50000/float32 и alpha из prefix — новые непроверенные recipe-параметры. |
| **P1: ёмкость / регуляризация** | CB depth6→8; LGB leaves31→63; min leaf40→20 либо80; regularization5→10 | Одно изменение за trial; закрыть Dataset pre-filter caveat. Reject при плохой primary, неоправданном ресурсе или потере своевременного CSV. Не строить декартово произведение вариантов. |
| **P1: веса / правило решения** | Без весов → capped sqrt веса; отдельно beta∈{0,0.25,0.5} при prior-offset | Веса/OOF/частоты только T_fit; основной F1 без дополнительных evaluator weights. Считать FP/FN/recall/precision по классам; не включать веса и offsets автоматически вместе. |
| **P1: target transform / robust loss** | Raw squared-loss control → log/robust; smearing отдельно | Domain/inverse и finite guards; решение по original RMSE. Коррекцию по остаткам оценивать train-side OOF/past-only, без in-sample остатков или outer. Выигрыш UNKNOWN. |
| **P1: semantic features / history / blend** | Только обоснованные units/отношения; затем причинная история либо смесь до двух моделей | Coverage, missing-history, ambiguity, nnz/time и добавочная primary-польза. Исторический ключ не объявлять ID здания. Для inner4 использовать только периоды1–3; same-period/future target запрещён. Не удалять строки с неоднозначной историей. |

XGBoost2.1.4 и один AutoML-компаратор остаются следующими гипотезами, а не обязательными дополнительными системами первого baseline. Для category mapping нельзя предполагать функции более новых XGBoost; [tagged guide из prefix](https://github.com/dmlc/xgboost/blob/v2.1.4/doc/tutorials/categorical.rst) здесь повторно не проверялся. Это ограничение будущей проверки, не результат нового адаптера.

## Протокол небольшого screen-эксперимента

1. Зафиксировать source/partition/recipe SHA и seed42; до результатов определить второй seed. Изменение закрытых данных не должно менять seed через полный source SHA. Доступное пространство поиска и primary metric одинаковы у плеч.
2. Публичная регрессия: fit1–3, inner4; outer5 закрыт до freeze. Для классификации использовать принятый H03.3 partition: T_fit56108, inner14028, outer17534. Это параметры нашего public split, а не константы универсального агента.
3. Первый содержательный fit — с фиксированными iterations. Early stop, если вводится позже: reg train1–2→stop3 внутри T_fit; classification — только внутреннее train-side разделение. y_inner не передавать через eval_set/callback.
4. Для решения/калибровки классификации допустимы две OOF-части внутри T_fit, с наличием всех необходимых классов в каждой train-части. Pipeline обучается заново внутри fold; OOF-метки не используются для его early stopping. При infeasible split — явный отказ от процедуры, без удаления классов.
5. Ограниченное правило, например argmax(log(max(p,eps))−beta·log(pi)), выбирается train-side, затем фиксируется до inner. Beta и частоты из разрешённых данных записываются явно; результат выбора OOF не считается независимой оценкой.
6. После freeze записать код, preprocessing-алгоритм, фактические model parameters/iterations, class mapping, offsets и ансамбль. Frozen refit заново обучает состояния того же recipe на development; former inner не открывает новый HPO/early stop/threshold search. Метрика родителя не превращается в измеренную метрику refit.

Общая положительная temperature всех logits сохраняет argmax: деление на положительное число и softmax не меняют порядок. Это аналитический факт, а не эксперимент; такая температура сама по себе не изменит Macro F1 при прежнем argmax. Иное правило или per-class calibration — отдельные изменения, которые требуют проверки.

Во взвешенной идеальной cross-entropy целевое q(c|x) пропорционально w_c·p(c|x). Это математическое объяснение изменения границы решений, а не обещание роста recall/F1. Capped sqrt из prefix и штатный auto-class-weight не следует считать одним рецептом; веса нельзя повторно накладывать через два API без явного намерения.

### Полные H1–H9 из полученного END

Все строки — **PROPOSED / NOT_RUN**; сроки заданы на каждое полное плечо. Для первых H1/H2/H3 источник предлагает приоритет1/2/3, остальные допускаются при достаточном резерве.

| Гипотеза источника | Предлагаемый равный бюджет | Что опровергает практическую пользу |
| --- | ---: | --- |
| H1: CB-native ↔ LGB-OHE на обеих задачах | 900s/плечо | Нет MEI или теряется готовый CSV. Сравниваются рецепты целиком. |
| H2: none ↔ capped sqrt weights | 900s/плечо | Нет primary-прироста либо направление нестабильно между seed. |
| H3: raw target ↔ log1p, тот же regressor | 900s/плечо | Выигрыш только в log-RMSE, без original-scale RMSE. |
| H4: argmax ↔ один OOF prior-offset | 1800s/плечо | OOF-прирост не переносится на inner; два OOF-fit и refit также оплачиваются временем. |
| H5: одно увеличение depth/leaves | 900s/плечо | Растёт только fit-score либо нет MEI inner. |
| H6: ограниченные semantic ratios/crosses | 900s/плечо | Нестабильные denominators/nonfinite или нет MEI. |
| H7: raw squared ↔ один robust loss | 900s/плечо | Нет original-RMSE прироста, независимо от MAE. |
| H8: past-only group history | 1800s/плечо | Нет переноса на следующий внутренний период; coverage/коллизии также фиксируются. |
| H9: лучший одиночный ↔ смесь двух predictions | 1800s/плечо с обоими финальными fit/predict | Пропущен deadline или нет MEI. |

В предложении H1 для двух задач имеет потолок3600s; H2+H3 — ещё3600s, итого до7200s без повторов. Это арифметическая сумма будущих лимитов, не оценка скорости или измеренный расход. Последовательность300→900→1800 оплачивает сумму запусков. Сравнивать pre-refit inner metric; не открывать outer для каждого кандидата и не продолжать подбор по former inner после freeze/refit.

Для blend сначала фиксированное50/50 либо небольшой набор весов по T_fit-OOF. Отсутствие OOF не разрешает сотни коэффициентов по inner. Дополнительно проверена первичная [StackingClassifier1.5.2](https://scikit-learn.org/1.5/modules/generated/sklearn.ensemble.StackingClassifier.html): cv="prefit" использует прогнозы prefit-моделей на полном переданном train, а не создаёт OOF; документация прямо предупреждает об overfitting при совпадении их обучающих данных с meta-fit. Это подтверждение риска, не измерение пользы stacking у нас.

## Время, stop rules и честные outcomes

| Предложенный полный бюджет плеча | Назначение | Условие допуска |
| ---: | --- | --- |
| **300s** | Ранний fallback и один содержательный fit | Включены cold CLI/import/read/preprocess/evaluate/refit/predict/write; это не300s только на fit. |
| **900s** | Контроль против одного изменения | Неудачи, повторные fit и финализация входят в тот же потолок. |
| **1800s** | Подтверждение выбранной гипотезы / ограниченный подбор | Новый trial допускается лишь при наблюдаемом запасе на refit, predict/write и cleanup. |

Эти бюджеты и доли распределения в prefix **PROPOSAL / NOT_MEASURED**. Не продлевать исходный RunBudget и не объявлять timeout доказательством низкого качества. Допуск: upper estimate нового trial + refit + predict/write + запас < remaining. Начальное масштабирование по числу строк — гипотеза: словарь, feature count и iteration count также меняют цену.

Предложенный MEI: относительное снижение RMSE ≥0.5% либо абсолютный Macro F1 прирост ≥0.003. Записать его до просмотра результата; это критерий screen, а не ожидаемый выигрыш. Один seed — только PROMISING; согласованный второй seed и готовый output могут дать PASS-screen в заранее заданной области. Ниже MEI — не включать к текущему сроку, сохранив отрицательное наблюдение: это не доказательство бесполезности метода вообще. Нельзя переносить этот статус на private, трёхчасовой бюджет или победу в хакатоне.

Stop/reject: budget admission закрыт; invalid/nonfinite output или class/row mapping; отсутствующий класс в нужной OOF train-части; превышение memory/nnz; новый рецепт не успевает завершить пригодный CSV; заранее выбранный критерий качества не выполнен. Последний валидный CSV сохраняется. Частично оборванный fit не считается завершённой моделью; только проверенный checkpoint может заменить fallback.

Один обучающийся кандидат, последовательные folds, суммарно до8CPU; nesting BLAS/joblib учитывать отдельно. CTR RAM и histogram cache не выдаются за полный RSS cap. Предложенный admission ориентир16GiB при локальных20GiB — непроверенная политика запаса, а не измеренная доступная память.

## Что должно остаться в записи каждого будущего сравнения

| Блок | Минимальная запись |
| --- | --- |
| Identity / доступ | Source, schema, partition, exact recipe/code SHA; версии и fitted scope; отсутствие outer feedback. |
| Качество | Primary до/после и delta, заданный MEI, per-class диагностика отдельно, finite/shape/class-order проверки. Score платформы и параметры B не выдумывать. |
| Ресурсы | Полное wallclock и стадии, завершённые iterations, fit/refit/predict counts, peak памяти с областью измерения, features/nnz и стоимость неудач. |
| Ready artifact | SHA валидного CSV, test order/raw ID, origin fit/refit и ссылка на оценённого родителя; fallback/degraded/timeout раздельно. |
| Отрицательный результат | Ошибка, отсутствие эффекта, непригодный по времени/памяти рецепт и причина исключения сохраняются наравне с удачным trial. |

## UNKNOWN и продолжение

Фактическое качество/скорость всех предложенных estimator-рецептов, выигрыш native categories, weights/offsets/calibration/text/history, перенос на private, достаточность300/900/1800s и устойчивость refit — **UNKNOWN / NOT_RUN**. Калибровка не оптимизирует F1 автоматически; external studies и документация не обещают нам прироста. Log inverse, clipping по train-max и превращение временного кода в календарный год также не получают презумпции полезности.

### Диагностика гипотетического «локально хорошо, official0»

Не считать наличие CSV доказательством estimator-fit. До выводов о силе метода проверить: fitted attributes/iterations и origin prediction; primary metric/direction/inverse; row/class mapping и finite; связь оценённого parent с замороженным recipe/refit/export; future-period/unknown обработку; support/FP/FN редких классов; количество сравнений и открытий контроля. Официальный B неизвестен: локальный контроль не устанавливает превосходство над ним, а50/.60 остаются примерами, не baseline-константами.

Отчёт имеет три независимых слоя: **format/runtime** — новый валидный CSV, порядок/срок/ресурсы; **ML-quality** — настоящий fit и метрика конкретного split; **official** — ответ платформы для конкретного ZIP SHA. Ни один слой не заменяет следующий; official public/private score до ответа UNKNOWN.

План к21:00 в END — предложение, не разрешение обучения или обещание готовности. Сначала нужны измерения одного завершённого CPU-fit обеих задач и refit-стоимости; затем H1/H2/H3. Остановить исследование раньше срока на измеренную стоимость холодных проверок обеих задач + финализацию + резерв исправлений. Два полных последовательных трёхчасовых запуска требуют до шести часов; короткий screen их не заменяет. При недостатке окна выбирать уже проверенный вариант, не незавершённое улучшение.

Новые numerical параметры не внедряются в существующие модули этой запиской. Полный официальный образ/все pins, hard runtime limit и worker boundary имеют собственные приёмки. **Tail получен и прочитан до END; coverage завершено, исходный original-long-message byte-exact всё ещё NOT_RETRIEVED.** Дальнейшая реализация или эксперимент остаются отдельной командой владельца.
