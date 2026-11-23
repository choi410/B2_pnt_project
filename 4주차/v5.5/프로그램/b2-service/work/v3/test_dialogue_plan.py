"""Multi-turn acceptance tests: scope, IDs, counts, presentation and permissions.

Synthetic records only; metadata cases fail if generation is attempted.
"""
import pytest
from work.v3.test_connected import client,w
from work.v3.test_questions_trash import project,meeting
from work.v3.test_conversations import send
from work.v17 import questions


def result(t):return t['messages'][-1]['result']
def mids(t):
    with w.connect() as c:
        m=w.read(c,'ai_message',t['messages'][-1]['id'])
        return {s['meeting_id'] for s in m['job']['result'].get('sources',[])}
def state(t):
    with w.connect() as c:return w.read(c,'ai_message',t['messages'][-1]['id'])['context']


@pytest.fixture
def records(client,monkeypatch):
    c,_=client
    a=project(c,'세척기 교체');b=project(c,'저장탱크 증설');secret=project(c,'배관 이설',members=['team1'])
    records={}
    for key,p,d in [('a6',a,'2026-06-14'),('a71',a,'2026-07-05'),('a72',a,'2026-07-26'),('a8',a,'2026-08-09'),
                    ('b7',b,'2026-07-12'),('b8',b,'2026-08-23'),('secret',secret,'2026-07-19')]:
        m=meeting(c,p,'검사 기간은 3일로 합의했다. 안전 펜스는 유지한다.',d)
        with w.connect() as db:
            m=w.read(db,'meeting',m['id']);m['created_at']=('2026-08-02' if key=='a72' else d)+'T09:00:00+09:00'
            if key=='b8':m['deleted_at']=w.now()
            w.save(db,'meeting',m)
        records[key]=m['id']
    c.post('/api/demo-login',json={'username':'team2'})
    monkeypatch.setattr(questions,'generate',lambda *a,**kw:pytest.fail('Metadata lookup must not call a language model'))
    return c,a,b,secret,records


@pytest.mark.parametrize('opening',['회의록을 월별로 찾아줘','회의록 월별로 정리해줘','회의록을 달별로 묶어줘','회의록 월별 목록 보여주세요'])
def test_month_filter_count_group_chain(records,opening):
    c,a,b,secret,m=records
    t=send(c,opening)
    assert result(t)['group_by']=='month' and result(t)['count']==5
    t=send(c,'여기서 7월 회의록만 모아줘',cid=t['id'])
    assert mids(t)=={m['a71'],m['a72'],m['b7']}
    assert result(t)['mode']=='meeting_lookup'
    t=send(c,'몇 건이야?',cid=t['id']);assert result(t)['count']==3
    t=send(c,'프로젝트별로 다시',cid=t['id'])
    assert result(t)['group_by']=='project' and mids(t)=={m['a71'],m['a72'],m['b7']}
    assert secret['name'] not in str(result(t))


@pytest.mark.parametrize('q',['다른 프로젝트는 7월 회의록이 없어?','다른 데는 7월에 없었어?','나머지 프로젝트도 7월 회의록 보여줘'])
def test_other_and_date_compose(records,q):
    c,a,b,_,m=records
    t=send(c,'세척기 7월 회의록 모아줘');assert mids(t)=={m['a71'],m['a72']}
    t=send(c,q,cid=t['id']);assert mids(t)=={m['b7']}
    t=send(c,'8월은?',cid=t['id']);assert mids(t)==set()
    assert state(t)['project_ids']==[b['id']] and '2026-08' in state(t)['label']
    t=send(c,'전체 프로젝트에서 보여줘',cid=t['id']);assert mids(t)=={m['a8']}


def test_dates_and_exclusion_have_separate_lifetimes(records):
    c,a,b,_,m=records
    t=send(c,'7월 빼고 회의록 보여줘');assert mids(t)=={m['a6'],m['a8']}
    t=send(c,'세척기도 빼고',cid=t['id']);assert not mids(t)
    t=send(c,'제외 다 풀어줘',cid=t['id']);assert result(t)['count']==5
    t=send(c,'7월 회의록',cid=t['id']);assert result(t)['count']==3
    t=send(c,'세척기만',cid=t['id']);assert result(t)['count']==2
    t=send(c,'기간 조건 없이 전부 보여줘',cid=t['id']);assert result(t)['count']==4
    assert state(t)['project_ids']==[a['id']]


def test_registration_basis_switch(records):
    c,_,_,_,m=records
    t=send(c,'8월에 올라온 회의록');assert mids(t)=={m['a72'],m['a8']}
    assert result(t)['lookup_order']=='registered_at'
    t=send(c,'8월에 한 회의는?',cid=t['id']);assert mids(t)=={m['a8']}
    assert result(t)['lookup_order']=='meeting_date'


def test_new_topic_resets_dates_and_old_list_restores(records):
    c,_,_,_,m=records
    t=send(c,'7월 회의록 목록')
    t=send(c,'안전 관련 내용 있어?',cid=t['id'])
    assert result(t)['mode']=='meeting_search' and result(t)['count']==5
    t=send(c,'아까 목록 다시',cid=t['id'])
    assert mids(t)=={m['a71'],m['a72'],m['b7']}


def test_months_keep_years_separate_and_ambiguous_year_clarifies(records):
    c,a,b,_,m=records
    c.post('/api/demo-login',json={'username':'team1'})
    old=meeting(c,b,date='2025-07-20');c.post('/api/demo-login',json={'username':'team2'})
    t=send(c,'회의록 월별로 정리해줘');assert result(t)['count']==6
    assert {'2025-07','2026-07'}<= {x['group_date'][:7] for x in result(t)['meetings']}
    t=send(c,'7월 회의록',cid=t['id']);assert result(t)['kind']=='clarification'
    t=send(c,'2026년 7월',cid=t['id']);assert result(t)['count']==3
    t=send(c,'작년 것은?',cid=t['id']);assert mids(t)=={old['id']}


@pytest.mark.parametrize('q',['두 번째 거 열어줘','그거 말고 마지막 거','지운 것도 포함해서','보안등급 높은 회의록만','제목에 없는거 빼줘'])
def test_unresolved_conditions_never_silently_widen(records,q):
    c,_,_,_,m=records
    t=send(c,'회의록 월별로 보여줘');t=send(c,q,cid=t['id'])
    assert result(t)['kind']=='clarification' and not mids(t)


def test_permissions_deletion_and_count_scope_rechecked(records):
    c,a,b,secret,m=records
    t=send(c,'세척기 7월 회의록 몇건이야?');assert result(t)['count']==2
    t=send(c,'다른 프로젝트는 7월에 없어?',cid=t['id']);assert result(t)['count']==1
    with w.connect() as db:
        item=w.read(db,'meeting',m['b7']);item['deleted_at']=w.now();w.save(db,'meeting',item)
    t=send(c,'목록으로 보여줘',cid=t['id']);assert not mids(t)
    t=send(c,'배관 이설 것도',cid=t['id']);assert result(t)['kind']=='clarification'
    assert secret['name'] not in str(result(t))
    with w.connect() as db:
        p=w.read(db,'project',a['id']);p['members']=['team1'];w.save(db,'project',p)
    t=send(c,'전체 프로젝트 회의록 보여줘',cid=t['id'])
    assert not mids(t) and a['name'] not in str(result(t))


def test_large_results_subset_is_not_only_displayed_page(records):
    c,a,b,_,m=records
    c.post('/api/demo-login',json={'username':'team1'})
    extra={meeting(c,a,text=f'검사 안건 {i}번을 논의했다.',date='2026-07-06')['id'] for i in range(12)}
    c.post('/api/demo-login',json={'username':'team2'})
    t=send(c,'회의록 전부 월별로 보여줘');assert result(t)['count']==17
    t=send(c,'여기서 7월 것만',cid=t['id'])
    assert mids(t)==extra|{m['a71'],m['a72'],m['b7']}
    source=result(t)['sources'][-1]
    r=c.get(f"/api/conversations/{t['id']}/messages/{t['messages'][-1]['id']}/sources/{source['id']}")
    assert r.status_code==200 and r.json()['lines']


def test_reordering_and_limit(records):
    c,_,_,_,m=records
    t=send(c,'회의록 목록');t=send(c,'오래된순 2건만 보여줘',cid=t['id'])
    assert mids(t)=={m['a6'],m['a71']}
    t=send(c,'제한 없이 전부 보여줘',cid=t['id']);assert result(t)['count']==5


@pytest.mark.parametrize('topic',['안전 관련 내용 있어?','기간 관련 내용 있어?'])
def test_content_scope_compound_and_format_transform(records,topic):
    c,a,b,_,m=records
    t=send(c,'세척기 '+topic);assert result(t)['count']==4
    t=send(c,'다른 프로젝트는 7월에 없어?',cid=t['id']);assert mids(t)=={m['b7']}
    t=send(c,'몇 건이야?',cid=t['id']);assert result(t)['count']==1
    t=send(c,'전체 프로젝트에서 월별로 보여줘',cid=t['id'])
    assert mids(t)=={m['a71'],m['a72'],m['b7']} and result(t)['group_by']=='month'


def test_content_filter_survives_count_and_regroup(records):
    c,a,b,_,m=records
    c.post('/api/demo-login',json={'username':'team1'})
    irrelevant=meeting(c,a,'회의실 예약은 담당 부서에 문의한다.','2026-07-20')
    c.post('/api/demo-login',json={'username':'team2'})
    t=send(c,'안전 관련 내용 있어?');assert result(t)['count']==5
    t=send(c,'여기서 7월 것만 모아줘',cid=t['id']);assert result(t)['count']==3
    t=send(c,'몇 건이야?',cid=t['id']);assert result(t)['count']==3
    t=send(c,'프로젝트별로 다시',cid=t['id'])
    assert mids(t)=={m['a71'],m['a72'],m['b7']} and irrelevant['id'] not in mids(t)


@pytest.mark.parametrize('q,expected',[
    ('2026-07-01부터 2026-08-31까지 회의록',['a71','a72','b7','a8']),
    ('2026년 회의록',['a6','a71','a72','b7','a8']),
    ('2026-07-12 기준 회의록',['a6','a71','b7']),
    ('2026년 13월 회의록',None),('2026-08-31부터 2026-07-01까지 회의록',None)])
def test_ranges_and_invalid_dates(records,q,expected):
    c,_,_,_,m=records;t=send(c,q)
    if expected is None:assert result(t)['kind']=='clarification'
    else:assert mids(t)=={m[k] for k in expected}
