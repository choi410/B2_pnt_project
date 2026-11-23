"""Requirements projected from grounded AI records, with separate human tracking.

No extra model call: responsibility and deadlines are accepted only from explicit
source clauses. A mention, customer recipient or meeting date is not an assignment.
"""
from datetime import date
import hashlib,json,re
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field

def norm(s):return re.sub(r'[\s·_().\-]','',s or '').casefold()
def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def topic_key(e):return e['project_id']+'|'+e['category']+'|'+norm(e['title'])
def tracking_state(value):
    # Read old notes without requiring a database migration or changing history.
    return '미등록' if value in ('처리 결과 미확인','미확인',None,'') else value

def related(title,text):
    if norm(title) in norm(text):return True
    words=[w for w in re.findall(r'[가-힣A-Za-z]+',title) if len(w)>1 and w not in {'장비','방식','변경','요구','사항','기본','기준','요청','설계'}]
    matches=[w for w in words if w in text]
    # Accept a shortened two-word subject (압연 속도 -> 속도, 점검 커버 -> 커버).
    # Longer compound specifications remain conservative: 건조로 alone must not
    # link a component-delivery action to 건조로 설정 온도 상한.
    return len(matches)>=2 or (len(words)==1 and len(matches)==1) or (len(words)==2 and words[-1] in text)

def explicit_metadata(quotes,people):
    owners=set();deadlines=set();owner_refs=[];due_refs=[]
    for row in quotes:
        text=row['text']
        # A person explaining a specification, or receiving a report, is not the owner.
        for person in people:
            name=person['name']
            subject=re.search(r'(?<![가-힣])'+re.escape(name)+r'\s*(?:[:：]|(?:이|가|은|는)\s)',text)
            labeled=re.search(r'담당(?:자)?\s*[:：]\s*(?:[가-힣]+\s+)?'+re.escape(name)+r'(?![가-힣])',text)
            if labeled or (subject and re.search(r'(?:작성|반영|수정|확인|검토|공유|전달|회신|제출|담당|진행|정리|요청)(?:한다|합니다|할|하기로|해|하여|하고|중|예정|하)',text[subject.end():])):
                owners.add(name);owner_refs.append(row['id'])
        # Also preserve explicitly labeled names/departments outside the login roster.
        for match in re.finditer(r'담당(?:자)?\s*[:：]\s*([^|,;\n.]{2,30})',text):
            value=match[1].strip()
            if not re.search(r'미정|없음|확인\s*필요|기한|까지|담당한다',value):owners.add(value);owner_refs.append(row['id'])
        for m in re.finditer(r'(20\d{2})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})\s*일?',text):
            tail=text[m.end():m.end()+10];prefix=text[max(0,m.start()-8):m.start()]
            if not (re.match(r'\s*(?:까지|이내)',tail) or re.search(r'기한\s*[:：]?\s*$',prefix)):continue
            try:deadlines.add(date(*map(int,m.groups())).isoformat());due_refs.append(row['id'])
            except ValueError:pass
    # A single known name and an equivalent departmental label are the same owner.
    for name in list(owners):
        if any(other!=name and other.endswith(' '+name) for other in owners):owners.discard(name)
    return {'owner':next(iter(owners)) if len(owners)==1 else '',
            'due':next(iter(deadlines)) if len(deadlines)==1 else '',
            'owner_ambiguous':len(owners)>1,'due_ambiguous':len(deadlines)>1,
            'owner_evidence':list(dict.fromkeys(owner_refs)),'due_evidence':list(dict.fromkeys(due_refs))}

def build_requirements(w,c,actor):
    projects={p['id']:p for p in w.all_records(c,'project') if not p.get('deleted_at') and actor['id'] in p['members']}
    meetings={m['id']:m for m in w.all_records(c,'meeting') if m['project_id'] in projects and not m.get('deleted_at') and not m.get('analysis_stale') and m.get('analysis_state')=='ready'}
    groups={}
    for e in w.all_records(c,'change_event'):
        m=meetings.get(e['meeting_id'])
        if not m or e.get('superseded_by_revision') or e.get('review_state')=='제외' or e.get('source_revision')!=m['revision']:continue
        groups.setdefault(topic_key(e),[]).append(e)
    saved={n['id']:n for n in w.all_records(c,'requirement_note')}
    people=w.all_records(c,'person');out=[]
    for key,events in groups.items():
        events.sort(key=lambda e:(meetings[e['meeting_id']].get('date') or e.get('effective_date',''),e.get('created_at',''),e['id']))
        e=events[-1];m=meetings[e['meeting_id']];refs={x['id']:x['text'] for x in m.get('lines',[])}
        evidence=[x for x in e.get('evidence',[]) if x in refs]
        linked=[]
        bundle=m.get('reviewed_bundle') or m.get('v3_bundle') or {}
        for candidate in bundle.get('candidates',m.get('candidates',[])):
            ids=[x for x in candidate.get('evidence',[]) if x in refs]
            quote=' '.join(refs[x] for x in ids)
            if ids and related(e['title'],quote):linked.extend(ids)
        allids=list(dict.fromkeys(evidence+linked))
        quotes=[{'id':i,'text':refs[i],'kind':'요구사항 근거' if i in evidence else '담당·기한 관련 근거'} for i in allids]
        # Follow-up clauses establish responsibility; explanatory speeches do not.
        meta=explicit_metadata([q for q in quotes if q['id'] in linked] or quotes,people)
        rid=fingerprint(key)[:24]
        sig=fingerprint([e['id'],e.get('version',1),m['revision'],e['after'],e['business_state'],quotes])
        note=saved.get(rid);applicable=note and note.get('signature')==sig
        state='미등록';owner=meta['owner'];due=meta['due'];result=''
        if applicable:owner=note['owner'];due=note['due'];state=tracking_state(note['state']);result=note['result']
        risks=[]
        if e['business_state']!='철회':
            if not owner:risks.append('담당자 확인 필요' if meta['owner_ambiguous'] and not applicable else '담당자 미정')
            if not due:risks.append('기한 확인 필요' if meta['due_ambiguous'] and not applicable else '기한 미정')
            if due and due<w.now()[:10] and state!='조치 완료':risks.append('기한 경과')
            if note and not applicable:risks.append('새 기록 확인 필요')
        p=projects[e['project_id']]
        out.append({'id':rid,'key':key,'event_id':e['id'],'project_id':e['project_id'],'project_name':p['name'],
                    'title':e['title'],'content':e['after'],'before':e.get('before',''),'category':e['category'],
                    'business_state':e['business_state'],'change_kind':'변경' if len(events)>1 or e.get('before') else '신규',
                    'owner':owner,'due':due,'state':'철회' if e['business_state']=='철회' else state,'result':result,
                    'risks':risks,'risk':bool(risks),'quotes':quotes,'evidence':allids,'source_evidence':evidence,
                    'meeting_id':m['id'],'meeting_title':m['title'],'meeting_date':m.get('date',''),'event_count':len(events),
                    'signature':sig,'version':note.get('version',0) if note else 0,'edited':bool(applicable),
                    'can_edit':actor['id'] in (p['pm'],m['author']),'updated_by':note.get('updated_by') if applicable else None,
                    'updated_at':note.get('updated_at') if applicable else None})
    return sorted(out,key=lambda r:(r['meeting_date'],r['title']),reverse=True)

class RequirementEdit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int
    signature:str
    owner:str=Field(default='',max_length=60)
    due:str=''
    state:str='미등록'
    result:str=Field(default='',max_length=2000)

def build_router(w):
    router=APIRouter(prefix='/api/v3')
    @router.patch('/requirements/{rid}')
    def update(rid,body:RequirementEdit,actor=Depends(w.user)):
        state=tracking_state(body.state)
        if state not in ('미등록','진행 중','조치 완료'):raise HTTPException(422,'처리 상태를 확인해 주세요.')
        if body.due:
            try:
                if date.fromisoformat(body.due).isoformat()!=body.due:raise ValueError()
            except ValueError:raise HTTPException(422,'기한을 YYYY-MM-DD 형식으로 입력해 주세요.')
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=next((r for r in build_requirements(w,c,actor) if r['id']==rid),None)
            if not row:raise HTTPException(404,'현재 요구사항을 찾을 수 없습니다. 회의록 상태를 확인해 주세요.')
            if not row['can_edit']:raise HTTPException(403,'프로젝트 PM 또는 회의록 등록자가 수정할 수 있습니다.')
            if body.signature!=row['signature'] or body.version!=row['version']:raise HTTPException(409,'새 기록 또는 수정사항이 있습니다. 닫은 뒤 다시 열어 주세요.')
            if row['business_state']=='철회':raise HTTPException(409,'철회된 요구사항은 조치 상태를 변경하지 않습니다.')
            note={'id':rid,'project_id':row['project_id'],'meeting_id':row['meeting_id'],'signature':body.signature,
                  'owner':body.owner.strip(),'due':body.due,'state':state,'result':body.result.strip(),
                  'version':body.version+1,'updated_by':actor['id'],'updated_at':w.now()}
            previous=next((n for n in w.all_records(c,'requirement_note') if n['id']==rid),None)
            note['history']=(previous.get('history',[])+[{k:v for k,v in previous.items() if k!='history'}]) if previous else []
            w.save(c,'requirement_note',note)
            return {'ok':True,'version':note['version']}
    return router
