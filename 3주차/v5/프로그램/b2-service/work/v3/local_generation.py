"""Structured auxiliary generation using the same local model as AI chat.

Callers hold the service AI lock. Meeting extraction and AI chat keep their own
validated prompts; this adapter connects the team's project-stage feature.
"""
from pathlib import Path
import os,sys,time

def available():
    if os.environ.get('B2_STAGE_LOCAL')!='1':return False
    model=Path(__file__).resolve().parents[3]/'b2-model/models/base'
    if not (model/'config.json').is_file():return False
    try:
        import torch
        return torch.cuda.is_available()
    except (ImportError, OSError):
        return False

def chat(messages,max_tokens,schema=None):
    import workspace_ai as shared
    folder=Path(__file__).resolve().parents[3]/'b2-model'
    if str(folder) not in sys.path:sys.path.insert(0,str(folder))
    from runtime import load_base,encode_prompt
    import torch
    started=time.perf_counter()
    if shared._model is None:shared._tokenizer,shared._model=load_base()
    ids=encode_prompt(shared._tokenizer,messages).to('cuda')
    if ids.shape[1]>4096:raise ValueError('단계 판단에 사용할 원문이 너무 깁니다.')
    options={}
    if schema:
        from lmformatenforcer import JsonSchemaParser
        from lmformatenforcer.integrations.transformers import build_token_enforcer_tokenizer_data,build_transformers_prefix_allowed_tokens_fn
        if not hasattr(shared,'_question_token_data'):
            shared._question_token_data=build_token_enforcer_tokenizer_data(shared._tokenizer)
        options['prefix_allowed_tokens_fn']=build_transformers_prefix_allowed_tokens_fn(shared._question_token_data,JsonSchemaParser(schema))
    with torch.inference_mode():
        output=shared._model.generate(input_ids=ids,attention_mask=torch.ones_like(ids),do_sample=False,max_new_tokens=max_tokens,pad_token_id=shared._tokenizer.eos_token_id,**options)
    text=shared._tokenizer.decode(output[0,ids.shape[1]:],skip_special_tokens=True)
    return text,{'seconds':time.perf_counter()-started,'model':'Qwen3-4B-Instruct-2507 · shared local runtime','input_tokens':int(ids.shape[1]),'output_tokens':int(output.shape[1]-ids.shape[1])}
