"""Requirement history with immutable reference data and reviewed AI alternatives."""
from pathlib import Path
import hashlib, json, uuid
from datetime import date
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import Field, field_validator
from typing import Literal
import workflow as w

REFERENCE=Path(__file__).parent/'sample'/'pnt-sim-001'
STATES=['검토중','확정','철회','재검토','적용대기']
KINDS=['신규','값변경','유지확인','철회','재개','재검토','상태변경','담당기한변경','승인']


def stable(value):return str(uuid.uuid5(uuid.NAMESPACE_URL,'b2-reference:'+value))
def packed(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))


def initialize(con):
    con.execute('CREATE TABLE IF NOT EXISTS req_projects(project_id TEXT PRIMARY KEY,code TEXT UNIQUE NOT NULL,provenance TEXT NOT NULL,source_hash TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1)')
    con.execute('CREATE TABLE IF NOT EXISTS req_people(code TEXT PRIMARY KEY,name TEXT NOT NULL,data_json TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS req_equipment(code TEXT PRIMARY KEY,project_id TEXT NOT NULL,data_json TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS req_meetings(code TEXT PRIMARY KEY,project_id TEXT NOT NULL,meeting_id TEXT NOT NULL UNIQUE,seq INTEGER NOT NULL,meeting_date TEXT NOT NULL,title TEXT NOT NULL,filename TEXT NOT NULL,segments_json TEXT NOT NULL,UNIQUE(project_id,seq))')
    con.execute('CREATE TABLE IF NOT EXISTS req_definitions(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,title TEXT NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS req_events(id TEXT PRIMARY KEY,requirement_id TEXT NOT NULL,meeting_code TEXT NOT NULL,origin TEXT NOT NULL,data_json TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,trial_id TEXT,reviewer_name TEXT,created_at TEXT NOT NULL)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_req_event_requirement ON req_events(requirement_id,meeting_code)')
    con.execute('CREATE TABLE IF NOT EXISTS req_trials(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,meeting_code TEXT NOT NULL,status TEXT NOT NULL,context_json TEXT NOT NULL,output_json TEXT,error TEXT,metrics_json TEXT,review_json TEXT,version INTEGER NOT NULL DEFAULT 1,project_version INTEGER NOT NULL,created_at TEXT NOT NULL)')
    con.execute("UPDATE req_trials SET status='failed',error='서버 재시작으로 분석이 중단됐습니다. 다시 실행해 주세요.',version=version+1 WHERE status IN ('queued','analyzing')")


def import_demo(con,parse):
    data=json.loads((REFERENCE/'reference.json').read_text(encoding='utf-8'))
    project=data['project'];pid=stable(project['프로젝트번호'])
    previous=con.execute('SELECT * FROM req_projects WHERE code=?',(project['프로젝트번호'],)).fetchone()
    if previous:
        if previous['source_hash']!=data['source_zip_sha256']:raise HTTPException(409,'다른 버전의 자료가 이미 등록돼 있습니다.')
        return {'project_id':previous['project_id'],'imported':False}
    pname=project['프로젝트번호']+' '+project['프로젝트명']
    con.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,1)',(pid,pname,'연속 회의 5회와 요구사항 변경 이력을 확인하는 가상 프로젝트',project['PM성명'],project['납기일'],w.now()))
    con.execute('INSERT INTO req_projects(project_id,code,provenance,source_hash) VALUES(?,?,?,?)',(pid,project['프로젝트번호'],data['provenance'],data['source_zip_sha256']))
    for p in data['people']:con.execute('INSERT OR IGNORE INTO req_people VALUES(?,?,?)',(p['사번'],p['성명'],packed(p)))
    for e in data['equipment']:con.execute('INSERT INTO req_equipment VALUES(?,?,?)',(e['장비번호'],pid,packed(e)))
    for m in data['meetings']:
        mid=stable(m['회의번호']);timestamp=w.now()
        parsed=parse((REFERENCE/m['원본파일명']).read_bytes())
        source=parsed['source'];fingerprint=hashlib.sha256((pname+'\n'+source).encode()).hexdigest()
        reviewed={'summary':'제공된 가상 기준자료입니다. 요구사항·변경 이력에서 회의 간 변화를 확인할 수 있습니다.','items':[],'review_points':[]}
        con.execute("INSERT INTO meetings(id,fingerprint,created_at,updated_at,project,title,meeting_date,source,status,warnings,project_id,reviewed,reviewer_id,reviewer_name,reviewed_at) VALUES(?,?,?,?,?,?,?,?,'saved',?,?,?,?,?,?)",
            (mid,fingerprint,timestamp,timestamp,pname,m['회의명'],m['회의일시'],source,packed(['제공된 가상자료 · AI 분석으로 생성한 결과가 아닙니다.']),pid,packed(reviewed),'reference','제공된 가상자료',None))
        segments=[s for s in data['segments'] if s['회의번호']==m['회의번호']]
        con.execute('INSERT INTO req_meetings VALUES(?,?,?,?,?,?,?,?)',(m['회의번호'],pid,mid,int(m['회차']),m['회의일시'],m['회의명'],m['원본파일명'],packed(segments)))
    for r in data['requirements']:con.execute('INSERT INTO req_definitions VALUES(?,?,?)',(r['id'],pid,r['title']))
    for h in data['history']:
        # Supplied history is retained verbatim, including sample reviewer codes and dates.
        con.execute('INSERT INTO req_events(id,requirement_id,meeting_code,origin,data_json,created_at) VALUES(?,?,?,?,?,?)',(h['이력번호'],h['요구사항번호'],h['회의번호'],'reference',packed(h),w.now()))
    return {'project_id':pid,'imported':True,'meetings':5,'requirements':12,'events':32}


def project_info(con,pid):
    row=con.execute('SELECT r.*,p.name FROM req_projects r JOIN projects p ON p.id=r.project_id WHERE r.project_id=?',(pid,)).fetchone()
    if not row:raise HTTPException(404,'요구사항 이력이 등록된 프로젝트를 선택해 주세요.')
    return dict(row)


def events_for(con,pid,through=999999,basis='reference'):
    rows=[dict(r) for r in con.execute('SELECT e.*,m.seq,m.meeting_date,m.title AS meeting_title,m.meeting_id FROM req_events e JOIN req_meetings m ON m.code=e.meeting_code JOIN req_definitions d ON d.id=e.requirement_id WHERE d.project_id=? AND m.seq<=? ORDER BY m.seq,e.rowid',(pid,through))]
    if basis=='reference':return [r for r in rows if r['origin']=='reference']
    replacements={(r['requirement_id'],r['meeting_code']) for r in rows if r['origin']=='reviewed' and r['active']}
    return [r for r in rows if (r['origin']=='reviewed' and r['active']) or (r['origin']=='reference' and (r['requirement_id'],r['meeting_code']) not in replacements)]


def snapshots(con,pid,through=999999,basis='reference'):
    definitions={r['id']:dict(r) for r in con.execute('SELECT * FROM req_definitions WHERE project_id=?',(pid,))}
    current={};people={p['code']:p['name'] for p in con.execute('SELECT code,name FROM req_people')}
    for row in events_for(con,pid,through,basis):
        h=json.loads(row['data_json']);rid=row['requirement_id']
        item=current.setdefault(rid,{**definitions[rid],'value':'','unit':'','tolerance':'','reference_point':'','owner_id':'','due':'','state':'','approved_value':None,'approved_unit':'','approved_tolerance':'','approved_meeting':None,'targets':'','excluded':'','event_count':0})
        for src,dst in [('변경후값','value'),('단위','unit'),('공차','tolerance'),('기준점','reference_point'),('담당자사번','owner_id'),('기한','due'),('상태후','state'),('적용대상장비','targets'),('제외장비','excluded')]:
            if h.get(src,'')!='':item[dst]=h[src]
        for field in h.get('clear_fields',[]):item[field]=''
        if item['state']=='확정' or (h.get('이벤트구분')=='승인' and item['state']=='적용대기'):
            item.update(approved_value=item['value'],approved_unit=item['unit'],approved_tolerance=item['tolerance'],approved_meeting=row['meeting_code'])
        item.update(last_meeting=row['meeting_code'],last_seq=row['seq'],last_date=row['meeting_date'],event_count=item['event_count']+1,origin=row['origin'])
        item['owner_name']=people.get(item['owner_id'],item['owner_id'])
    return list(current.values())


def meeting_info(con,mid):
    row=con.execute("SELECT m.code,m.project_id,m.seq,(SELECT COUNT(*) FROM req_events e WHERE e.meeting_code=m.code AND e.origin='reference') AS event_count FROM req_meetings m WHERE m.meeting_id=?",(mid,)).fetchone()
    return dict(row) if row else None


def context_for(con,pid,code):
    meeting=con.execute('SELECT * FROM req_meetings WHERE code=? AND project_id=?',(code,pid)).fetchone()
    if not meeting:raise HTTPException(404,'해당 프로젝트의 회의를 선택해 주세요.')
    # Only events BEFORE this meeting are visible to the model. No final-answer table.
    previous=snapshots(con,pid,meeting['seq']-1,'reviewed')
    known=[{k:r[k] for k in ['id','title','value','unit','tolerance','state','approved_value','owner_id','due']} for r in previous]
    return {'project_id':pid,'meeting_code':code,'meeting_date':meeting['meeting_date'],'previous_requirements':known,
        'source_segments':[{'id':s['원문구간ID'],'text':s['원문텍스트']} for s in json.loads(meeting['segments_json'])],
        'people':[{'id':p['code'],'name':p['name']} for p in con.execute('SELECT code,name FROM req_people ORDER BY code')]}


class Candidate(w.Strict):
    matched_requirement_id:str|None
    title:str=Field(min_length=1,max_length=200)
    event_type:Literal['신규','값변경','유지확인','철회','재개','재검토','상태변경','담당기한변경','승인']
    value:str=Field(max_length=300)
    unit:str=Field(max_length=40)
    tolerance:str=Field(max_length=80)
    reference_point:str=Field(max_length=80)
    state:Literal['검토중','확정','철회','재검토','적용대기']
    owner_id:str|None
    due:str|None
    evidence_ids:list[str]=Field(min_length=1,max_length=10)
    _date=field_validator('due')(w.WorkInput.valid_date.__func__)


class Output(w.Strict):
    candidates:list[Candidate]=Field(max_length=30)


class TrialInput(w.Strict):
    project_id:str
    meeting_code:str
    actor_id:str


class ReviewCandidate(Candidate):
    decision:Literal['accept','reject']


class TrialReview(w.Strict):
    version:int
    candidates:list[ReviewCandidate]=Field(max_length=30)
    note:str=Field(min_length=1,max_length=2000)
    actor_id:str


def serialize_trial(row):
    item=dict(row)
    for key in ['context_json','output_json','metrics_json','review_json']:
        value=item.pop(key);item[key.removesuffix('_json')]=json.loads(value) if value else None
    return item


def run_trial(connection,tid,generate):
    with connection() as con:
        con.execute("UPDATE req_trials SET status='analyzing' WHERE id=?",(tid,))
        row=con.execute('SELECT * FROM req_trials WHERE id=?',(tid,)).fetchone();context=json.loads(row['context_json'])
    try:
        payload,metrics=generate(context)
        output=Output.model_validate(payload)
        allowed={s['id'] for s in context['source_segments']};known={r['id'] for r in context['previous_requirements']}
        for c in output.candidates:
            if not set(c.evidence_ids)<=allowed:raise ValueError('AI가 존재하지 않는 원문 구간을 인용했습니다.')
            if c.matched_requirement_id and c.matched_requirement_id not in known:raise ValueError('AI가 이전 회의에 없는 요구사항에 연결했습니다.')
        with connection() as con:con.execute("UPDATE req_trials SET status='review',output_json=?,metrics_json=?,version=version+1 WHERE id=?",(output.model_dump_json(),packed(metrics),tid))
    except Exception as exc:
        with connection() as con:con.execute("UPDATE req_trials SET status='failed',error=?,version=version+1 WHERE id=?",(str(exc)[:1200],tid))


def build_router(connection,parse,submit,generate):
    router=APIRouter(prefix='/api')

    @router.post('/requirements/import-demo')
    def import_reference(body:dict):
        w.pm(body.get('actor_id',''))
        with connection() as con:
            con.execute('BEGIN IMMEDIATE')
            return import_demo(con,parse)

    @router.get('/requirements')
    def listing(project_id:str,through:int|None=None,basis:Literal['reference','reviewed']='reference'):
        with connection() as con:
            project=project_info(con,project_id)
            meetings=[dict(r) for r in con.execute('SELECT code,seq,meeting_date,title,meeting_id FROM req_meetings WHERE project_id=? ORDER BY seq',(project_id,))]
            return {'project':project,'meetings':meetings,'items':snapshots(con,project_id,through if through is not None else 999999,basis),
                'people':[dict(r) for r in con.execute('SELECT code,name FROM req_people')],
                'definitions':[dict(r) for r in con.execute('SELECT id,title FROM req_definitions WHERE project_id=? ORDER BY id',(project_id,))],
                'equipment':[json.loads(r['data_json']) for r in con.execute('SELECT data_json FROM req_equipment WHERE project_id=?',(project_id,))]}

    @router.get('/requirements/{rid}/history')
    def history(rid:str,basis:Literal['reference','reviewed']='reference',through:int|None=None):
        with connection() as con:
            definition=con.execute('SELECT * FROM req_definitions WHERE id=?',(rid,)).fetchone()
            if not definition:raise HTTPException(404,'요구사항을 찾을 수 없습니다.')
            pid=definition['project_id'];events=[];byseq={}
            for r in events_for(con,pid,through if through is not None else 999999,basis):
                if r['requirement_id']!=rid:continue
                if r['seq'] not in byseq:byseq[r['seq']]={s['id']:s for s in snapshots(con,pid,r['seq'],basis)}
                before={s['id']:s for s in snapshots(con,pid,r['seq']-1,basis)}.get(rid,{})
                events.append({**r,'data':json.loads(r['data_json']),'effective_before':before.get('value',''),'snapshot':byseq[r['seq']][rid]})
            return {'requirement':dict(definition),'events':events}

    @router.get('/requirement-meetings/{code}')
    def source(code:str):
        with connection() as con:
            r=con.execute('SELECT * FROM req_meetings WHERE code=?',(code,)).fetchone()
            if not r:raise HTTPException(404,'회의를 찾을 수 없습니다.')
            result=dict(r);result['segments']=json.loads(result.pop('segments_json'));return result

    @router.get('/requirement-meetings/{code}/docx')
    def download(code:str):
        with connection() as con:r=con.execute('SELECT filename FROM req_meetings WHERE code=?',(code,)).fetchone()
        if not r:raise HTTPException(404,'회의를 찾을 수 없습니다.')
        return FileResponse(REFERENCE/r['filename'],filename=r['filename'])

    @router.get('/requirement-trials')
    def trials(project_id:str):
        with connection() as con:return [serialize_trial(r) for r in con.execute('SELECT * FROM req_trials WHERE project_id=? ORDER BY rowid DESC',(project_id,))]

    @router.post('/requirement-trials',status_code=202)
    def start_trial(body:TrialInput):
        w.pm(body.actor_id);tid=w.ident()
        with connection() as con:
            con.execute('BEGIN IMMEDIATE');project=project_info(con,body.project_id)
            if con.execute("SELECT 1 FROM req_trials WHERE status IN ('queued','analyzing')").fetchone():raise HTTPException(429,'이력 분석이 진행 중입니다. 완료 후 다시 실행해 주세요.')
            context=context_for(con,body.project_id,body.meeting_code)
            con.execute("INSERT INTO req_trials(id,project_id,meeting_code,status,context_json,project_version,created_at) VALUES(?,?,?,'queued',?,?,?)",(tid,body.project_id,body.meeting_code,packed(context),project['version'],w.now()))
        submit(run_trial,connection,tid,generate)
        return {'id':tid}

    @router.post('/requirement-trials/{tid}/review')
    def review(tid:str,body:TrialReview):
        actor=w.pm(body.actor_id)
        with connection() as con:
            con.execute('BEGIN IMMEDIATE')
            row=con.execute('SELECT * FROM req_trials WHERE id=?',(tid,)).fetchone()
            if not row:raise HTTPException(404,'분석 결과를 찾을 수 없습니다.')
            if row['status']!='review' or row['version']!=body.version:raise HTTPException(409,'이미 검토했거나 변경된 결과입니다. 다시 열어 주세요.')
            project=project_info(con,row['project_id'])
            if project['version']!=row['project_version']:raise HTTPException(409,'요구사항 검토 이력이 바뀌었습니다. 최신 정보로 다시 분석해 주세요.')
            original=json.loads(row['output_json'])['candidates']
            if len(original)!=len(body.candidates):raise HTTPException(422,'모든 후보의 반영 또는 제외 여부를 선택해 주세요.')
            context=json.loads(row['context_json']);allowed={s['id'] for s in context['source_segments']}
            meeting=con.execute('SELECT * FROM req_meetings WHERE code=?',(row['meeting_code'],)).fetchone()
            previous={s['id']:s for s in snapshots(con,row['project_id'],meeting['seq']-1,'reviewed')}
            seen=set();accepted=0
            for candidate in body.candidates:
                if candidate.decision=='reject':continue
                if not set(candidate.evidence_ids)<=allowed:raise HTTPException(422,'현재 회의에 있는 원문 근거를 선택해 주세요.')
                if candidate.owner_id and not con.execute('SELECT 1 FROM req_people WHERE code=?',(candidate.owner_id,)).fetchone():raise HTTPException(422,'담당자를 사번 기준으로 선택해 주세요.')
                rid=candidate.matched_requirement_id
                if rid:
                    target=con.execute('SELECT * FROM req_definitions WHERE id=? AND project_id=?',(rid,row['project_id'])).fetchone()
                    if not target:raise HTTPException(422,'같은 프로젝트의 요구사항만 연결할 수 있습니다.')
                else:
                    if candidate.event_type!='신규':raise HTTPException(422,'변경·철회·유지 후보는 기존 요구사항을 연결해 주세요.')
                    rid='REQ-LOCAL-'+uuid.uuid4().hex[:8].upper()
                    con.execute('INSERT INTO req_definitions VALUES(?,?,?)',(rid,row['project_id'],candidate.title))
                if rid in seen:raise HTTPException(422,'같은 요구사항의 중복 후보는 하나만 반영해 주세요.')
                seen.add(rid);before=previous.get(rid,{})
                if candidate.event_type=='유지확인' and (not before or candidate.value!=before['value']):raise HTTPException(422,'유지확인은 이전값과 같은 값을 사용해야 합니다.')
                if candidate.event_type=='철회' and candidate.state!='철회':raise HTTPException(422,'철회 항목의 상태를 철회로 선택해 주세요.')
                if candidate.event_type=='재개' and before.get('state')!='철회':raise HTTPException(422,'철회된 요구사항만 재개할 수 있습니다.')
                if candidate.event_type=='신규' and before:raise HTTPException(422,'기존 요구사항의 변경 유형을 선택해 주세요.')
                if candidate.event_type!='신규' and not before:raise HTTPException(422,'이전 회의에 없던 요구사항은 신규로 등록해 주세요.')
                h={'이벤트구분':candidate.event_type,'변경전값':before.get('value',''),'변경후값':candidate.value,'단위':candidate.unit,'공차':candidate.tolerance,'기준점':candidate.reference_point,'담당자사번':candidate.owner_id or '',
                    '기한':candidate.due or '', '상태전':before.get('state',''),'상태후':candidate.state,'적용대상장비':before.get('targets',''),'제외장비':before.get('excluded',''),
                    '근거원문구간ID':candidate.evidence_ids[0],'근거원문구간IDs':candidate.evidence_ids,'확정자명':actor['name'],'확정일시':w.now(),'비고':body.note}
                con.execute("UPDATE req_events SET active=0 WHERE requirement_id=? AND meeting_code=? AND origin='reviewed' AND active=1",(rid,row['meeting_code']))
                con.execute("INSERT INTO req_events(id,requirement_id,meeting_code,origin,data_json,trial_id,reviewer_name,created_at) VALUES(?,?,?,'reviewed',?,?,?,?)",(w.ident(),rid,row['meeting_code'],packed(h),tid,actor['name'],w.now()))
                accepted+=1
            con.execute("UPDATE req_trials SET status='done',review_json=?,version=version+1 WHERE id=?",(packed({'actor':actor['name'],'note':body.note,'candidates':[c.model_dump() for c in body.candidates],'reviewed_at':w.now()}),tid))
            if accepted:con.execute('UPDATE req_projects SET version=version+1 WHERE project_id=?',(row['project_id'],))
            if accepted:
                # Later AI reviews were based on the old history. Retain their audit but
                # stop treating them as current until they are analyzed/reviewed again.
                later=[r['code'] for r in con.execute('SELECT code FROM req_meetings WHERE project_id=? AND seq>?',(row['project_id'],meeting['seq']))]
                for code in later:
                    con.execute("UPDATE req_events SET active=0 WHERE meeting_code=? AND origin='reviewed'",(code,))
                    con.execute("UPDATE req_trials SET status='stale',version=version+1 WHERE meeting_code=? AND status='done'",(code,))
            return {'accepted':accepted,'excluded':len(body.candidates)-accepted}

    return router
