# Пакет для чата «2»: исправления H02.3/H02.4

Статус: СОХРАНЁН, НЕ ОТПРАВЛЕН. Владелец остановил веб-обращения после429 до продолжения. H03.1 пока НЕ выполнять; ниже только проверенные исправления предыдущих этапов. API запрещён до отдельной команды владельца. Никаких секретов или raw CSV в пакете нет.

Ты — независимый технический наставник. Предыдущие полные review0e7bed48… и0d95a297… прочитаны до изменений. Проверь только исправления пяти findings и границы утверждений. Отделяй статическое заключение от наших локальных результатов; байты/SHA без своих вычислений не называй независимо воспроизведёнными. Не управляй компьютером и другими чатами, не запускай API/код. Настройки модели выбирает владелец; не утверждай, что видишь их.

1. Закрывает ли структурный разбор TYPEINTRO показанные mixed/unknown heading и ложный конфликт из обсуждения метода? Сохранилось ли различие absent vs invalid? Не требуй универсальногоNLP: ограниченные recognized EN/RU forms.
2. ПроверщикCLI должен сохранять чужой container приcollision, различать daemonerror/absence, не выдаватьPASS приcleanupunknown, одинаково проверять normal/-O, сохранять existing/race receipt, отклонять frozenROOT drift. Есть ли относящийся обход в текущем патче?
3. Проверь, что фактические2Docker exit3/contracttrue не объявлены новымCSV/ML/Qwen/fullH05. Послеcapture ограничение логов относится к доверенномукороткомуCLI; adversarialstreaming ещёNOT_RUN.
4. Напиши конечный список подтверждённых remaining blockers с минимальным контрпримером и ожидаемым исходом; отличи их от P1предложений. Не добавляй новые независимые задачи H03 и не принимай будущие этапы.

Ограничение provenance: actualDockerJSON не записывает собственный checker_sha256; связь с946f940f… опирается на recorded frozen handoff до запуска, mock receipt и неизменность файла. Не выдавай это за самодостаточное поле JSON. Исходный DockerJSON сохранён без исправления задним числом.

## Карта результата

# Исправления полных review H02.3/H02.4

Статус: **PASS_H02_REVIEW_REPAIRS_ONLY**. Полные ответы чата2 получены до начала исправлений: Docker `0e7bed48-d75a-4f35-a861-0c0c4cba86bf` (13036 символов), H02.3 `0d95a297-2b29-4049-bd33-8964c31f9af1` (14899 символов). Рецензент читал код; перечисленные ниже прогоны выполнены локально в WSL Python 3.12.3, а не им. Исходная точка — commit `187328f2f382ce2a994a507b715cb97416557102`. Оригинальные квитанции предыдущих этапов сохранены.

| Finding | Изменение и относящееся доказательство |
| --- | --- |
| H023-TYPEINTRO-001 | Структурные EN/RU объявления, в том числе Markdown heading/list, разбираются целиком. Свободное обсуждение методов не определяет тип. Отсутствующее объявление допускает metric-domain fallback; неподдержанное объявление отклоняется. На старом SHA151d… адресный набор воспроизвёл 11 ожидаемых сбоев и четыре успешных контроля в 15 подслучаях; на новом SHA b33bb466… все 43 метода / 108 сценариев / 6 CLI прошли, включая оба actual public inputs. |
| H024-CLI-OWN-001 | UUID owner label и подтверждённый полный container ID; чужой контейнер не удаляется. Отсутствие отличено от ошибки daemon; неизвестный cleanup запрещает PASS. Mock проверяет коллизию/ошибку/отсутствие, actual Docker подтвердил отсутствие обоих своих контейнеров после запуска. |
| H024-CLI-ASSERT-001 | Обязательные критерии используют explicit require; AST assert=0. Неверный exit/флаги отвергаются в normal и -O; положительные контроли проходят. |
| H024-CLI-RECEIPT-001 | Exclusive open до Docker, fd удерживается до записи. Существующая квитанция и гонка создания сохраняют sentinel и не запускают Docker. |
| H024-CLI-SOURCE-001 | Выбран frozen-root-and-identical-staging контракт. Контролируемый root drift даёт FAIL; неизменный контроль PASS. В двух actual Docker runs root_source_changed=false. |
| WEB-REVIEW-ORDER-001 | Получены оба полных итоговых ответа, сохранены snapshots и составлена эта карта; только затем внесены исправления. Причина прежнего отсутствия ответа не объявлена доказанной отменой. |

Доказательства:

- [TYPEINTRO before](../docs/H02_REPAIR_TYPEINTRO_BEFORE_RESULT.json): изолированный старый snapshot, без изменения проекта; ожидаемые ошибки сохранены.
- [TaskContract after](../docs/H02_REPAIR_CONTRACT_RESULT.json): 43/108/6, роли/метрики/порядок и public mappings сохранены; ограниченная EN/RU грамматика, без произвольного NLP.
- [Bootstrap](../docs/H02_REPAIR_BOOTSTRAP_RESULT.json): 24/51/37, один общий кооперативный RunBudget.
- [CLI mock](../docs/H02_REPAIR_CLI_REGRESSIONS_RESULT.json): 11 методов / 17 сценариев, 17 subprocess invocations проверщика, 75 fake Docker actions; реальных Docker/API/fit в этом наборе нет. Пять сценариев воспроизводят старые дефекты, остальные проверяют исправления.
- [Actual Docker CLI](../docs/H02_REPAIR_DOCKER_CLI_RESULT.json): два публичных набора, literal `python3 solution.py task.md`, неизменные входы и прежний CSV, exit3/contract_valid=true. Нового CSV нет; API/tools/research/submission=false, experiments=0. Cleanup verified, unresolved resources=[]; checker SHA946f940f… .

Подтверждённые findings закрыты только в этих областях. Это не полный H05, не официальный образ/full37 и не 10800-секундный прогон. После capture лог ограничен для доверенного короткого CLI; streaming bounded log будущего generated worker ещё не проверен. H024-OOM-ATTR-001 ранее закрыт отдельными квитанциями и не пересчитывается этим набором. Основные 74+17 сценариев остаются NOT_RUN. Обучение, Qwen API и официальный score не измерялись.

Последнее уточнение владельца: H03.1 пока не выполнять, завершить всё до него. Обсуждение API профиля остановлено, H03.1-код и проверки не выполнялись. Исследования будущих этапов разрешены отдельно и не меняют NOT_RUN.

## Текущие SHA

```json
{
  "aegml_contracts.py": "b33bb466b3ab11911e514dfea20530bbeec179bb9777a45ef3a67c9eeb5314d3",
  "scripts/check_h023_contract.py": "a00c8c36be3da323acc6f00bfc583efcaf930b15af257004f0d56128c8df333c",
  "scripts/check_h024_platform_cli.py": "946f940febd24f313871835f8e927f27f5c2f1c09162ba6fbb84832984c79e5b",
  "scripts/check_h024_cli_regressions.py": "a6d8ba7530a178230d7d57e725a99c4e9fabef5d6800a519df741be8cbd7b0a6"
}
```

## Патч к187328f

```diff
diff --git a/aegml_contracts.py b/aegml_contracts.py
index 340b7e7..14b7f63 100644
--- a/aegml_contracts.py
+++ b/aegml_contracts.py
@@ -415,20 +415,24 @@ def _metric_declarations(text, dictionary_rows):


 def _type_declarations(text, expected):
-    explicit = _directive(text, r"task\s*type|problem\s*type|тип\s+задачи")
-    lines = explicit or [(re.split(r"\n\s*##\s*(?:Данные|Data)\b", text, maxsplit=1, flags=re.I)[0], None)]
+    """Read complete type declarations, never keywords from arbitrary prose.
+
+    H023-TYPEINTRO-001: Markdown decoration cannot hide a declaration, and a
+    found-but-invalid declaration cannot fall back to the metric's domain.
+    Free discussion of models or feature engineering is not a declaration.
+    """
     types, evidence = set(), []
+    aliases = {
+        "regression": (r"(?:(?:a|an|supervised|tabular)\s+)?regression(?:\s+(?:task|problem))?|"
+                       r"регрессия|регрессионная\s+задача|задача\s+регрессии"),
+        "classification": (r"(?:(?:a|an|supervised|tabular)\s+)?(?:binary\s+|multi[ -]?class\s+)?"
+                           r"classification(?:\s+(?:task|problem))?|binary|multiclass|"
+                           r"(?:бинарная\s+|многоклассовая\s+)?классификация|"
+                           r"задача\s+(?:бинарной\s+|многоклассовой\s+)?классификации"),
+    }

     def parse_explicit(value):
         clean = value.replace("**", "").replace("`", "").strip().strip(".:; ")
-        aliases = {
-            "regression": (r"(?:(?:a|an|supervised|tabular)\s+)?regression(?:\s+(?:task|problem))?|"
-                           r"регрессия|регрессионная\s+задача|задача\s+регрессии"),
-            "classification": (r"(?:(?:a|an|supervised|tabular)\s+)?(?:binary\s+|multi[ -]?class\s+)?"
-                               r"classification(?:\s+(?:task|problem))?|binary|multiclass|"
-                               r"(?:бинарная\s+|многоклассовая\s+)?классификация|"
-                               r"задача\s+(?:бинарной\s+|многоклассовой\s+)?классификации"),
-        }

         def alias(token):
             names = {name for name, expression in aliases.items()
@@ -449,24 +453,76 @@ def _type_declarations(text, expected):
             return selected
         return alias(clean)

-    for value, number in lines:
-        if explicit:
-            types.add(parse_explicit(value))
+    type_key = r"(?:task\s*type|problem\s*type|тип\s+задачи)"
+    declaration = re.compile(r"^" + type_key + r"\s*[:=]\s*(.*?)\s*$", re.I)
+    declaration_start = re.compile(r"^" + type_key + r"\b", re.I)
+    bare_heading = re.compile(
+        r"regression|регрессия|classification|классификация|"
+        r"(?:binary|multi[ -]?class)\s+classification|"
+        r"(?:бинарная|многоклассовая)\s+классификация", re.I)
+    statements = (
+        r"this\s+is\s+(.+?\s+(?:task|problem))[.!]?",
+        r"это\s+(задача\s+.+?)[.!]?",
+        r"это\s+(.+?\s+задача)[.!]?",
+    )
+    intro = True
+    fence = None
+    for number, raw in enumerate(text.splitlines(), 1):
+        plain = raw.strip()
+        marker = re.match(r"^(`{3,}|~{3,})", plain)
+        if marker:
+            token = marker.group(1)
+            if fence is None:
+                fence = token
+            elif token[0] == fence[0] and len(token) >= len(fence):
+                fence = None
+            continue
+        if fence is not None or plain.startswith(">"):
+            continue
+
+        # At most one list marker and one ATX heading decorate the statement.
+        # Both list->heading and heading->list forms preserve its source line.
+        heading = False
+        for _ in range(2):
+            atx = re.match(r"^(#{1,6})(?!#)[ \t]*(.*)$", plain)
+            listed = re.match(r"^(?:[-*+]|[0-9]+[.)])[ \t]+(.*)$", plain)
+            if atx and not heading:
+                heading = True
+                plain = atx.group(2).strip()
+            elif listed:
+                plain = listed.group(1).strip()
+            else:
+                break
+        if heading:
+            plain = re.sub(r"[ \t]+#+[ \t]*$", "", plain)
+        plain = plain.replace("**", "").replace("`", "").strip()
+        if heading and re.match(r"^(?:Данные|Data)\b", plain, re.I):
+            intro = False
+
+        if declaration_start.match(plain):
+            match = declaration.fullmatch(plain)
+            if match is None:
+                raise ContractError("unsupported_task_type")
+            types.add(parse_explicit(match.group(1)))
             evidence.append(_evidence("task", "task_type", number))
             continue
-        local_types = set()
-        clean = re.sub(r"(?:not|не)\s+(?:a\s+)?(?:regression|classification|регресс\w*|классифика\w*)", "", value, flags=re.I)
-        if re.search(r"regress|регресс", clean, re.I):
-            local_types.add("regression")
-        if re.search(r"classif|классифика|\bmulticlass\b|\bbinary\b", clean, re.I):
-            local_types.add("classification")
-        types.update(local_types)
-        evidence.append(_evidence("task", "task_intro", number))
+        if not intro:
+            continue
+        if heading and bare_heading.fullmatch(plain.strip(".:; ")):
+            types.add(parse_explicit(plain))
+            evidence.append(_evidence("task", "task_type_heading", number))
+            continue
+        for statement in statements:
+            match = re.fullmatch(statement, plain, re.I)
+            if match:
+                types.add(parse_explicit(match.group(1)))
+                evidence.append(_evidence("task", "task_type_statement", number))
+                break
+
     if len(types) > 1 or (types and expected not in types):
         raise ContractError("task_type_conflict")
     return evidence if types else [_evidence("metric_registry", "metric_domain")]

-
 def _output_order(text):
     found = []
     explicit = _directive(text, r"output\s*order|row\s*order|порядок\s+(?:выходных\s+)?строк|порядок\s+вывода")
diff --git a/scripts/check_h023_contract.py b/scripts/check_h023_contract.py
index cb03b24..6fe9d10 100644
--- a/scripts/check_h023_contract.py
+++ b/scripts/check_h023_contract.py
@@ -298,6 +298,75 @@ class ContractChecks(unittest.TestCase):
                     self.assertEqual(payload["prediction_schema"]["output_order"], expected)
                     self.assertEqual(contract.alignment["output_to_test"], [1, 0] if expected == "sample" else [0, 1])

+    def typeintro_fixture(self, label, intro):
+        fixture = self.review_fixture("typeintro-" + label)
+        fixture.rows = {"train": [["train_a", "1", "10"]],
+                        "test": [["test_a", "2"], ["test_b", "3"]],
+                        "sample_submission": [["test_b", "0"], ["test_a", "0"]]}
+        fixture.save()
+        text = (intro + "\n\nTarget: y\nID: id\nMetric: RMSE\nOutput order: test\n\n## Data\n"
+                "- `train.csv`\n- `test.csv`\n- `data_dictionary.csv`\n- `sample_submission.csv`\n")
+        fixture.task.write_text(text, encoding="utf-8")
+        return fixture
+
+    def test_review_typeintro_rejects_complete_unknown_declarations(self):
+        variants = (("heading_mixed", "# Task type: regression + clustering"),
+                    ("heading_unknown", "# Task type: clustering"),
+                    ("russian_heading_mixed", "## Тип задачи: регрессия + кластеризация"),
+                    ("plain_mixed", "Task type: regression + clustering"))
+        for label, intro in variants:
+            with self.subTest(case=label), self.case("H023-TYPEINTRO-001_" + label):
+                fixture = self.typeintro_fixture(label, intro)
+                self.rejected(fixture, codes={"unsupported_task_type"})
+                self.assertFalse((fixture.root / ".aegml_runs").exists())
+
+    def test_review_typeintro_provenance_and_absent_declaration(self):
+        variants = (("explicit_heading", "# Task type: regression", "task_type"),
+                    ("bare_english_heading", "# Regression", "task_type_heading"),
+                    ("bare_russian_heading", "# Регрессия", "task_type_heading"),
+                    ("heading_list", "### - **Problem type:** regression", "task_type"))
+        for label, intro, rule in variants:
+            with self.subTest(case=label), self.case("H023-TYPEINTRO-001_" + label):
+                fixture = self.typeintro_fixture(label, intro)
+                contract, payload = self.build(fixture)
+                self.assertEqual(payload["task_type"], "regression")
+                evidence = payload["provenance"]["fields"]["task_type"]
+                self.assertIn({"source": "task", "rule": rule, "line": 1}, evidence)
+                self.assertEqual(contract.alignment["output_to_test"], [0, 1])
+        with self.case("H023-TYPEINTRO-001_no_declaration_uses_metric_domain"):
+            fixture = self.typeintro_fixture("no-declaration", "# Energy modelling notes")
+            _, payload = self.build(fixture)
+            self.assertEqual(payload["task_type"], "regression")
+            self.assertEqual(payload["provenance"]["fields"]["task_type"],
+                             [{"source": "metric_registry", "rule": "metric_domain"}])
+
+    def test_review_typeintro_ignores_feature_engineering_discussion(self):
+        descriptions = (("clustering", "clustering may be used to construct additional features."),
+                        ("classification", "predictions from a classification model may be used as additional features."))
+        for label, description in descriptions:
+            with self.subTest(case=label), self.case("H023-TYPEINTRO-001_discussion_" + label):
+                fixture = self.typeintro_fixture(label, "# Task type: regression\n\nFeature engineering: " + description)
+                _, payload = self.build(fixture)
+                self.assertEqual(payload["task_type"], "regression")
+                self.assertEqual(payload["provenance"]["fields"]["task_type"],
+                                 [{"source": "task", "rule": "task_type", "line": 1}])
+
+    def test_review_typeintro_conflicting_declarations_still_reject(self):
+        intros = (("two_directives", "# Task type: regression\nProblem type: classification"),
+                  ("bare_and_directive", "# Regression\nProblem type: classification"))
+        for label, intro in intros:
+            with self.subTest(case=label), self.case("H023-TYPEINTRO-001_conflict_" + label):
+                fixture = self.typeintro_fixture(label, intro + "\nFeature engineering: clustering is optional.")
+                self.rejected(fixture, codes={"task_type_conflict"})
+
+    def test_review_typeintro_cli_refuses_before_publication(self):
+        for label, intro in (("mixed", "# Task type: regression + clustering"),
+                             ("unknown", "# Task type: clustering")):
+            with self.subTest(case=label), self.case("H023-TYPEINTRO-001_cli_" + label):
+                self.fixture = self.typeintro_fixture("cli-" + label, intro)
+                self.cli(["task.md"], expected_code=2, valid=False)
+                self.assertFalse((self.fixture.root / ".aegml_runs").exists())
+
     def test_target_position_and_feature_projection(self):
         for label, order in (("nonlast", ["left", "y", "id", "right"]), ("first", ["y", "left", "id", "right"])):
             with self.subTest(case=label), self.case("target_" + label):
diff --git a/scripts/check_h024_platform_cli.py b/scripts/check_h024_platform_cli.py
index 8069b95..6e7a4c3 100644
--- a/scripts/check_h024_platform_cli.py
+++ b/scripts/check_h024_platform_cli.py
@@ -1,94 +1,319 @@
-"""Trusted local Docker launch checks; no ML, provider key, or live network."""
+"""Trusted local Docker CLI checks; frozen root, no ML/key/API/worker acceptance.
+
+Acceptance uses explicit checks even under Python -O. A fresh receipt is reserved
+exclusively before any Docker call. Each --rm container has a private cidfile and
+owner label; cleanup deletes only a verified full ID. A failed inspect alone is
+never proof that a container is absent. Capture remains for a trusted short CLI,
+not a streaming output limit for an adversarial worker.
+"""
+
 import argparse
 import hashlib
 import json
 import os
 from pathlib import Path
+import re
 import shutil
 import subprocess
+import sys
 import uuid

+
 ROOT = Path(__file__).resolve().parents[1]
 DOCKER = ['docker', '--host', 'unix:///var/run/docker.sock']
 SOURCES = ['solution.py', 'aegml_contracts.py', 'aegml_input.py', 'aegml_schemas.py', 'requirements.txt']
 INPUTS = ['task.md', 'train.csv', 'test.csv', 'data_dictionary.csv', 'sample_submission.csv']
+OWNER_LABEL = 'org.aegml.h024.cli.owner'
+MAX_OUTPUT_BYTES = 65536
+INSPECT_FORMAT = ('{"Id":{{json .Id}},"Name":{{json .Name}},'
+                  '"Owner":{{json (index .Config.Labels "' + OWNER_LABEL + '")}}}')
+
+
+class CheckError(Exception):
+    def __init__(self, code):
+        super().__init__(code)
+        self.code = code
+
+
+def require(condition, code):
+    if not condition:
+        raise CheckError(code)


 def sha(path):
-    return hashlib.sha256(path.read_bytes()).hexdigest()
+    digest = hashlib.sha256()
+    with path.open('rb') as stream:
+        for block in iter(lambda: stream.read(1 << 20), b''):
+            digest.update(block)
+    return digest.hexdigest()
+
+
+def source_hashes(root):
+    return {name: sha(root / name) for name in SOURCES}
+
+
+def strict_json(value):
+    def reject_constant(_):
+        raise ValueError('nonfinite_json')
+    return json.loads(value, parse_constant=reject_constant)
+
+
+def run_docker(arguments, *, timeout=15):
+    """Known short Docker commands only; raw error text is not put in receipts."""
+    try:
+        child = subprocess.run(DOCKER + arguments, capture_output=True, text=True,
+                               timeout=timeout, check=False)
+    except subprocess.TimeoutExpired:
+        return {'returncode': None, 'stdout': '', 'timed_out': True,
+                'capture_valid': False, 'error': 'docker_timeout'}
+    except (OSError, UnicodeError):
+        return {'returncode': None, 'stdout': '', 'timed_out': False,
+                'capture_valid': False, 'error': 'docker_call_failed'}
+    stdout = child.stdout or ''
+    stderr = child.stderr or ''
+    if not isinstance(stdout, str) or not isinstance(stderr, str):
+        return {'returncode': child.returncode, 'stdout': '', 'timed_out': False,
+                'capture_valid': False, 'error': 'invalid_docker_capture'}
+    valid = (len(stdout.encode('utf-8', errors='replace')) < MAX_OUTPUT_BYTES
+             and len(stderr.encode('utf-8', errors='replace')) < MAX_OUTPUT_BYTES)
+    return {'returncode': child.returncode, 'stdout': stdout if valid else '',
+            'timed_out': False, 'capture_valid': valid,
+            'stdout_bytes': len(stdout.encode('utf-8', errors='replace')),
+            'stderr_bytes': len(stderr.encode('utf-8', errors='replace'))}
+

+def _absence(name, container_id=None):
+    filters = ['name=^/' + name + '$']
+    if container_id:
+        filters.append('id=' + container_id)
+    observations = []
+    for selector in filters:
+        call = run_docker(['ps', '-a', '--no-trunc', '--filter', selector, '--format', '{{.ID}}'], timeout=8)
+        observations.append({'filter': selector, 'returncode': call['returncode'],
+                             'timed_out': call['timed_out']})
+        if call['returncode'] != 0 or not call['capture_valid']:
+            return False, observations, 'docker_absence_query_failed'
+        ids = call['stdout'].split()
+        if any(re.fullmatch(r'[0-9a-f]{64}', item) is None for item in ids):
+            return False, observations, 'invalid_absence_query_response'
+        if ids:
+            return False, observations, 'container_still_present'
+    return True, observations, None

-def main():
-    parser = argparse.ArgumentParser()
+
+def cleanup_container(name, owner, cidfile):
+    """Never remove by name. CID/name/owner must all agree before full-ID rm."""
+    result = {'name': name, 'container_id': None, 'status': 'cleanup_unverified', 'verified': False}
+    if re.fullmatch(r'aegml-h024-cli-[0-9a-f]{32}-[12]', name) is None:
+        result['reason'] = 'invalid_owned_container_name'
+        return result
+    container_id = None
+    try:
+        if os.path.lexists(cidfile):
+            require(not cidfile.is_symlink() and cidfile.is_file() and cidfile.stat().st_size <= 65,
+                    'invalid_cidfile')
+            candidate = cidfile.read_text(encoding='ascii').strip()
+            if candidate:
+                require(re.fullmatch(r'[0-9a-f]{64}', candidate) is not None, 'invalid_cidfile')
+                container_id = candidate
+        result['container_id'] = container_id
+        call = run_docker(['inspect', '--type', 'container', '--format', INSPECT_FORMAT,
+                           container_id or name], timeout=8)
+        result['inspect_returncode'] = call['returncode']
+        result['inspect_timed_out'] = call['timed_out']
+        if call['returncode'] != 0 or not call['capture_valid']:
+            absent, observations, reason = _absence(name, container_id)
+            result['absence_checks'] = observations
+            if absent:
+                result.update(status='verified_absent', verified=True)
+            else:
+                result['reason'] = reason
+            return result
+        info = strict_json(call['stdout'])
+        # The selected Go template returns an object; standard inspect JSON is
+        # accepted as well so callers can supply a faithful Docker API fixture.
+        if isinstance(info, list):
+            require(len(info) == 1, 'invalid_container_inspection')
+            info = info[0]
+        require(isinstance(info, dict), 'invalid_container_inspection')
+        actual_id = info.get('Id')
+        actual_name = info.get('Name')
+        actual_owner = info.get('Owner')
+        if actual_owner is None:
+            actual_owner = (info.get('Config', {}).get('Labels') or {}).get(OWNER_LABEL)
+        require(isinstance(actual_id, str) and re.fullmatch(r'[0-9a-f]{64}', actual_id) is not None,
+                'invalid_container_inspection')
+        if actual_name != '/' + name or actual_owner != owner:
+            result.update(status='foreign_preserved', reason='container_ownership_mismatch')
+            return result
+        require(container_id is None or actual_id == container_id, 'container_id_mismatch')
+        result['container_id'] = actual_id
+        removal = run_docker(['rm', '-f', actual_id], timeout=15)
+        result['remove_returncode'] = removal['returncode']
+        result['remove_timed_out'] = removal['timed_out']
+        absent, observations, reason = _absence(name, actual_id)
+        result['absence_checks'] = observations
+        if absent:
+            result.update(status='owned_removed' if removal['returncode'] == 0 else 'verified_absent_after_remove',
+                          verified=True)
+        else:
+            result['reason'] = reason
+        return result
+    except CheckError as exc:
+        result['reason'] = exc.code
+    except (OSError, UnicodeError, ValueError, TypeError, AttributeError):
+        result['reason'] = 'cleanup_inspection_unusable'
+    return result
+
+
+def run_case(folder, index, stage, image, owner, expected_sources):
+    original = ROOT / 'drive-download-20261019T181414Z-1-001' / folder
+    work = stage / folder
+    work.mkdir()
+    name = 'aegml-h024-cli-' + owner + '-' + str(index)
+    cidfile = stage / (name + '.cid')  # Outside the writable /work mount.
+    case = {'dataset': folder, 'status': 'FAIL', 'name': name,
+            'literal_container_argv': ['python3', 'solution.py', 'task.md']}
+    try:
+        originals = {item: sha(original / item) for item in INPUTS}
+        for item in INPUTS:
+            shutil.copyfile(original / item, work / item)
+        for item in SOURCES:
+            shutil.copyfile(ROOT / item, work / item)
+        require(source_hashes(work) == expected_sources, 'staged_source_drift')
+        os.chown(work, 1000, 1000)
+        for path in work.iterdir():
+            os.chown(path, 1000, 1000)
+        existing = work / 'submission.csv'
+        existing.write_text('historical_sentinel\nkeep\n', encoding='utf-8')
+        os.chown(existing, 1000, 1000)
+        old = (sha(existing), existing.stat().st_mtime_ns)
+        require(not os.path.lexists(cidfile), 'cidfile_already_exists')
+        arguments = ['run', '--name', name, '--rm', '--init', '--pull=never',
+                     '--label', OWNER_LABEL + '=' + owner, '--cidfile', str(cidfile),
+                     '--network=none', '--read-only', '--cap-drop=ALL',
+                     '--security-opt=no-new-privileges', '--user=1000:1000',
+                     '--memory=20g', '--memory-swap=20g', '--cpus=8', '--pids-limit=256',
+                     '--tmpfs=/tmp:rw,nosuid,nodev,size=64m,mode=1777',
+                     '--mount', 'type=bind,source=' + str(work) + ',target=/work',
+                     '--workdir=/work', image, 'python3', 'solution.py', 'task.md']
+        child = run_docker(arguments, timeout=45)
+        case.update(exit_code=child['returncode'], run_timed_out=child['timed_out'])
+        require(not child['timed_out'], 'docker_run_timeout')
+        require(child['capture_valid'], 'docker_output_limit_or_capture_failed')
+        require(child['returncode'] == 3, 'unexpected_container_exit')
+        outcome = strict_json(child['stdout'])
+        require(isinstance(outcome, dict), 'invalid_cli_outcome')
+        require(outcome.get('phase') == 'H02.3' and outcome.get('contract_valid') is True,
+                'contract_acceptance_missing')
+        require(outcome.get('termination_reason') == 'implementation_incomplete', 'invalid_termination_reason')
+        require(all(outcome.get(item) is False for item in
+                    ['api_verified', 'tools_verified', 'research_completed', 'submission_valid'])
+                and type(outcome.get('experiments_completed')) is int and outcome['experiments_completed'] == 0,
+                'false_full_agent_acceptance')
+        require(old == (sha(existing), existing.stat().st_mtime_ns), 'existing_csv_changed')
+        require(originals == {item: sha(original / item) for item in INPUTS}, 'original_input_changed')
+        require(originals == {item: sha(work / item) for item in INPUTS}, 'staged_input_changed')
+        require(expected_sources == source_hashes(work), 'staged_source_changed')
+        artifact_root = work / '.aegml_runs'
+        require(artifact_root.is_dir() and not artifact_root.is_symlink(), 'invalid_artifact_root')
+        artifacts = list(artifact_root.glob('*/*.json'))
+        require(len(artifacts) == 2 and {path.name for path in artifacts} ==
+                {'task_contract.json', 'row_alignment.json'}, 'invalid_artifact_count_or_names')
+        require(len({path.parent for path in artifacts}) == 1 and
+                all(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(work.resolve())
+                    for path in artifacts), 'invalid_artifact_location')
+        require({path.name: sha(path) for path in artifacts} == outcome.get('artifact_sha'), 'artifact_sha_mismatch')
+        contract_path = next(path for path in artifacts if path.name == 'task_contract.json')
+        contract = strict_json(contract_path.read_text(encoding='utf-8'))
+        require(contract['prediction_schema']['output_order'] == 'test', 'public_output_order_mismatch')
+        case.update(source_sha256_preserved=True, input_sha256_preserved=True,
+                    existing_csv_preserved=True, outcome=outcome, resolved_metric=contract['metric'],
+                    output_order='test', artifact_count=len(artifacts), status='PASS')
+    except CheckError as exc:
+        case['reason'] = exc.code
+    except KeyboardInterrupt:
+        case['reason'] = 'checker_interrupted'
+    except Exception as exc:
+        case.update(reason='cli_check_internal_error', error_type=type(exc).__name__)
+    finally:
+        try:
+            cleanup = cleanup_container(name, owner, cidfile)
+        except BaseException as exc:
+            cleanup = {'name': name, 'container_id': None, 'status': 'cleanup_unverified',
+                       'verified': False, 'reason': 'cleanup_internal_error',
+                       'error_type': type(exc).__name__}
+        if not cleanup['verified']:
+            case.update(status='FAIL', cleanup_unverified=True)
+    return case, cleanup
+
+
+def main(argv=None):
+    parser = argparse.ArgumentParser(description=__doc__)
     parser.add_argument('--image', required=True)
     parser.add_argument('--receipt', type=Path, required=True)
-    args = parser.parse_args()
-    if not args.image.startswith('sha256:'):
+    args = parser.parse_args(argv)
+    if re.fullmatch(r'sha256:[0-9a-f]{64}', args.image) is None:
         parser.error('use an immutable local image ID')
-    proof = args.receipt.resolve().parent
-    proof.mkdir(parents=True, exist_ok=True)
-    stage = proof / ('platform-cli-' + uuid.uuid4().hex)
-    stage.mkdir()
-    result = {'status': 'FAIL_H02_4_DOCKER_CLI_ONLY', 'image': args.image,
-              'source_sha256': {p: sha(ROOT/p) for p in SOURCES}, 'cases': [],
-              'model_fit_calls': 0, 'live_api_calls': 0, 'official_image_verified': False}
+    # Existing files, directories and dangling symlinks are all existing history.
+    if os.path.lexists(args.receipt):
+        parser.error('receipt already exists; select a fresh path')
+    args.receipt.parent.mkdir(parents=True, exist_ok=True)
     try:
-        for folder in ['Регрессия', 'Многоклассовая классификация']:
-            original = ROOT / 'drive-download-20261019T181414Z-1-001' / folder
-            work = stage / folder
-            work.mkdir()
-            originals = {p: sha(original/p) for p in INPUTS}
-            for name in INPUTS:
-                shutil.copyfile(original/name, work/name)
-            for name in SOURCES:
-                shutil.copyfile(ROOT/name, work/name)
-            # Task-local staging is the only writable host mount, as on platform.
-            os.chown(work, 1000, 1000)
-            for path in work.iterdir():
-                os.chown(path, 1000, 1000)
-            existing = work / 'submission.csv'
-            existing.write_text('historical_sentinel\nkeep\n')
-            os.chown(existing, 1000, 1000)
-            old = (sha(existing), existing.stat().st_mtime_ns)
-            name = 'aegml-h024-cli-' + uuid.uuid4().hex
-            command = DOCKER + ['run', '--name', name, '--rm', '--init', '--pull=never',
-                '--network=none', '--read-only', '--cap-drop=ALL',
-                '--security-opt=no-new-privileges', '--user=1000:1000',
-                '--memory=20g', '--memory-swap=20g', '--cpus=8', '--pids-limit=256',
-                '--tmpfs=/tmp:rw,nosuid,nodev,size=64m,mode=1777',
-                '--mount', f'type=bind,source={work},target=/work',
-                '--workdir=/work', args.image, 'python3', 'solution.py', 'task.md']
+        receipt_stream = args.receipt.open('x', encoding='utf-8')
+    except FileExistsError:
+        # A race after the initial check must still stop BEFORE any Docker call.
+        parser.error('receipt appeared before exclusive reservation')
+    result = {'status': 'FAIL_H02_4_DOCKER_CLI_ONLY', 'image': args.image,
+              'source_sha256': {}, 'cases': [], 'cleanup': [], 'unresolved_resources': [],
+              'source_policy': 'frozen_root_and_identical_staging', 'root_source_changed': True,
+              'python_optimize': sys.flags.optimize, 'python_version': sys.version.split()[0],
+              'model_fit_calls': 0, 'live_api_calls': 0, 'official_image_verified': False,
+              'full_H05_acceptance_claimed': False,
+              'capture_scope': 'postcapture limit for trusted short CLI, not adversarial streaming',
+              'receipt_creation': 'held_exclusive_fd_before_docker'}
+    with receipt_stream:
+        try:
+            result['source_sha256'] = source_hashes(ROOT)
+            owner = uuid.uuid4().hex
+            stage = args.receipt.resolve().parent / ('platform-cli-' + uuid.uuid4().hex)
+            stage.mkdir()
+            result['stage'] = str(stage)
+            for index, folder in enumerate(['Регрессия', 'Многоклассовая классификация'], 1):
+                case, cleanup = run_case(folder, index, stage, args.image, owner, result['source_sha256'])
+                result['cases'].append(case)
+                result['cleanup'].append(cleanup)
+                if not cleanup['verified']:
+                    result['unresolved_resources'].append({'name': cleanup['name'],
+                                                           'container_id': cleanup['container_id']})
+                if case['status'] != 'PASS':
+                    break
+        except CheckError as exc:
+            result['failure_reason'] = exc.code
+        except KeyboardInterrupt:
+            result['failure_reason'] = 'checker_interrupted'
+        except Exception as exc:
+            result.update(failure_reason='checker_internal_error', error_type=type(exc).__name__)
+        finally:
             try:
-                child = subprocess.run(command, capture_output=True, text=True, timeout=45)
-                assert child.returncode == 3, (folder, child.returncode, child.stderr[:500])
-                assert len(child.stdout) < 65536 and len(child.stderr) < 65536
-                outcome = json.loads(child.stdout)
-                assert outcome['phase'] == 'H02.3' and outcome['contract_valid']
-                assert outcome['termination_reason'] == 'implementation_incomplete'
-                assert not any(outcome[k] for k in ['api_verified','tools_verified','research_completed','submission_valid','experiments_completed'])
-                assert old == (sha(existing), existing.stat().st_mtime_ns)
-                assert originals == {p: sha(original/p) for p in INPUTS}
-                assert originals == {p: sha(work/p) for p in INPUTS}
-                assert result['source_sha256'] == {p: sha(work/p) for p in SOURCES}
-                artifacts = list((work/'.aegml_runs').glob('*/*.json'))
-                assert len(artifacts) == 2
-                assert {p.name:sha(p) for p in artifacts} == outcome['artifact_sha']
-                contract = json.loads(next(p for p in artifacts if p.name=='task_contract.json').read_text())
-                assert contract['prediction_schema']['output_order'] == 'test'
-                result['cases'].append({'dataset': folder, 'exit_code': child.returncode,
-                    'literal_container_argv': ['python3','solution.py','task.md'],
-                    'source_sha256_preserved': True, 'input_sha256_preserved': True,
-                    'existing_csv_preserved': True, 'outcome': outcome,
-                    'resolved_metric': contract['metric'], 'output_order': 'test',
-                    'artifact_count': len(artifacts), 'status': 'PASS'})
-            finally:
-                subprocess.run(DOCKER+['rm','-f',name],capture_output=True,timeout=15)
-        result['status'] = 'PASS_H02_4_DOCKER_CLI_ONLY'
-    finally:
-        result['source_sha256_after'] = {p:sha(ROOT/p) for p in SOURCES}
-        args.receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
-    print(json.dumps({'status':result['status'],'datasets':len(result['cases'])}))
+                result['source_sha256_after'] = source_hashes(ROOT)
+                result['root_source_changed'] = result['source_sha256'] != result['source_sha256_after']
+            except Exception as exc:
+                result.update(root_source_changed=True, source_recheck_error=type(exc).__name__)
+            if result['root_source_changed']:
+                result['failure_reason'] = 'root_source_drift'
+            passed = (len(result['cases']) == 2 and all(case['status'] == 'PASS' for case in result['cases'])
+                      and len(result['cleanup']) == 2 and all(item['verified'] for item in result['cleanup'])
+                      and not result['unresolved_resources'] and not result['root_source_changed']
+                      and not result.get('failure_reason'))
+            result['status'] = 'PASS_H02_4_DOCKER_CLI_ONLY' if passed else 'FAIL_H02_4_DOCKER_CLI_ONLY'
+            json.dump(result, receipt_stream, ensure_ascii=False, indent=2, allow_nan=False)
+            receipt_stream.write('\n')
+    print(json.dumps({'status': result['status'], 'datasets': len(result['cases']),
+                      'root_source_changed': result['root_source_changed'],
+                      'cleanup_verified': all(item['verified'] for item in result['cleanup'])}, ensure_ascii=False))
+    return 0 if result['status'] == 'PASS_H02_4_DOCKER_CLI_ONLY' else 1


 if __name__ == '__main__':
-    main()
+    raise SystemExit(main())

```

## Новый независимый mock checker

```python
"""Mock-only H02.4 trusted CLI-checker regressions; no Docker/API/ML.

Run under the authorized Linux Python 3.12 environment with --receipt NEW.json.
Optionally pass --before-checker historical.py for the fixed historical SHA.
All checker invocations use synthetic temporary ROOTs and a subprocess.run
double inside a separate Python interpreter, including explicit -O coverage.
No production source, real dataset, private configuration or container is edited.
"""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts/check_h024_platform_cli.py"
BEFORE_SHA = "01cfba293a37f15ab4dc060ffafbee16ef57848fa083b171fe676fda5d875e1a"
BEFORE_CHECKER = None
CASES, INVOCATIONS = [], []
IMAGE = "sha256:" + "9" * 64
SOURCES = ("solution.py", "aegml_contracts.py", "aegml_input.py", "aegml_schemas.py", "requirements.txt")
SENTINEL = b'{"fixture":"prior-receipt-must-survive"}\n'


DRIVER = r'''
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

root, scenario, receipt = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
checker = root / "scripts/check_h024_platform_cli.py"
IMAGE = "sha256:" + "9" * 64
SENTINEL = b'{"fixture":"prior-receipt-must-survive"}\n'
RealCompletedProcess = subprocess.CompletedProcess
RealCalledProcessError = subprocess.CalledProcessError


class FakeDocker:
    def __init__(self):
        self.actions = []
        self.containers = {}
        self.starts = 0
        self.created = 0
        self.race_snapshot = None
        self.foreign_id = "f" * 64

    def answer(self, command, rc=0, stdout="", stderr="", **kwargs):
        text = bool(kwargs.get("text") or kwargs.get("universal_newlines") or kwargs.get("encoding"))
        if not text:
            stdout, stderr = stdout.encode(), stderr.encode()
        if kwargs.get("check") and rc:
            raise RealCalledProcessError(rc, command, output=stdout, stderr=stderr)
        return RealCompletedProcess(command, rc, stdout, stderr)

    def inspect_data(self, item):
        return {
            "Id": item["id"], "Name": "/" + item["name"], "Image": IMAGE,
            "Owner": item["labels"].get("org.aegml.h024.cli.owner", ""),
            "id": item["id"], "name": "/" + item["name"],
            "owner": item["labels"].get("org.aegml.h024.cli.owner", ""),
            "Config": {"Labels": item["labels"], "User": "1000:1000"},
            "HostConfig": {"Memory": 20 * 1024**3, "MemorySwap": 20 * 1024**3,
                "NanoCpus": 8 * 10**9, "PidsLimit": 256, "NetworkMode": "none",
                "ReadonlyRootfs": True, "Privileged": False, "CapDrop": ["ALL"],
                "CapAdd": None, "SecurityOpt": ["no-new-privileges=true"],
                "Binds": None, "Tmpfs": {"/tmp": "rw,nosuid,nodev,size=64m,mode=1777"}},
            "State": {"Status": "exited" if item.get("started") else "created", "ExitCode": 3},
            "Mounts": [{"Type": "bind", "Source": str(item["work"]),
                        "Destination": "/work", "RW": True}],
        }

    def get(self, target):
        return next((item for item in self.containers.values()
                     if target in (item["name"], item["id"])), None)

    def materialize(self, item):
        self.starts += 1
        item["started"] = True
        work = item["work"]
        artifacts = work / ".aegml_runs" / ("a" * 31 + str(self.starts))
        artifacts.mkdir(parents=True)
        contract = {"prediction_schema": {"output_order": "test"},
                    "metric": {"name": "rmse" if self.starts == 1 else "macro_f1"}}
        (artifacts / "task_contract.json").write_text(json.dumps(contract), encoding="utf-8")
        (artifacts / "row_alignment.json").write_text('{"output_to_test":[0]}', encoding="utf-8")
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts.iterdir()}
        outcome = {"phase": "H02.3", "contract_valid": True,
                   "termination_reason": "implementation_incomplete", "api_verified": False,
                   "tools_verified": False, "research_completed": False, "submission_valid": False,
                   "experiments_completed": 0, "artifact_sha": hashes}
        if scenario == "bad_flags":
            outcome["api_verified"] = True
        if scenario == "root_changed" and self.starts == 2:
            path = root / "solution.py"
            path.write_bytes(path.read_bytes() + b"\n# synthetic concurrent root mutation\n")
        if scenario == "absent_after_run":
            self.containers.pop(item["name"], None)
        return 0 if scenario == "bad_exit" else 3, json.dumps(outcome)

    def __call__(self, command, *args, **kwargs):
        command = list(command)
        # The double never delegates an unrecognised command to the OS.
        if not command or Path(str(command[0])).name != "docker":
            raise RuntimeError("unexpected_non_docker_command_blocked")
        tokens = command[1:]
        if tokens[:1] == ["--host"]:
            tokens = tokens[2:]
        if tokens[:1] == ["container"]:
            tokens = tokens[1:]
        action = tokens[0] if tokens else ""
        self.actions.append({"action": action, "argv": command})
        if action in ("create", "run"):
            name = tokens[tokens.index("--name") + 1]
            mount = tokens[tokens.index("--mount") + 1]
            source = next(part[7:] for part in mount.split(",") if part.startswith("source="))
            labels = {}
            for index, token in enumerate(tokens):
                if token == "--label":
                    key, value = tokens[index + 1].split("=", 1)
                    labels[key] = value
                elif token.startswith("--label="):
                    key, value = token[len("--label="):].split("=", 1)
                    labels[key] = value
            if scenario == "collision":
                self.containers[name] = {"name": name, "id": self.foreign_id,
                                         "labels": {"fixture.foreign-owner": "foreign"}, "work": Path(source)}
                return self.answer(command, 125, stderr="Conflict: container name already in use", **kwargs)
            self.created += 1
            item = {"name": name, "id": format(self.created, "064x"),
                    "labels": labels, "work": Path(source)}
            self.containers[name] = item
            if "--cidfile" in tokens:
                Path(tokens[tokens.index("--cidfile") + 1]).write_text(item["id"] + "\n", encoding="utf-8")
            if action == "run":
                rc, output = self.materialize(item)
                return self.answer(command, rc, output, **kwargs)
            return self.answer(command, stdout=item["id"] + "\n", **kwargs)
        if action == "inspect":
            target = tokens[-1]
            if scenario == "inspect_error" and self.starts:
                return self.answer(command, 1, stderr="Cannot connect to the Docker daemon", **kwargs)
            item = self.get(target)
            if item is None:
                return self.answer(command, 1, stderr="Error: No such container: " + target, **kwargs)
            data = self.inspect_data(item)
            if "--format" in tokens:
                return self.answer(command, stdout=json.dumps(data), **kwargs)
            return self.answer(command, stdout=json.dumps([data]), **kwargs)
        if action in ("ps", "ls"):
            if scenario == "inspect_error" and self.starts:
                return self.answer(command, 1, stderr="Cannot connect to the Docker daemon", **kwargs)
            items = list(self.containers.values())
            for index, token in enumerate(tokens):
                if token != "--filter":
                    continue
                key, value = tokens[index + 1].split("=", 1)
                if key == "name":
                    name = value.lstrip("^").lstrip("/").rstrip("$")
                    items = [item for item in items if item["name"] == name]
                elif key == "id":
                    items = [item for item in items if item["id"] == value]
            return self.answer(command, stdout="".join(item["id"] + "\n" for item in items), **kwargs)
        if action == "start":
            item = self.get(tokens[-1])
            if item is None:
                return self.answer(command, 1, stderr="No such container", **kwargs)
            rc, output = self.materialize(item)
            return self.answer(command, rc, output, **kwargs)
        if action in ("rm", "remove"):
            target = tokens[-1]
            item = self.get(target)
            if scenario == "rm_failure":
                return self.answer(command, 1, stderr="Cannot connect to the Docker daemon", **kwargs)
            if item is None:
                return self.answer(command, 1, stderr="Error: No such container: " + target, **kwargs)
            self.containers.pop(item["name"], None)
            return self.answer(command, stdout=target + "\n", **kwargs)
        raise RuntimeError("unexpected_docker_action_blocked:" + action)


fake = FakeDocker()
# Simulate the real receipt TOCTOU: another writer wins after exists() but
# before exclusive open. This never alters an already-reserved receipt inode.
original_path_open = Path.open
def racing_path_open(path, mode="r", *args, **kwargs):
    if scenario == "receipt_race" and Path(path) == receipt and "x" in mode and fake.race_snapshot is None:
        with original_path_open(path, "wb") as stream:
            stream.write(SENTINEL)
        os.utime(path, ns=(1_600_000_000_000_000_000,) * 2)
        fake.race_snapshot = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                              "mtime_ns": path.stat().st_mtime_ns}
    return original_path_open(path, mode, *args, **kwargs)
Path.open = racing_path_open
spec = importlib.util.spec_from_file_location("h024_fixture_checker", checker)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
exit_code, error_type = 0, None
try:
    spec.loader.exec_module(module)
    module.ROOT = root
    module.os.chown = lambda *args, **kwargs: None
    module.subprocess.run = fake
    sys.argv = [str(checker), "--image", IMAGE, "--receipt", str(receipt)]
    # Do not let the checker's ordinary stdout mix with this driver's JSON.
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        returned = module.main()
    exit_code = returned if type(returned) is int else 0
except SystemExit as exc:
    exit_code = exc.code if type(exc.code) is int else 1
    error_type = "SystemExit"
except BaseException as exc:
    exit_code, error_type = 1, type(exc).__name__
payload = None
if receipt.is_file():
    try:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        pass
print(json.dumps({"exit_code": exit_code, "error_type": error_type, "optimize": sys.flags.optimize,
    "receipt": payload, "receipt_exists": receipt.exists(), "actions": fake.actions,
    "remaining": [{"name": item["name"], "id": item["id"], "labels": item["labels"]}
                  for item in fake.containers.values()],
    "race_snapshot": fake.race_snapshot,
    "receipt_snapshot": {"sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
                         "mtime_ns": receipt.stat().st_mtime_ns} if receipt.is_file() else None},
    ensure_ascii=False, allow_nan=False))
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def has_pass(outcome):
    payload = outcome.get("receipt")
    return isinstance(payload, dict) and str(payload.get("status", "")).startswith("PASS_")


class CliCheckerChecks(unittest.TestCase):
    @contextmanager
    def case(self, name, finding, *, historical=False):
        record = {"test": self.id(), "case": name, "finding": finding,
                  "historical_before": historical, "status": "RUNNING"}
        CASES.append(record)
        try:
            yield record
        except BaseException:
            record["status"] = "FAIL"
            raise
        else:
            record["status"] = "PASS_EXPECTED_OLD_BEHAVIOR" if historical else "PASS"

    def invoke(self, scenario="normal", *, optimize=False, existing=False, before=False):
        source = BEFORE_CHECKER if before else CHECKER
        self.assertIsNotNone(source)
        with tempfile.TemporaryDirectory(prefix="aegml-h024-mock-") as temporary:
            base = Path(temporary)
            root = base / "synthetic root"
            scripts = root / "scripts"
            scripts.mkdir(parents=True)
            shutil.copyfile(source, scripts / CHECKER.name)
            executed_checker_sha = sha(scripts / CHECKER.name)
            for filename in SOURCES:
                content = "# Synthetic fixture only; never executed.\n" if filename.endswith(".py") else "fixture-package==0\n"
                (root / filename).write_text(content, encoding="utf-8")
            for folder in ("Регрессия", "Многоклассовая классификация"):
                task = root / "drive-download-20261019T181414Z-1-001" / folder
                task.mkdir(parents=True)
                for filename in ("task.md", "train.csv", "test.csv", "data_dictionary.csv", "sample_submission.csv"):
                    (task / filename).write_text("# synthetic fixture\n" if filename == "task.md" else "id,y\n001,0\n", encoding="utf-8")
            driver = base / "driver.py"
            driver.write_text(DRIVER, encoding="utf-8")
            receipt = base / "proof" / "checker.json"
            receipt.parent.mkdir()
            sentinel_snapshot = None
            if existing:
                receipt.write_bytes(SENTINEL)
                os.utime(receipt, ns=(1_600_000_000_000_000_000,) * 2)
                sentinel_snapshot = {"sha256": sha(receipt), "mtime_ns": receipt.stat().st_mtime_ns}
            before_hash = sha(root / "solution.py")
            command = [sys.executable, "-B"] + (["-O"] if optimize else []) + [str(driver), str(root), scenario, str(receipt)]
            env = {"PATH": str(Path(sys.executable).parent), "PYTHONDONTWRITEBYTECODE": "1",
                   "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
            child = subprocess.run(command, capture_output=True, text=True, timeout=15, env=env, cwd=base)
            self.assertEqual(child.returncode, 0, "fixture driver failed; no Docker was delegated")
            self.assertLess(len(child.stdout), 262144)
            self.assertEqual(child.stderr, "", "fixture driver emitted unexpected stderr")
            outcome = json.loads(child.stdout)
            self.assertEqual(outcome["optimize"], int(optimize), "actual child optimization mode differs")
            outcome["root_changed"] = sha(root / "solution.py") != before_hash
            outcome["sentinel_snapshot"] = sentinel_snapshot
            INVOCATIONS.append({"scenario": scenario, "historical_before": before, "optimize": optimize,
                "observed_optimize": outcome["optimize"],
                "checker_sha256": executed_checker_sha, "driver_python_exit": child.returncode,
                "checker_exit": outcome["exit_code"], "checker_status": (outcome.get("receipt") or {}).get("status"),
                "mock_actions": outcome["actions"], "real_docker_actions": 0,
                "root_changed_inside_synthetic_fixture": outcome["root_changed"]})
            return outcome

    def assert_failed(self, outcome):
        self.assertNotEqual(outcome["exit_code"], 0)
        self.assertFalse(has_pass(outcome), "invalid fixture obtained overall PASS")

    def test_unchanged_control_passes(self):
        with self.case("unchanged_two_task_snapshot_control", "H024-CLI-SOURCE-001"):
            outcome = self.invoke()
            self.assertEqual(outcome["exit_code"], 0)
            self.assertTrue(has_pass(outcome))
            self.assertFalse(outcome["root_changed"])
            self.assertEqual(len(outcome["receipt"]["cases"]), 2)
            self.assertEqual(outcome["receipt"]["unresolved_resources"], [])
            self.assertTrue(all(item["verified"] for item in outcome["receipt"]["cleanup"]))
            removals = [item["argv"][-1] for item in outcome["actions"] if item["action"] in ("rm", "remove")]
            self.assertEqual(len(removals), 2)
            self.assertTrue(all(len(value) == 64 and all(char in "0123456789abcdef" for char in value)
                                for value in removals), "owned cleanup must address full IDs, never names")

    def test_foreign_name_collision_never_removed(self):
        with self.case("foreign_collision_no_delete", "H024-CLI-OWN-001"):
            outcome = self.invoke("collision")
            self.assert_failed(outcome)
            self.assertFalse(any(item["action"] in ("rm", "remove") for item in outcome["actions"]))
            self.assertEqual([item["id"] for item in outcome["remaining"]], ["f" * 64])

    def test_cleanup_inspect_daemon_error_is_not_absence(self):
        with self.case("cleanup_inspect_error_is_unknown_and_fails", "H024-CLI-OWN-001"):
            outcome = self.invoke("inspect_error")
            self.assert_failed(outcome)
            self.assertTrue(outcome["remaining"])
            self.assertIsNotNone(outcome["receipt"], "failure needs a new diagnostic receipt")
            self.assertTrue(outcome["receipt"]["unresolved_resources"])
            self.assertTrue(any(not item["verified"] for item in outcome["receipt"]["cleanup"]))
            self.assertFalse(any(item["action"] in ("rm", "remove") for item in outcome["actions"]))

    def test_confirmed_absence_after_run_is_allowed(self):
        with self.case("confirmed_auto_removed_container_not_false_failure", "H024-CLI-OWN-001"):
            outcome = self.invoke("absent_after_run")
            self.assertEqual(outcome["exit_code"], 0)
            self.assertTrue(has_pass(outcome))
            self.assertEqual(outcome["remaining"], [])
            self.assertTrue(all(item["verified"] for item in outcome["receipt"]["cleanup"]))

    def test_rm_failure_retains_unresolved_cleanup(self):
        with self.case("owned_rm_failure_recorded_and_fails", "H024-CLI-OWN-001"):
            outcome = self.invoke("rm_failure")
            self.assert_failed(outcome)
            self.assertTrue(outcome["remaining"])
            self.assertTrue(any(item["action"] in ("rm", "remove") for item in outcome["actions"]))
            self.assertTrue(outcome["receipt"]["unresolved_resources"])
            self.assertTrue(any(not item["verified"] for item in outcome["receipt"]["cleanup"]))

    def test_invalid_exit_normal_and_optimized(self):
        for optimized in (False, True):
            with self.subTest(optimize=optimized), self.case("invalid_exit_rejected_optimize_" + str(optimized), "H024-CLI-ASSERT-001"):
                outcome = self.invoke("bad_exit", optimize=optimized)
                self.assert_failed(outcome)

    def test_invalid_flags_normal_and_optimized(self):
        for optimized in (False, True):
            with self.subTest(optimize=optimized), self.case("invalid_flags_rejected_optimize_" + str(optimized), "H024-CLI-ASSERT-001"):
                outcome = self.invoke("bad_flags", optimize=optimized)
                self.assert_failed(outcome)

    def test_existing_receipt_preserved_before_docker(self):
        with self.case("existing_receipt_bytes_mtime_and_zero_actions", "H024-CLI-RECEIPT-001"):
            outcome = self.invoke(existing=True)
            self.assert_failed(outcome)
            self.assertEqual(outcome["actions"], [])
            self.assertEqual(outcome["receipt_snapshot"], outcome["sentinel_snapshot"])

    def test_receipt_race_never_overwrites_new_owner(self):
        with self.case("raced_receipt_creation_preserves_bytes_and_mtime", "H024-CLI-RECEIPT-001"):
            outcome = self.invoke("receipt_race")
            self.assert_failed(outcome)
            self.assertIsNotNone(outcome["race_snapshot"])
            self.assertEqual(outcome["receipt_snapshot"], outcome["race_snapshot"])
            self.assertEqual(outcome["actions"], [], "lost receipt reservation must fail before Docker")

    def test_root_mutated_after_second_staging_is_not_pass(self):
        with self.case("root_drift_after_last_staging_nonpass", "H024-CLI-SOURCE-001"):
            outcome = self.invoke("root_changed")
            self.assertTrue(outcome["root_changed"], "mutation fixture did not execute")
            self.assert_failed(outcome)
            payload = outcome["receipt"]
            self.assertNotEqual(payload["source_sha256"], payload["source_sha256_after"])
            self.assertTrue(payload["root_source_changed"])

    def test_historical_before_counterexamples(self):
        if BEFORE_CHECKER is None:
            self.skipTest("historical checker not supplied; before evidence NOT_RUN")
        self.assertEqual(sha(BEFORE_CHECKER), BEFORE_SHA)
        for scenario in ("collision", "bad_exit", "existing_receipt", "root_changed", "rm_failure"):
            optimized = scenario == "bad_exit"
            with self.subTest(scenario=scenario), self.case("historical_counterexample_" + scenario,
                    {"collision": "H024-CLI-OWN-001", "bad_exit": "H024-CLI-ASSERT-001",
                     "existing_receipt": "H024-CLI-RECEIPT-001", "root_changed": "H024-CLI-SOURCE-001",
                     "rm_failure": "H024-CLI-OWN-001"}[scenario], historical=True):
                outcome = self.invoke(scenario, optimize=optimized, before=True, existing=scenario == "existing_receipt")
                if scenario == "collision":
                    self.assertTrue(any(item["action"] in ("rm", "remove") for item in outcome["actions"]))
                    self.assertEqual(outcome["remaining"], [])
                elif scenario == "existing_receipt":
                    self.assertNotEqual(outcome["receipt_snapshot"], outcome["sentinel_snapshot"])
                    self.assertTrue(has_pass(outcome))
                else:
                    self.assertTrue(has_pass(outcome), "historical counterexample no longer reproduced")
                    if scenario == "root_changed":
                        self.assertTrue(outcome["root_changed"])


def main():
    global BEFORE_CHECKER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--before-checker", type=Path)
    args = parser.parse_args()
    if args.receipt.exists():
        parser.error("receipt already exists; select a fresh receipt path")
    if args.before_checker is not None:
        BEFORE_CHECKER = args.before_checker.resolve()
        if not BEFORE_CHECKER.is_file() or sha(BEFORE_CHECKER) != BEFORE_SHA:
            parser.error("before-checker must have the declared historical SHA256")
    source_paths = (CHECKER, Path(__file__).resolve())
    initial = {str(path.relative_to(ROOT)): sha(path) for path in source_paths}
    receipt = {"phase": "H02.4", "status": "NOT_RUN", "python": platform.python_version(),
        "scope": "mock-only trusted Docker CLI-checker regression; synthetic temporary ROOTs only",
        "source_sha256": initial, "before_checker_sha256": sha(BEFORE_CHECKER) if BEFORE_CHECKER else None,
        "before_coverage": "REQUESTED" if BEFORE_CHECKER else "NOT_RUN",
        "real_docker_commands": 0, "live_api_calls": 0, "fit_calls": 0,
        "package_installation_executed": False, "real_project_mutation": False,
        "official_platform_image_verified": False, "full_H05_accepted": False,
        "child_environment_controlled": True,
        "notes": ["subprocess.run is replaced inside each isolated fixture Python process; it never delegates Docker.",
                  "Python -O is exercised in a separate process, not simulated by changing __debug__.",
                  "Mock filesystem artifacts are hand-authored and do not execute production solution.py.",
                  "Historic expected-defect observations are separate from fixed-checker acceptance."]}
    if sys.platform != "linux" or sys.version_info[:2] != (3, 12):
        receipt.update(status="BLOCKED_WRONG_CHECK_ENVIRONMENT", test_methods_run=0,
                       behavior_cases_checked=0, checker_invocations=0)
        code = 2
    else:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CliCheckerChecks))
        final = {str(path.relative_to(ROOT)): sha(path) for path in source_paths}
        stable = initial == final
        passed = result.wasSuccessful() and stable
        receipt.update(status="PASS_H024_CLI_MOCK_REGRESSIONS_ONLY" if passed else "FAIL_H024_CLI_MOCK_REGRESSIONS",
            test_methods_run=result.testsRun, behavior_cases_checked=len(CASES),
            behavior_cases_passed=sum(case["status"].startswith("PASS") for case in CASES),
            checker_invocations=len(INVOCATIONS), cases=CASES, invocations=INVOCATIONS,
            source_sha256_after=final, source_unchanged_during_check=stable,
            before_coverage="OBSERVED" if BEFORE_CHECKER else "NOT_RUN",
            unittest_failures=[{"test": test.id(), "detail": detail} for test, detail in result.failures],
            unittest_errors=[{"test": test.id(), "detail": detail} for test, detail in result.errors],
            unittest_skips=[{"test": test.id(), "reason": reason} for test, reason in result.skipped])
        code = 0 if passed else 1
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": receipt["status"], "receipt": str(args.receipt),
        "test_methods_run": receipt["test_methods_run"], "behavior_cases_checked": receipt["behavior_cases_checked"],
        "checker_invocations": receipt["checker_invocations"]}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

```

## Извлечённые поля новых квитанций

```json
{
  "H02_REPAIR_CONTRACT_RESULT.json": {
    "status": "PASS_H02_3_CONTRACT_ONLY",
    "test_methods_run": 43,
    "behavior_cases_checked": 108,
    "behavior_cases_passed": 108,
    "cli_invocations": 6,
    "source_unchanged_during_check": true,
    "source_sha256": {
      "solution.py": "0a6a30ccf53a95cb75a96c8edf7d449fdd393e573027a1188c9adc7189d0f177",
      "aegml_contracts.py": "b33bb466b3ab11911e514dfea20530bbeec179bb9777a45ef3a67c9eeb5314d3",
      "aegml_input.py": "0b08f1285a2ea9851db45f8b5a39bba826d3800b73e6e5e6ffd67b99c66eef74",
      "aegml_schemas.py": "b2cfb4b51df3b51a48d53c45b182b6789c4bf099af2c025f402ec28d8a74352d",
      "requirements.txt": "9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6",
      "scripts/check_h023_contract.py": "a00c8c36be3da323acc6f00bfc583efcaf930b15af257004f0d56128c8df333c"
    },
    "source_sha256_after": {
      "solution.py": "0a6a30ccf53a95cb75a96c8edf7d449fdd393e573027a1188c9adc7189d0f177",
      "aegml_contracts.py": "b33bb466b3ab11911e514dfea20530bbeec179bb9777a45ef3a67c9eeb5314d3",
      "aegml_input.py": "0b08f1285a2ea9851db45f8b5a39bba826d3800b73e6e5e6ffd67b99c66eef74",
      "aegml_schemas.py": "b2cfb4b51df3b51a48d53c45b182b6789c4bf099af2c025f402ec28d8a74352d",
      "requirements.txt": "9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6",
      "scripts/check_h023_contract.py": "a00c8c36be3da323acc6f00bfc583efcaf930b15af257004f0d56128c8df333c"
    }
  },
  "H02_REPAIR_BOOTSTRAP_RESULT.json": {
    "status": "PASS_H02_2_BOOTSTRAP_REGRESSION",
    "test_methods_run": 24,
    "behavior_cases_checked": 51,
    "behavior_cases_passed": 51,
    "cli_invocations": 37,
    "source_unchanged_during_check": true,
    "source_sha256": {
      "solution.py": "0a6a30ccf53a95cb75a96c8edf7d449fdd393e573027a1188c9adc7189d0f177",
      "aegml_contracts.py": "b33bb466b3ab11911e514dfea20530bbeec179bb9777a45ef3a67c9eeb5314d3",
      "aegml_input.py": "0b08f1285a2ea9851db45f8b5a39bba826d3800b73e6e5e6ffd67b99c66eef74",
      "aegml_schemas.py": "b2cfb4b51df3b51a48d53c45b182b6789c4bf099af2c025f402ec28d8a74352d",
      "requirements.txt": "9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6",
      "scripts/check_h02_bootstrap.py": "a6bcfeba45c01c2e3e483161fe498e96ce8a8410ed8e38f37504945285079a3f"
    },
    "source_sha256_after": {
      "solution.py": "0a6a30ccf53a95cb75a96c8edf7d449fdd393e573027a1188c9adc7189d0f177",
      "aegml_contracts.py": "b33bb466b3ab11911e514dfea20530bbeec179bb9777a45ef3a67c9eeb5314d3",
      "aegml_input.py": "0b08f1285a2ea9851db45f8b5a39bba826d3800b73e6e5e6ffd67b99c66eef74",
      "aegml_schemas.py": "b2cfb4b51df3b51a48d53c45b182b6789c4bf099af2c025f402ec28d8a74352d",
      "requirements.txt": "9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6",
      "scripts/check_h02_bootstrap.py": "a6bcfeba45c01c2e3e483161fe498e96ce8a8410ed8e38f37504945285079a3f"
    }
  },
  "H02_REPAIR_DOCKER_CLI_RESULT.json": {
    "status": "PASS_H02_4_DOCKER_CLI_ONLY",
    "root_source_changed": false,
    "cleanup": [
      {
        "name": "aegml-h024-cli-fb3642f01a914a01b52fc0a6c2eec4b3-1",
        "container_id": "08378f83c1c47a025dd7c09f0bc7552d88f42d3f46d56ede76ff8ed674aaef92",
        "status": "verified_absent",
        "verified": true,
        "inspect_returncode": 1,
        "inspect_timed_out": false,
        "absence_checks": [
          {
            "filter": "name=^/aegml-h024-cli-fb3642f01a914a01b52fc0a6c2eec4b3-1$",
            "returncode": 0,
            "timed_out": false
          },
          {
            "filter": "id=08378f83c1c47a025dd7c09f0bc7552d88f42d3f46d56ede76ff8ed674aaef92",
            "returncode": 0,
            "timed_out": false
          }
        ]
      },
      {
        "name": "aegml-h024-cli-fb3642f01a914a01b52fc0a6c2eec4b3-2",
        "container_id": "3f89ea674cd09bddf1196d68bd473f1097030fd2638f88f6b19da368cb1ea122",
        "status": "verified_absent",
        "verified": true,
        "inspect_returncode": 1,
        "inspect_timed_out": false,
        "absence_checks": [
          {
            "filter": "name=^/aegml-h024-cli-fb3642f01a914a01b52fc0a6c2eec4b3-2$",
            "returncode": 0,
            "timed_out": false
          },
          {
            "filter": "id=3f89ea674cd09bddf1196d68bd473f1097030fd2638f88f6b19da368cb1ea122",
            "returncode": 0,
            "timed_out": false
          }
        ]
      }
    ],
    "unresolved_resources": [],
    "source_policy": "frozen_root_and_identical_staging",
    "source_sha256": {
      "solution.py": "0a6a30ccf53a95cb75a96c8edf7d449fdd393e573027a1188c9adc7189d0f177",
      "aegml_contracts.py": "b33bb466b3ab11911e514dfea20530bbeec179bb9777a45ef3a67c9eeb5314d3",
      "aegml_input.py": "0b08f1285a2ea9851db45f8b5a39bba826d3800b73e6e5e6ffd67b99c66eef74",
      "aegml_schemas.py": "b2cfb4b51df3b51a48d53c45b182b6789c4bf099af2c025f402ec28d8a74352d",
      "requirements.txt": "9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6"
    },
    "source_sha256_after": {
      "solution.py": "0a6a30ccf53a95cb75a96c8edf7d449fdd393e573027a1188c9adc7189d0f177",
      "aegml_contracts.py": "b33bb466b3ab11911e514dfea20530bbeec179bb9777a45ef3a67c9eeb5314d3",
      "aegml_input.py": "0b08f1285a2ea9851db45f8b5a39bba826d3800b73e6e5e6ffd67b99c66eef74",
      "aegml_schemas.py": "b2cfb4b51df3b51a48d53c45b182b6789c4bf099af2c025f402ec28d8a74352d",
      "requirements.txt": "9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6"
    }
  },
  "H02_REPAIR_CLI_REGRESSIONS_RESULT.json": {
    "status": "PASS_H024_CLI_MOCK_REGRESSIONS_ONLY",
    "test_methods_run": 11,
    "behavior_cases_checked": 17,
    "behavior_cases_passed": 17,
    "checker_invocations": 17,
    "source_unchanged_during_check": true,
    "source_sha256": {
      "scripts/check_h024_platform_cli.py": "946f940febd24f313871835f8e927f27f5c2f1c09162ba6fbb84832984c79e5b",
      "scripts/check_h024_cli_regressions.py": "a6d8ba7530a178230d7d57e725a99c4e9fabef5d6800a519df741be8cbd7b0a6"
    },
    "source_sha256_after": {
      "scripts/check_h024_platform_cli.py": "946f940febd24f313871835f8e927f27f5c2f1c09162ba6fbb84832984c79e5b",
      "scripts/check_h024_cli_regressions.py": "a6d8ba7530a178230d7d57e725a99c4e9fabef5d6800a519df741be8cbd7b0a6"
    },
    "before_checker_sha256": "01cfba293a37f15ab4dc060ffafbee16ef57848fa083b171fe676fda5d875e1a"
  },
  "H02_REPAIR_TYPEINTRO_BEFORE_RESULT.json": {
    "status": "EXPECTED_FAILURES_REPRODUCED_PRE_TYPEINTRO_SOURCE_ONLY",
    "cli_invocations": 2,
    "subcases": 15,
    "failed_subcases": 11,
    "passed_controls": 4
  }
}
```
