"""Personal calendar notes and PM-owned project direction. No inferred progress."""
import hashlib, json, re
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from work.v17.retrieval import registered_document, document_lines

DEFAULT_STAGES=['수주','설계 및 변경','구매','제작','검수','납품','현장','종료']

def stages_for(overview):
 stages=list(dict.fromkeys(overview.get('stages') or DEFAULT_STAGES))
 current=overview.get('current_stage')
 if current and current not in stages:stages.append(current)
 return stages

def suggestions(w,c,p):
 """Reuse the latest registered text and reviewed extraction; never call a model.
 A stage needs an explicit assertion. Goals are proposals, not a baseline.
 Older meetings cannot resurrect a goal after a newer meeting is registered.
 """
 docs=[]
 for m in w.all_records(c,'meeting'):
  if m['project_id']!=p['id']:continue
  doc=registered_document(m)
  if doc:docs.append((m,doc))
 docs.sort(key=lambda item:(item[1].get('date') or '',item[0].get('created_at',''),item[0]['id']),reverse=True)
 overview=p.get('overview') or {}
 out={'items':[],'meeting':None,'stale':False}
 if not docs:return out
 m,doc=docs[0]
 out['meeting']={'id':m['id'],'title':doc['title'],'date':doc.get('date'),'revision':doc['revision']}
 if m.get('revision')!=doc['revision']:
  out['stale']=True;return out
 lines=document_lines(doc);by_id={x['id']:x for x in lines}
 def add(field,value,refs,due='',origin='원문에 명시된 내용'):
  refs=[r for r in dict.fromkeys(refs) if r in by_id]
  if not value or not refs or value==overview.get(field):return
  key=hashlib.sha256(json.dumps([p['id'],doc['fingerprint'],field,value,refs,due],ensure_ascii=False).encode()).hexdigest()
  out['items'].append({'id':key,'field':field,'value':value,'due':due,'origin':origin,'evidence':[by_id[r] for r in refs], 'meeting':out['meeting']})
 # Only "현재 단계: X" / "현재 단계는 X입니다" is accepted, never stage keywords.
 found=[]
 for line in lines:
  match=re.search(r'(?:프로젝트\s*)?현재\s*(?:진행\s*)?단계\s*(?:[:：]|는|은)\s*(.+)',line['text'])
  if match:
   value=re.sub(r'(?:입니다|이다|임)?[.。]?\s*$','',match.group(1)).strip()
   if value in stages_for(overview):found.append((value,line['id']))
 if len({v for v,r in found})==1:
  add('current_stage',found[0][0],[r for v,r in found])
 # Do not silently choose between conflicting explicitly labelled goals.
 goals=[]
 for line in lines:
  match=re.match(r'\s*(?:프로젝트\s*)?다음\s*목표\s*[:：]\s*(.+)',line['text'])
  if match and len(match.group(1))<=2000:goals.append((match.group(1).strip(),line['id']))
 if goals:
  for value,ref in goals[:2]:add('next_goal',value,[ref])
 elif (m.get('overview') or {}).get('revision')==doc['revision']:
  seen=set()
  for item in (m.get('reviewed_bundle') or {}).get('candidates',[]):
   if item.get('kind')!='업무':continue
   text=(item.get('title') or item.get('description') or '').strip()
   if not text or len(text)>2000 or text in seen:continue
   seen.add(text)
   # A date proposal is shown only when the same ISO date is present in its evidence.
   refs=item.get('evidence') or []
   due=item.get('due') or ''
   if due and not any(due in by_id.get(r,{}).get('text','') for r in refs):due=''
   add('next_goal',text,refs,due,'등록 시 확인한 후속 조치')
   if sum(x['field']=='next_goal' for x in out['items'])>=2:break
 return out

class MemoInput(BaseModel):
 model_config=ConfigDict(extra='forbid')
 text:str=Field(max_length=1000)

class FocusInput(BaseModel):
 model_config=ConfigDict(extra='forbid')
 version:int
 current_stage:str=Field(default='',max_length=80)
 next_goal:str=Field(default='',max_length=2000)
 next_goal_date:str=Field(default='',max_length=10)
 suggestion_ids:list[str]=Field(default_factory=list,max_length=2)

def build_router(w):
 r=APIRouter(prefix='/api')
 @r.get('/home/attention')
 def attention(actor=Depends(w.user)):
  from work.v17.home_attention import attention_items
  with w.connect() as c:
   projects=[p for p in w.all_records(c,'project') if actor['id'] in p.get('members',[])]
   return {'items':attention_items(projects,w.all_records(c,'meeting'),w.all_records(c,'task'),w.all_records(c,'person'),w.now()[:10])}
 @r.get('/calendar/memos')
 def memos(start:date,end:date,actor=Depends(w.user)):
  if not 0<=(end-start).days<42:raise HTTPException(422,'조회 범위는 최대 42일입니다.')
  with w.connect() as c:
   return {row['day']:row['text'] for row in c.execute('SELECT day,text FROM calendar_memos WHERE user_id=? AND day BETWEEN ? AND ?',(actor['id'],start.isoformat(),end.isoformat()))}
 @r.put('/calendar/memos/{day}')
 def save_memo(day:date,body:MemoInput,actor=Depends(w.user)):
  text=body.text.strip();key=(actor['id'],day.isoformat())
  with w.connect() as c:
   if text:c.execute('INSERT INTO calendar_memos(user_id,day,text) VALUES(?,?,?) ON CONFLICT(user_id,day) DO UPDATE SET text=excluded.text',(*key,text))
   else:c.execute('DELETE FROM calendar_memos WHERE user_id=? AND day=?',key)
  return {'text':text}
 @r.get('/projects/{pid}/focus-suggestions')
 def get_suggestions(pid,actor=Depends(w.user)):
  with w.connect() as c:
   p=w.project(c,pid,actor,True)
   return suggestions(w,c,p)
 @r.patch('/projects/{pid}/focus')
 def save_focus(pid,body:FocusInput,actor=Depends(w.user)):
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE');p=w.project(c,pid,actor,True)
   old=p.get('overview') or {'version':1};w.version(old,body.version)
   stage=body.current_stage.strip();goal=body.next_goal.strip();due=w.due(body.next_goal_date) or ''
   if due and not goal:raise HTTPException(422,'목표일을 지정하려면 다음 목표를 입력해 주세요.')
   if body.suggestion_ids:
    current={s['id']:s for s in suggestions(w,c,p)['items']}
    for key in body.suggestion_ids:
     item=current.get(key)
     if not item:raise HTTPException(409,'근거 회의록이 바뀌었습니다. 제안을 다시 확인해 주세요.')
     if item['value']!={'current_stage':stage,'next_goal':goal}[item['field']]:raise HTTPException(422,'수정한 내용은 직접 입력으로 저장해 주세요.')
   stages=stages_for(old)
   if stage and stage not in stages:
    if len(stages)>=12:raise HTTPException(422,'진행 단계는 최대 12개입니다. 프로젝트 정보에서 기존 단계를 정리해 주세요.')
    stages.append(stage)
   p['overview']={**old,'current_stage':stage,'stages':stages,'next_goal':goal,'next_goal_date':due,'version':body.version+1,'updated_by':actor['id'],'updated_at':w.now(),'focus_updated_by':actor['id'],'focus_updated_at':w.now()}
   w.save(c,'project',p)
   return p['overview']
 return r
