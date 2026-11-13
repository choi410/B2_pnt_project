"""Presentation scope and registration integration checks; disposable data only."""
import os, tempfile, sys
from copy import deepcopy
from unittest.mock import patch
from fastapi.testclient import TestClient

SOURCE='''회의명: 롤프레스 점검 커버 변경 협의
회의일: 2026-11-11
논의: 고객이 점검 커버 방식을 여닫이에서 측면 슬라이드로 변경 요청했다. 제작 승인은 아직 받지 않았다.
결정사항: 기존 체결 구멍은 유지하고 변경 가능 여부만 검토한다.
후속 조치: 진효창이 간섭 검토 도면을 2026-11-13까지 작성한다.
추가 확인: 배근우가 협력사 제작 가능 여부를 확인한다. 기한은 미정이다.'''

def exercise(w):
 w.init()
 clients=[TestClient(w.app,headers={'X-B2-Request':'workspace'}) for _ in range(4)]
 def req(client,method,path,status=200,**kwargs):
  r=client.request(method,'/api'+path,**kwargs)
  assert r.status_code==status,(path,r.status_code,r.text)
  return r.json()
 for i,c in enumerate(clients):req(c,'POST','/demo-login',json={'username':f'team{i+1}'})
 pm,staff,other,outsider=clients
 boot=req(pm,'GET','/bootstrap')
 assert not any(boot[k] for k in ('projects','meetings','tasks','imports'))
 assert [p['name'] for p in boot['people']]==['김양일','진효창','배근우','최인혁']
 assert w.COOKIE=='b2_pnt_demo_session' and w.team_config.PORT==8772
 p=req(pm,'POST','/projects',201,json={'name':'시연 검증용 롤프레스','members':['team2','team3']})
 pid=p['id']
 req(pm,'PATCH',f'/projects/{pid}/overview',json={'version':1,'purpose':'고객 요구에 따른 점검 커버 방식 검토','scope':'커버 설계 변경과 간섭 검토','stages':['요구 접수','설계 검토','합의'],'current_stage':'설계 검토','next_goal':'고객 변경안 검토','customer':'가상 고객','equipment':'롤프레스','start_date':'2026-11-01','due_date':'2026-12-31'})
 bundle={'summary':[{'text':'고객이 점검 커버의 측면 슬라이드 방식을 요청했다.','evidence':['L003']}],
  'decisions':[{'text':'기존 체결 구멍은 유지하고 변경 가능 여부를 검토한다.','evidence':['L004']}],
  'candidates':[{'id':'draw','title':'간섭 검토 도면 작성','description':'기존 체결 구멍을 유지하면서 간섭 검토 도면을 작성한다.','kind':'업무','owner_id':None,'reviewer_id':None,'due':None,'evidence':['L004','L005']},
   {'id':'check','title':'협력사 제작 가능 여부 확인','description':'제작 가능 여부를 협력사에 확인한다.','kind':'확인사항','owner_id':None,'reviewer_id':None,'due':None,'evidence':['L006']}],
  'changes':[{'title':'점검 커버 개폐 방식','category':'사양','before':'여닫이','after':'측면 슬라이드','business_state':'요청','evidence':['L003'],'review_action':'record'}]}
 def draft(client,title,source=SOURCE):
  d=req(client,'POST','/meeting-imports',201,data={'text':source})
  r=req(client,'PATCH','/meeting-imports/'+d['id'],json={'version':d.get('draft_version',1),'title':title,'meeting_date':'2026-11-11','body':source,'project_id':pid,'review_bundle':bundle,'review_confirmed':True})
  return d['id'],r['version']
 iid,v=draft(staff,'점검 커버 변경 협의')
 req(staff,'POST',f'/meeting-imports/{iid}/finalize',422,json={'version':v,'selected':['draw']})
 assert not req(staff,'GET',f'/meeting-imports/{iid}').get('meeting_id')
 result=req(staff,'POST',f'/meeting-imports/{iid}/finalize',201,json={'version':v,'selected':[]})
 assert not result['created'] and result['requested']==0 and result['change_candidates']==1
 mid=result['id'];m=req(staff,'GET',f'/meetings/{mid}')
 assert m['document_status']=='등록 완료' and len(m['reviewed_bundle']['candidates'])==2
 assert m['reviewed_bundle']['candidates'][0]['evidence']==['L004','L005']
 assert not req(pm,'GET','/bootstrap')['tasks']
 notices=req(pm,'GET','/notifications')['items']
 assert notices and all(n['target_type']=='meeting' and not n.get('task_ids') for n in notices)
 assert not req(outsider,'GET','/notifications')['items']
 changes=req(pm,'GET','/changes?project_id='+pid)
 assert any(e['after']=='측면 슬라이드' for e in changes['events'])
 for method,path in [('POST','/tasks'),('PATCH','/tasks/x'),('POST','/tasks/x/actions'),('GET','/work-proposals'),('POST',f'/meetings/{mid}/review'),('POST',f'/meetings/{mid}/assignment-request'),('POST','/reports'),('GET','/reports'),('POST','/reports/read-file'),('GET','/cooperation'),('POST','/context-drafts/task/x')]:
  req(pm,method,path,404,json={})
 # Registration is sufficient; no separate document approval workflow is exposed.
 req(staff,'POST',f'/meetings/{mid}/document-action',404,json={'version':m['version'],'action':'submit'})
 m=req(pm,'GET',f'/meetings/{mid}');assert m['document_status']=='등록 완료'
 req(pm,'POST',f'/meetings/{mid}/trash',json={'version':m['version']})
 deleted=req(pm,'GET','/trash');item=next(x for x in deleted if x['id']==mid)
 req(pm,'POST',f'/meetings/{mid}/restore',json={'version':item['version']})
 assert req(pm,'GET',f'/meetings/{mid}')['source']==SOURCE
 assert not req(pm,'GET','/bootstrap')['tasks']
 # Saved draft for browser checks; explicit human-prepared fixture, not fake AI output.
 draft_id,_=draft(pm,'등록 화면 검증',SOURCE+'\n비고: 화면 검증용 임시 자료')
 print('PASS: empty startup, four users, isolated port/cookie, registration without assignment, follow-up text/evidence retained, automatic change records, scoped meeting notices, no approval workflow, trash/restore, task and D3 APIs unavailable.',flush=True)
 return {'project_id':pid,'meeting_id':mid,'draft_id':draft_id}

def main():
 with tempfile.TemporaryDirectory(prefix='b2-demo-qa-') as temp:
  os.environ.update(B2_TEAM_DATA_DIR=temp,B2_TEAM_TESTING='1',B2_DEMO_MODE='1')
  os.environ.pop('B2_TEAM_LAN_IP',None);os.environ.pop('B2_TEAM_LAN_CIDR',None)
  from work.v17 import server as w
  w.team_config.ORIGINS.add('http://127.0.0.1:8773')
  ids=exercise(w);print(ids,flush=True)
  if '--serve' in sys.argv:
   w.COOKIE='b2_demo_qa_session'
   import uvicorn
   uvicorn.run(w.app,host='127.0.0.1',port=8773,proxy_headers=False,access_log=False)

if __name__=='__main__':main()
