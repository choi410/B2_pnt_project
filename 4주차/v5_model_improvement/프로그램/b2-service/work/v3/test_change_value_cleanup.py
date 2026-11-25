"""Change records keep only source-backed values, in any project domain."""
from work.v17.changes import normalize_extraction,drop_valueless

def run(items,source):
 lines=[{'id':'L1','text':source}]
 full=[{'topic_id':None,'category':'사양','before':'','business_state':'확정','evidence':['L1'],**x} for x in items]
 return drop_valueless(normalize_extraction({'lines':lines},full,[]))

def test_restated_new_value_is_not_a_previous_value():
 item,=run([{'title':'공속','before':'0.625','after':'0.625'}],'1. 공속 0.625 고정.')
 assert (item['before'],item['after'])==('','0.625')

def test_previous_value_absent_from_evidence_is_cleared():
 placeholder,invented=run([{'title':'공격 수치','before':'없음','after':'v0.95'},
                           {'title':'이동기','before':'돌진·점멸형 포함','after':'돌진·점멸형 미포함'}],
                          'PBE 투입 수치는 v0.95로 동결. 돌진·점멸형 이동기는 넣지 않음.')
 assert placeholder['before']=='' and invented['before']==''

def test_stated_previous_value_survives_formatting_differences():
 item,=run([{'title':'체력 재생','before':'5.5/5초','after':'6/5초'}],'1. 이동 속도 325 → 330, 체력 재생 5.5 → 6/5초.')
 assert item['before']=='5.5/5초'

def test_keep_decision_without_a_value_is_not_a_change():
 assert run([{'title':'공격 관련 수치','after':'PBE 버전 유지'}],'2. 공격 관련 수치(패시브·Q·W·E·R)는 PBE 버전 유지.')==[]

def test_work_items_and_status_reports_are_not_changes():
 source='채널링 중 조준 원뿔 표시 구현. 대사 녹음 완료. 출시 목표 시점 미정. 알려진 문제로 패치노트에 명시.'
 items=[{'title':'조준 원뿔','after':'채널링 중 조준 원뿔 표시 구현'},{'title':'대사','after':'녹음 완료'},
        {'title':'출시 시점','after':'출시 목표 시점 미정','business_state':'보류'},
        {'title':'장신구','after':'알려진 문제로 패치노트에 명시','business_state':'요청'}]
 assert run(items,source)==[]

def test_bare_requester_value_uses_the_request_title():
 item,=run([{'title':'문자 검증 카메라 추가','category':'요구사항','after':'고객 요청','business_state':'요청'}],
           '문자 검증 카메라 추가는 고객 요청으로 기록하며 아직 적용 여부를 결정하지 않았다.')
 assert item['after']=='문자 검증 카메라 추가'

def test_requested_addition_and_valued_changes_are_kept():
 kept=run([{'title':'문자 검증 카메라 추가','category':'요구사항','after':'문자 검증 카메라 추가','business_state':'요청'},
           {'title':'압연 속도','before':'120 m/min','after':'135 m/min'},
           {'title':'납품일','category':'납기','after':'2026-12-18 완료 예정','business_state':'요청'}],
          '고객은 문자 검증 카메라 추가를 요청했다. 압연 속도를 120 m/min에서 135 m/min으로 합의했다. 납품일 2026-12-18 완료 예정을 요청했다.')
 assert [x['title'] for x in kept]==['문자 검증 카메라 추가','압연 속도','납품일'] and kept[1]['before']=='120 m/min'


def test_summary_with_a_reworded_number_shows_the_source_sentence_instead_of_failing():
    # "이틀" -> "2일" used to fail the whole analysis ("근거 문장에 없는 숫자").
    from work.v17.demo_ai import normalize_notes
    lines = [{'id': 'L009', 'text': 'A9: 고객사에서 설치 후 교육을 하루에서 이틀로 늘려달라는 얘기가 있었음.'}]
    out = normalize_notes({'notes': [{'kind': '논의', 'text': '교육 기간 연장(1일에서 2일) 요청이 있었다.', 'evidence': ['L009']}]}, lines)
    assert out['summary'] == [{'text': '고객사에서 설치 후 교육을 하루에서 이틀로 늘려달라는 얘기가 있었음.', 'evidence': ['L009']}]


# Held or withdrawn requests: after = the value asked for, before = the value kept.
def held(item, *texts):
    lines = [{'id': f'L{i}', 'text': t} for i, t in enumerate(texts, 1)]
    full = {'topic_id': None, 'category': '사양', 'before': '', 'evidence': [l['id'] for l in lines], **item}
    return drop_valueless(normalize_extraction({'lines': lines}, [full], []))

def test_kept_value_written_as_the_request_is_swapped_back():
    item, = held({'title': '건조로 온도 상한', 'after': '120 ℃', 'business_state': '보류'},
                 '고객은 건조로 온도 상한을 120 ℃에서 140 ℃로 높여 달라고 요청했으나 소재 내열 자료가 없다.',
                 '건조로 온도 상한 140 ℃ 요청은 보류했다. 기존 온도 상한 120 ℃를 유지한다.')
    assert (item['before'], item['after'], item['business_state']) == ('120 ℃', '140 ℃', '보류')

def test_status_word_or_sentence_becomes_the_held_date_and_the_kept_date():
    text = ('장비 납품일 2026-12-23 변경 요청은 보류했다. 현재 합의된 납품일은 2026-12-18이며 2026-12-23으로 변', '경 확정된 상태가 아니다.')
    for after in ('보류', '장비 납품일 2026-12-23 변경 요청은 보류했다.'):
        item, = held({'title': '장비 납품일', 'category': '납기', 'before': '2026-12-23', 'after': after, 'business_state': '보류'}, *text)
        assert (item['before'], item['after']) == ('2026-12-18', '2026-12-23')

def test_withdrawn_method_change_keeps_the_named_methods():
    item, = held({'title': '점검 커버 방식', 'after': '철회', 'business_state': '철회'},
                 '측면 슬라이드 커버는 고객 현장의 통로와 간섭한다. 고객은 슬라이드 변경 요청을 철회하기로 했다.',
                 '점검 커버의 측면 슬라이드 변경 요청은 철회했다. 기존 여닫이 방식을 유지한다.')
    assert (item['before'], item['after'], item['business_state']) == ('여닫이 방식', '측면 슬라이드', '철회')

def test_other_wording_and_units_are_recovered():
    item, = held({'title': '공급 압력', 'after': '공급 압력 3.5 bar 변경 요청을 보류하고 기존 3.0 bar를 유지한다.', 'business_state': '보류'},
                 '공급 압력 3.5 bar 변경 요청을 보류하고 기존 3.0 bar를 유지한다.')
    assert (item['before'], item['after']) == ('3.0 bar', '3.5 bar')

def test_wording_the_repair_does_not_know_is_left_as_cited_not_guessed():
    # The hold is clear but no value is stated the way the repair reads it: nothing is invented,
    # the cited sentence is kept as before.
    item, = held({'title': '적재 하중', 'after': '보류', 'business_state': '보류'},
                 '적재 하중 상향 요청은 보류했다. 기존 하중 기준을 그대로 쓴다.')
    assert item['after'].startswith('적재 하중 상향 요청은 보류했다') and item['before'] == ''

def test_two_held_requests_in_the_same_sentence_are_not_guessed():
    item, = held({'title': '속도', 'after': '보류', 'business_state': '보류'},
                 '속도 140 m/min 요청은 보류했고 폭 700 mm 요청도 보류했다. 기존 속도 120 m/min를 유지한다.')
    assert item['after'] != '140 m/min' or item['before'] == '120 m/min'

def test_the_kept_value_is_not_recorded_as_a_new_agreement():
    # The record is the held 140 ℃ request; 120 ℃ kept as before is no change, and never 확정.
    assert held({'title': '건조로 온도 상한', 'after': '120 ℃', 'business_state': '확정'},
                '건조로 온도 상한 140 ℃ 요청은 보류했다. 기존 온도 상한 120 ℃를 유지한다.') == []
    item, = held({'title': '건조로 온도 상한', 'after': '140 ℃', 'business_state': '확정'},
                 '건조로 온도 상한을 120 ℃에서 140 ℃로 올리기로 확정했다.')
    assert (item['after'], item['business_state']) == ('140 ℃', '확정')

def test_held_value_written_twice_is_one_record():
    lines = [{'id': 'L1', 'text': '고객은 포장 완충재를 20 mm에서 30 mm로 두껍게 해 달라고 요청했다.'},
             {'id': 'L2', 'text': '포장 완충재 두께 30 mm 변경 요청은 보류했다. 기존 완충재 두께 20 mm를 유지한다.'}]
    base = {'topic_id': None, 'category': '사양', 'business_state': '보류', 'title': '포장 완충재 두께'}
    items = [{**base, 'before': '20 mm', 'after': '30 mm', 'evidence': ['L1', 'L2']},
             {**base, 'before': '20 mm', 'after': '포장 완충재 두께 30 mm 변경 요청은 보류했다. 기존 완충재 두께 20 mm를 유지한다.', 'evidence': ['L2']}]
    out = drop_valueless(normalize_extraction({'lines': lines}, items, []))
    assert [(x['before'], x['after']) for x in out] == [('20 mm', '30 mm')]

def test_words_in_place_of_the_kept_value_are_replaced():
    item, = held({'title': '측면 슬라이드 커버 변경 요청', 'before': '변경 요청', 'after': '측면 슬라이드', 'business_state': '철회'},
                 '측면 슬라이드 커버는 고객 현장의 통로와 간섭한다. 고객은 슬라이드 변경 요청을 철회하기로 했다.',
                 '점검 커버의 측면 슬라이드 변경 요청은 철회했다. 기존 여닫이 방식을 유지한다.')
    assert (item['before'], item['after']) == ('여닫이 방식', '측면 슬라이드')

def test_same_record_from_separate_lines_is_merged_with_its_evidence():
    lines = [{'id': 'L1', 'text': '고객은 포장 완충재를 20 mm에서 30 mm로 두껍게 해 달라고 요청했다.'},
             {'id': 'L2', 'text': '포장 완충재 두께 30 mm 변경 요청은 보류했다. 기존 완충재 두께 20 mm를 유지한다.'}]
    base = {'topic_id': None, 'category': '사양', 'business_state': '보류', 'title': '포장 완충재 두께', 'before': '20 mm', 'after': '30 mm'}
    out = drop_valueless(normalize_extraction({'lines': lines}, [{**base, 'after': '30 mm 요청', 'evidence': ['L1']}, {**base, 'evidence': ['L2']}], []))
    assert len(out) == 1 and out[0]['evidence'] == ['L1', 'L2'] and out[0]['after'] == '30 mm'

def test_different_subjects_with_the_same_value_stay_apart():
    lines = [{'id': 'L1', 'text': '코팅 폭과 건조 폭은 모두 650 mm로 합의했다.'}]
    base = {'topic_id': None, 'category': '사양', 'business_state': '확정', 'before': '', 'after': '650 mm', 'evidence': ['L1']}
    out = drop_valueless(normalize_extraction({'lines': lines}, [{**base, 'title': '코팅 폭'}, {**base, 'title': '건조 폭'}], []))
    assert [x['title'] for x in out] == ['코팅 폭', '건조 폭']


# Excel minutes with a status column (external set): words copied from the sheet, tables, dates.
def lines_of(*texts):
 return [{'id':f'L{i}','text':t} for i,t in enumerate(texts,1)]

def norm(items,*texts):
 full=[{'topic_id':None,'category':'사양','before':'','evidence':['L1'],**x} for x in items]
 return drop_valueless(normalize_extraction({'lines':lines_of(*texts)},full,[]))

def test_status_words_from_the_sheet_are_read_as_states_and_one_bad_item_does_not_fail_the_meeting():
 row='A14: 2 | B14: 마킹 속도 | D14: 분당 120개가 가능하다는 시뮬레이션 결과를 공유함. 실제 성능 시험 후 확정하기로 함. | G14: 검토중'
 items=norm([{'title':'마킹 속도','after':'분당 120개','business_state':'검토중'},
             {'title':'레이저 출력','after':'50 W','business_state':'완료됨'}],row)
 assert [(x['title'],x['business_state']) for x in items]==[('마킹 속도','요청')]

def test_under_review_read_as_a_hold_is_a_request_when_nothing_was_held():
 row='A16: SL-02 | B16: 절단 폭 | C16: - | D16: 150 mm | F16: 검토중 | H16: 고객이 절단 폭 150 mm를 요구함. 도면을 받은 뒤 최종 확정하기로 함.'
 item,=norm([{'title':'절단 폭','after':'150 mm','business_state':'보류'}],row)
 assert item['business_state']=='요청'
 held_row='납품일 12월 3일 변경 요청은 검토했으나 보류함.'
 item,=norm([{'title':'납품일','category':'납기','after':'12월 3일','business_state':'보류'}],held_row)
 assert item['business_state']=='보류'

def test_value_kept_after_a_withdrawn_request_is_not_an_agreement():
 row=('A15: CT-03 | B15: 건조로 구성 | C15: 3존(PNT 제안) | D15: 4존 | E15: 3존 유지 | F15: 철회 | H15: 4존을 적용하면 설비 길이가 '
      '레이아웃을 넘는다는 검토 결과를 공유함. 고객이 4존 요청을 철회하고 3존 열풍 건조를 유지하기로 함.')
 for after,state in (('3존','확정'),('3존 열풍 건조','철회'),('3존 유지','확정')):
  item,=norm([{'title':'건조로 구성','after':after,'business_state':state}],row)
  assert (item['before'],item['after'],item['business_state'])==(after.replace(' 유지',''),'4존','철회'),after
 # An agreement in the same evidence as another withdrawn request stays an agreement.
 item,=norm([{'title':'코팅 폭','after':'650 mm','business_state':'확정'}],'코팅 폭은 650 mm로 확정했다. 고객이 히터 변경 요청을 철회하고 기존 건조 온도를 유지했다.')
 assert item['business_state']=='확정'

def test_held_schedule_without_its_date_takes_the_one_date_of_its_hold_sentence():
 text=('흄은 배기 덕트에 연결하는 걸로 확정함. 연결 구경은 150 mm. 납품은 고객이 12월 첫째 주를 원하는데 광원 납기를 몰라서 '
       '납품일 정하는 건 보류함. 배근우가 10월 20일까지 광원 납기 확인하기로 함.')
 item,=norm([{'title':'납품 일정','category':'납기','after':'','business_state':'보류'}],text)
 assert item['after']=='12월 첫째 주'
 # No date, or two dates, in the hold sentence: nothing is guessed and the empty item is dropped.
 assert norm([{'title':'검수일','category':'납기','after':'','business_state':'보류'}],'고객 참관일을 확인한 뒤 검수일을 정하기로 하고 보류함.')==[]
 assert norm([{'title':'출하일','category':'납기','after':'','business_state':'보류'}],'출하일은 11월 말 또는 12월 초 중에서 정하기로 하고 보류함.')==[]

def test_progress_reports_follow_up_rows_and_next_meeting_agenda_are_not_changes():
 items=[{'title':'장비 납품일','category':'납기','after':'협의 중','business_state':'요청'},
        {'title':'부품 발주 일정','category':'납기','after':'11월 6일까지 잡는 중','business_state':'보류'},
        {'title':'납품일','category':'납기','after':'고객 반입 일정에 따라 결정','business_state':'요청'},
        {'title':'다이 견적','after':'배근우가 10월 28일에 받아 옴','business_state':'보류'}]
 assert norm(items,'장비 납품일은 협의 중. 부품 발주 일정은 11월 6일까지 잡는 중. 납품일은 고객 반입 일정에 따라 결정. 다이 견적은 배근우가 10월 28일에 받아 옴.')==[]
 sheet=('A19: 번호 | B19: 조치 내용 | E19: 담당자 | F19: 기한 | G19: 진행 상태',
        'A20: 1 | B20: 주요 부품 발주 일정 확정 | E20: 배근우 | F20: 2026-11-06T00:00:00 | G20: 미착수',
        'A27: 차기 회의 | B27: 2026-11-18T00:00:00',
        'A28: 주요 안건 | B28: 코팅 폭, 건조로 온도 상한 확정',
        'A13: 1 | B13: 코팅 폭 | D13: 코팅 폭을 650 mm로 확정함. | G13: 확정')
 full=[{'topic_id':None,'category':'납기','before':'','business_state':'요청','title':'주요 부품 발주 일정','after':'2026-11-06','evidence':['L2']},
       {'topic_id':None,'category':'사양','before':'','business_state':'요청','title':'운전 사양','after':'코팅 폭, 건조로 온도 상한','evidence':['L4']},
       {'topic_id':None,'category':'사양','before':'','business_state':'확정','title':'코팅 폭','after':'650 mm','evidence':['L5']}]
 kept=normalize_extraction({'lines':lines_of(*sheet)},full,[])
 assert [x['title'] for x in kept]==['코팅 폭']

def test_value_with_a_progress_note_in_brackets_and_a_condition_are_kept_without_a_restated_prior():
 item,=norm([{'title':'마킹 속도','before':'분당 120개','after':'분당 120개 (실제 성능 시험 보고 확정 전까지 검토 중)','business_state':'요청'}],
            '마킹 속도는 분당 120개를 해 달라고 함. 실제 성능 시험 보고 확정 전까지 검토 중.')
 assert item['before']=='' and item['after'].startswith('분당 120개')
 item,=norm([{'title':'운전 속도','before':'120 m/min','after':'120 m/min → 135 m/min','business_state':'요청'}],'운전 속도를 120 m/min에서 135 m/min으로 요청함.')
 assert item['before']=='120 m/min'

def test_a_request_line_read_as_a_hold_stays_with_the_hold_stated_on_another_line():
 lines=lines_of('고객은 포장 완충재를 20 mm에서 30 mm로 두껍게 해 달라고 요청했다. 두께 변경은 추가 검토가 필요하다.',
                '포장 완충재 두께 30 mm 변경 요청은 보류했다. 기존 완충재 두께 20 mm를 유지한다.')
 full=[{'topic_id':None,'category':'사양','title':'포장 완충재 두께','before':'20 mm','after':'30 mm 요청','business_state':'보류','evidence':['L1']},
       {'topic_id':None,'category':'사양','title':'포장 완충재 두께','before':'20 mm','after':'30 mm','business_state':'보류','evidence':['L2']}]
 item,=normalize_extraction({'lines':lines},full,[])
 assert (item['before'],item['business_state'],item['evidence'])==('20 mm','보류',['L1','L2'])


# Consecutive meetings (series set): rejections, restated values, work items, misplaced values, delivery names.
def test_a_rejected_request_keeping_the_old_value_is_a_withdrawal_not_an_agreement():
 text=('얼라인은 ±0.2 mm 맞추려면 비전 카메라 2대 더 달고 1,800만 원쯤 올라가서 고객 예산 넘는다고, 우리가 반려하고 ±0.3 mm 유지. '
       '장력은 지난번 정한 1.5 N으로 이미 도면 반영 끝, 더 얘기 없음.')
 item,=norm([{'title':'정렬 정밀도','after':'±0.3 mm 유지','business_state':'확정'}],text)
 assert (item['before'],item['after'],item['business_state'])==('±0.3 mm','±0.2 mm','철회')
 row=('A16: WD-06 | B16: 제전기 수량 | C16: 2개소 | D16: 4개소 | E16: 2개소 유지 | F16: 반려 | H16: 4개소를 설치하면 안전 커버를 '
      '새로 설계해야 해 납기를 맞출 수 없음. PNT가 요청을 반려하고 2개소 유지로 정리함.')
 for before,after,state in (('','2개소','확정'),('4개소','2개소','보류'),('2개소','4개소','보류')):
  item,=norm([{'title':'제전기 수량','before':before,'after':after,'business_state':state}],row)
  assert (item['before'],item['after'],item['business_state'])==('2개소','4개소','철회'),(before,after,state)
 item,=norm([{'title':'매거진 수','before':'6개','after':'4개','business_state':'철회'}],
            '적층 매수를 양극 36매로 늘리기로 확정함. 대신 매거진 6개 요청은 고객이 철회해 4개 유지로 정리함.')
 assert (item['before'],item['after'],item['business_state'])==('4개','6개','철회')

def test_a_value_agreed_before_and_mentioned_again_is_not_a_new_change():
 text=('제전기는 4개소면 납기를 못 맞춤, 그래서 우리가 반려하고 2개소 유지. 라인 속도는 지난번 합의한 130 m/min 유지, 모터 재확인도 1/19에 끝남. '
       '출하 일정은 2027-03-05 그대로고 고객도 따로 얘기 없었음. 장력은 1.5 N으로 설계 반영 완료, 추가 요청 없음.')
 items=[{'title':'라인 속도','after':'130 m/min','business_state':'확정'},{'title':'출하 일정','category':'납기','after':'2027-03-05','business_state':'확정'},
        {'title':'분리막 장력','after':'1.5 N','business_state':'확정'}]
 assert norm(items,text)==[]
 # A new value in the same paragraph, or a change away from the earlier value, stays.
 kept=norm([{'title':'라인 속도','before':'분당 135 m','after':'분당 130 m','business_state':'확정'}],
           '지난 회의에서 정한 분당 135 m를 분당 130 m로 낮춰 달라고 해서 그렇게 합의함. 장력 범위는 처음 정한 20~80 N 그대로.')
 assert [x['after'] for x in kept]==['분당 130 m']

def test_work_items_with_deadlines_and_leftover_words_are_not_changes():
 text='권취 축 가공 발주는 1/15까지 진행. FAT 체크리스트 42항목은 2/22까지 고객에게 보냄. 금형 견적은 12/22까지 받기로 함. 초경은 안 하겠다고 해서 요청 철회.'
 items=[{'title':'권취 축 가공 발주','category':'납기','after':'1/15까지 진행','business_state':'요청'},
        {'title':'FAT 체크리스트','after':'42항목','business_state':'요청'},
        {'title':'금형 견적 및 납기','category':'납기','after':'12/22까지','business_state':'요청'},
        {'title':'금형 재질','after':'해서','business_state':'철회'}]
 assert norm(items,text)==[]

def test_values_written_in_the_wrong_place_are_moved():
 item,=norm([{'title':'출하 일정','category':'납기','after':'3/10 → 3/17','business_state':'확정'}],'출하 일정은 3/10에서 3/17로 미루는 걸로 확정함.')
 assert (item['before'],item['after'])==('3/10','3/17')
 row='A14: 2 | B14: 스태킹 속도 | D14: 고객 요청 0.8 s/매는 분리막 정렬이 흔들림. 보완품 시험이 끝날 때까지 결정을 보류함. | G14: 보류'
 item,=norm([{'title':'스태킹 속도','before':'0.8 s/매 고객 요청','after':'보완품 시험이 끝날 때까지 결정을 보류함.','business_state':'보류'}],row)
 assert (item['before'],item['after'],item['business_state'])==('','0.8 s/매','보류')
 item,=norm([{'title':'장비 납품일','category':'납기','before':'-','after':'2027.03.05','business_state':'확정'}],'A16: NT-04 | B16: 장비 납품일 | C16: - | D16: 2027.03.05 | F16: 합의')
 assert item['before']==''

def test_a_request_held_later_in_its_own_clause_is_a_hold():
 text='장력 범위를 20~80 N에서 10~80 N으로 하한을 낮춰 달라고 함, 로드셀 공급사 답을 아직 못 들어서 보류, 신예린이 2/9까지 확인.'
 item,=norm([{'title':'장력 범위','before':'20~80 N','after':'10~80 N','business_state':'요청'}],text)
 assert item['business_state']=='보류'
 # A hold of another subject later in the sentence does not hold this request.
 item,=norm([{'title':'작업 폭','before':'300 mm','after':'320 mm','business_state':'요청'}],'작업 폭을 300 mm에서 320 mm로 올려 달라고 함, 속도 85 spm 요청은 보류.')
 assert item['business_state']=='요청'

def test_delivery_dates_under_other_names_are_suggested_as_the_same_subject():
 from work.v17.changes import suggest_topic
 topics=[{'id':'t1','title':'장비 납품일'},{'id':'t2','title':'금형 납기'},{'id':'t3','title':'출하일'}]
 assert suggest_topic('출하 일정',topics)['id'] in ('t1','t3') and suggest_topic('납기',[topics[0]])['id']=='t1'
 assert suggest_topic('출하일',topics)['id']=='t3'                      # the exact name still wins
 assert suggest_topic('금형 도면',[topics[0]]) is None

def test_a_neighbouring_line_cited_by_mistake_is_replaced_by_the_line_with_the_value():
 sheet=('A15: 3 | B15: 안전 펜스 높이 | D15: 고객이 안전 펜스 높이를 1.8 m에서 2.0 m로 올려 달라고 요청함. 출하 전에 반영하기로 확정함. | G15: 확정',
        'A18: 02  후속 조치')
 full=[{'topic_id':None,'category':'사양','title':'안전 펜스 높이','before':'1.8 m','after':'2.0 m','business_state':'확정','evidence':['L2']}]
 item,=normalize_extraction({'lines':lines_of(*sheet)},full,[])
 assert item['evidence']==['L1'] and item['before']=='1.8 m'

def test_a_year_added_to_a_date_is_not_a_number_the_minutes_must_state():
 from work.v17.changes import value_numbers
 need,stated=value_numbers('2027-03-12','PNT가 출하 일정을 2/26에서 3/12로 조정하자고 제안함.')
 assert need<=stated
 need,stated=value_numbers('2026-12-04','장비 납품일을 2026년 12월 4일로 확정함.')
 assert need<=stated
 need,stated=value_numbers('2027-03-15','출하 일정을 3/12로 조정하자고 제안함.')
 assert not need<=stated


# A long internal review paragraph (rollpress set): judged on the sentence and clause of the value.
ROLL_DRIVE=('A10: 구동부 적용 속도는 기작성 계산자료에 기재된 120m/min을 기준으로 적정성을 검토하였으며, 서보 직결 방식을 고객 제안자료의 우선 검토안에 반영하기로 하였습니다. '
            '이에 따라 설명자료 작성에 적용하는 검토 기준 속도는 100m/min으로 하되, 기존 자료의 120m/min 기재 내용을 일괄 삭제하는 대신 계산 참고값으로 구분하여 남기기로 하였습니다. '
            '감속기 적용안은 비교 대상에서 제외하지 않으며, 검토 결과를 확인하기 전까지 대안으로 유지합니다. '
            '모터 용량과 관련해서는 11kW 표기가 포함된 검토표와 기존 7.5kW 자료가 함께 확인되었으나, 전자의 수치 역시 선정 완료값이 아닌 예시값으로 확인되어 용량 선정 완료로 연결하지 않았습니다.')
ROLL_CHILLER=('A14: 칠러는 기존 검토자료상 1,800만원 및 납기 8주로 기재되어 있었으나, 회의 중 확인한 수정 견적에는 1,650만원, 부가가치세 별도 조건이 적용되어 있었습니다. '
              '납기 역시 발주 및 도면 승인 완료 후 10주로 제시되어 있어, 기존 금액과 납기를 조합하여 적용하지 않도록 검토자료를 수정할 필요가 있습니다. '
              '수정 견적의 유효기간은 기존 견적의 조건을 그대로 적용할 수 있는지 확인되지 않았습니다.')

def test_a_kept_alternative_elsewhere_in_the_paragraph_does_not_hide_a_change():
 kept=norm([{'title':'칠러 금액','before':'1,800만원','after':'1,650만원','business_state':'요청'},
            {'title':'칠러 납기','before':'8주','after':'10주','business_state':'요청'}],ROLL_CHILLER)
 assert [(x['before'],x['after']) for x in kept]==[('1,800만원','1,650만원'),('8주','10주')]
 item,=norm([{'title':'검토 기준 속도','before':'120 m/min','after':'100 m/min','business_state':'요청'}],ROLL_DRIVE)
 assert (item['before'],item['after'])==('120 m/min','100 m/min')
 # One sentence that says the value is kept is still not a change.
 assert norm([{'title':'코팅 폭','after':'650 mm','business_state':'확정'}],'코팅 폭은 기존 650 mm를 그대로 유지한다.')==[]

def test_an_example_or_reference_value_is_not_a_requirement():
 items=[{'title':'모터 용량','before':'7.5kW','after':'11kW','business_state':'요청'},
        {'title':'압연 속도','after':'120 m/min','business_state':'확정'}]
 assert norm(items,ROLL_DRIVE)==[]
 # A hold stays: the minutes may hold a value they call a draft.
 item,=norm([{'title':'두께 관리범위','after':'±3μm','business_state':'보류'}],
            '내부 시운전 비교를 위한 ±3μm 관리범위 적용안도 검토되었으나, 측정 조건이 정리되지 않아 채택은 보류하였습니다.')
 assert item['business_state']=='보류'

def test_correcting_how_a_value_is_written_is_not_a_change():
 text=('제품 두께 편차는 ±2μm를 내부 목표 초안으로 유지하면서 조건을 정리하기로 하였습니다. '
       '다만, 본 목표는 최종 보증사양이 아니므로, 관련 자료에 혼재된 ±2mm 표기는 단위 오류로 수정해야 합니다.')
 assert norm([{'title':'제품 두께 편차','before':'±2mm','after':'±2μm','business_state':'보류'}],text)==[]

def test_a_short_no_change_sentence_after_the_value_still_counts():
 row='A16: 4 | B16: 노칭 속도 | D16: 노칭 속도는 지난 회의에서 정한 분당 75회 기준으로 금형 설계 진행 중. 변경 없음.'
 assert norm([{'title':'노칭 속도','after':'분당 75회','business_state':'확정'}],row)==[]


# Written-example format (02): previous values next to the new one, the minutes' own dates, cells.
def test_the_previous_value_stated_next_to_the_new_one_is_filled():
 cases=[('장비 납품일','3월 둘째 주','보류','고객 기초 공사가 늦어질 수 있어 2월 24일 출하를 3월 둘째 주로 옮겨 달라고 함. 정하기로 하고 보류함.','2월 24일'),
        ('출하 일정','3월 초','보류','고객 공사가 늦어져 2/19 출하를 3월 초로 미뤄 달라는 요청이 있음. 날짜는 정하지 않고 보류함.','2/19'),
        ('얼라인 정밀도','±0.25 mm','확정','고객이 예전 요청 ±0.2 mm 대신 ±0.25 mm로 다시 요청함. 추가 비용 없이 ±0.3 mm에서 ±0.25 mm로 확정함.','±0.3 mm'),
        ('라인 속도','130 m/min','확정','고객이 지난 회의에서 정한 분당 135 m를 분당 130 m로 낮춰 달라고 요청했고 그대로 합의함.','분당 135 m')]
 for title,after,state,text,before in cases:
  item,=norm([{'title':title,'category':'납기' if '일' in title or '일정' in title else '사양','after':after,'business_state':state}],text)
  assert item['before']==before,(title,item['before'])
 # A first value, or two candidates, is left empty.
 item,=norm([{'title':'코팅 폭','after':'650 mm','business_state':'확정'}],'코팅 폭을 650 mm로 확정함.')
 assert item['before']==''

def test_a_year_the_minutes_do_not_state_is_not_added_to_a_date():
 item,=norm([{'title':'납품일','category':'납기','after':'2026-02-19','business_state':'확정'}],
            '금형 업체가 1월 22일 입고로 회신해 고객 희망인 2월 셋째 주 안에서 납품일을 2월 19일로 확정함.')
 assert item['after']=='2월 19일'
 item,=norm([{'title':'출하 일정','category':'납기','after':'2027-03-12','business_state':'요청'}],'PNT가 출하 일정을 2/26에서 3/12로 조정하자고 제안함.')
 assert (item['before'],item['after'])==('2/26','3/12')
 item,=norm([{'title':'장비 납품일','category':'납기','after':'2026-12-04','business_state':'확정'}],'장비 납품일을 2026년 12월 4일로 확정함.')
 assert item['after']=='2026-12-04'

def test_a_table_row_in_the_value_of_a_held_request_gives_way_to_the_value():
 row='A14: 2 | B14: 스태킹 속도 | D14: 고객 요청 0.8 s/매는 폴딩 시험에서 분리막 정렬이 흔들림. 보완품 시험이 끝날 때까지 결정을 보류함. | G14: 보류'
 item,=norm([{'title':'스태킹 속도','before':'0.8 s/매','after':'2 | B14: 스태킹 속도 | D14: 고객 요청 0.8 s/매는 폴딩 시험에서 분리막 정렬이 흔들림.','business_state':'보류'}],row)
 assert (item['before'],item['after'])==('','0.8 s/매')

def test_a_status_word_is_never_replaced_by_a_header_line():
 sheet=('A3: 가상 회의 메모입니다. 아래 회의 내용과 인물은 실제 기록이 아닙니다.',)
 full=[{'topic_id':None,'category':'납기','title':'납품 일정','before':'','after':'요청','business_state':'요청','evidence':['L1']}]
 assert drop_valueless(normalize_extraction({'lines':lines_of(*sheet)},full,[]))==[]

def test_a_short_no_new_request_sentence_after_the_value_marks_a_restatement():
 row='A17: 5 | B17: 분리막 장력 | D17: 1.5 N으로 설계 반영 완료. 추가 요청 없음.'
 assert norm([{'title':'분리막 장력','after':'1.5 N','business_state':'확정'}],row)==[]


# Sentence-level input of free-form minutes, and what it surfaced.
def test_a_kept_value_written_with_an_extra_leading_word_is_still_not_an_agreement():
 text='백지민 선임이 전용 집진기 별도 공급 해 달라고 했는데 견적 기본안은 공장 중앙 집진 연결이고 둘 자리도 없어서 우리가 반려함, 중앙 집진 연결 유지로 정리했고 류태경이 실측하기로.'
 item,=norm([{'title':'전용 집진기 공급','after':'공장 중앙 집진 연결','business_state':'확정'}],text)
 assert item['business_state']=='철회'

def test_internal_hand_in_times_are_not_changes_but_a_moved_deadline_is():
 text=('제어 인터페이스 페이지는 정우진이 작성하여 같은 날 오후 1시까지 전달하며, 설치 공간 스케치는 배근우가 오전 11시까지 제출하는 것으로 협의하였습니다. '
       '김양일은 요청 메일을 내일 정오까지 발송합니다. 고객 설명자료 전체 초안은 당초 기재한 금요일 오후 3시에서 고객회의 당일 오전 9시 제출로 변경하였습니다.')
 items=[{'title':'제어 인터페이스 페이지 제출 일시','category':'납기','after':'오후 1시','business_state':'확정'},
        {'title':'설치 공간 스케치 제출 일시','category':'납기','after':'오전 11시','business_state':'확정'},
        {'title':'칠러 사양 요청 메일 발송 일시','category':'납기','after':'내일 정오','business_state':'확정'},
        {'title':'고객 설명자료 제출 일시','category':'납기','before':'금요일 오후 3시','after':'고객회의 당일 오전 9시','business_state':'요청'}]
 assert [x['title'] for x in norm(items,text)]==['고객 설명자료 제출 일시']

def test_free_form_paragraphs_are_given_as_sentences_and_cited_by_their_lines():
 from work.v3.fast_ai import _sentence_lines,_cite_lines
 memo=lines_of('시트: 줄글 회의록','A5: 납품은 12월 첫째 주를 원하는데 납품일 정하는 건 보류함. 연결 구경은 150 mm로 확정함.')
 lines,back=_sentence_lines(memo)
 assert [x['id'] for x in lines]==['L2.0','L2.1'] and back=={'L2.0':'L2','L2.1':'L2'}
 out=_cite_lines({'items':[{'evidence':['L2.1','L2.0']}],'summary':[{'evidence':['L2.0']}]},back)
 assert out=={'items':[{'evidence':['L2']}],'summary':[{'evidence':['L2']}]}
 sheet=lines_of('A11: 01  논의 및 결정 사항','A12: 번호 | 안건 | 논의 내용 | 결정 상태','A13: 1 | 코팅 폭 | 650 mm로 확정함. 도면에 반영함. | 확정')
 assert _sentence_lines(sheet)==(sheet,None)

def test_sentence_values_bare_words_and_restated_deadlines_of_a_long_review_paragraph():
 hold='내부 시운전 비교를 위한 ±3μm 관리범위 적용안도 함께 검토되었으나, 측정 조건이 정리되지 않은 상태에서 해당 범위를 채택하는 것은 보류하였습니다.'
 item,=norm([{'title':'측정 범위 ±3μm','before':'적용안','after':hold,'business_state':'보류'}],hold)
 assert (item['before'],item['after'])==('','±3μm')
 assert norm([{'title':'감속기 적용안','after':'제외','business_state':'보류'}],'감속기 적용안은 비교 대상에서 제외되는 것으로 처리하지 않으며, 대안으로 유지합니다.')==[]
 assert norm([{'title':'칠러 사양 요청 메일 발송 일시','category':'납기','before':'내일 정오','after':'10월 29일 12시','business_state':'확정'}],
             '금요일은 10월 30일, 칠러 사양 요청 메일 발송 기한인 내일 정오는 10월 29일 12시를 의미합니다.')==[]


# Records the model found but wrote in the wrong cells (they used to be dropped as empty).
def test_a_withdrawn_request_written_in_the_previous_value_cell_is_kept():
 row='A17: ST-06 | B17: 매거진 수량 | C17: 4개 | D17: 6개 | E17: 4개 유지 | F17: 철회 | H17: 매거진 6개를 넣으면 설비 길이가 늘어난다는 검토 결과를 공유함. 고객이 요청을 철회해 4개 유지로 정리함.'
 item,=norm([{'title':'매거진 수량','before':'6개','after':'','business_state':'철회'}],row)
 assert (item['after'],item['business_state'])==('6개','철회')

def test_request_and_kept_value_in_swapped_cells_are_put_back():
 row='A14: 2 | B14: 코어 규격 | D14: 겸용 척은 교체 시간이 20분 이상 걸린다는 검토 결과를 공유함. 고객이 3인치/6인치 겸용 요청을 철회해 6인치 단독 유지로 정리함. | G14: 철회'
 item,=norm([{'title':'코어 규격','before':'3인치/6인치 겸용','after':'6인치 단독','business_state':'철회'}],row)
 assert (item['before'],item['after'],item['business_state'])==('6인치 단독','3인치/6인치 겸용','철회')
 row='A16: 4 | B16: 집진 방식 | D16: 고객이 노칭부 전용 집진기 별도 공급을 요청함. 견적 범위 기본안이 고객 공장 중앙 집진 연결이고 설치 공간도 없어 PNT가 반려함. 중앙 집진 연결 유지로 정리함. | G16: 반려'
 item,=norm([{'title':'집진 방식','before':'고객 공장 중앙 집진 연결','after':'중앙 집진 연결 유지','business_state':'철회'}],row)
 assert item['before']=='중앙 집진 연결' and '전용 집진기 별도 공급' in item['after'] and item['business_state']=='철회'

def test_a_one_letter_subject_is_kept():
 item,=norm([{'title':'폭','before':'320 mm','after':'320 mm','business_state':'확정'}],'폭은 가이드 레일만 늘리면 돼서 320 mm로 확정, 레일 연장 부품은 문지호가 2/18까지 추가 발주 중.')
 assert (item['title'],item['after'])==('폭','320 mm')

def test_the_old_value_in_the_previous_cell_is_not_taken_for_the_request():
 row='A15: 3 | B15: 납품 일정 | D15: 고객 라인 증설 공사가 늦어져 3월 12일 납품을 3월 말로 미뤄 달라고 함. 장비 보관 비용 부담 주체가 정해지지 않아 보류함. | G15: 보류'
 item,=norm([{'title':'납품 일정','category':'납기','before':'3월 12일','after':'','business_state':'보류'}],row)
 assert (item['before'],item['after'],item['business_state'])==('3월 12일','3월 말','보류')

def test_the_kept_value_becomes_the_previous_value_of_a_withdrawn_request():
 row='A14: 2 | B14: 코어 규격 | D14: 겸용 척은 교체 시간이 20분 이상 걸린다는 검토 결과를 공유함. 고객이 3인치/6인치 겸용 요청을 철회해 6인치 단독 유지로 정리함. | G14: 철회'
 item,=norm([{'title':'코어 규격','before':'3인치/6인치 겸용','after':'','business_state':'철회'}],row)
 assert (item['before'],item['after'])==('6인치 단독','3인치/6인치 겸용')
 text='코어는 검토에서 겸용 척이면 교체 시간이 20분 넘게 걸려서 표성훈 선임이 3인치/6인치 겸용 요청 철회, 6인치 단독 유지.'
 item,=norm([{'title':'코어 구조','before':'겸용 척','after':'6인치 단독','business_state':'확정'}],text)
 assert (item['before'],item['after'],item['business_state'])==('6인치 단독','3인치/6인치 겸용','철회')


# Agreed answer-key conventions: the base offer is the previous value; a value only asked for is not.
def test_the_base_offer_is_the_previous_value_of_a_request():
 cases=[('권취 속도','135 mpm','확정','고객 요청으로 권취 속도를 135 mpm으로 확정함. 기본안 120 mpm 대비 상향.','120 mpm'),
        ('마킹 속도','분당 120개','요청','마킹 속도는 고객이 분당 120개를 해 달라고 함. 우리 기본안은 분당 100개라서 검토중.','분당 100개'),
        ('버 높이','20 μm 이하','요청','PNT 기본 기준은 25 μm 이하인데 고객이 20 μm 이하를 요청함.','25 μm 이하'),
        ('건조로 구성','4존','요청','A15: CT-03 | B15: 건조로 구성 | C15: 3존(PNT 제안) | D15: 4존 | F15: 검토중','3존'),
        ('나이프 재질','초경','확정','A15: SL-04 | B15: 나이프 재질 | C15: 공구강(기본안) | D15: 초경 | F15: 합의','공구강')]
 for title,after,state,text,before in cases:
  item,=norm([{'title':title,'after':after,'business_state':state}],text)
  assert item['before']==before,(title,item['before'])

def test_a_value_only_asked_for_is_not_the_previous_value_of_the_agreement():
 item,=norm([{'title':'적층 속도','before':'0.8초','after':'0.9초','business_state':'확정'}],
            '재시험 결과 매당 0.9초까지 안정적이었음. 고객이 요청한 매당 0.8초 대신 매당 0.9초로 합의함.')
 assert item['before']==''
 item,=norm([{'title':'노칭 속도','before':'80 spm','after':'75 spm','business_state':'확정'}],
            '고객이 80 spm을 요청했으나 금형 수명을 고려해 PNT가 75 spm을 제안했고 고객이 동의함. 기본안 60 spm 대비 상향.')
 assert item['before']=='60 spm'
 # A value in effect before stays.
 item,=norm([{'title':'운전 속도','before':'120 m/min','after':'135 m/min','business_state':'확정'}],'운전 속도는 기존 120 m/min에서 135 m/min으로 올리는 걸로 확정함.')
 assert item['before']=='120 m/min'

def test_base_offers_written_as_proposals_words_and_neighbouring_sentences():
 item,=norm([{'title':'건조로 구성','after':'4존','business_state':'요청'}],'PNT는 3존 열풍 건조를 제안했으나 고객이 4존을 요청함. 설비 길이에 맞는지 검토하기로 함.')
 assert item['before']=='3존'
 item,=norm([{'title':'건조로','after':'4존','business_state':'요청'}],'건조로는 우리가 3존 열풍으로 제안했는데 고객이 4존으로 해 달라고 함.')
 assert item['before']=='3존'
 item,=norm([{'title':'나이프 재질','after':'초경','business_state':'확정'}],'버 높이 20 μm 맞추려면 나이프를 공구강에서 초경으로 바꾸는 게 맞아서 초경으로 확정함.')
 assert item['before']=='공구강'
 sentences=[{'id':'L5.0','text':'마킹 속도는 고객이 라인 택트 때문에 분당 120개를 해 달라고 함.'},
            {'id':'L5.1','text':'우리 기본안은 분당 100개라서 레이저 출력이랑 스캐너 속도를 봐야 함.'}]
 full=[{'topic_id':None,'category':'사양','title':'마킹 속도','before':'','after':'분당 120개','business_state':'요청','evidence':['L5.0']}]
 item,=normalize_extraction({'lines':sentences},full,[])
 assert item['before']=='분당 100개'

def test_a_base_offer_from_a_neighbouring_sentence_is_cited():
 sentences=[{'id':'L5.0','text':'마킹 속도는 고객이 라인 택트 때문에 분당 120개를 해 달라고 함.'},
            {'id':'L5.1','text':'우리 기본안은 분당 100개라서 레이저 출력이랑 스캐너 속도를 봐야 함.'}]
 full=[{'topic_id':None,'category':'사양','title':'마킹 속도','before':'','after':'분당 120개','business_state':'요청','evidence':['L5.0']}]
 item,=normalize_extraction({'lines':sentences},full,[])
 assert item['before']=='분당 100개' and item['evidence']==['L5.0','L5.1']
