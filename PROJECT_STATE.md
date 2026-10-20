# Состояние AegML — 20.10.2026

**Ожидание полных review чата2 — по последней команде владельца.** Docker final0e7bed48… получен: фактические локальные прогоны не опровергнуты, но CLI-OWN/ASSERT/RECEIPT/SOURCE остаются OPEN. OOM уже исправлен в411e628. У postfix-H023 нет полного ответа; отправлен запрос только на его завершение. До всех итогов код/проверщики не менять, тесты/ML/API/H03 не запускать. После полного ответа разрешено одним проверяемым этапом исправить подтверждённые замечания. Новых исправлений после411e628 не было.

**H02.4 завершён: PASS_H02_4_LOCAL_CONTAINER_ONLY.** Engine29.9.1/systemd/cgroupv2, digest-pinned Ubuntu24.04/Python3.12.3/dev13direct/45dist. [Квитанция](docs/H024_RECEIPT.md), [профиль](docs/container-profile.json). Ресурсы6/6, повторены после H024-OOM-ATTR-001 с oom/max/oom_kill; literal `python3 solution.py task.md` на двух actual public наборах в Docker PASS; imports13/45 PASS. Штатный агент ещё exit3/incomplete, contract_valid=true, API/tools/research/submission=false, experiments0; нового CSV нет.

**H02.3 после чата2:** три ROLE/DECL/ORDER исправлены и проверены38методов/93сценария/4CLI, bootstrap24/51/37. [Отчёт](docs/H023_REVIEW_FIXES.md). Старые34/76/4 и machineJSON сохранены с историческимSHA; текущий contracts SHA151d5283… . H03/ML/AutoResearch ещё не реализованы.

**Ресурсы:** WSLmemory24GiBconfigured, observed25202294784bytes (~23,47GiB), swap4GiBнаE, CPUs12сохранены. Docker20GiB/noSwap/quota8/PIDs256, nonroot1000/CAP0/NoNewPrivs/seccomp/networknone. CPU-visible12 не отменяет quota8. Малые OOM64/128MiB, max192MiBtouch; все20GiB не выделялись. Контролируемые canary не закрывают adversarial H05/kill-tree/10800s.

**Before/rollback:** оба distro Stopped, .wslconfig прежде отсутствовал; новый SHA826662a1… . Global shutdown не выполнялся, default Ubuntu и файлы AEGYX не запускались/не менялись. Общий memory envelope повлияет на будущие другие WSL. Rollback guards и пути в container-profile. Dockerrootfulunixonly, userнеdocker-group; storage/rootimage/cache внутри VHD наE. Official32GB/full37 image UNKNOWN.

**API:** private config вне Git, UID1000/0700/0600, реальных Qwen-запросов0. LIVE_API_ON_OWNER_COMMAND_ONLY: только после команды «протестить по API». Auth/tools ещё не проверены. Сеть использовалась для apt/image setup, не для конкурсного API или моделей.

**Веб-чаты:** новый reply2a0eca288… прочитан и исправлен. После уведомления сообщения в1 (H05 research) и2 (исправления+code+tests) успешно приняты. Целевая модель владельца GPT‑5.6Pro; UIselection независимо не подтверждён. Веб пользователя работает; IABошибки не считаются общей неисправностью сервиса/нашим дефектом. Повторные отправки разрешены. Новый ответ1 прочитан из attachment и принят в CHAT1_H024_H05_INTAKE; чат2 ещё работает по сообщению владельца, не опрашивать. Читать ответы по сигналу без polling; отдельный полный Docker packet также принят чатом2.

**Осталось:** H03.1 по отдельной команде → H03.2–H03.5 → H04; generated code только после H05.1, Qwen только по команде. Все74+17 основных сценариев NOT_RUN; OPEN BASE/ADAPT/DATA сохраняются. Inner/outer и frozen-refit контракты не реализованы; официальныйscore/B/privateкачество неизвестны. AEGYX остаётся на паузе INDEX81, не продолжать.

**Сдача:** ZIP≤100000000байт, только root.py+неизменённый provided37requirements. Dockerfile/devscripts/image/wheels/data/runs/key в ZIP не включать. Новых сабмитов/автоматизаций не было. Git private, бюджет600₽ не рассчитывать. [READ_FIRST](docs/READ_FIRST.md) → [WORK_BLOCKS](docs/WORK_BLOCKS.md).
