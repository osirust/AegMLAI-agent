# Что читать и как поручать работу

Мы создаём полноценный ML-агент для новых задач. Обзор источников и ТЗ подготовлены; сейчас по прямой команде владельца выполняется **весь H03.1–H03.5**. Библиотечная основа данных реализована: профиль, предобработка, метрики/разбиения и writer. Состояния предобработки и TF‑IDF реально обучались; predictive estimator, Qwen и официальный submission ещё не запускались. Mini остаётся историей технической проверки.

H02.1 LOCAL_SUBSET, H02.2 BOOTSTRAP_ONLY, H02.3 CONTRACT_ONLY и H02.4 LOCAL_CONTAINER_ONLY завершены в своих областях; [квитанция контейнера](H024_RECEIPT.md), [исправления H02](H02_REVIEW_REPAIRS.md). Исторические попытки и SHA сохраняются. Актуальный H03 — в обновляемой [H03_RECEIPT.md](H03_RECEIPT.md): профиль имеет относящийся PASS и закрытый external static postfix review; текущие BUILT-binding и metrics/validation fixes, свежий общий прогон и review остальных компонентов ещё выполняются. Итоговый H03 PASS пока не объявлен.

## Начать с трёх файлов

1. [PROJECT_STATE.md](../PROJECT_STATE.md) — цель, факты, ограничения и текущий подпункт.
2. [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) — нормативное ТЗ: функции, контракты, данные/метрики, безопасность, этапы и проверки.
3. [WORK_BLOCKS.md](WORK_BLOCKS.md) — 50 малых подпунктов: входы, зависимости, будущие файлы, приёмка и остановка.

После этих трёх читать относящуюся дорожку, не весь комплект без причины:

| Для чего | Читать | Этап |
|---|---|---|
| AutoResearch и сравнение подходов | [AUTOML_RESEARCH_BRIEF](AUTOML_RESEARCH_BRIEF.md) → [RESEARCH_PROTOCOL](RESEARCH_PROTOCOL.md) | H01/H07/H09 |
| Qwen harness, роли, память и tools | [QWEN_HARNESS_DESIGN](QWEN_HARNESS_DESIGN.md) | H01.2/H06/H07 |
| Метрики, split, утечки и качество | [MATHEMATICS_AND_VALIDATION](MATHEMATICS_AND_VALIDATION.md) | H01.4/H03/H04/H09/H11 |
| Плоские модули, структуры, вход/выход | [BACKEND_CONTRACT](BACKEND_CONTRACT.md) | H02–H08 |
| Таймер, worker и отказы | [RUNTIME_AND_FAILURES](RUNTIME_AND_FAILURES.md) | H05–H07/H10 |
| WSL, отдельная ML-venv, пакеты и Docker | [LOCAL_ENVIRONMENT](LOCAL_ENVIRONMENT.md) | H02.1/H02.4/H10 |
| Что действительно доказано | [EVIDENCE_REGISTER](EVIDENCE_REGISTER.md) | При оценке статуса и после каждого блока |
| Первичные статьи и границы переноса | [RESEARCH_SOURCES](RESEARCH_SOURCES.md) | При обосновании дизайна |
| Нерешённые сведения организаторов | [ORGANIZER_QUESTIONS](ORGANIZER_QUESTIONS.md) | Перед API/образом/сабмитом |

Исходные task.md двух задач обязательны при работе с данными. SOURCE_MANIFEST и INDEX хранят версии/SHA. DOC_REVIEW_RECEIPT и квитанции H02.1/H02.2/H02.3 сохраняют историческую область. [Parser fixes](H023_REVIEW_FIXES.md), [локальный контейнер H02.4](H024_RECEIPT.md) и [библиотечные результаты H03](H03_RECEIPT.md) не заменяют чтение контракта и не закрывают будущие проверки полного агента.

## Новое обязательное правило упаковки

Переданный TXT платформы уточнил запуск: **`python3 solution.py task.md`**, cwd — каталог задачи, CSV — рядом.
ZIP не больше 100 МБ; используем консервативный предел **`100000000` байт**. Только корневые `.py` и неизменённый предоставленный `requirements.txt`, без папок.
P0 — `solution.py` + `aegml_*.py`; схемы реализованы внутри `aegml_schemas.py`, для будущих prompts предусмотрен `aegml_prompts.py`. Вложенный пакет, JSON/config/prompt assets и сторонние wheels не копируются платформой.
Зависимости устанавливает платформа из предоставленного списка. Runtime не вызывает pip; локальный subset не подменяет submission requirements. Исходные 37 pins сохраняются.
Рабочие подкаталоги во время исполнения разрешены: ограничение папок относится только к ZIP.
Boosters queue — не результат. Успешное завершение обозначается «Точность вычисления: …»; подробные логи доступны администраторам, а не обязательно пользователю.

## Текущая последовательность

H02.1 завершён: `/home/aegml/venvs/aegml-ml-py312`, Python 3.12.3, 13 direct pins / 45 distributions, 44 dependency wheels плюс bootstrap pip 25.2, 9 package smoke и pip check PASS.
Доказательства: [environment-lock.json](environment-lock.json), run `h02-20261020T160924Z` в `runs/h02/`. Старая stdlib-venv сохранена с 0 distributions. Это `PASS_H02_1_LOCAL_SUBSET_ONLY`, не полный образ или модель.
H02.3 реализовал контракт и однозначный resolver, проверку ID/порядка и встроенные схемы. Успешная подготовка создаёт два новых JSON в `.aegml_runs/<uuid>/`: `task_contract.json` и `row_alignment.json`. CLI возвращает exit 3 / implementation_incomplete с `contract_valid=true`; ML/API/tools/AutoResearch/submission ещё не подтверждены, нового CSV нет.
Сейчас заканчиваем разрешённый H03.1–H03.5: адресные исправления → свежие WSL integration/Docker harness → относящийся review и квитанции. Первый WSL library-chain и Docker harness уже прошли на предыдущем core, но их PASS не переносится на текущие fixes автоматически. Production CSV-loader требует BUILT TaskContract и связанный SplitPlan; low-level caller-asserted DataFrame API его не заменяет. Mapping fix writer прошёл локально; свежая общая перепроверка ещё впереди. CLI пока остаётся H02.3, exit3 / implementation_incomplete.

Следующий маршрут по отдельным командам: H04 baseline → H05 worker boundary и H06 Qwen protocol → H07 AutoResearch → перенос/сравнение/ZIP. H06.2 следует после offline mock/replay H06.1 и требует отдельной команды на live API; полный H07 зависит от H04/H05/H06. Все 74 основных и 17 пересекающихся HARN-T остаются предметом собственных проверок: компонентные PASS их целиком не закрывают.

H02.4 применил WSL 24 GiB / swap 4 GiB на E: при сохранённых 12 CPU и проверил локальный контейнер 20 GiB / quota 8 / no-swap / pids 256. Официальные 32 GB, полный образ и все 37 installed pins этим не воспроизведены. Predictive estimator, live API, полный срок и OS-worker boundary не проверены; generated code не запускать до H05.1.

API-запросов 0. Настройки сохранены локально, статус CONFIGURED_UNVERIFIED; **LIVE_API_ON_OWNER_COMMAND_ONLY**. Даже REST `/key/info` вне `/v1` ждёт будущей команды владельца. H06.2 проверит безопасное действие без generated ML-кода только после своих prerequisites.

## Как давать небольшое задание

> Заверши относящиеся исправления H03 по WORK_BLOCKS и главному ТЗ. Сначала прочитай состояние и H03_RECEIPT. Зафиксируй входной source SHA, проверь только изменённую область и необходимые регрессии, сохрани результаты и ограничения. H04 автоматически не начинай.

Различать: что написано, что запущено, что доказано и что осталось NOT_RUN/HOLD. Обзор, аналитическая формула, replay, live API, ML-fit и официальный score — разные результаты.

## Слова простым языком

| Термин | Значение |
|---|---|
| Harness | Управляющий слой вокруг Qwen: контракты, tools, память, исполнение и проверка |
| AutoResearch | Гипотеза → код → эксперимент → измерение → решение → следующая гипотеза |
| Переносимость | Один код понимает новые схемы/метрики и запускается в требуемой среде |
| T_fit / inner_score | Обучающие данные кандидата / контроль выбора внутри разработки |
| Outer | Контроль замороженного метода, не feedback исследования |
| Frozen refit | После freeze обучить рецепт на полном development без нового поиска |
| Worker / evaluator | Ограниченный исполнитель / независимый расчёт метрики |
| Incumbent / best-ready | Лучшая измеренная гипотеза / вариант с уже пригодным CSV |
| PASS / NOT_RUN / HOLD | Проверено в указанной области / не выполнялось / есть открытое условие |

Четыре участника делают независимые версии. Есть два пользовательских чата Vovan: первый — research, второй — teacher. Веб и оба saved packets возобновлены владельцем 21.10; [подтверждение отправки](WEB_DISPATCH_20261021.json). Прежний stop перед H03 — история, снятая отдельной прямой командой на весь H03. Во время активной работы root проверяет ответы последовательно, не чаще разрешённого интервала; при429 обращения прекращаются. Это не разрешение на конкурсный API.

Пакеты [1](../research_packets/CHAT1_FUTURE_RESEARCH.md)/[2](../research_packets/CHAT2_H02_REPAIR_REVIEW.md) сохраняют исторический unsent snapshot, а ответы и новые задания учитываются отдельно. [Очередь исследований](RESEARCH_BACKLOG.md) не меняет разрешённый scope. Исторические H02 исправления и metadata review — [H02_REVIEW_REPAIRS](H02_REVIEW_REPAIRS.md), [H02_REPAIR_FINAL_REVIEW](H02_REPAIR_FINAL_REVIEW.json); текущую H03 приёмку смотреть в [H03_RECEIPT](H03_RECEIPT.md). Читать также NEXT_SESSION; H04, live Qwen и следующие блоки автоматически не начинать.
