"""Document registration and task assignment are separate, auditable actions."""
from copy import deepcopy
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

POLICY = 'author-registration-v1'

def mark_registered(w, m, actor):
 stamp = w.now()
 m.update(registration_policy=POLICY, document_status='등록 완료',
          registered_revision=m['revision'], registered_by=actor['id'], registered_at=stamp)
 m['revisions'][-1].update(status='등록 완료', registered=True,
                         registered_by=actor['id'], registered_at=stamp)

def registration_notice(w, c, m, actor, task_ids=(), requested=()):
 """One meeting-level notice; candidates alone do not create review alerts."""
 p = w.read(c, 'project', m['project_id'])
 key = f"meeting:{m['id']}:registered:{m['revision']}"
 notified = {n['recipient'] for n in w.all_records(c,'notification') if n.get('event_key') == key}
 tasks = [w.read(c,'task',tid) for tid in task_ids]
 for recipient in set(p['members']) - {actor, None, ''} - notified:
  assigned = [t['id'] for t in tasks if (t.get('reviewer_id') if t['kind']=='확인사항' else t.get('owner_id')) == recipient]
  request = recipient == p['pm'] and bool(requested)
  title = p['name'] + (' · 회의록 수정본 등록 · ' if m['revision']>1 else ' · 회의록 등록 · ') + m['title']
  if request: title += f' · 업무 배정 요청 {len(requested)}건'
  if assigned: title += f' · 내 업무 {len(assigned)}건 배정'
  w.save(c,'notification',{'id':w.uid(),'recipient':recipient,'actor':actor,'project_id':p['id'],
   'target_type':'assignment_request' if request else 'meeting','target_id':m['id'],
   'title':title,'created_at':w.now(),'read_at':None,'event_key':key,'task_ids':assigned})

def request_assignments(w,c,m,p,selected,actor,notify=True):
 candidates={x['id']:x for x in m['candidates']}
 if len(selected)!=len(set(selected)) or any(x not in candidates or candidates[x]['state']!='draft' for x in selected):
  raise HTTPException(422,'요청할 업무 제안을 다시 선택해 주세요.')
 if not selected: return
 for cid in selected:
  item=candidates[cid]
  if not item.get('title','').strip() or not item.get('evidence') or item.get('needs_recheck'):
   raise HTTPException(422,'요청할 업무의 내용과 현재 원문 근거를 확인해 주세요.')
 fresh=[cid for cid in selected if not candidates[cid].get('assignment_requested_by')]
 for cid in fresh:
  candidates[cid].update(assignment_requested_by=actor['id'],assignment_requested_at=w.now())
 m['requested_task_ids']=list(dict.fromkeys([*m.get('requested_task_ids',[]),*selected]))
 w.save(c,'meeting',m)
 if notify and fresh:
  from work.v17.documents import notify as send
  send(w,c,[p['pm']],actor['id'],p['id'],'assignment_request',m['id'],
       f'업무 배정 요청 {len(fresh)}건 · '+m['title'])

class AssignmentRequest(BaseModel):
 model_config=ConfigDict(extra='forbid')
 version:int
 candidates:list[dict]=Field(max_length=30)
 selected:list[str]=Field(default_factory=list,max_length=30)

def build_router(w):
 r=APIRouter(prefix='/api')
 @r.get('/work-proposals')
 def proposals(project_id:str|None=None,meeting_id:str|None=None,actor=Depends(w.user)):
  with w.connect() as c:
   projects={p['id']:p for p in w.all_records(c,'project') if actor['id'] in p['members']}
   if project_id: projects={project_id:w.project(c,project_id,actor)}
   if meeting_id:
    meeting=w.read(c,'meeting',meeting_id);w.project(c,meeting['project_id'],actor)
   rows=[]
   for m in w.all_records(c,'meeting'):
    if m['project_id'] not in projects or m.get('deleted_at') or meeting_id and m['id']!=meeting_id: continue
    candidates=[x for x in m.get('candidates',[]) if x['state']=='draft']
    if not candidates: continue
    rows.append({k:m.get(k) for k in ('id','title','date','project_id','author','version','document_status','revision')} |
     {'pending':len(candidates),'requested':sum(bool(x.get('assignment_requested_by')) or x['id'] in m.get('requested_task_ids',[]) for x in candidates),
      'can_edit':actor['id'] in (m['author'],projects[m['project_id']]['pm']),
      'candidates':deepcopy(candidates)})
   return sorted(rows,key=lambda m:(-m['requested'],m.get('date') or ''),reverse=False)
 @r.post('/meetings/{mid}/assignment-request')
 def request(mid,body:AssignmentRequest,actor=Depends(w.user)):
  from work.v17.intake_review import active
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');m=w.read(c,'meeting',mid);p=w.project(c,m['project_id'],actor);active(m);w.version(m,body.version)
   if actor['id'] not in (m['author'],p['pm']):raise HTTPException(403,'작성자 또는 프로젝트 PM이 요청할 수 있습니다.')
   if m.get('analysis_state') in ('running','queued'):raise HTTPException(409,'분석이 끝난 뒤 요청해 주세요.')
   w.apply_candidates(c,m,p,body.candidates,[],actor)
   request_assignments(w,c,m,p,body.selected,actor)
  return {'ok':True,'version':m['version'],'requested':len(body.selected)}
 return r
