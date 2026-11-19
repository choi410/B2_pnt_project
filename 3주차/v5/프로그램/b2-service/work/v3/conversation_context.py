"""Resolve follow-ups from record identities, never from generated answer prose."""
import re
from fastapi import HTTPException
from work.v3 import question_policy as policy
from work.v3.query_intent import normalize, metadata_plan, uncertain_project, strip_labels, edit_distance
from work.v3.question_scope import plan_question
from work.v17 import questions
from work.v3.topic_search import search_intent

MEETING_REFERENCE=re.compile(r'(?:그|이)\s*회의(?:록)?(?=\s|에서|에|의|는|은|를|을|가|도|내용|안건|[?!.]|$)')

def result_entities(previous):
    result=(previous or {}).get('job',{}).get('result',{})
    if (previous or {}).get('state')=='failed':return [],[]
    # Sources and project results originate in accessible database records.
    projects=list(dict.fromkeys([p['id'] for p in result.get('projects',[]) if result.get('kind')=='projects']+
                               [s['project_id'] for s in result.get('sources',[])]))
    meetings=list(dict.fromkeys(s['meeting_id'] for s in result.get('sources',[]) if s.get('meeting_id')))
    return projects,meetings


def resolve(w,c,actor,question,previous=None,project_id=None,meeting_id=None):
    from work.v3.conversations import subject_in
    question=normalize(question)
    available=[p for p in w.all_records(c,'project') if not p.get('deleted_at') and actor['id'] in p['members']]
    old=(previous or {}).get('context',{})
    old_result=(previous or {}).get('job',{}).get('result',{})
    result_projects,result_meetings=result_entities(previous)
    named=policy.name_matches(available,question)
    intent=metadata_plan(question,available)
    global_metadata=bool(intent and intent['entity']=='project' and intent['operation'] in ('rank','count','list') and not named)
    broad=policy.is_broad(question) or global_metadata
    date_only=bool(re.fullmatch(r'\s*(?:(?:그럼|그러면)\s*)?(?:20\d{2}\s*(?:년|[-./])\s*)?\d{1,2}\s*(?:월|[-./])\s*\d{1,2}\s*일?\s*(?:에는|은|는|기준)?[?!. ]*',question))
    meeting_ref=bool(MEETING_REFERENCE.search(question))
    ref=meeting_ref or bool(re.search(r'그럼|그러면|그\s*(?:날짜|속도|항목|내용|프로젝트|회의록|때|전|건|거|것)|이유|왜|언제|얼마|같았|유지|보류',question)) or date_only
    correction=bool(named and previous and re.match(r'\s*(?:아니|아니고|대신)',question))
    confirming=bool(old_result.get('kind')=='clarification' and (
        named and len(policy.clean(strip_labels(question,named)))<=3 or
        project_id and any(p['id']==project_id for p in old_result.get('projects',[]))))
    ids_from_before=result_projects or old.get('project_ids',[])
    if project_id:selected=[w.project(c,project_id,actor)]
    elif named:selected=named
    elif previous and (ref or correction) and not broad and len(ids_from_before)==1:
        selected=[w.project(c,ids_from_before[0],actor)]
    else:selected=available
    ids=[p['id'] for p in selected]
    context={'query':question,'project_id':ids[0] if len(ids)==1 and (project_id or named or previous and ref and not broad) else None,
             'project_ids':ids,'subject':'','label':'','time_scope':{},'meeting_ids':[]}
    def clarify(message,projects=(),meetings=()):
        return {**context,'clarify':message,'projects':[{'id':p['id'],'name':p['name']} for p in projects],
                'meetings':[{'id':d['meeting_id'],'title':d['title'],'date':d.get('date','')} for d in meetings]}
    if not project_id and not named:
        uncertain=uncertain_project(available,question)
        if uncertain is not None:
            return clarify('프로젝트 이름을 확인해 주세요. 아래 프로젝트를 말씀하신 건가요?' if uncertain else '일치하는 프로젝트를 찾지 못했습니다. 이름이나 코드를 확인해 주세요.',uncertain)
    if named and len(named)>1 and not broad and not project_id:
        return clarify('이 이름에 해당하는 프로젝트가 여러 개입니다. 어느 프로젝트인지 선택해 주세요.',named)
    if previous and ref and not broad and not named and not project_id and len(ids_from_before)>1 and not meeting_ref:
        return clarify('앞 답변에 프로젝트가 여러 개 있습니다. 어느 프로젝트를 이어서 볼까요?',
                       [p for p in available if p['id'] in ids_from_before])
    query=question
    if correction or confirming:
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
    new_attribute=bool(intent or re.search(r'아젠다|어젠다|agenda|안건|논의\s*주제|회의\s*주제|납품|납기|속도|커버|출하|검수|가압력|코팅\s*폭|계약|금액|보증|담당|완료',query,re.I))
    if not subject and not intent:
        attr=re.search(r'압연\s*속도|납품일|납기일|납기|점검\s*커버|코팅\s*폭|가압력',query)
        if attr:subject=attr[0]
    inherited=False
    if not subject and previous and (ref or correction or confirming) and not broad and not intent:
        if not new_attribute or re.search(r'그건|그거|그것',query):
            subject=old.get('subject','');inherited=bool(subject)
    chosen_docs=[]
    if meeting_id:
        chosen_docs=[d for d in docs if d['meeting_id']==meeting_id]
        if not chosen_docs:raise HTTPException(404,'조회할 수 있는 등록 회의록이 아닙니다.')
    elif meeting_ref and previous and not (named or project_id):
        chosen_docs=[d for d in docs if d['meeting_id'] in result_meetings]
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
    elif previous and ref and not broad and not subject and not new_attribute and not policy.project_lookup(query):
        return clarify('어떤 항목을 이어서 물으시는지 알려주세요. 예: 납품일, 압연 속도, 점검 커버')
    if date_only and subject:
        query=re.sub(r'^(?:그럼|그러면)\s*','',question).strip('?! .')
        query=re.sub(r'(?:에는|은|는|기준)$','',query).strip()+' 기준 '+subject+'는 얼마야?'
    elif inherited:query=subject+'에 대해, '+query
    if inherited and re.search(r'누가|담당',question):query='회의록에 기록된 '+query
    time_scope=plan_question(query,docs)
    old_scope=old.get('time_scope',{})
    if subject and subject==old.get('subject') and ids==old.get('project_ids') and not re.search(r'현재|지금|최신|오늘|\d\s*(?:월|일|[-./])',question) and old_scope.get('end') and time_scope['mode'] in ('current','clarify'):
        query=(old_scope['start']+'부터 '+old_scope['end']+'까지 ' if old_scope.get('start') else old_scope['end']+' 기준 ')+re.sub(r'그때|당시','',query)
        time_scope=plan_question(query,docs)
    elif re.search(r'그전|이전',question) and not re.search(r'\d\s*(?:월|일|[-./])',question) and time_scope['mode'] in ('current','clarify'):
        query=re.sub(r'그전|이전\s*회의','변경 전',query)+' 변경 이력';time_scope=plan_question(query,docs)
    if len(query)>500:raise HTTPException(422,'앞 대화와 연결할 수 있도록 질문을 조금 짧게 입력해 주세요.')
    context.update(query=query,subject=subject,label=' · '.join(([selected[0]['name']] if len(selected)==1 else [])+([subject] if subject else [])),
                   time_scope={k:time_scope.get(k) for k in ('mode','start','end')})
    return context
