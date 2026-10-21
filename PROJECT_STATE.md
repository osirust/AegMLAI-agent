# Состояние AegML — H04 принят в своей области

**Текущий итог:** H04.1–H04.4 завершены для фиксированных CPU baseline, inner-диагностики и локальной воспроизводимости. Подробная приёмка — [H04_RECEIPT](docs/H04_RECEIPT.md). Это ещё не полный Qwen/AutoResearch-агент.

**Проверено:** artifacts 20 методов / 78 сценариев; estimator 13 / 48; training data 17 / 31; общая цепочка 14 / 27. Эти наборы пересекаются и не складываются в число независимых измерений качества. Две реальные задачи повторены на исправленном замороженном коде в WSL и Docker с вложенными входными путями; inner-метрики независимо пересчитаны sklearn, прогнозы совпали, удаление двух контейнеров подтверждено.

**Качество:** RMSE mean 58.460386 → CatBoost 47.303244; Macro F1 majority 0.0484115 → CatBoost 0.50464385. Полные валидные CSV — 22449 и 41166 строк. Общий рецепт: CPU, 300 деревьев, seed 42, 8 threads. Это T_fit → inner, без frozen refit и оценки outer. Официальный baseline/score неизвестен; больше20 и одинаковое public/private качество не подтверждены.

**Исправления:** четыре замечания внешнего review воспроизведены, исправлены и закрыты полным повторным статическим ответом чата «2»: fit-matrix binding, temporal resolution, published-CSV progress, artifact commit registry. [Результат](docs/H04_STATIC_REVIEW_RESULT.json). Remaining blockers этого review — 0. Исходные before/FAIL и первые 13 JSON сохранены рядом с новыми V2; старый PASS не перенесён автоматически.

**Что дальше:** H05.1 — фактическая OS-граница worker, затем остальные H05/H06 с собственными приёмками. Владелец разрешил этот маршрут; ориентир 21.10.2026 18:00 МСК остаётся ручным, без автоматической отправки ZIP.

**Подготовка будущих этапов:** H05 observer WSL/Docker получил ABI7 и безопасный seccomp-контроль; Docker unshare вернул EPERM. Это PREPARATION_ONLY, не допуск generated code. H06 scratch 16 / 70 проверяет только offline-протокол; HTTP/SDK/live 0, код ещё не production. Чат «1» исследует read-only worker; ответ ожидается. Не исполнять generated code до H05 admission.

**API:** фактических конкурсных вызовов 0, включая /key/info. На H04 API запрещён. Условный будущий live H06.2 допустим лишь после готовности исполнения H05 и offline/mock H06; сейчас эти предпосылки не приняты. Ключ не печатать, не передавать веб-чатам, не включать в Git/ZIP.

**Ограничения:** официальный образ/full37, полный 10800s, private-задачи, outer-quality, frozen refit и AutoResearch не проверены. Полная матрица 74+17 остаётся отдельной будущей приёмкой. Среду/caps не меняли. AEGYX INDEX81 OWNER_PAUSE_BEFORE_SOURCE3 сохранён; default Ubuntu не запускать.

Читать при продолжении: этот файл → [NEXT_SESSION](docs/NEXT_SESSION.md) → основной раздел9 [ТЗ](docs/TECHNICAL_SPEC.md) → нужный подпункт [WORK_BLOCKS](docs/WORK_BLOCKS.md). История H03 — [H03_RECEIPT](docs/H03_RECEIPT.md).

Публикационная сверка H04: [H04_PUBLICATION_RESULT](docs/H04_PUBLICATION_RESULT.json), 5884 metadata-проверок; это не дополнительные ML-тесты. Старые квитанции и исходные данные сохранены. Локальная проверка ключа — [H04_SECRET_SCAN_RESULT](docs/H04_SECRET_SCAN_RESULT.json), API0.
