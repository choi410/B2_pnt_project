"""Integration regression for context; disposable database, never team data."""
import os,tempfile,sys,time,json
from copy import deepcopy
from unittest.mock import patch
from fastapi.testclient import TestClient

SOURCE='''회의명: 점검 커버 제작 검토
회의일: 2026-11-09
프로젝트 목적: 롤프레스 점검 시 정지 상태에서 안전하게 접근할 수 있도록 점검 커버를 개선한다.
진행 범위: 점검 커버와 힌지 도면만 수정한다. 구동부는 변경하지 않는다.
논의: 현재 힌지와 프레임이 간섭한다. 힌지 위치를 20mm 옮기되 기존 체결 구멍은 유지한다.
결정: 변경 도면과 간섭 검토 결과를 PM에게 제출한다. 제작 착수는 도면 확인 후 별도 결정한다.
후속 조치: 팀원 2가 점검 커버 변경 도면과 간섭 검토 결과를 2026-11-13까지 제출한다.
추가 확인: 팀원 3이 협력사 가공 가능 여부를 확인한다. 회신 기한은 미정이다.'''

def seed(w):
 w.init()
 clients=[TestClient(w.app,headers={'X-B2-Request':'workspace'}) for _ in range(4)]
 def req(c,method,path,status=200,**kw):
  r=c.request(method,'/api'+path,**kw);assert r.status_code==status,(path,r.status_code,r.text);return r.json()
 for i,c in enumerate(clients):req(c,'POST','/demo-login',json={'username':'team'+str(i+1)})
 pm,owner,colleague,outside=clients
 p=req(pm,'POST','/projects',201,json={'name':'롤프레스 점검 커버 개선','members':['team2','team3']});pid=p['id']
 o={'version':1,'purpose':'점검 시 안전하게 접근할 수 있도록 점검 커버를 개선합니다.','scope':'점검 커버 및 힌지 도면 변경. 구동부 제외.','next_goal':'변경 도면과 간섭 검토 결과 확인','stages':['설계','도면 확인','제작','시운전'],'current_stage':'설계'}
 req(owner,'PATCH','/projects/'+pid+'/overview',403,json=o);req(outside,'GET','/projects/'+pid+'/overview',403)
 saved=req(pm,'PATCH','/projects/'+pid+'/overview',json=o);assert saved['version']==2
 req(pm,'PATCH','/projects/'+pid+'/overview',409,json=o)
 assert req(owner,'GET','/projects/'+pid+'/overview')['current_stage']=='설계'
 req(pm,'PATCH','/projects/'+pid+'/overview',422,json={**o,'version':2,'current_stage':'없는 단계'})
 # Metadata is saved explicitly and older clients cannot silently erase it.
 metadata={'customer':'  가상 고객  ','equipment':'롤프레스 1호기','start_date':'2026-11-01','due_date':'2027-02-15'}
 saved=req(pm,'PATCH','/projects/'+pid+'/overview',json={**o,**metadata,'version':2})
 assert saved['version']==3 and saved['customer']=='가상 고객' and saved['due_date']=='2027-02-15'
 for dates in ({'start_date':'2027-03-01'},{'due_date':'2026-10-01'},{'due_date':'2026-02-30'}):
  req(pm,'PATCH','/projects/'+pid+'/overview',422,json={**o,**dates,'version':3})
 assert req(owner,'GET','/projects/'+pid+'/overview')['version']==3
 saved=req(pm,'PATCH','/projects/'+pid+'/overview',json={**o,'version':3})
 assert all(saved[k]==v.strip() for k,v in metadata.items()),saved
 req(owner,'PATCH','/projects/'+pid+'/overview',403,json={**o,**metadata,'version':4})
 req(pm,'PATCH','/projects/'+pid+'/overview',409,json={**o,'version':3})

 d=req(pm,'POST','/meeting-imports',201,data={'text':SOURCE})
 req(pm,'PATCH','/meeting-imports/'+d['id'],json={'version':1,'title':'점검 커버 제작 검토','meeting_date':'2026-11-09','body':SOURCE,'project_id':pid,'review_bundle':{},'review_confirmed':False})
 extraction={'summary':[{'text':'힌지와 프레임의 간섭으로 위치 변경을 검토했다.','evidence':['L005']}],'decisions':[{'text':'변경 도면과 간섭 검토 결과 제출 후 제작 착수를 별도로 결정한다.','evidence':['L006']}],'items':[{'title':'점검 커버 변경 도면 작성','description':'해야 할 일: 점검 커버 변경 도면을 작성한다.\n대상·조건: 힌지 위치를 20mm 옮기고 기존 체결 구멍을 유지한다.\n완료 산출물: 변경 도면과 간섭 검토 결과.','kind':'업무','owner_id':'team2','start':None,'due':'2026-11-13','evidence':['L005','L006','L007']},{'title':'협력사 가공 가능 여부 확인','description':'협력사의 가공 가능 여부를 확인한다. 회신 기한은 확인 필요.','kind':'확인사항','owner_id':'team3','start':None,'due':None,'evidence':['L008']}]}
 from work.v17.intake_review import analyze_import
 with patch('work.v17.ai.extract',return_value=(extraction,{'model':'QA fixture'})),patch('work.v17.changes.extract_changes',return_value=({'items':[]},{})):
  analyze_import(w,d['id'])
 d=req(pm,'GET','/meeting-imports/'+d['id']);assert d['analysis_state']=='ready',d
 bundle=deepcopy(d['review_bundle']);bundle['summary'][0]['text']='힌지 간섭을 해소하되 기존 체결 구멍은 유지하기로 검토했다.'
 version=req(pm,'PATCH','/meeting-imports/'+d['id'],json={'version':d['draft_version'],'title':'점검 커버 제작 검토','meeting_date':'2026-11-09','body':SOURCE,'project_id':pid,'review_bundle':bundle,'review_confirmed':True})['version']
 mid=req(pm,'POST','/meeting-imports/'+d['id']+'/finalize',201,json={'version':version})['id']
 m=req(pm,'GET','/meetings/'+mid);assert m['ai_snapshot']['bundle']['summary'][0]['text']!=m['overview']['summary'][0]['text']
 assert m['ai_snapshot']['source']==SOURCE
 result=req(pm,'POST','/meetings/'+mid+'/review',json={'version':m['version'],'candidates':m['candidates'],'selected':[m['candidates'][0]['id']]})
 tid=result['created'][0];t=next(t for t in req(owner,'GET','/bootstrap')['tasks'] if t['id']==tid)
 assert '20mm' in t['description'] and '간섭 검토 결과' in t['description']
 payload={k:t.get(k) for k in ('version','title','description','owner_id','reviewer_id','requires_review','start','due','kind')};payload['description']+='\nPM 확인: 제작 착수 전 도면 확인 필요.'
 req(owner,'PATCH','/tasks/'+tid,403,json=payload)
 t=req(pm,'PATCH','/tasks/'+tid,json=payload);assert t['events'][-1]['changes']['description']['after']==t['description']
 req(pm,'PATCH','/tasks/'+tid,409,json=payload)
 before=deepcopy(t)
 sent=req(owner,'POST','/cooperation',201,json={'task_id':tid,'recipient_id':'team3','subject':'가공 가능 여부 확인','message':'기존 구멍을 유지하면서 힌지 위치 변경이 가능한지 확인해 주세요.'})
 req(owner,'POST','/cooperation',422,json={'task_id':tid,'recipient_id':'team4','subject':'외부 요청','message':'권한이 없는 사람'})
 req(owner,'POST','/cooperation',422,json={'task_id':tid,'recipient_id':'team2','subject':'본인 요청','message':'본인에게 요청'})
 assert req(pm,'GET','/tasks/'+tid+'/cooperation')[0]['id']==sent['id']
 req(outside,'GET','/tasks/'+tid+'/cooperation',403)
 n=next(n for n in req(colleague,'GET','/notifications')['items'] if n.get('cooperation_id')==sent['id']);assert n['target_type']=='task' and n['target_id']==tid
 req(owner,'POST','/cooperation/'+sent['id']+'/reply',403,json={'version':1,'message':'허가되지 않음'})
 req(colleague,'POST','/cooperation/'+sent['id']+'/reply',json={'version':1,'message':'기존 구멍 유지가 가능합니다. 변경 도면을 받으면 위치를 다시 대조하겠습니다.'})
 req(colleague,'POST','/cooperation/'+sent['id']+'/reply',409,json={'version':1,'message':'동시 변경'})
 after=next(t for t in req(owner,'GET','/bootstrap')['tasks'] if t['id']==tid);assert before=={k:v for k,v in after.items() if k!='unseen'}
 assert any(n.get('cooperation_id')==sent['id'] for n in req(owner,'GET','/notifications')['items'])
 req(colleague,'POST','/tasks/'+tid+'/actions',403,json={'version':t['version'],'action':'approve'})
 # Isolated AI worker contract: output review, scope, access, and stale evidence.
 from work.v17 import context_ai
 def fake(kind,source,title=''):
  keys=['action','conditions','deliverable'] if kind=='task' else ['purpose','scope','next_goal']
  return {k:{'text':'QA 검증용 초안','evidence':[source[0]['id']]} for k in keys}
 with patch.object(context_ai,'generate',side_effect=fake):
  req(owner,'POST','/context-drafts/task/'+tid,403,json={})
  job=req(pm,'POST','/context-drafts/project/'+pid,202,json={})
  for _ in range(100):
   job=req(pm,'GET','/context-drafts/'+job['id'])
   if job['state'] not in ('queued','running'):break
   time.sleep(.03)
  assert job['state']=='ready' and not job['stale'],job
  req(owner,'GET','/context-drafts/'+job['id'],403)
  assert req(pm,'GET','/projects/'+pid+'/overview')['purpose']==o['purpose']
  m=req(pm,'GET','/meetings/'+mid)
  with patch('work.v17.changes.submit_scan'):
   req(pm,'PATCH','/meetings/'+mid+'/content',json={'version':m['version'],'title':m['title'],'meeting_date':m['date'],'body':m['source']+'\n수정 문장'})
  assert req(pm,'GET','/context-drafts/'+job['id'])['stale']
 print('PASS: rich instructions persist; PM edit/version control; raw AI separate from reviewed text; cooperation recipients/reply/notifications with unchanged task and reviewer; overview permissions/stages/conflicts; AI drafts never auto-apply and stale sources blocked.',flush=True)
 return {'project_id':pid,'meeting_id':mid,'task_id':tid}

def main():
 with tempfile.TemporaryDirectory(prefix='b2-context-qa-') as tmp:
  os.environ.update(B2_TEAM_DATA_DIR=tmp,B2_TEAM_TESTING='1')
  from work.v17 import server as w
  w.COOKIE='b2_context_qa_session';w.team_config.ORIGINS.add('http://localhost:8772')
  ids=seed(w);print(json.dumps(ids,ensure_ascii=False),flush=True)
  if '--serve' in sys.argv:
   import uvicorn
   uvicorn.run(w.app,host='127.0.0.1',port=8772,proxy_headers=False,access_log=False)
if __name__=='__main__':main()
