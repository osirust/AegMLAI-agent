# Следующее продолжение AegML

Текущая задача — исправление диагностической mini по замечанию владельца M00-API-002. **Strict v3 локально проверена, на платформу не отправлена.** Читать PROJECT_STATE, TESTMINI_PLAN, TESTMINI_STRICT_RESULT и последнюю команду.

Старый testmini.zip/v2 владелец показал в истории платформы: score0,17:14,«Лучшее решение»,10.3сек в колонке«Длительность загрузки». Это не доказанное время агента, exit0 или API-success. ПрисланныйZIP совпадает с нашейv2 и содержит толькоsolution.py. Логи/CSV/APIответа в нём нет. Полная запись — PLATFORM_OBSERVATION_20261020.json. Числа B_RMSE50/B_F1.60 на другом скриншоте — условныйпример, не подтверждённые официальныеB.

Новый dist/testmini_strict_api.zip: API обязателен по умолчанию ДО CSV. missing/partial/HTTP/invalid response приводят к exit1+failed_api_gate без новогоCSV; старыйCSV сохранён. code0 в режиме required возможен только после api_probe.success и валидногоCSV. Явный TESTMINI_API_MODE=off — только локальный file-only/API_NOT_CHECKED. HTTPstub подтверждает реализацию, не живойQwen. M00-API-002 закрыт только этим scope; платформа может иначе трактовать exitcode, это UNKNOWN.

Ближайший шаг — передать владельцу новыйZIP; не тратить вторуюпопытку автоматически. При доступности получить platform stdout/stderr/mini_diagnostics.json либо ответ организаторов о статусах. API_WAIT сохраняется, ключ/endpoint/modelID не проверены. После мини по решению владельца продолжаем ТЗ: backend/WSL24/Docker20/8CPU как ПЛАН и устранениеSPEC-DOC-003; H01.1 и остальныеблоки не запускать автоматически.

Прежние source SHA, closedCORE-REV-001/002 и SPEC-DOC-001/002, miniM00-API-001 сохраняются. OPEN SPEC-BASE-001..006/SPEC-ADAPT-001..003/SPEC-DATA-001/SPEC-DOC-003. Все49 основных сценариев NOT_RUN; полноценногоML/AutoResearch пока нет. Старые21PASS не повторять без причины.

Среда прежняя: AegML-Hackathon наE:, useraegml, venv/home/aegml/venvs/aegml-py312 Python3.12.3, безML-пакетов/Docker; около15.18GiB/12CPU. .wslconfig/Ubuntu-default/AEGYX не менять. Платформа8CPU/32GB/3часа на отдельнуюзадачу, один неизменныйкод наprivate; бюджет600₽ не считать, сырые данные/ключи не публиковать. Команда делает независимыеверсии, никомуне писатьавтоматически.
