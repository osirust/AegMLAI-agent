# Локальная среда и развёртывание на платформе

Редакция 21.10.2026. Среда H02.4 сохранена как **PASS_H02_4_LOCAL_CONTAINER_ONLY**: Engine/локальный образ, 6/6 ресурсных canary, пакетная проверка 13 прямых pins / 45 distributions / Python 3.12.3 и literal Docker CLI двух actual public-задач. [Квитанция H02.4](H024_RECEIPT.md), [профиль](container-profile.json). Владелец разрешил весь H03.1–H03.5; библиотечные компоненты реализованы, текущие review fixes и свежая общая перепроверка ещё выполняются. [Сводка H03](H03_RECEIPT.md) обновляется отдельно и пока не объявляет окончательную готовность агента.

H02.3 после полного review прошёл43метода/108сценариев/6CLI, bootstrap24/51/37; CLI-checker11/17mock и2actualDocker: [H02_REVIEW_REPAIRS](H02_REVIEW_REPAIRS.md). Старые38/93/4 сохранены историческими. Прежние H023 34/76/4 и H022-квитанции сохранены историческими. В H03 реально обучались состояния предобработки и TF‑IDF; predictive estimator, реальные LLM-запросы и официальный submission не выполнялись. Writer проверен на форматных константах в рабочих копиях.

## 1. Что действительно существует

| Объект | Факт и доказательство | Граница результата |
| --- | --- | --- |
| Windows-ПК | Ryzen 5 9600X, 12 логических CPU, заявленные 32 GiB DDR5 и RTX 5070 Ti 16 GB; в inventory 33 410 088 960 байт физической памяти; Windows 11 Pro | Это не объём свободной RAM процесса и не измерение скорости модели |
| WSL2 | AegML-Hackathon, Ubuntu 24.04.5, пользователь aegml; VHD на E:/WSL/AegML-Hackathon | Отдельная WSL сама по себе не подтверждает H05 worker boundary |
| Старая stdlib-venv | Python 3.12.3, /home/aegml/venvs/aegml-py312; 0 сторонних distributions, сохранена | Историческая минимальная среда, не полный requirements |
| ML-venv H02.1 | /home/aegml/venvs/aegml-ml-py312; 13 direct pins / 45 distributions, 9 smoke и pip check PASS | H03 fit предобработки выполнен; predictive estimator и полный официальный образ не проверены |
| Установочные артефакты | 44 dependency wheels и bootstrap pip; исходные версии/пути/SHA в [environment-lock.json](environment-lock.json) | Wheels/pip нельзя включать в submission ZIP |
| TaskContract H02.3 | Resolver, target/type/metric/ID, finite schemas и направленные карты; историческая приёмка — [H02_REVIEW_REPAIRS](H02_REVIEW_REPAIRS.md) | H03 добавил профиль, numerical metrics/splits, preprocessing и writer; текущие fixes — [H03_RECEIPT](H03_RECEIPT.md) |
| Текущий CLI | Два свежих JSON task_contract/row_alignment, exit 3 / implementation_incomplete, contract_valid=true | API/tools/research/submission false, experiments 0; нового CSV нет |
| H03 library foundation | Профиль, train-only preprocessing, metrics/splits и trusted writer; отдельные локальные квитанции в [H03_RECEIPT](H03_RECEIPT.md) | Компоненты и свежая trusted-цепочка WSL/Docker прошли; относящиеся post-fix review завершены. CLI ещё не подключён как полный агент |
| WSL ресурсы H02.4 | Configured memory 24 GiB; замер 25 202 294 784 байт RAM ≈ 23,47 GiB; swap 4 GiB на E:, CPU 12 | Память гостя после накладных расходов и общий cap не равны свободной памяти модели |
| Docker Engine | 29.9.1, rootful, Unix socket, cgroup v2/systemd; daemon запускается systemd | Пользователь aegml не добавлен в docker group; вложенный Docker платформы не предполагается |
| Docker storage | /var/lib/docker внутри Linux VHD AegML-Hackathon на E: | Docker Desktop и второй backend не готовились |
| Локальный контейнер | Memory 20 GiB / no-swap / CPU quota 8 / pids 256; UID/GID 1000:1000 | Это не официальный образ и не платформенные 32 GB |
| Mini | Исторические 6 файловых и 17 API-stub сценариев; [квитанция](TESTMINI_STRICT_RESULT.json) | Не настоящий Qwen, ML по признакам или полный агент |

Python 3.12.3 — patch-релиз ветки 3.12; замена на 3.12.0 не требуется. Параметры официального образа по-прежнему UNKNOWN. Упоминание i5 в старом prompt Vovan не является характеристикой этого ПК.

## 2. Где редактируем и где исполняем

| Слой | Работа | Путь / состояние |
| --- | --- | --- |
| Windows/Codex | Основной Git, редактор, документация | E:/work/AegMLAI-agent |
| Исходные материалы | Неизменяемые файлы кейса | drive-download-20261019T181414Z-1-001 внутри проекта |
| WSL/Python | Две сохранённые venv; H03 проверки с fit предобработки, без predictive estimator/Qwen | AegML-Hackathon, Linux VHD на E: |
| Docker | Один локальный Engine, образ и временные canary-контейнеры | /var/lib/docker; факты в [H024_RECEIPT](H024_RECEIPT.md) |
| Будущий ML staging | Экспорт конкретного commit, а не отдельный расходящийся master | `/home/aegml/aegml_workspace/<commit>/` — PLANNED |
| Будущие input snapshots/cache | Копии с source SHA и временные ML-артефакты | /home/aegml/aegml_data/, /home/aegml/cache/ — PLANNED |
| Исторические mini runs | Уже выполненные рабочие копии | /mnt/e/work/AegMLAI-agent/runs/testmini/ |

Mini и H02.3 действительно запускались в Linux. В H02.4 точный CLI выполнен в контейнере на рабочих копиях двух задач; не монтировались весь репозиторий, Windows home, private config или Docker socket. Будущие тяжёлые ML-runs желательно хранить в Linux filesystem с source/data SHA; их скорость ещё не измерена.

## 3. Применённые ресурсы и откат

WSL настроена на **24 GiB memory и 4 GiB swap на E:**. Зафиксированный guest memory — 25 202 294 784 байт (около 23,47 GiB). Глобальный processors=8 не задавался: остаются 12 логических CPU хоста. Контейнерный лимит 20 GiB входит в память WSL; он не добавляет ещё 20 GiB.

До H02.4 .wslconfig отсутствовал. На момент изменения оба дистрибутива были Stopped; wsl --shutdown не выполнялся. Default Ubuntu-24.04 не запускали, её файлы, исходники и venv AEGYX не меняли. Однако .wslconfig общий для WSL2, поэтому memory/swap envelope будущего запуска default Ubuntu тоже изменился. Это явно разрешённое общее изменение, а не обещание отсутствия любого влияния на AEGYX. [Документация Microsoft](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)

Before/after, SHA созданной конфигурации и rollback относятся к [квитанции H02.4](H024_RECEIPT.md) / [container-profile](container-profile.json). Исходное состояние — отсутствие файла, поэтому восстановление нельзя подменять произвольным числовым cap. Перед откатом нужно сверить текущий SHA с внесённой версией и сохранить возможные последующие изменения владельца; автоматический откат здесь не выполнялся.

В baseline-контейнере зафиксированы memory.max=21474836480, memory.swap.max=0, cpu.max="800000 100000", pids.max=256. Видимые cpu_count/affinity=12 не являются ошибкой: quota ограничивает CPU-время, а не обязана менять число видимых логических CPU. Локальные 20 GiB теснее заявленных платформой 32 GB и не подтверждают пригодность любого будущего fit. [Docker resources](https://docs.docker.com/engine/containers/resource_constraints/)

Один кандидат обучается одновременно. Будущие AutoML/CV/BLAS не получают по восемь потоков на каждый процесс. ML-потребление RAM, время и достаточность общего резерва ещё предстоит измерить. Локальная видеокарта не заменяет обязательную CPU-приёмку.

## 4. Образ и компонентная приёмка H02.4

Engine **29.9.1** установлен внутри AegML-Hackathon; daemon rootful и запускается systemd. Управление идёт через Unix socket. Пользователь aegml не добавлен в docker group; контейнер не получает socket, privileged или host namespaces. Источник установки — [Docker Ubuntu](https://docs.docker.com/engine/install/ubuntu/); rootful и non-root runtime процесса — разные уровни прав.

Локальный image ID: `sha256:95e451e558d36beade7ffb1c64045a34cf152f9daac57336166e023c745cef0b`.
База — Ubuntu 24.04, digest `sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac`. Внутри Python 3.12.3 и glibc 2.39. Это наш dev-образ, а не образ организаторов. Версии OS-пакетов зафиксированы: apt-install не имеет отдельных version pins, поэтому одна только ссылка на base digest не обещает побайтно одинаковый будущий rebuild.

| Квитанция | Что действительно проверено | Чего она не закрывает |
| --- | --- | --- |
| [H024_CONTAINER_RESULT](H024_CONTAINER_RESULT.json) | 6/6: baseline-профиль, малый CPU throttle, OOM при 64 и 128 MiB, pids 16 и tmpfs 4 MiB | Полную adversarial H05, ML peak RAM и три часа |
| [H024_IMPORT_RESULT](H024_IMPORT_RESULT.json) | Python 3.12.3, 13 direct pins / 45 distributions, provided requirements SHA, OS package manifest | Все 37 direct pins и официальный platform image |
| [H024_DOCKER_CLI_RESULT](H024_DOCKER_CLI_RESULT.json) | Два actual public-набора через literal python3 solution.py task.md; SHA исходников/входов и старый CSV сохранены | Новое предсказание CSV, вычисленные RMSE/F1, fit или API |

В baseline-профиле корневая FS read-only, writable /work — ограниченный tmpfs 512 MiB, UID/GID 1000:1000, CapEff=0, NoNewPrivs=1, Seccomp=2, network=none и только loopback. Это фактические параметры локального canary, а не общий сертификат безопасности. OOM выполнялся только в малых контейнерах 64/128 MiB: выделение всех 20 GiB не проводилось. Real API и generated code не запускались. Наблюдения и inspect сохранены в JSON; флаг без наблюдаемого результата не считается приёмкой.

H05.1 отдельно проверит полный worker boundary до недоверенного generated code. H10.2 отдельно требует точный официальный образ; при его отсутствии остаётся локальное приближение. H10.3 — самостоятельный длительный wall-clock прогон. VirtualBox, Docker-in-Docker и скрытое расширение прав не вводились. Временные canary не превращают rootful host daemon в непривилегированный сервис.

## 5. Пакеты: последовательность, а не установка всего сразу

Полученный `requirements.txt` содержит 37 pins и не перезаписывается. В H02.1 установлены 13 direct pins: numpy 1.26.4, scipy 1.12.0, pandas 2.2.3, scikit-learn 1.5.2, CatBoost 1.2.8, joblib 1.4.2, threadpoolctl 3.6.0, psutil 6.1.1, openai 1.68.2, httpx 0.28.1, pydantic 2.10.6, jsonschema 4.23.0, setuptools 80.9.0. Это локальное подмножество, **не замена submission requirements**.

Фактический порядок H02.1: новая ML-venv → bootstrap pip 25.2 → 44 dependency wheels → локальная установка → pip check PASS → версии/импорты и 9 smoke. Всего 45 distributions, включая pip. Pip — development installer, не новая submission-зависимость. Версии, import paths и SHA колёс сохранены в lock; run ID — `h02-20261020T160924Z`, локальные артефакты — `runs/h02/h02-20261020T160924Z/`.

`installation.json` фиксирует промежуточное состояние до smoke; конечный статус берётся из `smoke.json` и environment-lock. Девять проверок охватывают NumPy, SciPy ABI/sparse, pandas CSV, пакетные sklearn-метрики, CatBoost import/Pool без fit, pydantic/jsonschema, конструкцию/закрытие OpenAI/httpx без запроса, psutil и отсутствие MCP. Это не H03-адаптер и не обучение модели.
После H02.1 были зафиксированы model_fit_calls=0 и real_api_requests=0; старая stdlib-venv сохранила 0 distributions. Теперь H02.3 отдельно подтвердил resolver, а H02.4 — локальный образ с 13 прямыми pins / 45 distributions, Python 3.12.3 и glibc 2.39: [H024_IMPORT_RESULT](H024_IMPORT_RESULT.json). Для build повторно проверены SHA 45 cached wheels, включая bootstrap pip; установка выполнялась при сборке, не из solution.py. Полные 37 pins, AutoGluon/LightAutoML и официальный образ этим не проверены. Малый fit/predict относится к будущему H04.

После рабочего baseline добавляются LightGBM4.6.0/XGBoost2.1.4 и предварительно FLAML2.3.6 для сравнения. AutoGluon1.3.1 и LightAutoML0.4.2 — альтернативы из исследования; все три движка сразу не обязательны. auto-sklearn и Qwen-Agent не входят в выданный список. Torch/CUDA не нужен P0; собственные скачиваемые embeddings и pretrained tabular-модели не используются.

Если пакет/версия не работают на платформе, это разрыв совместимости, а не повод вызывать pip из `solution.py`. По новому TXT зависимости устанавливает платформа из неизменённого предоставленного root `requirements.txt`; собственный runtime pip недоступен. Пакетная/registry-сеть использовалась для подготовки локальных H02.1/H02.4, а не для runtime solution.py. Локальный subset/его манифест не подменяют полный предоставленный submission-файл; сторонние библиотеки, venv и wheels в ZIP запрещены.

## 6. Qwen и текущая локальная конфигурация

Ключ получен от владельца. Private config вне Git, UID1000/0700/0600: [LOCAL_PROVIDER_RECEIPT](LOCAL_PROVIDER_RECEIPT.json). Статус CONFIGURED_UNVERIFIED_NO_LIVE_REQUESTS, реальных API-запросов 0. **LIVE_API_ON_OWNER_COMMAND_ONLY**: только после отдельной команды «протестить по API». Импорт SDK или проверка локального файла не равны проверке аутентификации.

H02.1–H02.4 выполнены без реального LLM API и без обучения; H03 обучает только состояния предобработки. H06.1 offline mock/replay остаётся отдельным подпунктом; H06.2 следует после него и только после отдельной команды проверит безопасную цепочку action → result → продолжение без generated ML. Любой REST `/key/info` вне `/v1` тоже ждёт будущего разрешения владельца. Используется выданный API; другие модели через собственные ключи запрещены. Допустимость локальной той же Qwen UNKNOWN, веса сейчас не скачиваются. Полный AutoResearch H07 идёт после H04/H05/H06 и их приёмок.

## 7. Что осталось непроверенным

Текущая разрешённая работа — **весь H03.1–H03.5**. Профиль, preprocessing, numerical metrics/splits и CSV writer существуют; H03.1 external static postfix review закрыт. Сейчас усиливаются BUILT-binding production loader и metrics/validation; mapping fix writer локально прошёл. Production loader требует BUILT TaskContract и связанный SplitPlan, а low-level caller-asserted DataFrame API остаётся отдельным режимом. Первый WSL library-chain и Docker harness прошли на предыдущем core; после исправлений нужны свежие квитанции. Подробности — в обновляемой [сводке H03](H03_RECEIPT.md), без раннего итогового PASS.

Predictive fit, live API/tools, AutoResearch, полный process-tree/hard-timeout boundary, официальный образ и все 37 installed pins не проверены. Component PASS не закрывает целиком 74 основных и 17 пересекающихся HARN-T сценариев. Ресурсные настройки H02.4 этой работой не менялись.

У организаторов остаются image/Dockerfile, actual env/версии, доступные OS-примитивы, трактовка exitcode и last/best selection. Подробные логи могут быть только у администраторов; не предполагать их наличие в пользовательском UI. [ORGANIZER_QUESTIONS](ORGANIZER_QUESTIONS.md) — неотправленный черновик.

Исторические ответы H02.4 получены и учтены в H02_REVIEW_REPAIRS. Веб возобновлён владельцем 21.10; текущий H03-review ведёт root. Это не разрешение на live API и не изменение локальных caps.

## 8. Точный submission-контракт из платформенного TXT

ZIP до 100 МБ; консервативный предел — **`100000000` байт**. В корне без папок только `solution.py`, собственные `.py` и неизменённый предоставленный `requirements.txt`.
P0 использует плоские `aegml_*.py`: схемы уже встроены в `aegml_schemas.py`, для будущих prompts предусмотрен `aegml_prompts.py`. Package directories, JSON/config/prompt assets, данные и wheels в архив не входят: платформа копирует только root `.py` и requirements.
Во время выполнения можно создавать cwd/подкаталоги/`/tmp`; запрет папок касается ZIP, а не временного workspace. `submission.csv` сохраняется рядом с task.
Boosters queue («Решение находится на проверке») — ещё не результат. Сообщение «Точность вычисления: …» обозначает успешную оценку; сама загрузка, Best-метка или score 0 не доказывают API/tools.
