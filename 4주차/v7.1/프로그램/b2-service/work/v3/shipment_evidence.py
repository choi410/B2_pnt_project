"""Find dated shipment mentions in registered minutes without totaling them."""
from calendar import monthrange
from datetime import date
import re

from work.v17 import questions
from work.v17.retrieval import document_lines
from work.v3 import question_policy as policy
from work.v3.query_intent import relative_period
from work.v3.topic_search import source_for


EVENT_DATE = re.compile(
    r'(?<!\d)(20\d{2})(?:\s*년(?:\s*(\d{1,2})\s*월(?:\s*(\d{1,2})\s*일)?)?'
    r'|[-./](\d{1,2})[-./](\d{1,2})(?!\d))')
COMPLETED = re.compile(
    r'(?:출고|출하|납품|선적|인도)(?:를)?\s*(?:완료(?:했|하였|됐|되었|함)?|했|하였|함|됐|되었)'
    r'|(?:발송|인계)(?:을|를)?\s*(?:했|하였|함|완료)|보냈|보내\s*줬')
UNVERIFIED = re.compile(r'예정|계획|목표|검토|추정|가정|취소|미완료|미출고|미납품|못\s*했|않았|않음|아니|여부|대비|[?？]')


def date_bounds(match):
    year, month, day = int(match[1]), match[2] or match[4], match[3] or match[5]
    if not month:
        return date(year, 1, 1).isoformat(), date(year, 12, 31).isoformat()
    number = int(month)
    last = monthrange(year, number)[1]
    return (date(year, number, int(day) if day else 1).isoformat(),
            date(year, number, int(day) if day else last).isoformat())


def period_for(question):
    explicit = list(EVENT_DATE.finditer(question))
    relative = relative_period(question)
    # Multiple date expressions need a clearer request before searching.
    if len(explicit) > 1 or explicit and relative:
        return None
    if not explicit:
        return relative
    try:
        start, end = date_bounds(explicit[0])
    except ValueError:
        return None
    return {'start':start, 'end':end}


def period_followup(question):
    from work.v3.dialogue_plan import DATE_TOKEN
    return bool(re.fullmatch(
        rf'\s*(?:(?:그럼|그러면|그렇다면|이번에는)\s*)?(?:{DATE_TOKEN})(?:에는|에|은|는|도)?'
        r'\s*(?:몇\s*(?:대|기)(?:였어|야|였나요|예요)?|물량(?:은|도)?)?'
        r'\s*(?:알려\s*줘)?[?!.\s]*',question))


def in_period(statement, period):
    dates = list(EVENT_DATE.finditer(statement))
    if len(dates) != 1:
        return False
    event = COMPLETED.search(statement, dates[0].end())
    if not event or UNVERIFIED.search(statement):
        return False
    date_tail = statement[dates[0].end():]
    if re.match(r'\s*(?:모델|기종|사양|버전|연식)',date_tail):
        return False
    try:
        start, end = date_bounds(dates[0])
    except ValueError:
        return False
    return period['start'] <= start <= end <= period['end']


def answer(w, c, actor, question, equipment, project_id=None, prior=None):
    from work.v3.conversation_followups import available_projects

    available = available_projects(w, c, actor)
    named = policy.name_matches(available, question)
    prior = prior or {}
    continuing = bool(prior and period_followup(question))
    if continuing:
        equipment = prior.get('equipment')
    remembered_id = prior.get('selected_project') if continuing else None
    selected_id = project_id or (None if named or policy.is_broad(question) else remembered_id)
    selected = [w.project(c, selected_id, actor)] if selected_id else named or available
    if not selected_id and len(named) == 1:
        selected_id = named[0]['id']
    projects = {p['id']:p for p in selected}
    if selected_id:
        scope = selected[0]['name']
    else:
        scope = '지정 프로젝트' if named else '전체 프로젝트'
    period = period_for(question)
    origin = prior.get('origin_question') if continuing else question
    context = {'query':question, 'project_ids':list(projects), 'label':scope,
               'shipment':{'equipment':equipment,'selected_project':selected_id,'origin_question':origin or question}}
    result = policy.shipment_total_unavailable()
    if not period:
        result['message'] += ' 참고할 회의록을 찾으려면 출고 시기를 알려 주세요. 예를 들어 작년이나 2025년처럼 물어볼 수 있어요.'
        return context, result
    if equipment is None:
        result['message'] += ' 참고할 근거를 찾으려면 설비 이름이나 종류를 알려 주세요.'
        return context, result
    context['shipment']['period'] = period
    result['notice'] = (
        f"출고 언급 기간 {period['start']}~{period['end']} · 회의일 전체 · "
        f"열람 범위 {len(projects)}개 프로젝트"
    )
    docs = questions.corpus(w, c, projects)
    points, sources, seen = [], [], set()
    key = policy.clean(equipment)
    for doc in sorted(docs,key=lambda d:d['date'] or '',reverse=True):
        project = projects[doc['project_id']]
        statements = []
        for line in document_lines(doc):
            for statement in re.split(r'\.\s+|\s*[;；。]\s*',line['text']):
                if not in_period(statement, period):
                    continue
                normalized = policy.clean(statement)
                if key and key not in normalized:
                    continue
                fingerprint = (project['id'], normalized)
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                if len(sources) < 6:
                    statements.append((line, statement.strip()))
            if len(statements) >= 6:
                break
        if not statements:
            continue
        sid = 'S'+str(len(sources)+1)
        lines = list({line['id']:line for line, _ in statements}.values())
        source = source_for(doc, project, sid, lines)
        source['exact_highlights'] = source['line_ids']
        sources.append(source)
        for _, quote in statements[:6]:
            points.append({'text':quote,'project_id':project['id'],'project_name':project['name'],'sources':[sid]})
    result['points'], result['sources'] = points, sources
    result['notice'] += f' · 등록 회의록 {len(docs)}건 확인'
    result['notice'] += ' · 원문에 출고 시기와 완료가 함께 적힌 문장만 표시합니다. 반복 기록은 합산하지 않습니다.'
    if points:
        result['message'] = (
            '회의록에서 해당 기간의 출고 완료를 언급한 문장을 찾았어요. '
            '전체 출고 대수는 설비별 실적 자료가 있어야 확인할 수 있어요.'
        )
    else:
        result['message'] += ' 확인한 회의록에서 해당 기간의 출고 완료를 뒷받침하는 문장을 찾지 못했어요.'
    return context, result
