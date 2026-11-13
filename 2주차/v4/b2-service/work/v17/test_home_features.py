"""Isolated checks for private notes, PM edits, and source-bound suggestions."""
import os,tempfile
from fastapi.testclient import TestClient

def exercise(w):
 from work.v17.test_demo import exercise as seed
 ids=seed(w);pid=ids['project_id'];mid=ids['meeting_id']
 clients=[TestClient(w.app,headers={'X-B2-Request':'workspace'}) for _ in range(4)]
 for i,c in enumerate(clients):assert c.post('/api/demo-login',json={'username':f'team{i+1}'}).status_code==200
 pm,staff,member,outsider=clients
 def req(c,method,path,code=200,**kwargs):
  r=c.request(method,'/api'+path,**kwargs);assert r.status_code==code,(path,r.status_code,r.text);return r.json()
 rng='/calendar/memos?start=2026-11-01&end=2026-12-12'
 req(pm,'PUT','/calendar/memos/2026-11-12',json={'text':'고객 도면 협의 · 준비 자료 확인'})
 assert req(staff,'GET',rng)=={}
 req(staff,'PUT','/calendar/memos/2026-11-12',json={'text':'team2 전용'})
 assert req(pm,'GET',rng)['2026-11-12'].startswith('고객')
 req(pm,'PUT','/calendar/memos/2026-11-13',json={'text':'삭제 확인'})
 req(pm,'PUT','/calendar/memos/2026-11-13',json={'text':''})
 assert '2026-11-13' not in req(pm,'GET',rng)
 req(pm,'GET','/calendar/memos?start=2026-11-01&end=2026-12-13',422)
 req(pm,'PUT','/calendar/memos/2026-02-30',422,json={'text':'x'})
 req(pm,'PUT','/calendar/memos/2026-11-12',422,json={'text':'x'*1001})
 req(TestClient(w.app),'GET',rng,401)
 req(staff,'GET',f'/projects/{pid}/focus-suggestions',403)
 req(outsider,'GET',f'/projects/{pid}/focus-suggestions',403)
 initial=req(pm,'GET',f'/projects/{pid}/overview')
 form={'version':initial['version'],'current_stage':'설계 검토','next_goal':'고객 도면 승인 받기','next_goal_date':'2026-11-20'}
 req(staff,'PATCH',f'/projects/{pid}/focus',403,json=form)
 req(pm,'PATCH',f'/projects/{pid}/focus',422,json={**form,'next_goal':'','next_goal_date':'2026-11-20'})
 result=req(pm,'PATCH',f'/projects/{pid}/focus',json=form)
 assert result['purpose']==initial['purpose'] and result['scope']==initial['scope']
 req(pm,'PATCH',f'/projects/{pid}/focus',409,json=form)
 # Registered, explicit assertions in a disposable source fixture.
 with w.connect() as c:
  m=w.read(c,'meeting',mid)
  source=m['source']+'\n현재 단계: 제작\n다음 목표: 고객 입회 검사 준비'
  m['source']=source
  for rev in m['revisions']:
   if rev['number']==m['registered_revision']:rev['body']=source
  w.save(c,'meeting',m)
 proposed=req(pm,'GET',f'/projects/{pid}/focus-suggestions')
 # Custom stored stages do not silently add guessed defaults.
 assert all(x['field']!='current_stage' for x in proposed['items'])
 goal=next(x for x in proposed['items'] if x['field']=='next_goal')
 applied=req(pm,'PATCH',f'/projects/{pid}/focus',json={'version':result['version'],'current_stage':'설계·구매 병행','next_goal':goal['value'],'next_goal_date':'','suggestion_ids':[goal['id']]})
 assert '설계·구매 병행' in applied['stages']
 # Existing metadata editor must preserve the new date and focus attribution.
 dated=req(pm,'PATCH',f'/projects/{pid}/focus',json={'version':applied['version'],'current_stage':'설계·구매 병행','next_goal':goal['value'],'next_goal_date':'2026-11-24'})
 metadata={k:dated[k] for k in ('version','purpose','scope','next_goal','stages','current_stage')}
 saved=req(pm,'PATCH',f'/projects/{pid}/overview',json=metadata)
 assert saved['next_goal_date']=='2026-11-24' and saved['focus_updated_by']=='team1'
 with w.connect() as c:
  m=w.read(c,'meeting',mid);m['revision']+=1;w.save(c,'meeting',m)
 assert req(pm,'GET',f'/projects/{pid}/focus-suggestions')['stale']
 req(pm,'PATCH',f'/projects/{pid}/focus',409,json={'version':saved['version'],'current_stage':'설계·구매 병행','next_goal':goal['value'],'next_goal_date':'','suggestion_ids':[goal['id']]})
 with w.connect() as c:
  m=w.read(c,'meeting',mid);m['revision']-=1;w.save(c,'meeting',m)
  p=w.read(c,'project',pid);p['overview']['stages'].append('제작');w.save(c,'project',p)
 proposed=req(pm,'GET',f'/projects/{pid}/focus-suggestions')
 assert any(x['field']=='current_stage' and x['value']=='제작' for x in proposed['items'])
 print('PASS: private notes, validation, PM rights, optimistic locking, metadata preservation, grounded suggestions and stale source rejection.',flush=True)
 return ids

def main():
 with tempfile.TemporaryDirectory(prefix='b2-home-calendar-qa-') as temp:
  os.environ.update(B2_TEAM_DATA_DIR=temp,B2_TEAM_TESTING='1',B2_DEMO_MODE='1')
  os.environ.pop('B2_TEAM_LAN_IP',None);os.environ.pop('B2_TEAM_LAN_CIDR',None)
  from work.v17 import server as w
  exercise(w)
if __name__=='__main__':main()
