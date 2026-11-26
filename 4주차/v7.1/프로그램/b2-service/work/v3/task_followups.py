"""Read task assignments and their deadlines from current, authorized minutes."""
import re
from datetime import date
from fastapi import HTTPException

from work.v17.evidence_text import content_line, coverage, normalized, topic_terms
from work.v17.retrieval import document_lines
from work.v3.answer_meaning import event_dates
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
ORIGINAL_DEADLINE = re.compile(
    r'(?=.*(?:원래|당초|처음))(?:(?:그럼|그러면)\s*)?(?:그|이|해당)\s*(?:사람|분|담당자|업무)(?:의|은|는)?\s*'
    r'(?:(?:원래|당초|처음)\s*)?(?:제출\s*일(?:자)?|(?:제출\s*)?기한|마감\s*일)(?:은|는|이|가)?\s*'
    r'(?:(?:원래|당초|처음)\s*)?언제(?:였어(?:요)?|였지|였나요|였습니까|였는지)?[?!. ]*')
ASSIGNMENT = re.compile(
    r'(?P<topic>.+?)\s+(?:누가\s*언제\s*까지|언제\s*까지\s*누가'
    r'|담당자?\s*(?:와|과|랑|이랑|하고|및)\s*(?:제출\s*)?기한|기한\s*(?:과|이랑|하고|및)\s*담당자?)'
    r'(?=\s|은|는|이|을|를|[?!.,]|$)(?P<request>.*)')
ROLE = re.compile(r'담당|맡(?:기로|는다|았다)|책임자')
ASSIGNEE_TITLE = re.compile(r'[가-힣]{2,5}\s+(?:사원|대리|과장|차장|팀장|책임|선임|부장|대표|매니저)(?:[가은는이]|\s|$)')
UNASSIGNED = re.compile(r'미정|미지정|정하지\s*(?:못|않)|담당자.{0,6}없|정할\s*예정')
DEADLINE = re.compile(r'기한|까지\s*(?:제출|작성|준비|내기로|마치|완료|공유|확인|보내)')
ASSIGNMENT_COMMITMENT = re.compile(
    r'(?:^|[은는을를]\s+)[가-힣]{2,5}[이가은는]\s+.{0,105}?'
    r'(?:제출|작성|준비|완료|공유|확인|검토)하기로\s*(?:했|합의했|결정했)')
ACTUAL_SUBMISSION_DATE = re.compile(
    r'(?:(?:그럼|그러면)\s*)?(?:실제(?:로)?\s*)?(?:낸\s*(?:날|날짜)|제출한\s*(?:날|날짜)|실제\s*제출일)'
    r'(?:은|는|이|가)?\s*(?:언제(?:야|였어|예요|인가요|였나요)?|알려\s*(?:줘|주세요))?[?!. ]*')
SUBMISSION_TIMING = re.compile(
    r'(?:(?:그럼|그러면)\s*)?(?:기한보다\s*)?(?:(?:하루|이틀|사흘|며칠|\d+\s*일)\s*)?'
    r'(?:늦은|빠른)\s*(?:거(?:야|예요|지|나요)|건가요)[?!. ]*')
SUBMISSION_DEADLINE = re.compile(r'제출\s*기한|까지\s*제출하기로\s*(?:했|합의했|결정했)')


def assignment_record(text):
    return ROLE.search(text) or ASSIGNEE_TITLE.search(text) or ASSIGNMENT_COMMITMENT.search(text)


def with_task_sources(result, project, rows, mode, message):
    points=[]
    sources=[]
    for doc,line,quote in rows:
        sid=f'S{len(sources)+1}'
        source=source_for(doc,project,sid,[line])
        source['exact_highlights']=source['line_ids']
        sources.append(source)
        points.append({'text':quote,'project_id':project['id'],'project_name':project['name'],'sources':[sid]})
    return {**result,'kind':'documents','mode':mode,'answerable':True,'points':points,
            'sources':sources,'message':message}


def submission_answer(w,c,actor,question,previous,project_id,meeting_id):
    prior=(previous or {}).get('context',{})
    mode=(previous or {}).get('job',{}).get('result',{}).get('mode')
    actual=ACTUAL_SUBMISSION_DATE.fullmatch(question.strip())
    compare=SUBMISSION_TIMING.fullmatch(question.strip())
    if not prior.get('assignment_topic') or not (
        actual and mode in ('task_deadline','task_submission_date') or compare and mode=='task_submission_date'
    ):
        return None
    ids=prior.get('project_ids',[])
    meeting_ids=prior.get('meeting_ids',[])
    context={'query':question,'project_ids':[],'label':''}
    unavailable={'kind':'clarification','mode':'task_reference','answerable':False,'points':[],'sources':[],
                 'message':'어느 업무의 실제 제출일을 확인할까요? 업무 이름을 알려주세요.'}
    if len(ids)!=1 or (project_id and project_id!=ids[0]) or (meeting_id and meeting_ids!=[meeting_id]):
        return context,unavailable
    tools=ReadTools(w,c,actor)
    try:
        project=tools.projects(ids)[0]
        docs=tools.meetings(ids,meeting_ids=meeting_ids or None)
    except HTTPException:
        return context,unavailable
    scope=prior.get('time_scope',{})
    task=prior['assignment_topic']
    terms=topic_terms(without_date_scope(strip_labels(task,[project]),scope))
    if not terms:
        return context,unavailable
    context.update(project_ids=ids,project_id=ids[0],label=project['name'],assignment_topic=task,
                   meeting_ids=meeting_ids,time_scope=scope)
    submissions={}
    deadlines={}
    for doc in docs:
        if not in_scope(doc,scope):
            continue
        for line in document_lines(doc):
            if not content_line(line['text']):
                continue
            for clause in re.split(r'(?<=[.!?])\s+',line['text']):
                if coverage(clause,terms)!=1:
                    continue
                matches=list(DATE.finditer(clause))
                if len(matches)!=1:
                    continue
                row=(doc,line,clause)
                for action,year,month,day in event_dates(clause):
                    if action=='제출':
                        submissions.setdefault((year,month,day),row)
                if compare and SUBMISSION_DEADLINE.search(clause) and not re.search(r'예정|제안|요청|미정|철회|취소|보류|않|못',clause):
                    parts=tuple(int(value) if value else None for value in matches[0].group('year','month','day'))
                    deadlines.setdefault(parts,row)
    if len(submissions)!=1:
        return context,{**unavailable,'kind':'documents','message':'같은 업무의 실제 제출일을 원문에서 하나로 확인하지 못했어요.'}
    submitted,submission=next(iter(submissions.items()))
    if not compare:
        return context,with_task_sources(unavailable,project,[submission],'task_submission_date',
                                         '회의록에 기록된 실제 제출일이에요.')
    if len(deadlines)!=1:
        return context,{**unavailable,'kind':'documents','message':'제출 기한이 명확하지 않아 실제 제출일과 비교하기 어려워요.'}
    due,deadline=next(iter(deadlines.items()))
    try:
        delta=(date(*submitted)-date(*due)).days
    except (TypeError, ValueError):
        return context,{**unavailable,'kind':'documents','message':'두 날짜의 연·월·일을 확인할 수 있어야 비교할 수 있어요.'}
    message='제출 기한 당일에 제출했어요.' if not delta else f'기한보다 {abs(delta)}일 {"늦게" if delta>0 else "일찍"} 제출했어요.'
    return context,with_task_sources(unavailable,project,[deadline,submission],'task_submission_timing',message)


def resolve(w, c, actor, question, previous, project_id=None, meeting_id=None):
    submission=submission_answer(w,c,actor,question,previous,project_id,meeting_id)
    if submission is not None:
        return submission
    history = OWNER_HISTORY.fullmatch(question.strip())
    original = ORIGINAL_DEADLINE.fullmatch(question.strip())
    deadline = original or PERSON_DEADLINE.fullmatch(question.strip())
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
    if deadline and (project_id and project_id not in prior.get('project_ids',[])
                     or meeting_id and meeting_id not in prior.get('meeting_ids',[])):
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
                role=assignment_record(clause)
                if coverage(clause,terms)==1 and (role or (assignment or original) and DEADLINE.search(clause)) and doc.get('date'):
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
        owners=[row for row in records if assignment_record(row[2])]
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
        chosen=on(records[0][0]['date']) if original else latest
        if len(chosen)!=1 or UNASSIGNED.search(chosen[0][2]) or not DEADLINE.search(chosen[0][2]) or len(list(DATE.finditer(chosen[0][2])))!=1:
            result['message']='해당 업무의 담당자와 기한을 원문에서 함께 확인하지 못했어요. 업무나 담당자 이름을 알려주세요.'
            return context,result
        selected=chosen
    else:
        first=on(records[0][0]['date'])
        selected=first+latest if len(first)==len(latest)==1 and first!=latest else []
        if not selected:
            result['message']='처음과 현재의 담당자를 모두 비교할 수 있는 원문을 찾지 못했어요.'
            return context,result
    mode='task_deadline' if deadline or assignment else 'task_owner_history'
    message=('조회한 회의록에서 처음 확인되는 제출 기한이에요.' if original else
             '회의록에 기록된 담당자와 기한이에요.' if deadline or assignment else '처음과 최근 회의의 담당 기록이에요.')
    return context,with_task_sources(result,project,selected,mode,message)
