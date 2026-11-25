"""Equivalent wording shares evidence; different attributes remain distinct."""
import pytest
from work.v3.test_connected import client,w
from work.v3.test_questions_trash import project,meeting
from work.v3.content_query import prepare
from work.v3.question_scope import plan_question,in_scope
from work.v3.answer_meaning import validate_meaning,unsupported_decision
from work.v17 import questions,retrieval
from work.v17.evidence_text import topic_terms


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


def test_rotational_and_transfer_speed_cannot_borrow_rolling_speed():
    sources=[{'id':'S1','date':'2026-11-13','text':'압연 속도는 135 m/min으로 합의했다.'}]
    for subject in ('회전 속도','이송 속도'):
        assert validate_meaning([{'text':subject+'는 135 m/min입니다.','sources':['S1']}],sources,subject+'는 얼마야?')==[]


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
