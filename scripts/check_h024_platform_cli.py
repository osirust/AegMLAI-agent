"""Trusted local Docker CLI checks; frozen root, no ML/key/API/worker acceptance.

Acceptance uses explicit checks even under Python -O. A fresh receipt is reserved
exclusively before any Docker call. Each --rm container has a private cidfile and
owner label; cleanup deletes only a verified full ID. A failed inspect alone is
never proof that a container is absent. Capture remains for a trusted short CLI,
not a streaming output limit for an adversarial worker.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]
DOCKER = ['docker', '--host', 'unix:///var/run/docker.sock']
SOURCES = ['solution.py', 'aegml_contracts.py', 'aegml_input.py', 'aegml_schemas.py', 'requirements.txt']
INPUTS = ['task.md', 'train.csv', 'test.csv', 'data_dictionary.csv', 'sample_submission.csv']
OWNER_LABEL = 'org.aegml.h024.cli.owner'
MAX_OUTPUT_BYTES = 65536
INSPECT_FORMAT = ('{"Id":{{json .Id}},"Name":{{json .Name}},'
                  '"Owner":{{json (index .Config.Labels "' + OWNER_LABEL + '")}}}')


class CheckError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require(condition, code):
    if not condition:
        raise CheckError(code)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def source_hashes(root):
    return {name: sha(root / name) for name in SOURCES}


def strict_json(value):
    def reject_constant(_):
        raise ValueError('nonfinite_json')
    return json.loads(value, parse_constant=reject_constant)


def run_docker(arguments, *, timeout=15):
    """Known short Docker commands only; raw error text is not put in receipts."""
    try:
        child = subprocess.run(DOCKER + arguments, capture_output=True, text=True,
                               timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {'returncode': None, 'stdout': '', 'timed_out': True,
                'capture_valid': False, 'error': 'docker_timeout'}
    except (OSError, UnicodeError):
        return {'returncode': None, 'stdout': '', 'timed_out': False,
                'capture_valid': False, 'error': 'docker_call_failed'}
    stdout = child.stdout or ''
    stderr = child.stderr or ''
    if not isinstance(stdout, str) or not isinstance(stderr, str):
        return {'returncode': child.returncode, 'stdout': '', 'timed_out': False,
                'capture_valid': False, 'error': 'invalid_docker_capture'}
    valid = (len(stdout.encode('utf-8', errors='replace')) < MAX_OUTPUT_BYTES
             and len(stderr.encode('utf-8', errors='replace')) < MAX_OUTPUT_BYTES)
    return {'returncode': child.returncode, 'stdout': stdout if valid else '',
            'timed_out': False, 'capture_valid': valid,
            'stdout_bytes': len(stdout.encode('utf-8', errors='replace')),
            'stderr_bytes': len(stderr.encode('utf-8', errors='replace'))}


def _absence(name, container_id=None):
    filters = ['name=^/' + name + '$']
    if container_id:
        filters.append('id=' + container_id)
    observations = []
    for selector in filters:
        call = run_docker(['ps', '-a', '--no-trunc', '--filter', selector, '--format', '{{.ID}}'], timeout=8)
        observations.append({'filter': selector, 'returncode': call['returncode'],
                             'timed_out': call['timed_out']})
        if call['returncode'] != 0 or not call['capture_valid']:
            return False, observations, 'docker_absence_query_failed'
        ids = call['stdout'].split()
        if any(re.fullmatch(r'[0-9a-f]{64}', item) is None for item in ids):
            return False, observations, 'invalid_absence_query_response'
        if ids:
            return False, observations, 'container_still_present'
    return True, observations, None


def cleanup_container(name, owner, cidfile):
    """Never remove by name. CID/name/owner must all agree before full-ID rm."""
    result = {'name': name, 'container_id': None, 'status': 'cleanup_unverified', 'verified': False}
    if re.fullmatch(r'aegml-h024-cli-[0-9a-f]{32}-[12]', name) is None:
        result['reason'] = 'invalid_owned_container_name'
        return result
    container_id = None
    try:
        if os.path.lexists(cidfile):
            require(not cidfile.is_symlink() and cidfile.is_file() and cidfile.stat().st_size <= 65,
                    'invalid_cidfile')
            candidate = cidfile.read_text(encoding='ascii').strip()
            if candidate:
                require(re.fullmatch(r'[0-9a-f]{64}', candidate) is not None, 'invalid_cidfile')
                container_id = candidate
        result['container_id'] = container_id
        call = run_docker(['inspect', '--type', 'container', '--format', INSPECT_FORMAT,
                           container_id or name], timeout=8)
        result['inspect_returncode'] = call['returncode']
        result['inspect_timed_out'] = call['timed_out']
        if call['returncode'] != 0 or not call['capture_valid']:
            absent, observations, reason = _absence(name, container_id)
            result['absence_checks'] = observations
            if absent:
                result.update(status='verified_absent', verified=True)
            else:
                result['reason'] = reason
            return result
        info = strict_json(call['stdout'])
        # The selected Go template returns an object; standard inspect JSON is
        # accepted as well so callers can supply a faithful Docker API fixture.
        if isinstance(info, list):
            require(len(info) == 1, 'invalid_container_inspection')
            info = info[0]
        require(isinstance(info, dict), 'invalid_container_inspection')
        actual_id = info.get('Id')
        actual_name = info.get('Name')
        actual_owner = info.get('Owner')
        if actual_owner is None:
            actual_owner = (info.get('Config', {}).get('Labels') or {}).get(OWNER_LABEL)
        require(isinstance(actual_id, str) and re.fullmatch(r'[0-9a-f]{64}', actual_id) is not None,
                'invalid_container_inspection')
        if actual_name != '/' + name or actual_owner != owner:
            result.update(status='foreign_preserved', reason='container_ownership_mismatch')
            return result
        require(container_id is None or actual_id == container_id, 'container_id_mismatch')
        result['container_id'] = actual_id
        removal = run_docker(['rm', '-f', actual_id], timeout=15)
        result['remove_returncode'] = removal['returncode']
        result['remove_timed_out'] = removal['timed_out']
        absent, observations, reason = _absence(name, actual_id)
        result['absence_checks'] = observations
        if absent:
            result.update(status='owned_removed' if removal['returncode'] == 0 else 'verified_absent_after_remove',
                          verified=True)
        else:
            result['reason'] = reason
        return result
    except CheckError as exc:
        result['reason'] = exc.code
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError):
        result['reason'] = 'cleanup_inspection_unusable'
    return result


def run_case(folder, index, stage, image, owner, expected_sources):
    original = ROOT / 'drive-download-20261019T181414Z-1-001' / folder
    work = stage / folder
    work.mkdir()
    name = 'aegml-h024-cli-' + owner + '-' + str(index)
    cidfile = stage / (name + '.cid')  # Outside the writable /work mount.
    case = {'dataset': folder, 'status': 'FAIL', 'name': name,
            'literal_container_argv': ['python3', 'solution.py', 'task.md']}
    try:
        originals = {item: sha(original / item) for item in INPUTS}
        for item in INPUTS:
            shutil.copyfile(original / item, work / item)
        for item in SOURCES:
            shutil.copyfile(ROOT / item, work / item)
        require(source_hashes(work) == expected_sources, 'staged_source_drift')
        os.chown(work, 1000, 1000)
        for path in work.iterdir():
            os.chown(path, 1000, 1000)
        existing = work / 'submission.csv'
        existing.write_text('historical_sentinel\nkeep\n', encoding='utf-8')
        os.chown(existing, 1000, 1000)
        old = (sha(existing), existing.stat().st_mtime_ns)
        require(not os.path.lexists(cidfile), 'cidfile_already_exists')
        arguments = ['run', '--name', name, '--rm', '--init', '--pull=never',
                     '--label', OWNER_LABEL + '=' + owner, '--cidfile', str(cidfile),
                     '--network=none', '--read-only', '--cap-drop=ALL',
                     '--security-opt=no-new-privileges', '--user=1000:1000',
                     '--memory=20g', '--memory-swap=20g', '--cpus=8', '--pids-limit=256',
                     '--tmpfs=/tmp:rw,nosuid,nodev,size=64m,mode=1777',
                     '--mount', 'type=bind,source=' + str(work) + ',target=/work',
                     '--workdir=/work', image, 'python3', 'solution.py', 'task.md']
        child = run_docker(arguments, timeout=45)
        case.update(exit_code=child['returncode'], run_timed_out=child['timed_out'])
        require(not child['timed_out'], 'docker_run_timeout')
        require(child['capture_valid'], 'docker_output_limit_or_capture_failed')
        require(child['returncode'] == 3, 'unexpected_container_exit')
        outcome = strict_json(child['stdout'])
        require(isinstance(outcome, dict), 'invalid_cli_outcome')
        require(outcome.get('phase') == 'H02.3' and outcome.get('contract_valid') is True,
                'contract_acceptance_missing')
        require(outcome.get('termination_reason') == 'implementation_incomplete', 'invalid_termination_reason')
        require(all(outcome.get(item) is False for item in
                    ['api_verified', 'tools_verified', 'research_completed', 'submission_valid'])
                and type(outcome.get('experiments_completed')) is int and outcome['experiments_completed'] == 0,
                'false_full_agent_acceptance')
        require(old == (sha(existing), existing.stat().st_mtime_ns), 'existing_csv_changed')
        require(originals == {item: sha(original / item) for item in INPUTS}, 'original_input_changed')
        require(originals == {item: sha(work / item) for item in INPUTS}, 'staged_input_changed')
        require(expected_sources == source_hashes(work), 'staged_source_changed')
        artifact_root = work / '.aegml_runs'
        require(artifact_root.is_dir() and not artifact_root.is_symlink(), 'invalid_artifact_root')
        artifacts = list(artifact_root.glob('*/*.json'))
        require(len(artifacts) == 2 and {path.name for path in artifacts} ==
                {'task_contract.json', 'row_alignment.json'}, 'invalid_artifact_count_or_names')
        require(len({path.parent for path in artifacts}) == 1 and
                all(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(work.resolve())
                    for path in artifacts), 'invalid_artifact_location')
        require({path.name: sha(path) for path in artifacts} == outcome.get('artifact_sha'), 'artifact_sha_mismatch')
        contract_path = next(path for path in artifacts if path.name == 'task_contract.json')
        contract = strict_json(contract_path.read_text(encoding='utf-8'))
        require(contract['prediction_schema']['output_order'] == 'test', 'public_output_order_mismatch')
        case.update(source_sha256_preserved=True, input_sha256_preserved=True,
                    existing_csv_preserved=True, outcome=outcome, resolved_metric=contract['metric'],
                    output_order='test', artifact_count=len(artifacts), status='PASS')
    except CheckError as exc:
        case['reason'] = exc.code
    except KeyboardInterrupt:
        case['reason'] = 'checker_interrupted'
    except Exception as exc:
        case.update(reason='cli_check_internal_error', error_type=type(exc).__name__)
    finally:
        try:
            cleanup = cleanup_container(name, owner, cidfile)
        except BaseException as exc:
            cleanup = {'name': name, 'container_id': None, 'status': 'cleanup_unverified',
                       'verified': False, 'reason': 'cleanup_internal_error',
                       'error_type': type(exc).__name__}
        if not cleanup['verified']:
            case.update(status='FAIL', cleanup_unverified=True)
    return case, cleanup


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args(argv)
    if re.fullmatch(r'sha256:[0-9a-f]{64}', args.image) is None:
        parser.error('use an immutable local image ID')
    # Existing files, directories and dangling symlinks are all existing history.
    if os.path.lexists(args.receipt):
        parser.error('receipt already exists; select a fresh path')
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    try:
        receipt_stream = args.receipt.open('x', encoding='utf-8')
    except FileExistsError:
        # A race after the initial check must still stop BEFORE any Docker call.
        parser.error('receipt appeared before exclusive reservation')
    result = {'status': 'FAIL_H02_4_DOCKER_CLI_ONLY', 'image': args.image,
              'source_sha256': {}, 'cases': [], 'cleanup': [], 'unresolved_resources': [],
              'source_policy': 'frozen_root_and_identical_staging', 'root_source_changed': True,
              'python_optimize': sys.flags.optimize, 'python_version': sys.version.split()[0],
              'model_fit_calls': 0, 'live_api_calls': 0, 'official_image_verified': False,
              'full_H05_acceptance_claimed': False,
              'capture_scope': 'postcapture limit for trusted short CLI, not adversarial streaming',
              'receipt_creation': 'held_exclusive_fd_before_docker'}
    with receipt_stream:
        try:
            result['source_sha256'] = source_hashes(ROOT)
            owner = uuid.uuid4().hex
            stage = args.receipt.resolve().parent / ('platform-cli-' + uuid.uuid4().hex)
            stage.mkdir()
            result['stage'] = str(stage)
            for index, folder in enumerate(['Регрессия', 'Многоклассовая классификация'], 1):
                case, cleanup = run_case(folder, index, stage, args.image, owner, result['source_sha256'])
                result['cases'].append(case)
                result['cleanup'].append(cleanup)
                if not cleanup['verified']:
                    result['unresolved_resources'].append({'name': cleanup['name'],
                                                           'container_id': cleanup['container_id']})
                if case['status'] != 'PASS':
                    break
        except CheckError as exc:
            result['failure_reason'] = exc.code
        except KeyboardInterrupt:
            result['failure_reason'] = 'checker_interrupted'
        except Exception as exc:
            result.update(failure_reason='checker_internal_error', error_type=type(exc).__name__)
        finally:
            try:
                result['source_sha256_after'] = source_hashes(ROOT)
                result['root_source_changed'] = result['source_sha256'] != result['source_sha256_after']
            except Exception as exc:
                result.update(root_source_changed=True, source_recheck_error=type(exc).__name__)
            if result['root_source_changed']:
                result['failure_reason'] = 'root_source_drift'
            passed = (len(result['cases']) == 2 and all(case['status'] == 'PASS' for case in result['cases'])
                      and len(result['cleanup']) == 2 and all(item['verified'] for item in result['cleanup'])
                      and not result['unresolved_resources'] and not result['root_source_changed']
                      and not result.get('failure_reason'))
            result['status'] = 'PASS_H02_4_DOCKER_CLI_ONLY' if passed else 'FAIL_H02_4_DOCKER_CLI_ONLY'
            json.dump(result, receipt_stream, ensure_ascii=False, indent=2, allow_nan=False)
            receipt_stream.write('\n')
    print(json.dumps({'status': result['status'], 'datasets': len(result['cases']),
                      'root_source_changed': result['root_source_changed'],
                      'cleanup_verified': all(item['verified'] for item in result['cleanup'])}, ensure_ascii=False))
    return 0 if result['status'] == 'PASS_H02_4_DOCKER_CLI_ONLY' else 1


if __name__ == '__main__':
    raise SystemExit(main())
