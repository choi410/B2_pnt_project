from pathlib import Path
import os
for key in ['HF_HUB_DISABLE_TELEMETRY','DO_NOT_TRACK','WANDB_DISABLED']:
    os.environ[key]='1'
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'

import json
import time
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'models'/'base'
RESULTS=ROOT/'results'
RESULTS.mkdir(exist_ok=True)

def save_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def load_base():
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA GPU is required for this experiment.')
    tokenizer=AutoTokenizer.from_pretrained(BASE,local_files_only=True,trust_remote_code=False)
    tokenizer.pad_token=tokenizer.eos_token
    model=AutoModelForCausalLM.from_pretrained(BASE,local_files_only=True,trust_remote_code=False,
        dtype=torch.bfloat16,device_map={'':0},attn_implementation='sdpa',low_cpu_mem_usage=True)
    model.generation_config.do_sample=False
    model.generation_config.temperature=None
    model.generation_config.top_p=None
    model.generation_config.top_k=None
    model.eval()
    return tokenizer,model

def encode_prompt(tokenizer,messages):
    return tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_tensors='pt')

def infer(tokenizer,model,messages,max_new_tokens=550):
    ids=encode_prompt(tokenizer,messages).to('cuda')
    if ids.shape[1]>4096:
        raise ValueError(f'Input has {ids.shape[1]} tokens; limit 4096. No silent truncation.')
    torch.cuda.synchronize()
    start=time.perf_counter()
    with torch.inference_mode():
        out=model.generate(input_ids=ids,attention_mask=torch.ones_like(ids),max_new_tokens=max_new_tokens,
            do_sample=False,pad_token_id=tokenizer.pad_token_id,use_cache=True)
    torch.cuda.synchronize()
    generated=out[0,ids.shape[1]:]
    text=tokenizer.decode(generated,skip_special_tokens=True)
    return {'text':text,'input_tokens':ids.shape[1],'output_tokens':len(generated),
        'seconds':round(time.perf_counter()-start,3),
        'hit_token_limit':len(generated)>=max_new_tokens}

def inspect_result(result,check):
    import datetime
    payload=json.loads(check['messages'][-1]['content'])
    allowed={x['id'] for x in payload['utterances']}
    allowed.update(ref for x in payload.get('previous_issues',[]) for ref in x.get('evidence_ids',[]))
    errors=[]
    diagnostics=[]
    try:
        parsed=json.loads(result['text'])
        required={'issue_id','mentioned','state','owner','next_due','approval','reviewer','summary','evidence_ids'}
        if not isinstance(parsed,dict) or set(parsed)!=required:
            errors.append('wrong_schema_keys')
        if not isinstance(parsed.get('mentioned'),bool): errors.append('mentioned_not_boolean')
        if parsed.get('approval') not in ['pending','approved','unknown']: errors.append('invalid_approval')
        for key in ['owner','next_due','reviewer']:
            if parsed.get(key) is not None and not isinstance(parsed[key],str): errors.append(f'{key}_type')
        if parsed.get('next_due') is not None: datetime.date.fromisoformat(parsed['next_due'])
        refs=parsed.get('evidence_ids')
        if not isinstance(refs,list) or not refs or any(not isinstance(x,str) or x not in allowed for x in refs): errors.append('invalid_evidence_ids')
        if parsed.get('issue_id')!=payload['requested_issue_id']: errors.append('wrong_issue_id')
        for key in ['issue_id','state','summary']:
            if not isinstance(parsed.get(key),str): errors.append(f'{key}_type')
        current_ids={x['id'] for x in payload['utterances']}
        if parsed.get('mentioned') is True and isinstance(refs,list) and not current_ids.intersection(refs):
            diagnostics.append('mentioned_true_but_no_current_meeting_evidence')
        expected=check.get('target')
        fields={k:parsed.get(k)==expected[k] for k in ['issue_id','mentioned','owner','next_due','approval','reviewer']} if expected else {}
    except (ValueError,TypeError,AttributeError,KeyError):
        parsed=None; fields={}; errors.append('invalid_json_or_types')
    if result['hit_token_limit']: errors.append('truncated_generation')
    return {**result,'parsed':parsed,'schema_errors':errors,'diagnostic_flags':diagnostics,'draft_key_field_matches':fields,
        'all_key_fields_match':(bool(fields) and all(fields.values())) if check.get('target') else None}

def run_checks(tokenizer,model,name):
    checks=json.loads((ROOT/'data'/'checks.json').read_text(encoding='utf-8'))
    results=[]
    for check in checks:
        print(f'{name}: {check["id"]}',flush=True)
        output=inspect_result(infer(tokenizer,model,check['messages']),check)
        results.append({'id':check['id'],'group':check['check_group'],**output})
        save_json(RESULTS/f'{name}.json',{'not_final_evaluation':True,'human_reviewed':False,'results':results})
        print(f'  {output["seconds"]}s, schema_errors={output["schema_errors"]}, draft_fields={output["all_key_fields_match"]}',flush=True)
    return results
