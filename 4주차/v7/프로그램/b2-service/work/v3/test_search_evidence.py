"""Regressions for topic discovery, qualified evidence and recorded completion."""
import pytest
from work.v3.test_connected import client,w
from work.v3.test_questions_trash import project,meeting
from work.v3 import conversations
from work.v3.answer_meaning import validate_meaning, unsupported_decision
from work.v17 import questions,retrieval
from work.v17.evidence_text import META


def test_event_date_needs_its_own_exact_source():
    from work.v3.answer_meaning import unsupported_event_dates
    source={'date':'2026-09-24','text':'확인서 접수를 완료했다. 2026년 9월 24일에 성적서를 제출했다.'}
    assert unsupported_event_dates('확인서는 2026년 9월 24일에 접수를 완료했다.',[source])=={'접수'}
    assert unsupported_event_dates('확인서는 2026년 9월 24일 회의에서 접수를 완료했다.',[source])=={'접수'}
    assert not unsupported_event_dates('2026년 9월 24일 회의에서 접수가 완료되었다고 확인했다.',[source])
    source['text']='2026년 9월 18일에 확인서 접수를 완료했다.'
    assert not unsupported_event_dates('확인서는 2026-09-18에 접수했다.',[source],['확인서'])
    assert unsupported_event_dates('확인서는 2026-09-24 접수 완료.',[source],['확인서'])=={'접수'}


@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(w,'DB',tmp_path/'evidence.sqlite3')
    monkeypatch.setattr(w,'FILES',tmp_path/'files')
    monkeypatch.setattr(questions,'JOBS',{})
    class NoModel:
        def submit(self,*args):raise AssertionError('Record lookup must not invoke generation')
    monkeypatch.setattr(questions,'POOL',NoModel())


def ask(c,q,**kw):
    r=c.post('/api/questions',json={'question':q,**kw});assert r.status_code==202,r.text
    assert r.json()['state']=='done',r.text
    return r.json()


@pytest.mark.parametrize('query',[
    '베터리 슬리터 설비 몇대 나갔어?',
    '2026년에 출하된 배터리 슬리터 설비는 몇 대야?',
    '작년 장비 출고 대수 알려줘',
])
def test_shipment_totals_are_not_inferred_from_project_names(client,monkeypatch,query):
    from work.v3.test_conversations import send
    c,_=client
    p=project(c,'새빛 배터리 슬리터 3호기')
    meeting(c,p,'장비 납품일은 2026-12-23으로 합의했다.')
    monkeypatch.setattr('work.v3.chat_jobs.start',lambda *a,**kw:pytest.fail('No model needed for a missing ledger'))
    result=send(c,query)['messages'][-1]['result']
    assert result['mode']=='shipment_total_unavailable'
    assert not result['answerable'] and '실적 자료' in result['message']
    assert not result.get('projects') and not result['sources']
    assert ask(c,query)['result']['mode']==result['mode']


def test_selected_schedule_distinguishes_dispatch_shipment_and_delivery(client,monkeypatch):
    from work.v3.test_conversations import send
    from work.v3.test_question_scope import change
    c,_=client
    p=project(c,'새빛 포장라인');other=project(c,'해든 검사기')
    record=meeting(c,p,'출하일은 2026-11-27로 합의했다.','2026-11-19')
    change(record,'출하일','2026-11-27')
    delivery=meeting(c,other,'장비 납품일은 2026-12-23으로 합의했다.','2026-11-19')
    change(delivery,'장비 납품일','2026-12-23')
    monkeypatch.setattr('work.v3.chat_jobs.start',lambda *a,**kw:pytest.fail('Use the verified agreement'))
    prompt='이 설비 출고 언제야?'
    assert len(send(c,prompt)['messages'][-1]['result']['projects'])==2
    result=send(c,prompt,p=p['id'])['messages'][-1]['result']
    assert '출고일을 확인하지 못했어요' in result['message']
    assert not result['values']
    assert '출하일: 2026-11-27' in result['points'][0]['text']
    assert [s['project_id'] for s in result['sources']]==[p['id']]
    result=send(c,prompt,p=other['id'])['messages'][-1]['result']
    assert not result['answerable'] and not result['sources']
    result=send(c,'이 설비 납품일 언제야?',p=other['id'])['messages'][-1]['result']
    assert '2026-12-23' in result['points'][0]['text']
    assert [s['project_id'] for s in result['sources']]==[other['id']]
    dispatched=meeting(c,p,'출고일은 2026-11-25로 합의했다.','2026-11-20')
    change(dispatched,'출고일','2026-11-25')
    result=send(c,prompt,p=p['id'])['messages'][-1]['result']
    assert not result['message']
    assert '출고일: 2026-11-25' in result['points'][0]['text']
    assert [s['date'] for s in result['sources']]==['2026-11-20']


def test_topic_list_all_dates_not_first_document_and_no_generation(client):
    c,_=client;p=project(c)
    made=[meeting(c,p,'점검 커버는 여닫이 방식으로 합의했다.',f'2026-11-{d:02}') for d in (13,9,11)]
    meeting(c,p,'압연 속도는 120 m/min이다.','2026-11-15')
    q='한빛셀 점검 커버를 논의한 회의록 전부 찾아줘. 첫 회의부터 날짜순으로 보여줘.'
    with w.connect() as db:
        ctx=conversations.resolve_question(w,db,w.read(db,'person','team1'),q)
    assert not ctx['meeting_ids'] and not ctx.get('clarify')
    result=ask(c,q)['result']
    assert result['mode']=='meeting_search' and result['count']==3
    assert [s['date'] for s in result['sources']]==['2026-11-09','2026-11-11','2026-11-13']
    assert {s['meeting_id'] for s in result['sources']}=={m['id'] for m in made}
    assert '빠질 수' in result['notice']


def test_unassigned_fields_search_only_reads_joint_original_records(client, monkeypatch):
    from work.v3.test_conversations import send
    from work.v3 import chat_jobs
    c, _ = client
    a = project(c, '해든 자동화')
    b = project(c, '온새미 계측')
    private = project(c, '비공개 장비', members=['team1'])
    first = meeting(c, a, '배치 검토의 담당자와 기한을 정하지 못했다.', '2026-11-10')
    second = meeting(c, b, '센서 교정의 담당자와 검토 기한은\n미정이다.', '2026-11-11')
    meeting(c, a, '장비 반입 기한은 미정이다. 담당자는 김양일이다.', '2026-11-12')
    meeting(c, a, '담당자와 기한은 미정이 아니다. 부품 검토는 보류했다.', '2026-11-13')
    meeting(c, a, '후속 조치를 검토한다. 고객과 협의한다.', '2026-11-14')
    meeting(c, private, '검사 담당자와 기한은 미정이다.', '2026-11-15')
    c.post('/api/demo-login', json={'username':'team2'}).raise_for_status()
    monkeypatch.setattr(chat_jobs, 'start', lambda *a, **kw: pytest.fail('A joint field lookup needs no model'))

    thread = send(c, '담당자와 기한을 못 정한 사항들을 찾아줘.')
    message = thread['messages'][-1]
    result = message['result']
    assert result['mode'] == 'meeting_search' and result['count'] == 2
    assert '실제 처리 상태' in result['notice']
    assert [s['date'] for s in result['sources']] == [first['date'], second['date']]
    proof = c.get(f"/api/conversations/{thread['id']}/messages/{message['id']}/sources/{result['sources'][-1]['id']}")
    assert proof.status_code == 200
    data = proof.json()
    assert [l['text'] for l in data['lines'] if l['id'] in data['highlight']] == [
        '센서 교정의 담당자와 검토 기한은', '미정이다.']
    scoped = send(c, '기한과 담당자가 미정인 항목만 알려줘', p=a['id'])
    assert scoped['messages'][-1]['result']['count'] == 1
    dated = send(c, '2026-11-10 기준 담당자와 기한이 미정인 항목 보여줘')
    assert [s['date'] for s in dated['messages'][-1]['result']['sources']] == [first['date']]


def test_list_not_limited_to_generation_top_k_and_permissions(client):
    c,_=client;p=project(c);secret=project(c,'비공개',members=['team1'])
    for d in range(1,14):meeting(c,p,'점검 커버 개폐 검토',f'2026-11-{d:02}')
    hidden=meeting(c,secret,'점검 커버 개폐 검토')
    deleted=meeting(c,p,'점검 커버 개폐 검토','2026-11-20')
    with w.connect() as db:deleted['deleted_at']=w.now();w.save(db,'meeting',deleted)
    c.post('/api/demo-login',json={'username':'team2'})
    result=ask(c,'점검 커버 회의록 전부 찾아줘')['result']
    assert result['count']==13 and len(result['meetings'])==13
    assert hidden['id'] not in {s['meeting_id'] for s in result['sources']}
    filtered=ask(c,'2026-11-05부터 2026-11-08까지 점검 커버 회의록 찾아줘')['result']
    assert filtered['count']==4


@pytest.mark.parametrize('wording',[
    '한빛셀 사양서 개정이 끝났어?', '한빛셀 사양서 개정 완료됐어?',
    '한빛셀 사양서 개정을 마쳤어?', '한빛셀 사양서 개정 마무리됐어?',
])
def test_completion_never_invents_fact_from_negation(client,wording):
    c,_=client;p=project(c)
    meeting(c,p,'사양서를 개정해 고객에게 공유한다. 이번 합의는 자료 개정이 완료됐다는 뜻이 아니다.','2026-11-13')
    result=ask(c,wording)['result']
    assert result['mode']=='recorded_status'
    assert '완료 사실을 확인하지 못했습니다' in result['points'][0]['text']
    assert '뜻이 아니다' in result['points'][0]['text']


@pytest.mark.parametrize('body',[
    '사양서 개정을 11월 20일까지 완료한다.',
    '사양서 개정이 완료되면 고객에게 공유한다.',
    '사양서 개정 완료 여부를 확인한다.',
    '사양서 개정은 완료되지 않았다.',
])
def test_plan_condition_check_not_completion(client,body):
    c,_=client;p=project(c);meeting(c,p,body)
    text=ask(c,'한빛셀 사양서 개정이 끝났어?')['result']['points'][0]['text']
    assert '완료 사실을 확인하지 못했습니다' in text and body in text


def test_positive_partial_and_later_rework_preserved(client):
    c,_=client;p=project(c)
    first=meeting(c,p,'사양서 개정은 완료했다. 배치도 개정은 진행 중이다.','2026-11-13')
    text=ask(c,'한빛셀 사양서 개정이 끝났어?')['result']['points'][0]['text']
    assert '완료 표현이 있는 기록' in text and '배치도 개정은 진행 중' in text
    later=meeting(c,p,'사양서 오류를 발견해 재개정이 필요하다.','2026-11-20')
    result=ask(c,'한빛셀 사양서 개정이 끝났어?')['result']
    assert '재개정' in result['points'][0]['text'] and '완료 사실을 확인하지 못했습니다' in result['points'][0]['text']
    assert [s['meeting_id'] for s in result['sources']]==[later['id']]
    historical=ask(c,'한빛셀 2026년 11월 13일 기준 사양서 개정이 끝났어?')['result']
    assert [s['meeting_id'] for s in historical['sources']]==[first['id']]


def test_test_completion_followup_uses_the_earlier_verified_width(client,monkeypatch):
    from work.v3.test_question_scope import change
    c,_=client;p=project(c,'온새미 절단기')
    quote='윤지호는 2026-11-20부터 2026-11-24까지 절단 폭 160 mm의 반복 정밀도 시험을 진행한다.'
    m=meeting(c,p,'절단 폭은 160 mm로 합의했다.\n'+quote,'2026-11-18')
    change(m,'절단 폭','160 mm')
    meeting(c,p,'절단 폭 180 mm의 반복 정밀도 시험은 완료했다.','2026-11-25')
    meeting(c,p,'절단 폭 1160 mm의 반복 정밀도 시험은 완료했다.','2026-11-26')
    first=c.post('/api/conversations/questions',json={'question':'온새미 절단 폭은 현재 얼마야?'}).json()
    assert first['messages'][-1]['result']['mode']=='baseline'
    response=c.post('/api/conversations/questions',json={
        'conversation_id':first['id'],'question':'그 폭으로 반복 정밀도 시험도 이미 끝났어?',
    })
    assert response.status_code==202,response.text
    result=response.json()['messages'][-1]['result']
    assert result['mode']=='recorded_status'
    assert '완료 사실을 확인하지 못했습니다' in result['points'][0]['text']
    assert quote in result['points'][0]['text']
    assert {s['date'] for s in result['sources']}=={'2026-11-18'}


def test_fallback_never_substitutes_delivery_for_cover():
    sources=[{'id':'S1','date':'2026-11-13','text':'납품일은 12월 18일로 합의했다. 점검 커버는 슬라이드 요청을 철회했다.'}]
    out=validate_meaning([{'text':'점검 커버는 슬라이드 방식으로 합의했다.','sources':['S1']}],sources,'점검 커버 변경 과정을 설명해줘')
    assert len(out)==1 and '철회' in out[0]['text'] and '납품일' not in out[0]['text']
    assert validate_meaning([{'text':'커버는 확정되었습니다.','sources':['S1']}],[{'id':'S1','text':'납품일은 확정했다.'}],'점검 커버')==[]


def test_later_withdrawal_does_not_mask_false_initial_agreement():
    sources=[{'id':'S1','text':'커버는 여닫이 방식으로 합의했다. 슬라이드 커버 변경 요청을 철회했다.'}]
    for claim in ('커버는 슬라이딩 방식으로 합의했다.', '커버를 슬라이딩 방식으로 하기로 했었지만, 이후 요청을 철회했다.'):
        assert unsupported_decision(claim,sources)


@pytest.mark.parametrize('source,claim',[
    ('검사 장치는 A타입으로 합의했다.','검사 장치는 B타입으로 합의했다.'),
    ('센서는 광학 방식으로 합의했다.','센서는 초음파 방식으로 확정했다.'),
])
def test_unrecognized_qualitative_values_do_not_bypass_verification(source,claim):
    assert unsupported_decision(claim,[{'id':'S1','text':source}])
    assert not unsupported_decision(source,[{'id':'S1','text':source}])


def test_false_premise_abstention_can_quote_topic_negative_but_not_other_topics():
    sources=[{'id':'S1','project_id':'p','project_name':'프로젝트','date':'2026-11-13',
              'text':'납품일 변경 요청은 보류했다. 현재 납품일은 12월 18일을 유지한다.'}]
    assert '보류' in validate_meaning([],sources,'납품일이 확정됐다는 근거 찾아줘')[0]['text']
    assert validate_meaning([],sources,'고객 승인 이메일 찾아줘')==[]
    assert '보류' in validate_meaning([],sources,'납품일이 현재 12월 23일이라는 게 맞아?')[0]['text']


def test_search_source_after_trash_is_rejected(client):
    c,_=client;p=project(c);m=meeting(c,p,'점검 커버는 여닫이 방식이다.')
    job=ask(c,'한빛셀 점검 커버 회의록 찾아줘')
    with w.connect() as db:m['deleted_at']=w.now();w.save(db,'meeting',m)
    assert c.get('/api/questions/'+job['id']).json()['state']=='failed'
    assert c.get('/api/questions/'+job['id']+'/sources/S1').status_code==409


def test_later_different_object_does_not_replace_completion_record(client):
    c,_=client;p=project(c)
    first=meeting(c,p,'사양서 개정은 완료했다.','2026-11-13')
    meeting(c,p,'배치도 개정은 진행 중이다.','2026-11-20')
    result=ask(c,'한빛셀 사양서 개정이 끝났어?')['result']
    assert [s['meeting_id'] for s in result['sources']]==[first['id']]


def test_headers_not_highlighted_but_author_query_can_highlight():
    lines=[{'id':'L001','text':'프로젝트명 | 한빛셀 전극 롤프레스 1호기'},
           {'id':'L002','text':'작성자 | 김양일'},
           {'id':'L003','text':'점검 커버 변경 요청을 철회하고 여닫이 방식을 유지한다.'}]
    ids=[l['id'] for l in lines]
    h=questions.highlight_lines(lines,ids,'한빛셀 점검 커버',[], 'S1')
    assert h==['L003']
    assert questions.highlight_lines(lines,['L001'],'한빛셀 점검 커버',[],'S1')==[]
    assert 'L002' in questions.highlight_lines(lines,ids,'작성자는 누구야?',[],'S1')


def test_value_answer_highlights_maintained_baseline_not_just_request():
    lines=[{'id':'L011','text':'압연 속도: 고객은 120 m/min에서 135 m/min으로 상향을 요청했다. 구동부 용량과 발열 검토가 필요하다.'},
           {'id':'L016','text':'현재 기준은 속도 120 m/min, 여닫이 커버, 납품일 2026-12-18이다. 이번 회의에서는 세 변경 요청을 승인하지 않았다.'},
           {'id':'L020','text':'진효창: 2026-11-12까지 압연 속도 상향 영향과 측면 슬라이드 커버 간섭 검토 결과를 작성해 김양일에게 전달한다.'}]
    points=[{'text':'한빛셀에서 2026년 11월 11일 당시 압연 속도는 120 m/min으로 합의돼 있었음','sources':['S1'],'project_name':'한빛셀'}]
    h=questions.highlight_lines(lines,[l['id'] for l in lines],'한빛셀에서 2026년 11월 11일 당시 압연 속도는 얼마로 합의돼 있었어?',points,'S1')
    assert 'L016' in h and 'L020' not in h


def test_body_and_qualification_reach_prompt_even_if_header_similarity_high(client,monkeypatch):
    c,_=client;p=project(c)
    ms=[]
    for d,body in ((9,'점검 커버는 여닫이 방식으로 합의했다.'),(11,'점검 커버 측면 슬라이드 변경을 요청했다. 이 변경은 합의하지 않았다.'),(13,'점검 커버의 슬라이드 변경 요청을 철회했다. 여닫이 방식을 유지한다.')):
        ms.append(meeting(c,p,'회의명 | 점검 커버 협의\n작성자 | 김양일\n참석자 | 진효창\n프로젝트명 | 한빛셀\n주요 논의\n'+body,f'2026-11-{d:02}'))
    # Semantic-only scores favor the headers. Body anchors must still survive.
    monkeypatch.setattr(retrieval,'embed',lambda texts,prefix:[[1.0,0.0] for _ in texts])
    docs=[retrieval.registered_document(m) for m in ms]
    out=retrieval.retrieve(w,p['id'],docs,'점검 커버 변경 과정을 설명해줘')
    assert len(out)==3
    assert '합의하지 않았다' in next(s['text'] for s in out if s['date']=='2026-11-11')
    assert '철회' in next(s['text'] for s in out if s['date']=='2026-11-13')
    for s in out:
        doc=next(d for d in docs if d['meeting_id']==s['meeting_id'])
        highlight=questions.highlight_lines(retrieval.document_lines(doc),s['line_ids'],'점검 커버',[],s['id'])
        assert highlight and all(not META.match(l['text']) for l in retrieval.document_lines(doc) if l['id'] in highlight)
