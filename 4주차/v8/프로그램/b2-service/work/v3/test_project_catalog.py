"""Project inventory questions must use records, including projects without minutes."""
import pytest
from work.v3.test_connected import client, w
from work.v3.test_questions_trash import project, meeting
from work.v3.test_project_order import stamp
from work.v3.query_intent import metadata_plan
from work.v17 import questions


@pytest.fixture(autouse=True)
def no_generation(monkeypatch):
    monkeypatch.setattr(questions, 'JOBS', {})
    class NoModel:
        def submit(self, *args):
            raise AssertionError('Project inventory must not enter document RAG')
    monkeypatch.setattr(questions, 'POOL', NoModel())


def send(c, question, cid=None):
    response = c.post('/api/conversations/questions', json={
        'question': question, 'conversation_id': cid})
    assert response.status_code == 202, response.text
    thread = response.json()
    message = thread['messages'][-1]
    assert message['state'] == 'done', message
    return thread, message['result']


@pytest.mark.parametrize('question', [
    '현재 프로젝트 뭐뭐있어?', '현재 프로젝트 뭐 뭐 있어?',
    '지금 프로젝트 뭐가 있어?', '프로젝트 뭐 있어?',
    '프로젝트들이 뭐가 있나요?', '어떤 프로젝트들이 있어?',
    '무슨 프로젝트가 있나요?', '등록된 프로젝트 전부 보여줘',
    '우리 프로젝트 뭐뭐 있어?', '등록되어 있는 프로젝트 목록 알려줘',
    '현재 프로잭트 뭐뭐있어?', '프로젝트 뭐뭐 있는지 알려줘',
])
def test_catalog_uses_every_accessible_project_not_meeting_corpus(client, question):
    c, _ = client
    a = project(c, '목록 검증 롤프레스')
    b = project(c, '회의록 없는 슬리터')
    stamp(a, '2026-11-01T09:00:00+09:00')
    stamp(b, '2026-11-02T09:00:00+09:00')
    meeting(c, a, '회의명과 프로젝트명은 다른 정보다.')
    private = project(c, '접근 불가 설비', members=['team1'])
    deleted = project(c, '삭제된 설비')
    with w.connect() as db:
        deleted['deleted_at'] = w.now()
        w.save(db, 'project', deleted)
    c.post('/api/demo-login', json={'username': 'team2'})
    _, result = send(c, question)
    assert result['kind'] == 'projects'
    assert result['mode'] == 'project_list'
    assert [p['id'] for p in result['projects']] == [b['id'], a['id']]
    assert result['count'] == result['total_count'] == 2
    assert result['points'] == result['sources'] == []
    assert '총 2개' in result['message']
    assert private['id'] not in result['result_project_ids']


@pytest.mark.parametrize('question', [
    '현재 프로젝트 변경사항 뭐뭐 있어?', '프로젝트의 납기 문제 뭐가 있어?',
    '진행 중인 프로젝트가 뭐뭐 있어?', '완료된 프로젝트 뭐가 있어?',
    '프로젝트 뭐가 잘못됐어?', '현재 선택한 프로젝트가 뭐야?',
    '프로젝트 위험요소 뭐뭐 있어?', '프로젝트에 필요한 게 뭐야?',
])
def test_content_or_unimplemented_filters_do_not_become_inventory(question):
    assert metadata_plan(question) is None


def test_catalog_after_named_project_and_explicit_count_followup(client):
    c, _ = client
    a = project(c, '한빛셀 롤프레스')
    b = project(c, '서린 코팅라인')
    thread, first = send(c, a['id']+' 프로젝트 찾아줘')
    assert [p['id'] for p in first['projects']] == [a['id']]
    thread, catalog = send(c, '현재 프로젝트 뭐뭐있어?', thread['id'])
    assert {p['id'] for p in catalog['projects']} == {a['id'], b['id']}
    _, count = send(c, '그럼 프로젝트는 총 몇 개야?', thread['id'])
    assert count['count'] == 2 and count['sources'] == []


def test_limited_catalog_reports_total_and_empty_catalog_stays_empty(client):
    c, _ = client
    for name in ('목록 가', '목록 나', '목록 다'):
        project(c, name, members=['team1'])
    _, result = send(c, '프로젝트 2개만 보여줘')
    assert len(result['projects']) == result['count'] == 2
    assert result['total_count'] == 3 and '총 3개 중 2개' in result['message']
    c.post('/api/demo-login', json={'username': 'team2'})
    _, result = send(c, '현재 프로젝트 뭐뭐있어?')
    assert not result['projects'] and result['count'] == 0
    assert result['sources'] == []
