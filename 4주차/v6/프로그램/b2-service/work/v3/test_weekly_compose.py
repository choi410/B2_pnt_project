import re
import pytest
from work.v3 import weekly_compose as wc, weekly_match as wm
from work.v3.test_weekly_match import index, row

S, E = '2026-11-16', '2026-11-20'

def build(rows, actor='최인혁', extra=lambda e: e['selected']):
    matched, extras = wm.match_rows(rows, index(), S, E, actor)
    links = {r['id']: [c for c in r['candidates'] if c['selected']] for r in matched}
    return wc.compose(rows, links, [e for e in extras if extra(e)], S, E), links

def texts(draft, key):
    return [i['text'] for s in draft['sections'] if s['key'] == key for i in s['items']]

ROWS = [row('롤프레스 속도 135 재협의', '2026-11-18', '완료', 'R1'), row('구동부 배치도 개정', '2026-11-20', '진행', 'R2'),
        row('사내 안전 교육 참석', '2026-11-20', '완료', 'R3'), row('슬리터 검수 참관', '2026-11-27', '예정', 'R4')]

def test_sections_follow_the_agreed_layout():
    draft, _ = build(ROWS)
    assert [s['heading'] for s in draft['sections']] == ['금주 실적', '차주 계획']
    done, plan = texts(draft, 'done'), texts(draft, 'plan')
    assert done[0].startswith('회의 1건 진행: 11/18 롤프레스 변경 요청 재협의')
    assert '롤프레스 속도 135 재협의 — 완료' in done
    assert '압연 속도 120 m/min → 135 m/min 확정 (11/18 회의)' in done
    assert '구동부 배치도 개정 — 진행 중' in done and '사내 안전 교육 참석 — 완료' in done
    assert '슬리터 검수 참관 — 예정' not in done  # 예정 업무는 실적에 넣지 않는다.
    assert '구동부 배치도 개정 — 계속 진행 (회의록 기한 11/23)' in plan
    assert any(t.startswith('슬리터 검수 참관') for t in plan)
    assert done.index('기타 업무') > done.index('한빛셀 전극 롤프레스 1호기')  # 연결 안 된 메모는 뒤에 모은다.

def test_actions_table_uses_owner_and_due_from_minutes_only():
    draft, _ = build(ROWS)
    table = {a['task']: (a['owner'], a['due']) for a in draft['actions']}
    assert table['압연 속도 135 m/min을 반영한 구동부 배치도 개정'] == ('진효창', '11/23')
    assert table['수정한 공장 검수 체크리스트를 고객에게 공유'] == ('최인혁', '11/25')  # 내 담당 차주 조치는 기본 포함
    assert all(a['evidence'] and a['evidence'][0]['lines'] for a in draft['actions'])

def test_action_reported_done_in_memo_leaves_the_table():
    rows = [row('커버 통로 간섭 검토서 공유', '2026-11-20', '완료')]
    draft, links = build(rows, actor='')
    assert any(u['kind'] == 'action' for u in links['R1'])
    assert not any('간섭 검토서' in a['task'] for a in draft['actions'])
    rows[0]['status'] = '진행'
    draft, _ = build(rows, actor='')
    assert any('간섭 검토서' in a['task'] and a['owner'] == '최인혁' and a['due'] == '11/20' for a in draft['actions'])

def test_every_number_in_the_draft_comes_from_memo_or_evidence():
    draft, _ = build(ROWS, extra=lambda e: True)
    memo = ' '.join(r['text'] + ' ' + r['date'] for r in ROWS)
    def numbers(text):
        return set(re.findall(r'\d+', text))
    for section in draft['sections']:
        for it in section['items']:
            if it['type'] == 'group':
                continue
            allowed = numbers(memo) | {n for ev in it['evidence'] for n in numbers(ev['quote'] + ev['meeting_date'] + ev['meeting_title'])}
            if it['text'].startswith('회의 '):
                allowed.add(str(len(it['evidence'])))  # 유일하게 새로 만드는 숫자: 회의 건수
            assert numbers(it['text']) <= allowed, it['text']
    for a in draft['actions']:
        assert numbers(a['task'] + a['due']) <= numbers(a['evidence'][0]['quote'])

def test_unlinked_memo_only_draft_has_no_group_header_and_no_meeting_claim():
    draft, _ = build([row('사내 안전 교육 참석', '2026-11-20', '완료'), row('도면 검토', '', '진행', 'R2')], actor='')
    assert texts(draft, 'done') == ['사내 안전 교육 참석 — 완료', '도면 검토 — 진행 중']
    assert texts(draft, 'plan') == ['도면 검토 — 계속 진행']
    assert draft['actions'] == [] and draft['stats']['meetings'] == 0
    assert all(i['source'] == 'memo' and not i['evidence'] for s in draft['sections'] for i in s['items'])

def test_extras_add_schedule_open_items_and_decisions():
    draft, _ = build([], actor='', extra=lambda e: e['group'] in ('schedule', 'open', 'decided', 'meeting'))
    assert '공장 검수일 11/27 (확정 일정)' in texts(draft, 'plan')
    assert any(t.startswith('장비 납품일 2026-12-23 변경 요청은 보류했다.') for t in texts(draft, 'done'))
    assert texts(draft, 'done')[0].startswith('회의 2건 진행')
    assert any(a['owner'] == '미정' and a['due'] == '미정' for a in draft['actions'])

def test_unreviewed_change_is_marked_in_text():
    unit = {'id': 'C:x', 'kind': 'change', 'kind_label': '변경 이력', 'subject': '압연 속도', 'before': '120 m/min', 'after': '135 m/min',
            'state': '요청', 'category': '사양', 'meeting_date': '2026-11-13', 'reviewed': False}
    assert wc.change_text(unit, wc._day(E)) == '압연 속도 120 m/min → 135 m/min 고객 요청 접수(미확정) (11/13 회의, 검토 전)'

def test_plain_text_and_bad_period():
    draft, _ = build(ROWS)
    text = wc.plain_text(draft)
    assert text.startswith('1. 금주 실적') and '2. 차주 계획' in text and '3. 조치사항 (담당자 / 기한)' in text
    with pytest.raises(ValueError):
        wc.compose([], {}, [], E, S)
