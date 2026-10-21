# Продолжение AegML: H04 принят в своей области, далее H05

Сначала прочитать последнюю команду владельца, [PROJECT_STATE](../PROJECT_STATE.md), [H04_RECEIPT](H04_RECEIPT.md), [READ_FIRST](READ_FIRST.md) и раздел 9 [ТЗ](TECHNICAL_SPEC.md).

**Текущий статус:** `PASS_H04_FIXED_BASELINE_ONLY`. После четырёх P0 исправлений прошли A 20/78, E 13/48, root 14/27, новые actual WSL и Docker на двух задачах. TD 17/31 относится к неизменённому компоненту; его работа в новом составе проверена сквозными V2. Полный [postfix-review2](H04_STATIC_REVIEW_RESULT.json) прочитан до END 21.10 в 11:23:42 UTC: четыре P0 CLOSED, remaining=0. Рецензент не повторял runtime-тесты; область — trusted H04.

- RMSE mean 58.4604 → CatBoost 47.3032; Macro F1 majority 0.0484115 → CatBoost 0.50464385. CSV 22449/41166 строк.
- Обучение только T_fit, оценка inner; WSL oracle sklearn прошёл. Docker с declared nested paths сохранил идентичные прогнозы. Это фиксированный baseline, не AutoResearch и не outer/frozen-refit оценка.
- Основные квитанции: [WSL V2](H04_WSL_PUBLIC_V2_RESULT.json), [Docker V2](H04_DOCKER_PUBLIC_V2_RESULT.json), [synthetic V2](H04_BASELINE_SYNTHETIC_V2_RESULT.json), [quality V2](H044_QUALITY_V2_RESULT.json).
- Старые 13 JSON и EXPORT_MANIFEST неизменны; 12 новых экспортов учитывает отдельный ignored EXPORT_V2_MANIFEST. История H02/H03 — в [H03_RECEIPT](H03_RECEIPT.md) и [H02_REVIEW_REPAIRS](H02_REVIEW_REPAIRS.md).

**Ближайший шаг:** H05.1 → последующие H05 → H06 с отдельными gates по уже полученной команде владельца. Полный список 50 подпунктов и зависимости остаются в [WORK_BLOCKS](WORK_BLOCKS.md); неподтверждённые full-agent тесты не закрывать соседним PASS.

**Подготовка будущего:** H05 observer в WSL/Docker увидел ABI 7 и безопасный seccomp-контроль, parent неизменён, cleanup подтверждён; Docker unshare возвращает EPERM с неизвестной причиной. H06 scratch16/70, HTTP0. Оба результата — только PREPARATION_ONLY, не production и не H05 admission. [Досье H05/H06](CHAT1_H05_H06_INTAKE.md) — обзор и проект приёмки.

**API=0, включая /key/info.** На H04 API запрещён. Условная команда владельца допускает первый короткий live H06.2 лишь после готовности исполнения H05 и offline/mock H06; эти предпосылки ещё не приняты. Ключ/fingerprint не читать для отчёта, не выводить и не включать в Git/ZIP. Моки и наличие ключа не live PASS. Generated code не исполнять до подтверждённой H05.1.

Среду не переустанавливать: AegML-Hackathon на E, Python 3.12.3, MLvenv /home/aegml/venvs/aegml-ml-py312. Локальный Docker 20 GiB/quota 8/no-swap не официальный image/full37; профиль в [container-profile](container-profile.json). Официальные 32 GB,10800 s, private/score, frozen refit, AutoResearch и полный worker boundary остаются непроверенными.

Веб: root — диспетчер research1/review2; общий интервал обращений≥60 сек, при 429 остановка; предупреждать перед отправкой и не перебивать активное задание. Фоновых автоматизаций и автоматического сабмита нет. Ручной ориентир 21.10 18:00 МСК не является гарантией срока/score.

AEGYX INDEX81: OWNER_PAUSE_BEFORE_SOURCE3. Default Ubuntu/AEGYX, его исходники/venv и global caps не менять без новой команды.
