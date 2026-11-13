import copy, os, tempfile
from fastapi.testclient import TestClient
from work.v17.home_attention import attention_items

def main():
 people=[{'id':'p','name':'김양일'},{'id':'a','name':'진효창'},{'id':'b','name':'최인혁'}]
 projects=[{'id':'allowed','pm':'p','members':['p','a','b']}]
 candidate={'id':'c','kind':'업무','title':'도면 작성','owner_id':None,'due':None,'state':'draft','evidence':['L001']}
 source='진효창이 2026-11-10까지 도면을 작성한다.'
 meeting={'id':'m','project_id':'allowed','title':'설계 협의','date':'2026-11-09','revision':1,'registered_revision':1,'overview':{'revision':1},'reviewed_bundle':{'candidates':[candidate]},'revisions':[{'number':1,'title':'설계 협의','body':source,'date':'2026-11-09','status':'작성 중'}]}
 before=copy.deepcopy(meeting)
 items=attention_items(projects,[meeting],[],people,'2026-11-12')
 assert items[0]['owner_id']=='a' and items[0]['due']=='2026-11-10'
 assert items[0]['reasons']==['기한 경과','처리 결과 확인']
 assert meeting==before,'Display inference must not write an assignment'
 assert attention_items([{**projects[0],'members':['p']}],[meeting],[],people,'2026-11-12')[0]['owner_id']=='a','An explicitly named non-member remains a source contact, not a new project member'
 task={'id':'t','candidate_id':'c','meeting_id':'m','project_id':'allowed','status':'완료'}
 assert attention_items(projects,[meeting],[task],people,'2026-11-12')==[],'Completed linked work suppresses its candidate'
 assert attention_items([], [meeting],[],people,'2026-11-12')==[]
 for patch in ({'deleted_at':'today'},{'revision':2},{'overview':{'revision':2}},{'registered_revision':None}):
  assert attention_items(projects,[{**meeting,**patch}],[],people,'2026-11-12')==[]
 ambiguous=copy.deepcopy(meeting);ambiguous['reviewed_bundle']['candidates'][0]['owner_id']='b'
 assert attention_items(projects,[ambiguous],[],people,'2026-11-12')[0]['reasons'][0]=='담당 확인'
 undated=copy.deepcopy(meeting);undated['revisions'][0]['body']='담당자와 기한은 미정이다.'
 item=attention_items(projects,[undated],[],people,'2026-11-12')[0]
 assert item['owner_id'] is None and not item['due'] and '기한 경과' not in item['reasons']
 check=copy.deepcopy(undated);check['reviewed_bundle']['candidates'][0].update(kind='확인사항',reviewer_id='p')
 assert attention_items(projects,[check],[],people,'2026-11-12')[0]['owner_id'] is None,'Default PM reviewer is not inferred as assignee'
 with tempfile.TemporaryDirectory(prefix='b2-home-attention-qa-') as temp:
  os.environ.update(B2_TEAM_DATA_DIR=temp,B2_TEAM_TESTING='1',B2_DEMO_MODE='1')
  from work.v17 import server as w
  w.init()
  with w.connect() as c:
   # Use SQL for isolated fixtures so unrelated migration logic is not needed.
   import json
   p={'id':'allowed','name':'QA','pm':'team1','members':['team1']}
   m={**meeting,'reviewed_bundle':{'candidates':[{**candidate,'owner_id':'team1'}]}}
   for kind,d in [('project',p),('project',{**p,'id':'private','members':['team2']}),('project',{**p,'id':'archived','deleted_at':'today'}),('meeting',m),('meeting',{**m,'id':'private-m','project_id':'private'}),('meeting',{**m,'id':'archived-m','project_id':'archived'})]:
    c.execute('INSERT INTO records VALUES(?,?,?)',(kind,d['id'],json.dumps(d)))
  client=TestClient(w.app,headers={'X-B2-Request':'workspace'})
  assert client.get('/api/home/attention').status_code==401
  assert client.post('/api/demo-login',json={'username':'team1'}).status_code==200
  res=client.get('/api/home/attention');assert res.status_code==200,res.text
  assert [x['meeting_id'] for x in res.json()['items']]==['m'],'Enforce membership and archive boundaries'
 print('PASS: source-backed contacts/dates; no false completion; linked work; stale/trash exclusions; read-only data; authenticated project isolation.')

if __name__=='__main__':main()
