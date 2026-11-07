"""Share the virtual-data Docker demo through a temporary link, without email enrollment."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.request

from docker_manage import ROOT, DATA, docker_path, prepare

NAME = 'b2-workspace-share'
LABEL = 'b2.temporary-share'
IMAGE = 'cloudflare/cloudflared@sha256:4955524aeaa379e154023d5a027c250f7b35041a2e7e950cf13f144bc9b9c5ba'
STATE = DATA / 'internet-share.json'
URL_PATTERN = re.compile(r'https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com\b')


def run(docker, args, *, capture=False, env=None, check=True, timeout=180):
    return subprocess.run([docker, *args], cwd=ROOT, env=env, text=True,
        encoding='utf-8', errors='replace', capture_output=capture, check=check, timeout=timeout)


def info(docker):
    result = run(docker, ['inspect', NAME], capture=True, check=False, timeout=15)
    if result.returncode:
        error = result.stderr.strip() or result.stdout.strip()
        if any(message in error.lower() for message in [
                'no such object: '+NAME, 'no such container: '+NAME]):
            return None
        raise RuntimeError('Could not inspect the sharing connector: '+error[:500])
    value = json.loads(result.stdout)[0]
    if value['Config'].get('Labels', {}).get(LABEL) != 'true':
        raise RuntimeError(f'Container {NAME} belongs to another task; it was left untouched.')
    return value


def active_url(docker, value):
    result = run(docker, ['logs', '--since', value['State']['StartedAt'], '--tail', '100', NAME],
        capture=True, timeout=15)
    matches = URL_PATTERN.findall(result.stdout + result.stderr)
    return matches[-1] if matches else None


def healthy(url):
    request = urllib.request.Request(url + '/api/health', headers={'User-Agent':'B2-Share-Check'})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return response.status == 200 and json.load(response).get('ok') is True
    except (urllib.error.URLError, ValueError, OSError):
        return False


def save(url):
    DATA.mkdir(exist_ok=True)
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps({'url':url,'container':NAME,'access':'anyone-with-link'}, indent=2)+'\n', encoding='utf-8')
    temporary.replace(STATE)


def stop(docker):
    value = info(docker)
    if value:
        run(docker, ['stop', '--time', '10', NAME], timeout=30)
        run(docker, ['rm', NAME], timeout=30)
    STATE.unlink(missing_ok=True)
    print('Internet sharing stopped. B2 and the saved records remain available locally.', flush=True)


def start(docker):
    run(docker, ['info', '--format', '{{.ServerVersion}}'], timeout=30)
    value = info(docker)
    if value and value['State']['Running']:
        url = active_url(docker, value)
        if url and healthy(url):
            save(url)
            print('Existing internet link is ready: ' + url, flush=True)
            return
    elif value:
        run(docker, ['rm', NAME], timeout=30)
        value = None
    prepare()
    created = False
    compose = ['compose', '-f', str(ROOT/'compose.yaml'), '-f', str(ROOT/'compose.gpu.yaml')]
    try:
        if not value:
            # Build first; public requests stay blocked until the exact hostname is registered.
            run(docker, compose + ['up','-d','--build','--wait','--wait-timeout','180'], timeout=1200)
            run(docker, ['run','-d','--name',NAME,'--label',LABEL+'=true',
                '--network','b2-workspace_default','--restart','no',IMAGE,
                'tunnel','--no-autoupdate','--protocol','http2','--url','http://b2:8766'], timeout=180)
            created = True
        print('Creating a temporary HTTPS address...', flush=True)
        deadline = time.monotonic() + 90
        url = None
        while time.monotonic() < deadline:
            value = info(docker)
            if not value or not value['State']['Running']:
                raise RuntimeError('The sharing connector stopped before it created a URL.')
            url = active_url(docker, value)
            if url:
                break
            time.sleep(1)
        if not url:
            raise RuntimeError('The sharing connector did not produce an HTTPS URL.')
        env = os.environ.copy()
        env['B2_PUBLIC_ORIGIN'] = url
        print('Registering the public address with B2...', flush=True)
        run(docker, compose + ['-f',str(ROOT/'compose.internet.yaml'),
            'up','-d','--build','--wait','--wait-timeout','180'], env=env, timeout=1200)
        deadline = time.monotonic() + 90
        while not healthy(url):
            if time.monotonic() >= deadline:
                raise RuntimeError('The public HTTPS health check did not succeed.')
            time.sleep(2)
        save(url)
        print('\nInternet link is ready: ' + url, flush=True)
        print('Anyone with this link can view and edit the virtual-data demo.', flush=True)
        print('Keep this PC and Docker running. Use 10_stop_internet_share.cmd to close the link.', flush=True)
    except BaseException:
        if created:
            stop(docker)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['start','stop','status'])
    args = parser.parse_args()
    docker = docker_path()
    if args.action == 'start':
        start(docker)
    elif args.action == 'stop':
        stop(docker)
    else:
        value = info(docker)
        url = active_url(docker,value) if value and value['State']['Running'] else None
        print(json.dumps({'running':bool(url),'url':url,'healthy':healthy(url) if url else False}))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        raise SystemExit(f'Internet sharing failed: {exc}')
