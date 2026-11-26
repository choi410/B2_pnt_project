"""Resolve follow-ups from record identities, never from generated answer prose."""
import os
import re
from datetime import date
from fastapi import HTTPException
from work.v3 import question_policy as policy
from work.v3.query_intent import normalize, metadata_plan, uncertain_project, strip_labels, edit_distance, unit_quantity, equipment_units, leading_unit_reference, ATTRIBUTE
from work.v3.question_scope import plan_question
from work.v17 import questions
from work.v3.topic_search import search_intent
from work.v17.evidence_text import TOPIC_REFERENCE, content_line, coverage, topic_terms

MEETING_REFERENCE=re.compile(r'(?:그|이)\s*회의(?:록)?(?=\s|에서|에|의|는|은|를|을|가|도|내용|안건|[?!.]|$)')
SAME_PROJECT=re.compile(r'^\s*(?:(?:그럼|그러면)\s+)?(?:같은|동일한)\s*프로젝트(?:에서(?:는)?|의)?(?=\s|$)\s*')
NEW_TOPIC = re.compile(r'^\s*(?:별개로|다른\s+얘기로|앞\s*질문과\s*별개로)\s*[,，]?\s+')
_VALUE_REFERENCE = r'(?:그건|그(?:거|것|\s+(?:값|수치|항목))(?:은|는|이|가)?)'
PUBLIC_VALUE = re.compile(
    rf'(?:그럼\s+|그러면\s+)?(?:{_VALUE_REFERENCE}\s+)?(?:(?P<ours>우리|저희|당사)\s*)?'
    r'(?:프로젝트|장비|설비|쪽|건)?\s*(?:에서는|에서|은|는|도)?\s*(?:실제로\s+|현재\s+)?'
    rf'(?:(?P<topic>{ATTRIBUTE})(?:은|는|이|가)?\s*|{_VALUE_REFERENCE}\s+)?'
    r'(?P<value>얼마(?:로\s*(?:정해졌(?:어(?:요)?|지|나요|습니까)|'
    r'(?:합의|결정|확정|정)\s*(?:했|됐|하였|되었)(?:어(?:요)?|지|나요|습니까))|야|예요|였어|인가요))'
    r'[?!.\s]*')


def public_value_followup(w, c, actor, question, previous, public_history, projects,
                          project_id=None, meeting_id=None):
    """Carry a topic from the user's public question into a fresh record lookup."""
    if meeting_id:
        return None
    old = (previous or {}).get('context', {})
    pending = old.get('pending_public_value')
    pending_topic = old.get('pending_public_topic') or {}
    named = policy.name_matches(projects, question)
    residue = strip_labels(question, named).strip()
    match = PUBLIC_VALUE.fullmatch(residue)
    choice = pending and (project_id or named) and (
        match and not match['topic'] or re.fullmatch(r'(?:프로젝트)?(?:은|는|도|만|으로)?[?!.\s]*',residue))
    topic_choice = re.fullmatch(rf'(?P<topic>{ATTRIBUTE})(?:은|는|이요|요)?[?!.\s]*', residue)
    fields = {}
    pinned = old.get('exploration', {}).get('pinned_id') or pending_topic.get('project_id')
    if choice:
        query, subject = pending['query'], pending['subject']
    elif pending_topic and topic_choice and (subject := pending_topic['fields'].get(re.sub(r'\s+', '', topic_choice['topic']))):
        query = f"{subject} {pending_topic['value']}?"
    else:
        if not match or not (match['ours'] or named or project_id) or (previous and not public_history):
            return None
        from work.v3.general_chat import RESTATE, value_topics
        # Only the literal subject of the latest substantive user question is carried over.
        # A computed value and any text from the answer stay out of the lookup.
        public_question = next((turn['question'] for turn in reversed(public_history)
                                if not RESTATE.search(turn['question'])), '')
        fields = value_topics(public_question)
        if match['topic']:
            subject = fields.get(re.sub(r'\s+', '', match['topic']), '')
            if not subject:
                return None
        else:
            subject = next(iter(fields.values())) if len(fields)==1 else ''
        query = f"{subject} {match['value']}?" if subject else ''
    pinned_project = next((p for p in projects if p['id']==pinned), None)
    selected = [w.project(c, project_id, actor)] if project_id else named or (
        [pinned_project] if pinned_project else projects)
    scope_lost = bool(pinned and not (pinned_project or project_id or named))
    ids = [p['id'] for p in selected]
    if query and len(selected)==1 and not scope_lost:
        from work.v3.conversation_followups import remember
        return remember(resolve(w,c,actor,query,project_id=ids[0]),query,projects,ids[0])
    context = {'query':question,'project_id':None,'project_ids':ids,'meeting_ids':[],
               'subject':subject,'label':'','time_scope':{}}
    if not ids:
        context.update(clarify='조회할 수 있는 프로젝트가 없어요.',empty_result=True)
    elif not query:
        choices = ', '.join(fields.values())
        message = f'앞에서 이야기한 항목 중 어느 값을 볼까요? ({choices})' if choices else '어떤 항목의 합의값을 볼까요? 확인할 항목명을 알려주세요.'
        context.update(clarify=message)
        if choices:
            context['pending_public_topic'] = {'fields':fields, 'value':match['value'],
                                               'project_id':project_id or (ids[0] if len(named)==1 else pinned)}
    else:
        message = f'{subject} 값을 어느 프로젝트에서 확인할까요?'
        if scope_lost:
            message = '앞서 선택한 프로젝트에 접근할 수 없어요. ' + message
        context.update(clarify=message,
                       projects=[{'id':p['id'],'name':p['name']} for p in selected],
                       pending_public_value={'query':query,'subject':subject})
    return context

def scope_question(question):
    """Questions about the search operation, not reasons stated in meetings."""
    q=normalize(question)
    if re.search(r'찾아줘|검색해\s*줘|조회해\s*줘|비교해\s*줘|바꿔|넓혀|좁혀',q):return False
    if re.search(r'(?:검색|조회|비교)\s*(?:범위|기준)',q) and re.search(r'왜|어떻|뭐|무엇|어디|어느|알려|설명|확인',q):return True
    target=re.search(r'프로젝트|범위|거기|그쪽|여기|전체|전부|어디',q)
    operation=re.search(r'찾았|찾은|찾는|찾아봤|검색|조회|비교|선택|골랐|고른',q)
    return bool(target and operation and re.search(r'왜|어느|어디|전체.*(?:거야|했어|했니)|여기만|거기만',q))


def explain_scope(w,c,actor,question,previous):
    """Explain the recorded search scope, checking access again before naming it."""
    if not scope_question(question):return None
    from work.v3.chat_tools import ReadTools
    projects={p['id']:p for p in ReadTools(w,c,actor).projects()}
    old=(previous or {}).get('context',{})
    job=(previous or {}).get('job',{})
    result=job.get('result',{})
    raw_ids=list(dict.fromkeys(job.get('scope_ids',old.get('project_ids',[]))))
    ids=[pid for pid in raw_ids if pid in projects]
    context={'query':question,'project_id':None,'project_ids':ids,'meeting_ids':[],
             'subject':'','label':'조회 범위 확인','time_scope':{}}
    if not previous or not raw_ids:
        text='설명할 이전 조회 범위가 없어요. 먼저 프로젝트나 회의 기록을 질문해 주세요.'
    elif len(ids)!=len(raw_ids):
        text='이전 조회 대상 중 현재 열람할 수 없는 프로젝트가 있어요. 현재 접근 가능한 범위에서 다시 조회해 주세요.'
    else:
        names=[projects[pid]['name'] for pid in ids]
        scope=('조회 가능한 전체 '+str(len(ids))+'개 프로젝트' if set(ids)==set(projects) and len(ids)>1
               else '「'+names[0]+'」 프로젝트' if len(ids)==1
               else str(len(ids))+'개 프로젝트')
        selected=old.get('input_scope',{}).get('project_id')
        named={p['id'] for p in policy.name_matches(list(projects.values()),(previous or {}).get('question',''))}
        if selected and ids==[selected]:
            text=f'앞 질문을 보낼 때 「{names[0]}」 프로젝트가 지정되어, 해당 프로젝트 범위로 조회했어요.'
        elif named and named==set(ids):
            text=f'앞 질문에 적힌 프로젝트 이름을 기준으로 {scope}에서 조회했어요.'
        else:
            text=f'앞 답변은 {scope}를 대상으로 조회했어요.'
            if len(ids)==1 and 'input_scope' not in old:
                text+=' 해당 범위를 선택한 이유는 이전 기록만으로 확인하기 어려워요.'
        winners=[pid for pid in result.get('result_project_ids',[]) if pid in projects and pid in ids]
        if result.get('mode')=='change_rank' and winners and isinstance(result.get('count'),int):
            label=' · '.join(projects[pid]['name'] for pid in winners[:3])
            if len(winners)>3:label+=f' 외 {len(winners)-3}개'
            text+=f' 그중 「{label}」의 변경 기록이 {result["count"]}건으로 가장 많아 결과에 표시했어요.'
        elif result.get('mode')=='change_rank' and result.get('count')==0:
            text+=' 당시 그 범위에서 집계된 변경 기록은 0건이었어요.'
        requested={p['id'] for p in policy.name_matches(list(projects.values()),question)}
        if requested-set(ids):text+=' 질문에 적으신 프로젝트 중 앞 조회 범위에 포함되지 않은 프로젝트가 있어요.'
        period=old.get('time_scope',{})
        if period.get('start') or period.get('end'):
            text+=f' 기간 조건은 {period.get("start") or "시작일 제한 없음"} ~ {period.get("end") or "종료일 제한 없음"}이었어요.'
    return context,{'kind':'conversation','mode':'scope_explanation','answerable':True,
                    'message':text,'points':[],'sources':[]}


def field_project(w,c,actor,question,previous):
    """A registered field is not an equipment-word project alias.

    Only disambiguate a single established, still accessible project. Explicit
    names/codes/customer prefixes always win; generated answer prose is unused.
    """
    from work.v3.conversations import subject_in
    from work.v3.chat_interpreter import memory,available
    from work.v3.query_intent import leading_aliases,label_pattern
    from work.v3.dialogue_plan import OTHER
    if not previous or equipment_units(question):return None
    ps=available(w,c,actor);q=normalize(question)
    state=memory(w,c,actor,previous)
    ids=state.get('project_ids') or state.get('scope_ids',[])
    if len(ids)!=1 or ids[0] not in {p['id'] for p in ps}:return None
    if policy.is_broad(question) or re.search(OTHER,question):return None
    titles={e['title'] for e in w.all_records(c,'change_event') if e.get('project_id')==ids[0]
            and not e.get('superseded_by_revision') and e.get('review_state')!='제외'}
    field=subject_in(question,titles)
    if not field:return None
    lookup=metadata_plan(question,ps)
    if lookup and lookup['operation']!='list':return None
    for p in ps:
        labels={p['name'],p['id'],p.get('code','')}
        labels.update(label for label in leading_aliases(p) if policy.clean(label) not in policy.clean(field))
        if any(label and re.search(label_pattern(normalize(label)),q) for label in labels):return None
    return ids[0]

def result_entities(previous):
    result=(previous or {}).get('job',{}).get('result',{})
    if (previous or {}).get('state')=='failed':return [],[]
    # Sources and project results originate in accessible database records.
    projects=list(dict.fromkeys([p['id'] for p in result.get('projects',[]) if result.get('kind')=='projects']+
                               [s['project_id'] for s in result.get('sources',[])]+
                               (result.get('result_project_ids',[]) if result.get('mode') in ('project_owner','change_rank','change_history') else [])))
    meetings=list(dict.fromkeys(s['meeting_id'] for s in result.get('sources',[]) if s.get('meeting_id')))
    if result.get('mode')=='value_comparison' and result.get('focus_project_ids'):
        projects=result['focus_project_ids']
    return projects,meetings


def interpreted_subject(previous,project_ids):
    """Reuse a validated selection of user words, never generated answer facts."""
    from work.v17.evidence_text import topic_terms
    old=(previous or {}).get('context',{})
    result=(previous or {}).get('job',{}).get('result',{})
    if len(project_ids)!=1 or project_ids!=old.get('project_ids') or not result.get('answerable'):return ''
    if (previous or {}).get('state')!='done':return ''
    if result.get('mode')=='recorded_status' and result.get('completion_subject'):
        return result['completion_subject']
    words=set(re.findall(r'[가-힣A-Za-z0-9]+',old.get('query') or previous.get('question','')))
    candidates=set()
    for source in result.get('sources',[]):
        if source.get('project_id')!=project_ids[0]:return ''
        scope=source.get('query_scope',{})
        terms=scope.get('evidence_topic_terms') or scope.get('content_meaning',{}).get('terms',[])
        if not terms or len(terms)>8 or any(not isinstance(t,str) or t not in words for t in terms):return ''
        candidates.add(tuple(topic_terms(' '.join(terms)) if scope.get('evidence_topic_terms') else terms))
    return ' '.join(next(iter(candidates))) if len(candidates)==1 else ''


def completion_reference(question, previous):
    from work.v3.answer_meaning import completion_question, completion_topic

    result=(previous or {}).get('job',{}).get('result',{})
    return bool(result.get('mode')=='recorded_status' and result.get('completion_subject')
                and result.get('answerable') and previous.get('state')=='done'
                and TOPIC_REFERENCE.search(question) and completion_question(question)
                and not topic_terms(completion_topic(question)))


_NAMED_STATUS_REFERENCE = re.compile(
    r'^(?:그|해당)\s+(?P<noun>[가-힣]{2,18}?)(?:은|는|이|가|을|를)\s+'
    r'(?:결국\s+)?(?:(?:실제로?|이미|벌써)\s+)?(?P<status>.+)$'
)
_BARE_STATUS_REFERENCE = re.compile(
    r'(?:(?:그럼|그러면|그래서)\s+)?(?:끝난\s*(?:거야|건가요|거예요)|'
    r'완료됐(?:어(?:요)?|나요)|실제로\s*했(?:어(?:요)?|나요))[?!. ]*'
)
_PREVIOUS_HOLD_REASON = re.compile(
    r'(?:그때|당시)\s+|\s+(?:그때|당시)\s*'
)
_DAY_CHANGE = re.compile(
    r'^(?:(?:그럼|그러면|그러다가)\s+)?(?P<day>\d{1,2})\s*일에는\s+'
    r'(?P<ask>(?:뭘로|무엇으로|얼마로|어떻게)\s+(?:합의|결정|확정|정)했(?:어(?:요)?|나요|지))[?!.\s]*$'
)
_SCHEDULE_FIELD = re.compile(
    r'(?<![가-힣])(?:(?:납품|납기|출하|출고|반입|인도|검수|설치)\s*일(?:자)?|(?:현장\s*)?인수\s*시험)'
    r'(?=$|[^가-힣]|은|는|에|이|가|을|를|과|하고|로|만)'
)
_NAMED_SCHEDULE_REASON = re.compile(
    r'(?:(?:프로젝트|건)(?:은|는|도)?\s+)?'
    r'왜\s+(?:(?:날짜|일정)(?:가|이|는|은)?\s*)?'
    r'(?:바뀌었|달라졌|미뤄졌|변경됐|변경되었)'
    r'(?:던\s*거야|어(?:요)?|나요|지|고\s+(?:며칠|언제)에서\s+(?:며칠|언제)로\s+(?:간|바뀐)\s*거야)[?!.\s]*'
)


def cited_topic(subject, result, docs):
    """Check the previous topic against the current original source revision."""
    from work.v17.retrieval import document_lines

    terms = topic_terms(subject)
    if not terms:
        return False
    originals = {(doc['meeting_id'], doc.get('fingerprint')): doc for doc in docs}
    return any(
        coverage(line['text'],terms)==1
        for source in result.get('sources', [])
        if source.get('fingerprint') and (doc := originals.get((source.get('meeting_id'), source['fingerprint'])))
        for line in document_lines(doc)
        if line['id'] in (source.get('exact_highlights') or source.get('line_ids', [])) and content_line(line['text'])
    )


def scoped_record_followup(question, previous, context, docs, prior_subject):
    """Bind an explicit reference to the previous cited topic and its date."""
    from work.v3.answer_meaning import completion_question

    old = (previous or {}).get('context', {})
    result = (previous or {}).get('job', {}).get('result', {})
    ids = context['project_ids']
    same_project = len(ids) == 1 and ids == old.get('project_ids')
    if (not same_project or not prior_subject or old.get('meeting_ids')
            or (previous or {}).get('state') != 'done' or not result.get('answerable')
            or result.get('kind') != 'documents'):
        return None
    scope = old.get('time_scope', {})
    cutoff = scope.get('end')
    new_day = _DAY_CHANGE.fullmatch(question) if scope.get('mode') in ('as_of', 'meeting') and cutoff else None
    historical_reason = (
        scope.get('mode') == 'as_of' and cutoff and _PREVIOUS_HOLD_REASON.search(question)
        and re.fullmatch(r'왜\s+(?:(?:상향|하향|변경|조정)(?:을|를)?\s+)?(?:미뤘|보류했)(?:어(?:요)?|나요|지)[?!.\s]*',
                         _PREVIOUS_HOLD_REASON.sub(' ', question).strip())
    )
    reference = _NAMED_STATUS_REFERENCE.fullmatch(question) if scope.get('mode') in (None, 'current', 'as_of') else None
    bare_status = _BARE_STATUS_REFERENCE.fullmatch(question) if scope.get('mode') in (None, 'current', 'as_of') else None
    if not (new_day or historical_reason or reference or bare_status) or not cited_topic(prior_subject,result,docs):
        return None

    if new_day:
        try:
            day = date.fromisoformat(cutoff).replace(day=int(new_day['day']))
        except ValueError:
            return None
        return f"{day.isoformat()} 회의에서 {prior_subject} {new_day['ask']}?", prior_subject

    if historical_reason:
        return f'{cutoff} 기준 {prior_subject} 변경을 왜 보류했어?', prior_subject

    if bare_status:
        prefix=f'{cutoff} 기준 ' if scope.get('mode')=='as_of' and cutoff else ''
        return f'{prefix}{prior_subject} 완료됐어?', prior_subject

    if reference and completion_question(f"{reference['noun']} {reference['status']}"):
        parts = prior_subject.split()
        noun = reference['noun']
        noun_terms = topic_terms(noun)
        matches = [index for index, part in enumerate(parts) if noun_terms and topic_terms(part) == noun_terms]
        if len(matches) == 1:
            target = ' '.join(parts[:matches[0] + 1])
            status = reference['status']
            prefix = f'{cutoff} 기준 ' if scope.get('mode') == 'as_of' and cutoff else ''
            return f'{prefix}{target} {status}', target
    return None


def named_schedule_followup(w,c,question,previous,context,named,available,docs):
    """Carry only a single schedule field into an explicitly named project."""
    ids=context['project_ids']
    if len(named)!=1 or ids!=[named[0]['id']]:
        return None
    old=previous.get('context',{})
    old_ids=old.get('project_ids',[])
    result=previous.get('job',{}).get('result',{})
    reason=_NAMED_SCHEDULE_REASON.fullmatch(question)
    repeat=(result.get('mode')=='recorded_schedule' and old.get('time_scope',{}).get('mode') in (None,'current')
            and re.fullmatch(r'(?:쪽|프로젝트)?(?:은|는|도)?[?!.\s]*',question))
    if not (reason or repeat):
        return None
    if (previous.get('state')!='done' or result.get('kind')!='documents' or not result.get('answerable')
            or old.get('meeting_ids') or len(old_ids)!=1 or not set(old_ids)<={p['id'] for p in available}):
        return None
    question_before=strip_labels(old.get('query') or previous.get('question',''),available)
    fields={' '.join(match[0].split()).removesuffix('자') for match in _SCHEDULE_FIELD.finditer(question_before)}
    if len(fields)!=1:
        return None
    field=fields.pop()
    prior_docs=docs if old_ids==ids else questions.corpus(w,c,old_ids)
    # The schedule reader validates the exact event against the cited lines.
    prior_field=result.get('schedule_subject')
    if not cited_topic(field,result,prior_docs) and not (
        prior_field==field and field=='현장 인수 시험' and cited_topic('인수 시험',result,prior_docs)
    ):
        return None
    if repeat:
        return f'{field}은 언제로 정했어?', field
    particle='이' if field[-1] in '일험' else '가'
    return f'{field}{particle} 왜 바뀌었어?', field


def resolve(w,c,actor,question,previous=None,project_id=None,meeting_id=None,topic_relation=''):
    from work.v3.conversations import subject_in
    question=normalize(question)
    available=[p for p in w.all_records(c,'project') if not p.get('deleted_at') and actor['id'] in p['members']]
    old=(previous or {}).get('context',{})
    old_result=(previous or {}).get('job',{}).get('result',{})
    result_projects,result_meetings=result_entities(previous)
    same_project=SAME_PROJECT.match(question)
    words=question[same_project.end():] if same_project else question
    named=policy.name_matches(available,words)
    intent=metadata_plan(words,available)
    # A validated field follow-up may contain a generic equipment word that
    # the legacy metadata parser otherwise mistakes for a project-list request.
    field_context=bool(project_id and previous and field_project(w,c,actor,question,previous)==project_id)
    if field_context:intent=None;named=[]
    global_metadata=bool(intent and intent['entity']=='project' and intent['operation'] in ('rank','count','list','change_rank') and not named)
    broad=policy.is_broad(question) or global_metadata
    date_followup=re.fullmatch(
        r'\s*(?:(?:그럼|그러면)\s*)?'
        r'(?P<day>(?:20\d{2}\s*(?:년|[-./])\s*)?\d{1,2}\s*(?:월|[-./])\s*\d{1,2}\s*일?)'
        r'\s*(?:에는|은|는|기준(?:으로(?:는)?)?)?\s*(?:어땠(?:어|나요)|어떠했(?:어|나요))?[?!. ]*',
        question)
    date_only=bool(date_followup)
    meeting_ref=bool(MEETING_REFERENCE.search(question))
    field_followup=bool(previous and re.search(ATTRIBUTE,question,re.I) and re.search(r'(?:은|는|도)\s*(?:알려줘|보여줘)?[?!.\s]*$',question))
    task_ref=bool(TOPIC_REFERENCE.search(question))
    ref=bool(same_project) or task_ref or meeting_ref or bool(re.search(r'그럼|그러면|거기|그쪽|(?:그|이)\s*(?:설비|장비|날짜|속도|항목|내용|프로젝트|회의록|때|전|건|거|것)|이유|왜|언제|얼마|같았|유지|보류',question)) or date_only or field_followup
    broad_quantity=not named and not ref and not project_id and not meeting_id and unit_quantity(question)
    broad=broad or broad_quantity
    correction=bool(named and previous and re.match(r'\s*(?:아니|아니고|대신)',question))
    confirming=bool(old_result.get('kind')=='clarification' and (
        named and len(policy.clean(strip_labels(question,named)))<=3 or
        project_id and any(p['id']==project_id for p in old_result.get('projects',[]))))
    ids_from_before=result_projects or old.get('project_ids',[])
    allowed={p['id'] for p in available}
    # A user's established single-project scope survives an empty/failed
    # answer and a new topic. Result count alone must not create this scope.
    active_project=old.get('project_id') or old.get('exploration',{}).get('pinned_id')
    unit_reference=leading_unit_reference(words)
    requested_units=equipment_units(words)
    if not (project_id or broad) and len(named)>1 and unit_reference and len(requested_units)==1:
        # Use an established project only if the requested unit still matches.
        pinned=[p for p in named if p['id']==active_project]
        if pinned and old.get('project_ids')==[active_project]:
            named=pinned
    keep_project=bool(previous and active_project and old.get('project_ids')==[active_project]
                      and not broad and not named and not project_id)
    if project_id:selected=[w.project(c,project_id,actor)]
    elif named:selected=named
    elif keep_project:selected=[w.project(c,active_project,actor)]
    elif previous and (ref or correction) and not broad and len(ids_from_before)==1:
        selected=[w.project(c,ids_from_before[0],actor)]
    else:selected=available
    ids=[p['id'] for p in selected]
    context={'query':question,'project_id':ids[0] if len(ids)==1 and (project_id or named or keep_project or previous and ref and not broad) else None,
             'project_ids':ids,'subject':'','label':'','time_scope':{},'meeting_ids':[]}
    def clarify(message,projects=(),meetings=()):
        return {**context,'clarify':message,'projects':[{'id':p['id'],'name':p['name']} for p in projects],
                'meetings':[{'id':d['meeting_id'],'title':d['title'],'date':d.get('date','')} for d in meetings]}
    if same_project and not project_id and not named and not keep_project and not (len(ids_from_before)==1 and ids_from_before[0] in allowed):
        options=[p for p in available if p['id'] in ids_from_before] if previous else available
        return clarify('어느 프로젝트를 이어서 볼까요? 프로젝트를 선택해 주세요.',options)
    if not project_id and not named and not previous and len(available)>1 and re.search(r'(?:이|그)\s*(?:설비|장비|프로젝트)',question):
        return clarify('어느 프로젝트의 설비를 말씀하시나요? 프로젝트를 선택해 주세요.',available)
    if project_id and requested_units and project_id not in {p['id'] for p in named}:
        return clarify('선택한 프로젝트에서 해당 호기를 확인하지 못했어요.',named)
    from work.v3.project_facts import owner_filter_people
    if not project_id and not named and not owner_filter_people(w,c,available,question):
        uncertain=uncertain_project(available,words)
        if uncertain is not None:
            if not uncertain and unit_reference:
                return clarify(f'조회할 수 있는 프로젝트에서 {unit_reference[0]}를 찾지 못했어요. 호기 번호를 확인해 주세요.')
            return clarify('프로젝트 이름을 확인해 주세요. 아래 프로젝트를 말씀하신 건가요?' if uncertain else '일치하는 프로젝트를 찾지 못했습니다. 이름이나 코드를 확인해 주세요.',uncertain)
    if named and len(named)>1 and not broad and not project_id:
        if unit_reference and len(requested_units)==1:
            return clarify(f'{unit_reference[0]}에 해당하는 프로젝트가 여러 개예요. 어느 프로젝트인지 선택해 주세요.',named)
        return clarify('이 이름에 해당하는 프로젝트가 여러 개입니다. 어느 프로젝트인지 선택해 주세요.',named)
    if previous and ref and not broad and not named and not project_id and len(ids_from_before)>1 and not meeting_ref:
        return clarify('앞 답변에 프로젝트가 여러 개 있습니다. 어느 프로젝트를 이어서 볼까요?',
                       [p for p in available if p['id'] in ids_from_before])
    query=re.sub(r'^\s*(?:거기|그쪽)(?:의|에서|는)?\s*','',words) if ref and len(ids)==1 else words
    replacement_only=not re.search(ATTRIBUTE,strip_labels(question,named),re.I)
    if correction and replacement_only or confirming:
        # Reuse the user's earlier question structure only, after removing its
        # project label. Neither previous generated text nor values are copied.
        query=old.get('query') or previous['question']
        if confirming:
            prefix=re.match(r'^\s*([가-힣a-zA-Z0-9-]+)',query)
            if prefix and len(prefix[1])>=3 and any(edit_distance(prefix[1],part)==1 for p in selected for part in p['name'].split() if len(part)>=3):
                query=query[prefix.end():]
        query=strip_labels(query,available)
        query=re.sub(r'^\s*(?:아니|대신)\s*','',query).strip()
        context['project_id']=ids[0] if len(ids)==1 else None
        intent=metadata_plan(query,available)
    docs=questions.corpus(w,c,ids)
    titles=sorted({e['title'] for e in w.all_records(c,'change_event') if e.get('project_id') in ids
                   and not e.get('superseded_by_revision') and e.get('review_state')!='제외'})
    subject='' if intent else subject_in(query,titles)
    new_attribute=bool(intent or re.search(ATTRIBUTE+r'|논의\s*주제|회의\s*주제|담당|완료',query,re.I))
    if not new_attribute:
        from work.v3.answer_meaning import completion_question
        from work.v3.content_query import explicit_measurement_reason
        from work.v3.inbound_schedule import request as schedule_request
        new_attribute=completion_question(query) or explicit_measurement_reason(query) or bool(schedule_request(query,selected,{}))
    if topic_relation=='new':new_attribute=True
    if not subject and not intent:
        attr=re.search(r'압연\s*속도|납품일|납기일|납기|점검\s*커버|코팅\s*폭|가압력',query)
        if attr:subject=attr[0]
    inherited=False
    prior_subject=old.get('subject','') or interpreted_subject(previous,ids)
    status_reference=ids==old.get('project_ids') and len(ids)==1 and completion_reference(question,previous)
    if not subject and previous and (ref or correction or confirming) and not broad and not intent:
        if topic_relation!='new' and (not new_attribute or task_ref):
            subject=prior_subject;inherited=bool(subject)
    chosen_docs=[]
    if meeting_id:
        chosen_docs=[d for d in docs if d['meeting_id']==meeting_id]
        if not chosen_docs:raise HTTPException(404,'조회할 수 있는 등록 회의록이 아닙니다.')
    elif meeting_ref and previous and not (named or project_id):
        selected_refs=old.get('selected_documents') or (old.get('chat_memory') or {}).get('selected_documents')
        if selected_refs:
            from work.v3.chat_state import memory
            pinned=memory(w,c,actor,previous).get('selected_meeting_ids',[])
            if len(pinned)!=len(selected_refs):
                return clarify('앞서 선택한 회의록이 변경되었거나 현재 열람할 수 없습니다. 회의록을 다시 선택해 주세요.')
            chosen_docs=[d for d in docs if d['meeting_id'] in pinned]
        else:chosen_docs=[d for d in docs if d['meeting_id'] in result_meetings]
        if len(chosen_docs)!=1:
            return clarify('어느 회의록을 이어서 볼까요?' if chosen_docs else '이어서 볼 회의록을 먼저 찾아 주세요.',meetings=chosen_docs)
    else:
        explicit_docs=[d for d in docs if d['title'] and d['title'] in query]
        if len(explicit_docs)==1:chosen_docs=explicit_docs
        elif not intent and not search_intent(query,selected) and re.search(r'(?:최신|최근|마지막|첫|오래된).*회의록',query):
            head=re.search(r'(.*?회의록)',query)[1]
            lookup=metadata_plan(head,available)
            if lookup:
                found=policy.metadata_answer(w,c,selected,lookup,{})
                doc_ids={s['meeting_id'] for s in found.get('sources',[])}
                chosen_docs=[d for d in docs if d['meeting_id'] in doc_ids]
                if len(chosen_docs)!=1:
                    return clarify('같은 기준의 회의록이 여러 개입니다. 어느 회의록을 볼까요?' if chosen_docs else '조회할 수 있는 등록 회의록이 없습니다.',meetings=chosen_docs)
    if chosen_docs:
        context['meeting_ids']=[d['meeting_id'] for d in chosen_docs]
        subject='';inherited=False
        context['project_ids']=list(dict.fromkeys(d['project_id'] for d in chosen_docs))
        context['project_id']=context['project_ids'][0] if len(context['project_ids'])==1 else None
        query=MEETING_REFERENCE.sub('선택한 회의록',query)
    if not (chosen_docs or broad or intent or topic_relation) and previous:
        residue = strip_labels(question,named).strip()
        carried = scoped_record_followup(residue,previous,context,docs,prior_subject)
        if carried is None:
            carried = named_schedule_followup(w,c,residue,previous,context,named,available,docs)
        if carried:
            resolved, target = carried
            scope = plan_question(resolved,docs)
            return {**context,'query':resolved,'subject':target,'label':selected[0]['name']+' · '+target,
                    'time_scope':{key:scope[key] for key in ('mode','start','end')},
                    'scope_override':True,'record_followup':True}
        if _BARE_STATUS_REFERENCE.fullmatch(residue):
            return clarify('어떤 작업이 끝났는지 말씀하시나요? 작업 이름을 알려주세요.')
    if task_ref and not subject and not chosen_docs and not intent and not topic_terms(strip_labels(query,available)):
        return clarify('어떤 항목이나 업무를 말씀하시는지 알려주세요. 이름이나 관련 내용을 함께 적어 주세요.')
    unresolved=bool(not chosen_docs and previous and ref and not broad and not subject
                    and not new_attribute and not policy.project_lookup(query))
    # Unknown equipment attributes must not silently inherit the old subject
    # just because they contain "why/how much". Resolve this small ambiguity
    # asynchronously, outside the request's DB connection and chat lock.
    if ((inherited or unresolved) and not topic_relation and not (date_only or correction or confirming or named or status_reference)
            and ids==old.get('project_ids') and len(ids)==1
            and os.environ.get('B2_CHAT_CONTENT_MODEL','1')=='1'):
        context.update(query=question,topic_followup={'subject':prior_subject},label=selected[0]['name'])
        return context
    if unresolved:
        return clarify('어떤 항목을 이어서 물으시는지 알려주세요. 예: 납품일, 압연 속도, 점검 커버')
    if date_only and subject:
        query=f"{date_followup['day'].strip()} 기준, {subject} 어땠어?"
    elif status_reference and inherited:query=subject+' '+TOPIC_REFERENCE.sub('',query).strip()
    elif inherited:query=subject+'에 대해, '+query
    if inherited and re.search(r'누가|담당',question):query='회의록에 기록된 '+query
    time_scope=plan_question(query,docs)
    old_scope=old.get('time_scope',{})
    if subject and subject==prior_subject and ids==old.get('project_ids') and not re.search(r'현재|지금|최신|오늘|\d\s*(?:월|일|[-./])',question) and old_scope.get('end') and time_scope['mode'] in ('current','clarify'):
        query=(old_scope['start']+'부터 '+old_scope['end']+'까지 ' if old_scope.get('start') else old_scope['end']+' 기준 ')+re.sub(r'그때|당시','',query)
        time_scope=plan_question(query,docs)
    elif re.search(r'그전|이전',question) and not re.search(r'\d\s*(?:월|일|[-./])',question) and time_scope['mode'] in ('current','clarify'):
        query=re.sub(r'그전|이전\s*회의','변경 전',query)+' 변경 이력';time_scope=plan_question(query,docs)
    if len(query)>500:raise HTTPException(422,'앞 대화와 연결할 수 있도록 질문을 조금 짧게 입력해 주세요.')
    scope_label='전체 프로젝트' if broad_quantity and not chosen_docs else selected[0]['name'] if len(selected)==1 else ''
    context.update(query=query,subject=subject,label=' · '.join(filter(None,(scope_label,subject))),
                   time_scope={k:time_scope.get(k) for k in ('mode','start','end')})
    return context
