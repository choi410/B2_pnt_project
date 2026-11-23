"""Exercise destructive operations only in a disposable database/files directory."""
import os,tempfile,sys
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from work.v17.test_demo import exercise

def main():
 with tempfile.TemporaryDirectory(prefix='b2-purge-qa-') as temp:
  os.environ.update(B2_TEAM_DATA_DIR=temp,B2_TEAM_TESTING='1',B2_DEMO_MODE='1')
  from work.v17 import server as w
  ids=exercise(w);pid=ids['project_id'];mid=ids['meeting_id']
  clients=[TestClient(w.app,headers={'X-B2-Request':'workspace'}) for _ in range(3)]
  def req(client,method,path,status=200,**kw):
   r=client.request(method,'/api'+path,**kw);assert r.status_code==status,(path,r.status_code,r.text);return r.json()
  pm,staff,outsider=clients
  for c,who in zip(clients,['team1','team2','team4']):req(c,'POST','/demo-login',json={'username':who})
  def make(client,title,finalize=False):
   d=req(client,'POST','/meeting-imports',201,data={'text':f'회의명: {title}\n논의 내용: 자료 확인 방법에 대한 의견을 공유했다. 변경 요청이나 합의는 없다.'})
   r=req(client,'PATCH','/meeting-imports/'+d['id'],json={'version':1,'title':title,'body':d['source'],'project_id':pid,'review_bundle':{'changes':[]},'review_confirmed':True})
   if not finalize:return d['id'],r['version']
   result=req(client,'POST',f"/meeting-imports/{d['id']}/finalize",201,json={'version':r['version'],'selected':[]})
   return result['id'],d['id']
  def trash(client,kind,id):
   endpoint='/meetings/' if kind=='meeting' else '/meeting-imports/'
   d=req(client,'GET',endpoint+id);v=d.get('version',d.get('draft_version',1))
   req(client,'POST',endpoint+id+'/trash',json={'version':v})
   return next(x for x in req(client,'GET','/trash') if x['id']==id)
  # Old review-pending data can be edited after removal of the approval workflow.
  with w.connect() as c:
   old=w.read(c,'meeting',mid);old['document_status']='검토 대기';w.save(c,'meeting',old)
  with patch('work.v17.changes.submit_scan'):
   req(staff,'PATCH',f'/meetings/{mid}/content',json={'version':old['version'],'title':old['title']+' 수정','meeting_date':old['date'],'body':old['source']})
  assert req(staff,'GET',f'/meetings/{mid}')['document_status']=='등록 완료'
  with w.connect() as c:
   old=w.read(c,'meeting',mid);old['change_scan_state']='ready';w.save(c,'meeting',old)
  item=trash(pm,'meeting',mid)
  assert not item['can_purge'] and '변경이력' in item['purge_reason']
  req(pm,'DELETE',f'/meetings/{mid}',409,json={'version':item['version'],'confirmed':True})
  # A private draft is owned by its author and requires a fresh version and confirmation.
  did,v=make(staff,'임시 저장본 삭제 검증')
  req(staff,'DELETE',f'/meeting-imports/{did}',409,json={'version':v,'confirmed':True})
  item=trash(staff,'import',did)
  req(pm,'DELETE',f'/meeting-imports/{did}',403,json={'version':item['version'],'confirmed':True})
  req(staff,'DELETE',f'/meeting-imports/{did}',422,json={'version':item['version']})
  req(staff,'DELETE',f'/meeting-imports/{did}',409,json={'version':v,'confirmed':True})
  with w.connect() as c:original_file=Path(w.read(c,'import',did)['txt'])
  req(staff,'DELETE',f'/meeting-imports/{did}',json={'version':item['version'],'confirmed':True})
  assert not original_file.exists()
  req(staff,'GET',f'/meeting-imports/{did}',404)
  req(staff,'POST',f'/meeting-imports/{did}/restore',404,json={'version':item['version']})
  # A registered document deletes its import copy and notices; unrelated records survive.
  clean,import_id=make(staff,'연결 없는 회의록 삭제 검증',True)
  with w.connect() as c:
   before=w.read(c,'meeting',clean);source_file=Path(before['txt'])
  item=trash(pm,'meeting',clean)
  req(staff,'DELETE',f'/meetings/{clean}',403,json={'version':item['version'],'confirmed':True})
  req(outsider,'DELETE',f'/meetings/{clean}',403,json={'version':item['version'],'confirmed':True})
  assert item['can_purge']
  req(pm,'DELETE',f'/meetings/{clean}',json={'version':item['version'],'confirmed':True})
  req(pm,'GET',f'/meetings/{clean}',404);req(staff,'GET',f'/meeting-imports/{import_id}',404)
  assert not source_file.exists()
  with w.connect() as c:
   assert not any(n['target_id']==clean for n in w.all_records(c,'notification'))
   assert w.read(c,'meeting',mid)['id']==mid
  # Files shared by another record are retained. A failing file move leaves the trash intact.
  did,_=make(staff,'공유 원본 보존 검증');item=trash(staff,'import',did)
  with w.connect() as c:
   d=w.read(c,'import',did);shared=Path(d['txt']);other={**d,'id':'shared-copy','deleted_at':None};w.save(c,'import',other)
  req(staff,'DELETE',f'/meeting-imports/{did}',json={'version':item['version'],'confirmed':True});assert shared.exists()
  fail_id,_=make(staff,'파일 잠금 검증');item=trash(staff,'import',fail_id)
  with w.connect() as c:locked=Path(w.read(c,'import',fail_id)['txt'])
  with patch('work.v17.meeting_purge.os.replace',side_effect=PermissionError('locked')):
   req(staff,'DELETE',f'/meeting-imports/{fail_id}',409,json={'version':item['version'],'confirmed':True})
  assert locked.exists() and req(staff,'GET',f'/meeting-imports/{fail_id}')['deleted_at']
  extra=w.FILES/'second-file.txt';extra.write_text('preserve',encoding='utf-8')
  with w.connect() as c:
   d=w.read(c,'import',fail_id);d['pdf']=str(extra);w.save(c,'import',d)
  actual_replace=os.replace;calls=[0]
  def fail_second(src,dst):
   calls[0]+=1
   if calls[0]==2:raise PermissionError('second file locked')
   return actual_replace(src,dst)
  with patch('work.v17.meeting_purge.os.replace',side_effect=fail_second):
   req(staff,'DELETE',f'/meeting-imports/{fail_id}',409,json={'version':item['version'],'confirmed':True})
  assert calls[0]==3 and locked.exists() and extra.read_text()=='preserve'
  with w.connect() as c:
   d=w.read(c,'import',fail_id);d.update(docx=str(extra),pdf=None,preview_finished=False);w.save(c,'import',d)
  req(staff,'DELETE',f'/meeting-imports/{fail_id}',409,json={'version':item['version'],'confirmed':True})
  with w.connect() as c:
   d=w.read(c,'import',fail_id);d.update(docx=None,preview_finished=True);w.save(c,'import',d)
  # Storage paths outside the service directory must never be touched.
  outside=Path(temp)/'outside.txt';outside.write_text('keep',encoding='utf-8')
  with w.connect() as c:
   d=w.read(c,'import',fail_id);d['txt']=str(outside);w.save(c,'import',d)
  req(staff,'DELETE',f'/meeting-imports/{fail_id}',409,json={'version':item['version'],'confirmed':True});assert outside.read_text()=='keep'
  with w.connect() as c:
   d=w.read(c,'import',fail_id);d['txt']=str(locked);w.save(c,'import',d)
  print('PASS: legacy edit, linked-history block, author/PM roles, fresh confirmation, permanent record/file deletion, import/notice cleanup, shared file retention, locked-file rollback, bounded file paths.',flush=True)
  if '--serve' in sys.argv:
   w.COOKIE='b2_demo_qa_session';w.team_config.ORIGINS.add('http://127.0.0.1:8773')
   import uvicorn
   uvicorn.run(w.app,host='127.0.0.1',port=8773,proxy_headers=False,access_log=False)

if __name__=='__main__':main()
