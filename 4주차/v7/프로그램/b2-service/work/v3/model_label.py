"""Name of the AI model that produced a result, as connected by b2-model/runtime.py."""
import sys


def label():
    runtime = sys.modules.get('runtime')
    if runtime is not None and hasattr(runtime, 'model_label'):
        return runtime.model_label()
    return 'Qwen3-4B-Instruct-2507'
