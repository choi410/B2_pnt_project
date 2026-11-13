"""Project context and reviewed, source-bound task instruction drafts."""
import hashlib,json
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from work.v17.features import revision_source,source_lines

def fingerprint(source):return hashlib.sha256(json.dumps(source,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def sources(w,c,kind,record):
 if kind=='task':
  if not record.get('meeting_id'):raise HTTPException(422,'연결된 회의록이 없습니다. 해야 할 일을 직접 작성해 주세요.')
  m=w.read(c,'meeting',record['meeting_id'])
  text=revision_source(m,record.get('source_revision',1))
  return [{'id':x['id'],'text':x['text']} for x in source_lines(text)]
 from work.v17.retrieval import registered_document
 meetings=sorted([m for m in w.all_records(c,'meeting') if m['project_id']==record['id'] and registered_document(m)],key=lambda m:(m.get('date',''),m['created_at']),reverse=True)[:5]
 result=[];budget=0
 for m in meetings:
  doc=registered_document(m)
  for x in source_lines(doc['body']):
   if budget+len(x['text'])>14000:break
   result.append({'id':m['id']+':'+x['id'],'text':x['text'],'meeting_id':m['id'],'title':doc['title'],'date':doc.get('date'),'revision':doc['revision']})
   budget+=len(x['text'])
 if not result:raise HTTPException(422,'등록된 회의록이 없습니다. 프로젝트 개요를 직접 작성해 주세요.')
 return result

def worker(w,jid):
 try:
  with w.AI_LOCK:
   with w.connect() as c:
    job=w.read(c,'context_draft',jid);job['state']='running';w.save(c,'context_draft',job)
   from work.v17.context_ai import generate
   result=generate(job['kind'],job['sources'],job.get('title',''))
   with w.connect() as c:
    c.execute('BEGIN IMMEDIATE');job=w.read(c,'context_draft',jid);job.update(state='ready',result=result);w.save(c,'context_draft',job)
 except Exception as e:
  with w.connect() as c:
   job=w.read(c,'context_draft',jid);job.update(state='failed',error=str(getattr(e,'detail',e))[:350]);w.save(c,'context_draft',job)

class Overview(BaseModel):
 model_config=ConfigDict(extra='forbid')
 version:int
 purpose:str=Field(default='',max_length=2000)
 scope:str=Field(default='',max_length=4000)
 next_goal:str=Field(default='',max_length=2000)
 stages:list[str]=Field(default_factory=list,max_length=12)
 current_stage:str=Field(default='',max_length=80)
 customer:str=Field(default='',max_length=200)
 equipment:str=Field(default='',max_length=200)
 start_date:str=Field(default='',max_length=10)
 due_date:str=Field(default='',max_length=10)

def build_router(w):
 r=APIRouter(prefix='/api')
 @r.get('/context-drafts/latest/{kind}/{rid}')
 def latest(kind,rid,actor=Depends(w.user)):
  if kind not in ('task','project'):raise HTTPException(404)
  with w.connect() as c:
   record=w.read(c,kind,rid);w.project(c,record['project_id'] if kind=='task' else rid,actor,True)
   rows=[j for j in w.all_records(c,'context_draft') if j['kind']==kind and j['record_id']==rid and j['actor']==actor['id']]
   return max(rows,key=lambda j:j['created_at']) if rows else None
 @r.get('/projects/{pid}/overview')
 def get_overview(pid,actor=Depends(w.user)):
  with w.connect() as c:
   p=w.project(c,pid,actor)
   return p.get('overview') or {'version':1,'purpose':'','scope':'','next_goal':'','stages':[],'current_stage':''}
 @r.patch('/projects/{pid}/overview')
 def save_overview(pid,body:Overview,actor=Depends(w.user)):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');p=w.project(c,pid,actor,True);old=p.get('overview') or {'version':1};w.version(old,body.version)
   stages=[s.strip() for s in body.stages]
   if any(not s or len(s)>80 for s in stages) or len(stages)!=len(set(stages)) or (body.current_stage and body.current_stage not in stages):raise HTTPException(422,'단계 이름은 중복 없이 작성하고 현재 단계를 목록에서 골라 주세요.')
   # Older clients may omit new descriptive fields; preserve already saved values.
   metadata={key:(getattr(body,key) if key in body.model_fields_set else old.get(key,'')) for key in ('customer','equipment','start_date','due_date')}
   metadata['start_date']=w.due(metadata['start_date']) or '';metadata['due_date']=w.due(metadata['due_date']) or ''
   if metadata['start_date'] and metadata['due_date'] and metadata['start_date']>metadata['due_date']:raise HTTPException(422,'착수일은 납기일보다 늦을 수 없습니다.')
   metadata['customer']=metadata['customer'].strip();metadata['equipment']=metadata['equipment'].strip()
   p['overview']={**body.model_dump(),**metadata,'stages':stages,'version':body.version+1,'updated_by':actor['id'],'updated_at':w.now()}
   w.save(c,'project',p);return p['overview']
 @r.post('/context-drafts/{kind}/{rid}',status_code=202)
 def start(kind,rid,actor=Depends(w.user)):
  if kind not in ('task','project'):raise HTTPException(404)
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');record=w.read(c,kind,rid);p=w.project(c,record['project_id'] if kind=='task' else rid,actor,True)
   if kind=='task' and record['status']=='완료':raise HTTPException(409,'완료된 업무는 수정할 수 없습니다.')
   jobs=w.all_records(c,'context_draft')
   if any(j['actor']==actor['id'] and j['state'] in ('queued','running') for j in jobs):raise HTTPException(409,'요청한 초안을 준비 중입니다. 잠시 기다려 주세요.')
   pending=sum(j['state'] in ('queued','running') for j in jobs)+sum(x.get('analysis_state') in ('queued','running') for k in ('meeting','import') for x in w.all_records(c,k))
   if pending>=8:raise HTTPException(429,'분석 대기가 많습니다. 잠시 후 시도해 주세요.')
   source=sources(w,c,kind,record)
   job={'id':w.uid(),'kind':kind,'record_id':rid,'project_id':p['id'],'title':record.get('title',''),'actor':actor['id'],'state':'queued','sources':source,'fingerprint':fingerprint(source),'created_at':w.now()}
   w.save(c,'context_draft',job)
  w.POOL.submit(worker,w,job['id']);return job
 @r.get('/context-drafts/{jid}')
 def result(jid,actor=Depends(w.user)):
  with w.connect() as c:
   job=w.read(c,'context_draft',jid)
   if job['actor']!=actor['id']:raise HTTPException(403)
   w.project(c,job['project_id'],actor,True)
   try:job['stale']=fingerprint(sources(w,c,job['kind'],w.read(c,job['kind'],job['record_id'])))!=job['fingerprint']
   except HTTPException:job['stale']=True
   if job['kind']=='task' and w.read(c,'task',job['record_id'])['title']!=job.get('title'):job['stale']=True
   return job
 return r
