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
from work.v3.approval import latest_by_meeting,summary as approval_summary
from work.v3.requirements import build_requirements

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
    meeting_dates={m['id']:m.get('date','') for m in meetings}
    for e in sorted(changes,key=lambda e:(e.get('effective_date',''),meeting_dates.get(e['meeting_id'],''),e.get('created_at',''),e['id'])):
        if e.get('business_state')=='확정' and e.get('extracted_category',e.get('category'))=='납기':latest[(e['project_id'],e.get('topic_id') or norm(e['title']))]=e
    for e in latest.values():
        ds=date_values(e['after'])
        if len(ds)==1:out.append({'id':'change:'+e['id'],'meeting_id':e['meeting_id'],'project_id':e['project_id'],'title':e['title']+' · '+e['after'],'start':ds[0],'end':ds[0],'kind':'합의 일정','evidence':e['evidence']})
    return out

_PDF_CACHE={}
def _squash(t):
    import unicodedata
    return ''.join(x for x in unicodedata.normalize('NFKC',t or '').casefold() if x.strip())
def _pdf_index(path):
    """원본 PDF의 글자와 위치를 한 번 읽어 둔다."""
    import unicodedata
    import pypdfium2 as pdfium
    from work.v17.intake_review import PDF_LOCK
    key=(path,Path(path).stat().st_mtime)
    if key in _PDF_CACHE:return _PDF_CACHE[key]
    pages=[]
    with PDF_LOCK:
        with pdfium.PdfDocument(path) as doc:
            for p in range(len(doc)):
                page=doc[p];tp=page.get_textpage()
                try:
                    W,H=page.get_size();chars=[];where=[]
                    for i in range(tp.count_chars()):
                        ch=unicodedata.normalize('NFKC',tp.get_text_range(i,1) or '').casefold()
                        if not ch.strip():continue
                        box=tp.get_charbox(i,loose=True)
                        for x in ch:
                            if x.strip():chars.append(x);where.append(box)
                    pages.append((W,H,''.join(chars),where))
                finally:
                    tp.close();page.close()
    if len(_PDF_CACHE)>16:_PDF_CACHE.clear()
    _PDF_CACHE[key]=pages
    return pages
def _rects(pages,p,k,size):
    W,H,_,where=pages[p];rows=[]
    for l,b,r_,t in where[k:k+size]:
        for row in rows:
            if min(row[3],t)-max(row[1],b)>0.5*min(row[3]-row[1],t-b):
                row[0]=min(row[0],l);row[1]=min(row[1],b);row[2]=max(row[2],r_);row[3]=max(row[3],t);break
        else:rows.append([l,b,r_,t])
    pad=1.5
    return {'page':p+1,'rects':[[round(max(0,(l-pad)/W),4),round(max(0,(H-t-pad)/H),4),round((r_-l+2*pad)/W,4),round((t-b+2*pad)/H,4)] for l,b,r_,t in rows]}
def _find_lines(pages,lines):
    """각 원문 행이 PDF 어디에 있는지(페이지, 시작, 길이). 못 찾은 행은 빠진다."""
    out={};cursor=(0,0)
    for line in lines:
        text=_squash(line['text'])
        if len(text)<2:continue
        bare=_squash(re.sub(r'^\s*(?:\d+[.)]|[-\u2022\u00b7*])\s*','',line['text']))
        hit=None
        for probe in dict.fromkeys([text,bare,bare[:40],bare[:24],bare[:14]]):
            if len(probe)<6 and probe!=text:continue
            for p in list(range(cursor[0],len(pages)))+list(range(0,cursor[0])):
                start=cursor[1] if p==cursor[0] else 0
                k=pages[p][2].find(probe,start)
                if k<0 and start:k=pages[p][2].find(probe)
                if k>=0:hit=(p,k,len(probe));break
            if hit:break
        if hit:out[line['id']]=hit;cursor=(hit[0],hit[1]+hit[2])
    return out
def locate_lines(path,lines):
    pages=_pdf_index(path)
    return {k:[_rects(pages,*hit)] for k,hit in _find_lines(pages,lines).items()}
def best_clause(text,event):
    """근거 행이 여러 내용을 담은 긴 문단일 때, 이 항목의 값이 적힌 구절만 골라낸다(규칙 기반). 못 고르면 행 전체."""
    parts=[x for x in re.split(r'(?<=[.!?])\s+|(?<=\))\s*,\s+|,\s+(?=[^\d])|;\s+',text) if x and x.strip()]
    if len(parts)<2:return text
    nums=lambda t:set(re.findall(r'\d+(?:[.,:/~\-]\d+)*',t))
    grams=lambda t:{t[i:i+2] for i in range(len(t)-1)}
    want=nums((event.get('after') or '')+' '+(event.get('before') or ''));words=grams(_squash((event.get('title') or '')+(event.get('after') or '')))
    def score(part):
        return 3*len(want&nums(part))+len(words&grams(_squash(part)))/max(6,len(_squash(part)))**0.5
    ranked=sorted(parts,key=score,reverse=True)
    if score(ranked[0])<=0.6:return text
    best=ranked[0].strip().rstrip('.,;')
    return best if len(_squash(best))>=4 else text
def clause_score(clause,event):
    nums=lambda t:set(re.findall(r'\d+(?:[.,:/~\-]\d+)*',t))
    grams=lambda t:{t[i:i+2] for i in range(len(t)-1)}
    want=nums((event.get('after') or '')+' '+(event.get('before') or ''));words=grams(_squash((event.get('title') or '')+(event.get('after') or '')))
    return 3*len(want&nums(clause))+len(words&grams(_squash(clause)))/max(6,len(_squash(clause)))**0.5
def source_wording(e,quotes):
    """서술형 내용은 AI가 다시 쓴 문장 대신 원문 문장을 그대로 쓴다(규칙 기반). 짧은 값이거나 이미 원문 그대로면 None."""
    after=str(e.get('after') or '')
    if e.get('edit_history') or len(after.split())<8 or _squash(after) in _squash(' '.join(quotes)):return None
    sentences=[x.strip() for q in quotes for x in re.split(r'(?<=[.!?])\s+',q) if x.strip()]
    if not sentences:return None
    best=max(sentences,key=lambda x:clause_score(x,e))
    return best if clause_score(best,e)>0.6 and _squash(best)!=_squash(after) else None
def locate_events(path,lines,events):
    """항목마다 원본에서 칠할 위치와, 텍스트 보기에서 칠할 구절을 돌려준다."""
    pages=_pdf_index(path) if path else [];hits=_find_lines(pages,lines) if pages else {}
    refs={l['id']:l['text'] for l in lines};out={}
    for e in events:
        boxes=[];clauses={};scores={}
        for ref in e.get('evidence') or []:
            if ref not in refs:continue
            clause=best_clause(refs[ref],e);clauses[ref]=clause;scores[ref]=clause_score(clause,e)
        main=max(scores,key=lambda k:scores[k]) if scores else None
        for ref,clause in clauses.items():
            hit=hits.get(ref)
            if not hit:continue
            p,k,size=hit;probe=_squash(clause);at=pages[p][2].find(probe,k,k+size+len(probe)) if clause!=refs[ref] else -1
            boxes.append({**(_rects(pages,p,at,len(probe)) if at>=0 else _rects(pages,p,k,size)),'main':ref==main})
        out[e['id']]={'boxes':boxes,'clauses':clauses,'main':main}
    return out

STAGES=['수주/사양협의','설계(기구/전장)','구매/제작','조립/사내시운전(FAT)','현장셋업(SAT)','양산/CS']
STAGE_KEYWORDS={
    '수주/사양협의':['수주','계약','견적','입찰','제안서','킥오프','착수','PO','URS'],
    '설계(기구/전장)':['승인도','설계','도면','사양','규격','공차','배치도','레이아웃','변경 요청','설계 변경','Rev.','검토 의견','DR'],
    '구매/제작':['구매','발주','자재','부품','구성품','업체 선정','외주','제작','가공','용접','도장','제관'],
    '조립/사내시운전(FAT)':['조립','배선','FAT','사내 시운전','공장 시운전','출하 검사','성능 시험','성능 확인','검수'],
    '현장셋업(SAT)':['현장 설치','설치','SAT','셋업','Hook-up','반입','시운전','현장'],
    '양산/CS':['양산','안정화','CS','하자 보수','하자 처리','정산','인수인계','최종 승인','클로징'],
}
_STAGE_WORDS=sorted([(s,k) for s,ks in STAGE_KEYWORDS.items() for k in ks],key=lambda x:-len(x[1]))
_SCHEDULE=re.compile(r'^\s?(일|일정|일자|날짜|예정일|투입일|기한|시점)')
_HEADS={'결정사항':2,'합의사항':2,'후속조치':2,'향후조치':2,'actionitem':2,'actionitems':2,'회의안건':1.5,'안건':1.5,'논의내용':1,'논의사항':1,'추가확인사항':1,'확인사항':1,'확인필요사항':1,'참고사항':.5}
def _stage_hits(text):
    """\ub2e8\uacc4 \ud575\uc2ec\uc5b4\ub97c \uae34 \uac83\ubd80\ud130 \ud55c \ubc88\uc529\ub9cc \uc13c\ub2e4. \ub0a0\uc9dc\u00b7\uc77c\uc815 \uc5b8\uae09(\ucd9c\ud558\uc77c \ub4f1)\uc740 \uc810\uc218\uc5d0\uc11c \ube80\ub2e4. (12\ub370\ubaa8\uc640 \uac19\uc740 \uaddc\uce59)"""
    used=[False]*len(text);out={}
    for stage,word in _STAGE_WORDS:
        start=0
        while True:
            i=text.find(word,start)
            if i<0:break
            start=i+len(word)
            if any(used[i:i+len(word)]):continue
            for k in range(i,i+len(word)):used[k]=True
            if _SCHEDULE.match(text[i+len(word):]):continue
            out.setdefault(stage,[]).append(word)
    return out
def infer_stage(m):
    """\ud68c\uc758\ub85d \ud558\ub098\uc758 \ub2e8\uacc4\ub97c \uaddc\uce59\uc73c\ub85c \ucd94\uc815\ud55c\ub2e4(AI \uc544\ub2d8). \uc810\uc218 3 \ubbf8\ub9cc\uc774\uac70\ub098 1\u00b72\uc704 \ucc28\uc774\uac00 \uc791\uc73c\uba74 \ucd94\uc815\ud558\uc9c0 \uc54a\ub294\ub2e4."""
    score={s:0.0 for s in STAGES};hits={s:[] for s in STAGES};best={}
    def add(text,weight,line=None):
        clean=re.sub(r'\s*/\s*[^/]*$',lambda x:'' if re.search(r'\d{4}-\d{2}-\d{2}|\uae4c\uc9c0|\ucc28\uc8fc|\uc911$',x.group(0)) else x.group(0),str(text or ''))
        for s,ws in _stage_hits(clean).items():
            score[s]+=len(ws)*weight;hits[s]+=ws
            if line and (s not in best or len(ws)*weight>best[s][0]):best[s]=(len(ws)*weight,line)
    add(m.get('title'),1.5)
    weight=1
    for line in m.get('lines') or []:
        text=str(line.get('text') or '').strip()
        if not text:continue
        key=re.sub(r'[\s:\uff1a\[\]]','',text).lower()
        if key in _HEADS:weight=_HEADS[key];continue
        if re.match(r'^(\ud68c\uc758\ub85d|meetingminutes|\ud68c\uc758\uba85|\ud504\ub85c\uc81d\ud2b8\uba85|\uc77c\uc2dc|\ucc38\uc11d\uc790|\uc791\uc131\uc790)',re.sub(r'\|.*','',key),re.I):continue
        add(text,weight,line)
    ranked=sorted(STAGES,key=lambda s:-score[s]);top,second=ranked[0],ranked[1]
    confident=score[top]>=3 and score[top]>=score[second]*1.5
    line=best.get(top,(0,None))[1]
    return {'stage':top if confident else None,'top':top,'score':round(score[top],1),'second':second,'second_score':round(score[second],1),
            'hits':list(dict.fromkeys(hits[top]))[:6],'meeting_id':m['id'],'meeting_title':m.get('title'),'meeting_date':m.get('date') or '',
            'line':{'id':line['id'],'text':line['text']} if line else None}

STAGE_PROMPT=("너는 설비 제작 프로젝트의 회의록을 읽고, 이 회의가 열린 시점에 프로젝트가 어느 단계까지 와 있는지 판단한다. 단계는 "+' → '.join(STAGES)+" 순서다.\n"
 "회의 주제가 아니라 회의 날짜 기준으로 실제 진행 중인 일로 고른다. 앞으로의 일정·계획 언급만으로 그 단계라고 보지 않는다. 애매하면 직전 회의 단계를 고른다.\n"
 "in_progress에 지금 하고 있는 일, planned에 나중에 하기로 한 일을 적고 stage는 in_progress만 보고 고른다. reason은 한 문장, evidence는 근거 문장 하나를 글자 그대로 옮긴다.")
_STAGE_FILE=Path(__file__).with_name('stage_prompt.txt')
def stage_prompt():
    """지시문은 stage_prompt.txt에서 매번 읽는다(고쳐도 재시작이 필요 없다). 파일이 없으면 기본 지시문."""
    try:
        text=_STAGE_FILE.read_text(encoding='utf-8').strip()
        if text:return text
    except OSError:pass
    return STAGE_PROMPT
def stage_version():
    """지시문이 바뀌면 값이 달라져 예전 판단이 자동으로 무효가 된다."""
    return hashlib.sha1(stage_prompt().encode('utf-8')).hexdigest()[:10]
def judge_stage(m,prev=None):
    """연결된 AI 또는 공용 로컬 모델로 단계를 판단한다. 실패하면 규칙 추정을 유지한다."""
    from work.v17 import llm
    if not llm.stage_available():return None
    text='\n'.join(str(l.get('text') or '').strip() for l in (m.get('lines') or []) if str(l.get('text') or '').strip())[:3500]
    if not text:return None
    from work.v3 import analysis_cache
    cache_inputs={'lines':m.get('lines') or [],'title':m.get('title') or '',
                  'date':m.get('date') or '', 'previous_stage':prev,'prompt':stage_prompt()}
    use_cache=analysis_cache.root() is not None and not llm.available()
    cached=analysis_cache.read('meeting-stage',cache_inputs) if use_cache else None
    if cached and isinstance(cached.get('value'),dict) and cached['value'].get('stage') in STAGES:
        return {**cached['value'],'revision':m.get('revision'),'at':stamp(),'cache_hit':True}
    schema={'type':'object','properties':{'in_progress':{'type':'string'},'planned':{'type':'string'},'stage':{'type':'string','enum':STAGES},'reason':{'type':'string'},'evidence':{'type':'string'}},'required':['in_progress','planned','stage','reason','evidence'],'additionalProperties':False}
    user=f"직전 회의 단계: {prev or '없음'}\n회의 제목: {m.get('title') or ''}\n회의 날짜: {m.get('date') or ''}\n회의록:\n{text}"
    try:
        raw,measure=llm.stage_chat([{'role':'system','content':stage_prompt()},{'role':'user','content':user}],500,schema=schema)
        out=json.loads(raw[raw.find('{'):raw.rfind('}')+1])
    except Exception:return None
    if out.get('stage') not in STAGES:return None
    ev=str(out.get('evidence') or '').strip();sq=lambda x:re.sub(r'\s+','',x)
    line=next((l for l in (m.get('lines') or []) if ev and (sq(ev) in sq(l.get('text') or '') or sq(l.get('text') or '') in sq(ev) and len(sq(l.get('text') or ''))>8)),None)
    result={'stage':out['stage'],'reason':str(out.get('reason') or '')[:200],'evidence':line['text'] if line else '','line_id':line['id'] if line else None,'revision':m.get('revision'),'v':stage_version(),'in_progress':str(out.get('in_progress') or '')[:300],'planned':str(out.get('planned') or '')[:300],'model':measure.get('model',llm.MODEL_LABEL),'at':stamp()}
    if use_cache:analysis_cache.write('meeting-stage',cache_inputs,result)
    return result
def stage_of(m):
    """화면에 쓸 회의 단계: AI 판단이 현재 원문 기준이면 그것, 아니면 규칙 추정."""
    if m.get('stage_manual') in STAGES:return {'stage':m['stage_manual'],'source':'pm','reason':'PM이 직접 지정했습니다.','evidence':'','line_id':None}
    a=m.get('stage_ai')
    if a and a.get('revision')==m.get('revision') and a.get('v')==stage_version():return {'stage':a['stage'],'source':'ai','reason':a.get('reason',''),'evidence':a.get('evidence',''),'line_id':a.get('line_id')}
    g=infer_stage(m);return {'stage':g['stage'],'source':'rule','reason':('키워드: '+', '.join(g['hits'])) if g['stage'] else '','evidence':(g['line'] or {}).get('text',''),'line_id':(g['line'] or {}).get('id')}

_UNIT=re.compile(r'\d\s*([A-Za-z\u03bc\u00b5\u2103\u00b0%]+(?:/[A-Za-z]+)?)')
def value_units(*texts):
    """값에 붙은 단위(숫자 바로 뒤의 영문·기호). 단위 목록을 따로 두지 않고 원문 표기에서 읽는다."""
    return {u.lower().replace('\u00b5','\u03bc').replace('\u00b0c','\u2103') for t in texts for u in _UNIT.findall(str(t or ''))}
def title_in_text(title,text):
    """항목명의 낱말이 근거 문장에 절반 이상 나오는지. '출하일'↔'출하'처럼 끝 글자만 다른 표기는 같은 낱말로 본다."""
    tokens=re.findall(r'\d+[\uac00-\ud7a3]+|[\uac00-\ud7a3]+|[A-Za-z]{2,}',str(title or ''));flat=norm(text)
    hit=lambda t:norm(t) in flat or (len(t)>=3 and norm(t[:2]) in flat)
    return not tokens or sum(hit(t) for t in tokens)*2>=len(tokens)
def event_checks(e,quotes,siblings):
    """규칙으로 걸러내는 의심 표시(AI 아님). 사람이 이름을 고쳤거나 기존 항목에 맞춰 이름을 바꾼 기록은 이름 점검을 하지 않는다."""
    out=[];text=' '.join(quotes)
    if not e.get('original_title') and not e.get('title_checked') and not title_in_text(e['title'],text):out.append({'kind':'title','text':'항목명이 근거 문장에 없습니다. 다른 대상의 값일 수 있습니다.'})
    others_=[o for o in siblings if o is not e and o.get('id')!=e.get('id')]
    if others_ and not e.get('title_checked'):
        # 값의 모양: 다른 기록은 모두 날짜인데 이 기록에는 날짜가 없거나, 다른 기록보다 훨씬 긴 설명 문장이다.
        dated=lambda t:bool(re.search(r'\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}/\d{1,2}',str(t or '')))
        mine_text=str(e.get('before') or '')+' '+str(e.get('after') or '')
        if all(dated(str(o.get('before') or '')+' '+str(o.get('after') or '')) for o in others_) and not dated(mine_text):
            out.append({'kind':'shape','text':'같은 항목의 다른 기록은 날짜인데 이 기록에는 날짜가 없습니다. 다른 대상의 내용일 수 있습니다.'})
        else:
            lens=sorted(len(str(o.get('after') or '')) for o in others_);mid=lens[len(lens)//2];L=len(str(e.get('after') or ''))
            if L>36 and L>3*max(mid,6):out.append({'kind':'shape','text':'같은 항목의 다른 기록보다 내용이 훨씬 깁니다. 값이 아니라 설명 문장일 수 있습니다.'})
    if norm(e.get('after')) and norm(e['after']) in norm(e['title']) and not e.get('title_checked'):
        out.append({'kind':'title','text':'항목명과 내용이 같거나 내용이 항목명을 되풀이합니다. 값이 빠졌거나 문장이 통째로 항목명이 된 것일 수 있습니다.'})
    if e.get('ai_kind'):out.append({'kind':'scope','text':'AI가 이 항목을 요구·사양·납기가 아닌 "'+e['ai_kind']+'"(으)로 봤습니다. 변경이력에 둘 내용인지 확인해 주세요.'})
    mine=value_units(e.get('before'),e.get('after'));others=set()
    for o in siblings:
        if o is not e and o.get('id')!=e.get('id'):others|=value_units(o.get('before'),o.get('after'))
    if mine and others and not(mine&others):out.append({'kind':'unit','text':'같은 항목의 다른 기록과 단위가 다릅니다('+', '.join(sorted(mine))+' ↔ '+', '.join(sorted(others))+'). 다른 대상의 값일 수 있습니다.'})
    return out
def attach_checks(events,quote_of):
    """같은 프로젝트·구분·이름끼리 묶어 각 기록에 checks를 붙인다."""
    groups={}
    for e in events:
        if e.get('review_state')!='제외':groups.setdefault((e['project_id'],e['category'],norm(e['title'])),[]).append(e)
    for e in events:
        e['checks']=[] if e.get('review_state')=='제외' else event_checks(e,quote_of(e),groups.get((e['project_id'],e['category'],norm(e['title'])),[]))
RETITLE_PROMPT=("회의록 문장과 거기서 뽑은 값이 주어진다. 그 값이 무엇에 대한 값인지 대상 이름을 짧게(2~12자) 답한다.\n"
 "이름은 문장에 실제로 나온 낱말로 짓는다. existing_titles에 같은 대상이 있으면 그 이름을 그대로 쓴다. 문장에 없는 대상을 지어내지 않는다.")
def retitle(e,existing):
    """의심 표시가 붙은 항목 하나만 AI에 다시 물어 이름을 받는다. 서버가 없거나 답이 근거 문장과 맞지 않으면 None."""
    from work.v17 import llm
    if not llm.available():return None
    schema={'type':'object','properties':{'title':{'type':'string'}},'required':['title'],'additionalProperties':False}
    user=json.dumps({'sentences':e.get('quotes') or [],'value':((e.get('before')+' → ') if e.get('before') else '')+e['after'],'wrong_title':e['title'],'existing_titles':[t for t in existing if norm(t)!=norm(e['title'])][:30]},ensure_ascii=False)
    try:
        raw,_=llm.chat([{'role':'system','content':RETITLE_PROMPT},{'role':'user','content':user}],60,schema=schema)
        new=' '.join(str(json.loads(raw[raw.find('{'):raw.rfind('}')+1]).get('title') or '').split())[:40]
    except Exception:return None
    if len(new)<2 or norm(new)==norm(e['title']):return None
    return new if title_in_text(new,' '.join(e.get('quotes') or [])) else None
ITEM_KINDS=['고객 요구','장비 사양','납기 조건','사내 계획','기타']
KIND_PROMPT=("회의록 문장과 거기서 뽑은 항목 하나가 주어진다. 이 항목이 무엇에 대한 것인지 하나만 고른다.\n"
 "- 고객 요구: 고객이 요청했거나 고객과 합의한 내용\n- 장비 사양: 납품할 장비의 사양 값이나 구성\n- 납기 조건: 출하일·납기·선적·포장 같은 납품 조건\n"
 "- 사내 계획: 회사 내부에서 일을 수행하기 위한 인원·기간·순서·준비 계획\n- 기타: 위 어느 것도 아님")
def item_kind(e):
    """뽑힌 항목 하나가 요구·사양·납기에 해당하는지 AI에 따로 묻는다(좁은 질문 하나). 서버가 없거나 실패하면 None."""
    from work.v17 import llm
    if not llm.available():return None
    schema={'type':'object','properties':{'kind':{'type':'string','enum':ITEM_KINDS}},'required':['kind'],'additionalProperties':False}
    user=json.dumps({'sentences':e.get('quotes') or [],'item':{'title':e['title'],'content':((e.get('before')+' → ') if e.get('before') else '')+e['after'],'requested_by':e.get('requested_by') or ''}},ensure_ascii=False)
    try:
        raw,_=llm.chat([{'role':'system','content':KIND_PROMPT},{'role':'user','content':user}],30,schema=schema)
        kind=json.loads(raw[raw.find('{'):raw.rfind('}')+1]).get('kind')
    except Exception:return None
    return kind if kind in ITEM_KINDS else None
def screen_proposals(w,m,proposals):
    """분석 직후 점검: 이름·단위가 의심스러운 항목만 AI에 다시 물어 이름을 고친다. 고쳐도 의심이 남으면 표시가 그대로 남는다."""
    with w.connect() as c:
        prior=[e for e in w.all_records(c,'change_event') if e['project_id']==m['project_id'] and e['meeting_id']!=m['id'] and not e.get('superseded_by_revision') and e.get('review_state')!='제외']
    fixed=0
    for e in proposals:
        same=lambda title:[o for o in prior+proposals if o is not e and o['category']==e['category'] and norm(o['title'])==norm(title)]
        if not event_checks(e,e.get('quotes') or [],same(e['title'])):continue
        new=retitle(e,list(dict.fromkeys(o['title'] for o in prior+proposals if o['category']==e['category'])))
        if not new:continue
        trial={**e,'title':new}
        if any(x['kind'] in ('unit','shape') for x in event_checks(trial,e.get('quotes') or [],same(new))):continue
        e.update(retitled_from=e['title'],title=new,topic_id=None);fixed+=1
    # 사내 작업 계획은 구분한다. 새로운 주제라는 이유만으로 원문에 있는 기록을 버리지 않는다.
    kept=[];dropped=0;dropped_items=[]
    for e in proposals:
        kind=item_kind(e)
        if kind in ('사내 계획','기타'):
            # 요청자 없는 사내 계획만 제외한다. 기타 주제와 합의·보류·철회는 보존한다.
            if kind=='사내 계획' and not e.get('requested_by') and e.get('business_state')=='요청':
                dropped+=1;dropped_items.append({'title':e['title'],'after':e['after'][:160],'kind':kind});continue
            e['ai_kind']=kind
        kept.append(e)
    proposals[:]=kept
    return {'retitled':fixed,'screened_out':dropped,'screened_items':dropped_items[:20]}

def topic_key(e):
    """v3\uc5d0\uc11c \ud55c \uac74\uc744 \uac00\ub9ac\ud0a4\ub294 \uac12. \uae30\uc874 topic_id\uac00 \uc5c6\uc73c\uba74 \uad6c\ubd84+\uc81c\ubaa9\uc73c\ub85c \ub9cc\ub4e0\ub2e4."""
    return e.get('topic_id') or 'auto-'+hashlib.sha1((e['category']+norm(e['title'])).encode()).hexdigest()[:14]

def suggest_links(proposals,topics):
    """\uc774\ub984\uc774 \uacb9\uce58\ub294 \uae30\uc874 \ud56d\ubaa9\uc744 '\ucd94\ucc9c'\ub9cc \ud55c\ub2e4(\uaddc\uce59 \uae30\ubc18, AI \uc544\ub2d8). \uc2e4\uc81c \uc5f0\uacb0\uc740 \uc0ac\ub78c\uc774 \ud655\uc778\ud560 \ub54c\ub9cc \ubc18\uc601\ub41c\ub2e4."""
    from work.v17.changes import suggest_topic
    for e in proposals:
        if e.get('topic_id'):continue
        hit=suggest_topic(e['title'],[t for t in topics if t.get('category')==e['category']])
        if hit:e.update(suggested_topic_id=hit['id'],suggested_topic_title=hit['title'])

def confirm_v3(w,c,item,actor,target=None,known=()):
    """\uc0ac\ub78c\uc774 \ud655\uc778\ud55c \ud56d\ubaa9\ub9cc \uc774\ub825\uc5d0 \ubc18\uc601\ud55c\ub2e4.
    \uc5f0\uacb0 \ub300\uc0c1\uc744 \uace0\ub974\uba74 \uadf8 \ud56d\ubaa9\uacfc \uac19\uc740 \uac74\uc73c\ub85c \ubb36\uace0, \uac19\uc740 \uc0ac\uc591\uc774 \ub2e4\ub978 \uc774\ub984\uc73c\ub85c \uc801\ud614\uc73c\uba74 \uc774\ub984\uc744 \ub9de\ucd94\uace0 \ud68c\uc758\ub85d \ud45c\uae30\ub294 \ub530\ub85c \ub0a8\uae34\ub2e4."""
    from work.v17.changes import suggest_topic
    def rename(title):
        if norm(title)==norm(item['title']):return
        item['original_title']=item.get('original_title') or item['title'];item['title']=title
    if target:
        item['topic_id']=topic_key(target);rename(target['title'])
    else:
        item['topic_id']=item.get('topic_id') or topic_key(item)
        names=[{'title':t,'category':item['category']} for t in dict.fromkeys([e['title'] for e in known if topic_key(e)==item['topic_id']])]
        hit=suggest_topic(item['title'],names)
        if hit:rename(hit['title'])
    item.update(review_state='\ud655\uc778\ub428',confirmed_by=actor['id'],confirmed_at=w.now(),suggested_topic_id=None,suggested_topic_title=None)

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
                # 연결 대상은 이 회의보다 앞선 회의의 항목뿐이다. 뒤 회의나 이 회의 자신의 예전 결과를 넘기면 모델이 엉뚱한 이름에 맞춘다.
                dates={x['id']:x.get('date') or '' for x in w.all_records(c,'meeting')}
                revision=m['revision'];m.update(analysis_state='running',analysis_phase='notes',analysis_started_at=stamp(),analysis_loading_seconds=0);w.save(c,'meeting',m)
                topics=[{'id':e.get('topic_id') or 'auto-'+hashlib.sha1((e['category']+norm(e['title'])).encode()).hexdigest()[:14],'title':e['title'],'category':e['category']} for e in w.all_records(c,'change_event') if e['project_id']==m['project_id'] and e['meeting_id']!=mid and not e.get('superseded_by_revision') and e.get('review_state')!='제외' and dates.get(e['meeting_id'],'')<(m.get('date') or '9999')]
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
            groups=chunks(m['lines']);bundle={'summary':[],'decisions':[],'candidates':[]};change_items=[];dropped_notes=0;metrics={'chunks':len(groups),'queue_seconds':round(acquired-started,2),'passes':[]}
            for i,group in enumerate(groups):
                # 추출할 때는 앞 회의의 항목 이름을 넘기지 않는다. 이름을 주면 모델이 엉뚱한 문장에 그 이름을 붙인다.
                # 기존 항목과의 연결은 추출 뒤에 이름 비교(suggest_links)와 사람의 확인으로 한다.
                notes,found,measure=extract(w,group,[],on_phase=report_phase)
                dropped_notes+=notes.get('dropped_notes',0)
                for key in ('summary','decisions'):bundle[key].extend(notes.get(key,[]))
                for item in notes.get('items',[]):bundle['candidates'].append({**item,'id':w.uid(),'state':'draft','note':'','reviewer_id':None})
                metrics['model']=measure.get('model');metrics['passes'].append(measure)
                with w.connect() as c:
                    current=w.read(c,'meeting',mid)
                    if current.get('v3_job')!=job or current.get('deleted_at') or current['revision']!=revision:return
                    current.update(v3_bundle=deepcopy(bundle),analysis_phase=f'combined:{i+1}/{len(groups)}');w.save(c,'meeting',current)
                change_items.extend(found['items'])
            # 항목이 많아도 회의록 전체를 실패시키지 않는다. 상한까지 반영하고 몇 건이 빠졌는지 남긴다.
            from work.v17.changes import MAX_ITEMS
            dropped_changes=max(0,len(change_items)-MAX_ITEMS);change_items=change_items[:MAX_ITEMS]
            proposals=make_proposals(w,m,change_items,topics)
            try:metrics.update(screen_proposals(w,m,proposals))
            except Exception:metrics['retitled']=0
            suggest_links(proposals,topics)
            for e in proposals:
                if e['before'] and (norm(e['before'])==norm(e['after']) or norm(e['before']) in norm(e['after'])):e['before']=''
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
                seen=set();kept=[];nums=lambda x:set(re.findall(r'\d+(?:[.,]\d+)*',x['before']+' '+x['after']))
                for e in proposals:
                    if (e['category'],norm(e['title']),tuple(sorted(e['evidence']))) in corrected_sources:continue
                    key=(norm(e['title']),e['business_state'],e['after'])
                    if key in seen:continue
                    # 같은 대상·상태·근거에 값도 같으면 모델이 되풀이한 것이다. 하나만 남긴다.
                    if any(norm(k['title'])==norm(e['title']) and k['business_state']==e['business_state'] and set(k['evidence'])&set(e['evidence']) and (nums(k)<=nums(e) or nums(e)<=nums(k)) for k in kept):continue
                    # 이름만 다르고 내용과 근거가 같은 항목도 되풀이다(이미 사람이 확인한 기록 포함).
                    same=[k for k in kept+[o for o in w.all_records(c,'change_event') if o['meeting_id']==mid and not o.get('superseded_by_revision') and o.get('review_state')!='제외']]
                    if any(norm(k['after'])==norm(e['after']) and set(k['evidence'])==set(e['evidence']) for k in same):continue
                    seen.add(key);kept.append(e);w.save(c,'change_event',e)
                metrics.update(dropped_notes=dropped_notes,dropped_changes=dropped_changes,seconds=round(time.perf_counter()-started,2),analysis_seconds=round(time.perf_counter()-acquired,2),source_chars=len(current['source']),source_revision=revision,
                               cache_hit=bool(metrics['passes']) and all(p.get('cache_hit') for p in metrics['passes']))
                current.update(v3_bundle=bundle,reviewed_bundle=bundle,overview={k:bundle[k] for k in ('summary','decisions')},candidates=bundle['candidates'],ai_snapshot={'bundle':deepcopy(bundle),'created_at':w.now(),'model':metrics.get('model')},analysis_state='ready',analysis_phase='complete',analysis_stale=False,error='',metrics=metrics,analysis_finished_at=w.now(),change_scan_state='ready',change_scan_revision=revision,change_scan_extraction_version=EXTRACTION_VERSION,version=current['version']+1)
                w.save(c,'meeting',current)
            # 분석이 끝나면 같은 AI로 이 회의의 진행 단계도 판단해 둔다. 실패해도 분석 결과에는 영향 없음.
            try:
                with w.connect() as c:
                    allm=[x for x in w.all_records(c,'meeting') if x['project_id']==current['project_id'] and not x.get('deleted_at') and x['id']!=mid and (x.get('date') or '')<=(current.get('date') or '')]
                prev=sorted(allm,key=lambda x:(x.get('date') or '',x.get('created_at') or ''))
                prev=(prev[-1].get('stage_ai') or {}).get('stage') if prev else None
                a=judge_stage(current,prev)
                if a:
                    with w.connect() as c:
                        c.execute('BEGIN IMMEDIATE');cur=w.read(c,'meeting',mid)
                        if cur.get('revision')==revision:cur['stage_ai']=a;cur['version']=cur['version']+1;w.save(c,'meeting',cur)
            except Exception:pass
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
class StageSet(Strict):
    stage:str=Field(default='',max_length=40)
class ChangeReview(Strict):
    version:int
    action:str
    link_to:str=Field(default='',max_length=100)
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
            renamed=bool(item.get('title_checked')) or norm(item['title'])!=norm(body.title)
            item.update(payload,topic_id=topic_id,version=item['version']+1,human_edited=True,title_checked=renamed,review_state='검토 전',updated_at=w.now(),updated_by=actor['id'])
            w.save(c,'change_event',item)
        return {**item,'context':change_context(item['quotes'],item['after'])}
    @r.post('/changes/{cid}/review')
    def review_change(cid,body:ChangeReview,actor=Depends(w.user)):
        """\ub4f1\ub85d\ub41c \ub0b4\uc6a9\uc744 \uc0ac\ub78c\uc774 \uc6d0\ubb38\uacfc \ub300\uc870\ud574 \ud655\uc778\u00b7\uc81c\uc678\ud558\uace0, \uac19\uc740 \uac74\uc73c\ub85c \uc5f0\uacb0\ud55c\ub2e4."""
        if body.action not in ('\ud655\uc778','\uc81c\uc678','\uac80\ud1a0 \uc804'):raise HTTPException(422,'\ud655\uc778\u00b7\uc81c\uc678\u00b7\uac80\ud1a0 \uc804 \uc911\uc5d0\uc11c \uace8\ub77c \uc8fc\uc138\uc694.')
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE');item=w.read(c,'change_event',cid)
            w.project(c,item['project_id'],actor,True);w.version(item,body.version)
            m=w.read(c,'meeting',item['meeting_id']);active(m)
            if item.get('superseded_by_revision') or item['source_revision']!=m['revision'] or m.get('analysis_stale'):
                raise HTTPException(409,'\uc6d0\ubb38 \ub610\ub294 \ubcc0\uacbd \uae30\ub85d\uc774 \ubc14\ub01c\uc5c8\uc2b5\ub2c8\ub2e4. \ucd5c\uc2e0 \ubcc0\uacbd\uc774\ub825\uc744 \ub2e4\uc2dc \uc5f4\uc5b4 \uc8fc\uc138\uc694.')
            if m.get('analysis_state') in ('queued','running'):raise HTTPException(409,'\ud68c\uc758\ub85d \ubd84\uc11d\uc774 \ub05d\ub09c \ub4a4\uc5d0 \ud655\uc778\ud574 \uc8fc\uc138\uc694.')
            others=[e for e in w.all_records(c,'change_event') if e['project_id']==item['project_id'] and e['id']!=cid and not e.get('superseded_by_revision') and e.get('review_state')!='\uc81c\uc678']
            if body.action=='\ud655\uc778':
                target=None
                if body.link_to:
                    target=next((e for e in others if e['id']==body.link_to),None)
                    if not target:raise HTTPException(422,'\uc5f0\uacb0\ud560 \ud56d\ubaa9\uc744 \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4. \ubaa9\ub85d\uc744 \uc0c8\ub85c \uace0\uce5c \ub4a4 \ub2e4\uc2dc \uc120\ud0dd\ud574 \uc8fc\uc138\uc694.')
                    if target['category']!=item['category']:raise HTTPException(422,'\uac19\uc740 \uad6c\ubd84\uc758 \ud56d\ubaa9\ub07c\ub9ac\ub9cc \uc5f0\uacb0\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.')
                confirm_v3(w,c,item,actor,target,[e for e in others if e.get('review_state')=='\ud655\uc778\ub428'])
            elif body.action=='\uc81c\uc678':item.update(review_state='\uc81c\uc678',confirmed_by=actor['id'],confirmed_at=w.now())
            else:item.update(review_state='\uac80\ud1a0 \uc804',confirmed_by=None,confirmed_at=None)
            item.update(version=item['version']+1,human_edited=True,updated_at=w.now(),updated_by=actor['id'])
            w.save(c,'change_event',item)
        return {**item,'context':change_context(item['quotes'],item['after'])}
    @r.get('/meetings/{mid}/line-boxes')
    def line_boxes(mid,actor=Depends(w.user)):
        with w.connect() as c:
            m=w.read(c,'meeting',mid);w.project(c,m['project_id'],actor)
        path=m.get('pdf')
        if not path or not Path(path).is_file():return {}
        try:return locate_lines(path,m.get('lines') or [])
        except Exception:return {}
    @r.get('/projects/{pid}/flow')
    def project_flow(pid,actor=Depends(w.user)):
        """프로젝트 흐름 화면용: 회의마다 추정 단계, 최근 추정과 그 근거, PM이 지정한 단계."""
        with w.connect() as c:
            p=w.project(c,pid,actor)
            ms=sorted([m for m in w.all_records(c,'meeting') if m['project_id']==pid and not m.get('deleted_at')],key=lambda m:(m.get('date') or '',m.get('created_at') or ''))
        per={};detail={};guess=None
        for m in ms:
            d=stage_of(m);per[m['id']]=d['stage'];detail[m['id']]=d
            if d['stage']:guess={**infer_stage(m),**d}
        if not guess and ms:guess=infer_stage(ms[-1])
        from work.v17 import llm
        return {'stages':STAGES,'manual':p.get('stage_manual') or None,'manual_by':p.get('stage_set_by'),'manual_at':p.get('stage_set_at'),'guess':guess,'per_meeting':per,'per_detail':detail,'ai_ready':llm.stage_available(),'rejudge':True,'build':'89','ai_missing':sum(1 for m in ms if detail[m['id']]['source']=='rule')}
    @r.post('/meetings/{mid}/stage')
    def set_meeting_stage(mid,body:StageSet,actor=Depends(w.user)):
        """PM이 회의 하나의 단계를 직접 고친다. 빈 값이면 자동 판단으로 되돌린다."""
        if body.stage and body.stage not in STAGES:raise HTTPException(422,'단계를 다시 골라 주세요.')
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE');m=w.read(c,'meeting',mid);p=w.project(c,m['project_id'],actor)
            if p.get('pm')!=actor['id']:raise HTTPException(403,'PM만 단계를 지정할 수 있습니다.')
            m.update(stage_manual=body.stage or None,stage_manual_by=actor['id'],stage_manual_at=w.now());w.save(c,'meeting',m)
        return {'ok':True,'stage':m['stage_manual']}
    @r.post('/meetings/{mid}/stage-ai')
    def stage_ai_one(mid,actor=Depends(w.user)):
        """회의 하나의 단계를 AI로 다시 판단한다. PM이 직접 지정한 단계는 풀고 AI 판단으로 바꾼다."""
        from work.v17 import llm
        if not llm.stage_available():raise HTTPException(503,'AI 실행 환경을 확인해 주세요. 실행.cmd로 서비스를 시작한 뒤 다시 시도해 주세요.')
        with w.connect() as c:
            m=w.read(c,'meeting',mid);w.project(c,m['project_id'],actor,True);active(m)
            ms=sorted([x for x in w.all_records(c,'meeting') if x['project_id']==m['project_id'] and not x.get('deleted_at')],key=lambda x:(x.get('date') or '',x.get('created_at') or ''))
        i=next((k for k,x in enumerate(ms) if x['id']==mid),0)
        prev=stage_of(ms[i-1])['stage'] if i>0 else None
        with w.AI_LOCK:a=judge_stage(m,prev)
        if not a:raise HTTPException(502,'AI가 단계를 판단하지 못했습니다. 잠시 뒤 다시 눌러 주세요.')
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE');cur=w.read(c,'meeting',mid)
            active(cur)
            if cur.get('revision')!=m.get('revision'):raise HTTPException(409,'원문이 변경되었습니다. 최신 회의록으로 다시 판단해 주세요.')
            cur['stage_ai']=a;cur['stage_manual']=None;w.save(c,'meeting',cur)
        return {'ok':True,'stage':a['stage']}
    @r.post('/projects/{pid}/stage-ai')
    def stage_ai(pid,actor=Depends(w.user)):
        """AI 판단이 없거나 원문이 바뀐 회의만 날짜 순으로 단계를 판단해 저장한다."""
        from work.v17 import llm
        if not llm.stage_available():raise HTTPException(503,'AI 실행 환경을 확인해 주세요. 실행.cmd로 서비스를 시작한 뒤 다시 시도해 주세요.')
        with w.connect() as c:
            w.project(c,pid,actor,True)
            ms=sorted([m for m in w.all_records(c,'meeting') if m['project_id']==pid and not m.get('deleted_at')],key=lambda m:(m.get('date') or '',m.get('created_at') or ''))
        done=0;prev=None
        with w.AI_LOCK:
            for m in ms:
                a=m.get('stage_ai')
                if not(a and a.get('revision')==m.get('revision') and a.get('v')==stage_version()):
                    a=judge_stage(m,prev)
                    if a:
                        with w.connect() as c:
                            c.execute('BEGIN IMMEDIATE');cur=w.read(c,'meeting',m['id'])
                            if cur.get('revision')==m.get('revision'):cur['stage_ai']=a;w.save(c,'meeting',cur);done+=1
                if a:prev=a['stage']
        return {'ok':True,'judged':done}
    @r.post('/projects/{pid}/stage')
    def set_stage(pid,body:StageSet,actor=Depends(w.user)):
        if body.stage and body.stage not in STAGES:raise HTTPException(422,'단계를 다시 골라 주세요.')
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE');p=w.project(c,pid,actor)
            if p.get('pm')!=actor['id']:raise HTTPException(403,'PM만 단계를 지정할 수 있습니다.')
            p.update(stage_manual=body.stage or None,stage_set_by=actor['id'],stage_set_at=w.now());w.save(c,'project',p)
        return {'ok':True,'manual':p['stage_manual']}
    @r.get('/meetings/{mid}/change-boxes')
    def change_boxes(mid,actor=Depends(w.user)):
        with w.connect() as c:
            m=w.read(c,'meeting',mid);w.project(c,m['project_id'],actor)
            events=[e for e in w.all_records(c,'change_event') if e['meeting_id']==mid and not e.get('superseded_by_revision') and e.get('source_revision')==m['revision']]
        path=m.get('pdf') if m.get('pdf') and Path(m['pdf']).is_file() else None
        try:return locate_events(path,m.get('lines') or [],events)
        except Exception:return {}
    def public_import(d,ps,context=''):
        return {k:d.get(k) for k in ('id','filename','title','meeting_date','warnings')}|{'declared_project':' '.join(str(d.get('declared_project') or '').split())[:120]}|match_project(d['filename'],d.get('declared_project',''),d['source'],ps,context)
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
                    register_revision(m);w.save(c,'meeting',m);d['meeting_id']=mid;d['preview_finished']=True;w.save(c,'import',d);jobs.append((mid,job,bool(d.get('docx'))));result.append({'id':mid,'duplicate':False})
                except HTTPException as exc:errors.append({'id':item.id,'error':str(exc.detail)})
        for mid,job,word in jobs:
            w.POOL.submit(run_analysis,w,mid,job)
            if word:w.PREVIEW_POOL.submit(w.convert_background,mid)
        return {'registered':result,'errors':errors}
    @r.post('/meetings/{mid}/dry-run')
    def dry_run(mid,use_topics:int=0,actor=Depends(w.user)):
        """분석을 저장 없이 한 번 돌려 결과만 돌려준다(품질 측정용). 회의록과 변경 기록은 바뀌지 않는다."""
        from work.v3.fast_ai import extract
        from work.v17.changes import make_proposals,MAX_ITEMS
        with w.connect() as c:
            m=w.read(c,'meeting',mid);w.project(c,m['project_id'],actor)
            dates={x['id']:x.get('date') or '' for x in w.all_records(c,'meeting')}
            topics=[{'id':e.get('topic_id') or 'auto-'+hashlib.sha1((e['category']+norm(e['title'])).encode()).hexdigest()[:14],'title':e['title'],'category':e['category']} for e in w.all_records(c,'change_event') if e['project_id']==m['project_id'] and e['meeting_id']!=mid and not e.get('superseded_by_revision') and e.get('review_state')!='제외' and dates.get(e['meeting_id'],'')<(m.get('date') or '9999')] if use_topics else []
        started=time.perf_counter();items=[];traces=[];pipe=''
        with w.AI_LOCK:
            for group in chunks(m['lines']):
                notes,found,measure=extract(w,group,list({x['id']:x for x in topics}.values())[:30])
                items.extend(found['items']);traces.append(measure.get('trace'));pipe=measure.get('pipeline')
            proposals=make_proposals(w,m,items[:MAX_ITEMS],topics)
            try:info=screen_proposals(w,m,proposals)
            except Exception as exc:info={'error':str(exc)[:200]}
        seen=set();out=[]
        for e in proposals:
            key=(norm(e['title']),e['business_state'],norm(e['after']))
            if key in seen:continue
            seen.add(key);out.append({k:e.get(k) for k in ('title','category','before','after','business_state','requested_by','evidence','retitled_from','ai_kind','topic_id')}|{'checks':[x['kind'] for x in event_checks(e,e.get('quotes') or [],[o for o in proposals if o is not e and o['category']==e['category'] and norm(o['title'])==norm(e['title'])])]})
        return {'seconds':round(time.perf_counter()-started,1),'pipeline':pipe,'topics':len(topics),'items':out,'screen':info,'trace':traces}
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
            # 회의록별 최신 고객 승인 요청(표시용 상태)
            current=w.now();approvals=latest_by_meeting(x for x in w.all_records(c,'approval_request') if x['meeting_id'] in by)
            es=[]
            for e in w.all_records(c,'change_event'):
                m=by.get(e['meeting_id'])
                if not m or e.get('superseded_by_revision') or e.get('source_revision')!=m['revision'] or m.get('analysis_stale'):continue
                refs={x['id']:x['text'] for x in m['lines']}
                quotes=[refs[x] for x in e['evidence'] if x in refs]
                es.append({**e,'quotes':quotes,'context':change_context(quotes,e['after']),'meeting_title':m['title'],'meeting_date':m.get('date','')})
            attach_checks(es,lambda e:e['quotes'])
            for e in es:
                exact=source_wording(e,e['quotes'])
                if exact:e['after_source']=exact
            meetings=[{k:m.get(k) for k in ('id','project_id','title','date','author','analysis_state','analysis_phase','analysis_stale','error','version','revision','created_at','warnings','source_type','filename')}|{'points':note_points(m),'metrics':m.get('metrics',{}),'progress':progress.get(m['id']),'approval':approval_summary(approvals[m['id']],current,m['revision']) if m['id'] in approvals else None} for m in ms]
            archived=[{k:m.get(k) for k in ('id','title','project_id','deleted_at')} for m in w.all_records(c,'meeting') if m['project_id'] in ids and m.get('deleted_at') and actor['id'] in (m['author'],next(p['pm'] for p in ps if p['id']==m['project_id']))]
            return {'user':actor,'people':w.all_records(c,'person'),'projects':ps,'meetings':meetings,'archived':archived,'changes':es,'calendar':calendar_events(ms,es),'requirements':build_requirements(w,c,actor),'recent_batch':recent_batch([m for m in all_meetings if m['project_id'] in ids],actor['id']),'today':w.now()[:10],'can_create_project':w.can_create_project(c,actor),'version':'6.0.0'}
    @r.get('/search')
    def search(q:str=Query(default='',max_length=120),project_id:str='',actor=Depends(w.user)):
        terms=[norm(x) for x in q.split() if norm(x)]
        if not terms:return {'items':[],'total':0}
        with w.connect() as c:
            ps=[w.project(c,project_id,actor)] if project_id else [p for p in w.all_records(c,'project') if actor['id'] in p['members']]
            projects={p['id']:p for p in ps};items=[]
            from work.v3.meeting_review import review_pending
            pending=review_pending(w,c)
            for m in w.all_records(c,'meeting'):
                if m['project_id'] not in projects or m.get('deleted_at') or m['id'] in pending:continue
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
