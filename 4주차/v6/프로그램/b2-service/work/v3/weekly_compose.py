"""주간보고 초안 조립: 사용자가 확인한 연결만으로 금주 실적, 차주 계획, 조치사항을 만든다.

규칙으로만 쓴다. 본문에 나오는 수치·이름·날짜는 메모 또는 연결된 회의록에 있는 것뿐이고,
새로 만드는 숫자는 '회의 N건' 같은 개수뿐이다. 줄마다 근거(evidence)를 붙여 화면과 Word에서 대조할 수 있게 한다.
"""
from datetime import date, timedelta

HEADINGS = {'done': '금주 실적', 'plan': '차주 계획', 'actions': '조치사항 (담당자 / 기한)'}
STATUS_LABEL = {'완료': '완료', '진행': '진행 중', '보류': '보류', '예정': '예정'}
STATE_PHRASE = {'확정': '확정', '요청': '고객 요청 접수(미확정)', '보류': '보류', '철회': '요청 철회', '검토': '검토 중'}
OTHER = '기타 업무'


def _day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def short_date(value, anchor):
    """11/23처럼 쓴다. 보고 기간과 연도가 다르면 연도를 남긴다."""
    day = _day(value)
    if not day:
        return str(value or '')
    return f'{day.month}/{day.day}' if day.year == anchor.year else day.isoformat()


def evidence_of(unit):
    return {'unit_id': unit['id'], 'kind': unit['kind'], 'kind_label': unit['kind_label'], 'meeting_id': unit['meeting_id'],
            'meeting_title': unit['meeting_title'], 'meeting_date': unit['meeting_date'], 'project_name': unit['project_name'],
            'revision': unit['revision'], 'lines': unit['lines'], 'quote': unit['quote'], 'reviewed': unit.get('reviewed', True)}


def change_text(unit, anchor):
    """변경 이력을 한 줄로: '압연 속도 120 m/min → 135 m/min 확정 (11/18 회의)'."""
    fmt = lambda v: short_date(v, anchor) if unit.get('category') == '납기' and _day(v) else v
    before, after = fmt(unit.get('before', '')), fmt(unit.get('after', ''))
    value = f'{before} → {after}' if before and before != after else after
    if value == unit['subject']:
        value = ''
    phrase = STATE_PHRASE.get(unit.get('state', ''), unit.get('state', ''))
    core = ' '.join(x for x in (unit['subject'], value, phrase) if x)
    note = '' if unit.get('reviewed', True) else ', 검토 전'
    return f"{core} ({short_date(unit['meeting_date'], anchor)} 회의{note})"


def action_row(unit, anchor):
    action = unit['action']
    return {'task': action['task'], 'owner': action['owner'] or '미정', 'due': short_date(action['due'], anchor) if action['due'] else '미정',
            'due_date': action['due'], 'project_name': unit['project_name'], 'evidence': [evidence_of(unit)]}


def compose(rows, links, extras, start, end):
    """초안을 만든다.

    rows: [{id,date,text,status}], links: {row_id: [단위,…]} 사용자가 확인한 연결,
    extras: 메모에 없지만 사용자가 넣기로 한 회의록 단위 목록.
    """
    start, end = _day(start), _day(end)
    if not start or not end or start > end:
        raise ValueError('보고 기간의 시작일과 종료일을 확인해 주세요.')
    next_start, next_end = end + timedelta(days=1), end + timedelta(days=9)
    groups, order = {}, []  # 프로젝트 이름 -> {'done': [...], 'plan': [...]}
    def bucket(name):
        name = name or OTHER
        if name not in groups:
            groups[name] = {'done': [], 'plan': []}; order.append(name)
        return groups[name]
    counter = [0]
    def item(text, source, evidence, level=0, row_id=''):
        counter[0] += 1
        return {'id': 'I' + str(counter[0]), 'type': 'item', 'text': text, 'level': level, 'source': source,
                'evidence': evidence, 'row_id': row_id}
    meetings, actions, action_done, shown_changes, planned_actions = {}, {}, set(), set(), set()
    for row in rows:
        units = [u for u in links.get(row['id'], [])]
        votes = {}
        for u in units:
            votes[u['project_name']] = votes.get(u['project_name'], 0) + 1
        project = max(votes, key=votes.get) if votes else ''
        target, status = bucket(project), row.get('status', '')
        row_day = _day(row.get('date'))
        evidence = [evidence_of(u) for u in units]
        source = 'linked' if units else 'memo'
        for u in units:
            day = _day(u['meeting_date'])
            if day and start <= day <= end:
                meetings.setdefault(u['meeting_id'], u)
            if u['kind'] == 'action':
                actions.setdefault(u['id'], u)
                due = _day(u['action']['due'])
                if status == '완료' and due and due <= end:
                    action_done.add(u['id'])  # 메모에서 끝났다고 한 일은 조치사항에 다시 올리지 않는다.
        future = bool(row_day and row_day > end)
        if status != '예정' and not future:
            label = STATUS_LABEL.get(status, '')
            target['done'].append(item(row['text'] + (' — ' + label if label else ''), source, evidence, 0, row['id']))
            for u in units:
                if u['kind'] == 'change' and u['id'] not in shown_changes:
                    shown_changes.add(u['id'])
                    target['done'].append(item(change_text(u, end), 'meeting', [evidence_of(u)], 1, row['id']))
                elif u['kind'] == 'decision':
                    target['done'].append(item(f"{u['text']} ({short_date(u['meeting_date'], end)} 회의)", 'meeting', [evidence_of(u)], 1, row['id']))
        if status in ('진행', '예정') or future:
            pending = [u for u in units if u['kind'] == 'action' and u['id'] not in action_done]
            dues = sorted({u['action']['due'] for u in pending if u['action']['due'] and _day(u['action']['due']) >= start})
            note = f" (회의록 기한 {short_date(dues[-1], end)})" if dues else (f" ({short_date(row['date'], end)})" if future else '')
            suffix = ' — 계속 진행' if status == '진행' else ''
            target['plan'].append(item(row['text'] + suffix + note, source, evidence, 0, row['id']))
            planned_actions.update(u['id'] for u in pending)
    for u in extras:
        target = bucket(u['project_name'])
        day = _day(u['meeting_date'])
        if u['kind'] == 'meeting':
            if day and start <= day <= end:
                meetings.setdefault(u['meeting_id'], u)
        elif u['kind'] == 'action':
            actions.setdefault(u['id'], u)
        elif u['kind'] == 'change':
            target_day = _day(u.get('after')) if u.get('category') == '납기' else None
            if target_day and next_start <= target_day <= next_end and u.get('state') == '확정' and not u.get('superseded'):
                target['plan'].append(item(f"{u['subject']} {short_date(u['after'], end)} (확정 일정)", 'meeting', [evidence_of(u)]))
            if u['id'] not in shown_changes and day and start <= day <= end:
                shown_changes.add(u['id'])
                target['done'].append(item(change_text(u, end), 'meeting', [evidence_of(u)]))
        elif u['kind'] == 'decision':
            target['done'].append(item(f"{u['text']} ({short_date(u['meeting_date'], end)} 회의)", 'meeting', [evidence_of(u)]))
    # 아직 끝나지 않은 조치 가운데 메모 줄에 이미 묶이지 않은 것은 차주 계획에도 올린다.
    table = []
    for uid, u in actions.items():
        if uid in action_done:
            continue
        action, due = u['action'], _day(u['action']['due'])
        if due and due < start and not action['undecided']:
            continue  # 기간 전에 기한이 지난 조치는 이번 보고의 조치사항으로 보지 않는다.
        table.append(action_row(u, end))
        upcoming = due and due > end or _day(action['start']) and due and due >= next_start
        if upcoming and uid not in planned_actions:
            who = f"{action['owner']}, " if action['owner'] else ''
            bucket(u['project_name'])['plan'].append(item(f"{action['task']} ({who}기한 {short_date(action['due'], end)})", 'meeting', [evidence_of(u)]))
    table.sort(key=lambda a: (a['due_date'] or '9999', a['project_name'], a['task']))
    sections = []
    for key in ('done', 'plan'):
        items = []
        if key == 'done' and meetings:
            held = sorted(meetings.values(), key=lambda u: (u['meeting_date'], u['meeting_title']))
            names = ', '.join(f"{short_date(u['meeting_date'], end)} {u['meeting_title']}" for u in held)
            items.append(item(f'회의 {len(held)}건 진행: {names}', 'meeting',
                              [{**evidence_of(u), 'unit_id': 'M:' + u['meeting_id'], 'kind': 'meeting', 'kind_label': '회의',
                                'lines': [], 'quote': u['meeting_title']} for u in held]))
        used = [name for name in order if groups[name][key]]
        used.sort(key=lambda name: name == OTHER)  # 연결되지 않은 메모는 맨 뒤에 모은다.
        for name in used:
            if not (len(used) == 1 and name == OTHER):
                items.append({'id': 'G' + str(len(items)) + key, 'type': 'group', 'text': name, 'level': 0, 'source': '', 'evidence': [], 'row_id': ''})
            items.extend(groups[name][key])
        sections.append({'key': key, 'heading': HEADINGS[key], 'items': items})
    stats = {'rows': len(rows), 'linked_rows': sum(1 for r in rows if links.get(r['id'])),
             'meetings': len(meetings), 'actions': len(table)}
    return {'sections': sections, 'actions': table, 'stats': stats}


def plain_text(draft):
    """초안을 글로 펼친다. Word 본문과 화면 복사에 같이 쓴다."""
    lines = []
    for number, section in enumerate(draft['sections'], 1):
        lines.append(f"{number}. {section['heading']}")
        for it in section['items']:
            if it['type'] == 'group':
                lines.append(f"  [{it['text']}]")
            else:
                lines.append(('    - ' if it['level'] else '  · ') + it['text'])
        if not section['items']:
            lines.append('  · 기재 내용 없음')
        lines.append('')
    lines.append(f"{len(draft['sections']) + 1}. {HEADINGS['actions']}")
    for a in draft['actions']:
        lines.append(f"  · {a['task']} / {a['owner']} / {a['due']}")
    if not draft['actions']:
        lines.append('  · 기재 내용 없음')
    return '\n'.join(lines)
