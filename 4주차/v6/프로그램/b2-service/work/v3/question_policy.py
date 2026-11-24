"""V3 question scope and source-backed fast answers; no approval is invented."""
import re
from fastapi import HTTPException
from work.v17.retrieval import registered_document, document_lines
from work.v3.question_scope import plan_question, in_scope, value_subject, without_project
from work.v3.query_intent import metadata_plan, normalize, uncertain_project, unresolved_metadata
from work.v3.metadata_questions import answer as metadata_answer, query_scope as metadata_scope
from work.v3.answer_meaning import validate_meaning, completion_answer
from work.v3.topic_search import search as search_meetings
from work.v3.change_approval import published


def clean(text):
    return re.sub(r'[^가-힣a-z0-9]', '', normalize(text))


def project_lookup(question):
    q=clean(question)
    if project_order_question(question):return True
    # Content questions containing 'project' still go through source retrieval.
    return '프로젝트' in q and not any(x in q for x in ('회의','변경','납기','납품','사양','속도','보류','철회','요구','일정')) and any(x in q for x in ('찾','검색','목록','열어','보여','어떤','무슨'))


def name_matches(projects,question):
    q=clean(question)
    exact=[p for p in projects if clean(p['name']) in q or re.search(r'(?<![\w-])'+re.escape(p['id'])+r'(?![\w-])',question,re.I)]
    if exact:return exact
    ignored={'프로젝트','전극','제작','장비','신규','설계','라인','설비','목록','리스트','회의록'}
    matches=[]
    for p in projects:
        words=[clean(x) for x in re.split(r'[\s·_()/-]+',p['name'])]
        words=[x for x in words if len(x)>=2 and x not in ignored and not re.fullmatch(r'\d+호기?',x)]
        hits=[x for x in words if x in q]
        ordinal=[x for x in re.findall(r'\d+호기',p['name']) if x in q]
        if hits:matches.append((p,sum(len(x) for x in hits)+sum(len(x) for x in ordinal)))
    if not matches:return []
    best=max(score for _,score in matches)
    return [p for p,score in matches if score==best]


def scope_projects(w,c,pid,actor,question=''):
    if pid:return [w.project(c,pid,actor)]
    ps=[p for p in w.all_records(c,'project') if not p.get('deleted_at') and actor['id'] in p['members']]
    intent=metadata_plan(question,ps)
    if not ps:
        if intent and intent['entity']=='project':return []
        raise HTTPException(422,'조회할 수 있는 프로젝트가 없습니다.')
    if intent and intent['entity']=='project' and intent['operation'] in ('rank','count') and not name_matches(ps,question):return ps
    return name_matches(ps,question) or ps


def is_broad(question):
    q=clean(question)
    return any(x in q for x in ('전체','모든','각프로젝트','프로젝트별','비교','목록','각각'))


def project_order_question(question):
    """A request to identify a project by order, not its specifications or contents."""
    intent=metadata_plan(question)
    if intent and intent['entity']=='project' and intent['operation']=='rank':
        return {'direction':intent['direction'],'basis':intent['basis']}
    return None


def ordered_projects(w,c,projects,question):
    intent=metadata_plan(question,projects)
    return metadata_answer(w,c,projects,intent,{}) if intent and intent['entity']=='project' else None


def meeting_lookup_order(question,projects=()):
    intent=metadata_plan(question,projects)
    return intent['basis'] if intent and intent['entity']=='meeting' and intent['operation']=='rank' and not intent['per_project'] else None


def latest_meetings(w,c,projects,question,plan):
    intent=metadata_plan(question,projects)
    return metadata_answer(w,c,projects,intent,plan or {}) if intent and intent['entity']=='meeting' else None


def topic_matches(topics,question,projects=()):
    for subject in dict.fromkeys((value_subject(question),value_subject(question,projects))):
        if not subject:continue
        named=[t for t in topics if clean(t['title'])==subject]
        if not named:
            # A complete, explicitly asked attribute may omit its equipment prefix
            # (e.g. 장비 납품일 -> 납품일). Never match a shared prefix such as 장비,
            # expand a category, or infer an alias from arbitrary words in a question.
            named=[t for t in topics if len(subject)>=3 and clean(t['title']).endswith(subject)]
        if named:return named if len(named)==1 else []
    return []


def event_source(e,m,p):
    if not m or m.get('deleted_at') or m.get('analysis_stale') or e.get('superseded_by_revision') or not published(e,m) or e.get('source_revision')!=m['revision']:return None
    doc=registered_document(m)
    if not doc or doc['revision']!=e.get('source_revision'):return None
    lines={l['id']:l['text'] for l in document_lines(doc)}
    refs=[r for r in e.get('evidence',[]) if r in lines]
    if not refs:return None
    return {k:v for k,v in doc.items() if k!='body'}|{'project_name':p['name'],'line_ids':refs,'text':'\n'.join(lines[r] for r in refs),'event_id':e['id'],'score':1.0}


def held_items(w,c,projects,question):
    pattern=r'(?:최근|현재|지금)?(?:회의(?:에서|의)?)?보류(?:된)?(?:변경)?(?:사항|항목|내용|목록)(?:은|는|이|가|을|를)?(?:뭐야|무엇인가요|알려줘|보여줘|모아줘|모아서보여줘|모아주세요)?'
    if not any(re.fullmatch(pattern,q) for q in (clean(question),without_project(question,projects))):return None
    ps={p['id']:p for p in projects};ms={m['id']:m for m in w.all_records(c,'meeting') if m['project_id'] in ps}
    groups={}
    for e in w.all_records(c,'change_event'):
        if e['project_id'] not in ps:continue
        s=event_source(e,ms.get(e['meeting_id']),ps[e['project_id']])
        if s:groups.setdefault((e['project_id'],e['category'],clean(e['title'])),[]).append((e,s))
    documented={m['project_id'] for m in ms.values() if registered_document(m)}
    if documented-{key[0] for key in groups}:return None
    points=[];sources=[]
    for records in groups.values():
        latest=max(e.get('effective_date') or s['date'] for e,s in records)
        held={}
        for e,s in records:
            if (e.get('effective_date') or s['date'])!=latest:continue
            # Quote an explicit held statement; do not repeat a possibly wrong
            # AI state label (e.g. a withdrawn cover request classified as hold).
            clauses=re.split(r'[.!?]\s+|\n',s['text'])
            quote=next((x.strip() for x in clauses if re.search(r'보류했|보류하였|보류한다|보류함|보류하기로',x)),None)
            if not quote:continue
            sid='S'+str(len(sources)+1);sources.append(dict(s,id=sid))
            numeric=tuple(re.findall(r'\d+(?:\.\d+)?',quote))
            identity=numeric or clean(quote)
            if identity in held:
                held[identity]['sources'].append(sid)
                if len(quote)>len(held[identity]['quote']):held[identity]['quote']=quote
            else:held[identity]={'quote':quote,'title':e['title'],'project_id':e['project_id'],'project_name':ps[e['project_id']]['name'],'sources':[sid]}
        for item in held.values():
            quote=item.pop('quote');title=item.pop('title');item['text']=(title+': ' if title not in quote else '')+quote;points.append(item)
    if not points:return None
    return {'kind':'documents','mode':'baseline','answerable':True,'points':points,'sources':sources,'message':'','notice':'변경 항목별 최신 기록에서 보류가 명시된 원문을 모았습니다. 등록되지 않은 후속 결정은 포함하지 않습니다.'}


def recorded_agreements(w,c,projects,question,plan=None):
    ps={p['id']:p for p in projects}
    meetings={m['id']:m for m in w.all_records(c,'meeting') if m['project_id'] in ps}
    docs=[d for m in meetings.values() if (d:=registered_document(m))]
    plan=plan or plan_question(question,docs)
    if plan['mode'] not in ('current','as_of'):return None
    # Only official records (approved, or legacy non-excluded) become ledger answers.
    events=[e for e in w.all_records(c,'change_event') if e['project_id'] in ps and published(e,meetings.get(e.get('meeting_id')))]
    # V3 groups events directly; old imports may have no change_topic record.
    key=lambda e:(e['project_id'],e['category'],clean(e['title']))
    topics=topic_matches(list({key(e):{'id':key(e),'project_id':e['project_id'],'category':e['category'],'title':e['title']} for e in events}.values()),plan['value_question'],projects)
    if not topics:return None  # Unknown subject: search the documents, not a fake empty ledger.
    sources=[];points=[]
    def source(e):
        return event_source(e,meetings.get(e.get('meeting_id')),ps[e['project_id']])
    def add(s):
        existing=next((x for x in sources if x['event_id']==s['event_id']),None)
        if existing:return existing['id']
        sid='S'+str(len(sources)+1);sources.append(dict(s,id=sid));return sid
    for t in sorted(topics,key=lambda t:(t['project_id'],t['title'])):
        related=[e for e in events if key(e)==t['id'] and not e.get('superseded_by_revision') and e.get('review_state')!='제외'
                 and (m:=meetings.get(e.get('meeting_id'))) and not m.get('deleted_at') and in_scope(m,plan)]
        valid=[(e,s) for e in related if (s:=source(e))]
        if len(valid)!=len(related):return None
        # effective_date has not been established as a business-effective date.
        # Divergent dates require source reading, not a silently shifted baseline.
        if any(e.get('effective_date') and e['effective_date']!=s['date'] for e,s in valid):return None
        # Keep model extraction distinct from approval, and require agreement
        # language in the source rather than trusting the classification alone.
        accepted=[]
        for e,s in valid:
            value=e.get('after','').strip()
            scalar=re.match(r'(20\d{2}-\d{2}-\d{2}|\d+(?:\.\d+)?\s*(?:m/min|mm|℃|°C|kg|kW|rpm|%))',value,re.I)
            if scalar:value=scalar[0]
            clauses=re.split(r'[.!?]\s+|\n',s['text'])
            for clause in clauses:
                if re.search(r'보류|미정|철회|(?:합의|확정|승인)(?:하지\s*않|되지\s*않|하지\s*못|되지\s*못)|확정.{0,5}아니',clause):continue
                if clean(value) and clean(value) in clean(clause) and re.search(r'합의했|합의하였|합의한다|합의함|합의했습니다|확정했|확정하였|확정함|승인했|하기로\s*했|유지한다|유지하기로',clause):
                    if e.get('business_state')!='확정':return None
                    accepted.append((dict(e,after=value),s));break
        if not accepted:continue
        latest_date=max(s['date'] for e,s in accepted)
        accepted_ids={e['id'] for e,s in accepted}
        if any(e.get('business_state')=='확정' and s['date']>=latest_date and e['id'] not in accepted_ids for e,s in valid):
            return None  # A newer agreement could not be verified: retrieve its source.
        current=[(e,s) for e,s in accepted if s['date']==latest_date]
        values=list(dict.fromkeys(e['after'] for e,s in current))
        later=[(e,s) for e,s in valid if s['date']>=latest_date and e['id'] not in {x['id'] for x,_ in current}]
        # A later withdrawal/hold may revoke the agreement itself. Only keep
        # a fast value when every later record explicitly preserves that value.
        # Otherwise let the source reader show the qualification or conflict.
        if later:
            if len(values)!=1:return None
            for e,s in later:
                preserved=any(clean(values[0]) in clean(clause) and re.search(r'유지한다|유지하기로|유지했',clause)
                              and not re.search(r'않|못|아니|무효|취소',clause)
                              for clause in re.split(r'[.!?]\s+|\n',s['text']))
                doc=registered_document(meetings[e['meeting_id']])
                pending_only=e.get('business_state')=='요청' and '요청' in s['text'] and re.search(r'(?:합의|승인)(?:하지\s*않|되지\s*않)',s['text']) and not re.search(r'철회|취소|무효',doc['body'])
                if not (preserved or pending_only):return None
        citations=[add(s) for e,s in current]
        if len(values)>1:
            text=t['title']+': 같은 날짜의 회의록에 서로 다른 합의값('+ ' / '.join(values)+')이 기록되어 있습니다. 원문 확인이 필요합니다.'
        else:
            text=t['title']+': '+values[0]+' (회의록에 기록된 합의)'
            if later:
                e,s=max(later,key=lambda x:x[1]['date'])
                citations.extend(add(source) for _,source in later)
                text+=' 이후 '+(e.get('business_state') or '후속')+' 기록이 있으며, 새로운 합의값으로 바꾸지 않았습니다.'
        points.append({'text':text,'project_id':t['project_id'],'project_name':ps[t['project_id']]['name'],'sources':list(dict.fromkeys(citations))})
    if not points:return None  # Let the model explain pending/unknown values from sources.
    return {'kind':'documents','mode':'baseline','answerable':True,'points':points,'sources':sources,'message':'','notice':(plan['notice']+' ' if plan['notice'] else '')+'등록된 회의록의 합의 표현과 변경 기록을 대조한 결과입니다. 별도의 사람 승인 여부를 뜻하지 않습니다.','searched_projects':len(projects),'searched_meetings':len({s['meeting_id'] for s in sources})}


def quick_answer(w,c,projects,actor,question,explicit_scope,plan=None):
    question=normalize(question)
    named=name_matches(projects,question)
    if not explicit_scope and not named:
        uncertain=uncertain_project(projects,question)
        if uncertain is not None:
            return {'kind':'clarification','answerable':False,'message':'프로젝트 이름을 확인해 주세요. 아래 프로젝트를 말씀하신 건가요?' if uncertain else '일치하는 프로젝트를 찾지 못했습니다. 프로젝트명이나 코드를 확인해 주세요.',
                    'projects':[{'id':p['id'],'name':p['name']} for p in uncertain]}
    if not explicit_scope and len(projects)>1 and named and not is_broad(question):
        return {'kind':'clarification','answerable':False,'message':'이 이름에 해당하는 프로젝트가 여러 개입니다. 어느 프로젝트인지 선택해 주세요.','projects':[{'id':p['id'],'name':p['name']} for p in projects]}
    intent=metadata_plan(question,projects)
    if intent:
        plan=metadata_scope(w,c,projects,intent,question,plan or {})
        if plan and plan.get('message') and not intent.get('period'):
            return {'kind':'documents','answerable':False,'points':[],'sources':[],'message':plan['message']}
        return metadata_answer(w,c,projects,intent,plan or {})
    if unresolved_metadata(question,projects):
        return {'kind':'clarification','answerable':False,'projects':[],'message':'조회 기준을 조금 더 알려주세요. 예: 최근 생성한 프로젝트, 회의록 개수, 회의록 최신순'}
    if plan and plan.get('message'):
        return {'kind':'documents','answerable':False,'points':[],'sources':[],'message':plan['message']}
    if question=='선택한 회의록 원문 전체 보기' and (plan or {}).get('meeting_ids'):
        from work.v3.topic_search import full_document
        return full_document(w,c,projects,plan)
    # Resolve bounded current-status lists before synonym expansion turns
    # "변경사항" into a request for the entire historical change sequence.
    if (not plan or plan.get('mode')=='current') and not (plan or {}).get('meeting_ids'):
        held=held_items(w,c,projects,question)
        if held is not None:return held
    from work.v3.topic_overview import search as category_search
    result=category_search(w,c,projects,question,plan or {})
    if result is not None:return result
    from work.v3.content_query import prepare,bind
    docs=[d for m in w.all_records(c,'meeting') if m['project_id'] in {p['id'] for p in projects}
          and (d:=registered_document(m)) and in_scope(d,plan or {})
          and (not (plan or {}).get('meeting_ids') or m['id'] in plan['meeting_ids'])]
    content=prepare(question,projects,docs)
    if content['message']:return {'kind':'clarification','answerable':False,'message':content['message'],'projects':[]}
    question=content['question']
    if plan is not None:
        plan.update(bind(plan,content))
        scoped_plans={}
        for p in projects:
            item=prepare(question,[p],[d for d in docs if d['project_id']==p['id']])
            if item['message']:return {'kind':'clarification','answerable':False,'projects':[],'message':p['name']+': '+item['message']}
            scoped_plans[p['id']]=bind(plan,item)
        plan['content_plans']=scoped_plans
        plan['value_question']=prepare(plan.get('value_question',question),projects,docs)['question']
    result=search_meetings(w,c,projects,question,plan or {})
    if result is not None:
        if content['notice']:result['notice']=(result.get('notice','')+' '+content['notice']).strip()
        return result
    # A bounded meeting-wide status question has no attribute search term.
    # Do not discard every source simply because topic coverage is undefined.
    if plan and plan.get('operation')=='decision' and not plan.get('search_terms') and plan.get('mode')=='meeting':
        from work.v3.answer_meaning import DECISION,NEGATIVE
        from work.v3.topic_search import source_for
        from work.v17.evidence_text import content_line
        ps={p['id']:p for p in projects};sources=[];points=[]
        for doc in docs:
            hits=[l for l in document_lines(doc) if content_line(l['text']) and re.search(DECISION,l['text'])
                  and re.search(r'합의|확정|승인|결정',l['text']) and not re.search(NEGATIVE,l['text'])]
            if not hits:continue
            sid='S'+str(len(sources)+1);p=ps[doc['project_id']]
            sources.append(source_for(doc,p,sid,hits,plan))
            points.append({'text':'합의·결정 표현이 명시된 원문입니다.\n'+'\n'.join('“'+l['text']+'”' for l in hits),
                           'sources':[sid],'project_id':p['id'],'project_name':p['name'],'verification':'source_quote'})
        if points:return {'kind':'documents','mode':'recorded_status','answerable':True,'points':points,'sources':sources,'message':'','notice':plan.get('notice','')}
    result=completion_answer(w,c,projects,question,plan or {})
    if result is not None:return result
    if plan and plan.get('meeting_ids'):return None
    result=recorded_agreements(w,c,projects,question,plan)
    if result is not None:return result
    if not plan or plan['mode']=='current':return held_items(w,c,projects,question)
    return None
