"""Behavioral regression cases from the wording/context audit. Isolated DB only."""
from datetime import date
import pytest
from work.v3.test_connected import client,w
from work.v3.test_questions_trash import project,meeting
from work.v3.test_project_order import stamp
from work.v3.test_latest_meetings import change
from work.v3 import conversations,question_policy as policy
from work.v3.query_intent import metadata_plan,relative_period
from work.v3.answer_meaning import validate_meaning,unsupported_decision
from work.v17 import questions


@pytest.mark.parametrize('name',['ㅈㅇㅇㅁㅇ','ㄱㄴ','!!!','🔥','---','','  ','北京'])
@pytest.mark.parametrize('question',['변경이력이 가장 많은 프로젝트는?','한빛셀 현재 속도 알려줘','회의록을 월별로 찾아줘'])
def test_unrelated_unicode_or_empty_names_never_match_every_question(name,question):
    candidate={'id':'P-UNRELATED','name':name}
    assert policy.name_matches([candidate],question)==[]


@pytest.mark.parametrize('name,question',[
    ('ㅈㅇㅇㅁㅇ','ㅈㅇㅇㅁㅇ 프로젝트 담당자는 누구야?'),
    ('ㄱㄴ','ᄀᄂ 프로젝트 보여줘'),('北京','北京 프로젝트 보여줘'),
    ('Alpha','alpha 프로젝트 담당자는?'),('A','A 프로젝트 보여줘'),('11','11 프로젝트 보여줘'),
    ('ㅈㅇㅇㅁㅇ','P-EXPLICIT 프로젝트 보여줘'),('🔥','P-EXPLICIT 프로젝트 보여줘')])
def test_explicit_unicode_names_and_codes_remain_selectable(name,question):
    candidate={'id':'P-EXPLICIT','name':name}
    assert policy.name_matches([candidate],question)==[candidate]


@pytest.mark.parametrize('name,question',[('A','AI 질문이야'),('11','11월 회의록 찾아줘'),('11','2026-11-25 회의록'),('AA','BAA 프로젝트')])
def test_short_names_do_not_match_inside_words_or_dates(name,question):
    assert policy.name_matches([{'id':'P-SHORT','name':name}],question)==[]


def test_empty_label_pattern_never_matches():
    import re
    from work.v3.query_intent import label_pattern
    assert re.search(label_pattern('   '),'프로젝트') is None


@pytest.mark.parametrize('name',['ㅈㅇㅇㅁㅇ','北京'])
def test_model_proposed_unicode_name_is_bound_to_question_and_access(client,name):
    from work.v3 import chat_interpreter as language
    c,_=client;p=project(c,name);project(c,'한빛셀 롤프레스')
    proposal=language.Plan(action='owner',scope='named',projects=[name]).model_dump()
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        context,result=language.execute(w,db,actor,name+' 프로젝트 담당자는 누구야?',proposal)
        assert context['project_ids']==[p['id']] and result['mode']=='project_owner'
        _,rejected=language.execute(w,db,actor,'한빛셀 프로젝트 담당자는 누구야?',proposal)
        assert rejected['kind']=='clarification' and not rejected['answerable']


@pytest.mark.parametrize('question',[
    '왜 ㅈㅇㅇㅁㅇ 프로젝트에서 찾은거야?', '왜 거기에서 찾았어?',
    '어느 프로젝트에서 검색한 거야?', '검색 범위가 어떻게 돼?',
    '전체 프로젝트를 비교한 거야?', '왜 이 프로젝트만 선택했어?', '어디까지 검색했어?'])
def test_scope_questions_are_search_explanations(question):
    from work.v3.conversation_context import scope_question
    assert scope_question(question)


@pytest.mark.parametrize('question',[
    '왜 보류했지?', '한빛셀 프로젝트에서 왜 납품을 미뤘어?',
    '왜 납품을 미뤘는지 프로젝트에서 찾아줘', '프로젝트에서 왜 속도가 바뀌었는지 검색해줘',
    '전체 프로젝트로 검색 범위를 바꿔줘', '전체에서 찾아줘', '그 프로젝트의 변경이력 보여줘'])
def test_business_reasons_and_new_searches_are_not_scope_explanations(question):
    from work.v3.conversation_context import scope_question
    assert not scope_question(question)


@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(w,'DB',tmp_path/'interpretation.sqlite3')
    monkeypatch.setattr(w,'FILES',tmp_path/'files')
    monkeypatch.setattr(questions,'JOBS',{})
    class NoModel:
        def submit(self,*args):raise AssertionError('Metadata must not use generation')
    monkeypatch.setattr(questions,'POOL',NoModel())


def send(c,q,cid=None,**kw):
    r=c.post('/api/conversations/questions',json={'question':q,'conversation_id':cid,**kw})
    assert r.status_code==202,r.text
    return r.json()


def stored_result(thread):
    with w.connect() as db:
        return conversations.messages(w,db,thread['id'])[-1]['job']['result']


@pytest.mark.parametrize('question',[
    '가장 최신 회의록 뭐야?', '가장 최신 희의록 뭐야?',
    '가장 최신 회으록 뭐야?', '가장 최신 회이록 뭐야?',
    '전체 프로젝트에서 가장 최신 희의록은 뭐야?'])
def test_latest_meeting_after_project_ranking_and_scope_explanation(client,question):
    from work.v3.test_questions_trash import event
    c,_=client;a=project(c,'한빛셀 롤프레스');b=project(c,'서린 코팅라인')
    old=meeting(c,a,date='2026-11-09');latest=meeting(c,b,date='2026-11-19')
    tied=meeting(c,a,date='2026-11-19')
    event(old,'speed','확정','120');event(old,'speed','요청','135')
    t=send(c,'변경이력이 가장 많은 프로젝트는?')
    assert stored_result(t)['result_project_ids']==[a['id']]
    t=send(c,'왜 그 프로젝트에서 찾은거야?',t['id'])
    assert stored_result(t)['mode']=='scope_explanation'
    t=send(c,question,t['id']);r=stored_result(t)
    assert r['mode']=='meeting_lookup' and not r.get('projects')
    assert {s['meeting_id'] for s in r['sources']}=={latest['id'],tied['id']}
    with w.connect() as db:
        saved=conversations.messages(w,db,t['id'])[-1]
    assert saved['question']==question
    assert set(saved['job']['scope_ids'])=={a['id'],b['id']}
    for s in r['sources']:
        assert c.get(f"/api/conversations/{t['id']}/messages/{saved['id']}/sources/{s['id']}").status_code==200


@pytest.mark.parametrize('question',[
    '가장 최신 회의록 뭐야?', '가장 최신 희의록 뭐야?', '전체 회의록 몇 개야?'])
@pytest.mark.parametrize('wrong_action',['projects','project_order','project_count'])
def test_wrong_model_entity_cannot_override_explicit_meeting_query(client,question,wrong_action):
    from work.v3 import chat_interpreter as language
    c,_=client;a=project(c,'한빛셀 롤프레스');b=project(c,'서린 코팅라인')
    meeting(c,a,date='2026-11-09');latest=meeting(c,b,date='2026-11-19')
    t=send(c,'한빛셀 프로젝트 보여줘')
    with w.connect() as db:
        previous=conversations.messages(w,db,t['id'])[-1]
        actor=w.read(db,'person','team1')
        proposal=language.Plan(action=wrong_action,scope='previous',relation='continue').model_dump()
        context,result=language.execute(w,db,actor,question,proposal,previous)
    assert context['interpretation_repair']=='explicit_entity'
    assert not result.get('projects')
    if '몇' in question:
        assert result['mode']=='count' and result['count']==2
    else:
        assert result['mode']=='meeting_lookup'
        assert {s['meeting_id'] for s in result['sources']}=={latest['id']}


@pytest.mark.parametrize('question',['최신 회고록 뭐야?','회의론은 뭐야?','가장 최신 회사록 뭐야?','최신 회의록 내용 요약해줘'])
def test_other_words_and_content_do_not_become_meeting_metadata(question):
    assert metadata_plan(question) is None


def test_latest_meeting_typo_respects_explicit_project_selection(client):
    c,_=client;a=project(c,'한빛셀 롤프레스');b=project(c,'서린 코팅라인')
    selected=meeting(c,a,date='2026-11-09');meeting(c,b,date='2026-11-19')
    t=send(c,'가장 최신 희의록 뭐야?',project_id=a['id'])
    assert {s['meeting_id'] for s in stored_result(t)['sources']}=={selected['id']}


def test_wrong_model_meetings_plan_cannot_override_project_count(client):
    from work.v3 import chat_interpreter as language
    c,_=client;a=project(c,'한빛셀 롤프레스');project(c,'서린 코팅라인')
    meeting(c,a)
    with w.connect() as db:
        context,result=language.execute(w,db,w.read(db,'person','team1'),
            '전체 프로젝트 몇 개야?',language.Plan(action='meetings').model_dump())
    assert context['interpretation_repair']=='explicit_entity'
    assert result['count']==2 and result['mode']=='count'
    assert '프로젝트' in result['message'] and not result['sources']


@pytest.mark.parametrize('unrelated_name',['ㅈㅇㅇㅁㅇ','!!!','北京'])
def test_global_ranking_and_explanation_with_unrelated_project(client,unrelated_name):
    from work.v3.test_questions_trash import event
    c,_=client;a=project(c,'한빛셀 롤프레스');b=project(c,'서린 코팅라인')
    unrelated=project(c,unrelated_name)
    m=meeting(c,a);n=meeting(c,b)
    event(m,'speed','확정','120');event(m,'speed','요청','135');event(n,'width','확정','650')
    t=send(c,'변경이력이 가장 많은 프로젝트는?');r=stored_result(t)
    assert r['count']==2 and r['result_project_ids']==[a['id']] and r['compared_projects']==3
    with w.connect() as db:
        saved=conversations.messages(w,db,t['id'])[-1]
        assert set(saved['job']['scope_ids'])=={a['id'],b['id'],unrelated['id']}
    t=send(c,f'왜 {unrelated_name} 프로젝트에서 찾은거야?',t['id']);r=stored_result(t)
    assert r['mode']=='scope_explanation' and '전체 3개 프로젝트' in r['message']
    assert a['name'] in r['message'] and '2건' in r['message'] and not r['sources']
    t=send(c,'그 프로젝트 담당자는 누구야?',t['id']);r=stored_result(t)
    assert r['mode']=='project_owner' and r['result_project_ids']==[a['id']]


def test_explicit_consonant_project_and_selection_reason(client):
    c,_=client;p=project(c,'ㅈㅇㅇㅁㅇ');project(c,'한빛셀 롤프레스')
    t=send(c,'ㅈㅇㅇㅁㅇ 프로젝트 PM 누구야?');r=stored_result(t)
    assert r['mode']=='project_owner' and r['result_project_ids']==[p['id']]
    t=send(c,'왜 이 프로젝트에서 찾았어?',t['id']);r=stored_result(t)
    assert r['mode']=='scope_explanation' and '앞 질문에 적힌' in r['message']
    t=send(c,'변경이력이 가장 많은 프로젝트는?',project_id=p['id'])
    t=send(c,'왜 여기만 검색했어?',t['id']);r=stored_result(t)
    assert r['mode']=='scope_explanation' and '질문을 보낼 때' in r['message']
    assert '지정되어' in r['message'] and '0건' in r['message']


def test_scope_explanation_does_not_invent_legacy_selection_reason(client):
    c,_=client;p=project(c,'ㅈㅇㅇㅁㅇ');project(c,'한빛셀 롤프레스')
    t=send(c,'변경이력이 가장 많은 프로젝트는?',project_id=p['id'])
    with w.connect() as db:
        old=conversations.messages(w,db,t['id'])[-1]
        old['context'].pop('input_scope',None);w.save(db,'ai_message',old)
    t=send(c,'왜 ㅈㅇㅇㅁㅇ 프로젝트에서 찾은거야?',t['id']);r=stored_result(t)
    assert r['mode']=='scope_explanation' and '이전 기록만으로 확인하기 어려워요' in r['message']
    assert '지정되어' not in r['message']


def test_scope_explanation_rechecks_permissions(client):
    c,_=client;p=project(c,'비공개될 설비');project(c,'공개 설비')
    t=send(c,'프로젝트 담당자는 누구야?',project_id=p['id'])
    with w.connect() as db:
        p['members']=['team2'];w.save(db,'project',p)
    t=send(c,'왜 그 프로젝트에서 찾았어?',t['id']);r=stored_result(t)
    assert r['mode']=='scope_explanation' and '현재 열람할 수 없는' in r['message']
    assert p['name'] not in str(r) and p['id'] not in str(r)
    with w.connect() as db:
        latest=conversations.messages(w,db,t['id'])[-1]
        assert latest['context']['project_ids']==[] and latest['job']['scope_ids']==[]


def test_scope_explanation_without_previous_search(client):
    c,_=client;t=send(c,'어느 프로젝트에서 검색한 거야?');r=stored_result(t)
    assert r['mode']=='scope_explanation' and '이전 조회 범위가 없어요' in r['message']


def test_async_result_keeps_original_request_scope(client):
    from copy import deepcopy
    c,_=client;p=project(c,'ㅈㅇㅇㅁㅇ')
    t=send(c,'프로젝트 담당자는 누구야?',project_id=p['id'])
    with w.connect() as db:
        old=conversations.messages(w,db,t['id'])[-1]
        done=deepcopy(old['job']);done['conversation_context']={'project_ids':[p['id']],'query':old['question']}
        old['state']='queued';old['job']['state']='queued';w.save(db,'ai_message',old)
    questions.JOBS[done['id']]=done
    conversations.sync_message(w,old['id'])
    with w.connect() as db:
        updated=w.read(db,'ai_message',old['id'])
        assert updated['state']=='done'
        assert updated['context']['input_scope']=={'project_id':p['id'],'meeting_id':None}


def setup(c):
    old=project(c,'한빛셀 롤프레스');new=project(c,'aa')
    stamp(old,'2026-11-12T09:00:00+09:00');stamp(new,'2026-11-17T09:00:00+09:00')
    a=meeting(c,old,date='2026-11-13')
    b=meeting(c,new,new['id']+' 과거 날짜 회의록. 기본 설계를 검토했다.',date='2026-10-15')
    return old,new,a,b


@pytest.mark.parametrize('q',[
    '방금 생성한 프로젝트 찾아줘','가장 마지막에 만든 프로젝트 알려줘','막 만든 프로젝트가 뭐야?',
    '가장 새 프로젝트 알려줘','젤 최근 프로젝트 뭐야?','제일 최근 프로잭트가 뭐야?',
    '제일 최근 프로젝트 뭐야? 생성일 기준으로',
])
def test_project_paraphrases_are_global_record_lookups(client,q):
    c,_=client;_,new,_,_=setup(c)
    m=send(c,q)['messages'][-1]
    assert m['state']=='done'
    assert [p['id'] for p in m['result']['projects']]==[new['id']]


@pytest.mark.parametrize('q,basis,direction',[
    ('방금 올린 회의록 뭐야?','registered_at','newest'),
    ('마지막 회의록 제목 알려줘','meeting_date','newest'),
    ('가장 오래된 회의록 찾아줘','meeting_date','oldest'),
    ('제일 최근 회으록 보여줘','meeting_date','newest'),
    ('회의록 등록일 기준 가장 최근 회의록','registered_at','newest'),
])
def test_meeting_paraphrases(q,basis,direction):
    plan=metadata_plan(q)
    assert plan and plan['basis']==basis and plan['direction']==direction


@pytest.mark.parametrize('q',[
    '첫 프로젝트의 압연 속도는 얼마야?','프로젝트 예산은 얼마야?',
    '프로젝트를 누가 생성했어?','최신 회의록의 결정사항 알려줘',
    '회의록이 몇 개 변경되었어?','최근 회의록과 이전 회의록 비교해줘',
    '회의록에 나온 프로젝트 납기는 언제야?',
])
def test_content_never_replaced_with_names_counts_or_titles(q):
    assert metadata_plan(q) is None


def test_sort_count_limit_and_per_project_latest(client):
    c,_=client;old,new,a,b=setup(c)
    def answer(q):
        thread=send(c,q);m=thread['messages'][-1];assert m['state']=='done';return stored_result(thread)
    assert [p['id'] for p in answer('프로젝트를 최신순으로 보여줘')['projects']]==[new['id'],old['id']]
    assert len(answer('프로젝트 1개만 보여줘')['projects'])==1
    assert answer('등록된 프로젝트가 몇 개야?')['count']==2
    assert answer('회의록이 총 몇 개야?')['count']==2
    assert answer('한빛셀 회의록 몇 개야?')['count']==1
    assert {s['meeting_id'] for s in answer('프로젝트별 최신 회의록 보여줘')['sources']}=={a['id'],b['id']}
    change(b,deleted_at=w.now())
    assert answer('회의록이 총 몇 개야?')['count']==1


def test_resolved_latest_project_survives_cache_loss_and_followup(client):
    c,_=client;old,new,a,b=setup(c)
    first=send(c,'제일 최근 프로젝트가 뭐야?')
    with questions.LOCK:questions.JOBS.clear()
    second=send(c,'그 프로젝트 최신 회의록 보여줘',first['id'])
    result=stored_result(second)
    assert [s['meeting_id'] for s in result['sources']]==[b['id']]
    with w.connect() as db:
        previous=conversations.messages(w,db,first['id'])[-1]
        ctx=conversations.resolve_question(w,db,w.read(db,'person','team1'),'그 회의록 요약해줘',previous)
    assert ctx['project_id']==new['id'] and ctx['meeting_ids']==[b['id']]
    assert not ctx.get('clarify') and a['id'] not in ctx['meeting_ids']


def test_referenced_document_scope_reaches_retrieval(client,monkeypatch):
    c,_=client;old,new,a,b=setup(c);captured=[]
    first=send(c,'한빛셀 최신 회의록 보여줘')
    class Immediate:
        def submit(self,fn,*args):fn(*args)
    monkeypatch.setattr(questions,'POOL',Immediate())
    def retrieve(w,pid,docs,q,**kwargs):
        captured.extend(d['meeting_id'] for d in docs);return []
    monkeypatch.setattr(questions,'retrieve',retrieve)
    from work.v3 import agenda_questions
    def summary_retrieve(docs,q,**kwargs):
        captured.extend(d['meeting_id'] for d in docs);return []
    monkeypatch.setattr(agenda_questions,'retrieve',summary_retrieve)
    final=send(c,'그 회의록 요약해줘',first['id'])['messages'][-1]
    assert final['state']=='done' and captured==[a['id']]
    assert b['id'] not in captured
    # An explicit document ID cannot bypass project membership.
    private=project(c,'비공개',members=['team1']);secret=meeting(c,private)
    c.post('/api/demo-login',json={'username':'team2'})
    r=c.post('/api/questions',json={'question':'회의록 요약해줘','meeting_ids':[secret['id']]})
    assert r.status_code==404


def test_tied_documents_require_selection_then_use_selected_id(client,monkeypatch):
    c,_=client;p=project(c);a=meeting(c,p,date='2026-11-13');b=meeting(c,p,p['id']+' 다른 회의 기록입니다.',date='2026-11-13')
    first=send(c,'최신 회의록 보여줘')
    clarify=send(c,'그 회의록 요약해줘',first['id'])
    result=clarify['messages'][-1]['result']
    assert result['kind']=='clarification' and {m['id'] for m in result['meetings']}=={a['id'],b['id']}
    with w.connect() as db:
        prior=conversations.messages(w,db,first['id'])[-1]
        ctx=conversations.resolve_question(w,db,w.read(db,'person','team1'),'그 회의록 요약해줘',prior,meeting_id=b['id'])
    assert ctx['meeting_ids']==[b['id']] and not ctx.get('clarify')


def test_project_typo_is_confirmation_not_implicit_all_scope(client):
    c,_=client;old,new,_,_=setup(c)
    first=send(c,'한빗셀 프로젝트 찾아줘')
    r=first['messages'][-1]['result']
    assert r['kind']=='clarification' and [p['id'] for p in r['projects']]==[old['id']]
    follow=send(c,'한빛셀',first['id'])['messages'][-1]
    assert follow['state']=='done' and [p['id'] for p in follow['result']['projects']]==[old['id']]
    first=send(c,'한빗셀 프로젝트 찾아줘')
    clicked=send(c,'한빗셀 프로젝트 찾아줘',first['id'],project_id=old['id'])['messages'][-1]
    assert clicked['state']=='done' and [p['id'] for p in clicked['result']['projects']]==[old['id']]
    missing=send(c,'없는회사 프로젝트 납품일은 언제야?')['messages'][-1]
    assert missing['result']['kind']=='clarification'
    assert not missing['result']['projects']


def test_correction_date_and_resolved_subject(client):
    c,_=client;old,new,a,b=setup(c)
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        prior={'question':'한빛셀 현재 납품일은 언제야?','context':{'query':'한빛셀 현재 납품일은 언제야?',
              'subject':'납품일','project_ids':[old['id']],'time_scope':{'mode':'current'}}}
        ctx=conversations.resolve_question(w,db,actor,'아니 aa로',prior)
        assert ctx['project_id']==new['id'] and '납품일' in ctx['query'] and '한빛셀' not in ctx['query']
        dated=conversations.resolve_question(w,db,actor,'11월 11일에는?',prior)
        assert dated['project_id']==old['id'] and dated['time_scope']['end']=='2026-11-11'
        assert '납품일' in dated['query']
        named=conversations.resolve_question(w,db,actor,'그건 누가 담당해?',prior)
        assert named['project_id']==old['id'] and '납품일' in named['query'] and '회의록' in named['query']


def test_relative_dates_use_korean_calendar_and_registration_basis(client,monkeypatch):
    c,_=client;old,new,a,b=setup(c)
    assert relative_period('지난주 회의록',date(2026,11,18))=={'start':'2026-11-09','end':'2026-11-15'}
    assert relative_period('어제 올린 회의록',date(2026,11,18))=={'start':'2026-11-17','end':'2026-11-17'}
    monkeypatch.setattr('work.v3.query_intent.relative_period',lambda q: {'start':'2026-11-17','end':'2026-11-17'})
    change(a,created_at='2026-11-17T02:00:00+09:00');change(b,created_at='2026-11-18T02:00:00+09:00')
    result=stored_result(send(c,'어제 올린 회의록 보여줘'))
    assert [s['meeting_id'] for s in result['sources']]==[a['id']]
    assert '등록일' in result['notice'] and '2026-11-17' in result['notice']


def test_explicit_date_filters_use_creation_and_upload_dates(client):
    c,_=client;old,new,a,b=setup(c)
    change(a,created_at='2026-11-18T02:00:00+09:00');change(b,created_at='2026-11-12T02:00:00+09:00')
    result=stored_result(send(c,'2026-11-13 기준 프로젝트 몇 개야?'))
    assert result['count']==1
    result=stored_result(send(c,'2026-11-13 기준 등록된 회의록 몇 개야?'))
    assert result['count']==1 and '등록일' in result['notice']


def test_unrecognized_order_request_does_not_ask_model_to_invent_rank(client):
    c,_=client;setup(c)
    result=stored_result(send(c,'제일 최근 프로젝트 적절히 뽑아봐'))
    assert result['kind']=='clarification' and not result['answerable']


@pytest.mark.parametrize('source,claim,reject',[
    ('고객은 압연 속도 135 m/min을 요청했다. 변경은 확정하지 않았다. 현재 기준은 120 m/min을 유지한다.','압연 속도는 135 m/min으로 확정되었습니다.',True),
    ('압연 속도 135 m/min으로 변경하기로 합의했다.','압연 속도는 135 m/min으로 합의했습니다.',False),
    ('압연 속도는 120 m/min으로 합의했다. 135 m/min 변경 요청은 보류했다.','압연 속도는 135 m/min으로 합의했습니다.',True),
    ('압연 속도는 135 m/min으로 합의하지 않았다.','압연 속도는 135 m/min으로 확정되었습니다.',True),
    ('압연 속도는 135 m/min 변경을 보류했다.','135 m/min으로 확정되지 않았습니다.',False),
    ('점검 커버는 여닫이 방식이다. 납품일은 12월 18일로 확정했다.','점검 커버는 여닫이 방식으로 확정되었습니다.',True),
])
def test_status_claims_require_matching_support(source,claim,reject):
    sources=[{'id':'S1','text':source}]
    assert unsupported_decision(claim,sources)==reject
    result=validate_meaning([{'text':claim,'sources':['S1'],'project_id':'p'}],sources)
    assert (result[0].get('verification')=='source_quote')==reject
    if reject:assert '원문을 표시' in result[0]['text'] and result[0]['sources']==['S1']
