"""Evidence coordinates and explicit colleague requests; no implicit access grants."""
import re, hashlib
from pathlib import Path
from functools import lru_cache
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from work.v17.intake_review import PDF_LOCK, preview_pages

def source_lines(text):
 from server import lines
 return lines(text)

def revision_source(m, revision=None, original=False):
 if original:return m.get('original_source',m['source'])
 if revision is None or revision==m.get('revision',1):return m['source']
 r=next((r for r in m.get('revisions',[]) if r['number']==revision),None)
 if not r:raise HTTPException(404,'해당 본문 버전을 찾을 수 없습니다.')
 return r['body']

@lru_cache(maxsize=32)
def locate_pdf(path,mtime,source):
 import pypdfium2 as pdfium
 refs=source_lines(source);found={};pages=[]
 def clean(text):return ''.join(ch.casefold() for ch in text if ch.isalnum())
 with PDF_LOCK, pdfium.PdfDocument(path) as doc:
  for pn in range(min(len(doc),50)):
   sheet=doc[pn];tp=sheet.get_textpage()
   try:
    width,height=sheet.get_size();pages.append({'width':width,'height':height})
    # char-by-char indices correspond to PDFium character boxes.
    chars=[];indices=[]
    for i in range(min(tp.count_chars(),60000)):
     s=tp.get_text_range(i,1)
     for ch in s:
      if ch.isalnum():chars.append(ch.casefold());indices.append(i)
    hay=''.join(chars)
    for row in refs:
     needle=clean(row['text'])
     if len(needle)<5:continue
     offset=0
     for occurrence in range(4):
      pos=hay.find(needle,offset)
      if pos<0:break
      offset=pos+len(needle);groups=[]
      for idx in dict.fromkeys(indices[pos:offset]):
       l,b,r,t=tp.get_charbox(idx)
       if r<=l or t<=b:continue
       box={'left':100*l/width,'top':100*(height-t)/height,'width':100*(r-l)/width,'height':100*(t-b)/height}
       g=next((x for x in groups if abs(x['top']-box['top'])<0.6 and abs(x['height']-box['height'])<0.8),None)
       if g:
        right=max(g['left']+g['width'],box['left']+box['width']);g['left']=min(g['left'],box['left']);g['width']=right-g['left'];g['height']=max(g['height'],box['height'])
       else:groups.append(box)
      if groups:found.setdefault(row['id'],[]).append({'page':pn+1,'rects':groups})
   finally:tp.close();sheet.close()
 return {'matches':found,'pages':pages}

class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class RequestInput(Strict):
 task_id:str
 recipient_id:str
 subject:str=Field(min_length=2,max_length=160)
 message:str=Field(min_length=2,max_length=4000)
class Reply(Strict):
 version:int
 message:str=Field(min_length=2,max_length=4000)
class Members(Strict):ids:list[str]=Field(max_length=100)

def build_router(w):
 r=APIRouter(prefix='/api')
 @r.patch('/projects/{pid}/members')
 def add_members(pid,body:Members,actor=Depends(w.user)):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');p=w.project(c,pid,actor,True)
   valid={x['id'] for x in w.all_records(c,'person')}
   if any(x not in valid for x in body.ids):raise HTTPException(422,'등록된 구성원을 선택해 주세요.')
   p['members']=list(dict.fromkeys(p['members']+body.ids));w.save(c,'project',p)
  return {'ok':True}
 def map_record(d,text):
  result={'matches':{},'pages':[],'source_hash':hashlib.sha256(text.encode()).hexdigest(),'source_text':text}
  p=Path(d.get('pdf') or '-')
  if p.is_file():
   try:result.update(locate_pdf(str(p),p.stat().st_mtime_ns,text))
   except Exception:result['notice']='원본 위치를 찾지 못했습니다. 아래 원문 문장을 대조해 주세요.'
  return result
 @r.get('/meetings/{mid}/evidence-map')
 def meeting_map(mid,revision:int|None=None,original:bool=False,actor=Depends(w.user)):
  with w.connect() as c:
   m=w.read(c,'meeting',mid);w.project(c,m['project_id'],actor)
  return map_record(m,revision_source(m,revision,original))
 @r.get('/meeting-imports/{iid}/evidence-map')
 def import_map(iid,actor=Depends(w.user)):
  with w.connect() as c:
   d=w.read(c,'import',iid)
   if d['actor_id']!=actor['id']:raise HTTPException(403,'본인의 작성 중인 문서만 볼 수 있습니다.')
  return map_record(d,d.get('edited_body') or d['source'])
 @r.get('/tasks/{tid}/source')
 def task_source(tid,actor=Depends(w.user)):
  with w.connect() as c:
   t=w.read(c,'task',tid);w.project(c,t['project_id'],actor)
   if not t.get('meeting_id'):raise HTTPException(404,'연결된 회의록이 없습니다.')
   m=w.read(c,'meeting',t['meeting_id']);rev=t.get('source_revision',1);text=revision_source(m,rev)
   return {k:v for k,v in m.items() if k not in ('docx','pdf','txt','source','lines')}|{'source':text,'lines':source_lines(text),'view_revision':rev,'preview_pages':preview_pages(m.get('pdf')),'task_evidence':t.get('evidence',[])}
 def coop_read(c,item,actor):
  if item.get('project_shared'):w.project(c,item['project_id'],actor);return
  if actor['id'] not in (item['sender_id'],item['recipient_id']):raise HTTPException(403,'요청 당사자만 첨부를 볼 수 있습니다.')
 def coop_write(c,item,actor):
  if actor['id'] not in (item['sender_id'],item['recipient_id']):raise HTTPException(403,'요청한 사람과 요청받은 사람만 자료를 올릴 수 있습니다.')
  if item.get('project_shared'):w.project(c,item['project_id'],actor)
 def public_files(item):
  return [{k:v for k,v in f.items() if k!='path'} for f in (item.get('files') or [])]
 def notice(c,record,actor,recipient,title):
  w.save(c,'notification',{'id':w.uid(),'recipient':recipient,'actor':actor,'project_id':record['project_id'],'target_type':'task' if record.get('project_shared') else 'cooperation','target_id':record['task_id'] if record.get('project_shared') else record['id'],'cooperation_id':record['id'],'title':title,'created_at':w.now(),'read_at':None})
 @r.get('/cooperation')
 def requests(actor=Depends(w.user)):
  with w.connect() as c:
   rows=[x for x in w.all_records(c,'cooperation') if actor['id'] in (x['sender_id'],x['recipient_id'])]
   for x in rows:
    p=w.read(c,'project',x['project_id']);x['can_open_task']=actor['id'] in p['members']
    x['files']=public_files(x)
    if not x['can_open_task']:x.pop('task_id',None);x.pop('project_id',None)
  return sorted(rows,key=lambda x:x['created_at'],reverse=True)
 @r.get('/tasks/{tid}/cooperation')
 def task_requests(tid,actor=Depends(w.user)):
  with w.connect() as c:
   t=w.read(c,'task',tid);w.project(c,t['project_id'],actor)
   rows=[x for x in w.all_records(c,'cooperation') if x['task_id']==tid and (x.get('project_shared') or actor['id'] in (x['sender_id'],x['recipient_id']))]
   for x in rows:x['files']=public_files(x)
   return sorted(rows,key=lambda x:x['created_at'],reverse=True)
 COOP_EXT=('.pdf','.png','.jpg','.jpeg','.gif','.docx','.xlsx','.pptx','.hwp','.hwpx','.txt')
 COOP_MAX=12*1024*1024
 @r.post('/cooperation/{rid}/files',status_code=201)
 async def coop_upload(rid:str,file:UploadFile=File(...),actor=Depends(w.user)):
  name=Path(file.filename or '').name
  if Path(name).suffix.lower() not in COOP_EXT:raise HTTPException(422,'이미지·PDF·Word·Excel·PowerPoint·한글·텍스트 파일을 올려 주세요.')
  data=await file.read(COOP_MAX+1)
  if len(data)>COOP_MAX:raise HTTPException(413,'첨부파일은 12MB까지 올릴 수 있습니다.')
  if not data:raise HTTPException(422,'빈 파일입니다.')
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');item=w.read(c,'cooperation',rid);coop_write(c,item,actor)
   if len(item.get('files') or [])>=10:raise HTTPException(422,'첨부는 10개까지 올릴 수 있습니다.')
   fid=w.uid();path=w.FILES/(fid+Path(name).suffix.lower());path.write_bytes(data)
   item['files']=(item.get('files') or [])+[{'id':fid,'name':name,'path':str(path),'at':w.now(),'by':actor['id'],'size':len(data)}]
   w.save(c,'cooperation',item)
  return {'ok':True,'id':fid}
 @r.get('/cooperation/{rid}/files/{fid}')
 def coop_download(rid:str,fid:str,actor=Depends(w.user)):
  with w.connect() as c:
   item=w.read(c,'cooperation',rid);coop_read(c,item,actor)
  a=next((x for x in (item.get('files') or []) if x['id']==fid),None)
  if not a:raise HTTPException(404,'첨부를 찾을 수 없습니다.')
  mt={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.gif':'image/gif','.pdf':'application/pdf','.txt':'text/plain; charset=utf-8'}.get(Path(a['name']).suffix.lower())
  return FileResponse(a['path'],filename=a['name'],media_type=mt or 'application/octet-stream',content_disposition_type='inline' if mt else 'attachment')
 @r.delete('/cooperation/{rid}/files/{fid}')
 def coop_remove(rid:str,fid:str,actor=Depends(w.user)):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');item=w.read(c,'cooperation',rid);coop_write(c,item,actor)
   a=next((x for x in (item.get('files') or []) if x['id']==fid),None)
   if not a:raise HTTPException(404,'첨부를 찾을 수 없습니다.')
   if a['by']!=actor['id']:raise HTTPException(403,'올린 사람만 지울 수 있습니다.')
   item['files']=[x for x in item['files'] if x['id']!=fid];w.save(c,'cooperation',item)
  return {'ok':True}
 @r.post('/cooperation',status_code=201)
 def send(body:RequestInput,actor=Depends(w.user)):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');t=w.read(c,'task',body.task_id);p=w.project(c,t['project_id'],actor)
   if body.recipient_id not in p['members']:raise HTTPException(422,'같은 프로젝트의 참여자를 선택해 주세요.')
   w.read(c,'person',body.recipient_id)
   if body.recipient_id==actor['id']:raise HTTPException(422,'다른 요청받을 사람을 선택해 주세요.')
   if len(body.subject.strip())<2 or len(body.message.strip())<2:raise HTTPException(422,'제목과 요청 내용을 작성해 주세요.')
   item={'id':w.uid(),'project_shared':True,'project_id':p['id'],'task_id':t['id'],'sender_id':actor['id'],'recipient_id':body.recipient_id,'subject':body.subject.strip(),'message':body.message.strip(),'reply':'','status':'답변 대기','created_at':w.now(),'version':1}
   w.save(c,'cooperation',item);notice(c,item,actor['id'],body.recipient_id,'협조 요청 · '+item['subject'])
  return item
 @r.post('/cooperation/{rid}/reply')
 def reply(rid,body:Reply,actor=Depends(w.user)):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');item=w.read(c,'cooperation',rid)
   if item['recipient_id']!=actor['id']:raise HTTPException(403,'요청받은 사람만 답변할 수 있습니다.')
   w.version(item,body.version)
   if item.get('project_shared'):w.project(c,item['project_id'],actor)
   if len(body.message.strip())<2:raise HTTPException(422,'답변을 작성해 주세요.')
   item.update(reply=body.message.strip(),status='답변 완료',replied_at=w.now(),version=item['version']+1)
   w.save(c,'cooperation',item);notice(c,item,actor['id'],item['sender_id'],'협조 요청 답변 · '+item['subject'])
  return {'ok':True}
 return r
