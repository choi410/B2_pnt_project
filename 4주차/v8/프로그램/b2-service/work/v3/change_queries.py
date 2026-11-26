"""Record-backed change-history queries, including ranking -> detail follow-ups."""
import re
from copy import deepcopy
from datetime import date
from work.v3 import question_policy as policy
from work.v3.project_facts import active_changes
from work.v3.chat_tools import ReadTools
from work.v3.query_intent import compact, normalize, strip_labels

MODES={'change_rank','change_history'}
ENTITY=r'변경\s*(?:이력|기록|내역|사항)|변경점'
WORDS='''그럼 그러면 그 그거 그것 그건 그중 이 이거 저 앞서 아까 방금 나온 말한
 변경이력 변경기록 변경내역 변경사항 변경점 기록 이력 내용 내역 상세히 자세히 상세 자세한 상세내용
 어떻게돼 어떻게되 어떻게돼요 어떻게되나요 어떻게되는지 어떻게됐어 어떻게됐는지 어떤건데 어떤거야
 뭐가바뀐거야 뭐가바뀌었어 무엇이바뀌었어 어떤내용이야 어떤내용인지 뭐가있어 무엇이있어 뭐야 무엇인가요
 보여줘 보여주세요 보여줄래 알려줘 알려주세요 알려줄래 찾아줘 찾아주세요 정리해줘 정리해줄래
 목록 목록으로 전부 모두 다 전체 각각 둘다 두개다 프로젝트 전체프로젝트 다른프로젝트 나머지프로젝트 상태
 날짜순 날짜순으로 오래된순 오래된순으로 최신순 최신순으로 최신 최근 처음부터 회의일 기준 기준으로
 합의 확정 요청 보류 철회 된 것 거 건 만 은 는 이 가 을 를 의 에서 에 대한 대해 야 요 좀 더 도
 있나요 있나 있어 어떻게 되어있는지 어떻게되어있어 어떤것들 어떤것들이 순 순으로 정렬해줘 관련된 관련'''

DELIVERY = r'납품일(?:자)?|납기(?:일|일자)?'
DELIVERY_PROJECTS = re.compile(
    r'(?P<continue>그럼|그러면|이어서|이제)?'
    r'(?P<reset>(?:기간|날짜)(?:조건)?(?:은|는|을)?(?:빼고|없애고|없이|제외하고))?'
    r'(?:(?:전체|모든|전)프로젝트(?:중에서|중에|중|에서|의)?|전체에서)?'
    rf'(?:{DELIVERY})(?:이|가|은|는)?(?:실제로|최종적으로)?'
    r'(?:바뀐|변경된|조정된|(?:변경|조정)(?:이|을)?(?:합의|확정|결정)(?:된|한))'
    r'(?:프로젝트|곳)(?:만|은|는|이|가|을|를)?'
    r'(?:알려줘(?:요)?|알려주세요|보여줘(?:요)?|찾아줘(?:요)?|있어|있나요|뭐야|어디야|목록)?')


def confirmed_delivery_pair(clause):
    """Require explicit before/after dates and a decision in the same sentence."""
    from work.v3.question_scope import DATE
    matches=list(DATE.finditer(clause))
    if len(matches)!=2:
        return False
    before,after=matches
    head=clause[:before.start()]
    states=clause[after.end():]
    if not re.search(DELIVERY,head) or not re.fullmatch(r'\s*(?:에서|→|->|대신)\s*',clause[before.end():after.start()]):
        return False
    if re.search(r'요청|문의|검토|제안|보류|철회|취소|미정|가정|가능|예정|여부|못했|않|아니|가안',clause):
        return False
    if not re.search(r'(?:변경|조정|연기|앞당기).{0,16}(?:합의|확정|결정|하기로\s*(?:했다|함))',states):
        return False
    try:
        first,last=(date(int(m['year'] or 2000),int(m['month']),int(m['day'])) for m in matches)
    except (TypeError,ValueError):
        return False
    if not before['year'] or not after['year']:
        return (first.month,first.day)!=(last.month,last.day)
    return first!=last


def confirmed_delivery_projects(w,c,actor,question,previous,project_id=None,meeting_id=None):
    request=DELIVERY_PROJECTS.fullmatch(compact(question))
    if not request:
        return None
    from work.v17.evidence_text import content_line,normalized
    from work.v17.retrieval import document_lines
    from work.v3.question_scope import describe_scope,in_scope
    from work.v3.topic_search import source_for

    tools=ReadTools(w,c,actor)
    projects=tools.projects([project_id] if project_id else None)
    ids=[p['id'] for p in projects]
    old=(previous or {}).get('context',{})
    inherit=request['continue'] and not request['reset'] and re.search(DELIVERY,old.get('subject','') or old.get('query',''))
    scope=old.get('time_scope',{}) if inherit else {}
    docs=tools.meetings(ids,meeting_ids=[meeting_id] if meeting_id else None)
    docs=[doc for doc in docs if doc.get('date') and in_scope(doc,scope)]
    matches={}
    for doc in sorted(docs,key=lambda d:(d['date'],d['meeting_id']),reverse=True):
        for line in document_lines(doc):
            if not content_line(line['text']):
                continue
            for clause in re.split(r'(?<=[.!?])\s+|\s*[;；]\s*',line['text']):
                if confirmed_delivery_pair(clause):
                    matches.setdefault(doc['project_id'],{}).setdefault(normalized(clause),(doc,line,clause))
    points=[];sources=[]
    for project in projects:
        rows=matches.get(project['id'])
        if not rows:
            continue
        doc,line,quote=next(iter(rows.values()))
        sid=f'S{len(sources)+1}'
        source=source_for(doc,project,sid,[line])
        source['exact_highlights']=source['line_ids']
        sources.append(source)
        points.append({'project_id':project['id'],'project_name':project['name'],'text':quote,'sources':[sid]})
    label=projects[0]['name'] if project_id and projects else '전체 프로젝트'
    scope_label=describe_scope(scope) or '회의일 전체'
    if meeting_id:
        scope_label='선택한 회의록'
    context={'query':question,'project_ids':ids,'project_id':project_id,'meeting_ids':[meeting_id] if meeting_id else [],
             'label':label,'subject':'납품일','time_scope':scope}
    result={'kind':'documents','mode':'confirmed_delivery_projects','answerable':bool(points),'count':len(matches),
            'points':points,'sources':sources,'result_project_ids':list(matches),
            'message':f'납품일 변경 합의가 기록된 프로젝트는 {len(matches)}개예요.' if points else '납품일 변경 합의가 명시된 프로젝트를 확인하지 못했어요.',
            'notice':f'{scope_label} · 열람 가능한 프로젝트 {len(projects)}개 · 등록 회의록 {len(docs)}건 확인. '
                     '이전 날짜와 새 날짜가 함께 적힌 변경 결정을 기준으로 프로젝트마다 최근 근거 한 건을 표시합니다.'}
    return context,result


def intent(question,previous=None):
    q=normalize(question)
    prior=(previous or {}).get('job',{}).get('result',{}).get('mode') in MODES
    explicit=bool(re.search(ENTITY,q))
    detail=bool(re.search(r'자세|상세|내역|목록|어떻게|뭐가\s*바뀌|뭐가\s*바뀐|내용|기록|합의|확정|요청|보류|철회|다른\s*프로젝트|\d+\s*월|그중|관련된.*만',q))
    # Causal or specification questions still need source reading, not a ledger
    # silently substituted for an explanation.
    if re.search(r'왜|이유|원인|근거\s*(?:문장|원문)|원문\s*(?:보여|열어)|담당|책임|PM|pm',q):return False
    if re.search(r'가장|제일|최다',q) and re.search(r'많|적',q):return False
    if not explicit and re.search(r'얼마|언제|며칠|몇\s*일|맞아|맞지',q):return False
    return explicit or prior and detail and not re.search(r'회의록|프로젝트\s*목록',q)


def resolve(w,c,actor,question,previous=None,project_id=None,meeting_id=None,force=False):
    if meeting_id or not (force or intent(question,previous)):return None
    from work.v3.dialogue_plan import slots,date_scope
    ps=[p for p in w.all_records(c,'project') if not p.get('deleted_at') and actor['id'] in p['members']]
    by_id={p['id']:p for p in ps};q=normalize(question);delta=slots(q,ps)
    old=(previous or {}).get('context',{});result=(previous or {}).get('job',{}).get('result',{})
    named=policy.name_matches(ps,q)
    context={'query':question,'project_id':None,'project_ids':[],'meeting_ids':[],
             'subject':'변경 기록','label':'','time_scope':{},'scope_override':True,'change_request':True}
    def stop(text,choices=()):
        return {**context,'clarify':text,'projects':[{'id':p['id'],'name':p['name']} for p in choices],
                **({'clarification_mode':'change_project_choice'} if choices else {})}
    reference=result.get('mode') in MODES
    previous_ids=[pid for pid in result.get('result_project_ids',[]) if pid in by_id] if reference else []
    all_projects=bool(re.search(r'(?:전체|모든|각)\s*프로젝트|프로젝트\s*별',q))
    others=bool(re.search(r'(?:다른|나머지)\s*프로젝트',q))
    pinned=old.get('input_scope',{}).get('project_id') or old.get('exploration',{}).get('pinned_id')
    if not pinned and (previous or {}).get('state')=='done' and result.get('answerable'):
        previous_named=policy.name_matches(ps,(previous or {}).get('question',''))
        if len(previous_named)==1 and old.get('project_ids')==[previous_named[0]['id']]:
            pinned=previous_named[0]['id']
    if project_id:selected=[w.project(c,project_id,actor)]
    elif named:selected=named
    elif others and reference:selected=[p for p in ps if p['id'] not in previous_ids]
    elif all_projects:selected=ps
    elif reference:selected=[by_id[pid] for pid in previous_ids]
    elif not others and pinned in by_id and old.get('project_ids')==[pinned]:selected=[by_id[pinned]]
    elif not others and len(ps)==1:selected=ps
    else:return stop('어느 프로젝트의 변경 기록을 볼까요?',ps)
    if not selected:return stop('앞 답변의 프로젝트에 현재 열람할 수 있는 변경 기록이 없어요.')
    if len(selected)>1 and not (all_projects or others or re.search(r'둘\s*다|두\s*개\s*다|각각',q)):
        return stop('앞 답변에 프로젝트가 여러 개예요. 어느 프로젝트의 변경 기록을 볼까요?',selected)
    ids=[p['id'] for p in selected]
    context.update(project_ids=ids,project_id=ids[0] if len(ids)==1 else None,
                   label=' · '.join(p['name'] for p in selected))
    # Consume supported conditions completely. Unknown qualifiers must never
    # become an unrestricted history/project list.
    remainder=strip_labels(q,named)
    for token in delta['dates']:remainder=remainder.replace(token,'')
    remainder=compact(remainder);attribute_text=remainder
    from work.v3.conversations import subject_in
    events,_=active_changes(w,c,selected)
    titles=sorted({e.get('title','') for e in events if e.get('title')})
    attribute=subject_in(attribute_text,titles)
    old_query=old.get('change_query') or {}
    inherited=reference and not all_projects and not named
    ledger_filter=bool(reference and re.search(r'그중|관련|목록|내역',q))
    if attribute and ledger_filter:
        # Match only the registered subject (or its established alias), never
        # widen a specific attribute into every event of the same category.
        aliases=[attribute]
        if re.search(r'납품|납기',attribute):aliases+=['납품일','납기일','납기']
        remainder=re.sub('|'.join(re.escape(compact(x)) for x in sorted(aliases,key=len,reverse=True)),'',remainder)
    elif attribute:return None
    elif inherited:attribute=old_query.get('title','')
    remainder=re.sub('|'.join(re.escape(x) for x in sorted(set(WORDS.split()),key=len,reverse=True)),'',remainder)
    if remainder and not force:
        # Specific equipment attributes keep the existing source-backed answer
        # path; this route is for the ledger itself, not a replacement for RAG.
        if subject_in(attribute_text,titles) or re.search(r'속도|납품일|납기|점검커버|코팅폭|검수일',attribute_text):return None
    if remainder or delta['exclude_date'] or delta['exclude']:
        return stop('변경 기록의 어떤 항목이나 조건을 볼까요? 프로젝트·회의일·합의/요청/보류/철회 상태로 조회할 수 있어요.')
    scope,error=date_scope(w,c,selected,{'entity':'meeting','basis':'meeting_date'},delta,
                           old.get('time_scope',{}) if inherited else {})
    if error:return stop(error)
    states=re.findall(r'합의|확정|요청|보류|철회',strip_labels(q,named))
    states=list(dict.fromkeys('확정' if s=='합의' else s for s in states))
    if not states and inherited:states=old_query.get('states',[])
    if re.search(r'전체\s*(?:상태|기록)|모든\s*(?:상태|기록)',q):states=[]
    direction=delta['direction'] or (old_query.get('direction','oldest') if inherited else 'oldest')
    context.update(subject=attribute or '변경 기록',time_scope=scope,change_query={'project_ids':ids,'states':states,'direction':direction,'time_scope':scope,'title':attribute})
    return context


def execute(w,c,actor,context):
    from work.v3.service import topic_key

    query=context['change_query'];projects=[w.project(c,pid,actor) for pid in query['project_ids']]
    by_id={p['id']:p for p in projects};events,meetings=ReadTools(w,c,actor).changes([p['id'] for p in projects])
    scope=query.get('time_scope') or {};states=query.get('states',[])
    rows=[]
    for e in events:
        if query.get('title') and e.get('title')!=query['title']:continue
        day=meetings[e['meeting_id']].get('date','')
        if (scope.get('start') and day<scope['start']) or (scope.get('end') and day>scope['end']):continue
        if states and e.get('business_state') not in states:continue
        rows.append(e)
    rows.sort(key=lambda e:(meetings[e['meeting_id']].get('date',''),e.get('created_at',''),e['id']),reverse=query.get('direction')=='newest')
    items=[];sources=[];points=[]
    for e in rows:
        m=meetings[e['meeting_id']];p=by_id[e['project_id']];source=policy.event_source(e,m,p)
        sid='S'+str(len(sources)+1) if source else None
        if source:sources.append(dict(source,id=sid,exact_highlights=source['line_ids']))
        state='합의' if e.get('business_state')=='확정' else e.get('business_state') or '미정'
        title=e.get('title') or '제목 없음'
        topic=topic_key({**e,'category':e.get('category') or '', 'title':title}) if e.get('title') else e['id']
        item={'id':e['id'],'project_id':p['id'],'project_name':p['name'],'date':m.get('date',''),'topic_id':topic,
              'title':title,'state':state,'before':e.get('before') or '','after':e.get('after') or '',
              'review_state':e.get('review_state','검토 전'),'source_id':sid}
        items.append(item)
        value=(item['before']+' → ' if item['before'] else '')+item['after']
        points.append({'project_id':p['id'],'project_name':p['name'],'text':f'{item["date"]} · {item["title"]} · {state}\n{value}','sources':[sid] if sid else []})
    label=projects[0]['name'] if len(projects)==1 else f'{len(projects)}개 프로젝트'
    return {'kind':'metadata','mode':'change_history','answerable':True,'message':f'{label}의 변경 기록은 {len(items)}건이에요.',
            'direction':query.get('direction','oldest'),
            'count':len(items),'result_project_ids':[p['id'] for p in projects],
            'points':points,'sources':sources,'change_items':items,
            'notice':'변경이력에 등록된 기록 · 회의일 '+('최신순' if query.get('direction')=='newest' else '오래된순')+
            (' · '+(scope.get('start') or '처음')+' ~ '+(scope.get('end') or '현재') if scope.get('start') or scope.get('end') else '')+
            ' · 각 기록 당시의 상태이며, 요청·보류·철회도 포함됩니다. 제외·삭제·구버전 기록은 제외합니다.'}
