# Продолжение после H02.2

Прочитать последнюю команду владельца, [PROJECT_STATE](../PROJECT_STATE.md), [READ_FIRST](READ_FIRST.md), выбранный подпункт [WORK_BLOCKS](WORK_BLOCKS.md) и относящийся контракт. AEGYX на паузе, его не менять.

H02.1 LOCAL_SUBSET и H02.2 BOOTSTRAP_ONLY завершены. H02.2: 24 метода, 51/51 сценарий, 37 CLI в WSL Python 3.12.3; [квитанция](H022_RECEIPT.md). Повторять проверки без новой причины не нужно. H02-BOOT-001 закрыт только для трёх bootstrap-ошибок; OPEN полного агента сохраняются.

Следующий подпункт — **H02.3 по новой команде владельца**: TaskContract и однозначный resolver. Читать BACKEND §3.1 (неоднозначности и test/sample ID), оба task.md, TECHNICAL_SPEC и WORK. Уникальные переставленные test/sample ID можно однозначно выровнять; готовый CSV обязан следовать контракту. Train/test ID не обязаны совпадать. Числовой target сам по себе не означает регрессию. Код H02.3 ещё не написан.

Далее отдельно H03 данные/метрики/CSV, H04 модели, H05 OS-worker/жёсткие лимиты, H06 tools, H07 AutoResearch. Generated ML не запускать до H05.1. Текущий таймер кооперативный: startup до отметки NOT_MEASURED, зависший worker не прерывается. Все 74 + 17 будущих сценариев остаются NOT_RUN.

API настроен локально: [LOCAL_PROVIDER_RECEIPT](LOCAL_PROVIDER_RECEIPT.json), private JSON вне Git, UID1000/0700/0600. **LIVE_API_ON_OWNER_COMMAND_ONLY**: запросы только после отдельной команды «протестить по API». Проверка файла не равна auth/tools PASS. Endpoint/model есть в API_INSTRUCTIONS_INTAKE, capabilities UNKNOWN. Не читать почту и не создавать автоматизации.

Упаковка: root .py + исходный requirements с 37 pins, ZIP ≤100000000 байт, selective copy, `python3 solution.py task.md`. Собственные артефакты с нуля разрешены новым ответом организаторов; отдельные веса не копируются; поддерживаются root .py-компоненты. [P2-backlog](OPTIONAL_ARTIFACTS_RESEARCH.md) пока NOT_RUN. Веса, данные, секреты, venv, wheels и runs не добавлять в текущий Git/ZIP.

Чаты Vovan создал владелец: «1» — источники, «2» — преподаватель. Читать по его сигналу, перед каждой отправкой сообщать в основном чате. В «1» ожидается сравнение ML-агентов; ответ «2» про timer/resolver учтён. Чаты не видят локальные файлы по имени; секрет им не передавать.

WSL 24 GiB / Docker 20 GiB / 8 CPU — план. Default Ubuntu, общую .wslconfig и AEGYX не менять. Новые сабмиты и сообщения организаторам — только по команде. Бюджет 600 ₽ не рассчитывать; четыре независимые версии команды.
