"""Assignment workflow regression and optional browser fixture, in temporary storage."""
import os,sys,tempfile
from copy import deepcopy
from fastapi.testclient import TestClient

def exercise():
 from work.v17 import server as w
 w.init()
 clients=[TestClient(w.app,headers={'X-B2-Request':'workspace'}) for _ in range(3)]
 pm,staff,outside=clients
 def req(client,method,path,status=200,**kwargs):
  r=client.request(method,'/api'+path,**kwargs)
  assert r.status_code==status,(path,r.status_code,r.text)
  return r.json()
 for i,c in enumerate(clients):req(c,'POST','/demo-login',json={'username':f'team{i+1}'})
 p=req(pm,'POST','/projects',201,json={'name':'담당자 지정 회귀 검증','members':[]})
 assert p['members']==['team1']
 def meeting(title,selected=(),owner=None,reviewer=None):
  source=f'회의명: {title}\n점검 커버 변경 도면을 작성한다.\n고객 확인 자료를 정리한다.\n제작 착수 일정을 확인한다.'
  candidates=[{'id':f'item{i}','title':x,'kind':'업무','owner_id':owner,'reviewer_id':reviewer,'requires_review':True,'due':None,'evidence':[f'L00{i+2}']} for i,x in enumerate(['점검 커버 변경 도면 작성','고객 확인 자료 정리','제작 착수 일정 확인'])]
  d=req(pm,'POST','/meeting-imports',201,data={'text':source})
  v=req(pm,'PATCH','/meeting-imports/'+d['id'],json={'version':1,'title':title,'meeting_date':'2026-11-10','body':source,'project_id':p['id'],'review_bundle':{'summary':[],'decisions':[],'candidates':candidates,'changes':[]},'review_confirmed':True})['version']
  r=req(pm,'POST','/meeting-imports/'+d['id']+'/finalize',201,json={'version':v,'selected':list(selected)})
  return req(pm,'GET','/meetings/'+r['id'])
 def tasks():return req(pm,'GET','/bootstrap')['tasks']
 def edit(t,**changes):
  fields={k:t.get(k) for k in ('version','title','kind','owner_id','reviewer_id','requires_review','start','due')}
  return dict(fields,**changes)
 def count():
  with w.connect() as c:return {k:len(w.all_records(c,k)) for k in ['task','notification','task_attention']}
 # Both registration paths allow unknown people, without fake assignments/alerts.
 m=meeting('등록 단계에서 담당자 미정',['item0'])
 t=tasks()[0]
 assert t['owner_id'] is None and t['reviewer_id'] is None and t['requires_review']
 assert count()=={'task':1,'notification':0,'task_attention':0}
 m=meeting('등록한 회의에서 담당자 미정')
 r=req(pm,'POST','/meetings/'+m['id']+'/review',json={'version':m['version'],'candidates':m['candidates'],'selected':['item0','item1']})
 assert len(r['created'])==2 and len(tasks())==3
 assert all(t['owner_id'] is None for t in tasks())
 # A PM alone can assign to self only with explicit direct completion.
 req(pm,'PATCH','/tasks/'+t['id'],422,json=edit(t,owner_id='team1',reviewer_id='team1'))
 req(pm,'PATCH','/tasks/'+t['id'],422,json=edit(t,owner_id='team1'))
 t=req(pm,'PATCH','/tasks/'+t['id'],json=edit(t,owner_id='team1',requires_review=False))
 req(pm,'POST','/tasks/'+t['id']+'/actions',422,json={'version':t['version'],'action':'complete','note':''})
 t=req(pm,'POST','/tasks/'+t['id']+'/actions',json={'version':t['version'],'action':'complete','note':'변경 도면을 작성하고 간섭 여부를 확인했습니다.'})
 assert t['status']=='완료' and t['completion_method']=='self' and t['reviewer_id'] is None
 # Adding membership requires a PM action; no picker bypass grants access.
 req(staff,'GET','/meetings/'+m['id'],403)
 req(staff,'PATCH','/projects/'+p['id']+'/members',403,json={'ids':['team2']})
 req(pm,'PATCH','/projects/'+p['id']+'/members',json={'ids':['team2']})
 req(staff,'GET','/meetings/'+m['id'])
 pending=next(x for x in tasks() if x['status']!='완료')
 req(pm,'PATCH','/tasks/'+pending['id'],422,json=edit(pending,owner_id='team3',reviewer_id='team1'))
 req(staff,'PATCH','/tasks/'+pending['id'],403,json=edit(pending,owner_id='team2',requires_review=False))
 pending=req(pm,'PATCH','/tasks/'+pending['id'],json=edit(pending,owner_id='team2',reviewer_id='team1'))
 notices=req(staff,'GET','/notifications')['items']
 assert any(x['target_id']==pending['id'] and '업무 배정' in x['title'] for x in notices)
 req(staff,'POST','/tasks/'+pending['id']+'/actions',403,json={'version':pending['version'],'action':'complete','note':'검토 없이 완료 시도'})
 pending=req(staff,'POST','/tasks/'+pending['id']+'/actions',json={'version':pending['version'],'action':'submit','note':'고객 자료를 대조했습니다.'})
 req(staff,'POST','/tasks/'+pending['id']+'/actions',403,json={'version':pending['version'],'action':'approve'})
 req(pm,'POST','/tasks/'+pending['id']+'/actions',json={'version':pending['version'],'action':'approve'})
 # Invalid second selection rolls back the entire batch, including notifications.
 m=meeting('일괄 지정 원자성')
 candidates=deepcopy(m['candidates'])
 for c in candidates:c.update(owner_id='team2',reviewer_id='team1')
 candidates[1]['owner_id']='team3'
 before=count()
 req(pm,'POST','/meetings/'+m['id']+'/review',422,json={'version':m['version'],'candidates':candidates,'selected':['item0','item1']})
 assert count()==before
 assert req(pm,'GET','/meetings/'+m['id'])['version']==m['version']
 candidates[1]['owner_id']='team2'
 r=req(pm,'POST','/meetings/'+m['id']+'/review',json={'version':m['version'],'candidates':candidates,'selected':['item0','item1']})
 assert len(r['created'])==2
 assert all(x['owner_id']=='team2' and x['reviewer_id']=='team1' for x in tasks() if x['id'] in r['created'])
 # Checks can remain unassigned too; no silent PM fallback in finalize.
 req(pm,'POST','/tasks',201,json={'project_id':p['id'],'title':'확인 담당자 미정','kind':'확인사항'})
 # Fresh one-person project and candidates for interactive QA; no live data.
 p=req(pm,'POST','/projects',201,json={'name':'배정 화면 확인 · PM 한 명','members':[]})
 m=meeting('업무 배정 흐름 점검',reviewer='team1')
 print('PASS: unassigned registration (both paths), explicit self-completion, review restrictions, membership, later-assignment notice, atomic batch, retained evidence.',flush=True)
 print('Browser fixture meeting: '+m['id'],flush=True)

if __name__=='__main__':
 with tempfile.TemporaryDirectory(prefix='b2-assignment-qa-') as tmp:
  os.environ.update(B2_TEAM_DATA_DIR=tmp,B2_TEAM_TESTING='1',B2_DEMO_MODE='1')
  os.environ.pop('B2_TEAM_LAN_IP',None);os.environ.pop('B2_TEAM_LAN_CIDR',None)
  from work.v17 import server as w
  w.COOKIE='b2_assignment_qa_session';w.team_config.ORIGINS.add('http://127.0.0.1:8772')
  exercise()
  if '--serve' in sys.argv:
   import uvicorn
   uvicorn.run(w.app,host='127.0.0.1',port=8772,proxy_headers=False,access_log=False)
