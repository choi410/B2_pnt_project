"""One source-grounded query for retrieval, generation and claim verification.

Vocabulary resolution is deliberately bounded: record-backed terminology, not
an assumption that every speed or every due date denotes the same quantity.
"""
import re
from work.v3.query_intent import strip_labels
from work.v17.evidence_text import normalize_request, normalized, content_line
from work.v17.retrieval import document_lines

LINEAR_SPEED = r'(?:라인|압연|이송|운전|생산)\s*속도'


GENERIC_VALUE = {'수치','수치값','수치들','값','값들','숫자','숫자들','데이터','정보'}


def missing_subject(question, terms, fields):
    """'수치 얼마야' names no attribute. Searching for the word 수치 alone cannot
    select evidence, so ask for the item instead of answering 'no evidence'."""
    if not re.search(r'수치|값|숫자', question):return ''
    if any(not isinstance(t,str) or t not in GENERIC_VALUE for t in terms or []):return ''
    names=sorted({f for f in fields if 2<=len(f)<=15 and not re.search(r'수치|값|숫자',f)})[:6]
    hint=' 이 프로젝트 회의록에 기록된 항목: '+', '.join(names)+'.' if names else ''
    example=names[0] if names else '압연 속도'
    return ('어떤 항목의 수치를 볼까요? 항목 이름을 넣어 다시 질문해 주세요. 예: “'+example+' 최근 값 알려줘”.'+hint+
            ' 바뀐 값 전체를 보려면 “변경 이력 보여줘”라고 물어보세요.')


def bind(plan,content):
    """Carry one interpretation through every content-answer stage."""
    plan=dict(plan)
    plan.update(resolved_question=content['question'],operation=content['operation'],
                search_terms=content.get('search_terms'),subjects=content.get('subjects',[]),
                topic_notice=content['notice'])
    if content['history'] and plan.get('mode','current')=='current':plan['mode']='history'
    return plan


def prepare(question, projects, docs):
    from work.v3.source_terms import catalog,resolve
    from work.v3.answer_meaning import completion_question
    _,catalog_fields=catalog(docs)
    fields=set(re.findall(LINEAR_SPEED,question))
    fields.update(catalog_fields)
    for doc in docs:
        for line in document_lines(doc):
            if not content_line(line['text']):continue
            label=re.match(r'^([^:：]{2,24})[:：]',line['text'])
            if label:fields.add(label[1].strip())
            fields.update(re.findall(LINEAR_SPEED,line['text']))
    q=normalize_request(strip_labels(question,projects,protected=fields))
    history=bool(re.search(r'변경\s*이력|변경\s*전|경위|어떻게\s*바뀌',q))
    operation='history' if history else 'completion' if completion_question(q) else 'decision' if re.search(r'승인|합의|확정|결정|바뀌었|변경됐|변경되었',q) else 'responsibility' if re.search(r'담당|누가|누구|기한',q) else 'content'
    result={'question':q,'history':history,'operation':operation,'notice':'','message':''}
    def finish():
        resolved=resolve(result['question'],docs)
        result.update(question=resolved['question'],search_terms=resolved['terms'],subjects=resolved['subjects'])
        result['notice']=' '.join(x for x in (result['notice'],resolved['notice']) if x)
        result['message']=result['message'] or resolved['message'] or missing_subject(result['question'],resolved['terms'],fields)
        return result
    if len(projects)!=1:return result  # Resolve independently inside each project.
    requested=list(re.finditer(r'(?<![가-힣a-z])'+LINEAR_SPEED+r'(?=$|[^가-힣a-z]|[은는이가을를의])',q,re.I))
    if not requested:return finish()
    names={}
    for doc in docs:
        for line in document_lines(doc):
            if not content_line(line['text']):continue
            for m in re.finditer(r'(?<![가-힣a-z])'+LINEAR_SPEED,line['text'],re.I):
                name=re.sub(r'\s*속도$',' 속도',m[0]);names[normalized(name)]=name
    notices=[]
    for m in reversed(requested):
        key=normalized(m[0])
        if key in names:target=names[key]
        elif key not in ('라인속도','운전속도','생산속도'):continue
        elif len(names)==1:target=next(iter(names.values()))
        elif len(names)>1:
            result['message']='이 프로젝트에는 '+', '.join(sorted(names.values()))+'가 기록되어 있습니다. 어느 속도의 내용을 볼까요?'
            return result
        else:continue
        q=q[:m.start()]+target+q[m.end():]
        if key!=normalized(target):notices.append('회의록의 ‘'+target+'’ 항목을 기준으로 조회했습니다.')
    result.update(question=q,notice=' '.join(dict.fromkeys(notices)))
    return finish()
