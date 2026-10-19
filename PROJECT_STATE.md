# Состояние AegML — 19.10.2026

Цель: опубликовать малую проверяемую основу в osirust/AegMLAI-agent и план для четырёх участников. Это отдельный проект; состояние и пауза AEGYX не меняются.

Подтверждено: выбран трек «AI-агент для разработки ML-моделей», четыре участника по скриншоту регистрации. Изначально в репозитории только README, commit 081bf27. Полного ТЗ и данных нет.

Реализовано: CLI, CSV профиль, mock/совместимый Chat Completions провайдер, строгий JSON план, отдельные run directories, SHA входов/исходников/артефактов, журнал событий, документация и четыре рабочих потока. Core только stdlib. Реального обучения, скачивания весов и выполнения сгенерированного кода нет.

Проверено на Windows / Python 3.12.14 в отдельной .venv: editable install; 21 unittest PASS (8.029s); CLI с CSV и console entrypoint без CSV — exit0. HTTP body/header/path, timeout, redirect, bad JSON, response limit и ошибки проверены локальными тестовыми HTTPServer. В тестах подтверждены хеши исходных байтов, отсутствие ключа/значений строк CSV в артефактах, неизменность прошлого запуска. Это не проверка настоящей LLM. Git diff --check без ошибок. Независимое ревью выполнено.

Исправления этой версии:
- CORE-REV-001 — CLOSED. Факт: task_type=[] вызывал TypeError и traceback. Действие: проверять str перед membership. Условие закрытия: list/dict/null/bool через CLI дают exit1 без traceback. Новый результат: test_cli_machine_readable_success_and_nonzero_error PASS.
- CORE-REV-002 — CLOSED. Факт: вложенный JSON 20 KiB вызывал RecursionError в task/plan/API-envelope. Действие: преобразовать ошибку декодирования в штатный отказ. Условие закрытия: плохой task даёт exit1, плохой plan сохраняет failed run, плохой envelope даёт ProviderError. Новый результат: относящиеся deep JSON и failed-run тесты PASS в общем прогоне21/21.

Публикация: выполнена через локальный Git в main, commit 8f1245fc61ce6ab81e4200e3f9bbab51e6400531 (push exit0, 081bf27..8f1245f). Отдельное обновление README/этого состояния содержит только документацию; код и тесты этого commit не меняются.

Удалённый CI: https://github.com/osirust/AegMLAI-agent/actions/runs/39179505198 — completed/success для exact source commit 8f1245f. Все три job test(3.11), test(3.12), test(3.13): установка, unittest21/21 и демонстрационный CLI — success. Результаты проверены по GitHub Actions run и job/step metadata. Это подтверждает запуск на Ubuntu с указанными версиями Python, а не работу настоящей LLM.

Ограничения: нет полного ТЗ, данных, метрики, правил API/обучения и сведений о GPU. CSV сейчас только UTF-8/comma до20MiB, профиль не проверяет ML-утечки или семантику данных. Реальные API/Ollama/vLLM не проверены; удалённая генерация не детерминирована. Открытые вопросы CASE-001..003 в docs/CASE_INTAKE.md сохраняются.

Текущая цель основы выполнена. Ближайший шаг: получить официальное ТЗ и заполнить docs/CASE_INTAKE.md, затем выбрать baseline и модель по требованиям. Обучение и следующий этап — по новой команде владельца. AEGYX остаётся на прежней паузе, его файлы и процессы не менялись.
