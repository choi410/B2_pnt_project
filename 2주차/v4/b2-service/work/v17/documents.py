"""Meeting revisions, document approval, and personal in-app notifications."""
from copy import deepcopy
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field


def ensure_document(m):
 if 'document_status' in m:return m
 m.update(document_status='작성 중',revision=1,original_source=m['source'],original_title=m['title'],original_date=m.get('date',''),approved_revision=None,document_events=[],analysis_stale=False)
 m['revisions']=[{'number':1,'title':m['title'],'date':m.get('date',''),'body':m['source'],'status':'작성 중','saved_by':m['author'],'saved_at':m.get('created_at'),'note':'최초 등록본'}]
 return m


def notify(w,c,recipients,actor,project_id,target_type,target_id,title):
 p=w.read(c,'project',project_id)
 for recipient in set(recipients)-{None,'',actor}:
  if recipient not in p['members']:continue
  w.save(c,'notification',{'id':w.uid(),'recipient':recipient,'actor':actor,'project_id':project_id,'target_type':target_type,'target_id':target_id,'title':title,'created_at':w.now(),'read_at':None})


def meeting_confirmed(w,c,m,actor,task_ids=()):
 """One informational notice per member/revision, including their new assignments."""
 p=w.read(c,'project',m['project_id'])
 key=f"meeting:{m['id']}:confirmed:{m['revision']}"
 existing={n['recipient'] for n in w.all_records(c,'notification') if n.get('event_key')==key}
 tasks=[w.read(c,'task',tid) for tid in task_ids]
 for recipient in set(p['members'])-{actor,None,''}-existing:
  assigned=[t['id'] for t in tasks if (t.get('owner_id') if t['kind']=='업무' else t.get('reviewer_id'))==recipient]
  label='회의록 수정본 확정' if m['revision']>1 else '회의록 확정'
  title=p['name']+' · '+label+' · '+m['title']
  if assigned:title+=' · 내 업무 '+str(len(assigned))+'건 배정'
  w.save(c,'notification',{'id':w.uid(),'recipient':recipient,'actor':actor,'project_id':p['id'],'target_type':'meeting','target_id':m['id'],'title':title,'created_at':w.now(),'read_at':None,'event_key':key,'task_ids':assigned})


def task_notification(w,c,t,actor,event,old_owner=None):
 from work.v17.task_attention import emit
 if event!='reassigned':emit(w,c,t,actor,event)
 if event=='assigned':
  target=t.get('owner_id') if t['kind']=='업무' else t.get('reviewer_id')
  notify(w,c,[target],actor,t['project_id'],'task',t['id'],'업무 배정 · '+t['title'])
 elif event=='reassigned':
  notify(w,c,[old_owner],actor,t['project_id'],'task',t['id'],'담당자 변경 · '+t['title'])
  task_notification(w,c,t,actor,'assigned')
 elif event=='submit':notify(w,c,[t['reviewer_id']],actor,t['project_id'],'task',t['id'],'완료 검토 요청 · '+t['title'])
 elif event in ('approve','return','reopen'):
  label={'approve':'업무 완료 승인','return':'업무 보완 요청','reopen':'업무 재확인 요청'}[event]
  notify(w,c,[t.get('owner_id')],actor,t['project_id'],'task',t['id'],label+' · '+t['title'])
 elif event=='withdraw':notify(w,c,[t['reviewer_id']],actor,t['project_id'],'task',t['id'],'완료 검토 요청 회수 · '+t['title'])


def save_content(w,m,actor,title,day,body):
 from work.v17.intake_review import active
 active(m)
 ensure_document(m)
 if m['analysis_state'] in ('queued','running'):raise HTTPException(409,'AI 분석이 끝난 뒤 본문을 수정해 주세요.')
 if not title.strip():raise HTTPException(422,'회의 제목을 입력해 주세요.')
 if len(body.strip())<10:raise HTTPException(422,'회의 내용을 10자 이상 작성해 주세요.')
 day=w.due(day) or ''
 title=title.strip();body=body.strip()
 if (m['title'],m.get('date',''),m['source'])==(title,day,body):return False
 body_changed=m['source']!=body
 m.update(title=title,date=day,source=body,revision=m['revision']+1,document_status='작성 중',version=m['version']+1)
 if body_changed:
  from server import lines
  prior={x['id']:x['text'] for x in m['lines']};m['lines']=lines(body)
  for cand in m['candidates']:
   if cand['state']=='applied':continue
   cand['previous_evidence']=[prior.get(x,'') for x in cand.get('evidence',[])]
   cand['evidence']=[];cand['needs_recheck']=True
  m['analysis_stale']=any(x['state']=='draft' for x in m['candidates'])
 m['revisions'].append({'number':m['revision'],'title':title,'date':day,'body':body,'status':'작성 중','saved_by':actor['id'],'saved_at':w.now(),'note':'웹에서 수정'})
 m['document_events'].append({'at':w.now(),'actor':actor['id'],'action':'수정본 저장','revision':m['revision'],'note':''})
 return True


class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Content(Strict):
 version:int
 title:str=Field(min_length=1,max_length=240)
 meeting_date:str|None=None
 body:str=Field(min_length=10,max_length=20000)
class Decision(Strict):
 version:int
 action:str
 note:str=Field(default='',max_length=3000)
 changes:list[dict]=Field(default_factory=list,max_length=100)
 candidates:list[dict]|None=None
 selected:list[str]=Field(default_factory=list,max_length=30)
class ImportDraft(Strict):
 version:int=1
 title:str=Field(default='',max_length=240)
 meeting_date:str|None=None
 body:str=Field(min_length=10,max_length=20000)
 project_id:str|None=None
 review_bundle:dict|None=None
 review_confirmed:bool=False
class ReadNotices(Strict):ids:list[str]=[];all:bool=False
class DeleteNotices(Strict):ids:list[str]=Field(default_factory=list,max_length=100);read_only:bool=False
class RestoreNotices(Strict):ids:list[str]=Field(default_factory=list,max_length=100)


def build_router(w):
 router=APIRouter(prefix='/api')
 @router.patch('/meeting-imports/{iid}')
 def draft(iid,body:ImportDraft,actor=Depends(w.user)):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');d=w.read(c,'import',iid)
   if d['actor_id']!=actor['id']:raise HTTPException(403,'본인의 임시 저장본만 수정할 수 있습니다.')
   if d.get('chosen_project'):w.project(c,d['chosen_project'],actor)
   from work.v17.intake_review import active,validate_bundle,source_hash
   active(d)
   if d.get('analysis_state') in ('running','queued'):raise HTTPException(409,'분석이 끝난 뒤 수정해 주세요.')
   if d.get('meeting_id'):raise HTTPException(409,'이미 등록되었습니다. 회의록에서 수정해 주세요.')
   if d.get('draft_version',1)!=body.version:raise HTTPException(409,'다른 변경이 먼저 저장되었습니다. 다시 열어 주세요.')
   p=w.project(c,body.project_id,actor) if body.project_id else None
   if len(body.body.strip())<10:raise HTTPException(422,'회의 내용을 10자 이상 작성해 주세요.')
   text=body.body.replace('\r\n','\n').replace('\r','\n').strip()
   bundle=validate_bundle(w,body.review_bundle or {},text,p)
   d.update(title=body.title.strip(),meeting_date=w.due(body.meeting_date) or '',edited_body=text,chosen_project=body.project_id or '',draft_version=body.version+1,review_bundle=bundle,review_confirmed=body.review_confirmed,review_hash=source_hash(text) if body.review_confirmed else None)
   w.save(c,'import',d)
  return {'ok':True,'version':d['draft_version']}

 @router.patch('/meetings/{mid}/content')
 def content(mid,body:Content,actor=Depends(w.user)):
  from work.v17.registration_policy import mark_registered,registration_notice
  from work.v17.changes import prepare_scan,submit_scan
  job=None
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');m=w.read(c,'meeting',mid);p=w.project(c,m['project_id'],actor);w.version(m,body.version)
   if actor['id'] not in (m['author'],p['pm']):raise HTTPException(403,'작성자 또는 프로젝트 PM이 수정할 수 있습니다.')
   if save_content(w,m,actor,body.title,body.meeting_date,body.body):
    mark_registered(w,m,actor);job=prepare_scan(w,m)
    registration_notice(w,c,m,actor['id'])
   w.save(c,'meeting',m)
  if job:submit_scan(w,mid,job)
  return {'id':mid,'version':m['version'],'revision':m['revision']}

 @router.post('/meetings/{mid}/document-action')
 def action(mid,body:Decision,actor=Depends(w.user)):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');m=w.read(c,'meeting',mid);p=w.project(c,m['project_id'],actor);w.version(m,body.version);ensure_document(m)
   from work.v17.intake_review import active
   active(m)
   a=body.action;s=m['document_status'];note=body.note.strip()
   if body.candidates is not None or body.selected or body.changes:raise HTTPException(422,'문서 검토와 업무 배정·변경 반영은 별도입니다. 업무 또는 변경이력에서 처리해 주세요.')
   if a in ('submit','withdraw'):
    if actor['id'] not in (m['author'],p['pm']):raise HTTPException(403,'작성자 또는 프로젝트 PM이 처리할 수 있습니다.')
    if a=='submit':
     if s not in ('등록 완료','작성 중','보완 요청'):raise HTTPException(409,'검토를 요청할 수 없는 문서 상태입니다.')
     m['document_status']='검토 대기';recipients=[p['pm']];label='회의록 검토 요청'
    else:
     if s!='검토 대기':raise HTTPException(409,'검토 대기 중인 회의록만 회수할 수 있습니다.')
     m['document_status']='등록 완료' if m.get('registered_revision')==m['revision'] else '작성 중';recipients=[p['pm']];label='회의록 검토 요청 회수'
   elif a=='confirm':
    if actor['id']!=p['pm'] or m['author']!=actor['id']:raise HTTPException(403,'해당 프로젝트 PM이 직접 작성한 회의록만 바로 확정할 수 있습니다.')
    if s not in ('등록 완료','작성 중','보완 요청'):raise HTTPException(409,'검토 요청 중이면 먼저 요청을 회수해 주세요.')
    m.update(document_status='확정',approved_revision=m['revision']);recipients=[];label='PM 직접 확정'
   elif a in ('approve','return'):
    w.project(c,m['project_id'],actor,True)
    if s!='검토 대기':raise HTTPException(409,'검토 요청된 회의록만 승인·보완 처리할 수 있습니다.')
    if a=='return' and not note:raise HTTPException(422,'보완이 필요한 내용을 입력해 주세요.')
    m['document_status']='확정' if a=='approve' else '보완 요청';recipients=[m['author']];label='회의록 승인' if a=='approve' else '회의록 보완 요청'
    if a=='approve':m['approved_revision']=m['revision']
   else:raise HTTPException(422,'지원하지 않는 동작입니다.')
   m['revisions'][-1].update(status=m['document_status'],reviewed_by=actor['id'],reviewed_at=w.now())
   m['document_events'].append({'at':w.now(),'actor':actor['id'],'action':label,'revision':m['revision'],'note':note})
   m['version']+=1;w.save(c,'meeting',m)
   made=[]
   if a in ('confirm','approve'):
    notify(w,c,[m['author']],actor['id'],m['project_id'],'meeting',mid,'회의록 검토 완료 · '+m['title'])
   else:notify(w,c,recipients,actor['id'],m['project_id'],'meeting',mid,label+' · '+m['title'])
  return {'ok':True,'status':m['document_status'],'created':made}

 @router.get('/notifications')
 def notifications(actor=Depends(w.user)):
  with w.connect() as c:
   projects={p['id'] for p in w.all_records(c,'project') if actor['id'] in p['members']}
   ns=[n for n in w.all_records(c,'notification') if n['recipient']==actor['id'] and (n['project_id'] in projects or n.get('target_type')=='cooperation') and not n.get('deleted_at')]
   ns.sort(key=lambda n:(n['created_at'],n['id']),reverse=True)
  return {'items':ns[:100],'unread':sum(not n['read_at'] for n in ns)}

 @router.post('/notifications/read')
 def mark_read(body:ReadNotices,actor=Depends(w.user)):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   for n in w.all_records(c,'notification'):
    if n['recipient']==actor['id'] and not n.get('deleted_at') and (body.all or n['id'] in body.ids):
     if not n['read_at']:n['read_at']=w.now();w.save(c,'notification',n)
  return {'ok':True}
 @router.post('/notifications/delete')
 def delete_notices(body:DeleteNotices,actor=Depends(w.user)):
  removed=[]
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   for n in w.all_records(c,'notification'):
    if n['recipient']==actor['id'] and not n.get('deleted_at') and (n['id'] in body.ids or body.read_only and n.get('read_at')):
     n['deleted_at']=w.now();w.save(c,'notification',n);removed.append(n['id'])
  return {'ids':removed}
 @router.post('/notifications/restore')
 def restore_notices(body:RestoreNotices,actor=Depends(w.user)):
  restored=[]
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   for n in w.all_records(c,'notification'):
    if n['recipient']==actor['id'] and n.get('deleted_at') and n['id'] in body.ids:
     n.pop('deleted_at',None);w.save(c,'notification',n);restored.append(n['id'])
  return {'ids':restored}
 return router
