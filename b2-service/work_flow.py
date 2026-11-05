"""Agenda grouping and human-reviewed decision follow-up; never infer dependencies."""
import json
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import Field, field_validator
from typing import Literal
import workflow as w


def initialize(con):
    if 'agenda_id' not in {r['name'] for r in con.execute('PRAGMA table_info(work_items)')}:
        con.execute('ALTER TABLE work_items ADD COLUMN agenda_id TEXT')
    con.execute('CREATE TABLE IF NOT EXISTS agendas(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,title TEXT NOT NULL,source_meeting_id TEXT UNIQUE,grouping TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1)')
    con.execute('CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,agenda_id TEXT,meeting_id TEXT NOT NULL,source_index INTEGER NOT NULL,content TEXT NOT NULL,evidence_ids TEXT NOT NULL,owner TEXT,due TEXT,state TEXT NOT NULL DEFAULT \'대기\',result TEXT NOT NULL DEFAULT \'\',version INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL,UNIQUE(meeting_id,source_index))')
    con.execute('CREATE TABLE IF NOT EXISTS flow_events(id TEXT PRIMARY KEY,entity_id TEXT NOT NULL,actor_name TEXT NOT NULL,created_at TEXT NOT NULL,note TEXT NOT NULL,before_json TEXT,after_json TEXT NOT NULL)')


def register_meeting(con, meeting_id, reviewed):
    meeting=con.execute('SELECT * FROM meetings WHERE id=?',(meeting_id,)).fetchone()
    agenda_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'b2-agenda:'+meeting_id))
    created=con.execute('INSERT OR IGNORE INTO agendas(id,project_id,title,source_meeting_id,grouping) VALUES(?,?,?,?,?)',
        (agenda_id,meeting['project_id'],meeting['title'],meeting_id,'meeting')).rowcount
    # Only seed once: intentional ungrouping must survive every server restart.
    if created:
        con.execute('UPDATE work_items SET agenda_id=? WHERE meeting_id=? AND agenda_id IS NULL',(agenda_id,meeting_id))
    for index,point in enumerate(reviewed.get('review_points',[])):
        con.execute('INSERT OR IGNORE INTO decisions(id,project_id,agenda_id,meeting_id,source_index,content,evidence_ids,updated_at) VALUES(?,?,?,?,?,?,?,?)',
            (w.ident(),meeting['project_id'],agenda_id,meeting_id,index,point['content'],json.dumps(point['evidence_ids']),w.now()))


class AgendaInput(w.Strict):
    project_id:str
    title:str=Field(min_length=1,max_length=200)
    item_ids:list[str]=Field(default_factory=list,max_length=300)
    item_versions:dict[str,int]=Field(default_factory=dict)
    version:int|None=None
    note:str=Field(min_length=1,max_length=2000)
    actor_id:str


class DecisionInput(w.Strict):
    version:int
    owner:str|None=None
    due:str|None=None
    state:Literal['대기','보류','해결']
    result:str=Field(max_length=2000)
    note:str=Field(min_length=1,max_length=2000)
    actor_id:str
    _date=field_validator('due')(w.WorkInput.valid_date.__func__)


def audit(con,entity_id,actor,note,before,after):
    con.execute('INSERT INTO flow_events VALUES(?,?,?,?,?,?,?)',(w.ident(),entity_id,actor['name'],w.now(),note,json.dumps(before,ensure_ascii=False) if before else None,json.dumps(after,ensure_ascii=False)))


def build_router(connection):
    router=APIRouter()

    @router.get('/work-flow')
    def flow():
        with connection() as con:
            agendas=[dict(r) for r in con.execute('SELECT a.*,a.rowid AS number,m.meeting_date FROM agendas a LEFT JOIN meetings m ON m.id=a.source_meeting_id ORDER BY m.meeting_date DESC,m.created_at DESC,a.rowid DESC')]
            decisions=[]
            for row in con.execute('SELECT d.*,m.title AS meeting_title,m.meeting_date,p.name AS project_name FROM decisions d JOIN meetings m ON m.id=d.meeting_id JOIN projects p ON p.id=d.project_id ORDER BY d.updated_at DESC'):
                item=dict(row);item['evidence_ids']=json.loads(item['evidence_ids'])
                source=con.execute('SELECT source FROM meetings WHERE id=?',(item['meeting_id'],)).fetchone()['source']
                item['source_lines']=[{'id':f'L{i+1:03d}','text':line.strip()} for i,line in enumerate(s for s in source.splitlines() if s.strip()) if f'L{i+1:03d}' in item['evidence_ids']]
                item['events']=[dict(e) for e in con.execute('SELECT actor_name,created_at,note,after_json FROM flow_events WHERE entity_id=? ORDER BY rowid DESC',(item['id'],))]
                decisions.append(item)
            return {'agendas':agendas,'decisions':decisions}

    def save_agenda(body,agenda_id=None):
        actor=w.pm(body.actor_id)
        with connection() as con:
            con.execute('BEGIN IMMEDIATE')
            if not con.execute('SELECT 1 FROM projects WHERE id=?',(body.project_id,)).fetchone():raise HTTPException(404,'프로젝트를 찾을 수 없습니다.')
            before=None
            if agenda_id:
                row=con.execute('SELECT * FROM agendas WHERE id=?',(agenda_id,)).fetchone()
                if not row:raise HTTPException(404,'안건을 찾을 수 없습니다.')
                before=dict(row)
                if row['project_id']!=body.project_id:raise HTTPException(422,'안건의 프로젝트는 변경할 수 없습니다.')
                if row['version']!=body.version:raise HTTPException(409,'안건이 변경되었습니다. 다시 열어 주세요.')
            else:agenda_id=w.ident()
            selected=set(body.item_ids)
            rows=[dict(r) for r in con.execute('SELECT * FROM work_items WHERE project_id=?',(body.project_id,))]
            if not selected.issubset({r['id'] for r in rows}):raise HTTPException(422,'같은 프로젝트의 항목만 연결할 수 있습니다.')
            changed=[r for r in rows if (r['id'] in selected and r['agenda_id']!=agenda_id) or (r['agenda_id']==agenda_id and r['id'] not in selected)]
            for row in changed:
                if body.item_versions.get(row['id'])!=row['version']:raise HTTPException(409,'연결할 항목이 변경되었습니다. 다시 열어 주세요.')
            if before:con.execute('UPDATE agendas SET title=?,grouping=\'confirmed\',version=version+1 WHERE id=?',(body.title,agenda_id))
            else:con.execute('INSERT INTO agendas(id,project_id,title,grouping) VALUES(?,?,?,\'confirmed\')',(agenda_id,body.project_id,body.title))
            for row in changed:
                target=agenda_id if row['id'] in selected else None
                con.execute('UPDATE work_items SET agenda_id=?,version=version+1,updated_at=? WHERE id=?',(target,w.now(),row['id']))
                after=dict(con.execute('SELECT * FROM work_items WHERE id=?',(row['id'],)).fetchone())
                w.event(con,row['id'],actor,'안건 연결',body.note,row,after)
                # Invalidate concurrently open grouping forms for the source agenda too.
                if row['agenda_id'] and row['agenda_id']!=agenda_id:con.execute('UPDATE agendas SET version=version+1 WHERE id=?',(row['agenda_id'],))
            after=dict(con.execute('SELECT * FROM agendas WHERE id=?',(agenda_id,)).fetchone())
            audit(con,agenda_id,actor,body.note,before,after)
            return after

    @router.post('/agendas',status_code=201)
    def create_agenda(body:AgendaInput):return save_agenda(body)

    @router.patch('/agendas/{agenda_id}')
    def edit_agenda(agenda_id:str,body:AgendaInput):return save_agenda(body,agenda_id)

    @router.patch('/decisions/{decision_id}')
    def edit_decision(decision_id:str,body:DecisionInput):
        actor=w.pm(body.actor_id)
        if body.state in ('해결','보류') and not body.result.strip():raise HTTPException(422,'결정 결과 또는 보류 사유를 적어 주세요.')
        with connection() as con:
            con.execute('BEGIN IMMEDIATE')
            row=con.execute('SELECT * FROM decisions WHERE id=?',(decision_id,)).fetchone()
            if not row:raise HTTPException(404,'확인 사항을 찾을 수 없습니다.')
            before=dict(row)
            if row['version']!=body.version:raise HTTPException(409,'확인 사항이 변경되었습니다. 다시 열어 주세요.')
            con.execute('UPDATE decisions SET owner=?,due=?,state=?,result=?,version=version+1,updated_at=? WHERE id=?',(body.owner,body.due,body.state,body.result,w.now(),decision_id))
            after=dict(con.execute('SELECT * FROM decisions WHERE id=?',(decision_id,)).fetchone())
            audit(con,decision_id,actor,body.note,before,after)
            return {'id':decision_id}

    return router
