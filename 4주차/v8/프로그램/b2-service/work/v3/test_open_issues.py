"""Open issues in the minutes and what later meetings did with them (sentences from real minutes)."""
from work.v3.open_issues import attach, extract, keywords


def lines(*texts):
    return [{'id': f'L{i:03d}', 'text': t} for i, t in enumerate(texts, 1)]


def meeting(mid, date, *texts, project='P'):
    return {'id': mid, 'project_id': project, 'title': mid, 'date': date, 'created_at': date, 'lines': lines(*texts)}


def test_keywords_drop_particles_open_words_and_speaker_labels():
    assert keywords('고객 소재 내열 자료의 제출 담당자와 제출 기한은 미정이다.') == ['소재', '내열', '자료', '제출']
    assert keywords('QA 윤채원 선임: 자동 재장전까지의 대기 시간은 기한 미정.') == ['자동', '재장전', '대기', '시간']


def test_pending_section_items_and_undecided_sentences_become_issues():
    found = extract(lines('논의 내용',
                          '고객사 김민수는 조치 전후 사진도 함께 보자고 제안했다. 사진 촬영 범위와 제출 방식은 결정하지 않았다.',
                          '결정 사항',
                          '1. 점검 결과는 항목별 목록으로 공유한다.',
                          '추가 확인 사항',
                          '점검문과 배선덕트의 간섭 여부, 조치 전후 사진의 촬영 범위 및 제출 방식.'))
    texts = [x['text'] for x in found]
    # The decided line is not an issue; the first discussion sentence (a proposal) is not either.
    assert not any('항목별 목록' in t for t in texts)
    assert len(found) == 2
    photo = next(x for x in found if '사진' in x['text'])
    assert photo['text'].startswith('사진 촬영 범위') and set(photo['evidence']) == {'L002', 'L006'}
    assert any(x['text'] == '점검문과 배선덕트의 간섭 여부' for x in found)


def test_two_undecided_points_in_one_line_are_two_issues():
    found = extract(lines('추가 확인 사항', '공속 아이템 처리 방식(공격력 변환 여부)은 미정. 출시 목표 시점 미정.'))
    assert [x['text'] for x in found] == ['공속 아이템 처리 방식(공격력 변환 여부)은 미정.', '출시 목표 시점 미정.']


def test_a_sentence_broken_across_lines_is_joined_and_a_subjectless_tail_stays_with_it():
    found = extract(lines('결정 사항',
                          '문자 검증 카메라 추가는 고객 요청으로 기록하며 아직 적용 여부를 결정하지 않았다. 담당자와 검토 기한은',
                          '미정이다.'))
    assert len(found) == 1 and found[0]['text'].endswith('담당자와 검토 기한은 미정이다.')
    assert found[0]['evidence'] == ['L002', 'L003']


def test_header_block_and_agenda_are_not_issues():
    found = extract(lines('회의명: 코팅라인 소재 자료 확보 및 온도 조건 재협의', '참석자: 김양일, 진효창',
                          '회의 안건', '1. 점검문 위치 재검토', '결정 사항', '코팅 폭은 680 mm로 유지한다.'))
    assert found == []


def test_later_meeting_resolves_an_issue_and_names_the_sentence():
    first = meeting('m1', '2026-11-17', '결정 사항', '건조로 온도 상한 140 ℃ 요청은 보류했다. 기존 온도 상한 120 ℃를 유지한다.',
                    '후속 조치', '고객 소재 내열 자료의 제출 담당자와 제출 기한은 미정이다.')
    second = meeting('m2', '2026-11-19', '논의 내용', '고객이 소재 내열 자료를 제출했다. 자료상 허용 온도는 120 ℃이다.',
                     '결정 사항', '건조로 온도 상한을 기존 120 ℃에서 140 ℃로 높이려던 변경 요청을 철회했다.')
    attach([second, first], [])
    issues = {x['text'][:6]: x for x in first['open_issues']}
    assert issues['건조로 온도']['status'] == 'resolved' and '철회' in issues['건조로 온도']['by']['text']
    assert issues['고객 소재 ']['status'] == 'resolved' and issues['고객 소재 ']['by']['text'] == '고객이 소재 내열 자료를 제출했다.'
    assert issues['고객 소재 ']['by']['meeting_id'] == 'm2'
    assert second['open_issues'] == []


def test_still_undecided_later_is_discussed_and_a_follow_up_task_does_not_resolve():
    first = meeting('m1', '2026-01-05', '논의 내용', '안전커버와 점검문의 상세 위치는 이번 회의에서 확정하지 않았다.')
    second = meeting('m2', '2026-11-04', '회의 안건', '1. 코팅 설비 안전커버 점검문 위치 및 작업 접근성 검토',
                     '결정 사항', '2. 점검문 우측 이동안은 검토 중이며, 이번 회의에서 설계 변경을 승인하지 않는다.',
                     '후속 조치', '1. 이준호: 점검문 위치와 안전커버 간섭 검토 결과 공유 / 2026-11-06')
    attach([first, second], [])
    issue = first['open_issues'][0]
    assert issue['status'] == 'discussed' and issue['by']['meeting_id'] == 'm2'


def test_agreed_change_record_in_a_later_meeting_resolves_an_issue():
    first = meeting('m1', '2015-03-10', '추가 확인', '출시 목표 시점 미정.')
    second = meeting('m2', '2015-04-07', '논의 내용', '사업 측 의견 정리.')
    change = {'id': 'c1', 'meeting_id': 'm2', 'title': '정식 출시 목표일', 'after': '2016-02-01', 'business_state': '확정'}
    attach([first, second], [change])
    issue = first['open_issues'][0]
    assert issue['status'] == 'resolved' and issue['by']['change_id'] == 'c1'
    excluded = {**change, 'review_state': '제외'}
    first.pop('open_issues')
    attach([first, second], [excluded])
    assert first['open_issues'][0]['status'] == 'open'


def test_other_projects_and_earlier_meetings_do_not_resolve():
    first = meeting('m1', '2026-11-17', '추가 확인', '고객 소재 내열 자료의 제출 기한은 미정이다.')
    other = meeting('x', '2026-11-19', '논의 내용', '고객이 소재 내열 자료를 제출했다.', project='Q')
    earlier = meeting('m0', '2026-11-10', '논의 내용', '고객이 소재 내열 자료를 제출했다.')
    attach([first, other, earlier], [])
    assert first['open_issues'][0]['status'] == 'open'


def test_looking_back_at_something_once_undecided_is_not_an_open_issue_and_cell_labels_are_dropped():
    found = extract(lines('A5: 먼저 지난번에 검토중이던 운전 속도 건. 135 m/min으로 올리는 걸로 확정함.',
                          'A7: 진동 기준은 이번에 못 정하고 보류함.'))
    assert [x['text'] for x in found] == ['진동 기준은 이번에 못 정하고 보류함.']


def test_meeting_date_is_read_from_the_date_field():
    from work.v17.intake import parse_date, parse_text

    text = '회의일: 2026-11-10\n다음 회의는 2026년 12월 4일에 한다.'
    assert parse_date(parse_text(text)['meeting_date']) == '2026-11-10'
