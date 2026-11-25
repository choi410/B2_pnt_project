"""Read agenda overviews from registered documents, retaining original line IDs.

An agenda question asks what was discussed, not for a passage containing the
literal word 'agenda', nor for the current approval/completion of those topics.
"""
import re
from work.v3.query_intent import strip_labels
from work.v17.evidence_text import content_line, topic_terms, HEAD, META
from work.v17.retrieval import document_lines

AGENDA = r'아젠다|어젠다|agenda|안건|논의\s*주제|회의\s*주제'
FILLER = {'주요', '주된', '핵심', '중요', '중요한', '무슨', '뭐지', '뭔지', '뭐였어',
          '무엇인가요', '무엇이야', '무엇인지', '다뤘어', '다루는', '다루었던', '다뤘던'}
DECISION_HEADING = re.compile(r'^(?:(?:주요\s*)?(?:결정|합의)\s*(?:사항|내용|결과)|회의\s*결과)\s*[:：]?$')
OTHER_HEADING = re.compile(r'^(?:진행\s*현황|주요\s*안건|논의\s*사항|추가\s*확인\s*사항|기타)\s*[:：]?$')


def intent(question, projects=()):
    if summary_intent(question,projects):return True
    q = strip_labels(question, projects)
    if not re.search(AGENDA, q, re.I): return False
    if re.search(r'변경|변동|완료|승인|확정|합의|결정|담당|기한|납기|누가|왜',q):return False
    # Keep focused questions (e.g. camera ownership, agenda approval) with the
    # normal evidence reader. Only a general list/overview uses this path.
    residual = re.sub(AGENDA, ' ', q, flags=re.I)
    residual = re.sub(r'(?<![가-힣])(?:는|은|이|가|을|를|의)(?![가-힣])', ' ', residual)
    return not [t for t in topic_terms(residual) if t not in FILLER]


def summary_intent(question,projects=()):
    """General meeting summaries read the body, not just an agenda heading."""
    from work.v3.query_intent import ATTRIBUTE
    q=strip_labels(question,projects)
    return bool(re.search(r'요약|핵심.*정리',q) and not re.search(ATTRIBUTE+r'|왜|이유|변경|담당|완료',q,re.I))


def section_label(text):
    return re.sub(r'^\s*[#*\d.)\-·•]+\s*', '', text).strip().strip('* ')


def decision_section(doc):
    """Read the original decision section without interpreting its outcomes."""
    selected = []
    active = False
    for line in document_lines(doc):
        label = section_label(line['text'])
        if DECISION_HEADING.fullmatch(label):
            active = True
        elif HEAD.match(label) or META.match(label) or OTHER_HEADING.fullmatch(label):
            active = False
        elif active:
            selected.append(line)
    # Only fall back to a compact, complete section. Cutting at a line limit
    # could drop the end of a decision or an exception on its next line.
    return selected if len(selected) <= 5 and sum(len(l['text']) for l in selected) <= 700 else []


def lines_for(doc,summary=False):
    lines = document_lines(doc)
    selected = []; active = False; explicit = False
    for line in lines:
        label = section_label(line['text'])
        heading = re.match(r'^(?:회의\s*안건|주요\s*안건|안건|agenda|아젠다|어젠다)\s*(?:[:：|]\s*(.*))?$', label, re.I)
        if heading:
            active = explicit = True
            if heading[1]: selected.append(line)
            continue
        if active and (HEAD.match(label) or META.match(label) or re.fullmatch(
                r'(?:주요\s*)?(?:논의\s*(?:내용|사항)|결정\s*사항|후속\s*조치|추가\s*확인\s*사항|회의\s*결과|기타)\s*[:：]?', label)):
            active = False
        if active: selected.append(line)
    if summary or not selected:
        # Unstructured minutes can still be summarized. Do not require users
        # to use a specific template or mistake an empty heading for evidence.
        selected = [l for l in lines if content_line(l['text'])]
        explicit = False
    kept = []; size = 0
    for line in selected:
        if kept and size + len(line['text']) > 1800: break
        kept.append(line); size += len(line['text'])
    return kept, explicit, len(kept) < len(selected)


def scope_documents(docs, question):
    ordered = sorted(docs, key=lambda d: (d.get('date', ''), d['meeting_id']), reverse=True)
    if re.search(r'최신|최근|마지막|첫|처음|오래된', question):
        dated = [d for d in ordered if d.get('date')]
        if dated:
            date = dated[-1]['date'] if re.search(r'첫|처음|오래된', question) else dated[0]['date']
            ordered = [d for d in dated if d['date'] == date]
    return ordered


def retrieve(docs, question, limit=8):
    """Caller supplies only authorized, registered and date-filtered documents."""
    ordered = scope_documents(docs, question)
    summary = summary_intent(question)
    result = []
    for doc in ordered:
        lines, explicit, partial = lines_for(doc,summary)
        if not lines: continue
        result.append({k: v for k, v in doc.items() if k != 'body'} | {
            'line_ids': [l['id'] for l in lines], 'text': '\n'.join(l['text'] for l in lines),
            'score': 1.0, 'agenda_explicit': explicit, 'agenda_partial': partial})
        if summary:
            result[-1]['decision_lines'] = decision_section(doc)
        if len(result) >= limit: break
    return result


def source_fallback(sources):
    """Use explicitly labeled original sections if summary generation fails."""
    points = []
    for source in sources:
        if decisions := source.get('decision_lines'):
            source['text'] = '\n'.join(line['text'] for line in decisions)
            source['line_ids'] = [line['id'] for line in decisions]
            source['exact_highlights'] = source['line_ids']
            intro = ' 회의의 결정 사항 원문\n'
        elif source.get('agenda_explicit'):
            intro = ' 회의에 기록된 안건:\n'
        else:
            continue
        points.append({
            'text': (source.get('date') or '날짜 미정') + intro + source['text'],
            'project_id': source['project_id'], 'project_name': source['project_name'],
            'sources': [source['id']], 'verification': 'source_quote',
        })
    return points
