"""Conservative question scopes. Dates describe meeting records, not legal effect."""
import calendar
import re
from datetime import date, timedelta
from work.v3.query_intent import relative_period, metadata_plan


DATE = re.compile(
    r'(?<!\d)(?:(?P<year>20\d{2})\s*(?:년|[-./])\s*)?'
    r'(?P<month>\d{1,2})\s*(?:월|[-./])\s*(?P<day>\d{1,2})\s*일?(?!\d)'
    r'|(?<!\d)(?P<day_only>\d{1,2})\s*일(?!\d)'
)
DATE_CONTEXT = re.compile(r'^\s*(?:의\s*)?(?:기준|시점|당시|현재|까지|이전|이후|부터|[~～]|(?:자\s*)?회의|에(?:는)?\s*(?:합의|결정|논의|정했|요청|철회))')
MONTH = re.compile(r'(?<!\d)(?:(20\d{2})\s*년\s*)?(\d{1,2})\s*월|(?<!\d)(20\d{2})[-./](\d{1,2})(?![-./\d])')


def historical_state(tail):
    # Colloquial "그 날짜에는 ... 어떤 상태였지?" asks for the state
    # reached by that date, not only events recorded on that exact day.
    # Require past-state wording so a proposed delivery date is not a cutoff.
    if re.fullmatch(r'\s*에는\s*[?!.]*\s*',tail):return True
    return bool(re.match(r'^\s*에(?:는)?\s*', tail) and re.search(
        r'(?:상태|기준)(?:였|이었)|(?:얼마|어느\s*정도)(?:였|이었)|어땠|'
        r'(?:승인|확정|합의|결정)(?:된|됐|되었|했)|'
        r'(?:정해져|합의되어|확정되어|유지되고)\s*있었', tail))


def compact(text):
    return re.sub(r'[^가-힣a-z0-9]', '', text.lower())


def record_dates(docs):
    result = []
    for doc in docs:
        try:
            result.append(date.fromisoformat(doc.get('date', '')))
        except (ValueError, TypeError):
            pass
    return sorted(set(result))


def describe_scope(plan):
    if plan.get('mode')=='as_of':return f"{plan['end']}까지의 회의 기록 기준입니다. 등록일이나 소급 효력일 기준이 아닙니다."
    if plan.get('mode')=='meeting':return f"{plan['start']} 회의의 기록을 조회했습니다."
    if plan.get('mode')=='period':return f"{plan['start'] or '첫 기록'}부터 {plan['end'] or '최근 기록'}까지의 회의 기록입니다."
    return ''


def resolve(match, dates):
    parts = match.groupdict()
    day = int(parts.get('day') or parts['day_only'])
    month = int(parts['month']) if parts.get('month') else None
    year = int(parts['year']) if parts.get('year') else None
    if year and month:
        return [date(year, month, day)]
    candidates = {(year or d.year, month or d.month) for d in dates}
    # A month without a year is ambiguous across project years even if no
    # meeting occurred on that exact day. An as-of question need not name a meeting.
    valid=[]
    for y,m in candidates:
        try:valid.append(date(y,m,day))
        except ValueError:pass
    if candidates and not valid:raise ValueError('Invalid calendar date')
    return sorted(set(valid))


def plan_question(question, docs):
    plan = {'mode': 'current', 'start': None, 'end': None, 'notice': '',
            'message': '', 'value_question': question}
    dates = record_dates(docs)
    active = [m for m in DATE.finditer(question)
              if DATE_CONTEXT.search(question[m.end():m.end()+24])
              or historical_state(question[m.end():])
              or re.search(r'(?:기준일|회의일)\s*[:：]?\s*$', question[:m.start()])]
    if not active:
        # Unsupported relative dates must not fall through to today's fast value.
        relative=relative_period(question)
        months=list(MONTH.finditer(question))
        if relative:
            state=bool(re.search(r'얼마|언제|기준|상태|유지',question)) and not re.search(r'회의록|목록|몇\s*(?:개|건)',question)
            plan.update(mode='as_of' if state else 'period',start=None if state else relative['start'],end=relative['end'])
        elif re.search(r'작년|지난해|그때|당시|이전\s*회의', question):
            plan.update(mode='clarify', message='어느 시점의 기록인지 날짜를 함께 입력해 주세요. 예: 2026-11-11 기준')
        elif re.search(r'(?:\d{1,2}\s*월)\s*(?:의|에|중|동안)?\s*(?:회의|논의|변경|정한|정했던|합의한|결정한|확정한)', question) or (months and metadata_plan(question)):
            m=months[0];year=m[1] or m[3];month=int(m[2] or m[4])
            years = {int(year)} if year else {d.year for d in dates}
            if len(months)>1:
                plan.update(mode='clarify', message='조회 기간의 시작일과 종료일을 함께 입력해 주세요. 예: 2026-07-01부터 2026-08-31까지')
            elif not 1<=month<=12:
                plan.update(mode='clarify', message='조회할 월을 확인해 주세요. 1월부터 12월까지 입력할 수 있습니다.')
            elif len(years) != 1:
                plan.update(mode='clarify', message='조회할 연도를 함께 입력해 주세요. 등록된 자료만으로 월의 연도를 특정하지 못했습니다.')
            else:
                try:
                    y = next(iter(years))
                    plan.update(mode='period', start=date(y, month, 1).isoformat(),
                                end=date(y, month, calendar.monthrange(y, month)[1]).isoformat())
                except ValueError:
                    plan.update(mode='clarify', message='조회할 날짜를 확인해 주세요.')
        elif re.search(r'과거|변경\s*전|이력|과정|경위|어떻게\s*바뀌', question):
            plan['mode'] = 'history'
        elif re.search(r'\d{1,2}\s*월.*(?:기준|시점)|\d{4}.*(?:기준|시점)', question):
            plan.update(mode='clarify', message='기준으로 삼을 날짜를 연·월·일까지 입력해 주세요.')
    else:
        resolved = []
        for m in active:
            try:
                candidates = resolve(m, dates)
            except ValueError:
                plan.update(mode='clarify', message='조회할 날짜를 확인해 주세요. 달력에 없는 날짜는 사용할 수 없습니다.')
                return plan
            if len(candidates) != 1:
                examples = ' / '.join(d.isoformat() for d in candidates[:4])
                plan.update(mode='clarify', message='어느 날짜를 뜻하는지 연·월·일까지 입력해 주세요.' + (f' 가능한 날짜: {examples}' if examples else ' 등록된 자료에서 연·월을 특정하지 못했습니다.'))
                return plan
            resolved.append(candidates[0])
        if len(resolved) > 2:
            plan.update(mode='clarify', message='조회할 기준일 하나 또는 시작일과 종료일을 입력해 주세요.')
            return plan
        if len(resolved) == 2:
            if resolved[0] > resolved[1]:
                plan.update(mode='clarify', message='조회 기간의 시작일이 종료일보다 늦습니다. 날짜를 확인해 주세요.')
                return plan
            plan.update(mode='period', start=resolved[0].isoformat(), end=resolved[1].isoformat())
        else:
            d = resolved[0]
            tail = question[active[0].end():]
            relative_tail=re.sub(r'^\s*(?:의\s*)?(?:자\s*)?회의\s*','',tail)
            if re.match(r'\s*이전', relative_tail):
                plan.update(mode='as_of', end=(d-timedelta(days=1)).isoformat())
            elif re.match(r'\s*이후', relative_tail):
                plan.update(mode='period', start=(d+timedelta(days=1)).isoformat())
            elif re.match(r'\s*부터', relative_tail):
                plan.update(mode='period', start=d.isoformat())
            elif historical_state(tail) or re.match(r'\s*(?:의\s*)?(?:회의\s*)?(?:기준|시점|당시|현재|까지)', tail) or re.search(r'(?:기준일|회의일)\s*[:：]?\s*$', question[:active[0].start()]):
                plan.update(mode='as_of', end=d.isoformat())
            else:
                plan.update(mode='meeting', start=d.isoformat(), end=d.isoformat())
        value_question = question
        for m in reversed(active):
            end = m.end()
            cue = re.match(r'\s*(?:의\s*)?(?:회의\s*)?(?:기준|시점|당시|까지)?(?:에는|의|에|은|는)?\s*', question[end:])
            value_question = value_question[:m.start()] + value_question[end+cue.end():]
        plan['value_question'] = value_question
    if plan['mode'] == 'as_of':
        plan['notice'] = f"{plan['end']}까지의 회의 기록 기준입니다. 등록일이나 소급 효력일 기준이 아닙니다."
    elif plan['mode'] == 'meeting':
        plan['notice'] = f"{plan['start']} 회의의 기록을 조회했습니다."
    elif plan['mode'] == 'period':
        plan['notice'] = f"{plan['start'] or '첫 기록'}부터 {plan['end'] or '최근 기록'}까지의 회의 기록입니다."
    return plan


def in_scope(doc, plan):
    if not plan.get('start') and not plan.get('end'):
        return True
    try:
        day = date.fromisoformat(doc.get('date', '')).isoformat()
    except (TypeError, ValueError):
        return False
    return (not plan.get('start') or day >= plan['start']) and (not plan.get('end') or day <= plan['end'])


def without_project(question, projects):
    q = compact(question)
    # Only remove a leading, explicitly named project. Generic nouns do not
    # become topic aliases and are never deleted from the middle of a question.
    labels = set()
    generic = {'프로젝트', '전극', '제작', '장비', '신규', '설계', '라인', '설비'}
    for p in projects:
        labels.update(compact(p[k]) for k in ('name', 'id') if p.get(k))
        first=p.get('name', '').split()[:1]
        labels.update(compact(x) for x in first
                      if len(x) >= 2 and x not in generic and not re.fullmatch(r'\d+호기?', x))
    for label in sorted(labels, key=len, reverse=True):
        if q.startswith(label):
            q = q[len(label):]
            q = re.sub(r'^(?:프로젝트)?의', '', q)
            break
    return q


def value_subject(question, projects=()):
    """Recognize a small positive value-query grammar, not arbitrary word overlap."""
    q = without_project(question, projects)
    q = re.sub(r'^(?:(?:현재|지금|최종|기준|합의된|확정된|기록된))+', '', q)
    # Compound questions, requested values, reasons and completion claims go to
    # the source reader; no automatic aliases or broad category expansion.
    ending = (r'(?:언제(?:야|지|인가요|인가|예요|입니까)?|'
              r'얼마(?:야|지|인가요|인가|예요|입니까|로정했어|로합의한상태였어)?|'
              r'뭐야|무엇인가요|알려줘|알려주세요|알려줄래|확인해줘)')
    m = re.fullmatch(r'(.+?)(?:은|는|이|가|을|를)?' + ending, q)
    return m[1] if m else ''
