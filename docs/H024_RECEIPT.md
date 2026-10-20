# H02.4 — локальная среда Docker и компонентная приёмка

Дата: 20.10.2026. Итог: **PASS_H02_4_LOCAL_CONTAINER_ONLY**. Подготовлены локальный Engine, один dev-образ и измеряемый ресурсный профиль. Выполнены шесть коротких handwritten resource canaries, два запуска реального TaskContract CLI в контейнере и проверка dev-зависимостей. Это локальное приближение; официальный образ и полный агент не проверены.

Машиночитаемый профиль — [container-profile.json](container-profile.json). Raw-артефакты сохранены в `runs/h02/h024-20261020T184606Z/`; отдельные Linux-квитанции находятся в `/home/aegml/checks/h024-20261020T184606Z/`. При оформлении этого документа тесты не запускались повторно.

## Фактические результаты

| Квитанция | Выполнено | SHA256 |
|---|---|---|
| [H024_CONTAINER_FINAL_RESULT.json](H024_CONTAINER_FINAL_RESULT.json) | Текущий checker после H024-OOM-ATTR-001: 6/6 PASS | `223e7cb7c0b5f99fdeadffd824e6f82864e23014aac1202c9f38a8b4cf0dc01e` |
| [H024_CONTAINER_RESULT.json](H024_CONTAINER_RESULT.json) | Первая версия checker: 6/6 resource probes PASS; шесть собственных контейнеров удалены, remaining_owned_names пуст | `77039490e41de383387d837afad043660f65ead5b6725759e3b6d057cc079046` |
| [H024_DOCKER_CLI_RESULT.json](H024_DOCKER_CLI_RESULT.json) | 2/2 public-задачи, literal `python3 solution.py task.md`, оба выхода3/incomplete | `c018108160db945d68f17136db187d71ded7460f3120aa61b97d6a29b3515508` |
| [H024_IMPORT_RESULT.json](H024_IMPORT_RESULT.json) | Python 3.12.3 / glibc 2.39, dev-подмножество 13 direct pins / 45 distributions | `e2720c68ddec084ce46c26b2a4ae0af1df7f66e5bf1a0939abe96ed13cd331e8` |

CLI получил только четыре root `.py`, исходный requirements и рабочие копии входов. В каждом запуске `contract_valid=true`; API/tools/research/submission=false, экспериментов 0. Определены rmse/minimize/original для regression и macro_f1/maximize с average=macro, labels=null для classification; output order=test. Созданы только два JSON-артефакта контракта/alignment. Прежний CSV-сентинел и SHA исходников/входов сохранены; нового CSV с предсказаниями нет. Exit 3 является ожидаемым незавершённым агентом, а не ошибкой этого компонентного теста.

Полные 37 платформенных зависимостей не устанавливались и не проверялись. Корневой provided requirements сохранён побайтово, SHA256 `9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6`; dev-подмножество его не заменяет. Импорты/версии не означают пригодность будущего fit или метрики.

## Среда и воспроизводимость образа

- WSL 3.0.3.0, kernel 6.18.54.1-microsoft-standard-WSL2; дистрибутив AegML-Hackathon хранится на E: в `E:/WSL/AegML-Hackathon`.
- Новая общая настройка WSL: memory=24GB — проектные 24 GiB (`25769803776` байт), swap 4 GiB на E:, processors не задан, видны 12 logical CPU. Наблюдение WSL/Docker: `25202294784` байт RAM; настроенный предел и видимая память различаются.
- Docker Engine 29.9.1, rootful/systemd, cgroup v2, Unix socket `/var/run/docker.sock`, data-root `/var/lib/docker` внутри VHD на E:. TCP API не включался; пользователь aegml не добавлен в docker group.
- Локальный образ: `sha256:95e451e558d36beade7ffb1c64045a34cf152f9daac57336166e023c745cef0b`, tag `aegml-dev:h024-20261020`, размер `1350672156` байт.
- Один зафиксированный Ubuntu 24.04 base: `ubuntu@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac`.
- [Dockerfile.dev](../Dockerfile.dev) SHA256 `1b538059bb4bcebe9777be21060c0437a906a21e12eee1195213111e16e2bcc0`. Dev lock и wheels проверены по SHA. Фактические apt-версии записаны в import manifest, но `apt-get install` в Dockerfile не фиксирует их версиями: **побайтово одинаковая будущая пересборка не гарантируется**. Приёмка относится к данному готовому image ID; dev-образ не является сдаваемым ZIP.

После нового ответа чата1 усилена атрибуция OOM: помимо oom_kill теперь требуются положительные oom/max. [Guard regression](H024_OOM_GUARD_RESULT.json) показывает, что synthetic global-only event прежде проходил, теперь отклоняется; положительный локальный контроль проходит. Повторены только шесть относящихся resource probes, все PASS на новом SHA. Первоначальные JSON/source сохранены. [Intake и будущие H05-проверки](CHAT1_H024_H05_INTAKE.md).

## Ресурсные canaries и границы доказательства

Базовый контейнер: 20 GiB memory.max, swap.max=0, CPU quota `800000/100000`=8, pids.max=256, /work tmpfs 512 MiB. UID/GID 1000, read-only rootfs, cap-drop ALL, NoNewPrivs=1, builtin seccomp (mode 2), network none/только lo; домашние каталоги, исходники проекта, provider config и Docker socket не монтировались. Видимое число CPU/affinity осталось 12 и не приравнивается квоте 8. Предел 20 GiB проверен как настройка/cgroup ceiling, не выделением 20 GiB данных.

| Probe | Наблюдение первой версии; текущая повторно прошла все шесть случаев |
|---|---|
| H024-BASELINE | Разрешена запись /work, rootfs возвращает EROFS; права /work 0700, tmpfs 512 MiB; runtime security/cgroup значения соответствуют профилю |
| H024-CPU-THROTTLE | Квота 0.5 CPU, два child с wall-loop 1.6 с; elapsed≈1.669 с, children CPU 0.82 с, nr_throttled+17 |
| H024-MEMORY-64M / H024-MEMORY-128M | Отдельные лимиты 64/128 MiB, group-OOM=0; parent выжил, child SIGKILL, oom_kill+1 в каждом случае. Worker ограничен попыткой выделить/коснуться максимум 192 MiB, а не бесконечной аллокацией |
| H024-PIDS-16 | Из максимум 40 попыток созданы 15 child; EAGAIN, pids.current=16, pids.events.max вырос; после очистки осталось 1 |
| H024-TMPFS-4M | ENOSPC после 4194304 байт при предельной попытке 8 MiB |

**До stress** проверялся Docker inspect: identity/label, image ID, declared limits, mounts и security flags. **После bounded canary** сверялись фактические cgroup limits/counters. Эти две проверки не объявляются одним runtime preflight. Resource checker собирал stdout/stderr потоково с удержанием 64 KiB на каждый pipe, command timeouts и log-driver=none; признаков timeout/truncation/incomplete capture в 38 Docker-командах нет. Cleanup проверял exact name, owner label и полный ID перед удалением только своего контейнера.

Два CLI-теста имеют отдельный профиль: разрешён единственный host bind рабочей **staging-копии** в /work, /tmp — tmpfs 64 MiB; память 20 GiB/no swap, quota 8 и pids 256. Это trusted короткий CLI с контролируемым выводом, не испытание враждебного worker или доказательство потокового сбора его логов. Ресурсный профиль /work tmpfs 512 MiB не приписывается этим CLI-запускам.

## Изменения WSL и откат

До изменения обе дистрибуции были Stopped, `.wslconfig` отсутствовал. Создан только новый `C:/Users/ggdro/.wslconfig`; `wsl --shutdown` не выполнялся. Файлы default Ubuntu/AEGYX не менялись и default Ubuntu в этом этапе не запускалась. Однако **новые memory/swap являются общей настройкой WSL2** и повлияют также на будущие запуски default Ubuntu; отсутствия файловых правок недостаточно для заявления об отсутствии этого влияния.

Guard SHA нового config: `826662a1560f653b9df93173cfeba2a1675600a8c6df1b76f890e4d2c31c3794`. В windows-after обе дистрибуции снова Stopped. Откат не применялся: по отдельной команде сначала повторно проверить, что все WSL остановлены, затем SHA именно указанного файла; только при совпадении удалить **только новый config**. Если SHA изменился, автоматического удаления нет. VHD, swap-файл, данные/образы Docker и default Ubuntu этим откатом не удалять. Изменение вступит в силу при следующем запуске WSL, принудительную общую остановку сейчас не делать.

## Короткое воспроизведение готового образа

Справочно для отдельного разрешённого повтора: в AegML-Hackathon под UID0, из `/mnt/e/work/AegMLAI-agent`, заменить NEW-H024-RUN новым каталогом квитанций. Эти команды не пересобирают образ, не делают pull и не запускают ML/API; при оформлении документа они не исполнялись.

```sh
aegml_h024_image='sha256:95e451e558d36beade7ffb1c64045a34cf152f9daac57336166e023c745cef0b'
/usr/bin/python3 -B scripts/check_h024_container.py --image "$aegml_h024_image" --receipt /home/aegml/checks/NEW-H024-RUN/resources.json
/usr/bin/python3 -B scripts/check_h024_platform_cli.py --image "$aegml_h024_image" --receipt /home/aegml/checks/NEW-H024-RUN/cli.json
```

Текущий resource checker SHA256 `5a94fc420e2cc4743eadc0c08a341a6defbc1d1c85eb6e6c04540f1105a41223` (первый bceeeceb…c60b2 сохранён в истории); CLI checker — `01cfba293a37f15ab4dc060ffafbee16ef57848fa083b171fe676fda5d875e1a`.

## Сохранённые ограничения и продолжение

Исправления parser review подтверждены отдельно: 38/93/4 и bootstrap 24/51/37 в [H023_REVIEW_FIXES.md](H023_REVIEW_FIXES.md); прежние H023 JSON/source SHA сохранены историческими. Сами 74 основных и 17 HARN-T строк [TEST_MATRIX](TEST_MATRIX.md) остаются NOT_RUN: компонентный результат не закрывает их целиком.

Не выполнены официальный runtime со всеми 37 pins, H05 adversarial isolation/process-tree/hard timeout, полный 10800-секундный прогон, feature-based fit, измеренные RMSE/F1, live API/tools и AutoResearch. API-вызовов 0. **Следующий подпункт — H03.1 только по команде владельца**, без автоматического перехода.
