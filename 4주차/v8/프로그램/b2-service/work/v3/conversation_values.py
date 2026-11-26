"""Compare referenced record values without treating prior AI prose as evidence.

History supplies accessible project/field identities and date scopes only.
Every value is reread through the source-verified agreement policy. Unsupported
operations, missing evidence and ambiguous targets stop before broad generation.
"""
import re
from datetime import date
from work.v3 import question_policy as policy
from work.v3.query_intent import compact, strip_labels, ATTRIBUTE
from work.v3.question_scope import describe_scope, plan_question, DATE


def titles_for(w,c,pid):
    return sorted({e['title'] for e in w.all_records(c,'change_event')
                   if e.get('project_id')==pid and not e.get('deleted_at')
                   and not e.get('superseded_by_revision') and e.get('review_state')!='제외'})


def lookup(w,c,project,ref):
    scope=ref.get('time_scope') or {}
    if scope.get('mode') not in (None,'current','as_of'):return None
    title=ref['title'];q=title+'는 얼마야?'
    plan={'mode':scope.get('mode') or 'current','start':None,'end':scope.get('end'),
          'value_question':q,'message':'','notice':describe_scope(scope)}
    result=policy.recorded_agreements(w,c,[project],q,plan)
    values=(result or {}).get('values',[])
    if len(values)!=1 or values[0]['title']!=title:return None
    value=values[0]['value'].strip();kind=None;unit='';key=None
    try:key=date.fromisoformat(value);kind='date'
    except ValueError:
        scalar=re.fullmatch(r'([-+]?\d+(?:\.\d+)?)\s*(m/min|mm|℃|°C|kg|kW|rpm|%)',value,re.I)
        if scalar:kind='number';key=float(scalar[1]);unit=scalar[2]
    if not kind:return None
    return {'project_id':project['id'],'project_name':project['name'],'title':title,'value':value,
            'kind':kind,'unit':unit,'key':key,'since':values[0]['since'],
            'sources':result['sources'],'time_scope':scope}


def resolve_test_width(w, c, actor, question, past, context):
    from work.v3.answer_meaning import completion_question

    reference = re.search(r'(?<![가-힣])그\s*폭으로(?=$|[^가-힣])', question)
    if not reference or not completion_question(question) or context.get('clarify'):
        return False
    ids = context.get('project_ids', [])
    if len(ids) == 1:
        project = w.project(c, ids[0], actor)
        for message in reversed(past[-12:]):
            result = message.get('job', {}).get('result', {})
            if result.get('mode') in ('project_list', 'project_order', 'project_owner', 'meeting_lookup', 'count'):
                break
            values = [row for row in result.get('values', []) if row['project_id'] == project['id']
                      and row['title'].endswith('폭')]
            if not values:
                continue
            if len(values) == 1:
                row = values[0]
                verified = lookup(w, c, project, {
                    'title': row['title'], 'time_scope': message.get('context', {}).get('time_scope', {}),
                })
                if verified and verified['unit'].lower() == 'mm' and verified['value'] == row['value']:
                    width = re.sub(r'\s+', '', verified['value'])
                    context['query'] = question[:reference.start()] + row['title'] + ' ' + width + '로' + question[reference.end():]
                    context['scope_override'] = True
                    return True
            break
    context['clarify'] = '어느 폭으로 진행한 시험인지 확인이 필요해요. 폭의 항목명과 수치를 알려주세요.'
    return True


def references(w,c,projects,past,question,operation):
    from work.v3.conversations import subject_in
    refs=[];seen=set();group=None
    wanted_speed=operation=='units' and '속도' in question
    field_question=strip_labels(question,list(projects.values()))
    explicit_field=bool(re.search(ATTRIBUTE,field_question,re.I))
    for message in reversed(past[-12:]):
        result=message.get('job',{}).get('result',{});context=message.get('context',{})
        if message.get('state')!='done' or not result.get('answerable') or result.get('mode')=='social':continue
        if result.get('mode') in ('project_list','project_order','project_owner','meeting_lookup','count'):break
        prior_refs=context.get('value_references')
        if prior_refs:
            candidates=prior_refs
        else:
            ids=list(dict.fromkeys(s['project_id'] for s in result.get('sources',[])))
            candidates=[]
            for pid in ids:
                if pid not in projects:continue
                titles=titles_for(w,c,pid)
                title=context.get('subject')
                if title not in titles:title=subject_in(context.get('query') or message['question'],titles)
                if title:candidates.append({'project_id':pid,'title':title,'time_scope':context.get('time_scope',{})})
        for ref in candidates:
            pid=ref['project_id'];title=ref['title']
            if pid not in projects:continue
            titles=titles_for(w,c,pid)
            requested=subject_in(field_question,titles)
            if requested:
                title=requested;ref={**ref,'title':title}
            elif explicit_field:
                continue
            if title not in titles:continue
            if wanted_speed and '속도' not in title:continue
            if operation=='dates':
                if group is None:group=title
                if title!=group:continue
            identity=(pid,title)
            if identity in seen:continue
            seen.add(identity);refs.append(ref)
        if operation=='previous' and refs:break
        if operation=='dates' and refs and re.search(r'그(?:둘|두|셋|세|넷|네|\d)',compact(question)):break
        if len(refs)>=12:break
    return refs


def resolve(w,c,actor,question,past,project_id=None,meeting_id=None):
    if not past or meeting_id:return None
    q=compact(question)
    previous=next((m for m in reversed(past) if m.get('job',{}).get('result',{}).get('mode')!='social'),None)
    if not previous:return None
    old=previous.get('context',{});old_result=previous.get('job',{}).get('result',{})
    operation=('units' if '단위' in q and re.search(r'같|다르|비교|환산',q) else
               'dates' if re.search(r'날짜|납품|납기|일정|검수|출하|출고|교육',q) and re.search(r'빠른|빠르|빨라|이른|늦|먼저|정렬|날짜순',q) else
               'previous' if re.search(r'원래|그전|변경전|이전값',q) and re.search(r'언제|얼마|값|몇|기준',q) and not re.search(r'회의록|원문',q) else None)
    projects={p['id']:p for p in w.all_records(c,'project') if not p.get('deleted_at') and actor['id'] in p['members']}
    named=policy.name_matches(list(projects.values()),question)
    if project_id:
        w.project(c,project_id,actor)
        projects={pid:p for pid,p in projects.items() if pid==project_id}
    select=bool(old_result.get('mode')=='value_comparison' and len(named)==1 and
                re.fullmatch(r'(?:그럼)?(?:프로젝트)?(?:것|거)?(?:만|은|는)?(?:다시)?(?:짧게|간단히)?(?:보여줘|알려줘|정리해줘)?',compact(strip_labels(question,named))))
    if not operation and not select:return None
    operation='select' if select else operation
    if operation!='previous' and not select and not re.search(r'두|둘|세|셋|네|넷|\d+|그|앞|비교|프로젝트|같은',q):return None
    refs=old.get('value_references',[]) if select else references(w,c,projects,past,question,operation)
    if named:refs=[r for r in refs if r['project_id'] in {p['id'] for p in named}]
    refs=[r for r in refs if r['project_id'] in projects]
    context={'query':question,'project_id':None,'project_ids':list(dict.fromkeys(r['project_id'] for r in refs)),
             'subject':refs[0]['title'] if refs and len({r['title'] for r in refs})==1 else '',
             'time_scope':{'mode':'current','start':None,'end':None},'meeting_ids':[],
             'scope_override':True,'label':'앞 대화의 등록 기록 기준','value_references':refs}
    def stop(text):
        return context,{'kind':'clarification','answerable':False,'message':text,'points':[],'sources':[],
                        'projects':[{'id':pid,'name':projects[pid]['name']} for pid in context['project_ids']]}
    if re.search(r'제외|빼고|말고|완료된|취소된|진행중|위험|평균|합계|삭제|수정해',q):
        return stop('이 비교에서는 해당 조건을 적용하지 못해요. 비교할 프로젝트와 항목을 직접 지정해 주세요.')
    if DATE.search(question):
        from work.v17.questions import corpus
        scope=plan_question(question,corpus(w,c,context['project_ids']))
        if scope.get('mode')!='as_of' or scope.get('message'):return stop(scope.get('message') or '비교할 기준일 하나를 지정해 주세요.')
        refs=[{**r,'time_scope':{k:scope.get(k) for k in ('mode','start','end')}} for r in refs]
    count_match=re.search(r'(두|둘|세|셋|네|넷|\d+)(?:개|프로젝트|속도|항목|값|중)',q)
    count=(int(count_match[1]) if count_match[1].isdigit() else {'두':2,'둘':2,'세':3,'셋':3,'네':4,'넷':4}[count_match[1]]) if count_match else None
    if count and len(refs)!=count:return stop('앞 대화에서 비교할 '+str(count)+'개 대상을 명확히 찾지 못했어요. 프로젝트와 항목을 지정해 주세요.')
    if not refs or operation not in ('previous','select') and len(refs)<2:return stop('비교할 프로젝트와 항목을 먼저 알려주세요.')
    rows=[lookup(w,c,projects[r['project_id']],r) for r in refs]
    if any(row is None for row in rows):return stop('비교 대상 중 합의값을 원문에서 확실히 확인하지 못한 항목이 있어요. 해당 항목의 변경 기록을 먼저 확인해 주세요.')
    focus=[];message='';mode='value_comparison'
    if operation=='previous':
        if len(rows)!=1:return stop('어느 프로젝트 항목의 이전 값을 볼까요?')
        current=rows[0];ref=refs[0]
        days=sorted({m.get('date','') for m in w.all_records(c,'meeting') if m.get('project_id')==ref['project_id']
                     and not m.get('deleted_at') and m.get('date','')<current['since']},reverse=True)
        older=None
        for day in days:
            candidate=lookup(w,c,projects[ref['project_id']],{**ref,'time_scope':{'mode':'as_of','start':None,'end':day}})
            if not candidate:return stop('이전 합의값을 원문에서 확실히 확인하지 못했어요. 과거 변경 기록을 확인해 주세요.')
            if candidate['value']!=current['value']:older=candidate;break
        if not older:return stop('등록된 기록에서 이 항목의 다른 이전 합의값을 확인하지 못했어요.')
        rows=[older];message=f"변경 전 {current['title']}은 {older['value']}입니다. 이후 기록된 합의값은 {current['value']}입니다."
        rows[0]['sources']=older['sources']+current['sources'];mode='previous_value'
    elif operation=='dates':
        if any(r['kind']!='date' for r in rows):return stop('날짜로 확인되는 항목끼리만 순서를 비교할 수 있어요.')
        reverse=bool(re.search(r'늦|내림',q));rows.sort(key=lambda r:r['key'],reverse=reverse)
        winner=bool(re.search(r'어느|어떤|뭐|누가|먼저.*(?:건|것)',q))
        focus=[r['project_id'] for r in rows if r['key']==rows[0]['key']] if winner else []
        message=(' · '.join(projects[pid]['name'] for pid in focus)+'의 날짜가 가장 '+('늦어요.' if reverse else '빨라요.')) if focus else '회의록에서 확인한 합의 날짜순입니다.'
    elif operation=='units':
        if any(r['kind']!='number' for r in rows):return stop('단위가 명시된 수치 항목을 지정해 주세요.')
        same=len({r['unit'].casefold().replace('℃','°c') for r in rows})==1
        message='기록된 단위는 같습니다. 서로 다른 항목의 값은 구분해서 보세요.' if same else '서로 다른 단위입니다. 기록된 숫자를 같은 척도로 비교하거나 서로 환산하지 않았습니다.'
    else:message='선택한 프로젝트의 합의값입니다.'
    sources=[];points=[]
    for row in rows:
        ids=[]
        for source in row['sources']:
            existing=next((s for s in sources if s.get('event_id')==source.get('event_id') and s['meeting_id']==source['meeting_id']),None)
            if not existing:
                existing={**source,'id':'S'+str(len(sources)+1),'exact_highlights':source['line_ids']};sources.append(existing)
            ids.append(existing['id'])
        points.append({'project_id':row['project_id'],'project_name':row['project_name'],'text':row['title']+': '+row['value'],'sources':list(dict.fromkeys(ids))})
    context['project_ids']=list(dict.fromkeys(r['project_id'] for r in rows))
    context['project_id']=focus[0] if len(focus)==1 else context['project_ids'][0] if len(context['project_ids'])==1 else None
    context['value_references']=[{'project_id':r['project_id'],'title':r['title'],'time_scope':r['time_scope']} for r in rows]
    return context,{'kind':'documents','mode':mode,'answerable':True,'message':message,'points':points,'sources':sources,
                    'result_project_ids':focus or context['project_ids'],'focus_project_ids':focus,
                    'notice':'대화에서 언급한 대상의 등록 기록과 원문을 다시 대조했습니다. 요청·보류를 합의값으로 취급하지 않습니다.'}
