"""Read task assignments and their deadlines from current, authorized minutes."""
import re

from work.v17.evidence_text import content_line, coverage, normalized, topic_terms
from work.v17.retrieval import document_lines
from work.v3.chat_tools import ReadTools
from work.v3.query_intent import strip_labels
from work.v3.question_policy import name_matches
from work.v3.question_scope import DATE, in_scope, plan_question
from work.v3.topic_overview import without_date_scope
from work.v3.topic_search import source_for


OWNER_HISTORY = re.compile(
    r'(?P<topic>.+?)\s*담당(?:자)?(?:은|는|이|가)?\s*(?:처음|초기|당초)(?:에는|엔|부터)?'
    r'\s*(?:과|와|이랑|하고|,)?\s*(?:현재|지금|최신)(?:이|은|는|의|에)?'
    r'\s*(?:어떻게|뭐가|무엇이)?\s*(?:달라졌|바뀌었|변했)(?:어|나요|지|어요|습니까)?[?!. ]*')
PERSON_DEADLINE = re.compile(
    r'(?:(?:그럼|그러면)\s*)?(?:그|이|해당)\s*(?:사람|분|담당자)(?:의|은|는)?\s*'
    r'(?:(?:업무|제출)\s*)?(?:기한(?:만|은|도)?|언제까지(?:야|인가요)?)\s*'
    r'(?:다시\s*)?(?:알려\s*(?:줘(?:요)?|주세요)|보여\s*줘(?:요)?)?[?!. ]*')
ASSIGNMENT = re.compile(
    r'(?P<topic>.+?)\s+(?:누가\s*언제\s*까지|언제\s*까지\s*누가'
    r'|담당자?\s*(?:와|과|랑|이랑|하고|및)\s*기한|기한\s*(?:과|이랑|하고|및)\s*담당자?)'
    r'(?=\s|은|는|이|을|를|[?!.,]|$)(?P<request>.*)')
ROLE = re.compile(r'담당|맡(?:기로|는다|았다)|책임자')
ASSIGNEE_TITLE = re.compile(r'[가-힣]{2,5}\s+(?:사원|대리|과장|차장|팀장|책임|선임|부장|대표|매니저)(?:[가은는이]|\s|$)')
UNASSIGNED = re.compile(r'미정|미지정|정하지\s*(?:못|않)|담당자.{0,6}없|정할\s*예정')
DEADLINE = re.compile(r'기한|까지\s*(?:제출|작성|준비|내기로|마치|완료|공유|확인|보내)')


def resolve(w, c, actor, question, previous, project_id=None, meeting_id=None):
    history = OWNER_HISTORY.fullmatch(question.strip())
    deadline = PERSON_DEADLINE.fullmatch(question.strip())
    assignment = ASSIGNMENT.fullmatch(question.strip())
    if assignment and re.search(r'각각|각자|둘\s*다|비교|처음|이력|변경',question):
        assignment=None
    if not history and not deadline and not assignment:
        return None
    prior = (previous or {}).get('context', {})
    history_of_task = OWNER_HISTORY.fullmatch((previous or {}).get('question','').strip())
    explicit=history or assignment
    task = explicit['topic'] if explicit else prior.get('assignment_topic') or (history_of_task['topic'] if history_of_task else '')
    context = {'query':question,'project_ids':[],'time_scope':{},'label':''}
    result = {'kind':'clarification','mode':'task_reference','answerable':False,'points':[],'sources':[]}
    clarification = '어떤 업무의 담당자와 기한을 확인할까요? 프로젝트나 업무 이름을 알려주세요.'
    result['message'] = clarification
    fallback=None if assignment else (context,result)
    if not task:
        return fallback
    tools = ReadTools(w,c,actor)
    named = name_matches(tools.projects(),task)
    if deadline and project_id and project_id not in prior.get('project_ids',[]):
        return context,result
    ids = [project_id] if project_id else [p['id'] for p in named] or prior.get('project_ids',[])
    if len(ids)!=1:
        return fallback
    project = tools.projects(ids)[0]
    meeting_ids=[meeting_id] if meeting_id else prior.get('meeting_ids',[]) if deadline else []
    docs=tools.meetings(ids,meeting_ids=meeting_ids or None)
    scope=prior.get('time_scope',{}) if deadline else {}
    if assignment:
        plan=plan_question(question,docs)
        if plan.get('message'):
            return fallback
        scope={key:plan[key] for key in ('mode','start','end')}
    terms = topic_terms(without_date_scope(strip_labels(task,[project]),scope))
    if not terms:
        return fallback
    context.update(project_ids=ids,project_id=ids[0],label=project['name'],assignment_topic=task)
    # Preserve any known cutoff for a short reference to an earlier task.
    if scope:
        context['time_scope']=scope
    context['meeting_ids']=meeting_ids
    records=[]
    for doc in docs:
        if not in_scope(doc,scope):
            continue
        for line in document_lines(doc):
            if not content_line(line['text']):
                continue
            for clause in re.split(r'(?<=[.!?])\s+',line['text']):
                role=ROLE.search(clause) or ASSIGNEE_TITLE.search(clause)
                if coverage(clause,terms)==1 and (role or assignment and DEADLINE.search(clause)) and doc.get('date'):
                    records.append((doc,line,clause))
    records.sort(key=lambda r:(r[0]['date'],r[0]['meeting_id']))
    if not records:
        return fallback

    def on(day):
        return list({normalized(row[2]):row for row in records if row[0]['date']==day}.values())

    latest=on(records[-1][0]['date'])
    if assignment:
        # A later progress note may repeat the deadline without naming the
        # assignee. Retain the last explicit assignment, scoped to this task.
        owners=[row for row in records if ROLE.search(row[2]) or ASSIGNEE_TITLE.search(row[2])]
        if not owners:
            return None
        day=owners[-1][0]['date']
        current=list({normalized(row[2]):row for row in owners if row[0]['date']==day}.values())
        if len(current)!=1 or UNASSIGNED.search(current[0][2]) or len(latest)!=1:
            return None
        assigned,due=current[0],latest[0]
        due_dates=list(DATE.finditer(due[2]))
        if not DEADLINE.search(due[2]) or len(due_dates)!=1:
            return None
        selected=[assigned] if assigned==due else [assigned,due]
    elif deadline:
        if len(latest)!=1 or UNASSIGNED.search(latest[0][2]) or not DEADLINE.search(latest[0][2]) or len(list(DATE.finditer(latest[0][2])))!=1:
            result['message']='해당 업무의 담당자와 기한을 원문에서 함께 확인하지 못했어요. 업무나 담당자 이름을 알려주세요.'
            return context,result
        selected=latest
    else:
        first=on(records[0][0]['date'])
        selected=first+latest if len(first)==len(latest)==1 and first!=latest else []
        if not selected:
            result['message']='처음과 현재의 담당자를 모두 비교할 수 있는 원문을 찾지 못했어요.'
            return context,result
    points=[];sources=[]
    for doc,line,quote in selected:
        sid=f'S{len(sources)+1}'
        source=source_for(doc,project,sid,[line])
        source['exact_highlights']=source['line_ids']
        sources.append(source)
        points.append({'text':quote,'project_id':project['id'],'project_name':project['name'],'sources':[sid]})
    result.update(kind='documents',mode='task_deadline' if deadline or assignment else 'task_owner_history',answerable=True,
                  points=points,sources=sources,
                  message='회의록에 기록된 담당자와 기한이에요.' if deadline or assignment else '처음과 최근 회의의 담당 기록이에요.')
    return context,result
