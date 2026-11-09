"""Project schedule: eight delivery phases, milestones, schedule items, Excel import/export and a schedule change ledger.

Schedule items are plain planning rows (not work tasks). Work tasks with a start/due date are shown on the same
Gantt chart under their phase; a task's phase is the only task field this module writes.
"""
from __future__ import annotations
import io,re
from datetime import date,datetime,timedelta
from fastapi import APIRouter,Depends,HTTPException,UploadFile,File,Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel,ConfigDict,Field

PHASES=['수주','설계 및 변경','구매','제작','검수','납품','현장','종료']
PHASE_COLORS={'수주':'#6b7a8f','설계 및 변경':'#2f6db5','구매':'#d08a2e','제작':'#b55a3c','검수':'#2a9d8f','납품':'#7b61b8','현장':'#4f8f3a','종료':'#3b4a5c'}
# Weight of each phase when default milestone dates are spread over the project period.
PHASE_WEIGHTS={'수주':4,'설계 및 변경':20,'구매':14,'제작':20,'검수':12,'납품':5,'현장':17,'종료':8}
PHASE_ALIASES={'수주':'수주','계약':'수주','착수':'수주','영업':'수주',
 '설계':'설계 및 변경','설계및변경':'설계 및 변경','설계·변경':'설계 및 변경','설계/변경':'설계 및 변경','설계변경':'설계 및 변경','변경':'설계 및 변경','design':'설계 및 변경',
 '구매':'구매','발주':'구매','자재':'구매','purchase':'구매',
 '제작':'제작','조립':'제작','제작조립':'제작','제작·조립':'제작','가공':'제작','fabrication':'제작',
 '검수':'검수','검사':'검수','시운전':'검수','fat':'검수','사내시운전':'검수','inspection':'검수',
 '납품':'납품','출하':'납품','운송':'납품','shipping':'납품',
 '현장':'현장','설치':'현장','sat':'현장','현장설치':'현장','site':'현장',
 '종료':'종료','인수':'종료','완료':'종료','최종인수':'종료','close':'종료'}
# (phase, title, key milestone, completion criterion)
DEFAULT_MILESTONES=[
 ('수주','계약 체결·프로젝트 착수',False,'계약 범위, 납기, 기본 사양 확정'),
 ('설계 및 변경','고객 사양 확정',False,'요구사항과 성능 기준 합의'),
 ('설계 및 변경','설계 검토 완료',False,'기본·상세 설계 검토 완료'),
 ('설계 및 변경','승인도 승인',True,'고객이 도면 승인'),
 ('구매','핵심 부품 발주',False,'롤, 모터, 감속기 등 주요 품목 발주'),
 ('구매','핵심 부품 입고',True,'주요 부품 입고와 입고 검사 완료'),
 ('제작','제작·조립 완료',False,'기구, 전장 조립 완료'),
 ('검수','사내 시운전 완료',False,'자체 동작과 성능 확인'),
 ('검수','FAT 완료',True,'공장에서 고객 입회 검수 통과'),
 ('납품','출하',True,'장비 포장과 운송 시작'),
 ('현장','설치·시운전 완료',False,'고객 공장에서 설치와 시운전 완료'),
 ('현장','SAT 완료',True,'고객 현장에서 성능 검수 통과'),
 ('종료','최종 인수',False,'고객 인수와 프로젝트 종료'),
]
ITEM_KINDS=('마일스톤','항목')
EXCEL_HEADERS=['단계','구분','항목명','담당자','시작일','종료일','진행률','핵심','선행작업','비고']
HEADER_ALIASES={'단계':'단계','phase':'단계','공정':'단계','구분':'구분','종류':'구분','유형':'구분','type':'구분',
 '항목명':'항목명','항목':'항목명','업무명':'항목명','업무':'항목명','작업':'항목명','작업명':'항목명','마일스톤':'항목명','내용':'항목명','title':'항목명','task':'항목명',
 '담당자':'담당자','담당':'담당자','owner':'담당자','책임자':'담당자',
 '시작일':'시작일','시작':'시작일','착수일':'시작일','start':'시작일','시작예정일':'시작일',
 '종료일':'종료일','종료':'종료일','완료일':'종료일','기한':'종료일','납기':'종료일','end':'종료일','완료예정일':'종료일','완료목표':'종료일',
 '진행률':'진행률','진척률':'진행률','진행':'진행률','progress':'진행률','%':'진행률',
 '핵심':'핵심','핵심마일스톤':'핵심','key':'핵심','중요':'핵심',
 '선행작업':'선행작업','선행':'선행작업','의존':'선행작업','depends':'선행작업',
 '비고':'비고','메모':'비고','note':'비고','완료기준':'비고','설명':'비고'}
PROJECT_FIELD_ALIASES={'프로젝트번호':'code','프로젝트 번호':'code','번호':'code','code':'code','프로젝트명':'name','프로젝트 이름':'name','name':'name',
 '고객사':'customer','고객':'customer','customer':'customer','장비':'equipment','장비·호기':'equipment','장비/호기':'equipment','대표장비':'equipment','equipment':'equipment',
 '착수일':'start','시작일':'start','start':'start','납기일':'end','납기':'end','종료일':'end','end':'end'}

class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class ItemInput(Strict):
 project_id:str
 kind:str='항목'
 phase:str
 title:str=Field(min_length=1,max_length=200)
 owner_id:str|None=None
 owner_name:str=Field(default='',max_length=80)
 start:str|None=None
 end:str|None=None
 progress:int=Field(default=0,ge=0,le=100)
 key:bool=False
 depends_on:str=Field(default='',max_length=200)
 note:str=Field(default='',max_length=1000)
class ItemEdit(Strict):
 version:int
 kind:str|None=None
 phase:str|None=None
 title:str|None=Field(default=None,min_length=1,max_length=200)
 owner_id:str|None=None
 owner_name:str|None=Field(default=None,max_length=80)
 start:str|None=None
 end:str|None=None
 progress:int|None=Field(default=None,ge=0,le=100)
 key:bool|None=None
 depends_on:str|None=Field(default=None,max_length=200)
 note:str|None=Field(default=None,max_length=1000)
 reason:str=Field(default='',max_length=500)
class ItemDelete(Strict):version:int;reason:str=Field(default='',max_length=500)
class TaskPhase(Strict):version:int;phase:str|None=None
class ProjectInfo(Strict):
 code:str|None=Field(default=None,max_length=60)
 customer:str|None=Field(default=None,max_length=120)
 equipment:str|None=Field(default=None,max_length=120)
 start:str|None=None
 end:str|None=None
 reason:str=Field(default='',max_length=500)

def norm_phase(value):
 if value is None:return None
 s=re.sub(r'[\s·/&및]+','',str(value)).strip().lower()
 if not s:return None
 if str(value).strip() in PHASES:return str(value).strip()
 if s in PHASE_ALIASES:return PHASE_ALIASES[s]
 for alias,phase in PHASE_ALIASES.items():
  if alias in s:return phase
 return None
def parse_day(value):
 """Accept Excel dates, datetimes, and strings like 2026-11-13, 2026.11.13, 2026/11/13, 11/13 (current year)."""
 if value is None or value=='':return None
 if isinstance(value,datetime):return value.date().isoformat()
 if isinstance(value,date):return value.isoformat()
 if isinstance(value,(int,float)):
  try:return (date(1899,12,30)+timedelta(days=int(value))).isoformat()
  except (OverflowError,ValueError):return None
 s=str(value).strip()
 m=re.match(r'^(20\d{2})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})일?$',s)
 if m:
  try:return date(int(m[1]),int(m[2]),int(m[3])).isoformat()
  except ValueError:return None
 m=re.match(r'^(\d{1,2})[-./월]\s*(\d{1,2})일?$',s)
 if m:
  try:return date(date.today().year,int(m[1]),int(m[2])).isoformat()
  except ValueError:return None
 return None
def parse_progress(value):
 if value is None or value=='':return 0
 if isinstance(value,(int,float)):
  v=float(value);v=v*100 if 0<v<=1 else v
  return max(0,min(100,int(round(v))))
 s=str(value).strip().replace('%','')
 try:v=float(s)
 except ValueError:return 0
 return max(0,min(100,int(round(v*100 if 0<v<=1 and '.' in s else v))))
def truthy(value):return str(value or '').strip().lower() in ('y','yes','o','●','★','true','1','핵심','예','v','√','✓')
def check_day(w,value,label):
 if value in (None,''):return None
 try:return w.due(value)
 except HTTPException:raise HTTPException(422,f'{label}은(는) YYYY-MM-DD 형식의 날짜여야 합니다.')
def item_status(it,today):
 if it.get('progress',0)>=100 or it.get('done_at'):return '완료'
 end=it.get('end') or it.get('start')
 if end and end<today:return '지연'
 if it.get('start') and it['start']<=today:return '진행중'
 return '예정'
def spread_dates(start,end):
 """Default milestone dates spread across the project period by phase weight; None when the period is unknown."""
 if not (start and end) or start>end:return {}
 s=date.fromisoformat(start);total=(date.fromisoformat(end)-s).days;weight=sum(PHASE_WEIGHTS.values());acc=0;out={}
 for phase in PHASES:
  acc+=PHASE_WEIGHTS[phase];out[phase]=(s+timedelta(days=round(total*acc/weight))).isoformat()
 return out
def phase_of_date(dates,phase,index,count):
 """Milestones inside a phase are spaced evenly up to the phase end date."""
 if phase not in dates:return None
 prev=PHASES.index(phase);start=date.fromisoformat(dates[PHASES[prev-1]]) if prev>0 else None;end=date.fromisoformat(dates[phase])
 if start is None or count<=1:return end.isoformat()
 return (start+timedelta(days=round((end-start).days*(index+1)/count))).isoformat()

def record_change(w,c,project_id,actor,source,target_type,target_id,title,phase,action,changes=None,note=''):
 w.save(c,'schedule_change',{'id':w.uid(),'project_id':project_id,'at':w.now(),'actor':actor,'source':source,'target_type':target_type,'target_id':target_id,'title':title,'phase':phase,'action':action,'changes':changes or {},'note':note})

def ensure_milestones(w,c,p,actor='system'):
 """Seed the default milestones once per project; dates are spread when the project period is known."""
 if p.get('milestones_seeded'):return False
 dates=spread_dates(p.get('start'),p.get('end'));stamp=w.now()
 counts={};index={}
 for phase,_,_,_ in DEFAULT_MILESTONES:counts[phase]=counts.get(phase,0)+1
 for phase,title,key,criterion in DEFAULT_MILESTONES:
  i=index.get(phase,0);index[phase]=i+1;day=phase_of_date(dates,phase,i,counts[phase])
  w.save(c,'schedule_item',{'id':w.uid(),'project_id':p['id'],'kind':'마일스톤','phase':phase,'title':title,'owner_id':None,'owner_name':'','start':day,'end':day,'progress':0,'key':key,'depends_on':'','note':criterion,'source':'기본','import_id':None,'version':1,'created_at':stamp,'updated_at':stamp,'created_by':actor,'done_at':None,'deleted_at':None})
 p['milestones_seeded']=True;w.save(c,'project',p);return True

def project_card(p,items,tasks,today):
 live=[x for x in items if not x.get('deleted_at')]
 ms=[x for x in live if x['kind']=='마일스톤']
 done=[x for x in ms if item_status(x,today)=='완료']
 # The current phase is the first phase that still has an unfinished milestone or item.
 current=next((ph for ph in PHASES if any(x['phase']==ph and item_status(x,today)!='완료' for x in live)),PHASES[-1] if live else None)
 dates=[d for x in live for d in (x.get('start'),x.get('end')) if d]+[t[k] for t in tasks for k in ('start','due') if t.get(k)]
 return {'id':p['id'],'code':p.get('code') or p['id'],'name':p['name'],'pm':p['pm'],'customer':p.get('customer',''),'equipment':p.get('equipment',''),'start':p.get('start') or (min(dates) if dates else None),'end':p.get('end') or (max(dates) if dates else None),'planned_start':p.get('start'),'planned_end':p.get('end'),'current_phase':current,'milestones_total':len(ms),'milestones_done':len(done),'late':sum(item_status(x,today)=='지연' for x in live),'members':p['members']}

def task_schedule_changes(t,project):
 """Schedule-relevant task events (start/due/phase changes and creation) rendered as change rows."""
 out=[]
 for e in t.get('events',[]):
  ch=e.get('changes') or {}
  picked={k:v for k,v in ch.items() if k in ('start','due','phase')}
  if e['action'] in ('직접 등록','업무 반영','확인사항 등록') and (t.get('start') or t.get('due')):
   out.append({'id':t['id']+':'+e['at'],'project_id':t['project_id'],'at':e['at'],'actor':e['actor'],'source':'업무','target_type':'업무','target_id':t['id'],'title':t['title'],'phase':t.get('phase'),'action':'업무 등록','changes':{'start':{'before':None,'after':t.get('start')},'due':{'before':None,'after':t.get('due')}},'note':''})
  elif picked:
   action='단계 변경' if set(picked)=={'phase'} else '기간 변경'
   out.append({'id':t['id']+':'+e['at'],'project_id':t['project_id'],'at':e['at'],'actor':e['actor'],'source':'업무','target_type':'업무','target_id':t['id'],'title':t['title'],'phase':t.get('phase'),'action':action,'changes':picked,'note':e.get('note','')})
 return out

def visible_projects(w,c,actor,project_id):
 ps=[p for p in w.all_records(c,'project') if actor['id'] in p['members']]
 if project_id:
  p=w.project(c,project_id,actor);ps=[p]
 return ps

def snapshot(w,c,actor,project_id,today):
 ps=visible_projects(w,c,actor,project_id);ids={p['id'] for p in ps}
 for p in ps:ensure_milestones(w,c,p)
 items=[x for x in w.all_records(c,'schedule_item') if x['project_id'] in ids and not x.get('deleted_at')]
 tasks=[t for t in w.all_records(c,'task') if t['project_id'] in ids and (t.get('start') or t.get('due'))]
 for x in items:x['status']=item_status(x,today)
 task_rows=[{'id':t['id'],'project_id':t['project_id'],'title':t['title'],'phase':t.get('phase'),'owner_id':t.get('owner_id') if t['kind']=='업무' else t.get('reviewer_id'),'start':t.get('start') or t.get('due'),'end':t.get('due') or t.get('start'),'status':t['status'],'kind':t['kind'],'version':t['version']} for t in tasks]
 changes=[x for x in w.all_records(c,'schedule_change') if x['project_id'] in ids]
 for t in [t for t in w.all_records(c,'task') if t['project_id'] in ids]:changes+=task_schedule_changes(t,None)
 changes.sort(key=lambda x:x['at'],reverse=True)
 by_project={p['id']:[x for x in items if x['project_id']==p['id']] for p in ps}
 cards=[project_card(p,by_project[p['id']],[t for t in tasks if t['project_id']==p['id']],today) for p in ps]
 phase_order={ph:i for i,ph in enumerate(PHASES)}
 items.sort(key=lambda x:(phase_order.get(x['phase'],99),x.get('start') or '9999',x['kind']!='마일스톤',x['title']))
 return {'phases':[{'name':ph,'color':PHASE_COLORS[ph]} for ph in PHASES],'projects':sorted(cards,key=lambda x:(x['start'] or '9999',x['name'])),'items':items,'tasks':task_rows,'changes':changes[:500],'today':today,'default_milestones':[{'phase':a,'title':b,'key':k,'criterion':d} for a,b,k,d in DEFAULT_MILESTONES]}

def read_workbook(data):
 try:
  import openpyxl
 except ImportError:raise HTTPException(500,'엑셀 처리를 위해 openpyxl 설치가 필요합니다. 01_처음한번_설치.cmd를 다시 실행해 주세요.')
 try:return openpyxl.load_workbook(io.BytesIO(data),data_only=True,read_only=True)
 except Exception:raise HTTPException(422,'읽을 수 있는 Excel(.xlsx) 파일을 올려 주세요.')

def header_map(row):
 out={}
 for i,cell in enumerate(row):
  s=re.sub(r'[\s()（）*]+','',str(cell or '')).strip().lower()
  if not s:continue
  for alias,name in HEADER_ALIASES.items():
   if s==alias.lower() or s.startswith(alias.lower()):
    out.setdefault(name,i);break
 return out

def parse_schedule_sheet(ws):
 rows=list(ws.iter_rows(values_only=True));header=None;cols=None
 for idx,row in enumerate(rows[:15]):
  cols=header_map(row)
  if '항목명' in cols and ('단계' in cols or '시작일' in cols):header=idx;break
 if header is None:raise HTTPException(422,'엑셀 첫 15행 안에서 "단계·항목명·시작일" 머리글을 찾지 못했습니다. 양식을 내려받아 사용해 주세요.')
 out=[];problems=[]
 def get(row,name):
  i=cols.get(name);return row[i] if i is not None and i<len(row) else None
 for n,row in enumerate(rows[header+1:],start=header+2):
  if not row or all(v in (None,'') for v in row):continue
  title=str(get(row,'항목명') or '').strip()
  if not title:problems.append(f'{n}행: 항목명이 비어 있어 건너뜀');continue
  phase=norm_phase(get(row,'단계'))
  if not phase:problems.append(f'{n}행 "{title}": 단계를 인식하지 못해 건너뜀 (사용 가능: '+', '.join(PHASES)+')');continue
  kind_raw=str(get(row,'구분') or '').strip()
  kind='마일스톤' if ('마일' in kind_raw or kind_raw.lower() in ('milestone','ms','m')) else '항목'
  start=parse_day(get(row,'시작일'));end=parse_day(get(row,'종료일'))
  if kind=='마일스톤':
   day=end or start
   if not day:problems.append(f'{n}행 "{title}": 마일스톤 날짜가 없어 미정으로 등록')
   start=end=day
  else:
   if not start and not end:problems.append(f'{n}행 "{title}": 날짜가 없어 미정으로 등록')
   start=start or end;end=end or start
   if start and end and start>end:start,end=end,start;problems.append(f'{n}행 "{title}": 시작일이 종료일보다 늦어 서로 바꿈')
  entry={'kind':kind,'phase':phase,'title':title[:200],'owner_name':str(get(row,'담당자') or '').strip()[:80],'start':start,'end':end,'progress':parse_progress(get(row,'진행률')),'key':truthy(get(row,'핵심')),'depends_on':str(get(row,'선행작업') or '').strip()[:200],'note':str(get(row,'비고') or '').strip()[:1000],'row':n}
  dup=next((i for i,x in enumerate(out) if x['phase']==phase and x['title']==entry['title']),None)
  if dup is not None:problems.append(f'{n}행 "{title}": 같은 단계에 같은 항목명이 {out[dup]["row"]}행에도 있어 아래 행을 적용');out[dup]=entry
  else:out.append(entry)
 return out,problems

def parse_project_sheet(ws):
 """Key/value rows (A: label, B: value) or a header row followed by one data row."""
 rows=[r for r in ws.iter_rows(values_only=True) if r and any(v not in (None,'') for v in r)]
 if not rows:return {}
 out={}
 def label(v):return re.sub(r'\s+','',str(v or '')).strip()
 first=[label(v) for v in rows[0]]
 if sum(1 for v in first if v in PROJECT_FIELD_ALIASES)>=2 and len(rows)>1:
  for i,v in enumerate(first):
   if v in PROJECT_FIELD_ALIASES and i<len(rows[1]):out[PROJECT_FIELD_ALIASES[v]]=rows[1][i]
 else:
  for r in rows:
   if len(r)>=2 and label(r[0]) in PROJECT_FIELD_ALIASES:out[PROJECT_FIELD_ALIASES[label(r[0])]]=r[1]
 clean={}
 for k,v in out.items():
  if v in (None,''):continue
  clean[k]=parse_day(v) if k in ('start','end') else str(v).strip()
 return clean

def match_owner(name,people,members):
 if not name:return None
 hits=[p for p in people if p['id'] in members and p['name']==name.strip()]
 return hits[0]['id'] if len(hits)==1 else None

def apply_import(w,c,p,actor,rows,info,mode,import_id,people):
 today=datetime.now(w.KST).date().isoformat()
 existing={ (x['phase'],x['title']):x for x in w.all_records(c,'schedule_item') if x['project_id']==p['id'] and not x.get('deleted_at')}
 added=changed=removed=unchanged=0;seen=set();stamp=w.now()
 for r in rows:
  key=(r['phase'],r['title']);seen.add(key);old=existing.get(key)
  owner_id=match_owner(r['owner_name'],people,p['members'])
  fieldsd={'kind':r['kind'],'owner_id':owner_id,'owner_name':r['owner_name'],'start':r['start'],'end':r['end'],'progress':r['progress'],'key':r['key'],'depends_on':r['depends_on'],'note':r['note']}
  if old:
   diff={k:{'before':old.get(k),'after':v} for k,v in fieldsd.items() if old.get(k)!=v and not (k=='note' and not v)}
   if not diff:unchanged+=1;continue
   if 'note' in diff and not r['note']:diff.pop('note')
   old.update({k:v['after'] for k,v in diff.items()},version=old['version']+1,updated_at=stamp,source='엑셀' if old.get('source')!='기본' else '기본',import_id=import_id)
   w.save(c,'schedule_item',old)
   action='기간 변경' if ({'start','end'}&set(diff)) else '진행률 변경' if 'progress' in diff else '내용 변경'
   record_change(w,c,p['id'],actor,'엑셀',old['kind'],old['id'],old['title'],old['phase'],action,diff,'엑셀 업로드');changed+=1
  else:
   item={'id':w.uid(),'project_id':p['id'],'phase':r['phase'],'title':r['title'],**fieldsd,'source':'엑셀','import_id':import_id,'version':1,'created_at':stamp,'updated_at':stamp,'created_by':actor,'done_at':None,'deleted_at':None}
   w.save(c,'schedule_item',item);record_change(w,c,p['id'],actor,'엑셀',item['kind'],item['id'],item['title'],item['phase'],'추가',{'start':{'before':None,'after':item['start']},'end':{'before':None,'after':item['end']}},'엑셀 업로드');added+=1
 if mode=='replace':
  for key,old in existing.items():
   if key in seen or old.get('source')!='엑셀':continue
   old.update(deleted_at=stamp,version=old['version']+1);w.save(c,'schedule_item',old)
   record_change(w,c,p['id'],actor,'엑셀',old['kind'],old['id'],old['title'],old['phase'],'삭제',{'start':{'before':old.get('start'),'after':None},'end':{'before':old.get('end'),'after':None}},'엑셀에 없는 항목 제거');removed+=1
 info_changes={}
 for k in ('code','name','customer','equipment','start','end'):
  if k in info and info[k] and p.get(k)!=info[k]:
   if k=='name':continue  # Project names are managed in the project dialog, never silently renamed by a file.
   info_changes[k]={'before':p.get(k),'after':info[k]};p[k]=info[k]
 if info_changes:
  w.save(c,'project',p);record_change(w,c,p['id'],actor,'엑셀','프로젝트',p['id'],p['name'],None,'납기 변경' if 'end' in info_changes else '프로젝트 정보 변경',info_changes,'엑셀 프로젝트 시트')
 return {'added':added,'changed':changed,'removed':removed,'unchanged':unchanged,'project_updated':sorted(info_changes)}

def build_workbook(w,c,actor,project_id,today,template=False):
 try:
  import openpyxl
  from openpyxl.styles import Font,PatternFill,Alignment,Border,Side
  from openpyxl.worksheet.datavalidation import DataValidation
  from openpyxl.utils import get_column_letter
 except ImportError:raise HTTPException(500,'엑셀 처리를 위해 openpyxl 설치가 필요합니다. 01_처음한번_설치.cmd를 다시 실행해 주세요.')
 wb=openpyxl.Workbook();ws=wb.active;ws.title='일정'
 head_font=Font(bold=True,color='FFFFFF');head_fill=PatternFill('solid',fgColor='132F52');thin=Side(style='thin',color='DCE2E9');border=Border(left=thin,right=thin,top=thin,bottom=thin)
 def header(sheet,names):
  for i,n in enumerate(names,start=1):
   cell=sheet.cell(row=1,column=i,value=n);cell.font=head_font;cell.fill=head_fill;cell.alignment=Alignment(horizontal='center',vertical='center');cell.border=border
  sheet.row_dimensions[1].height=22;sheet.freeze_panes='A2'
 header(ws,EXCEL_HEADERS)
 widths=[14,10,34,12,12,12,8,6,22,36]
 for i,wd in enumerate(widths,start=1):ws.column_dimensions[get_column_letter(i)].width=wd
 people={p['id']:p for p in w.all_records(c,'person')}
 if template:
  ps=visible_projects(w,c,actor,project_id) if project_id else []
  p=ps[0] if ps else None
  sample_dates=spread_dates(p.get('start'),p.get('end')) if p else spread_dates(today,(date.fromisoformat(today)+timedelta(days=180)).isoformat())
  counts={};index={};r=2
  for phase,title,key,criterion in DEFAULT_MILESTONES:counts[phase]=counts.get(phase,0)+1
  for phase,title,key,criterion in DEFAULT_MILESTONES:
   i=index.get(phase,0);index[phase]=i+1;day=phase_of_date(sample_dates,phase,i,counts[phase])
   for col,val in enumerate([phase,'마일스톤',title,'',None,day,'','Y' if key else '','',criterion],start=1):ws.cell(row=r,column=col,value=val).border=border
   r+=1
  example=[('설계 및 변경','항목','기본 설계도 작성','',sample_dates.get('수주'),sample_dates.get('설계 및 변경'),30,'','고객 사양 확정','예시 행입니다. 지우고 사용하세요.')]
  for row in example:
   for col,val in enumerate(row,start=1):ws.cell(row=r,column=col,value=val).border=border
   r+=1
  dv=DataValidation(type='list',formula1='"'+','.join(PHASES)+'"',allow_blank=False);dv.error='단계 목록에서 골라 주세요.';ws.add_data_validation(dv);dv.add(f'A2:A500')
  dv2=DataValidation(type='list',formula1='"마일스톤,항목"',allow_blank=True);ws.add_data_validation(dv2);dv2.add('B2:B500')
  guide=wb.create_sheet('작성 안내')
  lines=['PNT 프로젝트 일정 양식','',
   '· 단계: '+' → '.join(PHASES),'· 구분: 마일스톤(하루짜리 완료 기준점) 또는 항목(기간이 있는 작업). 비우면 항목으로 봅니다.',
   '· 날짜: 2026-11-13 또는 2026.11.13 형식. 마일스톤은 종료일만 적어도 됩니다.','· 진행률: 0~100 숫자. 핵심: 핵심 마일스톤이면 Y.',
   '· 담당자: 프로젝트 참여자 이름과 같으면 자동 연결되고, 아니면 이름 그대로 표시합니다.',
   '· 같은 단계·같은 항목명이 이미 있으면 그 항목을 갱신하고, 변경 내용은 변경 이력에 남습니다.',
   '· "프로젝트" 시트의 착수일·납기일·고객사·장비는 프로젝트 정보에 반영됩니다. (PM만 업로드 가능)']
  for i,l in enumerate(lines,start=1):guide.cell(row=i,column=1,value=l).font=Font(bold=(i==1),size=13 if i==1 else 11)
  guide.column_dimensions['A'].width=110
  pj=wb.create_sheet('프로젝트');header(pj,['프로젝트번호','프로젝트명','고객사','장비·호기','착수일','납기일'])
  vals=[p.get('code') or p['id'],p['name'],p.get('customer',''),p.get('equipment',''),p.get('start'),p.get('end')] if p else ['PNT-SIM-001','구미 전극 노칭기 프로젝트 01','고객 SIM-01','전극 노칭기 1호기',today,(date.fromisoformat(today)+timedelta(days=180)).isoformat()]
  for i,v in enumerate(vals,start=1):pj.cell(row=2,column=i,value=v).border=border
  for i,wd in enumerate([16,34,16,20,12,12],start=1):pj.column_dimensions[get_column_letter(i)].width=wd
  return wb
 snap=snapshot(w,c,actor,project_id,today);r=2
 names={p['id']:p for p in snap['projects']}
 multi=len(snap['projects'])>1
 if multi:
  ws.insert_cols(1);ws.cell(row=1,column=1,value='프로젝트').font=head_font;ws.cell(row=1,column=1).fill=head_fill;ws.column_dimensions['A'].width=30
 for it in snap['items']:
  owner=people.get(it.get('owner_id'),{}).get('name') or it.get('owner_name','')
  row=[it['phase'],it['kind'],it['title'],owner,it.get('start'),it.get('end'),it.get('progress',0),'Y' if it.get('key') else '',it.get('depends_on',''),it.get('note','')]
  if multi:row=[names[it['project_id']]['name']]+row
  for col,val in enumerate(row,start=1):ws.cell(row=r,column=col,value=val).border=border
  r+=1
 for t in snap['tasks']:
  row=[t.get('phase') or '미분류','업무',t['title'],people.get(t.get('owner_id'),{}).get('name',''),t.get('start'),t.get('end'),100 if t['status']=='완료' else '', '','','업무 관리에서 등록된 업무 · '+t['status']]
  if multi:row=[names[t['project_id']]['name']]+row
  for col,val in enumerate(row,start=1):ws.cell(row=r,column=col,value=val).border=border
  r+=1
 pj=wb.create_sheet('프로젝트');header(pj,['프로젝트번호','프로젝트명','고객사','장비·호기','착수일','납기일','현재 단계','PM'])
 for i,p in enumerate(snap['projects'],start=2):
  for col,val in enumerate([p['code'],p['name'],p['customer'],p['equipment'],p['planned_start'],p['planned_end'],p['current_phase'],people.get(p['pm'],{}).get('name','')],start=1):pj.cell(row=i,column=col,value=val).border=border
 for i,wd in enumerate([16,34,16,20,12,12,14,10],start=1):pj.column_dimensions[get_column_letter(i)].width=wd
 ch=wb.create_sheet('변경 이력');header(ch,['일시','프로젝트','변경자','출처','대상','단계','항목','변경 내용','전','후','비고'])
 for i,x in enumerate(snap['changes'],start=2):
  parts=x.get('changes') or {}
  before=' / '.join(f"{k}: {v.get('before')}" for k,v in parts.items());after=' / '.join(f"{k}: {v.get('after')}" for k,v in parts.items())
  for col,val in enumerate([x['at'].replace('T',' ')[:16],names.get(x['project_id'],{}).get('name',''),people.get(x['actor'],{}).get('name',x['actor']),x['source'],x['target_type'],x.get('phase') or '',x['title'],x['action'],before,after,x.get('note','')],start=1):ch.cell(row=i,column=col,value=val).border=border
 for i,wd in enumerate([16,26,10,8,10,14,32,12,30,30,24],start=1):ch.column_dimensions[get_column_letter(i)].width=wd
 return wb

def xlsx_response(wb,filename):
 buf=io.BytesIO();wb.save(buf);buf.seek(0)
 from urllib.parse import quote
 return StreamingResponse(buf,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(filename)})

def build_router(w):
 r=APIRouter(prefix='/api')
 def today():return datetime.now(w.KST).date().isoformat()
 @r.get('/schedule')
 def get_schedule(project_id:str|None=None,actor=Depends(w.user)):
  with w.connect() as c:return snapshot(w,c,actor,project_id or None,today())
 @r.get('/schedule/template')
 def template(project_id:str|None=None,actor=Depends(w.user)):
  with w.connect() as c:wb=build_workbook(w,c,actor,project_id or None,today(),template=True)
  return xlsx_response(wb,'PNT_프로젝트_일정_양식.xlsx')
 @r.get('/schedule/export')
 def export(project_id:str|None=None,actor=Depends(w.user)):
  with w.connect() as c:
   wb=build_workbook(w,c,actor,project_id or None,today())
   name=(w.read(c,'project',project_id)['name'] if project_id else '전체 프로젝트')
  return xlsx_response(wb,f'PNT_일정표_{name}_{today()}.xlsx')
 def resolve_target(info,filename,actor):
  """No project chosen: reuse the project with the same number (or name) from the sheet, otherwise create it."""
  def key(s):return re.sub(r'\s+','',str(s or '')).casefold()
  with w.connect() as c:
   mine=[p for p in w.all_records(c,'project') if actor['id'] in p['members']]
   hit=next((p for p in mine if info.get('code') and key(p.get('code') or p['id'])==key(info['code'])),None) or next((p for p in mine if info.get('name') and key(p['name'])==key(info['name'])),None)
   if hit:
    w.project(c,hit['id'],actor,True);return hit['id'],False
  name=(info.get('name') or re.sub(r'\.(xlsx|xlsm)$','',filename or '',flags=re.I)).strip()
  if len(name)<2:raise HTTPException(422,'엑셀의 "프로젝트" 시트에 프로젝트명을 적거나, 반영할 프로젝트를 선택해 주세요.')
  p=w.create_project(w.ProjectInput(name=name[:120],code=info.get('code') or None,customer=info.get('customer') or None,equipment=info.get('equipment') or None,start=info.get('start'),end=info.get('end')),actor=actor)
  return p['id'],True
 @r.post('/schedule/import',status_code=201)
 async def import_excel(project_id:str=Form(''),mode:str=Form('merge'),file:UploadFile=File(...),actor=Depends(w.user)):
  if not (file.filename or '').lower().endswith(('.xlsx','.xlsm')):raise HTTPException(422,'Excel(.xlsx) 파일을 올려 주세요.')
  if mode not in ('merge','replace'):raise HTTPException(422,'반영 방식을 확인해 주세요.')
  data=await file.read(8*1024*1024+1)
  if len(data)>8*1024*1024:raise HTTPException(413,'엑셀 파일은 8MB까지 올릴 수 있습니다.')
  wb=read_workbook(data)
  sheet=next((wb[n] for n in wb.sheetnames if n.strip() in ('일정','일정표','schedule','Schedule')),wb[wb.sheetnames[0]])
  rows,problems=parse_schedule_sheet(sheet)
  info=parse_project_sheet(wb['프로젝트']) if '프로젝트' in wb.sheetnames else {}
  if not rows and not info:raise HTTPException(422,'반영할 행이 없습니다. '+' '.join(problems[:3]))
  created=False
  if not project_id:project_id,created=resolve_target(info,file.filename,actor)
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');p=w.project(c,project_id,actor,True);ensure_milestones(w,c,p,actor['id'])
   people=w.all_records(c,'person');import_id=w.uid()
   result=apply_import(w,c,p,actor['id'],rows,info,mode,import_id,people)
  return {**result,'rows':len(rows),'problems':problems[:30],'import_id':import_id,'project_id':p['id'],'project_name':p['name'],'project_created':created}
 @r.post('/schedule/items',status_code=201)
 def create_item(body:ItemInput,actor=Depends(w.user)):
  if body.kind not in ITEM_KINDS or body.phase not in PHASES:raise HTTPException(422,'구분과 단계를 확인해 주세요.')
  start=check_day(w,body.start,'시작일');end=check_day(w,body.end,'종료일')
  if body.kind=='마일스톤':start=end=(end or start)
  else:
   start=start or end;end=end or start
   if start and end and start>end:raise HTTPException(422,'시작일은 종료일보다 늦을 수 없습니다.')
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');p=w.project(c,body.project_id,actor,True);ensure_milestones(w,c,p,actor['id'])
   if body.owner_id and body.owner_id not in p['members']:raise HTTPException(422,'프로젝트 참여자 중에서 담당자를 선택해 주세요.')
   if any(x['project_id']==p['id'] and not x.get('deleted_at') and x['phase']==body.phase and x['title'].strip()==body.title.strip() for x in w.all_records(c,'schedule_item')):raise HTTPException(409,'같은 단계에 같은 이름의 항목이 있습니다.')
   stamp=w.now();item={'id':w.uid(),'project_id':p['id'],'kind':body.kind,'phase':body.phase,'title':body.title.strip(),'owner_id':body.owner_id,'owner_name':body.owner_name.strip(),'start':start,'end':end,'progress':body.progress,'key':body.key,'depends_on':body.depends_on.strip(),'note':body.note.strip(),'source':'직접','import_id':None,'version':1,'created_at':stamp,'updated_at':stamp,'created_by':actor['id'],'done_at':None,'deleted_at':None}
   w.save(c,'schedule_item',item);record_change(w,c,p['id'],actor['id'],'직접',item['kind'],item['id'],item['title'],item['phase'],'추가',{'start':{'before':None,'after':start},'end':{'before':None,'after':end}})
   item['status']=item_status(item,today());return item
 @r.patch('/schedule/items/{iid}')
 def edit_item(iid:str,body:ItemEdit,actor=Depends(w.user)):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');it=w.read(c,'schedule_item',iid)
   if it.get('deleted_at'):raise HTTPException(404,'삭제된 항목입니다.')
   p=w.project(c,it['project_id'],actor,True);w.version(it,body.version)
   new={k:v for k,v in body.model_dump(exclude={'version','reason'}).items() if k in body.model_fields_set}
   if 'kind' in new and new['kind'] not in ITEM_KINDS:raise HTTPException(422,'구분을 확인해 주세요.')
   if 'phase' in new and new['phase'] not in PHASES:raise HTTPException(422,'단계를 확인해 주세요.')
   if 'owner_id' in new and new['owner_id'] and new['owner_id'] not in p['members']:raise HTTPException(422,'프로젝트 참여자 중에서 담당자를 선택해 주세요.')
   if 'title' in new:new['title']=new['title'].strip()
   for k,label in (('start','시작일'),('end','종료일')):
    if k in new:new[k]=check_day(w,new[k],label)
   merged={**it,**new}
   if merged['kind']=='마일스톤':
    day=merged['end'] if 'end' in new else merged['start'] if 'start' in new else (merged.get('end') or merged.get('start'));merged['start']=merged['end']=day;new.update(start=day,end=day)
   else:
    if merged.get('start') and merged.get('end') and merged['start']>merged['end']:raise HTTPException(422,'시작일은 종료일보다 늦을 수 없습니다.')
   diff={k:{'before':it.get(k),'after':v} for k,v in new.items() if it.get(k)!=v}
   if not diff:return {**it,'status':item_status(it,today())}
   if 'progress' in diff:merged['done_at']=w.now() if merged['progress']>=100 else None;diff.setdefault('done_at',{'before':it.get('done_at'),'after':merged['done_at']})
   merged.update(version=it['version']+1,updated_at=w.now());w.save(c,'schedule_item',merged)
   action='기간 변경' if {'start','end'}&set(diff) else '완료' if merged.get('progress',0)>=100 and 'progress' in diff else '진행률 변경' if 'progress' in diff else '단계 변경' if 'phase' in diff else '담당자 변경' if {'owner_id','owner_name'}&set(diff) else '내용 변경'
   record_change(w,c,p['id'],actor['id'],'직접',merged['kind'],iid,merged['title'],merged['phase'],action,{k:v for k,v in diff.items() if k!='done_at'},body.reason.strip())
   merged['status']=item_status(merged,today());return merged
 @r.post('/schedule/items/{iid}/delete')
 def delete_item(iid:str,body:ItemDelete,actor=Depends(w.user)):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');it=w.read(c,'schedule_item',iid);p=w.project(c,it['project_id'],actor,True);w.version(it,body.version)
   if it.get('deleted_at'):return {'ok':True}
   it.update(deleted_at=w.now(),version=it['version']+1);w.save(c,'schedule_item',it)
   record_change(w,c,p['id'],actor['id'],'직접',it['kind'],iid,it['title'],it['phase'],'삭제',{'start':{'before':it.get('start'),'after':None},'end':{'before':it.get('end'),'after':None}},body.reason.strip())
  return {'ok':True}
 @r.patch('/schedule/tasks/{tid}/phase')
 def set_task_phase(tid:str,body:TaskPhase,actor=Depends(w.user)):
  if body.phase is not None and body.phase not in PHASES:raise HTTPException(422,'단계를 확인해 주세요.')
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');t=w.read(c,'task',tid);w.project(c,t['project_id'],actor,True);w.version(t,body.version)
   if t.get('phase')==body.phase:return t
   w.ev(t,actor['id'],'단계 지정',changes={'phase':{'before':t.get('phase'),'after':body.phase}});t.update(phase=body.phase,version=t['version']+1,updated_at=w.now());w.save(c,'task',t);return t
 @r.patch('/projects/{pid}/info')
 def project_info(pid:str,body:ProjectInfo,actor=Depends(w.user)):
  start=check_day(w,body.start,'착수일');end=check_day(w,body.end,'납기일')
  if start and end and start>end:raise HTTPException(422,'착수일은 납기일보다 늦을 수 없습니다.')
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');p=w.project(c,pid,actor,True)
   new={'code':(body.code or '').strip() or p.get('code') or p['id'],'customer':(body.customer or '').strip(),'equipment':(body.equipment or '').strip(),'start':start,'end':end}
   sent={k:v for k,v in new.items() if k in body.model_fields_set or k=='code'}
   if 'code' in sent and sent['code']!=p.get('code') and any(x['id']!=p['id'] and (x.get('code') or x['id'])==sent['code'] for x in w.all_records(c,'project')):raise HTTPException(409,'같은 프로젝트 번호가 이미 있습니다.')
   diff={k:{'before':p.get(k),'after':v} for k,v in sent.items() if p.get(k)!=v}
   if not diff:return p
   first_period=not p.get('start') and not p.get('end') and (start or end)
   p.update(sent);w.save(c,'project',p)
   record_change(w,c,p['id'],actor['id'],'직접','프로젝트',p['id'],p['name'],None,'납기 변경' if 'end' in diff else '착수일 변경' if 'start' in diff else '프로젝트 정보 변경',diff,body.reason.strip())
   # Seeded milestones that still have no date take their date from the first project period entered.
   if first_period and p.get('start') and p.get('end'):
    dates=spread_dates(p['start'],p['end']);counts={};index={}
    for phase,_,_,_ in DEFAULT_MILESTONES:counts[phase]=counts.get(phase,0)+1
    titles={(a,b):(k) for a,b,k,_ in DEFAULT_MILESTONES}
    for x in w.all_records(c,'schedule_item'):
     if x['project_id']!=p['id'] or x.get('deleted_at') or x.get('source')!='기본' or x.get('start'):continue
     i=index.get(x['phase'],0);index[x['phase']]=i+1;day=phase_of_date(dates,x['phase'],i,counts.get(x['phase'],1))
     x.update(start=day,end=day,version=x['version']+1,updated_at=w.now());w.save(c,'schedule_item',x)
   return p
 return r
