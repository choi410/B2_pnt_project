"""Read-only home follow-ups. A recorded action is not proof it remains undone."""
import re
from datetime import date
from work.v17.retrieval import registered_document, document_lines


def attention_items(projects, meetings, tasks, people, today):
 projects={p['id']:p for p in projects if not p.get('deleted_at')}
 people={p['id']:p for p in people}
 tasks=[t for t in tasks if t.get('project_id') in projects and not t.get('deleted_at')]
 linked={(t.get('meeting_id'),t.get('candidate_id')):t for t in tasks if t.get('candidate_id')}
 out=[]
 for m in meetings:
  p=projects.get(m.get('project_id'))
  if not p:continue
  doc=registered_document(m)
  if not doc or doc['revision']!=m.get('revision') or (m.get('overview') or {}).get('revision')!=doc['revision']:continue
  lines={line['id']:line['text'] for line in document_lines(doc)}
  seen=set()
  for item in (m.get('reviewed_bundle') or {}).get('candidates',[]):
   if item.get('kind') not in ('업무','확인사항') or item.get('state') in ('excluded','dismissed','제외'):continue
   if (m['id'],item.get('id')) in linked:continue
   text=str(item.get('description') or item.get('title') or '').strip()
   if not text or text in seen:continue
   seen.add(text)
   quotes=list(dict.fromkeys(lines[ref] for ref in item.get('evidence',[]) if ref in lines))
   # Display an explicitly named person, including a non-member. This grants no access or assignment.
   named=set()
   for pid in people:
    name=people.get(pid,{}).get('name','')
    if name and any(re.search(r'^\s*(?:[-•]\s*)?'+re.escape(name)+r'(?:이|가|은|는|\s*:)\s*',q) for q in quotes):named.add(pid)
   owner=item.get('owner_id')
   if owner not in p.get('members',[]):owner=None
   conflict=bool(owner and named and named!={owner}) or len(named)>1
   if conflict:owner=None
   elif not owner and len(named)==1:owner=next(iter(named))
   elif not owner and item.get('kind')=='확인사항' and item.get('reviewer_id') in p.get('members',[]):
    # The PM is the default reviewer, not necessarily the person doing the check.
    if item['reviewer_id']!=p.get('pm'):owner=item['reviewer_id']
   due=item.get('due') or ''
   if not due:
    dates={d for q in quotes for d in re.findall(r'(\d{4}-\d{2}-\d{2})\s*까지',q)}
    if len(dates)==1:due=next(iter(dates))
   try:
    if due:date.fromisoformat(due)
   except (ValueError,TypeError):due=''
   reasons=[]
   if not owner:reasons.append('담당 확인' if conflict else '담당자 미정')
   if due and due<today:reasons.append('기한 경과')
   reasons.append('처리 결과 확인')
   out.append({'id':'meeting:'+m['id']+':'+str(item.get('id') or len(out)),
    'project_id':p['id'],'meeting_id':m['id'],'meeting_title':doc['title'],'meeting_date':doc.get('date',''),
    'title':item.get('title') or text,'description':text,'owner_id':owner,'owner_basis':'회의록 표기',
    'due':due,'reasons':reasons,'quotes':quotes,'kind':item['kind'],'origin':'회의록',
    'note':'담당자와 기한은 회의록의 표기이며 업무 배정을 뜻하지 않습니다. 이후 처리 결과가 업무 기록과 연결되어 있지 않아 완료 여부는 담당자에게 확인해야 합니다.'})
 for t in tasks:
  if t.get('status')=='완료':continue
  owner=t.get('reviewer_id') if t.get('kind')=='확인사항' else t.get('owner_id')
  reasons=[]
  if not owner:reasons.append('담당자 미정')
  if t.get('due') and t['due']<today:reasons.append('기한 지남')
  if t.get('status')=='검토대기':reasons.append('완료 검토 대기')
  elif t.get('status')=='보완요청':reasons.append('보완 요청')
  elif t.get('kind')=='확인사항' and not t.get('result'):reasons.append('확인 결과 없음')
  if not reasons:continue
  out.append({'id':'task:'+t['id'],'project_id':t['project_id'],'meeting_id':t.get('meeting_id'),
   'title':t['title'],'description':t.get('description',''),'owner_id':owner,'owner_basis':'배정 담당',
   'due':t.get('due') or '', 'reasons':reasons,'quotes':[],'kind':t.get('kind'),'origin':'업무',
   'result':t.get('result',''),'note':'등록된 업무의 담당자·기한·처리 상태를 기준으로 표시합니다.'})
 return out
