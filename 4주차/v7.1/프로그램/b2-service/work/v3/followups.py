"""Read the owner and dates of a follow-up action from how minutes write it (rules, no AI).

Two common forms:
  "1. QA 윤채원: 4발 버전 체감 테스트 시나리오 정리 / 2015-04-21"   (numbered row)
  "배근우는 2026-11-19부터 2026-11-24까지 헤드 구매 사양을 확정한다."   (sentence)
Anything else returns None, and nothing is guessed. A named person who is not a project
member keeps the name only: the minutes say who, but that grants no assignment.
"""
import re
from datetime import date

_DATE = r'(?:20\d{2}\s*[-./년]\s*\d{1,2}\s*[-./월]\s*\d{1,2}\s*일?)'
_ROW = re.compile(r'^\s*(?:\d+[.)]\s*)?(?P<who>[^:：/]{2,24}?)\s*[:：]\s*(?P<task>.+?)\s*/\s*(?P<d1>' + _DATE + r')'
                  r'(?:\s*[~～\-]\s*(?P<d2>' + _DATE + r'))?\s*\.?\s*$')
_SENTENCE = re.compile(r'^\s*(?:\d+[.)]\s*)?(?P<name>[가-힣]{2,4})(?:은|는|이|가)\s+'
                       r'(?:(?P<start>' + _DATE + r')\s*부터\s+)?(?P<due>' + _DATE + r')\s*(?:까지|에)\s*(?P<task>.+?)\s*$')
_NAME = re.compile(r'^[가-힣]{2,4}$')


def iso(text):
    m = re.match(r'(20\d{2})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})', text or '')
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    except ValueError:
        return None


def parse_followup(text):
    """Return {'owner_name','task','start','due'} or None when the text does not state them."""
    text = ' '.join(str(text or '').split())
    m = _ROW.match(text)
    if m:
        words = m['who'].split()
        name = words[-1] if words else ''
        # "QA 윤채원", "게임플레이 서지안": a short role word may precede the name.
        if _NAME.match(name) and len(words) <= 3:
            d1, d2 = iso(m['d1']), iso(m['d2']) if m['d2'] else None
            if d1 and (d2 is None or d2 >= d1):
                return {'owner_name': name, 'task': m['task'].strip(), 'start': d1 if d2 else None, 'due': d2 or d1}
    m = _SENTENCE.match(text)
    if m:
        start, due = iso(m['start']) if m['start'] else None, iso(m['due'])
        if due and (start is None or start <= due):
            return {'owner_name': m['name'], 'task': m['task'].rstrip('.').strip(), 'start': start, 'due': due}
    return None


def fill_followup(item, members):
    """Fill owner_id/owner_name/start/due on a follow-up item when the minutes state them.
    members: {name: person_id} of the project. Existing values (set by a person) are kept."""
    if item.get('kind') not in (None, '업무'):
        return item
    found = parse_followup(item.get('description') or item.get('title') or item.get('text'))
    if not found:
        return item
    out = dict(item)
    if not out.get('owner_id') and not out.get('owner_name'):
        out['owner_name'] = found['owner_name']
        if found['owner_name'] in members:
            out['owner_id'] = members[found['owner_name']]
    if not out.get('due'):
        out['due'] = found['due']
        if found['start'] and not out.get('start'):
            out['start'] = found['start']
    out.setdefault('task', found['task'])
    return out
