"""Project and work-item lifecycle for the single-PC role-playing MVP."""
from __future__ import annotations
import csv, io, json, sqlite3, uuid
from datetime import date, datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal

PEOPLE=[{'id':'pm','name':'박서연','role':'PM','department':'프로젝트 관리'},
        {'id':'design','name':'이준호','role':'담당자','department':'기계설계'},
        {'id':'quality','name':'정유진','role':'담당자','department':'품질'}]
STATES=['미착수','진행중','검토요청','보완요청','완료']
def now():return datetime.now(timezone.utc).isoformat()
def ident():return str(uuid.uuid4())
def person(actor_id):
    actor=next((p for p in PEOPLE if p['id']==actor_id),None)
    if not actor:raise HTTPException(400,'체험할 사용자를 선택해 주세요.')
    return actor
def pm(actor_id):
    actor=person(actor_id)
    if actor['role']!='PM':raise HTTPException(403,'PM 역할에서 처리할 수 있습니다.')
    return actor
def event(con,item_id,actor,kind,note,before,after):
    con.execute('INSERT INTO work_events(id,item_id,created_at,actor_id,actor_name,kind,note,before_json,after_json) VALUES(?,?,?,?,?,?,?,?,?)',
      (ident(),item_id,now(),actor['id'],actor['name'],kind,note,json.dumps(before,ensure_ascii=False) if before else None,json.dumps(after,ensure_ascii=False)))
def project_for(con,name):
    name=name.strip() or '미분류'
    row=con.execute('SELECT id FROM projects WHERE name=?',(name,)).fetchone()
    if row:return row['id']
    project_id=ident();con.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,?)',(project_id,name,'','박서연','',now(),1))
    return project_id

def register_meeting(con,meeting_id,reviewed,actor_id='pm',migration=False):
    meeting=con.execute('SELECT * FROM meetings WHERE id=?',(meeting_id,)).fetchone()
    project_id=meeting['project_id'] or project_for(con,meeting['project'])
    con.execute('UPDATE meetings SET project_id=? WHERE id=?',(project_id,meeting_id))
    actor={'id':'system','name':'기존 기록 연결'} if migration else person(actor_id)
    for index,item in enumerate(reviewed['items']):
        if con.execute('SELECT 1 FROM work_items WHERE meeting_id=? AND source_index=?',(meeting_id,index)).fetchone():continue
        item_id=ident();timestamp=now()
        status='미착수' if item['category']=='할일' else None
        con.execute('INSERT INTO work_items(id,project_id,meeting_id,source_index,category,content,owner,due,agreement,status,evidence_ids,created_at,updated_at,version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1)',
          (item_id,project_id,meeting_id,index,item['category'],item['content'],item['owner'],item['due'],item['agreement'],status,json.dumps(item['evidence_ids']),timestamp,timestamp))
        event(con,item_id,actor,'등록','기존 검토 기록에서 업무 목록으로 연결' if migration else '회의록 검토 후 업무 목록에 등록',None,dict(con.execute('SELECT * FROM work_items WHERE id=?',(item_id,)).fetchone()))

def initialize(con):
    con.execute('CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE,description TEXT NOT NULL,pm_name TEXT NOT NULL,target_date TEXT NOT NULL,created_at TEXT NOT NULL,version INTEGER NOT NULL)')
    columns={row['name'] for row in con.execute('PRAGMA table_info(meetings)')}
    if 'project_id' not in columns:con.execute('ALTER TABLE meetings ADD COLUMN project_id TEXT')
    con.execute('CREATE TABLE IF NOT EXISTS work_items(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),meeting_id TEXT REFERENCES meetings(id),source_index INTEGER,category TEXT NOT NULL,content TEXT NOT NULL,owner TEXT,due TEXT,agreement TEXT,status TEXT,evidence_ids TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,version INTEGER NOT NULL,UNIQUE(meeting_id,source_index))')
    con.execute('CREATE TABLE IF NOT EXISTS work_events(id TEXT PRIMARY KEY,item_id TEXT NOT NULL REFERENCES work_items(id),created_at TEXT NOT NULL,actor_id TEXT NOT NULL,actor_name TEXT NOT NULL,kind TEXT NOT NULL,note TEXT NOT NULL,before_json TEXT,after_json TEXT NOT NULL)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_work_project ON work_items(project_id)')
    con.execute('CREATE INDEX IF NOT EXISTS idx_event_item ON work_events(item_id,created_at)')
    for meeting in con.execute('SELECT * FROM meetings').fetchall():
        if not meeting['project_id']:
            con.execute('UPDATE meetings SET project_id=? WHERE id=?',(project_for(con,meeting['project']),meeting['id']))
        if meeting['status']=='saved' and meeting['reviewed']:
            register_meeting(con,meeting['id'],json.loads(meeting['reviewed']),migration=True)

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class ProjectInput(Strict):
    name:str=Field(min_length=1,max_length=160)
    description:str=Field(default='',max_length=1000)
    target_date:str=''
    actor_id:str='pm'
    @field_validator('target_date')
    @classmethod
    def valid_date(cls,v):
        if v and (len(v)!=10 or date.fromisoformat(v).isoformat()!=v):raise ValueError('날짜 형식을 확인해 주세요.')
        return v
class WorkInput(Strict):
    project_id:str
    category:Literal['할일','고객요구','설계변경']
    content:str=Field(min_length=1,max_length=800)
    owner:str|None=None
    due:str|None=None
    agreement:Literal['검토중','확정','취소','불명확']|None=None
    note:str=Field(min_length=1,max_length=2000)
    actor_id:str
    @field_validator('due')
    @classmethod
    def valid_date(cls,v):
        if v is not None and (len(v)!=10 or date.fromisoformat(v).isoformat()!=v):raise ValueError('날짜 형식을 확인해 주세요.')
        return v
class WorkEdit(Strict):
    version:int
    content:str=Field(min_length=1,max_length=800)
    owner:str|None
    due:str|None
    agreement:Literal['검토중','확정','취소','불명확']|None
    note:str=Field(min_length=1,max_length=2000)
    actor_id:str
    _date=field_validator('due')(WorkInput.valid_date.__func__)
class WorkAction(Strict):
    version:int
    action:Literal['start','note','submit','approve','return','reopen']
    note:str=Field(min_length=1,max_length=2000)
    actor_id:str

def build_router(connection):
    router=APIRouter(prefix='/api')
    def get_item(con,item_id):
        row=con.execute('SELECT w.*,p.name AS project_name,m.title AS meeting_title FROM work_items w JOIN projects p ON p.id=w.project_id LEFT JOIN meetings m ON m.id=w.meeting_id WHERE w.id=?',(item_id,)).fetchone()
        if not row:raise HTTPException(404,'업무 항목을 찾을 수 없습니다.')
        item=dict(row);item['evidence_ids']=json.loads(item['evidence_ids'])
        return item
    def counts(con,project_id=None):
        query='SELECT * FROM work_items'+(' WHERE project_id=?' if project_id else '')
        items=[dict(row) for row in con.execute(query,(project_id,) if project_id else ())]
        tasks=[x for x in items if x['category']=='할일']
        open_tasks=[x for x in tasks if x['status']!='완료']
        today=datetime.now(timezone(timedelta(hours=9))).date().isoformat()
        return {'items':len(items),'tasks':len(tasks),'open':len(open_tasks),'review':sum(x['status']=='검토요청' for x in tasks),'done':sum(x['status']=='완료' for x in tasks),'overdue':sum(bool(x['due'] and x['due']<today) for x in open_tasks),'unassigned':sum(not x['owner'] for x in open_tasks),'undated':sum(not x['due'] for x in open_tasks),'pending_agreement':sum(x['category']!='할일' and x['agreement'] in ('검토중','불명확') for x in items)}

    @router.get('/people')
    def people():return PEOPLE

    @router.get('/projects')
    def projects():
        with connection() as con:
            result=[]
            for row in con.execute('SELECT * FROM projects ORDER BY created_at'):
                project=dict(row);project['counts']=counts(con,project['id'])
                project['meeting_count']=con.execute('SELECT COUNT(*) FROM meetings WHERE project_id=?',(project['id'],)).fetchone()[0]
                result.append(project)
            return result

    @router.post('/projects',status_code=201)
    def create_project(body:ProjectInput):
        actor=pm(body.actor_id);project_id=ident()
        try:
            with connection() as con:
                con.execute('INSERT INTO projects VALUES(?,?,?,?,?,?,1)',(project_id,body.name,body.description,actor['name'],body.target_date,now()))
        except sqlite3.IntegrityError:raise HTTPException(409,'같은 이름의 프로젝트가 있습니다.')
        return {'id':project_id}

    @router.get('/overview')
    def overview():
        with connection() as con:
            return {'counts':counts(con),'meeting_review':con.execute("SELECT COUNT(*) FROM meetings WHERE status IN ('review','failed')").fetchone()[0],'today':datetime.now(timezone(timedelta(hours=9))).date().isoformat(),'local_role_simulation':True}

    @router.get('/work-items')
    def list_items(project_id:str|None=None):
        with connection() as con:
            rows=con.execute('SELECT id FROM work_items'+(' WHERE project_id=?' if project_id else '')+' ORDER BY updated_at DESC',(project_id,) if project_id else ()).fetchall()
            return [get_item(con,row['id']) for row in rows]

    @router.post('/work-items',status_code=201)
    def create_item(body:WorkInput):
        actor=pm(body.actor_id)
        if body.category=='할일' and body.agreement is not None:raise HTTPException(422,'할일에는 합의 상태를 지정하지 않습니다.')
        if body.category!='할일' and body.agreement is None:raise HTTPException(422,'요구·변경안의 합의 상태를 선택해 주세요.')
        with connection() as con:
            if not con.execute('SELECT id FROM projects WHERE id=?',(body.project_id,)).fetchone():raise HTTPException(404,'프로젝트를 선택해 주세요.')
            item_id=ident();timestamp=now()
            con.execute('INSERT INTO work_items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1)',(item_id,body.project_id,None,None,body.category,body.content,body.owner,body.due,body.agreement,'미착수' if body.category=='할일' else None,'[]',timestamp,timestamp))
            item=get_item(con,item_id);event(con,item_id,actor,'직접 등록',body.note,None,item)
            return item

    @router.get('/work-items/{item_id}')
    def item_detail(item_id:str):
        with connection() as con:
            item=get_item(con,item_id)
            item['events']=[{**dict(row),'before_json':json.loads(row['before_json']) if row['before_json'] else None,'after_json':json.loads(row['after_json'])} for row in con.execute('SELECT * FROM work_events WHERE item_id=? ORDER BY created_at DESC,rowid DESC',(item_id,))]
            item['source_lines']=[]
            if item['meeting_id']:
                source=con.execute('SELECT source FROM meetings WHERE id=?',(item['meeting_id'],)).fetchone()['source']
                item['source_lines']=[{'id':f'L{i+1:03d}','text':text.strip()} for i,text in enumerate(line for line in source.splitlines() if line.strip()) if f'L{i+1:03d}' in item['evidence_ids']]
            return item

    @router.patch('/work-items/{item_id}')
    def edit_item(item_id:str,body:WorkEdit):
        actor=pm(body.actor_id)
        with connection() as con:
            con.execute('BEGIN IMMEDIATE');before=get_item(con,item_id)
            if before['version']!=body.version:raise HTTPException(409,'다른 화면에서 내용이 바뀌었습니다. 다시 열어 주세요.')
            if before['status'] in ('검토요청','완료'):raise HTTPException(409,'검토 중이거나 완료된 업무는 보완 또는 재개 처리 후 수정해 주세요.')
            if (before['category']=='할일') != (body.agreement is None):raise HTTPException(422,'항목 종류와 합의 상태를 확인해 주세요.')
            con.execute('UPDATE work_items SET content=?,owner=?,due=?,agreement=?,updated_at=?,version=version+1 WHERE id=?',(body.content,body.owner,body.due,body.agreement,now(),item_id))
            after=get_item(con,item_id);event(con,item_id,actor,'내용 수정',body.note,before,after);return after

    @router.post('/work-items/{item_id}/actions')
    def action(item_id:str,body:WorkAction):
        actor=person(body.actor_id)
        with connection() as con:
            con.execute('BEGIN IMMEDIATE');before=get_item(con,item_id)
            if before['version']!=body.version:raise HTTPException(409,'다른 화면에서 내용이 바뀌었습니다. 다시 열어 주세요.')
            is_pm=actor['role']=='PM';assigned=before['owner']==actor['name']
            current=before['status'];target=current
            if body.action=='note':
                if not (is_pm or assigned):raise HTTPException(403,'담당자 또는 PM만 기록을 남길 수 있습니다.')
                kind='업무 메모'
            else:
                if before['category']!='할일':raise HTTPException(422,'진행 상태는 할일에서만 변경합니다. 요구·변경안의 합의 상태는 내용 수정에서 관리합니다.')
                if body.action in ('start','submit'):
                    if not assigned:raise HTTPException(403,'배정된 담당자 역할로 전환해 주세요.')
                    valid={'start':['미착수','보완요청'],'submit':['진행중','보완요청']}[body.action]
                    if current not in valid:raise HTTPException(409,'현재 상태에서는 이 동작을 할 수 없습니다.')
                    target='진행중' if body.action=='start' else '검토요청'
                    kind='업무 시작' if body.action=='start' else '검토 요청'
                else:
                    if not is_pm:raise HTTPException(403,'PM만 최종 확인할 수 있습니다.')
                    required='완료' if body.action=='reopen' else '검토요청'
                    if current!=required:raise HTTPException(409,'현재 상태에서는 이 동작을 할 수 없습니다.')
                    target={'approve':'완료','return':'보완요청','reopen':'진행중'}[body.action]
                    kind={'approve':'완료 확인','return':'보완 요청','reopen':'업무 재개'}[body.action]
            con.execute('UPDATE work_items SET status=?,updated_at=?,version=version+1 WHERE id=?',(target,now(),item_id))
            after=get_item(con,item_id);event(con,item_id,actor,kind,body.note,before,after);return after

    @router.get('/work-export')
    def export(project_id:str|None=None):
        with connection() as con:
            rows=con.execute('SELECT id FROM work_items'+(' WHERE project_id=?' if project_id else ''),(project_id,) if project_id else ()).fetchall()
            stream=io.StringIO();writer=csv.writer(stream)
            writer.writerow(['프로젝트','종류','내용','담당자','기한','합의 상태','진행 상태','최근 변경'])
            def safe(value):
                text=str(value or '')
                return "'"+text if text.lstrip().startswith(('=','+','-','@')) else text
            for row in rows:
                item=get_item(con,row['id']);writer.writerow([safe(item[k]) for k in ['project_name','category','content','owner','due','agreement','status','updated_at']])
            return Response('\ufeff'+stream.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="project-work.csv"'})
    return router
