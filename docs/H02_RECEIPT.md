# H02.1 — локальная ML-среда

**Результат: PASS_H02_1_LOCAL_SUBSET_ONLY.** Подготовка пакетов завершена; H02.2 ещё NOT_RUN. Это не весь H02 и не проверка конкурсного агента.

Среда: WSL2 `AegML-Hackathon` на E:, Ubuntu 24.04.5, Python 3.12.3, отдельная `/home/aegml/venvs/aegml-ml-py312`. Старая `/home/aegml/venvs/aegml-py312` сохранена с 0 сторонних distributions. Общая .wslconfig, default Ubuntu и AEGYX не менялись.

Установлены 13 прямых закреплённых зависимостей и их транзитивные зависимости, всего 45 distributions. В числе 13 — setuptools как инструмент установки. Сохранены имена и SHA 44 dependency wheels и отдельного bootstrap pip 25.2. Пакеты скачивались по HTTPS с PyPI, затем устанавливались из локального кеша. `pip check` прошёл. Это не установка всего списка из 37 пакетов и не проверка официального образа.

Корневой [requirements.txt](../requirements.txt) побайтово равен исходному: SHA `9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6`. Он обязателен для будущей сдачи. [requirements-h02.txt](../requirements-h02.txt) — только локальное подмножество. [constraints-platform.txt](../constraints-platform.txt) сохраняет все 37 версий, удаляя лишь extras из имён для совместимости с pip constraints. Подмножество и constraints в конкурсный ZIP не входят.

Девять пакетных smoke-проверок прошли:

1. NumPy: матричное произведение.
2. SciPy: решение системы и sparse/ABI.
3. Pandas: UTF-8 CSV, пропуски и ID с ведущими нулями.
4. Sklearn: несколько ручных примеров метрик; будущие адаптеры H03 этим не приняты.
5. CatBoost: import, Pool и конструкторы без fit.
6. Pydantic/jsonschema: принятие корректной схемы и отклонение ошибочной.
7. OpenAI/httpx: создание и закрытие клиента с MockTransport, без HTTP-запроса.
8. Psutil: сведения о собственном процессе.
9. Отсутствие MCP в новой ML-среде.

Версии всех 13 прямых зависимостей проверены. Для setuptools проверены metadata/path, его import не заявляется. Измеренный RSS после импортов относится только к этому smoke-процессу; это не пик памяти обучения.

Машинная квитанция: [environment-lock.json](environment-lock.json). Исходные локальные доказательства: `runs/h02/h02-20261020T160924Z/`; они не публикуются в Git. Промежуточный installation.json содержит pending-import, а конечные smoke.json и environment-lock — завершённый результат. Проверка метаданных: [H02_REVIEW_RECEIPT.json](H02_REVIEW_RECEIPT.json).

Воспроизводимые средства разработки: [prepare_h02_environment.py](../scripts/prepare_h02_environment.py), [check_h02_environment.py](../scripts/check_h02_environment.py), [review_h02_receipt.py](../scripts/review_h02_receipt.py). Подготовку повторно без причины не запускать. Новая копия prepare-helper допускает отсутствие игнорируемой исходной папки, проверяя обязательный root requirements по зафиксированному SHA; эта правка проверена синтаксически и чтением, повторная установка не выполнялась. Фактическая установка выполнена ранее внешним helper с теми же версиями и сохранёнными raw-квитанциями.

Не выполнялись: model fit, реальные запросы к Qwen, generated execution, AutoResearch, Docker, изменение caps и новые сабмиты. Полный образ платформы и OS-граница UNKNOWN. Все 74 основных будущих сценария и 17 пересекающихся HARN-T остаются NOT_RUN. Следующий подпункт по команде владельца — H02.2: entrypoint и общий timer.
