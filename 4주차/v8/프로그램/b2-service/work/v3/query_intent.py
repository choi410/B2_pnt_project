"""Bounded query plans for registered metadata; no generated IDs or SQL.

Normalize vocabulary, then separate entity, operation, order, date basis and limit.
Content questions stay with the source reader, even when they mention 'latest'.
"""
import calendar
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone

CONTENT = r'요약|정리|내용|아젠다|어젠다|agenda|안건|논의|주제|납품|납기|속도|사양|성능|보류|철회|요구|변경|결정|합의|이유|왜|어떻게|담당|누가|누구|완료|진행|상태|해야|방법|삭제|수정|만들때|생성방법|비교|예산|비용|가격|목적'
ATTRIBUTE = r'납품|납기|출하|출고|속도|커버|검수|검사|가압력|코팅\s*폭|슬리팅\s*폭|온도|재질|소재|교육|완충재|두께|카메라|계약|금액|보증|아젠다|어젠다|agenda|안건'
GENERIC_LABELS = {'프로젝트', '전극', '제작', '장비', '신규', '설계', '라인', '설비', '목록', '리스트', '회의록', '코팅', '롤프레스', '믹서', '슬리터', '배터리'}
EQUIPMENT_UNIT = re.compile(
    rf'(?<![0-9a-z])(?P<number>[0-9]+)\s*호기'
    rf'(?=$|[^가-힣a-z0-9]|[은는이가을를의와과에도만]|\s*프로젝트|{ATTRIBUTE})', re.I
)


def equipment_units(text):
    return {unit['number'].lstrip('0') or '0' for unit in EQUIPMENT_UNIT.finditer(text)}


def leading_unit_reference(text):
    prefix = re.match(r'\s*(?:(?:그럼|그러면)\s+)?', text)
    return EQUIPMENT_UNIT.match(text, prefix.end())


def leading_aliases(project):
    """Bounded customer/name prefixes derived from the registered name only.

    Shared prefixes remain multiple candidates; they never pick an arbitrary ID.
    Equipment-only names and codes do not acquire two-character aliases.
    """
    first = normalize(project.get('name', '')).split()[:1]
    if not first or first[0] in GENERIC_LABELS or not name_key(first[0]) or EQUIPMENT_UNIT.fullmatch(first[0]):
        return set()
    word = first[0]
    aliases = {word} if len(word) >= 2 else set()
    if re.fullmatch(r'[가-힣]{4,}', word):
        aliases.update(word[:n] for n in range(2, len(word)) if word[:n] not in GENERIC_LABELS)
    return aliases


def label_pattern(label):
    pattern = r'\s*'.join(re.escape(ch) for ch in label if not ch.isspace())
    if not pattern:return r'(?!)'
    return r'(?<!\w)' + pattern + r'(?=$|\s|[?.,!]|프로젝트|회의록|의|에서|로|은|는|말고|빼고|제외|만|도)'


def name_key(text):
    """Keep Unicode letters/numbers for identity, including standalone Hangul."""
    return ''.join(ch for ch in unicodedata.normalize('NFKC', normalize(text)).casefold()
                   if ch.isalnum())


def normalize(text):
    text = text.lower()
    for wrong, right in (('프로잭트', '프로젝트'), ('프로젝드', '프로젝트'),
                         ('회으록', '회의록'), ('회이록', '회의록'), ('희의록', '회의록'), ('젤', '제일')):
        text = text.replace(wrong, right)
    return text


def compact(text):
    return re.sub(r'[^가-힣a-z0-9]', '', normalize(text))


def unit_quantity(question):
    return bool(re.search(r'몇\s*(?:대(?!\s*상)|기(?!\s*간))|대수|물량|수량', normalize(question)))


def strip_labels(question, projects, protected=()):
    text = normalize(question)
    labels = set()
    full_labels = set()
    units = set()
    generic = {'프로젝트', '전극', '제작', '장비', '신규', '설계', '라인', '설비', '목록', '리스트', '회의록'}
    counting_units = unit_quantity(question)
    for p in projects:
        full_labels.update(normalize(p[k]) for k in ('name', 'id') if p.get(k))
        units.update(equipment_units(p.get('name', '')))
        if not counting_units:
            labels.update(normalize(x) for x in p.get('name', '').split()
                          if len(x) >= 2 and x not in generic and x != '호기')
        labels.update(leading_aliases(p))
    if (match := leading_unit_reference(text)) and equipment_units(match[0]) <= units:
        tail = text[match.end():].lstrip()
        if not re.match(ATTRIBUTE,tail):
            tail = re.sub(r'^(?:의|은|는|이|가|에서)\s*', '', tail)
        if re.match(ATTRIBUTE,tail):
            text = tail
    labels.update(full_labels)
    for label in sorted(labels, key=len, reverse=True):
        # Never remove a short label from inside an unrelated word.
        terms=list(protected)+[m[0] for m in re.finditer(ATTRIBUTE,text,re.I)
                               if len(compact(m[0]))>len(compact(label))]
        spans=[m.span() for term in terms for m in re.finditer(r'\s*'.join(re.escape(ch) for ch in normalize(term) if not ch.isspace()),text)] if label not in full_labels else []
        def replace(m):
            return m[0] if any(start<m.end() and end>m.start() for start,end in spans) else ' '
        # Name matching ignores spacing too (e.g. 롤프레스 / 롤 프레스).
        # Keep word boundaries and protected subject phrases intact.
        text = re.sub(label_pattern(label), replace, text)
    return text


def relative_period(question, today=None):
    today = today or datetime.now(timezone(timedelta(hours=9))).date()
    q = compact(question)
    if '어제' in q: start = end = today-timedelta(days=1)
    elif '그제' in q: start = end = today-timedelta(days=2)
    elif '오늘' in q: start = end = today
    elif '지난주' in q:
        end = today-timedelta(days=today.weekday()+1); start = end-timedelta(days=6)
    elif '이번주' in q:
        start = today-timedelta(days=today.weekday()); end = start+timedelta(days=6)
    elif '지난달' in q:
        end = today.replace(day=1)-timedelta(days=1); start = end.replace(day=1)
    elif '이번달' in q:
        start = today.replace(day=1); end = (start+timedelta(days=32)).replace(day=1)-timedelta(days=1)
    elif '다음달' in q:
        start = (today.replace(day=1)+timedelta(days=32)).replace(day=1)
        end = (start+timedelta(days=32)).replace(day=1)-timedelta(days=1)
    elif any(word in q for word in ('작년', '지난해', '올해', '금년', '이번해')):
        year = today.year - int('작년' in q or '지난해' in q)
        start, end = date(year, 1, 1), date(year, 12, 31)
        month = re.search(r'(?:작년|지난해|올해|금년|이번해)(?:의|에)?(\d{1,2})월', q)
        if month:
            number = int(month[1])
            if not 1 <= number <= 12:
                return None
            start, end = date(year, number, 1), date(year, number, calendar.monthrange(year, number)[1])
    else: return None
    return {'start': start.isoformat(), 'end': end.isoformat()}


def metadata_plan(question, projects=()):
    q = compact(strip_labels(question, projects))
    # Normalize references to a meeting record while retaining the date and
    # order words that the ordinary metadata parser will interpret.
    q = q.replace('회의기록', '회의록')
    q = re.sub(
        r'회의(?:를|가)?((?:가장|제일)?(?:최근|처음|마지막)(?:에)?)(?:한|했던|열린|개최한)기록',
        r'\1회의록', q)
    # A leading contrast can replace the requested record type. Parse all
    # remaining conditions normally, including any unsupported restrictions.
    replacement = re.match(
        r'^(?:(?:그럼|그러면|이제|이번에는|이번엔))?'
        r'(회의록|프로젝트)(?:은|는|을|를)?(?:말고|대신(?:에)?)(.+)$', q)
    if replacement:
        q = replacement[2]
    # Meeting takes precedence in '프로젝트별 최신 회의록'. A date-basis phrase
    # mentioning meetings is not itself the requested entity.
    criterion = re.search(r'(프로젝트생성일|회의록등록일|생산시작일|생성일|등록일|회의일|생산일|착수일)기준(?:으로)?', q)
    basis_phrase = criterion[1] if criterion else ''
    if criterion: q = q[:criterion.start()]+q[criterion.end():]
    entity = 'meeting' if '회의록' in q else 'project' if '프로젝트' in q else None
    if not entity: return None
    if replacement and entity == ('meeting' if replacement[1] == '회의록' else 'project'):
        return None
    if entity=='project' and not basis_phrase:
        from work.v3.project_facts import plan as project_fact_plan
        facts=project_fact_plan(q)
        if facts:return facts
    # These are content/behavior questions, not metadata queries. Do not answer
    # '최근 프로젝트의 납품일' with a project name or a global date ranking.
    if re.search(CONTENT, q):
        return None
    q = re.sub(r'(몇(?:개|건))(?:인지|입니까|인가요)', r'\1', q)
    vocabulary = '''프로젝트 회의록 중에서 중에 가운데 어떤 어떤거야 어떤건가요 무슨 뭐야 뭐지 뭔가요 뭔지 무엇인가요 무엇입니까 무엇이야 무엇인가 무엇 뭐
        알려주세요 알려줄래 알려줘 알려줄수있어 알려주시겠어요 보여주세요 보여줘 보여줄래 찾아주세요 찾아줘 검색 확인해줘 열어줘 조회 부탁해 보고싶어 보고싶어요 보고싶습니다
        생성했던 생성된 생성한 생성 등록했던 등록되어 등록돼 등록된 등록한 등록 업로드된 업로드한 업로드 올린 올라온 올렸 만든 만들어진 만들었던 생긴 추가된 추가한 추가
        생산한 생산된 착수한 시작한 첫번째 첫 처음으로 처음 먼저 오래된 초기 최신 최근에 최근 마지막으로 마지막에 마지막 나중에 나중
        제일 가장 방금 막 새로 새 이름 제목 명 목록 리스트 정렬 순서대로 순으로 순서 순 전체 모든 전부 각 별 마다 각각
        몇개나 몇개 몇건 개수 갯수 건수 총수 총 합계 개 건 만 그럼 그러면 이제 이번에는 이번엔 현재 지금 오늘 어제 그제 지난주 이번주 지난달 이번달
        기준일 회의일 생성일 등록일 이전 이후 부터 까지 기준 시점 년 월 일 있었던 있는 있어 있나요 있니 있나 우리 저희 것 거 꺼 게 들 는 은 이 가 을 를 의 에 에서 중 그 로 한 된 으로 나 야 지 인가요 인가 입니다'''
    residual=re.sub('|'.join(re.escape(word) for word in sorted(set(vocabulary.split()),key=len,reverse=True)), '', q)
    residual=re.sub(r'\d+','',residual)
    if residual:return None
    count = bool(re.search(r'몇(?:개|건)|개수|갯수|건수|총수|몇개나', q))
    quantity = re.search(r'(\d+)\s*(?:개|건)', q)
    limit = min(int(quantity[1]), 100) if quantity else None
    newest = bool(re.search(r'최신|최근|마지막|나중|방금|막(?:만든|생성|등록)|(?:가장|제일)?새(?:프로젝트|회의록)|새로(?:만든|생성|등록)', q))
    oldest = bool(re.search(r'처음|첫|먼저|오래된|오래된순|초기', q))
    direction = 'oldest' if oldest else 'newest' if newest else None
    listing = bool(re.search(r'목록|리스트|정렬|순(?:으로|서|서대로)?', q)) or limit is not None
    if not direction and re.search(r'전체|모든|전부',q):listing=True
    period = relative_period(question)
    operation = 'count' if count else 'list' if listing or period else 'rank' if direction else 'list'
    if entity == 'project':
        basis = 'created_at'
        if basis_phrase and basis_phrase not in ('생성일','등록일','프로젝트생성일'): basis = basis_phrase
        if re.search(r'생산한|생산된|착수한|시작한', q): basis = '생산·착수일'
    else:
        basis = 'registered_at' if re.search(r'등록|업로드|올린|올라온|올렸', q) or basis_phrase == '등록일' else 'meeting_date'
        if basis_phrase and basis_phrase not in ('회의일','등록일','회의록등록일'): basis = basis_phrase
        if basis_phrase == '회의록등록일': basis = 'registered_at'
    return {'entity':entity, 'operation':operation, 'direction':direction or 'newest',
            'basis':basis, 'limit':limit, 'per_project':entity == 'meeting' and bool(re.search(r'프로젝트(?:별|마다)|각프로젝트', q)),
            'period':period}


def unresolved_metadata(question,projects=()):
    q=compact(strip_labels(question,projects))
    return bool(re.search(r'프로젝트|회의록',q) and not re.search(CONTENT,q)
                and re.search(r'최근|최신|처음|첫|몇|개수|갯수|건수|순서|정렬',q))


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (AttributeError, TypeError, ValueError):
        return None


def edit_distance(a, b):
    # Adjacent transpositions count as one typo.
    table = [[0]*(len(b)+1) for _ in range(len(a)+1)]
    for i in range(len(a)+1): table[i][0] = i
    for j in range(len(b)+1): table[0][j] = j
    for i in range(1,len(a)+1):
        for j in range(1,len(b)+1):
            table[i][j] = min(table[i-1][j]+1,table[i][j-1]+1,table[i-1][j-1]+(a[i-1]!=b[j-1]))
            if i>1 and j>1 and a[i-1]==b[j-2] and a[i-2]==b[j-1]:
                table[i][j] = min(table[i][j],table[i-2][j-2]+1)
    return table[-1][-1]


def uncertain_project(projects, question):
    """Offer accessible candidates, never silently apply a fuzzy match."""
    # '회의록에서' introduces a source, not a project name. Keep the rest
    # subject to the usual name checks, including an unknown name after it.
    question = re.sub(r'^\s*(?:(?:등록된|저장된)\s+)?회의(?:록|\s*기록)\s*에서(?:는|도)?\s*', '', normalize(question))
    # A leading date describes the search period, not a missing project name.
    # Strip it only for name recognition; scope parsing still validates the
    # month/day. Keep actual names after the date subject to the same checks.
    question = re.sub(
        r'^\s*(?:(?:20\d{2}\s*년\s*)?\d{1,2}\s*월(?:\s*\d{1,2}\s*일)?'
        r'|20\d{2}[-./]\d{1,2}(?:[-./]\d{1,2})?|\d{1,2}\s*일)'
        r'(?:\s*(?:에는|에서|의|에|동안|중|기준))?(?=$|\s|회의록|프로젝트|납기|납품일)\s*',
        '', question)
    # The metadata grammar already accounts for phrases such as '등록한
    # 회의록'. These are not project names either. Unknown names leave a
    # residual and still proceed to the explicit/fuzzy name checks below.
    if metadata_plan(question,projects):return None
    if equipment_units(question):return []
    tokens = re.findall(r'[가-힣a-zA-Z0-9-]+', normalize(question))
    candidates = []
    generic = {'프로젝트','회의록','전극','설계','장비','제작','신규','설비','납품일','납기일','알려줘','보여줘','찾아줘','현재','최근','최신','전체'}
    for p in projects:
        labels = [compact(x) for x in p['name'].split() if len(x)>=3 and x not in generic and not re.fullmatch(r'\d+호기?',x)]
        if any(t not in generic and len(t)>=3 and not re.match(label_pattern(label),t)
               and edit_distance(t,label)==1 for t in tokens for label in labels):
            candidates.append(p)
    if candidates: return candidates
    # A named project request that did not match may not become an all-project
    # content search. Generic ordering/listing words are intentionally excluded.
    prefix = re.match(r'^\s*([가-힣a-zA-Z0-9-]+(?:\s+[가-힣a-zA-Z0-9-]+)*)\s+프로젝트', normalize(question))
    generic_prefix=r'전체|모든|각|그|이|다른|나머지|거기|그쪽|앞서|아까|최근|최신|첫|첫번째|처음|새|어떤|무슨|등록된|생성된|만든|올린|지난주|이번주|어제|오늘|이번|지난|현재|장비|설비|최종'
    if prefix and not re.fullmatch(generic_prefix,prefix[1].split()[0]):
        return []
    prefix=re.match(r'^\s*([가-힣a-zA-Z0-9-]+)\s+(?:납품일|납기|압연\s*속도|회의록)',normalize(question))
    if prefix and prefix[1] not in generic and not re.fullmatch(generic_prefix,prefix[1]):
        return []
    return None
