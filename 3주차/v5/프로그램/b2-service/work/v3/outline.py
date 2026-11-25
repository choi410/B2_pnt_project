"""The whole meeting, section by section (AI 정리 tab).

The earlier screen showed only the sentences the model chose, so whatever it did not
choose was missing (one kickoff showed 4 of 29 lines). Here the code places every line of
the minutes under its own section heading, so nothing can be left out; the model's choice
only marks a sentence as a key point. Computed when the workspace is read: older analyses
get the full view without being analysed again.

  sectioned minutes : each line goes under its section (안건, 진행 현황, 논의, 결정, 추가 확인,
                      후속 조치); the header block (회의명, 일시, 참석자 ...) is listed as left out.
  free-form minutes : no headings to follow, so every sentence is listed under "전체 내용".
"""
import re

from work.v3.open_issues import _END, _ITEM, _META, _sections

VERSION = 'outline-1'
ORDER = [('agenda', '회의 안건'), ('status', '진행 현황'), ('discussion', '논의 내용'), ('decision', '결정 사항'),
         ('followup', '후속 조치'), ('pending', '추가 확인'), ('next', '다음 회의')]
_STATUS = re.compile(r'진행\s*현황|진행\s*상황|추진\s*현황')
_SPEAKER = re.compile(r'^([^:：|]{2,24})[:：]\s+(\S.*)$')
_MARK = re.compile(r'^\s*(\d+[.)]|[-•·])\s*')
_CELL = re.compile(r'^[A-Z]{1,2}\d+:\s*')


def _where(lines):
    """Section of each line, with 진행 현황 kept apart from the discussion."""
    where = _sections(lines)
    current = None
    for line in lines or []:
        if where.get(line['id']) == 'header':
            text = re.sub(r'^[\s\d.)\]\-•·#|]+', '', str(line.get('text') or '')).strip()
            current = 'status' if _STATUS.search(text) else None
        elif current == 'status':
            where[line['id']] = 'status'
    return where


def _groups(lines, where):
    """[(text, [line ids], section)]: one entry per line, a broken sentence joined to its start."""
    out = []
    for line in lines or []:
        section = where.get(line['id'])
        text = str(line.get('text') or '').strip()
        if section in (None, 'header') or not text:
            continue
        if out and out[-1][2] == section and not _END.search(out[-1][0]) and not _ITEM.match(text) \
                and not _SPEAKER.match(text):
            out[-1] = (out[-1][0] + ' ' + text, out[-1][1] + [line['id']], section)
        else:
            out.append((text, [line['id']], section))
    return out


def _stored(meeting):
    """What the analysis and its reviewers stored: {tuple(evidence): text}, the picked line ids,
    and whether a person edited the summary."""
    bundle = meeting.get('reviewed_bundle') or meeting.get('v3_bundle') or meeting.get('overview') or {}
    texts = {}; picked = set()
    for key in ('summary', 'decisions', 'candidates'):
        for item in bundle.get(key, meeting.get('candidates', []) if key == 'candidates' else []):
            evidence = tuple(item.get('evidence') or [])
            picked.update(evidence)
            if evidence:
                texts[evidence] = str(item.get('text') or item.get('description') or '')
    edited = any(e.get('action') == 'AI 정리 수정' for e in meeting.get('document_events') or [])
    return texts, picked, edited


def _result(meeting, mode, sections, coverage, converted=False):
    """The outline with the AI summary (brief) written at analysis time."""
    stored = meeting.get('brief') or {}
    shown_ids = {x['id'] for sec in sections for x in sec['items']}
    brief = [{'text': x['text'], 'evidence': x['evidence'], 'ids': x['ids']} for x in stored.get('items') or []
             if set(x.get('ids') or []) <= shown_ids] if stored.get('revision') in (None, meeting.get('revision')) else []
    return {'mode': mode, 'sections': sections, 'v': VERSION, 'coverage': coverage, 'converted': converted, 'brief': brief,
            'brief_written': meeting.get('brief') is not None}


def build(meeting, changes=()):
    """{'mode','sections':[{'kind','label','items':[...]}],'coverage':{'body','shown','left_out':[...],'header':[...]}}
    item: {'id','text','evidence','speaker','key','edited','changes':[{'id','title','review_state'}],
           'owner_name','task','start','due'}"""
    from work.v3.followups import parse_followup
    lines = meeting.get('lines') or []
    where = _where(lines)
    sectioned = any(v not in (None, 'header') for v in where.values())
    stored, picked, was_edited = _stored(meeting)
    overrides = meeting.get('outline_edits') or {}
    by_line = {}
    for e in changes or ():
        if e.get('review_state') == '제외':
            continue
        for ref in e.get('evidence') or []:
            by_line.setdefault(ref, []).append({'id': e.get('id'), 'title': e.get('title'), 'review_state': e.get('review_state'),
                                                '_words': re.findall(r'[가-힣A-Za-z]{2,}|\d+(?:[.,]\d+)*', str(e.get('title')) + ' ' + str(e.get('after')))})

    def item(text, ids, section, own=None):
        # own: the item's id when it is one sentence of a line (free-form minutes).
        key_id = own or ids[0]
        shown = _MARK.sub('', _CELL.sub('', text))
        speaker = None
        if section in ('discussion', 'all'):
            found = _SPEAKER.match(shown)
            if found and not re.search(r'\d{1,2}$', found[1]):  # "14:00" is a time, not a speaker
                speaker, shown = found[1].strip(), found[2].strip()
        edited = False
        if key_id in overrides:
            shown, edited = overrides[key_id], True
        elif not own and was_edited and tuple(ids) in stored and stored[tuple(ids)].strip() not in (text, shown):
            shown, edited = stored[tuple(ids)].strip(), True
        linked = list({c['id']: c for i in ids for c in by_line.get(i, [])}.values())
        if own:
            # One free-form line holds many sentences: keep a record only on the sentence that names it.
            linked = [c for c in linked if sum(w in text for w in c['_words']) * 2 >= len(c['_words'])]
        linked = [{k: v for k, v in c.items() if k != '_words'} for c in linked]
        key = bool(linked) if section == 'all' else (section in ('decision', 'followup', 'pending') or bool(set(ids) & picked) or bool(linked))
        out = {'id': key_id, 'text': shown, 'evidence': ids, 'speaker': speaker, 'edited': edited, 'changes': linked,
               'key': key and not text.startswith('※')}
        if section == 'followup':
            out.update(parse_followup(text) or {})
        return out

    if sectioned:
        grouped = {}
        for text, ids, section in _groups(lines, where):
            grouped.setdefault(section, []).append(item(text, ids, section))
        sections = [{'kind': kind, 'label': label, 'items': grouped[kind]} for kind, label in ORDER if grouped.get(kind)]
        used = {i for s in sections for x in s['items'] for i in x['evidence']}
        rest = [l for l in lines if l['id'] not in used and where.get(l['id']) != 'header' and str(l.get('text') or '').strip()]
        # Lines above the first heading are the header block (회의명, 일시, 참석자 ...).
        head = [{'id': l['id'], 'text': l['text']} for l in rest if where.get(l['id']) is None]
        left = [{'id': l['id'], 'text': l['text']} for l in rest if where.get(l['id']) is not None]
        mode = 'sections'
    else:
        # Free-form minutes. With a stored layout (the model gave every sentence a section, see
        # freeform.py) they are shown in the standard format; without one, as a plain list.
        from work.v3.freeform import sentences as split
        stored_layout = meeting.get('layout') or {}
        layout = stored_layout.get('items') if stored_layout.get('revision') in (None, meeting.get('revision')) else None
        found = split(lines)
        in_sentence = {line_id for _, line_id, _ in found}
        left = []
        head = [{'id': l['id'], 'text': l['text']} for l in lines if str(l.get('text') or '').strip() and l['id'] not in in_sentence]
        if layout:
            grouped = {}
            for sid, line_id, text in found:
                section = layout.get(sid, 'discussion')
                if section == 'header':
                    head.append({'id': sid, 'text': text})
                else:
                    grouped.setdefault(section, []).append(item(text, [line_id], section, own=sid))
            sections = [{'kind': kind, 'label': label, 'items': grouped[kind]} for kind, label in ORDER if grouped.get(kind)]
            mode = 'sections'
        else:
            items = [item(text, [line_id], 'all', own=sid) for sid, line_id, text in found]
            sections = [{'kind': 'all', 'label': '전체 내용', 'items': items}] if items else []
            mode = 'flat'
        shown = sum(len(sec['items']) for sec in sections)
        return _result(meeting, mode, sections, {'body': shown, 'shown': shown, 'left_out': left, 'header': head, 'unit': '문장'},
                       converted=bool(layout))
    # body = every line of the minutes except section headings and the header block.
    body = sum(1 for l in lines if str(l.get('text') or '').strip() and where.get(l['id']) != 'header') - len(head)
    return _result(meeting, mode, sections, {'body': body, 'shown': body - len(left), 'left_out': left, 'header': head, 'unit': '행'})


def attach(meetings, changes):
    """Set m['outline'] on each meeting dict (a failure leaves None, and the screen falls back)."""
    by_meeting = {}
    for e in changes or ():
        by_meeting.setdefault(e.get('meeting_id'), []).append(e)
    for m in meetings:
        try:
            m['outline'] = build(m, by_meeting.get(m['id'], []))
        except Exception:
            m['outline'] = None
