# Продолжение после H02.3

Прочитать последнюю команду владельца, [PROJECT_STATE](../PROJECT_STATE.md), [READ_FIRST](READ_FIRST.md), выбранный подпункт [WORK_BLOCKS](WORK_BLOCKS.md) и относящийся контракт. AEGYX на паузе, его не менять.

H02.3 завершён как **PASS_H02_3_CONTRACT_ONLY**: 34 метода / 76 сценариев / 4 CLI, [квитанция](H023_RECEIPT.md). Реализованы TaskContract, resolver/ID/порядок и встроенные схемы. Успешный CLI создаёт два свежих JSON в `.aegml_runs/<uuid>/` — `task_contract.json` и `row_alignment.json`, возвращает exit 3 / implementation_incomplete с `contract_valid=true`; новый CSV не создаётся. Экспериментов 0, API/tools/research/submission-флаги остаются false.

Следующий подпункт — **H02.4 по отдельной команде владельца**: Docker и фактический профиль; затем H03.1–H03.5 → H04. Для H02.4 читать LOCAL_ENVIRONMENT и RUNTIME_AND_FAILURES; сохранить before/rollback и учесть влияние глобальных WSL caps на AEGYX. Не повторять H02.3 без новой причины. Исторические H02.1 LOCAL_SUBSET и H02.2 BOOTSTRAP_ONLY сохраняются: H02.2 — 24 метода / 51 сценарий / 37 CLI в WSL Python 3.12.3, [квитанция](H022_RECEIPT.md); её SHA и прежние результаты не переписывать. Закрытие bootstrap-findings не закрывает OPEN полного агента.

Обучение, новый CSV полного агента, live API, tools, AutoResearch, Docker/caps, полный образ и OS-изоляция пока не проверены. H02.4 подготовить до H07; generated ML не запускать до подтверждённой H05.1. Текущий таймер кооперативный: startup до отметки NOT_MEASURED, зависший worker не прерывается. Все 74 основных и 17 пересекающихся будущих сценариев остаются NOT_RUN.

API настроен локально: [LOCAL_PROVIDER_RECEIPT](LOCAL_PROVIDER_RECEIPT.json), private JSON вне Git, UID1000/0700/0600. Реальных API-запросов 0. **LIVE_API_ON_OWNER_COMMAND_ONLY**: запросы только после отдельной команды «протестить по API». Проверка файла не равна auth/tools PASS. Endpoint/model есть в API_INSTRUCTIONS_INTAKE, capabilities UNKNOWN. Не читать почту и не создавать автоматизации.

Упаковка: root .py + исходный requirements с 37 pins, ZIP ≤100000000 байт, selective copy, `python3 solution.py task.md`. Собственные артефакты с нуля разрешены новым ответом организаторов; отдельные веса не копируются; поддерживаются root .py-компоненты. [P2-backlog](OPTIONAL_ARTIFACTS_RESEARCH.md) пока NOT_RUN. Веса, данные, секреты, venv, wheels и runs не добавлять в текущий Git/ZIP.

Чаты Vovan создал владелец: «1» — research, «2» — teacher. Новый ответ «1» прочитан по сигналу владельца: [CPU ML intake](CHAT1_CPU_ML_INTAKE.md). Чату «2» после уведомления отправлен actual H023 code/SHA/результат; нового ответа в доступной истории пока нет. Старый c62a… про H02.2 уже учтён. Дальше читать по сигналу владельца без polling, перед каждой отправкой сообщать.

WSL 24 GiB / Docker 20 GiB / 8 CPU — план. Default Ubuntu, общую .wslconfig и AEGYX не менять. Новые сабмиты и сообщения организаторам — только по команде. Бюджет 600 ₽ не рассчитывать; четыре независимые версии команды.
