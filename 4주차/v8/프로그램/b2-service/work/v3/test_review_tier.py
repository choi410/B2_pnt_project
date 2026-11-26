"""Shadow-mode triage: which AI change records a person must check, and why."""
from work.v3.review_tier import assess, sections, is_spot_check

def test_spot_check_sample_is_stable_and_about_one_in_five():
    ids = [f'id-{i}' for i in range(2000)]
    picked = [is_spot_check(x) for x in ids]
    assert picked == [is_spot_check(x) for x in ids]
    assert 0.15 < sum(picked) / len(ids) < 0.25

LINES = [
    {'id': 'L012', 'text': '논의 내용'},
    {'id': 'L013', 'text': '게임플레이 서지안 선임: Q는 최대 4회 튕김. 1차안 증가량 50%.'},
    {'id': 'L015', 'text': '밸런스 문태경 책임: 증가량 35%로 낮추고 쿨타임 8~6초로 시작.'},
    {'id': 'L017', 'text': 'QA 윤채원 선임: 덫 3개 저장은 시야 장악이 과함. 2개면 충분.'},
    {'id': 'L019', 'text': '결정 사항'},
    {'id': 'L020', 'text': '1. Q: 최대 4회 튕김, 처치 시 다음 피해 35% 증가, 쿨타임 8~6초(1차안).'},
    {'id': 'L021', 'text': '2. E: 덫 최대 2개 저장, 지속 2분, 35% 둔화 후 2초 뒤 폭발.'},
    {'id': 'L025', 'text': '후속 조치'},
    {'id': 'L027', 'text': '2. QA 윤채원: 덫 2개 vs 3개 비교 테스트 / 2015-06-16'},
]

def item(title, after, before='', state='확정', evidence=('L020',), **extra):
    return {'title': title, 'category': '사양', 'before': before, 'after': after,
            'business_state': state, 'evidence': list(evidence), **extra}

def tier(e, history=()):
    return assess(e, LINES, list(history))

def test_sections_follow_header_lines():
    where, has_decision = sections(LINES)
    assert has_decision and where['L013'] == 'discussion' and where['L020'] == 'decision' and where['L027'] == 'followup'

def test_value_written_in_a_decision_line_is_an_auto_candidate():
    result = tier(item('E 덫 지속 시간', '2분', evidence=('L021',)))
    assert result['tier'] == 'auto' and result['reasons'] == []

def test_previous_value_only_proposed_in_this_meeting_needs_a_person():
    result = tier(item('Q 튕김 피해 증가량', '35% 증가', before='50%', evidence=('L013', 'L015', 'L020')))
    assert result['tier'] == 'human' and 'before_unverified' in {r['code'] for r in result['reasons']}

def test_decision_that_replaces_an_agreed_value_needs_a_person():
    # The previous value is right (agreed in an earlier meeting), but the agreed value changes.
    earlier = [item('E 둔화', '30% 둔화', evidence=('L021',))]
    result = tier(item('E 둔화', '35% 둔화', before='30% 둔화', evidence=('L021',)), earlier)
    assert result['tier'] == 'human' and {r['code'] for r in result['reasons']} == {'changes_agreed', 'before_history'}

def test_request_to_change_an_agreed_value_keeps_the_verified_previous_value_as_quick():
    earlier = [item('E 둔화', '30% 둔화', evidence=('L021',))]
    result = tier(item('E 둔화', '35% 둔화', before='30% 둔화', state='요청', evidence=('L021',)), earlier)
    assert {r['code'] for r in result['reasons']} == {'state', 'before_history'}

def test_previous_value_older_than_the_latest_agreement_is_flagged():
    earlier = [item('E 둔화', '30% 둔화', evidence=('L021',)), item('E 둔화', '35% 둔화', evidence=('L021',))]
    result = tier(item('E 둔화', '40% 둔화', before='30% 둔화', evidence=('L021',)), earlier)
    assert 'before_stale' in {r['code'] for r in result['reasons']}

def test_repeating_the_agreed_value_is_not_a_change():
    earlier = [item('E 둔화', '35% 둔화', evidence=('L021',))]
    codes = {r['code'] for r in tier(item('E 둔화', '35% 둔화', evidence=('L021',)), earlier)['reasons']}
    assert not codes & {'changes_agreed', 'conflict'}

def test_count_words_and_order_do_not_split_a_subject_but_skill_letters_do():
    from work.v3.review_tier import _same_subject
    assert _same_subject(item('덫 저장 수', '2개'), item('덫 저장 개수', '3개'))
    assert _same_subject(item('사거리 Q', '600'), item('Q 사거리', '650'))
    assert not _same_subject(item('Q 사거리', '600'), item('W 사거리', '650'))
    assert _same_subject(item('건조로 온도', '120 ℃'), item('건조로 온도 상한', '140 ℃'))
    assert _same_subject(item('건조 온도 상한', '140 ℃'), item('건조로 온도 상한', '120 ℃'))
    assert not _same_subject(item('온도 상한', '140 ℃'), item('온도 하한', '120 ℃'))
    assert not _same_subject(item('장탄 수', '4발'), item('장탄 수 및 튕김 횟수 모티프', '숫자 4'))

def test_prior_value_is_the_latest_agreement_with_its_meeting():
    from work.v3.review_tier import prior_value
    date = lambda e: e['meeting_date']
    history = [item('E 둔화', '30% 둔화', meeting_id='m1', meeting_title='킥오프', meeting_date='2015-03-10'),
               item('E 둔화', '40% 둔화', state='요청', meeting_id='m2', meeting_date='2015-03-20'),
               item('E 둔화', '35% 둔화', meeting_id='m3', meeting_title='체감 리뷰', meeting_date='2015-04-07')]
    found = prior_value(item('E 둔화', '25% 둔화'), history, date)
    assert (found['value'], found['meeting_title'], found['date'], found['changed']) == ('35% 둔화', '체감 리뷰', '2015-04-07', True)
    assert prior_value(item('E 둔화', '35%'), history, date)['changed'] is False
    assert prior_value(item('Q 쿨타임', '8초'), history, date) is None

def test_tentative_marker_on_a_shared_decision_line_applies_to_its_items():
    # "(1차안)" closes the whole Q decision line, so every value from it may still change.
    assert tier(item('Q 튕김 횟수', '최대 4회 튕김'))['tier'] == 'quick'

def test_tentative_wording_or_pending_test_is_a_quick_check():
    first_draft = tier(item('Q 쿨타임', '8~6초(1차안)'))
    tested_later = tier(item('E 덫 저장 수', '최대 2개 저장', evidence=('L021',)))
    assert first_draft['tier'] == 'quick' and tested_later['tier'] == 'quick'
    assert 'tentative' in {r['code'] for r in tested_later['reasons']}

def test_past_test_in_discussion_does_not_make_a_decided_value_tentative():
    lines = [{'id': 'L012', 'text': '논의 내용'},
             {'id': 'L014', 'text': 'QA: 사내 블라인드 테스트에서 4발 선호. 재장전 중 스킬 사용은 허용해야 함.'},
             {'id': 'L018', 'text': '결정 사항'},
             {'id': 'L019', 'text': '1. 장탄 4발, 재장전 2.5초 확정. 재장전 중 스킬 사용 가능.'}]
    result = assess(item('재장전 중 스킬 사용', '가능', evidence=('L014', 'L019')), lines, [])
    assert result['tier'] == 'auto' and result['reasons'] == []

def test_kept_value_next_to_a_hold_is_not_an_agreement():
    lines = [{'id': 'L011', 'text': '결정 사항'},
             {'id': 'L013', 'text': '포장 완충재 두께 30 mm 변경 요청은 보류했다. 기존 완충재 두께 20 mm를 유지한다.'}]
    result = assess(item('포장 완충재 두께', '20 mm', evidence=('L013',)), lines, [])
    assert result['tier'] == 'human' and 'state_conflict' in {r['code'] for r in result['reasons']}

def test_not_agreed_states_and_schedules_need_a_person():
    held = tier(item('덫 저장 수', '3개', before='2개', state='보류', evidence=('L017',)))
    schedule = tier({**item('출시일', '2016-02-01'), 'category': '납기'})
    assert held['tier'] == 'human' and schedule['tier'] == 'human'

def test_conflict_with_an_earlier_agreed_value_needs_a_person():
    earlier = [item('E 덫 지속 시간', '3분', evidence=('L021',))]
    result = tier(item('E 덫 지속 시간', '2분', evidence=('L021',)), earlier)
    assert result['tier'] == 'human' and 'conflict' in {r['code'] for r in result['reasons']}

def test_disagreeing_reask_needs_a_person():
    result = tier(item('E 덫 지속 시간', '2분', evidence=('L021',), reask={'state': '요청', 'task': False}))
    assert result['tier'] == 'human' and 'reask_state' in {r['code'] for r in result['reasons']}

def test_reworded_value_and_discussion_only_evidence_are_quick_checks():
    reworded = tier(item('E 덫 지속 시간', '두 시간', evidence=('L021',)))
    discussed = tier(item('Q 튕김 횟수', '최대 4회', evidence=('L013',)))
    assert reworded['tier'] == 'quick' and 'reworded' in {r['code'] for r in reworded['reasons']}
    assert discussed['tier'] == 'quick' and 'not_decision' in {r['code'] for r in discussed['reasons']}
