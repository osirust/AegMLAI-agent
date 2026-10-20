"""Prepare only the authorized H02.1 ML environment; never train or call an LLM."""
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
import venv
from datetime import datetime, timezone
from pathlib import Path

assert sys.platform=='linux' and sys.version_info[:2]==(3,12)
assert os.getuid()==1000
repo=Path(__file__).resolve().parent.parent
target=Path('/home/aegml/venvs/aegml-ml-py312')
assert target.parent.resolve()==Path('/home/aegml/venvs')
cache=Path('/home/aegml/cache/h02')
wheels=cache/'wheels'
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
proof=Path('/home/aegml/checks')/('h02-'+stamp)
for p in (cache,wheels,proof):p.mkdir(parents=True,exist_ok=True)
started=time.monotonic()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,obj):(proof/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
env=os.environ.copy()
for key in list(env):
    if key.casefold().endswith('_proxy') or key.startswith(('OPENAI_','PIP_')):env.pop(key,None)
env.update({'PIP_CONFIG_FILE':'/dev/null','PYTHONNOUSERSITE':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
def run(args,name,timeout=900):
    print(json.dumps({'phase':name,'status':'started'}),flush=True)
    with (proof/(name+'.log')).open('w',encoding='utf-8') as log:
        result=subprocess.run(args,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
    if result.returncode:
        tail=(proof/(name+'.log')).read_text(encoding='utf-8',errors='replace')[-6000:]
        print(json.dumps({'phase':name,'return_code':result.returncode,'log_tail':tail}),flush=True)
        raise RuntimeError('phase failed: '+name)
    print(json.dumps({'phase':name,'status':'completed'}),flush=True)

expected_requirements_sha='9173b0388532fbd2a709e4f4b3029e3b9ccab685fce43a85261ffa1ba95efbe6'
source_requirements=repo/'drive-download-20261019T181414Z-1-001/requirements.txt'
source_sha=sha(source_requirements) if source_requirements.is_file() else None
assert sha(repo/'requirements.txt')==expected_requirements_sha
assert source_sha is None or source_sha==expected_requirements_sha
save('before.json',{'phase':'H02.1','uid':os.getuid(),'python':platform.python_version(),'target':str(target),
    'historical_stdlib_venv_preserved':'/home/aegml/venvs/aegml-py312','root_requirements_sha256':sha(repo/'requirements.txt'),
    'source_requirements_sha256':source_sha,'expected_requirements_sha256':expected_requirements_sha,
    'constraints_sha256':sha(repo/'constraints-platform.txt'),'subset_sha256':sha(repo/'requirements-h02.txt')})
if not target.exists():venv.EnvBuilder(with_pip=False,symlinks=True).create(target)
python=target/'bin/python'
assert (target/'pyvenv.cfg').is_file() and python.is_file()
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open('https://pypi.org/pypi/pip/25.2/json',timeout=20) as response:meta=json.load(response)
wheel=next(x for x in meta['urls'] if x['filename']=='pip-25.2-py3-none-any.whl')
assert wheel['url'].startswith('https://files.pythonhosted.org/')
bootstrap=cache/wheel['filename']
if not bootstrap.exists() or sha(bootstrap)!=wheel['digests']['sha256']:
    with opener.open(wheel['url'],timeout=30) as response:payload=response.read(8*1024*1024+1)
    assert len(payload)<=8*1024*1024 and hashlib.sha256(payload).hexdigest()==wheel['digests']['sha256']
    bootstrap.write_bytes(payload)
bootstrap_code="import runpy,sys;sys.path.insert(0,sys.argv.pop(1));sys.argv[0]='pip';runpy.run_module('pip',run_name='__main__')"
run([str(python),'-I','-c',bootstrap_code,str(bootstrap),'install','--no-index','--no-deps',str(bootstrap)],'bootstrap-pip',120)
run([str(python),'-I','-m','pip','--isolated','download','--index-url','https://pypi.org/simple','--only-binary=:all:',
     '--dest',str(wheels),'--constraint',str(repo/'constraints-platform.txt'),'--requirement',str(repo/'requirements-h02.txt'),
     '--disable-pip-version-check','--no-input'],'download-wheels')
run([str(python),'-I','-m','pip','--isolated','install','--no-index','--find-links',str(wheels),'--only-binary=:all:',
     '--constraint',str(repo/'constraints-platform.txt'),'--requirement',str(repo/'requirements-h02.txt'),
     '--report',str(proof/'install-report.json'),'--disable-pip-version-check','--no-input'],'offline-install')
run([str(python),'-I','-m','pip','check'],'pip-check',120)
run([str(python),'-I','-m','pip','list','--format=json'],'package-list',120)
save('wheels.json',{'bootstrap':{'file':bootstrap.name,'sha256':sha(bootstrap),'pypi_expected_sha256':wheel['digests']['sha256']},
    'wheels':[{'filename':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(wheels.glob('*.whl'))]})
save('installation.json',{'status':'INSTALLED_PENDING_IMPORT_SMOKE','proof_dir':str(proof),'venv':str(target),
    'python':platform.python_version(),'pip_bootstrap':'25.2 development tool only','elapsed_seconds':round(time.monotonic()-started,3),
    'training_executed':False,'live_api_called':False,'platform_image_verified':False,'historical_stdlib_venv_modified':False})
(Path('/home/aegml/checks')/'h02-latest-proof.txt').write_text(str(proof)+'\n',encoding='utf-8')
print(json.dumps({'status':'INSTALLED_PENDING_IMPORT_SMOKE','proof_dir':str(proof),'venv':str(target)}),flush=True)
