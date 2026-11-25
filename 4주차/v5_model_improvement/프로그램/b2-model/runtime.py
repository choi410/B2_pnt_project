from pathlib import Path
import os
for key in ['HF_HUB_DISABLE_TELEMETRY','DO_NOT_TRACK','WANDB_DISABLED']:
    os.environ[key]='1'
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'

import json
import re
import time
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'models'/'base'
RESULTS=ROOT/'results'
RESULTS.mkdir(exist_ok=True)

def save_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

# --- llama.cpp engine -------------------------------------------------------
# start.py launches llama-server (CUDA) and sets B2_ENGINE_URL. The proxy below keeps the
# transformers generate() contract the service already uses: the same chat-template token
# ids go in, greedy output token ids come back, so prompts and callers stay unchanged.
ENGINE_URL=os.environ.get('B2_ENGINE_URL','').rstrip('/')

try:
    # Callers build lm-format-enforcer filters from a JSON schema; remember that schema on
    # the returned filter so llama.cpp can enforce the same structure with its own grammar.
    from lmformatenforcer import JsonSchemaParser as _Parser
    import lmformatenforcer.integrations.transformers as _lfe
    _parser_init=_Parser.__init__
    def _remember_schema(self,json_schema,*args,**kwargs):
        _parser_init(self,json_schema,*args,**kwargs)
        self._b2_schema=json_schema
    _Parser.__init__=_remember_schema
    _build_filter=_lfe.build_transformers_prefix_allowed_tokens_fn
    def _filter_with_schema(tokenizer_data,parser,*args,**kwargs):
        fn=_build_filter(tokenizer_data,parser,*args,**kwargs)
        try:fn._b2_schema=getattr(parser,'_b2_schema',None)
        except AttributeError:pass
        return fn
    _lfe.build_transformers_prefix_allowed_tokens_fn=_filter_with_schema
except Exception:
    pass

def _relax(schema):
    # Length limits make the grammar huge and slow; callers already validate lengths.
    if isinstance(schema,dict):return {k:_relax(v) for k,v in schema.items() if k not in ('minLength','maxLength')}
    if isinstance(schema,list):return [_relax(v) for v in schema]
    return schema

def engine_ready(url=None,timeout=1.5):
    import urllib.request
    url=(url or ENGINE_URL).rstrip('/')
    if not url:return False
    try:
        with urllib.request.urlopen(url+'/health',timeout=timeout) as res:return res.status==200
    except Exception:
        return False

_CHATML=re.compile(r'<\|im_start\|>(system|user|assistant)\n(.*?)<\|im_end\|>',re.S)

# The engine recomputes every prompt instead of reusing a slot's state from an earlier request:
# with reuse, the same minutes gave different records from one analysis to the next (free-form
# consistency 67% -> 100% without it, same speed). B2_ENGINE_CACHE_PROMPT=1 turns reuse back on.
_CACHE_PROMPT=__import__('os').environ.get('B2_ENGINE_CACHE_PROMPT','0')=='1'

class LlamaModel:
    """Minimal stand-in for AutoModelForCausalLM.generate() backed by llama-server.

    Same tokenizer family as models/base (the 4B model): token ids go in and come back
    unchanged. Another model family (different vocabulary, e.g. Qwen3.6 or Gemma): the
    prompt is turned back into chat messages and sent to /v1/chat/completions, so the
    engine applies that model's own chat template (with thinking off); the answer text is
    re-encoded so callers keep decoding output[0, len(input):] as before."""
    engine='llama.cpp'
    def __init__(self,url,tokenizer=None):
        import threading
        self.url=url
        self.tokenizer=tokenizer
        self._chat=None
        self._fallback=None
        self._fallback_lock=threading.Lock()  # the in-process model is not thread-safe
    def eval(self):return self
    def chat_mode(self):
        if self._chat is None:
            forced=os.environ.get('B2_ENGINE_MODE','').lower()
            if forced in ('chat','tokens'):self._chat=forced=='chat'
            else:
                import urllib.request
                try:
                    with urllib.request.urlopen(self.url+'/v1/models',timeout=5) as res:
                        n_vocab=int(json.load(res)['data'][0]['meta']['n_vocab'])
                    self._chat=self.tokenizer is not None and abs(n_vocab-len(self.tokenizer))>2048
                except Exception:
                    self._chat=False
        return self._chat
    def _chat_request(self,input_ids,max_new_tokens,schema):
        text=self.tokenizer.decode(input_ids[0].tolist(),skip_special_tokens=False)
        messages=[{'role':r,'content':c} for r,c in _CHATML.findall(text)]
        if not messages:raise ValueError('AI 엔진에 보낼 대화 형식을 만들지 못했습니다.')
        body={'messages':messages,'max_tokens':int(max_new_tokens),'temperature':0,'top_k':1,'cache_prompt':_CACHE_PROMPT,
              'stream':False,'chat_template_kwargs':{'enable_thinking':False}}
        if schema:body['response_format']={'type':'json_schema','json_schema':{'name':'result','schema':_relax(schema)}}
        return '/v1/chat/completions',body
    def generate(self,input_ids,max_new_tokens=512,streamer=None,prefix_allowed_tokens_fn=None,**_ignored):
        import urllib.request,urllib.error
        prompt=input_ids[0].tolist()
        schema=getattr(prefix_allowed_tokens_fn,'_b2_schema',None)
        if self.chat_mode():
            path,body=self._chat_request(input_ids,max_new_tokens,schema)
            if streamer is not None:streamer.put(input_ids.cpu())
            try:
                req=urllib.request.Request(self.url+path,data=json.dumps(body,ensure_ascii=False).encode('utf-8'),headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=900) as res:result=json.loads(res.read().decode('utf-8'))
            except urllib.error.HTTPError as exc:
                detail=exc.read().decode('utf-8','replace')[:300]
                if 'context' in detail.lower():raise ValueError('분석 가능한 길이를 넘었습니다. 회의 안건을 나누어 등록해 주세요.')
                raise ValueError('AI 엔진(llama.cpp)이 요청을 처리하지 못했습니다. '+detail)
            content=(result['choices'][0]['message'].get('content') or '')
            content=re.sub(r'<think>.*?</think>','',content,flags=re.S).strip()
            generated=self.tokenizer.encode(content,add_special_tokens=False)+[self.tokenizer.eos_token_id]
            if streamer is not None:streamer.put(torch.tensor(generated));streamer.end()
            return torch.tensor([prompt+generated],dtype=input_ids.dtype).to(input_ids.device)
        # Non-streaming on purpose: streamed chunks hold back tokens that end mid UTF-8
        # character (most Korean syllables span tokens), which corrupted generated text.
        body={'prompt':prompt,'n_predict':int(max_new_tokens),'temperature':0,'top_k':1,
              'cache_prompt':_CACHE_PROMPT,'return_tokens':True,'stream':False}
        if schema:body['json_schema']=_relax(schema)
        req=urllib.request.Request(self.url+'/completion',data=json.dumps(body,ensure_ascii=False).encode('utf-8'),
                                   headers={'Content-Type':'application/json'})
        generated=[]
        if streamer is not None:streamer.put(input_ids.cpu())
        try:
            with urllib.request.urlopen(req,timeout=900) as res:
                result=json.loads(res.read().decode('utf-8'))
            generated=[int(t) for t in result.get('tokens') or []]
            if generated and streamer is not None:streamer.put(torch.tensor(generated))
        except urllib.error.HTTPError as exc:
            detail=exc.read().decode('utf-8','replace')[:300]
            if 'context' in detail.lower():raise ValueError('분석 가능한 길이를 넘었습니다. 회의 안건을 나누어 등록해 주세요.')
            raise ValueError('AI 엔진(llama.cpp)이 요청을 처리하지 못했습니다. '+detail)
        except (urllib.error.URLError,OSError):
            # Engine window closed or crashed: continue on the in-process model instead.
            with self._fallback_lock:
                if self._fallback is None:self._fallback=_load_transformers()
                return self._fallback.generate(input_ids=input_ids,max_new_tokens=max_new_tokens,streamer=streamer,
                                               prefix_allowed_tokens_fn=prefix_allowed_tokens_fn,**_ignored)
        if streamer is not None:streamer.end()
        out=torch.tensor([prompt+generated],dtype=input_ids.dtype)
        return out.to(input_ids.device)

def _load_tokenizer():
    tokenizer=AutoTokenizer.from_pretrained(BASE,local_files_only=True,trust_remote_code=False)
    tokenizer.pad_token=tokenizer.eos_token
    return tokenizer

ACTIVE_LABEL={'value':'Qwen3-4B-Instruct-2507'}

def model_label():
    """Name of the model the last load_base() connected to, for analysis records."""
    return ACTIVE_LABEL['value']

def _engine_label(url):
    import urllib.request
    try:
        with urllib.request.urlopen(url+'/v1/models',timeout=5) as res:
            name=Path(json.load(res)['data'][0]['id']).stem
        return re.sub(r'-(UD-)?(Q\d\w*|IQ\d\w*|BF16|F16|MXFP4\w*)$','',name)+' · llama.cpp'
    except Exception:
        return 'llama.cpp'

def load_base():
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA GPU is required for this experiment.')
    tokenizer=_load_tokenizer()
    if ENGINE_URL and engine_ready(timeout=3):
        ACTIVE_LABEL['value']=_engine_label(ENGINE_URL)
        return tokenizer,LlamaModel(ENGINE_URL,tokenizer)
    ACTIVE_LABEL['value']='Qwen3-4B-Instruct-2507 · transformers'
    return tokenizer,_load_transformers()

def _load_transformers():
    model=AutoModelForCausalLM.from_pretrained(BASE,local_files_only=True,trust_remote_code=False,
        dtype=torch.bfloat16,device_map={'':0},attn_implementation='sdpa',low_cpu_mem_usage=True)
    # bitsandbytes 4bit dequantizes on every token, which roughly halves decode speed.
    # On GPUs with room for full bf16 weights (~10GB incl. cache), unpack once at load.
    # Set B2_MODEL_PRECISION=4bit to keep the original 4bit weights.
    total_gb=torch.cuda.get_device_properties(0).total_memory/1024**3
    if os.environ.get('B2_MODEL_PRECISION','').lower()!='4bit' and total_gb>=16 \
            and getattr(model,'is_loaded_in_4bit',False):
        model=model.dequantize().to(torch.bfloat16)
        torch.cuda.empty_cache()
    model.generation_config.do_sample=False
    model.generation_config.temperature=None
    model.generation_config.top_p=None
    model.generation_config.top_k=None
    model.eval()
    return model

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
