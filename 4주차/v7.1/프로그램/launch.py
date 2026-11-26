"""Launch the v7.1 package on loopback with its own workspace."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser


ROOT = Path(__file__).resolve().parent
SERVICE = ROOT / 'b2-service'
MODEL_CODE = ROOT / 'b2-model'
MODEL_FILES = Path(os.environ.get('PNT_MODEL_DIR') or MODEL_CODE / 'models').expanduser().resolve()
DATA = SERVICE / 'data' / 'v7.1'
HOST = '127.0.0.1'
PORT = 8779
URL = f'http://{HOST}:{PORT}'


def running():
    try:
        with urllib.request.urlopen(URL + '/api/package-info', timeout=1) as response:
            info = json.load(response)
        return info.get('version') == '7.1.0' and Path(info.get('service_root', '')).resolve() == SERVICE
    except (OSError, ValueError):
        return False


def environment():
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith(('B2_', 'SMTP_'))}
    env.pop('PYTHONHOME', None)
    env.update(
        PYTHONUTF8='1', PYTHONPATH=str(MODEL_CODE),
        B2_DEMO_MODE='1', B2_STAGE_LOCAL='1', B2_TEAM_PORT=str(PORT),
        B2_TEAM_DATA_DIR=str(DATA),
        B2_ANALYSIS_CACHE_DIR=str(DATA / 'analysis-cache'), B2_MODEL_RESULTS=str(DATA / 'model-results'),
        B2_MODEL_BASE=str(MODEL_FILES / 'base'),
        B2_EMBEDDING_MODEL_DIR=str(MODEL_FILES / 'multilingual-e5-small'),
        B2_LLAMA_DISABLE='1', B2_CHAT_SEMANTIC='0', B2_CHAT_SHIPMENT_INTENT='1', B2_CHAT_GENERAL='1',
        MAIL_MODE='console',
    )
    return env


def start():
    with socket.socket() as sock:
        if sock.connect_ex((HOST, PORT)) == 0:
            raise RuntimeError(f'{PORT} 포트를 다른 서비스가 사용 중입니다.')
    DATA.mkdir(parents=True, exist_ok=True)
    log = DATA / 'server.log'
    with log.open('a', encoding='utf-8') as stream:
        process = subprocess.Popen(
            [sys.executable, '-B', '-X', 'utf8', '-m', 'uvicorn', 'work.v3.server:app',
             '--host', HOST, '--port', str(PORT), '--no-proxy-headers', '--no-access-log'],
            cwd=SERVICE, env=environment(), stdout=stream, stderr=stream,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    for _ in range(60):
        if running():
            return
        if process.poll() is not None:
            break
        time.sleep(.5)
    if process.poll() is None:
        process.terminate()
    raise RuntimeError(f'v7.1을 시작하지 못했습니다. {log}를 확인해 주세요.')


def main():
    if not running():
        start()
    print(f'PNT v7.1 실행 완료: {URL}')
    if '--no-browser' not in sys.argv:
        webbrowser.open(URL)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
