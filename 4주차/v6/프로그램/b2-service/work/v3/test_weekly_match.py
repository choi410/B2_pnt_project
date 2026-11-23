from work.v3 import weekly_match as wm

PEOPLE = ['김양일', '진효창', '배근우', '최인혁']
PROJECTS = [{'id': 'P1', 'name': '한빛셀 전극 롤프레스 1호기'}, {'id': 'P2', 'name': '새롬에너지 전극 슬리터 3호기'}]
BODY1 = '''회의록
회의명: 롤프레스 변경 요청 재협의
회의일: 2026-11-18 | 참석: 김양일, 진효창
진행 현황
기구 설계와 전장 설계를 진행 중이다.
논의 내용
속도 검토 결과 구동부 용량을 조정하면 압연 속도 135 m/min을 적용할 수 있다.
결정 사항
압연 속도를 120 m/min에서 135 m/min으로 변경하기로 합의했다.
장비 납품일 2026-12-23 변경 요청은 보류했다. 현재 합의된 납품일은 2026-12-18이며 2026-12-23으로 변
경 확정된 상태가 아니다.
후속 조치
진효창은 2026-11-19부터 2026-11-23까지 압연 속도 135 m/min을 반영한 구동부 배치도를 개정한다.
최인혁은 2026-11-20까지 여닫이 커버의 통로 간섭 검토서를 김양일에게
공유한다.
고객 반입 계획의 추가 확인은 담당자와 기한을 정하지 못했다.'''
BODY2 = '''회의명: 슬리터 절단 폭 변경 및 검수 일정 조정
진행 현황
조립을 완료하고 공장 검수 준비를 진행 중이다.
결정 사항
공장 검수일을 2026-11-24에서 2026-11-27로 변경하기로 합의했다.
후속 조치
최인혁은 2026-11-25까지 수정한 공장 검수 체크리스트를 고객에게 공유한다.'''
BODY0 = '''회의명: 슬리터 절단 사양 및 검수 일정 협의
결정 사항
공장 검수일은 2026-11-24로 합의했다.'''

def doc(mid, pid, title, day, body):
    return {'meeting_id': mid, 'project_id': pid, 'revision': 1, 'title': title, 'date': day, 'body': body}

def event(eid, pid, mid, title, before, after, state, lines, category='사양', day='2026-11-18', review='확인됨'):
    return {'id': eid, 'project_id': pid, 'meeting_id': mid, 'title': title, 'before': before, 'after': after, 'business_state': state,
            'category': category, 'effective_date': day, 'evidence': lines, 'quotes': [], 'review_state': review}

def index():
    docs = [doc('m1', 'P1', '롤프레스 변경 요청 재협의', '2026-11-18', BODY1), doc('m2', 'P2', '슬리터 절단 폭 변경 및 검수 일정 조정', '2026-11-19', BODY2),
            doc('m0', 'P2', '슬리터 절단 사양 및 검수 일정 협의', '2026-11-12', BODY0)]
    events = [event('e1', 'P1', 'm1', '압연 속도', '120 m/min', '135 m/min', '확정', ['L009']),
              event('e2', 'P2', 'm2', '공장 검수일', '2026-11-24', '2026-11-27', '확정', ['L005'], '납기', '2026-11-19'),
              event('e0', 'P2', 'm0', '공장 검수일', '', '2026-11-24', '확정', ['L003'], '납기', '2026-11-12')]
    return wm.build_index(PROJECTS, docs, events, PEOPLE)

def row(text, day='', status='완료', rid='R1'):
    return {'id': rid, 'date': day, 'text': text, 'status': status, 'raw': text}

def test_wrapped_pdf_lines_are_rejoined_with_line_ids():
    found = {text: (kind, ids) for kind, text, ids in wm.sentences(BODY1)}
    assert found['현재 합의된 납품일은 2026-12-18이며 2026-12-23으로 변경 확정된 상태가 아니다.'] == ('decision', ['L010', 'L011'])
    assert found['최인혁은 2026-11-20까지 여닫이 커버의 통로 간섭 검토서를 김양일에게 공유한다.'] == ('action', ['L014', 'L015'])
    assert found['기구 설계와 전장 설계를 진행 중이다.'][0] == 'progress'

def test_action_owner_due_and_task_come_only_from_the_sentence():
    a = wm.parse_action('진효창은 2026-11-19부터 2026-11-23까지 압연 속도 135 m/min을 반영한 구동부 배치도를 개정한다.', PEOPLE)
    assert a == {'owner': '진효창', 'start': '2026-11-19', 'due': '2026-11-23', 'undecided': False, 'task': '압연 속도 135 m/min을 반영한 구동부 배치도 개정'}
    b = wm.parse_action('고객 반입 계획의 추가 확인은 담당자와 기한을 정하지 못했다.', PEOPLE)
    assert (b['owner'], b['due'], b['undecided']) == ('', '', True)
    c = wm.parse_action('홍길동은 다음 주까지 견적을 보낸다.', PEOPLE)
    assert (c['owner'], c['due']) == ('', '')  # 등록되지 않은 이름과 날짜 없는 기한은 채우지 않는다.

def test_memo_row_links_to_the_right_project_and_selects_direct_matches():
    rows, _ = wm.match_rows([row('롤프레스 속도 135 재협의', '2026-11-18')], index(), '2026-11-16', '2026-11-20')
    r = rows[0]
    assert r['match_state'] == 'linked' and r['project_id'] == 'P1'
    chosen = [c for c in r['candidates'] if c['selected']]
    assert chosen and all(c['project_id'] == 'P1' and c['confidence'] == 'high' for c in chosen)
    assert any(c['kind'] == 'change' and c['after'] == '135 m/min' for c in chosen)
    # 회의 이름만 맞은 문장(진행 현황 등)은 자동으로 고르지 않는다.
    assert not any(c['selected'] and c['text'].startswith('기구 설계') for c in r['candidates'])

def test_decision_sentence_covered_by_reviewed_change_is_not_duplicated():
    texts = [u['text'] for u in index()['units']]
    assert not any(t.startswith('압연 속도를 120 m/min에서') for t in texts)
    assert any(t.startswith('장비 납품일 2026-12-23 변경 요청은 보류') for t in texts)

def test_unrelated_and_generic_rows_are_not_linked():
    rows, _ = wm.match_rows([row('사내 안전 교육 참석'), row('도면 검토', rid='R2'), row('회의 진행 완료', rid='R3')], index(), '2026-11-16', '2026-11-20')
    assert [r['match_state'] for r in rows] == ['none', 'none', 'none']
    assert all(not r['project_id'] for r in rows)

def test_ambiguous_row_is_offered_but_not_auto_selected():
    rows, _ = wm.match_rows([row('검수 준비')], index(), '2026-11-16', '2026-11-20')
    assert rows[0]['match_state'] in ('check', 'linked')
    rows, _ = wm.match_rows([row('전극 설비 변경 대응')], index(), '2026-11-16', '2026-11-20')
    assert not any(c['selected'] for c in rows[0]['candidates'])

def test_extras_offer_next_week_items_and_skip_superseded_schedule():
    _, extras = wm.match_rows([], index(), '2026-11-16', '2026-11-20', '최인혁')
    by = {}
    for e in extras:
        by.setdefault(e['group'], []).append(e)
    assert [e['after'] for e in by['schedule']] == ['2026-11-27']  # 11/24는 뒤 회의에서 바뀐 지난 값
    nxt = {e['action']['task']: e for e in by['next']}
    assert '압연 속도 135 m/min을 반영한 구동부 배치도 개정' in nxt
    mine = nxt['수정한 공장 검수 체크리스트를 고객에게 공유']
    assert mine['mine'] and mine['selected']
    assert any(e['action']['undecided'] for e in by['open'])
    assert {e['meeting_id'] for e in by['meeting']} == {'m1', 'm2'}

def test_unreviewed_change_is_flagged_and_scored_lower():
    docs = [doc('m1', 'P1', '롤프레스 변경 요청 재협의', '2026-11-18', BODY1)]
    make = lambda review: wm.build_index(PROJECTS, docs, [event('e1', 'P1', 'm1', '압연 속도', '120 m/min', '135 m/min', '확정', ['L009'], review=review)], PEOPLE)
    pick = lambda idx: next(c for c in wm.match_rows([row('압연 속도 135 변경')], idx, '2026-11-16', '2026-11-20')[0][0]['candidates'] if c['kind'] == 'change')
    done, draft = pick(make('확인됨')), pick(make('검토 전'))
    assert done['reviewed'] and not draft['reviewed'] and draft['score'] < done['score']

def test_same_input_gives_same_result():
    a = wm.match_rows([row('구동부 배치도 개정', '2026-11-20', '진행')], index(), '2026-11-16', '2026-11-20')
    b = wm.match_rows([row('구동부 배치도 개정', '2026-11-20', '진행')], index(), '2026-11-16', '2026-11-20')
    assert a == b and a[0][0]['candidates'][0]['action']['owner'] == '진효창'
