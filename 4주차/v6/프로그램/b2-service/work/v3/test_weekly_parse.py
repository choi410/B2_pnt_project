import io
from datetime import date, datetime
import pytest
from work.v3 import weekly_parse as wp

S, E = '2026-11-16', '2026-11-20'

def brief(rows):
    return [(r['date'], r['text'], r['status']) for r in rows]

def test_free_memo_lines_with_dates_and_status():
    rows = wp.parse_text('11/16 믹서 구매 사양 회의 - 완료\n- 11.18 롤프레스 배치도 개정 (진행중)\n· 11월 19일 슬리터 검수 체크리스트 수정 예정\n2026-11-20 재질 성적서 확보: 완료', S, E)
    assert brief(rows) == [
        ('2026-11-16', '믹서 구매 사양 회의', '완료'),
        ('2026-11-18', '롤프레스 배치도 개정', '진행'),
        ('2026-11-19', '슬리터 검수 체크리스트 수정', '예정'),
        ('2026-11-20', '재질 성적서 확보', '완료')]

def test_excel_paste_with_header_and_blank_date_carries_down():
    text = '일자\t업무 내용\t상태\n10/20\tA사 납품\t완료\n\t부품 재발주\t진행\n10/22\t도면 검토\t진행\n10/23\t고객 회의\t완료'
    rows = wp.parse_text(text, '2026-10-19', '2026-10-23')
    assert brief(rows) == [('2026-10-20', 'A사 납품', '완료'), ('2026-10-20', '부품 재발주', '진행'),
                           ('2026-10-22', '도면 검토', '진행'), ('2026-10-23', '고객 회의', '완료')]

def test_date_only_line_applies_to_following_lines():
    rows = wp.parse_text('11/18\n롤프레스 재협의 완료\n커버 간섭 검토서 작성 진행', S, E)
    assert brief(rows) == [('2026-11-18', '롤프레스 재협의', '완료'), ('2026-11-18', '커버 간섭 검토서 작성', '진행')]

def test_unreadable_line_is_kept_without_status_and_numbers_are_not_dates():
    rows = wp.parse_text('압연 속도 135 m/min 반영\n완료 보고서 작성 건 확인', S, E)
    assert brief(rows) == [('', '압연 속도 135 m/min 반영', ''), ('', '완료 보고서 작성 건 확인', '')]

def test_year_boundary_picks_year_nearest_to_period():
    rows = wp.parse_text('12/31 연말 점검 완료\n1/2 신년 회의 예정', '2026-12-28', '2027-01-01')
    assert [r['date'] for r in rows] == ['2026-12-31', '2027-01-02']

def test_incomplete_and_status_words():
    assert wp.normalize_status('미완료') == '진행'
    assert wp.normalize_status('진행 완료') == '완료'
    assert wp.normalize_status('검토중') == '진행'
    assert wp.normalize_status('대기') == '예정'
    assert wp.normalize_status('') == ''

def test_xlsx_with_real_date_cells_and_title_rows():
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.append(['주간 업무 (11/16~11/20)']); ws.append([])
    ws.append(['일자', '업무 내용', '상태', '비고'])
    ws.append([datetime(2026, 11, 16), '믹서 구매 사양 회의', '완료', ''])
    ws.append([date(2026, 11, 18), '롤프레스 구동부 배치도 개정', '진행중', '135 m/min'])
    ws.append([None, '커버 간섭 검토서 공유', '완료', None])
    out = io.BytesIO(); wb.save(out)
    rows, note = wp.parse_file('주간.xlsx', out.getvalue(), S, E)
    assert brief(rows) == [('2026-11-16', '믹서 구매 사양 회의', '완료'), ('2026-11-18', '롤프레스 구동부 배치도 개정', '진행'),
                           ('2026-11-18', '커버 간섭 검토서 공유', '완료')]
    assert '색으로 표시한' in note

def test_xlsx_without_header_guesses_columns():
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.append(['11/17', '코팅 폭 변경 회의', '완료']); ws.append(['11/19', '헤드 구매 사양 확정', '진행'])
    out = io.BytesIO(); wb.save(out)
    rows, _ = wp.parse_file('a.xlsx', out.getvalue(), S, E)
    assert brief(rows) == [('2026-11-17', '코팅 폭 변경 회의', '완료'), ('2026-11-19', '헤드 구매 사양 확정', '진행')]

def test_rejects_bad_period_unknown_file_and_empty():
    with pytest.raises(ValueError): wp.parse_text('a', '2026-11-20', '2026-11-16')
    with pytest.raises(ValueError): wp.parse_file('a.hwp', b'x', S, E)
    with pytest.raises(ValueError): wp.parse_file('a.txt', b'   \n', S, E)
    with pytest.raises(ValueError): wp.parse_file('a.xlsx', b'not a zip', S, E)

def test_week_of():
    assert wp.week_of(date(2026, 11, 18)) == (date(2026, 11, 16), date(2026, 11, 20))
