"""Check this checkout's prerequisites without loading weights or changing data."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import struct
import sys

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--require-ai', action='store_true')
    args = parser.parse_args()
    basic = sys.version_info[:2] == (3, 12) and struct.calcsize('P') == 8
    print('Python 3.12 64-bit:', 'OK' if basic else 'MISSING')
    for name in ('fastapi', 'uvicorn', 'multipart', 'pypdfium2', 'PIL', 'docx', 'openpyxl'):
        ok = importlib.util.find_spec(name) is not None
        basic = basic and ok
        print(name + ':', 'OK' if ok else 'MISSING - run 01')
    ok = (ROOT / 'b2-service/work/v3/workspace.html').is_file()
    basic = basic and ok
    print('Built screen:', 'OK' if ok else 'MISSING')
    try:
        bundle = json.loads((ROOT / 'sample-data/workspace.json').read_text(encoding='utf-8'))
        assert bundle['format'] == 1
        for name, digest in bundle['files'].items():
            assert Path(name).name == name
            assert hashlib.sha256((ROOT / 'sample-data/files' / name).read_bytes()).hexdigest() == digest
        print('Fictional sample and original PDFs: OK')
    except (OSError, ValueError, KeyError, AssertionError) as error:
        basic = False
        print('Fictional sample: MISSING OR DAMAGED - download the entire v5 folder again')
    ai = True
    for name in ('torch', 'transformers', 'accelerate', 'bitsandbytes', 'lmformatenforcer', 'numpy'):
        ok = importlib.util.find_spec(name) is not None
        ai = ai and ok
        print(name + ':', 'OK' if ok else 'MISSING - run 03 for AI')
    try:
        import torch
        cuda = torch.cuda.is_available()
        bf16 = cuda and torch.cuda.is_bf16_supported()
        ai = ai and cuda and bf16
        print('GPU:', torch.cuda.get_device_name(0) if cuda else 'NVIDIA CUDA GPU not available')
        print('BF16:', 'OK' if bf16 else 'NOT AVAILABLE')
    except (ImportError, OSError, RuntimeError):
        ai = False
        print('GPU check: NOT READY')
    for folder in ('base', 'multilingual-e5-small'):
        ok = all((ROOT / 'b2-model/models' / folder / name).is_file()
                 for name in ('config.json', 'tokenizer_config.json', 'tokenizer.json', 'model.safetensors'))
        ai = ai and ok
        print(folder + ':', 'OK' if ok else 'MISSING - run 04 for AI')
    print('\nBASIC SERVICE:', 'READY' if basic else 'NOT READY')
    print('AI:', 'PREREQUISITES READY - inference and VRAM still require testing' if ai else 'NOT READY')
    print('Without AI, you can browse the included reviewed examples and their original PDFs.')
    print('New analysis and semantic/generated answers require AI setup. Each PC keeps separate data.')
    return 1 if not basic else 2 if args.require_ai and not ai else 0


if __name__ == '__main__':
    raise SystemExit(main())
