"""Bounded category discovery. Quotes are records, never a generated baseline.

Only a whole, unqualified category query enters this path. Additional nouns,
numbers, negation, or status conditions must stay in ordinary content search.
"""
import re
from work.v3.query_intent import strip_labels
from work.v3.question_scope import in_scope
from work.v3.topic_search import source_for
from work.v17.evidence_text import content_line
from work.v17.retrieval import registered_document, document_lines

CATEGORIES = {
    'all': ('전체 항목', (), r'.'),
    'time': ('일정·기간', ('일정', '기간', '기한', '납기', '날짜'),
             r'일정|기간|기한|납품|납기|출하|반입|연기|지연|\d\s*일부터|\d\s*일까지|\d{4}-\d{2}-\d{2}.*까지'),
    'cost': ('비용', ('비용', '금액', '가격', '예산', '돈'), r'비용|금액|가격|예산|견적|대금|원가|단가'),
    'safety': ('안전', ('안전',), r'안전|위험|비상\s*정지|인터록|끼임|추락|방호|보호\s*장치'),
    'responsibility': ('담당', ('담당', '담당자', '역할'), r'담당|책임자|검토자|역할|분담'),
}
ASSIGNMENT_FIELDS = r'(?:담당자?(?:와|과|및|하고|이랑|[,·/])(?:제출|검토|처리)?기한|기한(?:과|및|하고|이랑|[,·/])(?:제출|검토|처리)?담당자?)'
UNASSIGNED_QUERY = re.compile(
    r'(?:(?:전체|모든)프로젝트(?:에서|의)?|회의(?:록|기록)(?:에서|에))?'
    + ASSIGNMENT_FIELDS + r'(?:을|를|이|가|은|는)?(?:아직)?'
    r'(?:못정한|안정한|안정해진|정하지못한|정하지않은|정해지지않은|미정(?:인)?|미지정(?:인)?)'
    r'(?:사항|항목|업무|내용|것|건|거)(?:들)?(?:만)?(?:을|를|은|는|이|가)?'
    r'(?:찾아줘|찾아주세요|보여줘|보여주세요|알려줘|알려주세요|정리해줘|있어|있나|있나요|뭐야)?'
)
UNASSIGNED_RECORD = re.compile(
    ASSIGNMENT_FIELDS + r'(?:을|를|이|가|은|는)?(?:아직)?'
    r'(?:미정(?:이다|임|입니다)?|미지정(?:이다|임|입니다)?|'
    r'정하지(?:못했다|못함|않았다|않음)|정해지지않았다|'
    r'(?:다음|차기)(?:회의|협의|미팅)에서정한다)(?=$|[.!?。])'
)


def without_date_scope(question, scope):
    """Remove only recognized record-date qualifiers, not dates used as values."""
    if not (scope or {}).get('start') and not (scope or {}).get('end'):return question
    q=re.sub(r'지난달|이번\s*달|이번달|지난주|이번주|어제|그제|오늘', ' ', question)
    q=re.sub(r'(?:20\d{2}\s*(?:년|[-./])\s*)?\d{1,2}\s*(?:월|[-./])\s*\d{1,2}\s*일?\s*(?:기준|시점|당시|부터|까지|이전|이후|에는)', ' ', q)
    q=re.sub(r'(?:20\d{2}\s*년\s*)?\d{1,2}\s*월(?:의|에|에는|중|동안)?', ' ', q)
    return re.sub(r'\s+', ' ', q).strip()


def intent(question, projects=(), scope=None):
    q=without_date_scope(strip_labels(question,projects),scope)
    # A closed grammar avoids turning e.g. '보증 기간', '기간 3일',
    # '안전 비용', or '기한 지난 것' into a broad category answer.
    q=re.sub(r'\s+', '', q).strip('?!. ,')
    found=[key for key,(_,names,_) in CATEGORIES.items() if any(name in q for name in names)]
    if len(found)!=1:return None
    key=found[0]
    for name in sorted(CATEGORIES[key][1],key=len,reverse=True):q=q.replace(name,'')
    words='''예전에 예전 과거 우리가 우리 이전에 기존에 회의했던거 회의했던것 회의했던 회의한 회의에서 회의중 회의록에서
        회의록 회의 프로젝트 중에서 중에 중 그중 관련된 관련해서 관련한 관련에 관련 얘기 이야기 논의했던 논의한 논의된 논의 내용 기록 자료 사항
        좀 한번 다시 있나요 있는지 있나 있어 없어 있었어 있었나 알려주세요 알려줘 보여주세요 보여줘 찾아주세요 찾아줘 찾아볼래 찾아볼수있어
        찾아볼수있을까 볼수있어 볼수있을까 볼까 찾아 설명해줘 정리해줘 확인해줘 전체 전부 모두 모든 각 어떤 뭐뭐 뭐가 뭐야
        처음부터 날짜순 순서대로 목록 리스트 나온 적 건 들 만 은 는 이 가 을 를 의 에 서 로 것 거'''.split()
    q=re.sub('|'.join(re.escape(w) for w in sorted(set(words),key=len,reverse=True)),'',q)
    return key if not q else None


def query(question,projects=(),scope=None):
    """A bounded topic + recorded-status filter, never a current-state claim."""
    q=without_date_scope(strip_labels(question,projects),scope)
    q=re.sub(r'^(?:그럼|그러면)\s*','',q)
    if UNASSIGNED_QUERY.fullmatch(re.sub(r'\s+', '', q).strip('?!. ,')):
        return {'category':'responsibility','recorded_status':'unassigned','dates_only':False}
    conditions={
        'unsettled':r'(?:아직\s*)?(?:안\s*정해진|정해지지\s*않은|결정\s*안\s*된|결정되지\s*않은|미정(?:인)?|미결정(?:인)?|보류된|보류\s*중인)',
        'agreed':r'정한|정했던|합의한|합의된|확정한|확정된|결정한|결정된',
    }
    matches=[k for k,p in conditions.items() if re.search(p,q)]
    if len(matches)>1:return None
    status=matches[0] if matches else None
    if status:q=re.sub(conditions[status],'',q)
    key=intent(q)
    if status and not key and re.fullmatch(r'(?:거|것|항목|내용|사항|회의록)?(?:은|는|이|가)?(?:있어|있나|있나요|알려줘|보여줘|찾아줘)?[?!.]*',re.sub(r'\s+','',q)):
        key='all'
    return {'category':key,'recorded_status':status,'dates_only':bool(re.search(r'날짜',q))} if key else None


def status_matches(text,status):
    if status=='unsettled':return bool(re.search(r'보류|미정|미결정|정하지\s*못|정해지지\s*않|추후\s*(?:협의|결정)|확정되지\s*않|아직.{0,12}(?:결정|확정)(?:되|하)?지\s*(?:않|못)',text))
    if status=='agreed':return bool(re.search(r'합의|확정|결정|정했다|정함',text) and not re.search(r'미합의|미확정|미정|미결정|(?:합의|확정|결정)(?:하|되)?지\s*(?:않|못)|(?:합의|확정|결정)\s*(?:못|안|되지\s*않)',text))
    return True


def unassigned_lines(doc):
    lines = document_lines(doc)
    matched = {}
    for index, line in enumerate(lines):
        if not content_line(line['text']):
            continue
        text = re.sub(r'\s+', '', line['text'])
        if UNASSIGNED_RECORD.search(text):
            matched[line['id']] = line
        elif re.search(ASSIGNMENT_FIELDS + r'(?:을|를|은|는|이|가)?$', text) and index + 1 < len(lines):
            following = lines[index + 1]
            if (int(following['id'][1:]) == int(line['id'][1:]) + 1
                    and UNASSIGNED_RECORD.search(text + re.sub(r'\s+', '', following['text']))):
                matched[line['id']] = line
                matched[following['id']] = following
    return list(matched.values())


def search(w,c,projects,question,plan):
    spec=query(question,projects,plan)
    if not spec:return None
    key=spec['category'];status=spec['recorded_status']
    label,_,pattern=CATEGORIES[key];ps={p['id']:p for p in projects}
    matches=[];searched=0;total_lines=0
    for m in w.all_records(c,'meeting'):
        if m['project_id'] not in ps:continue
        d=registered_document(m)
        if not d or not in_scope(d,plan) or plan.get('meeting_ids') and d['meeting_id'] not in plan['meeting_ids']:continue
        searched+=1
        if status == 'unassigned':
            lines = unassigned_lines(d)
        else:
            lines=[l for l in document_lines(d) if content_line(l['text']) and re.search(pattern,l['text'],re.I)]
            if spec['dates_only']:lines=[l for l in lines if re.search(r'\d{1,4}[-./]\d{1,2}|\d\s*월|납품일|출하일|반입일|일자',l['text'])]
            lines=[l for l in lines if status_matches(l['text'],status)]
        if lines:
            total_lines+=len(lines);matches.append((d,lines))
    matches.sort(key=lambda pair:(pair[0].get('date',''),pair[0]['meeting_id']))
    sources=[];items=[]
    for d,lines in matches:
        sid='S'+str(len(sources)+1);p=ps[d['project_id']]
        # Existing paginated meeting result UI; all matching lines remain in
        # the evidence view. No model/context-window project cap applies.
        scoped={**plan,'resolved_question':label,'search_terms':None,'category':key}
        source=source_for(d,p,sid,lines,scoped)
        source['exact_highlights']=[l['id'] for l in lines]
        sources.append(source)
        items.append({'source_id':sid,'title':d['title'],'date':d.get('date',''),'project_id':p['id'],
                      'project_name':p['name'],'snippet':'\n'.join(l['text'] for l in lines),'matched_lines':len(lines)})
    count=len(items);matched=len({s['project_id'] for s in sources})
    if spec['dates_only']:label='날짜·일정'
    if status == 'unassigned':
        label = '담당자·기한 미정'
        status_notice = '담당자와 기한을 모두 정하지 않았다고 적힌 당시 기록입니다. 현재 배정 여부와 실제 처리 상태는 별도로 확인해야 합니다. '
    elif status:
        label += ' · '+('보류·미정 언급' if status=='unsettled' else '합의·결정 언급')
        status_notice = '해당 회의 당시의 언급이며, 현재 확정·미해결 상태를 뜻하지 않습니다. '
    else:
        status_notice = ''
    counts=[{'project_id':pid,'project_name':p['name'],'count':sum(i['project_id']==pid for i in items)} for pid,p in ps.items() if any(i['project_id']==pid for i in items)]
    return {'kind':'documents','mode':'meeting_search','category':key,'answer_mode':'source_quote',
            'recorded_status':status,'project_counts':counts,
            'answerable':bool(items),'points':[],'sources':sources,'meetings':items,'count':count,
            'message':f'{label} 관련 표현이 있는 회의록 {count}건 · {matched}개 프로젝트입니다.' if items else f'조회 범위의 등록 회의록에서 {label} 관련 표현을 찾지 못했습니다.',
            'notice':f'{len(projects)}개 프로젝트 · 등록 회의록 {searched}건에서 {label} 관련 표현을 찾았습니다. 회의일 오래된순이며 원문 기록을 표시합니다. 표현이 다른 내용은 빠질 수 있습니다. '+
                     status_notice+plan.get('notice',''),
            'searched_projects':len(projects),'searched_meetings':searched,'matched_lines':total_lines}
