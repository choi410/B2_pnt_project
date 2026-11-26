"""The company's fixed minutes form (미팅 회의록, fixed on 2026-11-25).

Layout of the one sheet:
  top block   Project / Description / Item / Date / 作成 / 承認 / Sheet No / Revision (label, value to its right)
  table head  구 분 | 회 의 내 용 | 담당자 | 일 정 | 비 고
  rows        1 회의일자, 2 회의장소, 3 회의참석 (고객사 / PNT / 협력사), 4 회의내용
  회의내용     headings ("* 개조 내용 :", "1. 코팅 폭·속도") and statement rows: who said it (고객사 / pnt /
              협력사) left of the text, then 담당자, 일정 and a 비고 word.

read() turns the sheet into the lines the analysis reads, one statement per line:
  [고객사] 코팅 폭 800mm → 780mm 변경 요청 (담당 김도윤 · 비고 변경)
apply_remarks() then sets each change record's state from the 비고 column, which the writer filled in by
hand: the model no longer has to guess what the form already says.

비고 words: 신규 / 변경 say what kind of statement it is; 유지 says nothing changed; the others are the
state. The service keeps four states, so each maps to one, and the form's own word is kept in
`form_state` for display:
  확정, 완료, 합격 -> 확정     검토 중, 조치 중, 미달 -> 요청     보류 -> 보류     철회 -> 철회
"""
import re

STATE = {'확정': '확정', '완료': '확정', '합격': '확정', '검토 중': '요청', '조치 중': '요청', '미달': '요청',
         '보류': '보류', '철회': '철회'}
KIND = ('신규', '변경', '유지')
_TOP = {'project': 'project', 'description': 'description', 'item': 'item', 'date': 'date', '作成': 'author',
        '承認': 'approver', 'sheetno': 'sheet', 'revision': 'revision'}
_tight = lambda v: re.sub(r'\s+', '', str(v or ''))
_REMARK = re.compile(r'비고 (' + '|'.join(list(STATE) + list(KIND)) + r')\)\s*$')
_TAIL = re.compile(r'\s*\((?:담당|일정|비고) [^()]*\)\s*$')
_SPEAKER = re.compile(r'^\s*\[[^\]]{1,12}\]\s*')
_ASKING = re.compile(r'요청|검토|제안|문의|예정|협의|회신')


def _text(v):
    if hasattr(v, 'isoformat'):
        return v.isoformat()[:10]
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _remark(v):
    """A 비고 cell as one of the known words ('검토중' -> '검토 중'), else ''."""
    t = _tight(v)
    return next((w for w in list(STATE) + list(KIND) if _tight(w) == t), '')


def _head(rows):
    """(row index, {'content','owner','due','remark': column}) of the table head, or None."""
    for n, row in enumerate(rows[:30]):
        names = {_tight(v): c for c, v in row}
        if '회의내용' in names and '비고' in names and '담당자' in names:
            return n, {'content': names['회의내용'], 'owner': names['담당자'], 'due': names.get('일정'), 'remark': names['비고']}
    return None


def is_form(rows):
    return _head(rows) is not None


def read(rows):
    """rows: one list of (column number, value) per sheet row, empty cells left out.
    Returns {'source', 'title', 'project', 'meeting_date'}; None when the sheet is not this form."""
    found = _head(rows)
    if not found:
        return None
    head, col = found
    top = {}
    for row in rows[:head]:
        cells = sorted(row)
        for i, (_, v) in enumerate(cells):
            key = _TOP.get(_tight(v).casefold())
            if key and i + 1 < len(cells) and _tight(cells[i + 1][1]).casefold() not in _TOP:
                top.setdefault(key, _text(cells[i + 1][1]))
    project = ' '.join(x for x in (top.get('project'), top.get('description')) if x)
    lines = [f'프로젝트: {project}'] if project else []
    if top.get('item'):
        lines.append('회의명: ' + top['item'])
    signed = [f'{k} {top[f]}' for k, f in (('작성', 'author'), ('승인', 'approver'), ('Revision', 'revision')) if top.get(f)]
    block = ''; when = ''
    body = []
    for row in rows[head + 1:]:
        cells = dict(row)
        text = _text(cells[col['content']]) if cells.get(col['content']) not in (None, '') else ''
        labels = [_text(v) for c, v in sorted(row) if c < col['content'] and not isinstance(v, (int, float)) and _text(v)]
        label = labels[-1] if labels else ''
        if _tight(label) in ('회의일자', '회의장소', '회의참석', '회의내용'):
            block = _tight(label); label = ''
        if not text:
            continue
        if block == '회의일자':
            when = when or text; lines.append('회의일: ' + text); continue
        if block == '회의장소':
            lines.append('회의장소: ' + text); continue
        if block == '회의참석':
            lines.append('참석 ' + text); continue
        tail = [f'{k} {_text(cells[c])}' for k, c in (('담당', col['owner']), ('일정', col['due'])) if c and cells.get(c) not in (None, '')]
        remark = _remark(cells.get(col['remark']))
        if remark:
            tail.append('비고 ' + remark)
        if not label and not tail and text.startswith('(') and body and body[-1][0].startswith('['):
            body[-1][0] += ' ' + text   # a reason written under a statement belongs to that statement
            continue
        body.append([(f'[{label}] ' if label else '') + text, tail])
    body = [text + (' (' + ' · '.join(tail) + ')' if tail else '') for text, tail in body]
    if signed:
        lines.append(' · '.join(signed))
    date = top.get('date') or ''
    m = re.search(r'(20\d{2})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})', date or when)
    return {'source': '\n'.join(lines + body), 'title': top.get('item', ''), 'project': project,
            'meeting_date': f'{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}' if m else ''}


def _plain(value):
    """A value the model copied as a whole line, without the form's speaker tag and tail."""
    return _TAIL.sub('', _SPEAKER.sub('', str(value))).strip()


def apply_remarks(items, source_lines):
    """Set each record's state from the 비고 word of its lines. Lines without the form's tail are left
    to the model, so minutes in any other form pass through unchanged.

    - a state word on the record's own lines decides (the first one: '미달' before the '조치 중' reply);
    - 신규 / 변경 only: the reply that follows in the same block decides ('변경' then '[pnt] … 확정');
    - no reply: 신규 is a request; 변경 is a request when its sentence asks ('요청', '검토' …), else agreed;
    - 유지 only: nothing changed, the record is dropped.
    """
    remarks = {}
    for line in source_lines or []:
        m = _REMARK.search(str(line.get('text') or ''))
        remarks[line['id']] = m[1] if m else ''
    if not any(remarks.values()):
        return items
    order = [line['id'] for line in source_lines]
    texts = {line['id']: str(line.get('text') or '') for line in source_lines}
    out = []
    for item in items:
        ids = sorted((i for i in item.get('evidence') or [] if i in remarks), key=order.index)
        own = [remarks[i] for i in ids if remarks[i]]
        if not own:
            out.append(item); continue
        if all(r == '유지' for r in own):
            continue
        word = next((r for r in own if r in STATE), '')
        if not word:
            for i in order[order.index(ids[-1]) + 1:]:
                if remarks[i] in STATE:
                    word = remarks[i]; break
                if remarks[i] in KIND or not texts[i].startswith('['):
                    break   # the next statement of its own, or the next heading
        if word:
            item = {**item, 'business_state': STATE[word], 'form_state': word}
        elif item.get('business_state') not in ('보류', '철회'):
            said = ' '.join(_REMARK.sub('', texts[i]).split(' (담당 ')[0] for i in ids)
            asked = '신규' in own or bool(_ASKING.search(said)) and '확정' not in said
            item = {**item, 'business_state': '요청' if asked else '확정'}
        out.append({**item, **{k: _plain(item.get(k)) for k in ('title', 'before', 'after') if item.get(k)}})
    return out


RESULT = ('완료', '합격', '미달', '조치 중')   # inspection and action results: a record even without a number


def threads(source_lines):
    """The statements the 비고 column marks, grouped into one thread per subject:
    [{'ids': [line ids], 'section': the heading above}]. A thread opens at a marked statement (유지 is not
    one). Until it has a state, the lines under it are its replies ('변경' then '[pnt] … 확정'); an action
    reply ('조치 중') after a failed check ('미달') also belongs to it. Unmarked lines outside a thread and
    headings are not statements to record."""
    out = []; open_ = None; section = ''
    for line in source_lines or []:
        text = str(line.get('text') or '')
        if not text.startswith('['):
            section = text; open_ = None; continue
        m = _REMARK.search(text); word = m[1] if m else ''
        reply = open_ is not None and word not in KIND and (
            open_['state'] is None or (word == '조치 중' and open_['state'] == '미달'))
        if reply:
            open_['ids'].append(line['id'])
            if word in STATE and open_['state'] is None:
                open_['state'] = word
        elif word and word != '유지':
            open_ = {'ids': [line['id']], 'section': section, 'state': word if word in STATE else None}
            out.append(open_)
        else:
            open_ = None
    return [{'ids': t['ids'], 'section': t['section']} for t in out]


def uncovered(items, source_lines):
    """Threads none of whose lines a record cites."""
    cited = {i for x in items for i in x.get('evidence') or []}
    return [t for t in threads(source_lines) if not cited & set(t['ids'])]


_ANY_TAIL = re.compile(r'\s*\(((?:담당|일정|비고) [^()]*)\)')
_ANY_SPEAKER = re.compile(r'(^|(?<=[.\s]))\[(?:고객사|협력사|pnt|PNT|Pnt)\]\s*')


def plain_text(text):
    """Form statements as the service shows them: nothing is removed. Statements joined into one text
    ('[고객사] … (담당 한소희 · 비고 합격) [고객사] … (담당 …)') are put on separate lines, and a form statement
    ends with a line break so that statements joined later by the screen stay one per line.
    Text without the form's marks is returned as is."""
    text = str(text or '')
    if not _ANY_TAIL.search(text) and not _ANY_SPEAKER.search(text):
        return text
    text = re.sub(r'(\((?:담당|일정|비고) [^()]*\))[ \t]+(?=\S)', r'\1\n', text.strip())   # after a statement's tail
    text = re.sub(r'(?<=\S)[ \t]+(?=\[(?:고객사|협력사|pnt|PNT|Pnt)\] )', '\n', text)        # before the next speaker
    return text + '\n'


_NOTE_KIND = {'확정': '결정', '완료': '결정', '합격': '결정', '보류': '결정', '철회': '결정',
              '검토 중': '추가 확인', '조치 중': '추가 확인', '미달': '추가 확인'}


def split_notes(items, source_lines):
    """The model often answers a kickoff with one '결정' note that cites every statement. In the company form
    each statement is its own line with its own 비고, so a note that cites form statements becomes one note
    per line, and the 비고 decides its kind:
      확정 · 완료 · 합격 · 보류 · 철회 -> 결정      검토 중 · 조치 중 · 미달 -> 추가 확인
      신규 · 변경 with no reply yet -> 논의          유지 -> 논의
      no 비고 but a due date (일정) -> 후속 조치     otherwise the model's own kind
    A 신규 / 변경 line takes the state of the reply under it (see threads). Notes on other lines pass through."""
    texts = {x['id']: str(x.get('text') or '') for x in source_lines or []}
    own = {}
    for i, t in texts.items():
        m = _REMARK.search(t)
        own[i] = m[1] if m else ''
    if not any(own.values()):
        return items
    order = list(texts)
    state = dict(own)
    for i in order:
        if own[i] not in ('신규', '변경'):
            continue
        for j in order[order.index(i) + 1:]:
            if own[j] in STATE:
                state[i] = own[j]; break
            if own[j] in KIND or not texts[j].startswith('['):
                break
    out = []; seen = set()
    for item in items:
        if not (isinstance(item, list) and len(item) == 2 and isinstance(item[1], list)
                and any(isinstance(i, str) and texts.get(i, '').startswith('[') for i in item[1])):
            out.append(item); continue
        kind, ids = item
        for i in ids:
            if i in seen or not isinstance(i, str) or i not in texts:
                continue
            seen.add(i)
            line_kind = _NOTE_KIND.get(state[i]) or ('논의' if own[i] in KIND else None)
            if line_kind is None and '일정 ' in (_ANY_TAIL.search(texts[i]) or [''])[0]:
                line_kind = '후속 조치'
            out.append([line_kind or kind, [i]])
    return out


def is_statement(text):
    """A line of the company form with its speaker tag or its (담당 · 일정 · 비고) tail."""
    text = str(text or '')
    return bool(_ANY_TAIL.search(text) or _ANY_SPEAKER.search(text))
