"""Current agreed values come from the reviewed ledger, never a raw model guess."""
import hashlib,json,re
from work.v17.retrieval import revision_document,document_lines

def baseline_intent(question):
 q=re.sub(r'\s+','',question)
 if any(s in q for s in ('이유','왜','논의','요청','이력','과정','변경전','제안','보류','철회','언급','회의내용')):return False
 return any(s in q for s in ('현재','최종','확정','합의된','기준')) or bool(re.search(r'(납기|납품일|사양).*(언제|얼마|몇|뭐|무엇|알려)',q))

def signature(w,c,ids):
 ids=set(ids)
 rows=[x for x in w.all_records(c,'change_event') if x['project_id'] in ids]
 meetings=[(m['id'],m.get('revision'),m.get('deleted_at')) for m in w.all_records(c,'meeting') if m['project_id'] in ids]
 return hashlib.sha256(json.dumps([sorted(rows,key=lambda x:x['id']),sorted(meetings)],sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def answer(w,c,projects,question):
 ps={p['id']:p for p in projects};q=re.sub(r'\s+','',question).lower()
 topics=[t for t in w.all_records(c,'change_topic') if t['project_id'] in ps]
 named=[t for t in topics if re.sub(r'\s+','',t['title']).lower() in q]
 if named:topics=named
 elif any(k in q for k in ('납기','납품일','납품기한')):topics=[t for t in topics if t['category']=='납기']
 elif '사양' in q:topics=[t for t in topics if t['category']=='사양']
 elif '요구사항' in q:topics=[t for t in topics if t['category']=='요구사항']
 elif not any(k in q for k in ('전체','기준','확정내용','합의내용','최종합의')):
  topics=[t for t in topics if any(len(word)>=2 and word.lower() in q for word in t['title'].split())]
 events=w.all_records(c,'change_event');meetings={m['id']:m for m in w.all_records(c,'meeting')}
 points=[];sources=[];unavailable=0
 for topic in sorted(topics,key=lambda t:(t['project_id'],t['title'])):
  accepted=sorted([e for e in events if e.get('topic_id')==topic['id'] and e['review_state']=='확인됨' and e['business_state']=='확정' and not e.get('superseded_by_revision')],key=lambda e:(e['effective_date'],e.get('confirmed_at','')))
  if not accepted:continue
  e=accepted[-1];m=meetings.get(e['meeting_id']);doc=revision_document(m,e['source_revision']) if m else None
  if not doc:unavailable+=1;continue
  sid='S'+str(len(sources)+1);p=ps[topic['project_id']]
  lines={line['id']:line['text'] for line in document_lines(doc)}
  refs=[ref for ref in e['evidence'] if ref in lines]
  if not refs:unavailable+=1;continue
  text=topic['title']+': '+e['after']
  points.append({'text':text,'sources':[sid],'project_id':p['id'],'project_name':p['name']})
  sources.append({k:v for k,v in doc.items() if k!='body'}|{'id':sid,'project_name':p['name'],
   'line_ids':refs,'text':'\n'.join(lines[r] for r in refs),'event_id':e['id'],
   'review_status':'기준 반영 확인','score':1.0})
 return {'kind':'documents','mode':'baseline','answerable':bool(points),'points':points,'sources':sources,
  'message':'확인된 프로젝트 기준이 없습니다. 변경이력에서 합의 근거를 확인해 반영해 주세요.' if not points else '',
  'searched_projects':len(projects),'searched_meetings':len({s['meeting_id'] for s in sources}),
  'notice':'변경이력에서 확인·반영된 확정값입니다. 요청·보류·미검토 후보는 포함하지 않습니다.' + (' 원문을 확인할 수 없는 기준은 표시하지 않았습니다.' if unavailable else '')}
