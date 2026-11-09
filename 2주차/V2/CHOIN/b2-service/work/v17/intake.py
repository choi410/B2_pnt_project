"""Review document metadata before connecting it to a project."""
import hashlib,io,re,zipfile
from datetime import date
from pathlib import Path
from fastapi import APIRouter,Depends,File,Form,UploadFile,HTTPException
from pydantic import BaseModel,ConfigDict,Field

class Register(BaseModel):
 model_config=ConfigDict(extra='forbid')
 project_id:str=Field(max_length=80)
 title:str=Field(default='',max_length=240)
 meeting_date:str|None=None
 confirm_project_mismatch:bool=False
class FieldReport(BaseModel):
 model_config=ConfigDict(extra='forbid')
 project_id:str;title:str=Field(min_length=1,max_length=1000);description:str=Field(min_length=1,max_length=6000)
class Feedback(BaseModel):
 model_config=ConfigDict(extra='forbid')
 content:str=Field(min_length=5,max_length=4000);screen:str=Field(default='',max_length=100)
class Metadata(BaseModel):
 model_config=ConfigDict(extra='forbid')
 version:int
 title:str=Field(min_length=1,max_length=240)
 meeting_date:str|None=None

def normalize(text):return re.sub(r'[\s·_().-]','',text or '').casefold()
def match_projects(declared,projects):
 if not declared:return []
 return [p['id'] for p in projects if normalize(p['name'])==normalize(declared) or re.search(r'(?<![A-Za-z0-9])'+re.escape(p['id'])+r'(?![A-Za-z0-9])',declared,re.I)]
def parse_date(raw):
 m=re.search(r'(20\d{2})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})',raw or '')
 if m:
  try:return date(*map(int,m.groups())).isoformat()
  except ValueError:pass
 return ''
def parse_text(text):
 def find(labels):
  m=re.search(r'^\s*(?:'+labels+r')\s*[:：|]\s*(.+)$',text,re.M)
  return m.group(1).strip() if m else ''
 return {'source':text,'title':find('회의명|회의 제목|제목'),'project':find('프로젝트명|프로젝트'),'meeting_date':find('일시|회의일|회의 날짜|일자'),'warnings':[]}

def build_router(w):
 router=APIRouter(prefix='/api')
 def own(c,id,actor):
  record=w.read(c,'import',id)
  if record['actor_id']!=actor['id']:raise HTTPException(403,'본인이 불러온 문서만 등록할 수 있습니다.')
  return record
 def public(record,projects):
  from work.v17.intake_review import preview_pages
  return {k:v for k,v in record.items() if k not in ('docx','pdf','txt','fingerprint')}|{'suggested_projects':match_projects(record.get('declared_project'),projects),'has_pdf':bool(record.get('pdf') and Path(record['pdf']).is_file()),'preview_pages':preview_pages(record.get('pdf'))}
 @router.post('/meeting-imports',status_code=201)
 async def prepare(file:UploadFile|None=File(default=None),text:str=Form(default=''),actor=Depends(w.user)):
  if bool(file)==bool(text.strip()):raise HTTPException(422,'Word 파일 또는 붙여넣은 내용 중 한 가지를 선택해 주세요.')
  iid=w.uid();source_type='docx' if file else 'text';path=None
  if file:
   if Path(file.filename or '').suffix.lower()!='.docx':raise HTTPException(422,'Word(.docx) 파일을 선택해 주세요.')
   data=await file.read(4*1024*1024+1)
   from server import import_docx
   try:
    parsed=import_docx(data)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
     if any('vbaProject' in i.filename or 'embeddings/' in i.filename for i in z.infolist()):raise ValueError('매크로나 포함 개체가 없는 Word 문서를 사용해 주세요.')
     for i in z.infolist():
      if i.filename.endswith('.xml') and re.search(rb'\b(?:DDEAUTO|INCLUDETEXT|INCLUDEPICTURE)\b',z.read(i.filename),re.I):raise ValueError('외부 연결 필드가 없는 문서를 사용해 주세요.')
   except ValueError as e:raise HTTPException(422,str(e))
   filename=Path(file.filename).name;path=w.FILES/(iid+'.docx');path.write_bytes(data)
  else:
   text=text.replace('\r\n','\n').replace('\r','\n').strip()
   if len(text)<10:raise HTTPException(422,'회의 내용을 10자 이상 입력해 주세요.')
   if len(text)>12000:raise HTTPException(422,'내용이 깁니다. 안건별로 나누어 등록해 주세요.')
   parsed=parse_text(text);filename='붙여넣은 회의록';data=text.encode('utf-8');path=w.FILES/(iid+'.txt');path.write_bytes(data)
  item={'id':iid,'actor_id':actor['id'],'source_type':source_type,'filename':filename,'title':parsed['title'] or (Path(filename).stem if file else ''),'meeting_date':parse_date(parsed['meeting_date']),'declared_project':parsed['project'],'source':parsed['source'],'warnings':parsed['warnings'],'created_at':w.now(),'fingerprint':hashlib.sha256(data).hexdigest(),'docx':str(path) if file else None,'txt':str(path) if not file else None}
  with w.connect() as c:
   w.save(c,'import',item);projects=[p for p in w.all_records(c,'project') if actor['id'] in p['members']]
  if file:
   from work.v17.intake_review import convert_import
   w.PREVIEW_POOL.submit(convert_import,w,iid)
  return public(item,projects)
 @router.get('/meeting-imports/{iid}')
 def get_import(iid,actor=Depends(w.user)):
  with w.connect() as c:
   item=own(c,iid,actor);projects=[p for p in w.all_records(c,'project') if actor['id'] in p['members']]
  return public(item,projects)
 @router.post('/meeting-imports/{iid}/register',status_code=201)
 def register(iid,body:Register,actor=Depends(w.user)):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');item=own(c,iid,actor);p=w.project(c,body.project_id,actor)
   from work.v17.intake_review import active
   active(item)
   if item.get('meeting_id'):return {'id':item['meeting_id']}
   allowed=[p for p in w.all_records(c,'project') if actor['id'] in p['members']]
   suggestions=match_projects(item['declared_project'],allowed)
   mismatch=bool(item['declared_project']) and p['id'] not in suggestions
   if mismatch and not body.confirm_project_mismatch:raise HTTPException(422,'문서에 적힌 프로젝트와 선택한 프로젝트가 다릅니다. 선택을 확인하거나 다른 표기임을 확인해 주세요.')
   duplicate=next((m for m in w.all_records(c,'meeting') if m.get('fingerprint')==item['fingerprint'] and m['project_id']==p['id']),None)
   if duplicate:raise HTTPException(409,{'message':'이 프로젝트에 같은 원문이 이미 등록되어 있습니다.','meeting_id':duplicate['id']})
   from server import lines
   mid=w.uid();m={'id':mid,'project_id':p['id'],'title':body.title.strip() or item['title'] or '제목 미정 회의록','date':w.due(body.meeting_date) or '',
    'source':item['source'],'lines':lines(item['source']),'author':actor['id'],'candidates':[],'analysis_state':'idle','analysis_origin':'아직 분석하지 않음','error':'','warnings':item['warnings'],'version':1,'created_at':w.now(),'docx':item['docx'],'txt':item['txt'],'pdf':None,'fingerprint':item['fingerprint'],'source_type':item['source_type'],'declared_project':item['declared_project'],'project_mismatch_confirmed':mismatch,'registration_confirmed_by':actor['id']}
   w.ensure_document(m)
   if item.get('edited_body') and item['edited_body']!=m['source']:w.save_content(w,m,actor,m['title'],m['date'],item['edited_body'])
   w.save(c,'meeting',m);item['meeting_id']=mid;w.save(c,'import',item)
  if m['source_type']=='docx':w.PREVIEW_POOL.submit(w.convert_background,mid)
  return {'id':mid}
 @router.post('/field-reports',status_code=201)
 def report(body:FieldReport,actor=Depends(w.user)):
  with w.connect() as c:
   p=w.project(c,body.project_id,actor)
   if not body.title.strip() or not body.description.strip():raise HTTPException(422,'발견한 내용과 상황을 입력해 주세요.')
   t={'id':w.uid(),'project_id':p['id'],'title':body.title.strip(),'description':body.description.strip(),'owner_id':None,'reviewer_id':p['pm'],'due':None,'kind':'업무','status':'미착수','created_by':actor['id'],'meeting_id':None,'candidate_id':None,'evidence':[],'result':'','attachments':[],'version':1,'created_at':w.now(),'updated_at':w.now(),'events':[],'submitted_at':None,'completed_at':None}
   w.ev(t,actor['id'],'현장 이슈 접수','PM의 담당자·기한 확인 대기');w.save(c,'task',t)
   w.notify(w,c,[p['pm']],actor['id'],p['id'],'task',t['id'],'새 현장 이슈 접수 · '+t['title'])
  return t
 @router.patch('/meetings/{mid}/metadata')
 def edit_metadata(mid,body:Metadata,actor=Depends(w.user)):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');m=w.read(c,'meeting',mid);p=w.project(c,m['project_id'],actor);w.version(m,body.version)
   if actor['id'] not in (m['author'],p['pm']):raise HTTPException(403,'등록자 또는 프로젝트 PM이 회의 정보를 수정할 수 있습니다.')
   if not body.title.strip():raise HTTPException(422,'회의 제목을 입력해 주세요.')
   before={k:m[k] for k in ('title','date')}
   w.save_content(w,m,actor,body.title,body.meeting_date,m['source'])
   m.setdefault('metadata_history',[]).append({'at':w.now(),'by':actor['id'],'before':before,'after':{k:m[k] for k in ('title','date')}})
   w.save(c,'meeting',m)
  return {'ok':True}
 @router.get('/trial-review')
 def trial_review(actor=Depends(w.user)):
  import json
  path=w.ROOT/'trial_review.json'
  return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'people':[],'findings':[],'status':'역할별 점검 중'}
 @router.post('/feedback',status_code=201)
 def feedback(body:Feedback,actor=Depends(w.user)):
  with w.connect() as c:w.save(c,'feedback',{'id':w.uid(),'actor_id':actor['id'],'content':body.content.strip(),'screen':body.screen,'created_at':w.now(),'origin':'서비스 사용자 입력'})
  return {'ok':True}
 return router
