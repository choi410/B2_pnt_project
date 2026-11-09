"""Per-user list attention, deliberately independent of notification read state."""
import hashlib
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field


def marker_id(task_id,user_id,bucket):
 return hashlib.sha256('\0'.join((task_id,user_id,bucket)).encode()).hexdigest()


def emit(w,c,t,actor,event):
 if event not in ('assigned','reassigned','return','reopen','submit'):return
 p=w.read(c,'project',t['project_id'])
 bucket='review' if event=='submit' else 'mine'
 owner=t.get('reviewer_id') if t['kind']=='확인사항' else t.get('owner_id')
 recipients={t.get('reviewer_id'),p['pm']} if bucket=='review' else {owner}
 for user_id in recipients.intersection(p['members'])-{actor,None,t.get('owner_id') if bucket=='review' else None}:
  record={'id':marker_id(t['id'],user_id,bucket),'task_id':t['id'],'user_id':user_id,'project_id':p['id'],
          'bucket':bucket,'token':w.uid(),'event':event,'created_at':w.now(),'seen_token':None}
  w.save(c,'task_attention',record)


def visible_tokens(w,c,actor,tasks,projects):
 ts={t['id']:t for t in tasks};ps={p['id']:p for p in projects};result={}
 for record in w.all_records(c,'task_attention'):
  if record['user_id']!=actor['id'] or record.get('seen_token')==record['token']:continue
  t=ts.get(record['task_id'])
  if not t or t['status']=='완료' or t['project_id'] not in ps:continue
  own=t.get('owner_id')==actor['id'] or t['kind']=='확인사항' and t.get('reviewer_id')==actor['id']
  review=t['kind']=='업무' and t['status']=='검토대기' and t.get('owner_id')!=actor['id'] and actor['id'] in (t.get('reviewer_id'),ps[t['project_id']]['pm'])
  if record['bucket']=='mine' and own or record['bucket']=='review' and review:
   result.setdefault(t['id'],{})[record['bucket']]=record['token']
 return result


class Seen(BaseModel):
 model_config=ConfigDict(extra='forbid')
 tokens:dict[str,str]=Field(default_factory=dict,max_length=2)


def build_router(w):
 r=APIRouter(prefix='/api')
 @r.post('/tasks/{tid}/seen')
 def seen(tid,body:Seen,actor=Depends(w.user)):
  if any(k not in ('mine','review') or len(v)>64 for k,v in body.tokens.items()):raise HTTPException(422,'확인할 업무 표시를 다시 불러와 주세요.')
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');t=w.read(c,'task',tid);w.project(c,t['project_id'],actor)
   for bucket,token in body.tokens.items():
    ident=marker_id(tid,actor['id'],bucket)
    found=c.execute("SELECT 1 FROM records WHERE kind='task_attention' AND id=?",(ident,)).fetchone()
    if not found:continue
    record=w.read(c,'task_attention',ident)
    # A request received while the detail is open must remain new.
    if record['token']==token and record.get('seen_token')!=token:
     record.update(seen_token=token,seen_at=w.now());w.save(c,'task_attention',record)
  return {'ok':True}
 return r
