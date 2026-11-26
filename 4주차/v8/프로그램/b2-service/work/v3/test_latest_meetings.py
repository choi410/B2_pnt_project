"""Latest-document lookup uses stored dates and permissions, never model ranking."""
import pytest
from work.v3.test_connected import client, w
from work.v3.test_questions_trash import project, meeting
from work.v3 import question_policy as policy, conversations
from work.v17 import questions


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(w, 'DB', tmp_path/'latest.sqlite3')
    monkeypatch.setattr(w, 'FILES', tmp_path/'files')
    monkeypatch.setattr(questions, 'JOBS', {})
    class NoModel:
        def submit(self, *args):
            raise AssertionError('Document dates must not need model inference')
    monkeypatch.setattr(questions, 'POOL', NoModel())


@pytest.mark.parametrize('question,order', [
    ('제일 최신 회의록이 뭐야', 'meeting_date'),
    ('가장 최근 회의록은 무엇인가요?', 'meeting_date'),
    ('최근 회의록 보여줘', 'meeting_date'),
    ('최신 회의록', 'meeting_date'),
    ('마지막 회의록 찾아줘', 'meeting_date'),
    ('전체 프로젝트 중 제일 최신 회의록이 뭐야?', 'meeting_date'),
    ('최근 등록한 회의록 알려줘', 'registered_at'),
    ('가장 최근에 업로드된 회의록은 뭐야?', 'registered_at'),
    ('마지막으로 올린 회의록 보여줘', 'registered_at'),
])
def test_lookup_intent(question, order):
    assert policy.meeting_lookup_order(question) == order


@pytest.mark.parametrize('question', [
    '최신 회의록 요약해줘', '최근 회의록에서 납품일이 어떻게 바뀌었어?',
    '최근 회의에서 보류된 사항은?', '현재 압연 속도는 얼마야?',
    '최신 회의록과 이전 회의록 비교해줘', '프로젝트별 최신 회의록 보여줘',
])
def test_content_questions_are_not_replaced_with_a_document_title(question):
    assert policy.meeting_lookup_order(question) is None


def change(m, **fields):
    with w.connect() as c:
        current=w.read(c,'meeting',m['id']);current.update(fields);w.save(c,'meeting',current)


def ask(c, question='제일 최신 회의록이 뭐야', pid=None):
    r=c.post('/api/questions',json={'question':question,'project_id':pid})
    assert r.status_code==202, r.text
    result=r.json();assert result['state']=='done',result
    return result


def test_global_meeting_date_differs_from_upload_date_and_keeps_ties(client):
    c,_=client;p=project(c,'한빛셀 롤프레스');other=project(c,'서린 코팅라인')
    older=meeting(c,p,date='2026-11-01');a=meeting(c,p,date='2026-11-13');b=meeting(c,other,date='2026-11-13')
    change(older,created_at='2026-11-18T10:00:00+09:00')
    change(a,created_at='2026-11-17T09:00:00+09:00')
    change(b,created_at='2026-11-17T08:00:00+09:00')
    result=ask(c)['result']
    assert {s['meeting_id'] for s in result['sources']}=={a['id'],b['id']}
    assert '2건' in result['notice'] and '회의일 기준' in result['notice']
    uploaded=ask(c,'최근 등록한 회의록 알려줘')['result']
    assert [s['meeting_id'] for s in uploaded['sources']]==[older['id']]
    assert '등록일 기준' in uploaded['notice']


def test_project_lookup_source_and_analysis_not_required(client):
    c,_=client;p=project(c);m=meeting(c,p,date='2026-11-13')
    other=project(c,'다른 코팅라인');meeting(c,other,date='2026-11-17')
    change(m,analysis_state='queued')
    answer=ask(c,'롤프레스 프로젝트에서 최신 회의록 보여줘')
    assert [s['meeting_id'] for s in answer['result']['sources']]==[m['id']]
    proof=c.get('/api/questions/'+answer['id']+'/sources/S1')
    assert proof.status_code==200 and proof.json()['lines']
    assert not proof.json()['highlight'], 'A date lookup must not highlight a made-up supporting clause'


def test_hidden_and_deleted_records_never_become_the_latest(client):
    c,_=client;p=project(c);visible=meeting(c,p,date='2026-11-01')
    removed=meeting(c,p,date='2026-11-18');change(removed,deleted_at=w.now())
    private=project(c,'비공개 설비',members=['team1']);meeting(c,private,date='2026-11-19')
    archived=project(c,'휴지통 프로젝트');meeting(c,archived,date='2026-11-20')
    with w.connect() as db:
        archived['deleted_at']=w.now();w.save(db,'project',archived)
    c.post('/api/demo-login',json={'username':'team2'})
    result=ask(c)['result']
    assert [s['meeting_id'] for s in result['sources']]==[visible['id']]


def test_empty_and_unknown_dates_are_explained(client):
    c,_=client;p=project(c)
    assert not ask(c,pid=p['id'])['result']['answerable']
    missing=meeting(c,p,date='')
    undated=ask(c,pid=p['id'])['result']
    assert '최신 순서를 정할 수 없습니다' in undated['message']
    assert '최근 등록한 회의록 알려줘' in undated['message']
    assert ask(c,'최근 등록한 회의록 알려줘',p['id'])['result']['sources'][0]['meeting_id']==missing['id']
    known=meeting(c,p,date='2026-11-12')
    result=ask(c,pid=p['id'])['result']
    assert [s['meeting_id'] for s in result['sources']]==[known['id']]
    assert '회의일 미정 1건' in result['notice']


def test_registration_timestamps_compare_instants(client):
    c,_=client;p=project(c);a=meeting(c,p,date='2026-11-12');b=meeting(c,p,date='2026-11-13')
    change(a,created_at='2026-11-18T00:30:00+09:00')
    change(b,created_at='2026-11-17T16:00:00+00:00')
    result=ask(c,'최근 등록한 회의록 알려줘',p['id'])['result']
    assert [s['meeting_id'] for s in result['sources']]==[b['id']]


def test_conversation_lookup_does_not_inherit_old_spec_or_cutoff(client):
    c,_=client;p=project(c);m=meeting(c,p,date='2026-11-13')
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        previous={'context':{'project_ids':[p['id']],'subject':'압연 속도','time_scope':{'mode':'as_of','end':'2026-11-11'}}}
        context=conversations.resolve_question(w,db,actor,'그럼 제일 최신 회의록이 뭐야?',previous)
        assert context['query']=='그럼 제일 최신 회의록이 뭐야?'
        assert context['subject']=='' and context['time_scope']['end'] is None
    first=c.post('/api/conversations/questions',json={'question':p['id']+' 프로젝트 찾아줘'}).json()
    second=c.post('/api/conversations/questions',json={'question':'그럼 제일 최신 회의록이 뭐야?','conversation_id':first['id']}).json()
    message=second['messages'][-1]
    assert message['state']=='done' and message['result']['mode']=='meeting_lookup'
    assert m['title'] in message['result']['points'][0]['text']
    proof=c.get('/api/conversations/'+first['id']+'/messages/'+message['id']+'/sources/S1')
    assert proof.status_code==200 and proof.json()['lines']
