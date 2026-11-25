"""Owner and due dates of follow-up actions, read from how the minutes write them."""
from work.v3.followups import parse_followup, fill_followup


def test_numbered_rows_with_a_role_word():
    assert parse_followup('1. QA 윤채원: 4발 버전 체감 테스트 시나리오 정리 / 2015-04-21') == {
        'owner_name': '윤채원', 'task': '4발 버전 체감 테스트 시나리오 정리', 'start': None, 'due': '2015-04-21'}
    assert parse_followup('2. 게임플레이 서지안: 패시브·스킬 5종 기획서 초안 / 2015-04-28')['owner_name'] == '서지안'
    assert parse_followup('1. 이준호: 고객 요구사항 목록 및 기본 배치도 초안 공유 / 2026-01-09')['due'] == '2026-01-09'


def test_sentences_with_due_range_and_single_day():
    assert parse_followup('배근우는 2026-11-20까지 코팅 헤드의 구매 사양을 확인한다.') == {
        'owner_name': '배근우', 'task': '코팅 헤드의 구매 사양을 확인한다', 'start': None, 'due': '2026-11-20'}
    ranged = parse_followup('배근우는 2026-11-19부터 2026-11-24까지 코팅 폭 680 mm에 맞는 헤드 구매 사양을 확정한다.')
    assert (ranged['start'], ranged['due']) == ('2026-11-19', '2026-11-24')
    assert parse_followup('김양일은 2026-11-23에 믹서 구매 사양 확인 회의를 진행한다.')['due'] == '2026-11-23'
    assert parse_followup('진효창이 2026-11-12까지 배치도를 개정한다.')['owner_name'] == '진효창'


def test_nothing_is_guessed_without_a_name_and_a_date():
    assert parse_followup('공격하지 않을 때 자동 재장전까지의 대기 시간은 기한 미정.') is None
    assert parse_followup('A24: 다음 회의는 2026년 11월 27일 본사 회의실에서 하기로 했음.') is None
    assert parse_followup('설치 자료 제출 담당자와 기한은 미정이다.') is None
    assert parse_followup('1. 고객 요구사항 목록 정리 / 2026-01-09') is None


def test_fill_links_members_keeps_others_by_name_and_respects_existing_values():
    members = {'배근우': 'team3'}
    linked = fill_followup({'kind': '업무', 'description': '배근우는 2026-11-20까지 사양을 확인한다.'}, members)
    assert (linked['owner_id'], linked['owner_name'], linked['due']) == ('team3', '배근우', '2026-11-20')
    outsider = fill_followup({'kind': '업무', 'description': '1. QA 윤채원: 시나리오 정리 / 2015-04-21'}, members)
    assert outsider.get('owner_id') is None and outsider['owner_name'] == '윤채원'
    edited = fill_followup({'kind': '업무', 'description': '배근우는 2026-11-20까지 확인한다.', 'owner_id': 'team1', 'due': '2026-12-01'}, members)
    assert (edited['owner_id'], edited['due']) == ('team1', '2026-12-01')
    check = {'kind': '확인사항', 'description': '배근우는 2026-11-20까지 확인한다.'}
    assert fill_followup(check, members) == check
