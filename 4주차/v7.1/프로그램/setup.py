"""Install the Windows workspace dependencies in the package's virtual environment."""
from pathlib import Path
import struct
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parent
ENVIRONMENT = ROOT.parent / '.venv'
PYTHON = ENVIRONMENT / 'Scripts' / 'python.exe'


def install():
    if sys.version_info[:2] != (3, 12) or struct.calcsize('P') != 8:
        raise SystemExit('Python 3.12 64-bit가 필요합니다.')
    if not PYTHON.is_file():
        venv.EnvBuilder(with_pip=True).create(ENVIRONMENT)

    pip = [str(PYTHON), '-m', 'pip', 'install', '--disable-pip-version-check']
    if '--ai' in sys.argv:
        model = ROOT / 'b2-model'
        subprocess.check_call([*pip, '-r', str(model / 'requirements-ai.txt')])
        subprocess.check_call([str(PYTHON), '-X', 'utf8', str(model / 'download_models.py')])
    else:
        service = ROOT / 'b2-service'
        subprocess.check_call([*pip, '-r', str(service / 'requirements.txt'), '-c', str(service / 'requirements-lock.txt')])
    print('설치가 끝났습니다. 실행.cmd를 열어 주세요.', flush=True)


if __name__ == '__main__':
    install()
