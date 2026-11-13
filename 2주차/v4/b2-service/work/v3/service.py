"""Immediate durable registration, serial background inference and shared projections."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import hashlib, io, json, re, time, zipfile
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from work.v17.intake import parse_date, parse_text
from work.v17.documents import ensure_document
from work.v17.intake_review import active
from work.v3.analysis_progress import stamp,epoch,estimate_runtime,progress_snapshot,recent_batch

def norm(text):
    return re.sub(r'[\s·_().\-]', '', text or '').casefold()

def register_revision(m):
    """Search the registered source without inventing a PM approval."""
    rev=next((r for r in m.setdefault('revisions',[]) if r['number']==m['revision']),None)
    if rev is None:
        m['revisions'].append({'number':m['revision'],'title':m['title'],'date':m.get('date',''),'body':m['source'],'status':'등록 완료','saved_by':m['author'],'saved_at':m.get('created_at'),'note':'등록 본문'})
    m['registered_revision']=m['revision']
    m['document_status']='등록 완료'

def match_project(filename, declared, source, projects, context=''):
    """Only explicit identifiers/names; never infer from generic equipment words."""
    text = filename+'\n'+declared+'\n'+source
    candidates = []
    for p in projects:
        code = re.search(r'(?<![A-Za-z0-9])'+re.escape(p['id'])+r'(?![A-Za-z0-9])', text, re.I)
        if code or (len(norm(p['name'])) >= 3 and any(norm(p['name']) in norm(line) for line in text.splitlines())):
            candidates.append(p['id'])
    if len(candidates)>1:return {'project_id':'','reason':'문서에 여러 프로젝트가 있습니다.','needs_check':True}
    if len(candidates)==1:
        if context and context!=candidates[0]:return {'project_id':'','suggested':candidates[0],'reason':'선택한 프로젝트와 문서 표기가 다릅니다.','needs_check':True}
        return {'project_id':candidates[0],'reason':'문서 표기와 일치','needs_check':False}
    if declared:return {'project_id':'','reason':'문서에 적힌 프로젝트를 목록에서 찾지 못했습니다.','needs_check':True}
    if context in {p['id'] for p in projects}:return {'project_id':context,'reason':'현재 프로젝트로 선택','needs_check':False}
    return {'project_id':'','reason':'프로젝트를 확인해 주세요.','needs_check':True}

def parse_file(name, data):
    suffix=Path(name).suffix.lower()
    if not data or len(data)>8*1024*1024:raise ValueError('파일은 8MB 이하로 올려 주세요.')
    if suffix in ('.docx','.xlsx'):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if len(z.infolist())>2000 or sum(i.file_size for i in z.infolist())>40*1024*1024:raise ValueError('압축 해제 크기가 너무 큽니다.')
            if any('vbaProject' in i.filename or 'embeddings/' in i.filename for i in z.infolist()):raise ValueError('매크로나 포함 개체가 없는 문서를 사용해 주세요.')
            for i in z.infolist():
                if i.filename.endswith('.xml') and re.search(rb'\b(?:DDEAUTO|INCLUDETEXT|INCLUDEPICTURE)\b',z.read(i.filename),re.I):raise ValueError('외부 연결 필드가 없는 문서를 사용해 주세요.')
    if suffix=='.docx':
        from server import import_docx
        parsed=import_docx(data)
    elif suffix=='.pdf':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(data) as doc:
            if len(doc)>80:raise ValueError('80페이지 이하의 문서를 올려 주세요.')
            pages=[]
            for page in doc:
                textpage=page.get_textpage()
                try:pages.append(textpage.get_text_range())
                finally:textpage.close();page.close()
        parsed=parse_text('\n'.join(pages))
        if len(parsed['source'].strip())<10:raise ValueError('글자를 읽을 수 없는 PDF입니다. 스캔본은 Word 또는 텍스트로 변환해 주세요.')
    elif suffix=='.xlsx':
        import openpyxl
        book=openpyxl.load_workbook(io.BytesIO(data),read_only=True,data_only=True)
        rows=[];count=0;metadata={}
        try:
            for sheet in book:
                if (sheet.max_row or 0)*(sheet.max_column or 0)>100000:raise ValueError('시트 범위가 너무 큽니다. 필요한 영역만 별도 파일로 올려 주세요.')
                rows.append('시트: '+sheet.title)
                for row in sheet.iter_rows():
                    cells=[cell.value for cell in row if cell.value is not None]
                    if len(cells)>=2:
                        field={'회의명':'title','회의 제목':'title','제목':'title','프로젝트':'project','프로젝트명':'project','회의일':'meeting_date','회의 날짜':'meeting_date','일시':'meeting_date'}.get(str(cells[0]).strip().rstrip(':：'))
                        if field and field not in metadata:metadata[field]=str(cells[1])
                    values=[f'{cell.coordinate}: {cell.value.isoformat() if hasattr(cell.value,"isoformat") else cell.value}' for cell in row if cell.value is not None]
                    if values:rows.append(' | '.join(values));count+=len(values)
                    if count>2500:raise ValueError('내용이 많습니다. 필요한 시트만 별도 파일로 올려 주세요.')
        finally:book.close()
        parsed=parse_text('\n'.join(rows));parsed.update(metadata);parsed['warnings']=['Excel 셀의 텍스트를 분석합니다. 색상·도형만으로 표시한 간트 기간은 해석하지 않습니다.']
    elif suffix in ('.txt','.md'):
        try:text=data.decode('utf-8-sig')
        except UnicodeDecodeError:text=data.decode('cp949')
        parsed=parse_text(text)
    else:raise ValueError('Word(.docx), PDF, Excel(.xlsx), 텍스트 파일을 올려 주세요.')
    parsed['source']=parsed['source'].replace('\r\n','\n').strip()
    fallback=parse_text(parsed['source'])
    for key in ('title','project','meeting_date'):
        if not parsed.get(key):parsed[key]=fallback[key]
    if len(parsed['source'])<10:raise ValueError('분석할 회의 내용이 없습니다.')
    if len(parsed['source'])>60000:raise ValueError('문서가 너무 깁니다. 안건 또는 시트별로 나누어 주세요.')
    return parsed,suffix

def chunks(rows,limit=3300):
    out=[];current=[];size=0
    for row in rows:
        if len(row['text'])>limit:raise ValueError('한 문단이 너무 깁니다. 문단을 나누어 주세요.')
        if current and size+len(row['text'])>limit:out.append(current);current=[];size=0
        current.append(row);size+=len(row['text'])
    if current:out.append(current)
    return out

def note_points(m):
    bundle=m.get('reviewed_bundle') or m.get('v3_bundle') or m.get('overview') or {}
    out=[]
    for key,label in [('summary','핵심 내용'),('decisions','결정사항'),('candidates','후속 확인')]:
        items=bundle.get(key, m.get('candidates',[]) if key=='candidates' else [])
        for i,item in enumerate(items):
            text=item.get('text') or item.get('description') or item.get('title','')
            if text:out.append({'id':f'{key}:{i}','kind':label,'text':text,'evidence':item.get('evidence',[]),'start':item.get('start'),'due':item.get('due')})
    return out

def date_values(text):
    out=[]
    for y,m,d in re.findall(r'(20\d{2})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})',text):
        try:value=date(int(y),int(m),int(d)).isoformat()
        except ValueError:continue
        if value not in out:out.append(value)
    return out

def event_state(text):
    if re.search(r'철회|취소',text):return '철회'
    if re.search(r'보류',text):return '보류'
    if re.search(r'미정|미확정|합의하지|확정하지|요청|검토 예정',text):return '요청'
    return '일정'

def change_context(quotes,after):
    """Use original wording for conditions; never infer an explanation."""
    if not quotes:return ''
    clauses=re.split(r'(?<=[.!?])\s+',quotes[0])
    useful=[s for s in clauses if re.search(r'검토|확인|간섭|공간|위해|조건|부담|별도|미정|한도|상한',s) and norm(s) not in norm(after)]
    return ' '.join(useful[:2])

def calendar_events(meetings,changes):
    out=[]
    for m in meetings:
        if m.get('date'):out.append({'id':'meeting:'+m['id'],'meeting_id':m['id'],'project_id':m['project_id'],'title':m['title'],'start':m['date'],'end':m['date'],'kind':'회의','evidence':[]})
        if m.get('analysis_stale'):continue
        for i,p in enumerate(note_points(m)):
            if p['kind']!='후속 확인':continue
            text=p['text'];ds=date_values(text)
            if not ds and p.get('due'):ds=[d for d in [p.get('start'),p['due']] if d]
            if not ds or event_state(text) in ('보류','철회'):continue
            span=len(ds)==2 and (bool(p.get('start')) or bool(re.search(r'부터|까지.*기간|~|～',text)))
            out.append({'id':f'note:{m["id"]}:{i}','meeting_id':m['id'],'project_id':m['project_id'],'title':text,'start':min(ds) if span else ds[-1],'end':max(ds) if span else ds[-1],'kind':'요청 일정' if event_state(text)=='요청' else '회의록 일정','evidence':p['evidence']})
    # Show only the latest agreed delivery per subject. Requests never replace it.
    latest={}
    for e in sorted(changes,key=lambda e:(e.get('effective_date',''),e.get('created_at',''))):
        if e.get('business_state')=='확정' and e.get('category')=='납기':latest[(e['project_id'],e.get('topic_id') or norm(e['title']))]=e
    for e in latest.values():
        ds=date_values(e['after'])
        if len(ds)==1:out.append({'id':'change:'+e['id'],'meeting_id':e['meeting_id'],'project_id':e['project_id'],'title':e['title']+' · '+e['after'],'start':ds[0],'end':ds[0],'kind':'합의 일정','evidence':e['evidence']})
    return out

def run_analysis(w,mid,job):
    from server import lines
    from work.v3.fast_ai import extract,VERSION
    from work.v17.changes import make_proposals,EXTRACTION_VERSION
    started=time.perf_counter()
    with w.AI_LOCK:
        acquired=time.perf_counter()
        try:
            with w.connect() as c:
                m=w.read(c,'meeting',mid)
                if m.get('v3_job')!=job or m.get('deleted_at'):return
                if not m.get('analysis_estimate'):m['analysis_estimate']=estimate_runtime(m['source'],[x for x in w.all_records(c,'meeting') if x['id']!=mid],VERSION)
                revision=m['revision'];m.update(analysis_state='running',analysis_phase='notes',analysis_started_at=stamp(),analysis_loading_seconds=0);w.save(c,'meeting',m)
                topics=[{'id':e.get('topic_id') or 'auto-'+hashlib.sha1((e['category']+norm(e['title'])).encode()).hexdigest()[:14],'title':e['title'],'category':e['category']} for e in w.all_records(c,'change_event') if e['project_id']==m['project_id']]
            def report_phase(phase):
                with w.connect() as c:
                    current=w.read(c,'meeting',mid)
                    if current.get('v3_job')!=job or current.get('deleted_at') or current['revision']!=revision:return
                    moment=stamp()
                    if current.get('analysis_phase')=='loading' and phase!='loading':
                        since=epoch(current.get('analysis_loading_started_at'))
                        current['analysis_loading_seconds']=current.get('analysis_loading_seconds',0)+(max(0,epoch(moment)-since) if since else 0)
                    if phase=='loading':current['analysis_loading_started_at']=moment
                    current['analysis_phase']=phase;w.save(c,'meeting',current)
            groups=chunks(m['lines']);bundle={'summary':[],'decisions':[],'candidates':[]};change_items=[];metrics={'chunks':len(groups),'queue_seconds':round(acquired-started,2),'passes':[]}
            for i,group in enumerate(groups):
                notes,found,measure=extract(w,group,list({x['id']:x for x in topics}.values())[:30],on_phase=report_phase)
                for key in ('summary','decisions'):bundle[key].extend(notes.get(key,[]))
                for item in notes.get('items',[]):bundle['candidates'].append({**item,'id':w.uid(),'state':'draft','note':'','reviewer_id':None})
                metrics['model']=measure.get('model');metrics['passes'].append(measure)
                with w.connect() as c:
                    current=w.read(c,'meeting',mid)
                    if current.get('v3_job')!=job or current.get('deleted_at') or current['revision']!=revision:return
                    current.update(v3_bundle=deepcopy(bundle),analysis_phase=f'combined:{i+1}/{len(groups)}');w.save(c,'meeting',current)
                change_items.extend(found['items'])
            proposals=make_proposals(w,m,change_items[:12],topics) if len(change_items)<=12 else []
            if len(change_items)>12:raise ValueError('요구·변경 항목이 12개를 넘었습니다. 회의 안건을 나누어 등록해 주세요.')
            with w.connect() as c:
                c.execute('BEGIN IMMEDIATE');current=w.read(c,'meeting',mid)
                if current.get('v3_job')!=job or current.get('deleted_at') or current['revision']!=revision:return
                # Replace only this pipeline's prior machine results, preserving human edits.
                corrected_sources=set()
                for old in w.all_records(c,'change_event'):
                    if old['meeting_id']==mid and not old.get('human_edited'):
                        old['superseded_by_revision']=revision;w.save(c,'change_event',old)
                    elif old['meeting_id']==mid and old.get('human_edited') and old.get('source_revision')==revision:
                        # Re-analysis must not bring back the machine text a person corrected.
                        for original in [old,*[h['record'] for h in old.get('edit_history',[])]]:
                            corrected_sources.add((original['category'],norm(original['title']),tuple(sorted(original['evidence']))))
                seen=set()
                for e in proposals:
                    if (e['category'],norm(e['title']),tuple(sorted(e['evidence']))) in corrected_sources:continue
                    key=(norm(e['title']),e['business_state'],e['after'])
                    if key in seen:continue
                    seen.add(key);w.save(c,'change_event',e)
                metrics.update(seconds=round(time.perf_counter()-started,2),analysis_seconds=round(time.perf_counter()-acquired,2),source_chars=len(current['source']),source_revision=revision)
                current.update(v3_bundle=bundle,reviewed_bundle=bundle,overview={k:bundle[k] for k in ('summary','decisions')},candidates=bundle['candidates'],ai_snapshot={'bundle':deepcopy(bundle),'created_at':w.now(),'model':metrics.get('model')},analysis_state='ready',analysis_phase='complete',analysis_stale=False,error='',metrics=metrics,analysis_finished_at=w.now(),change_scan_state='ready',change_scan_revision=revision,change_scan_extraction_version=EXTRACTION_VERSION,version=current['version']+1)
                w.save(c,'meeting',current)
        except Exception as exc:
            with w.connect() as c:
                m=w.read(c,'meeting',mid)
                if m.get('v3_job')==job and not m.get('deleted_at'):
                    m.update(analysis_state='failed',analysis_phase='failed',error=str(getattr(exc,'detail',exc))[:500],version=m['version']+1);w.save(c,'meeting',m)

class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Selection(Strict):
    id:str
    project_id:str
    title:str=Field(default='',max_length=240)
    date:str=''
    confirmed:bool=False
class Batch(Strict):items:list[Selection]=Field(min_length=1,max_length=20)
class NoteEdit(Strict):version:int;point:str;text:str=Field(min_length=1,max_length=2000)
class SourceEdit(Strict):version:int;title:str=Field(min_length=1,max_length=240);date:str='';source:str=Field(min_length=10,max_length=60000)
class ChangeEdit(Strict):
    version:int
    source_revision:int
    title:str=Field(min_length=2,max_length=160)
    business_state:str
    before:str=Field(default='',max_length=1500)
    after:str=Field(min_length=1,max_length=1500)
    evidence:list[str]=Field(min_length=1,max_length=20)

def build_router(w):
    r=APIRouter(prefix='/api/v3')
    def queue_fields(m,history):
        from work.v3.fast_ai import VERSION
        return {'analysis_queued_at':stamp(),'analysis_started_at':None,'analysis_finished_at':None,'analysis_loading_seconds':0,'analysis_loading_started_at':None,'analysis_estimate':estimate_runtime(m['source'],history,VERSION)}
    @r.patch('/changes/{cid}')
    def edit_change(cid,body:ChangeEdit,actor=Depends(w.user)):
        from work.v17.changes import Change,validate_change,archive_record
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE');item=w.read(c,'change_event',cid)
            w.project(c,item['project_id'],actor,True);w.version(item,body.version)
            m=w.read(c,'meeting',item['meeting_id']);active(m)
            if item.get('superseded_by_revision') or item.get('review_state')=='제외' or item['source_revision']!=m['revision'] or body.source_revision!=m['revision'] or m.get('analysis_stale'):
                raise HTTPException(409,'원문 또는 변경 기록이 바뀌었습니다. 최신 변경이력을 다시 열어 주세요.')
            if m.get('analysis_state') in ('queued','running'):
                raise HTTPException(409,'회의록 분석이 끝난 뒤 수정해 주세요.')
            # v3 uses inferred topic IDs, which are not legacy change_topic rows.
            payload=validate_change(w,c,Change(meeting_id=m['id'],source_revision=m['revision'],category=item['category'],effective_date=item['effective_date'],**body.model_dump(exclude={'source_revision'})),actor)
            topic_id=item.get('topic_id') if norm(item['title'])==norm(body.title) else None
            archive_record(w,item,actor,'수정')
            item.update(payload,topic_id=topic_id,version=item['version']+1,human_edited=True,review_state='검토 전',updated_at=w.now(),updated_by=actor['id'])
            w.save(c,'change_event',item)
        return {**item,'context':change_context(item['quotes'],item['after'])}
    def public_import(d,ps,context=''):
        return {k:d.get(k) for k in ('id','filename','title','meeting_date','warnings')}|match_project(d['filename'],d.get('declared_project',''),d['source'],ps,context)
    @r.post('/imports')
    async def prepare(files:list[UploadFile]=File(default=[]),text:str=Form(default=''),context:str=Form(default=''),actor=Depends(w.user)):
        if len(files)>20:raise HTTPException(422,'한 번에 20개까지 등록할 수 있습니다.')
        if not files and not text.strip():raise HTTPException(422,'파일 또는 내용을 입력해 주세요.')
        with w.connect() as c:
            ps=[p for p in w.all_records(c,'project') if actor['id'] in p['members']]
            if context:w.project(c,context,actor)
        inputs=[(f.filename or '회의록',await f.read(8*1024*1024+1)) for f in files]
        if text.strip():inputs.append(('직접 입력한 회의록.txt',text.encode('utf-8')))
        items=[];errors=[]
        for filename,data in inputs:
            try:
                parsed,suffix=parse_file(filename,data);iid=w.uid();path=w.FILES/(iid+suffix);path.write_bytes(data)
                d={'id':iid,'actor_id':actor['id'],'filename':Path(filename).name,'title':parsed['title'] or Path(filename).stem,'meeting_date':parse_date(parsed.get('meeting_date')),'source':parsed['source'],'declared_project':parsed.get('project',''),'warnings':parsed.get('warnings',[]),'created_at':w.now(),'fingerprint':hashlib.sha256(data).hexdigest(),'source_type':suffix.lstrip('.'),'original_path':str(path),'docx':str(path) if suffix=='.docx' else None,'pdf':str(path) if suffix=='.pdf' else None,'txt':str(path) if suffix in ('.txt','.md') else None,'preview_finished':suffix!='.docx','v3_import':True}
                with w.connect() as c:w.save(c,'import',d)
                items.append(public_import(d,ps,context))
            except Exception as exc:errors.append({'filename':filename,'error':str(getattr(exc,'detail',exc))[:300]})
        return {'items':items,'errors':errors}
    @r.post('/register',status_code=202)
    def register(body:Batch,actor=Depends(w.user)):
        jobs=[];result=[];errors=[];batch_id=w.uid();batch_at=stamp()
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            ps=[p for p in w.all_records(c,'project') if actor['id'] in p['members']]
            history=w.all_records(c,'meeting')
            for item in body.items:
                try:
                    d=w.read(c,'import',item.id)
                    if d['actor_id']!=actor['id']:raise HTTPException(403,'본인이 올린 파일만 등록할 수 있습니다.')
                    if d.get('meeting_id'):
                        registered=w.read(c,'meeting',d['meeting_id']);w.project(c,registered['project_id'],actor)
                        if registered.get('deleted_at'):raise HTTPException(409,'휴지통에 있는 회의록입니다. 복원한 뒤 확인해 주세요.')
                        result.append({'id':registered['id'],'duplicate':True});continue
                    p=w.project(c,item.project_id,actor)
                    match=match_project(d['filename'],d.get('declared_project',''),d['source'],ps)
                    if (match['needs_check'] or match['project_id']!=p['id']) and not item.confirmed:raise HTTPException(422,'프로젝트 선택을 확인해 주세요.')
                    duplicate=next((m for m in w.all_records(c,'meeting') if m.get('fingerprint')==d['fingerprint'] and m['project_id']==p['id'] and not m.get('deleted_at')),None)
                    if duplicate:d['meeting_id']=duplicate['id'];w.save(c,'import',d);result.append({'id':duplicate['id'],'duplicate':True});continue
                    from server import lines
                    mid=w.uid();job=w.uid();registered_at=w.now()
                    m={'id':mid,'project_id':p['id'],'title':item.title.strip() or d['title'],'date':w.due(item.date or d.get('meeting_date')) or '','source':d['source'],'lines':lines(d['source']),'author':actor['id'],'candidates':[],'analysis_state':'queued','analysis_phase':'queued','analysis_origin':'로컬 AI 분석','error':'','warnings':d.get('warnings',[]),'version':1,'created_at':registered_at,'v3_job':job,'document_status':'등록 완료','revision':1,'original_source':d['source'],'original_title':d['title'],'original_date':d.get('meeting_date',''),'approved_revision':None,'document_events':[],'analysis_stale':False,'revisions':[]}
                    m.update({k:d.get(k) for k in ('docx','pdf','txt','fingerprint','source_type','original_path','filename','preview_finished')})
                    m.update(queue_fields(m,history),registration_batch_id=batch_id,registration_batch_at=batch_at)
                    register_revision(m);w.save(c,'meeting',m);d['meeting_id']=mid;w.save(c,'import',d);jobs.append((mid,job,bool(d.get('docx'))));result.append({'id':mid,'duplicate':False})
                except HTTPException as exc:errors.append({'id':item.id,'error':str(exc.detail)})
        for mid,job,word in jobs:
            w.POOL.submit(run_analysis,w,mid,job)
            if word:w.PREVIEW_POOL.submit(w.convert_background,mid)
        return {'registered':result,'errors':errors}
    @r.post('/meetings/{mid}/analyze',status_code=202)
    def retry(mid,actor=Depends(w.user)):
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE');m=w.read(c,'meeting',mid);p=w.project(c,m['project_id'],actor);active(m)
            if actor['id'] not in (m['author'],p['pm']):raise HTTPException(403,'작성자 또는 PM이 다시 분석할 수 있습니다.')
            if m['analysis_state'] in ('queued','running'):return {'ok':True}
            job=w.uid();timing=queue_fields(m,[x for x in w.all_records(c,'meeting') if x['id']!=mid]);m.update(timing,v3_job=job,analysis_state='queued',analysis_phase='queued',error='',version=m['version']+1);w.save(c,'meeting',m)
        w.POOL.submit(run_analysis,w,mid,job);return {'ok':True}
    @r.get('/workspace')
    def workspace(actor=Depends(w.user)):
        with w.connect() as c:
            # Explicit creation order; rowid resolves creations within the same second.
            ordered=[json.loads(row[0]) for row in c.execute("SELECT payload FROM records WHERE kind='project' ORDER BY json_extract(payload,'$.created_at') DESC,rowid DESC")]
            ps=[p for p in ordered if actor['id'] in p['members'] and not p.get('deleted_at')];ids={p['id'] for p in ps}
            all_meetings=w.all_records(c,'meeting');active_project_ids={p['id'] for p in ordered if not p.get('deleted_at')}
            progress=progress_snapshot([m for m in all_meetings if m['project_id'] in active_project_ids])
            ms=[m for m in all_meetings if m['project_id'] in ids and not m.get('deleted_at')];by={m['id']:m for m in ms}
            es=[]
            for e in w.all_records(c,'change_event'):
                m=by.get(e['meeting_id'])
                if not m or e.get('superseded_by_revision') or e.get('review_state')=='제외' or e.get('source_revision')!=m['revision'] or m.get('analysis_stale'):continue
                refs={x['id']:x['text'] for x in m['lines']}
                quotes=[refs[x] for x in e['evidence'] if x in refs]
                es.append({**e,'quotes':quotes,'context':change_context(quotes,e['after']),'meeting_title':m['title'],'meeting_date':m.get('date','')})
            meetings=[{k:m.get(k) for k in ('id','project_id','title','date','author','analysis_state','analysis_phase','analysis_stale','error','version','revision','created_at','warnings','source_type','filename')}|{'points':note_points(m),'metrics':m.get('metrics',{}),'progress':progress.get(m['id'])} for m in ms]
            archived=[{k:m.get(k) for k in ('id','title','project_id','deleted_at')} for m in w.all_records(c,'meeting') if m['project_id'] in ids and m.get('deleted_at') and actor['id'] in (m['author'],next(p['pm'] for p in ps if p['id']==m['project_id']))]
            return {'user':actor,'people':w.all_records(c,'person'),'projects':ps,'meetings':meetings,'archived':archived,'changes':es,'calendar':calendar_events(ms,es),'recent_batch':recent_batch([m for m in all_meetings if m['project_id'] in ids],actor['id']),'today':w.now()[:10],'can_create_project':w.can_create_project(c,actor),'version':'3.0-local'}
    @r.get('/search')
    def search(q:str=Query(default='',max_length=120),project_id:str='',actor=Depends(w.user)):
        terms=[norm(x) for x in q.split() if norm(x)]
        if not terms:return {'items':[],'total':0}
        with w.connect() as c:
            ps=[w.project(c,project_id,actor)] if project_id else [p for p in w.all_records(c,'project') if actor['id'] in p['members']]
            projects={p['id']:p for p in ps};items=[]
            for m in w.all_records(c,'meeting'):
                if m['project_id'] not in projects or m.get('deleted_at'):continue
                text=norm(m['title']+' '+projects[m['project_id']]['name']+' '+m['source'])
                if not all(t in text for t in terms):continue
                matched=[x for x in m['lines'] if any(t in norm(x['text']) for t in terms)]
                items.append({'id':m['id'],'title':m['title'],'date':m.get('date',''),'project_id':m['project_id'],'project_name':projects[m['project_id']]['name'],'excerpts':matched[:3]})
            items.sort(key=lambda x:x['date'],reverse=True)
            return {'items':items[:50],'total':len(items)}
    @r.get('/meetings/{mid}/download')
    def download(mid,actor=Depends(w.user)):
        with w.connect() as c:m=w.read(c,'meeting',mid);w.project(c,m['project_id'],actor);active(m)
        path=Path(m.get('original_path') or m.get('docx') or m.get('txt') or m.get('pdf') or '-')
        if not path.is_file():raise HTTPException(404,'원본 파일을 찾지 못했습니다.')
        return FileResponse(path,filename=m.get('filename') or m['title']+path.suffix)
    @r.patch('/meetings/{mid}/note')
    def edit_note(mid,body:NoteEdit,actor=Depends(w.user)):
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE');m=w.read(c,'meeting',mid);p=w.project(c,m['project_id'],actor);active(m);w.version(m,body.version)
            if actor['id'] not in (m['author'],p['pm']):raise HTTPException(403,'작성자 또는 PM이 수정할 수 있습니다.')
            if m['analysis_state'] in ('running','queued'):raise HTTPException(409,'분석 후 수정해 주세요.')
            try:key,index=body.point.split(':');index=int(index);bundle=deepcopy(m.get('reviewed_bundle') or m.get('v3_bundle') or m.get('overview') or {});point=bundle[key][index]
            except (KeyError,ValueError,IndexError):raise HTTPException(422,'수정할 항목을 다시 열어 주세요.')
            if key not in ('summary','decisions','candidates') or index<0 or not body.text.strip():raise HTTPException(422,'항목을 확인해 주세요.')
            field='description' if key=='candidates' else 'text';point[field]=body.text.strip()
            m.update(reviewed_bundle=bundle,version=m['version']+1);m.setdefault('document_events',[]).append({'at':w.now(),'actor':actor['id'],'action':'AI 정리 수정','point':body.point});w.save(c,'meeting',m)
        return {'ok':True}
    @r.patch('/meetings/{mid}/source',status_code=202)
    def edit_source(mid,body:SourceEdit,actor=Depends(w.user)):
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE');m=w.read(c,'meeting',mid);p=w.project(c,m['project_id'],actor);active(m);w.version(m,body.version)
            if actor['id'] not in (m['author'],p['pm']):raise HTTPException(403,'작성자 또는 PM이 수정할 수 있습니다.')
            w.save_content(w,m,actor,body.title,body.date,body.source);m.update(analysis_stale=True);register_revision(m);w.save(c,'meeting',m)
        return retry(mid,actor)
    @r.delete('/meetings/{mid}')
    def trash(mid,actor=Depends(w.user)):
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE');m=w.read(c,'meeting',mid);p=w.project(c,m['project_id'],actor)
            if actor['id'] not in (m['author'],p['pm']):raise HTTPException(403,'작성자 또는 PM이 삭제할 수 있습니다.')
            m.update(deleted_at=w.now(),deleted_by=actor['id'],v3_job=w.uid(),version=m['version']+1);w.save(c,'meeting',m)
        return {'ok':True}
    @r.post('/meetings/{mid}/restore')
    def restore(mid,actor=Depends(w.user)):
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE');m=w.read(c,'meeting',mid);p=w.project(c,m['project_id'],actor)
            if actor['id'] not in (m['author'],p['pm']):raise HTTPException(403,'작성자 또는 PM이 복원할 수 있습니다.')
            m.pop('deleted_at',None);m.pop('deleted_by',None)
            if m['analysis_state'] in ('queued','running'):m.update(analysis_state='failed',error='복원되었습니다. 다시 분석해 주세요.')
            m['version']+=1;w.save(c,'meeting',m)
        return {'ok':True}
    return r
