"""주간보고 입력 정리: 메모·Excel을 (일자, 업무 내용, 상태) 행으로 바꾼다.

AI를 쓰지 않는다. 읽지 못한 줄은 버리지 않고 '상태 미정' 행으로 남겨 사용자가 고칠 수 있게 한다.
"""
import io
import re
import zipfile
from datetime import date, datetime, timedelta

MAX_ROWS = 60
MAX_TEXT = 18000
STATUSES = ('완료', '진행', '예정', '보류')

# 긴 표현이 먼저 맞도록 정렬해서 쓴다. '진행 완료'는 완료, '미완료'는 진행이다.
_STATUS_WORDS = [
    ('미완료', '진행'), ('미완', '진행'), ('진행 완료', '완료'), ('진행완료', '완료'),
    ('완료', '완료'), ('종료', '완료'), ('마감', '완료'), ('done', '완료'), ('끝', '완료'),
    ('진행 중', '진행'), ('진행중', '진행'), ('진행', '진행'), ('작업 중', '진행'), ('작업중', '진행'),
    ('검토 중', '진행'), ('검토중', '진행'), ('ing', '진행'), ('wip', '진행'),
    ('예정', '예정'), ('계획', '예정'), ('대기', '예정'), ('착수 전', '예정'), ('todo', '예정'),
    ('보류', '보류'), ('중단', '보류'), ('hold', '보류'), ('지연', '진행'),
]
_HEADER_DATE = ('일자', '날짜', '일시', 'date', '요일')
_HEADER_TEXT = ('업무내용', '업무', '내용', '작업', '항목', '실적', 'task', '메모')
_HEADER_STATUS = ('상태', '진행상태', '진척', '비고', 'status', '결과')
_DATE_PATTERNS = [
    re.compile(r'(?P<y>20\d{2})\s*[-./년]\s*(?P<m>\d{1,2})\s*[-./월]\s*(?P<d>\d{1,2})\s*일?'),
    re.compile(r'(?<!\d)(?P<m>\d{1,2})\s*월\s*(?P<d>\d{1,2})\s*일'),
    re.compile(r'(?<![\d.])(?P<m>\d{1,2})\s*[/.]\s*(?P<d>\d{1,2})(?![\d.])'),
]
_BULLET = re.compile(r'^\s*(?:[-*•·▪◦■□○●▶]+|\d{1,2}[.)](?!\d))\s*')
_WEEKDAY = re.compile(r'^\s*[(\[]?[월화수목금토일](?:요일)?[)\]]?\s*[:,]?\s*')


def week_of(day):
    """day가 속한 주의 월요일~금요일."""
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=4)


def _iso(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def resolve_date(month, day, start, end, year=None):
    """연도가 없는 '11/18'을 보고 기간에 가장 가까운 연도로 해석한다. 날짜가 아니면 ''."""
    years = [year] if year else sorted({start.year - 1, start.year, end.year, end.year + 1})
    best = None
    for y in years:
        try:
            candidate = date(y, month, day)
        except ValueError:
            continue
        distance = 0 if start <= candidate <= end else min(abs((candidate - start).days), abs((candidate - end).days))
        if best is None or distance < best[0]:
            best = (distance, candidate)
    return best[1].isoformat() if best else ''


def find_date(text, start, end):
    """문장 앞쪽의 날짜를 찾아 (ISO 날짜, 날짜를 뺀 문장)을 돌려준다."""
    for pattern in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match or match.start() > 12:
            continue
        year = int(match['y']) if 'y' in pattern.groupindex else None
        found = resolve_date(int(match['m']), int(match['d']), start, end, year)
        if found:
            rest = (text[:match.start()] + ' ' + text[match.end():]).strip()
            return found, _WEEKDAY.sub('', rest, count=1) if re.match(r'^\s*[(\[][월화수목금토일]', rest) else rest
    return '', text


def normalize_status(text):
    compact = str(text or '').strip().lower()
    if not compact:
        return ''
    for word, status in _STATUS_WORDS:
        if word in compact:
            return status
    return ''


def split_status(text):
    """문장 끝의 상태 표시를 분리한다: '도면 검토 - 진행', '납품(완료)', '재발주 [진행중]'."""
    tail = re.search(r'\s*(?:[-–—:/|,]\s*|[(\[]\s*)([^\s()\[\]]{1,6}(?:\s[^\s()\[\]]{1,3})?)\s*[)\]]?\s*$', text)
    if tail:
        status = normalize_status(tail.group(1))
        # 꼬리 표현이 상태 낱말 그 자체일 때만 떼어 낸다. '완료 보고서 작성' 같은 본문은 건드리지 않는다.
        if status and len(tail.group(1).replace(' ', '')) <= 5:
            return text[:tail.start()].strip(), status
    plain = re.search(r'\s(완료|진행\s?중|진행|예정|보류)\s*$', text)
    if plain:
        return text[:plain.start()].strip(), normalize_status(plain.group(1))
    return text.strip(), ''


def _cells(line):
    if '\t' in line:
        return [c.strip() for c in line.split('\t')]
    if line.count('|') >= 2:
        return [c.strip() for c in line.strip().strip('|').split('|')]
    return None


def _header_map(cells):
    """표 머리글이면 {'date':i,'text':j,'status':k}, 아니면 None."""
    found = {}
    for i, cell in enumerate(cells):
        key = re.sub(r'[\s/·()]', '', str(cell or '')).lower()
        if not key or len(key) > 8:
            continue
        for name, words in (('date', _HEADER_DATE), ('status', _HEADER_STATUS), ('text', _HEADER_TEXT)):
            if name not in found and any(key == w or key.startswith(w) for w in words):
                found[name] = i
                break
    return found if 'text' in found and len(found) >= 2 else None


def _row(rows, day, text, status, raw):
    text = re.sub(r'\s+', ' ', str(text or '')).strip(' -·:')
    if not text:
        return
    rows.append({'id': 'R' + str(len(rows) + 1), 'date': day, 'text': text[:300], 'status': status, 'raw': str(raw)[:400]})


def _cell_date(value, start, end):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return find_date(str(value or ''), start, end)[0]


def rows_from_table(table, start, end):
    """셀 값의 2차원 목록에서 행을 만든다. 머리글이 없으면 날짜·상태처럼 보이는 열을 추정한다."""
    rows, mapping, carried = [], None, ''
    for cells in table:
        cells = list(cells)
        if not any(str(c or '').strip() for c in cells):
            continue
        header = _header_map(cells)
        if header:
            if mapping is None:
                rows.clear()  # 머리글 위의 제목·기간 줄은 업무 항목이 아니다.
            mapping = header
            continue
        if mapping:
            get = lambda name: cells[mapping[name]] if name in mapping and mapping[name] < len(cells) else ''
            day = _cell_date(get('date'), start, end) or carried
            carried = day  # 병합 셀처럼 날짜가 비어 있으면 위 행의 날짜를 잇는다.
            text, status = str(get('text') or '').strip(), normalize_status(get('status'))
            if not status:
                text, status = split_status(text)
            _row(rows, day, text, status, ' | '.join(str(c or '') for c in cells))
            continue
        day, texts, status = '', [], ''
        for cell in cells:
            value = str(cell or '').strip() if not isinstance(cell, (date, datetime)) else cell
            if not value:
                continue
            found = _cell_date(value, start, end) if isinstance(value, (date, datetime)) or len(str(value)) <= 14 else ''
            if found and not day:
                day = found
            elif not status and len(str(value)) <= 6 and normalize_status(value):
                status = normalize_status(value)
            else:
                texts.append(str(value))
        text = ' '.join(texts)
        if not day:
            day, text = find_date(text, start, end)
        if not status:
            text, status = split_status(text)
        _row(rows, day, text, status, ' | '.join(str(c or '') for c in cells))
    return rows


def parse_text(text, start, end):
    """붙여넣은 메모를 행으로 바꾼다. Excel에서 복사한 탭 구분 표도 받는다."""
    start, end = _iso(start), _iso(end)
    if not start or not end or start > end:
        raise ValueError('보고 기간의 시작일과 종료일을 확인해 주세요.')
    if len(text) > MAX_TEXT:
        raise ValueError('메모가 18,000자를 넘습니다. 나누어 입력해 주세요.')
    lines = [line for line in text.replace('\r', '').split('\n') if line.strip()]
    if sum(1 for line in lines if _cells(line)) >= max(2, len(lines) // 2):
        rows = rows_from_table([_cells(line) or [line] for line in lines], start, end)
    else:
        rows, carried = [], ''
        for line in lines:
            body = _BULLET.sub('', line).strip()
            day, body = find_date(body, start, end)
            if day and not body.strip(' :-·'):
                carried = day  # '11/18' 한 줄만 있으면 아래 줄들의 날짜로 쓴다.
                continue
            body, status = split_status(_BULLET.sub('', body))
            _row(rows, day or carried, body, status, line)
    if len(rows) > MAX_ROWS:
        raise ValueError(f'업무 항목이 {MAX_ROWS}개를 넘습니다. 기간을 나누어 작성해 주세요.')
    return rows


def parse_file(filename, raw, start, end):
    """Excel·Word·텍스트 파일에서 행을 만든다. (rows, 안내 문구)를 돌려준다."""
    start_day, end_day = _iso(start), _iso(end)
    if not start_day or not end_day or start_day > end_day:
        raise ValueError('보고 기간의 시작일과 종료일을 확인해 주세요.')
    if len(raw) > 5 * 1024 * 1024:
        raise ValueError('파일은 5MB 이하로 올려 주세요.')
    ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext in ('.xlsx', '.docx'):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if sum(x.file_size for x in z.infolist()) > 30 * 1024 * 1024:
                    raise ValueError('압축 해제 크기가 너무 큽니다.')
        except zipfile.BadZipFile:
            raise ValueError('파일을 읽지 못했습니다. 암호가 걸리지 않은 정상 파일인지 확인해 주세요.')
    if ext == '.xlsx':
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        rows, formulas = [], False
        try:
            for sheet in wb:
                if sheet.sheet_state != 'visible':
                    continue
                table = []
                for i, cells in enumerate(sheet.iter_rows(values_only=True)):
                    if i >= 1000:
                        raise ValueError('시트는 1,000행 이내로 나누어 주세요.')
                    table.append(list(cells[:30]))
                found = rows_from_table(table, start_day, end_day)
                for row in found:
                    row['id'] = 'R' + str(len(rows) + 1)
                    rows.append(row)
        finally:
            wb.close()
        note = '셀의 글자와 날짜만 읽었습니다. 색으로 표시한 일정, 도형, 이미지는 읽지 않습니다.'
    elif ext == '.docx':
        from docx import Document
        doc, lines = Document(io.BytesIO(raw)), []
        for block in doc.iter_inner_content():
            if hasattr(block, 'text'):
                lines.append(block.text)
            else:
                for r in block.rows:
                    lines.append('\t'.join(dict.fromkeys(c.text.strip() for c in r.cells)))
        rows, note = parse_text('\n'.join(lines), start, end), ''
    elif ext in ('.txt', '.md', '.csv'):
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('cp949', errors='replace')
        if ext == '.csv':
            text = '\n'.join('\t'.join(c.strip().strip('"') for c in line.split(',')) for line in text.splitlines())
        rows, note = parse_text(text, start, end), ''
    else:
        raise ValueError('Excel(.xlsx), Word(.docx), 텍스트(.txt·.csv) 파일을 선택해 주세요.')
    if not rows:
        raise ValueError('업무 항목을 찾지 못했습니다. 일자, 업무 내용, 상태가 한 줄에 하나씩 있는지 확인해 주세요.')
    if len(rows) > MAX_ROWS:
        raise ValueError(f'업무 항목이 {MAX_ROWS}개를 넘습니다. 기간을 나누어 작성해 주세요.')
    return rows, note
