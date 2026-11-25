"""Resolve a request for the other of two options found in registered minutes."""
import re

from fastapi import HTTPException

from work.v17.evidence_text import content_line
from work.v17.retrieval import document_lines
from work.v3.chat_state import reference_lines
from work.v3.chat_tools import ReadTools
from work.v3.conversation_context import interpreted_subject
from work.v3.query_intent import label_pattern, name_key, normalize
from work.v3.question_scope import describe_scope, in_scope
from work.v3.topic_search import source_for


OTHER_SIDE = re.compile(
    r'(?:(?:그럼|그러면|그렇다면)\s*)?(?:(?:나머지|다른)\s*(?:한\s*)?|반대\s*)쪽(?:은|는|도|이|의)?\s*'
    r'(?:얼마(?:야|인가요|예요)?|뭐야|알려\s*(?:줘(?:요)?|주세요)|보여\s*줘(?:요)?)?[?!.\s]*')


def resolve(w, c, actor, question, past, project_id=None, meeting_id=None):
    if not OTHER_SIDE.fullmatch(question.strip()):
        return None
    result = {'kind':'clarification','mode':'paired_reference','answerable':False,'points':[],'sources':[],
              'message':'앞에서 비교한 두 대상을 원문에서 확인하지 못했어요. 확인할 항목 이름을 알려주세요.'}
    context = {'query':question,'project_ids':[],'label':'','time_scope':{}}
    turns = [m for m in past if m.get('job',{}).get('result',{}).get('mode') not in ('social','scope_explanation')]
    if len(turns)<2:
        return context,result
    overview,focused = turns[-2:]
    old,selected = overview.get('context',{}),focused.get('context',{})
    ids=old.get('project_ids',[])
    if len(ids)!=1 or selected.get('project_ids')!=ids or project_id and project_id!=ids[0]:
        return context,result
    if any(m.get('state')!='done' or not m.get('job',{}).get('result',{}).get('answerable') for m in (overview,focused)):
        return context,result
    scope=old.get('time_scope',{})
    if scope!=selected.get('time_scope',{}):
        return context,result
    meeting_ids=old.get('meeting_ids',[])
    if meeting_ids!=selected.get('meeting_ids',[]) or meeting_id and meeting_ids!=[meeting_id]:
        return context,result

    # Recover the common topic from vocabulary selected out of the user's
    # original request. Neither the comparison's prose nor a past value is data.
    words=interpreted_subject(overview,ids).split()
    if not words:
        return context,result
    last=words[-1]
    words[-1]=re.sub(r'(?<=[가-힣]{2})(?:은|는|을|를|이|가|의)$','',last)
    topic=' '.join(words)
    form=re.compile(r'(?<!\w)(?P<label>[가-힣a-zA-Z0-9][가-힣a-zA-Z0-9·-]*)\s+'
                    +r'\s*'.join(re.escape(word) for word in words)
                    +r'(?=$|[^가-힣a-zA-Z0-9]|은|는|이|가|을|를|의|으로|에)',re.I)
    try:
        broad_lines=reference_lines(w,c,actor,overview,ids[0])
        focused_lines=reference_lines(w,c,actor,focused,ids[0])
        tools=ReadTools(w,c,actor)
        project=tools.projects(ids)[0]
        docs=tools.meetings(ids,meeting_ids=meeting_ids or None)
    except HTTPException:
        return context,result
    labels={name_key(m['label']):m['label'] for row in broad_lines for m in form.finditer(row['text'])}
    if len(labels)!=2:
        return context,result
    focus_query=normalize(focused['question'])
    chosen=[key for key,label in labels.items() if
            re.search(label_pattern(normalize(label)),focus_query)
            or re.search(r'(?<!\w)'+re.escape(normalize(label))+r'\s*쪽(?:은|는|도)?(?=$|[^가-힣a-z0-9])',focus_query)]
    if len(chosen)!=1 or not any(name_key(m['label'])==chosen[0] for row in focused_lines for m in form.finditer(row['text'])):
        return context,result
    other=next(key for key in labels if key!=chosen[0])
    subject=f'{labels[other]} {topic}'

    candidates=[]
    for doc in docs:
        if not doc.get('date') or not in_scope(doc,scope):
            continue
        for line in document_lines(doc):
            if not content_line(line['text']):
                continue
            for clause in re.split(r'(?<=[.!?])\s+|\s*[;；]\s*',line['text']):
                clause_labels={name_key(m['label']) for m in form.finditer(clause)}
                if clause_labels=={other}:
                    candidates.append((doc,line,clause))
    if not candidates:
        return context,result

    latest=max(doc['date'] for doc,_,_ in candidates)
    matches=list({name_key(quote):(doc,line,quote) for doc,line,quote in candidates if doc['date']==latest}.values())
    if len(matches)!=1:
        return context,result
    doc,line,quote=matches[0]
    source=source_for(doc,project,'S1',[line])
    source['exact_highlights']=source['line_ids']
    context.update(query=subject,subject=subject,project_ids=ids,project_id=ids[0],label=project['name'],
                   time_scope=scope,meeting_ids=meeting_ids)
    result.update(kind='documents',mode='paired_alternative',answerable=True,message=f'다른 쪽인 {subject}의 회의 기록이에요.',
                  points=[{'text':quote,'project_id':ids[0],'project_name':project['name'],'sources':['S1']}],
                  sources=[source],notice=describe_scope(scope))
    return context,result
