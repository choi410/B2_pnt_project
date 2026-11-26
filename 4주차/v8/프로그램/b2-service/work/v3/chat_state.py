"""Server-owned dialogue state. Generated answer prose is never stored as fact."""
from copy import deepcopy
import re
from work.v3.chat_tools import ReadTools
from work.v17.retrieval import document_lines
from fastapi import HTTPException

POINT_ORDINAL = re.compile(r'(?<![가-힣0-9])(첫|두|둘|세|셋|네|넷|다섯|[1-9]\d*)\s*번째(?:\s*(?:항목|업무|내용|거|것)(?=$|[^가-힣]|은|는|을|를|의))?')


def point_focus(w,c,actor,question,previous,project_id=None):
    """Bind a displayed answer position before interpreting its meaning.

    The UI groups points by project. Neither source order nor surviving records
    may renumber those points. Display text is a reference cue, never evidence.
    """
    result=(previous or {}).get('job',{}).get('result',{})
    if result.get('kind')!='documents' or result.get('mode') in (
            'project_owner','project_order','change_rank','change_history','meeting_lookup','meeting_search','count'):
        return None
    if (previous or {}).get('state')!='done' or not result.get('answerable'):return None
    match=POINT_ORDINAL.search(question)
    if match and re.search(r'프로젝트|회의록|회의|원문',question[match.start():]):return None
    groups={}
    for point in result.get('points',[]):groups.setdefault(point.get('project_id') or 'all',[]).append(point)
    points=[point for group in groups.values() for point in group]
    if not match:
        from work.v17.evidence_text import TOPIC_REFERENCE,topic_terms
        from work.v3.content_query import ROLE_WORD
        bare=[t for t in topic_terms(question) if not ROLE_WORD.fullmatch(t)]
        if (len(points)>1 and not (previous or {}).get('context',{}).get('subject') and not bare
                and (TOPIC_REFERENCE.search(question) or re.search(r'누가|담당|기한|언제',question))):
            return {'error':'앞 답변에 항목이 여러 개 있어요. 항목명이나 몇 번째 항목인지 알려주세요.'}
        return None
    n=match[1];index=(int(n) if n.isdigit() else {'첫':1,'두':2,'둘':2,'세':3,'셋':3,'네':4,'넷':4,'다섯':5}[n])-1
    if index>=len(points):
        return {'error':f'앞 답변은 {len(points)}개 항목으로 표시되어 있어요. 문장 안의 업무를 뜻하셨다면 업무명을 알려주세요.'}
    point=points[index];sources={s['id']:s for s in result.get('sources',[]) if s.get('id')}
    tools=ReadTools(w,c,actor);rows=[];seen=set()
    for sid in point.get('sources',[]):
        source=sources.get(sid)
        if not source or not source.get('fingerprint') or not source.get('line_ids'):
            return {'error':'선택한 항목의 원문 근거를 확인할 수 없어요. 항목명으로 다시 조회해 주세요.'}
        try:doc=tools.original(source['meeting_id'],fingerprint=source['fingerprint'],line_ids=source['line_ids'])
        except HTTPException:return {'error':'선택한 항목의 원문이 변경되었거나 현재 열람할 수 없어요. 다시 조회해 주세요.'}
        if (doc['project_id']!=source.get('project_id') or point.get('project_id') not in (None,doc['project_id'])
                or project_id and project_id!=doc['project_id']):
            return {'error':'선택한 답변 항목과 프로젝트가 다릅니다. 항목명을 함께 알려주세요.'}
        for line in doc['lines']:
            key=(doc['meeting_id'],line['id'])
            if key in seen:continue
            seen.add(key);rows.append({'choice':'E'+str(len(rows)+1),'text':line['text'],'line_id':line['id'],
                **{k:doc[k] for k in ('meeting_id','project_id','fingerprint')}})
    if (not rows or len({r['project_id'] for r in rows})!=1 or len(rows)>24
            or sum(len(row['text']) for row in rows)>3000 or len(point.get('text',''))>2000):
        return {'error':'선택한 항목의 범위가 불명확해요. 확인할 업무명을 알려주세요.'}
    focus={'index':index,'display':point.get('text',''),'rows':rows}
    scopes=[sources[sid].get('query_scope',{}) for sid in point.get('sources',[])]
    hints={s.get('target_label') for s in scopes if 'target_index' in s}
    if scopes and all('target_index' in s for s in scopes) and len(hints)==1 and next(iter(hints)):
        focus['topic_hint']=next(iter(hints))
    return focus


def pin_selection(w, c, actor, context):
    """Capture explicit document selection before generation, even if it fails."""
    if not context.get('meeting_ids') or context.get('clarify'):
        return
    docs = ReadTools(w,c,actor).meetings(context.get('project_ids'), meeting_ids=context['meeting_ids'])
    context['selected_documents'] = [{k:d[k] for k in ('meeting_id','project_id','fingerprint')} for d in docs]


def _current(state, projects, docs):
    """Revalidate inherited state, including the clarification/social branches."""
    state = deepcopy(state)
    had_scope = bool(state.get('scope_ids') or state.get('project_ids'))
    for key in ('project_ids','scope_ids'):
        state[key] = [pid for pid in state.get(key,[]) if pid in projects]
    for key in ('meeting_ids',):
        state[key] = [mid for mid in state.get(key,[]) if mid in docs]
    # Preserve displayed positions after deletion/revocation; never reinterpret
    # "the first one" as the next surviving record. Remove the inaccessible ID.
    state['ordered_projects'] = [pid if pid in projects else None for pid in state.get('ordered_projects',[])]
    state['ordered_meetings'] = [mid if mid in docs else None for mid in state.get('ordered_meetings',[])]
    state['selected_documents'] = [ref for ref in state.get('selected_documents',[])
        if (doc:=docs.get(ref.get('meeting_id'))) and doc['fingerprint']==ref.get('fingerprint')
        and doc['project_id']==ref.get('project_id')]
    state['selected_meeting_ids'] = [ref['meeting_id'] for ref in state['selected_documents']]
    evidence = []
    for ref in state.get('evidence',[]):
        doc = docs.get(ref.get('meeting_id'))
        if not doc or doc['fingerprint']!=ref.get('fingerprint') or doc['project_id']!=ref.get('project_id'):
            continue
        valid = {line['id'] for line in document_lines(doc)}
        if set(ref.get('line_ids',[])) <= valid:
            evidence.append(ref)
    state['evidence'] = evidence
    owners = {projects[pid].get('pm') for pid in state['project_ids']}
    state['person_ids'] = [uid for uid in state.get('person_ids',[]) if uid in owners]
    plan = state.get('retrieval_plan')
    if plan:
        for key in ('project_ids','excluded_ids'):
            plan[key] = [pid for pid in plan.get(key,[]) if pid in projects]
        if plan.get('meeting_ids'):
            kept = [mid for mid in plan['meeting_ids'] if mid in docs]
            # A lost document filter must not become an unrestricted lookup.
            if len(kept)!=len(plan['meeting_ids']):state['retrieval_plan']=None
    if had_scope and not (state['scope_ids'] or state['project_ids']):
        state.update(query='', subject='', time_scope={}, retrieval_plan=None)
    return state


def memory(w, c, actor, previous):
    tools = ReadTools(w,c,actor)
    projects = {p['id']:p for p in tools.projects()}
    docs = {d['meeting_id']:d for d in tools.meetings(list(projects))}
    old = (previous or {}).get('context',{})
    result = (previous or {}).get('job',{}).get('result',{})
    if (previous or {}).get('state')=='failed':result={}
    if (result.get('kind')=='clarification' and old.get('chat_memory') and not old.get('selected_documents')) or result.get('mode')=='social':
        return _current(old.get('chat_memory') or {}, projects, docs)
    ids = list(dict.fromkeys(result.get('result_project_ids',[]) or
        [p['id'] for p in result.get('projects',[]) if result.get('kind')=='projects'] or
        [s['project_id'] for s in result.get('sources',[])]))
    mids = list(dict.fromkeys(s['meeting_id'] for s in result.get('sources',[]) if s.get('meeting_id')))
    owners = list(dict.fromkeys(projects[pid].get('pm') for pid in ids
        if pid in projects and projects[pid].get('pm'))) if result.get('mode')=='project_owner' else []
    return _current({'project_ids':ids, 'scope_ids':old.get('project_ids',[]),
        'meeting_ids':mids, 'ordered_projects':ids, 'ordered_meetings':mids, 'person_ids':owners,
        'selected_documents':old.get('selected_documents',[]),
        'evidence':[{k:s[k] for k in ('meeting_id','project_id','fingerprint','line_ids') if k in s}
                    for s in result.get('sources',[]) if s.get('line_ids')],
        'mode':result.get('mode') or ('content' if result.get('kind')=='documents' else ''), 'subject':old.get('subject',''),
        'action':('project_count' if (old.get('retrieval_plan') or {}).get('intent',{}).get('entity')=='project'
                  else 'meeting_count') if result.get('mode')=='count' else '',
        'time_scope':old.get('time_scope') or {}, 'retrieval_plan':old.get('retrieval_plan'),
        'query':old.get('query') or (previous or {}).get('question','')}, projects, docs)


def reference_lines(w,c,actor,previous,project_id=None):
    """Only live original evidence from one established project is a referent.

    Returned IDs/fingerprints are server-owned; only labels/text enter the model.
    Generated answer text and unrelated lines of a cited document are excluded.
    """
    state=memory(w,c,actor,previous)
    ids=state.get('project_ids') or state.get('scope_ids',[])
    if len(ids)!=1 or project_id and project_id not in ids:return []
    tools=ReadTools(w,c,actor);rows=[];seen=set();size=0
    for ref in reversed(state.get('evidence',[])):
        if ref['project_id'] not in ids:continue
        try:doc=tools.original(ref['meeting_id'],fingerprint=ref['fingerprint'],line_ids=ref['line_ids'])
        except HTTPException:continue
        for line in doc['lines']:
            key=(doc['meeting_id'],line['id'])
            if key in seen:continue
            if len(rows)>=24 or size+len(line['text'])>2200:return []  # Clarify rather than hide alternatives.
            seen.add(key);size+=len(line['text'])
            rows.append({'choice':'E'+str(len(rows)+1),'text':line['text'],'line_id':line['id'],
                         **{k:doc[k] for k in ('meeting_id','project_id','fingerprint')}})
    return rows
