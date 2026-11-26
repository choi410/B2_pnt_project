"""Find schedules explicitly attached to the requested event in meeting text."""
from datetime import date
import re

from work.v3.query_intent import strip_labels
from work.v3.question_scope import DATE
from work.v3.source_terms import resolve
from work.v3.topic_overview import without_date_scope
from work.v3.topic_search import source_for
from work.v17.evidence_text import content_line, normalized
from work.v17.retrieval import document_lines


EVENT = r'입고|반입'
DATE_FIELD = r'예정\s*일(?:자)?|일정|날짜|일자|시점|일(?!반)'
PARTICLE = r'(?:은|는|이|가|을|를)?'
QUESTION = re.compile(
    rf'(?P<subject>.{{0,80}}?)\s*(?P<event>{EVENT})\s*(?P<field>{DATE_FIELD})?\s*{PARTICLE}\s*'
    r'(?P<ask>언제(?:야|예요|인가요|인지|였어|였지|로\s*정했어)?|알려\s*(?:줘|주세요)|확인해\s*(?:줘|주세요)|뭐야)?'
)
INSPECTION_QUESTION = re.compile(
    rf'(?P<event>sat|fat)\s*(?:검수\s*)?(?P<field>{DATE_FIELD})?\s*{PARTICLE}\s*'
    r'(?P<ask>언제(?:야|예요|인가요|인지|였어|였지)?|알려\s*(?:줘|주세요)|뭐야)?', re.I
)
PENDING = re.compile(r'미정|미확정|보류|취소|철회|연기|재협의|추후\s*(?:협의|확정|결정)|정해지지\s*않')
OTHER_STAGE = re.compile(r'출하|출고|납품|납기|검수|설치|교육')
PARTS = re.compile(r'(?<=[.!?。])\s+|[,;]|\s+(?:및|그리고)\s+|\s*\|(?!\s*기한\s*[:：])\s*')
LEADING_DATE_EXCLUSION = re.compile(r'회의|논의|확인|협의|부터|까지|[.!?:：|]')
DISCUSSION_DATE = re.compile(r'\s*(?:에\s*)?(?:회의|미팅|협의|논의|재검토)')
TRIAL_SUBJECT = r'(?:현장\s+)?인수\s*시험'
TRIAL_QUESTION = re.compile(
    rf'(?P<subject>{TRIAL_SUBJECT})\s*{PARTICLE}\s*언제로\s*(?:정|합의|확정|결정)했(?:어(?:요)?|나요|지)'
)
TRIAL_STATUS = re.compile(
    r'(?:합의|확정|결정)(?:했|하였|됐|되었)(?:다|음|습니다)|'
    r'유지(?:한다|했다|함|하기로\s*했다)'
)
TRIAL_UNSETTLED = re.compile(r'보류|미정|철회|취소|재검토|검토\s*중|제안|요청|(?:하지|되지)\s*(?:않|못)')


def _has_term(text, term):
    if re.fullmatch(r'[a-z0-9]+', term):
        return bool(re.search(r'(?<![a-z0-9])' + re.escape(term) + r'(?![a-z0-9])', text, re.I))
    return term in normalized(text)


def _matches_topic(text, terms):
    return all(any(_has_term(text, value) for value in (term if isinstance(term, list) else [term])) for term in terms)


def _record_parts(text, event, terms):
    stage = re.compile(rf'{event}\s*(?:{DATE_FIELD}|예정|계획)?\s*{PARTICLE}\s*[:：]?\s*')
    for part in PARTS.split(text):
        for hit in stage.finditer(part):
            prefix = part[:hit.start()]
            # An earlier, different milestone cannot supply the equipment or date.
            topic = OTHER_STAGE.split(prefix)[-1]
            if not _matches_topic(topic, terms):
                continue
            tail = part[hit.end():].lstrip()
            stated_date = DATE.match(re.sub(r'^\|\s*기한\s*[:：]\s*', '', tail))
            if (stated_date and not DISCUSSION_DATE.match(stated_date.string[stated_date.end():])) or PENDING.match(tail):
                yield part.strip()
                break
            leading = DATE.match(topic.lstrip())
            if (leading and not LEADING_DATE_EXCLUSION.search(leading.string[leading.end():])
                    and re.match(r'^(?:예정|계획|완료|확정|합의|했|함|입니다|[.!?]|$)', tail)):
                yield part.strip()
                break


def _inspection_parts(text, event):
    # Schedule tables can render a row as "SAT 2027.05.12 오창공장" in a PDF.
    # A heading such as "6차 회의 (SAT)" or the filename is not a schedule row.
    stage = re.compile(rf'^(?:[-*•]\s*)?\b{event}\b\s*(?:검수\s*)?(?:{DATE_FIELD})?\s*{PARTICLE}\s*[:：]?\s*', re.I)
    for part in PARTS.split(text):
        hit = stage.match(part.strip())
        if not hit:
            continue
        tail = hit.string[hit.end():]
        if PENDING.match(tail):
            yield part.strip()
            continue
        day = DATE.match(tail)
        if not day or not day['month'] or DISCUSSION_DATE.match(tail[day.end():]):
            continue
        try:
            date(int(day['year'] or 2000), int(day['month']), int(day['day']))
        except ValueError:
            continue
        yield part.strip()


def request(question, projects, plan):
    query = without_date_scope(strip_labels(question, projects), plan).strip(' ?!.')
    query = re.sub(r'^프로젝트(?:에서|의)?\s+', '', query)
    inspection = INSPECTION_QUESTION.fullmatch(query)
    intent = inspection or QUESTION.fullmatch(query)
    if not intent or not (intent['ask'] or intent['field']):
        return None
    subject = '' if inspection else intent['subject'].strip()
    event = intent['event']
    if re.search(r'왜|이유|변경|비교|부터|까지|뒤|이후|기간|완료|실제|되면|출고|출하|반입|입고|각각|(?:와|과|하고|이랑)\s+', subject):
        return None
    return subject, event, bool(inspection)


def answer(question, projects, docs, plan):
    query = without_date_scope(strip_labels(question, projects), plan).strip(' ?!.')
    trial = TRIAL_QUESTION.fullmatch(query)
    if trial and len(projects)==1:
        return trial_schedule(projects[0],docs,plan,trial['subject'])
    schedule = request(question, projects, plan)
    if schedule is None:
        return None
    subject, event, inspection = schedule
    label = event.upper() if inspection else ' '.join(filter(None, (subject.upper() if re.fullmatch(r'[a-z]{2,8}', subject) else subject, event)))
    points, sources = [], []
    for project in projects:
        scoped = [doc for doc in docs if doc['project_id'] == project['id']]
        resolved = resolve(subject, scoped)
        if resolved['message']:
            return {'kind':'clarification','answerable':False,'points':[],'sources':[],'message':resolved['message']}
        matches = []
        for doc in scoped:
            hits = [(line, parts) for line in document_lines(doc) if content_line(line['text'])
                    and (parts := list(_inspection_parts(line['text'], event) if inspection
                                       else _record_parts(line['text'], event, resolved['terms'])))]
            if hits:
                matches.append((doc, hits))
        if not matches:
            continue
        latest = max(doc.get('date') or '' for doc, _ in matches)
        for doc, hits in matches:
            if plan.get('mode', 'current') in ('current', 'as_of') and (doc.get('date') or '') != latest:
                continue
            sid = 'S' + str(len(sources)+1)
            lines = [line for line, _ in hits]
            source = source_for(doc, project, sid, lines, plan)
            source['exact_highlights'] = source['line_ids']
            sources.append(source)
            quotes = '\n'.join(f'“{part}”' for _, parts in hits for part in parts)
            points.append({'text':f'회의록에 적힌 {label} 일정이에요.\n{quotes}', 'sources':[sid],
                           'project_id':project['id'], 'project_name':project['name'], 'verification':'source_quote'})
    return {'kind':'documents','mode':'inspection_schedule' if inspection else 'inbound_schedule','answerable':bool(points),
            'answer_mode':'source_quote' if points else 'no_evidence','points':points,'sources':sources,
            'message':'' if points else f'조회한 회의록에서 {label} 일정을 확인하지 못했어요.',
            'searched_projects':len(projects),'searched_meetings':len(docs),'notice':plan.get('notice','')}


def trial_schedule(project,docs,plan,subject):
    """Find the last recorded outcome for the named acceptance test."""
    rows=[]
    for doc in docs:
        if not doc.get('date'):
            continue
        for line in document_lines(doc):
            if not content_line(line['text']):
                continue
            for clause in re.split(r'(?<=[.!?])\s+',line['text']):
                hit=re.match(rf'^(?:[-•]\s*)?(?P<subject>{TRIAL_SUBJECT})(?:[은는이가을를]\s+|\s*[:：]\s*)',clause)
                if not hit:
                    continue
                exact=normalized(hit['subject'])==normalized(subject)
                tail=clause[hit.end():]
                dates=list(DATE.finditer(tail))
                valid=len(dates)==1 and not TRIAL_UNSETTLED.search(tail) and TRIAL_STATUS.search(tail)
                if valid:
                    day=dates[0].group('year','month','day')
                    valid=all(day) and not DISCUSSION_DATE.match(tail[dates[0].end():])
                if exact or subject.startswith('현장') and re.match(r'\s*기존\s+',tail):
                    rows.append((doc,line,clause,exact,day if valid else None))
    exact_days={(doc['date'],value) for doc,_,_,exact,value in rows if exact and value}
    relevant=[row for row in rows if row[3] or
              any(day<row[0]['date'] and value==row[4] for day,value in exact_days)]
    latest=max((row[0]['date'] for row in relevant),default='')
    selected=[(doc,line,quote) for doc,line,quote,_,value in relevant if doc['date']==latest and value]
    if not selected or any(row[0]['date']==latest and not row[4] for row in relevant):
        return None
    points=[]
    sources=[]
    for doc,line,quote in selected:
        sid=f'S{len(sources)+1}'
        source=source_for(doc,project,sid,[line],plan)
        source['exact_highlights']=[line['id']]
        sources.append(source)
        points.append({'text':quote,'sources':[sid],'project_id':project['id'],
                       'project_name':project['name'],'verification':'source_quote'})
    return {'kind':'documents','mode':'recorded_schedule','schedule_subject':subject,
            'answerable':True,'points':points,'sources':sources,'message':'회의록에 기록된 인수 시험 일정이에요.',
            'notice':plan.get('notice','')}
