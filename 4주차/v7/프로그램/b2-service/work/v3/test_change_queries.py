"""Ranking-to-detail dialogue, shared counts, evidence and access boundaries."""
import pytest
from work.v3.test_connected import client,w
from work.v3.test_questions_trash import project,meeting,event
from work.v3.test_project_catalog import no_generation,send
from work.v3 import chat_interpreter,change_queries


def seed(c):
    a=project(c,'한빛셀 롤프레스');b=project(c,'서린 코팅라인')
    m=meeting(c,a,'속도 120 m/min으로 합의했다.','2026-11-09')
    n=meeting(c,a,'속도 135 m/min 변경 요청은 보류했다.','2026-11-13')
    event(m,'speed','확정','120 m/min');event(n,'speed','요청','135 m/min');event(n,'speed','보류','135 m/min')
    event(meeting(c,b),'width','확정','650 mm')
    return a,b


@pytest.mark.parametrize('question',[
    '그 변경 기록이 어떻게돼?', '그 변경이력 보여줘', '그건 어떤 내용이야?',
    '자세히 알려줘', '뭐가 바뀐 거야?', '변경 내역을 날짜순으로 정리해줘',
])
def test_rank_drilldown_returns_records_not_all_projects(client,question):
    c,_=client;a,b=seed(c)
    t,rank=send(c,'변경이력이 가장 많은 프로젝트는?')
    t,r=send(c,question,t['id'])
    assert r['mode']=='change_history' and r['count']==rank['count']==3
    assert r['result_project_ids']==[a['id']]
    assert {e['state'] for e in r['change_items']}=={'합의','요청','보류'}
    assert [e['date'] for e in r['change_items']]==['2026-11-09','2026-11-13','2026-11-13']
    assert b['name'] not in str(r)
    mid=t['messages'][-1]['id'];sid=r['change_items'][0]['source_id']
    proof=c.get(f'/api/conversations/{t["id"]}/messages/{mid}/sources/{sid}')
    assert proof.status_code==200,proof.text
    assert proof.json()['highlight'] and '120 m/min' in str(proof.json()['lines'])


def test_confirmed_delivery_change_distinguishes_requests_and_respects_access(client):
    c,_=client
    changed=project(c,'솔빛 가열기')
    pending=project(c,'샘물 세척기')
    same=project(c,'두레 믹서')
    hidden=project(c,'비공개 포장기',members=['team1'])
    for p,text in [
        (changed,'납기는 2026년 11월 12일에서 2026년 11월 30일로 조정하기로 결정했다.'),
        (pending,'납품일은 2026년 11월 12일에서 2026년 11월 30일로 변경하자는 요청을 보류했다.'),
        (same,'납기는 2026년 11월 12일에서 2026년 11월 12일로 변경하기로 합의했다.'),
        (hidden,'납품일은 2026년 11월 12일에서 2026년 12월 3일로 변경하기로 합의했다.'),
    ]:
        meeting(c,p,text,'2026-09-20')
    c.post('/api/demo-login',json={'username':'team2'}).raise_for_status()
    t,r=send(c,'모든 프로젝트에서 납기가 조정된 프로젝트만 보여줘')
    assert r['mode']=='confirmed_delivery_projects' and r['count']==1
    assert r['result_project_ids']==[changed['id']]
    assert '11월 30일' in r['points'][0]['text']
    mid=t['messages'][-1]['id'];sid=r['sources'][0]['id']
    proof=c.get(f'/api/conversations/{t["id"]}/messages/{mid}/sources/{sid}')
    assert proof.status_code==200 and proof.json()['highlight']


def test_detail_count_uses_same_active_records_as_rank(client):
    c,_=client;a,b=seed(c);m=meeting(c,a,'기타 합의 기록','2026-11-17')
    for patch in ({'deleted_at':w.now()},{'review_state':'제외'},{'superseded_by_revision':2},{'source_revision':99}):
        e=event(m,'ignore','요청','999');e.update(patch)
        with w.connect() as db:w.save(db,'change_event',e)
    for patch in ({'deleted_at':w.now()},{'analysis_stale':True}):
        ignored=meeting(c,a,'과거 기록 '+w.uid());event(ignored,'ignore','확정','999');ignored.update(patch)
        with w.connect() as db:w.save(db,'meeting',ignored)
    # A record with an unresolved evidence link still belongs to the same
    # ledger count, but must not invent a working source.
    e=event(m,'missing','요청','근거 미연결');e['evidence']=[]
    with w.connect() as db:w.save(db,'change_event',e)
    t,rank=send(c,'변경이력이 가장 많은 프로젝트는?')
    _,r=send(c,'그 변경 기록이 어떻게돼?',t['id'])
    assert r['count']==rank['count']==4 and all(x['after']!='999' for x in r['change_items'])
    assert next(x for x in r['change_items'] if x['id']==e['id'])['source_id'] is None


def test_status_and_date_followups_keep_history_scope(client):
    c,_=client;a,b=seed(c)
    t,_=send(c,'한빛셀 변경이력 보여줘')
    t,r=send(c,'그중 보류된 것만',t['id'])
    assert r['count']==1 and r['change_items'][0]['state']=='보류'
    _,r=send(c,'11월 13일 기록만',t['id'])
    assert r['count']==1 and r['result_project_ids']==[a['id']]


def test_tie_clarifies_and_project_selection_keeps_detail_operation(client):
    c,_=client;a=project(c,'동률 설비 A');b=project(c,'동률 설비 B')
    event(meeting(c,a),'x','요청','1');event(meeting(c,b),'y','요청','2')
    t,_=send(c,'변경이력이 가장 많은 프로젝트는?')
    t,r=send(c,'그 변경 기록 보여줘',t['id'])
    assert r['kind']=='clarification' and r['mode']=='change_project_choice'
    assert {p['id'] for p in r['projects']}=={a['id'],b['id']}
    t=c.post('/api/conversations/questions',json={'conversation_id':t['id'],'question':'그 변경 기록 보여줘','project_id':b['id']}).json()
    r=t['messages'][-1]['result']
    assert r['mode']=='change_history' and r['result_project_ids']==[b['id']]


def test_change_history_uses_named_previous_project_and_exposes_topic_identity(client):
    c,_=client;a,b=seed(c)
    with w.connect() as db:
        rows=[e for e in w.all_records(db,'change_event') if e['project_id']==a['id']]
        for index,e in enumerate(rows):
            e['topic_id']='speed-verified'
            e['title']='조정 전 속도' if index==0 else '압연 속도'
            w.save(db,'change_event',e)
    _,chooser=send(c,'변경이력 뭐야?')
    assert chooser['mode']=='change_project_choice' and {p['id'] for p in chooser['projects']}=={a['id'],b['id']}
    thread,_=send(c,'한빛셀 회의록 목록 보여줘')
    _,history=send(c,'변경이력 뭐야?',thread['id'])
    assert history['mode']=='change_history' and history['result_project_ids']==[a['id']]
    assert history['direction']=='oldest'
    assert {e['topic_id'] for e in history['change_items']}=={'speed-verified'}
    assert {e['title'] for e in history['change_items']}=={'압연 속도','조정 전 속도'}


def test_explicit_new_project_inventory_is_not_captured_by_history(client):
    c,_=client;a,b=seed(c)
    t,_=send(c,'변경이력이 가장 많은 프로젝트는?')
    t,_=send(c,'자세히 보여줘',t['id'])
    _,r=send(c,'전체 프로젝트 목록 보여줘',t['id'])
    assert r['mode']=='project_list' and r['count']==2


def test_bad_model_cannot_replace_change_reference_with_inventory(client):
    c,_=client;a,b=seed(c);t,_=send(c,'변경이력이 가장 많은 프로젝트는?')
    with w.connect() as db:
        prior=w.read(db,'ai_message',t['messages'][-1]['id']);actor=w.read(db,'person','team1')
        _,r=chat_interpreter.execute(w,db,actor,'그 변경 기록이 어떻게돼?',
            chat_interpreter.Plan(action='projects',scope='previous').model_dump(),prior)
    assert r['mode']=='change_history' and r['result_project_ids']==[a['id']]


def test_reference_does_not_widen_after_project_access_removed(client):
    c,_=client;a,b=seed(c);c.post('/api/demo-login',json={'username':'team2'})
    t,_=send(c,'변경이력이 가장 많은 프로젝트는?')
    with w.connect() as db:
        prior=w.read(db,'ai_message',t['messages'][-1]['id']);actor=w.read(db,'person','team2')
        a['members']=['team1'];w.save(db,'project',a)
        context=change_queries.resolve(w,db,actor,'그 변경 기록 보여줘',prior)
    assert context.get('clarify') and not context['project_ids']


def test_specific_attribute_history_keeps_source_query_path(client):
    c,_=client;a,b=seed(c)
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        assert change_queries.resolve(w,db,actor,'한빛셀 압연 속도 변경 이력 알려줘') is None


def test_ledger_subset_keeps_project_and_exact_subject(client):
    from work.v3.test_question_scope import change
    c,_=client;a,b=seed(c)
    with w.connect() as db:
        for e in w.all_records(db,'change_event'):
            e['title']='압연 속도' if e['project_id']==a['id'] else '코팅 폭'
            w.save(db,'change_event',e)
    m=meeting(c,a,'장비 납품일은 2027-04-12로 합의했다.','2026-11-17')
    change(m,'장비 납품일','2027-04-12')
    change(m,'부품 도착일','2027-04-01')
    t,_=send(c,'한빛셀 변경이력 보여줘')
    t,r=send(c,'그중 납기 관련된 것만',t['id'])
    assert r['mode']=='change_history' and r['count']==1
    assert r['result_project_ids']==[a['id']]
    assert r['change_items'][0]['title']=='장비 납품일'
    _,r=send(c,'그중 합의된 것만',t['id'])
    assert r['count']==1 and r['change_items'][0]['title']=='장비 납품일'


@pytest.mark.parametrize('question',['위험한 변경기록만 보여줘','변경 기록 삭제해줘','11월 31일 변경 기록 보여줘'])
def test_unsupported_conditions_never_become_unfiltered_history(client,question):
    c,_=client;seed(c);t,_=send(c,'변경이력이 가장 많은 프로젝트는?')
    _,r=send(c,question,t['id'])
    assert r['kind']=='clarification' and not r.get('change_items')
