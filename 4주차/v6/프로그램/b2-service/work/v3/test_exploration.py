"""Scope/recall regression tests against isolated registered records."""
import pytest
from work.v3.test_connected import client,w
from work.v3.test_questions_trash import project,meeting
from work.v3.test_conversations import send
from work.v3.conversations import resolve_question
from work.v3.topic_overview import intent
from work.v17 import questions


def setup(c):
    a=project(c,'건조로 개조');b=project(c,'믹서 증설');secret=project(c,'권취기 이설',members=['team1'])
    meeting(c,a,'납품일 8/20 합의.\n보증 기간 12개월 합의.\n설치 중 안전 펜스 임시 철거 금지.','2027-04-05')
    meeting(c,a,'고객이 납품일 9/03 연기 요청, 보류.\n시운전 기간 5일 합의.','2027-04-19')
    meeting(c,b,'납품일 7/15 합의.\n검사 기간 3일 합의.','2027-04-08')
    meeting(c,b,'납품일 7/29로 변경 합의.\n운전 교육 담당은 정하지 못함.','2027-05-10')
    meeting(c,secret,'납품일 10/01 합의.','2027-04-12')
    meeting(c,secret,'고객이 계약 금액 증액 요청, 미결정.','2027-05-14')
    c.post('/api/demo-login',json={'username':'team2'})
    return a,b,secret


def last(thread):return thread['messages'][-1]


def result_projects(thread):return {s['project_id'] for s in last(thread)['result'].get('sources',[])}


def context(thread):
    with w.connect() as db:return w.read(db,'ai_message',last(thread)['id'])['context']


@pytest.mark.parametrize('q',['기간 관련 내용 있나?','예전에 우리가 회의했던거 중에 기간에 관련된 내용 있나?',
    '일정에 관련된 내용 보여줘','안전 관련 얘기 있었어?','비용 관련 내용 있어?','담당자 관련 논의 찾아줘'])
def test_broad_question_grammar(q):assert intent(q)


@pytest.mark.parametrize('q',['보증 기간 얼마야?','검사 기간 관련 내용 있어?','계약 금액 바뀐 프로젝트 있어?',
    '안전 비용 알려줘','기한 지난 것은?','기간 3일로 합의했나?','안전 관련 내용은 빼고 보여줘','기간 관련 고객 이메일 찾아줘'])
def test_qualified_questions_do_not_become_categories(q):assert intent(q) is None


def test_category_recall_and_exhausted_projects(client,monkeypatch):
    c,_=client;a,b,secret=setup(c)
    monkeypatch.setattr(questions,'generate',lambda *a,**kw:pytest.fail('Category discovery must not generate claims'))
    first=send(c,'예전에 우리가 회의했던거 중에 기간에 관련된 내용 있나?')
    r=last(first)['result']
    assert r['count']==4 and result_projects(first)=={a['id'],b['id']}
    text='\n'.join(m['snippet'] for m in r['meetings'])
    for expected in ('12개월','5일','3일','보류'):assert expected in text
    assert '10/01' not in text and secret['name'] not in str(r)
    other=send(c,'다른 프로젝트는 없어?',cid=first['id'])
    assert '더 조회할 프로젝트가 없습니다' in last(other)['result']['message']
    assert secret['name'] not in str(other)
    # Every quoted line, including the hold condition, remains inspectable.
    for source in r['sources']:
        proof=c.get('/api/conversations/'+first['id']+'/messages/'+last(first)['id']+'/sources/'+source['id'])
        assert proof.status_code==200
        assert set(proof.json()['highlight'])==set(source.get('line_ids',proof.json()['highlight']))
        assert all(not l['text'].startswith(('회의명:','회의일:','프로젝트:')) for l in proof.json()['lines'] if l['id'] in proof.json()['highlight'])


def test_other_chain_then_explicit_reset(client):
    c,_=client;a,b,_=setup(c)
    first=send(c,'건조로 기간 관련 내용 있어?')
    assert result_projects(first)=={a['id']}
    second=send(c,'다른 프로젝트는 없어?',cid=first['id'])
    assert result_projects(second)=={b['id']}
    third=send(c,'또 다른 프로젝트는?',cid=first['id'])
    assert not result_projects(third)
    reset=send(c,'전체 프로젝트에서 보여줘',cid=first['id'])
    assert result_projects(reset)=={a['id'],b['id']}
    assert not context(reset)['exploration']['excluded_ids']


def test_exclusion_survives_date_filter_and_no_silent_widening(client):
    c,_=client;a,b,_=setup(c)
    first=send(c,'기간 관련 내용 있나?')
    second=send(c,'믹서 말고',cid=first['id'])
    assert result_projects(second)=={a['id']}
    third=send(c,'그중 5월 것만',cid=first['id'])
    assert not result_projects(third)
    state=context(third)
    assert state['project_ids']==[a['id']] and state['time_scope']['start']=='2027-05-01'
    assert b['id'] in state['exploration']['excluded_ids']


def test_new_topic_keeps_pinned_project_but_resets_exclusions(client):
    c,_=client;a,b,_=setup(c)
    first=send(c,'건조로 기간 관련 내용 있어?')
    safety=send(c,'안전 관련 내용 있어?',cid=first['id'])
    assert result_projects(safety)=={a['id']}
    assert context(safety)['project_ids']==[a['id']]
    assert '납품일' not in str(last(safety)['result'])
    all_=send(c,'전부에서는?',cid=first['id'])
    assert set(context(all_)['project_ids'])=={a['id'],b['id']}
    # A new category after exclusion must not silently omit the earlier project.
    other=send(c,'다른 프로젝트는?',cid=first['id'])
    changed=send(c,'기간 관련 내용 있어?',cid=first['id'])
    assert result_projects(changed)=={a['id'],b['id']}


def test_named_followup_inherits_only_user_topic_and_reauthorizes(client):
    c,_=client;a,b,secret=setup(c)
    with w.connect() as db:
        actor=w.read(db,'person','team2')
        old=resolve_question(w,db,actor,'건조로 보증 기간 얼마야?')
        previous={'state':'done','context':old,'question':'건조로 보증 기간 얼마야?',
            'job':{'result':{'kind':'documents','points':[{'text':'999개월 확정'}],'sources':[{'project_id':a['id']}]}}}
        new=resolve_question(w,db,actor,'믹서는?',previous)
        assert new['project_ids']==[b['id']] and '보증' in new['query'] and '999' not in new['query']
        assert secret['id'] not in new['project_ids']
        b['members']=['team1'];w.save(db,'project',b)
        remaining=resolve_question(w,db,actor,'다른 프로젝트는?',previous)
        assert not remaining['project_ids'] and remaining['empty_result']


def test_project_scope_api_cannot_bypass_permissions(client):
    c,_=client;a,b,secret=setup(c)
    r=c.post('/api/questions',json={'question':'기간 관련 내용','project_ids':[secret['id']]})
    assert r.status_code==403
    assert c.post('/api/questions',json={'question':'기간 관련 내용','project_ids':[]}).status_code==422
    assert c.post('/api/questions',json={'question':'기간 관련 내용','project_ids':[a['id']],
        'record_scope':{'mode':'period','start':'2027-05-01','end':'2027-04-01'}}).status_code==422


def test_period_replacement_and_explicit_scope_reset(client,monkeypatch):
    from datetime import datetime,timezone
    import work.v3.query_intent as qi
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return cls(2027,5,20,tzinfo=timezone.utc)
    monkeypatch.setattr(qi,'datetime',Clock)
    c,_=client;a,b,_=setup(c)
    first=send(c,'지난달 회의에서 기간 얘기 있었어?')
    assert last(first)['result']['count']==3
    second=send(c,'이번 달은?',cid=first['id'])
    assert result_projects(second)=={b['id']} and last(second)['result']['count']==1
    assert context(second)['time_scope']['start']=='2027-05-01'
    third=send(c,'기간 조건 없이 전부 보여줘',cid=first['id'])
    assert last(third)['result']['count']==4


@pytest.mark.parametrize('reference',['이 프로젝트만 보여줘','그 프로젝트만 보여줘'])
def test_ambiguous_reference_and_missing_context(client,reference):
    c,_=client;a,b,_=setup(c)
    assert last(send(c,'다른 프로젝트는 없어?'))['result']['kind']=='clarification'
    first=send(c,'기간 관련 내용 있어?')
    ambiguous=send(c,reference,cid=first['id'])
    assert last(ambiguous)['result']['kind']=='clarification'
    assert len(last(ambiguous)['result']['projects'])==2
    selected=send(c,'믹서',cid=first['id'])
    assert result_projects(selected)=={b['id']}


def test_more_than_generation_cap_and_revision_cleanup(client):
    c,_=client
    ps=[project(c,'탐색검증 '+str(i)) for i in range(9)]
    meetings=[meeting(c,p,'납품 일정은 2027-08-12로 합의했다.','2027-06-01') for p in ps]
    first=send(c,'일정 관련 내용 보여줘')
    assert last(first)['result']['count']==9 and len(result_projects(first))==9
    with w.connect() as db:
        m=w.read(db,'meeting',meetings[0]['id']);m['deleted_at']=w.now();w.save(db,'meeting',m)
    again=send(c,'전체 프로젝트에서 보여줘',cid=first['id'])
    assert last(again)['result']['count']==8


def test_new_review_status_and_ordinal_counterexamples(client,monkeypatch):
    c,_=client;a,b,secret=setup(c)
    monkeypatch.setattr(questions,'generate',lambda *a,**kw:pytest.fail('Recorded expression search must not generate'))
    first=send(c,'돈 얘기 나온 적 있어?')
    assert last(first)['result']['category']=='cost' and not result_projects(first)
    unsettled=send(c,'그럼 일정 중에 아직 안 정해진 건?',cid=first['id'])
    result=last(unsettled)['result']
    assert result_projects(unsettled)=={a['id']} and result['count']==1
    assert '보류' in result['meetings'][0]['snippet'] and '담당' not in result['meetings'][0]['snippet']
    assert '현재 확정·미해결 상태를 뜻하지 않습니다' in result['notice']
    dates=send(c,'4월에 정한 날짜들 보여줘')
    assert last(dates)['result']['count']==2
    snippets=' '.join(m['snippet'] for m in last(dates)['result']['meetings'])
    assert '8/20' in snippets and '7/15' in snippets and '9/03' not in snippets and '12개월' not in snippets
    opened=send(c,'첫 번째 거 전체 내용 볼래',cid=dates['id'])
    assert last(opened)['result']['count']==1 and result_projects(opened)=={a['id']}
    proof=c.get('/api/conversations/'+opened['id']+'/messages/'+last(opened)['id']+'/sources/S1').json()
    assert any('안전 펜스' in line['text'] for line in proof['lines']) and not proof['highlight']


@pytest.mark.parametrize('q',['보증 기간 중 미정인 내용','안전 비용 중 합의된 내용','납품일 9월로 합의한 거야?'])
def test_status_filter_does_not_erase_specific_attributes(q):
    from work.v3.topic_overview import query
    assert query(q) is None


def test_status_expression_is_not_current_state(client):
    c,_=client;p=project(c)
    meeting(c,p,'납품일 2027-08-01 변경은 확정하지 않았다.','2027-04-02')
    meeting(c,p,'납품일 2027-08-01 변경은 보류 중이다.','2027-04-03')
    meeting(c,p,'납품일 2027-08-01로 합의했다.','2027-04-04')
    result=last(send(c,'4월에 정한 날짜 보여줘'))['result']
    assert result['count']==1 and result['meetings'][0]['date']=='2027-04-04'
    result=last(send(c,'아직 안 정해진 일정 보여줘'))['result']
    assert result['count']==1 and '현재 확정·미해결 상태를 뜻하지 않습니다' in result['notice']


def test_all_projects_does_not_clear_period(client):
    c,_=client;a,b,_=setup(c)
    first=send(c,'건조로 4월 회의에서 기간 관련 내용 보여줘')
    expanded=send(c,'전체 프로젝트에서 보여줘',cid=first['id'])
    assert last(expanded)['result']['count']==3 and context(expanded)['time_scope']['end']=='2027-04-30'


def test_ordinal_is_ambiguous_after_paginated_results(client):
    c,_=client;p=project(c)
    for day in range(1,7):meeting(c,p,'납품일 2027-08-01로 합의했다.',f'2027-04-{day:02d}')
    first=send(c,'기간 관련 내용 있어?')
    choice=send(c,'첫 번째 거 전체 내용 볼래',cid=first['id'])
    r=last(choice)['result'];assert r['kind']=='clarification' and len(r['meetings'])==6
    mid=r['meetings'][1]['id']
    selected=c.post('/api/conversations/questions',json={'question':'첫 번째 거 전체 내용 볼래','conversation_id':first['id'],'meeting_id':mid}).json()
    source=last(selected)['result']['sources'][0]
    with w.connect() as db:
        m=w.read(db,'ai_message',last(selected)['id'])
        assert m['job']['result']['sources'][0]['meeting_id']==mid
