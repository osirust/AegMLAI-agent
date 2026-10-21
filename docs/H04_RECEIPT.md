# H04 V2: фиксированный CPU baseline и локальная приёмка исправлений

Дата: **21.10.2026**. Текущий статус: **PASS_H04_FIXED_BASELINE_ONLY**.

На исправленном замороженном коде выполнены новые unit-проверки, обе public-задачи в WSL и повтор в локальном Docker с объявленными вложенными путями. **H04.1–H04.4 принят в области доверенного фиксированного baseline.** Полный [внешний postfix](H04_STATIC_REVIEW_RESULT.json) получен **11:23:42 UTC / 14:23:42 МСК**, message `3ca78653-31ff-4855-bf78-b443e33dc666`, 12865 символов до END: все четыре P0 CLOSED, remaining blockers=0. Рецензент выполнил static review; runtime-тесты не повторял и source SHA независимо не вычислял. Новые execution receipts принадлежат команде.

Это **H04_FIXED_SEARCH_FIT_ONLY / NO_REFIT_SEARCH_ONLY**: настоящий фиксированный CatBoost, inner-оценка и валидный test CSV. Это не AutoResearch или frozen refit. Outer-качество и официальный baseline/score не вычислялись; Qwen и `/key/info` не вызывались. Текущий маршрут — [PROJECT_STATE](../PROJECT_STATE.md), нормативный учёт IDs — раздел 9 [ТЗ](TECHNICAL_SPEC.md).

## 1. Текущее измеренное качество

Константа и feature model используют одинаковые T_fit и inner-строки. RMSE считается на исходной шкале; Macro F1 — с `labels=None`, без подмены Accuracy или fixed10. [Новый WSL oracle](H04_WSL_PUBLIC_V2_RESULT.json) независимо пересчитал те же inner-прогнозы через scikit-learn. Это численная сверка расчёта, а не независимая оценка обобщения.

| Задача | Fit / inner / outer | Константа на inner | CatBoost на inner | Улучшение | Test CSV |
| --- | --- | --- | --- | --- | --- |
| Регрессия | 22 054 / 12 946 / 18 308; периоды 1–3 / 4 / 5 | Mean RMSE **58.460385734** | RMSE **47.303244293** | RMSE меньше на **11.157141441** | **22 449** строк |
| Классификация | 56 108 / 14 028 / 17 534; stratified nested, seed 42 | Majority Macro F1 **0.048411498** | Macro F1 **0.504643848** | F1 больше на **0.456232350** | **41 166** строк |

Точные контракты, split/source SHA, параметры и диагностика — [регрессия V2](H041_REGRESSION_V2_RESULT.json), [классификация V2](H042_CLASSIFICATION_V2_RESULT.json). В обоих случаях выбран feature model. Модель обучена только на T_fit; полноценного development-refit не было. Доверенный splitter читает train-метки для стратификации, но estimator не получает inner/outer y. У test нет доступных нам правильных ответов.

Качество совпало с первым снимком до review. Исправления усиливают проверяемые контракты и обработку ошибок; нового выигрыша в ML-качестве от них не заявляется. Штатный первый baseline использовал правильную fit-матрицу: finding о возможности её подмены сам по себе не устанавливает утечку в первом actual-прогоне.

## 2. Рецепт, время и память

Фиксированный рецепт остался прежним: **CatBoost 1.2.8, CPU, 300 деревьев, threads 8, seed 42, learning rate 0.05, depth 6, l2_leaf_reg 5**. Нет eval_set/early stopping по inner, pretrained-весов или непрозрачного пула trials. Native preprocessing подготовил 121 признак регрессии и 81 классификации; его статистики обучаются на T_fit.

Среда: Python 3.12.3, NumPy 1.26.4, pandas 2.2.3, SciPy 1.12.0, scikit-learn 1.5.2. Каждый actual-запуск имеет один budget **900 секунд с резервом 60**, включая импорт, чтение, preprocessing, fit и запись. Это короткий pilot, не проверка 10800 секунд.

| Среда / задача | Время вместе со стартом Python | Fit по audit модели | Накопительная high-water RSS процесса |
| --- | --- | --- | --- |
| WSL / регрессия | **12.0067 с** | **0.4993 с** | **473 554 944 байта / 451.62 MiB** |
| WSL / классификация | **31.5348 с** | **16.7154 с** | **659 521 536 байт / 628.97 MiB** |
| Docker / регрессия | **14.0387 с** | **0.5019 с** | **480 432 128 байт / 458.18 MiB** |
| Docker / классификация | **32.2793 с** | **16.9462 с** | **653 406 208 байт / 623.14 MiB** |

Время старта взято из [WSL V2](H04_WSL_PUBLIC_V2_RESULT.json) и [Docker V2](H04_DOCKER_PUBLIC_V2_RESULT.json), fit — из соответствующего baseline-report. RSS прочитана из соседних runtime `manifest.json`: поле `process_high_water_rss_bytes`, `rss_scope=process_cumulative`; все четыре manifest SHA сверены с outcome соответствующего запуска. Это память всего процесса, включая импорты/подготовку, не изолированная память модели и не лимит Docker. Числовой RSS нет в самом baseline-report JSON; исходный runtime manifest отдельно не экспортирован.

Отдельные 161.36 MiB из estimator unit-квитанции относятся к tiny-checker и не подменяют public RSS. Параллельная dev-нагрузка и накопительные измерения не позволяют объявлять эту таблицу контролируемым performance benchmark.

## 3. Текущие проверки V2

| Компонент | Результат | Область |
| --- | --- | --- |
| Артефакты | **20 методов / 78 сценариев**, [V2 JSON](H04_ARTIFACTS_V2_RESULT.json) | Postcommit registry/cleanup, конечные inode/bytes/SHA, предупреждения и manifest refusal, no-clobber, сохранение чужого inode |
| Estimator | **13 / 48**, [V2 JSON](H04_ESTIMATORS_V2_RESULT.json) | Source-bound fit factory, отдельная train-row-space оболочка, matrix-content witness native/CSR, отказы до Pool/fit; девять успешных tiny-fit по 10 деревьев |
| Training data / evaluator | **17 / 31**, [неизменённый компонентный JSON](H04_TRAINING_DATA_RESULT.json) | BUILT/source/row binding, fit y отдельно от inner X, aggregate inner evaluation, protected poison, row order, error bands |
| Orchestrator / CLI | **14 / 27**, [V2 JSON](H04_BASELINE_SYNTHETIC_V2_RESULT.json) | Temporal resolution, postcommit progress, source/timer/mapping, четыре direct tiny-fit по 10 деревьев и один cold literal CLI с 300 деревьями |
| H04.4 method checks | **9 / 9**, [историческая неизменённая квитанция](H044_QUALITY_METHOD_RESULT.json) | Синтетическая проверка builder: source/phase/config/gain, отказ ложных claims, exclusive output; не измерение качества |
| Actual WSL | **Две задачи**, [V2 JSON](H04_WSL_PUBLIC_V2_RESULT.json) | Literal entrypoint, полный CSV, текущий frozen source, численный sklearn oracle |
| Actual Docker | **Две задачи**, [V2 JSON](H04_DOCKER_PUBLIC_V2_RESULT.json) | Объявленные nested paths, тот же source/recipe/split, совпадение прогнозов с текущим WSL, проверенный cleanup |

Наборы пересекаются: методы, сценарии, tiny-fit и повтор одного baseline не складываются в число независимых quality-экспериментов. TD исходник `b1475aa1…` и его зависимости из отдельной 17/31-квитанции не менялись; совместная работа с новыми estimator/artifacts проверена свежими synthetic/actual V2. Старые A 15/71, E 11/35, root 12/20 остаются историей прежнего кода.

## 4. Четыре внешних P0: before, действие и локальное закрытие

| Постоянный ID | Подтверждённый before | Действие и новый относящийся результат |
| --- | --- | --- |
| **H04-FIT-MATRIX-BIND-001** | При одинаковых размерах/индексах настоящий test PreparedData с fit-audit проходил до Pool/fit-spy; реальных estimator fits в before 0. [Before JSON](H04_MATRIX_BIND_BEFORE_RESULT.json) | Trusted factory получает source-bound TrainFitView, фиксирует row-space/source/split/статистики и witness фактической матрицы. Raw PreparedData, test-подмена, недостающий token, изменённые native/CSR значения отвергаются до Pool; правильный fit положительно проверен. **E 13/48**, затем actual V2 |
| **H04-TEMPORAL-RESOLVE-001** | Неизвестное имя при распознанной temporal-роли могло молча стать IID или потеряться рядом с корректной декларацией. [Before JSON](H04_EXTERNAL_ROOT_BEFORE_RESULT.json) | Роль распознаётся до проверки имени; неразрешённая колонка даёт явный отказ. Две отрицательные формы, корректная temporal-таблица и действительно отсутствующая декларация проверены в **root 14/27**, затем actual V2 |
| **H04-CLI-PUBLISHED-PROGRESS-001** | После commit model CSV поздняя ошибка могла оставить в CLI SHA прежней константы, хотя новый файл валиден. [Before JSON](H04_EXTERNAL_ROOT_BEFORE_RESULT.json) | Progress обновляется сразу после validated writer commit; последующий snapshot использует finalizing budget. Postcommit expiry/validation failure сообщает текущий SHA, precommit failure сохраняет прежний. **root 14/27**, затем actual V2 |
| **H04-ARTIFACT-COMMIT-001** | Сбой удаления временного имени после успешного hard link оставлял destination вне registry/manifest. [Before JSON](H04_ARTIFACT_COMMIT_BEFORE_RESULT.json) | Сразу регистрируется известный committed inode/bytes/SHA; bounded cleanup отдельно проверяется. Единичный/повторный/persistent сбой, postcommit stat, fsync warning и foreign inode проверены. Неподтверждённая очистка не получает согласованный manifest. **A 20/78**, затем actual V2 |

Все четыре ID закрыты локальными адресными/сквозными результатами и полным [static postfix](H04_STATIC_REVIEW_RESULT.json) в области trusted H04. Это не внешняя повторная runtime-проверка и не принятие H05. В before artifact JSON сохранено исходное поле `EXTERNAL_REVIEW_ID_PENDING_FULL_REPLY`: постоянный ID сопоставлен после получения полного review, исходные bytes не исправлялись задним числом.

**Отдельная история QA.** [Before checker fixture](H04_QA_FIXTURE_BEFORE_RESULT.json) фиксирует четыре функциональных PASS temporal-контролей и последующий FAIL в tearDown: тест сам перестроил fixture, но сравнил с прежним snapshot. После явной фиксации нового исходного snapshot весь root-набор **14/27 PASS**. Проверка неизменности источников не отключалась, product finding этим отдельным QA-сбоем не закрывался.

Прежние локальные findings также сохраняются: H04-SPLIT-ARTIFACT-SIZE-001, H04-CLI-TIMER-001 и H04-CLI-PROGRESS-001 имеют [исходный before](H04_PEER_BEFORE_RESULT.json), их регрессии входят в root 14/27. H04-ESTIMATOR-ADMISSION-001 имеет [before](H04_ESTIMATOR_ADMISSION_BEFORE_RESULT.json) и новый E 13/48 с fit-spy=0 после исчерпания budget в Pool. Полные membership-индексы остаются data-only CSV, split JSON — metadata.

Неуспешные старые попытки не перезаписывались. Training-data attempt1 ошибся в ожидаемом error code; ранний root-checker ожидал один exception type вместо двух собственных статических source-ошибок; quality-method attempt1 уточнил явную формулировку T_fit в гипотезе. Новые PASS не означают, что этих попыток не было, и не прибавляют их к последнему результату.

## 5. Declared nested paths и совпадение Docker/WSL

[Уточнение организаторов](ORGANIZER_UPDATES_20261021.md) отделяет flat ZIP кода от структуры входных CSV. WSL V2 читает новую рабочую копию фактической выгрузки. Docker V2 содержит четыре CSV только по declared `regression/participants/…` либо `multiclass/participants/…`, без корневых CSV-дублей. TaskContract подтверждает **explicit resolution, flat_fallback=false**.

Для каждой задачи совпали четыре файла прогнозов: constant/model × inner/test. В Docker V2 `wsl_repeat=MATCHED_SOURCE_SPLIT_RECIPE_PREDICTIONS_AND_ORACLE`; максимальная числовая разница **0**, class labels совпали точно. Совпадение model/run metadata SHA не требовалось. Исходные inputs и root/staged code сохранены.

Локальный dev-image: `sha256:95e451e558d36beade7ffb1c64045a34cf152f9daac57336166e023c745cef0b`. Profile до start: **20 GiB, memory-swap=20 GiB, CPU quota 8, PIDs 256, UID 1000, rootfs read-only, network none, drop ALL, NNP**. Оба контейнера удалены по проверенному full ID/owner, отсутствие проверено по имени и ID; unresolved resources нет.

Это не официальный образ/full37 и не generated-worker boundary. Рабочие /work и /tmp — принадлежащие проверке writable bind-каталоги; source неизменность доказывается SHA, а не read-only всем /work. Capture тихого trusted CLI ограничен после получения, не как adversarial streaming bound.

## 6. H04.4: ошибки и заранее записанные гипотезы

[Quality aggregate V2](H044_QUALITY_V2_RESULT.json) собран из текущих двух source-bound WSL-report: builder сверил SHA кода, source/split/phase, версии, параметры, направление gain и парность inner. Новых training calls и API **0**. [Первая build-квитанция](H044_QUALITY_BUILD_RESULT.json) относится к прежнему aggregate, а не V2; её bytes сохранены.

Слабые классы текущего inner:

| Класс | Support | F1 модели |
| --- | --- | --- |
| Worms | 10 | **0.000000** |
| DoS | 981 | **0.058651** |
| Backdoor | 140 | **0.120000** |
| Analysis | 160 | **0.154696** |

У Worms слишком малый support для вывода об устойчивости; DoS затрагивает гораздо больше строк. Регрессия: MAE **26.179205**, signed bias **+5.377250**, p99 абсолютной ошибки **172.750837**; худшие 10% строк дают **81.0541% SSE**. Это posthoc inner-диагностика, не независимое качество или доказанная причина ошибок.

HYP-R01/R02/C01/C02 сохраняют статус **PREREGISTERED_NOT_IMPLEMENTED_NOT_TESTED**, candidate fits **0**: depth 4 для регрессии; learning_rate 0.03 при 300 деревьях; bounded inverse-sqrt class weights; depth 4 классификации. Веса — только из T_fit, не из inner-support. Одно изменение на гипотезу, тот же split/seed/бюджет, явный stop rule; ухудшения не скрываются.

MEI: **0.5% относительного снижения RMSE** либо **0.003 абсолютного роста Macro F1**. Это выбранные проектные пороги, не официальный B, не выполненный improved fit и не обещанный эффект. Повторный выбор по inner способен переобучить поиск; outer/test labels не идут в feedback.

## 7. История, точная идентичность и границы

Первая серия и её **13 JSON** остаются историей до внешних guard-fixes. Их bytes/SHA и старый `runs/h04/h04-20261021/EXPORT_MANIFEST.json` сохранены. Созданы **12 новых побайтно идентичных экспортов**, учтённых в отдельном ignored `EXPORT_V2_MANIFEST.json` SHA `eff2de94bb7adae8ff8fc3dcf1d210b5316fea952ee4c31d230dac2553cdc4ea`; старый manifest не перезаписан.

Текущие 13 root Python + неизменённый requirements из обоих baseline V2 сверены с файлами. Основные SHA:

| Файл | SHA-256 |
| --- | --- |
| solution.py | `a71a8474359b7b620148cf1db026b0baf5b993084744be304de33a3976030f57` |
| aegml_baseline.py | `8e68fa7a9f68a55a179eb11275f5b966119c6e80d4271dc997daa77b3537906e` |
| aegml_estimators.py | `530d80a62332f122fa3e9602e27c8f0fd619d2e7a2cdbe2020beb442f7a10943` |
| aegml_artifacts.py | `ca40ae8779b16f2d6c12e7bf2d10b5653a007a71d55d44b376aae3d68bdd3b88` |
| aegml_training_data.py | `b1475aa12b3f16820aefcb8f2b97481ccd587b70fa23cae006b8db36a4b6caee` |
| provided requirements.txt | `9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6` |

Полный code map и checker hashes — в JSON. Главные текущие экспорты:

| JSON | SHA-256 |
| --- | --- |
| [WSL V2](H04_WSL_PUBLIC_V2_RESULT.json) | `1124d0e38d1c49083ec22a97cc3cb538e0a039d2798c7da0d315ca7904eeeb3d` |
| [Docker V2](H04_DOCKER_PUBLIC_V2_RESULT.json) | `8c4c9536716fec96bb37ee2965c7036e7a5c3d3ec8af55e90b5d21e5812b1d90` |
| [Synthetic V2](H04_BASELINE_SYNTHETIC_V2_RESULT.json) | `a7fb84ba664275f881c5f3d5a23a99af25ca7caec6b9745431a15b020e352f5c` |
| [Quality V2](H044_QUALITY_V2_RESULT.json) | `486f4b7cebe99ea711201234a737a4a9afb65c666dbd4e41aaac8628b2daabc9` |

Остальные новые экспорты — A/E V2, два baseline-report V2 и четыре before — связаны из соответствующих разделов выше. Финальные test CSV SHA: regression `ee57ae887177f01a2aba013d47e0105ee461e943ce0b9781bf93cea123831ab4`, classification `66363794a0ac97053269ae2b33f688a28e0e8adb4c4334be6535fbadf1dfb22b`. Они совпадают с первыми test CSV и являются runtime-артефактами, не загружаемым ZIP.

Полный H04 static review закрывает только описанные четыре исправления; его JSON SHA `9ec8df2c69816887c652769dc7f848286aea049465bd055c68f97ce21a0ff1ba`. Не приняты этим PASS: официальный image/full37, длительность 10800 s, private-задачи, официальный B/score, настоящий frozen refit, H05 worker isolation, live Qwen/tools и AutoResearch. H05 observer ABI 7/seccomp и H06 scratch — только PREPARATION_ONLY. Ошибка H04 остаётся честным nonzero даже при сохранённом CSV.

Исторические [H03_RECEIPT](H03_RECEIPT.md), [H02 review repairs](H02_REVIEW_REPAIRS.md) и [H02.4](H024_RECEIPT.md) не переписываются. Ручной ориентир владельца — H04→H05→H06 к 18:00 МСК, без гарантии срока/score и без автоматического сабмита. Live H06 допускается лишь после готовности H05 и offline/mock H06; сейчас API=0. Во время экспорта и редакции новых fit/API/Docker-прогонов не выполнялось.

## Заключительная сверка файлов

[Metadata-аудит](H04_PUBLICATION_RESULT.json) прошёл 5884 проверок источников, истории, exports, ссылок и staged bytes. Он не повторяет обучение и не добавляет независимые измерения качества. Первый отказ из-за формата V2-манифеста сохранён; исправление проверщика учитывает H04-QA-EXPORT-MANIFEST-SCHEMA-001. После добавления этой квитанции выполнен отдельный readback актуальных document SHA и Git blobs. [Локальная проверка ключа](H04_SECRET_SCAN_RESULT.json) не обращалась к API и не выводила значение или fingerprint.
