"""Registered meeting discovery, separate from generated answer passage limits."""
import re
from work.v3.query_intent import strip_labels, metadata_plan
from work.v3.question_scope import in_scope
from work.v17.evidence_text import topic_terms, coverage, content_line, HEAD
from work.v17.retrieval import registered_document, document_lines


def search_intent(question, projects=()):
    from work.v3.agenda_questions import intent as agenda_intent
    if agenda_intent(question,projects):return None
    if metadata_plan(question,projects):return None
    q=strip_labels(question,projects)
    if not re.search(r'회의록|회의',q) or not re.search(r'찾아|검색|목록|리스트|보여|전부|모든|몇\s*(?:개|건)',q):return None
    if re.search(r'요약|설명|비교|왜|어떻게',q):return None
    terms=topic_terms(q)
    if not terms:return None
    return {'terms':terms,'oldest':not bool(re.search(r'최신순|최근순|내림차순',q))}


def source_for(doc,project,sid,lines,plan=None):
    return {k:v for k,v in doc.items() if k!='body'}|{'id':sid,'project_name':project['name'],
        'line_ids':[l['id'] for l in lines],'text':'\n'.join(l['text'] for l in lines),'score':1.0,
        **({'query_scope':{k:v for k,v in plan.items() if k!='content_plans'}} if plan else {})}


def full_document(w,c,projects,plan):
    ps={p['id']:p for p in projects};sources=[];items=[]
    for m in w.all_records(c,'meeting'):
        if m['project_id'] not in ps or m['id'] not in plan.get('meeting_ids',[]):continue
        doc=registered_document(m)
        if not doc:continue
        lines=document_lines(doc);sid='S'+str(len(sources)+1);p=ps[doc['project_id']]
        source=source_for(doc,p,sid,lines,plan);source['exact_highlights']=[];sources.append(source)
        items.append({'source_id':sid,'title':doc['title'],'date':doc.get('date',''),'project_name':p['name'],
                      'project_id':p['id'],'snippet':'원문에서 보기를 누르면 회의록 전체 내용을 확인할 수 있습니다.'})
    return {'kind':'documents','mode':'meeting_search','answerable':bool(items),'points':[],'sources':sources,
            'meetings':items,'count':len(items),'message':'선택한 회의록의 원문입니다.' if items else '현재 조회 가능한 원문이 없습니다.',
            'notice':'현재 등록된 원문 전체를 조회합니다.'}


def search(w,c,projects,question,plan):
    intent=search_intent(question,projects)
    if not intent:return None
    if plan.get('message'):
        return {'kind':'documents','answerable':False,'points':[],'sources':[],'message':plan['message']}
    ps={p['id']:p for p in projects};matches=[];searched=0
    for m in w.all_records(c,'meeting'):
        if m['project_id'] not in ps:continue
        doc=registered_document(m)
        if not doc or not in_scope(doc,plan) or plan.get('meeting_ids') and m['id'] not in plan['meeting_ids']:continue
        searched+=1
        scoped=plan.get('content_plans',{}).get(m['project_id'],plan)
        terms=scoped.get('search_terms')
        if terms is None:terms=intent['terms']
        lines=[l for l in document_lines(doc) if content_line(l['text'])]
        # All terms must occur in the registered body (or actual meeting title).
        # This is a documented keyword match, not a claim of semantic completeness.
        if coverage(doc['title']+'\n'+'\n'.join(l['text'] for l in lines),terms)<1:continue
        hits=sorted(lines,key=lambda l:coverage(l['text'],terms),reverse=True)
        hits=[l for l in hits[:2] if coverage(l['text'],terms)>0]
        matches.append((doc,hits))
    matches.sort(key=lambda x:(x[0]['title'],x[0]['meeting_id']))
    dated=[x for x in matches if x[0].get('date')];undated=[x for x in matches if not x[0].get('date')]
    dated.sort(key=lambda x:x[0]['date'],reverse=not intent['oldest'])
    sources=[];items=[]
    for doc,hits in dated+undated:
        sid='S'+str(len(sources)+1);p=ps[doc['project_id']]
        sources.append(source_for(doc,p,sid,hits,plan.get('content_plans',{}).get(p['id'],plan)))
        items.append({'source_id':sid,'title':doc['title'],'date':doc.get('date',''),'project_name':p['name'],
                      'snippet':hits[0]['text'] if hits else '', 'project_id':doc['project_id']})
    return {'kind':'documents','mode':'meeting_search','answerable':bool(items),'points':[],'sources':sources,'meetings':items,
            'count':len(items),'message':f'검색어가 일치하는 회의록 {len(items)}건입니다.' if items else (
                f"{plan['start']}에 해당 조건으로 등록된 회의록은 없습니다. 다른 회의록에 적힌 예정일과 실제 회의일은 구분해서 조회합니다."
                if plan.get('mode')=='meeting' else '검색어가 일치하는 등록 회의록을 찾지 못했습니다.'),
            'notice':f'검색어: {" · ".join(intent["terms"])} · 조회 가능한 등록 회의록 {searched}건에서 검색했습니다. '+
                     ('회의일 오래된순입니다. ' if intent['oldest'] else '회의일 최신순입니다. ')+
                     '원문에 함께 표기된 별칭은 포함하며, 연결되지 않은 다른 표현의 회의는 빠질 수 있습니다.'+((' '+plan['notice']) if plan.get('notice') else ''),
            'searched_projects':len(ps),'searched_meetings':searched}
