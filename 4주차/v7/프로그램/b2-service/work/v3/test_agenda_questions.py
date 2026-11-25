"""Agenda vocabulary, whole-section evidence, scope and source provenance."""
import pytest
from work.v3.test_connected import client, w
from work.v3.test_questions_trash import project
from work.v3 import agenda_questions as agenda, conversations
from work.v3.query_intent import metadata_plan, unresolved_metadata
from work.v3.topic_search import search_intent
from work.v17 import questions
from work.v17.retrieval import registered_document, document_lines


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(w, 'DB', tmp_path / 'agenda.sqlite3')
    monkeypatch.setattr(w, 'FILES', tmp_path / 'files')
    monkeypatch.setattr(questions, 'JOBS', {})
    class Inline:
        def submit(self, fn, *args): fn(*args)
    monkeypatch.setattr(questions, 'POOL', Inline())
    monkeypatch.setattr(questions, 'retrieve', lambda *args, **kw: pytest.fail('Agenda must read whole sections'))


@pytest.mark.parametrize('q', [
    'aa프로젝트 아젠다가 뭐야?', 'aa 프로젝트 어젠다는 뭐야?',
    'aa 프로젝트 agenda 알려줘', 'aa 프로젝트 안건은 뭐야?',
    'aa 프로젝트 주요 논의 주제 보여줘', 'aa 최신 회의록 아젠다 보여줘',
    'aa 프로젝트 2026년 11월 1일 회의의 안건은 뭐야?',
])
def test_agenda_wordings(q):
    ps = [{'name': 'aa', 'id': 'P-001'}]
    assert agenda.intent(q, ps)
    assert not metadata_plan(q, ps) and not unresolved_metadata(q, ps)
    assert not search_intent(q, ps)


@pytest.mark.parametrize('q', [
    'aa프로젝트 이전 납기 뭐야?', 'aa 프로젝트 최신 회의록 뭐야?',
    'aa 프로젝트 카메라 안건 담당자는 누구야?', 'aa 프로젝트 안건은 승인됐어?',
    'aa 프로젝트 아젠다가 무슨 뜻이야?',
])
def test_other_intents_not_hijacked(q):
    assert not agenda.intent(q, [{'name': 'aa'}])


def ask(c, q, **kw):
    r = c.post('/api/questions', json={'question': q, **kw})
    assert r.status_code == 202, r.text
    r = c.get('/api/questions/' + r.json()['id'])
    assert r.json()['state'] == 'done', r.text
    return r.json()


def meeting(c, p, text, date='2026-11-01'):
    content = f'회의명: {date} 협의\n회의일: {date}\n프로젝트: {p["name"]}\n{text}'
    item = c.post('/api/v3/imports', files=[('files', ('회의.txt', content.encode(), 'text/plain'))]).json()['items'][0]
    r = c.post('/api/v3/register', json={'items': [{'id': item['id'], 'project_id': p['id'], 'date': date, 'confirmed': True}]})
    assert r.status_code == 202 and r.json()['registered'], r.text
    with w.connect() as db:
        m = w.read(db, 'meeting', r.json()['registered'][0]['id'])
        m['analysis_state'] = 'ready'; w.save(db, 'meeting', m)
    return m


def test_whole_agenda_across_meetings_and_source_ids(client, monkeypatch):
    c, _ = client; p = project(c, 'aa')
    a = meeting(c, p, '회의 안건\n1. 모터 용량\n2. 안전 커버\n3. 검사 방식\n4. 열매유 배치\n논의 내용\n모터는 검토 중이다.', '2026-11-01')
    b = meeting(c, p, '## Agenda\n- MES 연동\n- 카메라 공간\n결정 사항\n카메라는 결정하지 않았다.', '2026-11-03')
    seen = []
    def generate(w, q, sources, **kw):
        seen.extend(sources)
        assert '아젠다' not in q and '주요 안건' in q
        return {'answerable': False, 'points': []}  # Explicit lists remain usable.
    monkeypatch.setattr(questions, 'generate', generate)
    job = ask(c, 'aa프로젝트 아젠다가 뭐야?')
    assert job['result']['answerable']
    assert {s['meeting_id'] for s in seen} == {a['id'], b['id']}
    assert '4. 열매유 배치' in next(s['text'] for s in seen if s['meeting_id'] == a['id'])
    assert all('검토 중' not in s['text'] and '결정하지' not in s['text'] for s in seen)
    for s in seen:
        doc = registered_document(a if s['meeting_id'] == a['id'] else b)
        originals = {l['id']: l['text'] for l in document_lines(doc)}
        assert s['text'] == '\n'.join(originals[i] for i in s['line_ids'])
        proof = c.get('/api/questions/' + job['id'] + '/sources/' + s['id'])
        assert proof.status_code == 200 and proof.json()['highlight']


def test_scoped_dates_latest_private_deleted_and_draft(client, monkeypatch):
    c, _ = client; p = project(c, 'aa'); secret = project(c, '기밀', ['team1'])
    a = meeting(c, p, '회의 안건\n1. 모터 용량\n논의 내용\n검토 중이다.', '2026-11-01')
    b = meeting(c, p, '회의 안건\n1. 커버 변경\n논의 내용\n검토 중이다.', '2026-11-03')
    hidden = meeting(c, secret, '회의 안건\n1. 기밀 사양', '2026-11-05')
    trashed = meeting(c, p, '회의 안건\n1. 삭제 자료', '2026-11-06')
    with w.connect() as db:
        trashed['deleted_at'] = w.now(); w.save(db, 'meeting', trashed)
        b['revisions'].append({**b['revisions'][-1], 'number': 2, 'body': '회의 안건\n1. 미등록 초안'})
        b['revision'] = 2; w.save(db, 'meeting', b)
    c.post('/api/demo-login', json={'username': 'team2'})
    monkeypatch.setattr(questions, 'generate', lambda *args, **kw: {'answerable': False, 'points': []})
    all_result = ask(c, '전체 프로젝트 아젠다가 뭐야?')['result']
    assert {s['meeting_id'] for s in all_result['sources']} == {a['id'], b['id']}
    assert '미등록 초안' not in str(all_result)
    latest = ask(c, 'aa 프로젝트 최신 회의록 아젠다가 뭐야?')['result']
    assert [s['meeting_id'] for s in latest['sources']] == [b['id']]
    dated = ask(c, 'aa 프로젝트 2026년 11월 1일 회의의 안건은 뭐야?')['result']
    assert [s['meeting_id'] for s in dated['sources']] == [a['id']]
    selected = ask(c, 'aa 프로젝트 안건은 뭐야?', meeting_ids=[a['id']])['result']
    assert [s['meeting_id'] for s in selected['sources']] == [a['id']]


def test_no_template_required_and_old_subject_not_inherited(client, monkeypatch):
    c, _ = client; p = project(c, 'aa')
    meeting(c, p, '안전 커버 통로 간섭을 검토했다.\n고객은 표면 검사 공간 확보를 요청했다.')
    def generate(w, q, sources, **kw):
        assert all(not s['agenda_explicit'] for s in sources)
        assert '표면 검사 공간' in sources[0]['text']
        return {'answerable': True, 'points': [{'text': '논의 주제는 안전 커버 간섭과 표면 검사 공간 확보입니다.', 'sources': [sources[0]['id']]}]}
    monkeypatch.setattr(questions, 'generate', generate)
    assert ask(c, 'aa 프로젝트 주요 안건 알려줘')['result']['answerable']
    previous = {'question': 'aa 납기 뭐야?', 'context': {'project_ids': [p['id']], 'subject': '납기', 'query': 'aa 납기 뭐야?'}, 'job': {'result': {}}}
    with w.connect() as db:
        context = conversations.resolve_question(w, db, w.read(db, 'person', 'team1'), '그럼 아젠다는 뭐야?', previous=previous)
    assert context['project_ids'] == [p['id']] and '납기' not in context['query']


def test_missing_records_do_not_fabricate_agenda(client, monkeypatch):
    c, _ = client; project(c, 'aa')
    monkeypatch.setattr(questions, 'generate', lambda *args, **kw: pytest.fail('No evidence'))
    assert not ask(c, 'aa프로젝트 아젠다가 뭐야?')['result']['answerable']


def test_summary_fallback_preserves_decisions_from_the_selected_meeting(client, monkeypatch):
    from work.v3.test_conversations import send
    c, _ = client
    p = project(c, '해든 시험 장비')
    meeting(c, p, '결정 사항\n검사 주기는 25초로 합의했다.', '2026-11-01')
    decisions = [
        '검사 주기는 30초로 합의했다.',
        '온도 상향 요청은 보류하고',
        '기존 온도 80 ℃를 유지한다.',
    ]
    selected = meeting(c, p, '## 합의 사항\n' + '\n'.join(decisions)
                       + '\n후속 조치\n담당자는 검토 자료를 공유한다.', '2026-11-03')
    meeting(c, p, '결정 사항\n검사 주기는 40초로 합의했다.', '2026-12-01')

    def generate(w, q, sources, **kw):
        assert [s['meeting_id'] for s in sources] == [selected['id']]
        return {'answerable': True, 'points': [{'text': '검사 주기는 999초로 합의했다.',
                                                'sources': [sources[0]['id']]}]}
    monkeypatch.setattr(questions, 'generate', generate)
    thread = send(c, '해든 2026년 11월 회의록 보여줘')
    reply = send(c, '그중 나중 회의 핵심만 정리해줘.', cid=thread['id'])
    message = reply['messages'][-1]
    result = message['result']
    assert result['answer_mode'] == 'source_quote'
    assert result['points'][0]['text'].endswith('\n'.join(decisions))
    assert '결정 사항 원문을 표시했습니다' in result['notice']
    proof = c.get(f"/api/conversations/{thread['id']}/messages/{message['id']}/sources/{result['sources'][0]['id']}")
    assert proof.status_code == 200
    data = proof.json()
    assert data['meeting_id'] == selected['id']
    assert [line['text'] for line in data['lines'] if line['id'] in data['highlight']] == decisions


def test_source_invalidated_after_deletion(client, monkeypatch):
    c, _ = client; p = project(c, 'aa'); m = meeting(c, p, '회의 안건\n1. 안전 커버')
    monkeypatch.setattr(questions, 'generate', lambda *args, **kw: {'answerable': False, 'points': []})
    job = ask(c, 'aa프로젝트 아젠다가 뭐야?')
    with w.connect() as db: m['deleted_at'] = w.now(); w.save(db, 'meeting', m)
    assert c.get('/api/questions/' + job['id']).json()['state'] == 'failed'
    assert c.get('/api/questions/' + job['id'] + '/sources/S1').status_code == 409


def test_followup_reads_all_recorded_decisions_from_selected_meeting(client, monkeypatch):
    from work.v3.test_conversations import send
    c,_ = client
    p = project(c,'새해솔 검사 장비')
    kept = '시험 압력은 2.5 kPa로 유지한다.'
    approved = 'FAT 일정은 2026.09.18 본사로 결정했다.'
    pending = '측정 오차 원인은 다음 회의에서 결정한다.'
    chosen = meeting(c,p,'결정 사항\n'+'\n'.join([kept,approved,pending]),'2026-08-17')
    meeting(c,p,'결정 사항\n시험 압력은 3.8 kPa로 확정했다.','2026-09-01')
    monkeypatch.setattr(questions,'generate',lambda *a,**kw:pytest.fail('Read decisions from the selected original meeting'))
    thread = send(c,'2026년 8월 회의록 보여줘')
    thread = send(c,'그 회의에서 합의한 내용은?',cid=thread['id'])
    message = thread['messages'][-1]
    result = message['result']
    answer = result['points'][0]['text']
    assert all(text.rstrip('.') in answer for text in (kept,approved))
    assert '측정 오차' not in answer and '3.8' not in answer
    proof = c.get(f"/api/conversations/{thread['id']}/messages/{message['id']}/sources/{result['sources'][0]['id']}")
    assert proof.status_code==200
    payload = proof.json()
    assert payload['meeting_id']==chosen['id']
    assert [row['text'] for row in payload['lines'] if row['id'] in payload['highlight']]==[kept,approved]
