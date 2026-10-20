"""Build an explicit local context from already-verified H02.1 wheels; no fetch."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--context', required=True, type=Path)
    parser.add_argument('--wheel-root', required=True, type=Path)
    args = parser.parse_args()
    context = args.context.resolve()
    cache = args.wheel_root.resolve(strict=True)
    if context.exists():
        parser.error('context must be a fresh directory')
    lock = json.loads((ROOT / 'docs/environment-lock.json').read_text(encoding='utf-8'))
    expected = {w['filename']: w['sha256'] for w in lock['wheel_artifacts']['wheels']}
    pip = lock['wheel_artifacts']['bootstrap']
    expected[pip['file']] = pip['sha256']
    resolved = {}
    for name, sha in expected.items():
        matches = list(cache.rglob(name))
        if not matches or any(digest(p) != sha for p in matches):
            raise ValueError('missing or mismatched verified wheel')
        resolved[name] = matches[0]
    context.mkdir(parents=True)
    (context / 'wheels').mkdir()
    for name, source in resolved.items():
        shutil.copyfile(source, context / 'wheels' / name)
    shutil.copyfile(ROOT / 'Dockerfile.dev', context / 'Dockerfile')
    shutil.copyfile(ROOT / 'requirements.txt', context / 'provided-requirements.txt')
    pins = lock['installed_distributions']
    (context / 'dev-lock.txt').write_text(''.join(f'{k}=={v}\n' for k, v in sorted(pins.items())), encoding='utf-8')
    (context / 'wheels.SHA256').write_text(''.join(f'{v}  {k}\n' for k, v in sorted(expected.items())), encoding='utf-8')
    (context / '.dockerignore').write_text('*\n!Dockerfile\n!dev-lock.txt\n!provided-requirements.txt\n!wheels.SHA256\n!wheels/\n!wheels/*\n', encoding='utf-8')
    print(json.dumps({'status': 'PREPARED_VERIFIED_LOCAL_SUBSET_CONTEXT', 'wheel_count': len(expected),
                      'distribution_count': len(pins), 'provided_requirements_sha256': digest(ROOT/'requirements.txt'),
                      'context': str(context), 'dockerfile_sha256': digest(ROOT/'Dockerfile.dev')}))


if __name__ == '__main__':
    main()
