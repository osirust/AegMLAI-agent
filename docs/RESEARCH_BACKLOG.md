# Исследования заранее: очередь и доказательства

Актуально на **21.10.2026**: владелец разрешил весь H03.1–H03.5; компонентные, интеграционные и Docker-проверки выполнены локально, их область и квитанции учитываются в [H03_RECEIPT](H03_RECEIPT.md). **Следующая граница — остановка перед H04** до отдельной команды владельца. Разрешение чату «1» исследовать будущие этапы не разрешает их реализацию. Live Qwen и `/key/info` требуют отдельной команды владельца. Модель GPT‑5.6 Pro выбрана владельцем как целевая для веб-чатов, фактическое UI-переключение не подтверждено.

## Состояние передачи

Досье чата «1» по H03–H08/P2 прочитано по трём ignored-снимкам в `runs/h03/h03-20261021T060520Z/`: `chat1-dossier-prefix-TRUNCATED.txt`, `chat1-dossier-part2.txt`, `chat1-dossier-part3-END.txt`. [Разбор H03–H06](CHAT1_H03_H06_INTAKE.md) сохраняет свой ранний частичный снимок; [разбор H07/H08/P2](CHAT1_H07_H08_INTAKE.md) учитывает завершающую часть. Тематический охват получен, но побайтовая полнота первоначального первого сообщения не доказана. Проверена только явно указанная в этих разборах часть первичных утверждений; гипотезы не стали экспериментами или измеренным выигрышем.

Дополнительный H04-ответ прочитан до END: prefix20000символов (`cad10ec9…`) и запрошенное продолжение6164символа (`85e33a42…`). [Quality intake](CHAT1_H04_QUALITY_INTAKE.md) сохраняет пять сверенных primary-source claims, все H1–H9 и stop rules. Исходное длинное сообщение byte-for-byte не получено; архивы частей сохранены. MEI0.5%/.003 и бюджеты300/900/1800сек — предложения, не принятые критерии или измеренный выигрыш. Чат2 закрыл четыре замечания и отдельно destination-bind; [полный review intake](H03_CHAT2_REVIEW_INTAKE.md). Новых заданий нет; foreground polling завершён вместе с H03.

### История передачи 20–21.10

Единый запрос H03–H08 сохранён в `runs/h02/h02-review-repair-20261020T195535Z/chat1-future-research-prompt.txt` (ignored). Первая новая отправка вернула Too many requests; встроенный браузер не загрузил существующий разговор, принятие запроса тогда не было подтверждено. 21.10 владелец возобновил веб и оба пакета приняты с интервалом 94 сек; [подтверждения](WEB_DISPATCH_20261021.json). Причина прежнего 429 остаётся UNKNOWN. Исторические тексты: [чат1](../research_packets/CHAT1_FUTURE_RESEARCH.md) и [чат2](../research_packets/CHAT2_H02_REPAIR_REVIEW.md); их прежние stop/unsent фразы не задают текущий статус.

## Пакеты одного исследования

| ID | Этап и вопросы | Требуемый сохраняемый результат | Статус |
| --- | --- | --- | --- |
| FUT-RES-01 | H03: полный streaming input, fit-only статистика, null/missing, категории/текст, численная устойчивость метрик, ID/order и непустой atomic CSV | Источники + контракт данных + положительные/отрицательные контроли; отдельно исследовательские и защищённые строки | DOSSIER_READ_PRIMARY_SUBSET_VERIFIED_NOT_BENCHMARKED |
| FUT-RES-02 | H04: CatBoost1.2.8, LightGBM4.6.0, XGBoost2.1.4, sklearn1.5.2; AutoGluon1.3.1, FLAML2.3.6, LightAutoML0.4.2 | Матрица применимости при CPU8/трёх часах и доступной памяти; минимум равнобюджетных абляций | DOSSIER_READ_PRIMARY_SUBSET_VERIFIED_NOT_BENCHMARKED |
| FUT-RES-03 | H04: MacroF1/редкие классы, regression original-scale RMSE, веса, target transforms, ансамбли, frozen refit и стоимость финализации | Измеримая гипотеза/контроль/stop rule, без утечки outer и обещаний улучшения | DOSSIER_READ_PRIMARY_SUBSET_VERIFIED_NOT_BENCHMARKED |
| FUT-RES-04 | H05: OS-граница без предположения nested Docker, UID/proc/FD/secret, сеть, дерево процессов, RAM/PID/time/log bounds | Capability-gated варианты и dummy adversarial acceptance; локальные canaries не объявлять full H05 | DOSSIER_READ_PRIMARY_SUBSET_VERIFIED_NOT_BENCHMARKED |
| FUT-RES-05 | H06: Qwen transport/tools без обязательного mcp, malformed/partial replies, retries/budget/redaction/context | Контракты и mocks; service capabilities остаются UNKNOWN до отдельного live разрешения | DOSSIER_READ_PRIMARY_SUBSET_VERIFIED_NOT_BENCHMARKED |
| FUT-RES-06 | H07: AIDE и сходные ML-агенты, search tree/journal/repair/select/rollback; fixed/AutoML/one-shot/feedback/multirole | Official repo/paper/license/version, извлечённый механизм, ограничения переноса и сравнимые бюджеты | DOSSIER_READ_PRIMARY_SUBSET_VERIFIED_NOT_BENCHMARKED |
| FUT-RES-07 | H08: новые задачи, injection, adaptive validation overfit, multiple comparisons, seed/effect size, clean-room packaging | Диагностические fixtures и gates, отдельно runtime/quality/officialscore | DOSSIER_READ_PRIMARY_SUBSET_VERIFIED_NOT_BENCHMARKED |
| FUT-RES-08 | P2: собственные малые архитектуры с нуля и поддерживаемая доставка компонентов | Только обоснованные кандидаты после рабочего агента; без автоматического переноса AEGYX/весов | DOSSIER_READ_PRIMARY_SUBSET_VERIFIED_NOT_BENCHMARKED |

Этот статус описывает получение общего досье и проверку части его первичных ссылок. Он не означает независимую проверку каждого утверждения строки, выполненный benchmark, приёмку H04–H08/P2 или завершение отдельного дополнительного запроса H04.

## Проверенные ориентиры основного Codex

Это историческое краткое чтение первичных источников; более поздние проверки части досье перечислены в двух intake выше. Оно не является измерением выигрыша.

- Python3.12 `csv.reader` возвращает строки без автоматического определения числовых типов; поэтому смысл пустой ячейки, `NA` и `null` должен задавать наш контракт. [Python CSV](https://docs.python.org/3.12/library/csv.html).
- Python3.12 JSON поддерживает `allow_nan=False`; нечисловые JSON-значения NaN/Infinity нельзя молча публиковать в доказательствах. Размеры входов и выходов ограничиваются отдельно. [Python JSON](https://docs.python.org/3.12/library/json.html).
- Предобработку обучают только на разрешённом train, затем применяют к остальным частям; train/test нельзя смешивать при обучении преобразования. [sklearn1.5.2: common pitfalls](https://scikit-learn.org/1.5/common_pitfalls.html). Более строгая защита closed outer — наше требование из математического протокола.
- AutoGluon имеет отдельную документацию именно1.3.1; её и исходники этой версии надо использовать при проверке доступных режимов. Наличие современного tutorial не доказывает совместимость другого релиза или запрет pretrained компонентов. [AutoGluon1.3.1](https://auto.gluon.ai/1.3.1/tutorials/tabular/tabular-essentials.html).
- FLAML описывает `time_budget`; фактическая длительность и соблюдение общего deadline всего нашего процесса требуют отдельной проверки. Текущая страница не привязана к установленному2.3.6, поэтому детали сверять с pinned source. [FLAML](https://microsoft.github.io/FLAML/docs/Use-Cases/Task-Oriented-AutoML/).
- AIDE — релевантная база для изучения ML-агента; полный аудит архитектуры/лицензии и применимости ещё не выполнен этим чтением. [Официальный репозиторий](https://github.com/WecoAI/aideml).

## Как принимать и сохранять ответы

1. Сохранить полный ответ и идентификатор сообщения в ignored run, вычислить SHA; отдельно отметить длину/полноту и наличие первичных ссылок.
2. Разделить утверждение источника, наш вывод, проверяемую гипотезу и UNKNOWN. Проверить версии и фактический механизм в первичном источнике; чужой benchmark не становится нашим качеством.
3. Внести вывод в тематический Markdown: [источники](RESEARCH_SOURCES.md), [AutoML](AUTOML_RESEARCH_BRIEF.md), [агенты](OPEN_SOURCE_AGENT_REVIEW.md), [протокол](RESEARCH_PROTOCOL.md), [harness](QWEN_HARNESS_DESIGN.md), [runtime](RUNTIME_AND_FAILURES.md). Сохранить source/claim/limits/эксперимент, а не копировать статью целиком.
4. Для рекомендации указать applicability, равнобюджетный comparator, минимальный эффект, stop rule, критерий опровержения и зависимость WORK-блока. Implementation/test status остаётся NOT_RUN до его отдельного выполнения.
5. Менять ТЗ только после проверки рекомендации и в разрешённом scope. Ключи, raw CSV/ID/закрытые метки в веб-чаты не передавать. Перед новым сообщением уведомлять владельца; не прерывать самостоятельной задачей незавершённый запрос.


Текущий порядок веб-работы: основной Codex — единый диспетчер; делегированные агенты самостоятельно к чатам не обращаются. Во время активной работы допускается проверка прогресса примерно раз в 5 минут. Общий интервал между **любыми** read/status/send и браузерными чтениями обоих чатов — не менее 60 сек; обращения последовательные. Новый независимый запрос не добавлять в занятый чат. При 429 прекратить обращения и сообщить владельцу; автоматических retries и фоновых автоматизаций не создавать. Это локальное правило работы, не опубликованный лимит сервиса и не установленная причина прежнего 429. Ожидание веб-ответа не разрешает H04 или live API.
