"""Read projects by the contents of their registered meeting records."""
import re

from work.v3.outline import build as build_outline
from work.v3.question_scope import in_scope, plan_question
from work.v3.query_intent import label_pattern, leading_aliases, name_key, strip_labels
from work.v3.source_terms import resolve
from work.v3.topic_search import source_for
from work.v17.evidence_text import coverage
from work.v17.retrieval import document_lines, registered_document


USAGE_QUERY = re.compile(
    r'(?P<topic>[^?!.]{2,65}?)(?:을|를)?\s*(?P<actual>실제로\s*)?'
    r'(?:(?:사용|적용|도입|채택)\s*(?:했던|했었던|했는|하였던|된|하는|한|하고\s*있는|중인)|쓴|쓰는)\s*'
    r'프로젝트(?:가|는|를|을)?\s*(?:어떤\s*거야|뭐야|뭐가\s*있어|알려\s*(?:줘|주세요)|'
    r'(?:찾아|보여)\s*(?:줘|주세요)|목록|있(?:어|나요))?'
)
SUMMARY_QUERY = re.compile(
    r'(?:(?P<name>.+?)\s*)?프로젝트(?:의|를|는|은)?\s*'
    r'(?:(?:전체|전반|핵심|개요|한\s*번에)(?:를|을|만)?\s*)?'
    r'(?:요약|정리)(?:해\s*(?:줘|주세요)|\s*(?:부탁해|부탁해요))?'
)
ACTUAL = re.compile(r'(?:사용|적용|가동|생산|압연|운전)\s*(?:했|하였|함|중|하고\s*있)')
PROPOSED = re.compile(r'검토|요청|제안|예정|계획|보류|미정|미적용|미사용|철회|않|못|조건|가능|필요')
AGREED = re.compile(r'합의|확정|유지|기준|결정|하기로')
USAGE_LABELS = {'actual':'사용·적용 기록', 'agreed':'합의·기준', 'proposed':'요청·검토·계획', 'mention':'관련 기록'}


def intent(question):
    text = question.strip().rstrip('?! .')
    if match := USAGE_QUERY.fullmatch(text):
        topic = re.sub(r'\s*(?:을|를)$', '', match['topic']).strip()
        return {'mode':'project_usage','topic':topic,'actual':bool(match['actual'])}
    if match := SUMMARY_QUERY.fullmatch(text):
        return {'mode':'project_summary','name':(match['name'] or '').strip()}
    return None


def _named_projects(projects, name):
    key = name_key(name)
    exact = [p for p in projects if key in (name_key(p['name']), name_key(p['id']))]
    return exact or [p for p in projects if any(re.fullmatch(label_pattern(a),name,re.I) for a in leading_aliases(p))]


def _documents(w, c, ids, question, meeting_id):
    docs = [doc for meeting in w.all_records(c,'meeting') if meeting['project_id'] in ids
            and (not meeting_id or meeting['id']==meeting_id) and (doc:=registered_document(meeting))]
    plan = plan_question(question,docs)
    docs = [doc for doc in docs if in_scope(doc,plan)]
    docs.sort(key=lambda doc:(doc.get('date') or '',doc['meeting_id']),reverse=True)
    return docs, plan


def _evidence(doc):
    lines = document_lines(doc)
    refs = {line['id']:line for line in lines}
    sections = build_outline({'lines':lines})['sections']
    return [(section['kind'],item['text'],[refs[ref] for ref in item['evidence'] if ref in refs])
            for section in sections for item in section['items'] if item['evidence']]


def _kind(text):
    if PROPOSED.search(text):return 'proposed'
    if ACTUAL.search(text):return 'actual'
    if AGREED.search(text):return 'agreed'
    return 'mention'


def _add(points, sources, doc, project, heading, excerpts):
    sid = f'S{len(sources)+1}'
    lines = list({line['id']:line for _,_,rows in excerpts for line in rows}.values())
    source = source_for(doc,project,sid,lines)
    source['exact_highlights'] = source['line_ids']
    sources.append(source)
    text = heading + '\n' + '\n'.join(f'• {label} · {value}' for label,value,_ in excerpts)
    points.append({'text':text,'sources':[sid],'project_id':project['id'],'project_name':project['name'],
                   'verification':'source_quote'})


def _usage(projects, docs, spec, points, sources):
    topic = spec['topic']
    # '방식' identifies what about the process was asked. The process still
    # needs a literal or source-defined match in each cited original sentence.
    process = re.sub(r'\s+방식$', '', topic)
    explicit_use = False
    for project in projects:
        scoped = [doc for doc in docs if doc['project_id']==project['id']]
        terms = resolve(process,scoped)
        if terms['message'] or not terms['terms']:continue
        picked = {}
        for doc in scoped:
            for section, text, lines in _evidence(doc):
                if section=='agenda':continue
                for sentence in re.split(r'(?<=[.!?。])\s+',text):
                    if coverage(sentence,terms['terms'])<1:continue
                    status = _kind(sentence)
                    if spec['actual'] and status!='actual':continue
                    picked.setdefault(status,(doc,USAGE_LABELS[status],sentence,lines))
        for status in USAGE_LABELS:
            if status not in picked:continue
            explicit_use |= status=='actual'
            doc,label,text,lines = picked[status]
            _add(points,sources,doc,project,doc.get('date') or '회의일 미정',[(label,text,lines)])
    if points:
        count = len({p['project_id'] for p in points})
        message = f'‘{topic}’ 관련 기록이 있는 프로젝트는 {count}개예요.'
        if not explicit_use:
            message += ' 실제 사용 여부는 확인되지 않아 회의록에 적힌 상태를 함께 표시했어요.'
        return message
    target = '실제 사용을 명시한' if spec['actual'] else '관련 내용이 적힌'
    return f'조회한 회의록에서 ‘{topic}’ {target} 프로젝트를 확인하지 못했어요.'


def _summary(projects, docs, points, sources):
    labels = {'status':'진행', 'decision':'결정', 'pending':'추가 확인', 'followup':'후속 조치',
              'discussion':'논의', 'all':'본문', 'agenda':'안건', 'next':'다음 회의'}
    for project in projects:
        selected = [doc for doc in docs if doc['project_id']==project['id']][:5]
        for doc in reversed(selected):
            rows = _evidence(doc)
            excerpts = []
            for section in ('status','decision','pending','followup','discussion','all','agenda','next'):
                if section in ('discussion','all','agenda','next') and excerpts:break
                limit = 3 if section in ('decision','all') else 1
                excerpts.extend([(labels[section],text,lines) for kind,text,lines in rows if kind==section][:limit])
            if excerpts:
                date = doc.get('date') or '회의일 미정'
                _add(points,sources,doc,project,f'{date} · {doc["title"]}',excerpts)
    if not points:
        return '조회 범위에서 요약할 수 있는 등록 회의록 본문을 찾지 못했어요.'
    if len(sources)<len(docs):
        return f'등록 회의록 {len(docs)}건 중 {len(sources)}건의 핵심 내용을 정리했어요.'
    return f'등록 회의록 {len(docs)}건을 기준으로 프로젝트의 핵심 내용을 정리했어요.'


def answer(w,c,actor,question,spec,available,project_id=None,meeting_id=None):
    available = [p for p in available if not p.get('deleted_at') and actor['id'] in p['members']]
    if spec['mode']=='project_summary':
        name = spec['name']
        broad = name in ('전체','모든','각')
        projects = _named_projects(available,name) if name and not broad else available
        if project_id:
            selected = w.project(c,project_id,actor)
            projects = [p for p in projects if p['id']==selected['id']]
        if len(projects)!=1 and not broad:
            choices = [{'id':p['id'],'name':p['name']} for p in projects]
            message = '어느 프로젝트를 요약할까요?' if choices else '요약할 프로젝트를 찾지 못했어요. 프로젝트 이름이나 코드를 확인해 주세요.'
            return available, {'kind':'clarification','mode':'project_summary','answerable':False,
                               'message':message,'projects':choices,'points':[],'sources':[]}
    else:
        projects = [w.project(c,project_id,actor)] if project_id else available

    docs,plan = _documents(w,c,{p['id'] for p in projects},strip_labels(question,projects),meeting_id)
    points, sources = [], []
    if plan.get('message'):
        message=plan['message']
    elif spec['mode']=='project_summary':
        message=_summary(projects,docs,points,sources)
    else:
        message=_usage(projects,docs,spec,points,sources)
    notice = plan.get('notice') or '접근 가능한 등록 회의록을 대상으로 조회했어요.'
    if spec['mode']=='project_summary' and len(sources)<len(docs):
        notice += f' 본문을 인용한 회의록은 {len(sources)}건이며, 프로젝트당 최근 5건까지 요약해요.'
    return projects, {'kind':'documents','mode':spec['mode'],'answerable':bool(points),'points':points,'sources':sources,
                      'message':message,'notice':notice,'searched_projects':len(projects),'searched_meetings':len(docs)}
