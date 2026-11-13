"""llama.cpp(llama-server) 연결. 서버가 켜져 있으면 그쪽으로 생성하고, 없으면 호출한 쪽이 기존 엔진을 그대로 쓴다."""
import json,os,time,urllib.request,urllib.error

URL=os.environ.get('B2_LLAMA_URL','http://127.0.0.1:8080').rstrip('/')
MODEL_LABEL='Qwen3-4B-Instruct-2507 · GGUF 4bit · llama.cpp'
_state={'checked':0.0,'ok':False}

def available():
 if os.environ.get('B2_LLAMA_DISABLE'):return False
 now=time.time()
 if now-_state['checked']<5:return _state['ok']
 try:
  with urllib.request.urlopen(URL+'/health',timeout=1.5) as res:ok=res.status==200
 except Exception:ok=False
 _state.update(checked=now,ok=ok)
 return ok

def _relax(schema):
 # 길이 제한은 문법을 크게 만들어 느려질 수 있다. 구조·선택지만 강제하고 길이는 기존 후처리가 검사한다.
 if isinstance(schema,dict):return {k:_relax(v) for k,v in schema.items() if k not in ('minLength','maxLength')}
 if isinstance(schema,list):return [_relax(v) for v in schema]
 return schema

def _run(messages,max_tokens,schema,on_text):
 body={'messages':messages,'max_tokens':max_tokens,'temperature':0,'stream':True,'stream_options':{'include_usage':True},'cache_prompt':True}
 if schema:body['response_format']={'type':'json_schema','json_schema':{'name':'result','schema':_relax(schema)}}
 req=urllib.request.Request(URL+'/v1/chat/completions',data=json.dumps(body,ensure_ascii=False).encode('utf-8'),headers={'Content-Type':'application/json'})
 started=time.perf_counter();first=None;parts=[];usage={};timings={};shown=0
 with urllib.request.urlopen(req,timeout=900) as res:
  for line in res:
   line=line.decode('utf-8','replace').strip()
   if not line.startswith('data:'):continue
   data=line[5:].strip()
   if data=='[DONE]':break
   try:chunk=json.loads(data)
   except ValueError:continue
   if chunk.get('usage'):usage=chunk['usage']
   if chunk.get('timings'):timings=chunk['timings']
   for choice in chunk.get('choices') or []:
    piece=(choice.get('delta') or {}).get('content')
    if piece:
     if first is None:first=time.perf_counter()-started
     parts.append(piece)
   if on_text and len(parts)-shown>=12:
    shown=len(parts)
    try:on_text(''.join(parts),len(parts))
    except Exception:pass
 return ''.join(parts),{'seconds':time.perf_counter()-started,'first_token_seconds':first or 0,'input_tokens':int(usage.get('prompt_tokens') or 0),'output_tokens':int(usage.get('completion_tokens') or len(parts)),'tokens_per_second':timings.get('predicted_per_second'),'schema_enforced':bool(schema)}

def chat(messages,max_tokens,schema=None,on_text=None):
 """생성한 글과 측정값을 돌려준다. 형식 강제를 서버가 거부하면 프롬프트 지시만으로 다시 시도한다."""
 try:return _run(messages,max_tokens,schema,on_text)
 except urllib.error.HTTPError as exc:
  detail=exc.read().decode('utf-8','replace')[:300]
  if exc.code==400 and schema:
   try:return _run(messages,max_tokens,None,on_text)
   except urllib.error.HTTPError as again:detail=again.read().decode('utf-8','replace')[:300]
  if 'context' in detail.lower():raise ValueError('분석 가능한 길이를 넘었습니다. 회의 안건을 나누어 등록해 주세요.')
  raise ValueError('AI 서버(llama.cpp)가 요청을 처리하지 못했습니다. '+detail)
 except (urllib.error.URLError,OSError) as exc:
  _state.update(checked=0.0,ok=False)
  raise ValueError('AI 서버(llama.cpp)에 연결하지 못했습니다. 서버 창이 켜져 있는지 확인해 주세요. '+str(exc)[:120])
