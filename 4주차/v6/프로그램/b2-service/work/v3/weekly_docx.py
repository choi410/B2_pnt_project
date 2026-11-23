"""주간보고 초안을 회사 회의록 양식(Word)으로 내보낸다."""
import io
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / 'v17' / 'assets' / 'meeting-template.docx'
FONT = '맑은 고딕'


def export(report):
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt
    from docx.text.paragraph import Paragraph

    doc = Document(TEMPLATE)
    # 양식의 빈 줄은 손으로 쓰는 칸이다. 채워서 내보낼 때는 내용 길이에 맞춘다.
    for p in list(doc.paragraphs):
        if not p.text.strip() and not p._p.xpath('.//w:drawing'):
            p._p.getparent().remove(p._p)

    def style(run, size=10, bold=None):
        run.font.name = FONT; run.font.size = Pt(size)
        run._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'), FONT)
        if bold is not None:
            run.bold = bold

    def replace(p, text):
        if p.runs:
            p.runs[0].text = text
            for r in p.runs[1:]:
                r.text = ''
        else:
            p.add_run(text)

    def insert_after(anchor, text, indent=0.0, bold=False, size=10):
        el = OxmlElement('w:p'); anchor._p.addnext(el)
        p = Paragraph(el, anchor._parent)
        p.paragraph_format.space_after = Pt(4); p.paragraph_format.left_indent = Cm(indent)
        style(p.add_run(text), size, bold)
        return p

    headings = {p.text.replace(' ', ''): p for p in doc.paragraphs if p.text.strip()}
    replace(headings['회의록'], '주간 업무보고')
    replace(headings['MEETINGMINUTES'], 'WEEKLY REPORT')
    meta = doc.tables[0]
    projects = list(dict.fromkeys(i['text'] for s in report['sections'] for i in s['items'] if i['type'] == 'group' and i['text'] != '기타 업무'))
    period = report['start'] + ' ~ ' + report['end']
    cells = {(0, 0): '보고서명', (0, 1): report['title'], (1, 0): '프로젝트', (1, 1): ', '.join(projects) or '해당 없음',
             (2, 0): '보고 기간', (2, 1): period, (2, 2): '구분', (2, 3): '주간 업무보고',
             (3, 0): '자료 기준', (3, 1): report['created_at'][:16].replace('T', ' '),
             (4, 1): report['author_name'], (4, 3): report['updated_at'][:10]}
    for (r, c), value in cells.items():
        replace(meta.cell(r, c).paragraphs[0], value)

    agenda = headings['회의안건']
    agenda._p.getparent().remove(agenda._p)
    slots = [headings['논의내용'], headings['결정사항']]
    for number, (anchor, section) in enumerate(zip(slots, report['sections']), 1):
        replace(anchor, f"{number}. {section['heading']}")
        anchor.paragraph_format.space_before = Pt(12); anchor.paragraph_format.space_after = Pt(6)
        anchor.paragraph_format.keep_with_next = True
        last = anchor
        for it in section['items']:
            if not it['text'].strip():
                continue
            if it['type'] == 'group':
                last = insert_after(last, '■ ' + it['text'], 0.2, True)
            else:
                last = insert_after(last, ('- ' if it['level'] else '· ') + it['text'], 1.1 if it['level'] else 0.6)
        if last is anchor:
            insert_after(anchor, '기재 내용 없음', 0.6)

    anchor = headings['추가확인사항']
    replace(anchor, '3. 조치사항 (담당자 / 기한)')
    anchor.paragraph_format.space_before = Pt(12); anchor.paragraph_format.space_after = Pt(6)
    if report['actions']:
        table = doc.add_table(rows=1, cols=3); table.style = 'Table Grid'
        for cell, text in zip(table.rows[0].cells, ['조치사항', '담당', '기한']):
            cell.text = text
        for a in report['actions']:
            for cell, text in zip(table.add_row().cells, [a['task'], a['owner'] or '미정', a['due'] or '미정']):
                cell.text = text
        for n, row in enumerate(table.rows):
            for i, cell in enumerate(row.cells):
                cell.width = Cm([10.7, 3, 3.4][i])
                for p in cell.paragraphs:
                    p.paragraph_format.space_after = Pt(4); p.paragraph_format.space_before = Pt(4)
                    for run in p.runs:
                        style(run, 9, n == 0)
        anchor._p.addnext(table._tbl)
    else:
        insert_after(anchor, '기재 내용 없음', 0.6)

    sources = headings['후속조치']
    replace(sources, '근거 자료')
    sources.paragraph_format.space_before = Pt(14); sources.paragraph_format.space_after = Pt(6)
    used, last = {}, sources
    for section in report['sections']:
        for it in section['items']:
            for ev in it.get('evidence', []):
                used.setdefault(ev['meeting_id'], ev)
    for a in report['actions']:
        for ev in a.get('evidence', []):
            used.setdefault(ev['meeting_id'], ev)
    for ev in sorted(used.values(), key=lambda e: (e['meeting_date'], e['meeting_title'])):
        last = insert_after(last, f"· {ev['meeting_date']} {ev['meeting_title']} ({ev['project_name']})", 0.6, size=9)
    if not used:
        last = insert_after(last, '· 연결된 회의록 없음 (메모만으로 작성)', 0.6, size=9)
    state = '작성자 확인 완료' if report.get('checked') else '검토 전 초안'
    note = insert_after(last, f"작성 상태: {state} · 회의록 연결은 작성자가 확인한 항목만 사용했습니다.", 0, size=9)
    note.paragraph_format.space_before = Pt(10)
    out = io.BytesIO(); doc.save(out)
    return out.getvalue()
