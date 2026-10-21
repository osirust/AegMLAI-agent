# H03: квитанция компонентов данных и локальной интеграции

Дата: **21.10.2026**. Сводный статус: **PASS_H03_COMPONENTS_AND_LOCAL_INTEGRATION_ONLY**.

Компоненты H03.1–H03.5 и их сквозная цепочка прошли относящиеся локальные проверки в WSL и локальном Docker. Последняя версия writer включает исправление назначения файла; актуальны квитанции **V2**. Четыре первоначальных замечания закрыты внешним статическим review; destination-bind исправление также закрыто отдельным внешним ответом b2073b6d-3dee-4fbb-ae04-086b5aa7de18. [Все полные review](H03_CHAT2_REVIEW_INTAKE.md). Это компонентная приёмка основы данных, а не готовность полноценного ML-агента.

Прогнозных estimator обучено **0**, реальных вызовов Qwen **0**, новых официальных сабмитов **0**. Запрос к `/key/info` также не выполнялся. Предобработка действительно обучалась: медианы и категории — в том числе на разрешённых fit-частях public; vocabulary/IDF TF-IDF — в текстовых фикстурах. CSV для public созданы на синтетических константах и проверяют **только формат и публикацию**. Public/outer-качество модели и официальный score не измерялись.

## 1. Актуальные результаты

Среда компонентных прогонов — отдельная WSL `AegML-Hackathon`, Python 3.12.3. Предобработка использует NumPy 1.26.4, pandas 2.2.3, SciPy 1.12.0 и scikit-learn 1.5.2. Повторные и пересекающиеся проверки не складываются в число независимых тестов.

| Область | Последний относящийся результат | Доказанная граница |
| --- | --- | --- |
| H03.1: профиль | **18 методов / 52 сценария**, два actual public checks; [JSON](H031_PROFILE_RESULT.json) | Fit-only статистики, protected-poison invariance, честные частичные частоты, конечный JSON, UTF-8 caps, logical-record guard и bridge настоящего H03.3 SplitPlan |
| H03.2: предобработка и загрузчики | **18 / 35**, два actual public workflow; [JSON](H032_PREPROCESSING_RESULT.json) | Проверка байтов источников, feature-only fit projection, точная привязка к активному BUILT split, неизменный learned state при transform, сохранение test-строк |
| H03.3 и численные адаптеры H03.5 | **26 / 86**, **11 oracle comparisons**, два actual public split checks; [JSON](H033_METRICS_VALIDATION_RESULT.json) | Восемь метрик, explicit labels/probabilities, finite-арифметика, строгие разбиения и фазовые метаданные; без модели или outer-quality |
| H03.4: writer/validator, текущая V2 | **16 / 73**, два actual writer fixtures; [JSON](H034_SUBMISSION_V2_RESULT.json) | Формат, actual ID/order mapping, привязка назначения к текущей задаче, бюджет summary, сохранение прежнего CSV и validate-before-replace |
| H03.5: сквозная API-цепочка WSL | **8 / 32**, две полные public-цепочки; [V2 JSON](H03_INTEGRATION_V2_RESULT.json) | TaskContract → BUILT split → profile → source-bound preprocessing → диагностические константы → независимый validator/writer |
| Та же цепочка в локальном Docker | **8 / 32**, обе public-задачи; [внутренняя V2-квитанция](H03_CONTAINER_INTEGRATION_V2_RESULT.json), [wrapper V2](H03_CONTAINER_V2_RESULT.json) | Замороженные root/staging, локальные лимиты, неизменность входов, exit 0 проверщика и подтверждённая очистка собственного контейнера |
| Регрессия H02.3 | **43 / 108 / 6 CLI**; [JSON](H03_CONTRACT_REGRESSION_RESULT.json) | Resolver, TaskContract, ID/sidecars и публикация метаданных на согласованном core |
| Регрессия bootstrap H02.2 | **24 / 51 / 37 CLI**; [JSON](H03_BOOTSTRAP_REGRESSION_RESULT.json) | Конфигурация, early timer, секретные canaries и прежние границы entrypoint |
| Literal platform CLI | **Две actual public-задачи**, [JSON](H03_LITERAL_PLATFORM_CLI_RESULT.json) | Буквальная команда `python3 solution.py task.md`, сохранность входов/старого CSV и прежний штатный exit 3 / implementation_incomplete |

**Важно различать API-цепочку и штатный entrypoint.** Сквозную H03-цепочку вызывает проверщик интеграции. Обычный `solution.py` всё ещё завершает H02.3 с `contract_valid=true`, `experiments_completed=0`, остальными full-agent флагами false и без нового prediction CSV. Его literal CLI-регрессия не объявлена готовым end-to-end агентом.

Последние проверки profile, WSL-цепочки и контейнера выполнялись параллельно; свежие WSL/Docker V2 также запускались параллельно. Их elapsed/RSS — диагностические сведения конкретного прогона, **не сравнительный performance benchmark**. Высокая отметка RSS процесса может включать ранее выполненные тесты и задачи.

## 2. Public-данные, разбиения и форматные CSV

Train регрессии прочитан полностью: **43 416 931 байт / 53 308 строк**, классификации — **16 567 584 байт / 87 670 строк**. Отсечения на 20 MiB нет. В актуальной цепочке используется настоящий SplitPlan, техническая modulo-маска прежних попыток не применяется.

| Задача | Fit / inner / outer | Test-строки и число подготовленных признаков | Partition SHA256 |
| --- | --- | --- | --- |
| Регрессия | **22 054 / 12 946 / 18 308**; явные периоды Year_Factor 1–3 / 4 / 5 | **22 449** строк, **181** признак | `b5f68d502fd252801a7f4be0fbdfcb9ae2cbf2e448e59e3ce1c2ed21a15de1b3` |
| Классификация | **56 108 / 14 028 / 17 534**; stratified_nested_v1, seed 42 | **41 166** строк, **235** признаков | `32576585334f36943b656dbe48879cac196fcabc3bcc12d026edc058e8bdf794` |

Загрузчик fit сохраняет только признаки разрешённых строк; target, ID и отдельные inner/outer feature frames не возвращаются. Его production-путь требует `BUILT` и совпадения активных split metadata с проекцией переданного плана, которую записывает `attach_split_plan`. Это не буквальное равенство всему `plan.to_dict()` с дополнительными полями или индексами. При protected poison меняется общий source SHA, но не fit-values witness и не learned numeric/category/text state. Отдельный low-level DataFrame API остаётся явно caller-asserted и не заявляет проверку активного разбиения.

В WSL/Docker V2 опубликованы контракт с BUILT split, alignment metadata и **новые форматные CSV** на 22 449 / 41 166 строк. Порядок actual test ID дополнительно сравнивается независимо. SHA файлов:

- Регрессия: `87f080b960b99ec1e5b4ce273d79628bdb6418480650d79a7140418a56937e12`.
- Классификация: `1d48ebbc5487800102fc361274c00a1291890dbd1fba67bae0502afa8be7f3a4`.

Это `DIAGNOSTIC_CONSTANT_ONLY_NO_TRAINED_MODEL`, а не обученный baseline. Входные 12 файлов public-пакета сохранили SHA; записи выполнялись в проверочных копиях и временных каталогах. Оригинальный CSV оставался прежним либо отсутствовал.

Функции actual-цепочки используют один переданный RunBudget; стадии его не сбрасывают. Короткий тестовый бюджет harness не доказывает трёхчасовое исполнение и не меняет платформенный предел **на каждую отдельную задачу**.

## 3. Исправления последнего внешнего review

Следующие четыре замечания локально закрыты относящимися before/after и свежей интеграцией; полный внешний статический postfix-ответ также закрыл все четыре без оставшихся замечаний. Граница внешнего заключения приведена в разделе 5.

| Постоянный ID | Подтверждённый before | Исправление и относящийся after |
| --- | --- | --- |
| **H032-PARTITION-BIND-001** | При активном BUILT-плане A загрузчик принимал другой валидный план B того же source и возвращал outer(A) как fit(B); [before](H032_PARTITION_BEFORE_RESULT.json), старый source `d35821df…` | Production loader требует BUILT и точного совпадения partition/schema/train SHA, policy/strategy/source, seed, train rows и counts. A+B отвергнут до проекции CSV; A+A сохраняет медиану 2,0; metadata-подмены и явная legacy-граница проверены в [18/35](H032_PREPROCESSING_RESULT.json) |
| **H034-MAPPING-BIND-001** | TEST-контракт публиковал CSV с нетождественной sidecar-картой, в том числе после пересчёта SHA ошибочной карты; прежний CSV изменялся; [before](H034_MAPPING_BEFORE_RESULT.json) | Streaming digest/count карт, согласование с контрактом и независимое восстановление sample→test по actual ID. TEST — identity, SAMPLE — actual mapping. Отказы сохраняют прежний файл; текущие адресные проверки входят в [V2 16/73](H034_SUBMISSION_V2_RESULT.json) |
| **H035-AUC-CLASS-001** | При объявленных neg/pos неизвестный truth принимался одномерным AUC с 1,0, но отвергался двумерным; [before](H033_METRICS_BEFORE_RESULT.json) | Объявленный binary class contract проверяется до выбора формы вероятностей. Unknown truth одинаково отвергается для 1D/2D; valid/reordered и single-class undefined контролируются в [26/86](H033_METRICS_VALIDATION_RESULT.json) |
| **H033-OOF-FINITE-001** | `(SSE=1e308,n=1)` дважды давали metric_overflow, хотя общий RMSE около 1e154 представим; [before](H033_METRICS_BEFORE_RESULT.json) | Масштабирование до суммирования и безопасное восстановление корня; finite extreme, обычный pooled SSE/N, invalid/zero/budget и прежние oracles проходят в [26/86](H033_METRICS_VALIDATION_RESULT.json) |

**Дополнительное H034-DESTINATION-BIND-001** воспроизведено уже после отправки указанного postfix-пакета. При byte-identical копии задачи B контракт задачи A направлял публикацию в A: старый CSV A изменялся, B оставался без результата. [Отдельный before](H034_DESTINATION_BEFORE_RESULT.json) получен только на двух безопасных синтетических временных задачах.

Текущий writer `42692226…` сверяет `task_path`, все `input_paths` и `output_path` с текущим bundle и его каталогом `submission.csv`. В [V2 16/73](H034_SUBMISSION_V2_RESULT.json) проверены сохранность A при отказе, правильная публикация в B и три подменённых поля. Свежие [WSL V2](H03_INTEGRATION_V2_RESULT.json) и [Docker V2](H03_CONTAINER_INTEGRATION_V2_RESULT.json) прошли уже на этом writer. **Локально замечание закрыто; внешняя проверка этого дополнительного ID ещё впереди отдельным пакетом.**

### Предыдущие адресные доказательства и их ограничения

- **H031-CSV-RECORD-001:** [before](H031_RECORD_BEFORE_RESULT.json) материализовал 100 002 поля / 100 001 физический фрагмент из 600 035 байт до width-check. Это ограниченная фикстура, не OOM. Теперь общий reader считает декодированные символы логической записи до передачи очередного фрагмента parser; default — **1 048 576 символов**, не предел RSS. Тест с cap 64 подтвердил ранний отказ с чтением не более 16 KiB в данном прогоне, valid multiline ниже cap и полный late-fit проход >20 MiB. Не обещаются универсальный prefetch ≤16 KiB или общий RSS ≤1 MiB.
- **H034-SUMMARY-001 / H034-CLASSORDER-001:** [actual before](H034_SUMMARY_BEFORE_RESULT.json) воспроизвёл VALID после истечения summary-budget и необработанный ValueError для NumPy class_order. Streaming summary с обязательным budget и явная None-проверка имеют адресные after-контроли, сохранённые также в текущем V2-наборе.
- **H033-METRIC-LABEL-001:** typed fractional class codes проверены после исправления, включая три oracle comparisons с явной дискретной кодировкой для sklearn. **Before остался только в прежнем tool-output/сообщении ответственного агента; самостоятельной before-квитанции нет.** Исторический attempt1 21/63 не покрывал этот случай и не заменяет отсутствующий before JSON.

Исторические H03.1 **17/49**, H03.2 **12/19**, затем **15/26**, H03.3 **24/67** и H03.4 **14/59**, затем **15/68** сохраняют свои SHA и scope. Они не переписаны и не прибавлены к текущим числам.

## 4. Проверщик интеграции и контейнер

**H03-QA-RAW-ID-001** относится к выводу проверщика при ошибке, а не к production writer. Прежний assertEqual мог вывести actual ID в будущий diagnostic. На синтетической канарейке один legacy failure действительно воспроизвёл вывод значения; два after failure controls — для ID order и row-index order — подтвердили его отсутствие. Эти намеренные dummy failures не являются отказами продукта. Их результаты и SHA текста, без самой канарейки, сохранены в [WSL V2](H03_INTEGRATION_V2_RESULT.json) и [Docker V2](H03_CONTAINER_INTEGRATION_V2_RESULT.json).

Исправленный integration checker — `6f1f21d4fbe06bee38a087a30afd2f9a992f3d99f04576e0c20d40bd6fbaa156`; текущий набор **8/32** уже включает эти контроли. Их не надо учитывать как ещё два независимых полных набора. Внешний рецензент четырёх исправлений новый QA-diff не просматривал: статическое внешнее закрытие этого QA-ID ему не приписывается.

[Docker wrapper V2](H03_CONTAINER_V2_RESULT.json) использовал прежний локальный dev-image `sha256:95e451e558d36beade7ffb1c64045a34cf152f9daac57336166e023c745cef0b`: 20 GiB/no additional swap, CPU quota 8, PIDs 256, read-only rootfs, network none и drop ALL capabilities. Wrapper завершился без timeout; source/staging и входы сохранились, собственный контейнер имеет `verified_absent`. Это не официальный образ, не полный список 37 pins и не admission произвольного generated worker.

## 5. Внешний review и остановка

H03.1 logical-record postfix ранее проверен внешним статическим ответом **`b9c84a04-3f86-4270-9f9f-afb9a4bf2c39`** без оставшегося P0 в этой области. Это анализ кода и доказательств, не независимый повторный запуск.

Postfix-пакет четырёх замечаний из раздела 3, около **38,6 тысячи знаков**, отправлен чату2 **21.10.2026 в 07:31:27 UTC / 10:31:27 МСК**. Root получил и полностью прочитал ответ **`f0a10156-d6c0-413b-9f73-6dbdaa8429db`**, 13 182 знака, в **07:42:35 UTC / 10:42:35 МСК**: все четыре findings закрыты, remaining — 0. Рецензент прямо отделил своё статическое заключение от исполнения: source SHA самостоятельно не пересчитывал, runtime-тесты не повторял.

Новое **H034-DESTINATION-BIND-001** в этот пакет не входило. Отдельный полный ответ **b2073b6d-3dee-4fbb-ae04-086b5aa7de18**,5280символов, прочитан **07:48:44UTC / 10:48:44МСК**: destination-bind CLOSED, remaining0. Сводный статус **PASS_H03_COMPONENTS_AND_LOCAL_INTEGRATION_ONLY** относится к библиотечной основе, а не полному агенту. [Реестр review](H03_CHAT2_REVIEW_INTAKE.md). Закрытые четыре findings не переоткрываются только из-за этого отдельного замечания; всему текущему writer или новому QA-diff одобрение старого пакета не приписывается.

**H04 не начат.** Эта квитанция не разрешает обучение estimator, generated code, live Qwen или запрос остатка ключа. Следующие этапы и официальный сабмит имеют собственные команды и приёмки; автоматического перехода нет.

| Непроверенное свойство | Сохранённая граница |
| --- | --- |
| Peak temporary RAM TF-IDF transform | **P1 OPEN**: проверка nnz/bytes результата после transform не ограничивает все временные выделения библиотеки; нужны preflight/batching и адресная проверка |
| Полная OS-граница, labels/secrets, process tree, nested capabilities | **H05 NOT_RUN / UNKNOWN**; Python view/schema/grant и локальный внешний Docker не заменяют изоляцию worker |
| Общий 10 800-second runtime и принудительное прерывание | **NOT_RUN**; cooperative budget checks не доказывают hard deadline всего дерева и полный трёхчасовой запуск |
| Frozen refit | **NOT_RUN**: PhaseGrant/FrozenRecipe проверены как метаданные, `refit_performed=false`; реального refit модели нет |
| Официальный образ и full37 | **UNKNOWN**; локальные Python 3.12.3 / dev13 direct pins / 45 distributions не являются официальной средой |
| Прогнозный baseline, outer/public-quality, tools и AutoResearch | **H04/H06/H07 NOT_RUN**, model-fit/Qwen API 0; форматные константы не доказывают качество |
| Необязательные H02.4 checker P1 | Положительный optimized-контроль и own-checker SHA в будущих actual JSON не закрываются автоматически H03-проверками; прежние квитанции не переписываются |

Компонентный PASS не переводит автоматически все 74 основных сценария и 17 частично пересекающихся HARN-T в PASS. Каждая строка требует собственного относящегося доказательства.

## 6. Экспортированные квитанции

Ниже ссылки на документированный JSON-экспорт вместо ignored runs. Файлы экспортированы побайтно; их SHA рассчитаны при подготовке сводки. Исходные и исторические JSON этим документом не изменялись.

### Текущие after и регрессионные проверки

| JSON | SHA256 |
| --- | --- |
| [H031_PROFILE_RESULT.json](H031_PROFILE_RESULT.json) | `22c8ed432c959977c80c564ce3030f0448fb9de95aad02ad6109e326d8503eec` |
| [H032_PREPROCESSING_RESULT.json](H032_PREPROCESSING_RESULT.json) | `4bc94cef6e59af8b80af67029fd057a0d5d1f020b52bff3887128a9f6c8d3222` |
| [H033_METRICS_VALIDATION_RESULT.json](H033_METRICS_VALIDATION_RESULT.json) | `2657abed65d1936f7f7a443349e94014f544df93e414b1f370dddf0f2b6581ab` |
| [H034_SUBMISSION_V2_RESULT.json](H034_SUBMISSION_V2_RESULT.json) | `8c288b6248998d56a55793e472db0e9e6f6db1da7affc02c6c391fd73eafbb1e` |
| [H03_INTEGRATION_V2_RESULT.json](H03_INTEGRATION_V2_RESULT.json) | `cffb6ae14d55c7304e0fc3a7cb1f162fc70c7231190dfa7c1632957bf4dc33f0` |
| [H03_CONTAINER_V2_RESULT.json](H03_CONTAINER_V2_RESULT.json) | `f4ab0d4fb5be8fc6b6806ae1dbb7bfe0a2353599b95d30958aa6d5bb64daf411` |
| [H03_CONTAINER_INTEGRATION_V2_RESULT.json](H03_CONTAINER_INTEGRATION_V2_RESULT.json) | `c00aa3de641dad808876ab0f8c97f815ed2736a49237f50787b036e80b9def41` |
| [H03_CONTRACT_REGRESSION_RESULT.json](H03_CONTRACT_REGRESSION_RESULT.json) | `a9e4476838a58b812b2a8af179a27eb30a3a8ad46d7a23d12f0b265fd764d74e` |
| [H03_BOOTSTRAP_REGRESSION_RESULT.json](H03_BOOTSTRAP_REGRESSION_RESULT.json) | `e949798fbdf8a0d18fca0af08e9534dbfa6a736173afb4b8785b3eedc32ff4eb` |
| [H03_LITERAL_PLATFORM_CLI_RESULT.json](H03_LITERAL_PLATFORM_CLI_RESULT.json) | `dcb9613758ba05537f8c58ed267d1182d15f1259e5dd5562ace4cece2079f983` |

### Адресные before

| JSON | SHA256 |
| --- | --- |
| [H032_PARTITION_BEFORE_RESULT.json](H032_PARTITION_BEFORE_RESULT.json) | `43c5adc6b7f1e60441166384502ba033661d399b3388ff1d1c081add5995627f` |
| [H034_MAPPING_BEFORE_RESULT.json](H034_MAPPING_BEFORE_RESULT.json) | `d2663332e3caa3db94cf94a4d48ab93c4c06e997be576636a08dcc7731665458` |
| [H033_METRICS_BEFORE_RESULT.json](H033_METRICS_BEFORE_RESULT.json) | `8525fcc79082c3b181987249b4ab58680133eb2b599cae2f115c75f69660a579` |
| [H031_RECORD_BEFORE_RESULT.json](H031_RECORD_BEFORE_RESULT.json) | `a7cce6471614750954036bee940b87152c9fabbd60e205d0700a83191c62518d` |
| [H034_SUMMARY_BEFORE_RESULT.json](H034_SUMMARY_BEFORE_RESULT.json) | `827265083331ccb68a5bcc072e453d5d012266c7bec9e40021809d77e45d1493` |
| [H034_DESTINATION_BEFORE_RESULT.json](H034_DESTINATION_BEFORE_RESULT.json) | `8f060522126b68fa7de09054fba2c823e79042e3fe393f12e2bc732b31d292bd` |

### Предыдущий after-срез до destination-bind fix

Следующие четыре файла остаются неизменной историей writer `ca4f1cde…`. Для текущей приёмки назначения CSV используются V2 выше, а прежние **15/68** не выдаются за проверку нового writer.

| JSON | SHA256 |
| --- | --- |
| [H034_SUBMISSION_RESULT.json](H034_SUBMISSION_RESULT.json) | `6d162caf37d749ac5568f045857c52663b36a8583862d1b1d526a82b8ee8b3d1` |
| [H03_INTEGRATION_RESULT.json](H03_INTEGRATION_RESULT.json) | `fff1ec1920569fe8733308fec8ac697c15e70bbcd0590dfe81bb60c5dee870ed` |
| [H03_CONTAINER_RESULT.json](H03_CONTAINER_RESULT.json) | `7426a82511f7b14818de773118af7223e6f529f974ea21042b1a12cf85bcdd5b` |
| [H03_CONTAINER_INTEGRATION_RESULT.json](H03_CONTAINER_INTEGRATION_RESULT.json) | `32bc0424ece47975827c6dd0d66596e8ecf31715b4f36befe960e68ee12aac1b` |

## 7. Идентичность текущего core

SHA дисковых файлов сверены с `source_sha256` WSL/Docker V2; расхождений нет. Полные checker/dependency identities находятся в соответствующих JSON.

| Файл | SHA256 |
| --- | --- |
| `solution.py` | `0a6a30ccf53a95cb75a96c8edf7d449fdd393e573027a1188c9adc7189d0f177` |
| `aegml_contracts.py` | `c20b9002447f2350f0c03a30696fe97dde7b605196d2d06f13a6bbd72be580f7` |
| `aegml_input.py` | `64ad6eb5b8bee5f22d71d88bbb1ea38e82e4821e49594e64f66fd1a5007e7bdb` |
| `aegml_schemas.py` | `0e385034dfd0ddfdb186a4aa2f9e1cd43b33ce83ba9dc28ced5365b76d826715` |
| `aegml_profile.py` | `3d7976378677a15d40706628375174cf01bd84993f11b42894c55bf6365ebbce` |
| `aegml_preprocessing.py` | `436bbc5da74d724f8604b23444e152b1007fb571af2d217d7c659b5b8abf4f09` |
| `aegml_metrics.py` | `c697a4b421efe31dbbffcecd0d7229467bad5ebb48dff444ad03868104d06345` |
| `aegml_validation.py` | `3d6200cd982b3e94cecc21df7d9b5417eb634a821046b14cb122f03f1334cbd5` |
| `aegml_submission.py` | `42692226bd5aae056c2340aa189d793b32add3b3c8495502ee54d04ed98c2524` |
| `requirements.txt` | `9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6` |

Этот файл подготовлен чтением уже завершённых квитанций и проверкой их ссылок/SHA. При редактуре новые runtime-тесты, установки, модели или API-вызовы не запускались.
