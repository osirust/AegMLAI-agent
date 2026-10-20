"""Trusted local Docker launch checks; no ML, provider key, or live network."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
DOCKER = ['docker', '--host', 'unix:///var/run/docker.sock']
SOURCES = ['solution.py', 'aegml_contracts.py', 'aegml_input.py', 'aegml_schemas.py', 'requirements.txt']
INPUTS = ['task.md', 'train.csv', 'test.csv', 'data_dictionary.csv', 'sample_submission.csv']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if not args.image.startswith('sha256:'):
        parser.error('use an immutable local image ID')
    proof = args.receipt.resolve().parent
    proof.mkdir(parents=True, exist_ok=True)
    stage = proof / ('platform-cli-' + uuid.uuid4().hex)
    stage.mkdir()
    result = {'status': 'FAIL_H02_4_DOCKER_CLI_ONLY', 'image': args.image,
              'source_sha256': {p: sha(ROOT/p) for p in SOURCES}, 'cases': [],
              'model_fit_calls': 0, 'live_api_calls': 0, 'official_image_verified': False}
    try:
        for folder in ['Регрессия', 'Многоклассовая классификация']:
            original = ROOT / 'drive-download-20261019T181414Z-1-001' / folder
            work = stage / folder
            work.mkdir()
            originals = {p: sha(original/p) for p in INPUTS}
            for name in INPUTS:
                shutil.copyfile(original/name, work/name)
            for name in SOURCES:
                shutil.copyfile(ROOT/name, work/name)
            # Task-local staging is the only writable host mount, as on platform.
            os.chown(work, 1000, 1000)
            for path in work.iterdir():
                os.chown(path, 1000, 1000)
            existing = work / 'submission.csv'
            existing.write_text('historical_sentinel\nkeep\n')
            os.chown(existing, 1000, 1000)
            old = (sha(existing), existing.stat().st_mtime_ns)
            name = 'aegml-h024-cli-' + uuid.uuid4().hex
            command = DOCKER + ['run', '--name', name, '--rm', '--init', '--pull=never',
                '--network=none', '--read-only', '--cap-drop=ALL',
                '--security-opt=no-new-privileges', '--user=1000:1000',
                '--memory=20g', '--memory-swap=20g', '--cpus=8', '--pids-limit=256',
                '--tmpfs=/tmp:rw,nosuid,nodev,size=64m,mode=1777',
                '--mount', f'type=bind,source={work},target=/work',
                '--workdir=/work', args.image, 'python3', 'solution.py', 'task.md']
            try:
                child = subprocess.run(command, capture_output=True, text=True, timeout=45)
                assert child.returncode == 3, (folder, child.returncode, child.stderr[:500])
                assert len(child.stdout) < 65536 and len(child.stderr) < 65536
                outcome = json.loads(child.stdout)
                assert outcome['phase'] == 'H02.3' and outcome['contract_valid']
                assert outcome['termination_reason'] == 'implementation_incomplete'
                assert not any(outcome[k] for k in ['api_verified','tools_verified','research_completed','submission_valid','experiments_completed'])
                assert old == (sha(existing), existing.stat().st_mtime_ns)
                assert originals == {p: sha(original/p) for p in INPUTS}
                assert originals == {p: sha(work/p) for p in INPUTS}
                assert result['source_sha256'] == {p: sha(work/p) for p in SOURCES}
                artifacts = list((work/'.aegml_runs').glob('*/*.json'))
                assert len(artifacts) == 2
                assert {p.name:sha(p) for p in artifacts} == outcome['artifact_sha']
                contract = json.loads(next(p for p in artifacts if p.name=='task_contract.json').read_text())
                assert contract['prediction_schema']['output_order'] == 'test'
                result['cases'].append({'dataset': folder, 'exit_code': child.returncode,
                    'literal_container_argv': ['python3','solution.py','task.md'],
                    'source_sha256_preserved': True, 'input_sha256_preserved': True,
                    'existing_csv_preserved': True, 'outcome': outcome,
                    'resolved_metric': contract['metric'], 'output_order': 'test',
                    'artifact_count': len(artifacts), 'status': 'PASS'})
            finally:
                subprocess.run(DOCKER+['rm','-f',name],capture_output=True,timeout=15)
        result['status'] = 'PASS_H02_4_DOCKER_CLI_ONLY'
    finally:
        result['source_sha256_after'] = {p:sha(ROOT/p) for p in SOURCES}
        args.receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'datasets':len(result['cases'])}))


if __name__ == '__main__':
    main()
