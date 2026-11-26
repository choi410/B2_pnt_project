"""Private conversation history around the existing source-grounded question engine."""
from copy import deepcopy
import re
import threading
import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from work.v17 import questions
from work.v17.retrieval import revision_document, registered_document, document_lines
from work.v3 import question_policy as policy
from work.v3.question_scope import plan_question

CHAT_LOCK = threading.RLock()
TERMINAL = {'done', 'failed'}


class ChatQuestion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    conversation_id: str | None = Field(default=None, max_length=80)
    project_id: str | None = Field(default=None, max_length=80)
    meeting_id: str | None = Field(default=None, max_length=80)
    question: str | None = Field(default=None, min_length=2, max_length=500)
    choice_message_id: str | None = Field(default=None, max_length=80)


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


def resolve_choice(w,c,actor,body,past):
    if body.question is not None or bool(body.project_id)==bool(body.meeting_id):
        raise HTTPException(422,'앞 질문의 프로젝트 또는 회의록 하나를 선택해 주세요.')
    original=next((m for m in past if m['id']==body.choice_message_id),None)
    if not original or original['state']!='done':
        raise HTTPException(404,'이 대화에서 선택지를 찾을 수 없습니다.')
    result=original['job'].get('result',{})
    kind,selected_id,options=('project',body.project_id,'projects') if body.project_id else ('meeting',body.meeting_id,'meetings')
    if result.get('kind')!='clarification' or not any(item['id']==selected_id for item in result.get(options,[])):
        raise HTTPException(422,'앞 질문에 표시된 선택지를 다시 확인해 주세요.')
    if kind=='project':
        project=w.project(c,selected_id,actor)
        label=project['name']
    else:
        doc=registered_document(w.read(c,'meeting',selected_id))
        if not doc:
            raise HTTPException(404,'조회할 수 있는 등록 회의록이 아닙니다.')
        project=w.project(c,doc['project_id'],actor)
        label=doc['title']
    return original,{'kind':kind,'id':selected_id,'label':label,'project_id':project['id'],
                     'message_id':original['id']}


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
            if job.get('conversation_context'):
                input_scope=message.get('context',{}).get('input_scope')
                message['context']=deepcopy(job['conversation_context'])
                if input_scope is not None:message['context']['input_scope']=input_scope
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
    # Resolve short field questions from registered titles, not from generated
    # answer text. Keep ambiguous words (e.g. two different 검수일 fields) open.
    generic={'장비','설비','공장','항목','사항','기준','상한','하한','현재','최종','일정'}
    candidates=[]
    for title in titles:
        stems={re.sub(r'(?:상한|하한|기준|일)$','',policy.clean(t)) for t in title.split()}
        if any(len(t)>=2 and t not in generic and t in q for t in stems):candidates.append(title)
    if len(candidates)==1:return candidates[0]
    matches = []
    for title in titles:
        tokens = [policy.clean(x) for x in title.split() if len(x) >= 2]
        if len(tokens) >= 2 and sum(token in q for token in tokens) >= 2:
            matches.append(title)
    return matches[0] if len(matches) == 1 else ''


def resolve_question(w, c, actor, question, previous=None, project_id=None, meeting_id=None):
    from work.v3.conversation_context import resolve,field_project,NEW_TOPIC
    from work.v3 import conversation_followups as followups
    from work.v3 import dialogue_plan
    from work.v3.query_intent import metadata_plan
    from work.v3.chat_state import point_focus,memory
    if NEW_TOPIC.match(question):
        previous=None
        question=NEW_TOPIC.sub('',question,count=1)
    exclusion=followups.named_exclusions(w,c,actor,question,project_id,meeting_id)
    if exclusion is not None:
        return exclusion
    focus=point_focus(w,c,actor,question,previous,project_id) if not meeting_id else None
    if focus is not None:
        ids=list(dict.fromkeys(row['project_id'] for row in focus.get('rows',[])))
        prior=memory(w,c,actor,previous)
        if not ids:ids=prior.get('scope_ids') or prior.get('project_ids',[])
        if project_id:
            w.project(c,project_id,actor)
            ids=[project_id]
        return {'query':question,'project_id':ids[0] if len(ids)==1 else None,'project_ids':ids,
                'subject':'','time_scope':prior.get('time_scope',{}),'meeting_ids':[],'label':'선택한 답변 항목',
                'point_followup':True,**({'clarify':focus['error']} if focus.get('error') else {})}
    explicit=metadata_plan(question,followups.available_projects(w,c,actor))
    if explicit and explicit['entity']=='project' and not (previous and re.search(r'(?:이|그)\s*프로젝트|프로젝트\s*(?:에서|로|도)|전부에서는',question)):
        return resolve(w,c,actor,question,previous,project_id,meeting_id)
    # A validated meeting lookup takes precedence over an inferred follow-up
    # to change history, even when the user calls the document a '기록'.
    if not (explicit and explicit['entity']=='meeting'):
        from work.v3 import change_queries
        context=change_queries.resolve(w,c,actor,question,previous,project_id,meeting_id)
        if context is not None:return context
    context=dialogue_plan.resolve(w,c,actor,question,previous,project_id,meeting_id)
    if context is not None:return context
    # A new content topic must not inherit a metadata lookup's date/exclusions.
    last_plan=(previous or {}).get('context',{}).get('retrieval_plan') or (previous or {}).get('context',{}).get('last_retrieval_plan')
    if (previous or {}).get('context',{}).get('retrieval_plan') and not re.search(r'그\s*회의|이\s*회의|그거|그것|첫\s*번째|두\s*번째',question):
        previous=None
    context=followups.resolve(w,c,actor,question,previous,project_id,meeting_id)
    if context is None:
        inherited_project=field_project(w,c,actor,question,previous) if not project_id and not meeting_id else None
        context=resolve(w,c,actor,question,previous,project_id or inherited_project,meeting_id)
        if inherited_project:context['slot_sources']={'project':'previous_records','subject':'registered_field'}
        context=followups.remember(context,question,followups.available_projects(w,c,actor),project_id,previous)
    if last_plan:context['last_retrieval_plan']=last_plan
    return context


def public_message(w, c, message, actor):
    job = message['job']
    public = {k: message.get(k) for k in ('id', 'question', 'state', 'created_at', 'completed_at')}
    public['context_label'] = message.get('context', {}).get('label', '')
    selection=message.get('selection')
    try:
        for pid in dict.fromkeys(job.get('scope_ids', [])+([selection['project_id']] if selection else [])):
            w.project(c, pid, actor)
    except HTTPException:
        return {**public, 'state': 'failed', 'error': '이 대화의 프로젝트에 현재 접근할 수 없습니다.'}
    public['error'] = job.get('error', '')
    if selection:
        public['selection']={key:selection[key] for key in ('kind','id','label','message_id')}
    if job.get('result'):
        result = deepcopy(job['result'])
        from work.v3.chat_presentation import present
        result=present(result)
        if result.get('mode')=='change_project_choice':
            from work.v3.chat_tools import ReadTools
            current={p['id']:p for p in ReadTools(w,c,actor).projects()}
            result['projects']=[{'id':pid,'name':current[pid]['name']} for p in result.get('projects',[])
                                if (pid:=p['id']) in current]
            if not result['projects']:
                result['message']='현재 선택할 수 있는 프로젝트가 없어요.'
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
        question = (body.question or '').strip()
        if not body.choice_message_id and len(question)<2:
            raise HTTPException(422,'질문을 두 글자 이상 입력해 주세요.')
        with CHAT_LOCK:
            if body.conversation_id:
                detail(body.conversation_id, actor)
            with w.connect() as c:
                thread = own_thread(w, c, body.conversation_id, actor) if body.conversation_id else None
                past = messages(w, c, thread['id']) if thread else []
                if any(m['state'] not in TERMINAL for m in past):
                    raise HTTPException(409, '이 대화의 답변이 끝나면 이어서 질문해 주세요.')
                choice_source=selection=None
                if body.choice_message_id:
                    choice_source,selection=resolve_choice(w,c,actor,body,past)
                    question=choice_source['question']
                from work.v3 import chat_interpreter as language, general_chat
                # Capability notices do not replace the last query scope.
                notices = ('unsupported_action', 'shipment_total_unavailable', 'shipment_plan_unavailable',
                           'term_definition', *general_chat.PUBLIC_MODES)
                query_history = [m for m in past if m.get('job', {}).get('result', {}).get('mode') not in notices]
                if choice_source:
                    query_history=[m for m in query_history if m['sequence']<=choice_source['sequence']]
                public_history=general_chat.history(past) if general_chat.enabled() else []
                previous=next((m for m in reversed(query_history) if m.get('job',{}).get('result',{}).get('mode') not in ('social','scope_explanation')),None)
                if choice_source:
                    previous=choice_source
                    public_history=[]
                from work.v3.conversation_context import explain_scope, public_value_followup
                legacy_shipment = None if language.shipment_intent_enabled() else policy.shipment_total_answer(question)
                capability = legacy_shipment or language.record_management_response(question)
                scope_answer=explain_scope(w,c,actor,question,previous) if not capability else None
                social=(None if public_history else language.english_restatement(question,past[-1] if past else None)) or language.social(question)
                from work.v3 import project_records
                # '한빛셀 롤프레스에 대해서 알려줘' names one project and asks nothing specific: answer with its summary.
                record_question=question
                if not (capability or social or scope_answer) and not project_records.intent(question):
                    from work.v3.term_definition import about_project
                    about=about_project(question,language.available(w,c,actor))
                    if about:record_question=about['name']+' 프로젝트 요약해줘'
                record_plan=project_records.intent(record_question) if not (capability or social or scope_answer) else None
                project_answer=None
                if record_plan:
                    selected,result=project_records.answer(w,c,actor,record_question,record_plan,language.available(w,c,actor),body.project_id,body.meeting_id)
                    ids=[p['id'] for p in selected]
                    fixed=len(ids)==1 and result['kind']!='clarification'
                    project_answer=({'query':question,'project_ids':ids,'project_id':ids[0] if fixed else None,
                                     'label':selected[0]['name'] if fixed else ''},result)
                from work.v3.term_definition import requested_term
                ps=language.available(w,c,actor)
                general_question=(general_chat.workspace_explanation(question,previous,ps,body.project_id)
                                  if general_chat.enabled() and not (capability or social or scope_answer
                                      or project_answer or public_history or body.meeting_id) else None)
                if general_question is not None and body.project_id:
                    w.project(c,body.project_id,actor)
                mixed=(general_chat.comparison(question,ps,w.all_records(c,'project'))
                       if general_chat.enabled() and not (capability or social or scope_answer or project_answer) else None)
                term=(requested_term(question,ps,in_meeting=bool(body.meeting_id))
                      if general_question is None and not (capability or social or scope_answer or project_answer) else None)
                if term and general_chat.enabled() and (mixed or public_history or general_chat.needs_public(question)):
                    term=None
                from work.v3 import semantic_chat
                reference_ready=not (capability or term or project_answer) and bool(language.reference_lines(w,c,actor,question,previous,body.project_id))
                local=capability or (scope_answer[1] if scope_answer else None if term or project_answer or mixed else language.local_response(question,previous,resolve_references=semantic_chat.enabled() or reference_ready))
                from work.v3.conversation_values import resolve as resolve_values, resolve_test_width
                from work.v3.task_followups import resolve as resolve_task
                from work.v3.paired_followups import resolve as resolve_pair
                from work.v3.change_queries import confirmed_delivery_projects
                value_answer=project_answer
                search_records=general_question is None and not (social or local or term or project_answer or mixed)
                public_value=(public_value_followup(w,c,actor,question,previous,public_history,ps,
                                                    body.project_id,body.meeting_id)
                              if search_records and general_chat.enabled() else None)
                search_records=search_records and public_value is None
                if search_records:
                    value_answer=resolve_task(w,c,actor,question,previous,body.project_id,body.meeting_id)
                    if value_answer is None:
                        value_answer=resolve_pair(w,c,actor,question,query_history,body.project_id,body.meeting_id)
                    if value_answer is None:
                        value_answer=confirmed_delivery_projects(w,c,actor,question,previous,body.project_id,body.meeting_id)
                    if value_answer is None:
                        value_answer=resolve_values(w,c,actor,question,query_history,body.project_id,body.meeting_id)
                if mixed:
                    context=resolve_question(w,c,actor,mixed[0],previous,body.project_id,body.meeting_id)
                    if not context.get('clarify') and len(context['project_ids'])!=1:
                        context.update(clarify='어느 프로젝트의 사양을 비교할까요?',
                                       projects=[{'id':p['id'],'name':p['name']} for p in ps if p['id'] in context['project_ids']])
                elif term:
                    context = {'query': question, 'project_ids': [], 'label': '일반 용어 설명'}
                elif capability:
                    context = {'query': question, 'project_ids': []}
                elif general_question is not None:
                    context = {'query': general_question or question, 'project_ids': [], 'label': '일반 답변'}
                elif public_value is not None:
                    context = public_value
                else:
                    context = scope_answer[0] if scope_answer else value_answer[0] if value_answer else resolve_question(w, c, actor, question, previous, body.project_id, body.meeting_id) if not social else deepcopy((previous or {}).get('context',{}))
                width_resolved = search_records and not value_answer and resolve_test_width(w,c,actor,question,query_history,context)
                interpret=search_records and not width_resolved and not value_answer and not context.get('change_request') and language.needs_interpreter(w,c,actor,question,context,previous)
                semantic=search_records and not width_resolved and not value_answer and semantic_chat.eligible(w,c,actor,question,context,previous,interpret)
                if search_records and not semantic and not value_answer and not reference_ready:
                    local=language.local_response(question,previous)
                prior_turn=next((m for m in reversed(past)
                                 if m.get('job',{}).get('result',{}).get('mode') not in
                                 ('social','term_definition',*general_chat.PUBLIC_MODES)),{})
                prior_shipment=prior_turn.get('context',{}).get('shipment',{})
                shipment_probe=(search_records and not semantic and not local and not value_answer and not width_resolved
                                and not reference_ready and language.shipment_intent_candidate(question,context,bool(prior_shipment))
                                and not language.metadata_plan(question,ps))
                general=(search_records and not (body.project_id or body.meeting_id or local or value_answer
                                                 or width_resolved or reference_ready or shipment_probe)
                         and general_chat.candidate(question,ps,context,previous,public_history))
                from work.v3.chat_state import pin_selection
                if (search_records or mixed) and not local:pin_selection(w,c,actor,context)
            if social:
                job={'id':w.uid(),'state':'done','scope_ids':[],'question':question,
                     'result':{'kind':'conversation','mode':'social','answerable':True,'message':social,'points':[],'sources':[]}}
            elif general_question is not None:
                if general_question:
                    from work.v3.chat_jobs import start
                    job=start(w,actor,question,None,general_history=[],general_question=general_question)
                else:
                    result=language.clarification('어떤 항목의 일반 원리를 설명할까요? 항목명을 알려주세요.')
                    result['mode']='general_knowledge'
                    job={'id':w.uid(),'state':'done','scope_ids':[],'question':question,'result':result}
            elif term:
                from work.v3.chat_jobs import start
                job=start(w,actor,question,previous,body.project_id,definition_term=term)
            elif mixed and not context.get('clarify'):
                from work.v3.chat_jobs import start
                job=start(w,actor,question,previous,context['project_ids'][0],comparison=(context,mixed[1]))
            elif local:
                job={'id':w.uid(),'state':'done','scope_ids':context['project_ids'] if scope_answer else [],'question':question,'result':local}
            elif value_answer:
                job={'id':w.uid(),'state':'done','scope_ids':context['project_ids'],'question':question,'result':value_answer[1],'seconds':0}
            elif general:
                from work.v3.chat_jobs import start
                job=start(w,actor,question,previous,general_history=public_history,interpret=interpret)
            elif semantic:
                from work.v3.chat_jobs import start
                job=start(w,actor,question,previous,body.project_id,body.meeting_id,semantic_past=query_history)
            elif shipment_probe:
                from work.v3.chat_jobs import start
                job=start(w,actor,question,previous,body.project_id,body.meeting_id,
                          shipment_probe=(prior_shipment,interpret))
            elif interpret:
                from work.v3.chat_jobs import start
                job=start(w,actor,question,previous,body.project_id,body.meeting_id)
            elif context.get('clarify'):
                job = {'id': w.uid(), 'state': 'done', 'scope_ids': context['project_ids'],
                       'question': question, 'result': {'kind': 'documents' if context.get('empty_result') else 'clarification', 'answerable':False, 'message': context['clarify'],
                       'projects': context.get('projects', []), 'meetings': context.get('meetings', []), 'points': [], 'sources': []}}
                if context.get('clarification_mode'):
                    job['result']['mode']=context['clarification_mode']
            elif context.get('retrieval_plan'):
                from work.v3.dialogue_plan import execute
                with w.connect() as c:
                    result=execute(w,c,actor,context)
                job={'id':w.uid(),'state':'done','scope_ids':context['project_ids'], 'question':question,
                     'query_plan':deepcopy(context['retrieval_plan']),'result':result,'seconds':0}
            elif context.get('change_query'):
                from work.v3.change_queries import execute
                with w.connect() as c:result=execute(w,c,actor,context)
                job={'id':w.uid(),'state':'done','scope_ids':context['project_ids'],'question':question,'result':result,'seconds':0}
            else:
                response = ask(questions.Question(question=context['query'], project_id=context['project_id'], meeting_ids=context.get('meeting_ids') or None,
                    project_ids=context['project_ids'] if context.get('scope_override') else None,
                    record_scope=context.get('time_scope') if context.get('scope_override') else None), actor)
                with questions.LOCK:
                    job = deepcopy(questions.JOBS[response['id']])
            now = w.now()
            if job.get('conversation_context'):context=deepcopy(job['conversation_context'])
            context['input_scope']={'project_id':body.project_id,'meeting_id':body.meeting_id}
            if not capability and not term:
                with w.connect() as c:
                    context['chat_memory']=language.memory(w,c,actor,previous)
            if not thread:
                thread = {'id': w.uid(), 'user_id': actor['id'], 'title': question[:60], 'created_at': now}
            thread['updated_at'] = now
            thread['activity'] = time.time_ns()
            message = {'id': w.uid(), 'conversation_id': thread['id'], 'user_id': actor['id'],
                       'sequence': len(past), 'question': question, 'context': context,
                       'state': job['state'], 'job': job, 'created_at': now,
                       'completed_at': now if job['state'] in TERMINAL else None}
            if selection:
                message['selection']=selection
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
