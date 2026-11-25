"""AI 정리 shows the whole meeting, section by section (lines from real minutes)."""
from work.v3.outline import build


def meeting(*texts, **extra):
    return {'id': 'm1', 'lines': [{'id': f'L{i:03d}', 'text': t} for i, t in enumerate(texts, 1)], **extra}


KICKOFF = ('회의록', '회의명 | 신규 원거리 딜러 컨셉 킥오프', '참석자 | 게임플레이 한도윤(PM) · 밸런스 문태경',
           '회의 안건', '1. 신규 원거리 딜러 컨셉 후보 3안 비교',
           '논의 내용', "게임플레이 한도윤 수석: 후보는 A '공연하는 살인마', B '포병 저격수'.",
           '밸런스 문태경 책임: 공속 고정형은 아이템 체계와 충돌함.',
           '결정 사항', "1. A안(연출가 컨셉) 채택. 내부 코드명 'Virtuoso'.",
           '추가 확인 사항', '출시 목표 시점 미정.',
           '후속 조치', '1. 게임플레이 서지안: 장탄·재장전 기본 공격 프로토타입 v0.1 / 2015-03-24',
           '2. 내러티브 오세린: 컨셉 시놉시스·성격 설정 1차 / 2015-03-31')


def test_every_body_line_is_shown_under_its_section_even_when_the_model_chose_none():
    out = build(meeting(*KICKOFF))  # no stored summary at all
    assert out['mode'] == 'sections'
    assert [s['label'] for s in out['sections']] == ['회의 안건', '논의 내용', '결정 사항', '후속 조치', '추가 확인']
    assert out['coverage']['body'] == out['coverage']['shown'] == 7 and out['coverage']['left_out'] == []
    assert [x['text'][:3] for x in out['coverage']['header']] == ['회의록', '회의명', '참석자']


def test_speaker_is_split_from_a_discussion_line_and_list_numbers_are_dropped():
    sections = {s['kind']: s['items'] for s in build(meeting(*KICKOFF))['sections']}
    first = sections['discussion'][0]
    assert first['speaker'] == '게임플레이 한도윤 수석' and first['text'].startswith('후보는 A')
    assert sections['decision'][0]['text'].startswith('A안(연출가 컨셉) 채택')
    assert sections['agenda'][0]['text'] == '신규 원거리 딜러 컨셉 후보 3안 비교'


def test_each_follow_up_line_is_its_own_item_with_owner_and_due_date():
    items = {s['kind']: s['items'] for s in build(meeting(*KICKOFF))['sections']}['followup']
    assert [(x['owner_name'], x['due']) for x in items] == [('서지안', '2015-03-24'), ('오세린', '2015-03-31')]
    assert items[0]['evidence'] == ['L014']


def test_key_marks_decisions_follow_ups_and_what_the_model_picked_or_recorded():
    change = {'id': 'c1', 'title': '컨셉 방향', 'after': 'A안', 'review_state': '검토 전', 'evidence': ['L007', 'L010']}
    out = build(meeting(*KICKOFF, v3_bundle={'summary': [], 'decisions': [], 'candidates': []}), [change])
    sections = {s['kind']: s['items'] for s in out['sections']}
    assert [x['key'] for x in sections['discussion']] == [True, False]      # only the line a record cites
    assert sections['discussion'][0]['changes'] == [{'id': 'c1', 'title': '컨셉 방향', 'review_state': '검토 전'}]
    assert all(x['key'] for x in sections['decision'] + sections['followup'])
    assert not sections['agenda'][0]['key']
    excluded = build(meeting(*KICKOFF), [{**change, 'review_state': '제외'}])
    assert {s['kind']: s['items'] for s in excluded['sections']}['discussion'][0]['changes'] == []


def test_a_sentence_broken_across_lines_is_one_item_citing_both_lines():
    out = build(meeting('논의 내용', '고객은 코팅 폭 650 mm와 건조로 온도 상한 120 ℃를 요구했다. 온도 상한은 소재 손상을 방지하기 위한 운',
                        '전 조건이다.', '결정 사항', '코팅 폭은 650 mm로 합의했다.'))
    item = out['sections'][0]['items'][0]
    assert item['evidence'] == ['L002', 'L003'] and item['text'].endswith('운 전 조건이다.')


def test_progress_section_is_kept_apart_from_the_discussion():
    out = build(meeting('진행 현황', '주요 부품 구매를 진행 중이다.', '논의 내용', '고객은 코팅 폭 확대를 요청했다.'))
    assert [(s['label'], len(s['items'])) for s in out['sections']] == [('진행 현황', 1), ('논의 내용', 1)]


def test_a_person_s_edit_is_shown_instead_of_the_source_sentence():
    stored = {'summary': [], 'decisions': [{'text': 'A안 채택 (코드명 Virtuoso)', 'evidence': ['L010']}], 'candidates': []}
    edited = build(meeting(*KICKOFF, reviewed_bundle=stored, document_events=[{'action': 'AI 정리 수정'}]))
    decision = {s['kind']: s['items'] for s in edited['sections']}['decision'][0]
    assert decision['text'] == 'A안 채택 (코드명 Virtuoso)' and decision['edited']
    # Without an edit event the stored text is the model's wording, and the source sentence is shown.
    plain = build(meeting(*KICKOFF, reviewed_bundle=stored))
    assert not {s['kind']: s['items'] for s in plain['sections']}['decision'][0]['edited']
    # An edit made on the full view is stored by line id.
    direct = build(meeting(*KICKOFF, outline_edits={'L008': '공속 고정형은 아이템과 충돌 (변환 규칙 필요)'}))
    line = {s['kind']: s['items'] for s in direct['sections']}['discussion'][1]
    assert line['text'].startswith('공속 고정형은 아이템과 충돌') and line['edited']


def test_free_form_minutes_list_every_sentence_and_link_a_record_to_its_own_sentence():
    change = {'id': 'c1', 'title': '전면 커버 구조', 'after': '힌지형', 'review_state': '검토 전', 'evidence': ['L003']}
    out = build(meeting('시트: 줄글 회의록', 'A2: 회의 메모',
                        'A3: 속도 변경 자체는 아직 검토중이고 확정한 건 아님. 전면 커버 열리는 구조 얘기했고 힌지형으로 만드는 걸로 확정함.'),
                [change])
    assert out['mode'] == 'flat' and out['sections'][0]['label'] == '전체 내용'
    items = out['sections'][0]['items']
    assert [x['text'][:5] for x in items] == ['속도 변경', '전면 커버']
    assert [bool(x['changes']) for x in items] == [False, True] and [x['key'] for x in items] == [False, True]
    assert out['coverage']['left_out'] == [] and len(out['coverage']['header']) == 2
