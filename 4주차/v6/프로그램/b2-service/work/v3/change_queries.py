"""Record-backed change-history queries, including ranking -> detail follow-ups."""
import re
from copy import deepcopy
from work.v3 import question_policy as policy
from work.v3.project_facts import active_changes
from work.v3.query_intent import compact, normalize, strip_labels

MODES={'change_rank','change_history'}
ENTITY=r'변경\s*(?:이력|기록|내역|사항)|변경점'
# "최근 변경 수치", "바뀐 값" ask for the ledger's values even without the word
# 이력. A named attribute (압연 속도 ...) still goes to the source reader below.
VALUE_CHANGE=(r'(?:변경|바뀐|바뀌었던|달라진|변동)(?:\s*된)?\s*(?:수치|값|숫자)'
              r'|(?:수치|값|숫자)\s*(?:변경|변화|변동)'
              r'|최근\s*(?:에\s*)?(?:변경|바뀐|바뀌|달라)')
# Question words and polite request endings carry no filter condition. Listing
# every ending in WORDS is brittle ("몇이야", "얼마예요", "나열해 줄래"), so they
# are removed by pattern. Action verbs that change data (삭제해줘) are not here
# and still stop as unsupported conditions.
ASKING=(r'(?:몇|얼마|뭐|무엇|무슨)[가-힣]*|어떤|어느'
        r'|(?:확인|나열|정리|조회|요약)해[가-힣]*|(?:알려|보여|말해)[가-힣]*'
        r'|(?:이에요|예요|에요|인가요|입니까|인지|일까|줄래|주세요|줘)')
# A value question ("값 몇이야") wants the current value first.
VALUE_ASK=r'수치|값|숫자|얼마|몇\s*(?:이|으로|로)'
WORDS='''그럼 그러면 그 그거 그것 그건 그중 이 이거 저 앞서 아까 방금 나온 말한
 변경이력 변경기록 변경내역 변경사항 변경점 기록 이력 내용 내역 상세히 자세히 상세 자세한 상세내용
 어떻게돼 어떻게되 어떻게돼요 어떻게되나요 어떻게되는지 어떻게됐어 어떻게됐는지 어떤건데 어떤거야
 뭐가바뀐거야 뭐가바뀌었어 무엇이바뀌었어 어떤내용이야 어떤내용인지 뭐가있어 무엇이있어 뭐야 무엇인가요
 보여줘 보여주세요 보여줄래 알려줘 알려주세요 알려줄래 찾아줘 찾아주세요 정리해줘 정리해줄래
 목록 목록으로 전부 모두 다 전체 각각 둘다 두개다 프로젝트 전체프로젝트 다른프로젝트 나머지프로젝트 상태
 날짜순 날짜순으로 오래된순 오래된순으로 최신순 최신순으로 최신 최근 처음부터 회의일 기준 기준으로
 합의 확정 요청 보류 철회 된 것 거 건 만 은 는 이 가 을 를 의 에서 에 대한 대해 야 요 좀 더 도
 있나요 있나 있어 어떻게 되어있는지 어떻게되어있어 어떤것들 어떤것들이 순 순으로 정렬해줘
 변경된 변경 바뀐 바뀌었던 바뀌었어 바뀌었나 바뀌었는지 달라진 변동 변화 수치값 수치들 수치 값들 값 숫자
 얼마였어 얼마인지 얼마야 얼마로 얼마 최근에 가장최근 마지막'''


def intent(question,previous=None):
    q=normalize(question)
    prior=(previous or {}).get('job',{}).get('result',{}).get('mode') in MODES
    explicit=bool(re.search(ENTITY,q)) or bool(re.search(VALUE_CHANGE,q) and not re.search(r'회의록|회의\s*목록',q))
    detail=bool(re.search(r'자세|상세|내역|목록|어떻게|뭐가\s*바뀌|뭐가\s*바뀐|내용|기록|합의|확정|요청|보류|철회|다른\s*프로젝트|\d+\s*월',q))
    # Causal or specification questions still need source reading, not a ledger
    # silently substituted for an explanation.
    if re.search(r'왜|이유|원인|근거\s*(?:문장|원문)|원문\s*(?:보여|열어)|담당|책임|PM|pm',q):return False
    if re.search(r'가장|제일|최다',q) and re.search(r'많|적',q):return False
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
        return {**context,'clarify':text,'projects':[{'id':p['id'],'name':p['name']} for p in choices]}
    reference=result.get('mode') in MODES
    previous_ids=[pid for pid in result.get('result_project_ids',[]) if pid in by_id] if reference else []
    all_projects=bool(re.search(r'(?:전체|모든|각)\s*프로젝트|프로젝트\s*별',q))
    others=bool(re.search(r'(?:다른|나머지)\s*프로젝트',q))
    if project_id:selected=[w.project(c,project_id,actor)]
    elif named:selected=named
    elif others and reference:selected=[p for p in ps if p['id'] not in previous_ids]
    elif all_projects:selected=ps
    elif reference:selected=[by_id[pid] for pid in previous_ids]
    else:return stop('어느 프로젝트의 변경 기록을 볼까요?',ps)
    if not selected:return stop('앞 답변의 프로젝트에 현재 열람할 수 있는 변경 기록이 없어요.')
    if len(selected)>1 and not (all_projects or others or re.search(r'둘\s*다|두\s*개\s*다|각각',q)):
        return stop('앞 답변에 프로젝트가 여러 개예요. 어느 프로젝트의 변경 기록을 볼까요?',selected)
    ids=[p['id'] for p in selected]
    context.update(project_ids=ids,project_id=ids[0] if len(ids)==1 else None,
                   label=' · '.join(p['name'] for p in selected))
    # Consume supported conditions completely. Unknown qualifiers must never
    # become an unrestricted history/project list.
    remainder=strip_labels(q,named or selected)
    for token in delta['dates']:remainder=remainder.replace(token,'')
    remainder=compact(remainder);attribute_text=remainder
    remainder=re.sub(ASKING,'',remainder)
    remainder=re.sub('|'.join(re.escape(x) for x in sorted(set(WORDS.split()),key=len,reverse=True)),'',remainder)
    if remainder and not force:
        # Specific equipment attributes keep the existing source-backed answer
        # path; this route is for the ledger itself, not a replacement for RAG.
        from work.v3.conversations import subject_in
        events,_=active_changes(w,c,selected)
        titles=sorted({e.get('title','') for e in events if e.get('title')})
        if subject_in(attribute_text,titles) or re.search(r'속도|납품일|납기|점검커버|코팅폭|검수일',attribute_text):return None
    if remainder or delta['exclude_date'] or delta['exclude']:
        return stop('변경 기록의 어떤 항목이나 조건을 볼까요? 프로젝트·회의일·합의/요청/보류/철회 상태로 조회할 수 있어요.')
    old_query=old.get('change_query') or {}
    inherited=reference and not all_projects and not named
    scope,error=date_scope(w,c,selected,{'entity':'meeting','basis':'meeting_date'},delta,
                           old.get('time_scope',{}) if inherited else {})
    if error:return stop(error)
    states=re.findall(r'합의|확정|요청|보류|철회',strip_labels(q,named))
    states=list(dict.fromkeys('확정' if s=='합의' else s for s in states))
    if not states and inherited:states=old_query.get('states',[])
    if re.search(r'전체\s*(?:상태|기록)|모든\s*(?:상태|기록)',q):states=[]
    # Asking for a value ("변경된 수치") wants the current one first; a plain
    # ledger request keeps the chronological default.
    default='newest' if re.search(VALUE_CHANGE,q) or re.search(VALUE_ASK,q) else 'oldest'
    direction=delta['direction'] or (old_query.get('direction',default) if inherited else default)
    context.update(time_scope=scope,change_query={'project_ids':ids,'states':states,'direction':direction,'time_scope':scope})
    return context


def execute(w,c,actor,context):
    query=context['change_query'];projects=[w.project(c,pid,actor) for pid in query['project_ids']]
    by_id={p['id']:p for p in projects};events,meetings=active_changes(w,c,projects)
    scope=query.get('time_scope') or {};states=query.get('states',[])
    rows=[]
    for e in events:
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
        item={'id':e['id'],'project_id':p['id'],'project_name':p['name'],'date':m.get('date',''),
              'title':e.get('title') or '제목 없음','state':state,'before':e.get('before',''),'after':e.get('after',''),
              'review_state':e.get('review_state','검토 전'),'source_id':sid}
        items.append(item)
        value=(item['before']+' → ' if item['before'] else '')+item['after']
        points.append({'project_id':p['id'],'project_name':p['name'],'text':f'{item["date"]} · {item["title"]} · {state}\n{value}','sources':[sid] if sid else []})
    label=projects[0]['name'] if len(projects)==1 else f'{len(projects)}개 프로젝트'
    return {'kind':'metadata','mode':'change_history','answerable':True,'message':f'{label}의 변경 기록은 {len(items)}건이에요.',
            'count':len(items),'result_project_ids':[p['id'] for p in projects],
            'points':points,'sources':sources,'change_items':items,
            'notice':'변경이력에 등록된 기록 · 회의일 '+('최신순' if query.get('direction')=='newest' else '오래된순')+
            (' · '+(scope.get('start') or '처음')+' ~ '+(scope.get('end') or '현재') if scope.get('start') or scope.get('end') else '')+
            ' · 각 기록 당시의 상태이며, 요청·보류·철회도 포함됩니다. 제외·삭제·구버전 기록은 제외합니다.'}
