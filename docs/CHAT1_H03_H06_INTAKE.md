# Разбор исследовательского досье чата 1: H03–H06

Дата: 21.10.2026. Статус: **PARTIAL_DOSSIER_READ / DESK_RESEARCH_ONLY**.

Полностью прочитаны две сохранённые части: `runs/h03/h03-20261021T060520Z/chat1-dossier-prefix-TRUNCATED.txt` и `chat1-dossier-part2.txt` в том же каталоге. Их SHA256 — `9233cdba342813ae0b584c7b108216c378174fc0322215bf17f7d010937b2f4e` и `358b933ecee183faf65679ea8dfda834d1178d74ac14ff7cff730ee279933fe4`. Первая заканчивается внутри H04 §5, вторая продолжает эту фразу и заканчивается после таблицы проектов H07 §1. Отрицательные результаты H07, H08, итоговый backlog/P2 и заключительный UNKNOWN ещё не прочитаны. Досье целиком не объявляется разобранным.

Это аналитическая записка, а не команда запускать следующие этапы. Здесь не устанавливались пакеты, не обучались модели, не вызывался Qwen и не проверялись пользовательские веб-чаты. Первичные HTTPS-источники ниже прочитаны отдельно; чужие benchmark-числа не являются измерениями AegML.

## Как понимать статусы

- **VERIFIED-source:** утверждение проверено по указанному первичному источнику. Это не локальная проверка поведения установленного пакета.
- **LOCAL-EVIDENCE:** прочитана конкретная локальная квитанция и сопоставлены её SHA. Приёмка ограничена компонентой.
- **REPORTED-local:** результат сообщил ответственный агент/root; в этой записке соответствующий raw-result не перепроверен.
- **PROPOSAL / NOT_RUN:** будущая гипотеза и условия проверки; **UNKNOWN:** данных пока недостаточно.

## Пять точных утверждений, перепроверенных по первоисточникам

| ID | Проверенный факт и версия источника | Следствие для будущего адаптера; что не подтверждено |
| --- | --- | --- |
| C1-CAT-01 | В CatBoost `v1.2.8` автоматический learning rate для Logit/MultiClass/RMSE зависит от iterations, если не заданы leaf_estimation_iterations, leaf_estimation_method и l2_leaf_reg; иначе указан default 0.03. [Tagged parameters](https://raw.githubusercontent.com/catboost/catboost/v1.2.8/catboost/docs/en/references/training-parameters/common.md), раздел learning_rate. **VERIFIED-source**. | До freeze сохранить фактически разрешённый learning rate и число деревьев. Перенос iterations при сохранении default-параметров не доказывает идентичность рецепта. Локальный fit/refit этого адаптера **NOT_RUN**. |
| C1-AG-01 | API AutoGluon Tabular `1.3.1` предупреждает: итоговая модель может обучаться и на tuning_data; при bagging/stacking это особенно существенно. time_limit описан как приблизительный. [Versioned fit API](https://auto.gluon.ai/1.3.1/api/autogluon.tabular.TabularPredictor.fit.html). **VERIFIED-source**. | Во время поиска передавать фреймворку только T_fit; его собственный tuning/CV также ограничить T_fit. y_inner не становится разрешённым из-за имени tuning_data. Нужны внешний deadline и проверка фактических дополнительных стадий. |
| C1-FLAML-01 | В FLAML `v2.3.6` defaults включают n_jobs=-1, auto_augment=True, retrain_full=True. Формула `_state.retrain_final` содержит отдельные условия CV/max_iter и max_iter==1. [Tagged automl.py](https://raw.githubusercontent.com/microsoft/FLAML/v2.3.6/flaml/automl/automl.py), настройки и retrain_final. **VERIFIED-source**. | Явно задать CPU, estimator list, augmentation и оценивание. Один retrain_full=False не доказывает отсутствие всех внутренних retrain. До использования нужны spy/trace-проверки реальных fit scopes и затрат; интеграция **NOT_RUN**. |
| C1-LAMA-01 | Точный тег LightAutoML — `v.0.4.2`. Ограничения отсутствия memory management и text support указаны для **TabularAutoML**, а не для всей библиотеки. Есть явный TabICL-маршрут; автоматическое добавление в просмотренном блоке закомментировано. [Tagged tabular_presets.py](https://raw.githubusercontent.com/sb-ai-lab/LightAutoML/v.0.4.2/lightautoml/automl/presets/tabular_presets.py). **VERIFIED-source**. | Не распространять свойства одного preset на все API. Для будущего сравнения выбирать разрешённые алгоритмы явно; CPU/memory_limit не считать OS-границей. Происхождение весов и runtime TabICL здесь **UNKNOWN**, поэтому он не входит в P0-рецепт. |
| C1-CSV-01 | Python документация ветки `3.12` описывает атомарность успешного os.replace и возможный отказ между разными файловыми системами. [os.replace](https://docs.python.org/3.12/library/os.html#os.replace). При чтении страница уже обозначена 3.12.15, это не отдельная квитанция Python 3.12.3. **VERIFIED-source**. | Временный файл — рядом с итоговым, независимая проверка до replace. Проверка CSV, fsync и долговечность после сбоя питания — самостоятельные свойства. Одного rename недостаточно для PASS writer. |

Эти ссылки привязаны к тэгам или версиям документации, но commit SHA и SHA скачанных wheels ими не устанавливаются. Соответствие полного официального контейнера всем 37 pins остаётся отдельной проверкой.

## Что из предложений H03 уже имеет относящееся доказательство

| Предложение досье | Текущее доказательство и граница | Что ещё не закрыто |
| --- | --- | --- |
| Разделить полный структурный проход и разрешённые статистики | **LOCAL-EVIDENCE:** H03.1, [attempt2](../runs/h03/h031-20261021-attempt2/profile-result.json), 17 методов / 49 сценариев; profile SHA `14d741e3…cb486`. Полные public train 43,416,931 и 16,567,584 байт; target/feature stats только explicit fit. | Это исторический снимок до последующего review. Общая H03.3→ProfileScope интеграция и новые замечания чата2 этим PASS не закрываются. |
| Изменение protected X/y не меняет research/prompt | **LOCAL-EVIDENCE:** H03.1 содержит regression/classification poison и wide UTF‑8 poison; source SHA меняется, schema SHA и исследовательские данные сохраняются. ID не выдаются как raw values. | Проверка selector/seed/controller в полном исследовательском цикле **NOT_RUN**. Raw provenance нельзя автоматически включать в будущий prompt. |
| Bounded frequencies и отдельно bounded summary | **LOCAL-EVIDENCE:** H03.1 проверяет лимиты категорий/символов, partial frequency flags, unknown unseen, 4096 колонок, независимые UTF‑8 caps report/prompt и overflow. | Полевая, физическая и **логическая** CSV-запись — разные пределы. Нельзя объявлять конкретный logical-record guard выполненным только по общему malformed-CSV тесту; относящееся исправление/recheck учитываются отдельно. |
| Train-only numeric/category/text pipeline | **LOCAL-EVIDENCE:** [H03.2 attempt2](../runs/h03/h032-20261021-attempt2.json), 12 методов / 19 сценариев и два public набора; module SHA `8d7f0f5c…2636a`. Проверены empty-only missing, NA/null как литералы, numeric invalid/nonfinite/overflow, unknown categories, несколько text-полей и пустой словарь. | Classifier использовал честно обозначенную row-modulo техническую маску, не итоговую H03.3 стратификацию. Связь DataFrame с файлом утверждает trusted loader; полный loader integration ещё требуется. |
| Нет dense-конвертации всей sparse таблицы; состояние transform постоянно | **LOCAL-EVIDENCE:** H03.2 выдаёт CSR, сохраняет строки, состояние encoder/vectorizer до/после transform совпадает. | TF‑IDF transform сначала выделяет библиотечную sparse-матрицу, затем проверяет cap: это не доказательство предела peak temporary RAM. Общий runtime deadline и H05 OS-limit **NOT_RUN**. |
| Независимые метрики и nested split | **REPORTED-local:** ответственный H03.3 сообщил 22 метода / 64 сценария + два public inputs; validation SHA `3d6200cd…34cbd5`; reg 1–3/4/5, class fit/inner/outer 56108/14028/17534. | Raw-result этого запуска в рамках записки не перечитывался. Это не качество модели и не завершённый end-to-end цикл. H03.5 registry принимается только по своей итоговой квитанции. |
| Атомарный writer, raw-ID и test-order predictions | **REPORTED-local:** root сообщил H03.4 after 14 методов / 59 сценариев + два actual writer fixtures и before-воспроизведение SUMMARY/CLASSORDER findings. | Прогнозы fixture — синтетические константы, не baseline. Fault injection H05, OS-worker snapshot channel и официальный submit **NOT_RUN**. |

Отдельный ранее существовавший submission.csv не означает выпуск нового результата. Компонентные проверки также не снимают все 74 основных и 17 частично пересекающихся будущих сценариев общей матрицы.

## H04: гипотезы, которые стоит проверять после отдельной команды

Здесь все строки имеют статус **PROPOSAL / NOT_RUN**. Сначала пройти рабочий mean/majority → одна модель по признакам → inner metric → ранний валидный test CSV. Feature profiling и fit preprocessing не являются fit estimator.

| ID | Гипотеза | Условия и критерий проверки |
| --- | --- | --- |
| C1-H04-01 | Небольшой портфель CPU-рецептов CAT/LGB/XGB полезнее одного семейства | Только разрешённые версии/данные, одинаковый полный wallclock, один evaluator и фиксированный split; учитывать все неудачи, refit и predict. Нужен прирост готового результата, а не числа trials. Предложенные в досье 1800 секунд — будущий пилот, не установленный бюджет проекта. |
| C1-H04-02 | Native categories дают пользу относительно OHE | Менять кодирование отдельно либо честно сравнивать весь рецепт; сохранять одинаковую карту категорий между fit/predict. XGBoost `2.1.4` нельзя снабжать обещаниями auto-recoding из более новых версий. [Tagged categorical guide](https://raw.githubusercontent.com/dmlc/xgboost/v2.1.4/doc/tutorials/categorical.rst), claim досье здесь отдельно не перепроверен. |
| C1-H04-03 | TF‑IDF с линейным estimator полезен на свободном тексте | Словарь/IDF только T_fit, sparse путь, лимиты токенизации/nnz и явное усечение; сравнивать качество с рецептом без текста. Ни преимуществ, ни коэффициентов модели ещё не измерено. |
| C1-H04-04 | Умеренные class weights или правило решения улучшают Macro F1 | Веса/OOF-правило получать внутри T_fit, один компонент за сравнение; primary labels=None, fixed10 отдельно. Не подбирать offsets на y_inner, не заменять F1 accuracy. [sklearn 1.5 F1](https://scikit-learn.org/1.5/modules/generated/sklearn.metrics.f1_score.html) — первичная ссылка досье; повторной проверки этой страницы здесь не было. |
| C1-H04-05 | Log/robust target, capped blend до двух моделей дают дополнительный выигрыш | Оценка original-scale RMSE; domain/inverse и bias correction только train-side. Blend включает стоимость всех моделей, stacking требует корректного OOF, для времени — past-only. Отрицательный результат сохраняется. |
| C1-H04-06 | Один AutoML-компаратор полезен для абляции AutoResearch | Выбрать один framework после проверки доступности разрешённого env; передавать только T_fit и отключать запрещённые pretrained/внешние маршруты явным allowlist. Автоматические стадии/ресурсы проверять по C1-AG/FLAML/LAMA. Обычный AutoML не сводится к одному HPO. |

Freeze включает код, алгоритм preprocessing, гиперпараметры, resolved learning rate/iterations, ансамбль и правило решения. Primary refit заново обучает **состояния того же рецепта** на development 1–4 после freeze, без новых правок/feedback; outer5 остаётся закрыт. Финальный fit1–5→test6 — другая фаза, а не повторная независимая оценка outer. `best-inner` и готовый к публикации `best-ready` нужны как разные записи.

## H05: admission вместо обещания sandbox

Все нижеперечисленные проверки **NOT_RUN в полном worker-контуре**. Локальные H02.4 Docker canaries не доказывают nested Docker, разделение supervisor/evaluator/worker или доступность ABI платформы. Первичные ссылки досье: [cgroup v2, docs 6.12](https://docs.kernel.org/6.12/admin-guide/cgroup-v2.html), [seccomp 6.12](https://docs.kernel.org/6.12/userspace-api/seccomp_filter.html), [Landlock 6.12](https://docs.kernel.org/6.12/userspace-api/landlock.html), [Yama 6.12](https://docs.kernel.org/6.12/admin-guide/LSM/Yama.html). Эти страницы в текущем intake повторно не проверялись; версия документации не означает версию установленного ядра.

1. H05.1: dummy-секреты, protected paths/labels, parent proc, env/FD и чистое состояние нового interpreter; положительный разрешённый контроль обязателен. Same-UID и mode0700 сами по себе не разделяют стороны.
2. H05.2: потомки с fork/spawn/setsid, общий deadline, CPU/RAM/swap/disk и потоково ограниченные логи; завершение одной process group недостаточно для доказательства отсутствия всего дерева.
3. H05.3: падение, диск, обрыв записи и поздний API fault сохраняют последний валидный результат; unknown/in-flight не превращается в completed.
4. H05.4: evaluator принимает собственный bounded data-only snapshot, проверяет rows/classes/SHA; не импортирует worker .py и не unpickle/joblib output.

Если нужная граница отсутствует, generated code остаётся выключен. Доверенные recipes и typed actions можно исследовать отдельно, но они не доказывают выполнение требования генерации нового кода. Даже закрытые y не исключают transductive fit по validation X: phase-разделение должно охватывать preprocessing.

## H06: offline протокол прежде live endpoint

Всё ниже — **PROPOSAL / NOT_RUN полного H06**. API-вызовов в этом intake — 0; наличие конфигурации не является capability PASS. Отдельная команда владельца остаётся обязательной для live Qwen.

Досье ссылается на SDK `openai==1.68.2` ([constants](https://github.com/openai/openai-python/blob/v1.68.2/src/openai/_constants.py), [client](https://github.com/openai/openai-python/blob/v1.68.2/src/openai/_base_client.py)), HTTPX `0.28.1` ([client](https://raw.githubusercontent.com/encode/httpx/0.28.1/httpx/_client.py)) и [Qwen function calling](https://qwen.readthedocs.io/en/latest/framework/function_call.html). Claims о defaults 600s/two retries/follow_redirects/trust_env здесь **REPORTED-source**, эти три исходника повторно не проверялись. До реализации транспорта проверить точные defaults и явно настроить их; SDK — интерфейс выданного Qwen, не разрешение другого провайдера.

| Будущий тест | Условие принятия |
| --- | --- |
| Неизвестный tool, тип/extra fields, duplicate JSON keys, NaN, partial stream | Никакого side effect; схема/размер/глубина проверены до выполнения. |
| Один call ID с другими args; тот же experiment с новым ID | Конфликт либо чтение существующего результата; повторный fit без явного намерения не запускается. Dedupe key связывает code/recipe/source/split/fidelity/seed/repeat. |
| 429/5xx/auth/timeout, потерянный ответ | Один владелец retry, исходный deadline, сверка живого job и журнала; unknown не равен «не запускался». |
| Tool output просит сменить endpoint/evaluator | Наблюдение остаётся данными и не расширяет полномочия. Endpoint/секреты принадлежат trusted controller. |
| Большой ответ/контекст | Ограничение bytes до полного накопления; символы не выдаются за точные tokens; сводка сохраняет provenance результатов. |
| Native tools либо structured adapter | Явная версия транспорта; действие → настоящий безопасный tool → результат → использование результата LLM. Plain OK и replay не закрывают live capability. |

Фактический контекст, tokenizer, tool schema/continuation restrictions и auth/tools конкретного endpoint остаются **UNKNOWN до относящегося live-запуска**. При отказе LLM валидный baseline может сохраниться, но full AutoResearch не получает PASS по этому факту.

## Что пока не переносить из досье в выводы о проекте

Прочитанное начало H07 перечисляет AIDE, MLAgentBench, MLGym, AutoML-Agent, RD-Agent, ResearchAgent, SELA, MLE-STAR и AIRA. Это источники идей parent/child, draft/debug/improve и независимой оценки, а не доказательство преимущества нашей Qwen/CPU/3h-конфигурации. Указанные в чате success/medal rates, лицензии и настройки GPU-бенчмарков здесь повторно не верифицировались. Продолжение H07 с отрицательными результатами и H08 ещё ожидается; обещанные там числа не считаются прочитанным доказательством.

Дальнейшие решения: завершить относящиеся H03 исправления и интеграцию по собственным квитанциям; при разрешённом H04 сравнить простые CPU-рецепты; H05/H06 принимать отдельно. Исследовательская рекомендация не меняет статусы WORK_BLOCKS, не обучает модель и не даёт оснований обещать первое место или private-score.
