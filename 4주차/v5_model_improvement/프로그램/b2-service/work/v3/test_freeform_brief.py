"""Free-form minutes in the standard format, and the AI summary: the model judges, the code verifies."""
from work.v3 import brief, freeform
from work.v3.outline import build


def lines(*texts):
    return [{'id': f'L{i:03d}', 'text': t} for i, t in enumerate(texts, 1)]


MEMO = lines('시트: 줄글 회의록', 'A2: 회의 메모',
             'A3: 2026년 11월 27일 14시부터 본사 회의실에서 납품 일정 다시 얘기함. 메모는 이서연이 적음.',
             'A4: 135 m/min까지는 지금 모터로 가능하다고 함. 운전 속도는 기존 120 m/min에서 135 m/min으로 올리는 걸로 확정함. '
             '박준호가 12월 3일까지 8시간 연속 운전 시험 해보기로 함.',
             'A5: 진동 기준은 이번에 못 정하고 보류함.')
LAYOUT = {'L003.0': 'header', 'L003.1': 'header', 'L004.0': 'discussion', 'L004.1': 'decision', 'L004.2': 'followup', 'L005.0': 'pending'}


def test_sentences_have_stable_ids_and_skip_sheet_names_and_short_cells():
    assert [(i, l) for i, l, _ in freeform.sentences(MEMO)] == [
        ('L003.0', 'L003'), ('L003.1', 'L003'), ('L004.0', 'L004'), ('L004.1', 'L004'), ('L004.2', 'L004'), ('L005.0', 'L005')]
    assert freeform.is_free_form(MEMO) and not freeform.is_free_form(lines('결정 사항', '코팅 폭은 650 mm로 합의했다.'))


def test_layout_answer_keeps_each_sentence_once_and_fills_what_the_model_skipped():
    ids = [i for i, _, _ in freeform.sentences(MEMO)]
    answer = {'sentences': [{'id': 'L004.1', 'section': '결정 사항'}, {'id': 'L004.1', 'section': '논의 내용'},  # twice
                            {'id': 'L999.0', 'section': '결정 사항'}, {'id': 'L005.0', 'section': '없는 절'},
                            {'id': 'L003.0', 'section': '머리말'}]}
    placed = freeform.keep(answer, ids)
    assert list(placed) == ids
    assert placed['L004.1'] == 'decision' and placed['L003.0'] == 'header'
    assert placed['L005.0'] == 'discussion' and placed['L004.0'] == 'discussion'      # unknown section, skipped


def test_free_form_minutes_with_a_layout_are_shown_in_the_standard_format():
    change = {'id': 'c1', 'title': '운전 속도', 'after': '135 m/min', 'review_state': '검토 전', 'evidence': ['L004']}
    out = build({'id': 'm', 'revision': 1, 'lines': MEMO, 'layout': {'items': LAYOUT, 'revision': 1}}, [change])
    assert out['mode'] == 'sections' and out['converted'] and out['coverage']['unit'] == '문장'
    assert [(s['label'], [x['id'] for x in s['items']]) for s in out['sections']] == [
        ('논의 내용', ['L004.0']), ('결정 사항', ['L004.1']), ('후속 조치', ['L004.2']), ('추가 확인', ['L005.0'])]
    decision = out['sections'][1]['items'][0]
    assert decision['text'].startswith('운전 속도는 기존 120 m/min') and decision['evidence'] == ['L004'] and decision['changes']
    # The header sentences and the sheet-name lines are listed as left out of the body, not lost.
    assert {x['id'] for x in out['coverage']['header']} == {'L001', 'L002', 'L003.0', 'L003.1'}
    assert out['coverage']['body'] == out['coverage']['shown'] == 4


def test_without_a_layout_or_with_one_of_an_older_revision_the_plain_list_is_shown():
    plain = build({'id': 'm', 'revision': 2, 'lines': MEMO, 'layout': {'items': LAYOUT, 'revision': 1}})
    assert plain['mode'] == 'flat' and not plain['converted'] and plain['sections'][0]['label'] == '전체 내용'


def test_a_sentence_of_a_free_form_line_can_be_edited_and_old_risk_results_are_not_shown():
    # Risks were judged by older analyses; the feature is gone, so a stored result shows nothing.
    meeting = {'id': 'm', 'revision': 1, 'lines': MEMO, 'layout': {'items': LAYOUT, 'revision': 1},
               'outline_edits': {'L004.0': '135 m/min까지 현재 모터로 가능.'},
               'risks': {'items': [{'id': 'L004.0', 'kind': '기술'}], 'revision': 1}}
    out = build(meeting)
    sections = {s['kind']: s['items'] for s in out['sections']}
    assert sections['discussion'][0]['text'] == '135 m/min까지 현재 모터로 가능.' and sections['discussion'][0]['edited']
    assert 'risk' not in sections and 'risk' not in sections['discussion'][0] and 'risks_judged' not in out


def test_summary_line_is_dropped_when_its_number_is_not_in_the_sentences_it_cites():
    outline = build({'id': 'm', 'revision': 1, 'lines': MEMO, 'layout': {'items': LAYOUT, 'revision': 1}})
    offered = brief.offered(outline)
    assert [i for i, _, _, _ in offered] == ['L004.0', 'L004.1', 'L004.2', 'L005.0']
    answer = {'summary': [
        {'text': '운전 속도를 120 m/min에서 135 m/min으로 확정했다.', 'ids': ['L004.1']},
        {'text': '박준호가 12월 3일까지 8시간 연속 운전 시험을 한다.', 'ids': ['L005.0']},     # numbers are in another sentence
        {'text': '운전 속도를 140 m/min으로 확정했다.', 'ids': ['L004.1']},                      # invented number
        {'text': '진동 기준은 보류했다.', 'ids': ['L999.9']},                                    # cites nothing real
        {'text': '진동 기준은 보류했다.', 'ids': ['L005.0', 'L005.0']}]}
    kept = brief.keep(answer, offered)
    assert [x['text'] for x in kept] == ['운전 속도를 120 m/min에서 135 m/min으로 확정했다.', '진동 기준은 보류했다.']
    assert kept[0]['evidence'] == ['L004'] and kept[1]['ids'] == ['L005.0']


def test_outline_shows_the_stored_summary_only_for_the_current_revision_and_existing_sentences():
    stored = {'items': [{'text': '운전 속도를 120 m/min에서 135 m/min으로 확정했다.', 'ids': ['L004.1'], 'evidence': ['L004']},
                        {'text': '사라진 문장을 근거로 한 줄.', 'ids': ['L009.0'], 'evidence': ['L009']}], 'revision': 1}
    base = {'id': 'm', 'lines': MEMO, 'layout': {'items': LAYOUT, 'revision': 1}, 'brief': stored}
    shown = build({**base, 'revision': 1})
    assert [x['text'] for x in shown['brief']] == ['운전 속도를 120 m/min에서 135 m/min으로 확정했다.'] and shown['brief_written']
    assert build({**base, 'revision': 2, 'layout': {'items': LAYOUT, 'revision': 2}})['brief'] == []
    assert not build({'id': 'm', 'revision': 1, 'lines': MEMO})['brief_written']
