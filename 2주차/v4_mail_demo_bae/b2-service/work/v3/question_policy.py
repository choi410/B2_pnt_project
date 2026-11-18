"""V3 question scope and source-backed fast answers; no approval is invented."""
import re
from fastapi import HTTPException
from work.v17 import baseline_questions
from work.v17.retrieval import registered_document, document_lines


def clean(text):
    return re.sub(r'[^가-힣a-z0-9]', '', text.lower())


def project_lookup(question):
    q=clean(question)
    # Content questions containing 'project' still go through source retrieval.
    return '프로젝트' in q and not any(x in q for x in ('회의','변경','납기','납품','사양','속도','보류','철회','요구','일정')) and any(x in q for x in ('찾','검색','목록','열어','보여','어떤','무슨'))


def name_matches(projects,question):
    q=clean(question)
    exact=[p for p in projects if clean(p['name']) in q or re.search(r'(?<![\w-])'+re.escape(p['id'])+r'(?![\w-])',question,re.I)]
    if exact:return exact
    ignored={'프로젝트','전극','제작','장비','신규','설계','라인','설비'}
    matches=[]
    for p in projects:
        words=[clean(x) for x in re.split(r'[\s·_()/-]+',p['name'])]
        words=[x for x in words if len(x)>=2 and x not in ignored and not re.fullmatch(r'\d+호기?',x)]
        hits=[x for x in words if x in q]
        ordinal=[x for x in re.findall(r'\d+호기',p['name']) if x in q]
        if hits:matches.append((p,sum(len(x) for x in hits)+sum(len(x) for x in ordinal)))
    if not matches:return []
    best=max(score for _,score in matches)
    return [p for p,score in matches if score==best]


def scope_projects(w,c,pid,actor,question=''):
    if pid:return [w.project(c,pid,actor)]
    ps=[p for p in w.all_records(c,'project') if not p.get('deleted_at') and actor['id'] in p['members']]
    if not ps:raise HTTPException(422,'조회할 수 있는 프로젝트가 없습니다.')
    return name_matches(ps,question) or ps


def is_broad(question):
    q=clean(question)
    return any(x in q for x in ('전체','모든','각프로젝트','프로젝트별','비교','목록','각각'))


def topic_matches(topics,question):
    q=clean(question)
    named=[t for t in topics if clean(t['title']) in q]
    if named:return named
    if any(x in q for x in ('납기','납품일','납품기한')):return [t for t in topics if t['category']=='납기']
    if '사양' in q:return [t for t in topics if t['category']=='사양']
    if any(x in q for x in ('전체','기준','확정내용','합의내용','최종합의')):return topics
    return [t for t in topics if any(len(x)>=2 and clean(x) in q for x in t['title'].split())]


def event_source(e,m,p):
    if not m or m.get('deleted_at') or m.get('analysis_stale') or e.get('superseded_by_revision') or e.get('review_state')=='제외' or e.get('source_revision')!=m['revision']:return None
    doc=registered_document(m)
    if not doc or doc['revision']!=e.get('source_revision'):return None
    lines={l['id']:l['text'] for l in document_lines(doc)}
    refs=[r for r in e.get('evidence',[]) if r in lines]
    if not refs:return None
    return {k:v for k,v in doc.items() if k!='body'}|{'project_name':p['name'],'line_ids':refs,'text':'\n'.join(lines[r] for r in refs),'event_id':e['id'],'score':1.0}


def held_items(w,c,projects,question):
    q=clean(question)
    if '보류' not in q or any(x in q for x in ('왜','이유','과정','이력','모든회의','과거')) or not any(x in q for x in ('사항','항목','내용','목록','무엇','뭐')):return None
    ps={p['id']:p for p in projects};ms={m['id']:m for m in w.all_records(c,'meeting') if m['project_id'] in ps}
    groups={}
    for e in w.all_records(c,'change_event'):
        if e['project_id'] not in ps:continue
        s=event_source(e,ms.get(e['meeting_id']),ps[e['project_id']])
        if s:groups.setdefault((e['project_id'],e['category'],clean(e['title'])),[]).append((e,s))
    documented={m['project_id'] for m in ms.values() if registered_document(m)}
    if documented-{key[0] for key in groups}:return None
    points=[];sources=[]
    for records in groups.values():
        latest=max(e.get('effective_date') or s['date'] for e,s in records)
        held={}
        for e,s in records:
            if (e.get('effective_date') or s['date'])!=latest:continue
            # Quote an explicit held statement; do not repeat a possibly wrong
            # AI state label (e.g. a withdrawn cover request classified as hold).
            clauses=re.split(r'[.!?]\s+|\n',s['text'])
            quote=next((x.strip() for x in clauses if re.search(r'보류했|보류하였|보류한다|보류함|보류하기로',x)),None)
            if not quote:continue
            sid='S'+str(len(sources)+1);sources.append(dict(s,id=sid))
            numeric=tuple(re.findall(r'\d+(?:\.\d+)?',quote))
            identity=numeric or clean(quote)
            if identity in held:
                held[identity]['sources'].append(sid)
                if len(quote)>len(held[identity]['quote']):held[identity]['quote']=quote
            else:held[identity]={'quote':quote,'title':e['title'],'project_id':e['project_id'],'project_name':ps[e['project_id']]['name'],'sources':[sid]}
        for item in held.values():
            quote=item.pop('quote');title=item.pop('title');item['text']=(title+': ' if title not in quote else '')+quote;points.append(item)
    if not points:return None
    return {'kind':'documents','mode':'baseline','answerable':True,'points':points,'sources':sources,'message':'','notice':'변경 항목별 최신 기록에서 보류가 명시된 원문을 모았습니다. 등록되지 않은 후속 결정은 포함하지 않습니다.'}


def recorded_agreements(w,c,projects,question):
    ps={p['id']:p for p in projects}
    events=[e for e in w.all_records(c,'change_event') if e['project_id'] in ps]
    # V3 groups events directly; old imports may have no change_topic record.
    key=lambda e:(e['project_id'],e['category'],clean(e['title']))
    topics=topic_matches(list({key(e):{'id':key(e),'project_id':e['project_id'],'category':e['category'],'title':e['title']} for e in events}.values()),question)
    if not topics:return None  # Unknown subject: search the documents, not a fake empty ledger.
    meetings={m['id']:m for m in w.all_records(c,'meeting') if m['project_id'] in ps}
    sources=[];points=[]
    def source(e):
        return event_source(e,meetings.get(e.get('meeting_id')),ps[e['project_id']])
    def add(s):
        existing=next((x for x in sources if x['event_id']==s['event_id']),None)
        if existing:return existing['id']
        sid='S'+str(len(sources)+1);sources.append(dict(s,id=sid));return sid
    for t in sorted(topics,key=lambda t:(t['project_id'],t['title'])):
        valid=[(e,s) for e in events if key(e)==t['id'] and (s:=source(e))]
        # Keep model extraction distinct from approval, and require agreement
        # language in the source rather than trusting the classification alone.
        accepted=[]
        for e,s in valid:
            if e.get('business_state')!='확정':continue
            value=e.get('after','').strip()
            scalar=re.match(r'(20\d{2}-\d{2}-\d{2}|\d+(?:\.\d+)?\s*(?:m/min|mm|℃|°C|kg|kW|rpm|%))',value,re.I)
            if scalar:value=scalar[0]
            clauses=re.split(r'[.!?]\s+|\n',s['text'])
            for clause in clauses:
                if re.search(r'보류|미정|철회|(?:합의|확정|승인)(?:하지\s*않|되지\s*않|하지\s*못|되지\s*못)|확정.{0,5}아니',clause):continue
                if clean(value) and clean(value) in clean(clause) and re.search(r'합의했|합의하였|합의한다|합의함|합의했습니다|확정했|확정하였|확정함|승인했|하기로\s*했|유지한다|유지하기로',clause):
                    accepted.append((dict(e,after=value),s));break
        if not accepted:continue
        latest_date=max(e.get('effective_date') or s['date'] for e,s in accepted)
        if any(e.get('business_state')=='확정' and (e.get('effective_date') or s['date'])>latest_date for e,s in valid):
            return None  # A newer agreement could not be verified: retrieve its source.
        current=[(e,s) for e,s in accepted if (e.get('effective_date') or s['date'])==latest_date]
        values=list(dict.fromkeys(e['after'] for e,s in current))
        citations=[add(s) for e,s in current]
        if len(values)>1:
            text=t['title']+': 같은 날짜의 회의록에 서로 다른 합의값('+ ' / '.join(values)+')이 기록되어 있습니다. 원문 확인이 필요합니다.'
        else:
            text=t['title']+': '+values[0]+' (회의록에 기록된 합의)'
            newer=[(e,s) for e,s in valid if (e.get('effective_date') or s['date'])>latest_date]
            if newer:
                e,s=max(newer,key=lambda x:(x[0].get('effective_date') or x[1]['date'],x[0].get('created_at','')))
                citations.append(add(s))
                text+=' 이후 '+(e.get('business_state') or '후속')+' 기록이 있으며, 새로운 합의값으로 바꾸지 않았습니다.'
        points.append({'text':text,'project_id':t['project_id'],'project_name':ps[t['project_id']]['name'],'sources':list(dict.fromkeys(citations))})
    if not points:return None  # Let the model explain pending/unknown values from sources.
    return {'kind':'documents','mode':'baseline','answerable':True,'points':points,'sources':sources,'message':'','notice':'등록된 회의록의 합의 표현과 변경 기록을 대조한 결과입니다. 별도의 사람 승인 여부를 뜻하지 않습니다.','searched_projects':len(projects),'searched_meetings':len({s['meeting_id'] for s in sources})}


def quick_answer(w,c,projects,actor,question,explicit_scope):
    if project_lookup(question):
        named=name_matches(projects,question)
        q=clean(question)
        all_requested=any(x in q for x in ('전체','모든','프로젝트목록','프로젝트보여','어떤프로젝트','무슨프로젝트'))
        found=projects if all_requested else named
        people={p['id']:p['name'] for p in w.all_records(c,'person')}
        return {'kind':'projects','answerable':bool(found),'projects':[{'id':p['id'],'name':p['name'],'pm':people.get(p['pm'],'미지정')} for p in found],'message':f'프로젝트 {len(found)}개를 찾았습니다.' if found else '일치하는 프로젝트가 없습니다. 프로젝트명 일부 또는 코드를 입력해 주세요.'}
    if not explicit_scope and len(projects)>1 and name_matches(projects,question) and not is_broad(question):
        return {'kind':'clarification','answerable':False,'message':'이 이름에 해당하는 프로젝트가 여러 개입니다. 어느 프로젝트인지 선택해 주세요.','projects':[{'id':p['id'],'name':p['name']} for p in projects]}
    if baseline_questions.baseline_intent(question):return recorded_agreements(w,c,projects,question)
    return held_items(w,c,projects,question)
