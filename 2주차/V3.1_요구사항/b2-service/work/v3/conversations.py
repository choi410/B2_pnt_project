"""Private conversation history around the existing source-grounded question engine."""
from copy import deepcopy
import re
import threading
import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from work.v17 import questions
from work.v17.retrieval import revision_document, document_lines
from work.v3 import question_policy as policy
from work.v3.question_scope import plan_question

CHAT_LOCK = threading.RLock()
TERMINAL = {'done', 'failed'}


class ChatQuestion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    conversation_id: str | None = Field(default=None, max_length=80)
    project_id: str | None = Field(default=None, max_length=80)
    meeting_id: str | None = Field(default=None, max_length=80)
    question: str = Field(min_length=2, max_length=500)


class RenameConversation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=60)


def own_thread(w, c, cid, actor):
    thread = w.read(c, 'ai_conversation', cid)
    if thread['user_id'] != actor['id']:
        raise HTTPException(404, '대화를 찾을 수 없습니다.')
    return thread


def messages(w, c, cid):
    return sorted((m for m in w.all_records(c, 'ai_message') if m['conversation_id'] == cid),
                  key=lambda m: m['sequence'])


def sync_message(w, mid):
    with CHAT_LOCK, w.connect() as c:
        try:
            message = w.read(c, 'ai_message', mid)
        except HTTPException:
            return None
        if message['state'] in TERMINAL:
            return message
        with questions.LOCK:
            job = deepcopy(questions.JOBS.get(message['job']['id']))
        if not job:
            job = {**message['job'], 'state': 'failed',
                   'error': '서버가 재시작되어 답변이 중단되었습니다. 같은 질문을 다시 보내 주세요.'}
        if job['state'] != message['state'] or job.get('result') != message['job'].get('result'):
            message.update(job=job, state=job['state'])
            if job['state'] in TERMINAL:
                message['completed_at'] = w.now()
            w.save(c, 'ai_message', message)
        return message


def watch(w, mid):
    def run():
        while True:
            try:
                m = sync_message(w, mid)
                if not m or m['state'] in TERMINAL:
                    return
            except Exception:
                # A later history read can synchronize again after a transient DB lock.
                return
            time.sleep(.5)
    threading.Thread(target=run, name='b2-chat-save', daemon=True).start()


def subject_in(question, titles):
    q = policy.clean(question)
    exact = [title for title in titles if policy.clean(title) in q]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return ''
    # Match a complete attribute, never the answer's numerical value.
    aliases = (('납품일', '납기일', '납기'), ('압연속도', '속도'),
               ('점검커버', '커버'), ('출하일',), ('검수일',), ('가압력',), ('코팅폭',))
    found = set()
    for group in aliases:
        if any(word in q for word in group):
            found.update(title for title in titles if any(word in policy.clean(title) for word in group))
    if len(found) == 1:
        return found.pop()
    matches = []
    for title in titles:
        tokens = [policy.clean(x) for x in title.split() if len(x) >= 2]
        if len(tokens) >= 2 and sum(token in q for token in tokens) >= 2:
            matches.append(title)
    return matches[0] if len(matches) == 1 else ''


def resolve_question(w, c, actor, question, previous=None, project_id=None, meeting_id=None):
    from work.v3.conversation_context import resolve
    from work.v3 import conversation_followups as followups
    context=followups.resolve(w,c,actor,question,previous,project_id,meeting_id)
    if context is not None:return context
    context=resolve(w,c,actor,question,previous,project_id,meeting_id)
    return followups.remember(context,question,followups.available_projects(w,c,actor),project_id,previous)


def public_message(w, c, message, actor):
    job = message['job']
    public = {k: message.get(k) for k in ('id', 'question', 'state', 'created_at', 'completed_at')}
    public['context_label'] = message.get('context', {}).get('label', '')
    try:
        for pid in job.get('scope_ids', []):
            w.project(c, pid, actor)
    except HTTPException:
        return {**public, 'state': 'failed', 'error': '이 대화의 프로젝트에 현재 접근할 수 없습니다.'}
    public['error'] = job.get('error', '')
    if job.get('result'):
        result = deepcopy(job['result'])
        result['sources'] = [{k: s[k] for k in ('id', 'project_id', 'project_name', 'title', 'date') if k in s}
                             for s in result.get('sources', [])]
        public['result'] = result
    return public


def build_router(w, question_router):
    r = APIRouter(prefix='/api/conversations')
    ask = next(route.endpoint for route in question_router.routes if route.path == '/api/questions' and 'POST' in route.methods)

    @r.get('')
    def listing(actor=Depends(w.user)):
        with w.connect() as c:
            pending = [m['id'] for m in w.all_records(c, 'ai_message') if m['user_id'] == actor['id'] and m['state'] not in TERMINAL]
        for mid in pending:
            sync_message(w, mid)
        with w.connect() as c:
            own = [t for t in w.all_records(c, 'ai_conversation') if t['user_id'] == actor['id']]
            ms = [m for m in w.all_records(c, 'ai_message') if m['user_id'] == actor['id']]
            return {'items': [{k: t[k] for k in ('id', 'title', 'created_at', 'updated_at')} |
                             {'pending': any(m['conversation_id'] == t['id'] and m['state'] not in TERMINAL for m in ms)}
                             for t in sorted(own, key=lambda t: t.get('activity', 0), reverse=True)]}

    @r.get('/{cid}')
    def detail(cid, actor=Depends(w.user)):
        with w.connect() as c:
            thread = own_thread(w, c, cid, actor)
            pending = [m['id'] for m in messages(w, c, cid) if m['state'] not in TERMINAL]
        for mid in pending:
            sync_message(w, mid)
        with w.connect() as c:
            return {k: thread[k] for k in ('id', 'title', 'created_at', 'updated_at')} | {
                'messages': [public_message(w, c, m, actor) for m in messages(w, c, cid)]}

    @r.post('/questions', status_code=202)
    def send(body: ChatQuestion, actor=Depends(w.user)):
        question = body.question.strip()
        if len(question) < 2:
            raise HTTPException(422, '질문을 두 글자 이상 입력해 주세요.')
        with CHAT_LOCK:
            if body.conversation_id:
                detail(body.conversation_id, actor)
            with w.connect() as c:
                thread = own_thread(w, c, body.conversation_id, actor) if body.conversation_id else None
                past = messages(w, c, thread['id']) if thread else []
                if any(m['state'] not in TERMINAL for m in past):
                    raise HTTPException(409, '이 대화의 답변이 끝나면 이어서 질문해 주세요.')
                context = resolve_question(w, c, actor, question, past[-1] if past else None, body.project_id, body.meeting_id)
            if context.get('clarify'):
                job = {'id': w.uid(), 'state': 'done', 'scope_ids': context['project_ids'],
                       'question': question, 'result': {'kind': 'documents' if context.get('empty_result') else 'clarification', 'answerable':False, 'message': context['clarify'],
                       'projects': context.get('projects', []), 'meetings': context.get('meetings', []), 'points': [], 'sources': []}}
            else:
                response = ask(questions.Question(question=context['query'], project_id=context['project_id'], meeting_ids=context.get('meeting_ids') or None,
                    project_ids=context['project_ids'] if context.get('scope_override') else None,
                    record_scope=context.get('time_scope') if context.get('scope_override') else None), actor)
                with questions.LOCK:
                    job = deepcopy(questions.JOBS[response['id']])
            now = w.now()
            if not thread:
                thread = {'id': w.uid(), 'user_id': actor['id'], 'title': question[:60], 'created_at': now}
            thread['updated_at'] = now
            thread['activity'] = time.time_ns()
            message = {'id': w.uid(), 'conversation_id': thread['id'], 'user_id': actor['id'],
                       'sequence': len(past), 'question': question, 'context': context,
                       'state': job['state'], 'job': job, 'created_at': now,
                       'completed_at': now if job['state'] in TERMINAL else None}
            with w.connect() as c:
                w.save(c, 'ai_conversation', thread)
                w.save(c, 'ai_message', message)
            if job['state'] not in TERMINAL:
                watch(w, message['id'])
        return detail(thread['id'], actor)

    @r.get('/{cid}/messages/{mid}/sources/{sid}')
    def source(cid, mid, sid, actor=Depends(w.user)):
        with w.connect() as c:
            own_thread(w, c, cid, actor)
            message = w.read(c, 'ai_message', mid)
            if message['conversation_id'] != cid or message['user_id'] != actor['id']:
                raise HTTPException(404, '근거를 찾을 수 없습니다.')
            job = message['job']
            item = next((s for s in job.get('result', {}).get('sources', []) if s['id'] == sid), None)
            if message['state'] != 'done' or not item:
                raise HTTPException(404, '답변의 원문 근거를 찾을 수 없습니다.')
            meeting = w.read(c, 'meeting', item['meeting_id'])
            project = w.project(c, meeting['project_id'], actor)
            doc = revision_document(meeting, item['revision'])
            if not doc or doc['fingerprint'] != item['fingerprint']:
                raise HTTPException(409, '당시 참조한 회의록 본문을 확인할 수 없습니다.')
            lines = document_lines(doc)
            highlighted = questions.highlight_lines(lines, item['line_ids'], item.get('query_scope',{}).get('resolved_question',job['question']), job['result']['points'], sid, resolved=bool(item.get('query_scope',{}).get('resolved_question')),query_terms=item.get('query_scope',{}).get('search_terms'))
            if 'exact_highlights' in item:highlighted=[l['id'] for l in lines if l['id'] in item['exact_highlights']]
            return {k: doc[k] for k in ('meeting_id', 'project_id', 'title', 'date', 'revision', 'has_draft')} | {
                'project_name': project['name'], 'lines': lines, 'highlight': highlighted}

    @r.patch('/{cid}')
    def rename(cid, body: RenameConversation, actor=Depends(w.user)):
        title = re.sub(r'\s+', ' ', body.title).strip()
        if not title:
            raise HTTPException(422, '대화 이름을 입력해 주세요.')
        with CHAT_LOCK, w.connect() as c:
            thread = own_thread(w, c, cid, actor)
            thread['title'] = title
            thread['title_updated_at'] = w.now()
            # Editing a title is not new conversation activity: keep its place
            # in the recent list and leave messages/evidence untouched.
            w.save(c, 'ai_conversation', thread)
        return {k: thread[k] for k in ('id', 'title', 'updated_at')}

    @r.delete('/{cid}')
    def delete(cid, actor=Depends(w.user)):
        detail(cid, actor)
        with CHAT_LOCK, w.connect() as c:
            own_thread(w, c, cid, actor)
            ms = messages(w, c, cid)
            if any(m['state'] not in TERMINAL for m in ms):
                raise HTTPException(409, '답변 생성이 끝난 뒤 대화를 삭제해 주세요.')
            for m in ms:
                c.execute('DELETE FROM records WHERE kind=? AND id=?', ('ai_message', m['id']))
            c.execute('DELETE FROM records WHERE kind=? AND id=?', ('ai_conversation', cid))
        return {'deleted': cid}
    return r
