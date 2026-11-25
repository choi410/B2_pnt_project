"""Optional local reuse of validated machine output; never stores review decisions."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import uuid

FORMAT = 1
MAX_BYTES = 4 * 1024 * 1024
SERVICE = Path(__file__).resolve().parents[2]


def root():
    value = os.environ.get('B2_ANALYSIS_CACHE_DIR', '').strip()
    path = Path(value) if value else None
    return path.resolve() if path and path.is_absolute() else None


def signature():
    """Invalidate on extraction rules, stage prompts, runtime or local model changes."""
    digest = hashlib.sha256()
    for relative in ('work/v3/analysis_cache.py', 'work/v3/fast_ai.py',
                     'work/v3/service.py', 'work/v3/local_generation.py',
                     'work/v3/stage_prompt.txt', 'work/v17/demo_ai.py',
                     'work/v17/changes.py', 'workspace_ai.py'):
        path = SERVICE / relative
        digest.update(relative.encode())
        digest.update(path.read_bytes() if path.is_file() else b'missing')
    model = SERVICE.parent / 'b2-model'
    runtime = model / 'runtime.py'
    digest.update(runtime.read_bytes() if runtime.is_file() else b'missing-runtime')
    base = model / 'models/base'
    for path in sorted(base.rglob('*')):
        if not path.is_file():
            continue
        stat = path.stat()
        digest.update(json.dumps([str(path.relative_to(base)), stat.st_size,
                                  stat.st_mtime_ns]).encode())
        if path.suffix == '.json' and stat.st_size < 1024 * 1024:
            digest.update(path.read_bytes())
    return digest.hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def entry(namespace, inputs):
    folder = root()
    if folder is None:
        return None
    key = hashlib.sha256(encoded([FORMAT, namespace, signature(), inputs])).hexdigest()
    return folder / (key + '.json'), key


def read(namespace, inputs):
    try:
        target = entry(namespace, inputs)
        if target is None:
            return None
        path, key = target
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        record = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(record, dict) or not isinstance(record.get('created_at'), str):
            return None
        if record.get('format') != FORMAT or record.get('key') != key:
            return None
        if hashlib.sha256(encoded(record['value'])).hexdigest() != record.get('checksum'):
            return None
        return record
    except (OSError, ValueError, TypeError, KeyError):
        return None


def write(namespace, inputs, value):
    temporary = None
    try:
        target = entry(namespace, inputs)
        if target is None:
            return
        path, key = target
        payload = encoded({'format': FORMAT, 'key': key, 'value': value,
                           'created_at': datetime.now(timezone.utc).isoformat(),
                           'checksum': hashlib.sha256(encoded(value)).hexdigest()})
        if len(payload) > MAX_BYTES:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.stem + '.' + uuid.uuid4().hex + '.tmp')
        temporary.write_bytes(payload)
        temporary.replace(path)
    except (OSError, ValueError, TypeError):
        pass  # An unavailable cache must never break registration.
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
