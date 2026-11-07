import json
from concurrent.futures import Future
import pytest
from fastapi.testclient import TestClient
import server

def result():
    return {'summary':'간섭 검토 후 변경 여부를 판단한다.','items':[{'category':'할일','content':'간섭 검토 결과 공유','owner':'이준호','due':'2026-11-06','agreement':None,'evidence_ids':['L001']}],'review_points':[]}

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DB',tmp_path/'test.sqlite3')
    monkeypatch.setattr(server.ENGINE,'generate',lambda source,retry=False:(json.dumps(result(),ensure_ascii=False),{'seconds':0,'model':'TEST DOUBLE'}))
    def synchronous(fn,*args):
        f=Future(); f.set_result(fn(*args));return f
    monkeypatch.setattr(server.POOL,'submit',synchronous)
    with TestClient(server.app) as c: yield c

def create(client):
    response=client.post('/api/meetings',json={'project':'P-test','source':'이준호가 2026-11-06까지 간섭 검토 결과를 공유한다.'})
    assert response.status_code==202
    return response.json()

def test_human_review_persistence_and_duplicate_guard(client):
    record=create(client)
    assert record['status']=='review' and record['reviewed'] is None
    assert create(client)['id']==record['id']
    data={'version':record['version'],'reviewed':False,'analysis':result()}
    assert client.post(f"/api/meetings/{record['id']}/review",json=data).status_code==422
    data['reviewed']=True
    data['analysis']['items'][0]['owner']='담당자 재확인 필요'
    response=client.post(f"/api/meetings/{record['id']}/review",json=data)
    assert response.status_code==200
    saved=response.json()
    assert saved['analysis']['items'][0]['owner']=='이준호'
    assert saved['reviewed']['items'][0]['owner']=='담당자 재확인 필요'
    assert saved['reviewer_id']=='pm' and saved['reviewer_name']=='박서연' and saved['reviewed_at']
    assert saved['work_items'][0]['source_index']==0 and saved['work_items'][0]['status']=='미착수'
    assert client.post(f"/api/meetings/{record['id']}/review",json=data).status_code==409
    server.initialize()
    again=client.get(f"/api/meetings/{record['id']}").json()
    assert again['reviewed']==saved['reviewed'] and again['source']==record['source'] and again['reviewer_name']=='박서연'
    assert client.get(f"/api/meetings/{record['id']}/export").status_code==200

def test_invalid_evidence_stale_version_and_date_blocked(client):
    record=create(client);data={'version':record['version'],'reviewed':True,'analysis':result()}
    data['analysis']['items'][0]['evidence_ids']=['L999']
    assert client.post(f"/api/meetings/{record['id']}/review",json=data).status_code==422
    data['analysis']=result();data['version']=0
    assert client.post(f"/api/meetings/{record['id']}/review",json=data).status_code==409
    data['version']=record['version'];data['analysis']['items'][0]['due']='2026-02-30'
    assert client.post(f"/api/meetings/{record['id']}/review",json=data).status_code==422
    assert client.get(f"/api/meetings/{record['id']}").json()['reviewed'] is None

def test_one_retry_and_content_errors_do_not_trigger_more_attempts():
    calls=[]
    def fixed(source,retry=False):
        calls.append(retry)
        return ('broken' if not retry else json.dumps(result())),{'seconds':1}
    output,metrics,warnings=server.analyze_with_retry('간섭 검토 결과 공유',fixed)
    assert calls==[False,True] and metrics['attempts']==2 and metrics['seconds']==2
    calls.clear()
    def broken(source,retry=False):calls.append(retry);return 'broken',{}
    with pytest.raises(ValueError):server.analyze_with_retry('회의록',broken)
    assert len(calls)==2
    calls.clear()
    bad=result();bad['items'][0]['evidence_ids']=['L999']
    def invalid_content(source,retry=False):calls.append(retry);return json.dumps(bad),{}
    _,_,warnings=server.analyze_with_retry('회의록',invalid_content)
    assert len(calls)==1 and warnings

def test_docx_template_order_and_upload_errors(client):
    sample=client.get('/api/sample').json()
    assert sample['source'].index('프로젝트명')<sample['source'].index('회의 안건')<sample['source'].index('후속 조치')
    assert 'Rev.A' in sample['source'] and '가상 사례' in sample['source']
    assert sample['title']=='코팅 설비 안전커버 및 점검 보고 검토'
    with server.SAMPLE.open('rb') as f:
        uploaded=client.post('/api/import',files={'file':('sample.docx',f)})
    assert uploaded.json()==sample
    assert client.post('/api/import',files={'file':('bad.docx',b'no zip')}).status_code==400
    assert client.post('/api/import',files={'file':('bad.pdf',b'pdf')}).status_code==400
    assert client.post('/api/import',files={'file':('big.docx',b'x'*(4*1024*1024+1))}).status_code==400

def test_updated_core_document_formats_and_dual_engine_names(client):
    catalog=client.get('/api/document-formats').json()
    assert catalog['architecture']['name']=='하이브리드 듀얼 엔진'
    assert [engine['name'] for engine in catalog['architecture']['engines']]==['문서 해석 엔진','근거 규칙 검증 엔진']
    assert [form['code'] for form in catalog['formats']]==['DOC-01','DOC-02','DOC-03','DOC-04','DOC-05']
    kickoff=catalog['formats'][0]
    assert kickoff['title']=='킥오프 미팅 기록서'
    assert kickoff['sections'][2]['fields']==['요구번호','요구·결정 내용','확정 여부']
    inspection=catalog['formats'][4]
    assert inspection['sections'][1]['fields']==['요구번호·검사 항목','판정 기준','실측값·단위','판정']
    health=client.get('/api/health').json()
    assert health['architecture']=='하이브리드 듀얼 엔진' and len(health['engines'])==2

def test_local_origin_and_unauthorized_export(client):
    assert client.post('/api/meetings',headers={'Origin':'https://unrelated.example'},json={'source':'외부 사이트 요청 테스트'}).status_code==403
    record=create(client)
    assert client.get(f"/api/meetings/{record['id']}/export").status_code==409

def test_interrupted_job_preserves_source_for_manual_review(client,monkeypatch):
    monkeypatch.setattr(server.POOL,'submit',lambda *args:None)
    record=client.post('/api/meetings',json={'source':'간섭 검토가 필요하나 담당자 및 기한은 아직 결정하지 않았다.'}).json()
    assert record['status']=='queued'
    server.initialize()
    recovered=client.get(f"/api/meetings/{record['id']}").json()
    assert recovered['status']=='failed' and recovered['source']==record['source']
    data={'version':recovered['version'],'reviewed':True,'analysis':{'summary':'담당자와 기한 미정','items':[],'review_points':[{'content':'간섭 검토 담당자 및 기한 결정 필요','evidence_ids':['L001']}]}}
    assert client.post(f"/api/meetings/{record['id']}/review",json=data).status_code==200
