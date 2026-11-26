"""Launch the v8 package on loopback with its own workspace."""
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
DATA = SERVICE / 'data' / 'v8'
HOST = '127.0.0.1'
PORT = 8780
URL = f'http://{HOST}:{PORT}'
# llama.cpp engine (optional). With b2-model/llama-cpp/llama-server.exe and the GGUF file present, the
# analysis runs on it; without them the service loads the model in-process as before.
ENGINE_DIR = MODEL_CODE / 'llama-cpp'
ENGINE_MODEL = MODEL_FILES / 'gguf' / (os.environ.get('PNT_ENGINE_MODEL') or 'Qwen3-4B-Instruct-2507-Q8_0.gguf')
ENGINE_PORT = int(os.environ.get('PNT_ENGINE_PORT') or 8786)
ENGINE_URL = f'http://{HOST}:{ENGINE_PORT}'


def running():
    try:
        with urllib.request.urlopen(URL + '/api/package-info', timeout=1) as response:
            info = json.load(response)
        return info.get('version') == '8.0.0' and Path(info.get('service_root', '')).resolve() == SERVICE
    except (OSError, ValueError):
        return False


def engine_ready():
    try:
        with urllib.request.urlopen(ENGINE_URL + '/health', timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


def start_engine():
    """The engine's URL, or '' when it is not installed or did not start. An engine already answering on
    the port is reused (one copy of the model in GPU memory). Two slots of 16,384 tokens; --cache-ram 0
    keeps repeated analyses of the same minutes identical."""
    if engine_ready():
        return ENGINE_URL
    exe = ENGINE_DIR / 'llama-server.exe'
    if not exe.is_file() or not ENGINE_MODEL.is_file():
        return ''
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / 'engine.log').open('w', encoding='utf-8', errors='replace') as stream:
        process = subprocess.Popen(
            [str(exe), '-m', str(ENGINE_MODEL), '-ngl', '99', '-c', '32768', '-np', '2', '--cache-ram', '0',
             '-fa', 'on', '--reasoning', 'off', '--host', HOST, '--port', str(ENGINE_PORT), '--no-webui'],
            cwd=ENGINE_DIR, stdout=stream, stderr=stream, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    for _ in range(360):
        if engine_ready():
            return ENGINE_URL
        if process.poll() is not None:
            break
        time.sleep(.5)
    if process.poll() is None:
        process.terminate()
    print('llama.cpp 엔진을 시작하지 못했습니다. 모델을 서비스 안에서 직접 실행합니다. ' + str(DATA / 'engine.log'), file=sys.stderr)
    return ''


def environment():
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith(('B2_', 'SMTP_'))}
    env.pop('PYTHONHOME', None)
    env.update(
        PYTHONUTF8='1', PYTHONPATH=str(MODEL_CODE),
        B2_DEMO_MODE='1', B2_INCLUDE_SAMPLE='1', B2_STAGE_LOCAL='1', B2_TEAM_PORT=str(PORT),
        B2_TEAM_DATA_DIR=str(DATA), B2_DATABASE=str(DATA / 'meetings.sqlite3'),
        B2_ANALYSIS_CACHE_DIR=str(DATA / 'analysis-cache'), B2_MODEL_RESULTS=str(DATA / 'model-results'),
        B2_MODEL_BASE=str(MODEL_FILES / 'base'),
        B2_EMBEDDING_MODEL_DIR=str(MODEL_FILES / 'multilingual-e5-small'),
        B2_LLAMA_DISABLE='1', B2_CHAT_SEMANTIC='0', B2_CHAT_SHIPMENT_INTENT='1', B2_CHAT_GENERAL='1',
        MAIL_MODE='console',
    )
    engine = start_engine()
    if engine:
        env['B2_ENGINE_URL'] = engine
    # A temporary team demo through an HTTPS tunnel: only this exact host is accepted (work/v17/team_config.py).
    if os.environ.get('B2_PUBLIC_HOST'):
        env['B2_PUBLIC_HOST'] = os.environ['B2_PUBLIC_HOST']
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
    raise RuntimeError(f'v8을 시작하지 못했습니다. {log}를 확인해 주세요.')


def main():
    if not running():
        start()
    print(f'PNT v8 실행 완료: {URL}')
    if '--no-browser' not in sys.argv:
        webbrowser.open(URL)


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
