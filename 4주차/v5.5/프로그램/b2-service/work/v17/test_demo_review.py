"""Registration editorial order and reversible project lifecycle; disposable data."""
import os,tempfile
from copy import deepcopy
from fastapi.testclient import TestClient
from work.v17.test_demo import exercise

def main():
 with tempfile.TemporaryDirectory(prefix='b2-review-qa-') as temp:
  os.environ.update(B2_TEAM_DATA_DIR=temp,B2_TEAM_TESTING='1',B2_DEMO_MODE='1')
  from work.v17 import server as w
  ids=exercise(w);pid=ids['project_id'];iid=ids['draft_id'];mid=ids['meeting_id']
  clients=[TestClient(w.app,headers={'X-B2-Request':'workspace'}) for _ in range(4)]
  def req(client,method,path,status=200,**kw):
   r=client.request(method,'/api'+path,**kw);assert r.status_code==status,(path,r.status_code,r.text);return r.json()
  for i,c in enumerate(clients):req(c,'POST','/demo-login',json={'username':f'team{i+1}'})
  pm,staff,other,outsider=clients
  d=req(pm,'GET','/meeting-imports/'+iid);bundle=deepcopy(d['review_bundle'])
  # Insert a neutral manual note between a decision and a follow-up; omit a blank note on save.
  bundle['summary']+=[{'note_id':'manual-note','text':'검토 자료의 전달 방법은 미정이다.','evidence':[]},{'note_id':'empty-note','text':'','evidence':[]}]
  existing=bundle['note_order'];bundle['note_order']=[existing[0],existing[1],'manual-note','empty-note',*existing[2:]]
  body={'version':d['draft_version'],'title':d['title'],'body':d['source'],'meeting_date':'2026-11-11','project_id':pid,'review_bundle':bundle,'review_confirmed':True}
  v=req(pm,'PATCH','/meeting-imports/'+iid,json=body)['version']
  saved=req(pm,'GET','/meeting-imports/'+iid)['review_bundle']
  assert saved['note_order']==[existing[0],existing[1],'manual-note',*existing[2:]]
  assert saved['summary'][-1]['text']=='검토 자료의 전달 방법은 미정이다.'
  finalized=req(pm,'POST',f'/meeting-imports/{iid}/finalize',201,json={'version':v,'selected':[]})
  assert req(pm,'GET','/meetings/'+finalized['id'])['reviewed_bundle']['note_order']==saved['note_order']
  # Add a private draft and an independently trashed meeting before archiving the parent.
  di=req(staff,'POST','/meeting-imports',201,data={'text':'회의명: 프로젝트 삭제 검증\n논의: 초안을 보관하고 프로젝트 복구 후 이어서 확인한다.'})
  draft_body={'version':1,'title':'보관할 임시 저장본','body':di['source'],'project_id':pid,'review_bundle':{},'review_confirmed':False}
  req(staff,'PATCH','/meeting-imports/'+di['id'],json=draft_body)
  m=req(pm,'GET','/meetings/'+mid)
  req(pm,'POST',f'/meetings/{mid}/trash',json={'version':m['version']})
  info=req(pm,'GET',f'/projects/{pid}/trash-preview')
  req(staff,'POST',f'/projects/{pid}/trash',403,json={'version':info['version']})
  req(outsider,'GET',f'/projects/{pid}/trash-preview',403)
  with w.connect() as c:
   pending=w.read(c,'import',di['id']);pending['analysis_state']='queued';w.save(c,'import',pending)
  req(pm,'POST',f'/projects/{pid}/trash',409,json={'version':info['version']})
  with w.connect() as c:
   pending=w.read(c,'import',di['id']);pending['analysis_state']='idle';w.save(c,'import',pending)
   original_children={kind:w.all_records(c,kind) for kind in ('meeting','import','change_event','change_topic','notification')}
  req(pm,'POST',f'/projects/{pid}/trash',json={'version':info['version']})
  for client in (pm,staff):
   boot=req(client,'GET','/bootstrap')
   assert not any(boot[k] for k in ('projects','meetings','archived_meetings','imports','tasks'))
   assert not req(client,'GET','/changes')['events']
   assert not req(client,'GET','/notifications')['items']
  req(pm,'GET',f'/meetings/{mid}',410)
  req(staff,'GET','/meeting-imports/'+di['id'],410)
  req(staff,'PATCH','/meeting-imports/'+di['id'],410,json={**draft_body,'version':2,'project_id':None})
  assert not req(staff,'GET','/trash') and not req(staff,'GET','/project-trash')
  req(pm,'POST','/projects',409,json={'name':'시연 검증용 롤프레스'})
  item=req(pm,'GET','/project-trash')[0]
  req(staff,'POST',f'/projects/{pid}/restore',403,json={'version':item['version']})
  req(pm,'POST',f'/projects/{pid}/restore',409,json={'version':info['version']})
  req(pm,'POST',f'/projects/{pid}/restore',json={'version':item['version']})
  boot=req(pm,'GET','/bootstrap');assert len(boot['projects'])==1 and len(boot['meetings'])==1
  assert boot['archived_meetings'][0]['id']==mid
  assert req(staff,'GET','/bootstrap')['imports'][0]['id']==di['id']
  assert req(pm,'GET','/changes')['events']
  with w.connect() as c:
   assert original_children=={kind:w.all_records(c,kind) for kind in original_children}
  print('PASS: note insertion order survives draft/finalize, blank notes omitted, PM-only trash/restore, pending-job guard, hidden related records/direct access, stale version rejection, independent meeting trash and all child records preserved.')

if __name__=='__main__':main()
