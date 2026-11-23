"""회의록 청크 벡터 저장소.

retrieval.retrieve()가 쓰는 벡터 캐시를 한 곳으로 모은다. 저장소는 두 가지이다.

* sqlite   : 기존 방식. workspace.sqlite3의 rag_vectors 테이블에 JSON으로 저장하고 numpy로 점수를 계산한다.
* supabase : Supabase(PostgreSQL) + pgvector. 청크 본문·메타데이터·벡터를 meeting_chunks 테이블에 저장하고
             유사도 계산을 DB(match_meeting_chunks 함수)에서 한다.

선택 규칙 (b2-service/.env 또는 환경변수)
  B2_VECTOR_STORE=sqlite | supabase   비우면 SUPABASE_DB_URL이 있을 때 supabase, 없으면 sqlite
  SUPABASE_DB_URL=postgresql://...    Supabase 대시보드 > Connect > Session pooler 연결 문자열

검색 대상(승인본·기간·회의록 범위·권한)은 항상 호출한 쪽이 만든 코퍼스로 정한다.
저장소는 그 코퍼스의 cache_key 안에서만 점수를 돌려주므로, DB에 오래된 청크가 남아 있어도 답변 근거가 되지 않는다.
Supabase에 연결하지 못하면 서비스가 멈추지 않도록 sqlite로 전환하고 실행 창에 한 번 알린다.

자동 재색인 (install)
  회의록·프로젝트가 저장될 때(등록·본문 수정·PM 확정·휴지통 이동·복원) 해당 프로젝트를 백그라운드에서 다시 색인한다.
  검색에 쓰이는 본문(registered_document)이나 삭제 상태가 실제로 바뀐 경우에만 예약하고, 2초 안의 연속 저장은 한 번으로 묶는다.
  B2_VECTOR_AUTOSYNC=0 이면 끈다. 꺼져 있어도 질문할 때 필요한 청크는 지금처럼 바로 색인된다.

점검:    ..\\b2-model\\.venv\\Scripts\\python.exe -m work.v17.rag_store --check
전체 색인: ..\\b2-model\\.venv\\Scripts\\python.exe -m work.v17.rag_store --reindex
"""
import json,os,sys,time,threading
from datetime import date

TABLE_SQL='CREATE TABLE IF NOT EXISTS rag_vectors(project_id TEXT,cache_key TEXT,vector TEXT,PRIMARY KEY(project_id,cache_key))'
_state={'down_until':0.0,'warned':''}
_lock=threading.Lock()


_env_loaded=False


def _load_env():
 # mailer.py와 같은 .env를 프로세스에서 한 번만 읽는다. 실제 환경변수가 우선한다.
 # 매번 읽으면 실행 중에 지운 설정(테스트의 delenv 등)이 되살아난다.
 global _env_loaded
 if _env_loaded:return
 _env_loaded=True
 try:
  from work.v3.mailer import load_env
  load_env()
 except Exception:pass


def _warn(message):
 with _lock:
  if _state['warned']==message:return
  _state['warned']=message
 print('[vector-store] '+message,file=sys.stderr,flush=True)


def configured_backend():
 _load_env()
 name=(os.environ.get('B2_VECTOR_STORE') or '').strip().lower()
 if name in ('sqlite','local'):return 'sqlite'
 if name in ('supabase','pgvector','postgres'):return 'supabase'
 return 'supabase' if os.environ.get('SUPABASE_DB_URL') else 'sqlite'


class StoreUnavailable(Exception):
 """원격 저장소를 쓸 수 없을 때. 호출 쪽은 sqlite로 다시 실행한다."""


class SQLiteStore:
 name='sqlite'

 def __init__(self,w):
  self.w=w;self._vectors={}

 def _load(self,project_id):
  if project_id not in self._vectors:
   with self.w.connect() as c:
    c.execute(TABLE_SQL)
    self._vectors[project_id]={r[0]:json.loads(r[1]) for r in c.execute('SELECT cache_key,vector FROM rag_vectors WHERE project_id=?',(project_id,))}
  return self._vectors[project_id]

 def existing(self,project_id,keys):
  cached=self._load(project_id)
  return {k for k in keys if k in cached}

 def upsert(self,project_id,rows):
  if not rows:return
  cached=self._load(project_id)
  with self.w.connect() as c:
   c.execute(TABLE_SQL)
   c.executemany('INSERT OR REPLACE INTO rag_vectors VALUES(?,?,?)',[(project_id,r['cache_key'],json.dumps(r['vector'])) for r in rows])
  cached.update({r['cache_key']:r['vector'] for r in rows})

 def prune(self,project_id,keep):
  cached=self._load(project_id);stale=set(cached)-set(keep)
  if not stale:return
  with self.w.connect() as c:
   c.executemany('DELETE FROM rag_vectors WHERE project_id=? AND cache_key=?',[(project_id,k) for k in stale])
  for k in stale:cached.pop(k,None)

 def scores(self,project_id,keys,query):
  import numpy as np
  cached=self._load(project_id);keys=[k for k in dict.fromkeys(keys) if k in cached]
  if not keys:return {}
  values=np.asarray([cached[k] for k in keys])@np.asarray(query)
  return {k:float(v) for k,v in zip(keys,values)}

 def delete_project(self,project_id,c=None):
  def run(c):
   if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rag_vectors'").fetchone():
    c.execute('DELETE FROM rag_vectors WHERE project_id=?',(project_id,))
  if c is not None:run(c)
  else:
   with self.w.connect() as c:run(c)
  self._vectors.pop(project_id,None)


def _vector_literal(vector):
 return '['+','.join(format(float(x),'.7g') for x in vector)+']'


def _meeting_date(value):
 try:return date.fromisoformat(str(value)[:10]) if value else None
 except ValueError:return None


class SupabaseStore:
 name='supabase'

 def __init__(self,url=None):
  _load_env()
  self.url=url or os.environ.get('SUPABASE_DB_URL','')
  if not self.url:raise StoreUnavailable('SUPABASE_DB_URL이 설정되지 않았습니다.')
  try:import psycopg
  except ImportError as exc:raise StoreUnavailable('psycopg가 설치되지 않았습니다. requirements-vector.txt를 설치해 주세요.') from exc
  self._psycopg=psycopg

 def _run(self,sql,params=(),many=False,fetch=False):
  try:
   with self._psycopg.connect(self.url,autocommit=True,connect_timeout=5,prepare_threshold=None) as con:
    with con.cursor() as cur:
     if many:cur.executemany(sql,params)
     else:cur.execute(sql,params)
     return cur.fetchall() if fetch else None
  except self._psycopg.Error as exc:
   raise StoreUnavailable(str(exc).strip().splitlines()[0][:200]) from exc

 def existing(self,project_id,keys):
  keys=list(dict.fromkeys(keys))
  if not keys:return set()
  rows=self._run('select cache_key from public.meeting_chunks where project_id=%s and cache_key=any(%s)',(project_id,keys),fetch=True)
  return {r[0] for r in rows}

 def upsert(self,project_id,rows):
  if not rows:return
  from work.v17.retrieval import MODEL_KEY
  sql='''insert into public.meeting_chunks
   (project_id,cache_key,meeting_id,revision,review_status,meeting_date,title,line_ids,content,embedding,model_key)
   values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::extensions.vector,%s)
   on conflict (project_id,cache_key) do update set
    meeting_id=excluded.meeting_id,revision=excluded.revision,review_status=excluded.review_status,
    meeting_date=excluded.meeting_date,title=excluded.title,line_ids=excluded.line_ids,
    content=excluded.content,embedding=excluded.embedding,model_key=excluded.model_key'''
  params=[]
  for r in rows:
   p=r.get('passage') or {}
   params.append((project_id,r['cache_key'],str(p.get('meeting_id','')),int(p.get('revision') or 0),p.get('review_status','검토 완료'),
                  _meeting_date(p.get('date')),p.get('title',''),list(p.get('line_ids') or []),p.get('text',''),
                  _vector_literal(r['vector']),MODEL_KEY))
  self._run(sql,params,many=True)

 def prune(self,project_id,keep):
  self._run('delete from public.meeting_chunks where project_id=%s and not (cache_key=any(%s))',(project_id,list(set(keep))))

 def scores(self,project_id,keys,query):
  keys=list(dict.fromkeys(keys))
  if not keys:return {}
  rows=self._run('select cache_key,similarity from public.match_meeting_chunks(%s::extensions.vector,%s,%s,%s)',
                 (_vector_literal(query),project_id,keys,len(keys)),fetch=True)
  # e5 벡터는 정규화되어 있어 코사인 유사도 = 기존 numpy 내적 점수
  return {r[0]:float(r[1]) for r in rows}

 def delete_project(self,project_id,c=None):
  self._run('delete from public.meeting_chunks where project_id=%s',(project_id,))

 def check(self):
  rows=self._run("select extversion from pg_extension where extname='vector'",fetch=True)
  if not rows:raise StoreUnavailable('pgvector 확장이 켜져 있지 않습니다. supabase_pgvector.sql을 먼저 실행해 주세요.')
  count=self._run('select count(*),count(distinct project_id) from public.meeting_chunks',fetch=True)[0]
  return {'pgvector':rows[0][0],'chunks':count[0],'projects':count[1]}


def run(w,operation):
 """operation(store)를 설정된 저장소로 실행한다. Supabase 오류 시 60초 동안 sqlite로 전환한다."""
 if configured_backend()=='supabase' and time.time()>=_state['down_until']:
  try:
   result=operation(SupabaseStore())
   with _lock:_state['warned']=''
   return result
  except StoreUnavailable as exc:
   _state['down_until']=time.time()+60
   _warn('Supabase 벡터 저장소를 사용하지 못해 로컬(sqlite) 검색으로 전환합니다: '+str(exc))
 return operation(SQLiteStore(w))


def forget_project(w,project_id,c=None):
 """프로젝트·회의록 영구 삭제 후 해당 프로젝트 벡터를 지운다. 다음 질문 때 남은 회의록으로 다시 색인된다."""
 SQLiteStore(w).delete_project(project_id,c)
 if configured_backend()=='supabase':
  try:SupabaseStore().delete_project(project_id)
  except StoreUnavailable as exc:
   _warn('Supabase 벡터 삭제에 실패했습니다. 검색 대상에는 포함되지 않지만 DB에서 직접 지워 주세요: '+str(exc))


def index_project(w,project_id):
 """프로젝트의 검색 가능한 회의록(질문 때와 같은 registered_document 기준)을 색인하고 남은 청크를 지운다."""
 from work.v17 import retrieval
 with w.connect() as c:
  project=c.execute("SELECT payload FROM records WHERE kind='project' AND id=?",(project_id,)).fetchone()
  project=json.loads(project[0]) if project else None
  meetings=[m for m in w.all_records(c,'meeting') if m.get('project_id')==project_id]
 if not project or project.get('deleted_at'):
  forget_project(w,project_id)
  return {'project_id':project_id,'store':configured_backend(),'indexed':0,'chunks':0,'removed_project':True}
 docs=[d for m in meetings if (d:=retrieval.registered_document(m))]
 passages=retrieval.chunks(docs)
 keys=[retrieval.passage_key(p) for p in passages]
 by_key=dict(zip(keys,passages))
 def operation(store):
  existing=store.existing(project_id,keys) if keys else set()
  missing=[k for k in dict.fromkeys(keys) if k not in existing]
  if missing:
   values=retrieval.embed([retrieval.passage_text(by_key[k]) for k in missing],'passage: ')
   store.upsert(project_id,[{'cache_key':k,'vector':v,'passage':by_key[k]} for k,v in zip(missing,values)])
  store.prune(project_id,keys)
  return {'project_id':project_id,'store':store.name,'indexed':len(missing),'chunks':len(set(keys)),'removed_project':False}
 return run(w,operation)


def _signature(kind,data):
 # 검색 결과에 영향을 주는 값만 비교한다. 분석 진행률 같은 저장은 재색인을 예약하지 않는다.
 if kind=='project':return ('project',bool(data.get('deleted_at')))
 from work.v17.retrieval import registered_document
 doc=registered_document(data)
 return ('meeting',data.get('project_id'),doc['fingerprint'] if doc else None)


class Reindexer:
 """저장 직후 프로젝트 단위로 모아 백그라운드 스레드 하나에서 순서대로 재색인한다."""

 def __init__(self,w,delay=2.0):
  self.w=w;self.delay=delay;self.pending={};self.seen={}
  self.cond=threading.Condition();self.thread=None;self.busy=False;self.last=None

 def notice(self,kind,data):
  if kind not in ('meeting','project') or not isinstance(data,dict) or not data.get('id'):return
  pid=data.get('project_id') if kind=='meeting' else data.get('id')
  if not pid:return
  try:sig=_signature(kind,data)
  except Exception:sig=None
  key=(kind,data['id'])
  with self.cond:
   if key in self.seen and self.seen[key]==sig:return
   self.seen[key]=sig
  # 저장 트랜잭션이 끝난 뒤 실행되도록 잠시 기다린다. 롤백되어도 실제 DB 상태로 색인하므로 안전하다.
  self.schedule(pid)

 def schedule(self,project_id,delay=None):
  with self.cond:
   self.pending[project_id]=time.time()+(self.delay if delay is None else delay)
   if self.thread is None:
    self.thread=threading.Thread(target=self._loop,name='vector-reindex',daemon=True);self.thread.start()
   self.cond.notify()

 def _loop(self):
  while True:
   with self.cond:
    while not self.pending:
     if not self.cond.wait(timeout=30) and not self.pending:
      self.thread=None;return
    pid,due=min(self.pending.items(),key=lambda x:x[1])
    wait=due-time.time()
    if wait>0:self.cond.wait(timeout=wait);continue
    self.pending.pop(pid);self.busy=True
   try:self.last=index_project(self.w,pid)
   except (ImportError,ValueError) as exc:
    # AI 환경(torch·검색 모델)이 없는 PC: 화면 기능은 그대로 두고 알리기만 한다.
    _warn('검색 모델을 쓸 수 없어 자동 재색인을 건너뜁니다: '+str(exc)[:160])
   except Exception as exc:
    _warn('자동 재색인 중 오류가 있었습니다. 질문할 때 다시 색인합니다: '+repr(exc)[:200])
   finally:
    with self.cond:self.busy=False;self.cond.notify_all()

 def wait_idle(self,timeout=30):
  """테스트·CLI용: 예약된 재색인이 모두 끝날 때까지 기다린다."""
  end=time.time()+timeout
  with self.cond:
   while self.pending or self.busy:
    left=end-time.time()
    if left<=0:return False
    for pid in self.pending:self.pending[pid]=min(self.pending[pid],time.time())
    self.cond.notify_all();self.cond.wait(timeout=min(left,0.2))
  return True


_reindexer=None


def autosync_enabled():
 _load_env()
 value=(os.environ.get('B2_VECTOR_AUTOSYNC') or '').strip().lower()
 if value:return value not in ('0','false','off','no')   # 비어 있으면 기본값
 return 'pytest' not in sys.modules


def install(w):
 """w.save를 감싸 회의록·프로젝트 저장 뒤 재색인을 예약한다. 여러 번 불러도 한 번만 감싼다."""
 global _reindexer
 if not autosync_enabled() or getattr(w.save,'_rag_autosync',False):return _reindexer
 _reindexer=Reindexer(w)
 original=w.save
 def save(c,kind,data):
  result=original(c,kind,data)
  try:_reindexer.notice(kind,data)
  except Exception:pass
  return result
 save._rag_autosync=True;save.__wrapped__=original
 w.save=save
 return _reindexer


def sync_all(w,delay=5.0):
 """서버 시작 시: 삭제되지 않은 모든 프로젝트를 백그라운드에서 한 번 맞춘다(이미 색인된 청크는 건너뜀)."""
 if _reindexer is None:return
 with w.connect() as c:ids=[p['id'] for p in w.all_records(c,'project')]
 for i,pid in enumerate(ids):_reindexer.schedule(pid,delay=delay+i*0.1)


def _main(argv):
 if '--reindex' in argv:
  # 서비스(start.py)와 같은 데이터 폴더를 쓴다.
  from pathlib import Path
  os.environ.setdefault('B2_TEAM_DATA_DIR',str(Path(__file__).resolve().parents[2]/'data'/'v6'))
  from work.v17 import server as w
  with w.connect() as c:ids=[p['id'] for p in w.all_records(c,'project')]
  print('벡터 저장소:',configured_backend(),'· 프로젝트',len(ids),'개 색인 시작')
  for pid in ids:
   r=index_project(w,pid)
   print(f" {pid[:8]} · {r['store']} · 청크 {r['chunks']}개 · 새로 색인 {r['indexed']}개")
  return 0
 if '--check' not in argv:
  print(__doc__);return 0
 backend=configured_backend();print('설정된 벡터 저장소:',backend)
 if backend!='supabase':
  print('로컬(sqlite) 저장소를 사용합니다. Supabase를 쓰려면 .env에 SUPABASE_DB_URL을 넣어 주세요.');return 0
 try:info=SupabaseStore().check()
 except StoreUnavailable as exc:
  print('VECTOR STORE: NOT READY -',exc);return 1
 print('VECTOR STORE: READY · pgvector',info['pgvector'],'· 청크',info['chunks'],'개 · 프로젝트',info['projects'],'개');return 0


if __name__=='__main__':sys.exit(_main(sys.argv[1:]))
