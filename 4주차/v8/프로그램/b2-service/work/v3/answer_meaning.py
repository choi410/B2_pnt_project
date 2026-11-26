"""Conservative status-claim checks, in addition to citation/number validation.

This is a bounded contradiction guard, not a general entailment guarantee.
When a decision claim cannot be supported, return the actual cited wording.
"""
import re
from datetime import date
from work.v17.evidence_text import topic_terms, coverage, content_line, normalized

DECISION = r'(?:확정|합의|승인|결정)(?:되었|됐|된|됨|했다|했|하였|한다|함|입니다|되었습니다|되었습니다)|하기로\s*(?:했|합의|결정|정했)'
NEGATIVE = r'(?:확정|합의|승인|결정).{0,8}(?:않|못|아니|없)|미확정|미승인|미정|검토\s*중|보류|철회|취소'
SUBJECTS = (r'속도', r'납품|납기|출하', r'커버|개폐', r'코팅\s*폭', r'가압력', r'온도', r'재질')
DONE = r'완료(?:되었|됐|했|하였|됨|된|했습니다|되었습니다)|끝(?:났|난)|마쳤|마무리(?:했|되었|됐)|반영(?:했|됐|되었)'
NOT_DONE = r'않|못|아니|없|예정|계획|목표|여부|되면|하면|조건|경우|까지.*완료|진행\s*중|재개정|재작업|추가\s*(?:수정|작업)|철회|취소'
COMPLETION_ACTIONS = ('교체', '출고', '출하', '납품', '인도', '설치', '검수', '검사',
                      '수령', '접수', '제출', '반입', '발송', '교정', '개조', '보수', '입고')
_ACTION = '|'.join(COMPLETION_ACTIONS)
_PAST_QUESTION = r'(?:했|됐|되었|하였)(?:어(?:요)?|지|나요|습니까|는지)'
_ACTION_QUESTION = re.compile(
    rf'(?<![가-힣])({_ACTION})(?:[은는이가을를도]?\s*(?:이미|벌써|실제로)?\s*)'
    rf'{_PAST_QUESTION}[?!.\s]*$')
_ACTION_ALSO = re.compile(rf'(?<![가-힣])({_ACTION})도(?=$|[^가-힣])')
_STATUS_MODIFIER = re.compile(r'(?<![가-힣])(?:실제로?|이미|벌써)(?=$|[^가-힣])')
_COMPLETION_END = re.compile(
    r'(?:^|\s+)(?:끝난\s*(?:거야|건가요|건지|거예요)|(?:끝냈|(?:실행|실시|시행|완료)(?:했|됐|되었))'
    r'(?:어(?:요)?|나|나요|는지|습니까)|완료된\s+상태(?:야|인가요|예요))'
    r'(?:\s*(?:확인해|알려)\s*(?:줘|주세요))?[?!.\s]*$')
_RECEIPT = r'(?:회신|답신)'
_RECEIPT_LEAD = rf'{_RECEIPT}(?:은|는|이|가|을|를)?\s*(?:(?:이미|아직|벌써|실제로)\s+)?'
_RECEIPT_QUESTION = re.compile(
    rf'(?P<subject>.+?)\s+{_RECEIPT_LEAD}'
    r'(?:왔|받았|도착했|수신했|수신됐|수신되었)(?:어(?:요)?|나요|지|습니까|는지)'
    r'(?:\s*확인해\s*(?:줘|주세요))?[?!.\s]*$')
_DOCUMENT_RECEIPT_QUESTION = re.compile(
    r'(?P<subject>.+?(?:서명본|승인서|문서|도면|성적서|회신본|메일))'
    r'(?:은|는|이|가|을|를)?\s+(?:(?:아직|이미|벌써)\s+)?'
    r'(?:도착했|왔|받았|수신했|수신됐|수신되었)(?:어(?:요)?|나요|지|습니까|는지)[?!.\s]*$')
_RECEIPT_DONE = re.compile(
    rf'{_RECEIPT_LEAD}(?:(?:[가-힣]+(?:에서|로부터))\s+)?'
    r'(?:왔|(?:전달\s*)?받았|도착했|수신했|수신됐|수신되었)(?:다|음|습니다)(?![가-힣])')
_RECEIPT_MISSING = re.compile(
    rf'{_RECEIPT_LEAD}(?:없(?:다|음)|(?:받지|수신하지)\s*(?:못했|않았)(?:다|음|습니다)|미수신)(?![가-힣])')
_DOCUMENT_MISSING = re.compile(
    r'(?:(?:회신|수신)\s*)?받지\s*(?:못했|않았)(?:다|음|습니다)|미수신|도착하지\s*(?:않았|못했)(?:다|음)')
_DOCUMENT_RECEIVED = re.compile(r'(?:받았|수신됐|수신되었|도착했)(?:다|음|습니다)(?![가-힣])')
_STATUS_UNKNOWN = re.compile(
    r'(?:실제\s*)?(?:실행|실시|시행|완료)\s*여부.{0,40}(?:다루지|확인하지|확인할\s*수)\s*(?:않|못|없)')
_EVENT_DONE = (
    r'(?:(?:했|하였|됐|되었)고(?=\s|확인|보고|기록|공유)|'
    r'(?:(?:했|하였|됐|되었)(?:다|음|습니다|으며)|함)(?=$|[^가-힣]))'
)
_EVENT_OTHER = (
    r'(?:(?:완료|시작)\s*)?(?:하지|되지)\s*(?:않|못)|(?:할|될)\s*(?:예정|계획)|하기로\s*(?:했|합의|결정)|'
    r'(?:(?:진행|시행)(?:할|하기로|하지|한다|중)\s*|일정\s*)?'
    r'(?:예정|계획|보류|철회|취소|연기|미정)|진행\s*(?:중|한다)|미완료'
)


def completion_question(question):
    if re.search(r'완료|끝났|끝난|마쳤|마무리|반영.*(?:됐|했)|개정본.*나왔|제작.*들어갔',question):
        return True
    if re.search(r'누가|언제|왜|어떻게|어디|몇\s*(?:대|기|건)|(?:예정|계획|일정)(?:은|는|이|을|를)?\s',question):
        return False
    return bool(_ACTION_QUESTION.search(question) or _COMPLETION_END.search(question) or receipt_subject(question))


def receipt_subject(question):
    match = _RECEIPT_QUESTION.fullmatch(question.strip()) or _DOCUMENT_RECEIPT_QUESTION.fullmatch(question.strip())
    return match['subject'] if match else ''


def completion_topic(question):
    """Keep the work named by the user and remove the status question ending."""
    question = _STATUS_MODIFIER.sub(' ', question)
    question = _COMPLETION_END.sub('', question)
    question = _ACTION_QUESTION.sub(r'\1', question)
    question = _ACTION_ALSO.sub(r'\1', question)
    return receipt_subject(question) or re.sub(rf'(?<![가-힣]){_PAST_QUESTION}[?!.\s]*$', '', question)


def event_patterns(action):
    # A state must describe this action directly. For example, a photo sent
    # after shipment and the shipment itself are different events.
    start = rf'(?<![가-힣]){action}(?:\s+작업)?'
    topic = start + r'[은는이가을를]\s+'
    lead = rf'(?:{topic}|{start}\s*)'
    lead += (r'(?:(?:20\d{2}[-./년]\s*)?\d{1,2}[-./월]\s*\d{1,2}일?(?:에|로|까지)?\s+'
             r'|(?:이번|다음)\s*(?:주|달)(?:에|로|까지)?\s+)?')
    lead += r'(?:(?:아직|이미|최종|현재|실제로)\s+)?'
    completion = rf'(?:완료\s*)?{_EVENT_DONE}'
    condition = topic + r'[^.!?\n]{1,60}?\s+(?:이후|후|뒤)(?:에)?\s+'
    assignment = (
        rf'{start}(?:[은는이가을를])?\s+(?:담당자[^.!?\n]{{0,30}}미정|'
        r'[^!?\n]{0,60}?까지\s+(?:진행|실시|시행|처리)할\s+예정)'
    )
    state = re.compile(
        rf'{lead}(?:{completion}|{_EVENT_OTHER}|(?:일부\s+)?완료(?:\s|$|[.!?]))|'
        rf'{condition}(?:{_EVENT_OTHER})|{assignment}')
    done = re.compile(lead + rf'(?:{completion}|완료(?:\s*$|[.!?]))')
    return state, done


def completed_fact(text):
    return bool(re.search(DONE,text) and not re.search(NOT_DONE,text))


def clauses(text):
    return [s.strip() for s in re.split(r'(?<!\d)[.!?]\s*|\n',text) if s.strip()]


def numbers(text):
    return set(re.findall(r'\d+(?:\.\d+)?',text))


def event_dates(text):
    """Extract dates stated as completed event dates, excluding meeting attribution."""
    action=re.compile(r'(접수|수령|제출|출고|출하|납품|인도|설치|등록|검수)(?:을|를)?\s*'
                      r'(?:완료(?:했|하였|함|됐|되었|(?=\s*[.!?,]|\s*$))|했|하였|함|받았|됐|되었)')
    dates=re.compile(
        r'(?<!\d)(?:(20\d{2})\s*(?:년|[./-])\s*)?(\d{1,2})\s*(?:월|[./-])\s*(\d{1,2})\s*일?(?!\d)')
    result=[]
    for sentence in re.split(r'(?<=[.!?])\s+|\n',text):
        matches=list(dates.finditer(sentence))
        for index,match in enumerate(matches):
            tail=sentence[match.end():matches[index+1].start() if index+1<len(matches) else len(sentence)]
            phrase=action.search(tail)
            if not phrase:
                continue
            meeting=re.match(r'^\s*(?:에\s*)?(?:열린\s*)?회의(?:록)?\s*(?:에서는|에서|에는|에)',tail)
            reported=meeting and re.search(
                r'(?:다고|다는|음을|것을|완료\s*(?:여부|사실)).{0,20}(?:확인|보고|공유|기록|언급)',tail)
            linked=not reported and (meeting or not tail[:phrase.start()].strip() or re.match(r'^\s*에(?:\s|[가-힣]|$)',tail))
            if linked and not re.search(r'예정|계획|않|못|취소',tail[:phrase.end()+6]):
                result.append((phrase[1],int(match[1]) if match[1] else None,int(match[2]),int(match[3])))
    return result


def unsupported_event_dates(text, sources, terms=()):
    # Only the source body can support an event date, for the same action.
    supported={item for source in sources for part in re.split(r'(?<=[.!?])\s+|\n',source['text'])
               if not terms or coverage(part,terms)>=.75 for item in event_dates(part)}
    return {action for action,year,month,day in event_dates(text)
            if not any(action==a and (year is None or year==y) and (month,day)==(m,d)
                       for a,y,m,d in supported)}


def without_scope_prefix(text,sources):
    """Separate a verified lookup cutoff from dates/numbers asserted as facts.

    Only an explicit leading 'DATE 기준' matching every cited source's
    server-owned as-of scope qualifies. Never whitelist all question numbers.
    """
    m=re.match(r'^\s*(?:(20\d{2})\s*(?:년|[-./])\s*)?(\d{1,2})\s*(?:월|[-./])\s*(\d{1,2})\s*일?\s*기준(?:으로|에는)?(?:\s+|\s*[:：,]\s*)',text)
    if not m or not sources:return text
    scopes=[s.get('query_scope',{}) for s in sources]
    ends={s.get('end') for s in scopes}
    if any(s.get('mode')!='as_of' or s.get('start') for s in scopes) or len(ends)!=1:return text
    try:
        cutoff=date.fromisoformat(next(iter(ends)))
        stated=date(int(m[1]) if m[1] else cutoff.year,int(m[2]),int(m[3]))
        if stated!=cutoff or any(date.fromisoformat(s.get('date',''))>cutoff for s in sources):return text
    except (TypeError,ValueError):return text
    return text[m.end():]


def dated_claim(claim,sources):
    """A leading meeting date is context, not a specification value.

    Bind it to that meeting's evidence before removing it; a later approval
    may never validate a claim that approval already existed at an earlier date.
    """
    scoped=without_scope_prefix(claim,sources)
    if scoped!=claim:return scoped,sources
    m=re.match(r'^\s*(?:(20\d{2})\s*(?:년|[-./])\s*)?(\d{1,2})\s*(?:월|[-./])\s*(\d{1,2})\s*일?(?!\d)',claim)
    if not m:return claim,None
    # A yearless dotted number is also a decimal specification (3.0 kPa,
    # 0.6초). Only interpret it as a date when the notation or following
    # context explicitly identifies a date; source dates alone cannot decide.
    prefix=claim[:m.end()]
    if not m[1] and '.' in prefix and not re.search(r'월|일',prefix):
        if not re.match(r'^\s*(?:회의|기준|당시|에는|에서|에\b|부터|까지|[:：])',claim[m.end():]):
            return claim,None
    dates={s.get('date','') for s in sources if re.fullmatch(r'20\d{2}-\d{2}-\d{2}',s.get('date',''))
           and (not m[1] or int(s['date'][:4])==int(m[1])) and int(s['date'][5:7])==int(m[2]) and int(s['date'][8:10])==int(m[3])}
    if len(dates)!=1:return claim,[]
    rest=re.sub(r'^\s*(?:회의(?:에서|에서는|에는)?|에는|에|기준)?\s*[:：·-]?\s*','',claim[m.end():])
    return rest,[s for s in sources if s.get('date') in dates]


def leading_meeting_attribution(sentence):
    """Move an explicit trailing citation into the existing dated-claim form.

    This changes validation input only, not the displayed answer. The date
    still has to identify one cited meeting, which must support the whole
    assertion. Delivery dates and arbitrary date mentions are not citations.
    """
    pattern=(r'(?P<day>(?<!\d)(?:20\d{2}\s*(?:년|[-./])\s*)?'
             r'\d{1,2}\s*(?:월|[-./])\s*\d{1,2}\s*일?(?!\d))'
             r'\s*(?:의\s*)?회의(?:\s*기록|록)?(?:에서는|에서|에\s*따라)')
    matches=list(re.finditer(pattern,sentence))
    if len(matches)!=1 or not sentence[:matches[0].start()].strip():return sentence
    citation=matches[0]
    fact=re.sub(r'[,;]?\s*(?:이는|이것은|해당\s*(?:내용|사실)은)\s*$','',sentence[:citation.start()]).strip()
    if not fact:return sentence
    tail=re.sub(r'(?:내용|사실)(?:입니다|이다|이었습니다|이었다)(?=\s|$)','',sentence[citation.end():]).strip()
    return citation['day']+' 회의에서 '+fact+' '+tail


def unsupported_decision(text, sources):
    from work.v3.query_intent import strip_labels
    scoped=sources
    claims=[part for clause in clauses(text) for part in re.split(r'[,;]|(?<=[었였했됐])지만|(?<=었)으나|그러나|하지만|이후',leading_meeting_attribution(clause))]
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


def unsupported_document_review(text, sources):
    states = re.findall(r'작성자\s*확인\s*상태|문서\s*검토\s*완료|보완\s*요청\s*상태', text)
    return any(not any(normalized(state) in normalized(source['text']) for source in sources) for state in states)


def validate_meaning(points,sources,question=''):
    lookup={s['id']:s for s in sources};result=[]
    shared_terms=next((s['query_scope']['search_terms'] for s in sources if s.get('query_scope',{}).get('search_terms') is not None),None)
    scope=next((s.get('query_scope',{}) for s in sources),{})
    history=scope.get('operation')=='history' or scope.get('mode')=='history' or bool(re.search(r'이력|과정|경위',question))
    decision=scope.get('operation')=='decision' or (
        scope.get('mode','current') in ('current','as_of') and bool(re.search(r'얼마|언제|몇\s*(?:도|개|mm)',question,re.I))
    )
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
            # qualifications. In a timeline, the recorded decision is more
            # informative than a shorter note that only reopens the discussion.
            options.sort(key=lambda line:(coverage(line,terms),
                decision and bool(re.search(DECISION+'|'+NEGATIVE+r'|유지(?:한다|했다|하기로|함)',line)),
                history and any(coverage(part,terms)>=.5 and not re.search(NEGATIVE,part)
                                and any(not match[0].endswith('된') for match in re.finditer(DECISION,part))
                                for part in clauses(line)),
                bool(not history and re.search(r'않|못|아니|미정|미지정|정하지',line)),
                -sum(bool(re.search(pattern,line)) for pattern in SUBJECTS),
                bool(re.search(r'합의|확정|보류|철회|유지|완료|않|아니',line)),-len(line)),reverse=True)
            if options:chosen.append((s,options[0]))
        chosen.sort(key=lambda x:x[0].get('date',''))
        if len(chosen)>4:chosen=chosen[:1]+chosen[-3:]
        return chosen
    def quote_point(point,chosen):
        text='관련 회의 기록을 날짜순으로 표시합니다.\n'+'\n'.join((s.get('date','')+' ' if s.get('date') else '')+'“'+line+'”' for s,line in chosen)
        return {**point,'text':text,'sources':list(dict.fromkeys(s['id'] for s,_ in chosen)),'verification':'source_quote'}
    role_records=[]
    if scope.get('operation')=='responsibility' and scope.get('mode','current') in ('current','as_of') and shared_terms:
        role_records=[(s,line.strip()) for s in sources for line in s['text'].splitlines()
            if content_line(line,question) and coverage(line,shared_terms)==1
            and re.search(r'담당|기한|까지|제출|작성|공유|준비',line)]
        latest=max((s.get('date','') for s,_ in role_records),default='')
        role_records=[(s,line) for s,line in role_records if not s.get('date') or s['date']==latest]
    if not points and role_records:
        source=role_records[0][0]
        return [quote_point({'project_id':source.get('project_id'),'project_name':source.get('project_name')},role_records[:4])]
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
        latest_cited=max((s.get('date','') for s in cited),default='')
        newer_role_record=bool(role_records and any(s.get('date','')>latest_cited for s,_ in role_records))
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
        unsupported_dates=unsupported_event_dates(point['text'],cited,terms)
        if unsupported_dates:
            matched=[(s,part) for s in cited for part in clauses(s['text'])
                     if content_line(part,question) and (not terms or coverage(part,terms)>=.75)
                     and any(action in part for action in unsupported_dates)]
            if matched:
                revised=quote_point(point,matched[:4])
                revised['text']='실제 처리일은 회의록에서 확인되지 않아요.\n' + '\n'.join(
                    f'“{part}”' for _,part in matched[:4])
                result.append(revised)
            continue
        unreadable=len(point['text'])>340 or point['text'].count('해당')>=3
        if not unreadable and not later_qualification and not newer_role_record and not unsupported_decision(point['text'],cited) and not unsupported_unsettled(point['text'],cited) and not unsupported_document_review(point['text'],cited) and not (completion_claim and not completion_supported):
            result.append(point);continue
        # Do not rephrase a requested value as approved. Keep a usable answer
        # with exact source quotations, clearly identified as such.
        # A fallback is evidence too. Numbers alone never establish its topic.
        pool=[s for s in sources if not s.get('project_id') or s.get('project_id')==point.get('project_id')]
        chosen=source_quotes(pool,terms)
        if role_records:chosen=role_records[:4]
        if not chosen:continue
        revised=quote_point(point,chosen)
        revised['text']=('변경 경과를 확인할 수 있도록 ' if history else '관련 내용을 확인할 수 있도록 ')+'원문을 표시합니다.\n'+revised['text'].split('\n',1)[1]
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
    query=strip_labels(question,projects)
    receipt=bool(receipt_subject(query))
    document_receipt = bool(_DOCUMENT_RECEIPT_QUESTION.fullmatch(query))
    topic=completion_topic(query)
    default_terms=topic_terms(topic)
    if not default_terms:return None
    last_term=default_terms[-1]
    action='납품' if last_term=='납기' else last_term
    state_pattern,done_pattern=event_patterns(action) if action in COMPLETION_ACTIONS else (None,None)
    width=re.search(r'폭\s+(\d+(?:\.\d+)?)\s*mm',question,re.I)
    width_value=re.compile(r'(?<![\d.])'+re.escape(width[1])+r'\s*mm(?![a-z])',re.I) if width else None
    status_label='회신 수신' if receipt else '착수' if re.search(r'제작.*들어갔',question) else '완료'
    points=[];sources=[];searched=0
    for p in projects:
        scoped=plan.get('content_plans',{}).get(p['id'],plan)
        terms=scoped.get('search_terms')
        if terms is None:terms=default_terms
        sender_requested=False
        if document_receipt:
            # Match the document description next to the receipt status.
            # Sender words may appear in a separate clause of the same line.
            sender_requested=any(term in ('고객','고객사') for term in terms)
            terms=[t for t in terms if t not in ('고객','고객사')]
            if re.search(r'(?<![가-힣])승인\s+',topic):
                terms=[*terms,'승인']
        missing_receipt=_DOCUMENT_MISSING if document_receipt else _RECEIPT_MISSING
        received_receipt=_DOCUMENT_RECEIVED if document_receipt else _RECEIPT_DONE
        def matches(text):
            if receipt:
                return (coverage(text,terms)==1
                        and bool(missing_receipt.search(text) or (received_receipt.search(text) and not re.search(NOT_DONE,text))))
            if width_value:
                return coverage(text,terms)==1 and bool(width_value.search(text))
            if state_pattern:
                return coverage(text,terms)==1 and bool(state_pattern.search(text))
            if last_term=='검증':
                return bool(coverage(text,terms)==1 and
                            (_STATUS_UNKNOWN.search(text) or re.search(DONE+'|시행했|실시했',text)))
            return coverage(text,terms)>=.5
        def status_clauses(text):
            if document_receipt:
                text=re.sub(r'(?:지만|으나|는데)\s*,?\s+', '\n', text)
            return clauses(text)
        records=[]
        for m in w.all_records(c,'meeting'):
            if m['project_id']!=p['id']:continue
            doc=registered_document(m)
            if not doc or not in_scope(doc,plan) or plan.get('meeting_ids') and m['id'] not in plan['meeting_ids']:continue
            searched+=1
            if terms and coverage(doc['body'],terms)<1:continue
            hits=[l for l in document_lines(doc) if content_line(l['text'])
                  and (not sender_requested or '고객' in l['text'])
                  and (any(matches(part) for part in status_clauses(l['text'])) if receipt or state_pattern else matches(l['text']))]
            if hits:records.append((doc,hits))
        if not records:continue
        latest=max(d.get('date','') for d,_ in records)
        selected=[x for x in records if not x[0].get('date') or x[0]['date']==latest]
        quotes=[];refs=[]
        for doc,hits in selected:
            # Keep whole lines: a second clause may negate the first one's completion.
            hits=sorted(hits,key=lambda l:(bool(re.search(r'完了|완료|끝|재개정|재작업',l['text'])),coverage(l['text'],terms)),reverse=True)[:4]
            sid='S'+str(len(sources)+1)
            source=source_for(doc,p,sid,hits,scoped)
            if receipt or state_pattern or last_term=='검증':source['exact_highlights']=source['line_ids']
            sources.append(source);refs.append(sid)
            quotes.extend((doc.get('date') or '날짜 미정')+' “'+l['text']+'”' for l in hits)
        matching_clauses=[clause for _,hits in selected for l in hits for clause in status_clauses(l['text'])
                          if matches(clause) and coverage(clause,terms)>=.75]
        explicit=any(
            bool(done_pattern.search(clause)) and not re.search(NOT_DONE,clause) if done_pattern
            else completed_fact(clause) for clause in matching_clauses)
        prefix='완료 표현이 있는 기록입니다. 대상·범위와 후속 내용을 함께 확인해 주세요.' if explicit and status_label=='완료' else status_label+' 사실을 확인하지 못했습니다. 관련 최신 회의 기록입니다.'
        if receipt:
            received=any(received_receipt.search(clause) and not re.search(NOT_DONE,clause) for clause in matching_clauses)
            missing=any(missing_receipt.search(clause) for clause in matching_clauses)
            prefix=('조회한 기록에서 회신 수신 여부가 다르게 나와요.' if received and missing
                    else '회신을 받았다는 기록입니다.' if received else '아직 회신을 받지 못했다는 기록입니다.')
        points.append({'text':prefix+'\n'+'\n'.join(quotes),'sources':refs,'project_id':p['id'],'project_name':p['name'],'verification':'source_quote'})
    return {'kind':'documents','mode':'recorded_status','answerable':bool(points),'points':points,'sources':sources,
            'completion_subject':' '.join(default_terms) if state_pattern and len(points)==1 and len(projects)==1 else '',
            'message':'' if points else '이 표현으로는 '+status_label+' 여부를 확인할 회의 기록을 찾지 못했습니다. 원문에 사용한 항목명으로 다시 검색해 주세요.',
            'notice':(plan.get('notice','')+' ' if plan.get('notice') else '')+'회의 기록 기준입니다. 예정·합의만으로 실제 완료를 판단하지 않습니다.',
            'searched_projects':len(projects),'searched_meetings':searched}
