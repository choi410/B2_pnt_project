"""Category changes use isolated storage and preserve evidence/approval semantics."""
from copy import deepcopy
import pytest
from work.v3.test_history_edit import client, setup_change, body
from work.v3.test_questions_trash import meeting, project
from work.v3.test_connected import w
from work.v17.changes import normalize_extraction, make_proposals


def request(c, e, category, records=None, create=False):
    return c.patch('/api/v3/changes/'+e['id']+'/category', json={
        'category': category, 'create': create,
        'records': [{'id':x['id'], 'version':x['version']} for x in (records or [e])]})


@pytest.mark.parametrize('reverse',[False,True])
def test_delivery_date_ties_use_source_meeting_order(reverse):
    from work.v3.service import calendar_events
    meetings=[{'id':'older','project_id':'p','title':'기준 협의','date':'2026-11-09'},
              {'id':'newer','project_id':'p','title':'최종 협의','date':'2026-11-20'}]
    common={'project_id':'p','title':'납품일','topic_id':'delivery','category':'설치 일정',
            'extracted_category':'납기','business_state':'확정','evidence':[],
            'effective_date':'2026-11-09','created_at':'2026-11-23T09:00:00+09:00'}
    events=[{**common,'id':'z-older','meeting_id':'older','after':'2026-12-18'},
            {**common,'id':'a-newer','meeting_id':'newer','after':'2026-12-23'}]
    if reverse:events.reverse()
    result=[e for e in calendar_events(meetings,events) if e['kind']=='합의 일정']
    assert len(result)==1 and result[0]['id']=='change:a-newer'
    assert result[0]['start']=='2026-12-23'


def test_whole_subject_relabels_without_changing_source_or_review(client):
    c,_=client;p,m,e,_=setup_change(c)
    m2=meeting(c,p,'장비 납품일은 2026-12-23으로 합의했다.','2026-11-20')
    e2={**deepcopy(e),'id':w.uid(),'meeting_id':m2['id'],'evidence':[m2['lines'][-1]['id']]}
    for item in (e,e2):
        item.update(review_state='확인됨',confirmed_by='team1',confirmed_at='2026-11-19',
                    customer_agreed_at='2026-11-19',business_state='확정')
    with w.connect() as db:
        for item in (e,e2):w.save(db,'change_event',item)
    r=request(c,e,'설치 일정',[e,e2],True)
    assert r.status_code==200,r.text
    with w.connect() as db:
        for original in (e,e2):
            actual=w.read(db,'change_event',original['id'])
            assert actual['category']=='설치 일정' and actual['version']==original['version']+1
            for key in ('topic_id','title','before','after','business_state','review_state','confirmed_by',
                        'confirmed_at','customer_agreed_at','evidence','quotes','source_revision'):
                assert actual.get(key)==original.get(key),key
            assert actual['edit_history'][-1]['record']['category']=='납기'
            assert actual['human_edited']
        assert w.read(db,'meeting',m['id'])['source']==m['source']
        assert w.read(db,'project',p['id'])['change_categories']==['설치 일정']
    workspace=c.get('/api/v3/workspace').json()
    assert any(x['id']=='change:'+e2['id'] for x in workspace['calendar'])
    edited=next(x for x in workspace['changes'] if x['id']==e['id'])
    # Content editing remains available after assigning a custom category.
    assert c.patch('/api/v3/changes/'+e['id'],json=body(edited,after='2026-12-24')).status_code==200


def test_permissions_versions_and_missing_group_members_are_atomic(client):
    c,_=client;p,m,e,_=setup_change(c)
    c.post('/api/demo-login',json={'username':'team2'})
    assert request(c,e,'품질',create=True).status_code==403
    c.post('/api/demo-login',json={'username':'team1'})
    assert request(c,{**e,'version':99},'품질',create=True).status_code==409
    other={**deepcopy(e),'id':w.uid()}
    with w.connect() as db:w.save(db,'change_event',other)
    assert request(c,e,'품질',create=True).status_code==409
    with w.connect() as db:
        assert w.read(db,'change_event',e['id'])['category']=='납기'
        assert '품질' not in w.read(db,'project',p['id']).get('change_categories',[])


@pytest.mark.parametrize('name',[' ', '전체', '전체 구분', '가'*21])
def test_invalid_names_do_not_create_categories(client,name):
    c,_=client;p,m,e,_=setup_change(c)
    assert request(c,e,name,create=True).status_code==422


def test_aliases_duplicates_and_project_scoping(client):
    c,_=client;p,m,e,_=setup_change(c)
    assert request(c,e,'없는 구분').status_code==422
    assert request(c,e,'비용',create=True).status_code==200
    with w.connect() as db:e=w.read(db,'change_event',e['id'])
    assert request(c,e,'비 용',create=True).status_code==200
    with w.connect() as db:
        e=w.read(db,'change_event',e['id'])
        assert w.read(db,'project',p['id'])['change_categories']==['비용']
    assert request(c,e,'일정·납기').status_code==200
    other=project(c,'별도 프로젝트 '+w.uid()[:5])
    with w.connect() as db:assert '비용' not in w.read(db,'project',other['id']).get('change_categories',[])


def test_collision_does_not_merge_histories(client):
    c,_=client;p,m,e,_=setup_change(c)
    other={**deepcopy(e),'id':w.uid(),'category':'사양'}
    with w.connect() as db:w.save(db,'change_event',other)
    assert request(c,e,'사양').status_code==409
    with w.connect() as db:assert w.read(db,'change_event',e['id'])['version']==e['version']


@pytest.mark.parametrize('condition',['running','stale','deleted','superseded'])
def test_changing_source_or_unavailable_records_cannot_be_reclassified(client,condition):
    c,_=client;p,m,e,_=setup_change(c)
    with w.connect() as db:
        if condition=='running':m['analysis_state']='running'
        elif condition=='stale':m['analysis_stale']=True
        elif condition=='deleted':m['deleted_at']=w.now()
        else:e['superseded_by_revision']=1;w.save(db,'change_event',e)
        w.save(db,'meeting',m)
    assert request(c,e,'비용',create=True).status_code==409


def test_unknown_model_categories_keep_grounded_records():
    m={'lines':[{'id':'L1','text':'고객과 추가 운송비를 각각 50%씩 부담하기로 합의했다.'}]}
    raw={'title':'운송비 부담','category':'모델이 만든 새 구분','before':'','after':'각 50% 부담',
         'business_state':'확정','evidence':['L1'],'topic_id':None}
    normalized=normalize_extraction(m,[raw],[])
    assert normalized[0]['category']=='미분류' and normalized[0]['after']=='각 50% 부담'
    assert normalized[0]['business_state']=='확정' and normalized[0]['evidence']==['L1']
    with pytest.raises(ValueError):normalize_extraction(m,[{**raw,'evidence':['없는 근거']}],[])
    m.update(id='meeting',project_id='project',revision=1,date='2026-11-19')
    assert make_proposals(w,m,[raw])[0]['category']=='미분류'


def test_existing_custom_category_and_topic_survive_extraction():
    m={'lines':[{'id':'L1','text':'운송비 부담은 고객과 각각 50%씩 부담하는 것으로 합의했다.'}]}
    topics=[{'id':'cost','title':'운송비 부담','category':'비용'}]
    raw={'title':'운송비 부담','category':'요구사항','before':'','after':'각 50% 부담',
         'business_state':'확정','evidence':['L1'],'topic_id':'cost'}
    item=normalize_extraction(m,[raw],topics)[0]
    assert item['category']=='비용' and item['topic_id']=='cost'


def test_other_topic_is_not_discarded_by_scope_check(client,monkeypatch):
    c,_=client;p,m,e,_=setup_change(c)
    from work.v3 import service
    monkeypatch.setattr(service,'retitle',lambda e,known:None)
    monkeypatch.setattr(service,'item_kind',lambda e:'기타')
    proposed=[{**e,'category':'미분류','business_state':'요청','requested_by':''}]
    result=service.screen_proposals(w,m,proposed)
    assert len(proposed)==1 and result['screened_out']==0


def test_reanalysis_keeps_reclassification(client,monkeypatch):
    c,_=client;p,m,e,proposal=setup_change(c)
    assert request(c,e,'미분류').status_code==200
    from work.v3 import fast_ai,service
    monkeypatch.setattr(service,'item_kind',lambda e:None)
    monkeypatch.setattr(service,'retitle',lambda e,known:None)
    monkeypatch.setattr(fast_ai,'extract',lambda *a,**k:(
        {'summary':[],'decisions':[],'items':[]},{'items':[proposal]},{'model':'controlled-test'}))
    with w.connect() as db:
        m=w.read(db,'meeting',m['id']);m.update(v3_job='categories-test',analysis_state='queued');w.save(db,'meeting',m)
    service.run_analysis(w,m['id'],'categories-test')
    events=[x for x in c.get('/api/v3/workspace').json()['changes'] if x['meeting_id']==m['id']]
    assert len(events)==1 and events[0]['id']==e['id'] and events[0]['category']=='미분류'
