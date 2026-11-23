"""Four independent clients and shared writes, using a disposable empty workspace."""
import os,tempfile,importlib,json,hashlib
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi.testclient import TestClient

def main():
 with tempfile.TemporaryDirectory(prefix='b2-v17-team-') as tmp:
  os.environ.update(B2_TEAM_DATA_DIR=tmp,B2_TEAM_TESTING='1',B2_TEAM_LAN_IP='192.168.2.165',B2_TEAM_LAN_CIDR='192.168.2.0/24')
  w=importlib.import_module('work.v17.server')
  headers={'X-B2-Request':'workspace','Origin':'http://testserver'}
  def request(client,method,path,status=200,**kw):
   r=client.request(method,'/api'+path,**kw)
   assert r.status_code==status,(method,path,r.status_code,r.text)
   return r.json()
  with ExitStack() as stack:
   clients=[stack.enter_context(TestClient(w.app,headers=headers)) for _ in range(4)]
   pm,a,b,c=clients
   for i,client in enumerate(clients,1):
    request(client,'POST','/demo-login',json={'username':f'team{i}'})
    boot=request(client,'GET','/bootstrap')
    assert boot['user']['id']==f'team{i}' and len(boot['people'])==4
    assert not any(boot[k] for k in ('projects','meetings','tasks','imports','archived_meetings'))
    assert not request(client,'GET','/notifications')['items']
   with w.connect() as db:assert {r[0] for r in db.execute('SELECT DISTINCT kind FROM records')}=={'person'}
   request(a,'POST','/projects',403,json={'name':'Staff must not create'})
   p=request(pm,'POST','/projects',201,json={'name':'공동 테스트 검증','pm_id':'team1','members':['team2','team3','team4']})
   for client in clients:assert request(client,'GET','/bootstrap')['projects'][0]['id']==p['id']
   text='회의명: 공동 업무 점검\n회의일: 2026-11-09\n팀원 2는 도면 번호를 대조하고 검토를 요청한다.'
   draft=request(a,'POST','/meeting-imports',201,data={'text':text})
   saved=request(a,'PATCH','/meeting-imports/'+draft['id'],json={'version':1,'title':'공동 업무 점검','meeting_date':'2026-11-09','body':text,'project_id':p['id'],'review_bundle':{'changes':[]},'review_confirmed':True})
   mid=request(a,'POST','/meeting-imports/'+draft['id']+'/finalize',201,json={'version':saved['version']})['id']
   meeting=request(pm,'GET','/meetings/'+mid)
   assert meeting['document_status']=='등록 완료'
   request(a,'POST','/meetings/'+mid+'/document-action',json={'version':meeting['version'],'action':'submit'})
   meeting=request(pm,'GET','/meetings/'+mid)
   request(b,'POST','/meetings/'+mid+'/document-action',403,json={'version':meeting['version'],'action':'approve'})
   request(pm,'POST','/meetings/'+mid+'/document-action',json={'version':meeting['version'],'action':'approve'})
   for client in clients:assert request(client,'GET','/meetings/'+mid)['document_status']=='확정'
   t=request(pm,'POST','/tasks',201,json={'project_id':p['id'],'title':'도면 번호 대조','owner_id':'team2','reviewer_id':'team1','requires_review':True,'description':'대조 결과를 기록하고 검토 요청'})
   assert any(n['target_id']==t['id'] for n in request(a,'GET','/notifications')['items'])
   request(b,'POST','/tasks/'+t['id']+'/actions',403,json={'version':1,'action':'start'})
   t=request(a,'POST','/tasks/'+t['id']+'/actions',json={'version':1,'action':'submit','note':'도면 번호를 대조했습니다.'})
   request(c,'POST','/tasks/'+t['id']+'/actions',403,json={'version':t['version'],'action':'approve'})
   done=request(pm,'POST','/tasks/'+t['id']+'/actions',json={'version':t['version'],'action':'approve'})
   assert done['status']=='완료'
   for client in clients:assert request(client,'GET','/bootstrap')['tasks'][0]['status']=='완료'
   # Two writes using one displayed version: exactly one wins; the other gets a conflict.
   concurrent=request(pm,'POST','/tasks',201,json={'project_id':p['id'],'title':'동시 저장 확인','owner_id':'team3','reviewer_id':'team1'})
   def save_note(note):
    return b.post('/api/tasks/'+concurrent['id']+'/actions',json={'version':1,'action':'draft','note':note}).status_code
   with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(save_note,['first','second']))==[200,409]
   w.init()
   after=request(pm,'GET','/bootstrap')
   assert len(after['people'])==4 and len(after['projects'])==1 and len(after['meetings'])==1 and len(after['tasks'])==2
   request(pm,'POST','/demo-login',403,json={'username':'team1'},headers={'Origin':'http://evil.invalid'})
   assert pm.get('/api/health',headers={'Host':'evil.invalid'}).status_code==400
   blank=TestClient(w.app)
   assert blank.post('/api/demo-login',json={'username':'team1'}).status_code==403
   blank.cookies.set('b2_v16_session','old-workspace-cookie')
   assert blank.get('/api/bootstrap').status_code==401
   assert w.team_config.allowed_client('192.168.2.42')
   assert w.team_config.allowed_client('127.0.0.1')
   assert not w.team_config.allowed_client('192.168.3.42')
   assert not w.team_config.allowed_client('8.8.8.8')
   lan=TestClient(w.app,client=('192.168.2.42',50000),base_url='http://192.168.2.165:8771',headers={'X-B2-Request':'workspace','Origin':'http://192.168.2.165:8771'})
   assert lan.post('/api/demo-login',json={'username':'team4'}).status_code==200
   assert lan.get('/api/bootstrap').json()['user']['id']=='team4'
   outside=TestClient(w.app,client=('192.168.3.42',50000),base_url='http://192.168.2.165:8771')
   assert outside.get('/api/health').status_code==403
   for client in (blank,lan,outside):client.close()
  print('PASS: empty four-account workspace; independent sessions; shared meetings/tasks/notifications; PM permissions; concurrent-write conflict; restart persistence; LAN/Host/Origin boundaries.')

if __name__=='__main__':main()
