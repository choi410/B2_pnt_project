import os,tempfile
os.environ['B2_TEAM_TESTING']='1'
os.environ['B2_TEAM_DATA_DIR']=tempfile.mkdtemp(prefix='b2-v31-requirements-')
from fastapi.testclient import TestClient
from work.v3.server import app,legacy as w
from work.v3.requirements import explicit_metadata,related
import pytest

def test_explicit_metadata_not_recipient_or_meeting_date():
 people=[{'name':'진효창'},{'name':'김양일'}]
 result=explicit_metadata([{'id':'L1','text':'회의일: 2026-11-02. 진효창: 2026-11-20까지 사양서를 작성해 김양일에게 전달한다.'}],people)
 assert result['owner']=='진효창' and result['due']=='2026-11-20'
 assert not explicit_metadata([{'id':'L2','text':'진효창이 검토 결과를 설명했다. 고객은 2026-12-18 납품을 요청했다.'}],people)['owner']
 assert not explicit_metadata([{'id':'L2','text':'납품일을 2026-12-18에서 2026-12-23으로 변경 요청했다.'}],people)['due']
 assert related('압연 속도','진효창: 2026-11-20까지 속도 상향을 검토한다.')
 assert not related('건조로 설정 온도 상한','배근우가 건조로 구성품의 공급 일정을 확인한다.')

def test_ambiguous_fields_are_not_guessed():
 result=explicit_metadata([{'id':'L1','text':'진효창은 2026-11-20까지 도면을 작성한다. 김양일은 2026-11-22까지 검토한다.'}],[{'name':'진효창'},{'name':'김양일'}])
 assert result['owner']==result['due']==''
 assert result['owner_ambiguous'] and result['due_ambiguous']

@pytest.fixture
def scenario(monkeypatch):
 monkeypatch.setattr(w,'now',lambda:'2026-11-13T14:00:00+09:00')
 with TestClient(app,headers={'X-B2-Request':'workspace'}) as client:
  assert client.post('/api/demo-login',json={'username':'team1'}).status_code==200
  project=client.post('/api/projects',json={'name':'요구사항 검증 '+w.uid()[:6],'members':['team1','team2']}).json()
  m={'id':w.uid(),'project_id':project['id'],'title':'사양 회의','date':'2026-11-10','author':'team1','source':'압연 속도를 135 m/min으로 합의했다.','revision':1,'version':1,'analysis_state':'ready','lines':[{'id':'L1','text':'압연 속도를 135 m/min으로 합의했다.'},{'id':'L2','text':'진효창: 2026-11-20까지 속도 135 m/min을 사양서에 반영한다.'}],'reviewed_bundle':{'candidates':[{'description':'사양서 반영','evidence':['L2']}]},'candidates':[],'created_at':w.now()}
  e={'id':w.uid(),'project_id':project['id'],'meeting_id':m['id'],'source_revision':1,'title':'압연 속도','category':'사양','before':'','after':'135 m/min','business_state':'확정','evidence':['L1'],'review_state':'검토 전','version':1,'effective_date':m['date'],'created_at':w.now()}
  with w.connect() as c:w.save(c,'meeting',m);w.save(c,'change_event',e)
  yield client,project,m,e

def reqs(client,pid):return [r for r in client.get('/api/v3/workspace').json()['requirements'] if r['project_id']==pid]

def test_projection_correction_conflicts_and_new_record(scenario):
 client,p,m,e=scenario
 row=reqs(client,p['id'])[0]
 assert row['owner']=='진효창' and row['due']=='2026-11-20'
 assert row['state']=='미등록' and row['change_kind']=='신규'
 assert row['evidence']==['L1','L2'] and not row['risks'] and not row['risk']
 body={k:row[k] for k in ('version','signature','owner','due','state','result')};body['state']='조치 완료'
 assert client.patch('/api/v3/requirements/'+row['id'],json=body).status_code==200
 assert not reqs(client,p['id'])[0]['risk']
 assert client.patch('/api/v3/requirements/'+row['id'],json=body).status_code==409
 with w.connect() as c:
  e.update(after='140 m/min',version=2);w.save(c,'change_event',e)
 changed=reqs(client,p['id'])[0]
 assert changed['state']=='미등록' and changed['risks']==['새 기록 확인 필요']

def test_acl_stale_deleted_and_cancelled(scenario):
 client,p,m,e=scenario
 row=reqs(client,p['id'])[0];body={k:row[k] for k in ('version','signature','owner','due','state','result')}
 client.post('/api/demo-login',json={'username':'team2'})
 assert client.patch('/api/v3/requirements/'+row['id'],json=body).status_code==403
 client.post('/api/demo-login',json={'username':'team3'})
 assert not reqs(client,p['id'])
 assert client.patch('/api/v3/requirements/'+row['id'],json=body).status_code==404
 client.post('/api/demo-login',json={'username':'team1'})
 with w.connect() as c:m['analysis_stale']=True;w.save(c,'meeting',m)
 assert not reqs(client,p['id'])
 with w.connect() as c:
  m['analysis_stale']=False;e['business_state']='철회';w.save(c,'meeting',m);w.save(c,'change_event',e)
 assert not reqs(client,p['id'])[0]['risk']
 with w.connect() as c:m['deleted_at']=w.now();w.save(c,'meeting',m)
 assert not reqs(client,p['id'])
 with w.connect() as c:m.pop('deleted_at');w.save(c,'meeting',m)
 assert reqs(client,p['id'])

def test_missing_fields_and_no_double_count(scenario):
 client,p,m,e=scenario
 with w.connect() as c:
  m['reviewed_bundle']={'candidates':[]};w.save(c,'meeting',m)
  older={**e,'id':w.uid(),'after':'120 m/min','effective_date':'2026-11-01','created_at':'2026-11-01T00:00:00+09:00'};w.save(c,'change_event',older)
 rows=reqs(client,p['id'])
 assert len(rows)==1
 assert '담당자 미정' in rows[0]['risks'] and '기한 미정' in rows[0]['risks']
 assert rows[0]['event_count']==2 and rows[0]['change_kind']=='변경'

def test_optional_status_preserves_real_deadline_warning(scenario):
 client,p,m,e=scenario
 with w.connect() as c:
  m['lines'][1]['text']=m['lines'][1]['text'].replace('2026-11-20','2026-11-12');w.save(c,'meeting',m)
 row=reqs(client,p['id'])[0]
 assert row['state']=='미등록' and row['risks']==['기한 경과']
 body={k:row[k] for k in ('version','signature','owner','due','state','result')};body['state']='조치 완료'
 assert client.patch('/api/v3/requirements/'+row['id'],json=body).status_code==200
 assert reqs(client,p['id'])[0]['risks']==[]

def test_legacy_unrecorded_state_is_read_and_saved_compatibly(scenario):
 client,p,m,e=scenario
 row=reqs(client,p['id'])[0]
 body={k:row[k] for k in ('version','signature','owner','due','state','result')};body['state']='처리 결과 미확인'
 assert client.patch('/api/v3/requirements/'+row['id'],json=body).status_code==200
 changed=reqs(client,p['id'])[0]
 assert changed['state']=='미등록' and not changed['risk']
 with w.connect() as c:
  note=w.read(c,'requirement_note',row['id']);note['state']='처리 결과 미확인';w.save(c,'requirement_note',note)
 assert reqs(client,p['id'])[0]['state']=='미등록'
