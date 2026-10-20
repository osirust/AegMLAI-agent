# AegMLAI-agent

Проект автономного ML-агента для трека Альфа-Будущее 2026: новое условие и данные → контракт и валидация → обучение → Qwen AutoResearch → проверенный `submission.csv`.
Приоритеты — исследовательский цикл, перенос на новые задачи, измеренное качество и ответ в ресурсах платформы.

**Сейчас:** H02.3 завершён как **PASS_H02_3_CONTRACT_ONLY**: TaskContract, resolver и встроенные схемы, 34 метода / 76 сценариев / 4 CLI; [квитанция](docs/H023_RECEIPT.md). H02.1 LOCAL_SUBSET и исторический H02.2 BOOTSTRAP_ONLY (24 метода / 51 сценарий / 37 CLI) сохраняются, [квитанция H02.2](docs/H022_RECEIPT.md). Модели, измерения RMSE/F1, A–E и AutoResearch ещё не выполнялись.

## Читать сначала

1. [PROJECT_STATE](PROJECT_STATE.md) — факты, ограничения и текущий подпункт.
2. [READ_FIRST](docs/READ_FIRST.md) — маршрут чтения.
3. [TECHNICAL_SPEC](docs/TECHNICAL_SPEC.md) — нормативное полное ТЗ.
4. [WORK_BLOCKS](docs/WORK_BLOCKS.md) — 50 небольших заданий с входами, выходами и приёмкой.

Детали: [Qwen harness](docs/QWEN_HARNESS_DESIGN.md), [математика](docs/MATHEMATICS_AND_VALIDATION.md), [обзор AutoML](docs/AUTOML_RESEARCH_BRIEF.md), [план экспериментов](docs/RESEARCH_PROTOCOL.md), [backend](docs/BACKEND_CONTRACT.md), [время и отказы](docs/RUNTIME_AND_FAILURES.md), [среда](docs/LOCAL_ENVIRONMENT.md), [источники](docs/RESEARCH_SOURCES.md).

## Контракт платформы

По переданной владельцем инструкции платформа выполняет **`python3 solution.py task.md`** из каталога задачи. `submission.csv` создаётся рядом.
ZIP до 100 МБ; консервативный предел — **`100000000` байт**. В архиве без папок лежат только:

- `solution.py`;
- неизменённый предоставленный `requirements.txt`;
- собственные дополнительные корневые `.py`, для P0 — `aegml_*.py`.

Платформа копирует только эти файлы. Пакетные каталоги, JSON/prompts/config assets, данные, сторонние библиотеки и wheels недоступны из ZIP.
Схемы уже встроены в `aegml_schemas.py`; для будущих prompts предусмотрен `aegml_prompts.py`. Зависимости устанавливает платформа из предоставленного списка; собственный pip во время запуска недоступен.
Локальное подмножество зависимостей не заменяет submission requirements. Существующий исходный список из 37 pins не перезаписывается.
Рабочие папки и файлы в cwd/подкаталогах/`/tmp` разрешены во время выполнения; запрет папок относится к загрузочному архиву.
Платформа: Python 3.12, 8 CPU / 32 GB и до трёх часов на отдельную задачу; тот же код запускают на двух неизвестных private-задачах.

Boosters сначала ставит посылку в очередь: «Решение находится на проверке» — ещё не результат. Признак успешного завершения — сообщение «Точность вычисления: …»; ошибки показываются отдельно.
Этот UI-текст не означает метрику classification Accuracy или прямое доказательство API/tools. Подробные технические логи доступны администраторам и могут отсутствовать в пользовательском интерфейсе.

## Что действительно реализовано

- Прежний `src/aegml` — демонстрационный JSON-планировщик. Его 21 тест и старый CI не подтверждают обучение конкурсной модели.
- `testmini/` — исторический stdlib-пробник. Strict v3 локально прошла 6 файловых сценариев с явным API off и 17 HTTP-stub сценариев. Созданы CSV с 22 449 / 41 166 строками: mean/majority без признаков.
- Владелец показал strict-посылку со score 0 и меткой «Лучшее решение». 3,2 секунды — длительность загрузки. Эти поля сами по себе не доказывают завершение Boosters; фактические exit/env/диагностика не получены.
- Условие strict-кода сохраняется: если он запущен в default required и штатно завершился с exit 0, он требует успешный API и валидный CSV. Это условный вывод, не наблюдавшийся live-tool результат.
- H02.1: `/home/aegml/venvs/aegml-ml-py312`, Python 3.12.3; 13 direct pins, всего 45 distributions; 44 dependency wheels плюс bootstrap pip 25.2; 9 package smoke и pip check PASS. [environment-lock.json](docs/environment-lock.json), run `runs/h02/h02-20261020T160924Z/`.
- Старая stdlib-venv сохранена с 0 distributions. Fit/live API не выполнялись; Docker и caps не менялись; полный образ остаётся UNKNOWN. Это `PASS_H02_1_LOCAL_SUBSET_ONLY`, не весь H02 и не H03/H04.
- H02.3: реализованы `aegml_input.py`, TaskContract/resolver в `aegml_contracts.py` и встроенные схемы `aegml_schemas.py`. Успешный CLI создаёт два свежих JSON в `.aegml_runs/<uuid>/`: `task_contract.json` и `row_alignment.json`. Возвращает exit 3 / implementation_incomplete с `contract_valid=true`, остальные full-agent флаги false; нового CSV полного агента нет.

Scope доказательств — [EVIDENCE_REGISTER](docs/EVIDENCE_REGISTER.md). Исторические mini ZIP/JSON не переписываются под новые правила; [mini-инструкция](testmini/README.md) не является текущим submission-контрактом.

## Текущая работа и очередь

После H02.3 — остановка. Следующий H03.1, затем до H03.5 → H04 выполняются по отдельным командам; далее worker/Qwen → AutoResearch → перенос и чистый ZIP. Все 74 основных и 17 пересекающихся будущих сценариев остаются NOT_RUN.
API-запросов 0; локальная конфигурация имеет статус CONFIGURED_UNVERIFIED, **LIVE_API_ON_OWNER_COMMAND_ONLY**. Безопасный tool call H06.2 требует отдельной команды владельца. H02.4 нужен до H07, подтверждённая OS-граница H05.1 — до generated execution.
Fit, CSV полного агента, tools, AutoResearch, Docker/caps, полный образ и worker boundary пока не проверены. WSL 24 GiB / Docker 20 GiB / 8 CPU остаются неприменённым планом; API-конфигурация сохранена вне Git.

Четыре участника готовят четыре независимые версии, затем сравнивают их. Этот чат — Владимир/Codex. Два пользовательских чата Vovan разделены: первый — research, второй — teacher. Read/send разрешены по назначению, чтение — по сигналу владельца без polling. Чужие сведения о ПК в этих чатах не заменяют локальные подтверждённые факты.
Чаты Vovan создал владелец: «1» — research, «2» — teacher. Новый ответ «1» прочитан по сигналу владельца: [CPU ML intake](docs/CHAT1_CPU_ML_INTAKE.md). Чату «2» после уведомления отправлен actual H023 code/SHA/результат; нового ответа в доступной истории пока нет. Старый c62a… про H02.2 уже учтён. Дальше читать по сигналу владельца без polling, перед каждой отправкой сообщать.
Репозиторий ранее переведён в private. Исходные данные, ключи, venv, веса, runs и dist в Git не включаются. AEGYX — отдельный проект на паузе, его среда не меняется.
