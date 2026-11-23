"""Composable, server-owned plans for record lookup conversations.

Only user conditions and database identities survive turns. Generated prose never
becomes a filter or evidence. Unsupported clauses are not silently discarded.
"""
import re
from copy import deepcopy
from datetime import date
from work.v3.query_intent import normalize, strip_labels, metadata_plan
from work.v3 import query_intent
from work.v3.question_scope import plan_question
from work.v3.conversation_followups import available_projects
from work.v3.question_policy import name_matches
from work.v3.metadata_questions import answer, query_scope

DATE_TOKEN = r'(?:20\d{2}\s*년\s*)?\d{1,2}\s*월(?:\s*\d{1,2}\s*일)?|20\d{2}[-./]\d{1,2}(?:[-./]\d{1,2})?|20\d{2}\s*년|작년|지난해|올해|이번\s*해|지난\s*달|이번\s*달|다음\s*달|지난\s*주|이번\s*주|어제|오늘'
OTHER = r'(?:다른|나머지|그\s*외|그\s*밖의)\s*(?:프로젝트|데)'
WORDS = '''회의록 회의 기록 프로젝트 월별로 월별 달별로 달별 프로젝트별로 프로젝트별 표로 표형식으로 목록으로 목록 리스트 형식으로
 정리해줘 정리해서 묶어줘 모아줘 모아서 찾아줘 찾아주세요 찾아줄래 검색해줘 보여줘 보여주세요 보여줄래 알려줘 알려주세요 확인해줘 조회해줘 조회
 기준으로 기준 등록일 회의일 생성일 등록된 등록한 등록 업로드한 업로드된 업로드 올라온 올린 한 했던 열린 개최한
 몇건이나 몇개나 몇건 몇개 개수 갯수 건수 총수 몇 총 합계 모두 전체 모든 전부 다 다시 여기서 그중에서 그중 이중에서 이중 거기서
 그럼 그러면 이번에는 이번엔 이제 는 은 이 가 을 를 의 에서 에는 에 로 으로 중 만 것 거 것은 거는 건 꺼 도 한 된 있나요 있나 있어 없어 없나요 없었어 있었어
 아니 말고 빼고 제외하고 제외해줘 제외 포함해서 포함해줘 포함하고 부터 까지 이전 이후 에만 은요 는요 순으로 순서대로 순서 정렬 최신순 오래된순 오래된 오래된것부터
 최신 최근 가장 제일 첫번째 첫 처음 마지막 나중 먼저 건 개 씩 제한없이 제한 없이 상관없이 기간 날짜 조건 조건없이 조건은 조건는 전부에서는
 제외다풀어줘 제외풀어줘 제외해제 해제 초기화 몇개야 몇건이야 몇건이지 몇개지 건이야 개야 건이지 개지 뿐이야 있니 없니 다시는 재조회 해줘 해줄래 부탁해
 아까 앞의 앞서 이전 결과 목록다시 전체기간 전체프로젝트 전프로젝트 에걸쳐 포함 건가요 인가요 야 지 요 네요 줘 줘요 을까
 바꾸고 바꿔서 바꿔줘 걸로 것으로 그얘기 그이야기 나온 언급된 얘기 이야기'''


def compact(q):
    return re.sub(r'[^가-힣a-z0-9]', '', q)


def slots(question, projects):
    q = normalize(question); named = name_matches(projects, q)
    rest = strip_labels(q, named)
    tight = compact(rest)
    dates = re.findall(DATE_TOKEN, rest)
    other = bool(re.search(OTHER, rest))
    all_projects = bool(re.search(r'(?:전체|모든|전부|전)\s*프로젝트|전부에서는', rest))
    exclude = bool(named and re.search(r'말고|빼고|제외', rest))
    exclude_date = bool(dates and re.search(r'(?:월|일|년)\s*(?:은|는|을|를)?\s*(?:말고|빼고|제외)', rest))
    correction=bool(len(dates)==2 and re.search(r'말고',rest))
    if correction:dates=dates[1:];exclude_date=False
    group = 'month' if re.search(r'월별|달별', rest) else 'project' if re.search(r'프로젝트\s*별', rest) else None
    count = bool(re.search(r'몇\s*(?:개|건)|개수|갯수|건수|총수', rest))
    list_ = bool(group or re.search(r'목록|리스트|표\s*(?:로|형식)|모아|모아서|묶어|찾아|보여|정렬|정리', rest))
    basis = 'registered_at' if re.search(r'등록|업로드|올라온|올린', rest) else 'meeting_date' if re.search(r'회의일|(?:에|월|일)\s*(?:한|했던|열린|개최한)\s*회의', rest) else None
    quantity = re.search(r'(\d+)\s*(?:개|건)', rest)
    residual = re.sub(DATE_TOKEN, '', rest)
    residual = re.sub(OTHER, '', residual)
    residual = re.sub(r'\d+\s*(?:개|건)', '', residual)
    residual = compact(residual)
    residual = re.sub('|'.join(re.escape(x) for x in sorted(set(WORDS.split()), key=len, reverse=True)), '', residual)
    return dict(named=named, dates=dates, date_question=rest, other=other, all_projects=all_projects,
        exclude=exclude, exclude_date=exclude_date, group=group, count=count, listing=list_, basis=basis,
        limit=int(quantity[1]) if quantity else None, residual=residual,
        all_dates=bool(re.search(r'(?:기간|날짜)\s*(?:조건)?\s*(?:은|는)?\s*(?:없이|상관없이)|전체\s*기간', rest)),
        reset_exclusions=bool(re.search(r'제외\s*(?:다\s*)?(?:풀어|해제)', rest)),
        subset=bool(re.search(r'여기서|그중|이중|거기서', rest)),
        direction='oldest' if re.search(r'오래된|처음|먼저', rest) else 'newest' if re.search(r'최신|최근|마지막', rest) else None,
        unlimited=bool(re.search(r'제한\s*없이|전부|모두', rest)),
        table=bool(re.search(r'표\s*(?:로|형식)', rest)),
        restore=bool(re.search(r'(?:아까|앞서|이전)\s*(?:의\s*)?(?:목록|결과)', rest)),
        content_reference=bool(re.search(r'그\s*(?:얘기|이야기|내용|주제)',rest)))


def date_scope(w, c, projects, intent, changes, previous):
    if not changes['dates']:return dict(previous), ''
    text = ' '.join(changes['dates'])
    # Retain an explicitly established year/month for short date follow-ups.
    old_start = previous.get('start') or previous.get('end')
    if re.search(r'작년|지난해|올해|이번\s*해', text):
        year = date.today().year - int(bool(re.search(r'작년|지난해', text)))
        month = re.search(r'(\d{1,2})\s*월', text)
        if month or old_start and previous.get('start','')[:7] == previous.get('end','')[:7]:
            text = f'{year}년 {int(month[1]) if month else int(old_start[5:7])}월'
        else:return {'mode':'period','start':f'{year}-01-01','end':f'{year}-12-31'}, ''
    elif old_start and re.fullmatch(r'\d{1,2}\s*월(?:\s*\d{1,2}\s*일)?', text):
        text = old_start[:4]+'년 '+text
    year_only = re.fullmatch(r'(20\d{2})\s*년', text)
    if year_only:return {'mode':'period','start':year_only[1]+'-01-01','end':year_only[1]+'-12-31'}, ''
    # A single omitted year is inferred only if all accessible records agree.
    if len(changes['dates'])>1:
        text=changes['dates'][0]+'부터 '+changes['dates'][1]+'까지'
    elif re.search(r'기준|까지|이전|이후|부터',changes['date_question']):
        text+=' '+re.search(r'기준|까지|이전|이후|부터',changes['date_question'])[0]
    result = query_scope(w,c,projects,intent,text+' 회의록 목록',{})
    relative = query_intent.relative_period(text)
    if relative:result.update(mode='period', **relative)
    return {k:result.get(k) for k in ('mode','start','end')}, result.get('message','')


def resolve(w,c,actor,question,previous=None,project_id=None,meeting_id=None):
    if meeting_id:return None
    projects=available_projects(w,c,actor); by_id={p['id']:p for p in projects}
    if project_id:w.project(c,project_id,actor)
    old=(previous or {}).get('context',{})
    prior=deepcopy(old.get('retrieval_plan'))
    delta=slots(question,projects)
    if previous and re.fullmatch(r'(?:그럼|그러면)?\s*나머지(?:도|는)?\s*(?:보여줘|알려줘|있어)?[?.! ]*',question):
        return {'query':question,'project_id':None,'project_ids':[],'time_scope':{},'subject':'','label':'',
            'last_retrieval_plan':prior or old.get('last_retrieval_plan'),
            'clarify':'앞선 검색 결과의 나머지인가요, 다른 프로젝트의 자료인가요? 목록의 다음 페이지는 아래 다음 버튼으로 볼 수 있습니다.', 'projects':[]}
    if delta['restore']:
        prior=deepcopy(prior or old.get('last_retrieval_plan'))
    # Explicit reference transfers the complete lookup result into content
    # retrieval, regardless of UI pagination. Never seed facts from AI prose.
    refers=bool(re.match(r'\s*(?:거기서|여기서|그\s*중|이\s*중|그\s*회의들(?:에서)?|그\s*결과)',question))
    open_first=bool(re.search(r'(?:첫|가장\s*오래된)\s*회의(?:록)?\s*(?:의\s*)?원문',question))
    content_ref=bool(re.search(r'내용|요약|안건|원문|근거|납기|납품|속도|합의|보류|담당|미정|변경|비용|용량|결정|얘기',question))
    if prior and refers and content_ref:
        snapshot=execute(w,c,actor,{'retrieval_plan':prior,'label':''})
        docs=snapshot.get('sources',[])
        if not docs and prior['intent']['operation']=='count':
            listing=deepcopy(prior);listing['intent']['operation']='list'
            docs=execute(w,c,actor,{'retrieval_plan':listing,'label':''}).get('sources',[])
        if open_first and docs:
            dated=[s for s in docs if s.get('date')]
            earliest=min((s['date'] for s in dated),default=None)
            docs=[s for s in dated if s['date']==earliest]
        ids=list(dict.fromkeys(s['project_id'] for s in docs));mids=list(dict.fromkeys(s['meeting_id'] for s in docs))
        query=re.sub(r'^\s*(?:거기서|여기서|그\s*중(?:에)?|이\s*중(?:에)?|그\s*회의들(?:에서)?|그\s*결과)', '',question).strip()
        if open_first:query='선택한 회의록 원문 전체 보기'
        elif re.search(r'얘기\s*있는|언급된|나온',question) and not re.search(r'얼마|왜|요약',question):
            query=re.sub(r'얘기\s*있는\s*(?:거|것)|언급된|나온','',query).strip()+' 회의록 찾아줘'
        context={'query':query,'project_id':ids[0] if len(ids)==1 else None,'project_ids':ids,'meeting_ids':mids,
            'time_scope':{'mode':'current','start':None,'end':None},'scope_override':True,'subject':'',
            'label':f'앞선 조회 결과 {len(mids)}건 안에서 · 원문 기준','last_retrieval_plan':prior}
        if not mids:context.update(clarify='앞선 조회 결과에 현재 열람할 수 있는 회의록이 없습니다.',empty_result=True)
        elif open_first and len(mids)>1:context.update(clarify='같은 첫 회의일의 회의록이 여러 개입니다. 회의록을 선택해 주세요.',meetings=[{'id':s['meeting_id'],'title':s['title'],'date':s.get('date')} for s in docs])
        return context
    basic=metadata_plan(question,projects)
    old_result=(previous or {}).get('job',{}).get('result',{})
    if not prior and delta['content_reference'] and delta['listing'] and not delta['residual'] and old.get('query'):
        from work.v17.evidence_text import topic_terms
        terms=topic_terms(strip_labels(old.get('subject') or old['query'],projects))
        if terms:
            prior={'intent':{'entity':'meeting','operation':'list','direction':'newest','basis':'meeting_date','limit':None,'per_project':False,'period':None},
                'project_ids':old.get('project_ids',list(by_id)),'excluded_ids':[], 'time_scope':{'mode':'current','start':None,'end':None},
                'excluded_periods':[],'meeting_ids':[],'group_by':None,'content_query':' '.join(terms)+' 회의록 찾아줘'}
    # Search result sets also support count/regroup/date transformations, while
    # retaining their original content predicate for later project expansion.
    if not prior and old_result.get('mode')=='meeting_search' and not delta['residual'] and (
        delta['count'] or delta['group'] or delta['table'] or delta['subset'] or delta['content_reference']):
        state=old.get('exploration',{})
        prior={'intent':{'entity':'meeting','operation':'list','direction':'newest','basis':'meeting_date','limit':None,'per_project':False,'period':None},
               'project_ids':old.get('project_ids',list(by_id)), 'excluded_ids':state.get('excluded_ids',[]),
               'time_scope':old.get('time_scope',{}),'excluded_periods':[],'meeting_ids':[], 'group_by':None,
               'content_query':state.get('topic_query') or old.get('query','')}
    # Compose project operations with a date on ordinary grounded content turns.
    if not prior and previous and not delta['residual'] and delta['dates'] and (delta['other'] or delta['all_projects'] or delta['exclude'] or delta['named']):
        from work.v3.conversation_followups import resolve as followup
        op='다른 프로젝트는?' if delta['other'] else '전체 프로젝트에서 보여줘' if delta['all_projects'] else ' '.join(p['name'] for p in delta['named'])+(' 말고' if delta['exclude'] else '는?')
        context=followup(w,c,actor,op,previous,project_id)
        if context and not context.get('clarify'):
            selected=[p for p in projects if p['id'] in context['project_ids']]
            scope,error=date_scope(w,c,selected,{'entity':'meeting','basis':'meeting_date'},delta,context.get('time_scope',{}))
            context['time_scope']=scope;context['exploration']['time_scope']=scope
            context['label']=' · '.join(p['name'] for p in selected)+' · 회의일 '+(scope.get('start') or '처음')+' ~ '+(scope.get('end') or '현재')
            if error:context.update(clarify=error,projects=[])
        return context
    # Existing project ranking and content exploration have their own plans.
    # '전체 프로젝트에서' changes scope, not the requested entity.
    if basic and basic['entity']=='project':
        if prior and (delta['all_projects'] or delta['other'] or delta['exclude']):basic=None
        else:return None
    if not prior and re.search(r'(?:그|이)\s*프로젝트',question):return None
    # Preserve content RAG, historical values, and source references. This path
    # handles metadata, not a vocabulary-based approximation of content answers.
    eligible = bool(basic or prior or re.search(r'회의', question))
    content = re.search(r'내용|요약|안건|아젠다|원문|근거|납기|납품|속도|합의|보류|왜|담당|미정|변경|비용|용량',strip_labels(question,projects))
    if not eligible or content:return None
    if delta['residual'] and not basic:
        # Ambiguous ordinals, unknown constraints and deleted records must not
        # become an unrestricted list merely because they contain '회의록'.
        if not prior:return None
        return {'query':question,'project_id':None,'project_ids':[], 'time_scope':{}, 'subject':'','label':'',
                'retrieval_plan':prior,'clarify':'조회 조건을 정확히 구분하지 못했습니다. 프로젝트·기간 또는 원하는 회의록 제목을 함께 알려주세요.',
                'projects':[],'meetings':[]}
    if not basic and not prior and not re.search(r'회의',question):return None
    base = basic or {'entity':'meeting','operation':'list','direction':'newest','basis':'meeting_date','limit':None,'per_project':False,'period':None}
    # Explicit project/meeting entity changes start a new lookup.
    fresh = not prior or basic and basic['entity']!=prior['intent']['entity']
    plan=deepcopy(prior) if not fresh else {'intent':base,'project_ids':list(by_id),'excluded_ids':[],
        'time_scope':{'mode':'current','start':None,'end':None},'excluded_periods':[], 'meeting_ids':[], 'group_by':None}
    ids=[pid for pid in plan['project_ids'] if pid in by_id]
    excluded=set(plan.get('excluded_ids',[])) & set(by_id)
    if delta['reset_exclusions']:excluded=set();plan['excluded_periods']=[];ids=list(by_id)
    if delta['all_projects']:ids=list(by_id);excluded=set();plan['meeting_ids']=[]
    if delta['other']:
        result=(previous or {}).get('job',{}).get('result',{})
        seen=set(result.get('result_project_ids',[])) or {s['project_id'] for s in result.get('sources',[])}
        excluded.update(seen);ids=[pid for pid in by_id if pid not in excluded];plan['meeting_ids']=[]
    named=delta['named']
    if len(named)>1 and not delta['exclude'] and not re.search(r'모두|전부|전체|각|별',question):
        return {'query':question,'project_id':None,'project_ids':[], 'subject':'','label':'','time_scope':{},
                'retrieval_plan':plan,'clarify':'같은 이름에 해당하는 프로젝트가 여러 개입니다. 프로젝트를 선택해 주세요.',
                'projects':[{'id':p['id'],'name':p['name']} for p in named]}
    if delta['exclude']:
        excluded.update(p['id'] for p in named);ids=[pid for pid in ids if pid not in excluded]
    elif named or project_id:
        ids=[project_id] if project_id else [p['id'] for p in named];excluded=set();plan['meeting_ids']=[]
    plan['project_ids']=ids;plan['excluded_ids']=sorted(excluded)
    intent=plan['intent']
    if basic and fresh:intent.update(basic)
    if delta['count']:intent['operation']='count'
    elif delta['listing'] and not (fresh and basic and basic['operation']=='rank'):intent['operation']='list'
    if delta['basis']:intent['basis']=delta['basis']
    if delta['direction']:intent['direction']=delta['direction']
    if delta['limit'] is not None:intent['limit']=min(delta['limit'],100);intent['operation']='list'
    if delta['unlimited']:intent['limit']=None
    if delta['group']:plan['group_by']=delta['group']
    if delta['table']:plan['presentation']='table'
    if delta['all_dates']:plan['time_scope']={'mode':'current','start':None,'end':None};plan['excluded_periods']=[];plan['meeting_ids']=[]
    selected=[by_id[pid] for pid in ids]
    # Resolve dates against the established universe, not only the prior page.
    scope,error=date_scope(w,c,selected or projects,intent,delta,plan['time_scope'])
    if delta['exclude_date']:
        plan['excluded_periods'].append(scope)
    else:plan['time_scope']=scope
    if delta['subset'] and prior:
        # No displayed-page IDs: retain the query's full result universe even
        # when the previous response was a count. Explicit date replacement
        # intersects with the earlier dates for '그중/여기서'.
        before=prior.get('time_scope',{})
        if before.get('start'):scope['start']=max(scope.get('start') or before['start'],before['start'])
        if before.get('end'):scope['end']=min(scope.get('end') or before['end'],before['end'])
        if prior['intent'].get('limit') is not None or prior['intent']['operation']=='rank':
            previous_result=(previous or {}).get('job',{}).get('result',{})
            bounded=[s['meeting_id'] for s in previous_result.get('sources',[]) if s.get('meeting_id')]
            if bounded:plan['meeting_ids']=bounded
    intent['period']=None
    label=(' · '.join(p['name'] for p in selected) if len(selected)<=2 else f'{len(selected)}개 프로젝트') or '조회 대상 없음'
    label+=' · '+('등록일' if intent['basis']=='registered_at' else '생성일' if intent['entity']=='project' else '회의일')+' 기준'
    if scope.get('start') or scope.get('end'):label+=' · '+(scope.get('start') or '처음')+' ~ '+(scope.get('end') or '현재')
    else:label+=' · 전체 기간'
    if excluded:label+=f' · 프로젝트 {len(excluded)}개 제외'
    if plan['excluded_periods']:label+=' · 제외 기간 '+', '.join((p.get('start') or '처음')+' ~ '+(p.get('end') or '현재') for p in plan['excluded_periods'])
    if intent.get('limit') is not None:label+=f" · {'오래된' if intent['direction']=='oldest' else '최근'} {intent['limit']}건 제한"
    if plan.get('content_query'):label+=' · 내용 검색: '+plan['content_query'].replace('회의록 찾아줘','').strip()
    if delta['dates'] and not re.search(r'20\d{2}|작년|올해|지난|이번|오늘|어제',' '.join(delta['dates'])) and scope.get('start'):
        label+=' (연도: 앞선 조건/조회 자료 기준)'
    context={'query':question,'project_id':ids[0] if len(ids)==1 else None,'project_ids':ids,'time_scope':scope,
        'subject':'','label':label,'scope_override':True,'meeting_ids':plan['meeting_ids'],'retrieval_plan':plan,
        'exploration':{'topic_query':'회의록 목록' if intent['entity']=='meeting' else '프로젝트 목록','scope_ids':ids,'excluded_ids':list(excluded),
            'pinned_id':ids[0] if len(ids)==1 and (named or project_id) else None,'time_scope':scope,'meeting_ids':plan['meeting_ids']}}
    if error:context.update(clarify=error,projects=[])
    return context


def execute(w,c,actor,context):
    plan=context['retrieval_plan']; allowed=available_projects(w,c,actor)
    projects=[p for p in allowed if p['id'] in plan['project_ids']]
    scope={**plan['time_scope'],'meeting_ids':plan['meeting_ids'],'excluded_periods':plan['excluded_periods']}
    if plan.get('content_query'):
        from work.v3.question_policy import quick_answer
        found=quick_answer(w,c,projects,actor,plan['content_query'],True,dict(scope))
        if found is None or found.get('kind')=='clarification':
            return found or {'kind':'clarification','answerable':False,'message':'앞선 내용 검색을 다시 확인해 주세요.','points':[],'sources':[]}
        matches=[s['meeting_id'] for s in found.get('sources',[])]
        if matches:scope['meeting_ids']=matches
        else:projects=[]
    result=answer(w,c,projects,plan['intent'],scope)
    result['group_by']=plan.get('group_by');result['presentation']=plan.get('presentation','list')
    result['notice']=context['label']+' · 휴지통·미등록 자료는 제외했습니다.'+(' 원문 표현에 따른 검색이며, 표현이 다른 자료는 빠질 수 있습니다.' if plan.get('content_query') else '')
    return result
