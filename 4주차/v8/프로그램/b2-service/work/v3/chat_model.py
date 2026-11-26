"""Structured model boundary. Callers own locking, prompts and result validation.

Changing a backend does not change record access or conversation state. The
default remains the packaged local model; no remote service is contacted.
"""
from dataclasses import dataclass
from typing import Protocol
import json
import re
import sys


@dataclass(frozen=True)
class JsonRequest:
    system: str
    payload: dict
    schema: dict | None
    max_tokens: int = 240
    max_input_tokens: int = 2600
    max_seconds: int = 15
    overflow_error: str = 'semantic_context_too_large'


class StructuredModel(Protocol):
    def generate_json(self, request: JsonRequest) -> dict: ...


class LocalModel:
    def __init__(self, w):
        self.model_dir = w.ROOT.parent / 'b2-model'

    def generate_json(self, request):
        return json.loads(self.generate_text(request))

    def generate_text(self, request, messages=None):
        import workspace_ai as runtime
        if str(self.model_dir) not in sys.path:
            sys.path.insert(0, str(self.model_dir))
        from runtime import load_base, encode_prompt
        import torch
        if runtime._model is None:
            runtime._tokenizer, runtime._model = load_base()
        if messages is None:
            messages = [{'role':'system', 'content':request.system},
                        {'role':'user', 'content':json.dumps(request.payload, ensure_ascii=False)}]
        ids = encode_prompt(runtime._tokenizer, messages).to('cuda')
        if ids.shape[1] > request.max_input_tokens:
            raise ValueError(request.overflow_error)
        constraints = {}
        if request.schema is not None:
            from lmformatenforcer import JsonSchemaParser
            from lmformatenforcer.integrations.transformers import (
                build_token_enforcer_tokenizer_data, build_transformers_prefix_allowed_tokens_fn)
            if not hasattr(runtime, '_question_token_data'):
                runtime._question_token_data = build_token_enforcer_tokenizer_data(runtime._tokenizer)
            constraints['prefix_allowed_tokens_fn'] = build_transformers_prefix_allowed_tokens_fn(
                runtime._question_token_data, JsonSchemaParser(request.schema))
        with torch.inference_mode():
            output = runtime._model.generate(
                input_ids=ids, attention_mask=torch.ones_like(ids), do_sample=False,
                max_new_tokens=request.max_tokens, max_time=request.max_seconds,
                pad_token_id=runtime._tokenizer.eos_token_id, **constraints)
        generated = output[0, ids.shape[1]:]
        text = runtime._tokenizer.decode(generated, skip_special_tokens=True).strip()
        if request.schema is None and len(generated) and int(generated[-1]) != runtime._tokenizer.eos_token_id:
            ends = list(re.finditer(r'[.!?。！？](?=\s|$)|^\x60\x60\x60[ \t]*(?=\n|$)',text,re.M))
            if ends:
                text = text[:ends[-1].end()]
        return text


def complete(w, request: JsonRequest, *, backend: StructuredModel | None = None):
    """Backends return a proposal, never execute tools or modify records."""
    result = (backend if backend is not None else LocalModel(w)).generate_json(request)
    if not isinstance(result, dict):
        raise ValueError('model_response_must_be_an_object')
    return result


def reply(w, system, payload):
    messages = None
    if 'general_conversation' in payload:
        messages = [{'role':'system','content':system}]
        for turn in payload['general_conversation']:
            messages.extend([{'role':'user','content':turn['question']},
                             {'role':'assistant','content':turn['answer']}])
        messages.append({'role':'user','content':payload['question']})
    request = JsonRequest(system,payload,None,max_tokens=120 if payload.get('concise') else 260,max_seconds=20)
    return LocalModel(w).generate_text(request,messages)
