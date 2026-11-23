"""Question meaning/date regressions. Uses disposable records and fake inference."""
import json
import sqlite3
import pytest
from work.v3.test_connected import client, w
from work.v3.test_questions_trash import project as create_project, meeting
from work.v3 import question_policy as policy
from work.v3.question_scope import plan_question, in_scope
from work.v17 import questions, retrieval


def project(c,name):
    return create_project(c,name+' '+w.uid()[:8])


def change(m, title, value, state='확정', **extra):
    item={'id':w.uid(),'project_id':m['project_id'],'meeting_id':m['id'],
          'title':title,'category':'납기' if '납품' in title else '사양',
          'after':value,'before':'','business_state':state,'review_state':'검토 전',
          'source_revision':m['revision'],'effective_date':m['date'],
          'evidence':[r['id'] for r in m['lines'][3:]],**extra}
    with w.connect() as c:w.save(c,'change_event',item)
    return item


def speed_history(c):
    p=project(c,'시점 검증 압연 설비')
    a=meeting(c,p,'압연 속도는 120 m/min으로 합의했다.','2026-11-09')
    b=meeting(c,p,'압연 속도 135 m/min을 요청했다. 아직 합의하지 않았다. 기존 120 m/min을 유지한다.','2026-11-11')
    d=meeting(c,p,'압연 속도는 135 m/min으로 합의했다.','2026-11-13')
    change(a,'압연 속도','120 m/min');change(b,'압연 속도','135 m/min','요청');change(d,'압연 속도','135 m/min')
    return p,a,b,d


@pytest.mark.parametrize('question',[
    '장비의 최종 계약 금액은 얼마야?', '현재 장비 보증 기간은 얼마야?',
    '장비 납품일 변경 비용은 얼마야?', '장비 납품일의 담당자는 누구야?',
    '현재 사양 기준을 알려줘', '전체 기준은 뭐야?',
    '압연 속도 기준 135는 확정이야 요청이야?', '135 m/min 사양으로 제작 완료된 거야?',
])
def test_value_route_does_not_answer_another_attribute(question):
    topics=[{'title':'장비 납품일'},{'title':'압연 속도'}]
    assert policy.topic_matches(topics,question)==[]


def test_unique_complete_attribute_and_ambiguous_suffix():
    one=[{'title':'장비 납품일'}]
    assert policy.topic_matches(one,'현재 납품일은 언제야?')==one
    assert policy.topic_matches(one,'장비는 언제야?')==[]
    assert policy.topic_matches(one+[{'title':'부품 납품일'}],'현재 납품일은 언제야?')==[]


@pytest.mark.parametrize('question',[
    '11월 11일 기준 합의된 압연 속도는 얼마야?',
    '11월 11일 회의 시점에는 압연 속도를 얼마로 합의한 상태였어?',
    '2026-11-11 기준 압연 속도는 얼마야?',
])
def test_paraphrased_historical_questions_keep_same_value(client,question,monkeypatch):
    class NoModel:
        def submit(self,*args):raise AssertionError('Historical value should use bounded evidence')
    monkeypatch.setattr(questions,'POOL',NoModel())
    c,_=client;p,a,b,d=speed_history(c)
    result=c.post('/api/questions',json={'project_id':p['id'],'question':question}).json()
    assert result['state']=='done',result
    answer=result['result'];assert '120 m/min' in answer['points'][0]['text']
    assert '135 m/min' not in answer['points'][0]['text']
    assert {s['meeting_id'] for s in answer['sources']}=={a['id'],b['id']}
    assert '2026-11-11' in answer['notice']
    assert c.get('/api/questions/'+result['id']+'/sources/'+answer['sources'][0]['id']).status_code==200
    assert 'diagnostics' not in c.get('/api/questions/'+result['id']).json()


def test_late_registration_does_not_replace_newer_meeting(client):
    c,_=client;p,a,b,d=speed_history(c)
    older=meeting(c,p,'압연 속도는 100 m/min으로 합의했다.','2026-11-01')
    change(older,'압연 속도','100 m/min',created_at='2030-01-01')
    with w.connect() as db:answer=policy.recorded_agreements(w,db,[p],'현재 압연 속도는 얼마야?')
    assert '135 m/min' in answer['points'][0]['text']


@pytest.mark.parametrize('state,text',[
    ('철회','기존 압연 속도 120 m/min 합의를 철회했다. 새 속도는 미정이다.'),
    ('요청','압연 속도는 140 m/min으로 합의했다.'),
    ('보류','기존 압연 속도 120 m/min 합의는 무효이며 재검토를 보류했다.'),
])
def test_later_revocation_or_wrong_extraction_cannot_be_fast_value(client,state,text):
    c,_=client;p=project(c,'후속 기록 검증')
    a=meeting(c,p,'압연 속도는 120 m/min으로 합의했다.','2026-11-01')
    change(a,'압연 속도','120 m/min')
    b=meeting(c,p,text,'2026-11-02');change(b,'압연 속도','140 m/min' if state=='요청' else '120 m/min',state)
    with w.connect() as db:
        assert policy.recorded_agreements(w,db,[p],'현재 압연 속도는 얼마야?') is None
        assert policy.recorded_agreements(w,db,[p],'11월 2일 기준 압연 속도는 얼마야?') is None


def test_same_day_conflict_has_both_sources_no_last_writer_winner(client):
    c,_=client;p=project(c,'동일 날짜 충돌')
    for value in ('120 m/min','135 m/min'):
        m=meeting(c,p,f'압연 속도는 {value}으로 합의했다.','2026-11-11');change(m,'압연 속도',value)
    with w.connect() as db:a=policy.recorded_agreements(w,db,[p],'현재 압연 속도는 얼마야?')
    assert '서로 다른' in a['points'][0]['text'] and len(a['sources'])==2


def test_effective_date_not_assumed_to_be_meeting_date(client):
    c,_=client;p=project(c,'효력일 차이 검증')
    m=meeting(c,p,'압연 속도는 120 m/min으로 합의했다.','2026-11-13')
    change(m,'압연 속도','120 m/min',effective_date='2026-11-01')
    with w.connect() as db:assert policy.recorded_agreements(w,db,[p],'현재 압연 속도는 얼마야?') is None


@pytest.mark.parametrize('q,mode,start,end',[
    ('11월 11일 회의에서 나온 요청은?', 'meeting','2026-11-11','2026-11-11'),
    ('11월 9일부터 11월 11일까지 변경 과정은?', 'period','2026-11-09','2026-11-11'),
    ('11월 11일 이전 기준 압연 속도는?', 'as_of',None,'2026-11-10'),
    ('11월 11일 이후 회의에서 무엇을 정했어?', 'period','2026-11-12',None),
    ('11월 11일 회의 이후 속도 변경 과정은?', 'period','2026-11-12',None),
    ('11월 11일 현재 합의된 속도는?', 'as_of',None,'2026-11-11'),
    ('11월 11일에는 속도를 얼마로 정한 상태였지?', 'as_of',None,'2026-11-11'),
    ('11월 11일에 속도는 얼마였어?', 'as_of',None,'2026-11-11'),
    ('11월 11일에는 납품일이 어떻게 정해져 있었어?', 'as_of',None,'2026-11-11'),
    ('한빛셀 프로젝트는 11월 11일에는 속도가 어떤 상태였어?', 'as_of',None,'2026-11-11'),
    ('11월 11일에 합의한 속도는?', 'meeting','2026-11-11','2026-11-11'),
    ('11월의 변경 내용을 알려줘', 'period','2026-11-01','2026-11-30'),
    ('납품일 12월 23일로 확정된 거 맞지?', 'current',None,None),
    ('12월 23일에는 납품할 수 있어?', 'current',None,None),
])
def test_question_dates_are_not_requested_delivery_dates(q,mode,start,end):
    p=plan_question(q,[{'date':'2026-11-09'},{'date':'2026-11-13'}])
    assert (p['mode'],p['start'],p['end'])==(mode,start,end)


def test_missing_year_ambiguity_invalid_dates_and_undated_documents():
    docs=[{'date':'2025-11-09'},{'date':'2026-11-09'}]
    assert plan_question('11월 11일 기준 압연 속도는?',docs)['mode']=='clarify'
    assert plan_question('2026-11-11 기준 압연 속도는?',docs)['end']=='2026-11-11'
    assert plan_question('11월 31일 기준 속도는?',docs)['mode']=='clarify'
    assert plan_question('11일 기준 속도는?',[{'date':'2026-10-11'},{'date':'2026-11-11'}])['mode']=='clarify'
    p=plan_question('11일 기준 속도는?',[{'date':'2026-11-09'}]);assert p['end']=='2026-11-11'
    assert not in_scope({'date':''},p)
    assert plan_question('2월 29일 기준 속도는?',[{'date':'2024-01-01'},{'date':'2025-01-01'}])['end']=='2024-02-29'


class Immediate:
    def submit(self,fn,*args):fn(*args)


def controlled_reader(monkeypatch,seen):
    monkeypatch.setattr(questions,'POOL',Immediate())
    def retrieve(w,pid,docs,q,**kwargs):
        seen.extend(docs)
        assert not kwargs['prune_cache']
        return [{k:v for k,v in d.items() if k!='body'}|{'text':d['body'],'line_ids':['L004'],'score':1} for d in docs]
    def generate(w,q,sources,**kwargs):
        return {'answerable':True,'points':[{'text':'요청 기록을 확인했습니다.','sources':[s['id'] for s in sources]}]}
    monkeypatch.setattr(questions,'retrieve',retrieve);monkeypatch.setattr(questions,'generate',generate)


@pytest.mark.parametrize('query,expected',[
    ('11월 11일 회의에서 무엇을 요청했어?',{'2026-11-11'}),
    ('11월 9일부터 11월 11일까지 어떻게 바뀌었어?',{'2026-11-09','2026-11-11'}),
    ('11월 11일 기준 점검 커버는 어떻게 됐지?',{'2026-11-09','2026-11-11'}),
    ('11월 11일에는 속도를 얼마로 정한 상태였지?',{'2026-11-09','2026-11-11'}),
])
def test_date_scope_applies_before_retrieval_and_generation(client,monkeypatch,query,expected):
    c,_=client;p,*_=speed_history(c);seen=[];controlled_reader(monkeypatch,seen)
    job=c.post('/api/questions',json={'project_id':p['id'],'question':query}).json()
    result=c.get('/api/questions/'+job['id']).json()
    assert result['state']=='done',result
    assert {d['date'] for d in seen}==expected
    assert result['result']['notice'] and all(s['date'] in expected for s in result['result']['sources'])
    assert {d['stage'] for d in questions.JOBS[job['id']]['diagnostics']}>={'route','scope','selected','result'}


def test_before_first_record_does_not_use_future_or_invent_absence(client,monkeypatch):
    c,_=client;p,*_=speed_history(c);seen=[];controlled_reader(monkeypatch,seen)
    job=c.post('/api/questions',json={'project_id':p['id'],'question':'11월 8일 기준 압연 속도는 얼마야?'}).json()
    result=c.get('/api/questions/'+job['id']).json()['result']
    assert not seen and not result['answerable']
    assert '등록된 회의 자료에서 확인하지 못했습니다' in result['message']


def test_unknown_attribute_falls_back_without_leaking_wrong_ledger_answer(client,monkeypatch):
    c,_=client;p=project(c,'금액 검증')
    m=meeting(c,p,'장비 납품일은 2026-12-18로 합의했다.');change(m,'장비 납품일','2026-12-18')
    monkeypatch.setattr(questions,'POOL',Immediate())
    def retrieve(w,pid,docs,q,**kwargs):
        d=docs[0];return [{k:v for k,v in d.items() if k!='body'}|{'text':d['body'],'line_ids':['L004'],'score':1}]
    monkeypatch.setattr(questions,'retrieve',retrieve)
    monkeypatch.setattr(questions,'generate',lambda *a,**k:{'answerable':False,'points':[]})
    job=c.post('/api/questions',json={'project_id':p['id'],'question':'장비의 최종 계약 금액은 얼마야?'}).json()
    result=c.get('/api/questions/'+job['id']).json()['result']
    assert not result['answerable'] and not result['points']
    assert questions.JOBS[job['id']]['diagnostics'][0]['route']=='retrieval'


def test_historical_lookup_keeps_other_cached_vectors_and_traces_metadata(tmp_path,monkeypatch):
    class Store:
        def connect(self):return sqlite3.connect(tmp_path/'vectors.sqlite3')
    store=Store()
    with store.connect() as c:
        c.execute('CREATE TABLE rag_vectors(project_id TEXT,cache_key TEXT,vector TEXT,PRIMARY KEY(project_id,cache_key))')
        c.execute('INSERT INTO rag_vectors VALUES(?,?,?)',('p','future',json.dumps([1,0])))
    monkeypatch.setattr(retrieval,'embed',lambda texts,prefix:[[1,0] for _ in texts])
    docs=[{'meeting_id':'m','project_id':'p','title':'사양','date':'2026-11-01','revision':1,'fingerprint':'x','has_draft':False,'body':'속도는 120으로 합의했다.\n다음 확인은 미정이다.'}]
    events=[]
    result=retrieval.retrieve(store,'p',docs,'속도',prune_cache=False,trace=lambda stage,**d:events.append((stage,d)))
    assert result and events[0][1]['chosen'][0]['line_ids']
    assert 'body' not in json.dumps(events) and '속도는' not in json.dumps(events,ensure_ascii=False)
    with store.connect() as c:assert c.execute("SELECT 1 FROM rag_vectors WHERE cache_key='future'").fetchone()


def test_invalid_numeric_answer_stays_blocked_with_diagnostic():
    sources=[{'id':'S1','project_id':'p','date':'2026-11-09','text':'압연 속도는 120 m/min으로 합의했다.'}]
    events=[]
    with pytest.raises(ValueError,match='근거에 없는 수치'):
        questions.validate_answer({'answerable':True,'points':[{'text':'압연 속도는 999 m/min입니다.','sources':['S1']}]},sources,
                                  trace=lambda stage,**data:events.append((stage,data)))
    assert events==[('validation',{'reason':'unsupported_numbers','unsupported':[999.0],'cited_sources':['S1']})]
    good={'answerable':True,'points':[{'text':'압연 속도는 120 m/min입니다.','sources':['S1']}]}
    assert questions.validate_answer(good,sources)[0]['text']=='압연 속도는 120 m/min입니다.'
