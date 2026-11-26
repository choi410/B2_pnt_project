"""Source-derived vocabulary tests use domains outside the reviewer evaluation."""
import pytest
from work.v3.test_content_query import client,w,isolated,ask
from work.v3.test_questions_trash import project,meeting
from work.v3.content_query import prepare
from work.v3.source_terms import catalog,resolve
from work.v17.evidence_text import coverage,topic_terms
from work.v17 import questions,retrieval


def test_explicit_aliases_keep_originals_and_unknown_properties():
    docs=[{'body':'토출 유량(분당 배출량)은 40 L로 합의했다.','meeting_id':'m','revision':1,'date':'2026-01-01'}]
    before=docs[0]['body']
    q=prepare('분당배출량 변경내역 알려줘',[{'name':'시험 설비'}],docs)
    assert q['subjects'][0]['evidence'][0]['line_id']=='L001'
    assert coverage('토출 유량은 40 L',q['search_terms'])==1
    assert coverage('분당 배출량은 50 L',q['search_terms'])==1
    assert docs[0]['body']==before
    q=resolve('분당 배출량 측정기 보증 기간은?',docs)
    assert '보증' in q['terms'] and '기간' in q['terms']


@pytest.mark.parametrize('line',[
    '토출 유량(40 L)은 합의값이다.', '부스터(검토 중)는 아직 미정이다.',
    '시험 조건(고객 확인)은 별도로 관리한다.', '운전 온도(℃)는 80이다.',
    '담당자는 펌프(순환 장치)를 확인한다.',
])
def test_values_units_and_parenthetical_context_are_not_aliases(line):
    assert not catalog([{'body':line}])[0]


def test_shared_alias_asks_instead_of_choosing_first():
    docs=[{'body':'건조 온도(TEMP)는 80도로 합의했다.\n냉각 온도(TEMP)는 20도로 합의했다.'}]
    q=resolve('TEMP 변경내역 알려줘',docs)
    assert '건조 온도' in q['message'] and '냉각 온도' in q['message']
    assert not resolve('건조 온도 변경내역 알려줘',docs)['message']


@pytest.mark.parametrize('abbreviation',['CZZ','MQ','PKT'])
def test_explicit_english_definition_not_a_hardcoded_abbreviation(abbreviation):
    docs=[{'body':f'입력 압력(Input Pressure, 이하 {abbreviation}) 상한은 70 kPa로 합의했다.'}]
    result=resolve(abbreviation+' 지금 얼마야?',docs)
    assert result['subjects'][0]['variants']==['입력 압력','Input Pressure',abbreviation]
    assert coverage(abbreviation+'는 70',result['terms'])==1
    assert not resolve(abbreviation+' 지금 얼마야?',[{'body':'입력 압력 상한은 70 kPa로 합의했다.'}])['subjects']


def test_change_status_predicate_is_not_a_subject():
    from work.v3.answer_meaning import validate_meaning
    q='배관 방식 용접으로 바뀌었어?'
    assert topic_terms(q)==['배관','방식','용접']
    sources=[{'id':'s1','text':'배관은 용접으로 바꾸는 검토를 요청했으나 결정하지 않았다.'}]
    result=validate_meaning([],sources,q)
    assert result and '결정하지 않았다' in result[0]['text']
    assert not validate_meaning([],sources,'배관 계약 금액 알려줘')


def test_alias_covers_all_meetings_without_changing_citations(client,monkeypatch):
    c,_=client;p=project(c,'어휘 검증 설비')
    made=[meeting(c,p,text,day) for day,text in [
        ('2026-01-01','토출 유량(분당 배출량)은 40 L로 합의했다.'),
        ('2026-01-03','분당 배출량을 60 L로 변경 합의했다.'),
        ('2026-01-05','토출 유량은 50 L로 다시 합의했다.')]]
    result=ask(c,'분당 배출량 논의한 회의록 찾아줘',project_id=p['id'])['result']
    assert result['count']==3 and {s['meeting_id'] for s in result['sources']}=={m['id'] for m in made}
    def generate(w,q,sources,**kw):
        assert all(s['query_scope']['search_terms']==[['토출유량','분당배출량']] for s in sources)
        return {'answerable':False,'points':[]}
    monkeypatch.setattr(questions,'generate',generate)
    job=ask(c,'분당 배출량 변경내역 알려줘',project_id=p['id'])
    assert len(job['result']['sources'])==3
    for s in job['result']['sources']:
        proof=c.get('/api/questions/'+job['id']+'/sources/'+s['id']).json()
        assert proof['highlight'] and all(any(l['id']==r for l in proof['lines']) for r in proof['highlight'])


def test_alias_scope_respects_date_revision_and_project(client,monkeypatch):
    c,_=client;p=project(c,'범위 검증');other=project(c,'다른 설비')
    m=meeting(c,p,'토출 유량(분당 배출량)은 40 L로 합의했다.','2026-01-01')
    meeting(c,p,'펌프 토출량(분당 배출량)은 70 L로 합의했다.','2026-02-01')
    meeting(c,other,'냉각 유량(분당 배출량)은 80 L로 합의했다.','2026-01-01')
    def generate(w,q,sources,**kw):
        assert {s['meeting_id'] for s in sources}=={m['id']}
        return {'answerable':False,'points':[]}
    monkeypatch.setattr(questions,'generate',generate)
    r=ask(c,'1월 15일 기준 분당 배출량은 얼마야?',project_id=p['id'])['result']
    assert r['answerable'] and '40' in r['points'][0]['text']
    r=ask(c,'분당 배출량은 얼마야?',project_id=p['id'])['result']
    assert r['kind']=='clarification'


def test_rejected_generation_recovers_only_matching_exact_evidence(client,monkeypatch):
    c,_=client;p=project(c,'유량 검증')
    meeting(c,p,'토출 유량(분당 배출량)은 40 L로 합의했다.')
    monkeypatch.setattr(questions,'generate',lambda w,q,ss,**kw:{'answerable':True,'points':[{'text':'유량은 999 L입니다.','sources':[ss[0]['id']]}]})
    r=ask(c,'분당 배출량은 얼마야?',project_id=p['id'])['result']
    assert r['answerable'] and '999' not in str(r['points']) and r['answer_mode']=='source_quote'
    r=ask(c,'분당 배출량 측정기 보증 기간은 얼마야?',project_id=p['id'])['result']
    assert not r['answerable']


def test_unknown_is_not_no_documents(client,monkeypatch):
    c,_=client;p=project(c,'조회 검증')
    meeting(c,p,'작업대 위치는 아직 정하지 못했다.')
    monkeypatch.setattr(questions,'generate',lambda *a,**kw:{'answerable':False,'points':[]})
    r=ask(c,'작업대 위치는 어디로 정했어?',project_id=p['id'])['result']
    assert r['answerable'] and '정하지 못했다' in r['points'][0]['text']
    monkeypatch.setattr(questions,'retrieve',lambda *a,**kw:[])
    r=ask(c,'보증 기간 알려줘',project_id=p['id'])['result']
    assert not r['answerable'] and '회의록이 없습니다' not in r['message']


def test_later_qualification_cannot_disappear_from_current_answer():
    from work.v3.answer_meaning import validate_meaning
    sources=[{'id':'S1','date':'2026-01-01','text':'출하 일정은 6월 3일로 합의했다.','query_scope':{'mode':'current','search_terms':['출하']}},
             {'id':'S2','date':'2026-02-01','text':'출하 연기는 아직 보류 중이다.'}]
    points=[{'text':'출하 일정은 6월 3일로 합의했다.','sources':['S1']}]
    answer=validate_meaning(points,sources,'출하는 언제야?')
    assert answer[0]['verification']=='source_quote' and 'S2' in answer[0]['sources']


def test_specific_meeting_decisions_without_a_named_subject(client,monkeypatch):
    c,_=client;p=project(c,'회의 범위 시험')
    meeting(c,p,'펌프 형상은 원통으로 합의했다.\n배관 변경은 승인하지 않았다.\n단열재 교체는 보류한다.\n기록 검토는 다음 주까지 완료하기로 했다.','2026-04-03')
    monkeypatch.setattr(questions,'generate',lambda *a,**kw:pytest.fail('Exact meeting statements need no generation'))
    result=ask(c,'4월 3일 회의에서 합의된 건 뭐야?',project_id=p['id'])['result']
    assert result['answerable']
    assert '원통' in str(result['points']) and '교체' not in str(result['points']) and '배관' not in str(result['points'])
    assert '완료하기로' not in str(result['points'])


def test_meeting_responsibility_is_not_routed_to_task_database(client,monkeypatch):
    c,_=client;p=project(c,'담당 조회 시험')
    meeting(c,p,'배관 검토 담당자는 아직 정하지 않았다.')
    monkeypatch.setattr(questions,'generate',lambda *a,**kw:{'answerable':False,'points':[]})
    result=ask(c,'배관 검토 담당자는 누구야?',project_id=p['id'])['result']
    assert result['answerable'] and '정하지 않았다' in str(result['points'])
