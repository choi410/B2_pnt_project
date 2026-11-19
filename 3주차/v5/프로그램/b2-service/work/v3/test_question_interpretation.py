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
