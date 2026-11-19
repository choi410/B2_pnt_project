"""Private pre-registration review, immutable reviewed summaries, recoverable trash."""
import hashlib,io,threading,time
from copy import deepcopy
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse,Response
from pydantic import BaseModel, ConfigDict, Field
from work.v17.documents import ensure_document, notify, meeting_confirmed
PDF_LOCK=threading.Lock()

def preview_pages(path):
 if not path or not Path(path).is_file():return 0
 try:
  import pypdfium2 as pdfium
  with PDF_LOCK:
   with pdfium.PdfDocument(path) as doc:return len(doc)
 except Exception:return 0

def source_hash(text):return hashlib.sha256(text.replace('\r\n','\n').strip().encode()).hexdigest()
def active(record):
 if record.get('deleted_at'):raise HTTPException(409,'휴지통에 있는 회의록입니다. 복구한 뒤 수정해 주세요.')
def validate_bundle(w,bundle,source,project=None):
 from server import lines
 refs={x['id'] for x in lines(source)};out={'summary':[],'decisions':[],'candidates':[]}
 if not isinstance(bundle,dict):raise HTTPException(422,'정리 내용을 확인해 주세요.')
 note_ids=[]
 def note_id(item,key,index):
  value=item.get('note_id') or ('candidate-'+str(item.get('id')) if key=='candidates' else key+'-'+str(index))
  if not isinstance(value,str) or len(value)>160 or value in note_ids:raise HTTPException(422,'문장 식별자를 확인해 주세요.')
  note_ids.append(value);return value
 if isinstance(bundle.get('overall'),str) and bundle['overall'].strip():out['overall']=bundle['overall'].strip()[:1000]
 for key in ('summary','decisions'):
  items=bundle.get(key,[])
  if not isinstance(items,list) or len(items)>20:raise HTTPException(422,'정리 항목은 구분별로 20개까지 작성할 수 있습니다.')
  for index,item in enumerate(items):
   if not isinstance(item,dict):raise HTTPException(422,'정리 항목 형식이 올바르지 않습니다.')
   text=str(item.get('text','')).strip();evidence=item.get('evidence',[])
   if len(text)>2000:raise HTTPException(422,'정리 항목은 2000자 이내로 작성해 주세요.')
   if not isinstance(evidence,list) or any(x not in refs for x in evidence):raise HTTPException(422,'현재 본문에 있는 근거를 선택해 주세요.')
   if text:out[key].append({'note_id':note_id(item,key,index),'text':text,'evidence':list(dict.fromkeys(evidence))})
 items=bundle.get('candidates',[])
 if not isinstance(items,list) or len(items)>30:raise HTTPException(422,'업무 제안은 30개까지 작성할 수 있습니다.')
 seen=set()
 for index,item in enumerate(items):
  if not isinstance(item,dict):raise HTTPException(422,'업무 형식을 확인해 주세요.')
  title=str(item.get('title','')).strip()
  if not title:continue
  if len(title)>1000 or item.get('kind') not in ('업무','확인사항'):raise HTTPException(422,'업무 제목과 구분을 확인해 주세요.')
  cid=item.get('id') or w.uid()
  if not isinstance(cid,str) or len(cid)>100 or cid in seen:raise HTTPException(422,'업무 항목 식별자가 중복되었습니다.')
  seen.add(cid);evidence=item.get('evidence',[])
  if not isinstance(evidence,list) or any(x not in refs for x in evidence):raise HTTPException(422,'업무의 현재 본문 근거를 확인해 주세요.')
  people={k:item.get(k) or None for k in ('owner_id','reviewer_id')}
  if any(v and (not project or v not in project['members']) for v in people.values()):raise HTTPException(422,'선택한 프로젝트 참여자 중 담당자·확인자를 골라 주세요.')
  start=w.due(item.get('start'));due=w.due(item.get('due'))
  if start and due and start>due:raise HTTPException(422,'시작 예정일은 완료 목표일보다 늦을 수 없습니다.')
  out['candidates'].append({'note_id':note_id({**item,'id':cid},'candidates',index),'id':cid,'title':title,'description':str(item.get('description') or '')[:4000],'kind':item['kind'],**people,'start':start,'due':due,'evidence':list(dict.fromkeys(evidence)),'state':'draft','note':'','requires_review':bool(item.get('requires_review',True)),'selected_for_assignment':bool(item.get('selected_for_assignment',False))})
 order=bundle.get('note_order',[])
 if not isinstance(order,list) or len(order)>100 or any(not isinstance(x,str) for x in order):raise HTTPException(422,'문장 순서를 확인해 주세요.')
 out['note_order']=list(dict.fromkeys([x for x in order if x in note_ids]+note_ids))
 if 'changes' in bundle:
  from work.v17.changes import CATEGORIES,STATES,MAX_ITEMS
  changes=bundle['changes']
  if not isinstance(changes,list) or len(changes)>MAX_ITEMS:raise HTTPException(422,'요구사항·변경 제안 형식을 확인해 주세요.')
  topics={}
  if project and any(isinstance(x,dict) and x.get('topic_id') for x in changes):
   with w.connect() as c:topics={t['id']:t for t in w.all_records(c,'change_topic') if t['project_id']==project['id']}
  out['changes']=[]
  for item in changes:
   if not isinstance(item,dict) or item.get('category') not in CATEGORIES or item.get('business_state') not in STATES:raise HTTPException(422,'변경 구분과 원문의 상태를 확인해 주세요.')
   title=str(item.get('title','')).strip();after=str(item.get('after','')).strip();evidence=item.get('evidence',[])
   action=item.get('review_action','record')
   if not 2<=len(title)<=160 or not after or len(after)>1500 or len(str(item.get('before','')))>1500:raise HTTPException(422,'변경 대상과 내용을 확인해 주세요.')
   if not isinstance(evidence,list) or not evidence or len(evidence)>20 or any(x not in refs for x in evidence):raise HTTPException(422,'변경 제안의 현재 본문 근거를 선택해 주세요.')
   if action not in ('record','defer','exclude'):raise HTTPException(422,'변경 검토 방식을 확인해 주세요.')
   topic_id=item.get('topic_id') or None
   if topic_id and (not isinstance(topic_id,str) or topic_id not in topics or topics[topic_id]['category']!=item['category']):raise HTTPException(422,'같은 프로젝트·구분의 요구사항만 연결할 수 있습니다. 연결 대상을 다시 확인해 주세요.')
   out['changes'].append({'topic_id':topic_id,'title':title,'category':item['category'],'before':str(item.get('before') or ''),'after':after,'business_state':item['business_state'],'evidence':list(dict.fromkeys(evidence)),'review_action':action})
 return out

def convert_import(w,iid):
 with w.connect() as c:d=w.read(c,'import',iid)
 try:pdf=w.convert_docx(Path(d['docx']))
 except Exception:pdf=None
 with w.connect() as c:
  c.execute('BEGIN IMMEDIATE');d=w.read(c,'import',iid);d['pdf']=pdf;d['preview_finished']=True;w.save(c,'import',d)

def analyze_import(w,iid):
 with w.AI_LOCK:
  try:
   with w.connect() as c:
    c.execute('BEGIN IMMEDIATE');d=w.read(c,'import',iid);active(d)
    if d.get('meeting_id'):return
    worker_started=time.perf_counter()
    queue_seconds=max(0,time.time()-d.get('analysis_queued_at',time.time()))
    d.update(analysis_state='running',analysis_phase='notes');w.save(c,'import',d)
    text=d.get('edited_body') or d['source'];fingerprint=source_hash(text)
    p=w.read(c,'project',d['chosen_project']) if d.get('chosen_project') else None
    people=[w.read(c,'person',x) for x in p['members']] if p else []
   from server import lines
   from work.v17.demo_ai import extract_notes
   source_lines=lines(text);result,metrics=extract_notes(source_lines)
   postprocess_started=time.perf_counter()
   refs={x['id']:x['text'] for x in source_lines};bundle={'summary':[],'decisions':[],'candidates':[]}
   if result.get('overall'):bundle['overall']=str(result['overall'])[:600]
   for key in ('summary','decisions'):
    for item in result.get(key,[]):
     evidence=[x for x in item.get('evidence',[]) if x in refs]
     if evidence and item.get('text'):bundle[key].append({'text':item['text'][:2000],'evidence':evidence})
   for item in result['items']:
    evidence=[x for x in item.get('evidence',[]) if x in refs]
    if not evidence:continue
    quote=' '.join(refs[x] for x in evidence)
    owner=next((x['id'] for x in people if x['id']==item.get('owner_id') and x['name'] in quote),None)
    kind=item['kind'];due=item.get('due') if item.get('due') and item['due'] in quote else None
    start=item.get('start') if item.get('start') and item['start'] in quote else None
    if start and due and start>due:start=None
    bundle['candidates'].append({'id':w.uid(),'title':item['title'],'description':str(item.get('description') or '')[:4000],'kind':kind,'owner_id':owner if kind=='업무' else None,'reviewer_id':(owner or (p['pm'] if p else None)) if kind=='확인사항' else (p['pm'] if p else None),'start':start,'due':due,'evidence':evidence})
   bundle=validate_bundle(w,bundle,text,p)
   # Publish a read-only first stage. Final registration remains unavailable
   # until changes finish, so a partial draft cannot overwrite late results.
   metrics['notes_ready_seconds']=round(queue_seconds+time.perf_counter()-worker_started,3)
   with w.connect() as c:
    c.execute('BEGIN IMMEDIATE');d=w.read(c,'import',iid)
    if source_hash(d.get('edited_body') or d['source'])!=fingerprint:raise ValueError('본문이 변경되었습니다. 다시 분석해 주세요.')
    d.update(analysis_phase='changes',partial_bundle=deepcopy(bundle),partial_hash=fingerprint,metrics=deepcopy(metrics))
    w.save(c,'import',d)
   change_error='';change_started=time.perf_counter()
   # Keep the established task extractor separate from the business-change prompt.
   try:
    from work.v17.changes import extract_changes,EXTRACTION_VERSION
    with w.connect() as c:
     topics=[{'id':t['id'],'title':t['title'],'category':t['category']} for t in w.all_records(c,'change_topic') if p and t['project_id']==p['id']][:20]
    change_result,_=extract_changes(w,{'lines':source_lines},topics)
    bundle=validate_bundle(w,{**bundle,'changes':change_result['items']},text,p)
   except Exception as exc:change_error=str(getattr(exc,'detail',exc))[:400]
   metrics['change_analysis_seconds']=round(time.perf_counter()-change_started,3)
   metrics.update(queue_seconds=round(queue_seconds,3),postprocess_seconds=round(max(0,time.perf_counter()-postprocess_started-metrics['change_analysis_seconds']),3),worker_seconds=round(time.perf_counter()-worker_started,3),total_seconds=round(queue_seconds+time.perf_counter()-worker_started,3))
   with w.connect() as c:
    c.execute('BEGIN IMMEDIATE');d=w.read(c,'import',iid)
    if source_hash(d.get('edited_body') or d['source'])!=fingerprint:raise ValueError('본문이 변경되었습니다. 다시 분석해 주세요.')
    d.update(ai_snapshot={'bundle':deepcopy(bundle),'source':text,'source_hash':fingerprint,'created_at':w.now(),'model':metrics.get('model')},review_bundle=bundle,analysis_state='ready',analysis_phase='complete',partial_bundle=None,partial_hash=None,analysis_origin='로컬 AI 분석',analysis_hash=fingerprint,metrics=metrics,analysis_error='',change_analysis_error=change_error,change_analysis_version=EXTRACTION_VERSION if 'changes' in bundle else None,review_confirmed=False,draft_version=d.get('draft_version',1)+1)
    w.save(c,'import',d)
  except Exception as exc:
   with w.connect() as c:
    d=w.read(c,'import',iid);d.update(analysis_state='failed',analysis_phase='failed',partial_bundle=None,partial_hash=None,analysis_error=str(exc)[:400],draft_version=d.get('draft_version',1)+1);w.save(c,'import',d)

class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Finalize(Strict):
 version:int
 confirm_project_mismatch:bool=False
 confirm_changes:bool=False
 selected:list[str]=Field(default_factory=list,max_length=30)
class Version(Strict):version:int

def build_router(w):
 r=APIRouter(prefix='/api')
 def own(c,iid,actor):
  d=w.read(c,'import',iid)
  if d['actor_id']!=actor['id']:raise HTTPException(403,'본인이 작성 중인 회의록만 열 수 있습니다.')
  if d.get('chosen_project'):w.project(c,d['chosen_project'],actor)
  return d
 @r.get('/meeting-imports/{iid}/original/{fmt}')
 def original(iid,fmt,actor=Depends(w.user)):
  with w.connect() as c:d=own(c,iid,actor)
  if fmt not in ('docx','pdf','txt'):raise HTTPException(404)
  p=Path(d.get(fmt) or '-')
  if not p.is_file():raise HTTPException(404,'원본 미리보기를 준비 중입니다. 본문 대조 보기를 먼저 이용해 주세요.')
  return FileResponse(p,media_type='application/pdf' if fmt=='pdf' else 'application/octet-stream',filename=d['id']+'.'+fmt,content_disposition_type='inline' if fmt=='pdf' else 'attachment')
 def render_page(kind,id,page,actor):
  with w.connect() as c:
   d=own(c,id,actor) if kind=='import' else w.read(c,'meeting',id)
   if kind=='meeting':w.project(c,d['project_id'],actor)
  path=d.get('pdf')
  if not path or not Path(path).is_file():raise HTTPException(404,'미리보기를 준비 중입니다.')
  import pypdfium2 as pdfium
  with PDF_LOCK:
   with pdfium.PdfDocument(path) as doc:
    if page<1 or page>len(doc):raise HTTPException(404,'페이지를 찾을 수 없습니다.')
    sheet=doc[page-1]
    try:
     scale=min(1.8,2200/max(sheet.get_size()));bitmap=sheet.render(scale=scale)
     try:
      picture=bitmap.to_pil();buffer=io.BytesIO();picture.save(buffer,format='PNG');picture.close();data=buffer.getvalue()
     finally:bitmap.close()
    finally:sheet.close()
  return Response(data,media_type='image/png')
 @r.get('/meeting-imports/{iid}/preview/{page}')
 def import_preview(iid,page:int,actor=Depends(w.user)):return render_page('import',iid,page,actor)
 @r.get('/meetings/{mid}/preview/{page}')
 def meeting_preview(mid,page:int,actor=Depends(w.user)):return render_page('meeting',mid,page,actor)
 @r.post('/meeting-imports/{iid}/analyze',status_code=202)
 def analyze(iid,body:Version,actor=Depends(w.user)):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');d=own(c,iid,actor);active(d)
   if d.get('meeting_id'):raise HTTPException(409,'이미 등록된 회의록입니다.')
   if d.get('draft_version',1)!=body.version:raise HTTPException(409,'최신 임시 저장본을 다시 열어 주세요.')
   if d.get('analysis_state') in ('running','queued'):raise HTTPException(409,'이미 분석 중입니다.')
   count=sum(x.get('analysis_state') in ('running','queued') for kind in ('meeting','import') for x in w.all_records(c,kind))
   if count>=8:raise HTTPException(429,'분석 대기가 많습니다. 잠시 후 다시 시도해 주세요.')
   d.update(analysis_state='queued',analysis_phase='queued',partial_bundle=None,partial_hash=None,analysis_queued_at=time.time(),analysis_error='',review_confirmed=False,draft_version=d.get('draft_version',1)+1);w.save(c,'import',d)
  w.POOL.submit(analyze_import,w,iid);return {'ok':True}
 @r.post('/meeting-imports/{iid}/finalize',status_code=201)
 def finalize(iid,body:Finalize,actor=Depends(w.user)):
  if body.selected:raise HTTPException(422,'시연용에서는 회의록만 등록합니다. 업무 배정은 지원하지 않습니다.')
  from work.v17.intake import match_projects
  from work.v17.changes import prepare_scan,submit_scan,make_proposals,confirm_change
  from server import lines
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');d=own(c,iid,actor);active(d)
   if d.get('meeting_id'):
    existing=w.read(c,'meeting',d['meeting_id'])
    return {'id':existing['id'],'created':[x['task_id'] for x in existing['candidates'] if x.get('state')=='applied'],'requested':len(existing.get('requested_task_ids',[])),'pending':sum(x['state']=='draft' for x in existing['candidates']),'change_candidates':existing.get('change_scan_added',0),'change_analysis_state':existing.get('change_scan_state')}
   if d.get('draft_version',1)!=body.version:raise HTTPException(409,'최신 임시 저장본을 다시 열어 주세요.')
   if d.get('analysis_state') in ('running','queued'):raise HTTPException(409,'분석이 끝난 뒤 대조하고 등록해 주세요.')
   if not d.get('review_confirmed') or d.get('review_hash')!=source_hash(d.get('edited_body') or d['source']):raise HTTPException(422,'원본과 정리 내용을 대조한 뒤 확인 표시를 해 주세요.')
   if not d.get('chosen_project') or not d.get('title','').strip():raise HTTPException(422,'프로젝트와 회의 제목을 입력해 주세요.')
   p=w.project(c,d['chosen_project'],actor);text=d.get('edited_body') or d['source']
   mismatch=bool(d.get('declared_project')) and p['id'] not in match_projects(d['declared_project'],[p])
   if mismatch and not body.confirm_project_mismatch:raise HTTPException(422,'원문의 프로젝트 표기와 등록할 프로젝트가 다릅니다. 선택을 확인해 주세요.')
   duplicate=next((m for m in w.all_records(c,'meeting') if m.get('fingerprint')==d['fingerprint'] and m['project_id']==p['id']),None)
   if duplicate:raise HTTPException(409,{'message':'같은 원본이 이미 등록되어 있습니다.'+(' 휴지통에서 복구할 수 있습니다.' if duplicate.get('deleted_at') else ''),'meeting_id':duplicate['id']})
   bundle=validate_bundle(w,d.get('review_bundle',{}),text,p)
   if len(body.selected)!=len(set(body.selected)) or set(body.selected)-{x['id'] for x in bundle['candidates']}:raise HTTPException(422,'배정할 업무 선택을 다시 확인해 주세요.')
   mid=w.uid();stamp=w.now()
   m={'id':mid,'project_id':p['id'],'title':d['title'].strip(),'date':d.get('meeting_date') or '','source':d['source'],'lines':lines(d['source']),'author':actor['id'],'candidates':[],'analysis_state':'ready','analysis_origin':d.get('analysis_origin') or '작성자 직접 정리','error':'','warnings':[],'version':1,'created_at':stamp,'docx':d.get('docx'),'txt':d.get('txt'),'pdf':d.get('pdf'),'fingerprint':d['fingerprint'],'source_type':d['source_type']}
   m['preview_finished']=not bool(m.get('docx') and not m.get('pdf'))
   ensure_document(m)
   if text!=d['source']:w.save_content(w,m,actor,m['title'],m['date'],text)
   overview={k:bundle[k] for k in ('summary','decisions')}
   if bundle.get('overall'):overview['overall']=bundle['overall']
   overview['checks']=[deepcopy(x) for x in bundle['candidates'] if x['kind']=='확인사항']
   overview.update(reviewed_by=actor['id'],reviewed_at=stamp,source_hash=source_hash(text),revision=m['revision'],origin=m['analysis_origin'])
   from work.v17.registration_policy import mark_registered,registration_notice,request_assignments
   direct=actor['id']==p['pm']
   m.update(ai_snapshot=deepcopy(d.get('ai_snapshot')),reviewed_bundle=deepcopy(bundle),candidates=bundle['candidates'],overview=overview,metrics=d.get('metrics',{}),requested_task_ids=[])
   mark_registered(w,m,actor)
   m['revisions'][-1].update(overview=deepcopy(overview))
   m['document_events'].append({'at':stamp,'actor':actor['id'],'action':'작성자 확인 후 등록','revision':m['revision'],'note':'원본과 정리 내용을 대조함. 프로젝트 사양·납기 기준 확정은 별도 확인.'})
   change_job=None
   if 'changes' in bundle:
    m.update(change_scan_state='ready',change_scan_revision=m['revision'],change_scan_target_revision=m['revision'],change_scan_extraction_version=d.get('change_analysis_version'),change_scan_added=len(bundle['changes']))
   else:change_job=prepare_scan(w,m)
   w.save(c,'meeting',m)
   topics=[t for t in w.all_records(c,'change_topic') if t['project_id']==p['id']]
   for proposal,choice in zip(make_proposals(w,m,bundle.get('changes',[]),topics),bundle.get('changes',[])):
    proposal['human_edited']=True
    # Registration never confirms business facts, including for the PM.
    w.save(c,'change_event',proposal)
   made=[]
   if direct:
    if body.selected:made=w.apply_candidates(c,m,p,m['candidates'],body.selected,actor,notify_assignments=False)
   else:request_assignments(w,c,m,p,body.selected,actor,notify=False)
   registration_notice(w,c,m,actor['id'],made,body.selected if not direct else [])
   d['meeting_id']=mid;w.save(c,'import',d)
  if change_job:submit_scan(w,mid,change_job)
  if m.get('docx') and not m.get('pdf'):w.PREVIEW_POOL.submit(w.convert_background,mid)
  return {'id':mid,'created':made,'requested':len(body.selected) if not direct else 0,'pending':sum(x['state']=='draft' for x in m['candidates']),'change_candidates':len(bundle.get('changes',[])),'change_analysis_state':m.get('change_scan_state')}
 @r.get('/trash')
 def trash(actor=Depends(w.user)):
  with w.connect() as c:
   ps={p['id']:p for p in w.all_records(c,'project') if actor['id'] in p['members']};items=[]
   for kind in ('meeting','import'):
    for d in w.all_records(c,kind):
     if not d.get('deleted_at'):continue
     allowed=(kind=='import' and d['actor_id']==actor['id'] and (not d.get('chosen_project') or d['chosen_project'] in ps)) or (kind=='meeting' and d['project_id'] in ps and actor['id'] in (d['author'],ps[d['project_id']]['pm']))
     if allowed:
      from work.v17.meeting_purge import reason
      blocked=reason(w,c,kind,d,actor)
      items.append({'can_purge':not blocked,'purge_reason':blocked,'id':d['id'],'kind':kind,'title':d.get('title') or d.get('filename') or '제목 미정','project_id':d.get('project_id') or d.get('chosen_project'),'deleted_at':d['deleted_at'],'deleted_by':d.get('deleted_by'),'version':d.get('version',d.get('draft_version',1))})
  return sorted(items,key=lambda x:x['deleted_at'],reverse=True)
 def mutate_trash(kind,id,body,actor,restore=False):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');d=w.read(c,kind,id)
   if kind=='import':
    own(c,id,actor)
    if d.get('meeting_id'):raise HTTPException(409,'등록된 회의록 목록에서 처리해 주세요.')
    key='draft_version'
   else:
    key='version';p=w.project(c,d['project_id'],actor)
    linked=any(t.get('meeting_id')==id for t in w.all_records(c,'task'))
    submitted=any(e['action']=='회의록 검토 요청' for e in d.get('document_events',[]))
    author_allowed=actor['id']==d['author'] and d['document_status']=='작성 중' and not submitted and not linked
    if actor['id']!=p['pm'] and not author_allowed:raise HTTPException(403,'검토 요청되었거나 업무가 연결된 회의록은 프로젝트 PM이 처리할 수 있습니다.')
   if d.get(key,1)!=body.version:raise HTTPException(409,'최신 상태를 다시 열어 주세요.')
   if restore:
    if not d.get('deleted_at'):raise HTTPException(409,'휴지통에 없는 항목입니다.')
    d['deleted_at']=None;d['deleted_by']=None
   else:
    active(d)
    if d.get('analysis_state') in ('running','queued'):raise HTTPException(409,'분석이 끝난 뒤 삭제해 주세요.')
    d.update(deleted_at=w.now(),deleted_by=actor['id'])
   d[key]=d.get(key,1)+1
   if kind=='meeting':d.setdefault('document_events',[]).append({'at':w.now(),'actor':actor['id'],'action':'휴지통에서 복구' if restore else '휴지통으로 이동','revision':d['revision'],'note':''})
   w.save(c,kind,d)
  return {'ok':True}
 @r.post('/meetings/{mid}/trash')
 def delete_meeting(mid,body:Version,actor=Depends(w.user)):return mutate_trash('meeting',mid,body,actor)
 @r.post('/meetings/{mid}/restore')
 def restore_meeting(mid,body:Version,actor=Depends(w.user)):return mutate_trash('meeting',mid,body,actor,True)
 @r.post('/meeting-imports/{iid}/trash')
 def delete_import(iid,body:Version,actor=Depends(w.user)):return mutate_trash('import',iid,body,actor)
 @r.post('/meeting-imports/{iid}/restore')
 def restore_import(iid,body:Version,actor=Depends(w.user)):return mutate_trash('import',iid,body,actor,True)
 return r
