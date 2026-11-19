"""Change editing uses the disposable service fixture, never the live demo DB."""
from work.v3.test_connected import w,app,Queue
from fastapi.testclient import TestClient
from work.v3.test_questions_trash import project,meeting
from work.v17.changes import make_proposals
from work.v3.service import run_analysis
import pytest


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(w,'DATA_DIR',tmp_path)
    monkeypatch.setattr(w,'DB',tmp_path/'workspace.sqlite3')
    monkeypatch.setattr(w,'FILES',tmp_path/'files')
    queue=Queue();monkeypatch.setattr(w,'POOL',queue)
    with TestClient(app,headers={'X-B2-Request':'workspace'}) as c:
        assert c.post('/api/demo-login',json={'username':'team1'}).status_code==200
        yield c,queue


def setup_change(c):
    p=project(c,'기록 수정 검증 '+w.uid()[:8])
    m=meeting(c,p,'납품일은 2026-12-18로 합의했다.\n2026-12-23으로 변경해 달라는 요청은 보류했다.')
    proposal={'title':'장비 납품일','category':'납기','before':'','after':'2026-12-23','business_state':'확정','evidence':[m['lines'][-1]['id']]}
    e=make_proposals(w,m,[proposal],[])[0]
    # Real v3 topics can be synthetic IDs without a legacy change_topic row.
    e['topic_id']='auto-history-edit'
    with w.connect() as db:w.save(db,'change_event',e)
    return p,m,e,proposal


def body(e,**changes):
    return {**{k:e[k] for k in ('version','source_revision','title','business_state','before','after','evidence')},**changes}


def test_correct_record_updates_projection_and_keeps_original(client):
    c,_=client;p,m,e,_=setup_change(c)
    before=c.get('/api/v3/workspace').json()
    assert any(x['id']=='change:'+e['id'] for x in before['calendar'])
    r=c.patch('/api/v3/changes/'+e['id'],json=body(e,title='납품 일정',business_state='보류',after='12월 23일 변경 요청 보류 · 기존 12월 18일 유지'))
    assert r.status_code==200,r.text
    edited=r.json()
    assert edited['version']==2 and edited['human_edited']
    assert edited['updated_by']=='team1'
    assert edited['edit_history'][0]['record']['after']=='2026-12-23'
    assert edited['edit_history'][0]['record']['business_state']=='확정'
    assert edited['meeting_id']==m['id'] and edited['topic_id'] is None
    after=c.get('/api/v3/workspace').json()
    record=next(x for x in after['changes'] if x['id']==e['id'])
    assert record['title']=='납품 일정' and record['business_state']=='보류'
    assert not any(x['id']=='change:'+e['id'] for x in after['calendar'])
    source=c.get('/api/meetings/'+m['id']).json()
    assert source['source']==m['source'] and source['revision']==m['revision']
    # Another tab's stale save cannot overwrite the correction.
    assert c.patch('/api/v3/changes/'+e['id'],json=body(e)).status_code==409


def test_edit_permissions_and_source_validation(client):
    c,_=client;p,m,e,_=setup_change(c)
    c.post('/api/demo-login',json={'username':'team2'})
    assert c.patch('/api/v3/changes/'+e['id'],json=body(e)).status_code==403
    c.post('/api/demo-login',json={'username':'team1'})
    for patch in ({'evidence':['missing']},{'evidence':[]},{'business_state':'완료'},{'title':'  '},{'after':'  '},{'meeting_id':'another'}):
        assert c.patch('/api/v3/changes/'+e['id'],json=body(e,**patch)).status_code==422
    assert c.patch('/api/v3/changes/'+e['id'],json=body(e,source_revision=0)).status_code==409
    # Switching evidence is allowed, but only to lines from this source.
    replacement=[m['lines'][-2]['id']]
    r=c.patch('/api/v3/changes/'+e['id'],json=body(e,evidence=replacement,after='2026-12-18'))
    assert r.status_code==200,r.text
    assert r.json()['quotes']==[m['lines'][-2]['text']]
    assert r.json()['topic_id']=='auto-history-edit'


@pytest.mark.parametrize('condition',['running','stale','deleted','superseded'])
def test_unavailable_records_cannot_be_edited(client,condition):
    c,_=client;p,m,e,_=setup_change(c)
    with w.connect() as db:
        if condition=='running':m['analysis_state']='running'
        elif condition=='stale':m['analysis_stale']=True
        elif condition=='deleted':m['deleted_at']=w.now()
        else:e['superseded_by_revision']=1;w.save(db,'change_event',e)
        w.save(db,'meeting',m)
    assert c.patch('/api/v3/changes/'+e['id'],json=body(e)).status_code in (409,410)
    with w.connect() as db:assert w.read(db,'change_event',e['id'])['version']==1


def test_reanalysis_keeps_edit_without_reintroducing_machine_record(client,monkeypatch):
    c,_=client;p,m,e,proposal=setup_change(c)
    r=c.patch('/api/v3/changes/'+e['id'],json=body(e,title='납품 일정',business_state='보류',after='납품일 변경 보류'))
    assert r.status_code==200,r.text
    import work.v3.fast_ai
    def extract(w,rows,topics,on_phase=None):
        return {'summary':[],'decisions':[],'items':[]},{'items':[proposal]},{'model':'controlled-test'}
    monkeypatch.setattr(work.v3.fast_ai,'extract',extract)
    with w.connect() as db:
        m=w.read(db,'meeting',m['id']);m.update(v3_job='edit-reanalysis',analysis_state='queued');w.save(db,'meeting',m)
    run_analysis(w,m['id'],'edit-reanalysis')
    actual=c.get('/api/meetings/'+m['id']).json()
    assert actual['analysis_state']=='ready',actual.get('error')
    changes=[x for x in c.get('/api/v3/workspace').json()['changes'] if x['meeting_id']==m['id']]
    assert len(changes)==1 and changes[0]['id']==e['id'] and changes[0]['business_state']=='보류'
