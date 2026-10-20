# Ответ чата 1: границы H02.4 и будущая приёмка H05

Дата проверки источников: **20.10.2026**. Вход — переданный владельцем ответ `Вставленный текст.txt`, 15970 символов, SHA256 `ecd2a930827a0cf10820e0d4d8904697df68c07e9b5734e98c6fdb5c35212b4f`. Это исследовательская заметка, не независимый прогон среды. **SOURCE** ниже означает проверенную первичную документацию; **REPORTED** — сведения переданного отчёта; **PROPOSED** — ещё не выполненную проверку. Этот intake не разрешает H05, API, обучение или установку.

## Шесть первичных источников

| ID | Источник, версия | Подтверждаемое положение и предел переноса |
| --- | --- | --- |
| S1 | Microsoft, [WSL configuration](https://learn.microsoft.com/en-us/windows/wsl/wsl-config), текущая редакция | `.wslconfig` задаёт общий ресурсный контур VM WSL2; это не бюджет отдельного worker. Дату редакции из ответа отдельно не принимаем за локальный факт. |
| S2 | Docker, [container run](https://docs.docker.com/reference/cli/docker/container/run/), текущая документация | Read-only root, отдельные mounts и security options имеют разные области действия. Документация не проверяет нашу установку Engine29.9.1. |
| S3 | Docker, [Rootless mode](https://docs.docker.com/engine/security/rootless/), текущая документация | Rootless охватывает daemon и контейнеры в user namespace. Rootful daemon с UID1000 внутри контейнера — другая конфигурация. |
| S4 | Linux, [cgroup v2](https://docs.kernel.org/6.12/admin-guide/cgroup-v2.html), ветка 6.12 | Определены ресурсные контроллеры, OOM-события и завершение поддерева. Реальные права и поддержку интерфейсов проверяют в целевой среде. |
| S5 | Linux, [Seccomp BPF](https://docs.kernel.org/6.12/userspace-api/seccomp_filter.html), ветка 6.12 | Фильтрация syscall сокращает поверхность ядра; сама по себе не задаёт полноценную песочницу или политику информационных потоков. |
| S6 | Linux, [sysctl vm](https://docs.kernel.org/6.12/admin-guide/sysctl/vm.html), ветка 6.12 | `vm.max_map_count` ограничивает число отображений памяти процесса. Его нельзя путать с `memory.max`, выраженным в байтах. |

**Версия документации 6.12 не является версией установленного ядра.** Локальная квитанция H02.4 фиксирует `6.18.54.1-microsoft-standard-WSL2`; чат 1 не получил эту версию в исходном prompt. Поэтому его оговорка об неизвестном ядре относится к доступному ему контексту, а не к отсутствию локального измерения.

## Что уточняет ответ

**SOURCE:** `oom_kill` учитывает процессы данной cgroup, убитые любым видом OOM killer. Единственного положительного счётчика недостаточно для атрибуции срабатывания `memory.max`. Нужны изменения `max` и `oom`, точная группа, bounded-нагрузка, исход ребёнка и выживание parent. `memory.events` иерархичен; `memory.events.local` имеет другую область учёта. [S4](https://docs.kernel.org/6.12/admin-guide/cgroup-v2.html)

**Действие H024-OOM-ATTR-001:** root усилил predicate условием `oom>0 && max>0` вместе с прежними свидетельствами. Прочитанный [H024_OOM_GUARD_RESULT.json](H024_OOM_GUARD_RESULT.json) сообщает PASS отдельной проверки ложноположительного случая; [H024_CONTAINER_FINAL_RESULT.json](H024_CONTAINER_FINAL_RESULT.json) фиксирует новый локальный прогон с SHA изменённого checker. [H024_CONTAINER_RESULT.json](H024_CONTAINER_RESULT.json) сохраняется историческим. Intake не подменяет эти квитанции проверкой документации и не закрывает H05.

**REPORTED:** два штатных CLI-прохода с exit3 подтверждают незавершённый контрактный маршрут. Их RW staging и сохранённые SHA не доказывают невозможность записи недоверенным кодом. Read-only root не делает отдельный RW-bind неизменяемым. [S2](https://docs.docker.com/reference/cli/docker/container/run/)

## Восемь будущих проверок — все NOT_RUN

Это **PROPOSED** детализация существующих требований H05, не новый этап реализации. Каждая проверка использует только искусственные canary, ограниченные disposable-фикстуры и положительный контроль разрешённого действия.

| Проверка | Требуемое свидетельство; статус |
| --- | --- |
| 1. Parent/proc/env/host paths | Реальный launcher закрывает dummy-секреты, память и сигналы supervisor; записаны namespaces/UID mapping, разрешённый файл читается. **NOT_RUN**. |
| 2. Наследуемые FD | До первой инструкции кандидата доступны только разрешённые каналы; dummy-файл, directory FD и socket не обходят mounts через используемый fork/spawn/exec. **NOT_RUN**. |
| 3. Потомки и timeout | Bounded child/grandchild, новая сессия, игнорирование TERM и ранний выход parent не оставляют писателей после deadline+cleanup. Чужой sentinel сохранён. **NOT_RUN**. |
| 4. Файлы и staging | Truncate/rename/unlink/symlink/traversal не меняют защищённые train/split/task/evaluator/старый CSV; scratch, логи и заполнение диска ограничены. **NOT_RUN**. |
| 5. Labels и evaluator | Worker не видит закрытый target/cache; evaluator независимо считает метрику из данных, отвергает неверные строки и не импортирует кандидат. Outer не возвращается в feedback. **NOT_RUN**. |
| 6. Секреты по всему маршруту | Dummy-key только у provider; отсутствует в worker env/argv/FD, ошибках, stdout/stderr, артефактах и crash-пути; сами canary не печатаются в отчёте. **NOT_RUN**. |
| 7. Сеть и broker | Проверены bounded IPv4/IPv6/DNS/Unix-socket, proxy/redirect и размер ответа; worker не выбирает произвольный endpoint/auth. Разрешённый mock работает, live Qwen не нужен. **NOT_RUN**. |
| 8. Подмена артефакта | Symlink/FIFO/перезапись inode и crash публикации не меняют принятые evaluator байты; ограниченный собственный snapshot имеет SHA, старый CSV переживает отказ. **NOT_RUN**. |

## Архитектурные следствия

CPU/RAM quota контейнера не покрывает автоматически supervisor/evaluator/broker вне этой группы, общий deadline, диск и логи. Конкурсный бюджет учитывает весь процесс и потомков; host launcher не становится бесплатным ресурсом. Короткие canary не доказывают устойчивость на трёхчасовой нагрузке.

Закрытие labels не гарантирует train-only preprocessing: получив validation X, кандидат способен обучить на нём преобразование. Нужна контролируемая граница fit/predict. Платформенные namespaces/cgroups/nested Docker остаются UNKNOWN; локальный Docker не снимает это ограничение.

Если проверенная OS-граница недоступна, предлагается `GENERATED_CODE=DISABLED / ISOLATION_UNAVAILABLE`: только доверенные recipes с ограниченными типизированными параметрами, без исполнения/import/unpickle LLM-артефактов. Это явно degraded fallback; он не закрывает полноту generated-code AutoResearch. Subprocess, venv, AST и WSL сами по себе такую гарантию не дают.
