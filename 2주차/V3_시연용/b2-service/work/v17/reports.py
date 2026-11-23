"""D3 drafts: immutable input snapshots, explicit AI application, editable Word output."""
import io,json,zipfile
from pathlib import Path
from datetime import date
from fastapi import APIRouter,Depends,HTTPException,UploadFile,File
from fastapi.responses import Response
from pydantic import BaseModel,ConfigDict,Field
from work.v17.retrieval import registered_document

HEADINGS={'minutes':['논의 내용','결정 사항','추가 확인 사항'], 'weekly':['진행 요약','완료한 업무','진행 중인 업무','다음 계획·확인 사항']}
MAX_SOURCE=18000
class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class NewReport(Strict):
 project_id:str
 kind:str
 title:str=Field(min_length=1,max_length=180)
 start:str=''
 end:str=''
 memo:str=Field(default='',max_length=MAX_SOURCE)
class Section(Strict):
 heading:str=Field(max_length=80)
 text:str=Field(default='',max_length=12000)
class Action(Strict):
 task:str=Field(max_length=2000)
 owner:str=Field(default='',max_length=120)
 due:str=Field(default='',max_length=120)
class EditReport(Strict):
 version:int
 title:str=Field(min_length=1,max_length=180)
 sections:list[Section]=Field(max_length=8)
 actions:list[Action]=Field(default_factory=list,max_length=100)
 checked:bool=False
class Version(Strict):version:int

def snapshot(w,c,p,body):
 sources=[];actions=[];sections=[{'heading':h,'text':''} for h in HEADINGS[body.kind]]
 def add(text,label,**meta):
  if text.strip():sources.append({'id':'S'+str(len(sources)+1),'text':text.strip(),'label':label,**meta})
 if body.kind=='minutes':
  if not body.memo.strip():raise HTTPException(422,'회의 메모를 입력하거나 파일을 불러와 주세요.')
  for line in body.memo.splitlines():add(line,'입력 메모')
  sections[0]['text']=body.memo.strip()
 else:
  w.due(body.start);w.due(body.end)
  if not body.start or not body.end or body.start>body.end:raise HTTPException(422,'보고 기간의 시작일과 종료일을 확인해 주세요.')
  for m in sorted(w.all_records(c,'meeting'),key=lambda x:x.get('date','')):
   if m['project_id']!=p['id'] or m.get('deleted_at'):continue
   doc=registered_document(m)
   if doc and body.start<=doc.get('date','')<=body.end:
    for line in doc['body'].splitlines():add(line,doc['title']+' · '+doc.get('date',''),meeting_id=m['id'],revision=doc['revision'])
  people={x['id']:x['name'] for x in w.all_records(c,'person')}
  tasks=[]
  for t in w.all_records(c,'task'):
   if t['project_id']!=p['id'] or t.get('deleted_at'):continue
   changed=any(body.start<=str(e.get('at',''))[:10]<=body.end for e in t.get('events',[])) or body.start<=str(t.get('created_at',''))[:10]<=body.end
   if t['status']=='완료' and not changed:continue
   tasks.append(t);owner=people.get(t.get('owner_id') or t.get('reviewer_id'),'미정')
   add(f"업무: {t['title']} / 현재 상태: {t['status']} / 담당: {owner} / 기한: {t.get('due') or '미정'}\n{t.get('description','')}", '업무 현황 · '+t['title'],task_id=t['id'],version=t['version'])
   if t['status']!='완료':actions.append({'task':t['title'],'owner':owner,'due':t.get('due') or '미정'})
  sections[1]['text']='\n'.join('• '+t['title'] for t in tasks if t['status']=='완료')
  sections[2]['text']='\n'.join('• '+t['title']+' — '+t['status'] for t in tasks if t['status']!='완료')
  if body.memo.strip():
   for line in body.memo.splitlines():add(line,'추가 메모')
 if not sources:raise HTTPException(422,'선택 기간에 회의록·업무가 없습니다. 기간을 바꾸거나 메모를 입력해 주세요.')
 if len(sources)>240 or sum(len(s['text']) for s in sources)>MAX_SOURCE:raise HTTPException(422,'자료가 많습니다. 보고 기간을 줄이거나 메모를 나누어 주세요. 자료를 임의로 생략하지 않았습니다.')
 names=[x['name'] for x in w.all_records(c,'person') if x['id'] in p['members']]
 for s in sources:s['people']=[name for name in names if name in s['text']]
 return sources,sections,actions

def access(w,c,rid,actor,edit=False):
 d=w.read(c,'report',rid);p=w.project(c,d['project_id'],actor)
 if edit and actor['id'] not in (d['author'],p['pm']):raise HTTPException(403,'작성자 또는 프로젝트 PM이 수정할 수 있습니다.')
 return d

def worker(w,rid):
 try:
  with w.AI_LOCK:
   with w.connect() as c:
    d=w.read(c,'report',rid);d.update(ai_state='running');w.save(c,'report',d)
   from work.v17.reports_ai import generate
   result=generate(d['kind'],d['sources'],d['title'])
   with w.connect() as c:
    d=w.read(c,'report',rid);d.update(ai_state='ready',ai_result=result,ai_finished_at=w.now());w.save(c,'report',d)
 except Exception as e:
  with w.connect() as c:
   d=w.read(c,'report',rid);d.update(ai_state='failed',ai_error=str(getattr(e,'detail',e))[:400]);w.save(c,'report',d)

def export_docx(d):
 from docx import Document
 from docx.shared import Pt
 from docx.oxml import OxmlElement
 from docx.oxml.ns import qn
 from docx.text.paragraph import Paragraph
 doc=Document(Path(__file__).parent/'assets'/'meeting-template.docx')
 # The supplied blank form reserves handwriting space. Filled digital documents flow by content.
 for p in list(doc.paragraphs):
  if not p.text.strip() and not p._p.xpath('.//w:drawing'):
   p._p.getparent().remove(p._p)
 def replace(p,text):
  if p.runs:p.runs[0].text=text;[setattr(r,'text','') for r in p.runs[1:]]
  else:p.add_run(text)
 meta=doc.tables[0]
 values={(0,1):d['title'],(1,1):d['project_name'],(2,1):d['start']+(' ~ '+d['end'] if d['end']!=d['start'] and d['end'] else ''),(4,1):d['author_name'],(4,3):d['updated_at'][:10]}
 for (row,col),value in values.items():replace(meta.cell(row,col).paragraphs[0],value or '미정')
 def insert_after(anchor,text):
  el=OxmlElement('w:p');anchor._p.addnext(el);p=Paragraph(el,anchor._parent)
  p.paragraph_format.space_after=Pt(6)
  run=p.add_run(text);run.font.name='맑은 고딕';run.font.size=Pt(10)
  run._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'맑은 고딕')
  return p
 headings={p.text.replace(' ',''):p for p in doc.paragraphs if p.text.strip()}
 for key in ('회의안건','논의내용','결정사항','추가확인사항','후속조치'):
  headings[key].paragraph_format.space_before=Pt(12);headings[key].paragraph_format.space_after=Pt(6);headings[key].paragraph_format.keep_with_next=True
 replace(headings['회의록'],'회의록' if d['kind']=='minutes' else '주간 업무보고')
 replace(headings['MEETINGMINUTES'],'MEETING MINUTES' if d['kind']=='minutes' else 'WEEKLY REPORT')
 if d['kind']=='weekly':
  for row,col,text in [(0,0,'보고서명'),(2,0,'보고 기간'),(2,2,'구분'),(2,3,'주간 업무보고'),(3,0,'자료 기준'),(3,1,d['created_at'][:16].replace('T',' '))]:replace(meta.cell(row,col).paragraphs[0],text)
  replace(headings['회의안건'],'보고 주제')
 insert_after(headings['회의안건'],d['title'])
 slots=['논의내용','결정사항','추가확인사항']
 for i,s in enumerate(d['sections']):
  if i<len(slots):anchor=headings[slots[i]];replace(anchor,s['heading'])
  else:
   anchor=insert_after(last,s['heading'])
   for r in anchor.runs:r.bold=True
  last=anchor
  for line in (s['text'] or '기재 내용 없음').splitlines():last=insert_after(last,line)
 anchor=headings['후속조치']
 if d['actions']:
  t=doc.add_table(rows=1,cols=3);t.style='Table Grid'
  for cell,text in zip(t.rows[0].cells,['후속 조치','담당자','기한']):cell.text=text
  for a in d['actions']:
   for cell,text in zip(t.add_row().cells,[a['task'],a['owner'] or '미정',a['due'] or '미정']):cell.text=text
  from docx.shared import Cm
  for row in t.rows:
   for i,cell in enumerate(row.cells):
    cell.width=Cm([10.7,3,3.4][i])
    for p in cell.paragraphs:
     p.paragraph_format.space_after=Pt(4);p.paragraph_format.space_before=Pt(4)
     for run in p.runs:run.font.name='맑은 고딕';run.font.size=Pt(9);run._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),'맑은 고딕')
  anchor._p.addnext(t._tbl)
 else:insert_after(anchor,'기재 내용 없음')
 note=doc.add_paragraph('작성 상태: '+('작성자 확인 완료' if d['checked'] else '검토 전 초안')+' · 자료 기준 '+d['created_at'][:16].replace('T',' '))
 if d['kind']=='weekly':doc.add_paragraph('회의록은 선택한 기간, 업무는 초안 생성 시점의 미완료 업무 및 기간 내 변경된 완료 업무를 기준으로 작성했습니다.')
 doc.add_paragraph('사용 자료')
 for label in dict.fromkeys(s['label'] for s in d['sources']):doc.add_paragraph('• '+label)
 out=io.BytesIO();doc.save(out);return out.getvalue()

def build_router(w):
 r=APIRouter(prefix='/api/reports')
 @r.get('')
 def listing(project_id:str='',actor=Depends(w.user)):
  with w.connect() as c:
   ids={p['id'] for p in w.all_records(c,'project') if actor['id'] in p['members']}
   return sorted([{k:d[k] for k in ('id','title','kind','project_id','author','author_name','updated_at','checked','version','ai_state')} for d in w.all_records(c,'report') if d['project_id'] in ids and (not project_id or d['project_id']==project_id)],key=lambda d:d['updated_at'],reverse=True)
 @r.post('',status_code=201)
 def create(body:NewReport,actor=Depends(w.user)):
  if body.kind not in HEADINGS or not body.title.strip():raise HTTPException(422,'문서 종류와 제목을 확인해 주세요.')
  w.due(body.start);w.due(body.end)
  with w.connect() as c:
   p=w.project(c,body.project_id,actor);sources,sections,actions=snapshot(w,c,p,body)
   d={'id':w.uid(),'project_id':p['id'],'project_name':p['name'],'kind':body.kind,'title':body.title.strip(),'start':body.start,'end':body.end,'author':actor['id'],'author_name':actor['name'],'created_at':w.now(),'updated_at':w.now(),'version':1,'checked':False,'sources':sources,'sections':sections,'actions':actions,'ai_state':'idle','ai_result':None}
   w.save(c,'report',d);return d
 @r.post('/read-file')
 async def read_file(file:UploadFile=File(...),actor=Depends(w.user)):
  raw=await file.read(5*1024*1024+1)
  if len(raw)>5*1024*1024:raise HTTPException(422,'파일은 5MB 이하로 올려 주세요.')
  ext=Path(file.filename or '').suffix.lower()
  try:
   if ext in ('.docx','.xlsx'):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
     if sum(x.file_size for x in z.infolist())>30*1024*1024:raise ValueError('압축 해제 크기가 너무 큽니다.')
   if ext=='.docx':
    from docx import Document
    doc=Document(io.BytesIO(raw));lines=[]
    for block in doc.iter_inner_content():
     if hasattr(block,'text'):lines.append(block.text)
     else:
      for row in block.rows:lines.append(' | '.join(dict.fromkeys(c.text for c in row.cells)))
   elif ext=='.xlsx':
    from openpyxl import load_workbook
    wb=load_workbook(io.BytesIO(raw),read_only=True,data_only=False);lines=[]
    try:
     for sheet in wb:
      if sheet.sheet_state!='visible':continue
      lines.append('시트: '+sheet.title)
      if sheet.max_row>1000 or sheet.max_column>60:raise ValueError('시트는 1,000행·60열 이내로 나누어 주세요.')
      for row in sheet.iter_rows():
       vals=[]
       for cell in row:
        if cell.data_type=='f':raise ValueError('수식이 있습니다. 값을 복사한 파일로 올려 주세요.')
        if cell.value is not None:vals.append(f'{cell.coordinate}: {cell.value}')
       if vals:lines.append(' | '.join(vals))
    finally:wb.close()
   elif ext=='.txt':lines=raw.decode('utf-8-sig').splitlines()
   else:raise ValueError('Word(.docx), Excel(.xlsx), UTF-8 텍스트(.txt) 파일을 선택해 주세요.')
   text='\n'.join(lines)
   if not text.strip() or len(text)>MAX_SOURCE:raise ValueError('텍스트가 없거나 18,000자를 초과합니다. 자료를 나누어 주세요.')
   return {'text':text,'filename':file.filename,'note':'셀의 글자·날짜만 불러옵니다. 색으로 표시한 간트 일정·도형·이미지는 해석하지 않습니다.' if ext=='.xlsx' else ''}
  except Exception as e:raise HTTPException(422,str(e) if isinstance(e,ValueError) else '파일을 읽지 못했습니다. 암호화되지 않은 정상 파일인지 확인해 주세요.')
 @r.get('/{rid}')
 def get(rid,actor=Depends(w.user)):
  with w.connect() as c:return access(w,c,rid,actor)
 @r.patch('/{rid}')
 def edit(rid,body:EditReport,actor=Depends(w.user)):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');d=access(w,c,rid,actor,True);w.version(d,body.version)
   if not body.title.strip() or [s.heading for s in body.sections]!=HEADINGS[d['kind']]:raise HTTPException(422,'제목과 문서 항목을 확인해 주세요.')
   d.update(title=body.title.strip(),sections=[s.model_dump() for s in body.sections],actions=[a.model_dump() for a in body.actions if a.task.strip()],checked=body.checked,version=d['version']+1,updated_at=w.now(),ai_result=None)
   if d['ai_state']=='ready':d['ai_state']='idle'
   w.save(c,'report',d);return d
 @r.post('/{rid}/ai',status_code=202)
 def ai(rid,body:Version,actor=Depends(w.user)):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');d=access(w,c,rid,actor,True);w.version(d,body.version)
   if d['ai_state'] in ('queued','running'):raise HTTPException(409,'이미 AI 정리 중입니다.')
   if any(j.get('ai_state') in ('queued','running') and j['author']==actor['id'] for j in w.all_records(c,'report')):raise HTTPException(409,'요청한 문서가 처리 중입니다. 완료 후 다시 요청해 주세요.')
   d.update(ai_state='queued',ai_error='',ai_result=None,ai_base_version=d['version']);w.save(c,'report',d)
  w.POOL.submit(worker,w,rid);return d
 @r.get('/{rid}/word')
 def download(rid,actor=Depends(w.user)):
  with w.connect() as c:d=access(w,c,rid,actor)
  return Response(export_docx(d),media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',headers={'Content-Disposition':f'attachment; filename="PNT-{d["kind"]}-{rid[:8]}.docx"'})
 return r
