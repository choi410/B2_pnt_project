"""Find dates explicitly attached to the requested inbound event in meeting text."""
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
PENDING = re.compile(r'미정|미확정|보류|취소|철회|연기|재협의|추후\s*(?:협의|확정|결정)|정해지지\s*않')
OTHER_STAGE = re.compile(r'출하|출고|납품|납기|검수|설치|교육')
PARTS = re.compile(r'(?<=[.!?。])\s+|[,;]|\s+(?:및|그리고)\s+|\s*\|(?!\s*기한\s*[:：])\s*')
LEADING_DATE_EXCLUSION = re.compile(r'회의|논의|확인|협의|부터|까지|[.!?:：|]')
DISCUSSION_DATE = re.compile(r'\s*(?:에\s*)?(?:회의|미팅|협의|논의|재검토)')


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


def answer(question, projects, docs, plan):
    query = without_date_scope(strip_labels(question, projects), plan).strip(' ?!.')
    intent = QUESTION.fullmatch(query)
    if not intent or not (intent['ask'] or intent['field']):
        return None
    subject, event = intent['subject'].strip(), intent['event']
    if re.search(r'왜|이유|변경|비교|부터|까지|뒤|이후|기간|완료|실제|되면|출고|출하|반입|입고|각각|(?:와|과|하고|이랑)\s+', subject):
        return None
    label = ' '.join(filter(None, (subject.upper() if re.fullmatch(r'[a-z]{2,8}', subject) else subject, event)))
    points, sources = [], []
    for project in projects:
        scoped = [doc for doc in docs if doc['project_id'] == project['id']]
        resolved = resolve(subject, scoped)
        if resolved['message']:
            return {'kind':'clarification','answerable':False,'points':[],'sources':[],'message':resolved['message']}
        matches = []
        for doc in scoped:
            hits = [(line, parts) for line in document_lines(doc) if content_line(line['text'])
                    and (parts := list(_record_parts(line['text'], event, resolved['terms'])))]
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
    return {'kind':'documents','mode':'inbound_schedule','answerable':bool(points),
            'answer_mode':'source_quote' if points else 'no_evidence','points':points,'sources':sources,
            'message':'' if points else f'조회한 회의록에서 {label} 일정을 확인하지 못했어요.',
            'searched_projects':len(projects),'searched_meetings':len(docs),'notice':plan.get('notice','')}
