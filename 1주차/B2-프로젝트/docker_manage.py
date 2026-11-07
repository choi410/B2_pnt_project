"""Start the local Docker copy without sharing the live native SQLite database."""
from __future__ import annotations

import argparse
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'docker-data'
DB = DATA / 'meetings.sqlite3'


def prepare() -> None:
    DATA.mkdir(exist_ok=True)
    if DB.exists():
        print(f'Keeping existing Docker data: {DB}', flush=True)
        return
    source = ROOT / 'b2-service' / 'data' / 'meetings.sqlite3'
    if not source.is_file():
        raise RuntimeError(f'Native database is missing: {source}')
    # SQLite backup includes committed WAL content while the native site is running.
    fd, temporary = tempfile.mkstemp(prefix='initial-', suffix='.sqlite3', dir=DATA)
    os.close(fd)
    temp = Path(temporary)
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=30)) as src:
            with closing(sqlite3.connect(temp)) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Database snapshot did not pass integrity check.')
        # Do not overwrite data if another launcher already created it.
        if DB.exists():
            raise RuntimeError('Docker database appeared during preparation; keeping it.')
        temp.rename(DB)
        print(f'Created a consistent Docker database snapshot: {DB}', flush=True)
    finally:
        temp.unlink(missing_ok=True)


def docker_path() -> str:
    found = shutil.which('docker')
    if found:
        return found
    windows = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Docker/Docker/resources/bin/docker.exe'
    if windows.is_file():
        return str(windows)
    raise RuntimeError('Install Docker Desktop and start its Linux engine first.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'start', 'stop', 'status'])
    parser.add_argument('--manual', action='store_true', help='Use the web-only image without a GPU.')
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
        return
    docker = docker_path()
    subprocess.run([docker, 'info', '--format', '{{.ServerVersion}}'], check=True, timeout=30)
    compose = [docker, 'compose', '-f', str(ROOT / 'compose.yaml')]
    if not args.manual:
        compose += ['-f', str(ROOT / 'compose.gpu.yaml')]
    if args.action == 'start':
        if not args.manual:
            base = ROOT / 'b2-model/models/base'
            for name in ['config.json', 'tokenizer.json', 'model.safetensors']:
                if not (base / name).is_file():
                    raise RuntimeError(f'Local model file missing: {base / name}')
        prepare()
        subprocess.run(compose + ['up', '-d', '--build', '--wait', '--wait-timeout', '180'], cwd=ROOT, check=True)
        if not args.manual:
            subprocess.run(compose + ['exec', '-T', 'b2', 'python', '-c',
                "import torch; assert torch.cuda.is_available(), 'GPU unavailable'; print(torch.cuda.get_device_name(0))"],
                cwd=ROOT, check=True)
        print(f"B2 Docker is ready: http://127.0.0.1:{os.environ.get('B2_DOCKER_PORT', '8767')}/", flush=True)
        print('Docker and native data are separate copies; changes do not synchronize.', flush=True)
    elif args.action == 'stop':
        subprocess.run([sys.executable, str(ROOT/'internet_share.py'), 'stop'], cwd=ROOT, check=True)
        subprocess.run(compose + ['down'], cwd=ROOT, check=True)
        print(f'Docker stopped. Saved data remains at {DATA}', flush=True)
    else:
        subprocess.run(compose + ['ps'], cwd=ROOT, check=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, sqlite3.Error, subprocess.SubprocessError) as exc:
        raise SystemExit(f'Docker operation failed: {exc}')
