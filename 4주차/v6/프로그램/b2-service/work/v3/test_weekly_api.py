import io,os,tempfile
os.environ['B2_TEAM_TESTING']='1'
os.environ['B2_TEAM_DATA_DIR']=tempfile.mkdtemp(prefix='b2-v5-weekly-')
from fastapi.testclient import TestClient
import pytest
from work.v3.server import app,legacy as w
from work.v3 import weekly
from work.v3.test_weekly_match import BODY1

S,E='2026-11-16','2026-11-20'
MEMO='11/18 롤프레스 속도 135 재협의 - 완료\n11/20 구동부 배치도 개정 진행중\n11/20 사내 안전 교육 참석 완료'

@pytest.fixture
def scene():
 with TestClient(app,headers={'X-B2-Request':'workspace'}) as client:
  assert client.post('/api/demo-login',json={'username':'team1'}).status_code==200
  project=client.post('/api/projects',json={'name':'한빛셀 전극 롤프레스 '+w.uid()[:5],'members':['team1','team2']}).json()
  m={'id':w.uid(),'project_id':project['id'],'title':'롤프레스 변경 요청 재협의','date':'2026-11-18','author':'team1','source':BODY1,'version':1,
     'analysis_state':'ready','lines':[],'candidates':[],'created_at':w.now()}
  e={'id':w.uid(),'project_id':project['id'],'meeting_id':m['id'],'source_revision':1,'title':'압연 속도','category':'사양','before':'120 m/min','after':'135 m/min',
     'business_state':'확정','evidence':['L009'],'quotes':['압연 속도를 120 m/min에서 135 m/min으로 변경하기로 합의했다.'],'review_state':'확인됨','version':1,'effective_date':'2026-11-18','created_at':w.now()}
  with w.connect() as c:
   w.save(c,'meeting',m);m=w.read(c,'meeting',m['id']);m['registered_revision']=1;w.save(c,'meeting',m);w.save(c,'change_event',e)
  yield client,project,m,e

def make(client,pid):
 rows=client.post('/api/v3/weekly/parse',json={'text':MEMO,'start':S,'end':E}).json()['rows']
 matched=client.post('/api/v3/weekly/match',json={'rows':rows,'start':S,'end':E}).json()
 mine=lambda c:c['project_id']==pid
 # 테스트 DB에는 같은 이름의 프로젝트가 여러 개 쌓여 자동 선택이 꺼진다(모호함). 사용자가 고르듯 이 프로젝트의 직접 후보를 고른다.
 links={r['id']:[c['id'] for c in r['candidates'] if mine(c) and c['confidence']=='high' and c['kind'] in ('change','action')] for r in matched['rows']}
 extras=[x['id'] for x in matched['extras'] if mine(x) and x['group'] in ('next','open')]
 r=client.post('/api/v3/weekly/reports',json={'title':'주간 업무보고','start':S,'end':E,'rows':rows,'links':links,'extras':extras})
 assert r.status_code==201,r.text
 return r.json(),matched

def edit_body(report,**change):
 body={'version':report['version'],'title':report['title'],'checked':report['checked'],
       'sections':[{'key':s['key'],'items':[{'id':i['id'],'type':i['type'],'text':i['text'],'level':i['level']} for i in s['items']]} for s in report['sections']],
       'actions':[{'task':a['task'],'owner':a['owner'],'due':a['due']} for a in report['actions']]}
 body.update(change);return body

def test_parse_match_create_flow(scene):
 client,project,m,e=scene
 report,matched=make(client,project['id'])
 states={r['text']:r['match_state'] for r in matched['rows']}
 assert states['사내 안전 교육 참석']=='none' and states['롤프레스 속도 135 재협의'] in ('linked','check')
 done=[i['text'] for i in report['sections'][0]['items']]
 assert '압연 속도 120 m/min → 135 m/min 확정 (11/18 회의)' in done and '사내 안전 교육 참석 — 완료' in done
 change=next(i for i in report['sections'][0]['items'] if i['text'].startswith('압연 속도 120'))
 assert change['evidence'][0]['meeting_id']==m['id'] and change['evidence'][0]['lines']==['L009']
 assert any(a['owner']=='진효창' and a['due']=='11/23' for a in report['actions'])
 assert any(a['owner']=='미정' for a in report['actions'])
 listed=client.get('/api/v3/weekly/reports').json()
 assert [d['id'] for d in listed if d['id']==report['id']]==[report['id']]

def test_edit_keeps_evidence_marks_edited_and_checks_version(scene):
 client,project,m,e=scene
 report,_=make(client,project['id'])
 body=edit_body(report)
 target=next(i for i in body['sections'][0]['items'] if i['text'].startswith('압연 속도 120'))
 target['text']='압연 속도 135 m/min으로 변경 확정'
 body['sections'][1]['items'].append({'type':'item','text':'협력사 견적 접수','level':0})
 body['actions'][0]['owner']='김양일';body['checked']=True
 saved=client.patch('/api/v3/weekly/reports/'+report['id'],json=body)
 assert saved.status_code==200,saved.text
 saved=saved.json()
 item=next(i for i in saved['sections'][0]['items'] if i['id']==target['id'])
 assert item['edited'] and item['evidence'][0]['lines']==['L009']
 added=saved['sections'][1]['items'][-1]
 assert added['source']=='manual' and added['evidence']==[]
 assert saved['actions'][0]['edited'] and saved['actions'][0]['evidence'] and saved['checked'] and saved['version']==2
 assert client.patch('/api/v3/weekly/reports/'+report['id'],json=body).status_code==409
 bad=edit_body(saved);bad['sections']=bad['sections'][::-1]
 assert client.patch('/api/v3/weekly/reports/'+report['id'],json=bad).status_code==422

def test_report_is_private_and_sources_follow_project_membership(scene):
 client,project,m,e=scene
 report,_=make(client,project['id'])
 unit='C:'+e['id']
 with TestClient(app,headers={'X-B2-Request':'workspace'}) as other:
  assert other.post('/api/demo-login',json={'username':'team3'}).status_code==200
  assert other.get('/api/v3/weekly/reports/'+report['id']).status_code==404
  assert other.get('/api/v3/weekly/reports/'+report['id']+'/word').status_code==404
  assert all(d['id']!=report['id'] for d in other.get('/api/v3/weekly/reports').json())
  assert other.get('/api/v3/weekly/units',params={'meeting_id':m['id']}).status_code==404
  rows=[{'id':'R1','date':'2026-11-18','text':'롤프레스 속도 135 재협의','status':'완료'}]
  seen=other.post('/api/v3/weekly/match',json={'rows':rows,'start':S,'end':E}).json()
  assert all(c['project_id']!=project['id'] for r in seen['rows'] for c in r['candidates'])
  blocked=other.post('/api/v3/weekly/reports',json={'title':'x','start':S,'end':E,'rows':rows,'links':{'R1':[unit]},'extras':[]})
  assert blocked.status_code==409
 assert any(u['id']==unit for u in client.get('/api/v3/weekly/units',params={'meeting_id':m['id']}).json()['units'])

def test_word_export_contains_sections_table_and_sources(scene):
 from docx import Document
 client,project,m,e=scene
 report,_=make(client,project['id'])
 res=client.get('/api/v3/weekly/reports/'+report['id']+'/word')
 assert res.status_code==200 and 'wordprocessingml' in res.headers['content-type']
 doc=Document(io.BytesIO(res.content))
 text='\n'.join(p.text for p in doc.paragraphs)
 assert '주간 업무보고' in text and '1. 금주 실적' in text and '2. 차주 계획' in text and '3. 조치사항 (담당자 / 기한)' in text
 assert '압연 속도 120 m/min → 135 m/min 확정 (11/18 회의)' in text and '롤프레스 변경 요청 재협의' in text and '검토 전 초안' in text
 assert '회의 안건' not in text and '추가 확인 사항' not in text
 assert doc.tables[0].cell(2,1).text==S+' ~ '+E and doc.tables[0].cell(4,1).text=='김양일'
 grid=[[c.text for c in r.cells] for r in doc.tables[1].rows]
 assert grid[0]==['조치사항','담당','기한'] and ['압연 속도 135 m/min을 반영한 구동부 배치도 개정','진효창','11/23'] in grid

def test_file_upload_and_validation(scene):
 from openpyxl import Workbook
 client,*_=scene
 wb=Workbook();ws=wb.active;ws.append(['일자','업무 내용','상태']);ws.append(['11/18','롤프레스 속도 135 재협의','완료'])
 out=io.BytesIO();wb.save(out)
 res=client.post('/api/v3/weekly/parse-file',data={'start':S,'end':E},files={'file':('주간.xlsx',out.getvalue())})
 assert res.status_code==200 and res.json()['rows'][0]['status']=='완료' and res.json()['rows'][0]['date']=='2026-11-18'
 assert client.post('/api/v3/weekly/parse-file',data={'start':S,'end':E},files={'file':('a.hwp',b'x')}).status_code==422
 assert client.post('/api/v3/weekly/parse',json={'text':'  ','start':S,'end':E}).status_code==422
 assert client.post('/api/v3/weekly/parse',json={'text':'a','start':E,'end':S}).status_code==422
 assert client.post('/api/v3/weekly/match',json={'rows':[],'start':'2026-01-01','end':'2026-03-01'}).status_code==422
 with TestClient(app,headers={'X-B2-Request':'workspace'}) as anonymous:
  assert anonymous.post('/api/v3/weekly/parse',json={'text':'a','start':S,'end':E}).status_code==401

def test_delete_hides_report(scene):
 client,project,*_=scene
 report,_=make(client,project['id'])
 assert client.delete('/api/v3/weekly/reports/'+report['id']).json()=={'ok':True}
 assert client.get('/api/v3/weekly/reports/'+report['id']).status_code==404
 assert all(d['id']!=report['id'] for d in client.get('/api/v3/weekly/reports').json())

def test_stale_change_event_is_not_used(scene):
 client,project,m,e=scene
 with w.connect() as c:
  e2=w.read(c,'change_event',e['id']);e2['source_revision']=0;w.save(c,'change_event',e2)
 units=client.get('/api/v3/weekly/units',params={'meeting_id':m['id']}).json()['units']
 assert not any(u['kind']=='change' for u in units)
 assert any(u['kind']=='decision' and u['text'].startswith('압연 속도를 120 m/min에서') for u in units)

def test_polish_accepts_only_wording_changes():
 ok=weekly.polish_check
 assert ok('롤프레스 속도 135 재협의 — 완료','롤프레스 속도 135 재협의 완료')
 assert not ok('롤프레스 속도 135 재협의 — 완료','롤프레스 속도 140 재협의 완료')       # 수치 변경
 assert not ok('구동부 배치도 개정 — 진행 중','구동부 배치도 개정 및 승인 완료')            # 없는 사실 추가
 assert not ok('도면 검토 — 진행 중','도면 검토 진행 중이며 다음 주 화요일까지 마무리할 예정으로 일정 조율 중')  # 덧붙임
 assert not ok('도면 검토','')

def test_polish_route_filters_model_output(scene,monkeypatch):
 import json
 from work.v17 import llm
 client,project,*_=scene
 report,_=make(client,project['id'])
 res=client.post('/api/v3/weekly/reports/'+report['id']+'/polish',json={'version':report['version']})
 assert res.status_code==503  # AI 환경이 없으면 초안은 그대로, 기능만 안내
 items=[i for s in report['sections'] for i in s['items'] if i['type']=='item' and i['level']==0 and i['source'] in ('memo','linked')]
 answers=[{'id':items[0]['id'],'text':items[0]['text'].replace(' — ',' ')},{'id':items[1]['id'],'text':items[1]['text']+' 및 고객 승인 999건'},{'id':'없는id','text':'임의 문장'}]
 monkeypatch.setattr(llm,'stage_available',lambda:True)
 monkeypatch.setattr(llm,'stage_chat',lambda messages,n,schema=None:('참고: '+json.dumps({'items':answers},ensure_ascii=False),{}))
 res=client.post('/api/v3/weekly/reports/'+report['id']+'/polish',json={'version':report['version']})
 assert res.status_code==200
 assert res.json()['proposals']==[{'id':items[0]['id'],'before':items[0]['text'],'after':items[0]['text'].replace(' — ',' ')}]
 assert client.get('/api/v3/weekly/reports/'+report['id']).json()['version']==report['version']  # 제안만, 저장 안 함
