"""Explicit permanent deletion of unreferenced documents already in the trash."""
import json,os
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict

class Purge(BaseModel):
 model_config=ConfigDict(extra='forbid')
 version:int
 confirmed:bool=False

def refers_to(value,mid):
 if isinstance(value,dict):return value.get('meeting_id')==mid or any(refers_to(v,mid) for v in value.values())
 return isinstance(value,list) and any(refers_to(v,mid) for v in value)

def reason(w,c,kind,d,actor):
 if not d.get('deleted_at'):return '휴지통으로 옮긴 뒤 영구 삭제할 수 있습니다.'
 if kind=='import':
  if d['actor_id']!=actor['id']:return '작성자만 영구 삭제할 수 있습니다.'
  if d.get('meeting_id'):return '등록된 회의록의 휴지통에서 처리해 주세요.'
 else:
  p=w.read(c,'project',d['project_id'])
  if actor['id']!=p['pm']:return '프로젝트 PM만 영구 삭제할 수 있습니다.'
  if any(x.get('meeting_id')==d['id'] for x in w.all_records(c,'change_event')):return '변경이력의 근거로 연결되어 있어 영구 삭제할 수 없습니다.'
  if any(x.get('meeting_id')==d['id'] for x in w.all_records(c,'task')):return '연결된 업무가 있어 영구 삭제할 수 없습니다.'
  if any(refers_to(x,d['id']) for k in ('context_draft','report') for x in w.all_records(c,k)):return '생성된 자료의 근거로 사용 중이어서 영구 삭제할 수 없습니다.'
 related=[d]+([x for x in w.all_records(c,'import') if x.get('meeting_id')==d['id']] if kind=='meeting' else [])
 if any(x.get(key) in ('queued','running') for x in related for key in ('analysis_state','change_scan_state')):return 'AI 분석이 끝난 뒤 영구 삭제할 수 있습니다.'
 if any(x.get('docx') and not x.get('pdf') and x.get('preview_finished',True) is False for x in related):return '원본 미리보기 준비가 끝난 뒤 영구 삭제할 수 있습니다.'
 return ''

def file_values(value):
 if isinstance(value,dict):
  for k,v in value.items():
   if k in ('docx','pdf','txt','path') and isinstance(v,str) and v:yield v
   elif isinstance(v,(list,dict)):yield from file_values(v)
 elif isinstance(value,list):
  for v in value:yield from file_values(v)

def cleanup_files(w):
 """Retry inaccessible staged files without restoring deleted documents."""
 with w.connect() as c:
  for item in w.all_records(c,'purge_cleanup'):
   remaining=[]
   for name in item['paths']:
    path=Path(name).resolve()
    if not path.is_relative_to(w.FILES.resolve()) or not path.name.startswith('.purge-'):continue
    try:path.unlink(missing_ok=True)
    except OSError:remaining.append(name)
   if remaining:item['paths']=remaining;w.save(c,'purge_cleanup',item)
   else:c.execute('DELETE FROM records WHERE kind=? AND id=?',('purge_cleanup',item['id']))

def build_router(w):
 r=APIRouter(prefix='/api')
 def delete(kind,id,body,actor):
  staged=[]
  try:
   with w.connect() as c:
    c.execute('BEGIN IMMEDIATE');d=w.read(c,kind,id)
    if kind=='import':
     if d['actor_id']!=actor['id']:raise HTTPException(403,'작성자만 영구 삭제할 수 있습니다.')
     if d.get('chosen_project'):w.project(c,d['chosen_project'],actor)
     v=d.get('draft_version',1)
    else:
     w.project(c,d['project_id'],actor,True);v=d['version']
    if not body.confirmed:raise HTTPException(422,'복구할 수 없는 영구 삭제임을 확인해 주세요.')
    if body.version!=v:raise HTTPException(409,'최신 상태를 다시 열어 주세요.')
    blocked=reason(w,c,kind,d,actor)
    if blocked:raise HTTPException(409,blocked)
    records=[(row['kind'],row['id'],json.loads(row['payload'])) for row in c.execute('SELECT kind,id,payload FROM records')]
    targets={(kind,id)}
    if kind=='meeting':
     targets.update((k,i) for k,i,x in records if k=='import' and x.get('meeting_id')==id)
     targets.update((k,i) for k,i,x in records if k=='notification' and x.get('target_id')==id and x.get('target_type') in ('meeting','assignment_request'))
    owned={Path(name).resolve() for k,i,x in records if (k,i) in targets for name in file_values(x)}
    shared={Path(name).resolve() for k,i,x in records if (k,i) not in targets for name in file_values(x)}
    paths=owned-shared;root=w.FILES.resolve()
    if any(not path.is_relative_to(root) for path in paths):raise HTTPException(409,'원본 파일의 저장 경로를 확인해야 합니다. 영구 삭제하지 않았습니다.')
    # Rename only verified files; roll them back if the DB transaction fails.
    token=w.uid()
    for index,path in enumerate(sorted(paths)):
     if path.is_file():
      target=root/('.purge-'+token+'-'+str(index));os.replace(path,target);staged.append((path,target))
    for k,i in targets:c.execute('DELETE FROM records WHERE kind=? AND id=?',(k,i))
    if kind=='meeting' and c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rag_vectors'").fetchone():
     c.execute('DELETE FROM rag_vectors WHERE project_id=?',(d['project_id'],))
    if staged:w.save(c,'purge_cleanup',{'id':token,'paths':[str(path) for _,path in staged]})
  except Exception as exc:
   for source,target in reversed(staged):os.replace(target,source)
   if isinstance(exc,OSError):raise HTTPException(409,'파일이 사용 중이어서 삭제하지 못했습니다. 원본 문서를 닫고 다시 시도해 주세요.') from exc
   raise
  cleanup_files(w)
  return {'ok':True}
 @r.delete('/meetings/{mid}')
 def meeting(mid,body:Purge,actor=Depends(w.user)):return delete('meeting',mid,body,actor)
 @r.delete('/meeting-imports/{iid}')
 def draft(iid,body:Purge,actor=Depends(w.user)):return delete('import',iid,body,actor)
 return r
