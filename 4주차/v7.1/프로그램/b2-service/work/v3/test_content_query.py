"""Equivalent wording shares evidence; different attributes remain distinct."""
import pytest
from work.v3.test_connected import client,w
from work.v3.test_questions_trash import project,meeting
from work.v3.content_query import prepare
from work.v3.question_scope import plan_question,in_scope
from work.v3.answer_meaning import validate_meaning,unsupported_decision
from work.v17 import questions,retrieval
from work.v17.evidence_text import topic_terms


@pytest.mark.parametrize('question,expected',[
    ('그건 누가 해?',[]),
    ('언제까지야?',[]),
    ('언제부터인가요?',[]),
    ('그 일은 끝났어?',[]),
    ('그 업무는 완료됐어?',[]),
    ('해당 작업은 언제까지야?',[]),
    ('그린 센서 일정은?',['그린','센서','일정']),
    ('그건 냉각수 유량은 얼마야?',['냉각수','유량']),
    ('회의록에 기록된 센서 교정에 대해, 그건 누가 해?',['센서','교정']),
])
def test_reference_and_question_words_are_not_evidence_topics(question,expected):
    assert topic_terms(question)==expected


@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(w,'DB',tmp_path/'content.sqlite3')
    monkeypatch.setattr(w,'FILES',tmp_path/'files')
    monkeypatch.setattr(questions,'JOBS',{})
    class Inline:
        def submit(self,fn,*args):fn(*args)
    monkeypatch.setattr(questions,'POOL',Inline())
    monkeypatch.setattr(retrieval,'embed',lambda texts,prefix:[[1.,0.] for _ in texts])


def ask(c,q,**kw):
    r=c.post('/api/questions',json={'question':q,**kw});assert r.status_code==202,r.text
    r=c.get('/api/questions/'+r.json()['id']);assert r.json()['state']=='done',r.text
    return r.json()


@pytest.mark.parametrize('reason', [
    '현장 반입 일정이 확정돼 장비 납품일을 2026-12-23으로 변경했다.',
    '차량을 확보하지 못해 장비 납품일을 2026-12-23으로 변경했다.',
])
def test_reason_lookup_keeps_an_original_cause_and_excludes_date_only_records(client, monkeypatch, reason):
    from work.v3 import chat_model
    c, _ = client
    target = project(c, '푸른소재 포장설비')
    other = project(c, '은하 전극 조립라인')
    hidden = project(c, '비공개 설비', members=['team1'])
    meeting(c, target, '운송차량을 확보하지 못해 납품일 변경 요청을 보류했다.', '2026-11-10')
    meeting(c, target, reason + '\n검사 장비가 고장 나서 시운전을 미뤘다.', '2026-11-12')
    meeting(c, other, '장비 납품일은 2026-12-30으로 합의했다.')
    meeting(c, hidden, '비용이 증가해 장비 납품일을 2027-01-15로 변경했다.')
    c.post('/api/demo-login', json={'username':'team2'})
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL', '1')

    def choose_reason(_w, request):
        sentences = request.payload['sentences']
        assert [s['text'] for s in sentences] == [reason.rstrip('.')]
        return {'support':'direct', 'evidence':[sentences[0]['id']]}

    monkeypatch.setattr(chat_model, 'complete', choose_reason)
    monkeypatch.setattr(questions, 'generate', lambda *a, **kw: pytest.fail('Reason lookup must return original evidence'))
    response = c.post('/api/conversations/questions', json={'question':'회의록에서 납기가 왜 바뀌었는지 찾아줘'})
    assert response.status_code == 202
    thread = response.json()
    message = thread['messages'][-1]
    result = message['result']
    assert result['answer_mode'] == 'source_quote' and result['answerable']
    assert {s['project_id'] for s in result['sources']} == {target['id']}
    assert [p['project_id'] for p in result['points']] == [target['id']]
    sid = result['sources'][0]['id']
    proof = c.get(f"/api/conversations/{thread['id']}/messages/{message['id']}/sources/{sid}")
    assert proof.status_code == 200
    payload = proof.json()
    assert [row['text'] for row in payload['lines'] if row['id'] in payload['highlight']] == [reason]


def test_reason_lookup_reports_absent_reason_even_with_a_confirmed_date(client, monkeypatch):
    from work.v3 import chat_model
    c, _ = client
    target = project(c, '새빛 출하설비')
    meeting(c, target, '장비 납품일은 2026-12-30으로 변경하기로 합의했다.')
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL', '1')
    monkeypatch.setattr(chat_model, 'complete', lambda *a, **kw: pytest.fail('No causal text should reach selection'))
    monkeypatch.setattr(questions, 'generate', lambda *a, **kw: pytest.fail('Do not infer causes from dates'))
    found = ask(c, '납기 변경 사유는 뭐야?', project_id=target['id'])['result']
    assert not found['answerable'] and not found['sources']
    assert '이유를 명시한 문장' in found['message']


@pytest.mark.parametrize('assigned',[False,True])
def test_task_followups_keep_assignment_and_do_not_infer_completion(client,monkeypatch,assigned):
    from work.v3.test_questions_trash import event
    c,_=client;p=project(c,'새빛 계측설비')
    task=('센서 교정은 박하늘이 2026-12-03까지 진행할 예정이다.' if assigned
          else '센서 교정 담당자와 기한은 미정이다.')
    m=meeting(c,p,task+'\n배선 검토는 이지훈이 2026-12-09까지 진행할 예정이다.')
    e=event(m,'calibration','요청','교정 계획');e['title']='센서 교정'
    with w.connect() as db:w.save(db,'change_event',e)
    monkeypatch.setattr(questions,'generate',lambda *a,**kw:{'answerable':False,'points':[]})
    cid=None
    for q in ['센서 교정은 누가 해?','그건 누가 해?','언제까지야?','그 일은 끝났어?']:
        payload={'question':q,**({'conversation_id':cid} if cid else {'project_id':p['id']})}
        r=c.post('/api/conversations/questions',json=payload)
        assert r.status_code==202,r.text
        chat=r.json();cid=chat['id'];message=chat['messages'][-1]
        assert message['state']=='done',message
        with w.connect() as db:saved=w.read(db,'ai_message',message['id'])
        result=message['result'];text=' '.join(x['text'] for x in result['points'])
        assert result['answerable'] and '센서 교정' in text,(q,result,saved['context'],saved['job'].get('diagnostics'))
        assert '이지훈' not in text and '2026-12-09' not in text
        if assigned:assert '박하늘' in text and '2026-12-03' in text
        else:assert '미정' in text
        if q=='그 일은 끝났어?':assert '완료 사실을 확인하지 못했습니다' in text
        assert saved['context']['project_ids']==[p['id']]
        assert {s['meeting_id'] for s in saved['job']['result']['sources']}=={m['id']}


def test_model_content_meaning_preserves_query_and_scope(client,monkeypatch):
    from work.v3 import chat_model
    c,_=client;p=project(c,'다래소재 시험 설비')
    meeting(c,p,'열처리 압력은 2.5 kPa를 유지한다. 3.0 kPa 요청은 시험 자료가 없어 보류했다.','2026-10-03')
    meeting(c,p,'열처리 압력은 3.0 kPa로 변경 합의했다.','2026-10-12')
    other=project(c,'다른 설비');meeting(c,other,'열처리 압력은 9.0 kPa이다.')
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    def choose(w,request):
        assert '9.0' not in str(request.payload) and '변경 합의' not in str(request.payload)
        return {'terms':['열처리','압력을'],'purpose':'decision'}
    monkeypatch.setattr(chat_model,'complete',choose)
    def generate(w,q,sources,**kw):
        assert '결론 났어' in q
        assert all(s['project_id']==p['id'] and s['date']=='2026-10-03' for s in sources)
        assert all(s['query_scope']['operation']=='decision' and s['query_scope']['end']=='2026-10-05' for s in sources)
        return {'answerable':False,'points':[]}
    monkeypatch.setattr(questions,'generate',generate)
    job=ask(c,'10월 5일 기준 열처리 압력을 높이는 건 결론 났어?',project_id=p['id'])
    assert job['result']['answerable'] and '보류' in str(job['result']['points'])


@pytest.mark.parametrize('question',[
    '압력 상향 제안, 결말이 뭐야?',
    '센서 교정 담당자와 기한은?',
    '검토 결과 알려줘',
    '검토 결과와 시험 결과의 차이는?',
])
def test_single_topic_is_not_split_by_punctuation_or_requested_fields(monkeypatch,question):
    from work.v3 import chat_model
    from work.v3.content_query import split_targets
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    monkeypatch.setattr(chat_model,'complete',lambda *a,**kw:pytest.fail('No independent topic list'))
    assert split_targets(w,prepare(question,[{'name':'설비'}],[]),[]) is None


@pytest.mark.parametrize('last',[0,True,99,'3'])
def test_invalid_topic_choice_cannot_generate_a_partial_answer(monkeypatch,last):
    from work.v3 import chat_model
    from work.v3.content_query import split_targets
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    monkeypatch.setattr(chat_model,'complete',lambda *a,**kw:{'mode':'separate','last':last,'purpose':'responsibility'})
    content=prepare('배관 점검과 제어 도면 수정 업무를 각각 알려줘',[{'name':'설비'}],[])
    result=split_targets(w,content,[])
    assert result.get('message') and not result.get('targets')
    assert w.AI_LOCK.acquire(blocking=False)
    w.AI_LOCK.release()


@pytest.mark.parametrize('wording,first_topic,last_topic',[
    ('센서 교정과 내압 성적서 제출 업무를 각각 알려줘','센서 교정','내압 성적서 제출'),
    ('내압 성적서 제출, 센서 교정 업무를 각각 알려줘','내압 성적서 제출','센서 교정'),
])
@pytest.mark.parametrize('missing',[False,True])
def test_independent_tasks_preserve_all_targets_scope_and_original_assignment(client,monkeypatch,missing,wording,first_topic,last_topic):
    from work.v3 import chat_model
    c,_=client;p=project(c,'다래 설비')
    first='센서 교정 계획은 박하늘이 2026-10-12까지 작성한다.'
    second='내압 성적서 제출 담당자와 제출 기한은 미정이다.'
    m=meeting(c,p,first+('' if missing else '\n'+second),'2026-10-03')
    meeting(c,p,'내압 성적서 제출 담당자는 김서준이며 기한은 2026-10-20이다.','2026-10-12')
    other=project(c,'다른 설비');meeting(c,other,'내압 성적서 제출 담당자는 조서영이며 기한은 2026-10-07이다.','2026-10-03')
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    monkeypatch.setenv('B2_CHAT_EVIDENCE_FIRST','1')
    def complete(_w,request):
        if 'last_candidates' in request.payload:
            assert request.payload['first_topics']==[first_topic]
            choice=next(k for k,v in request.payload['last_candidates'].items() if v==last_topic)
            return {'mode':'separate','last':choice,'purpose':'responsibility'}
        assert '김서준' not in str(request.payload) and '조서영' not in str(request.payload)
        assert request.payload['time_scope']=={'mode':'as_of','start':None,'end':'2026-10-05'}
        target=first if '센서 교정' in request.payload['question'] else second
        rows=[r for r in request.payload['sentences'] if r['text'].rstrip('.')==target.rstrip('.')]
        return {'support':'direct' if rows else 'none','evidence':[r['id'] for r in rows]}
    monkeypatch.setattr(chat_model,'complete',complete)
    def generate(_w,q,sources,**kw):
        assert missing and '내압' in q  # Exact task records need no rephrasing.
        return {'answerable':False,'points':[]}
    monkeypatch.setattr(questions,'generate',generate)
    result=ask(c,'10월 5일 기준 '+wording,project_id=p['id'])['result']
    assert result['answerable'] and len(result['points'])==(1 if missing else 2)
    assert first in ' '.join(pt['text'] for pt in result['points'])
    if missing:
        assert [r['label'] for r in result['unanswered_targets']]==['내압 성적서 제출']
        assert '내압 성적서 제출' in result['notice']
    else:
        assert second in ' '.join(pt['text'] for pt in result['points']) and not result['unanswered_targets']
        assert result['points'][0]['text'].startswith(first_topic)
        assert result['points'][1]['text'].startswith(last_topic)
    assert {s['meeting_id'] for s in result['sources']}=={m['id']}
    assert all(pt['verification']=='source_quote' for pt in result['points'])


def test_third_unknown_task_remains_visible_in_partial_answer(client,monkeypatch):
    from work.v3 import chat_model
    c,_=client;p=project(c,'다래 설비')
    meeting(c,p,'센서 교정은 박하늘이 담당한다.\n내압 성적서 제출 담당자는 미정이다.')
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    def complete(_w,request):
        if 'last_candidates' in request.payload:
            assert request.payload['first_topics']==['센서 교정','내압 성적서 제출']
            choice=next(k for k,v in request.payload['last_candidates'].items() if v=='배관 누설 검사')
            return {'mode':'separate','last':choice,'purpose':'responsibility'}
        topic=request.payload['question'].split(' 회의록')[0]
        selected=[r['id'] for r in request.payload['sentences'] if topic in r['text']]
        return {'support':'direct' if selected else 'none','evidence':selected}
    monkeypatch.setattr(chat_model,'complete',complete)
    monkeypatch.setattr(questions,'generate',lambda *a,**kw:{'answerable':False,'points':[]})
    result=ask(c,'센서 교정과 내압 성적서 제출 및 배관 누설 검사 업무를 각각 알려줘',project_id=p['id'])['result']
    assert result['answerable'] and len(result['points'])==2
    assert [r['label'] for r in result['unanswered_targets']]==['배관 누설 검사']
    assert '배관 누설 검사' in result['notice']


def test_unknown_property_of_one_target_does_not_borrow_another_targets_value(client,monkeypatch):
    from work.v3 import chat_model
    c,_=client;p=project(c,'다래 설비')
    meeting(c,p,'배관 재질은 SUS304이다.\n센서 가격은 12만원이다.')
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    def complete(_w,request):
        if 'last_candidates' in request.payload:
            choice=next(k for k,v in request.payload['last_candidates'].items() if v=='센서 가격을')
            return {'mode':'separate','last':choice,'purpose':'content'}
        return {'support':'none','evidence':[]}
    monkeypatch.setattr(chat_model,'complete',complete)
    def generate(_w,q,sources,**kw):
        if '배관' in q:return {'answerable':False,'points':[]}
        return {'answerable':True,'points':[{'text':'센서 가격은 12만원이다.','sources':[sources[0]['id']]}]}
    monkeypatch.setattr(questions,'generate',generate)
    result=ask(c,'배관 가격과 센서 가격을 각각 알려줘',project_id=p['id'])['result']
    assert result['answerable'] and len(result['points'])==1
    assert result['points'][0]['text'].startswith('센서 가격')
    assert [r['label'] for r in result['unanswered_targets']]==['배관 가격']


@pytest.mark.parametrize('raw',[
    {'terms':['상상한 자료'],'purpose':'decision'},
    {'terms':[],'purpose':'unclear'},
    {'terms':['압력을'],'purpose':'decision','project_id':'다른 프로젝트'},
    {'terms':['압력을'],'purpose':'delete'},
])
def test_invalid_content_interpretation_keeps_existing_query(client,monkeypatch,raw):
    from work.v3 import chat_model
    from work.v3.content_query import interpret
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    monkeypatch.setattr(chat_model,'complete',lambda *a,**kw:raw)
    content=prepare('압력을 높이는 건 결론 났어?',[{'name':'장비'}],[])
    assert interpret(w,content,[])==content
    assert w.AI_LOCK.acquire(blocking=False)
    w.AI_LOCK.release()


def test_content_interpretation_failure_keeps_existing_query(client,monkeypatch):
    from work.v3 import chat_model
    from work.v3.content_query import interpret
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    def fail(*a,**kw):raise TimeoutError()
    monkeypatch.setattr(chat_model,'complete',fail)
    content=prepare('압력을 높이는 건 결론 났어?',[{'name':'장비'}],[])
    assert interpret(w,content,[])==content
    assert w.AI_LOCK.acquire(blocking=False)
    w.AI_LOCK.release()


def test_known_or_disabled_content_paths_do_not_call_model(client,monkeypatch):
    from work.v3 import chat_model
    from work.v3.content_query import interpret
    monkeypatch.setattr(chat_model,'complete',lambda *a,**kw:pytest.fail('Existing path needs no interpretation call'))
    monkeypatch.delenv('B2_CHAT_CONTENT_MODEL',raising=False)
    known=prepare('압력 변경은 합의됐어?',[{'name':'장비'}],[])
    assert interpret(w,known,[])==known
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','0')
    unknown=prepare('압력을 높이는 건 결론 났어?',[{'name':'장비'}],[])
    assert interpret(w,unknown,[])==unknown


def recovery_fixture():
    body='압력 변경 요청은 시험 자료가 없어 보류했다. 기존 압력 2.5 kPa를 유지한다.\n배선 도면은 장유진이 11월 18일까지 작성한다.'
    doc={'project_id':'p','meeting_id':'m','revision':1,'fingerprint':'f','date':'2026-11-05','body':body}
    source={**{k:v for k,v in doc.items() if k!='body'},'id':'S1','project_name':'시험 설비',
            'text':body,'line_ids':['L001','L002']}
    return doc,source


def test_dated_proposal_question_preserves_proposal_and_held_pressure():
    from work.v3.content_query import bind,early_evidence
    doc,source=recovery_fixture()
    proposed='고객은 시험 압력을 4.1 bar로 올리자고 제안했다.'
    held='시험 성적서가 없어 시험 압력 변경을 보류했다. 기존 3.7 bar를 유지한다.'
    doc['body']=proposed+'\n'+held
    project={'id':'p','name':'정렬 장비'}
    question='11월 5일 회의에서 시험 압력 올리자는 건 정해졌어?'
    content=prepare(question,[project],[doc])
    assert content['search_terms']==['시험','압력'] and content['operation']=='decision'
    source.update(text=doc['body'],query_scope=bind(plan_question(question,[doc]),content))
    point=early_evidence(w,content['question'],[source],[doc]).points[0]
    assert proposed in point['text'] and held in point['text']
    assert source['exact_highlights']==['L001','L002']
    assert source['query_scope']['evidence_topic_terms']==['시험','압력']


def test_as_of_value_includes_same_field_proposal_and_retention():
    from work.v3.content_query import bind, early_evidence, prepare
    from work.v3.question_scope import plan_question

    doc,source=recovery_fixture()
    proposal='고객사는 검사 온도 상한을 65 ℃로 올리는 방안을 제안했다.'
    outcome='검사 온도 상한 변경을 보류했다. 기존 60 ℃ 기준을 유지한다.'
    doc['body']=proposal+'\n'+outcome
    question='11월 12일 기준으로 보면 그 온도는 얼마였어?'
    scope=plan_question(question,[doc])
    content=prepare(question,[{'id':'p','name':'시험 설비'}],[doc])
    assert content['search_terms']==['온도']
    assert scope['mode']=='as_of' and scope['end']=='2026-11-12'
    source.update(text=doc['body'],query_scope=bind(scope,content))
    result=early_evidence(w,content['question'],[source],[doc])
    assert proposal in result.points[0]['text'] and outcome in result.points[0]['text']
    assert source['exact_highlights']==['L001','L002']


@pytest.mark.parametrize('latest_line', [
    '고객은 팬 속도를 다음 회의에서 다시 논의하자고 제안했다.',
    '고객은 팬 속도는 기존 1600 rpm을 유지하기로 제안했다.',
])
def test_latest_value_requires_confirmed_retention_in_the_latest_record(latest_line):
    from work.v3.content_query import bind, early_evidence, prepare

    doc,source=recovery_fixture()
    retained='팬 속도는 기존 1600 rpm을 유지한다.'
    doc['body']=retained
    newer={**doc,'meeting_id':'m2','date':'2026-11-06','body':latest_line}
    content=prepare('팬 속도는 얼마였고 최신 기록에서 바뀌었어?',
                    [{'id':'p','name':'시험 설비'}],[doc,newer])
    source.update(text=retained,line_ids=['L001'],query_scope=bind({'mode':'current'},content))
    assert not early_evidence(w,content['question'],[source],[doc,newer]).points
    latest_source={**source,'id':'S2','meeting_id':'m2','date':newer['date'],'text':latest_line}
    assert not early_evidence(w,content['question'],[source,latest_source],[doc,newer]).points


@pytest.mark.parametrize('operation',['content','decision','reason'])
def test_unrelated_source_cannot_become_a_quote_for_an_unknown_property(monkeypatch,operation):
    from work.v3.content_query import early_evidence,recover_evidence
    from work.v3 import chat_model
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    doc,source=recovery_fixture()
    source['query_scope']={'mode':'current','operation':operation,'search_terms':['토크']}
    monkeypatch.setattr(chat_model,'complete',lambda *a,**kw:pytest.fail('No source supports the requested property'))
    assert not early_evidence(w,'토크는 얼마야?',[source],[doc]).points
    assert recover_evidence(w,'토크는 얼마야?',[source],[doc])==[]


@pytest.mark.parametrize('wording', ['75도로 올리는 건 왜 보류했어?', '75 °C로 변경하려는 안은 왜 보류했어?'])
def test_degree_change_reason_matches_the_same_value_and_keeps_the_causal_record(monkeypatch,wording):
    from work.v3.content_query import bind,prepare,recover_evidence
    from work.v3 import chat_model
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    doc,source = recovery_fixture()
    target = '시험 온도 75 ℃ 적용은 내열 시험 결과가 나오지 않아 보류했다.'
    distractor = '시험 온도 175 ℃ 적용은 가열 장비를 확보하지 못해 보류했다.'
    doc['body'] = '\n'.join([distractor,target])
    content = prepare(wording,[{'name':'계측기 시제품','id':'p'}],[doc])
    assert content['search_terms']==['75도']
    source.update(text=doc['body'],line_ids=['L001','L002'],query_scope=bind({'mode':'current'},content))

    def select(_w,request):
        assert [row['text'] for row in request.payload['sentences']]==[target.rstrip('.')]
        return {'support':'direct','evidence':['E1']}

    monkeypatch.setattr(chat_model,'complete',select)
    points = recover_evidence(w,wording,[source],[doc])
    assert target in points[0]['text'] and distractor not in points[0]['text']
    assert source['exact_highlights']==['L002']


def test_measurement_hold_question_keeps_amount_and_unit():
    from work.v3.content_query import prepare,explicit_measurement_reason,HOLD_REQUEST
    from work.v17.evidence_text import coverage
    q='왜 680 mm로 바꾸는 걸 멈춘 거야?'
    content=prepare(q,[{'name':'분리막 코터','id':'p'}],[])
    assert explicit_measurement_reason(q) and HOLD_REQUEST.search(q)
    assert content['search_terms']==['680mm']
    assert coverage('680 mm 적용은 보류했다.',content['search_terms'])==1
    assert coverage('1680 mm 적용은 보류했다.',content['search_terms'])==0
    assert coverage('680 kg으로 맞췄다.',content['search_terms'])==0


@pytest.mark.parametrize('question', [
    '누설 시험 제안은 언제 이후였어?',
    '누설 시험을 언제 하자고 제안했어?',
])
def test_proposed_timing_quotes_work_record_instead_of_meeting_date(monkeypatch, question):
    from work.v3 import chat_model
    from work.v3.content_query import bind, early_evidence, prepare

    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    doc,source=recovery_fixture()
    plan='누설 시험은 12월 초에 하자고 제안했다.'
    doc['body']=plan+'\n절연 시험은 11월에 끝냈다.'
    content=prepare(question,[{'name':'한결공정 설비','id':'p'}],[doc])
    assert content['operation']=='proposal'
    assert content['question']==question
    source.update(text=doc['body'],query_scope=bind({'mode':'current'},content))

    def select(_w,request):
        assert [row['text'] for row in request.payload['sentences']]==[plan.rstrip('.')]
        return {'support':'direct','evidence':['E1']}

    monkeypatch.setattr(chat_model,'complete',select)
    result=early_evidence(w,question,[source],[doc])
    assert result.points[0]['verification']=='source_quote'
    assert plan in result.points[0]['text'] and source['exact_highlights']==['L001']


@pytest.mark.parametrize('operation,question', [
    ('decision','검사 온도는 얼마로 합의됐어?'),
    ('content','검사 온도는 얼마였어?'),
])
def test_decision_fallback_prefers_explicit_hold_and_retained_value_over_request(operation,question):
    from work.v3.answer_meaning import validate_meaning
    scope = {'mode':'current','operation':operation,'search_terms':['검사','온도']}
    agreed = '검사 온도는 42 ℃로 합의했다.'
    request = '검사 온도를 45 ℃로 올려 달라고 요청했다. 추가 시험이 필요하다.'
    outcome = '검사 온도 45 ℃ 적용은 보류했다. 기존 42 ℃를 유지한다.'
    sources = [
        {'id':'S1','date':'2026-08-01','project_id':'p','text':agreed,'query_scope':scope},
        {'id':'S2','date':'2026-08-02','project_id':'p','text':request+'\n'+outcome,'query_scope':scope},
    ]
    answer = {'text':agreed,'sources':['S1'],'project_id':'p'}
    points = validate_meaning([answer],sources,question)
    assert points[0]['verification']=='source_quote'
    assert outcome in points[0]['text'] and request not in points[0]['text']


def test_decision_evidence_keeps_wrapped_outcome_and_excludes_request_only_lines(monkeypatch):
    from work.v3.content_query import recover_evidence
    from work.v3 import chat_model
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    doc,source=recovery_fixture()
    original = [
        '고객은 시험 압력을 3.0 kPa로 높여 달라고',
        '요청했다.',
        '시험 압력 3.0 kPa 요청은 보류했다. 기존 시험 압력은',
        '2.5 kPa를 유지한다.',
        '배선 도면은 11월 18일에 확정했다.',
    ]
    doc['body']='\n'.join(original)
    source.update(text='\n'.join(original[i] for i in (0,2,4)),
                  line_ids=['L001','L003','L005'],query_scope={'operation':'decision','search_terms':['시험','압력']})
    outcome='\n'.join(original[2:4])
    def select(_w,request):
        assert [row['text'] for row in request.payload['sentences']]==[outcome]
        return {'support':'direct','evidence':['E1']}
    monkeypatch.setattr(chat_model,'complete',select)
    points=recover_evidence(w,'시험 압력 3.0 kPa로 확정됐어?',[source],[doc])
    assert outcome in points[0]['text']
    assert source['exact_highlights']==['L003','L004']
    assert 'L004' in source['line_ids']


@pytest.mark.parametrize('same_topic',[True,False])
def test_hold_reason_pairs_a_discussion_obstacle_only_with_the_same_topics_decision(monkeypatch,same_topic):
    from work.v3.content_query import recover_evidence
    from work.v3 import chat_model
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    doc,source=recovery_fixture()
    obstacle='시험 압력 3.0 kPa를 제안했으나 내압 성적서가 없다.'
    item='시험 압력' if same_topic else '배관 온도'
    decision=f'{item} 변경 요청은 보류했다.'
    doc['body']='\n'.join([obstacle,'결정 사항',decision])
    source.update(text=obstacle,line_ids=['L001'],
                  query_scope={'operation':'reason','search_terms':['시험','압력']})
    def select(_w,request):
        assert same_topic
        assert request.payload['sentences']==[
            {'id':'E1','date':doc['date'],'text':obstacle[:-1],'hold_decision':decision}]
        return {'support':'direct','evidence':['E1']}
    monkeypatch.setattr(chat_model,'complete',select)
    points=recover_evidence(w,'시험 압력은 왜 보류했지?',[source],[doc])
    if same_topic:
        assert all(f'“{line}”' in points[0]['text'] for line in (obstacle,decision))
        assert source['exact_highlights']==['L001','L003']
    else:
        assert points==[] and 'exact_highlights' not in source


def test_semantic_recovery_returns_original_line_and_keeps_qualification(monkeypatch):
    from work.v3.content_query import recover_evidence
    from work.v3 import chat_model
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    doc,source=recovery_fixture()
    def select(_w,request):
        assert request.payload['question']=='압력 상향안의 결말은?'
        sentence=next(row for row in request.payload['sentences'] if '보류' in row['text'])
        return {'support':'direct','evidence':[sentence['id'],sentence['id']]}
    monkeypatch.setattr(chat_model,'complete',select)
    points=recover_evidence(w,'압력 상향안의 결말은?',[source],[doc])
    assert len(points)==1 and points[0]['sources']==['S1']
    assert doc['body'].splitlines()[0] in points[0]['text']
    assert points[0]['text'].count('보류')==1 and '장유진' not in points[0]['text']
    assert source['exact_highlights']==['L001']
    assert w.AI_LOCK.acquire(blocking=False)
    w.AI_LOCK.release()


@pytest.mark.parametrize('raw',[
    {'support':'none','evidence':[]},
    {'support':'direct','evidence':[]},
    {'support':'direct','evidence':['E999']},
    {'support':'direct','evidence':['E1'],'text':'승인되었다'},
    {'support':'maybe','evidence':['E1']},
    {'support':'direct','evidence':[1]},
])
def test_semantic_recovery_rejects_abstention_invalid_ids_and_generated_prose(monkeypatch,raw):
    from work.v3.content_query import recover_evidence
    from work.v3 import chat_model
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    monkeypatch.setattr(chat_model,'complete',lambda *a,**kw:raw)
    doc,source=recovery_fixture()
    assert recover_evidence(w,'압력 상향안의 결말은?',[source],[doc])==[]
    assert 'exact_highlights' not in source
    assert w.AI_LOCK.acquire(blocking=False)
    w.AI_LOCK.release()


@pytest.mark.parametrize('mismatch',['project_id','meeting_id','revision','fingerprint'])
def test_recovery_cannot_quote_another_document_or_revision(monkeypatch,mismatch):
    from work.v3.content_query import recover_evidence
    from work.v3 import chat_model
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    monkeypatch.setattr(chat_model,'complete',lambda *a,**kw:pytest.fail('No eligible source'))
    doc,source=recovery_fixture();doc[mismatch]='other'
    assert recover_evidence(w,'압력 변경은?',[source],[doc])==[]


def test_recovery_does_not_quote_partial_lines_or_mix_projects(monkeypatch):
    from work.v3.content_query import recover_evidence
    from work.v3 import chat_model
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    monkeypatch.setattr(chat_model,'complete',lambda *a,**kw:pytest.fail('No eligible source'))
    doc,source=recovery_fixture()
    source['text']='압력 변경 요청은 시험 자료가 없어 보류했다.'
    assert recover_evidence(w,'압력 변경은?',[source],[doc])==[]
    doc,source=recovery_fixture()
    assert recover_evidence(w,'압력 변경은?',[source,{**source,'project_id':'other'}],[doc])==[]
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','0')
    assert recover_evidence(w,'압력 변경은?',[source],[doc])==[]


def test_recovery_timeout_keeps_abstention_and_releases_lock(monkeypatch):
    from work.v3.content_query import recover_evidence
    from work.v3 import chat_model
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    def fail(*a,**kw):raise TimeoutError()
    monkeypatch.setattr(chat_model,'complete',fail)
    doc,source=recovery_fixture()
    assert recover_evidence(w,'압력 변경은?',[source],[doc])==[]
    assert w.AI_LOCK.acquire(blocking=False)
    w.AI_LOCK.release()


def test_recovery_does_not_truncate_later_qualifications_to_fit_budget(monkeypatch):
    from work.v3.content_query import recover_evidence
    from work.v3 import chat_model
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    monkeypatch.setattr(chat_model,'complete',lambda *a,**kw:pytest.fail('Oversized context must abstain'))
    doc,source=recovery_fixture()
    text='\n'.join(['압력 변경을 검토했다.']*40+['압력 변경 요청은 철회했다.'])
    doc['body']=source['text']=text
    source['line_ids']=['L'+str(i+1).zfill(3) for i in range(41)]
    assert recover_evidence(w,'압력 변경은?',[source],[doc])==[]


def test_history_fallback_quotes_the_recorded_decision_instead_of_discussion_progress():
    scope={'mode':'history','operation':'history','search_terms':['커버']}
    initial='점검 커버 개폐 방식은 여닫이로 합의했다.'
    pending='점검 커버 개폐 방식 변경 요청은 보류했다.'
    decision='점검 커버 개폐 방식을 측면 슬라이드로 변경하기로 합의했다.'
    sources=[
        {'id':'S1','date':'2026-10-03','text':initial,'query_scope':scope,'project_id':'p'},
        {'id':'S2','date':'2026-10-05','text':pending,'query_scope':scope,'project_id':'p'},
        {'id':'S3','date':'2026-10-10','text':'점검 커버 변경 보류를 해소했다.\n'+decision,
         'query_scope':scope,'project_id':'p'},
    ]
    points=validate_meaning([],sources,'개폐 방식 관련 논의가 있었어?')
    assert points[0]['sources']==['S1','S2','S3']
    assert all(f'“{line}”' in points[0]['text'] for line in (initial,pending,decision))
    assert '보류를 해소했다' not in points[0]['text']


def test_supported_answer_does_not_add_a_recovery_model_call(client,monkeypatch):
    from work.v3 import chat_model
    c,_=client;p=project(c)
    meeting(c,p,'시험 압력은 2.5 kPa이다.')
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    calls=[]
    def interpret(_w,request):
        calls.append(request)
        assert 'terms' in request.schema['properties']
        return {'terms':['시험','압력은'],'purpose':'content'}
    monkeypatch.setattr(chat_model,'complete',interpret)
    monkeypatch.setattr(questions,'generate',lambda _w,q,ss,**kw:{'answerable':True,'points':[
        {'text':'시험 압력은 2.5 kPa이다.','sources':[ss[0]['id']]}]})
    result=ask(c,'시험 압력은 얼마야?',project_id=p['id'])['result']
    assert result['answer_mode']=='grounded_summary' and len(calls)==1


@pytest.mark.parametrize('early',[False,True])
@pytest.mark.parametrize('interpretation_timeout',[False,True])
def test_recovery_api_preserves_scope_and_opens_selected_original_line(client,monkeypatch,early,interpretation_timeout):
    from work.v3 import chat_model
    c,_=client;p=project(c,'다래소재 시험 설비')
    original='3.0 kPa 변경 요청은 내압 성적서가 없어 보류했다. 기존 압력 2.5 kPa를 유지한다.'
    m=meeting(c,p,'압력 기준은 2.5 kPa이다.\n'+original+'\n배선 도면은 장유진이 작성한다.','2026-10-03')
    meeting(c,p,'압력 3.0 kPa 변경은 승인되었다.','2026-10-12')
    hidden=project(c,'비공개 설비',members=['team1']);meeting(c,hidden,'압력 9.0 kPa는 승인되었다.')
    c.post('/api/demo-login',json={'username':'team2'})
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    monkeypatch.setenv('B2_CHAT_EVIDENCE_FIRST','1' if early else '0')
    calls=[]
    def complete(_w,request):
        calls.append(request)
        assert '9.0' not in str(request.payload) and '승인되었다' not in str(request.payload)
        if 'terms' in request.schema['properties']:
            if interpretation_timeout:raise TimeoutError()
            return {'terms':['압력을','상향하자는','제안'],'purpose':'decision'}
        row=next(r for r in request.payload['sentences'] if '보류' in r['text'])
        return {'support':'direct','evidence':[row['id']]}
    monkeypatch.setattr(chat_model,'complete',complete)
    # Invalid model prose is not reused as evidence by the recovery path.
    def generate(_w,q,ss,**kw):
        if early:pytest.fail('Confirmed original evidence needs no prose generation')
        return {'answerable':True,'points':[{'text':'압력 999 kPa 변경은 승인되었다.','sources':[ss[0]['id']]}]}
    monkeypatch.setattr(questions,'generate',generate)
    job=ask(c,'10월 5일 기준 압력을 상향하자는 제안, 결말이 뭐야?',project_id=p['id'])
    result=job['result'];assert result['answerable'] and result['answer_mode']=='source_quote'
    assert len(calls)==2 and original in result['points'][0]['text'] and '999' not in str(result['points'])
    assert {s['meeting_id'] for s in result['sources']}=={m['id']}
    # A generic follow-up retains the topic despite the failed interpretation.
    with questions.LOCK:
        scoped=questions.JOBS[job['id']]['result']['sources'][0]['query_scope']
    assert scoped['evidence_topic_terms']==['압력을']
    from work.v3.conversations import resolve_question
    previous={'state':'done','question':'압력을 상향하자는 제안, 결말이 뭐야?',
        'context':{'query':'압력을 상향하자는 제안, 결말이 뭐야?','project_ids':[p['id']],'project_id':p['id']},
        'job':questions.JOBS[job['id']]}
    with w.connect() as db:
        from work.v3 import chat_interpreter as language
        actor=w.read(db,'person','team2')
        pending=resolve_question(w,db,actor,'왜 보류된 거야?',previous)
        assert pending['topic_followup']['subject']=='압력'
        context,followup_result=language.execute(w,db,actor,'왜 보류된 거야?',
            language.Plan(action='search',scope='previous',topic_words=[]).model_dump(),previous)
        assert followup_result is None
    assert not context.get('clarify') and context['subject']=='압력' and '왜 보류' in context['query']
    proof=c.get('/api/questions/'+job['id']+'/sources/'+result['sources'][0]['id']).json()
    assert [l['text'] for l in proof['lines'] if l['id'] in proof['highlight']]==[original]


@pytest.mark.parametrize('mode,operation,terms,meaning,enabled',[
    ('history','history',['모르는말'],True,True),
    ('current','completion',['모르는말'],True,True),
    ('meeting','content',['모르는말'],True,True),
    ('current','content',['압력'],True,True),
    ('current','content',[],False,True),
    ('current','content',['모르는말'],True,False),
])
def test_early_evidence_keeps_other_answer_routes(monkeypatch,mode,operation,terms,meaning,enabled):
    from work.v3.content_query import early_evidence
    from work.v3 import chat_model
    doc,source=recovery_fixture()
    source['query_scope']={'mode':mode,'operation':operation,'search_terms':terms,'content_meaning':{'terms':terms} if meaning else None}
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    monkeypatch.setenv('B2_CHAT_EVIDENCE_FIRST','1' if enabled else '0')
    monkeypatch.setattr(chat_model,'complete',lambda *a,**kw:pytest.fail('Keep the existing synthesis route'))
    result=early_evidence(w,'압력 변경은?',[source],[doc])
    assert not result.points and not result.attempted


@pytest.mark.parametrize('selection_failure',['none','timeout','invalid'])
@pytest.mark.parametrize('generation_supported',[False,True])
def test_early_selection_failure_still_generates_without_repeating_selection(client,monkeypatch,selection_failure,generation_supported):
    from work.v3 import chat_model
    c,_=client;p=project(c)
    text='압력 변경 요청은 시험 자료가 없어 보류했다. 기존 압력 2.5 kPa를 유지한다.'
    meeting(c,p,text)
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1')
    monkeypatch.setenv('B2_CHAT_EVIDENCE_FIRST','1')
    calls=[]
    def complete(_w,request):
        if 'terms' in request.schema['properties']:
            calls.append('interpret')
            return {'terms':['압력을','상향하자는','제안'],'purpose':'decision'}
        calls.append('evidence')
        if selection_failure=='timeout':raise TimeoutError()
        if selection_failure=='invalid':return {'support':'direct','evidence':['E999']}
        return {'support':'none','evidence':[]}
    def generate(_w,q,ss,**kw):
        calls.append('generate')
        return {'answerable':generation_supported,'points':[{'text':text,'sources':[ss[0]['id']]}] if generation_supported else []}
    monkeypatch.setattr(chat_model,'complete',complete)
    monkeypatch.setattr(questions,'generate',generate)
    result=ask(c,'압력을 상향하자는 제안, 결말이 뭐야?',project_id=p['id'])['result']
    assert calls==['interpret','evidence','generate']
    assert result['answerable']==generation_supported


@pytest.mark.parametrize('wording',['담당이랑 기한은?','누가 언제까지 준비해?','담당자하고 기한 알려줘'])
def test_role_words_do_not_hide_later_subject_evidence(client,monkeypatch,wording):
    c,_=client;p=project(c,'열처리 검사장비')
    old=meeting(c,p,'열처리 검토 보고서는 김가람이 2026-11-08까지 작성한다.','2026-11-01')
    latest=meeting(c,p,'열처리 검토 보고서는 이도현이 2026-11-15까지 작성한다.\n배선 도면 담당자는 정유나이며 기한은 2026-11-18이다.','2026-11-05')
    def generate(_w,q,sources,**kwargs):
        later=next(s for s in sources if s['meeting_id']==latest['id'])
        assert '이도현' in later['text']
        # A generated old assignment cannot bypass the later source record.
        prior=next(s for s in sources if s['meeting_id']==old['id'])
        return {'answerable':True,'points':[{'text':'김가람이 2026-11-08까지 작성한다.','sources':[prior['id']]}]}
    monkeypatch.setattr(questions,'generate',generate)
    result=ask(c,'열처리 검토 보고서 '+wording,project_id=p['id'])['result']
    assert result['answerable']
    text=' '.join(pt['text'] for pt in result['points'])
    assert '이도현' in text and '2026-11-15' in text and '김가람' not in text and '정유나' not in text
    assert {s['meeting_id'] for s in result['sources']}=={latest['id']}


def test_newer_unrelated_assignment_does_not_replace_requested_task(client,monkeypatch):
    c,_=client;p=project(c)
    wanted=meeting(c,p,'압력 시험 보고서는 한소영이 2026-11-12까지 작성한다.','2026-11-01')
    meeting(c,p,'배선 도면은 조민석이 2026-11-20까지 작성한다.','2026-11-10')
    monkeypatch.setattr(questions,'generate',lambda *a,**kw:{'answerable':False,'points':[]})
    result=ask(c,'압력 시험 보고서 담당자와 기한은?',project_id=p['id'])['result']
    assert result['answerable'] and result['sources'][0]['meeting_id']==wanted['id']
    assert '조민석' not in str(result['points'])


def test_same_day_assignment_conflict_is_not_silently_resolved():
    scope={'operation':'responsibility','mode':'current','search_terms':['검증','보고서']}
    sources=[{'id':'S1','project_id':'p','date':'2026-11-05','text':'검증 보고서는 김가람이 11월 12일까지 작성한다.','query_scope':scope},
             {'id':'S2','project_id':'p','date':'2026-11-05','text':'검증 보고서는 이도현이 11월 15일까지 작성한다.','query_scope':scope}]
    points=validate_meaning([],sources,'검증 보고서 담당은?')
    assert set(points[0]['sources'])=={'S1','S2'}
    assert '김가람' in points[0]['text'] and '이도현' in points[0]['text']


@pytest.mark.parametrize('wording',[
    '라인속도 변경상황 알려줘','라인 속도 변경 내용 알려줘',
    '운전 속도 변경내역 알려줘','생산속도 변동 내역 알려줘',
    '압연속도 어떻게 바뀌었어?','압연 속도 바뀐 내용 알려줘',
    '라인속도변경상황 알려줘',
])
def test_equivalent_wordings_share_topic_and_history(wording):
    ps=[{'id':'p','name':'한빛셀'}];docs=[{'body':'압연 속도: 120 m/min으로 합의했다.'}]
    result=prepare('한빛셀 '+wording,ps,docs)
    assert not result['message'] and result['history']
    assert '압연 속도' in result['question']
    assert topic_terms(result['question'])==['압연','속도']


def test_ambiguous_and_distinct_physical_quantities():
    ps=[{'name':'한빛셀'}]
    docs=[{'body':'압연 속도: 120 m/min\n이송 속도: 80 m/min\n회전 속도: 90 rpm'}]
    assert '어느 속도' in prepare('라인속도 변경상황 알려줘',ps,docs)['message']
    assert not prepare('압연속도 변경상황 알려줘',ps,docs)['message']
    one=[{'body':'압연 속도: 120 m/min'}]
    assert '회전 속도' in prepare('회전 속도 변경상황 알려줘',ps,one)['question']
    assert '이송 속도' in prepare('이송 속도 변경상황 알려줘',ps,one)['question']
    assert '라인속도' in prepare('라인속도 변경상황 알려줘',ps,[])['question']


def test_project_words_do_not_erase_recorded_property():
    ps=[{'name':'시점 검증 압연 설비','id':'p'}]
    result=prepare('11월 11일 기준 합의된 압연 속도는 얼마야?',ps,[{'body':'압연 속도는 120 m/min으로 합의했다.'}])
    assert '압연 속도' in result['question'] and '11월 11일' in result['question']
    assert not result['history']


def test_same_query_reaches_retrieval_generation_verification_and_source(client,monkeypatch):
    c,_=client;p=project(c)
    made=[meeting(c,p,text,date) for date,text in [
        ('2026-11-09','압연 속도: 기본 사양은 120 m/min으로 합의했다.'),
        ('2026-11-11','압연 속도: 135 m/min으로 변경을 요청했다. 아직 합의하지 않았다. 기존 120 m/min을 유지한다.'),
        ('2026-11-13','압연 속도: 135 m/min으로 변경 합의했다. 제작 완료를 의미하지 않는다.')]]
    def generate(w,q,sources,**kw):
        assert q=='압연 속도 변경 이력 알려줘'
        assert {s['meeting_id'] for s in sources}=={m['id'] for m in made}
        assert all(s['query_scope']['mode']=='history' for s in sources)
        return {'answerable':False,'points':[]}
    monkeypatch.setattr(questions,'generate',generate)
    job=ask(c,'한빛셀 라인속도 변경상황 알려줘');result=job['result']
    assert result['answerable'] and '압연 속도' in result['notice']
    text=' '.join(p['text'] for p in result['points'])
    assert all(x in text for x in ('2026-11-09','2026-11-11','2026-11-13','120','135','아직 합의하지','제작 완료를 의미하지'))
    for src in result['sources']:
        proof=c.get('/api/questions/'+job['id']+'/sources/'+src['id'])
        assert proof.status_code==200 and proof.json()['highlight']


def test_search_list_uses_same_scoped_terminology(client,monkeypatch):
    c,_=client;p=project(c);m=meeting(c,p,'압연 속도: 120 m/min으로 합의했다.')
    hidden=project(c,'기밀 설비',members=['team1']);meeting(c,hidden,'이송 속도: 80 m/min으로 합의했다.')
    removed=meeting(c,p,'이송 속도: 90 m/min으로 합의했다.','2026-11-02')
    with w.connect() as db:removed['deleted_at']=w.now();w.save(db,'meeting',removed)
    c.post('/api/demo-login',json={'username':'team2'})
    monkeypatch.setattr(questions,'generate',lambda *a,**kw:pytest.fail('Meeting lists need no model'))
    result=ask(c,'한빛셀 라인속도 논의한 회의록 찾아줘')['result']
    assert result['count']==1 and result['sources'][0]['meeting_id']==m['id']


def test_ambiguous_query_never_invokes_generation(client,monkeypatch):
    c,_=client;p=project(c)
    meeting(c,p,'압연 속도: 120 m/min\n이송 속도: 80 m/min')
    monkeypatch.setattr(questions,'generate',lambda *a,**kw:pytest.fail('Must clarify'))
    result=ask(c,'한빛셀 라인속도 변경상황 알려줘')['result']
    assert result['kind']=='clarification' and not result['answerable']


def test_explicit_unassigned_is_evidence_but_unrelated_unknown_is_not():
    sources=[{'id':'S1','project_id':'p','project_name':'시험','date':'2026-10-15',
        'text':'표면 검사 카메라 설치 공간 검토는 담당자와 기한을 정하지 않았다.'}]
    result=validate_meaning([],sources,'표면 검사 카메라 공간 검토는 누가 언제까지 하기로 했어?')
    assert result and '정하지 않았다' in result[0]['text']
    assert validate_meaning([],sources,'열매유 배관 교체 담당자는 누구야?')==[]
    assert validate_meaning([],sources,'계약 금액은 얼마야?')==[]


def test_meeting_date_not_mistaken_for_value_but_dates_cannot_borrow_later_approval():
    sources=[{'id':'S1','date':'2026-11-09','text':'압연 속도는 120 m/min으로 합의했다.'},
             {'id':'S2','date':'2026-11-11','text':'압연 속도 135 m/min을 요청했다. 합의하지 않았다.'},
             {'id':'S3','date':'2026-11-13','text':'압연 속도는 135 m/min으로 합의했다.'}]
    assert not unsupported_decision('2026-11-09: 압연 속도는 120 m/min으로 합의했다.',sources)
    assert not unsupported_decision('11월 13일 회의에서 압연 속도는 135 m/min으로 합의했다.',sources)
    assert unsupported_decision('2026-11-11: 압연 속도는 135 m/min으로 합의했다.',sources)
    assert unsupported_decision('2026-11-09: 압연 속도는 999 m/min으로 합의했다.',sources)
    assert unsupported_decision('2026-11-10: 압연 속도는 120 m/min으로 합의했다.',sources)


@pytest.mark.parametrize('stamp',['2026-10-12','2026년 10월 12일','10월 12일'])
@pytest.mark.parametrize('fact,earlier,later',[
    ('검사 주기는 0.6초로 변경되었으며','제품 한 개의 검사 주기는 0.8초로 합의했다.','검사 주기를 0.8초에서 0.6초로 변경하기로 합의했다.'),
    ('브래킷 재질은 티타늄으로 변경되었으며','브래킷 재질은 알루미늄으로 합의했다.','브래킷 재질을 티타늄으로 변경하기로 합의했다.'),
])
def test_inline_meeting_attribution_binds_the_fact_to_that_meeting(stamp,fact,earlier,later):
    sources=[{'id':'S1','date':'2026-10-05','text':earlier},
             {'id':'S2','date':'2026-10-12','text':later}]
    text=f'{fact}, 이는 {stamp}의 회의 기록에서 합의된 내용이다.'
    assert not unsupported_decision(text,sources)
    raw={'answerable':True,'points':[{'text':text,'sources':['S2']}]}
    points=questions.validate_answer(raw,sources)
    assert validate_meaning(points,sources)==points
    # A valid later source cannot backdate the same fact to an earlier meeting.
    earlier_stamp=stamp.replace('12','05')
    assert unsupported_decision(text.replace(stamp,earlier_stamp),sources)


@pytest.mark.parametrize('claim,source_text',[
    ('검사 주기는 9.9초로 변경되었으며','검사 주기를 0.6초로 변경하기로 합의했다.'),
    ('검사 주기는 0.6초로 변경되었으며','검사 주기 0.6초 변경을 요청했으나 합의하지 않았다.'),
    ('브래킷 재질은 티타늄으로 변경되었으며','브래킷 재질은 알루미늄으로 합의했다.'),
])
def test_inline_attribution_cannot_validate_wrong_values_or_unapproved_requests(claim,source_text):
    sources=[{'id':'S1','date':'2026-10-12','text':source_text}]
    assert unsupported_decision(claim+', 이는 2026-10-12의 회의 기록에서 합의된 내용이다.',sources)


def test_meeting_attribution_requires_a_unique_cited_date_and_keeps_delivery_values():
    text='검사 주기는 0.6초로 변경되었으며, 이는 10월 12일의 회의 기록에서 합의된 내용이다.'
    sources=[{'id':'S1','date':'2025-10-12','text':'검사 주기는 0.6초로 합의했다.'},
             {'id':'S2','date':'2026-10-12','text':'검사 주기는 0.8초로 합의했다.'}]
    assert unsupported_decision(text,sources)
    assert unsupported_decision(text.replace('10월 12일','10월 13일'),sources)
    # Delivery dates are facts, even when they coincide with a source date.
    sources=[{'id':'S1','date':'2026-12-18','text':'납품일을 2026-12-23으로 합의했다.'}]
    assert unsupported_decision('납품일을 2026-12-18로 합의했다.',sources)


@pytest.mark.parametrize('prefix',['10월 5일 기준 ','2026-10-05 기준으로 ', '2026.10.05 기준: ','10/5 기준 ', '10.5 기준 '])
def test_as_of_prefix_is_a_scope_not_an_invented_specification(prefix):
    sources=[{'id':'S1','date':'2026-10-03','text':'시험 압력은 2.5 kPa로 합의했다.',
              'query_scope':{'mode':'as_of','start':None,'end':'2026-10-05'}}]
    raw={'answerable':True,'points':[{'text':prefix+'시험 압력은 2.5 kPa로 합의했다.','sources':['S1']}]}
    points=questions.validate_answer(raw,sources)
    assert validate_meaning(points,sources,'10월 5일 기준 시험 압력은?')==points
    raw['points'][0]['text']=prefix+'시험 압력은 5 kPa로 합의했다.'
    with pytest.raises(ValueError):questions.validate_answer(raw,sources)


@pytest.mark.parametrize('prefix,scope,source_date',[
    ('10월 6일 기준 ',{'mode':'as_of','end':'2026-10-05'},'2026-10-03'),
    ('2025-10-05 기준 ',{'mode':'as_of','end':'2026-10-05'},'2026-10-03'),
    ('10월 5일 기준 ',{'mode':'current'},'2026-10-03'),
    ('10월 5일 기준 ',{'mode':'period','start':'2026-10-01','end':'2026-10-05'},'2026-10-03'),
    ('10월 5일 기준 ',{'mode':'as_of','end':'2026-10-05'},'2026-10-12'),
    ('10월 5일 회의에서 ',{'mode':'as_of','end':'2026-10-05'},'2026-10-03'),
    ('10월 5일 납품으로 ',{'mode':'as_of','end':'2026-10-05'},'2026-10-03'),
])
def test_as_of_scope_cannot_license_wrong_dates_or_later_evidence(prefix,scope,source_date):
    sources=[{'id':'S1','date':source_date,'text':'시험 압력은 2.5 kPa로 합의했다.','query_scope':scope}]
    with pytest.raises(ValueError):
        questions.validate_answer({'answerable':True,'points':[{'text':prefix+'시험 압력은 2.5 kPa로 합의했다.','sources':['S1']}]},sources)


def test_as_of_date_does_not_turn_a_request_into_an_agreement():
    sources=[{'id':'S1','date':'2026-10-03','text':'시험 압력 3.0 kPa를 요청했으나 승인하지 않았다. 기존 2.5 kPa를 유지한다.',
              'query_scope':{'mode':'as_of','end':'2026-10-05'}}]
    claim='10월 5일 기준 시험 압력은 3.0 kPa로 합의했다.'
    points=questions.validate_answer({'answerable':True,'points':[{'text':claim,'sources':['S1']}]},sources)
    assert unsupported_decision(claim,sources)
    result=validate_meaning(points,sources,'10월 5일 기준 시험 압력 합의 여부는?')
    assert all(p.get('verification')=='source_quote' and '승인하지 않았다' in p['text'] for p in result)


def test_evidence_selection_receives_cutoff_and_excludes_future_meeting(client,monkeypatch):
    from work.v3 import chat_model
    c,_=client;p=project(c,'다래 시험 장비')
    older=meeting(c,p,'압력 3.0 kPa 변경 요청은 내압 성적서가 없어 보류했다. 기존 압력 2.5 kPa를 유지한다.','2026-10-03')
    meeting(c,p,'시험 압력 3.0 kPa 변경은 승인되었다.','2026-10-12')
    monkeypatch.setenv('B2_CHAT_CONTENT_MODEL','1');monkeypatch.setenv('B2_CHAT_EVIDENCE_FIRST','1')
    calls=[]
    def complete(_w,request):
        calls.append(request)
        assert '승인되었다' not in str(request.payload)
        if 'terms' in request.schema['properties']:return {'terms':['압력을','상향하자는','제안'],'purpose':'decision'}
        assert request.payload['time_scope']=={'mode':'as_of','start':None,'end':'2026-10-05'}
        assert {row['date'] for row in request.payload['sentences']}=={'2026-10-03'}
        row=next(r for r in request.payload['sentences'] if '보류' in r['text'])
        return {'support':'direct','evidence':[row['id']]}
    monkeypatch.setattr(chat_model,'complete',complete)
    monkeypatch.setattr(questions,'generate',lambda *a,**kw:pytest.fail('Direct evidence needs no prose generation'))
    result=ask(c,'10월 5일 기준 압력을 상향하자는 제안, 결말이 뭐야?',project_id=p['id'])['result']
    assert result['answerable'] and result['answer_mode']=='source_quote' and len(calls)==2
    assert {s['meeting_id'] for s in result['sources']}=={older['id']}
    assert '보류' in result['points'][0]['text'] and '승인되었다' not in str(result)


def test_rotational_and_transfer_speed_cannot_borrow_rolling_speed():
    sources=[{'id':'S1','date':'2026-11-13','text':'압연 속도는 135 m/min으로 합의했다.'}]
    for subject in ('회전 속도','이송 속도'):
        assert validate_meaning([{'text':subject+'는 135 m/min입니다.','sources':['S1']}],sources,subject+'는 얼마야?')==[]


@pytest.mark.parametrize('value,unit',[('3.0','kPa'),('0.6','초'),('10.5','mm'),('11.13','MPa')])
def test_leading_decimal_specification_is_not_a_meeting_date(value,unit):
    from work.v3.answer_meaning import dated_claim
    text=f'{value} {unit} 변경은 승인되지 않았다.'
    sources=[{'id':'S1','date':'2026-10-05','text':text}]
    assert dated_claim(text,sources)==(text,None)
    assert not unsupported_decision(text,sources)
    supported=questions.validate_answer({'answerable':True,'points':[{'text':text,'sources':['S1']}]},sources)
    assert validate_meaning(supported,sources,'변경 승인 여부는?')==supported
    # Recognizing a decimal must not grant approval absent from the evidence.
    assert unsupported_decision(f'{value} {unit} 변경은 승인되었다.',sources)


@pytest.mark.parametrize('prefix',['11.11 회의에서','11.11일','11.11:','11/11:','2026.11.11:'])
def test_explicit_meeting_dates_still_cannot_borrow_later_decimal_approval(prefix):
    sources=[{'id':'S1','date':'2026-11-11','text':'압력 3.0 kPa 변경은 보류했다.'},
             {'id':'S2','date':'2026-11-13','text':'압력 3.0 kPa 변경은 승인되었다.'}]
    assert unsupported_decision(prefix+' 압력 3.0 kPa 변경은 승인되었다.',sources)
    assert not unsupported_decision(prefix.replace('11.11','11.13').replace('11/11','11/13')+' 압력 3.0 kPa 변경은 승인되었다.',sources)


@pytest.mark.parametrize('q',[
    '압연 속도는 얼마야?', '압연 속도가 얼마인가요?', '압연 속도는 얼마였지?',
    '압연 속도 135로 승인된 거야?', '압연 속도 승인됐어?',
])
def test_question_endings_and_numeric_particles_are_not_subject_terms(q):
    assert topic_terms(q)==['압연','속도']


def test_current_baseline_qualification_survives_wording(client):
    c,_=client;p=project(c)
    m=meeting(c,p,'압연 속도: 고객은 135 m/min으로 변경을 요청했다.\n현재 기준은 속도 120 m/min, 여닫이 커버다. 변경 요청을 승인하지 않았다.')
    docs=[retrieval.registered_document(m)]
    result=retrieval.retrieve(w,p['id'],docs,'압연 속도는 얼마야?')
    assert '현재 기준은 속도 120' in result[0]['text']
    quote=validate_meaning([],result,'속도 135로 승인된 거야?')
    assert quote and '승인하지 않았다' in quote[0]['text']


def test_historical_approval_question_excludes_later_approval():
    docs=[{'date':'2026-11-09'},{'date':'2026-11-11'},{'date':'2026-11-13'}]
    plan=plan_question('한빛셀 11월 11일에는 속도 135로 승인된 거야?',docs)
    assert plan['mode']=='as_of' and plan['end']=='2026-11-11'
    assert [d['date'] for d in docs if in_scope(d,plan)]==['2026-11-09','2026-11-11']
