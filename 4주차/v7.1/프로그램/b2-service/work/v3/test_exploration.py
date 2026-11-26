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


def test_other_project_with_explicit_topic_preserves_exclusion(client):
    from work.v3 import conversation_followups
    c,_=client;a,b,secret=setup(c)
    previous={'state':'done','context':{'query':'납품일 관련 내용','project_ids':[a['id']],
        'subject':'납품일','time_scope':{'mode':'current','start':None,'end':None}},
        'job':{'result':{'kind':'documents','sources':[{'project_id':a['id'],'meeting_id':'old'}]}}}
    with w.connect() as db:
        actor=w.read(db,'person','team2')
        context=conversation_followups.resolve(w,db,actor,'다른 프로젝트도 납품일 얘기한 게 있어?',previous)
    assert context['project_ids']==[b['id']]
    assert context['exploration']['excluded_ids']==[a['id']]
    assert context['query']=='납품일 얘기한 게 있어?'


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


@pytest.mark.parametrize('first_has_answer',[True,False])
def test_content_other_projects_preserves_topic_cutoff_and_empty_scope(client,monkeypatch,first_has_answer):
    from work.v17 import retrieval
    from work.v3 import chat_interpreter
    c,_=client
    a=project(c,'북산 광학검사기');b=project(c,'남해 광학검사기')
    hidden=project(c,'비공개 광학검사기',members=['team1'])
    meeting(c,a,'검사 주기는 0.8초이다.' if first_has_answer else '전원 전압은 220 V이다.','2026-10-05')
    old_b=meeting(c,b,'검사 주기는 1.2초이다.','2026-10-06')
    meeting(c,b,'검사 주기는 1.0초로 변경했다.','2026-10-12')
    meeting(c,hidden,'검사 주기는 9.9초이다.','2026-10-06')
    c.post('/api/demo-login',json={'username':'team2'})
    class Inline:
        def submit(self,fn,*args):fn(*args)
    monkeypatch.setattr(questions,'POOL',Inline());monkeypatch.setattr(questions,'JOBS',{})
    monkeypatch.setattr(retrieval,'embed',lambda texts,prefix:[[1.,0.] for _ in texts])
    interpretation_calls=[]
    def unexpected_interpretation(*args):
        interpretation_calls.append(args)
        return chat_interpreter.Plan(action='clarify',unresolved='unexpected').model_dump()
    monkeypatch.setattr(chat_interpreter,'infer',unexpected_interpretation)
    def generate(_w,q,sources,**kw):
        ids={s['project_id'] for s in sources}
        assert len(ids)==1 and hidden['id'] not in ids
        assert all(s['date']<='2026-10-08' for s in sources)
        assert '검사 주기' in q
        if ids=={a['id']} and not first_has_answer:return {'answerable':False,'points':[]}
        value='0.8초' if ids=={a['id']} else '1.2초'
        return {'answerable':True,'points':[{'text':'검사 주기는 '+value+'이다.','sources':[sources[0]['id']]}]}
    monkeypatch.setattr(questions,'generate',generate)
    first=send(c,'10월 8일 기준 검사 주기는 얼마였어?',a['id'])
    assert last(first)['state']=='done' and last(first)['result']['answerable']==first_has_answer
    second=send(c,'다른 프로젝트는?',cid=first['id'])
    assert not interpretation_calls
    assert result_projects(second)=={b['id']}
    with w.connect() as db:
        stored=w.read(db,'ai_message',last(second)['id'])
    assert {s['meeting_id'] for s in stored['job']['result']['sources']}=={old_b['id']}
    assert context(second)['time_scope']=={'mode':'as_of','start':None,'end':'2026-10-08'}
    third=send(c,'또 다른 프로젝트는?',cid=first['id'])
    assert context(third)['project_ids']==[] and context(third)['empty_result']
    assert last(third)['result']['answerable'] is False
    selected=send(c,a['name']+'는?',cid=first['id'])
    assert context(selected)['project_ids']==[a['id']]
    assert context(selected)['time_scope']['end']=='2026-10-08'
    assert not context(selected)['exploration']['excluded_ids']
    assert last(selected)['result']['answerable']==first_has_answer


def test_empty_result_does_not_exclude_projects_omitted_from_the_answer(client):
    c,_=client;a,b,_=setup(c)
    with w.connect() as db:
        actor=w.read(db,'person','team2')
        old=resolve_question(w,db,actor,'기간 관련 내용 있어?')
        previous={'state':'done','question':'기간 관련 내용 있어?','context':old,
                  'job':{'result':{'kind':'documents','answerable':False,'sources':[],
                                  'omitted_projects':[{'id':b['id'],'name':b['name']}]}}}
        remaining=resolve_question(w,db,actor,'다른 프로젝트는?',previous)
    assert remaining['project_ids']==[b['id']]


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


def test_ambiguous_reference_and_missing_context(client):
    c,_=client;a,b,_=setup(c)
    assert last(send(c,'다른 프로젝트는 없어?'))['result']['kind']=='clarification'
    first=send(c,'기간 관련 내용 있어?')
    ambiguous=send(c,'이 프로젝트만 보여줘',cid=first['id'])
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


def test_content_scope_edits_keep_topic_and_cutoff_until_explicit_current(client,monkeypatch):
    from work.v3 import chat_interpreter as language
    from work.v17 import retrieval
    c,_=client
    a=project(c,'북산 광학검사기');b=project(c,'남해 광학검사기')
    empty=project(c,'동백 건조기');hidden=project(c,'비공개 검사기',members=['team1'])
    meeting(c,a,'검사 주기는 0.8초이다.','2026-10-05')
    meeting(c,a,'검사 주기는 0.6초이다.','2026-10-12')
    meeting(c,b,'검사 주기는 1.2초이다.','2026-10-06')
    meeting(c,b,'검사 주기는 1.0초이다.','2026-10-12')
    meeting(c,empty,'건조 압력은 2.5 kPa이다.','2026-10-03')
    meeting(c,hidden,'검사 주기는 9.9초이다.','2026-10-06')
    c.post('/api/demo-login',json={'username':'team2'})
    class Inline:
        def submit(self,fn,*args):fn(*args)
    monkeypatch.setattr(questions,'POOL',Inline());monkeypatch.setattr(questions,'JOBS',{})
    monkeypatch.setattr(retrieval,'embed',lambda texts,prefix:[[1.,0.] for _ in texts])
    requests=[]
    def infer(_w,payload):
        assert payload['content_scope_edit']
        requests.append(payload)
        assert hidden['name'] not in str(payload)
        q=payload['question']
        scope='all' if '모든' in q else 'named' if payload['named_projects'] else 'keep'
        time='current' if '최신' in q else 'keep'
        return language.Plan(action='search',content_scope={'scope':scope,'time':time}).model_dump()
    monkeypatch.setattr(language,'infer',infer)
    def generate(_w,q,sources,**kw):
        assert '검사 주기' in q and all(s['project_id']!=hidden['id'] for s in sources)
        if sources[0]['query_scope'].get('end'):
            assert all(s['date']<='2026-10-08' for s in sources)
        relevant=[s for s in sources if '검사 주기' in s['text']]
        if not relevant:return {'answerable':False,'points':[]}
        s=max(relevant,key=lambda s:s['date'])
        line=next(l for l in s['text'].splitlines() if '검사 주기' in l)
        return {'answerable':True,'points':[{'text':line,'sources':[s['id']]}]}
    monkeypatch.setattr(questions,'generate',generate)
    first=send(c,'10월 8일 기준 검사 주기는 얼마였어?',a['id'])
    expanded=send(c,'모든 프로젝트로 범위를 넓혀줘',cid=first['id'])
    assert result_projects(expanded)=={a['id'],b['id']}
    assert context(expanded)['time_scope']['end']=='2026-10-08'
    assert set(context(expanded)['project_ids'])=={a['id'],b['id'],empty['id']}
    absent=send(c,'동백 쪽만 보면?',cid=first['id'])
    assert not last(absent)['result']['answerable']
    assert context(absent)['project_ids']==[empty['id']]
    assert context(absent)['time_scope']['end']=='2026-10-08'
    selected=send(c,'남해 쪽으로 범위를 좁혀줘',cid=first['id'])
    assert result_projects(selected)=={b['id']}
    assert '1.2초' in str(last(selected)['result']['points'])
    latest=send(c,'최신 기준으로 다시 확인해줘',cid=first['id'])
    assert context(latest)['project_ids']==[b['id']] and context(latest)['time_scope']['end'] is None
    assert '1.0초' in str(last(latest)['result']['points'])
    # A genuinely new project inventory request keeps its own metadata route.
    inventory=send(c,'전체 프로젝트 목록을 보여줘',cid=first['id'])
    assert last(inventory)['result']['kind']=='projects'
    assert len(requests)==4


@pytest.mark.parametrize('question,edit',[
    ('북산 쪽만 보면?',{'scope':'all','time':'keep'}),
    ('전체 프로젝트로 넓혀줘',{'scope':'all','time':'current'}),
    ('13월 기준으로는?',{'scope':'keep','time':'current'}),
])
def test_scope_model_cannot_drop_literal_project_or_date_conditions(client,question,edit):
    from work.v3 import chat_interpreter as language
    c,_=client;a=project(c,'북산 검사장비');project(c,'남해 검사장비')
    old={'state':'done','context':{'query':'검사 주기는?','project_id':a['id'],
        'project_ids':[a['id']],'time_scope':{'mode':'as_of','start':None,'end':'2026-10-08'}},
        'job':{'result':{'kind':'documents','answerable':False,'sources':[]}}}
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        _,result=language.execute(w,db,actor,question,language.Plan(action='search',content_scope=edit).model_dump(),old)
    assert result['kind']=='clarification' and not result['sources']


def test_scope_planner_preserves_untouched_project_date_and_topic_slots(client,monkeypatch):
    from work.v3 import chat_interpreter as language
    c,_=client
    a=project(c,'솔빛 검사 장비');b=project(c,'바다 검사 장비')
    meeting(c,a,'납품일은 2026-12-20로 합의했다.','2026-11-05')
    meeting(c,b,'납품일은 2026-12-25로 합의했다.','2026-11-06')
    monkeypatch.setenv('B2_CHAT_SCOPE_PLANNER','1')
    scope={'mode':'as_of','start':None,'end':'2026-11-09'}
    old={'state':'done','context':{'query':'2026-11-09 기준 납품일은 언제야?', 'project_id':a['id'],
         'project_ids':[a['id']],'subject':'납품일','time_scope':scope},
         'job':{'result':{'kind':'documents','mode':'baseline','answerable':True,'sources':[]}}}
    cases=[
        ('바다 쪽으로 다시 보면?',{'scope':'named'},[b['id']],scope,'납품일'),
        ('2026년 11월 7일 기준으로는 어땠어?',{'time':'specified'},[a['id']],{**scope,'end':'2026-11-07'},'납품일'),
    ]
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        for query,edit,ids,expected_time,subject in cases:
            assert language.payload_for(w,db,actor,query,old)['content_scope_edit']
            ctx,result=language.execute(w,db,actor,query,language.Plan(action='search',content_scope=edit).model_dump(),old)
            assert result is None, result
            assert ctx['project_ids']==ids and ctx['time_scope']==expected_time
            assert ctx['subject']==subject and subject in ctx['query']
        query='그럼 코팅 폭은 얼마야?'
        assert not language.payload_for(w,db,actor,query,old)['content_scope_edit']
        context=resolve_question(w,db,actor,query,old)
        assert context['subject']=='코팅 폭' and context['time_scope']['end'] is None
        _,result=language.execute(w,db,actor,'2026년 11월 7일 기준으로는 어땠어?',
            language.Plan(action='search',content_scope={'time':'keep'}).model_dump(),old)
        assert result['kind']=='clarification' and not result['sources']


def test_scope_edit_rechecks_permission_after_interpretation(client):
    from work.v3 import chat_interpreter as language
    c,_=client;a=project(c,'북산 검사장비');b=project(c,'남해 검사장비')
    old={'state':'done','context':{'query':'검사 주기는?','project_id':a['id'],'project_ids':[a['id']]},
        'job':{'result':{'kind':'documents','answerable':False,'sources':[]}}}
    with w.connect() as db:
        actor=w.read(db,'person','team2')
        payload=language.payload_for(w,db,actor,'남해 쪽만 보면?',old)
        assert payload['content_scope_edit'] and payload['named_projects']==[b['name']]
        b['members']=['team1'];w.save(db,'project',b)
        _,result=language.execute(w,db,actor,'남해 쪽만 보면?',
            language.Plan(action='search',content_scope={'scope':'named','time':'keep'}).model_dump(),old)
    assert result['kind']=='clarification' and not result['sources']


def test_explicit_remaining_projects_excludes_every_named_project(client):
    from work.v3.conversations import resolve_question
    c,_=client
    a=project(c,'솔빛정밀 롤프레스')
    b=project(c,'해솔기전 검사 장비')
    remaining=project(c,'한울소재 전극 절단기')
    project(c,'숨김소재 시험장비',members=['team1'])
    with w.connect() as db:
        actor=w.read(db,'person','team2')
        query='솔빛정밀하고 해솔기전 빼고 나머지 프로젝트의 납품일 알려줘'
        context=resolve_question(w,db,actor,query)
        assert context['query']=='납품일 알려줘'
        assert context['project_ids']==[remaining['id']]
        assert set(context['exploration']['excluded_ids'])=={a['id'],b['id']}
        unknown=resolve_question(w,db,actor,query.replace('해솔기전','없는이름'))
        assert unknown['clarify'] and not unknown['project_ids']
        scoped=resolve_question(w,db,actor,query,project_id=a['id'])
        assert scoped['clarify'] and not scoped['project_ids']
    meeting(c,remaining,'2026년 9월 2일 납품으로 합의했다.','2026-07-02')
    c.post('/api/demo-login',json={'username':'team2'}).raise_for_status()
    response=c.post('/api/conversations/questions',json={'question':query})
    assert response.status_code==202,response.text
    with w.connect() as db:
        turn=w.read(db,'ai_message',response.json()['messages'][-1]['id'])
        assert turn['job']['scope_ids']==[remaining['id']]


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
