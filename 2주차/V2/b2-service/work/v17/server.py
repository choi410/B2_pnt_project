"""Separate four-person LAN trial, retaining the existing workflow."""
from __future__ import annotations
from contextlib import asynccontextmanager, contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
import hashlib, hmac, json, os, secrets, sqlite3, threading, time, uuid, zipfile, io, re, subprocess
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from work.v17.documents import ensure_document, task_notification, notify, save_content
from work.v17.intake_review import active
from work.v17 import team_config

ROOT=Path(__file__).resolve().parents[2]
DATA_DIR=Path(os.environ.get('B2_TEAM_DATA_DIR',str(ROOT/'data'/'v17'))).resolve()
if DATA_DIR==(ROOT/'data'/'v16').resolve():raise RuntimeError('The v1.6 data directory must not be used by the team trial.')
DB=DATA_DIR/'workspace.sqlite3'
FILES=DATA_DIR/'files'
POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix='b2-v1')
PREVIEW_POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix='b2-preview')
AI_LOCK=threading.Lock()
KST=timezone(timedelta(hours=9))
COOKIE='b2_v17_session'
DEMO_PASSWORD='demo2026!'
DEMO_MODE=os.environ.get('B2_DEMO_MODE','1')=='1'
def now():return datetime.now(KST).isoformat(timespec='seconds')
def uid():return uuid.uuid4().hex
@contextmanager
def connect():
 c=sqlite3.connect(DB,timeout=20);c.row_factory=sqlite3.Row
 try:
  with c:yield c
 finally:c.close()
def read(c,kind,id):
 r=c.execute('SELECT payload FROM records WHERE kind=? AND id=?',(kind,id)).fetchone()
 if not r:raise HTTPException(404,'항목을 찾을 수 없습니다.')
 return json.loads(r[0])
def save(c,kind,data):
 if kind=='meeting':ensure_document(data)
 c.execute('INSERT INTO records(kind,id,payload) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload',(kind,data['id'],json.dumps(data,ensure_ascii=False)))
def all_records(c,kind):return [json.loads(r[0]) for r in c.execute('SELECT payload FROM records WHERE kind=?',(kind,))]
def digest(password,salt):return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),210000).hex()
def ev(t,actor,action,note='',changes=None):
 t.setdefault('events',[]).append({'at':now(),'actor':actor,'action':action,'note':note,'changes':changes})
def init():
 DB.parent.mkdir(parents=True,exist_ok=True);FILES.mkdir(parents=True,exist_ok=True)
 with connect() as c:
  c.execute('PRAGMA journal_mode=WAL')
  c.execute('CREATE TABLE IF NOT EXISTS records(kind TEXT,id TEXT,payload TEXT NOT NULL,PRIMARY KEY(kind,id))')
  c.execute('CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,salt TEXT NOT NULL,password TEXT NOT NULL)')
  c.execute('CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL,expires REAL NOT NULL)')
  c.execute('CREATE TABLE IF NOT EXISTS login_limits(id TEXT PRIMARY KEY,failures INTEGER NOT NULL,last REAL NOT NULL)')
  team_config.initialize_people(sys.modules[__name__],c)
  for m in all_records(c,'meeting'):
   changed='document_status' not in m;ensure_document(m)
   if m.get('change_scan_state') in ('running','queued'):m.update(change_scan_state='failed',change_scan_error='서버 재시작으로 분석이 중단되었습니다. 다시 실행해 주세요.');changed=True
   if m['analysis_state'] in ('running','queued'):m.update(analysis_state='failed',error='서버 재시작으로 분석이 중단되었습니다. 다시 분석해 주세요.');changed=True
   if not m.get('fingerprint') and m.get('docx') and Path(m['docx']).is_file():m['fingerprint']=hashlib.sha256(Path(m['docx']).read_bytes()).hexdigest();changed=True
   if changed:save(c,'meeting',m)
  for d in all_records(c,'import'):
   if d.get('analysis_state') in ('running','queued'):
    d.update(analysis_state='failed',analysis_error='서버 재시작으로 분석이 중단되었습니다. 다시 분석해 주세요.',draft_version=d.get('draft_version',1)+1);save(c,'import',d)

@asynccontextmanager
async def lifespan(app):
 init()
 with connect() as c:
  for j in all_records(c,'context_draft'):
   if j['state'] in ('queued','running'):
    j.update(state='failed',error='서버가 재시작되었습니다. 다시 요청해 주세요.');save(c,'context_draft',j)
 yield
app=FastAPI(title='PNT 회의록 업무 관리',version='1.7.2-preview',lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=team_config.HOSTS)
@app.middleware('http')
async def local_boundary(req,call_next):
 if not req.client or not team_config.allowed_client(req.client.host):return JSONResponse({'detail':'공동 테스트에 허용된 네트워크에서 접속해 주세요.'},403)
 if req.method in ('POST','PATCH','PUT','DELETE'):
  if req.headers.get('X-B2-Request')!='workspace':return JSONResponse({'detail':'요청을 다시 시도해 주세요.'},403)
  origin=req.headers.get('origin')
  if origin and origin not in team_config.ORIGINS:return JSONResponse({'detail':'허용되지 않은 요청입니다.'},403)
 res=await call_next(req);res.headers['X-Content-Type-Options']='nosniff';res.headers['Referrer-Policy']='same-origin';res.headers['Cache-Control']='no-store'
 return res
def user(req:Request):
 token=req.cookies.get(COOKIE,'')
 with connect() as c:
  row=c.execute('SELECT user_id FROM sessions WHERE token=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
  if not row:raise HTTPException(401,'로그인이 필요합니다.')
  return read(c,'person',row[0])
def project(c,pid,actor,pm=False):
 p=read(c,'project',pid)
 if actor['id'] not in p['members']:raise HTTPException(403,'이 프로젝트에 접근할 수 없습니다.')
 if pm and actor['id']!=p['pm']:raise HTTPException(403,'이 프로젝트의 PM이 처리할 수 있습니다.')
 return p
def version(record,v):
 if record['version']!=v:raise HTTPException(409,'다른 변경이 먼저 저장되었습니다. 화면을 새로고침해 주세요.')
def due(value):
 if not value:return None
 try:
  if date.fromisoformat(value).isoformat()!=value:raise ValueError()
 except (ValueError,TypeError):raise HTTPException(422,'기한은 올바른 날짜로 입력해 주세요.')
 return value
def fields(p,d):
 title=str(d.get('title','')).strip()
 if not title or len(title)>1000:raise HTTPException(422,'업무 내용을 1~1000자로 입력해 주세요.')
 if d.get('kind') not in ('업무','확인사항'):raise HTTPException(422,'항목 구분을 확인해 주세요.')
 for key in ('owner_id','reviewer_id'):
  if d.get(key) and d[key] not in p['members']:raise HTTPException(422,'프로젝트 참여자 중에서 담당자를 선택해 주세요.')
 required=d.get('requires_review',True) if d.get('kind')=='업무' else True
 if required and not d.get('reviewer_id'):raise HTTPException(422,'확인자를 지정해 주세요.')
 if not required:d['reviewer_id']=None
 if d.get('kind')=='업무' and d.get('owner_id') and d['owner_id']==d.get('reviewer_id'):raise HTTPException(422,'업무 담당자와 완료 확인자는 서로 다르게 지정해 주세요.')
 start=due(d.get('start'));end=due(d.get('due'))
 if start and end and start>end:raise HTTPException(422,'시작 예정일은 완료 목표일보다 늦을 수 없습니다.')
 return {k:d.get(k) or None for k in ('owner_id','reviewer_id')}|{'title':title,'start':start,'due':end,'kind':d['kind'],'requires_review':required}
class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Login(Strict):username:str=Field(max_length=80);password:str=Field(max_length=128)
@app.get('/api/health')
def health():return {'ok':True,'version':'1.7.2-preview','storage':'SQLite','synthetic_data':True,'demo_mode':DEMO_MODE,'workspace':'b2-team-v1.7','team_size':4,'lan_url':f'http://{team_config.LAN_IP}:{team_config.PORT}/' if team_config.LAN_IP else None}
@app.get('/api/demo-accounts')
def accounts():
 with connect() as c:return all_records(c,'person')
class DemoLogin(Strict):username:str=Field(max_length=80)
def issue_session(c,person_id):
 c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
 token=secrets.token_urlsafe(32);c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),person_id,time.time()+43200))
 res=JSONResponse({'ok':True});res.set_cookie(COOKIE,token,httponly=True,samesite='strict',max_age=43200);return res
@app.post('/api/demo-login')
def demo_login(body:DemoLogin):
 if not DEMO_MODE:raise HTTPException(403,'빠른 체험 로그인이 꺼져 있습니다.')
 with connect() as c:
  read(c,'person',body.username)
  return issue_session(c,body.username)
@app.post('/api/login')
def login(body:Login):
 with connect() as c:
  limit=c.execute('SELECT * FROM login_limits WHERE id=?',(body.username,)).fetchone()
  if limit and limit['failures']>=8 and time.time()-limit['last']<60:raise HTTPException(429,'잠시 후 다시 로그인해 주세요.')
  row=c.execute('SELECT * FROM users WHERE id=?',(body.username,)).fetchone()
  ok=row and hmac.compare_digest(row['password'],digest(body.password,row['salt']))
  if not ok:
   c.execute('INSERT INTO login_limits VALUES(?,1,?) ON CONFLICT(id) DO UPDATE SET failures=CASE WHEN last < ? THEN 1 ELSE failures+1 END,last=excluded.last',(body.username,time.time(),time.time()-60));c.commit()
   raise HTTPException(401,'계정 또는 비밀번호를 확인해 주세요.')
  c.execute('DELETE FROM login_limits WHERE id=?',(body.username,));c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
  token=secrets.token_urlsafe(32);c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),row['id'],time.time()+43200))
 res=JSONResponse({'ok':True});res.set_cookie(COOKIE,token,httponly=True,samesite='strict',max_age=43200);return res
@app.post('/api/logout')
def logout(req:Request):
 with connect() as c:c.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(req.cookies.get(COOKIE,'').encode()).hexdigest(),))
 res=JSONResponse({'ok':True});res.delete_cookie(COOKIE);return res
@app.get('/api/bootstrap')
def bootstrap(actor=Depends(user)):
 with connect() as c:
  ps=[p for p in all_records(c,'project') if actor['id'] in p['members']];ids={p['id'] for p in ps}
  visible=[m for m in all_records(c,'meeting') if m['project_id'] in ids];ms=[m for m in visible if not m.get('deleted_at')];archived=[{k:m[k] for k in ('id','title','project_id','deleted_at')} for m in visible if m.get('deleted_at')];ts=[t for t in all_records(c,'task') if t['project_id'] in ids]
  for p in ps:p['reviewer_ids']=sorted(eligible_reviewers(c,p))
  for t in ts:
   t['attachments']=[{k:v for k,v in a.items() if k!='path'} for a in t['attachments']]
  from work.v17.task_attention import visible_tokens
  attention=visible_tokens(sys.modules[__name__],c,actor,ts,ps)
  for t in ts:t['unseen']=attention.get(t['id'],{})
  imports=[{'id':x['id'],'title':x.get('title') or x.get('filename') or '등록 중인 회의록','created_at':x['created_at'],'version':x.get('draft_version',1)} for x in all_records(c,'import') if x['actor_id']==actor['id'] and not x.get('meeting_id') and not x.get('deleted_at')]
  return {'user':actor,'people':all_records(c,'person'),'projects':ps,'meetings':[{k:v for k,v in m.items() if k not in ('docx','pdf','txt','lines','sections','candidates','revisions','original_source','ai_snapshot','reviewed_bundle')}|{'pending':sum(x['state']=='draft' for x in m['candidates'])} for m in ms],'archived_meetings':archived,'tasks':ts,'imports':imports,'demo_mode':DEMO_MODE,'today':datetime.now(KST).date().isoformat(),'can_create_project':can_create_project(c,actor)}
@app.get('/api/meetings/{mid}')
def meeting_detail(mid,actor=Depends(user)):
 with connect() as c:
  m=read(c,'meeting',mid);project(c,m['project_id'],actor)
  from work.v17.intake_review import preview_pages
  return {k:v for k,v in m.items() if k not in ('docx','pdf','txt')}|{'has_pdf':bool(m.get('pdf') and Path(m['pdf']).is_file()),'source_type':m.get('source_type','docx'),'preview_pages':preview_pages(m.get('pdf'))}
@app.get('/api/meetings/{mid}/original/{fmt}')
def original(mid,fmt,actor=Depends(user)):
 if fmt not in ('pdf','docx','txt'):raise HTTPException(404)
 with connect() as c:m=read(c,'meeting',mid);project(c,m['project_id'],actor)
 path=Path(m.get(fmt) or '-')
 if not path.is_file():raise HTTPException(404,'미리보기가 아직 준비되지 않았습니다. 원본 Word 파일을 내려받아 주세요.')
 return FileResponse(path,media_type='application/pdf' if fmt=='pdf' else 'text/plain; charset=utf-8' if fmt=='txt' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',filename=mid+'.'+fmt,content_disposition_type='inline' if fmt=='pdf' else 'attachment')
class Review(Strict):version:int;candidates:list[dict];selected:list[str]=[]
@app.post('/api/meetings/{mid}/review')
def review(mid,body:Review,actor=Depends(user)):
 with connect() as c:
  c.execute('BEGIN IMMEDIATE');m=read(c,'meeting',mid);p=project(c,m['project_id'],actor);version(m,body.version)
  active(m)
  if actor['id'] not in (p['pm'],m['author']):raise HTTPException(403,'작성자 또는 프로젝트 PM이 제안을 수정할 수 있습니다.')
  if body.selected and actor['id']!=p['pm']:raise HTTPException(403,'실제 업무 배정은 프로젝트 PM이 확정합니다.')
  if m['analysis_state'] in ('running','queued'):raise HTTPException(409,'분석이 끝난 뒤 검토해 주세요.')
  existing={x['id']:x for x in m['candidates']};refs={x['id'] for x in m['lines']};updated=[];seen=set();made=[]
  for cand in body.candidates:
   cid=cand.get('id') or uid()
   if cid in seen:raise HTTPException(422,'중복 항목이 있습니다.')
   seen.add(cid)
   if existing.get(cid,{}).get('state')=='applied':updated.append(existing[cid]);continue
   applying=cid in body.selected
   if applying:d=fields(p,cand)
   else:
    if cand.get('kind') not in ('업무','확인사항'):raise HTTPException(422,'항목 구분을 확인해 주세요.')
    for key in ('owner_id','reviewer_id'):
     if cand.get(key) and cand[key] not in p['members']:raise HTTPException(422,'프로젝트 참여자를 선택해 주세요.')
    d={k:cand.get(k) or None for k in ('owner_id','reviewer_id')}
    d.update(requires_review=bool(cand.get('requires_review',True)),title=str(cand.get('title','')).strip()[:1000],kind=cand['kind'],start=due(cand.get('start')),due=due(cand.get('due')))
    if d['start'] and d['due'] and d['start']>d['due']:raise HTTPException(422,'시작 예정일은 완료 목표일보다 늦을 수 없습니다.')
   evidence=cand.get('evidence',[])
   if (applying and not evidence) or any(x not in refs for x in evidence):raise HTTPException(422,'등록할 항목의 현재 본문 근거를 선택해 주세요.')
   if applying and existing.get(cid,{}).get('needs_recheck') and not cand.get('rechecked'):raise HTTPException(422,'본문 변경 후 담당자·기한·근거를 다시 확인하고 재확인 표시를 해 주세요.')
   new={'id':cid,**d,'description':str(cand.get('description') or '')[:4000],'evidence':list(dict.fromkeys(evidence)),'state':'draft','note':str(cand.get('note',''))[:2000],'needs_recheck':bool(existing.get(cid,{}).get('needs_recheck') and not (cand.get('rechecked') and evidence)),'previous_evidence':existing.get(cid,{}).get('previous_evidence',[])}
   if cid in body.selected:
    tid=uid();stamp=now();t={'id':tid,'project_id':p['id'],'meeting_id':mid,'candidate_id':cid,**d,'description':new['description'] or '\n'.join(x['text'] for x in m['lines'] if x['id'] in evidence),'status':'확인필요' if d['kind']=='확인사항' else '미착수','result':'','attachments':[],'evidence':evidence,'version':1,'created_at':stamp,'updated_at':stamp,'submitted_at':None,'completed_at':None,'events':[]}
    t['source_revision']=m['revision'];ev(t,actor['id'],'확인사항 등록' if d['kind']=='확인사항' else '업무 반영',new['note']);save(c,'task',t);task_notification(sys.modules[__name__],c,t,actor['id'],'assigned');new.update(state='applied',task_id=tid);made.append(tid)
   updated.append(new)
  if set(body.selected)-seen:raise HTTPException(422,'선택 항목을 다시 확인해 주세요.')
  for cid,cand in existing.items():
   if cid not in seen:updated.append(cand)
  m.update(candidates=updated,analysis_stale=any(x.get('needs_recheck') for x in updated if x['state']=='draft'),version=m['version']+1);save(c,'meeting',m)
 return {'created':made}
class TaskInput(Strict):
 project_id:str;title:str;description:str='';owner_id:str|None=None;reviewer_id:str|None=None;requires_review:bool=True;start:str|None=None;due:str|None=None;kind:str='업무';parent_id:str|None=None
@app.post('/api/tasks',status_code=201)
def create_task(body:TaskInput,actor=Depends(user)):
 with connect() as c:
  p=project(c,body.project_id,actor,True);d=fields(p,body.model_dump());stamp=now()
  if body.parent_id:
   parent=read(c,'task',body.parent_id)
   if parent['project_id']!=p['id']:raise HTTPException(422,'같은 프로젝트의 업무를 연결해 주세요.')
  t={'id':uid(),'project_id':p['id'],**d,'description':body.description[:4000],'parent_id':body.parent_id,'meeting_id':None,'candidate_id':None,'evidence':[],'status':'확인필요' if d['kind']=='확인사항' else '미착수','result':'','attachments':[],'version':1,'created_at':stamp,'updated_at':stamp,'submitted_at':None,'completed_at':None,'events':[]}
  ev(t,actor['id'],'직접 등록');save(c,'task',t);task_notification(sys.modules[__name__],c,t,actor['id'],'assigned');return t
class TaskEdit(Strict):version:int;title:str;description:str|None=Field(default=None,max_length=4000);owner_id:str|None=None;reviewer_id:str|None=None;requires_review:bool=True;start:str|None=None;due:str|None=None;kind:str='업무';note:str=''
@app.patch('/api/tasks/{tid}')
def edit_task(tid,body:TaskEdit,actor=Depends(user)):
 with connect() as c:
  c.execute('BEGIN IMMEDIATE');t=read(c,'task',tid);p=project(c,t['project_id'],actor,True);version(t,body.version)
  if t['status']=='완료':raise HTTPException(409,'완료된 업무는 수정할 수 없습니다. 후속 업무를 등록해 주세요.')
  if body.kind!=t['kind']:raise HTTPException(422,'기존 항목의 구분은 변경할 수 없습니다.')
  payload=body.model_dump()
  if 'requires_review' not in body.model_fields_set:payload['requires_review']=t.get('requires_review',True)
  if 'start' not in body.model_fields_set:payload['start']=t.get('start')
  d=fields(p,payload)
  if body.description is not None:d['description']=body.description.strip()
  changes={k:{'before':t.get(k),'after':v} for k,v in d.items() if t.get(k)!=v}
  if t['status']=='검토대기' and ('owner_id' in changes or 'reviewer_id' in changes or 'requires_review' in changes):raise HTTPException(409,'담당자·검토자는 요청 회수 또는 보완 요청 후 변경해 주세요.')
  old_owner=t['owner_id'] if t['kind']=='업무' else t['reviewer_id']
  t.update(d,version=t['version']+1,updated_at=now());ev(t,actor['id'],'정보 수정',body.note,changes);save(c,'task',t)
  if old_owner!=(t['owner_id'] if t['kind']=='업무' else t['reviewer_id']):task_notification(sys.modules[__name__],c,t,actor['id'],'reassigned',old_owner)
  return t
def eligible_reviewers(c,p):
 # A PM assigns a reviewer when registering or editing a task. Employee changes
 # may select only from this set, so they cannot grant new review authority.
 return ({p['pm']}|{t['reviewer_id'] for t in all_records(c,'task') if t['project_id']==p['id'] and t['kind']=='업무' and t.get('reviewer_id')})&set(p['members'])

class Action(Strict):version:int;action:str;note:str=Field(default='',max_length=6000);reviewer_id:str|None=None
@app.post('/api/tasks/{tid}/actions')
def task_action(tid,body:Action,actor=Depends(user)):
 with connect() as c:
  c.execute('BEGIN IMMEDIATE');t=read(c,'task',tid);p=project(c,t['project_id'],actor);version(t,body.version)
  a=body.action;s=t['status'];note=body.note.strip();is_owner=t['owner_id']==actor['id'];is_review=t['reviewer_id']==actor['id'];is_pm=p['pm']==actor['id']
  if a in ('start','draft','submit'):
   if not is_owner or t['kind']!='업무':raise HTTPException(403,'이 업무의 담당자만 처리할 수 있습니다.')
   if s not in ('미착수','진행중','보완요청'):raise HTTPException(409,'현재 상태에서는 처리할 수 없습니다.')
   if a=='start':t['status']='진행중'
   else:
    if not note:raise HTTPException(422,'처리 내용을 입력해 주세요.')
    t['result']=note
    if a=='submit':
     if not t.get('requires_review',True):raise HTTPException(409,'직접 완료하는 업무입니다. 완료 버튼을 사용해 주세요.')
     reviewer=body.reviewer_id or t['reviewer_id']
     if reviewer==actor['id'] or reviewer not in eligible_reviewers(c,p):raise HTTPException(422,'프로젝트 PM 또는 PM이 지정한 검토자를 선택해 주세요. 본인은 선택할 수 없습니다.')
     if reviewer!=t['reviewer_id']:
      ev(t,actor['id'],'검토자 변경',changes={'reviewer_id':{'before':t['reviewer_id'],'after':reviewer}})
      t['reviewer_id']=reviewer
     t.update(status='검토대기',submitted_at=now())
  elif a=='complete':
   if not is_owner or t['kind']!='업무':raise HTTPException(403,'업무 담당자만 직접 완료할 수 있습니다.')
   if t.get('requires_review',True):raise HTTPException(403,'별도 검토가 필요한 업무입니다. 지정 검토자에게 요청해 주세요.')
   if s not in ('미착수','진행중','보완요청'):raise HTTPException(409,'현재 상태에서는 완료할 수 없습니다.')
   if not note:raise HTTPException(422,'처리 결과를 작성해 주세요.')
   t.update(status='완료',result=note,completed_at=now(),completion_method='self',completed_by=actor['id'])
  elif a=='withdraw':
   if not is_owner or s!='검토대기':raise HTTPException(403,'검토 대기 중인 업무의 담당자만 요청을 회수할 수 있습니다.')
   t['status']='진행중'
  elif a in ('approve','return'):
   if is_owner:raise HTTPException(403,'본인이 처리한 업무는 다른 확인자에게 검토를 요청해 주세요.')
   if not (is_review or is_pm):raise HTTPException(403,'지정 확인자 또는 프로젝트 PM이 처리할 수 있습니다.')
   if s!='검토대기':raise HTTPException(409,'검토 요청된 업무만 확인할 수 있습니다.')
   if a=='return' and not note:raise HTTPException(422,'보완할 내용을 입력해 주세요.')
   t['status']='완료' if a=='approve' else '보완요청'
   if a=='approve':t.update(completed_at=now(),completion_method='reviewed',completed_by=actor['id'])
  elif a=='resolve':
   if not (is_review or is_pm):raise HTTPException(403,'확인 담당자 또는 PM이 처리할 수 있습니다.')
   if t['kind']!='확인사항' or s=='완료':raise HTTPException(409,'미해결 확인사항만 처리할 수 있습니다.')
   if not note:raise HTTPException(422,'확인된 내용을 작성해 주세요.')
   t.update(status='완료',result=note,completed_at=now())
  elif a=='reopen':
   if not is_pm:raise HTTPException(403,'프로젝트 PM이 처리할 수 있습니다.')
   if s!='완료' or not note:raise HTTPException(422,'완료 판단을 수정하는 이유가 필요합니다.')
   t.update(status='확인필요' if t['kind']=='확인사항' else '보완요청',completed_at=None)
  else:raise HTTPException(422,'지원하지 않는 동작입니다.')
  labels={'complete':'담당자 직접 완료','start':'처리 시작','draft':'처리 내용 저장','submit':'검토 요청','approve':'완료 확인','return':'보완 요청','resolve':'추가 확인 완료','reopen':'완료 판단 수정','withdraw':'검토 요청 회수'}
  ev(t,actor['id'],labels[a],note,{'status':{'before':s,'after':t['status']}});t.update(version=t['version']+1,updated_at=now());save(c,'task',t);task_notification(sys.modules[__name__],c,t,actor['id'],a);return t

@app.post('/api/tasks/{tid}/attachments')
async def attachment(tid:str,version:int=Form(...),file:UploadFile=File(...),actor=Depends(user)):
 ext=Path(file.filename or '').suffix.lower()
 if ext not in ('.pdf','.png','.jpg','.jpeg','.docx','.xlsx','.txt'):raise HTTPException(422,'PDF·이미지·Word·Excel·텍스트 파일을 올려 주세요.')
 data=await file.read(12*1024*1024+1)
 if len(data)>12*1024*1024:raise HTTPException(413,'첨부파일은 12MB까지 올릴 수 있습니다.')
 with connect() as c:
  c.execute('BEGIN IMMEDIATE');t=read(c,'task',tid);project(c,t['project_id'],actor)
  if t['version']!=version:raise HTTPException(409,'화면을 새로고침해 주세요.')
  if actor['id']!=t['owner_id'] or t['status'] not in ('미착수','진행중','보완요청'):raise HTTPException(403,'처리 중인 업무 담당자가 첨부할 수 있습니다.')
  fid=uid();path=FILES/(fid+ext);path.write_bytes(data);t['attachments'].append({'id':fid,'name':Path(file.filename).name,'path':str(path),'at':now(),'by':actor['id']});t.update(version=t['version']+1,updated_at=now());ev(t,actor['id'],'자료 첨부',Path(file.filename).name);save(c,'task',t)
 return {'ok':True}
@app.get('/api/tasks/{tid}/attachments/{fid}')
def download_attachment(tid,fid,actor=Depends(user)):
 with connect() as c:t=read(c,'task',tid);project(c,t['project_id'],actor)
 a=next((x for x in t['attachments'] if x['id']==fid),None)
 if not a:raise HTTPException(404)
 return FileResponse(a['path'],filename=a['name'],media_type='application/octet-stream')

def convert_docx(path:Path):
 """Use native Word with macros disabled; conversion may fail without blocking upload."""
 target=path.with_suffix('.pdf')
 script=ROOT/'convert_preview.ps1'
 r=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),'-Source',str(path),'-Destination',str(target)],capture_output=True,timeout=60)
 return str(target) if r.returncode==0 and target.is_file() else None
def convert_background(mid):
 with connect() as c:m=read(c,'meeting',mid)
 try:pdf=convert_docx(Path(m['docx']))
 except Exception:pdf=None
 with connect() as c:
  m=read(c,'meeting',mid);m['pdf']=pdf;save(c,'meeting',m)
@app.post('/api/meetings',status_code=201)
async def upload_meeting(project_id:str=Form(...),file:UploadFile=File(...),actor=Depends(user)):
 from work.v17.changes import prepare_scan,submit_scan
 with connect() as c:p=project(c,project_id,actor)
 if Path(file.filename or '').suffix.lower()!='.docx':raise HTTPException(422,'팀 양식으로 작성한 Word(.docx) 파일을 올려 주세요.')
 data=await file.read(4*1024*1024+1)
 from server import import_docx,lines
 try:
  parsed=import_docx(data)
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   if any('vbaProject' in x.filename or 'embeddings/' in x.filename for x in z.infolist()):raise ValueError('매크로나 포함 개체가 없는 문서를 사용해 주세요.')
   for info in z.infolist():
    if info.filename.endswith('.xml') and re.search(rb'\b(?:DDEAUTO|INCLUDETEXT|INCLUDEPICTURE)\b',z.read(info.filename),re.I):raise ValueError('외부 연결 필드가 없는 문서를 사용해 주세요.')
 except ValueError as exc:raise HTTPException(422,str(exc))
 title=parsed['title'] or Path(file.filename).stem
 dates=re.findall(r'20\d{2}[-./]\d{1,2}[-./]\d{1,2}',parsed['meeting_date'])
 day=None
 if dates:
  try:day=date(*map(int,re.split('[-./]',dates[0]))).isoformat()
  except ValueError:pass
 if not day:raise HTTPException(422,'양식의 일시에 회의 날짜를 YYYY-MM-DD 형식으로 작성해 주세요.')
 fingerprint=hashlib.sha256(data).hexdigest()
 with connect() as c:
  if any(x.get('fingerprint')==fingerprint and x['project_id']==project_id for x in all_records(c,'meeting')):raise HTTPException(409,'이미 등록한 회의록입니다.')
  mid=uid();path=FILES/(mid+'.docx');path.write_bytes(data)
  m={'id':mid,'project_id':project_id,'title':title,'date':day,'source':parsed['source'],'lines':lines(parsed['source']),'author':actor['id'],'candidates':[],'analysis_state':'idle','analysis_origin':'아직 분석하지 않음','error':'','warnings':parsed['warnings'],'version':1,'created_at':now(),'docx':str(path),'pdf':None,'fingerprint':fingerprint}
  ensure_document(m);change_job=prepare_scan(sys.modules[__name__],m);save(c,'meeting',m)
 submit_scan(sys.modules[__name__],mid,change_job)
 PREVIEW_POOL.submit(convert_background,mid)
 return {'id':mid}
def analyze(mid):
 AI_LOCK.acquire()
 try:
  with connect() as c:
   m=read(c,'meeting',mid);m.update(analysis_state='running',version=m['version']+1);save(c,'meeting',m)
  from workspace_ai import extract
  with connect() as c:m=read(c,'meeting',mid);p=read(c,'project',m['project_id']);people=[read(c,'person',i) for i in p['members']]
  result,metrics=extract(m['lines'],people)
  candidates=[];seen=set();valid={x['id'] for x in m['lines']}
  for item in result['items']:
   evidence=[x for x in item.get('evidence',[]) if x in valid]
   if not evidence:continue
   key=str(item.get('title','')).strip()
   if key in seen:continue
   seen.add(key);matches=[x for x in people if x['id']==item.get('owner_id')]
   quoted=' '.join(x['text'] for x in m['lines'] if x['id'] in evidence)
   owner=matches[0]['id'] if len(matches)==1 and matches[0]['name'] in quoted else None
   try:deadline=due(item['due']) if item.get('due') and item['due'] in quoted else None
   except HTTPException:deadline=None
   kind='확인사항' if item.get('kind')=='확인사항' else '업무'
   candidates.append({'id':uid(),'title':key,'owner_id':owner if kind=='업무' else None,'reviewer_id':(owner or p['pm']) if kind=='확인사항' else p['pm'],'due':deadline,'kind':kind,'evidence':evidence,'state':'draft','note':''})
  with connect() as c:
   m=read(c,'meeting',mid);m.update(candidates=candidates,analysis_stale=False,analysis_state='ready',analysis_origin='로컬 AI 분석',summary='',metrics=metrics,warnings=['한 번에 최대 6개 항목을 제안합니다. 원문과 비교해 누락된 항목을 추가해 주세요.'],error='',version=m['version']+1);save(c,'meeting',m)
 except Exception as exc:
  with connect() as c:
   m=read(c,'meeting',mid);m.update(analysis_state='failed',error=str(exc)[:400],version=m['version']+1);save(c,'meeting',m)
 finally:AI_LOCK.release()
@app.post('/api/meetings/{mid}/analyze',status_code=202)
def start_analysis(mid,actor=Depends(user)):
 with connect() as c:
  c.execute('BEGIN IMMEDIATE');m=read(c,'meeting',mid);project(c,m['project_id'],actor)
  active(m)
  p=read(c,'project',m['project_id'])
  if actor['id'] not in (m['author'],p['pm']):raise HTTPException(403,'작성자 또는 프로젝트 PM이 AI 분석을 실행할 수 있습니다.')
  if any(x['state']=='applied' for x in m['candidates']):raise HTTPException(409,'이미 업무에 반영한 회의록입니다. 기존 검토 결과와 연결 업무를 확인해 주세요.')
  if m['analysis_state'] in ('running','queued'):raise HTTPException(409,'이미 분석 중이거나 분석을 기다리는 회의록입니다.')
  if sum(x['analysis_state'] in ('running','queued') for x in all_records(c,'meeting'))>=8:raise HTTPException(429,'분석 대기가 많습니다. 원본은 보관되어 있으니 잠시 후 다시 시도해 주세요.')
  m.update(analysis_state='queued',error='',version=m['version']+1);save(c,'meeting',m)
 POOL.submit(analyze,mid);return {'ok':True}

@app.get('/')
def index():return FileResponse(ROOT/'work'/'v17'/'workspace.html',media_type='text/html')

def can_create_project(c,actor):
 return actor.get('level')=='leader' or any(p['pm']==actor['id'] for p in all_records(c,'project'))

class ProjectInput(Strict):
 name:str=Field(min_length=2,max_length=120)
 members:list[str]=Field(default_factory=list,max_length=100)
 pm_id:str|None=None

@app.post('/api/projects',status_code=201)
def create_project(body:ProjectInput,actor=Depends(user)):
 with connect() as c:
  if not can_create_project(c,actor):raise HTTPException(403,'프로젝트 생성 권한이 있는 PM 또는 관리자에게 요청해 주세요.')
  name=body.name.strip()
  if any(re.sub(r'\s+','',x['name']).casefold()==re.sub(r'\s+','',name).casefold() for x in all_records(c,'project')):raise HTTPException(409,'같은 이름의 프로젝트가 있습니다. 기존 프로젝트와 접근 권한을 확인해 주세요.')
  if len(name)<2:raise HTTPException(422,'프로젝트 이름을 두 글자 이상 입력해 주세요.')
  people={p['id'] for p in all_records(c,'person')}
  if any(x not in people for x in body.members):raise HTTPException(422,'등록된 참여자를 선택해 주세요.')
  pm_id=body.pm_id or actor['id']
  if pm_id not in people:raise HTTPException(422,'등록된 PM을 선택해 주세요.')
  pid='P-'+datetime.now(KST).strftime('%y')+'-'+uid()[:6].upper()
  p={'id':pid,'name':name,'pm':pm_id,'members':list(dict.fromkeys([actor['id'],pm_id]+body.members)),'year':datetime.now(KST).year,'created_at':now()}
  save(c,'project',p)
  return p

import sys
from work.v17.intake import build_router as intake_router
app.include_router(intake_router(sys.modules[__name__]))
from work.v17.documents import build_router as documents_router
app.include_router(documents_router(sys.modules[__name__]))
from work.v17.intake_review import build_router as intake_review_router
app.include_router(intake_review_router(sys.modules[__name__]))
from work.v17.features import build_router as features_router
app.include_router(features_router(sys.modules[__name__]))
from work.v17.changes import build_router as changes_router
app.include_router(changes_router(sys.modules[__name__]))
from work.v17.task_attention import build_router as task_attention_router
app.include_router(task_attention_router(sys.modules[__name__]))

from work.v17.questions import build_router as questions_router
app.include_router(questions_router(sys.modules[__name__]))
from work.v17.context_features import build_router as context_router
app.include_router(context_router(sys.modules[__name__]))
