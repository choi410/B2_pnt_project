"""Apply explicit conversation operations to user queries and record identities.

No previous generated prose or values are used as evidence. Scope narrowing,
exclusion, date replacement and topic changes have separate lifetimes.
"""
import re
from work.v3.query_intent import strip_labels, normalize
from work.v3.question_scope import plan_question, describe_scope
from work.v3.topic_overview import intent as category_intent, query as category_query, without_date_scope


def visible_entities(previous):
    from work.v3.conversation_context import result_entities
    return result_entities(previous)[0]


def available_projects(w,c,actor):
    return [p for p in w.all_records(c,'project') if not p.get('deleted_at') and actor['id'] in p['members']]


def remember(context,question,projects,project_id=None,previous=None):
    if context.get('clarify'):return context
    from work.v3.question_policy import name_matches
    named=name_matches(projects,question)
    pinned=project_id or (named[0]['id'] if len(named)==1 else None)
    scope=context.get('time_scope',{})
    topic=without_date_scope(strip_labels(context['query'],projects),scope).strip()
    if category_intent(topic) and not category_query(topic).get('dates_only'):
        topic={'time':'기간 관련 내용','cost':'비용 관련 내용','safety':'안전 관련 내용','responsibility':'담당 관련 내용'}[category_intent(topic)]
    context['exploration']={'topic_query':topic,'scope_ids':context['project_ids'],
        'excluded_ids':[],'pinned_id':pinned,'time_scope':scope,'meeting_ids':context.get('meeting_ids',[])}
    return context


def resolve(w,c,actor,question,previous=None,project_id=None,meeting_id=None):
    from work.v3.question_policy import name_matches
    from work.v17.questions import corpus
    q=normalize(question);tight=re.sub(r'\s+','',q).strip('?!.')
    projects=available_projects(w,c,actor);by_id={p['id']:p for p in projects}
    named=name_matches(projects,q)
    old=(previous or {}).get('context',{})
    old_result=(previous or {}).get('job',{}).get('result',{})
    state=old.get('exploration',{})
    visible=[pid for pid in visible_entities(previous) if pid in by_id]
    prior_topic=state.get('topic_query') or without_date_scope(strip_labels(old.get('query',''),projects),old.get('time_scope',{}))
    old_scope=state.get('time_scope') or old.get('time_scope',{})
    old_ids=[pid for pid in state.get('scope_ids',old.get('project_ids',[])) if pid in by_id]
    excluded={pid for pid in state.get('excluded_ids',[]) if pid in by_id}
    pinned=state.get('pinned_id') if state.get('pinned_id') in by_id else None
    residue=re.sub(r'[^가-힣a-z0-9]','',strip_labels(q,named)) if named else tight
    other=bool(re.fullmatch(r'(?:그럼|그러면|또)?(?:다른|나머지|그외|그밖의)프로젝트(?:는|도|에서|에서는)?(?:없어|있어|있나|있나요|없나요|보여줘|알려줘|찾아줘)?',tight))
    exclude_named=bool(named and re.fullmatch(r'(?:그럼|그러면)?(?:프로젝트)?(?:는|은|를|을)?(?:말고|빼고|제외하고)(?:다른프로젝트|나머지)?(?:보여줘|알려줘)?',residue))
    only_named=bool(named and re.fullmatch(r'(?:그럼|그러면)?(?:프로젝트)?(?:에서는|에서|는|은|만|것만|만보여줘|는어때|도|도보여줘)?',residue))
    only_ref=bool(re.fullmatch(r'(?:그럼|그러면)?(?:이|그)프로젝트(?:만|에서는|는|도)(?:보여줘|알려줘)?',tight))
    all_projects=bool(re.fullmatch(r'(?:그럼|그러면)?(?:(?:전체|모든|전부)(?:프로젝트)(?:에서|에서는|로|도)?|전부에서는)(?:다시|도)?(?:보여줘|알려줘)?',tight))
    all_dates=bool(re.fullmatch(r'(?:기간|날짜)(?:조건)?(?:은|는)?(?:없이|상관없이)(?:전부|전체|다)?(?:보여줘|알려줘)?',tight))
    show_all=bool(re.fullmatch(r'(?:그럼|그러면)?(?:전부|전체|모두|다)(?:보여줘|알려줘)',tight))
    ordinal=re.fullmatch(r'(첫|두|세|네|다섯|[1-9]\d*)번째(?:거|것|회의록)(?:의)?(?:원문|전체내용|내용전체)(?:볼래|보여줘|보기|알려줘)?',tight)
    date_query=re.sub(r'^(?:그중|그럼|그러면|그중에서)\s*','',q)
    date_only=bool(re.fullmatch(r'(?:(?:지난|이번)\s*(?:달|주)|어제|오늘|(?:20\d{2}\s*년\s*)?\d{1,2}\s*월(?:\s*\d{1,2}\s*일)?)\s*(?:회의(?:록)?|것|거|기록|내용)?\s*(?:만|에는|은|는|기준)?\s*(?:보여줘|알려줘)?[?!. ]*',date_query))
    operation='open_record' if ordinal else 'other' if other else 'exclude' if exclude_named else 'select' if only_named or only_ref else 'all_projects' if all_projects else 'all_dates' if all_dates else 'period' if date_only else 'show_all' if show_all else None
    if not previous and only_named:return None
    if only_named and (previous or {}).get('job',{}).get('result',{}).get('kind')=='clarification' and not state:return None
    # A new explicit category changes the topic but keeps a deliberately chosen
    # project. It drops exclusions and date restrictions. A fresh chat has none.
    changed=re.sub(r'^(?:그건|그거|이건|이거)?\s*말고\s*|^(?:그럼|그러면)\s*','',q)
    category=category_query(changed,projects)
    new_category=bool(previous and category and not operation and not named and not meeting_id)
    if not operation and not new_category:return None
    ids=list(old_ids);scope=dict(old_scope);topic=prior_topic;meeting_ids=[]
    def response(message=None,empty=False):
        selected=[by_id[pid] for pid in ids if pid in by_id]
        labels=[p['name'] for p in selected]
        scope_label=' · '.join(filter(None,[
            (' · '.join(labels) if len(labels)<=2 else f'{len(ids)}개 프로젝트') if ids else '조회 대상 없음',
            describe_scope(scope) or '전체 회의 기간',
            f'앞선 결과·지정 프로젝트 제외 {len(excluded)}개' if excluded else ''
        ]))
        context={'query':topic or q,'project_id':ids[0] if len(ids)==1 else None,'project_ids':ids,
                 'subject':old.get('subject','') if not new_category else '', 'time_scope':scope,'meeting_ids':meeting_ids,
                 'scope_override':True,'operation':operation or 'new_topic',
                 'label':scope_label,
                 'exploration':{'topic_query':topic,'scope_ids':ids,'excluded_ids':sorted(excluded),
                                'pinned_id':pinned,'time_scope':scope,'meeting_ids':meeting_ids}}
        if message:context.update(clarify=message,empty_result=empty,projects=[],meetings=[])
        return context
    if not previous or previous.get('state')=='failed' or not prior_topic:
        ids=list(by_id);return response('이어서 찾을 주제를 먼저 알려주세요. 예: 일정 관련 내용, 납품일 변경 이력')
    if ordinal:
        items=old_result.get('meetings',[]) if old_result.get('mode')=='meeting_search' else []
        selected=next((s for s in old_result.get('sources',[]) if s.get('meeting_id')==meeting_id),None) if meeting_id else None
        if not selected and meeting_id and old_result.get('kind')=='clarification' and any(m.get('id')==meeting_id for m in old_result.get('meetings',[])):
            m=w.read(c,'meeting',meeting_id)
            if m['project_id'] in by_id:selected={'meeting_id':meeting_id,'project_id':m['project_id']}
        if not selected and items:
            index=({'첫':1,'두':2,'세':3,'네':4,'다섯':5}.get(ordinal[1]) or int(ordinal[1]))-1
            if len(items)<=5 and index<len(items):
                selected=next((s for s in old_result.get('sources',[]) if s['id']==items[index]['source_id']),None)
        if not selected:
            result=response('어느 회의록의 원문 전체를 볼까요? 앞 답변의 원문 보기에서도 확인할 수 있습니다.' if items else '앞 답변에 선택할 회의록 목록이 없습니다. 먼저 회의록을 찾아 주세요.')
            result['meetings']=[{'id':s['meeting_id'],'title':s['title'],'date':s.get('date','')} for s in old_result.get('sources',[]) if s.get('meeting_id') and s['project_id'] in by_id] if items else []
            return result
        w.project(c,selected['project_id'],actor)
        ids=[selected['project_id']];meeting_ids=[selected['meeting_id']]
        topic='선택한 회의록 원문 전체 보기';scope={'mode':'current','start':None,'end':None};excluded=set();pinned=ids[0]
        return response()
    if meeting_id:return None
    if project_id and project_id not in by_id:
        w.project(c,project_id,actor)  # Standard access error, never silently widen.
    if new_category:
        ids=[project_id or pinned] if project_id or pinned else list(by_id)
        topic=changed;scope={'mode':'current','start':None,'end':None};excluded=set()
    elif other:
        # Cumulative exclusions apply only to this exploration chain.
        excluded.update(visible);pinned=None
        ids=[pid for pid in by_id if pid not in excluded]
    elif exclude_named:
        excluded.update(p['id'] for p in named)
        ids=[pid for pid in old_ids if pid not in excluded];pinned=None
    elif only_named or only_ref:
        choices=[p['id'] for p in named] if only_named else visible
        if len(choices)!=1:
            result=response('어느 프로젝트를 이어서 볼까요?')
            result['projects']=[{'id':pid,'name':by_id[pid]['name']} for pid in choices]
            return result
        ids=choices;excluded=set();pinned=ids[0]
    elif all_projects:
        ids=list(by_id);excluded=set();pinned=None
    elif all_dates:
        scope={'mode':'current','start':None,'end':None}
    elif date_only:
        # Month-only follow-ups refer to meeting dates. Use available records
        # to resolve the year; never copy a date from a generated answer.
        date_phrase=re.match(r'(?:(?:지난|이번)\s*(?:달|주)|어제|오늘|(?:20\d{2}\s*년\s*)?\d{1,2}\s*월(?:\s*\d{1,2}\s*일)?)',date_query)[0]
        scope=plan_question(re.sub(r'이번\s+달','이번달',date_phrase)+(' 기준' if '기준' in date_query else ' 회의'),corpus(w,c,ids))
        if scope.get('message'):return response(scope['message'])
        scope={k:scope.get(k) for k in ('mode','start','end')}
        if re.match(r'^그\s*중',q) and (old_scope.get('start') or old_scope.get('end')):
            starts=[x for x in (scope.get('start'),old_scope.get('start')) if x]
            ends=[x for x in (scope.get('end'),old_scope.get('end')) if x]
            scope.update(start=max(starts) if starts else None,end=min(ends) if ends else None,mode='period')
            if scope.get('start') and scope.get('end') and scope['start']>scope['end']:
                scope=old_scope
                return response('앞서 조회한 기간과 이번 기간이 겹치지 않아 표시할 회의 기록이 없습니다.',True)
        meeting_ids=state.get('meeting_ids',[])
    if not ids:return response('현재 열람 가능한 범위에서 더 조회할 프로젝트가 없습니다.',True)
    if not scope.get('mode'):scope={'mode':'current','start':None,'end':None}
    return response()
