"""Month queries must filter records, never treat a date as a project name."""
import pytest
from work.v3.test_connected import client, w
from work.v3.test_questions_trash import project, meeting
from work.v3.test_question_interpretation import send, stored_result
from work.v3.test_latest_meetings import change
from work.v3.query_intent import uncertain_project
from work.v17 import questions


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(w, 'DB', tmp_path/'month.sqlite3')
    monkeypatch.setattr(w, 'FILES', tmp_path/'files')
    monkeypatch.setattr(questions, 'JOBS', {})
    class NoModel:
        def submit(self, *args): raise AssertionError('Counts/lists must not use the model')
    monkeypatch.setattr(questions, 'POOL', NoModel())


def data(c):
    p = project(c)
    july = [meeting(c, p, date=f'2026-07-{d:02}') for d in (9, 15, 23)]
    meeting(c, p, date='2026-08-20')
    return p, july


@pytest.mark.parametrize('q', [
    '7월 회의록은 몇개야?', '7월 회의록은 몇 개야?', '7월회의록몇개야?',
    '7월 회의록 찾아줘', '7월의 회의록 보여줘', '2026년 7월 회의록 찾아줘',
    '회의록 7월 목록 알려줘',
    '2026-07 회의록 찾아줘',
])
def test_reported_queries_through_conversation_api(client, q):
    c, _ = client; _, july = data(c)
    result = stored_result(send(c, q))
    assert result['answerable'], result
    if '몇' in q: assert result['count'] == 3
    else:
        assert [s['date'] for s in result['sources']] == ['2026-07-23', '2026-07-15', '2026-07-09']
        assert {s['meeting_id'] for s in result['sources']} == {m['id'] for m in july}
    assert '2026-07-01' in result['notice'] and '2026-07-31' in result['notice']


def test_permissions_trash_and_drafts_never_affect_count_or_year(client):
    c, _ = client; p, july = data(c)
    secret = project(c, '비공개 장비', members=['team1'])
    meeting(c, secret, date='2025-07-02')
    removed = meeting(c, p, date='2025-07-03')
    draft = meeting(c, p, date='2025-07-04')
    with w.connect() as db:
        removed['deleted_at'] = w.now(); w.save(db, 'meeting', removed)
        draft['registered_revision'] = None; draft['approved_revision'] = None; w.save(db, 'meeting', draft)
    c.post('/api/demo-login', json={'username': 'team2'})
    assert stored_result(send(c, '7월 회의록은 몇개야?'))['count'] == 3
    listed = stored_result(send(c, '7월 회의록 찾아줘'))
    assert {s['meeting_id'] for s in listed['sources']} == {m['id'] for m in july}


def test_missing_year_clarifies_when_accessible_years_differ(client):
    c, _ = client; p, _ = data(c); meeting(c, p, date='2025-07-09')
    ambiguous = stored_result(send(c, '7월 회의록은 몇개야?'))
    assert not ambiguous['answerable'] and '연도' in ambiguous['message']
    assert stored_result(send(c, '2026년 7월 회의록은 몇개야?'))['count'] == 3
    assert stored_result(send(c, '2025년 7월 회의록은 몇개야?'))['count'] == 1


@pytest.mark.parametrize('q', ['13월 회의록 찾아줘', '0월 회의록은 몇개야?'])
def test_invalid_month_is_date_error_not_project_error(client, q):
    c, _ = client; data(c)
    result = stored_result(send(c, q))
    assert not result['answerable'] and '월을 확인' in result['message']


def test_empty_month_count_zero(client):
    c, _ = client; data(c)
    assert stored_result(send(c, '6월 회의록은 몇개야?'))['count'] == 0
    result = stored_result(send(c, '6월 회의록 찾아줘'))
    assert not result['answerable'] and '프로젝트' not in result['message']


def test_two_months_never_silently_search_only_the_first(client):
    c, _ = client; data(c)
    result = stored_result(send(c, '7월부터 8월까지 회의록 몇개야?'))
    assert not result['answerable'] and '시작일과 종료일' in result['message']


def test_upload_basis_and_omitted_year_use_uploads_not_meeting_dates(client):
    c, _ = client; p = project(c)
    a = meeting(c, p, date='2025-07-09'); b = meeting(c, p, date='2026-01-09')
    change(a, created_at='2026-06-30T15:30:00+00:00')  # July 1 in Korea.
    change(b, created_at='2026-08-01T00:00:00+09:00')
    for q in ('7월에 등록한 회의록 몇 건이야?', '한빛셀 프로젝트 7월에 등록한 회의록은 몇개야?'):
        result = stored_result(send(c, q))
        assert result.get('count') == 1 and '등록일' in result['notice'] and '2026-07-01' in result['notice'], (q,result)
    result = stored_result(send(c, '7월에 등록한 회의록 찾아줘'))
    assert [s['meeting_id'] for s in result['sources']] == [a['id']]


def test_unknown_project_name_after_date_still_rejected():
    ps = [{'name': '한빛셀 롤프레스 1호기', 'id': 'P-001'}]
    assert uncertain_project(ps, '7월 회의록 찾아줘') is None
    assert uncertain_project(ps, '7월 없는회사 회의록 찾아줘') == []


def test_explicit_project_and_followup_scope(client):
    c, _ = client; p, _ = data(c)
    other = project(c, '서린 코팅'); meeting(c, other, date='2026-07-03')
    first = send(c, '한빛셀 7월 회의록은 몇개야?')
    assert stored_result(first)['count'] == 3
    assert stored_result(send(c, '그럼 7월 회의록 찾아줘', first['id']))['searched_meetings'] == 3
    assert stored_result(send(c, '전체 프로젝트 7월 회의록은 몇개야?'))['count'] == 4
