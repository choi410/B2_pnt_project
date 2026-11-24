"""Paraphrased value questions: ledger routing, missing-item clarification, query text."""
import pytest
from work.v3.test_connected import client,w
from work.v3.test_project_catalog import send
from work.v3.test_change_queries import seed
from work.v3 import change_queries
from work.v3.content_query import prepare
from work.v17.retrieval import query_text


@pytest.mark.parametrize('question',[
    '롤프레스 최근 변경 수치 얼마야','롤프레스 최근 바뀐 값 알려줘','롤프레스 변경된 수치 보여줘',
])
def test_recent_value_change_reads_the_ledger_newest_first(client,question):
    c,_=client;a,b=seed(c)
    _,r=send(c,question)
    assert r['mode']=='change_history' and r['result_project_ids']==[a['id']]
    dates=[e['date'] for e in r['change_items']]
    assert dates==sorted(dates,reverse=True) and dates[0]=='2026-11-13'
    assert any(e['after']=='135 m/min' for e in r['change_items'])
    assert b['name'] not in str(r)


def test_value_change_with_named_attribute_keeps_source_reader(client):
    c,_=client;seed(c)
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        assert change_queries.resolve(w,db,actor,'한빛셀 압연 속도 최근 변경 수치') is None


@pytest.mark.parametrize('question',['최근 등록된 회의록 보여줘','최근 회의에서 왜 바뀌었어','속도 얼마야'])
def test_other_questions_are_not_captured_by_value_wording(question):
    assert not change_queries.intent(question)


@pytest.mark.parametrize('question',['한빛셀 수치 얼마야','한빛셀 값 알려줘','한빛셀 숫자 뭐야'])
def test_value_without_item_asks_for_the_item(question):
    ps=[{'id':'p','name':'한빛셀'}]
    docs=[{'body':'압연 속도: 120 m/min으로 합의했다.\n코팅폭: 650 mm로 유지한다.'}]
    result=prepare(question,ps,docs)
    assert '어떤 항목' in result['message']
    assert '압연 속도' in result['message'] and '코팅폭' in result['message']


@pytest.mark.parametrize('question',['한빛셀 압연 속도 수치 얼마야','한빛셀 코팅폭 값 알려줘','한빛셀 압연 속도 변경 이력'])
def test_value_with_item_is_answered_normally(question):
    ps=[{'id':'p','name':'한빛셀'}]
    docs=[{'body':'압연 속도: 120 m/min으로 합의했다.\n코팅폭: 650 mm로 유지한다.'}]
    assert not prepare(question,ps,docs)['message']


def test_query_vector_text_keeps_terms_and_question():
    assert query_text(['압연','속도'],'압연 속도 최근에 얼마로 바뀌었어')=='압연 속도\n압연 속도 최근에 얼마로 바뀌었어'
    assert query_text([['압연속도','rolling speed'],'변경'],'q')=='압연속도 / rolling speed 변경\nq'
    assert query_text([],'수치 얼마야')=='수치 얼마야'
    assert query_text(['수치'],'수치')=='수치'
