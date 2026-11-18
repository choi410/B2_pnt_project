"""Behavior checks use an isolated database and controlled inference responses."""
import os, tempfile
from pathlib import Path
os.environ['B2_TEAM_TESTING']='1'
os.environ['B2_TEAM_DATA_DIR']=tempfile.mkdtemp(prefix='b2-v3-tests-')
from fastapi.testclient import TestClient
from work.v3.server import app, legacy as w
from work.v3.service import match_project,calendar_events,run_analysis,parse_file
import pytest

class Queue:
    def __init__(self):self.jobs=[]
    def submit(self,*args):self.jobs.append(args)

@pytest.fixture
def client(monkeypatch):
    queue=Queue();monkeypatch.setattr(w,'POOL',queue)
    with TestClient(app,headers={'X-B2-Request':'workspace'}) as c:
        assert c.post('/api/demo-login',json={'username':'team1'}).status_code==200
        yield c,queue

def test_project_match():
    ps=[{'id':'P-001','name':'한빛셀 롤프레스 1호기'},{'id':'P-002','name':'서린 코팅라인'}]
    assert match_project('P-001_회의.txt','','',ps)['project_id']=='P-001'
    assert match_project('회의.txt','','한빛셀 롤프레스 1호기 협의',ps)['project_id']=='P-001'
    assert match_project('P-001.txt','','',ps,'P-002')['needs_check']
    assert match_project('회의.txt','없는 프로젝트','',ps,'P-001')['needs_check']
    assert match_project('P-001_P-002.txt','','',ps)['project_id']==''

def test_projects_are_newest_first_even_with_random_codes(client):
    c,_=client
    items=[c.post('/api/projects',json={'name':'정렬 검증 '+str(i),'members':['team1']}).json() for i in range(3)]
    with w.connect() as db:
        for i,p in enumerate(items):
            # The last two have identical timestamps; insertion order breaks the tie.
            p['created_at']='2026-01-01T09:00:00+09:00' if i==0 else '2026-01-02T09:00:00+09:00'
            w.save(db,'project',p)
    ids={p['id'] for p in items}
    ordered=[p['id'] for p in c.get('/api/v3/workspace').json()['projects'] if p['id'] in ids]
    assert ordered==[p['id'] for p in reversed(items)]

def test_connected_registration_analysis_and_restore(client,monkeypatch):
    c,queue=client
    p=c.post('/api/projects',json={'name':'연결 검증 프로젝트','members':['team1','team2']}).json()
    pid=p['id']
    content=f'프로젝트: {p["name"]}\n회의명: 일정 확인\n회의일: 2026-11-12\n김양일은 2026-11-13부터 2026-11-16까지 배치도를 검토한다.\n납품일은 2026-12-18로 합의했다.'
    response=c.post('/api/v3/imports',files=[('files',('회의.txt',content.encode(),'text/plain')),('files',('안됨.exe',b'abc','application/octet-stream'))])
    assert response.status_code==200,response.text
    d=response.json();assert len(d['items'])==len(d['errors'])==1
    item=d['items'][0];assert item['project_id']==pid
    body={'items':[{'id':item['id'],'project_id':pid,'title':item['title'],'date':item['meeting_date']}]}
    result=c.post('/api/v3/register',json=body);assert result.status_code==202,result.text
    mid=result.json()['registered'][0]['id']
    assert c.get('/api/meetings/'+mid).json()['analysis_state']=='queued'
    assert len(queue.jobs)==1
    assert c.post('/api/v3/register',json=body).json()['registered'][0]['duplicate']
    assert len(queue.jobs)==1
    import work.v3.fast_ai
    def notes(rows):
        ref=next(x['id'] for x in rows if '배치도' in x['text'])
        return {'summary':[],'decisions':[],'items':[{'title':'배치도 검토','description':'2026-11-13부터 2026-11-16까지 배치도를 검토한다.','kind':'업무','evidence':[ref]}]},{'seconds':.1,'model':'controlled-test'}
    def changes(_,m,topics):
        ref=next(x['id'] for x in m['lines'] if '납품일' in x['text'])
        return {'items':[{'title':'장비 납품일','category':'납기','before':'','after':'2026-12-18','business_state':'확정','evidence':[ref]}]},.1
    def joint(w,rows,topics,on_phase=None):
        n,metrics=notes(rows);found,_=changes(w,{'lines':rows},topics)
        return n,found,metrics
    monkeypatch.setattr(work.v3.fast_ai,'extract',joint)
    fn,*args=queue.jobs.pop();fn(*args)
    detail=c.get('/api/meetings/'+mid).json();assert detail['analysis_state']=='ready',detail.get('error')
    data=c.get('/api/v3/workspace').json()
    assert len([e for e in data['changes'] if e['meeting_id']==mid])==1
    assert any(e['start']=='2026-11-13' and e['end']=='2026-11-16' for e in data['calendar'])
    assert any(e['start']=='2026-12-18' and e['kind']=='합의 일정' for e in data['calendar'])
    assert c.get('/api/v3/meetings/'+mid+'/download').content==content.encode()
    from work.v17.retrieval import registered_document
    with w.connect() as db:
        doc=registered_document(w.read(db,'meeting',mid))
        assert doc and doc['body']==content and doc['revision']==1
    found=c.get('/api/v3/search',params={'q':'배치도','project_id':pid}).json()
    assert [r['id'] for r in found['items']]==[mid]
    assert '배치도' in found['items'][0]['excerpts'][0]['text']
    assert c.delete('/api/v3/meetings/'+mid).status_code==200
    data=c.get('/api/v3/workspace').json()
    assert not any(e['meeting_id']==mid for e in data['calendar']+data['changes'])
    assert any(m['id']==mid for m in data['archived'])
    assert c.post('/api/v3/meetings/'+mid+'/restore').status_code==200
    assert any(e['meeting_id']==mid for e in c.get('/api/v3/workspace').json()['changes'])
    # Project trash preserves linked records and restricts the operation to the PM.
    version=c.get('/api/projects/'+pid+'/trash-preview').json()['version']
    c.post('/api/demo-login',json={'username':'team2'})
    assert c.post('/api/projects/'+pid+'/trash',json={'version':version}).status_code==403
    c.post('/api/demo-login',json={'username':'team1'})
    assert c.post('/api/projects/'+pid+'/trash',json={'version':version}).status_code==200
    assert not any(r['id']==mid for r in c.get('/api/v3/search',params={'q':'배치도'}).json()['items'])
    assert not any(e['meeting_id']==mid for e in c.get('/api/v3/workspace').json()['calendar'])
    archived=next(p for p in c.get('/api/project-trash').json() if p['id']==pid)
    assert c.post('/api/projects/'+pid+'/restore',json={'version':archived['version']}).status_code==200
    assert any(r['id']==mid for r in c.get('/api/v3/search',params={'q':'배치도'}).json()['items'])
    # Revision change removes obsolete evidence immediately, before new inference.
    detail=c.get('/api/meetings/'+mid).json()
    result=c.patch('/api/v3/meetings/'+mid+'/source',json={'version':detail['version'],'title':detail['title'],'date':detail['date'],'source':content+'\n추가 논의는 다음 회의에서 진행한다.'})
    assert result.status_code==202,result.text
    with w.connect() as db:
        doc=registered_document(w.read(db,'meeting',mid))
        assert doc['revision']==2 and '추가 논의' in doc['body']
    assert not any(e['meeting_id']==mid for e in c.get('/api/v3/workspace').json()['changes'])
    # A deleted queued meeting cannot be resurrected by a stale worker.
    assert c.delete('/api/v3/meetings/'+mid).status_code==200
    fn,*args=queue.jobs.pop();fn(*args)
    assert not any(m['id']==mid for m in c.get('/api/v3/workspace').json()['meetings'])
    # Project membership still applies to the new endpoints.
    c.post('/api/demo-login',json={'username':'team3'})
    assert c.get('/api/v3/meetings/'+mid+'/download').status_code==403
    assert c.get('/api/v3/search',params={'q':'배치도','project_id':pid}).status_code==403

def test_unconfirmed_delivery_does_not_replace_agreement():
    base={'project_id':'p','meeting_id':'m','title':'납품일','category':'납기','evidence':[]}
    events=[dict(base,id='1',business_state='확정',after='2026-12-18',effective_date='2026-11-01'),dict(base,id='2',business_state='보류',after='2026-12-23',effective_date='2026-11-02')]
    result=calendar_events([],events)
    assert [e['start'] for e in result]==['2026-12-18']

def test_notes_preserve_negation_and_conditions():
    from work.v3.fast_ai import grounded_notes
    rows=[{'id':'L001','text':'135 m/min은 요청이다. 승인하지 않았다.'},{'id':'L002','text':'납품일 변경은 보류했다. 반입일은 미정이다.'}]
    notes=grounded_notes([['결정',['L001']],['추가 확인',['L002']]],rows)
    assert notes['decisions'][0]['text']==rows[0]['text']
    assert notes['items'][0]['description']==rows[1]['text']
    with pytest.raises(ValueError):grounded_notes([['결정',['L999']]],rows)

def test_change_condition_uses_original_words():
    from work.v3.service import change_context
    quote='점검 커버: 측면 슬라이드로 변경을 요청했다. 커버 이동 공간과 프레임 간섭을 확인한다.'
    assert change_context([quote],'측면 슬라이드')=='커버 이동 공간과 프레임 간섭을 확인한다.'

def test_document_parsers_and_batch(client,monkeypatch):
    import io
    from docx import Document
    from openpyxl import Workbook
    word=Document();word.add_paragraph('회의명: 연결 검증');word.add_paragraph('프로젝트: 형식 검증 프로젝트');word.add_paragraph('회의일: 2026-11-12');word.add_paragraph('김양일은 도면 확인 결과를 다음 회의에 공유한다.')
    out=io.BytesIO();word.save(out);docx=out.getvalue()
    parsed,suffix=parse_file('회의.docx',docx);assert '도면 확인' in parsed['source'] and suffix=='.docx'
    book=Workbook();book.active.append(['프로젝트','형식 검증 프로젝트']);book.active.append(['회의일','2026-11-12']);book.active.append(['확인할 내용','변경 요청은 보류한다.'])
    out=io.BytesIO();book.save(out);xlsx=out.getvalue()
    parsed,suffix=parse_file('회의.xlsx',xlsx);assert '변경 요청은 보류' in parsed['source'] and parsed['warnings']
    c,queue=client
    p=c.post('/api/projects',json={'name':'형식 검증 프로젝트','members':['team1']}).json()
    result=c.post('/api/v3/imports',files=[('files',('회의.docx',docx)),('files',('회의.xlsx',xlsx))]).json()
    assert not result['errors'] and len(result['items'])==2
    assert all(x['project_id']==p['id'] for x in result['items'])
    # Preview work is controlled here; real original rendering is covered by UI checks.
    monkeypatch.setattr(w,'PREVIEW_POOL',Queue())
    result=c.post('/api/v3/register',json={'items':[{'id':x['id'],'project_id':x['project_id']} for x in result['items']]})
    assert result.status_code==202 and len(result.json()['registered'])==2
    assert len(queue.jobs)==2
