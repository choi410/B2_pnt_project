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
PORT = 8777
URL = f'http://127.0.0.1:{PORT}'


def package_info():
    try:
        with urllib.request.urlopen(URL + '/api/package-info', timeout=1) as response:
            return json.load(response)
    except Exception:
        return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    info = package_info()
    if info.get('version') == '6.0.0' and Path(info.get('service_root', '')).resolve() == SERVICE:
        print('Already running: ' + URL, flush=True)
        if not args.no_browser:
            webbrowser.open(URL)
        return 0
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', PORT)) == 0:
            print('Port 8777 is used by another program. Stop that program first.', file=sys.stderr)
            return 1
    env = os.environ.copy()
    for key in ('B2_TEAM_LAN_IP', 'B2_TEAM_LAN_CIDR', 'B2_TEAM_TESTING',
                'B2_AI_DEBUG', 'B2_DATABASE', 'B2_SAMPLE_DOCX', 'PYTHONPATH', 'PYTHONHOME'):
        env.pop(key, None)
    env.update(PYTHONUTF8='1', B2_DEMO_MODE='1', B2_STAGE_LOCAL='1',
               B2_INCLUDE_SAMPLE='1', B2_TEAM_DATA_DIR=str(SERVICE / 'data/v6'),
               B2_ANALYSIS_CACHE_DIR=str(SERVICE / 'data/v6/analysis-cache'))
    # A different process on port 8080 must not silently become this package's model.
    env['B2_LLAMA_DISABLE'] = '1'
    print('PNT v6: ' + URL + '\nKeep this window open. Ctrl+C stops the service.', flush=True)
    process = subprocess.Popen([sys.executable, '-X', 'utf8', '-m', 'uvicorn',
                                'work.v3.server:app', '--host', '127.0.0.1', '--port', str(PORT),
                                '--no-proxy-headers', '--no-access-log'], cwd=SERVICE, env=env)
    ready = threading.Event()
    def wait_for_ready():
        for _ in range(120):
            if process.poll() is not None:
                return
            current = package_info()
            if current.get('version') == '6.0.0' and Path(current.get('service_root', '')).resolve() == SERVICE:
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


if __name__ == '__main__':
    raise SystemExit(main())
