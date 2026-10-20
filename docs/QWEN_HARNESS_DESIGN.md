# Harness Qwen: управляемый AutoResearch с проверяемыми действиями

Редакция: 20.10.2026. Статус: **исследование и протокол будущей реализации; все приёмочные сценарии NOT_RUN**.
Прочитаны [BACKEND_CONTRACT](BACKEND_CONTRACT.md), [RUNTIME_AND_FAILURES](RUNTIME_AND_FAILURES.md) и [математический план](MATHEMATICS_AND_VALIDATION.md).
Это проект CLI: `solution.py` и плоские корневые модули `aegml_*.py`, не новый сервис и не изменение исторической testmini.
По полученной инструкции платформы ZIP содержит только корневые `.py` и неизменённый предоставленный `requirements.txt`, без папок.
Консервативный предел — `100000000` байт (100 МБ); запуск точно задан: `python3 solution.py task.md`.
Каталоги пакетов, JSON/YAML-конфиги, prompt/schema assets и сторонние библиотеки платформа не копирует; схемы и prompts встраиваются в `aegml_schemas.py` / `aegml_prompts.py`.
Исследование не включало запусков кода, WSL, установки пакетов, обучения, скачивания весов или запросов к LLM API.

## HARN.1. Назначение и основания дизайна

Harness — проверенный программный контур между LLM, инструментами, worker, evaluator и файлами результата.
Его цель — превратить предложение модели в ограниченное действие и проверяемый результат, сохраняя ранний валидный CSV.
Рассуждение модели не заменяет состояние процесса, измеренную метрику, проверку безопасности или атомарную публикацию.
Усиление harness — инженерная гипотеза: оно должно проверяться абляциями при одинаковых ресурсах, а не обещанием места на хакатоне.

Основания из первичных источников:

- Qwen описывает полный обмен «выбор функции → исполнение приложением → результат функции → продолжение модели».
  Формат зависит от шаблона/сервера; документация отдельно предупреждает о stopword-based разборе ReAct у reasoning-моделей.
  Берём машинный протокол действий, не извлечение команд из рассуждений. [Qwen Function Calling](https://qwen.readthedocs.io/en/latest/framework/function_call.html).
- Qwen-Agent показывает разделение LLM, tools и agent, но его примеры не подтверждают совместимость нашего endpoint или защиту нашего worker.
  Это источник паттернов; `qwen_agent` и MCP не входят в выданные requirements и не импортируются.
  [Официальный репозиторий](https://github.com/QwenLM/Qwen-Agent).
- ReAct исследует чередование планирования, действий и наблюдений. Для нас полезна проверяемая связь следующего действия с наблюдением,
  а не перенос результатов QA/интерактивных сред на ML-задачу. [Авторская публикация](https://arxiv.org/abs/2210.03629).
- Reflexion использует текстовую обратную связь и episodic memory без обновления весов модели. Берём краткую память о проверенных попытках;
  самооценка LLM не становится доказательством улучшения. [Авторская публикация](https://arxiv.org/abs/2303.11366).
- AIDE рассматривает код как узлы поиска, отдельно draft/debug/improve и сводку истории; полезны parent-связи, ограниченный ремонт и небольшое изменение за шаг.
  Полное дерево поиска — дополнительная гипотеза после P0, не обязательный старт. [Paper](https://arxiv.org/html/2502.13138v1), [авторский repo](https://github.com/WecoAI/aideml).
- MLE-bench разделяет получение валидной сдачи и её качество; в исследовании встречаются ранняя остановка, переполнение контекста/ресурсов и ошибочный выбор best.
  Это основания для независимых validator/budget/evaluator, а не гарантия пользы конкретного промпта.
  Основные эксперименты статьи использовали до 24 часов, 36 vCPU, 440 GB RAM и A10 — существенно иной режим.
  [Paper](https://arxiv.org/html/2410.07095v1), [официальный evaluator repo](https://github.com/openai/mle-bench).

Ни проценты успеха papers, ни выбор их моделей/библиотек не переносятся на наш неизвестный Qwen API, 8 CPU / 32 GB / 3 часа.
AIDE и MLE-bench также не устанавливаются; их датасеты/чужие решения не добавляются к конкурсному обучению.

- **Выход:** перечень заимствованных принципов и проверяемых собственных гипотез, без новых зависимостей.
- **Приёмка:** каждое утверждение о результате отделено от идеи дизайна; чужой benchmark не назван нашим тестом.

## HARN.2. Детерминированный controller, LLM как proposer

Supervisor владеет TaskContract, MetricContract, split, допустимыми файлами, бюджетом, registry, evaluator и публикацией CSV.
LLM предлагает гипотезу, код/конфигурацию и следующий разрешённый шаг; она не изменяет правила и не присваивает себе `success`.
Ключевые инварианты проверяются независимо от того, насколько убедительно сформулирован ответ модели.

| Решение | Кто принимает его окончательно |
|---|---|
| Роли target/id, поддержка метрики, направление и схема прогноза | Проверенный контракт с provenance; конфликт явно фиксируется |
| Выбор следующей содержательной гипотезы/кода | LLM предлагает; controller проверяет допустимость, дубликат и остаток бюджета |
| Запуск worker и остановка дерева | Executor под supervisor, после проверки границы изоляции |
| Значение метрики и keep/revert | Независимый evaluator и фиксированное правило сравнения |
| Запись итогового CSV и завершение | Supervisor после проверки фактических артефактов и обязательных стадий |

P0: один управляющий контекст Qwen, один активный обучающийся кандидат; роли researcher/coder/critic могут быть последовательными.
Проверенный код репозитория и недоверенный код runtime-кандидата — разные уровни доверия.
Доверенный evaluator не импортирует кандидата и не исполняет формулу метрики из task.

- **Выход:** версия policy и разрешённые переходы состояния, закреплённые за проверенными модулями.
- **Приёмка:** предложение отменить deadline, открыть labels или назначить ложную метрику не меняет инварианты.

## HARN.3. API_WAIT и два явных транспорта действий

`Qwen3.8-27B` — буквальное обозначение из кейса, **не установленный provider model ID**.
`OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL` задаются организаторами; имя SDK не разрешает другой API/provider или модель.
Нельзя подбирать похожий model ID, обращаться к запасному provider или молча использовать стандартный сервер SDK.
Поддержка native tools, JSON response format, streaming, thinking flags, context size и concurrency пока UNKNOWN.

1. Предпочтительный режим — `native_chat_tools_v1`: явные tools, полученные `tool_calls` и ответ с соответствующим `tool_call_id`.
2. Если native tools не поддержаны, допустим **отдельный настроенный и проверенный** `structured_json_actions_v1`.
   Модель возвращает один JSON action; локальный adapter валидирует его и передаёт в тот же dispatcher.
   API-параметр `response_format` используется только при подтверждённой поддержке; локальная проверка JSON обязательна в любом случае.

Выбор фиксируется в capability receipt: config/profile version, tool schema SHA, mode, проверенные поля и ограничения.
Отказ native tools не превращается незаметно в текстовый успех. Переход режима — явное событие с причиной и отдельной приёмкой.
Нативный transport и JSON-adapter получают одинаковые полномочия; ни один не даёт свободного shell или `eval`.
Qwen-Agent показывает возможность шаблонной адаптации, но не является нашей зависимостью или доказательством её работоспособности здесь.
P0 обрабатывает только завершённый ответ; из частичного stream, `reasoning_content`, Markdown или фразы «Action:» ничего не исполняется.
Отсутствие финального текста допустимо у валидного tool call; reasoning без требуемого действия не считается вызовом инструмента.

- **Выход:** два versioned transport adapters по одному ActionContract, с явно выбранным режимом.
- **Приёмка:** отдельно доказан action → реальный безопасный tool → использование его результата моделью; plain «OK» этого не закрывает.

## HARN.4. Typed tool registry с ограниченными полномочиями

Registry статичен для версии harness. На каждый tool заданы schema/version, доступные фазы, тип эффекта, handler и лимиты.
Имена из ответа ищутся только в allowlist; динамический импорт по строке, URL-fetch и произвольный subprocess-инструмент отсутствуют.

| Действие P0 | Ограниченные входы | Результат и запрет |
|---|---|---|
| `read_profile` | ID разрешённого раздела, ограниченный список колонок | Сводка T_fit/контракта; не outer и не весь CSV |
| `read_artifact_summary` | Artifact ID текущего run и ожидаемый SHA | Ограниченная сводка/фрагмент; не чтение произвольного пути |
| `propose_candidate` | Parent ID/SHA, hypothesis, evidence refs, ограниченные source/config | Новый immutable candidate; не запуск и не изменение harness |
| `run_experiment` | Candidate ID, ожидаемая версия ExperimentSpec | Один допущенный job; data/split/metric/budget назначает controller |
| `get_result` | Завершённый experiment ID текущего run | Проверенная метрика и ограниченная диагностика; не raw validation labels |
| `finalize` | Причина остановки, ссылка на желаемого кандидата | Запрос финализации; supervisor сам выбирает допустимый best-ready и проверяет стадии |

Чтение и вычисление имеют разные бюджеты. Нельзя использовать read-only tool как скрытый бесконечный просмотр данных/логов.
Схема ограничивает required/enum/types, длины строк/списков/source, число полей, глубину JSON и объём ответа.
Неизвестные поля, NaN/Inf, повторяющиеся JSON-ключи, double-encoded arguments и лишние actions отклоняются явно.
Лимиты задаются конфигом и проверяются до аллокации большого содержимого; конкретные значения уточняются коротким пилотом.
Нормализованный envelope содержит `schema_version`, `run_id`, `step_id`, `expected_state_version`, `action`, `arguments` и provenance.
Authority-поля run/policy/split назначаются controller, а не принимаются на веру из arguments.
P0 допускает одно mutating action за assistant turn; неоднозначный набор действий не исполняется частично.

- **Выход:** ToolSpec/ActionEnvelope/ToolResult schemas и тестовые vectors обоих транспортов.
- **Приёмка:** ошибка типа/имени/фазы/размера/версии не создаёт job, файла или побочного эффекта.

## HARN.5. Состояния, подтверждения и идентичность действия

Основной путь: `contract_ready → baseline_ready → action_ready → candidate_admitted → executing → snapshot_validated → scored → kept/rejected`.
Ветви `api_failed`, `policy_rejected`, `syntax_failed`, `worker_failed`, `timed_out`, `invalid_prediction`, `invalid_metric`, `duplicate`,
`uncertain_effect` и `stopped_budget` различаются. Ни stderr, ни свободный текст модели не переводят job в `scored`.
Проверенный CPU baseline и ранний CSV возможны до завершения исследования; это не выдаёт API/tools/research PASS.
Во время длительного fit controller ждёт terminal job state, не расходуя LLM-вызовы на постоянный polling.
Сетевой запрос, вернувший assistant action, уже закончен; tool result добавляется только после фактического завершения действия.

Различаем четыре ключа:

- `run_id`: уникальная изолированная задача; чужие модели, outputs, кеш и память не наследуются.
- `call_handle`: run/assistant-turn/provider-tool-call ID. Для JSON-mode ID выдаёт adapter/controller; transport ID не используется как путь.
- `effect_key`: controller-хеш tool version и валидированных arguments с привязкой к run, parent/state/spec. Повтор одного эффекта не запускается повторно.
- `experiment_dedupe_key`: единый канонический состав ниже; exact source bytes, а не нормализованная программа.

Одинаковый call_handle с иными arguments — `protocol_conflict`; тот же эффект под новым transport ID возвращает существующий результат/статус.
Для повтора сначала проверяются schema/run binding и существующий ledger record; повтор уже завершённого эффекта не отклоняется лишь потому, что current state успел измениться.
Новый эффект проходит expected-state/policy/budget проверки. Его identity связывается с immutable принятым spec, а не пересчитывается из текущего счётчика состояния.
Для намеренного повторного измерения нужны явные replicate/seed и новый ExperimentSpec, а не обход dedupe случайным ID.
Хеш ловит точное операционное совпадение. Он не доказывает семантическую эквивалентность любых двух Python-программ.
Canonicalization применяется к известным схемам config; исполняемый код не «упрощается» изменением пробелов/AST ради совпадения SHA.

- **Выход:** детерминированные правила ключей и связей request/attempt/action/effect/experiment.
- **Приёмка:** повтор после сетевого сбоя не создаёт второй fit; конфликт payload по одному ID не маскируется как кешированный успех.

Канонический `experiment_dedupe_key`: exact executed source bytes SHA + canonical config + input/data/split/metric/prediction-schema SHA + seed/replicate + versions/environment-profile SHA + declared training budget. Текущее remaining-time не меняет identity уже принятого эффекта. Код не нормализуется пробелами/AST. Это определение точного операционного повтора, не обещание семантической эквивалентности программ.

## HARN.6. Журнал эффекта и восстановление без обещания exactly-once

До запуска persist `intent/admitted` с effect_key, spec SHA и job ID; после запуска — process ownership и terminal outcome.
Результат фиксируется только по фактам: завершение worker, неизменный snapshot, валидный прогноз, metric record.
Crash между эффектом и записью результата создаёт `uncertain_effect`, а не разрешение повторить всё вслепую.
Controller проверяет принадлежащий job, журнал и артефакты; непротиворечивый результат восстанавливает ссылками/SHA.
Нельзя гарантировать exactly-once для любого сбоя только словарём idempotency keys; неопределённость должна оставаться видимой.
Автоматическая компенсация не удаляет исходники или чужие файлы. Очистка касается лишь job-owned временной области.
Восстановление внутри run не равно переносу кеша между двумя независимыми задачами; повторный запуск не подхватывает чужой `submission.csv` как новый успех.

- **Выход:** append-only event ledger с intent/commit, статусом неопределённости и проверяемыми ссылками на артефакты.
- **Приёмка:** сбой после старта/после записи/до commit не даёт ни двойного fit, ни ложного `completed`.

## HARN.7. Candidate → snapshot → evaluator → best-ready

LLM предлагает полную ограниченную версию source либо ограниченный patch к конкретному parent SHA; P0 формат выбирается один и версионируется.
Controller сам вычисляет code/config SHA, проверяет parent и binding ExperimentSpec. Чужая или устаревшая база не применяется молча.
Syntax/AST/import-policy checks только отсеивают часть ошибок; они **не являются доказательством безопасности** и не запускают кандидат на host.
Полный Python выполняется только после подтверждения OS/контейнерной границы H05. При её отсутствии generated code fail-closed;
режим проверенных рецептов обозначается отдельно и не закрывает F02 code generation автоматически.

Во время поиска worker видит T_fit X/y и X_inner_score для predict, но не y_inner_score/outer. Early stopping и AutoML CV в этой фазе — только внутри T_fit. После freeze действует отдельное разрешение train labels полного development, описанное ниже; outer y всегда закрыты.
Worker выдаёт ограниченный data-only прогноз. Supervisor копирует его в собственный immutable snapshot вне доступной worker записи,
проверяет размер/shape/ID/finite/class order и передаёт evaluator именно этот snapshot, а не изменяемый путь кандидата.
Python кандидата, его pickle/joblib или модель не загружаются в процесс supervisor/evaluator; refit/predict остаются внутри worker boundary.
Синтаксически правильный прогноз ещё не измерен: metric record создаёт независимый evaluator с фиксированными labels/scale/direction.

Разделяются `quality_best_seen` и `best_ready`: лучший inner score не означает, что тестовый CSV уже успешно сформирован.
Новый best-ready требует корректного test prediction и publication receipt; при ошибке predict остаётся прежний пригодный CSV.
Публикация: проверенный временный файл → publish intent со старым/новым SHA → атомарная замена CSV → publish committed.
CSV и журнал не объявляются одной магической транзакцией: при сбое между ними recovery сверяет текущий SHA с intent.
Refit по выбранному рецепту на расширенном train — отдельный артефакт; прежняя inner-метрика не становится измерением качества нового test-прогноза.

- **Выход:** immutable CandidateRecord, ExperimentRecord, MetricRecord и BestReadyRecord с раздельными ссылками на код/прогноз/публикацию.
- **Приёмка:** подмена worker-файла после snapshot не меняет оценку; crash/невалидный новый CSV сохраняет прежний best-ready.

В PRIMARY применяется `FROZEN_REFIT_FULL_DEVELOPMENT`. Во время поиска worker не видит y_inner_score. После freeze кода, модели, гиперпараметров, конфигурации preprocessing и числа итераций supervisor запускает отдельную фазу в той же OS-границе: former inner-метки теперь разрешены только как train labels полного development. Ни эти метки, ни новые refit-ошибки не возвращаются LLM для продолжения поиска. Outer-метки остаются закрытыми. Для регрессии это refit1–4→outer5, для классификации полныйdevelopment→outer. Refit обучает состояния/веса по замороженному рецепту, а не запускает новый HPO. Он входит в общий бюджет; `refit_performed`, `trained_on_SHA` и fallback_reason фиксируются. NO_REFIT — отдельная абляция; fallback не объявляется измерением завершённой primary-процедуры.

## HARN.8. Контекст и память с provenance

Память не является изменяемым системным prompt. Неизменная policy хранится в проверенном коде и добавляется controller отдельно.
Текст task/dictionary, значения данных, stderr, комментарии кода и предложения предыдущей LLM рассматриваются как недоверенные данные.
Метки происхождения/разделители помогают интерпретации, но сами по себе не защищают от prompt injection; полномочия ограничивает dispatcher/OS.

| Слой | Что хранит | Кто определяет факты |
|---|---|---|
| Evidence store | Разрешённые исходники, bounded logs, code/prediction snapshots | Controller присваивает ID/SHA и уровень доверия |
| Experiment ledger | Статусы, config/split/metric SHA, значения evaluator, время, причины отказа | Только проверенные исполнители и evaluator |
| Rolling digest | Incumbent, последние релевантные попытки, negative evidence, pending hypothesis, остаток бюджета | Поля фактов строятся из ledger; LLM может предложить отдельную интерпретацию |
| Turn context | Policy + TaskContract/profile + разрешённая digest + выбранные artifact summaries | Controller собирает ограниченный prompt с версиями/ссылками |

У digest: `summary_version`, `through_event_seq`, `source_refs/SHA`, scope task/split, facts, hypotheses, unknowns, failures и superseded refs.
Компрессия не меняет метрики, kept/rejected, label policy, negative evidence и ограничения. Проверяется совпадение с authoritative ledger.
LLM-сводка «кандидат улучшил F1» остаётся интерпретацией, пока не привязана к существующему MetricRecord; фальшивая ссылка отклоняется.
Negative evidence содержит scope: ошибка конкретной конфигурации/seed/split не превращается в правило «этот алгоритм всегда плох».
Старые полные логи не добавляются к каждому запросу; нужный фрагмент получается bounded read по artifact ID текущего run.
Raw y_inner_score, outer-статистики, секреты, личные файлы и целые CSV в memory/prompt не включаются.
Рассуждения/`reasoning_content` не нужны как журнал доказательства; достаточно кратких hypothesis/rationale/evidence refs и фактических действий.

- **Выход:** MemoryDigest schema, retrieval policy и deterministic factual compression, отдельно от необязательного LLM reflection.
- **Приёмка:** после compression сохраняются худшие попытки/неизвестное; инъекция из лога не становится policy/tool action; метрика не меняется пересказом.

## HARN.9. Практический протокол rolling AutoResearch

1. Получить проверенный TaskContract, профиль T_fit, frozen split/metric и измеренный baseline; не подменять его sample placeholders.
2. Сформулировать одну конкретную гипотезу: observation refs → предполагаемая причина → изменение → ожидаемый знак эффекта → план измерения.
3. Создать кандидата с parent SHA; пройти schema/syntax/policy/dedupe/budget. Неисправимый контракт останавливает ветку до обучения.
4. Исполнить один эксперимент; получить независимую метрику и ограниченный error summary.
5. Применить math keep/revert с заранее заданными direction/epsilon/tie rules; записать и положительный, и отрицательный результат.
6. Обновить digest; следующая гипотеза ссылается на реальный результат и объясняет, что нового проверяется.
7. При нехватке времени или исчерпанной допустимой политике поиска финализировать best-ready, сохранив причины остановки.

Различать draft, debug и improve: исправление import error ещё не доказывает улучшение ML-качества; failed fit не даёт численной delta качества.
Для improve предпочтительно одно содержательное изменение, чтобы интерпретация была проще; причинный эффект всё равно ограничен stochasticity/выбором.
Примеры именно будущих гипотез, а не уже найденных улучшений:

| Наблюдение | Проверяемое действие | Что должно решить keep/revert |
|---|---|---|
| Пропуски признака подтверждены профилем T_fit | Добавить отдельный missing indicator без удаления test-строк | Исходный RMSE/F1 и отсутствие schema/row loss |
| Низкий recall редкого класса подтверждён разрешённым агрегатом evaluator | Проверить ограниченные train-frequency weights | Основной task Macro F1, precision/recall и FP по другим классам; улучшение не предполагается |
| Кандидат превысил память | Уменьшить допустимую сложность/объём обучения при том же split | Завершение в лимите и новая измеренная метрика; ресурсный успех не выдан за рост качества |

Error analysis допускает bounded агрегаты evaluator: ошибки по подтверждённым группам/классам и свойства прогнозов, без строк true labels.
Группы/срезы заранее разрешены; произвольные запросы по одному объекту через metric oracle не считаются безопасным чтением.
Даже агрегаты дают адаптивную информацию: inner остаётся tuning, не независимым доказательством переноса. Outer в этот цикл не возвращается.
Нельзя повторять точный rejected experiment без нового основания/replicate contract; количество гипотез не является целевой метрикой.

- **Выход:** связная HypothesisRecord → CandidateRecord → ExperimentRecord → MetricRecord → DecisionRecord последовательность.
- **Приёмка:** не менее двух связанных измеренных попыток в H07 и отдельный отказ от известного ухудшения; выводы пересчитываются по артефактам.

## HARN.10. P0 — один incumbent; дерево поиска — проверяемое P1

P0 имеет линейный цикл управления с одним incumbent и последовательными кандидатами. У каждого есть parent ID;
отклонённый потомок сохраняется, затем поиск возвращается к допустимой основе. Полный поиск по frontier не нужен для первого результата.
Небольшой лимит debug и bad-action streak фиксируется конфигом; ремонт не съедает весь срок без новых измерений.
Это использует идеи AIDE о локальном изменении и сохранении истории, но не заявляется воспроизведением полного AIDE.

P1 может сравнить bounded branching: несколько draft-направлений, ограниченные frontier/depth, выбор родителя по качеству и ожидаемой стоимости.
Обучение всё равно одно одновременно; ветки не получают собственные 8 CPU/32 GB/3 часа. Ни MCTS, ни beam search не обещаются победителями заранее.
Дерево/несколько контекстов могут увеличить разнообразие и одновременно ухудшить latency/долю завершённых fit — обе стороны измеряются.
При E researcher/coder/critic работают одной разрешённой Qwen; evaluator/supervisor остаются общими и детерминированными.
Один pool и доступы C/D, а для AutoML B — честный отчёт о различиях internals согласно математическому плану.
Сравнивать P0, branch search и E по качеству, валидности, времени первого CSV, peak memory и результатам всех повторов.

- **Выход:** P0 search policy и отдельная конфигурация/гипотеза P1 с общим BudgetContract.
- **Приёмка:** одинаковый общий wall-clock; отрицательный результат ветвления/мультиагентности допустим; лучшая увиденная outer-версия не названа независимой оценкой победителя.

## HARN.11. Контекстный и временной бюджет

Для каждой задачи один deadline от начала `solution.py`; чтение, LLM, backoff, worker, evaluator, refit/predict/write входят в 10 800 секунд.
Начальные рабочий горизонт/резерв из RUNTIME_AND_FAILURES — гипотезы до пилота; harness не получает дополнительного времени за новый turn/agent.
Перед LLM-вызовом проверяются remaining time и резерв на безопасную финализацию; перед fit — ещё и измеряемая оценка его стоимости/RAM/диска.
До первого пригодного результата бюджет не расходуется бесконечно на elaborate planning; ранний baseline и валидный CSV имеют отдельный приоритет.

Размер prompt выводится из подтверждённого context limit минус response budget и запас. Размеры из примеров другой Qwen не считаются нашими.
Без подтверждённого tokenizer/provider accounting byte/character estimate — лишь консервативная оценка; её нельзя подписывать точным числом tokens.
Context overflow даёт bounded shrink/retry с сохранением provenance, а не бесконечное усечение важных правил или тихое выпадение tool results.
Ошибка схемы допускает ограниченную коррекцию с кратким сообщением о причине; частичный JSON не исполняется.
401/403/неподдержанная конфигурация не повторяются бесконечно; временные сбои получают ограниченный backoff в том же deadline.
Retry задаётся на одном контролируемом уровне; скрытые многослойные повторы SDK/adapter/controller не должны перемножаться.
При uncertain API timeout usage остаётся unknown, если provider не вернул его; нулевой расход не выдумывается.
Число calls/attempts/token usage — техническая диагностика; денежные ограничения в рабочее планирование не добавляются.

- **Выход:** LLMRequestRecord с transport/model/config/prompt schema SHA, attempts, наблюдаемым usage, временем и причиной остановки.
- **Приёмка:** context overflow/429/retry/ремонт не выходят за общий бюджет; memory остаётся связной; последний валидный CSV сохраняется.

## HARN.12. Секрет и полномочия остаются вне candidate

Секрет доступен только LLM-клиенту; не включается в prompt, tool args, generated source, event ledger, errors, ZIP или worker env.
Ослабленный env не защищает от чтения родительского proc/файлов: фактическая OS/UID/mount/network граница проверяется отдельно по security-плану.
Worker не может менять supervisor/evaluator, split, secret files и authoritative артефакты; ограничены процессы, сеть и writable paths.
Свободный текст stderr и reasoning не получает права сетевого доступа. Redirect не пересылает ключ на другой адрес.
URL/model/config берутся из разрешённой конфигурации, не из task, tool result, кода кандидата или найденной в интернете инструкции.
Синтаксис/AST/import allowlist помогают диагностике; защита generated code требует проверенной границы исполнения, а не уверенности LLM-критика.

- **Выход:** явно разделённые LLM client, dispatcher, untrusted worker и evaluator с проверяемыми доступами.
- **Приёмка:** dummy canary недоступен кандидату/логам; изменение policy из task не даёт полномочий; неподтверждённая boundary блокирует generated execution.

## HARN.13. Безопасная capability-проверка после получения API

Сейчас все live capabilities UNKNOWN. Проверки ниже — будущая H06, не запуск в этом исследовании.

| Проверка | Что доказывает | Что не доказывает |
|---|---|---|
| C0: настройки и короткий assistant response | Доступность конкретной разрешённой конфигурации и формат ответа | Tools, code generation, ML-качество |
| C1: native tool schema и реальный безопасный handler | Native action transport для проверенного подмножества schema | Любые схемы, parallel calls или полный worker |
| C2: явный structured JSON adapter, если выбран | Parse/validate/dispatch того же ActionContract без native tools | Нативную поддержку tool_calls сервером |
| C3: модель использует непредсказуемый tool result | Продолжение по реальному наблюдению | AutoResearch, если ещё не было ML-эксперимента |
| C4: ошибки/ограничения на loopback и затем разрешённые live случаи | Корректные bounded failure paths выбранной конфигурации | Совместимость всех provider/model вариантов |

Безопасный handler `get_fixture_fact` принимает только фиксированный fixture ID, а nonce генерирует **после** вызова инструмента.
Модель должна вернуть полученный nonce и observation ref в валидированном подтверждении; заранее известный ей аргумент для echo этого не доказывает.
Handler не читает пользовательские файлы, не запускает generated code и не требует GPU. Raw y и реальные секреты не участвуют.
Native и JSON mode имеют отдельные receipts; неудача одного не маскируется успешным «OK» другого.
H06 требует LLM action → actual safe tool → LLM uses result. F02 отдельно потребует созданный код и реальное исполнение в проверенной границе.
После приёмки config/schema capabilities сохраняются для совместимости; факты `api_verified/tools_verified` текущего run не наследуются как выполненные от прошлой задачи.

- **Выход:** обезличенный CapabilityReceipt с mode, schema/config version, actual model ID при его получении и отдельными live/stub флагами.
- **Приёмка:** нет придуманных endpoint/ID и непройденных capabilities; nonce совпал с tool result; generated execution не запущен в H06 ради проверки транспорта.

## HARN.14. Честный RunOutcome и обязательные будущие проверки

Outcome отдельно хранит `contract_valid`, `api_verified`, `tools_verified`, `experiments_completed`, `research_completed`,
`submission_valid`, `termination_reason`, `warnings`, `artifact_sha` и выбранный transport mode.
CSV сохранён после позднего отказа — факт сохранности; незавершённый обязательный AutoResearch остаётся degraded/failed по backend-контракту.
Если обязательные стадии уже выполнены, отклонённая поздняя гипотеза не аннулирует их: выбирается прежний best-ready с предупреждением.
Ненулевой exit code и фактическая трактовка платформой пока не имеют подтверждённого evaluator-контракта; отсутствие штрафа не предполагается.
Исторические mini-файловые/stub тесты не закрывают ни один новый полный harness-сценарий автоматически.

| ID | Будущий сценарий / ожидаемый результат | Доказательство | Статус |
|---|---|---|---|
| HARN-T01 | Native безопасный action/result с непредсказуемым nonce | Обезличенный transcript, handler receipt и сверка nonce | NOT_RUN |
| HARN-T02 | Structured JSON mode проходит тот же handler и остаётся явно отдельным mode | Версия adapter/schema, action/result records | NOT_RUN |
| HARN-T03 | Plain OK/reasoning/Markdown не запускает действие и не закрывает tools/F02 | Отрицательные payload fixtures, отсутствие effect/job | NOT_RUN |
| HARN-T04 | Плохие типы/поля/дубли JSON/oversize/несколько actions отклоняются | Validator report и нулевой счётчик side effects | NOT_RUN |
| HARN-T05 | Повтор ID/эффекта не создаёт второй fit; другой payload по ID даёт conflict | Intent/commit ledger, число job starts | NOT_RUN |
| HARN-T06 | Crash между admission, start и outcome остаётся reconcile/uncertain, не success | Fault trace и ссылки/SHA найденных артефактов | NOT_RUN |
| HARN-T07 | Stale parent/state/schema запрещает применение code/config | Parent/snapshot SHA и отказ до execution | NOT_RUN |
| HARN-T08 | Синтаксически валидный недопустимый код не выходит за boundary | Policy/OS canary checks; отсутствие generated execution при неподтверждённой boundary | NOT_RUN |
| HARN-T09 | Подмена worker prediction после snapshot не меняет metric | SHA immutable копии, независимый пересчёт | NOT_RUN |
| HARN-T10 | Best inner candidate с плохим test prediction не уничтожает best-ready CSV | Два раздельных best records и CSV SHA | NOT_RUN |
| HARN-T11 | Crash на каждой стадии публикации сохраняет либо восстанавливает доказанный CSV | Publish intent/commit, old/new SHA | NOT_RUN |
| HARN-T12 | Compression сохраняет метрики/отказы/unknowns и отвергает выдуманные refs | Сравнение digest с ledger, bounded context report | NOT_RUN |
| HARN-T13 | Инъекции из task/stderr/памяти не меняют policy или полномочия | Canary fixtures, отказ dispatcher, неизменные contract SHA | NOT_RUN |
| HARN-T14 | Две гипотезы используют измеренные результаты; ухудшение отвергнуто | Связные experiment/metric/decision records | NOT_RUN |
| HARN-T15 | Ошибки API/context/retry и долгий worker ограничены общим deadline | Timeline, attempts, stop cause, preserved CSV | NOT_RUN |
| HARN-T16 | Чистая новая задача не наследует prompt memory/cache/model/output первой | Два run manifests и canary предыдущего run | NOT_RUN |
| HARN-T17 | P0 против branch/E при одинаковом бюджете, все результаты сохранены | Парная таблица качества/валидности/ресурсов и ограничений | NOT_RUN |

- **Выход:** сценарии приёмки с собственным scope и отдельным журналом реально выполненных результатов.
- **Приёмка:** PASS закрывает только воспроизведённый режим/SHA/сценарий; stub, replay и live результаты не смешиваются.

## HARN.15. Реализация по существующей карте модулей

Сначала корневые `aegml_contracts.py`, `aegml_tools.py`, `aegml_llm.py`: schemas, adapters и безопасная H06 fixture; без запуска кандидатов.
Константы схем и prompts находятся в корневых `aegml_schemas.py` и `aegml_prompts.py`; внешние JSON/text assets не требуются.
Затем `aegml_artifacts.py`, `aegml_budget.py`, `aegml_executor.py`: intent/commit, изоляция, bounded outputs и snapshot; безопасность H05 обязательна.
`aegml_metrics.py`, `aegml_validation.py`, `aegml_submission.py` дают независимые score/split/publication; `aegml_research.py` соединяет их с rolling loop.
Плановый ABI кандидата и data-only прогноз закрепляются до codegen; файлы создаются вместе с относящимися тестами, а не пустыми заглушками ради структуры.
После реального baseline — H07 две связанные итерации; затем перенос, controlled C/D ablation и только после этого возможные branch/E эксперименты.
Qwen-Agent/MCP/AIDE/MLE-bench не добавляются в requirements, ZIP или runtime. Совместимость и готовность нашего кода доказываются нашими артефактами.
Корневой submission `requirements.txt` — неизменённый предоставленный список из 37 pins; локальное подмножество H02.1 его не заменяет.
Платформа устанавливает зависимости из этого списка; `solution.py` не вызывает pip. Generated code и журналы можно создавать в task cwd/подкаталогах и `/tmp` во время запуска: запрет папок относится к загружаемому ZIP.
Сначала проверяется чистый запуск при копировании только root `.py` + `requirements.txt`; наличие dev-пакета или assets в репозитории не считается зависимостью, доступной на платформе.

- **Выход:** последовательные H-подпункты с работающим поведением, outcome и относящимися доказательствами.
- **Приёмка:** архитектурный документ не выдан за реализованный harness; перед переходом соблюдаются ТЗ, worker boundary и команда владельца.

## Реестр восьми ключевых первичных источников

| ID | Источник | Использование и предел вывода |
|---|---|---|
| S1 | [Qwen Function Calling](https://qwen.readthedocs.io/en/latest/framework/function_call.html) | Обмен actions/results, зависимость от serving/template; не сведения о нашем provider ID |
| S2 | [QwenLM/Qwen-Agent](https://github.com/QwenLM/Qwen-Agent) | Компоненты и адаптация протокола; паттерны, не импорт и не готовая sandbox-гарантия |
| S3 | [ReAct, Yao et al.](https://arxiv.org/abs/2210.03629) | План/action/observation; не parser reasoning-текста и не обещание ML-качества |
| S4 | [Reflexion, Shinn et al.](https://arxiv.org/abs/2303.11366) | Память обратной связи без обучения весов; факты памяти всё равно проверяются |
| S5 | [AIDE, Jiang et al.](https://arxiv.org/html/2502.13138v1) | Draft/debug/improve, дерево и summary; P1-гипотеза для наших ограничений |
| S6 | [WecoAI/aideml](https://github.com/WecoAI/aideml) | Референс code-search/артефактов; не пакет нашего разрешённого окружения |
| S7 | [MLE-bench, Chan et al.](https://arxiv.org/html/2410.07095v1) | Раздельные validity/quality, ресурсы/повторы и ограничения contamination; не гарантия private-переноса |
| S8 | [openai/mle-bench](https://github.com/openai/mle-bench) | Grading reports, описание среды/вариативности; чужая среда и данные не подменяют наш кейс |

Источники прочитаны 20.10.2026; живые README/docs могут меняться, paper IDs/версии указаны явно.
Сейчас подтверждено только содержание источников и подготовлен дизайн. Фактические tools/context/model ID provided Qwen,
качество generated code, безопасность worker, выигрыш от памяти/дерева/ролей и достижимость лимитов остаются непроверенными.
