"""Run this checkout on loopback with its own cookie, data and reviewed examples."""
from pathlib import Path
import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
SERVICE = ROOT / 'b2-service'
# B2_PORT lets a second copy (e.g. a development copy) run beside the team service.
PORT = int(os.environ.get('B2_PORT', '8776'))
URL = f'http://127.0.0.1:{PORT}'


def package_info():
    try:
        with urllib.request.urlopen(URL + '/api/package-info', timeout=1) as response:
            return json.load(response)
    except Exception:
        return {}


ENGINE_DIR = ROOT / 'b2-model' / 'llama-cpp'
GGUF_DIR = ROOT / 'b2-model' / 'models' / 'gguf'
# (file, GPU GB needed). Qwen3-4B (4.3 GB) runs on an 8 GB laptop GPU. Model comparison of
# 2026-11-23 (after the joint-analysis schema fix): score 86.8, recall 88.9%, precision 85.7%,
# no risky errors, no failures. Set B2_ENGINE_MODEL to use another file in models/gguf.
ENGINE_CHOICES = [('Qwen3-4B-Instruct-2507-Q8_0.gguf', 0)]


def gpu_memory_gb():
    """Total memory of the first NVIDIA GPU in GB (0 when it cannot be read)."""
    try:
        out = subprocess.run(['nvidia-smi', '--query-gpu=memory.total', '--format=csv,noheader,nounits'],
                             capture_output=True, text=True, timeout=10).stdout
        return int(out.split()[0]) / 1024
    except Exception:
        return 0


def pick_engine_model():
    """B2_ENGINE_MODEL names a GGUF file in models/gguf; otherwise the first choice that fits."""
    if os.environ.get('B2_ENGINE_MODEL'):
        return GGUF_DIR / os.environ['B2_ENGINE_MODEL']
    gpu = None
    for name, need_gb in ENGINE_CHOICES:
        if not (GGUF_DIR / name).exists():
            continue
        if need_gb:
            gpu = gpu_memory_gb() if gpu is None else gpu
            if gpu < need_gb:
                continue
        return GGUF_DIR / name
    return GGUF_DIR / ENGINE_CHOICES[-1][0]


ENGINE_MODEL = pick_engine_model()
ENGINE_PORT = int(os.environ.get('B2_ENGINE_PORT', '8786'))
ENGINE_URL = f'http://127.0.0.1:{ENGINE_PORT}'


def engine_health():
    try:
        with urllib.request.urlopen(ENGINE_URL + '/health', timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


def start_engine():
    """Start the bundled llama.cpp server when its files are present. Returns (process, url)."""
    exe = ENGINE_DIR / 'llama-server.exe'
    if os.environ.get('B2_ENGINE', '').lower() == 'transformers' or not exe.exists() or not ENGINE_MODEL.exists():
        return None, ''
    if engine_health():
        return None, ENGINE_URL
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', ENGINE_PORT)) == 0:
            print(f'Port {ENGINE_PORT} is busy; using the built-in AI engine instead.', flush=True)
            return None, ''
    log = open(ENGINE_DIR / 'server.log', 'w', encoding='utf-8', errors='replace')
    # Two slots let independent generations run at once; each slot gets 16,384 tokens,
    # which covers the largest caller (6,500 input + 3,000 output tokens).
    # --cache-ram 0: the engine otherwise restores the saved state of an earlier, similar prompt,
    # and the same minutes then gave different records from one analysis to the next
    # (free-form consistency 67% -> 100% with it off; speed unchanged).
    process = subprocess.Popen([str(exe), '-m', str(ENGINE_MODEL), '-ngl', '99', '-c', '32768', '-np', '2', '--cache-ram', '0',
                                '-fa', 'on', '--reasoning', 'off', '--host', '127.0.0.1', '--port', str(ENGINE_PORT), '--no-webui'],
                               cwd=ENGINE_DIR, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(360):  # a large model can take a while on the first, uncached load
        if process.poll() is not None:
            print('llama.cpp engine failed to start (see b2-model/llama-cpp/server.log); '
                  'using the built-in AI engine instead.', flush=True)
            return None, ''
        if engine_health():
            print('AI engine: llama.cpp ' + ENGINE_URL + ' · ' + ENGINE_MODEL.stem, flush=True)
            return process, ENGINE_URL
        time.sleep(0.5)
    process.terminate()
    print('llama.cpp engine did not become ready; using the built-in AI engine instead.', flush=True)
    return None, ''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    info = package_info()
    if info.get('version') == '5.0.0' and Path(info.get('service_root', '')).resolve() == SERVICE:
        print('Already running: ' + URL, flush=True)
        if not args.no_browser:
            webbrowser.open(URL)
        return 0
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', PORT)) == 0:
            print(f'Port {PORT} is used by another program. Stop that program first.', file=sys.stderr)
            return 1
    env = os.environ.copy()
    for key in ('B2_TEAM_LAN_IP', 'B2_TEAM_LAN_CIDR', 'B2_TEAM_TESTING',
                'B2_AI_DEBUG', 'B2_DATABASE', 'B2_SAMPLE_DOCX', 'PYTHONPATH', 'PYTHONHOME'):
        env.pop(key, None)
    env.update(PYTHONUTF8='1', B2_DEMO_MODE='1', B2_STAGE_LOCAL='1',
               B2_INCLUDE_SAMPLE='1', B2_TEAM_DATA_DIR=str(SERVICE / 'data/v5'))
    # A different process on port 8080 must not silently become this package's model.
    env['B2_LLAMA_DISABLE'] = '1'
    engine, engine_url = start_engine()
    env.pop('B2_ENGINE_URL', None)
    if engine_url:
        env['B2_ENGINE_URL'] = engine_url
    print('PNT v5: ' + URL + '\nKeep this window open. Ctrl+C stops the service.', flush=True)
    process = subprocess.Popen([sys.executable, '-X', 'utf8', '-m', 'uvicorn',
                                'work.v3.server:app', '--host', '127.0.0.1', '--port', str(PORT),
                                '--no-proxy-headers', '--no-access-log'], cwd=SERVICE, env=env)
    ready = threading.Event()
    def wait_for_ready():
        for _ in range(120):
            if process.poll() is not None:
                return
            current = package_info()
            if current.get('version') == '5.0.0' and Path(current.get('service_root', '')).resolve() == SERVICE:
                ready.set()
                print('Ready: ' + URL, flush=True)
                if not args.no_browser:
                    webbrowser.open(URL)
                return
            time.sleep(0.5)
        print('Startup is taking longer than expected; check the server messages.', flush=True)
    threading.Thread(target=wait_for_ready, daemon=True).start()
    try:
        return process.wait()
    except KeyboardInterrupt:
        # The terminal also delivers Ctrl+C to uvicorn; let it finish cleanly first.
        try:
            process.wait(timeout=8)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            process.terminate()
            process.wait(timeout=5)
        return 0
    finally:
        if engine is not None and engine.poll() is None:
            engine.terminate()
            try:
                engine.wait(timeout=5)
            except subprocess.TimeoutExpired:
                engine.kill()


if __name__ == '__main__':
    raise SystemExit(main())
