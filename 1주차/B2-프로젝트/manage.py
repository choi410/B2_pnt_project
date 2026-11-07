"""Setup and diagnostics for the Windows transfer package. Python 3.12 x64."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, os, platform, subprocess, sys, venv

ROOT=Path(__file__).resolve().parent
ENV=ROOT/'.venv'
PYTHON=ENV/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
APP=ROOT/'b2-service'

MODEL=ROOT/'b2-model'/'models'/'base'
def model_ready():
    return all((MODEL/name).is_file() for name in ['config.json','tokenizer.json','tokenizer_config.json','model.safetensors'])

def run(args,**kwargs):
    print('> '+' '.join(map(str,args)),flush=True)
    subprocess.run(list(map(str,args)),check=True,**kwargs)

def setup(ai=False):
    if ai and not model_ready():
        raise RuntimeError('This ZIP excludes model files. Copy the original models/base folder first; see 00_README.txt. Nothing was downloaded.')
    if sys.version_info[:2]!=(3,12) or sys.maxsize<2**32:
        raise RuntimeError('Use Python 3.12 (64-bit). See 00_README.txt.')
    if not PYTHON.exists():
        print('Creating a new environment inside this folder...',flush=True)
        venv.EnvBuilder(with_pip=True).create(ENV)
    run([PYTHON,'-c','import sys; assert sys.version_info[:2]==(3,12), "Existing environment must use Python 3.12"'])
    run([PYTHON,'-m','pip','install','--disable-pip-version-check','-r',ROOT/'requirements-web.txt'])
    if ai:
        if os.name!='nt' or platform.machine().lower() not in ('amd64','x86_64'):
            raise RuntimeError('The included AI setup is for Windows x64 with an NVIDIA GPU.')
        run([PYTHON,'-m','pip','install','--disable-pip-version-check','torch==2.9.1','--index-url','https://download.pytorch.org/whl/cu128'])
        run([PYTHON,'-m','pip','install','--disable-pip-version-check','-c',ROOT/'requirements-web.txt','-r',ROOT/'requirements-ai.txt'])
        run([PYTHON,Path(__file__).resolve(),'check','--require-ai'])
    else:
        run([PYTHON,Path(__file__).resolve(),'check'])
    print('\nSetup complete. Run 02_start.cmd.',flush=True)

def verify():
    manifest=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    broken=[]
    for rel,expected in manifest['sha256'].items():
        path=ROOT/rel
        if not path.is_file():broken.append(rel+' (missing)');continue
        with path.open('rb') as stream:
            digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if digest!=expected:broken.append(rel+' (changed)')
    if broken:raise RuntimeError('Package file mismatch: '+', '.join(broken))
    print('Package SHA-256 checks: OK. Runtime database is intentionally excluded.')

def check(require_ai=False):
    print('Python:',platform.python_version(),'/',platform.machine())
    missing=[p for p in ['fastapi','uvicorn','pydantic','multipart'] if importlib.util.find_spec(p) is None]
    if missing:raise RuntimeError('Run 01_setup.cmd first. Missing: '+', '.join(missing))
    if not (APP/'dist'/'index.html').is_file():raise RuntimeError('Built web files are missing. Extract the entire ZIP.')
    if not (APP/'sample'/'가상회의록_코팅설비_설계검토.docx').is_file():raise RuntimeError('Sample file missing. Extract the entire ZIP.')
    print('Web dependencies, built pages, sample document: OK')
    if not model_ready():
        print('Model files are not included. Normal start will use manual review. See 00_README.txt for optional AI setup.')
        if require_ai:raise RuntimeError('Model files are required before AI setup.')
        return
    modules=['torch','transformers','accelerate','bitsandbytes','lmformatenforcer']
    missing=[p for p in modules if importlib.util.find_spec(p) is None]
    if missing:
        print('AI is not installed. Records and manual workflow can be used. Optional: 03_setup_ai.cmd')
        if require_ai:raise RuntimeError('AI modules missing: '+', '.join(missing))
        return
    import torch
    if not torch.cuda.is_available():
        print('CUDA GPU is unavailable. Use 05_start_manual.cmd or check your NVIDIA driver.')
        if require_ai:raise RuntimeError('A working NVIDIA CUDA GPU is required.')
        return
    print('GPU:',torch.cuda.get_device_name(0))
    print('GPU memory (GiB):',round(torch.cuda.get_device_properties(0).total_memory/1024**3,2))
    print('BF16 supported:',torch.cuda.is_bf16_supported())
    if not torch.cuda.is_bf16_supported():raise RuntimeError('The packaged model configuration requires BF16 support.')
    base=ROOT/'b2-model'/'models'/'base'
    for filename in ['config.json','tokenizer.json','tokenizer_config.json','model.safetensors']:
        if not (base/filename).is_file():raise RuntimeError('Model file missing: '+filename)
    print('AI prerequisites: OK. This diagnostic does not load the model or prove generation quality.')

def start(manual=False):
    manual=manual or not model_ready()
    if not PYTHON.is_file():raise RuntimeError('Run 01_setup.cmd first.')
    run([PYTHON,'-c','import fastapi, uvicorn, pydantic, multipart'])
    env=os.environ.copy()
    env['PYTHONUTF8']='1';env['PYTHONIOENCODING']='utf-8'
    env['B2_MANUAL_ONLY']='1' if manual else '0'
    print('\nOpen http://127.0.0.1:8766 in your browser.',flush=True)
    print('Keep this window open. Press Ctrl+C to stop.',flush=True)
    print('Mode: '+('manual review' if manual else 'automatic analysis when AI prerequisites are available'),flush=True)
    run([PYTHON,'-m','uvicorn','server:app','--host','127.0.0.1','--port','8766'],cwd=APP,env=env)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['setup-web','setup-ai','check','verify','start','start-manual'])
    parser.add_argument('--require-ai',action='store_true')
    args=parser.parse_args()
    try:
        if args.action.startswith('setup'):setup(args.action=='setup-ai')
        elif args.action=='check':check(args.require_ai)
        elif args.action=='verify':verify()
        else:start(args.action=='start-manual')
    except KeyboardInterrupt:
        print('\nStopped. Saved records remain in b2-service/data.')
    except (RuntimeError,OSError,subprocess.CalledProcessError) as exc:
        print('\nERROR:',exc,file=sys.stderr)
        print('See 00_README.txt. Copy this error when requesting help.',file=sys.stderr)
        sys.exit(1)
