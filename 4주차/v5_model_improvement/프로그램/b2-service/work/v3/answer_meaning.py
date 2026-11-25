"""Conservative status-claim checks, in addition to citation/number validation.

This is a bounded contradiction guard, not a general entailment guarantee.
When a decision claim cannot be supported, return the actual cited wording.
"""
import re
from work.v17.evidence_text import topic_terms, coverage, content_line, normalized

DECISION = r'(?:확정|합의|승인|결정)(?:되었|됐|된|됨|했다|했|하였|한다|함|입니다|되었습니다|되었습니다)|하기로\s*(?:했|합의|결정|정했)'
NEGATIVE = r'(?:확정|합의|승인|결정).{0,8}(?:않|못|아니|없)|미확정|미승인|미정|검토\s*중|보류|철회|취소'
SUBJECTS = (r'속도', r'납품|납기|출하', r'커버|개폐', r'코팅\s*폭', r'가압력', r'온도', r'재질')
DONE = r'완료(?:되었|됐|했|하였|됨|된|했습니다|되었습니다)|끝(?:났|난)|마쳤|마무리(?:했|되었|됐)|반영(?:했|됐|되었)'
NOT_DONE = r'않|못|아니|없|예정|계획|목표|여부|되면|하면|조건|경우|까지.*완료|진행\s*중|재개정|재작업|추가\s*(?:수정|작업)|철회|취소'


def completion_question(question):
    return bool(re.search(r'완료|끝났|끝난|마쳤|마무리|반영.*(?:됐|했)|개정본.*나왔|제작.*들어갔',question))


def completed_fact(text):
    return bool(re.search(DONE,text) and not re.search(NOT_DONE,text))


def clauses(text):
    return [s.strip() for s in re.split(r'(?<!\d)[.!?]\s*|\n',text) if s.strip()]


def numbers(text):
    return set(re.findall(r'\d+(?:\.\d+)?',text))


def dated_claim(claim,sources):
    """A leading meeting date is context, not a specification value.

    Bind it to that meeting's evidence before removing it; a later approval
    may never validate a claim that approval already existed at an earlier date.
    """
    m=re.match(r'^\s*(?:(20\d{2})\s*(?:년|[-./])\s*)?(\d{1,2})\s*(?:월|[-./])\s*(\d{1,2})\s*일?(?!\d)',claim)
    if not m:return claim,None
    dates={s.get('date','') for s in sources if re.fullmatch(r'20\d{2}-\d{2}-\d{2}',s.get('date',''))
           and (not m[1] or int(s['date'][:4])==int(m[1])) and int(s['date'][5:7])==int(m[2]) and int(s['date'][8:10])==int(m[3])}
    if len(dates)!=1:return claim,[]
    rest=re.sub(r'^\s*(?:회의(?:에서|에서는|에는)?|에는|에|기준)?\s*[:：·-]?\s*','',claim[m.end():])
    return rest,[s for s in sources if s.get('date') in dates]


def unsupported_decision(text, sources):
    from work.v3.query_intent import strip_labels
    scoped=sources
    claims=[part for clause in clauses(text) for part in re.split(r'[,;]|(?<=[었였했됐])지만|(?<=었)으나|그러나|하지만|이후',clause)]
    for claim in claims:
        claim,dated=dated_claim(claim,sources)
        if dated is not None:
            if not dated:return True
            scoped=dated
        evidence=[clause for s in scoped for clause in clauses(s['text'])]
        if not re.search(DECISION,claim) or re.search(NEGATIVE,claim):continue
        values=numbers(claim)
        subjects=[pattern for pattern in SUBJECTS if re.search(pattern,claim)]
        # Qualitative values and identifiers need support too. An agreement
        # about A-type must never validate a B-type claim just because neither
        # contains a number. Unmatched paraphrases fall back to the source.
        bare=strip_labels(claim,[{'name':s.get('project_name','')} for s in sources])
        properties=[t for t in topic_terms(bare) if not re.match(
            r'^(?:합의|확정|승인|결정|변경|유지|하기|했|하였|되어|되었|됐|되었습니다|이었다|이다|입니다|있|초기|최초|최종|고객|기존|현재|해당|정해)',t)]
        supporting=[e for e in evidence if re.search(DECISION,e) and not re.search(NEGATIVE,e)
                    and values<=numbers(e) and all(re.search(pattern,e) for pattern in subjects)
                    and all(value in normalized(e) for value in properties)]
        if not supporting:return True
    return False


def unsupported_unsettled(text,sources):
    """Missing approval evidence is not evidence of a pending decision."""
    pending=r'미정|미결정|보류|(?:결정|확정)(?:되|하)?지\s*(?:않|못)|정해지지\s*않'
    for sentence in clauses(text):
        for claim in re.split(r'[,;]|지만|그러나|하지만',sentence):
            if not re.search(pending,claim):continue
            anchors=[t for t in topic_terms(claim) if not re.match(r'^(?:관련|사항|아직|결정|확정|정해|않|못|미정|미결정|보류|있|되|하)',t)]
            supported=any(re.search(pending,line) and (not anchors or coverage(line,anchors)>=.75)
                          for s in sources for line in s['text'].splitlines())
            if not supported:return True
    return False


def validate_meaning(points,sources,question=''):
    lookup={s['id']:s for s in sources};result=[]
    shared_terms=next((s['query_scope']['search_terms'] for s in sources if s.get('query_scope',{}).get('search_terms') is not None),None)
    def terms_for(text):return shared_terms if shared_terms is not None else topic_terms(text)
    # A matched alias does not license dropping the rest of the user's request
    # (e.g. asking a named component's price must not return its specification).
    if shared_terms and any(s.get('query_scope',{}).get('subjects') for s in sources):
        if coverage('\n'.join(s['text'] for s in sources),shared_terms)<1:return []
    # Different physical speed attributes cannot borrow each other's numbers.
    # Any supported terminology resolution has already happened in the shared
    # content query; a remaining specific attribute needs its own source.
    speeds=re.findall(r'(?:회전|이송|압연|라인|운전|생산)\s*속도',question)
    if speeds and not all(any(normalized(speed) in normalized(s['text']) for s in sources) for speed in speeds):return []
    def source_quotes(pool,terms):
        chosen=[]
        for s in pool:
            options=[line.strip() for line in s['text'].splitlines() if content_line(line,question) and coverage(line,terms)>=.5]
            # Independent topics sometimes share one physical line. A separate
            # sentence is a valid exact quote; never pick its unrelated neighbor.
            for line in list(options):
                parts=clauses(line)
                if any(any(re.search(pattern,part) for pattern in SUBJECTS) and coverage(part,terms)==0 for part in parts):
                    options.remove(line)
                    options.extend(part for part in parts if coverage(part,terms)>=.5)
            # Full original lines retain request/withdrawal and partial/negative
            # qualifications. Prefer a single-topic statement to agenda lists.
            options.sort(key=lambda line:(coverage(line,terms),
                bool(not re.search(r'이력|과정|경위',question) and re.search(r'않|못|아니|미정|미지정|정하지',line)),
                -sum(bool(re.search(pattern,line)) for pattern in SUBJECTS),
                bool(re.search(r'합의|확정|보류|철회|유지|완료|않|아니',line)),-len(line)),reverse=True)
            if options:chosen.append((s,options[0]))
        chosen.sort(key=lambda x:x[0].get('date',''))
        if len(chosen)>4:chosen=chosen[:1]+chosen[-3:]
        return chosen
    def quote_point(point,chosen):
        text='관련 회의 기록을 날짜순으로 표시합니다.\n'+'\n'.join((s.get('date','')+' ' if s.get('date') else '')+'“'+line+'”' for s,line in chosen)
        return {**point,'text':text,'sources':list(dict.fromkeys(s['id'] for s,_ in chosen)),'verification':'source_quote'}
    # A false premise can make the generator abstain despite explicit negative
    # evidence. Return only directly topic-matched status records in that case.
    if not points and question:
        terms=terms_for(question)
        # Generic specification words are optional only when two concrete
        # anchors remain. Never drop an unknown property such as price/warranty.
        core=[t for t in terms if not isinstance(t,str) or t not in ('방식','사양','항목','수치','결과')]
        if len(core)<2:core=terms
        status=r'합의|확정|보류|철회|유지|요청|미정|미지정|정하지\s*(?:않|못)|담당자.{0,8}없|기한.{0,8}없'
        matched=bool(core and any(content_line(l,question) and coverage(l,core)==1 and re.search(status,l) for s in sources for l in s['text'].splitlines()))
        pool=[s for s in sources if matched and any(content_line(l,question) and coverage(l,terms)>=.5 and re.search(status,l) for l in s['text'].splitlines())]
        chosen=source_quotes(pool,terms)
        if chosen:
            s=chosen[0][0]
            return [quote_point({'project_id':s.get('project_id'),'project_name':s.get('project_name')},chosen)]
    for point in points:
        cited=[lookup[sid] for sid in point['sources']]
        terms=terms_for(question or point['text'])
        scope=next((s.get('query_scope',{}) for s in sources),{})
        latest_cited=max((s.get('date','') for s in cited),default='')
        # A correct old value alone is incomplete when the selected corpus also
        # contains a later qualification, withdrawal or unresolved request.
        # Keep this independent of the generator's preferred citations.
        later_qualification=bool(terms and scope.get('mode','current') in ('current','as_of')
            and re.search(r'얼마|언제|현재|지금|기준|승인|확정|합의|결정',question)
            and any(s.get('date','')>latest_cited and any(coverage(l,terms)>=.75 and re.search(NEGATIVE,l)
                    for l in s['text'].splitlines()) for s in sources))
        completion_claim=bool(re.search(DONE,point['text']) and not re.search(NOT_DONE,point['text']))
        completion_supported=any(completed_fact(e) and (not terms or coverage(e,terms)>=.75)
                                 for s in cited for e in clauses(s['text']))
        unreadable=len(point['text'])>340 or point['text'].count('해당')>=3
        if not unreadable and not later_qualification and not unsupported_decision(point['text'],cited) and not unsupported_unsettled(point['text'],cited) and not (completion_claim and not completion_supported):
            result.append(point);continue
        # Do not rephrase a requested value as approved. Keep a usable answer
        # with exact source quotations, clearly identified as such.
        # A fallback is evidence too. Numbers alone never establish its topic.
        pool=[s for s in sources if not s.get('project_id') or s.get('project_id')==point.get('project_id')]
        chosen=source_quotes(pool,terms)
        if not chosen:continue
        revised=quote_point(point,chosen)
        revised['text']=('변경 경과를 확인할 수 있도록 ' if re.search(r'이력|과정|경위',question) else '관련 내용을 확인할 수 있도록 ')+'원문을 표시합니다.\n'+revised['text'].split('\n',1)[1]
        result.append(revised)
    return result


def completion_answer(w,c,projects,question,plan):
    """Quote latest topic records for status questions; never equate plans with done.

    The quote preserves partial completion, conditions, negation and later rework.
    It is a dated meeting record, not a claim of the current shop-floor state.
    """
    if not completion_question(question):return None
    from work.v3.query_intent import strip_labels
    from work.v3.question_scope import in_scope
    from work.v3.topic_search import source_for
    from work.v17.retrieval import registered_document,document_lines
    terms=topic_terms(strip_labels(question,projects))
    if not terms:return None
    status_label='착수' if re.search(r'제작.*들어갔',question) else '완료'
    points=[];sources=[];searched=0
    for p in projects:
        scoped=plan.get('content_plans',{}).get(p['id'],plan)
        project_terms=scoped.get('search_terms')
        if project_terms is not None:terms=project_terms
        records=[]
        for m in w.all_records(c,'meeting'):
            if m['project_id']!=p['id']:continue
            doc=registered_document(m)
            if not doc or not in_scope(doc,plan) or plan.get('meeting_ids') and m['id'] not in plan['meeting_ids']:continue
            searched+=1
            if terms and coverage(doc['body'],terms)<1:continue
            hits=[l for l in document_lines(doc) if content_line(l['text']) and coverage(l['text'],terms)>=.5]
            if hits:records.append((doc,hits))
        if not records:continue
        latest=max(d.get('date','') for d,_ in records)
        selected=[x for x in records if not x[0].get('date') or x[0]['date']==latest]
        quotes=[];refs=[]
        for doc,hits in selected:
            # Keep whole lines: a second clause may negate the first one's completion.
            hits=sorted(hits,key=lambda l:(bool(re.search(r'完了|완료|끝|재개정|재작업',l['text'])),coverage(l['text'],terms)),reverse=True)[:4]
            sid='S'+str(len(sources)+1);sources.append(source_for(doc,p,sid,hits,scoped));refs.append(sid)
            quotes.extend((doc.get('date') or '날짜 미정')+' “'+l['text']+'”' for l in hits)
        explicit=any(completed_fact(clause) and coverage(clause,terms)>=.75 for _,hits in selected for l in hits for clause in clauses(l['text']))
        prefix='완료 표현이 있는 기록입니다. 대상·범위와 후속 내용을 함께 확인해 주세요.' if explicit and status_label=='완료' else status_label+' 사실을 확인하지 못했습니다. 관련 최신 회의 기록입니다.'
        points.append({'text':prefix+'\n'+'\n'.join(quotes),'sources':refs,'project_id':p['id'],'project_name':p['name'],'verification':'source_quote'})
    return {'kind':'documents','mode':'recorded_status','answerable':bool(points),'points':points,'sources':sources,
            'message':'' if points else '이 표현으로는 '+status_label+' 여부를 확인할 회의 기록을 찾지 못했습니다. 원문에 사용한 항목명으로 다시 검색해 주세요.',
            'notice':(plan.get('notice','')+' ' if plan.get('notice') else '')+'회의 기록 기준입니다. 예정·합의만으로 실제 완료를 판단하지 않습니다.',
            'searched_projects':len(projects),'searched_meetings':searched}
