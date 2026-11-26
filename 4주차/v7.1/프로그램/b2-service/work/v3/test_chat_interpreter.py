"""Test server execution independently from language-model accuracy."""
from copy import deepcopy
import threading
import pytest
from work.v3.test_connected import client,w
from work.v3.test_questions_trash import project,meeting,event
from work.v3.test_project_order import stamp
from work.v3 import chat_interpreter as language, chat_jobs
from work.v17 import questions


def plan(action,**kw):return language.Plan(action=action,**kw).model_dump()


def test_owner_followup_uses_general_interpreter_and_distinguishes_result_from_scope(monkeypatch):
    requests=[]
    def complete(_w,request):
        requests.append(request)
        assert 'action' in request.schema['properties']
        return {'action':'meeting_count','relation':'continue','unresolved':False}
    monkeypatch.setattr(language.chat_model,'complete',complete)
    result=language.infer(None,{'question':'그 프로젝트 회의 횟수를 알고 싶어',
        'selected_project':'화면에서 선택한 장비','named_projects':[],
        'topic_followup':{'subject':''},'previous':{'mode':'project_owner','query':'이 설비의 PM은?',
            'projects':['선택 결과 장비'],'scope_count':9,'person_count':1}})
    assert result['action']=='meeting_count' and result['topic_words'] is None
    assert len(requests)==1
    assert requests[0].payload['previous']['result_projects']==['선택 결과 장비']
    assert requests[0].payload['previous']['searched_project_count']==9
    assert requests[0].payload['selected_project']=='화면에서 선택한 장비'


def test_project_count_does_not_treat_registered_word_as_meeting_timestamp(client,plans):
    c,_=client;pending,used=plans
    project(c,'모래 검사장비');project(c,'구름 포장장비')
    t,_=answer(c,'현재 프로젝트 뭐 있어?')
    pending.append(plan('project_count',scope='previous',relation='continue'))
    _,r=answer(c,'등록된 건 전부 몇개지?',t['id'])
    assert len(used)==1 and r['mode']=='count' and r['count']==2


def test_unparsed_lookup_with_bad_date_still_does_not_invoke_model(client,plans):
    c,_=client;_,used=plans;a=project(c,'모래 검사장비');meeting(c,a)
    t,_=answer(c,'모래 11월 회의록 보여줘')
    _,r=answer(c,'그럼 13월에는 몇 번 모인 거야?',t['id'])
    assert not used and r['kind']=='clarification'


@pytest.mark.parametrize('template',[
    '{name}가 PM인 프로젝트는?', 'PM이 {name}인 프로젝트 보여줘',
    '{name} 담당 프로젝트 알려줘', '{name}님이 맡은 프로젝트는?',
])
def test_registered_pm_name_reaches_owner_query(client,plans,template):
    c,_=client;pending,used=plans
    a=project(c,'푸른식품 충전라인');b=project(c,'노을기계 절단장비')
    hidden=project(c,'비공개 포장라인',members=['team1'])
    with w.connect() as db:
        person=w.read(db,'person','team2');person['name']='문지호';w.save(db,'person',person)
        for p in (a,hidden):p['pm']='team2';w.save(db,'project',p)
    c.post('/api/demo-login',json={'username':'team2'})
    pending.append(plan('owner_projects',person='문지호'))
    _,r=answer(c,template.format(name='문지호'))
    assert r['kind']=='projects' and [p['id'] for p in r['projects']]==[a['id']]
    assert len(used)==1 and hidden['name'] not in str(used)


def test_pm_filter_does_not_expose_inaccessible_people(client):
    from work.v3.project_facts import owner_filter_people
    c,_=client;p=project(c,'비공개 설비',members=['team1'])
    with w.connect() as db:
        person=w.read(db,'person','team3');p['pm']=person['id'];w.save(db,'project',p)
        actor=w.read(db,'person','team2')
        assert owner_filter_people(w,db,language.available(w,db,actor),person['name']+'가 PM인 프로젝트는?')==[]


@pytest.mark.parametrize('mode,action,expected',[('meeting_lookup','','meetings'),('count','meeting_count','meeting_count')])
def test_bounded_replacement_keeps_server_operation(monkeypatch,mode,action,expected):
    calls=[]
    def decide(_w,system,payload,schema,max_tokens):
        calls.append(payload)
        return {'relation':'replace_project'}
    monkeypatch.setattr(language,'complete_json',decide)
    result=language.infer(None,{'question':'구름 장비를 뜻했어','named_projects':['구름 장비'],
        'previous':{'mode':mode,'action':action,'query':'모래 장비 7월 회의록 조회'}})
    assert result['action']==expected and result['relation']=='correct'
    assert result['projects']==[] and result['period']==''
    assert len(calls)==1 and calls[0]['matched_projects']==['구름 장비']


@pytest.mark.parametrize('opening,expected',[('2026년 7월 회의록 월별로 찾아줘','meeting_lookup'),('2026년 7월 회의록 몇 건이야?','count')])
def test_project_correction_preserves_lookup_slots(client,plans,opening,expected):
    c,_=client;pending,used=plans
    a=project(c,'모래 연구장비');b=project(c,'구름 검사장비')
    july=meeting(c,b,date='2026-07-04');meeting(c,b,date='2026-08-04')
    t,r=answer(c,a['name']+' '+opening)
    assert r['count']==0,r
    pending.append(plan('meetings',scope='named',relation='correct'))
    t,r=answer(c,'구름 검사장비를 말한 거였어',t['id'])
    assert r['mode']==expected and r['count']==1 and len(used)==1
    with w.connect() as db:
        ctx=w.read(db,'ai_message',t['messages'][-1]['id'])['context']
    assert ctx['time_scope']['start']=='2026-07-01'
    assert ctx['retrieval_plan']['project_ids']==[b['id']]
    assert ctx['retrieval_plan']['group_by']==('month' if expected=='meeting_lookup' else None)
    if expected=='meeting_lookup':assert {s['id'] for s in r['sources']}


def test_model_correction_cannot_discard_invalid_date(client,plans):
    c,_=client;project(c,'모래 연구장비');project(c,'구름 검사장비')
    t,_=answer(c,'모래 연구장비 7월 회의록 찾아줘')
    with w.connect() as db:
        old=w.read(db,'ai_message',t['messages'][-1]['id']);actor=w.read(db,'person','team1')
        _,r=language.execute(w,db,actor,'구름 13월을 말한 거였어',plan('meetings',relation='correct',scope='named'),old)
    assert r['kind']=='clarification' and not r.get('answerable')


@pytest.mark.parametrize('question', [
    '삭제된 회의록도 포함해서 보여줘',
    '회의에서 삭제한 요구사항은 뭐야?',
    '“프로젝트 삭제해줘”라는 요청이 나온 회의록을 찾아줘',
])
def test_management_guidance_does_not_intercept_read_questions(question):
    assert language.record_management_response(question) is None


def test_english_greeting_and_management_help_do_not_search(client,plans):
    c,_=client
    _,used=plans
    pr=project(c,'진행 중인 테스트 프로젝트')
    thread,_=answer(c,'안녕')
    _,translated=answer(c,'영어로 말해줘',thread['id'])
    assert translated['message'].startswith('Hello!')
    for q in ('프로젝트 삭제는 어떻게해?','프로젝트는 어떻게 삭제해?'):
        _,help_answer=answer(c,q,thread['id'])
        assert help_answer['mode']=='unsupported_action' and not help_answer['sources']
        assert all(fragment in help_answer['message'] for fragment in ('변경이력','프로젝트 삭제','PM'))
    _,translated=answer(c,'방금 답변을 영어로 다시 말해줘',thread['id'])
    assert 'Change History' in translated['message']
    assert not used
    with w.connect() as db:
        assert not w.read(db,'project',pr['id']).get('deleted_at')


def test_assignment_combines_explicit_owner_with_updated_deadline(client,plans):
    c,_=client
    _,used=plans
    p=project(c,'새한 포장 장비')
    meeting(c,p,'밀봉 검사표는 윤도하 대리가 2026년 9월 20일까지 제출하기로 했다.','2026-09-05')
    meeting(c,p,'밀봉 검사표 기한은 2026년 9월 27일로 변경했다. 교정 계획서 담당은 서하늘이며 기한은 2026년 9월 29일이다.','2026-09-16')
    _,result=answer(c,'새한 밀봉 검사표 담당자랑 기한 알려줘')
    assert result['mode']=='task_deadline' and len(result['sources'])==2
    assert '윤도하' in result['points'][0]['text']
    assert '9월 27일' in result['points'][1]['text']
    assert '서하늘' not in str(result['points']) and not used


def test_assignment_uses_promised_due_date_after_early_submission(client,plans):
    c,_=client
    _,used=plans
    p=project(c,'미래 자동 검사기')
    meeting(c,p,'김유하가 정렬 검사표를 2026-09-24까지 제출하기로 했다.','2026-09-12')
    meeting(c,p,'정렬 검사표는 2026-09-20에 제출했다.','2026-09-22')
    _,result=answer(c,'미래 정렬 검사표 담당이랑 제출 기한이 어떻게 돼?')
    assert result['mode']=='task_deadline'
    assert '김유하' in result['points'][0]['text'] and '2026-09-24' in result['points'][0]['text']
    assert [source['date'] for source in result['sources']]==['2026-09-12']
    assert not used


@pytest.mark.parametrize('revised_deadline',[False,True])
def test_submission_followup_compares_explicit_dates_for_the_same_task(client,plans,revised_deadline):
    c,_=client
    _,used=plans
    p=project(c,'단비 정렬 설비')
    meeting(c,p,'교정 성적서는 안해솔이 2026-09-24까지 제출하기로 했다.','2026-09-12')
    meeting(c,p,'교정 성적서는 실제로 2026-09-20에 제출했다. 배선 도면은 2026-09-26에 제출했다.','2026-09-22')
    if revised_deadline:
        meeting(c,p,'교정 성적서 제출 기한은 2026-09-26으로 변경했다.','2026-09-19')
    thread,due=answer(c,'단비 교정 성적서는 누가 언제까지 내기로 했어?')
    assert due['mode']=='task_deadline'
    thread,actual=answer(c,'실제로 낸 날은?',thread['id'])
    assert actual['mode']=='task_submission_date'
    assert '2026-09-20' in actual['points'][0]['text'] and '2026-09-26' not in actual['points'][0]['text']
    _,timing=answer(c,'그럼 하루 늦은 거야?',thread['id'])
    assert not used
    if revised_deadline:
        assert not timing['answerable']
    else:
        assert '4일 일찍' in timing['message']
        assert len(timing['sources'])==2


def test_implicit_person_deadline_reads_same_task_original(client,plans):
    c,_=client
    _,used=plans
    p=project(c,'바다팩 자동 포장 설비')
    meeting(c,p,'포장 검사표 담당자를 정하지 못했다.','2026-09-01')
    meeting(c,p,'포장 검사표 담당은 이새봄으로 정했고 기한은 2026년 10월 2일이다. 검교정표 담당은 오한별이며 기한은 2026년 10월 6일이다.','2026-09-15')
    thread,history=answer(c,'바다팩 포장 검사표 담당은 처음과 지금이 어떻게 달라졌어?')
    assert history['mode']=='task_owner_history' and len(history['sources'])==2
    thread,deadline=answer(c,'그 사람 기한만 다시 알려줘',thread['id'])
    assert deadline['mode']=='task_deadline' and len(deadline['sources'])==1
    assert '이새봄' in deadline['points'][0]['text'] and '10월 2일' in deadline['points'][0]['text']
    assert '10월 6일' not in deadline['points'][0]['text']
    m=thread['messages'][-1]
    proof=c.get(f"/api/conversations/{thread['id']}/messages/{m['id']}/sources/{deadline['sources'][0]['id']}")
    assert proof.status_code==200 and proof.json()['highlight']
    _,missing=answer(c,'그 사람 기한은?')
    assert missing['kind']=='clarification' and not used


def test_original_deadline_uses_previous_task_and_earlier_meeting(client,plans):
    c,_=client
    _,used=plans
    p=project(c,'별나래 시험 설비')
    initial=meeting(c,p,'교정 확인표는 한서진이 2026년 8월 12일까지 제출한다.','2026-08-03')
    meeting(c,p,'교정 확인표의 담당자는 한서진으로 유지하고, 제출 기한만 2026년 8월 21일로 연기한다.','2026-08-15')
    thread,current=answer(c,'별나래 교정 확인표는 누가 언제까지 내?')
    assert '8월 21일' in current['points'][0]['text']
    _,original=answer(c,'그 사람 제출일 원래 언제였어?',thread['id'])
    assert original['mode']=='task_deadline' and '8월 12일' in original['points'][0]['text']
    assert [s['date'] for s in original['sources']]==[initial['date']]
    assert not used


@pytest.mark.parametrize('noun',['자료','보고서','도면','시험','업무'])
def test_unmentioned_task_reference_does_not_invent_a_target(noun):
    previous={'question':'왜 보류했지?','job':{'result':{'points':[{'text':'온도 요청을 보류하고 기존 온도를 유지합니다.'}]}}}
    result=language.local_response(f'그 {noun}는 누가 언제까지 하기로 했어?',previous)
    assert result['kind']=='clarification' and not result['points']
    previous['job']['result']['points'][0]['text']=f'고객의 {noun} 확인이 필요합니다.'
    assert language.local_response(f'그 {noun}는 누가 언제까지 하기로 했어?',previous) is None


def test_unmentioned_reference_stops_before_model_lookup(client,plans):
    c,_=client;_,used=plans
    t,_=answer(c,'전체 프로젝트 보여줘')
    _,r=answer(c,'그 자료는 누가 언제까지 내기로 했어?',t['id'])
    assert r['kind']=='clarification' and '어떤 자료' in r['message'] and not used


def answer(c,q,cid=None):
    r=c.post('/api/conversations/questions',json={'question':q,'conversation_id':cid})
    assert r.status_code==202,r.text
    t=r.json();assert t['messages'][-1]['state']=='done',t
    return t,t['messages'][-1]['result']


@pytest.fixture
def plans(monkeypatch):
    pending=[];used=[]
    monkeypatch.setattr(questions,'JOBS',{})
    class Inline:
        def submit(self,f,*args):f(*args)
    monkeypatch.setattr(questions,'POOL',Inline())
    def infer(_,payload):
        used.append(deepcopy(payload));assert pending,'Unexpected model interpretation'
        return pending.pop(0)
    monkeypatch.setattr(language,'infer',infer)
    return pending,used


def test_general_chat_uses_only_general_history_and_keeps_workspace_lookup(client,plans,monkeypatch):
    from work.v3 import chat_model
    c,_=client
    monkeypatch.setenv('B2_CHAT_GENERAL','1')
    p=project(c,'새울 전극 검사 설비')
    meeting(c,p,'내부 검증코드는 ZETA31이다.','2026-09-10')
    requests=[]

    def complete(_w,request):
        return {'route':'general','query':''}

    def reply(_w,system,payload):
        requests.append(payload)
        assert 'ZETA31' not in str(payload)
        if payload['general_conversation']:
            assert payload['general_conversation'][-1]['question']=='왜 별은 반짝여?'
            return '대기를 지나온 별빛이 공기의 움직임에 따라 흔들려요.'
        return '별빛이 지구 대기를 지나면서 굴절되기 때문이에요.'

    monkeypatch.setattr(chat_model,'complete',complete)
    monkeypatch.setattr(chat_model,'reply',reply)
    thread,r=answer(c,'새울 회의록 목록 보여줘')
    assert r['mode']=='meeting_lookup'
    thread,r=answer(c,'왜 별은 반짝여?',thread['id'])
    assert r['mode']=='general_knowledge' and r['answerable'] and not r['sources']
    assert not requests[0]['general_conversation']
    thread,r=answer(c,'그걸 한 문장으로 다시 설명해줘',thread['id'])
    assert r['mode']=='general_knowledge' and r['answerable']
    _,r=answer(c,'새울 회의록 몇 건이야?',thread['id'])
    assert r['count']==1 and len(requests)==2


def test_general_coating_calculation_uses_public_material_and_keeps_its_origin(client,plans,monkeypatch):
    from work.v3 import chat_model, general_chat

    c,_=client
    monkeypatch.setenv('B2_CHAT_GENERAL','1')
    p=project(c,'청해소재 전극 코팅기')
    meeting(c,p,'코팅 폭은 650 mm로 합의했다.','2026-11-13')
    requests=[]

    def no_routing(*args):
        pytest.fail('An explicit calculation with a known public reference needs no lookup')

    def reply(_w,system,payload):
        requests.append((system,payload))
        assert '650 mm' not in system+str(payload)
        assert '560 mm' in payload['general_conversation'][-1]['answer']
        return 'The coating width is 560 mm.'

    monkeypatch.setattr(chat_model,'complete',no_routing)
    monkeypatch.setattr(chat_model,'reply',reply)
    thread,r=answer(c,'폭 600mm 필름을 양쪽 20mm씩 비우면 코팅 폭은?')
    assert r['mode']=='public_search' and not r['sources'] and r['public_sources'] and '560 mm' in r['message']
    _,translated=answer(c,'방금 답을 영어 한 문장으로 말해줘.',thread['id'])
    assert translated['public_sources']==r['public_sources']
    assert len(requests)==1
    assert '700 mm' in general_chat.coating_calculation('너비 780mm 기재의 왼쪽 30mm, 오른쪽 50mm를 비우면 도포 폭은?')
    assert '남지 않아요' in general_chat.coating_calculation('폭 20mm 필름을 양쪽 10mm씩 비우면 코팅 폭은?')
    assert not general_chat.coating_calculation('폭 20mm 필름을 양쪽에 총 10mm 비우면 코팅 폭은?')
    assert not general_chat.technical_references('우리 프로젝트 코팅 폭은 어떻게 정했어?')
    assert not general_chat.technical_references('코팅 폭은?')
    assert not general_chat.candidate('청해소재 코팅 폭은 어떻게 정해져?',[p],{},None,[])


def test_replying_to_general_calculation_with_project_selection_checks_access(client,plans,monkeypatch):
    from work.v3 import chat_model
    from work.v3.test_question_scope import change

    c,_=client
    monkeypatch.setenv('B2_CHAT_GENERAL','1')
    a=project(c,'청해소재 전극 코팅기')
    b=project(c,'하늬기공 시험 코팅기')
    hidden=project(c,'비공개 제어팀')
    with w.connect() as db:
        w.save(db,'project',{**hidden,'pm':'team2','members':['team2']})
    note=meeting(c,b,'코팅 폭은 420 mm로 합의했다.')
    change(note,'코팅 폭','420 mm')
    thread,r=answer(c,'너비 780mm 기재의 왼쪽 30mm, 오른쪽 50mm를 비우면 코팅 폭은?')
    assert '700 mm' in r['message']
    monkeypatch.setattr(chat_model,'reply',lambda *_:'The width is 700 mm.')
    answer(c,'방금 답을 영어 한 문장으로 말해줘.',thread['id'])
    followup='우리 설비는 얼마로 확정했어?'
    _,r=answer(c,followup,thread['id'])
    assert r['kind']=='clarification' and '코팅 폭' in r['message'] and not r['sources']
    assert {p['id'] for p in r['projects']}=={a['id'],b['id']}
    denied=c.post('/api/conversations/questions',json={'question':followup,'conversation_id':thread['id'],'project_id':hidden['id']})
    assert denied.status_code==403
    chosen=c.post('/api/conversations/questions',json={'question':followup,'conversation_id':thread['id'],'project_id':b['id']})
    assert chosen.status_code==202,chosen.text
    r=chosen.json()['messages'][-1]['result']
    assert [s['project_id'] for s in r['sources']]==[b['id']]
    assert '420 mm' in r['points'][0]['text'] and not r.get('public_sources')


def test_public_followup_distinguishes_named_and_omitted_values(client,plans,monkeypatch):
    from work.v3 import chat_model
    from work.v3.test_question_scope import change

    c,_=client
    monkeypatch.setenv('B2_CHAT_GENERAL','1')
    p=project(c,'연수소재 코팅 설비')
    note=meeting(c,p,'코팅 폭은 540 mm로 합의했다.\n기판 두께는 18 μm로 합의했다.')
    change(note,'코팅 폭','540 mm')
    other=project(c,'유리공정 시험 설비')
    hidden=project(c,'비공개 검사실')
    with w.connect() as db:
        w.save(db,'project',{**hidden,'pm':'team2','members':['team2']})
    monkeypatch.setattr(chat_model,'complete',lambda *_: {'route':'general','query':''})
    monkeypatch.setattr(chat_model,'reply',lambda *_: '코팅 폭은 기재 폭을, 두께는 공정 조건을 봅니다.')
    opening='일반적으로 코팅 폭과 두께는 어떤 기준으로 정해요?'

    thread,_=answer(c,opening)
    _,r=answer(c,'우리 프로젝트에서 코팅 폭은 얼마로 합의했어?',thread['id'])
    assert r['kind']=='clarification' and '코팅 폭 값을 어느 프로젝트에서' in r['message']
    assert {row['id'] for row in r['projects']}=={p['id'],other['id']}
    _,r=answer(c,'연수소재',thread['id'])
    assert '540 mm' in r['points'][0]['text'] and [s['project_id'] for s in r['sources']]==[p['id']]

    thread,_=answer(c,opening)
    _,r=answer(c,'그건 연수소재 프로젝트에서 얼마로 합의했어?',thread['id'])
    assert r['kind']=='clarification' and '코팅 폭, 두께' in r['message'] and not r['sources']
    _,r=answer(c,'코팅 폭이요',thread['id'])
    assert '540 mm' in r['points'][0]['text'] and [s['project_id'] for s in r['sources']]==[p['id']]


def test_record_followup_sends_only_public_topic_and_can_return_to_a_different_project(client,plans,monkeypatch):
    from work.v3 import chat_model
    from work.v3.test_question_scope import change

    c,_=client
    monkeypatch.setenv('B2_CHAT_GENERAL','1')
    a=project(c,'새결기전 전극 코팅기')
    b=project(c,'하람소재 시험 코팅기')
    for p,value in ((a,'647 mm'),(b,'429 mm')):
        note=meeting(c,p,f'코팅 폭은 {value}로 합의했다.\n내부 코드명은 새벽단추다.')
        change(note,'코팅 폭',value)
    thread,r=answer(c,'새결기전 코팅 폭은 얼마로 합의됐어?')
    assert '647 mm' in r['points'][0]['text']
    prompts=[]

    def reply(_w,system,payload):
        prompts.append(payload)
        for private in ('새결기전','새벽단추','647','429'):
            assert private not in system+str(payload)
        if payload['general_conversation']:
            assert '코팅 폭' in payload['general_conversation'][-1]['question']
            return 'The target coating width depends on the substrate width and edge margins.'
        assert payload['question']=='일반적으로 코팅 폭 어떻게 정해져?'
        return '코팅 한 줄의 목표 폭은 기재 전체 폭과 양쪽 여백으로 정해요.'

    monkeypatch.setattr(chat_model,'reply',reply)
    _,r=answer(c,'그건 일반적으로 어떻게 정해져?',thread['id'])
    assert r['mode']=='public_search' and not r['sources']
    _,r=answer(c,'방금 답을 영어 한 문장으로 말해줘.',thread['id'])
    assert len(prompts)==2 and r['public_sources'] and not r['sources']
    _,r=answer(c,'하람소재 장비는 얼마로 합의됐어?',thread['id'])
    assert '429 mm' in r['points'][0]['text']
    assert [s['project_id'] for s in r['sources']]==[b['id']]


def test_unresolved_public_explanation_cannot_fall_back_to_workspace(client,plans,monkeypatch):
    from work.v3 import chat_model
    from work.v3.test_question_scope import change

    c,_=client
    monkeypatch.setenv('B2_CHAT_GENERAL','1')
    p=project(c,'새솔 열처리 설비')
    change(meeting(c,p,'온도는 153 ℃로 합의했다.'),'온도','153 ℃')
    thread,r=answer(c,'새솔 온도는 얼마로 합의했어?')
    assert '153 ℃' in r['points'][0]['text']

    def classify(_w,request):
        assert request.payload['question']=='일반적으로 온도 어떻게 정해져?'
        return {'route':'workspace','query':''}

    monkeypatch.setattr(chat_model,'complete',classify)
    _,r=answer(c,'그건 일반적으로 어떻게 정해져?',thread['id'])
    assert r['mode']=='general_knowledge' and not r['answerable'] and not r['sources']


def test_public_question_shows_public_links_and_transmits_only_current_search_terms(client,plans,monkeypatch):
    from work.v3 import chat_model,general_chat
    c,_=client
    monkeypatch.setenv('B2_CHAT_GENERAL','1')
    monkeypatch.setenv('BRAVE_SEARCH_API_KEY','test-only')
    searches=[]

    def search(query,key):
        searches.append(query)
        assert key=='test-only'
        return [{'title':'공공 날씨 자료','text':'구미 기온 12도','url':'https://example.org/weather'}]

    def complete(_w,request):
        if 'public_records' in request.payload:
            assert request.payload['public_records'][0]['id']=='W1'
            return {'sources':['W1']}
        return {'route':'web','query':'오늘 구미 날씨'}

    monkeypatch.setattr(general_chat,'_web_search',search)
    monkeypatch.setattr(chat_model,'complete',complete)
    monkeypatch.setattr(chat_model,'reply',lambda *a:'공개 자료에 제시된 구미 기온은 12도예요.')
    _,r=answer(c,'오늘 구미 날씨 알려줘')
    assert r['mode']=='public_search' and r['answerable'] and not r['sources']
    assert r['public_sources']==[{'title':'공공 날씨 자료','url':'https://example.org/weather'}]
    assert searches==['오늘 구미 날씨']
    assert not general_chat.search_query('연락처 me@example.org를 인터넷에서 찾아줘','me')
    assert not general_chat.search_query('오늘 구미 날씨 알려줘','2027 구미 날씨')
    monkeypatch.delenv('BRAVE_SEARCH_API_KEY')
    _,r=answer(c,'오늘 구미 날씨 알려줘')
    assert r['mode']=='public_search' and not r['answerable'] and not r['public_sources']
    assert searches==['오늘 구미 날씨']


def test_pnt_company_question_uses_public_record_instead_of_attendee_mentions(client,plans,monkeypatch):
    from work.v3 import chat_model,general_chat
    c,_=client
    monkeypatch.setenv('B2_CHAT_GENERAL','1')
    p=project(c,'접착기 설치')
    meeting(c,p,'참석자: PNT 사내 명단','2026-09-10')

    monkeypatch.setattr(chat_model,'complete',lambda *a:pytest.fail('Read the public company record'))
    _,r=answer(c,'pnt 는 뭐하는 회사야?')
    assert r['mode']=='public_search' and r['answerable'] and not r['sources']
    assert r['public_sources'][0]['url']==general_chat.PNT_PUBLIC['url']
    assert '이차전지' in r['message'] and '사내 명단' not in r['message']


def test_reference_question_can_use_public_encyclopedia_without_a_search_key(client,plans,monkeypatch):
    from work.v3 import chat_model,general_chat
    c,_=client
    monkeypatch.setenv('B2_CHAT_GENERAL','1')
    monkeypatch.delenv('BRAVE_SEARCH_API_KEY',raising=False)
    searches=[]
    def encyclopedia(query):
        searches.append(query)
        return [{'title':'메아리','text':'소리가 표면에 반사되어 다시 들리는 현상',
                 'url':'https://ko.wikipedia.org/wiki/메아리'}]
    def complete(_w,request):
        if 'public_records' in request.payload:
            return {'sources':['W1']}
        assert 'general_conversation' not in request.payload
        return {'route':'reference','query':'소리가 울리는 이유'}
    monkeypatch.setattr(general_chat,'_encyclopedia_search',encyclopedia)
    monkeypatch.setattr(chat_model,'complete',complete)
    monkeypatch.setattr(chat_model,'reply',lambda *a:'표면에 반사된 소리가 다시 들리는 현상이에요.')
    _,r=answer(c,'소리는 왜 울려?')
    assert r['mode']=='public_search' and r['public_sources'][0]['title']=='메아리'
    assert searches==['소리 울림']
    assert not general_chat._reference_query('기밀 자료에서 소리는 왜 울린대?', '소리 메아리')


def test_public_restatement_keeps_its_verified_link_without_reclassification(client,plans,monkeypatch):
    from work.v3 import chat_model
    c,_=client
    monkeypatch.setenv('B2_CHAT_GENERAL','1')
    monkeypatch.setattr(chat_model,'complete',lambda *a:pytest.fail('Rephrasing does not require another search decision'))
    monkeypatch.setattr(chat_model,'reply',lambda *a:'PNT supplies equipment for electrode manufacturing.')
    thread,original=answer(c,'PNT는 어떤 회사야?')
    _,rewritten=answer(c,'그 설명을 영어 한 문장으로 바꿔줘',thread['id'])
    assert rewritten['message'].startswith('PNT supplies')
    assert rewritten['public_sources']==original['public_sources']


def test_mixed_question_keeps_workspace_and_public_proof_separate(client,plans,monkeypatch):
    from work.v3 import chat_model,general_chat
    from work.v3.test_question_scope import change
    c,_=client
    monkeypatch.setenv('B2_CHAT_GENERAL','1')
    p=project(c,'바다소재 코팅기')
    m=meeting(c,p,'코팅 폭 650 mm로 합의했다.','2026-11-09')
    change(m,'코팅 폭','650 mm')
    asked=[]
    def search(topic):
        asked.append(topic)
        return [{'title':'공개 코팅 자료','url':'https://example.org/coating','text':'코팅 폭은 적용 소재와 장비에 따라 다르다.'}]
    monkeypatch.setattr(general_chat,'_encyclopedia_search',search)
    monkeypatch.setattr(chat_model,'complete',lambda *a:{'sources':['W1']})
    monkeypatch.setattr(chat_model,'reply',lambda *a:'코팅 폭은 소재와 장비에 따라 달라져요.')
    thread,r=answer(c,'우리 바다소재 프로젝트의 코팅 폭과 일반적인 코팅 폭은 어떻게 달라?')
    assert r['mode']=='workspace_public_comparison' and r['comparison_complete']
    assert '650 mm' in r['points'][0]['text']
    assert r['comparison_public']=={'message':'코팅 폭은 소재와 장비에 따라 달라져요.',
                                   'sources':[{'title':'공개 코팅 자료','url':'https://example.org/coating'}]}
    assert asked==['코팅 폭']
    message=thread['messages'][-1]
    proof=c.get(f"/api/conversations/{thread['id']}/messages/{message['id']}/sources/{r['sources'][0]['id']}")
    assert proof.status_code==200 and proof.json()['meeting_id']==m['id']
    assert not general_chat.comparison('우리 바다소재 코팅 폭과 일반적인 바다소재 폭은 어떻게 달라?',[p])[1]
    assert general_chat.comparison('일반적인 코팅 폭과 우리 바다소재 프로젝트의 코팅 폭을 비교해줘',[p])[1]=='코팅 폭'
    with w.connect() as db:
        from work.v3 import conversations
        actor=w.read(db,'person','team1')
        previous=w.read(db,'ai_message',message['id'])
        question='그럼 90도로 올리는 건 왜 보류했어?'
        ctx=conversations.resolve_question(w,db,actor,question,previous)
        assert ctx['project_ids']==[p['id']] and not ctx.get('clarify')
        assert not language.needs_interpreter(w,db,actor,question,ctx,previous)


def test_model_shipment_intent_handles_a_paraphrase_and_elliptical_followup(client,plans,monkeypatch):
    c,_=client
    from work.v3.query_intent import relative_period
    last_year=relative_period('작년')['start'][:4]
    this_year=relative_period('올해')['start'][:4]
    visible=project(c,'다래 검사 장비')
    hidden=project(c,'비공개 장비',members=['team1'])
    quote=f'{last_year}년 12월 16일에 검사 장비 2대를 고객사로 출고했다.'
    for day, body in [
        ('01',quote),('02',quote),('03',f'{last_year}년 12월 20일에 검사 장비 3대를 출고할 예정이다.'),
        ('04',f'{this_year}년 1월 10일에 검사 장비 1대를 출고했다.'),
        ('05',f'{last_year}년 12월 20일에 포장 설비 5대를 출고했다.'),
        ('06',f'{last_year}년 12월 20일에 검사 장비 출고가 완료되지 않았다.'),
    ]:
        meeting(c,visible,body,f'{this_year}-02-{day}')
    meeting(c,hidden,f'{last_year}년 12월 22일에 검사 장비 9대를 출고했다.',f'{this_year}-02-07')
    c.post('/api/demo-login',json={'username':'team2'}).raise_for_status()
    monkeypatch.setenv('B2_CHAT_SHIPMENT_INTENT','1')
    requests=[]
    def classify(_w,request):
        requests.append(request.payload)
        assert set(request.schema['properties'])=={'intent','equipment'}
        return {'intent':'actual_equipment_shipments','equipment':'검사 장비' if len(requests)==1 else ''}
    monkeypatch.setattr(language.chat_model,'complete',classify)
    q='작년에 고객사로 넘긴 검사 장비는 몇 기야?'
    assert not language.policy.shipment_total_answer(q)
    thread,result=answer(c,q)
    assert result['mode']=='shipment_total_unavailable' and not result['answerable'] and 'count' not in result
    assert [p['text'] for p in result['points']]==[quote]
    assert len(result['sources'])==1 and result['sources'][0]['date'].startswith(this_year)
    assert '회의일 전체' in result['notice'] and '등록 회의록 6건' in result['notice']
    message=thread['messages'][-1]
    proof=c.get(f"/api/conversations/{thread['id']}/messages/{message['id']}/sources/{result['sources'][0]['id']}")
    assert proof.status_code==200
    assert quote in [line['text'] for line in proof.json()['lines'] if line['id'] in proof.json()['highlight']]
    _,result=answer(c,'그러면 올해는?',thread['id'])
    assert result['mode']=='shipment_total_unavailable' and not result['answerable']
    assert [p['text'] for p in result['points']]==[f'{this_year}년 1월 10일에 검사 장비 1대를 출고했다.']
    assert requests==[
        {'question':q,'prior_shipment_question':''},
        {'question':'그러면 올해는?','prior_shipment_question':q},
    ]
    _,result=answer(c,'프로젝트는 총 몇 개야?',thread['id'])
    assert result['mode']=='count' and result['count']==1
    assert len(requests)==2


@pytest.mark.parametrize('relation',['others','previous'])
def test_model_reference_chain_uses_records_and_excludes_hidden(client,plans,relation):
    c,_=client;pending,used=plans
    a=project(c,'세척기 교체');b=project(c,'저장탱크 증설');h=project(c,'비공개 설비',members=['team1'])
    stamp(a,'2026-01-02T09:00:00+09:00');stamp(b,'2026-01-01T09:00:00+09:00')
    with w.connect() as db:
        for p in (a,b,h):
            current=w.read(db,'project',p['id']);current['pm']='team2';w.save(db,'project',current)
    c.post('/api/demo-login',json={'username':'team2'})
    pending.append(plan('projects'))
    t,r=answer(c,'프로젝트 좀 알려줄래')
    assert [p['id'] for p in r['projects']]==[a['id'],b['id']]
    pending.append(plan('owner',scope='results',selection=2))
    t,r=answer(c,'두 번째 거 책임지는 사람은?',t['id'])
    assert r['result_project_ids']==[b['id']]
    pending.append(plan('owner_projects',scope=relation,person='last'))
    t,r=answer(c,'그 사람 다른 건도 맡아?',t['id'])
    assert [p['id'] for p in r['projects']]==[a['id']]
    assert all('비공개' not in str(p) for p in used)
    assert not pending


def test_smalltalk_preserves_last_business_query_without_model(client,plans):
    c,_=client;pending,used=plans
    p=project(c,'세척기 교체')
    t,first=answer(c,'전체 프로젝트 보여줘')
    assert first.get('mode')=='project_list',first
    t,r=answer(c,'고마워, 근데 넌 이름이 뭐야',t['id'])
    assert r['mode']=='social' and not used
    pending.append(plan('owner',scope='results',selection=1))
    _,r=answer(c,'아까 첫 번째 거 책임자는?',t['id'])
    assert r['result_project_ids']==[p['id']]


def test_pm_correction_and_meeting_count(client,plans):
    c,_=client;pending,used=plans
    a=project(c,'혼합기 개조');b=project(c,'저장탱크 증설');meeting(c,b);meeting(c,b,'다른 회의')
    t,first=answer(c,'혼합기 프로젝트 PM 알려줘')
    assert first.get('mode')=='project_owner',first
    pending.append(plan('owner',scope='named',projects=['탱크']))
    t,r=answer(c,'아 혼합기 말고 탱크',t['id'])
    assert r.get('result_project_ids')==[b['id']],r
    pending.append(plan('meeting_count',scope='previous'))
    _,r=answer(c,'회의는 몇 번 했어?',t['id'])
    assert r['count']==2


@pytest.mark.parametrize('raw,q',[
    (plan('projects',scope='named',projects=['다른이름']),'세척기 보여줘'),
    (plan('projects',scope='named',projects=['비공개']),'비공개 프로젝트 알려줘'),
    (plan('projects',unresolved='우리 팀'),'우리 팀 거만'),
    (plan('projects'),'완료된 프로젝트만'),
    (plan('owner',scope='results'),'거기 책임자는?'),
    (plan('owner_projects',person='last'),'그 사람이 맡은 건?'),
    (plan('meetings',period='2026년 7월'),'회의 알려줘'),
    (plan('owner',period='7월'),'7월 PM은?'),
])
def test_unresolved_or_invented_filters_never_broaden(client,raw,q):
    c,_=client;project(c,'세척기 교체')
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        _,r=language.execute(w,db,actor,q,raw)
    assert r['kind']=='clarification' and not r.get('answerable')


def test_person_negation_uses_current_pm_only(client):
    c,_=client;a=project(c,'세척기');b=project(c,'탱크')
    with w.connect() as db:
        a['pm']='team2';b['pm']='team3';w.save(db,'project',a);w.save(db,'project',b)
        actor=w.read(db,'person','team1');person=w.read(db,'person','team2')['name']
        _,r=language.execute(w,db,actor,person+'이 PM 아닌 프로젝트',plan('owner_projects',person=person,exclude_person=True))
    assert [p['id'] for p in r['projects']]==[b['id']]


def test_reference_permission_rechecked_after_model(client):
    c,_=client;p=project(c,'세척기',members=['team1','team2'])
    previous={'state':'done','context':{'project_ids':[p['id']]},'job':{'result':{'kind':'projects','mode':'project_list','projects':[p]}}}
    with w.connect() as db:
        p['members']=['team1'];w.save(db,'project',p);actor=w.read(db,'person','team2')
        _,r=language.execute(w,db,actor,'첫 번째 PM은?',plan('owner',scope='results',selection=1),previous)
    assert r['kind']=='clarification' and not r['projects']


def test_busy_gpu_keeps_the_question_pending_until_the_model_is_free(client,monkeypatch,plans):
    from concurrent.futures import ThreadPoolExecutor
    import time

    c,_=client;project(c,'세척기')
    pending,used=plans
    pending.append(plan('projects'))
    with ThreadPoolExecutor(max_workers=1) as pool:
        monkeypatch.setattr(questions,'POOL',pool)
        with w.AI_LOCK:
            response=c.post('/api/conversations/questions',json={'question':'프로젝트 좀 알려줄래'})
            assert response.status_code==202,response.text
            path='/api/conversations/'+response.json()['id']
            for _ in range(50):
                turn=c.get(path).json()['messages'][-1]
                if turn['state']=='waiting_model':break
                time.sleep(.02)
            assert turn['state']=='waiting_model' and not used
    final=c.get(path).json()['messages'][-1]
    assert final['id']==turn['id'] and final['state']=='done'
    assert final['result']['mode']=='project_list' and len(used)==1


def test_invalid_model_output_fails_closed(client,plans):
    c,_=client;project(c,'세척기');plans[0].append({'action':'delete_all'})
    _,r=answer(c,'프로젝트 좀 알려줄래')
    assert r['kind']=='clarification' and not r['projects']


def test_plan_schema_disallows_unknown_fields():
    with pytest.raises(ValueError):language.Plan(action='projects',sql='SELECT * FROM records')


def test_deleted_first_result_does_not_shift_ordinal_to_another_project(client):
    c,_=client;a=project(c,'세척기');b=project(c,'혼합기')
    previous={'state':'done','context':{'project_ids':[a['id'],b['id']]},'job':{'result':{
        'kind':'projects','mode':'project_list','projects':[a,b]}}}
    with w.connect() as db:
        a['deleted_at']=w.now();w.save(db,'project',a);actor=w.read(db,'person','team1')
        _,r=language.execute(w,db,actor,'첫 번째 책임자는?',plan('owner',scope='results',selection=1),previous)
    assert r['kind']=='clarification' and not r['projects']


def test_model_cannot_drop_explicit_project_name(client):
    c,_=client;a=project(c,'세척기 교체');b=project(c,'혼합기 개조');meeting(c,a);meeting(c,b)
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        _,r=language.execute(w,db,actor,'세척기 회의 몇 번 했어?',plan('meetings',scope='all'))
    assert r['mode']=='count' and r['count']==1 and r['result_project_ids']==[a['id']]


def test_registered_person_filter_survives_generic_project_action(client):
    c,_=client;a=project(c,'세척기 교체');b=project(c,'혼합기 개조')
    with w.connect() as db:
        a['pm']='team2';b['pm']='team3';w.save(db,'project',a);w.save(db,'project',b)
        actor=w.read(db,'person','team1');name=w.read(db,'person','team2')['name']
        _,r=language.execute(w,db,actor,name+' PM이 하는 프로젝트 다 알려줘',plan('projects',scope='previous'))
    assert [p['id'] for p in r['projects']]==[a['id']]


def test_latest_reference_keeps_meeting_entity_and_period(client):
    c,_=client;p=project(c,'세척기 교체')
    meeting(c,p,'회의 하나','2026-07-05');meeting(c,p,'회의 둘','2026-07-20');meeting(c,p,'회의 셋','2026-09-01')
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        ctx,r=language.execute(w,db,actor,'세척기 7월 회의 목록',plan('meetings',period='7월'))
        previous={'state':'done','context':ctx,'job':{'result':r}}
        _,r=language.execute(w,db,actor,'제일 최근 건 언제야?',plan('projects',scope='previous'),previous)
    assert r['mode']=='meeting_lookup' and len(r['sources'])==1
    assert r['sources'][0]['date']=='2026-07-20'


def test_pending_comparison_uses_counts_not_rag_or_guessed_scope(client):
    c,_=client;a=project(c,'세척기 교체');b=project(c,'혼합기 개조');meeting(c,b)
    previous={'state':'done','context':{},'job':{'result':{**language.clarification('비교 기준은?'),'pending_comparison':True}}}
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        _,r=language.execute(w,db,actor,'그럼 회의 수로',plan('meetings',scope='previous'),previous)
    assert r['mode']=='meeting_comparison' and r['result_project_ids']==[b['id']] and r['count']==1


def test_casual_reaction_never_swallows_information_request():
    assert language.social('두 개나 하네, 바쁘겠다')
    assert language.social('많네. 그럼 담당자 누구야?') is None
