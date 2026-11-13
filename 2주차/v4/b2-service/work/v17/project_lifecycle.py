"""Reversible, PM-only project archive. Children retain their independent state."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

class Version(BaseModel):
 model_config=ConfigDict(extra='forbid')
 version:int

def build_router(w):
 r=APIRouter(prefix='/api')
 def owned(c,pid,actor):
  p=w.read(c,'project',pid)
  if p['pm']!=actor['id'] or actor['id'] not in p['members']:raise HTTPException(403,'이 프로젝트의 PM만 삭제·복구할 수 있습니다.')
  return p
 def counts(c,pid):
  return {'meetings':sum(x['project_id']==pid for x in w.all_records(c,'meeting')),
   'drafts':sum(x.get('chosen_project')==pid and not x.get('meeting_id') for x in w.all_records(c,'import')),
   'changes':sum(x['project_id']==pid for x in w.all_records(c,'change_event'))}
 @r.get('/project-trash')
 def trash(actor=Depends(w.user)):
  with w.connect() as c:
   items=[{'id':p['id'],'name':p['name'],'deleted_at':p['deleted_at'],'version':p.get('lifecycle_version',1)} for p in w.all_records(c,'project',include_archived=True) if p.get('deleted_at') and p['pm']==actor['id'] and actor['id'] in p['members']]
  return sorted(items,key=lambda p:p['deleted_at'],reverse=True)
 @r.get('/projects/{pid}/trash-preview')
 def preview(pid,actor=Depends(w.user)):
  with w.connect() as c:
   p=owned(c,pid,actor)
   if p.get('deleted_at'):raise HTTPException(409,'이미 휴지통에 있는 프로젝트입니다.')
   return {'version':p.get('lifecycle_version',1),**counts(c,pid)}
 def change(pid,body,actor,restore):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');p=owned(c,pid,actor)
   if p.get('lifecycle_version',1)!=body.version:raise HTTPException(409,'프로젝트 상태가 바뀌었습니다. 목록을 다시 열어 주세요.')
   if bool(p.get('deleted_at'))!=restore:raise HTTPException(409,'프로젝트의 현재 상태를 다시 확인해 주세요.')
   if not restore:
    meetings=[m for m in w.all_records(c,'meeting') if m['project_id']==pid]
    drafts=[d for d in w.all_records(c,'import') if d.get('chosen_project')==pid]
    jobs=[j for j in w.all_records(c,'context_draft') if j.get('project_id')==pid]
    if any(x.get(k) in ('queued','running') for x in meetings+drafts+jobs for k in ('analysis_state','change_scan_state','state')):
     raise HTTPException(409,'이 프로젝트의 AI 분석이 진행 중입니다. 분석이 끝난 뒤 휴지통으로 옮겨 주세요.')
   p.update(deleted_at=None if restore else w.now(),deleted_by=None if restore else actor['id'],lifecycle_version=body.version+1)
   p.setdefault('lifecycle_events',[]).append({'at':w.now(),'by':actor['id'],'action':'restore' if restore else 'trash'})
   w.save(c,'project',p)
  return {'ok':True}
 @r.post('/projects/{pid}/trash')
 def delete(pid,body:Version,actor=Depends(w.user)):return change(pid,body,actor,False)
 @r.post('/projects/{pid}/restore')
 def restore(pid,body:Version,actor=Depends(w.user)):return change(pid,body,actor,True)
 return r
