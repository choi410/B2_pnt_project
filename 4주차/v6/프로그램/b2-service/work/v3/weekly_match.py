"""주간보고 연동: 메모 한 줄마다 관련 회의록 문장·변경 이력·후속 조치 후보를 찾는다.

모델을 쓰지 않는 낱말 대조다. 같은 입력이면 항상 같은 결과가 나오고, 점수의 이유를 함께 돌려준다.
후보는 제안일 뿐이며 사용자가 연결 확인 화면에서 고른 것만 초안에 쓴다.
"""
import math
import re
from datetime import date, timedelta

SECTION_KINDS = [
    (('후속', '조치', '할 일', '할일', '액션', 'action'), 'action'),
    (('추가 확인', '확인 사항', '확인사항', '미결'), 'action'),
    (('결정', '합의', '결론'), 'decision'),
    (('진행', '현황', '경과'), 'progress'),
    (('논의', '안건', '협의', '내용'), 'discussion'),
]
KIND_LABEL = {'meeting': '회의', 'progress': '진행 현황', 'discussion': '논의', 'decision': '결정', 'action': '후속 조치',
              'change': '변경 이력'}
_PARTICLES = ('으로부터', '에게서', '이라고', '으로', '에서', '에게', '까지', '부터', '하고', '이며', '라고', '은', '는', '이', '가',
              '을', '를', '의', '에', '로', '와', '과', '도', '만')
_ENDINGS = ('하기로', '하였다', '했으나', '합니다', '했다', '한다', '했음', '하다', '된다', '됐다', '되었다', '하며', '해', '함', '됨')
_STOP = {'및', '등', '건', '관련', '대한', '위한', '통해', '그리고', '또는', '있다', '없다', '것', '수', '중', '후', '전', '시',
         '고객', '회의', '회의록', '진행', '완료', '예정', '확인', '검토', '요청', '협의', '기존', '현재', '해당', '담당자'}
_KIND_ORDER = {'change': 0, 'action': 1, 'decision': 2, 'progress': 3, 'discussion': 4, 'meeting': 5}
_DATE = re.compile(r'(20\d{2})-(\d{2})-(\d{2})')
_SENTENCE_END = re.compile(r'[.!?。]["\')\]]?$')


def compact(text):
    return re.sub(r'\s+', '', str(text or ''))


def stem(word):
    """조사와 흔한 어미를 떼어 낸다. 형태소 분석기가 아니므로 두 글자 미만으로는 줄이지 않는다."""
    for ending in _ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 2:
            return word[:-len(ending)]
    for particle in _PARTICLES:
        if word.endswith(particle) and len(word) - len(particle) >= 2:
            return word[:-len(particle)]
    return word


def terms(text):
    """대조에 쓰는 낱말 집합. 숫자는 단위와 떨어뜨려 그대로 둔다(135, 680)."""
    found = set()
    for word in re.findall(r'[가-힣]+|[A-Za-z][A-Za-z0-9]*|\d+(?:[.,]\d+)*', str(text or '')):
        if re.match(r'\d', word):
            found.add(word.replace(',', ''))
        elif re.match(r'[A-Za-z]', word):
            if len(word) >= 2:
                found.add(word.lower())
        else:
            base = stem(word)
            if len(base) >= 2 and base not in _STOP:
                found.add(base)
    return found


def heading_kind(line):
    key = line.strip().lower()
    if len(key) > 14 or _SENTENCE_END.search(key) or ':' in key or re.search(r'\d{2,}', key):
        return None
    for words, kind in SECTION_KINDS:
        if any(w in key for w in words):
            return kind
    return None


def vocabulary(bodies):
    """줄바꿈에 걸리지 않고 온전히 나온 낱말. 줄 끝에서 잘린 낱말을 다시 이을 때 기준으로 쓴다."""
    words = set()
    for body in bodies:
        closed = True
        for line in str(body or '').replace('\r', '').split('\n'):
            parts = line.split()
            if not parts:
                continue
            ends = bool(_SENTENCE_END.search(line.strip())) or heading_kind(line) is not None or ':' in line
            whole = parts[(0 if closed else 1):(len(parts) if ends else len(parts) - 1)]
            words.update(part.strip('.,()[]"\'') for part in whole)
            closed = ends
    words.discard('')
    return words


def _join(left, right_raw, known):
    """PDF 줄바꿈으로 나뉜 두 줄을 잇는다. 낱말 중간에서 끊겼으면 붙이고 아니면 띄운다."""
    right = right_raw.strip()
    if right_raw[:1].isspace():
        return left + ' ' + right
    a = left.split()[-1].strip('.,()[]"\'') if left.split() else ''
    b = right.split()[0].strip('.,()[]"\'') if right.split() else ''
    if a + b in known:
        return left + right
    korean = bool(re.search(r'[가-힣]$', a) and re.match(r'[가-힣]', b))
    if korean and (len(a) == 1 or len(b) == 1):
        return left + right  # 한 글자만 남은 쪽은 낱말이 잘린 것이다: '변/경', '요청했/다.'
    if korean and len(b) <= 3 and any(b.startswith(p) for p in _PARTICLES) and b not in known:
        return left + right  # 조사만 다음 줄로 넘어갔다: '조건/으로'
    return left + ' ' + right


def sentences(body, known=None):
    """회의록 본문을 (구역, 문장, 줄 번호들)로 나눈다. 줄 번호는 화면의 근거 표시(L001…)와 같다."""
    raw = [line for line in str(body or '').replace('\r', '').split('\n') if line.strip()]
    known = known if known is not None else vocabulary([body])
    result, kind, current, ids, closed = [], 'meta', '', [], True
    def flush():
        nonlocal current, ids
        if current.strip():
            parts = re.split(r'(?<=[.!?])\s+(?=[가-힣A-Z0-9(])', current.strip())
            for part in parts:
                if part.strip():
                    result.append((kind, part.strip(), list(ids)))
        current, ids = '', []
    for number, line_raw in enumerate(raw, 1):
        line, line_id = line_raw.strip(), 'L' + str(number).zfill(3)
        found = heading_kind(line) if closed else None
        metadata = bool(re.match(r'^[가-힣A-Za-z ]{2,10}\s*:\s*\S', line)) and closed
        if found:
            flush(); kind, closed = found, True
            continue
        if metadata or kind == 'meta':
            flush(); result.append(('meta', line, [line_id])); closed = True
            continue
        if current and not closed:
            current = _join(current, line_raw, known); ids.append(line_id)
        else:
            flush(); current, ids = line, [line_id]
        closed = bool(_SENTENCE_END.search(line))
    flush()
    return result


def parse_action(text, people):
    """후속 조치 문장에서 담당자, 기한, 할 일을 뽑는다. 문장에 없는 값은 만들지 않는다."""
    owners = [name for name in people if re.search(re.escape(name) + r'(?:은|는|이|가|과|와|,|\s)', text)]
    lead = re.match(r'\s*([가-힣]{2,4})(?:은|는|이|가)\s', text)
    owner = lead.group(1) if lead and lead.group(1) in people else (owners[0] if len(owners) == 1 else '')
    days = [m.group(0) for m in _DATE.finditer(text)]
    span = re.search(r'(20\d{2}-\d{2}-\d{2})\s*부터\s*(20\d{2}-\d{2}-\d{2})\s*까지', text)
    until = re.search(r'(20\d{2}-\d{2}-\d{2})\s*(?:까지|에|중)', text)
    begin, due = (span.group(1), span.group(2)) if span else ('', until.group(1) if until else (days[-1] if len(days) == 1 else ''))
    undecided = bool(re.search(r'미정|정하지 못|다음 협의에서 정|추후 (?:결정|협의)', text))
    task = text.strip()
    if owner and lead:
        task = task[lead.end():]
    task = re.sub(r'^\s*20\d{2}-\d{2}-\d{2}\s*부터\s*20\d{2}-\d{2}-\d{2}\s*까지\s*', '', task)
    task = re.sub(r'^\s*20\d{2}-\d{2}-\d{2}\s*(?:까지|에|중)\s*', '', task).rstrip('.').strip()
    if not undecided:
        short = re.sub(r'(?:한다|합니다|하기로 했다|하기로 함)$', '', task).strip()
        if short != task and len(short) >= 4:
            task = re.sub(r'(?<=[가-힣A-Za-z0-9])(?:을|를)\s+(\S+)$', r' \1', short)
    return {'owner': owner, 'start': begin, 'due': due, 'undecided': undecided, 'task': task or text.strip()}


def build_index(projects, documents, events, people):
    """대조할 단위 목록을 만든다.

    projects: [{id,name}], documents: registered_document 결과 목록, events: change_event 목록,
    people: 이름 목록. 반환값은 {'units':[...], 'idf':{...}, 'projects':{id:name}}.
    """
    names = {p['id']: p['name'] for p in projects}
    units, covered = [], {}
    docs = {d['meeting_id']: d for d in documents if d['project_id'] in names}
    known = vocabulary(d['body'] for d in docs.values())
    for event in events:
        doc = docs.get(event.get('meeting_id'))
        if not doc or event.get('deleted_at') or event.get('project_id') not in names:
            continue
        reviewed = event.get('review_state') == '확인됨'
        before, after = str(event.get('before') or '').strip(), str(event.get('after') or '').strip()
        value = (before + ' → ' + after) if before and before != after else after
        state = str(event.get('business_state') or '').strip()
        units.append({
            'id': 'C:' + event['id'], 'kind': 'change', 'project_id': event['project_id'], 'meeting_id': doc['meeting_id'],
            'meeting_title': doc['title'], 'meeting_date': doc.get('date', ''), 'revision': doc['revision'],
            'text': f"{event['title']}: {value}" + (f' ({state})' if state else ''), 'lines': list(event.get('evidence') or []),
            'quote': ' '.join(event.get('quotes') or [])[:400] or f"{event['title']}: {value}", 'reviewed': reviewed, 'category': event.get('category', ''),
            'subject': event['title'], 'before': before, 'after': after, 'state': state,
            'effective_date': event.get('effective_date', ''),
            'match_text': ' '.join([event['title'], before, after, state, ' '.join(event.get('quotes') or [])])})
        if reviewed:
            covered.setdefault(doc['meeting_id'], set()).update(event.get('evidence') or [])
    for doc in docs.values():
        base = {'project_id': doc['project_id'], 'meeting_id': doc['meeting_id'], 'meeting_title': doc['title'],
                'meeting_date': doc.get('date', ''), 'revision': doc['revision'], 'reviewed': True}
        units.append({**base, 'id': 'M:' + doc['meeting_id'], 'kind': 'meeting', 'text': doc['title'], 'lines': [],
                      'quote': doc['title'], 'match_text': doc['title']})
        for i, (kind, text, ids) in enumerate(sentences(doc['body'], known)):
            if kind == 'meta' or len(compact(text)) < 6:
                continue
            action = None
            if kind == 'action' or (kind == 'discussion' and re.search(r'까지', text) and any(n in text for n in people)):
                kind, action = 'action', parse_action(text, people)
            # 검토를 마친 변경 이력이 같은 줄을 이미 다루면 결정 문장은 중복이므로 후보에서 뺀다.
            if kind == 'decision' and ids and set(ids) <= covered.get(doc['meeting_id'], set()):
                continue
            unit = {**base, 'id': f"S:{doc['meeting_id']}:{i}", 'kind': kind, 'text': text, 'lines': ids, 'quote': text,
                    'match_text': text}
            if action:
                unit.update(action=action)
            units.append(unit)
    # 같은 항목이 뒤 회의에서 다시 바뀌었으면 앞의 값은 지난 값이다(예: 검수일 11/24 → 11/27).
    newest = {}
    for unit in units:
        if unit['kind'] == 'change':
            key, stamp = (unit['project_id'], unit['subject']), (unit['meeting_date'], unit['effective_date'])
            if key not in newest or stamp > newest[key][0]:
                newest[key] = (stamp, unit['id'])
    for unit in units:
        if unit['kind'] == 'change':
            unit['superseded'] = newest[(unit['project_id'], unit['subject'])][1] != unit['id']
    frequency = {}
    for unit in units:
        unit['terms'] = terms(unit['match_text'])
        unit['context'] = terms(names[unit['project_id']] + ' ' + unit['meeting_title']) - unit['terms']
        unit['own_compact'] = compact(unit['match_text'])
        unit['compact'] = compact(unit['match_text'] + names[unit['project_id']] + unit['meeting_title'])
        for term in unit['terms'] | unit['context']:
            frequency[term] = frequency.get(term, 0) + 1
    total = max(1, len(units))
    idf = {term: math.log(1 + total / count) for term, count in frequency.items()}
    return {'units': units, 'idf': idf, 'projects': names, 'default_idf': math.log(1 + total)}


def _day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def score(row, unit, index, start, end):
    """(점수 0~1.3, 문장 자체가 겹친 비율, 이유 목록). 메모의 낱말이 단위에 얼마나 들어 있는지를 본다."""
    row_terms = terms(row['text'])
    if not row_terms:
        return 0.0, 0.0, []
    idf, default = index['idf'], index['default_idf']
    weight = lambda t: idf.get(t, default)
    total = sum(weight(t) for t in row_terms)
    hit, context_hit, matched, around = 0.0, 0.0, [], []
    for term in row_terms:
        if term in unit['terms']:
            hit += weight(term); matched.append(term)
        elif term in unit['context']:
            context_hit += weight(term) * 0.55; around.append(term)
        elif len(term) >= 3 and term in unit['own_compact']:
            hit += weight(term) * 0.8; matched.append(term)
        elif len(term) >= 3 and term in unit['compact']:
            context_hit += weight(term) * 0.45; around.append(term)
    if not matched and not around:
        return 0.0, 0.0, []
    value = (hit + context_hit) / total
    if hit == 0:
        value *= 0.6  # 프로젝트·회의 이름만 맞고 문장 내용은 겹치지 않는다.
    top = lambda found: ', '.join(sorted(found, key=lambda t: -weight(t))[:4])
    reasons = (['겹치는 말: ' + top(matched)] if matched else []) + (['회의·프로젝트 이름: ' + top(around)] if around else [])
    row_day, meeting_day = _day(row.get('date')), _day(unit['meeting_date'])
    due = _day(unit.get('action', {}).get('due')) if unit.get('action') else None
    if row_day and meeting_day and row_day == meeting_day:
        value += 0.18; reasons.append('회의일과 같은 날짜')
    elif row_day and due and row_day == due:
        value += 0.15; reasons.append('조치 기한과 같은 날짜')
    elif meeting_day and start <= meeting_day <= end:
        value += 0.06; reasons.append('보고 기간 안의 회의')
    elif meeting_day and (meeting_day < start - timedelta(days=21) or meeting_day > end + timedelta(days=7)):
        value -= 0.12
    if unit['kind'] == 'meeting':
        value *= 0.9
    if not unit.get('reviewed', True):
        value -= 0.05; reasons.append('검토 전 변경 이력')
    return max(0.0, round(value, 3)), round(hit / total, 3), reasons


def confidence(value):
    return 'high' if value >= 0.62 else 'mid' if value >= 0.4 else 'low'


def public(unit, index):
    """화면과 저장에 쓰는 단위 요약."""
    item = {k: unit[k] for k in ('id', 'kind', 'project_id', 'meeting_id', 'meeting_title', 'meeting_date', 'revision', 'text',
                                  'lines', 'quote', 'reviewed')}
    item.update(kind_label=KIND_LABEL[unit['kind']], project_name=index['projects'][unit['project_id']])
    if unit.get('action'):
        item['action'] = unit['action']
    if unit['kind'] == 'change':
        item.update({k: unit[k] for k in ('category', 'subject', 'before', 'after', 'state', 'effective_date', 'superseded')})
    return item


def match_rows(rows, index, start, end, actor_name='', limit=6):
    """행마다 후보를 붙이고, 메모에 없지만 이번 주 보고에 쓸 만한 회의록 항목(extras)을 고른다."""
    start, end = _day(start), _day(end)
    matched_rows, used = [], set()
    for row in rows:
        scored = []
        for unit in index['units']:
            value, own, reasons = score(row, unit, index, start, end)
            if value >= 0.25:
                scored.append((value, unit, reasons, own))
        scored.sort(key=lambda x: (-x[0], -x[3], _KIND_ORDER[x[1]['kind']], x[1]['meeting_date'], x[1]['id']))
        # 같은 회의의 제목 단위는 문장 단위가 이미 잡혔으면 뒤로 미룬다.
        candidates, top_meeting = [], scored[0][1]['meeting_id'] if scored else None
        runner_up = next((x[0] for x in scored if x[1]['meeting_id'] != top_meeting), 0.0)
        for value, unit, reasons, own in scored[:limit]:
            level = confidence(value)
            clear = unit['meeting_id'] == top_meeting and scored[0][0] - runner_up >= 0.08
            # 회의 이름만 맞은 문장은 고르지 않는다. 문장 자체가 메모와 겹쳐야 자동 선택한다.
            direct = own >= 0.3 or unit['kind'] == 'meeting'
            selected = level == 'high' and clear and direct and sum(c['selected'] for c in candidates) < 4
            candidates.append({**public(unit, index), 'score': value, 'confidence': level, 'reasons': reasons, 'selected': selected})
            if selected:
                used.add(unit['id'])
        project_scores = {}
        for c in candidates:
            project_scores[c['project_id']] = project_scores.get(c['project_id'], 0) + c['score']
        best = max(project_scores, key=project_scores.get) if project_scores else ''
        state = 'linked' if any(c['selected'] for c in candidates) else 'check' if candidates else 'none'
        matched_rows.append({**row, 'candidates': candidates, 'project_id': best if state != 'none' else '',
                             'project_name': index['projects'].get(best, '') if state != 'none' else '', 'match_state': state})
    next_start, next_end = end + timedelta(days=1), end + timedelta(days=9)
    extras = []
    for unit in index['units']:
        if unit['id'] in used or unit.get('superseded'):
            continue
        meeting_day, group = _day(unit['meeting_date']), ''
        if unit['kind'] == 'action':
            action = unit['action']
            due, begin = _day(action['due']), _day(action['start'])
            if due and next_start <= due <= next_end or begin and due and begin <= next_end and due >= next_start:
                group = 'next'
            elif due and start <= due <= end:
                group = 'due'
            elif action['undecided'] and meeting_day and start <= meeting_day <= end:
                group = 'open'
        elif unit['kind'] == 'change' and meeting_day and start <= meeting_day <= end:
            target = _day(unit['after']) if unit['category'] == '납기' else None
            group = 'schedule' if target and next_start <= target <= next_end and unit['state'] == '확정' else 'decided'
        elif unit['kind'] == 'change' and unit['category'] == '납기' and unit['state'] == '확정':
            target = _day(unit['after'])
            if target and next_start <= target <= next_end:
                group = 'schedule'
        elif unit['kind'] == 'meeting' and meeting_day and start <= meeting_day <= end:
            group = 'meeting'
        elif unit['kind'] == 'decision' and meeting_day and start <= meeting_day <= end:
            group = 'decided'
        if not group:
            continue
        mine = bool(actor_name) and unit.get('action', {}).get('owner') == actor_name
        extras.append({**public(unit, index), 'group': group, 'mine': mine, 'selected': mine and group in ('next', 'due')})
    order = {'next': 0, 'due': 1, 'schedule': 2, 'open': 3, 'decided': 4, 'meeting': 5}
    extras.sort(key=lambda x: (order[x['group']], not x['mine'], x['project_name'], x['meeting_date'], x['id']))
    return matched_rows, extras
