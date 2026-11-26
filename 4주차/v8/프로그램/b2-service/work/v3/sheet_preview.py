"""A picture of an Excel sheet as its writer sees it, for the review screen's 원본 panel.

Word minutes get a PDF through Word; an .xlsx had nothing, so the panel showed only the text read from
it. This draws the first sheet (cell borders, merged cells, fills, bold, alignment, wrapped text) with
Pillow, crops it to the cells in use and saves it as a one-page PDF, which the existing preview shows like
any other original. No Excel or LibreOffice is needed.

The page is an image without a text layer, so the usual search for a sentence in the PDF finds nothing.
The drawing knows where every cell is, though: line_boxes() gives, for each line of the minutes, the
cells that hold its text, in the form the screen highlights ({'page', 'rects': [[x, y, w, h], …]} as
fractions of the page). The boxes are worked out again from the stored .xlsx (cached), so nothing extra
is kept on disk.
"""
import io
import re
from pathlib import Path

SCALE = 2            # pixels per Excel pixel: sharp enough to read when the panel zooms
MAX_CELLS = 20000
MARGIN = 12          # Excel pixels of white kept around the cells in use
_FONTS = [(r'C:\Windows\Fonts\malgun.ttf', r'C:\Windows\Fonts\malgunbd.ttf'),
          ('/usr/share/fonts/truetype/nanum/NanumGothic.ttf', '/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf'),
          ('/System/Library/Fonts/AppleSDGothicNeo.ttc', '/System/Library/Fonts/AppleSDGothicNeo.ttc')]
_CACHE = {}


def _font_files():
    return next(((a, b) for a, b in _FONTS if Path(a).is_file() and Path(b).is_file()), None)


def _rgb(color, default=None):
    """openpyxl colour -> '#RRGGBB' (theme and indexed colours are left to the default)."""
    value = getattr(color, 'rgb', None)
    if isinstance(value, str) and len(value) == 8 and value != '00000000':
        return '#' + value[2:]
    return default


def _show(value):
    if value is None:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d %H:%M' if getattr(value, 'hour', 0) or getattr(value, 'minute', 0) else '%Y-%m-%d')
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _draw(data):
    """(image cropped to the cells in use, [(cell text, [x, y, w, h] as fractions of that image), …] in
    reading order), or None when the sheet cannot be drawn."""
    files = _font_files()
    if not files:
        return None
    import openpyxl
    from openpyxl.utils import get_column_letter
    from PIL import Image, ImageDraw, ImageFont
    ws = openpyxl.load_workbook(io.BytesIO(data), data_only=True).worksheets[0]
    rows, cols = ws.max_row or 0, ws.max_column or 0
    if not rows or not cols or rows * cols > MAX_CELLS:
        return None
    default_w = ws.sheet_format.defaultColWidth or 8.43
    default_h = ws.sheet_format.defaultRowHeight or 15
    width = lambda c: 0 if ws.column_dimensions[get_column_letter(c)].hidden else \
        int(((ws.column_dimensions[get_column_letter(c)].width or default_w) * 7 + 5) * SCALE)
    height = lambda r: 0 if ws.row_dimensions[r].hidden else int((ws.row_dimensions[r].height or default_h) * 96 / 72 * SCALE)
    pad_out = MARGIN * SCALE
    xs = [pad_out]; ys = [pad_out]
    for c in range(1, cols + 1): xs.append(xs[-1] + width(c))
    for r in range(1, rows + 1): ys.append(ys[-1] + height(r))
    img = Image.new('RGB', (xs[-1] + pad_out, ys[-1] + pad_out), 'white'); d = ImageDraw.Draw(img)
    fonts = {}

    def font(size, bold):
        key = (max(6, int(round(size * 96 / 72 * SCALE))), bool(bold))
        if key not in fonts:
            fonts[key] = ImageFont.truetype(files[1] if bold else files[0], key[0])
        return fonts[key]

    merged = {}; covered = set()
    for rng in ws.merged_cells.ranges:
        merged[(rng.min_row, rng.min_col)] = (rng.max_row, rng.max_col)
        covered.update((r, c) for r in range(rng.min_row, rng.max_row + 1) for c in range(rng.min_col, rng.max_col + 1))
    boxes = []
    for r in range(1, rows + 1):
        for c in range(1, cols + 1):
            if (r, c) in covered and (r, c) not in merged:
                continue
            r2, c2 = merged.get((r, c), (r, c))
            boxes.append((ws.cell(r, c), xs[c - 1], ys[r - 1], xs[c2], ys[r2], r2, c2))
    used = [10 ** 9, 10 ** 9, 0, 0]     # bounding box of everything drawn

    def mark(x0, y0, x1, y1):
        used[0] = min(used[0], x0); used[1] = min(used[1], y0); used[2] = max(used[2], x1); used[3] = max(used[3], y1)

    for cell, x0, y0, x1, y1, _, _ in boxes:        # fills first, so borders and text stay on top
        if cell.fill is not None and cell.fill.fill_type == 'solid':
            colour = _rgb(cell.fill.fgColor)
            if colour and colour.upper() != '#FFFFFF' and x1 > x0 and y1 > y0:
                d.rectangle([x0, y0, x1, y1], fill=colour); mark(x0, y0, x1, y1)
    thick = {'medium': 2, 'thick': 3, 'double': 2}
    for cell, x0, y0, x1, y1, r2, c2 in boxes:
        if x1 <= x0 or y1 <= y0:
            continue
        last = ws.cell(r2, c2).border     # a merged area's right and bottom edges are stored on its last cell
        for side, line in ((cell.border.left, (x0, y0, x0, y1)), (cell.border.top, (x0, y0, x1, y0)),
                           (last.right, (x1, y0, x1, y1)), (last.bottom, (x0, y1, x1, y1))):
            if side is not None and side.style:
                d.line(line, fill=_rgb(side.color, '#000000'), width=thick.get(side.style, 1) * SCALE // 2 or 1)
                mark(line[0], line[1], line[2], line[3])
    pad = 3 * SCALE
    texts = []
    for cell, x0, y0, x1, y1, _, _ in boxes:
        text = _show(cell.value)
        if not text or x1 <= x0 or y1 <= y0:
            continue
        f = font(cell.font.size or 11, cell.font.bold)
        room = x1 - x0 - 2 * pad
        lines = []
        for part in text.split('\n'):
            if not (cell.alignment and cell.alignment.wrap_text) or d.textlength(part, font=f) <= room:
                lines.append(part); continue
            cur = ''
            for ch in part:                                   # Korean wraps at any character
                if cur and d.textlength(cur + ch, font=f) > room:
                    lines.append(cur); cur = ch.lstrip()
                else:
                    cur += ch
            lines.append(cur)
        step = int(f.size * 1.3)
        horizontal = (cell.alignment.horizontal if cell.alignment else None) or ('right' if isinstance(cell.value, (int, float)) else 'left')
        vertical = (cell.alignment.vertical if cell.alignment else None) or 'bottom'
        block = step * len(lines)
        y = y0 + pad if vertical == 'top' else (y1 - pad - block if vertical == 'bottom' else (y0 + y1 - block) // 2)
        widest = 0
        for line in lines:
            w = d.textlength(line, font=f); widest = max(widest, w)
            x = (x0 + x1 - w) // 2 if horizontal in ('center', 'centerContinuous') else (x1 - pad - w if horizontal == 'right' else x0 + pad)
            d.text((x, y + (step - f.size) // 2), line, font=f, fill=_rgb(cell.font.color, '#000000'))
            y += step
        # Text of an unwrapped cell runs over its empty neighbours, as in Excel: the box covers what is drawn.
        right = max(x1, x0 + pad + widest + pad) if horizontal not in ('center', 'centerContinuous', 'right') else x1
        mark(x0, y0, right, y1)
        texts.append((text, (x0, y0, right, y1)))
    if used[2] <= used[0] or used[3] <= used[1]:
        return None
    left, top = max(0, used[0] - pad_out), max(0, used[1] - pad_out)
    right, bottom = min(img.width, used[2] + pad_out), min(img.height, used[3] + pad_out)
    # The form's frame runs on for many empty rows under the last statement. Keep one row of room below the
    # last text and close the frame there, so the written part fills the panel.
    last_text = max(y1 for _, (_, _, _, y1) in texts) if texts else used[3]
    cut = last_text + int(default_h * 96 / 72 * SCALE)
    if cut < used[3]:
        d.line((used[0], cut, used[2], cut), fill='#000000', width=max(1, SCALE // 2))
        bottom = min(img.height, cut + pad_out)
    img = img.crop((left, top, right, bottom)); W, H = img.size
    cells = [(t, [round((x0 - left) / W, 4), round((y0 - top) / H, 4), round((x1 - x0) / W, 4), round((y1 - y0) / H, 4)])
             for t, (x0, y0, x1, y1) in texts]
    return img, cells


def render_xlsx(data):
    """PDF bytes of the first sheet of an .xlsx, or None."""
    try:
        drawn = _draw(data)
        if not drawn:
            return None
        out = io.BytesIO()
        drawn[0].save(out, 'PDF', resolution=96 * SCALE)    # one Excel pixel = 1/96 inch: the page has the sheet's own size
        return out.getvalue()
    except Exception:
        return None


def source_of(pdf_path):
    """The .xlsx a drawn preview ('<id>.sheet.pdf') was made from, or None for any other PDF."""
    path = Path(pdf_path)
    if not path.name.endswith('.sheet.pdf'):
        return None
    source = path.with_name(path.name[:-len('.sheet.pdf')] + '.xlsx')
    return source if source.is_file() else None


_squash = lambda text: re.sub(r'[^0-9A-Za-z가-힣]', '', str(text or '')).casefold()


def line_boxes(pdf_path, lines):
    """{line id: {'page': 1, 'rects': [...]}} for the lines whose text is in a cell of the drawn sheet, or
    None when the PDF is not a drawn sheet. A line of the minutes is built from one or more cells (the
    statement, the reason written under it, 담당자, 일정, 비고); a cell belongs to the line when its text is in
    the line, searched downward from the previous line's cell so that repeated words (pnt, 고객사) go to
    the right row. Cells of fewer than four letters are matched only on the same sheet row as a longer one."""
    source = source_of(pdf_path)
    if source is None:
        return None
    key = (str(source), source.stat().st_mtime)
    if key not in _CACHE:
        try:
            drawn = _draw(source.read_bytes())
        except Exception:
            drawn = None
        _CACHE.clear(); _CACHE[key] = drawn[1] if drawn else []
    cells = [(_squash(t), rect) for t, rect in _CACHE[key]]
    out = {}; cursor = 0
    for line in lines:
        want = _squash(line.get('text'))
        if len(want) < 4:
            continue
        found = next((i for i in list(range(cursor, len(cells))) + list(range(0, cursor)) if len(cells[i][0]) >= 4 and cells[i][0] in want), None)
        if found is None:
            continue
        rects = [cells[found][1]]; y = cells[found][1][1]; h = cells[found][1][3]
        for i in range(found - 1, -1, -1):          # the speaker cell left of the statement, on the same row
            text, rect = cells[i]
            if abs(rect[1] - y) >= h * 0.5: break
            if text and text in want: rects.insert(0, rect)
        for i in range(found + 1, len(cells)):
            text, rect = cells[i]
            same_row = abs(rect[1] - y) < h * 0.5
            below = len(text) >= 4 and text in want and text != cells[found][0]
            if same_row and text and text in want:
                rects.append(rect)
            elif below:
                rects.append(rect); found = i
            elif not same_row:
                break
        cursor = found + 1
        out[line['id']] = {'page': 1, 'rects': rects}
    return out
