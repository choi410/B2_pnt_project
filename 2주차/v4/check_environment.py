"""Read-only portability check. Does not load models or create workspace records."""
from pathlib import Path
import importlib.util
import sys
import struct

ROOT = Path(__file__).resolve().parent
base_ok = sys.version_info[:2] == (3, 12) and struct.calcsize('P') == 8
print('Python 3.12 64-bit:', 'OK' if base_ok else 'MISSING')
for module in ('fastapi', 'uvicorn', 'multipart', 'pypdfium2', 'PIL', 'docx', 'openpyxl'):
    ready = importlib.util.find_spec(module) is not None
    base_ok = base_ok and ready
    print(module + ':', 'OK' if ready else 'MISSING - run 01')
print('Basic service:', 'READY' if base_ok else 'NOT READY')
ai_ok = True
for module in ('torch', 'transformers', 'accelerate', 'bitsandbytes', 'lmformatenforcer', 'numpy'):
    ready = importlib.util.find_spec(module) is not None
    ai_ok = ai_ok and ready
    print(module + ':', 'OK' if ready else 'MISSING - run 03 for AI')
if importlib.util.find_spec('torch'):
    try:
        import torch
        cuda = torch.cuda.is_available()
        bf16 = cuda and torch.cuda.is_bf16_supported()
        ai_ok = ai_ok and cuda and bf16
        print('CUDA GPU:', torch.cuda.get_device_name(0) if cuda else 'NOT AVAILABLE')
        print('BF16 support:', 'OK' if bf16 else 'NOT AVAILABLE')
    except Exception as exc:
        ai_ok = False
        print('GPU check failed:', type(exc).__name__)
for folder in ('base', 'multilingual-e5-small'):
    ready = all((ROOT / 'b2-model' / 'models' / folder / name).is_file()
                for name in ('config.json', 'tokenizer_config.json', 'tokenizer.json', 'model.safetensors'))
    ai_ok = ai_ok and ready
    print(folder + ':', 'OK' if ready else 'MISSING - run 04 for AI')
print('AI prerequisites:', 'READY (inference and VRAM still need testing)' if ai_ok else 'NOT READY')
print('Microsoft Word desktop is optional for original DOCX page previews.')
print('No models were loaded and no workspace data was changed.')
raise SystemExit(0 if base_ok else 1)
