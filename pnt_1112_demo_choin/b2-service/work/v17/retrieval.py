"""Local E5 retrieval. The index is built only from the caller's approved project corpus."""
import hashlib,json,re,threading
from pathlib import Path

MODEL_DIR=Path(__file__).resolve().parents[3]/'b2-model'/'models'/'multilingual-e5-small'
MODEL_KEY='e5-small:614241f622f53c4eeff9890bdc4f31cfecc418b3:chunks-v2'
_encoder=None
_tokenizer=None
_lock=threading.Lock()


def fingerprint(value):
 return hashlib.sha256(value.encode()).hexdigest()


def approved_document(m):
 if m.get('deleted_at') or not m.get('approved_revision'):return None
 rev=next((r for r in m.get('revisions',[]) if r['number']==m['approved_revision'] and r.get('status')=='확정'),None)
 if not rev:return None
 body=rev['body']
 return {'meeting_id':m['id'],'project_id':m['project_id'],'revision':rev['number'],
         'title':rev['title'],'date':rev.get('date',''),'body':body,
         'fingerprint':fingerprint(json.dumps([m['project_id'],rev['number'],rev['title'],rev.get('date',''),body],ensure_ascii=False)),
         'has_draft':m['revision']!=rev['number']}


def revision_document(m, number):
 if m.get('deleted_at'):return None
 rev=next((r for r in m.get('revisions',[]) if r['number']==number),None)
 if not rev:return None
 status='검토 완료' if rev.get('status')=='확정' else '보완 요청' if rev.get('status')=='보완 요청' else '작성자 확인'
 return {'meeting_id':m['id'],'project_id':m['project_id'],'revision':number,'title':rev['title'],
         'date':rev.get('date',''),'body':rev['body'],'review_status':status,
         'fingerprint':fingerprint(json.dumps([m['project_id'],number,rev['title'],rev.get('date',''),rev['body'],status],ensure_ascii=False)),
         'has_draft':m['revision']!=number}


def registered_document(m):
 """Registration permits discussion search, not claims about the current baseline."""
 if m.get('registered_revision'):
  return revision_document(m,m['registered_revision'])
 doc=approved_document(m)
 if doc:doc['review_status']='검토 완료'
 return doc


def document_lines(doc):
 return [{'id':'L'+str(i+1).zfill(3),'text':line.strip()} for i,line in enumerate(doc['body'].splitlines()) if line.strip()]


def chunks(docs):
 result=[]
 for d in docs:
  # Small overlapping windows keep an assertion with its qualification.
  lines=document_lines(d);start=0
  while start<len(lines):
   selected=[];size=0
   for line in lines[start:]:
    if selected and (size+len(line['text'])>650 or len(selected)>=6):break
    selected.append(line);size+=len(line['text'])
   # A long individual line is split, rather than silently truncating the document.
   text='\n'.join(x['text'] for x in selected)
   for offset in range(0,max(len(text),1),600):
    part=text[offset:offset+700]
    if not part:continue
    result.append({'meeting_id':d['meeting_id'],'project_id':d['project_id'],'title':d['title'],'date':d['date'],'revision':d['revision'],
                   'fingerprint':d['fingerprint'],'line_ids':[x['id'] for x in selected],
                   'text':part,'has_draft':d['has_draft'],'review_status':d.get('review_status','검토 완료')})
   start+=max(1,len(selected)-1)
 return result


def embed(texts,prefix):
 global _encoder,_tokenizer
 import torch
 from transformers import AutoTokenizer,AutoModel
 with _lock:
  if _encoder is None:
   if not (MODEL_DIR/'model.safetensors').is_file():raise ValueError('검색 모델이 설치되어 있지 않습니다. 서버의 검색 모델 설치를 확인해 주세요.')
   _tokenizer=AutoTokenizer.from_pretrained(MODEL_DIR,local_files_only=True,trust_remote_code=False)
   _encoder=AutoModel.from_pretrained(MODEL_DIR,local_files_only=True,trust_remote_code=False).to('cpu').eval()
  vectors=[]
  for offset in range(0,len(texts),16):
   inputs=texts[offset:offset+16]
   batch=_tokenizer([prefix+text for text in inputs],padding=True,truncation=True,max_length=512,stride=64,return_overflowing_tokens=True,return_tensors='pt')
   mapping=batch.pop('overflow_to_sample_mapping')
   with torch.inference_mode():
    hidden=_encoder(**batch).last_hidden_state
    masked=hidden.masked_fill(~batch['attention_mask'][...,None].bool(),0)
    pooled=masked.sum(dim=1)/batch['attention_mask'].sum(dim=1)[...,None]
    pooled=torch.nn.functional.normalize(pooled,p=2,dim=1)
    merged=torch.zeros((len(inputs),pooled.shape[1]),dtype=pooled.dtype)
    merged.index_add_(0,mapping,pooled)
    vectors.extend(torch.nn.functional.normalize(merged,p=2,dim=1).tolist())
  return vectors


def retrieve(w,project_id,docs,question,limit=6):
 import numpy as np
 passages=chunks(docs)
 if not passages:return []
 texts=[p['title']+'\n'+p['text'] for p in passages]
 keys=[fingerprint(MODEL_KEY+'\n'+t) for t in texts]
 with w.connect() as c:
  c.execute('CREATE TABLE IF NOT EXISTS rag_vectors(project_id TEXT,cache_key TEXT,vector TEXT,PRIMARY KEY(project_id,cache_key))')
  cached={r[0]:json.loads(r[1]) for r in c.execute('SELECT cache_key,vector FROM rag_vectors WHERE project_id=?',(project_id,))}
 missing=list(dict.fromkeys(k for k in keys if k not in cached));text_by_key=dict(zip(keys,texts))
 if missing:
  values=embed([text_by_key[k] for k in missing],'passage: ')
  cached.update(zip(missing,values))
  with w.connect() as c:
   c.executemany('INSERT OR REPLACE INTO rag_vectors VALUES(?,?,?)',[(project_id,k,json.dumps(cached[k])) for k in missing])
 # Remove stale index entries for this project. Every query constructs its eligible
 # corpus anew; old/deleted/draft text is never eligible even before this cleanup.
 with w.connect() as c:
  stale=set(cached)-set(keys)
  c.executemany('DELETE FROM rag_vectors WHERE project_id=? AND cache_key=?',[(project_id,k) for k in stale])
 query=np.asarray(embed([question],'query: ')[0]);matrix=np.asarray([cached[k] for k in keys]);scores=matrix@query
 words=[x for x in re.findall(r'[가-힣A-Za-z0-9]+',question.lower()) if len(x)>1]
 for i,p in enumerate(passages):
  # Exact identifiers/specification terms supplement semantic retrieval.
  lexical=sum(x in texts[i].lower() for x in words)/max(1,len(words))
  p['score']=round(float(scores[i]),5);p['_rank']=float(scores[i])+0.08*lexical
 ranked=sorted(passages,key=lambda p:p['_rank'],reverse=True)
 best=max(p['score'] for p in ranked)
 ranked=[p for p in ranked if p['score']>=best-.06]
 chosen=[]
 # At least one passage per relevant meeting before adding nearby windows.
 for p in ranked:
  if len(chosen)>=limit:break
  if not any(x['meeting_id']==p['meeting_id'] for x in chosen):chosen.append(p)
 for p in ranked:
  if len(chosen)>=limit:break
  if p in chosen:continue
  if any(x['meeting_id']==p['meeting_id'] and len(set(x['line_ids'])&set(p['line_ids']))>=min(len(x['line_ids']),len(p['line_ids']))*.65 for x in chosen):continue
  chosen.append(p)
 chosen.sort(key=lambda p:(p['date'],p['meeting_id'],p['line_ids'][0]))
 # One citation per meeting avoids identical titles pointing to a different
 # window of the same document. Keep the actual selected text and line IDs.
 grouped={}
 for p in chosen:
  if p['meeting_id'] not in grouped:grouped[p['meeting_id']]={**p,'line_ids':list(p['line_ids']),'texts':[p['text']]}
  else:
   group=grouped[p['meeting_id']];group['line_ids']=list(dict.fromkeys(group['line_ids']+p['line_ids']));group['texts'].append(p['text']);group['score']=max(group['score'],p['score'])
 result=[]
 for i,p in enumerate(grouped.values()):
  text='\n'.join(dict.fromkeys(line for part in p['texts'] for line in part.splitlines()))
  result.append({**{k:v for k,v in p.items() if k not in ('_rank','texts')},'text':text,'id':'S'+str(i+1)})
 return result
