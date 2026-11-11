"""Download a pinned public 4-bit derivative; never upload project inputs."""
from pathlib import Path
import hashlib
import json
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
REPO = 'unsloth/Qwen3-4B-Instruct-2507-bnb-4bit'
REVISION = 'f12db89cd5156e090618dded9b4367f23f8f3b33'
DEST = ROOT / 'models' / 'base'
DEST.mkdir(parents=True, exist_ok=True)
meta = json.load(urllib.request.urlopen(f'https://huggingface.co/api/models/{REPO}/revision/{REVISION}?blobs=true', timeout=60))
assert meta['sha'] == REVISION
files = [x for x in meta['siblings'] if x['rfilename'] != '.gitattributes']
for item in files:
    name, size = item['rfilename'], item['size']
    target = DEST / name
    part = target.with_suffix(target.suffix + '.partial')
    if target.exists() and target.stat().st_size == size:
        print('Already present:', name, flush=True)
        continue
    for attempt in range(4):
        offset = part.stat().st_size if part.exists() else 0
        req = urllib.request.Request(f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}?download=true', headers={'Range': f'bytes={offset}-'} if offset else {})
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                resumed = offset and response.status == 206
                if not resumed:
                    offset = 0
                last = offset
                with part.open('ab' if resumed else 'wb') as output:
                    while block := response.read(4 * 1024 * 1024):
                        output.write(block)
                        offset += len(block)
                        if offset-last >= 128*1024*1024:
                            print(f'{name}: {offset/size:.0%}', flush=True)
                            last = offset
            assert part.stat().st_size == size, (name, part.stat().st_size, size)
            if item.get('lfs', {}).get('sha256'):
                digest = hashlib.file_digest(part.open('rb'), 'sha256').hexdigest()
                assert digest == item['lfs']['sha256'], f'Checksum mismatch: {name}'
            part.replace(target)
            print('Downloaded:', name, flush=True)
            break
        except Exception as exc:
            print(f'Retry {attempt+1}: {name}: {type(exc).__name__}', flush=True)
            if attempt == 3:
                raise
            time.sleep(2)
(ROOT / 'model_source.json').write_text(json.dumps({
    'base_model': 'Qwen/Qwen3-4B-Instruct-2507', 'quantized_distribution': REPO,
    'revision': REVISION, 'files': files, 'license': 'Apache-2.0',
    'quantization': 'NF4, double quantization, bf16 compute',
}, ensure_ascii=False, indent=2), encoding='utf-8')
print('DOWNLOAD_COMPLETE', flush=True)
