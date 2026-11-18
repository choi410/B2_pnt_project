"""Registration/approval is atomic; notices are scoped and grouped. Disposable data only."""
import os,tempfile,json,sys
from unittest.mock import patch
from copy import deepcopy
from fastapi.testclient import TestClient

SOURCE='''회의명: 점검 커버 설계 검토
회의일: 2026-11-09
논의: 힌지와 프레임 간섭을 해소하기 위해 힌지 위치를 20mm 변경하고 기존 체결 구멍은 유지한다.
후속 조치: 팀원 2가 변경 도면과 간섭 검토 결과를 2026-11-13까지 제출한다.
추가 확인: 팀원 3이 협력사 가공 가능 여부를 확인한다. 기한은 미정이다.'''

def exercise(w):
 w.init()
 clients=[TestClient(w.app,headers={'X-B2-Request':'workspace'}) for _ in range(4)]
 def req(client,method,path,status=200,**kwargs):
  response=client.request(method,'/api'+path,**kwargs)
  assert response.status_code==status,(path,response.status_code,response.text)
  return response.json()
 pm,staff,other,outside=clients
 for i,client in enumerate(clients):req(client,'POST','/demo-login',json={'username':f'team{i+1}'})
 p=req(pm,'POST','/projects',201,json={'name':'점검 커버 개선 프로젝트','members':['team2','team3']})
 pid=p['id']
 def notices(client,mid):return [n for n in req(client,'GET','/notifications')['items'] if n['target_id']==mid]
 def all_counts():
  with w.connect() as c:return {kind:len(w.all_records(c,kind)) for kind in ('meeting','task','notification','task_attention')}
 def draft(client,label):
  source=SOURCE+'\n비고: '+label
  d=req(client,'POST','/meeting-imports',201,data={'text':source})
  bundle={'summary':[],'decisions':[],'changes':[],'candidates':[
   {'id':'draw','title':'점검 커버 변경 도면 작성','description':'- 힌지 위치를 20mm 변경하고 간섭을 확인합니다.\n- 기존 체결 구멍을 유지합니다.\n- 변경 도면과 간섭 검토 결과를 제출합니다.','kind':'업무','owner_id':'team2','reviewer_id':'team1','due':'2026-11-13','evidence':['L003','L004'],'selected_for_assignment':True},
   {'id':'check','title':'협력사 가공 가능 여부 확인','description':'협력사에 가공 가능 여부를 확인합니다.','kind':'확인사항','owner_id':None,'reviewer_id':'team3','due':None,'evidence':['L005']},
   {'id':'pending','title':'후속 일정 확인','description':'','kind':'업무','owner_id':None,'reviewer_id':'team1','due':None,'evidence':[]}]}
  version=req(client,'PATCH','/meeting-imports/'+d['id'],json={'version':d.get('draft_version',1),'title':label,'meeting_date':'2026-11-09','body':source,'project_id':pid,'review_bundle':bundle,'review_confirmed':True})['version']
  return d,version,bundle
 def finalize(client,d,version,selected):return req(client,'POST','/meeting-imports/'+d['id']+'/finalize',201,json={'version':version,'selected':selected})

 before=all_counts();d,v,b=draft(pm,'PM 직접 등록 및 업무 배정')
 assert all_counts()==before,'Draft creation must not notify the project'
 assert req(pm,'GET','/meeting-imports/'+d['id'])['review_bundle']['candidates'][0]['selected_for_assignment']
 # Invalid second item must roll back the valid first task and the meeting itself.
 req(pm,'POST','/meeting-imports/'+d['id']+'/finalize',422,json={'version':v,'selected':['draw','pending']})
 assert all_counts()==before
 assert not req(pm,'GET','/meeting-imports/'+d['id']).get('meeting_id')
 result=finalize(pm,d,v,['draw']);mid=result['id'];assert len(result['created'])==1
 m=req(pm,'GET','/meetings/'+mid)
 assert m['document_status']=='등록 완료' and sum(x['state']=='draft' for x in m['candidates'])==2
 assert not notices(pm,mid) and not notices(outside,mid)
 n=notices(staff,mid);assert len(n)==1 and n[0]['task_ids']==result['created'] and '내 업무 1건' in n[0]['title']
 assert len(notices(other,mid))==1
 assert not [n for n in req(staff,'GET','/notifications')['items'] if n['target_id'] in result['created']]
 t=next(t for t in req(staff,'GET','/bootstrap')['tasks'] if t['id']==result['created'][0])
 assert t['description']==b['candidates'][0]['description'] and t['unseen']
 before=all_counts();assert finalize(pm,d,v,['draw'])['id']==mid;assert all_counts()==before
 req(staff,'POST','/notifications/read',json={'ids':[n[0]['id']]})
 assert notices(staff,mid)[0]['read_at']
 assert next(x for x in req(staff,'GET','/bootstrap')['tasks'] if x['id']==t['id'])['status']=='미착수'

 # Staff registration and assignment are separate; document review is optional.
 d,v,b=draft(staff,'사원이 작성한 회의록');before=all_counts();mid2=finalize(staff,d,v,['draw','check'])['id']
 assert all_counts()['task']==before['task']
 assert len(notices(pm,mid2))==1 and len(notices(other,mid2))==1 and not notices(staff,mid2)
 m=req(pm,'GET','/meetings/'+mid2);assert m['requested_task_ids']==['draw','check']
 req(staff,'POST','/meetings/'+mid2+'/review',403,json={'version':m['version'],'candidates':m['candidates'],'selected':['draw']})
 invalid=deepcopy(m['candidates']);invalid[0]['owner_id']='team4';before=all_counts()
 req(pm,'POST','/meetings/'+mid2+'/review',422,json={'version':m['version'],'candidates':invalid,'selected':['draw']})
 assert all_counts()==before and req(pm,'GET','/meetings/'+mid2)['document_status']=='등록 완료'
 candidates=deepcopy(m['candidates']);candidates[0]['description']+='\n- 제작 착수 전 도면을 제출합니다.'
 candidates[1]['reviewer_id']='team2'
 result=req(pm,'POST','/meetings/'+mid2+'/review',json={'version':m['version'],'candidates':candidates,'selected':['draw','check']})
 assert len(result['created'])==2
 assert len(notices(other,mid2))==1 and not notices(outside,mid2)
 before=all_counts()
 req(pm,'POST','/meetings/'+mid2+'/review',409,json={'version':m['version'],'candidates':candidates,'selected':['draw']})
 assert all_counts()==before
 # A newly registered revision is announced, while business changes remain pending.
 m=req(pm,'GET','/meetings/'+mid2)
 with patch('work.v17.changes.submit_scan'):
  req(pm,'PATCH','/meetings/'+mid2+'/content',json={'version':m['version'],'title':m['title'],'meeting_date':m['date'],'body':m['source']+'\n추가 결정: 제작은 도면 확인 후 협의한다.'})
 assert all_counts()['task']==before['task']
 assert len(notices(other,mid2))==2 and any('수정본 등록' in n['title'] for n in notices(staff,mid2))
 m=req(pm,'GET','/meetings/'+mid2)
 req(pm,'POST','/meetings/'+mid2+'/document-action',json={'version':m['version'],'action':'submit'})
 m=req(pm,'GET','/meetings/'+mid2)
 req(pm,'POST','/meetings/'+mid2+'/document-action',json={'version':m['version'],'action':'approve'})
 assert len(notices(other,mid2))==2
 # No assignments is a supported path, even with incomplete proposals.
 d,v,b=draft(pm,'회의록만 등록');before=all_counts();mid3=finalize(pm,d,v,[])['id']
 assert all_counts()['task']==before['task'] and len(notices(other,mid3))==1
 # A PM-owned direct-complete task does not create a self notification.
 d,v,b=draft(pm,'PM 직접 수행 업무');b['candidates'][0].update(owner_id='team1',reviewer_id=None,requires_review=False)
 record=req(pm,'GET','/meeting-imports/'+d['id'])
 v=req(pm,'PATCH','/meeting-imports/'+d['id'],json={'version':v,'title':record['title'],'body':record['edited_body'],'project_id':pid,'review_bundle':b,'review_confirmed':True})['version']
 result=finalize(pm,d,v,['draw']);assert not notices(pm,result['id'])
 # Safe display fallback for unsupported invented numbers; short descriptions stay short.
 from work.v17.ai import grounded_description
 refs={'L1':'힌지 위치를 20mm 변경한다.'}
 assert grounded_description('- 힌지 위치를 20mm 변경합니다.',['L1'],refs).startswith('-')
 assert grounded_description('- 힌지 위치를 25mm 변경합니다.',['L1'],refs)==refs['L1']
 assert grounded_description(None,['L1'],refs)==refs['L1']
 assert '변경 도면과 검토 결과를 제출' in grounded_description('- 도면을 작성합니다.',['L1'],{'L1':'후속 조치: 팀원 2가 변경 도면과 검토 결과를 제출한다.'})
 # Leave one PM draft and one staff submission for optional browser QA.
 ui_draft,_,_=draft(pm,'등록 화면 확인용 회의록')
 pending,version,_=draft(staff,'PM 검토 화면 확인용 회의록');pending_mid=finalize(staff,pending,version,['draw'])['id']
 print('PASS: atomic registration and separate assignment; no premature assignment; rollback; grouped project notices; no self/outside/duplicate notifications; revision notices; task-only selection; evidence and text preserved.',flush=True)
 return {'project_id':pid,'meeting_id':mid,'draft_id':ui_draft['id'],'pending_meeting_id':pending_mid}

def main():
 with tempfile.TemporaryDirectory(prefix='b2-registration-qa-') as tmp:
  os.environ.update(B2_TEAM_DATA_DIR=tmp,B2_TEAM_TESTING='1',B2_DEMO_MODE='1')
  os.environ.pop('B2_TEAM_LAN_IP',None);os.environ.pop('B2_TEAM_LAN_CIDR',None)
  from work.v17 import server as w
  w.COOKIE='b2_registration_qa_session';w.team_config.ORIGINS.add('http://127.0.0.1:8772')
  ids=exercise(w);print(json.dumps(ids,ensure_ascii=False),flush=True)
  if '--serve' in sys.argv:
   import uvicorn
   uvicorn.run(w.app,host='127.0.0.1',port=8772,proxy_headers=False,access_log=False)
if __name__=='__main__':main()
