# Локальная среда и развёртывание на платформе

Редакция 20.10.2026. **Текущий результат — PASS_H02_3_CONTRACT_ONLY**: TaskContract, resolver и встроенные схемы, 34 метода / 76 сценариев / 4 CLI; [квитанция H02.3](H023_RECEIPT.md). H02.1 остаётся PASS_H02_1_LOCAL_SUBSET_ONLY, [environment-lock.json](environment-lock.json); исторический H02.2 — bootstrap only, 24 метода / 51 сценарий / 37 CLI, [квитанция](H022_RECEIPT.md). Это не весь H02: Docker/profile, обучение, live API, изменение caps и сабмиты не выполнялись. Следующий H03.1 — только по отдельной команде.

## 1. Что действительно существует

| Объект | Факт и доказательство | Что это не подтверждает |
| --- | --- | --- |
| Windows-ПК | Ryzen 5 9600X, 6 ядер / 12 потоков; 32 GiB DDR5 (2 × 16); RTX 5070 Ti 16 GB; Windows 11 Pro; SOURCE_MANIFEST | Скорость будущей модели и 32 GB свободной памяти процесса |
| Новая WSL2 | AegML-Hackathon, Ubuntu 24.04.5, пользователь aegml, VHD `E:/WSL/AegML-Hackathon/ext4.vhdx` | OS-sandbox для произвольного Python |
| Старая stdlib-venv | Python 3.12.3, `/home/aegml/venvs/aegml-py312`; после H02.1 по-прежнему 0 установленных distributions, среда не менялась | Импорты полного официального requirements |
| Новая ML-venv H02.1 | `/home/aegml/venvs/aegml-ml-py312`, Python 3.12.3; 13 direct pins, всего 45 distributions, 9 package smoke и pip check PASS | Fit, H03 metric adapter, полный platform requirements или образ |
| Установочные артефакты | 44 dependency wheels и отдельный bootstrap pip 25.2; версии/пути/SHA в [environment-lock.json](environment-lock.json) | Разрешение включать wheels/pip в submission ZIP или устанавливать пакеты runtime |
| TaskContract H02.3 | Реализованы `aegml_input.py`, resolver/контракт в `aegml_contracts.py`, embedded schemas в `aegml_schemas.py`; [квитанция](H023_RECEIPT.md) | Профиль H03, модель, метрики, настоящий CSV, API/tools/AutoResearch или OS-изоляция |
| Артефакты успешного H02.3 CLI | Два свежих JSON в `.aegml_runs/<uuid>/`: `task_contract.json`, `row_alignment.json`; exit 3 / implementation_incomplete, `contract_valid=true`, остальные full-agent флаги false | Готовый агент или результат обучения; новый CSV не создаётся |
| Минимальная квитанция | [ENVIRONMENT_RECEIPT.json](ENVIRONMENT_RECEIPT.json): версия/prefix/CSV/JSON | Это историческая квитанция первоначальной настройки, не текущий полный runtime |
| Mini | 6 файловых и 17 API-stub сценариев в новой WSL; [TESTMINI_STRICT_RESULT.json](TESTMINI_STRICT_RESULT.json) | Настоящее ML, native tools, AutoResearch и полный образ |
| Сеть | Loopback HTTP в новой WSL проверен заглушкой; выданный внешний endpoint локально не проверен | Отсутствие сети вообще или успешный внешний запрос |
| Platform mini | Владелец показал strict ZIP, score 0 и «Лучшее решение»; условие кода — API/CSV при штатном exit 0 в required | Сам UI не доказывает завершение Boosters; 3,2 с — загрузка, actual exit/env неизвестны |
| Текущие ресурсы | Видны 12 CPU и 16 301 989 888 байт RAM ≈ 15,18 GiB; `.wslconfig` не меняли | Применённые WSL 24 / Docker 20 или точные 8 CPU / 32 GB платформы |
| Docker | Готового проектного Docker-образа и проверки Engine нет; установка не выполнена | Наличие вложенного Docker на платформе |

Python 3.12 — ветка, 3.12.3 — её patch-релиз. Устанавливать 3.12.0 ради записи «3.12» не требуется. Точный Python patch и нативные версии платформы фиксируются по образу, когда его дадут; web-документация не меняет нашу установленную версию.

Прежняя Ubuntu-24.04 остаётся default и относится к AEGYX. Её source, env, процессы и настройки не меняем. `wsl --shutdown` завершает все WSL; H02.1 не менял общий config/caps. Упоминание i5 в prompt Vovan — чужое/устаревшее сведение, не характеристика этого Ryzen 5 9600X. Пользовательские чаты Vovan разделены: первый — research, второй — teacher; read/send разрешены по назначению, читать по сигналу владельца без polling.

## 2. Где редактируем и где исполняем

| Слой | Работа | Путь/профиль |
| --- | --- | --- |
| Windows/Codex | Основной Git, редактор, документация и сборка | `E:/work/AegMLAI-agent` |
| Исходные материалы | Неизменяемая копия кейса | `E:/work/AegMLAI-agent/drive-download-20261019T181414Z-1-001` |
| WSL/Python | H02.1 LOCAL_SUBSET проверен; CPU-эксперименты только позже по H04 | AegML-Hackathon; ML `/home/aegml/venvs/aegml-ml-py312`, stdlib-venv отдельно |
| Будущий Linux staging | Экспорт конкретного commit для запусков, а не второй расходящийся master | `/home/aegml/aegml_workspace/<commit>/` — PLANNED |
| Будущие input snapshots | Копии данных с манифестом source SHA | `/home/aegml/aegml_data/<data_sha>/` — PLANNED |
| Будущий cache/runs | Пакеты/временные ML-файлы внутри VHD на E: | `/home/aegml/cache/`, `/home/aegml/runs/` — PLANNED |
| Текущие mini runs | Уже выполненные рабочие копии | `/mnt/e/work/AegMLAI-agent/runs/testmini/` |

Mini действительно запускалась из `/mnt/e`, поэтому нельзя писать «проект в Linux ещё не запускался». Будущие тяжёлые ML-runs желательно вынести в Linux filesystem, сохраняя Git/source/data SHA и экспортируя отчёты в основной проект. Их скорость ещё не измерена. Копия commit не редактируется как независимая версия без явного согласования.

## 3. Память и CPU: план и факт отдельно

Проектный ориентир — **WSL 24 GiB**, контейнер в ней **20 GiB / 8 CPU**, остальное остаётся Windows и процессам хоста. Память контейнера входит в память WSL, а не добавляется. Настройки сейчас не применяются; это не точная копия платформенных 32 GB. Свободную RAM, swap, объём E: и peak RSS измеряем перед будущим пилотом.

В [документации Microsoft](https://learn.microsoft.com/en-us/windows/wsl/wsl-config) `.wslconfig` описан как общий для WSL2; стандартная память —50% хоста. Нужное изменение оформляется отдельным H02.4 с сохранением before/after и учётом AEGYX. Текущее отсутствие файла не требует создать его сейчас.

Один кандидат обучается одновременно. Внутри AutoML/CV/BLAS не допускается умножение 8 потоков на каждый процесс. Лимит задаётся для дерева процессов и проверяется измерением. Локальная карта GPU не требуется для сдаваемого кода; ускоренный отдельный эксперимент P1 не заменяет CPU-приёмку.

## 4. Когда нужен Docker

1. **H02.1 завершён:** отдельная ML-venv, пакетные smoke/версии и pip check; существующая WSL и stdlib-venv сохранены. Это не установка Docker.
2. **H02.2 bootstrap и H02.3 контракт завершены в своих областях:** [историческая bootstrap-квитанция](H022_RECEIPT.md), [текущая H02.3](H023_RECEIPT.md). Следующий H03.1, далее до H03.5 → H04 — только по отдельным командам.
3. **H02.4 до H07:** подготовить один вариант Docker. Предпочтение проекта — Engine внутри AegML-Hackathon, чтобы данные Engine находились в VHD на E:. Docker Desktop с WSL2 — альтернатива, не второй одновременный backend. Его перенос хранилища требует отдельной проверки.
4. **H05.1:** проверить реальную worker boundary до любого недоверенного generated code. Локальный Engine можно использовать для disposable-job; не монтировать Windows home, Docker socket или секреты в worker.
5. **H10.2:** проверка полного ZIP в точном официальном образе. Если образ недоступен — записать digest локального приближения и незакрытое отличие; mini не заменяет эту приёмку.
6. **H10.3:** отдельный длительный прогон по полному wall-clock и ресурсам.

Engine устанавливается по [официальной инструкции Ubuntu](https://docs.docker.com/engine/install/ubuntu/); конкретная версия и digest фиксируются при выполнении, не подставляются как «latest». [Rootless](https://docs.docker.com/engine/security/rootless/) имеет свои условия; ограничения ресурсов нельзя объявить действующими лишь по выбранному флагу. Точная конфигурация проверяется capability report.

VirtualBox для этой схемы не требуется. Ранее найденная выключенная VM с малым выделением RAM не является нашей подготовленной средой и не должна автоматически перенастраиваться. Docker-в-Docker, privileged и доступ к host daemon на платформе не предполагаем; отсутствие этих возможностей влияет на выбор H05, а не решается скрытым запуском с большими правами.

## 5. Пакеты: последовательность, а не установка всего сразу

Полученный `requirements.txt` содержит 37 pins и не перезаписывается. В H02.1 установлены 13 direct pins: numpy 1.26.4, scipy 1.12.0, pandas 2.2.3, scikit-learn 1.5.2, CatBoost 1.2.8, joblib 1.4.2, threadpoolctl 3.6.0, psutil 6.1.1, openai 1.68.2, httpx 0.28.1, pydantic 2.10.6, jsonschema 4.23.0, setuptools 80.9.0. Это локальное подмножество, **не замена submission requirements**.

Фактический порядок H02.1: новая ML-venv → bootstrap pip 25.2 → 44 dependency wheels → локальная установка → pip check PASS → версии/импорты и 9 smoke. Всего 45 distributions, включая pip. Pip — development installer, не новая submission-зависимость. Версии, import paths и SHA колёс сохранены в lock; run ID — `h02-20261020T160924Z`, локальные артефакты — `runs/h02/h02-20261020T160924Z/`.

`installation.json` фиксирует промежуточное состояние до smoke; конечный статус берётся из `smoke.json` и environment-lock. Девять проверок охватывают NumPy, SciPy ABI/sparse, pandas CSV, пакетные sklearn-метрики, CatBoost import/Pool без fit, pydantic/jsonschema, конструкцию/закрытие OpenAI/httpx без запроса, psutil и отсутствие MCP. Это не H03-адаптер и не обучение модели.
После H02.1 выполнена остановка: `model_fit_calls=0`, `real_api_requests=0`, старый stdlib остаётся 0 distributions. Полный resolver/импорты всех 37 pins и официальный образ не проверены. Малый fit/predict относится к последующему H04.

После рабочего baseline добавляются LightGBM4.6.0/XGBoost2.1.4 и предварительно FLAML2.3.6 для сравнения. AutoGluon1.3.1 и LightAutoML0.4.2 — альтернативы из исследования; все три движка сразу не обязательны. auto-sklearn и Qwen-Agent не входят в выданный список. Torch/CUDA не нужен P0; собственные скачиваемые embeddings и pretrained tabular-модели не используются.

Если пакет/версия не работают на платформе, это разрыв совместимости, а не повод вызывать pip из `solution.py`. По новому TXT зависимости устанавливает платформа из неизменённого предоставленного root `requirements.txt`; собственный runtime pip недоступен. Наши установки и пакетная сеть относятся к локальному H02.1. Локальный subset/его манифест не подменяют полный предоставленный submission-файл; сторонние библиотеки, venv и wheels в ZIP запрещены.

## 6. Qwen и текущая локальная конфигурация

Ключ получен от владельца. Настройки взяты из официальной инструкции, private config записан вне Git с UID1000/0700/0600: [LOCAL_PROVIDER_RECEIPT](LOCAL_PROVIDER_RECEIPT.json). Статус CONFIGURED_UNVERIFIED_NO_LIVE_REQUESTS, реальных API-запросов 0. **LIVE_API_ON_OWNER_COMMAND_ONLY**: настоящие запросы только по отдельной команде владельца. Mini не заменяет проверку сервиса.

H02.1, bootstrap H02.2 и контракт H02.3 завершены без LLM API; наличие ключа и локального файла не является API_PASS. H06.1 offline-протокол — отдельный подпункт. H06.2 только после команды владельца проверит аутентификацию и действие → результат → продолжение на безопасном инструменте, без generated ML-кода; локальные пакеты не заменяют выданный runtime.

Chosen policy: использовать provided API. Материал прямо запрещает другие модели через собственные API-ключи. Допустимость локальной **той же** Qwen для dev не установлена; это UNKNOWN, а не полученное разрешение или прямой отдельный запрет. Поэтому веса сейчас не скачиваются. Документация Qwen-Agent может быть источником идей, не обязательной зависимостью приложения.

## 7. Приёмка среды и ещё открытые вопросы

Нужно сохранить OS/Python/package versions, commit/source/data SHA, пути обеих venv/cache/workspace, digest образа, effective CPU/RAM/swap/disk и capabilities worker. Команда уже известна из TXT: `python3 solution.py task.md`; её фактическое воспроизведение в точном образе — отдельная приёмка. Остальные неподтверждённые поля остаются UNKNOWN.

У организаторов при доступности нужны image/Dockerfile, actual env/версии, сеть, OS-isolation, трактовка exitcode и selection last/best. Подробные логи по TXT доступны только администраторам; можно просить обезличенный per-task итог, не предполагать его наличие в пользовательском UI. [ORGANIZER_QUESTIONS.md](ORGANIZER_QUESTIONS.md) содержит неотправленный черновик.

Весь H02 не закрывается созданной venv или историческими mini PASS. Новое изменение окружения выполняется в своём подпункте с доказательствами и rollback-планом; рабочие оригиналы и AEGYX сохраняются.

H02.3 проверяет только слой контракта. Все74основных и17HARN-T остаются NOT_RUN; CSV полного агента, fit/API/tools/AutoResearch, Docker/caps, OS-граница и точный образ ещё впереди. Новый CPU ML ответ чата «1» прочитан по сигналу владельца: [intake](CHAT1_CPU_ML_INTAKE.md). Чату «2» после уведомления передан actual H023 snapshot; новый ответ в доступной истории пока отсутствует. Предыдущие ответы относятся к H02.2, не к текущей реализации.

## 8. Точный submission-контракт из платформенного TXT

ZIP до 100 МБ; консервативный предел — **`100000000` байт**. В корне без папок только `solution.py`, собственные `.py` и неизменённый предоставленный `requirements.txt`.
P0 использует плоские `aegml_*.py`: схемы уже встроены в `aegml_schemas.py`, для будущих prompts предусмотрен `aegml_prompts.py`. Package directories, JSON/config/prompt assets, данные и wheels в архив не входят: платформа копирует только root `.py` и requirements.
Во время выполнения можно создавать cwd/подкаталоги/`/tmp`; запрет папок касается ZIP, а не временного workspace. `submission.csv` сохраняется рядом с task.
Boosters queue («Решение находится на проверке») — ещё не результат. Сообщение «Точность вычисления: …» обозначает успешную оценку; сама загрузка, Best-метка или score 0 не доказывают API/tools.
