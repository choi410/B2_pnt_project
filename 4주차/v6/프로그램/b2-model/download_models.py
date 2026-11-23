"""Download only pinned public model assets. Does not send meeting data."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent
MODELS = (
    ('unsloth/Qwen3-4B-Instruct-2507-bnb-4bit', 'f12db89cd5156e090618dded9b4367f23f8f3b33', 'base'),
    ('intfloat/multilingual-e5-small', '614241f622f53c4eeff9890bdc4f31cfecc418b3', 'multilingual-e5-small'),
)

def main():
    # runtime.py deliberately enforces offline inference. Downloads are an explicit separate step.
    for key in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE'):
        os.environ.pop(key, None)
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    from huggingface_hub import snapshot_download
    for repo, revision, folder in MODELS:
        print('Downloading', repo, revision, flush=True)
        snapshot_download(repo_id=repo, revision=revision, local_dir=ROOT / 'models' / folder,
                          token=False, allow_patterns=['*.json', '*.safetensors', '*.txt', '*.model', '*.jinja', 'README.md', 'LICENSE*'])
    print('Both model downloads completed. Run 05 to check GPU and files.')

if __name__ == '__main__':
    main()
