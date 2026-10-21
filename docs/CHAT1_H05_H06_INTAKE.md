# H05/H06: приём досье, первичные источники и проект проверок

Редакция: 21.10.2026, сверка источников завершена около 10:36 UTC / 13:36 МСК. Это **обзор источников и предложение реализации/приёмки**, не выполненная изоляция и не проверка Qwen.

Текущий статус этого документа: `DOSSIER_COVERAGE_COMPLETE_WITH_CONTINUATION`; для предложенных механизмов — `PROPOSAL / NOT_RUN`. Чат1 не является организатором или нормативным источником разрешений. Его советы сопоставлены с первичной документацией и текущими решениями владельца.

## 1. Что действительно прочитано

| Материал | Фактическая сохранённая форма | SHA-256 |
| --- | --- | --- |
| Ответ чата1, agent message `b6dedd17-0a45-4e4f-99f4-a456282e140c` | `runs/h04/h04-20261021/chat1-h05-h07-reply.txt`: усечённая видимая выдача 18000 символов; файл 18001 символ с завершающим переводом строки, 26774 байта | `3e601ff54a0c9d78a4aa33910b3ac8535acaf19c41fd6a49dac9cbb679aa3a40` |
| Продолжение, agent message `7d6ac81e-6749-404a-b81c-2983093ad248` | `runs/h04/h04-20261021/chat1-h05-h07-part2-END.txt`: 5049 видимых символов, файл 5050 символов / 7887 байт; прочитан до явного `END` | `19d6cd48aa1524dd2420381feacf444ed1d89f9719c1483040564177c688a070` |
| Предоставленные requirements | Неизменённые 37 pins, включая `openai==1.68.2`, `httpx==0.28.1`, `catboost==1.2.8` | `9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6` |

Продолжение начинается с окончания оборванного предложения о конфликте call ID. Доступное досье теперь покрывает оставшиеся H06-разделы и заключительный H07 gate. **Побайтовая полнота исходного первого сообщения не установлена:** это prefix плюс отдельно запрошенный tail. Ссылки вида `chatgpt-content-reference` из текста не используются как доказательства; ниже приведены проверенные первичные URL.

Версии OpenAI/HTTPX также записаны как реально установленные в исторической [H024_IMPORT_RESULT](H024_IMPORT_RESULT.json). Это подтверждение установки, а не использования сети. В рамках этого обзора прочитаны файлы и первичные веб-страницы; ОС-пробы, пакетные установки, обучение, запросы к провайдеру и `/key/info` не выполнялись.

## 2. Пять критических утверждений: что подтвердили первичные источники

### 2.1. Landlock ABI4 и ABI6 закрывают разные свойства

**SOURCE.** Версионированная документация Linux 6.12 показывает: ABI4 добавляет TCP bind/connect по порту; ABI5 — device ioctl; ABI6 — scopes для сигналов и abstract UNIX sockets. TCP-правило на порт не является фильтром адресов сервера или общей сетевой политикой. Права и scopes должны быть явно включены в ruleset. [Linux 6.12 Landlock](https://docs.kernel.org/6.12/userspace-api/landlock.html).

**INFERENCE для нашего проекта.** Разрешение TCP443 worker-у не означает «доступен только Qwen». P0 worker вообще не нуждается в сети: провайдер остаётся у доверенного broker. ABI-query сообщает возможности интерфейса; он не устанавливает ограничения и не доказывает правильность ruleset. Недостающие свойства нельзя молча исключать ради запуска. Выбор минимального ABI и доказанных компенсаций — часть версии backend policy.

### 2.2. Seccomp-BPF не читает `clone3` flags по указателю

**SOURCE.** Seccomp-filter получает скалярные syscall-аргументы и не разыменовывает указатели. `clone3` передаёт flags внутри `struct clone_args`, тогда как интерфейс `clone` отличается. Следовательно, фильтрация flags у этих вызовов не взаимозаменяема. [Kernel seccomp-filter 6.12](https://docs.kernel.org/6.12/userspace-api/seccomp_filter.html), [clone/clone3](https://man7.org/linux/man-pages/man2/clone.2.html).

**PROPOSAL.** В ограниченном backend запретить создание отдельных процессов и новые `execve/execveat`; `clone3` не разрешать как непрозрачный общий путь. Оставить только проверенный путь threads через допустимый `clone` с явными флагами, архитектурой и политикой ABI, включая отказ x32/неизвестным номерам. Конкретный errno и возможность libc fallback требуют положительного runtime-контроля: нельзя заранее обещать совместимость NumPy/CatBoost. Если безопасный thread-путь не работает, не ослаблять запрет до «разрешить весь clone3».

### 2.3. Свежий env не закрывает унаследованные FD и parent `/proc`

**SOURCE.** Landlock не отзывает файловые права у уже открытых до ограничения FD; часть metadata-операций, включая `chmod/chown`, им не закрывается. [landlock(7), file actions и caveats](https://man7.org/linux/man-pages/man7/landlock.7.html). `execve` заменяет память программы, но открытые FD без close-on-exec обычно сохраняются. [execve(2)](https://man7.org/linux/man-pages/man2/execve.2.html). `/proc/PID/environ` отражает начальное окружение процесса; позднее удаление переменной не равно её исчезновению из этого представления. [proc_pid_environ(5)](https://man7.org/linux/man-pages/man5/proc_pid_environ.5.html).

**PROPOSAL.** Чистый exec доверенного bootstrap, минимальный env без ключа, положительно заданный набор pipe-FD и закрытие остальных дескрипторов до candidate-кода. Запретить доступ к parent/sibling `/proc`, чужой памяти и средствам получения чужих FD. [close_range(2)](https://man7.org/linux/man-pages/man2/close_range.2.html) описывает закрытие диапазона; это возможный механизм, ещё не проверенный в нашей среде. `dumpable=0` у trusted-процессов полезен дополнительно, но не заменяет файловые/сигнальные запреты. [PR_SET_DUMPABLE](https://man7.org/linux/man-pages/man2/PR_SET_DUMPABLE.2const.html).

### 2.4. Rlimits не равны изолированной квоте worker

**SOURCE.** `RLIMIT_AS` ограничивает virtual address space, не измеренную RSS. `RLIMIT_NPROC` в Linux относится к real UID и учитывает threads; у него есть исключения для привилегированных процессов. `RLIMIT_FSIZE` ограничивает один файл, а `RLIMIT_CPU` — CPU time, не wall-clock. [getrlimit(2)](https://man7.org/linux/man-pages/man2/getrlimit.2.html).

**SOURCE.** Cgroup v2 имеет отдельные контроллеры и `cgroup.kill`, который охватывает дерево и конкурентные forks; доступность видимого cgroupfs не доказывает право управлять выделенной группой. [Kernel cgroup v2 6.12](https://docs.kernel.org/6.12/admin-guide/cgroup-v2.html).

**INFERENCE.** `thread_count=8`, env OpenMP и прежний Docker20GiB/quota8 не доказывают отдельный предел недоверенного worker в официальной среде. Для P0 разумен режим без новых процессов и без произвольной записи файлов: bounded pipes вместо scratch без квоты. Нужны проверяемые hard limits, независимый wall-clock watchdog и прекращение всех разрешённых threads. При недостаточной защите supervisor или ресурсов generated-code остаётся HOLD.

### 2.5. Defaults закреплённых HTTP-библиотек необходимо переопределить

**SOURCE, именно `openai==1.68.2`.** `DEFAULT_TIMEOUT` — 600 секунд с connect=5; `DEFAULT_MAX_RETRIES=2`. [Pinned constants](https://github.com/openai/openai-python/blob/v1.68.2/src/openai/_constants.py). Default SDK HTTP client задаёт `follow_redirects=True`; SDK содержит автоматические повторы для ряда ошибок, включая 429/5xx. [Pinned base client](https://github.com/openai/openai-python/blob/v1.68.2/src/openai/_base_client.py).

**SOURCE, именно `httpx==0.28.1`.** У прямого HTTPX Client defaults иные: `follow_redirects=False`, `trust_env=True`. [Pinned HTTPX client](https://github.com/encode/httpx/blob/0.28.1/httpx/_client.py). Read timeout ограничивает ожидание очередного chunk, а не весь ответ. [HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/).

**PROPOSAL.** Отключить скрытые SDK retries, redirects и неявные env proxy; TLS-проверку оставить включённой. Корпоративный proxy/CA возможен только как отдельная доверенная конфигурация. Один слой владеет bounded retry/backoff, лимитами connect/read/write/pool и абсолютным monotonic deadline. Ограничить bytes wire/decompressed body до накопления. Регулярный небольшой stream не должен продлевать общий срок. Это проект H06, не проверенное поведение выданного прокси.

## 3. Предлагаемый P0 backend без root

**Архитектурная рекомендация:** сначала проверить узкий backend «один процесс с разрешёнными threads», используя Landlock + seccomp-filter + no_new_privs; многопроцессный AutoML пока не допускать. Внешний Docker остаётся дополнительным окружением. Нельзя считать его внутренней границей worker/evaluator или переносить локальный PASS в неизвестный образ платформы.

NNP наследуется и не снимается; он препятствует получению новых прав через exec, но не отнимает существующие права и не закрывает файловый/IPC-доступ. [Kernel No New Privileges](https://docs.kernel.org/userspace-api/no_new_privs.html). Проверки архитектуры, наследования и thread-синхронизации seccomp должны быть частью gate. [seccomp(2)](https://man7.org/linux/man-pages/man2/seccomp.2.html).

Предлагаемый порядок запуска:

1. Supervisor фиксирует source/split/schema/policy SHA, дедлайн и разрешённую фазу. Готовый CSV и evaluator остаются у него.
2. Чистый exec загружает только доверенный bootstrap из проверенного пути. Ни taskdir, ни candidate-код не импортируются до admission. Никакого ключа, закрытых y или broker-сокета в env/памяти/FD worker.
3. Worker получает только необходимые данные: T_fit для разрешённого fit; prepared X для предсказания. Полный train, inner/outer y и исходный task-local каталог не выдаются. Если arbitrary-код видит inner X, это ещё не доказательство train-only preprocessing: режим должен либо передавать замороженное представление, либо честно учитывать это ограничение.
4. До первого недоверенного действия и до запуска threads закрываются лишние FD; устанавливаются hard resource limits, NNP, Landlock rules и seccomp. Права на библиотеки задаются минимальными физическими деревьями; нельзя разрешать всё home/repo с секретами и данными.
5. Сетевые sockets/IPC, новые процессы/exec, доступ к памяти и FD других процессов, опасные metadata/namespace/kernel interfaces блокируются проверяемой policy. Сигналы допустимы только в нужном внутреннем scope; parent и sibling должны переживать отрицательные контроли. Числовые syscall rules нельзя угадывать для неизвестной архитектуры.
6. Без проверенной scratch-квоты произвольная файловая запись запрещена; stdout/stderr и data-only predictions поступают по ограниченным каналам. Supervisor дренирует/ограничивает потоки до накопления и не импортирует/не unpickle-ит output кандидата.
7. Admission разрешает candidate только после положительных и отрицательных контролей конкретной комбинации kernel/image/launcher/policy. При обязательном разрыве — `GENERATED_CODE=HOLD`; доверенные recipes остаются отдельным режимом, без заявления, что они реализуют генерацию нового кода.

Наличие ABI, успешный syscall или `Seccomp=2` не закрывают этот список. Защита ядра от всех уязвимостей и побочных каналов данным проектом не обещается. Установка root-пакетов, Docker socket, изменение внешней security policy и снятие запретов ради успешного probe не предлагаются.

## 4. H06: offline-протокол отдельно от live-совместимости

**PROPOSAL / NOT_RUN.** Один controller, один активный запрос и последовательный dispatcher со статическим registry. Native `tool_calls` и JSON action в `content` — разные явно выбранные режимы с одинаковой локальной валидацией и полномочиями. JSON fallback не должен незаметно превращать native-tool отказ в PASS. Официальная [Qwen Function Calling](https://qwen.readthedocs.io/en/latest/framework/function_call.html) описывает семейство протоколов, но не устанавливает capabilities нашего endpoint.

Закреплённый SDK описывает optional `tool_calls` и предупреждает, что arguments требуют проверки; его типы не гарантируют корректный JSON от сервера. [OpenAI 1.68.2 message types](https://github.com/openai/openai-python/blob/v1.68.2/src/openai/types/chat/chat_completion_message.py).

Offline-пакет должен проверять:

- Полностью полученный ответ → strict JSON без duplicate keys/NaN/лишних полей → schema/tool/phase/budget validation → admission → исполнение handler → настоящий результат → continuation с правильным call ID. Из reasoning, Markdown и частичного stream ничего не исполняется.
- Журнал `proposed/validated/admitted/running/completed/failed`, отдельно `unknown/in-flight`. Повтор ID с другими arguments — конфликт. Утерянный result сверяется с журналом и живым исполнением; второй fit не запускается вслепую. Локальная идемпотентность не гарантирует exactly-once provider inference после transport timeout.
- Один bounded retry-владелец. 401/403 и несовместимая схема не становятся бесконечным retry; 429/5xx и Retry-After укладываются в остаток общего дедлайна вместе с финализацией. Mock не имеет live network fallback.
- Журнал содержит только allowlisted status/type/timings/request-ID и проверенные aggregate tool results. Ключ, headers, полный error body, request repr, private paths и закрытые данные не логируются. Канонические schema/request hashes не должны включать секрет.
- Usage учитывается, когда действительно возвращён и валиден; отсутствующее поле остаётся `null/UNKNOWN`, не нулём. Наличие в SDK типов prompt/completion/reasoning-token details не доказывает их выдачу прокси. [Pinned usage types](https://github.com/openai/openai-python/blob/v1.68.2/src/openai/types/completion_usage.py).

### Предложенный первый live-probe — не новое разрешение

Чат1 предлагает два inference-запроса, 60 секунд общего потолка и ноль автоматических повторов. Это **предлагаемый бюджет теста**, не ограничение владельца, не SLA Qwen и не доказательство отсутствия tools при timeout.

Первый prompt предлагает один безопасный `probe_echo`. Локальный handler после ответа создаёт свежую случайную canary, которой не было в первом prompt. Второй запрос получает настоящий tool-result; совпадение canary в continuation проверяет фактическую передачу результата. Один HTTP200, произвольный текст или JSON в content не подтверждают native tools. Structured-режим проверяется отдельно с явным статусом.

Предложение источника не вызывать `/key/info` относится к минимальному tool-probe и не отменяет будущую проверку остатка по решению владельца. Текущая условная команда допускает первый короткий live H06.2 только после готовности исполнения H05 и offline/mock H06. До этих предпосылок, в том числе сейчас на H04, API=0. Ключ этому агенту не передаётся. Лимит600₽ не используется для планирования по указанию владельца; числовые RPM/TPM/стоимость/контекст и фактическая поддержка tools остаются UNKNOWN.

## 5. Десять адресных acceptance-контролей

Все строки ниже — **план, NOT_RUN**. Только собственные временные canaries, малые лимиты и независимый watchdog; никаких внешних целей. Отрицательный отказ засчитывается лишь вместе с положительным контролем и доказательством, что целевая операция действительно была достигнута.

| ID | Отрицательный контроль | Положительный контроль и достаточное доказательство |
| --- | --- | --- |
| H05-P01 | Недоступен обязательный механизм/ABI либо policy не установлена | Доверенный bootstrap проходит; candidate-effect отсутствует при отказе; сохранены stage/errno/policy SHA |
| H05-P02 | Worker не читает protected canary и не изменяет content/mode/owner/rename/unlink источников | Разрешённые библиотеки и T_fit читаются; снаружи совпали bytes SHA и metadata защищённых файлов |
| H05-P03 | Нет доступа к dummy parent-env/memory/FD, заранее открытым secret/directory/socket FD; нельзя сигналить parent/sibling | Разрешённый pipe работает; trusted sentinel остаётся жив; canary не выводится даже при ошибке |
| H05-P04 | IPv4/IPv6/DNS/UNIX/abstract IPC не достигают собственных dummy listeners; нельзя получить новый FD через IPC | Разрешённый data-pipe передаёт bounded результат; listener counters подтверждают отсутствие соединений |
| H05-P05 | fork/vfork/process-clone/exec и непрозрачный clone3 не создают разрешённое отдельное дерево | Разрешённые threads и короткая синтетическая CPU-операция библиотеки работают; политика сохраняется у всех threads; новая задача не получает старые canaries |
| H05-P06 | Малые memory/CPU/thread/output limits и wall-clock timeout реально срабатывают; worker не меняет hard limits/affinity policy | Подпороговая нагрузка проходит; supervisor жив; после deadline нет worker threads/writers; счётчики и cleanup проверены снаружи |
| H05-P07 | Шумный/зависший output, symlink/FIFO/подмена, неверные строки/метрика/порядок не принимаются | Приняты те же bounded snapshot bytes, что проверены; корректный data-only прогноз проходит; прежний валидный CSV сохраняется при отказе |
| H06-P01 | Плохой/duplicate-key JSON, NaN, unknown tool, лишние поля, partial arguments, конфликт ID дают side effect=0 | Валидный mock action исполняется ровно один раз, tool-result привязан к исходному call ID; воспроизводимая replay identity |
| H06-P02 | Mock 401/429/5xx, slow chunks, redirect, proxy и canary в exception не обходят deadline/redaction/endpoint policy | Обычный mock response проходит; retries/bytes/time bounded; отсутствующий usage остаётся UNKNOWN; реальных HTTP-запросов0 |
| H06-P03 | После выполнения предпосылок неподходящий live response/timeout не получает tool PASS | По разрешённому probe сохранены mode/schema SHA, call ID, факт handler execution, fresh-canary match, timings/usage или UNKNOWN; статусы native/structured раздельны |

Для H05-P06 `RLIMIT_NPROC` сам по себе не считается изолированной PID-квотой, а `RLIMIT_AS/FSIZE` — RSS/суммарной disk-квотой. Если конкретный backend не обеспечивает заявленное свойство, оно остаётся HOLD; его нельзя закрывать соседним положительным тестом.

## 6. Порядок дальнейшей работы и сохранённые UNKNOWN

По последней команде владельца маршрут H04 → H05 → H06 с отдельными приёмками; начало H05 — после текущего H04 review/разрешённого перехода root. Ручной ориентир 21.10 18:00 МСК не гарантирует завершения всех gate или официальный score. Этот обзор не запускает этапы и не меняет основной план.

P0-порядок проектирования: capability registry/fail-closed admission → один проверенный backend → offline dispatcher/transport → короткий live-probe после предпосылок. Положительный fallback-baseline не означает завершённый Qwen research. Хвост досье полезно разделяет `protocol_mock_pass`, `protocol_live_pass`, `research_real_executed`, `quality_improved`, `generated_boundary_pass`; ни один статус не заменяет остальные.

H07 требует фактических H04/H05/H06: гипотеза с реальным исполнением, затем следующая гипотеза с использованием измеренной обратной связи, сопоставимые budget/split/metric и независимый keep/revert. Outer не становится feedback; frozen refit не запускает новый поиск. Это будущий gate, не выполненный AutoResearch и не доказанное улучшение.

**UNKNOWN на момент этой редакции:** возможности официального kernel/image; доступность/полнота Landlock/seccomp и namespace/cgroup delegation; совместимость выбранной thread-policy с библиотеками; hard deadline/cleanup и ресурсная изоляция worker; фактический endpoint protocol/context/usage/reasoning/RPM/TPM; безопасность и успешность live-call. Ни ABI-query, ни прежний Docker import/PASS, ни чтение этого досье данные статусы не закрывают.
