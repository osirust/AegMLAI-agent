# H02.3: закрытие замечаний независимого review

Дата: 20.10.2026. **H023-ROLE-001, H023-DECL-001 и H023-ORDER-001 закрыты только в области проверенных контрактов парсера/resolver.** Это не приёмка H03, ML, Qwen API, CSV writer или OS-изоляции.

Основание — полная статическая рецензия чата «2» `a0eca288…`, сохранённая в `runs/h02/h024-chat2-review.txt`, SHA256 `c23079140a0b1631c557467dbc064097c95d85fd267f4a46f3d99c9d3453e763`. В рецензии тесты не выполнялись. Новый результат ниже получен фактическим Linux-прогоном root; повторный запуск при этой документальной сверке не выполнялся. Проблемы передачи/отображения ответа в UI не считаются доказательством ошибки нашего CLI.

## Квитанции и версии

| Результат | Фактический scope | SHA256 JSON |
|---|---|---|
| [H023_REVIEW_FIXES_RESULT.json](H023_REVIEW_FIXES_RESULT.json) | PASS_H02_3_CONTRACT_ONLY: 38 методов, 93/93 сценария, 4 CLI; оба public-набора действительно проверены | `8dcd2ce7d7a07074447a69068b1c41138e0b7454e039c15975f3b8d30f47c466` |
| [H023_REVIEW_FIXES_BOOTSTRAP_RESULT.json](H023_REVIEW_FIXES_BOOTSTRAP_RESULT.json) | PASS_H02_2_BOOTSTRAP_REGRESSION: 24 метода, 51/51 сценарий, 37 CLI | `ca516e6c5f2890d4ad4be898fbe45a2d293c3ca757e03fae86295ea8df684af9` |

Среда: Python 3.12.3, `/home/aegml/venvs/aegml-ml-py312`. Исходные Linux-квитанции находятся в `/home/aegml/checks/h024-20261020T184606Z/parser-review-fixes/attempt1.json` и `bootstrap.json`. Ошибок и unittest failures нет; source SHA до/после совпадают. SHA текущих файлов дополнительно сверены чтением:

- `aegml_contracts.py`: `151d5283a144ed7d8d5fd7618042d53ea129b00ce29a2ae8f5853d16deae6599`.
- `scripts/check_h023_contract.py`: `a55cea2e3212277708a017e2877639222a22de5080f261d131e662169afd35fd`.

Полные SHA остальных root-модулей и original requirements сохранены в новых JSON. [H023_RECEIPT.md](H023_RECEIPT.md), прежние attempts и их source SHA остаются историческими; они не переписаны как новая приёмка. В частности, прежний `H023_CONTRACT_RESULT.json` имеет SHA256 `92335095065789143b2494983c23691aa78f927d88e438d689777b0046ce15c9` и не заменён новым результатом.

## H023-ROLE-001 — согласование явных ролей

**Факт review:** явный `Target: y` мог переопределить dictionary role=ignore, а явный `ID: id` — role=feature. Payload при этом мог остаться внутренне согласованным и пройти schema, скрыв конфликт источников.

**Действие:** совместимость роли проверяется независимо от способа получения target/ID. Явное противоречие даёт `target_role_conflict` либо `id_role_conflict` с provenance; отсутствие записи в dictionary разрешено дополнить из task. Допустимый positional/output-only ID сохранён.

**Условие закрытия и результат:** `ContractChecks.test_review_role_conflicts_and_absent_role_completion` прошёл все четыре адресных случая: `H023-ROLE-001_target_ignore`, `H023-ROLE-001_id_feature`, `H023-ROLE-001_missing_target_declaration`, `H023-ROLE-001_missing_id_declaration`. Отказы содержат column/role и task/dictionary provenance, публикация при отказе не создаётся. Сохранён положительный сценарий `explicit_positional_mapping_preserves_output_only_sample_ids` общего набора. **CLOSED_H023_ROLE_CONTRACT_SCOPE.**

## H023-DECL-001 — полное значение директивы

**Факт review:** знакомая часть `RMSE, MAPE` могла превратиться в rmse, а `regression + clustering` — в regression. Для dictionary `RMSE(log1p(y))` отсутствовала равная task проверка шкалы, хотя payload заявлял original scale.

**Действие:** применена ограниченная грамматика полного значения, общая проверка метрики task/dictionary, явный отказ от неизвестного остатка и неподдержанной трансформации. Поддерживаемые original-scale пояснения, известные отрицания и EN/RU-формулировки сохранены.

**Условие закрытия и результат:** `ContractChecks.test_review_rejects_unparsed_declaration_remainders` прошёл `H023-DECL-001_unknown_metric_suffix`, `H023-DECL-001_unsupported_type_suffix`, `H023-DECL-001_dictionary_metric_transform` с кодами соответственно `unsupported_metric`, `unsupported_task_type`, `unsupported_metric_transform`. `ContractChecks.test_review_supported_en_ru_declarations_remain_valid` прошёл четыре положительных случая: полный EN RMSE, EN/RU Macro F1 с известным отрицанием Accuracy и native RU RMSE исходной шкалы. Оба полных public task также приняты. **CLOSED_H023_DECLARATION_GRAMMAR_SCOPE.**

## H023-ORDER-001 — источник порядка результата

**Факт review:** структурная директива повторно попадала в эвристический prose-pass. Соседний `test.csv` мог противоречить явному sample-порядку либо заполнить отсутствующее указание порядка.

**Действие:** структурные строки исключены из повторного толкования; окно соседних строк удалено. Свободный текст задаёт порядок только поддерживаемым утверждением в той же фразе. Конфликтные указания и неоднозначная перестановка остаются отказами.

**Условие закрытия и результат:** `ContractChecks.test_review_output_order_is_not_inferred_from_neighboring_filename` прошёл шесть случаев `H023-ORDER-001_*`: `explicit_sample_near_input_test`, `row_order_matters_is_ambiguous`, `explicit_test_identity`, `two_explicit_orders_conflict`, `english_same_statement`, `russian_same_statement`. В синтетической двухстрочной базе sample→test=[1,0]; output→test=[1,0] при sample и [0,1] при test. Неоднозначность даёт `ambiguous_output_order`, действительный конфликт — `output_order_conflict`. **CLOSED_H023_OUTPUT_ORDER_SCOPE.**

## Разрешённые public-контракты и отображения

Это метаданные read-only builder, не вычисленные RMSE/F1. В обоих случаях `target_scale=original`, `finite_policy=finite_only`, `adapter_version=registry.v1_pending_H03`.

| Набор | Resolved metric | Output order и основание | Train / test / sample; признаки |
|---|---|---|---|
| Регрессия | rmse; minimize; numeric; parameters={} | test; `task/output_order_statement`, строка120 | 53 308 / 22 449 / 22 449; 62 |
| Классификация | macro_f1; maximize; label; average=macro, labels=null; `sklearn_labels_none` | test; `sample_submission/equivalent_test_sample_order` | 87 670 / 41 166 / 41 166; 42 |

Направления строго различаются: `sample_to_test` — **индекс строки sample → индекс исходной строки test**; `output_to_test` — **индекс выходной строки → индекс исходной строки test**. Обе карты каждого public-набора проверены как полные перестановки и фактически тождественны. Поэтому их SHA внутри данного набора совпадают:

| Набор | Count каждой карты | SHA256 каждой карты |
|---|---:|---|
| Регрессия | 22 449 | `dc294512d544d4dbd31382a67f229207f0621422b6bff01b2e8429353a52fe85` |
| Классификация | 41 166 | `63ed05cd2450bcd39c87f7fb9a9f343fd496d84840afb47380f1c95ebb1fe923` |

Проекция признаков индексирует **полный test header, включая ID-колонки**, в порядке признаков train. Для 62 regression-индексов SHA256=`d83491a6f49f2b9870dd8d4eb141d0a83e8fa097ff9295edffd84554b9f2d6ec`; для 42 classification-индексов — `9b669fa350a15f13d4ab456869612801860848d589df68cb61930c16e5ef4a98`. SHA порядка имён признаков и остальные компактные сводки находятся в JSON. Кодирование хешируемых значений: UTF-8 JSON, ensure_ascii=False, sort_keys=True, компактные separators, без завершающей новой строки. Raw ID и target-строки в этих сводках отсутствуют; исходные пять файлов каждого набора сохранили SHA.

## Что не закрыто

Вопросы review перед H03 остаются проектными задачами: передача разрешённого fit каждому преобразованию; полная семантика восьми metric adapters и вероятностных колонок; связь SHA/alignment с будущим loader/writer и применение output→test ровно один раз. Проверка отображений не означает, что такой writer уже реализован. Численного качества, live API, обучения, полного агента, официального образа и OS-границы эти результаты не доказывают.

Для будущих материалов чатам владелец указал **GPT‑5.6 Pro**; фактический выбор модели пока не подтверждён. Новых запросов чатам в этой сверке не отправлялось. Следующий этап и дополнительные действия определяются последней командой владельца, а не наличием PASS этой группы.

## Адресное воспроизведение до исправления

Позднее отдельно выполнен [old-source baseline](H023_REVIEW_BASELINE_RESULT.json): сохранённый contracts SHA7dcae3cd…8da72 загружен под отдельным именем, current checker без main; запущены только три относящихся метода ROLE/DECL/ORDER. Реально получены13подслучаев:7ожидаемыхсбоев и6успешныхконтролей; все3finding воспроизведены. Статус EXPECTED_FAILURES_REPRODUCED_OLD_SOURCE_ONLY не является FAIL текущего кода: текущие38/93PASS относятся к SHA151d5283… . Baseline не перезаписывал source/dependencies/новые PASS-квитанции и не запускал public CLI, Docker, fit или API.
