"""Conversation behavior, permissions and evidence are checked in a disposable DB."""
import pytest
from work.v3.test_connected import client, w
from work.v3.test_question_scope import speed_history, change
from work.v3.test_questions_trash import meeting
from work.v3 import conversations, question_policy
from work.v17 import questions
from work.v17.retrieval import registered_document


@pytest.fixture(autouse=True)
def isolated_chat_database(tmp_path, monkeypatch):
    monkeypatch.setattr(w, 'DB', tmp_path/'chat.sqlite3')
    monkeypatch.setattr(w, 'FILES', tmp_path/'files')
    monkeypatch.setattr(questions, 'JOBS', {})


def setup_chat(c, monkeypatch):
    p, a, b, d = speed_history(c)
    captured = []
    def quick(w, db, ps, actor, q, pid, plan):
        captured.append((q, pid, plan))
        doc = registered_document(w.read(db, 'meeting', d['id']))
        source = {k: v for k, v in doc.items() if k != 'body'} | {
            'id': 'S1', 'project_name': p['name'], 'line_ids': [d['lines'][-1]['id']], 'text': d['lines'][-1]['text']}
        return {'kind': 'documents', 'points': [{'project_id': p['id'], 'project_name': p['name'],
            'text': '135 m/min으로 합의했습니다.', 'sources': ['S1']}], 'sources': [source]}
    monkeypatch.setattr(question_policy, 'quick_answer', quick)
    return p, d, captured


def send(c, q, p=None, cid=None):
    response = c.post('/api/conversations/questions', json={'question': q, 'project_id': p, 'conversation_id': cid})
    assert response.status_code == 202, response.text
    return response.json()


def test_followup_uses_subject_and_project_but_not_generated_fact(client, monkeypatch):
    c, _ = client
    p, _, captured = setup_chat(c, monkeypatch)
    first = send(c, '현재 압연 속도는 얼마야?', p['id'])
    second = send(c, '왜 바뀐 거야?', cid=first['id'])
    assert len(second['messages']) == 2
    assert second['messages'][-1]['question'] == '왜 바뀐 거야?'
    assert captured[-1][1] == p['id']
    assert '압연 속도' in captured[-1][0]
    assert '135' not in captured[-1][0], 'A prior generated number is not injected as evidence'
    # History survives the question engine's in-memory cache being cleared.
    with questions.LOCK:
        questions.JOBS.clear()
    restored = c.get('/api/conversations/'+first['id']).json()
    assert len(restored['messages']) == 2
    assert restored['messages'][0]['result']['points']


def test_followup_date_and_explicit_current_reset(client, monkeypatch):
    c, _ = client
    p, _, captured = setup_chat(c, monkeypatch)
    first = send(c, '2026-11-11 기준 압연 속도는 얼마야?', p['id'])
    send(c, '왜 그렇게 정했어?', cid=first['id'])
    assert captured[-1][2]['end'] == '2026-11-11'
    send(c, '그럼 현재는 얼마야?', cid=first['id'])
    assert captured[-1][2]['mode'] == 'current'
    assert captured[-1][2]['end'] is None
    send(c, '11월 11일에는 얼마였어?', cid=first['id'])
    assert captured[-1][2]['end'] == '2026-11-11'


def test_new_attribute_does_not_reuse_old_topic(client, monkeypatch):
    c, _ = client
    p, _, captured = setup_chat(c, monkeypatch)
    first = send(c, '현재 압연 속도는 얼마야?', p['id'])
    send(c, '보증 기간은 얼마야?', cid=first['id'])
    assert '압연 속도' not in captured[-1][0]
    # Starting a new conversation never inherits the previous project's subject.
    fresh = send(c, '프로젝트 찾아줘')
    assert fresh['id'] != first['id']
    assert captured[-1][0] == '프로젝트 찾아줘'


def test_private_history_and_delete_only_chat_records(client, monkeypatch):
    c, _ = client
    p, _, _ = setup_chat(c, monkeypatch)
    first = send(c, '현재 압연 속도는 얼마야?', p['id'])
    with w.connect() as db:
        before = [(row['kind'], row['id'], row['payload']) for row in db.execute("SELECT * FROM records WHERE kind NOT IN ('ai_conversation','ai_message') ORDER BY kind,id")]
    c.post('/api/demo-login', json={'username': 'team2'})
    assert c.get('/api/conversations/'+first['id']).status_code == 404
    assert c.delete('/api/conversations/'+first['id']).status_code == 404
    assert not any(x['id'] == first['id'] for x in c.get('/api/conversations').json()['items'])
    c.post('/api/demo-login', json={'username': 'team1'})
    assert c.delete('/api/conversations/'+first['id']).status_code == 200
    assert c.get('/api/conversations/'+first['id']).status_code == 404
    with w.connect() as db:
        after = [(row['kind'], row['id'], row['payload']) for row in db.execute("SELECT * FROM records WHERE kind NOT IN ('ai_conversation','ai_message') ORDER BY kind,id")]
        assert not any(m['conversation_id'] == first['id'] for m in w.all_records(db, 'ai_message'))
    assert after == before


def test_source_retains_exact_revision_and_checks_access(client, monkeypatch):
    c, _ = client
    p, meeting_record, _ = setup_chat(c, monkeypatch)
    first = send(c, '현재 압연 속도는 얼마야?', p['id'])
    message = first['messages'][0]
    url='/api/conversations/'+first['id']+'/messages/'+message['id']+'/sources/S1'
    with questions.LOCK:
        questions.JOBS.clear()
    proof = c.get(url)
    assert proof.status_code == 200, proof.text
    assert proof.json()['highlight']
    assert any('135 m/min' in row['text'] for row in proof.json()['lines'])
    with w.connect() as db:
        m=w.read(db,'meeting',meeting_record['id'])
        m['revision']+=1
        m['revisions'].append({**m['revisions'][-1],'number':m['revision'],'body':'새 본문으로 변경됨'})
        w.save(db,'meeting',m)
    assert c.get(url).json()['revision'] == 1, 'Prior answers keep their original source revision'
    c.post('/api/demo-login', json={'username':'team2'})
    assert c.get(url).status_code == 404
    c.post('/api/demo-login', json={'username':'team1'})
    with w.connect() as db:
        record=w.read(db,'project',p['id']);record['members']=[];w.save(db,'project',record)
    assert c.get(url).status_code == 403
    assert 'result' not in c.get('/api/conversations/'+first['id']).json()['messages'][0]


def test_pending_delete_blocked_and_restart_recovers_failure(client, monkeypatch):
    c, _ = client
    p, _, _ = setup_chat(c, monkeypatch)
    monkeypatch.setattr(question_policy,'quick_answer',lambda *args:None)
    monkeypatch.setattr(conversations,'watch',lambda *args:None)
    class Queue:
        def submit(self,*args):pass
    monkeypatch.setattr(questions,'POOL',Queue())
    first=send(c,'압연 속도 변경 경위는?',p['id'])
    assert first['messages'][0]['state']=='queued'
    assert c.delete('/api/conversations/'+first['id']).status_code==409
    with questions.LOCK:questions.JOBS.clear()
    recovered=c.get('/api/conversations/'+first['id']).json()
    assert recovered['messages'][0]['state']=='failed'
    assert '재시작' in recovered['messages'][0]['error']
    assert c.delete('/api/conversations/'+first['id']).status_code==200


def test_unknown_followup_requests_clarification(client, monkeypatch):
    c,_=client
    p,_,captured=setup_chat(c,monkeypatch)
    first=send(c,'프로젝트 찾아줘',p['id'])
    count=len(captured)
    second=send(c,'그건 왜 바뀐 거야?',cid=first['id'])
    assert len(captured)==count
    assert second['messages'][-1]['result']['kind']=='clarification'
    assert '어떤 항목' in second['messages'][-1]['result']['message']


def test_rename_persists_without_reordering_or_changing_messages(client, monkeypatch):
    c,_=client;p,_,_=setup_chat(c,monkeypatch)
    first=send(c,'현재 압연 속도는 얼마야?',p['id'])
    other=send(c,'현재 압연 속도는 얼마야?',p['id'])
    before_order=[t['id'] for t in c.get('/api/conversations').json()['items']]
    with w.connect() as db:
        before_rows=[tuple(row) for row in db.execute("SELECT kind,id,payload FROM records WHERE kind!='ai_conversation' ORDER BY kind,id")]
        activity=w.read(db,'ai_conversation',first['id'])['activity']
    response=c.patch('/api/conversations/'+first['id'],json={'title':'  롤프레스   속도 확인  '})
    assert response.status_code==200 and response.json()['title']=='롤프레스 속도 확인'
    restored=c.get('/api/conversations/'+first['id']).json()
    assert restored['title']=='롤프레스 속도 확인' and restored['messages']==first['messages']
    assert restored['updated_at']==first['updated_at']
    assert [t['id'] for t in c.get('/api/conversations').json()['items']]==before_order
    with w.connect() as db:
        assert w.read(db,'ai_conversation',first['id'])['activity']==activity
        assert [tuple(row) for row in db.execute("SELECT kind,id,payload FROM records WHERE kind!='ai_conversation' ORDER BY kind,id")]==before_rows
    followed=send(c,'왜 바뀐 거야?',cid=first['id'])
    assert followed['title']=='롤프레스 속도 확인' and len(followed['messages'])==2
    assert c.get('/api/conversations/'+other['id']).json()['title']==other['title']


def test_rename_ownership_and_empty_or_long_title(client, monkeypatch):
    c,_=client;p,_,_=setup_chat(c,monkeypatch)
    first=send(c,'현재 압연 속도는 얼마야?',p['id']);url='/api/conversations/'+first['id']
    for value in ('','   ','가'*61):
        assert c.patch(url,json={'title':value}).status_code==422
    assert c.patch(url,json={'title':'허용 이름','user_id':'team2'}).status_code==422
    c.post('/api/demo-login',json={'username':'team2'})
    assert c.patch(url,json={'title':'다른 사람의 대화 변경'}).status_code==404
    c.post('/api/demo-login',json={'username':'team1'})
    assert c.get(url).json()['title']==first['title']
    assert c.patch(url,json={'title':'가'*60}).status_code==200
