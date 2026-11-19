"""Install reviewed fictional examples once; retain each computer's own workspace."""
import hashlib
import json
import os
import shutil
from pathlib import Path

SAMPLE = Path(__file__).resolve().parents[3] / 'sample-data'
FILE_KEYS = {'pdf', 'docx', 'txt', 'path', 'original_path'}
MARKER = 'v5_sample_initialized'


def _walk(value, replace, key=''):
    if isinstance(value, dict):
        return {k: _walk(v, replace, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk(v, replace, key) for v in value]
    return replace(value, key) if isinstance(value, str) else value


def initialize(w):
    with w.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        # Moving an already used folder must also preserve its source links.
        previous = c.execute("SELECT value FROM workspace_meta WHERE key='v5_files_root'").fetchone()
        if previous and previous[0] != str(w.FILES):
            old = previous[0].replace('\\', '/').rstrip('/') + '/'
            def relocate(value, key):
                normalized = value.replace('\\', '/')
                if key not in FILE_KEYS or not normalized.startswith(old):
                    return value
                target = (w.FILES / normalized[len(old):]).resolve()
                if not target.is_relative_to(w.FILES.resolve()) or not target.is_file():
                    raise RuntimeError('원문 파일을 찾지 못했습니다. data 폴더의 files까지 함께 옮겨 주세요.')
                return str(target)
            for row in c.execute('SELECT kind,payload FROM records').fetchall():
                value = json.loads(row['payload'])
                moved = _walk(value, relocate)
                if moved != value:
                    w.save(c, row['kind'], moved)
        c.execute("INSERT OR REPLACE INTO workspace_meta VALUES('v5_files_root',?)", (str(w.FILES),))
        if os.environ.get('B2_INCLUDE_SAMPLE') != '1':
            return
        if c.execute('SELECT 1 FROM workspace_meta WHERE key=?', (MARKER,)).fetchone():
            return
        if c.execute("SELECT COUNT(*) FROM records WHERE kind!='person'").fetchone()[0]:
            c.execute('INSERT INTO workspace_meta VALUES(?,?)', (MARKER, 'existing-workspace'))
            return
        bundle = json.loads((SAMPLE / 'workspace.json').read_text(encoding='utf-8'))
        if bundle.get('format') != 1:
            raise ValueError('지원하지 않는 예제 자료 형식입니다.')
        copies = {}
        for name, expected_hash in bundle['files'].items():
            if Path(name).name != name or '/' in name or '\\' in name:
                raise ValueError('예제 원문 파일 이름을 확인해 주세요.')
            source = SAMPLE / 'files' / name
            if hashlib.sha256(source.read_bytes()).hexdigest() != expected_hash:
                raise ValueError('예제 원문 파일이 손상되었습니다. v5 폴더를 다시 내려받아 주세요.')
            copies['@sample-file/' + name] = w.FILES / ('sample-' + name)
        def resolve(value, key):
            if value.startswith('@sample-file/'):
                if key not in FILE_KEYS or value not in copies:
                    raise ValueError('예제 원문의 연결 정보를 확인해 주세요.')
                return str(copies[value])
            return value
        records = []
        for item in bundle['records']:
            if item['kind'] not in ('project', 'meeting', 'change_event') or item['id'] != item['payload']['id']:
                raise ValueError('예제 자료의 항목을 확인해 주세요.')
            records.append((item['kind'], _walk(item['payload'], resolve)))
        for name, expected_hash in bundle['files'].items():
            target = copies['@sample-file/' + name]
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest() != expected_hash:
                    raise ValueError('같은 이름의 다른 원문이 있습니다. 원문을 덮어쓰지 않았습니다.')
            else:
                shutil.copyfile(SAMPLE / 'files' / name, target)
        for kind, value in records:
            w.save(c, kind, value)
        for memo in bundle.get('memos', []):
            c.execute('INSERT OR IGNORE INTO calendar_memos VALUES(?,?,?)',
                      (memo['user_id'], memo['day'], memo['text']))
        c.execute('INSERT INTO workspace_meta VALUES(?,?)', (MARKER, bundle['name']))
