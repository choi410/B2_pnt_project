"""Execute metadata plans over accessible records, without an LLM."""
from datetime import date, datetime, timezone, timedelta
from work.v17.retrieval import registered_document
from work.v3.query_intent import timestamp, strip_labels


def query_scope(w,c,projects,intent,question,plan):
    """Infer an omitted year from the requested date basis, within access scope."""
    if intent['basis'] not in ('created_at','registered_at','meeting_date'):return plan
    from work.v3.question_scope import plan_question
    ps={p['id'] for p in projects};dates=[]
    is_project=intent['entity']=='project'
    for record in (projects if is_project else w.all_records(c,'meeting')):
        if not is_project:
            doc=registered_document(record)
            if not doc or doc['project_id'] not in ps:continue
            if plan.get('meeting_ids') and record['id'] not in plan['meeting_ids']:continue
        if intent['basis']=='meeting_date':dates.append({'date':doc.get('date','')})
        else:
            key=timestamp(record.get('created_at'))
            if key:dates.append({'date':key.astimezone(timezone(timedelta(hours=9))).date().isoformat()})
    # Preserve an explicitly selected meeting while replacing only date scope.
    return {**plan,**plan_question(strip_labels(question,projects),dates)}


def answer(w,c,projects,intent,plan):
    is_project=intent['entity']=='project'
    basis=intent['basis']; operation=intent['operation']; newest=intent['direction']=='newest'
    if basis not in ('created_at','meeting_date','registered_at'):
        return {'kind':'projects' if is_project else 'documents','answerable':False,'projects':[], 'points':[], 'sources':[],
                'message':basis+' 기준의 순서는 이 조회에서 판단할 수 없습니다. 서비스 생성일·등록일과는 다른 기준입니다.'}
    ps={p['id']:p for p in projects};entries=[]
    period=intent.get('period')
    for record in (projects if is_project else w.all_records(c,'meeting')):
        doc=record if is_project else registered_document(record)
        if not doc or (not is_project and doc['project_id'] not in ps):continue
        if not is_project and plan.get('meeting_ids') and record['id'] not in plan['meeting_ids']:continue
        raw=record.get('created_at') if basis in ('created_at','registered_at') else doc.get('date')
        try:key=timestamp(raw) if basis!='meeting_date' else date.fromisoformat(raw)
        except (TypeError,ValueError):key=None
        if period:
            day=key.astimezone(timezone(timedelta(hours=9))).date().isoformat() if isinstance(key,datetime) else key.isoformat() if key else ''
            if not day or not period['start']<=day<=period['end']:continue
        elif plan.get('start') or plan.get('end'):
            # Explicit date filters use the requested date basis too, not the
            # meeting date when the user asks for upload/creation dates.
            day=key.astimezone(timezone(timedelta(hours=9))).date().isoformat() if isinstance(key,datetime) else key.isoformat() if key else ''
            if not day or plan.get('start') and day<plan['start'] or plan.get('end') and day>plan['end']:continue
        day=key.astimezone(timezone(timedelta(hours=9))).date().isoformat() if isinstance(key,datetime) else key.isoformat() if key else ''
        if any(day and (not p.get('start') or day>=p['start']) and (not p.get('end') or day<=p['end']) for p in plan.get('excluded_periods',[])):continue
        entries.append((record,doc,key))
    result_project_ids=list(dict.fromkeys(doc['id'] if is_project else doc['project_id'] for _,doc,_ in entries))
    noun='프로젝트' if is_project else '회의록';unit='개' if is_project else '건'
    label='생성일' if is_project else '등록일' if basis=='registered_at' else '회의일'
    notice='기준: 서비스에서 프로젝트를 생성한 시각' if is_project else label+' 기준입니다.'
    if period:notice+=' · '+period['start']+' ~ '+period['end']+' (한국 시간)'
    elif plan.get('start') or plan.get('end'):notice+=' · '+(plan.get('start') or '첫 기록')+' ~ '+(plan.get('end') or '최근 기록')
    if operation=='count':
        if intent.get('limit') is not None:
            entries=sorted(entries,key=lambda x: (str(x[2] or ''),x[0]['id']),reverse=newest)[:intent['limit']]
            result_project_ids=list(dict.fromkeys(doc['id'] if is_project else doc['project_id'] for _,doc,_ in entries))
        return {'kind':'metadata','mode':'count','answerable':True,'count':len(entries),'points':[],'sources':[],
                'result_project_ids':result_project_ids,
                'message':('조회 가능한 ' if len(projects)!=1 else projects[0]['name']+'의 ')+noun+('는 ' if is_project else '은 ')+str(len(entries))+unit+'입니다.',
                'notice':notice+(' · 휴지통과 미등록 자료는 제외했습니다.' if not is_project else ' · 휴지통은 제외했습니다.')}
    ranked=[x for x in entries if x[2] is not None]
    ranked.sort(key=lambda x:(x[1].get('title',x[1].get('name','')),x[0]['id']))
    ranked.sort(key=lambda x:x[2],reverse=newest)
    if operation=='rank' and ranked:
        if intent['per_project']:
            boundaries={}
            for item in ranked:boundaries.setdefault(item[1]['project_id'],item[2])
            chosen=[x for x in ranked if x[2]==boundaries[x[1]['project_id']]]
        else:chosen=[x for x in ranked if x[2]==ranked[0][2]]
        if len(chosen)>1 and not intent['per_project']:notice+=' · 같은 '+label+'의 '+noun+' '+str(len(chosen))+unit+'를 함께 표시했습니다.'
    elif operation=='rank':chosen=[]
    else:
        chosen=ranked+[x for x in entries if x[2] is None]
        if intent['limit'] is not None:chosen=chosen[:intent['limit']]
    missing=len(entries)-len(ranked)
    if missing:
        notice+=' · '+label+' 미정 '+str(missing)+unit+('은 날짜 비교에서 제외했습니다.' if operation=='rank' else '은 마지막에 표시했습니다.')
        if is_project and operation=='rank':notice+=' 생성일이 확인되지 않는 '+str(missing)+'개는 비교에서 제외했습니다.'
    if not chosen:
        message='조회할 수 있는 등록된 '+noun+'이 없습니다.' if not entries else label+'이 확인되지 않아 처음·최신 순서를 정할 수 없습니다.'
        return {'kind':'projects' if is_project else 'documents','mode':'project_order' if is_project else 'meeting_lookup', 'answerable':False,'projects':[],'points':[],'sources':[],'meetings':[],'count':0,'result_project_ids':[],'message':message,'notice':notice}
    if is_project:
        people={p['id']:p['name'] for p in w.all_records(c,'person')}
        return {'kind':'projects','mode':'project_order' if operation=='rank' else 'project_list','answerable':True,
                'lookup_order':intent['direction'],'projects':[{'id':p['id'],'name':p['name'],'pm':people.get(p.get('pm'),'미지정'),'created_at':p.get('created_at')} for p,_,_ in chosen],
                'message':('조회 가능한 프로젝트 중 가장 '+('최근에' if newest else '먼저')+' 생성한 프로젝트입니다.' if operation=='rank' else '프로젝트 '+str(len(chosen))+'개를 '+('최신순' if newest else '오래된순')+'으로 표시했습니다.'),'notice':notice}
    points=[];sources=[];meetings=[]
    for m,doc,key in chosen:
        sid='S'+str(len(sources)+1)
        sources.append({k:v for k,v in doc.items() if k!='body'}|{'id':sid,'project_name':ps[doc['project_id']]['name'],'line_ids':[],'text':'','score':1.0})
        text=doc['title']+'\n회의일 '+(doc.get('date') or '미정')
        if basis=='registered_at':text+=' · 등록 '+(m.get('created_at') or '미정')[:16].replace('T',' ')
        points.append({'project_id':doc['project_id'],'project_name':ps[doc['project_id']]['name'],'text':text,'sources':[sid]})
        meetings.append({'source_id':sid,'title':doc['title'],'date':doc.get('date'),'project_id':doc['project_id'],
            'project_name':ps[doc['project_id']]['name'],'registered_at':m.get('created_at'),
            'group_date':key.astimezone(timezone(timedelta(hours=9))).date().isoformat() if isinstance(key,datetime) else key.isoformat() if key else ''})
    return {'kind':'documents','mode':'meeting_lookup','answerable':True,'points':points,'sources':sources,
            'meetings':meetings,'count':len(chosen),'total_count':len(entries),'result_project_ids':result_project_ids,'direction':intent['direction'],
            'message':('프로젝트별 ' if intent['per_project'] else '')+('가장 최근' if newest else '가장 오래된')+' 회의록입니다.' if operation=='rank' else '회의록 '+str(len(chosen))+'건을 표시했습니다.',
            'notice':notice,'lookup_order':basis,'searched_projects':len(projects),'searched_meetings':len(entries)}
