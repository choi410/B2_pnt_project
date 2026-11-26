"""Conversation behavior, permissions and evidence are checked in a disposable DB."""
import pytest
from work.v3.test_connected import client, w
from work.v3.test_question_scope import speed_history, change
from work.v3.test_questions_trash import meeting
from work.v3 import conversations, question_policy
from work.v17 import questions
from work.v17.retrieval import registered_document


@pytest.mark.parametrize('question',[
    '그럼 코팅 폭 쪽 담당이랑 기한은?', '코팅폭은 누가 언제까지 확인해?',
])
def test_attribute_topic_switch_does_not_select_equipment_project(client,question):
    from work.v3.test_questions_trash import project
    from work.v3 import chat_interpreter as language
    from work.v3.query_intent import strip_labels
    c,_=client;a=project(c,'푸른식품 코팅라인');b=project(c,'코팅 설비 제작 프로젝트')
    meeting(c,a,'코팅 폭 사양은 문지호가 2027-03-20까지 확인한다.')
    previous={'state':'done','question':'푸른식품 내열 자료 담당은?',
        'context':{'query':'내열 자료 담당은?','project_id':a['id'],'project_ids':[a['id']],'subject':'내열 자료'},
        'job':{'result':{'kind':'documents','answerable':False,'sources':[]}}}
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        ctx=conversations.resolve_question(w,db,actor,question,previous)
        assert ctx['project_ids']==[a['id']] and ctx['subject'].replace(' ','')=='코팅폭'
        assert '내열 자료' not in ctx['query'] and not ctx.get('clarify')
        assert not language.payload_for(w,db,actor,question,previous)['content_scope_edit']
        # Complete project names and equipment-only requests still select B.
        switched=conversations.resolve_question(w,db,actor,b['name']+' 코팅 폭은?',previous)
        assert switched['project_ids']==[b['id']]
        assert question_policy.name_matches([a,b],'코팅 프로젝트 보여줘')==[b]
        assert '코팅' in strip_labels(question,[b])


def test_equipment_count_keeps_generic_name_out_of_project_scope(client):
    from work.v3.test_questions_trash import project
    from work.v3.query_intent import relative_period, strip_labels
    c,_=client
    slitter=project(c,'새롬에너지 전극 슬리터 3호기')
    press=project(c,'한빛셀 전극 롤프레스 1호기')
    private=project(c,'권한 없는 설비',members=['team2'])
    q='작년에 고객사로 보낸 슬리터는 몇 기야?'
    previous={'state':'done','question':'한빛셀 납품일은?',
              'context':{'project_id':press['id'],'project_ids':[press['id']]}}
    with w.connect() as db:
        w.save(db,'project',dict(private,pm='team2',members=['team2']))
        actor=w.read(db,'person','team1')
        for prior in (None,previous):
            ctx=conversations.resolve_question(w,db,actor,q,prior)
            assert set(ctx['project_ids'])=={slitter['id'],press['id']}
            assert ctx['project_id'] is None and not ctx.get('clarify') and slitter['name'] not in ctx['label']
            assert ctx['time_scope']=={'mode':'period',**relative_period('작년')}
        assert question_policy.scope_projects(w,db,None,actor,q)==question_policy.scope_projects(w,db,None,actor)
        assert '슬리터' in strip_labels(q,[slitter,press])
        for explicit in (slitter['name'],slitter['id'],'새롬에너지','슬리터 3호기'):
            assert question_policy.name_matches([slitter,press],explicit+' '+q)==[slitter]
        selected=conversations.resolve_question(w,db,actor,q,project_id=slitter['id'])
        assert selected['project_ids']==[slitter['id']]


def test_unit_delivery_date_offers_candidates_and_reuses_selected_project(client,monkeypatch):
    from work.v3.test_questions_trash import project

    monkeypatch.setenv('B2_CHAT_GENERAL','1')
    c,_=client
    first=project(c,'가람 전극 롤프레스 1호기')
    second=project(c,'한울 용액 믹서 1 호기')
    single=project(c,'나래 검사기 11호기')
    private=project(c,'제한 프로젝트 1호기',members=['team1'])
    for p,day in ((first,'2026-12-18'),(second,'2027-01-16'),(single,'2027-02-20')):
        row=meeting(c,p,f'장비 납품일은 {day}로 합의했다.')
        change(row,'장비 납품일',day)
    with w.connect() as db:
        w.save(db,'project',dict(private,pm='team1',members=['team1']))
    c.post('/api/demo-login',json={'username':'team2'}).raise_for_status()

    thread=send(c,'1호기 납품일')
    original=thread['messages'][-1]
    choice=original['result']
    assert choice['kind']=='clarification'
    assert {item['id'] for item in choice['projects']}=={first['id'],second['id']}
    assert 'selection' not in original

    pick={'conversation_id':thread['id'],'choice_message_id':original['id']}
    rejected=c.post('/api/conversations/questions',json={**pick,'project_id':single['id']})
    assert rejected.status_code==422
    response=c.post('/api/conversations/questions',json={**pick,'project_id':second['id']})
    assert response.status_code==202,response.text
    chosen=response.json()['messages'][-1]
    assert chosen['selection']=={'kind':'project','id':second['id'],'label':second['name'],'message_id':original['id']}
    saved=c.get(f"/api/conversations/{thread['id']}").json()['messages']
    assert saved[0]['question']=='1호기 납품일' and 'selection' not in saved[0]
    assert saved[-1]['selection']==chosen['selection']
    result=chosen['result']
    assert result['mode']=='baseline' and result['values'][0]['value']=='2027-01-16'
    assert {s['project_id'] for s in result['sources']}=={second['id']}
    proof=c.get(f"/api/conversations/{thread['id']}/messages/{chosen['id']}/sources/{result['sources'][0]['id']}")
    assert proof.status_code==200 and proof.json()['highlight']

    continued=send(c,'그럼 1 호기 납품일은?',cid=thread['id'])['messages'][-1]['result']
    assert {s['project_id'] for s in continued['sources']}=={second['id']}
    alternate=c.post('/api/conversations/questions',json={**pick,'project_id':first['id']})
    assert alternate.status_code==202,alternate.text
    latest=alternate.json()['messages'][-1]
    assert latest['selection']['label']==first['name'] and latest['result']['values'][0]['value']=='2026-12-18'
    unique=send(c,'11호기납품일')['messages'][-1]['result']
    assert unique['values'][0]['value']=='2027-02-20'
    mismatch=send(c,'1호기 납품일',p=single['id'])['messages'][-1]['result']
    assert mismatch['kind']=='clarification' and not mismatch['answerable']
    missing=send(c,'9호기 납품일')['messages'][-1]['result']
    assert '9호기' in missing['message'] and not missing['projects']


def test_registered_field_keeps_project_despite_equipment_alias(client):
    from work.v3.test_questions_trash import project,event
    c,_=client
    a=project(c,'푸른제약 충전라인');b=project(c,'충전 설비 개선')
    m=meeting(c,a,'충전 중량은 320 g이다.')
    e=event(m,'weight','합의','320 g');e['title']='충전 중량'
    with w.connect() as db:
        w.save(db,'change_event',e);actor=w.read(db,'person','team1')
        previous={'question':'온도는?','context':{'project_ids':[a['id']],'subject':'온도'},'job':{'result':{'kind':'clarification'}}}
        ctx=conversations.resolve_question(w,db,actor,'충전 중량은?',previous)
        assert ctx['project_ids']==[a['id']] and ctx['subject']=='충전 중량'
        assert '온도' not in ctx['query']
        explicit=conversations.resolve_question(w,db,actor,b['name']+' 충전 중량은?',previous)
        assert explicit['project_ids']==[b['id']]
        by_code=conversations.resolve_question(w,db,actor,b['id']+' 충전 중량은?',previous)
        assert by_code['project_ids']==[b['id']]
        selected=conversations.resolve_question(w,db,actor,'충전 중량은?',previous,b['id'])
        assert selected['project_ids']==[b['id']]
        # An unrelated new field must not become the old field automatically.
        ctx=conversations.resolve_question(w,db,actor,'보증 기간은?',previous)
        assert '충전 중량' not in ctx['query'] and '온도' not in ctx['query']


def test_field_resolution_does_not_override_other_project_request(client):
    from work.v3.test_questions_trash import project,event
    c,_=client;a=project(c,'푸른제약 코팅라인');b=project(c,'새별 코팅라인')
    m=meeting(c,a,'코팅 폭은 500 mm이다.');meeting(c,b,'코팅 폭은 600 mm이다.')
    e=event(m,'width','합의','500 mm');e['title']='코팅 폭'
    with w.connect() as db:
        w.save(db,'change_event',e);actor=w.read(db,'person','team1')
        previous={'question':'푸른제약 코팅 폭은?', 'context':{'query':'코팅 폭은?','project_ids':[a['id']],'subject':'코팅 폭'},
            'job':{'result':{'sources':[{'project_id':a['id'],'meeting_id':m['id']}]}}}
        ctx=conversations.resolve_question(w,db,actor,'다른 프로젝트도 코팅 폭 논의했어?',previous)
        assert ctx['project_ids']==[b['id']]


def test_field_context_does_not_restore_revoked_project(client):
    from work.v3.test_questions_trash import project,event
    from work.v3.conversation_context import field_project
    c,_=client;p=project(c,'보안 설비',members=['team1']);m=meeting(c,p)
    e=event(m,'private','합의','320 g');e['title']='충전 중량'
    with w.connect() as db:
        w.save(db,'change_event',e);actor=w.read(db,'person','team2')
        previous={'context':{'project_ids':[p['id']]},'job':{'result':{}}}
        assert field_project(w,db,actor,'충전 중량은?',previous) is None


@pytest.mark.parametrize('state',['done','failed'])
def test_empty_answer_keeps_explicit_project_across_new_topics(client,state):
    from work.v3.test_questions_trash import project
    c,_=client;a=project(c,'다래소재 세척 장비');b=project(c,'모아전자 검사 장비')
    prev={'state':state,'question':'다래소재 세정제 변경 결론 났어?',
          'context':{'project_id':a['id'],'project_ids':[a['id']],'query':'세정제 변경 결론 났어?',
                     'exploration':{'pinned_id':a['id']}},
          'job':{'result':{'kind':'documents','answerable':False,'sources':[]}}}
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        ctx=conversations.resolve_question(w,db,actor,'지금 진행 못 하는 원인이 뭔데?',prev)
        assert ctx['project_ids']==[a['id']] and ctx['project_id']==a['id']
        assert ctx['exploration']['pinned_id']==a['id']
        prev['context']=ctx
        ctx=conversations.resolve_question(w,db,actor,'온도 센서 쪽 할 일은?',prev)
        assert ctx['project_ids']==[a['id']] and ctx['query']=='온도 센서 쪽 할 일은?'
        explicit=conversations.resolve_question(w,db,actor,'모아전자 납품일은?',prev)
        assert explicit['project_ids']==[b['id']]
        broad=conversations.resolve_question(w,db,actor,'전체 프로젝트 납품일은?',prev)
        assert set(broad['project_ids'])=={a['id'],b['id']}
        unknown=conversations.resolve_question(w,db,actor,'은하위성 추진기 프로젝트 납품일은?',prev)
        assert unknown.get('clarify')
        fresh=conversations.resolve_question(w,db,actor,'온도 센서 쪽 할 일은?')
        assert set(fresh['project_ids'])=={a['id'],b['id']}


def test_kept_project_is_not_replaced_after_permission_loss(client):
    from fastapi import HTTPException
    from work.v3.test_questions_trash import project
    c,_=client;a=project(c,'보안 장비',members=['team1']);project(c,'공개 장비')
    prev={'state':'failed','context':{'project_id':a['id'],'project_ids':[a['id']]},'job':{}}
    with w.connect() as db:
        actor=w.read(db,'person','team2')
        with pytest.raises(HTTPException):
            conversations.resolve_question(w,db,actor,'진행 못 하는 원인은?',prev)


def test_interpreted_topic_survives_reason_followup_without_registered_field(client):
    from work.v3.test_questions_trash import project
    c,_=client;p=project(c,'아람테크 시험 장비');other=project(c,'새별 시험 장비')
    q='10월 5일 기준 압력을 상향하자는 제안, 결말이 뭐야?'
    source={'project_id':p['id'],'meeting_id':'m','query_scope':{'content_meaning':{
        'terms':['압력을','상향하자는','제안'],'purpose':'decision'}}}
    previous={'state':'done','question':q,'context':{'query':q,'subject':'','project_id':p['id'],'project_ids':[p['id']],
        'time_scope':{'mode':'as_of','start':None,'end':'2026-10-05'}},
        'job':{'result':{'answerable':True,'sources':[source],'points':[{'text':'존재하지 않는 허위 답변 999 kPa'}]}}}
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        context=conversations.resolve_question(w,db,actor,'왜 보류된 거야?',previous)
        assert not context.get('clarify') and context['project_ids']==[p['id']]
        assert context['subject']=='압력을 상향하자는 제안' and '왜 보류' in context['query']
        assert '999' not in context['query'] and context['time_scope']['end']=='2026-10-05'
        changed=conversations.resolve_question(w,db,actor,'온도 센서 쪽 할 일은?',previous)
        assert '상향' not in changed['query']
        different=conversations.resolve_question(w,db,actor,'왜 보류된 거야?',previous,other['id'])
        assert different.get('clarify') and '상향' not in different['query']


@pytest.mark.parametrize('terms', [['모델이 만든 항목'],[],['압력을','999']])
@pytest.mark.parametrize('topic_source',['interpretation','evidence'])
def test_interpreted_subject_must_come_from_previous_user_query(terms,topic_source):
    from work.v3.conversation_context import interpreted_subject
    previous={'state':'done','question':'압력을 높이는 건 결론 났어?',
        'context':{'project_ids':['p'],'query':'압력을 높이는 건 결론 났어?'},
        'job':{'result':{'answerable':True,'sources':[{'project_id':'p','query_scope':
            {'content_meaning':{'terms':terms}} if topic_source=='interpretation' else {'evidence_topic_terms':terms}}]}}}
    assert interpreted_subject(previous,['p'])==''


def test_cited_record_followups_keep_the_topic_and_apply_an_explicit_new_date(client,monkeypatch):
    from work.v3 import chat_interpreter, general_chat
    from work.v3.test_questions_trash import project
    from work.v17.retrieval import registered_document

    c,_=client
    monkeypatch.setenv('B2_CHAT_GENERAL','1')
    p=project(c,'한내기전 조립 장비')
    other=project(c,'해온테크 조립 장비')
    raw=meeting(c,p,'배기 필터 설치 변경은 자재 입고가 지연되어 보류했다.','2026-09-11')
    doc=registered_document(raw)
    source={'project_id':p['id'],'meeting_id':doc['meeting_id'],'fingerprint':doc['fingerprint'],
            'line_ids':[raw['lines'][-1]['id']],'query_scope':{'evidence_topic_terms':['배기','필터는']}}
    previous={'state':'done','question':'배기 필터는 어떻게 하기로 했어?',
              'context':{'query':'배기 필터는 어떻게 하기로 했어?','project_id':p['id'],
                         'project_ids':[p['id']],'time_scope':{'mode':'as_of','start':None,'end':'2026-09-15'}},
              'job':{'result':{'kind':'documents','answerable':True,'sources':[source]}}}
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        cases=[
            ('왜 그때 변경을 미뤘어?', '2026-09-15', '보류'),
            ('그러다가 24일에는 뭘로 합의했어?', '2026-09-24', '합의'),
            ('그 필터는 결국 실제로 설치됐어?', '2026-09-15', '설치'),
            ('그 필터는 실제로 시행했어?', '2026-09-15', '시행'),
        ]
        for question, end, verb in cases:
            ctx=conversations.resolve_question(w,db,actor,question,previous)
            assert ctx.get('record_followup') and ctx['project_ids']==[p['id']]
            assert ctx['subject']=='배기 필터' and verb in ctx['query'] and ctx['time_scope']['end']==end
            assert not chat_interpreter.needs_interpreter(w,db,actor,question,ctx,previous)
            assert not general_chat.candidate(question,[p,other],ctx,previous,[])
        changed=conversations.resolve_question(w,db,actor,'그 필터는 실제로 설치됐어?',previous,other['id'])
        assert changed['project_ids']==[other['id']] and not changed.get('record_followup')
        assert '배기 필터' not in changed['query'] and changed['time_scope'].get('end') is None
        independent='별개로 한내기전 프로젝트 포장 상자 단가가 얼마야?'
        fresh=conversations.resolve_question(w,db,actor,independent,previous)
        assert fresh['project_ids']==[p['id']] and not fresh.get('clarify')
        assert '포장 상자 단가' in fresh['query'] and '배기 필터' not in fresh['query']
        assert fresh['time_scope'].get('end') is None
        assert not chat_interpreter.needs_interpreter(w,db,actor,independent,fresh,previous)
        source['fingerprint']='obsolete'
        stale=conversations.resolve_question(w,db,actor,'그 필터는 실제로 설치됐어?',previous)
        assert not stale.get('record_followup')


def test_schedule_reason_uses_named_project_and_only_carries_the_cited_field(client):
    from work.v3.test_questions_trash import project
    from work.v17.retrieval import registered_document

    c,_=client
    a=project(c,'한내기전 조립 장비')
    b=project(c,'해온테크 조립 장비')
    raw=meeting(c,a,'출하일을 2026-10-21로 합의했다.','2026-09-11')
    doc=registered_document(raw)
    source={'project_id':a['id'],'meeting_id':doc['meeting_id'],'fingerprint':doc['fingerprint'],
            'line_ids':[raw['lines'][-1]['id']]}
    previous={'state':'done','question':'출하일은 언제로 합의했어?',
              'context':{'query':'출하일은 언제로 합의했어?','project_id':a['id'],'project_ids':[a['id']],
                         'time_scope':{'mode':'as_of','start':None,'end':'2026-09-15'}},
              'job':{'result':{'kind':'documents','answerable':True,'sources':[source]}}}
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        question='해온테크 건은 왜 날짜가 달라졌던 거야?'
        ctx=conversations.resolve_question(w,db,actor,question,previous)
        assert ctx.get('record_followup') and ctx['project_ids']==[b['id']]
        assert ctx['query']=='출하일이 왜 바뀌었어?' and ctx['time_scope']['mode']=='current'
        previous['context']['query']='출하일과 검수일은 언제였어?'
        assert not conversations.resolve_question(w,db,actor,question,previous).get('record_followup')
        previous['context']['query']='출하일은 언제로 합의했어?'
        source['fingerprint']='obsolete'
        assert not conversations.resolve_question(w,db,actor,question,previous).get('record_followup')


def test_bare_completion_followup_uses_only_the_cited_prior_topic(client):
    from work.v3.test_questions_trash import project
    from work.v17.retrieval import registered_document

    c,_=client
    p=project(c,'산들 정렬 설비')
    meeting_row=meeting(c,p,'센서 편차 검증은 10월 첫째 주에 시행하자고 제안했다.','2026-09-21')
    doc=registered_document(meeting_row)
    source={'project_id':p['id'],'meeting_id':doc['meeting_id'],'fingerprint':doc['fingerprint'],
            'line_ids':[meeting_row['lines'][-1]['id']],
            'query_scope':{'evidence_topic_terms':['센서','편차','검증은']}}
    question='센서 편차 검증은 언제 하자고 했어?'
    previous={'state':'done','question':question,
              'context':{'query':question,'project_id':p['id'],'project_ids':[p['id']]},
              'job':{'result':{'kind':'documents','answerable':True,'sources':[source]}}}
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        context=conversations.resolve_question(w,db,actor,'그러면 끝난 거야?',previous)
        assert context['query']=='센서 편차 검증 완료됐어?' and context['record_followup']
        source['fingerprint']='obsolete'
        context=conversations.resolve_question(w,db,actor,'그러면 끝난 거야?',previous)
        assert context['clarify'] and not context.get('record_followup')


def test_named_qa_switch_reuses_the_cited_schedule_field(client):
    from work.v3.test_questions_trash import project
    from work.v17.retrieval import registered_document

    c,_=client
    current=project(c,'서진 조립 설비')
    other=project(c,'동온 검사 설비')
    meeting_row=meeting(c,current,'현장 인수 시험은 2026-10-19로 합의했다.','2026-09-21')
    doc=registered_document(meeting_row)
    source={'project_id':current['id'],'meeting_id':doc['meeting_id'],'fingerprint':doc['fingerprint'],
            'line_ids':[meeting_row['lines'][-1]['id']]}
    question='서진 현장 인수 시험은 언제로 정했어?'
    previous={'state':'done','question':question,
              'context':{'query':question,'project_id':current['id'],'project_ids':[current['id']]},
              'job':{'result':{'kind':'documents','mode':'recorded_schedule','schedule_subject':'현장 인수 시험',
                               'answerable':True,'sources':[source]}}}
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        context=conversations.resolve_question(w,db,actor,'동온 쪽은?',previous)
        assert context['project_ids']==[other['id']] and context['record_followup']
        assert context['query']=='현장 인수 시험은 언제로 정했어?'
        source['fingerprint']='obsolete'
        context=conversations.resolve_question(w,db,actor,'동온 쪽은?',previous)
        assert not context.get('record_followup')


@pytest.fixture(autouse=True)
def isolated_chat_database(tmp_path, monkeypatch):
    monkeypatch.setattr(w, 'DB', tmp_path/'chat.sqlite3')
    monkeypatch.setattr(w, 'FILES', tmp_path/'files')
    monkeypatch.setattr(questions, 'JOBS', {})


@pytest.mark.parametrize('question,words,is_new',[
    ('토크는 얼마로 하기로 했지?',['토크는'],True),
    ('도장 색상은 왜 바뀌었어?',['도장'],True),
    ('냉각수 유량은 얼마야?',['냉각수','유량은'],True),
    ('진동 진폭은 왜 커졌어?',['진동','진폭은'],True),
    ('그럼 베어링 수명은?',['베어링'],True),
    ('왜 그랬어?',[],False),
    ('언제 바뀐 거야?',['언제'],False),
    ('그 요청은 왜 보류했어?',['요청은'],False),
    ('그건 누가 해?',['그건'],False),
    ('언제까지야?',['언제까지야'],False),
    ('그 일은 끝났어?',['그','일은'],False),
    ('그 업무는 완료됐어?',['그','업무는'],False),
    ('그 업무는 완료됐어?',['업무는'],False),
    ('해당 작업은 언제까지야?',['작업은'],False),
    ('그건 냉각수 유량은 얼마야?',['냉각수','유량은'],True),
])
def test_content_followup_selects_current_target_without_rewriting_question(client,monkeypatch,question,words,is_new):
    from work.v3.test_questions_trash import project
    from work.v3 import chat_interpreter as language,chat_model
    c,_=client;p=project(c,'다래 시험 장비');other=project(c,'모아 시험 장비')
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    previous={'state':'done','question':'압력 변경 결과는?',
        'context':{'query':'압력 변경 결과는?','subject':'압력','project_id':p['id'],'project_ids':[p['id']],
                   'time_scope':{'mode':'as_of','start':None,'end':'2026-10-05'}},
        'job':{'result':{'kind':'documents','answerable':True,'points':[{'text':'없는 사실 999 kPa'}],'sources':[]}}}
    calls=[]
    def select(_w,request):
        calls.append(request)
        assert request.payload['question']==question
        assert '999' not in str(request.payload) and other['id'] not in str(request.payload)
        return {'words':words}
    monkeypatch.setattr(chat_model,'complete',select)
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        pending=conversations.resolve_question(w,db,actor,question,previous)
        assert pending['query']==question and pending['topic_followup']['subject']=='압력'
        assert language.needs_interpreter(w,db,actor,question,pending,previous)
        raw=language.infer(w,language.payload_for(w,db,actor,question,previous))
        # Even irrelevant scope fields cannot redirect a topic-only decision.
        raw.update(scope='all',projects=[other['id']])
        context,result=language.execute(w,db,actor,question,raw,previous)
    assert len(calls)==1 and result is None and context['project_ids']==[p['id']]
    if is_new:
        assert context['query']==question and context['subject']==''
        assert not context['time_scope'].get('end')
    else:
        assert '압력' in context['query'] and question in context['query']
        assert context['time_scope']['end']=='2026-10-05'
    assert '999' not in context['query']


@pytest.mark.parametrize('raw',[
    {'words':['가짜대상']}, {'words':['토크는'],'project_id':'hidden'}, {'words':[1]},
])
def test_topic_selection_cannot_invent_words_or_scope(client,monkeypatch,raw):
    from work.v3 import chat_interpreter as language,chat_model
    monkeypatch.setattr(chat_model,'complete',lambda *a,**kw:raw)
    with pytest.raises(ValueError):
        language.infer(w,{'question':'토크는 얼마야?','topic_followup':{'subject':'압력'}})


@pytest.mark.parametrize('question',['그건 누가 해?','그 일은 끝났어?','그 업무는 완료됐어?'])
@pytest.mark.parametrize('has_previous',[False,True])
def test_task_reference_without_established_subject_asks_for_task(client,question,has_previous):
    from work.v3.test_questions_trash import project
    c,_=client;p=project(c,'푸른 검사장비')
    meeting(c,p,'배선 검토는 이지훈이 맡는다.\n센서 교정은 박하늘이 맡는다.')
    previous={'state':'done','question':'어떤 업무가 있어?',
        'context':{'query':'어떤 업무가 있어?','project_id':p['id'],'project_ids':[p['id']]},
        'job':{'result':{'answerable':True,'points':[],'sources':[]}}} if has_previous else None
    with w.connect() as db:
        context=conversations.resolve_question(w,db,w.read(db,'person','team1'),question,previous,p['id'])
    assert '어떤 항목이나 업무' in context.get('clarify','') and not context['subject']


def test_topic_selection_rechecks_project_access_after_model(client,monkeypatch):
    from fastapi import HTTPException
    from work.v3.test_questions_trash import project
    from work.v3 import chat_interpreter as language
    c,_=client;p=project(c,'보안 설비',members=['team1']);project(c,'공개 설비')
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    previous={'state':'done','context':{'query':'압력 변경은?','subject':'압력','project_id':p['id'],'project_ids':[p['id']]},'job':{}}
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        assert language.payload_for(w,db,actor,'토크는 얼마야?',previous)['topic_followup']
        p['members']=[];w.save(db,'project',p)
        with pytest.raises(HTTPException):
            language.execute(w,db,actor,'토크는 얼마야?',language.Plan(action='search',topic_words=['토크는']).model_dump(),previous)


@pytest.mark.parametrize('timeout',[False,True])
def test_topic_switch_after_no_evidence_uses_async_api(client,monkeypatch,timeout):
    from work.v3.test_questions_trash import project
    from work.v3 import chat_model
    c,_=client;p=project(c,'다래 시험 장비');project(c,'별도 시험 장비')
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    monkeypatch.setattr(question_policy,'quick_answer',lambda *a,**kw:None)
    captured=[]
    class Inline:
        def submit(self,fn,*args):fn(*args)
    monkeypatch.setattr(questions,'POOL',Inline())
    def no_evidence(_w,jid,*args):
        job=questions.JOBS[jid];captured.append((job['question'],job['scope_ids']))
        questions.update(jid,state='done',result={'kind':'documents','answerable':False,'points':[],'sources':[]})
    monkeypatch.setattr(questions,'answer_job',no_evidence)
    def select(_w,request):
        assert request.payload['question']=='토크는 얼마야?'
        if timeout:raise TimeoutError()
        return {'words':['토크는']}
    monkeypatch.setattr(chat_model,'complete',select)
    first=c.post('/api/conversations/questions',json={'question':'압력 변경 결과 알려줘','project_id':p['id']})
    assert first.status_code==202,first.text
    second=c.post('/api/conversations/questions',json={'question':'토크는 얼마야?','conversation_id':first.json()['id']})
    assert second.status_code==202,second.text
    message=second.json()['messages'][-1]
    assert message['state']=='done'
    if timeout:
        assert len(captured)==1 and message['result']['kind']=='clarification'
    else:
        assert captured[-1]==('토크는 얼마야?',[p['id']]) and len(captured)==2
        with w.connect() as db:
            saved=w.read(db,'ai_message',message['id'])
        assert saved['context']['query']=='토크는 얼마야?' and saved['context']['project_ids']==[p['id']]


@pytest.mark.parametrize('followup,mode,start,end',[
    ('10월 13일에는?','as_of',None,'2026-10-13'),
    ('그럼 10월 13일은?','as_of',None,'2026-10-13'),
    ('10월 13일 기준','as_of',None,'2026-10-13'),
    ('10월 13일 회의만 보여줘','meeting','2026-10-13','2026-10-13'),
    ('10월 회의록만','period','2026-10-01','2026-10-31'),
])
def test_date_followup_keeps_cutoff_but_explicit_records_override_it(client,followup,mode,start,end):
    from work.v3.test_questions_trash import project
    from work.v3.question_scope import in_scope
    c,_=client;p=project(c,'광학 시험 장비')
    older=meeting(c,p,'검사 주기는 0.8초이다.','2026-10-05')
    newer=meeting(c,p,'검사 주기는 0.6초로 변경했다.','2026-10-12')
    with w.connect() as db:
        actor=w.read(db,'person','team1');q='10월 8일 기준 검사 주기는 얼마였어?'
        first=conversations.resolve_question(w,db,actor,q,project_id=p['id'])
        previous={'question':q,'context':first,'job':{'result':{'answerable':False}}}
        context=conversations.resolve_question(w,db,actor,followup,previous)
    assert context['project_ids']==[p['id']]
    assert '검사 주기' in context['query'] if mode=='as_of' else context['query']==followup
    assert context['time_scope']=={'mode':mode,'start':start,'end':end}
    expected=[] if mode=='meeting' else [older['id'],newer['id']]
    assert [m['id'] for m in [older,newer] if in_scope(m,context['time_scope'])]==expected


def setup_chat(c, monkeypatch):
    p, a, b, d = speed_history(c)
    captured = []
    def quick(w, db, ps, actor, q, pid, plan):
        captured.append((q, pid, plan))
        doc = registered_document(w.read(db, 'meeting', d['id']))
        source = {k: v for k, v in doc.items() if k != 'body'} | {
            'id': 'S1', 'project_name': p['name'], 'line_ids': [d['lines'][-1]['id']], 'text': d['lines'][-1]['text']}
        return {'kind': 'documents', 'points': [{'project_id': p['id'], 'project_name': p['name'],
            'text': '135 m/min으로 합의했습니다.', 'sources': ['S1']}], 'sources': [source]}
    monkeypatch.setattr(question_policy, 'quick_answer', quick)
    return p, d, captured


def send(c, q, p=None, cid=None):
    response = c.post('/api/conversations/questions', json={'question': q, 'project_id': p, 'conversation_id': cid})
    assert response.status_code == 202, response.text
    return response.json()


@pytest.mark.parametrize('scenario',['two','three','changed_source'])
def test_other_side_validates_original_pair_and_uses_latest_record(client,monkeypatch,scenario):
    from work.v3.test_questions_trash import project
    from work.v3.topic_search import source_for
    from work.v17.retrieval import document_lines

    c,_=client
    p=project(c,'서해 열처리 장비')
    earlier='주 히터 전압은 220 V로 합의했다. 보조 히터 전압은 48 V로 합의했다.'
    if scenario=='three':
        earlier+=' 예비 히터 전압은 36 V로 합의했다.'
    first=meeting(c,p,earlier,'2026-09-01')
    latest=meeting(c,p,'주 히터 전압은 240 V로 변경 합의했다. 보조 히터 전압은 48 V를 유지한다.','2026-09-15')
    def quick(_w,db,ps,actor,q,scope,plan):
        document=registered_document(w.read(db,'meeting',first['id']))
        source=source_for(document,p,'S1',document_lines(document)[-1:],{
            'content_meaning':{'terms':['히터','전압은']}})
        return {'kind':'documents','answerable':True,'points':[{
            'text':'자동 설명에 적힌 값을 재사용하면 안 됩니다. 900 V', 'project_id':p['id'],'sources':['S1'],
        }],'sources':[source]}
    monkeypatch.setattr(question_policy,'quick_answer',quick)
    thread=send(c,'서해 히터 전압은 얼마야?',p['id'])
    thread=send(c,'보조 쪽',cid=thread['id'])
    send(c,'고마워',cid=thread['id'])
    if scenario=='changed_source':
        with w.connect() as db:
            row=w.read(db,'meeting',first['id'])
            row['deleted_at']=w.now()
            w.save(db,'meeting',row)

    thread=send(c,'그럼 다른 쪽도 알려줘',cid=thread['id'])
    message=thread['messages'][-1]
    result=message['result']
    if scenario!='two':
        assert result['kind']=='clarification' and not result['sources']
        return
    assert result['mode']=='paired_alternative'
    assert [point['text'] for point in result['points']]==['주 히터 전압은 240 V로 변경 합의했다.']
    proof=c.get(f"/api/conversations/{thread['id']}/messages/{message['id']}/sources/{result['sources'][0]['id']}")
    assert proof.status_code==200 and proof.json()['highlight']
    assert proof.json()['meeting_id']==latest['id']


def test_followup_uses_subject_and_project_but_not_generated_fact(client, monkeypatch):
    c, _ = client
    p, _, captured = setup_chat(c, monkeypatch)
    first = send(c, '현재 압연 속도는 얼마야?', p['id'])
    second = send(c, '왜 바뀐 거야?', cid=first['id'])
    assert len(second['messages']) == 2
    assert second['messages'][-1]['question'] == '왜 바뀐 거야?'
    assert captured[-1][1] == p['id']
    assert '압연 속도' in captured[-1][0]
    assert '135' not in captured[-1][0], 'A prior generated number is not injected as evidence'
    # History survives the question engine's in-memory cache being cleared.
    with questions.LOCK:
        questions.JOBS.clear()
    restored = c.get('/api/conversations/'+first['id']).json()
    assert len(restored['messages']) == 2
    assert restored['messages'][0]['result']['points']


def test_record_management_guidance_preserves_records_and_previous_query(client, monkeypatch):
    c, _ = client
    p, d, captured = setup_chat(c, monkeypatch)
    first = send(c, '현재 압연 속도는 얼마야?', p['id'])
    search_count = len(captured)
    with w.connect() as db:
        original = (w.read(db, 'project', p['id']), w.read(db, 'meeting', d['id']))
    for question, menu in (
        ('프로젝트 삭제해줘', '프로젝트 삭제'),
        ('이 회의록을 좀 지워 주세요.', '회의록 상세'),
        ('시점 검증 압연 설비 프로젝트 복원해 줄래?', '휴지통'),
    ):
        result = send(c, question, cid=first['id'])['messages'][-1]['result']
        assert result['mode'] == 'unsupported_action'
        assert menu in result['message'] and result['sources'] == []
    assert len(captured) == search_count
    with w.connect() as db:
        assert (w.read(db, 'project', p['id']), w.read(db, 'meeting', d['id'])) == original

    continued = send(c, '왜 바뀐 거야?', cid=first['id'])['messages'][-1]
    assert continued['result']['points']
    followup_searches = captured[search_count:]
    assert followup_searches
    assert all('압연 속도' in q and pid == p['id'] for q, pid, _ in followup_searches)


def test_followup_date_and_explicit_current_reset(client, monkeypatch):
    c, _ = client
    p, _, captured = setup_chat(c, monkeypatch)
    first = send(c, '2026-11-11 기준 압연 속도는 얼마야?', p['id'])
    send(c, '왜 그렇게 정했어?', cid=first['id'])
    assert captured[-1][2]['end'] == '2026-11-11'
    send(c, '그럼 현재는 얼마야?', cid=first['id'])
    assert captured[-1][2]['mode'] == 'current'
    assert captured[-1][2]['end'] is None
    send(c, '11월 11일에는 얼마였어?', cid=first['id'])
    assert captured[-1][2]['end'] == '2026-11-11'


def test_cutoff_followup_reuses_topic_from_registered_source(client):
    from work.v3.test_questions_trash import project
    c,_=client
    p=project(c,'푸른식품 포장라인')
    m=meeting(c,p,'밀봉 폭은 20 mm로 합의했다.','2026-08-12')
    previous={'state':'done','question':'푸른식품 밀봉 폭은 얼마야?',
        'context':{'query':'푸른식품 밀봉 폭은 얼마야?','project_ids':[p['id']]},
        'job':{'result':{'answerable':True,'sources':[{'project_id':p['id'],'meeting_id':m['id'],
            'query_scope':{'content_meaning':{'terms':['밀봉','폭은']}}}]}}}
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        context=conversations.resolve_question(w,db,actor,'2026년 8월 15일 기준으로는 어땠나요?',previous)
        assert '밀봉 폭' in context['query']
        assert context['project_ids']==[p['id']]
        assert context['time_scope']=={'mode':'as_of','start':None,'end':'2026-08-15'}


def test_remaining_projects_excludes_grounded_previous_project_switch(client):
    from work.v3.test_questions_trash import project
    c,_=client
    a,b,d=[project(c,name) for name in ('들꽃 설비','푸른 기계','바다 전극')]
    secret=project(c,'비공개 검사 설비')
    period={'mode':'as_of','start':None,'end':'2026-08-15'}
    with w.connect() as db:
        w.save(db,'project',dict(secret,pm='team2',members=['team2']))
        actor=w.read(db,'person','team1')
        old={'state':'done','question':'들꽃 납품일 언제야?',
             'context':{'query':'납품일 언제야?','subject':'납품일','project_id':a['id'],
                        'project_ids':[a['id']],'time_scope':period},
             'job':{'result':{'answerable':True,'sources':[{'project_id':a['id']}]}}}
        context=conversations.resolve_question(w,db,actor,'푸른은?',old)
        assert context['project_ids']==[b['id']]
        previous={**old,'context':context,'job':{'result':{'answerable':True,'sources':[{'project_id':b['id']}]}}}
        remaining=conversations.resolve_question(w,db,actor,'앞서 조회한 두 곳을 빼고 다른 프로젝트는요?',previous)
        assert remaining['project_ids']==[d['id']] and remaining['time_scope']==period
        assert '납품일' in remaining['query']
        unresolved=conversations.resolve_question(w,db,actor,'앞서 조회한 세 곳을 빼고 다른 프로젝트는요?',previous)
        assert unresolved['clarify']


def test_new_attribute_does_not_reuse_old_topic(client, monkeypatch):
    c, _ = client
    p, _, captured = setup_chat(c, monkeypatch)
    first = send(c, '현재 압연 속도는 얼마야?', p['id'])
    send(c, '보증 기간은 얼마야?', cid=first['id'])
    assert '압연 속도' not in captured[-1][0]
    # Starting a new conversation never inherits the previous project's subject.
    fresh = send(c, '프로젝트 찾아줘')
    assert fresh['id'] != first['id']
    assert captured[-1][0] == '프로젝트 찾아줘'


def test_content_project_switch_survives_chat_memory(client,monkeypatch):
    from work.v3.test_questions_trash import project
    from work.v3 import chat_interpreter
    c,_=client;p,_,_=setup_chat(c,monkeypatch)
    other=project(c,'해든배터리 코팅라인')
    first=send(c,'현재 압연 속도는 얼마야?',p['id'])
    with w.connect() as db:
        prev=w.read(db,'ai_message',first['messages'][-1]['id']);actor=w.read(db,'person','team1')
        prev['context']['chat_memory']={'mode':'documents','project_ids':[p['id']]}
        context=conversations.resolve_question(w,db,actor,'해든은?',prev)
        monkeypatch.setattr(question_policy,'quick_answer',lambda *a,**kw:None)
        assert context['project_ids']==[other['id']] and '압연 속도' in context['query']
        assert not chat_interpreter.needs_interpreter(w,db,actor,'해든은?',context,prev)
        changed=conversations.resolve_question(w,db,actor,'아니 해든 교반 속도는 얼마야?',prev)
        assert '교반' in changed['query'] and '압연' not in changed['query']


def test_unbound_equipment_reference_asks_instead_of_guessing(client):
    from work.v3.test_questions_trash import project
    c,_=client;project(c,'해든 설비');project(c,'한솔 설비')
    thread=send(c,'이 설비 출고는 언제야?')
    result=thread['messages'][-1]['result']
    assert result['kind']=='clarification' and len(result['projects'])==2


def test_metadata_result_to_content_uses_one_project_and_new_field(client,monkeypatch):
    from work.v3.test_questions_trash import project
    from work.v3 import chat_interpreter
    c,_=client;a=project(c,'해든배터리 혼합기');project(c,'한솔 코팅라인')
    prev={'state':'done','question':'프로젝트 보여줘','context':{'query':'프로젝트 보여줘','project_ids':[a['id']],'subject':''},
          'job':{'result':{'kind':'projects','mode':'project_list','projects':[{'id':a['id'],'name':a['name']}],'result_project_ids':[a['id']]}}}
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        monkeypatch.setattr(question_policy,'quick_answer',lambda *a,**kw:None)
        for q in ('거기 납품일은?','그쪽 재질도 알려줘','교육은?'):
            context=conversations.resolve_question(w,db,actor,q,prev)
            assert context['project_ids']==[a['id']],context
            assert not chat_interpreter.needs_interpreter(w,db,actor,q,context,prev)
        prev['job']['result']['projects'].append({'id':'inaccessible','name':'이전 결과'})
        context=conversations.resolve_question(w,db,actor,'거기 납품일은?',prev)
        assert context.get('clarify'), 'Multiple results must not silently pick one'


def test_private_history_and_delete_only_chat_records(client, monkeypatch):
    c, _ = client
    p, _, _ = setup_chat(c, monkeypatch)
    first = send(c, '현재 압연 속도는 얼마야?', p['id'])
    with w.connect() as db:
        before = [(row['kind'], row['id'], row['payload']) for row in db.execute("SELECT * FROM records WHERE kind NOT IN ('ai_conversation','ai_message') ORDER BY kind,id")]
    c.post('/api/demo-login', json={'username': 'team2'})
    assert c.get('/api/conversations/'+first['id']).status_code == 404
    assert c.delete('/api/conversations/'+first['id']).status_code == 404
    assert not any(x['id'] == first['id'] for x in c.get('/api/conversations').json()['items'])
    c.post('/api/demo-login', json={'username': 'team1'})
    assert c.delete('/api/conversations/'+first['id']).status_code == 200
    assert c.get('/api/conversations/'+first['id']).status_code == 404
    with w.connect() as db:
        after = [(row['kind'], row['id'], row['payload']) for row in db.execute("SELECT * FROM records WHERE kind NOT IN ('ai_conversation','ai_message') ORDER BY kind,id")]
        assert not any(m['conversation_id'] == first['id'] for m in w.all_records(db, 'ai_message'))
    assert after == before


def test_source_retains_exact_revision_and_checks_access(client, monkeypatch):
    c, _ = client
    p, meeting_record, _ = setup_chat(c, monkeypatch)
    first = send(c, '현재 압연 속도는 얼마야?', p['id'])
    message = first['messages'][0]
    url='/api/conversations/'+first['id']+'/messages/'+message['id']+'/sources/S1'
    with questions.LOCK:
        questions.JOBS.clear()
    proof = c.get(url)
    assert proof.status_code == 200, proof.text
    assert proof.json()['highlight']
    assert any('135 m/min' in row['text'] for row in proof.json()['lines'])
    with w.connect() as db:
        m=w.read(db,'meeting',meeting_record['id'])
        m['revision']+=1
        m['revisions'].append({**m['revisions'][-1],'number':m['revision'],'body':'새 본문으로 변경됨'})
        w.save(db,'meeting',m)
    assert c.get(url).json()['revision'] == 1, 'Prior answers keep their original source revision'
    c.post('/api/demo-login', json={'username':'team2'})
    assert c.get(url).status_code == 404
    c.post('/api/demo-login', json={'username':'team1'})
    with w.connect() as db:
        record=w.read(db,'project',p['id']);record['members']=[];w.save(db,'project',record)
    assert c.get(url).status_code == 403
    assert 'result' not in c.get('/api/conversations/'+first['id']).json()['messages'][0]


def test_pending_delete_blocked_and_restart_recovers_failure(client, monkeypatch):
    c, _ = client
    p, _, _ = setup_chat(c, monkeypatch)
    monkeypatch.setattr(question_policy,'quick_answer',lambda *args:None)
    monkeypatch.setattr(conversations,'watch',lambda *args:None)
    class Queue:
        def submit(self,*args):pass
    monkeypatch.setattr(questions,'POOL',Queue())
    first=send(c,'압연 속도 변경 경위는?',p['id'])
    assert first['messages'][0]['state']=='queued'
    assert c.delete('/api/conversations/'+first['id']).status_code==409
    with questions.LOCK:questions.JOBS.clear()
    recovered=c.get('/api/conversations/'+first['id']).json()
    assert recovered['messages'][0]['state']=='failed'
    assert '재시작' in recovered['messages'][0]['error']
    assert c.delete('/api/conversations/'+first['id']).status_code==200


def test_unknown_followup_requests_clarification(client, monkeypatch):
    c,_=client
    p,_,captured=setup_chat(c,monkeypatch)
    first=send(c,'프로젝트 찾아줘',p['id'])
    count=len(captured)
    second=send(c,'그건 왜 바뀐 거야?',cid=first['id'])
    assert len(captured)==count
    assert second['messages'][-1]['result']['kind']=='clarification'
    assert '어떤 항목' in second['messages'][-1]['result']['message']


def test_rename_persists_without_reordering_or_changing_messages(client, monkeypatch):
    c,_=client;p,_,_=setup_chat(c,monkeypatch)
    first=send(c,'현재 압연 속도는 얼마야?',p['id'])
    other=send(c,'현재 압연 속도는 얼마야?',p['id'])
    before_order=[t['id'] for t in c.get('/api/conversations').json()['items']]
    with w.connect() as db:
        before_rows=[tuple(row) for row in db.execute("SELECT kind,id,payload FROM records WHERE kind!='ai_conversation' ORDER BY kind,id")]
        activity=w.read(db,'ai_conversation',first['id'])['activity']
    response=c.patch('/api/conversations/'+first['id'],json={'title':'  롤프레스   속도 확인  '})
    assert response.status_code==200 and response.json()['title']=='롤프레스 속도 확인'
    restored=c.get('/api/conversations/'+first['id']).json()
    assert restored['title']=='롤프레스 속도 확인' and restored['messages']==first['messages']
    assert restored['updated_at']==first['updated_at']
    assert [t['id'] for t in c.get('/api/conversations').json()['items']]==before_order
    with w.connect() as db:
        assert w.read(db,'ai_conversation',first['id'])['activity']==activity
        assert [tuple(row) for row in db.execute("SELECT kind,id,payload FROM records WHERE kind!='ai_conversation' ORDER BY kind,id")]==before_rows
    followed=send(c,'왜 바뀐 거야?',cid=first['id'])
    assert followed['title']=='롤프레스 속도 확인' and len(followed['messages'])==2
    assert c.get('/api/conversations/'+other['id']).json()['title']==other['title']


def test_rename_ownership_and_empty_or_long_title(client, monkeypatch):
    c,_=client;p,_,_=setup_chat(c,monkeypatch)
    first=send(c,'현재 압연 속도는 얼마야?',p['id']);url='/api/conversations/'+first['id']
    for value in ('','   ','가'*61):
        assert c.patch(url,json={'title':value}).status_code==422
    assert c.patch(url,json={'title':'허용 이름','user_id':'team2'}).status_code==422
    c.post('/api/demo-login',json={'username':'team2'})
    assert c.patch(url,json={'title':'다른 사람의 대화 변경'}).status_code==404
    c.post('/api/demo-login',json={'username':'team1'})
    assert c.get(url).json()['title']==first['title']
    assert c.patch(url,json={'title':'가'*60}).status_code==200
