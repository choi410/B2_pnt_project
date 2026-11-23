"""Vector store switch: sqlite keeps prior ranking; pgvector path only scores the request corpus."""
import hashlib,sqlite3
from contextlib import contextmanager
import pytest
from work.v17 import retrieval,rag_store


class Workspace:
 def __init__(self,path):self.path=path
 @contextmanager
 def connect(self):
  c=sqlite3.connect(self.path)
  try:
   with c:yield c
  finally:c.close()


def fake_embed(texts,prefix):
 # Deterministic normalized vectors from character bigrams; no model download needed.
 import numpy as np
 out=[]
 for t in texts:
  v=np.zeros(64)
  for a,b in zip(t,t[1:]):v[int(hashlib.md5((a+b).encode()).hexdigest(),16)%64]+=1
  out.append((v/(np.linalg.norm(v) or 1)).tolist())
 return out


def doc(mid,body,date='2026-11-10'):
 return {'meeting_id':mid,'project_id':'p1','revision':1,'title':'회의 '+mid,'date':date,'body':body,
         'fingerprint':mid,'has_draft':False,'review_status':'검토 완료'}


DOCS=[doc('m1','논의: 롤프레스 속도 120 m/min 유지\n결정: 속도 135 m/min로 합의\n후속 조치: 김양일 도면 제출'),
      doc('m2','논의: 납기 12/18 요청\n결정: 납기 12/23으로 변경 보류\n추가 확인: 커버 요청 철회',date='2026-11-17')]


class MemoryPgStore:
 """Stands in for SupabaseStore: stores rows remotely and scores in the 'DB'."""
 name='supabase'
 rows={}
 def existing(self,pid,keys):return {k for k in keys if (pid,k) in self.rows}
 def upsert(self,pid,rows):
  for r in rows:self.rows[(pid,r['cache_key'])]=r
 def prune(self,pid,keep):
  for k in [k for p,k in self.rows if p==pid and k not in set(keep)]:self.rows.pop((pid,k))
 def scores(self,pid,keys,query):
  import numpy as np
  return {k:float(np.dot(self.rows[(pid,k)]['vector'],query)) for k in keys if (pid,k) in self.rows}
 def delete_project(self,pid,c=None):
  for key in [x for x in self.rows if x[0]==pid]:self.rows.pop(key)


@pytest.fixture
def ws(tmp_path,monkeypatch):
 monkeypatch.setattr(retrieval,'embed',fake_embed)
 monkeypatch.setenv('B2_VECTOR_STORE','sqlite')
 rag_store._state.update(down_until=0.0,warned='')
 return Workspace(tmp_path/'w.sqlite3')


def test_sqlite_store_caches_and_ranks(ws):
 first=retrieval.retrieve(ws,'p1',DOCS,'롤프레스 속도 합의')
 assert first and first[0]['meeting_id']=='m1'
 with ws.connect() as c:count=c.execute('SELECT count(*) FROM rag_vectors').fetchone()[0]
 assert count>0
 assert retrieval.retrieve(ws,'p1',DOCS,'롤프레스 속도 합의')==first


def test_pgvector_store_matches_sqlite_ranking(ws,monkeypatch):
 expected=retrieval.retrieve(ws,'p1',DOCS,'납기 변경')
 MemoryPgStore.rows={}
 monkeypatch.setenv('B2_VECTOR_STORE','supabase')
 monkeypatch.setattr(rag_store,'SupabaseStore',MemoryPgStore)
 traces=[]
 got=retrieval.retrieve(ws,'p1',DOCS,'납기 변경',trace=lambda stage,**v:traces.append(v))
 assert got==expected
 assert traces[-1]['vector_store']=='supabase' and MemoryPgStore.rows


def test_stale_remote_rows_never_become_evidence(ws,monkeypatch):
 MemoryPgStore.rows={}
 monkeypatch.setenv('B2_VECTOR_STORE','supabase')
 monkeypatch.setattr(rag_store,'SupabaseStore',MemoryPgStore)
 retrieval.retrieve(ws,'p1',DOCS,'납기',prune_cache=False)
 got=retrieval.retrieve(ws,'p1',DOCS[:1],'납기',prune_cache=False)
 assert {s['meeting_id'] for s in got}<={'m1'}


def test_supabase_failure_falls_back_to_sqlite(ws,monkeypatch,capsys):
 class Broken:
  def __init__(self):raise rag_store.StoreUnavailable('connection refused')
 monkeypatch.setenv('B2_VECTOR_STORE','supabase')
 monkeypatch.setattr(rag_store,'SupabaseStore',Broken)
 traces=[]
 got=retrieval.retrieve(ws,'p1',DOCS,'롤프레스 속도',trace=lambda stage,**v:traces.append(v))
 assert got and traces[-1]['vector_store']=='sqlite'
 assert '로컬(sqlite)' in capsys.readouterr().err


def test_forget_project_clears_both_stores(ws,monkeypatch):
 MemoryPgStore.rows={}
 monkeypatch.setenv('B2_VECTOR_STORE','supabase')
 monkeypatch.setattr(rag_store,'SupabaseStore',MemoryPgStore)
 retrieval.retrieve(ws,'p1',DOCS,'납기')
 rag_store.SQLiteStore(ws).upsert('p1',[{'cache_key':'k','vector':[1.0]}])
 rag_store.forget_project(ws,'p1')
 with ws.connect() as c:assert c.execute('SELECT count(*) FROM rag_vectors').fetchone()[0]==0
 assert not MemoryPgStore.rows


def test_vector_literal_and_backend_choice(monkeypatch):
 assert rag_store._vector_literal([0.5,1,-0.25])=='[0.5,1,-0.25]'
 monkeypatch.delenv('B2_VECTOR_STORE',raising=False)
 monkeypatch.setenv('SUPABASE_DB_URL','postgresql://example')
 assert rag_store.configured_backend()=='supabase'
 monkeypatch.setenv('B2_VECTOR_STORE','sqlite')
 assert rag_store.configured_backend()=='sqlite'


class SavingWorkspace(Workspace):
 """Minimal stand-in for work.v17.server: records table + save/all_records."""
 def __init__(self,path):
  super().__init__(path)
  with self.connect() as c:c.execute('CREATE TABLE records(kind TEXT,id TEXT,payload TEXT,PRIMARY KEY(kind,id))')
 def save(self,c,kind,data):
  import json
  c.execute('INSERT OR REPLACE INTO records VALUES(?,?,?)',(kind,data['id'],json.dumps(data,ensure_ascii=False)))
 def all_records(self,c,kind,include_archived=False):
  import json
  rows=[json.loads(r[0]) for r in c.execute('SELECT payload FROM records WHERE kind=?',(kind,))]
  return [r for r in rows if include_archived or kind!='project' or not r.get('deleted_at')]


def meeting(mid,body,status='확정',**extra):
 return {'id':mid,'project_id':'p1','revision':1,'approved_revision':1 if status=='확정' else None,'title':'회의 '+mid,
         'revisions':[{'number':1,'title':'회의 '+mid,'date':'2026-11-10','body':body,'status':status}],**extra}


def stored_keys(ws):
 with ws.connect() as c:
  if not c.execute("SELECT 1 FROM sqlite_master WHERE name='rag_vectors'").fetchone():return set()
  return {r[0] for r in c.execute("SELECT cache_key FROM rag_vectors WHERE project_id='p1'")}


@pytest.fixture
def auto(tmp_path,monkeypatch):
 monkeypatch.setattr(retrieval,'embed',fake_embed)
 monkeypatch.setenv('B2_VECTOR_STORE','sqlite')
 monkeypatch.setenv('B2_VECTOR_AUTOSYNC','1')
 ws=SavingWorkspace(tmp_path/'auto.sqlite3')
 reindexer=rag_store.install(ws);reindexer.delay=0.05
 with ws.connect() as c:ws.save(c,'project',{'id':'p1','name':'롤프레스'})
 return ws,reindexer


def test_approval_indexes_and_trash_removes(auto):
 ws,r=auto
 with ws.connect() as c:ws.save(c,'meeting',meeting('m1','결정: 속도 135 m/min로 합의\n후속 조치: 도면 제출'))
 assert r.wait_idle() and stored_keys(ws)
 with ws.connect() as c:ws.save(c,'meeting',meeting('m1','결정: 속도 135 m/min로 합의\n후속 조치: 도면 제출',deleted_at='2026-11-23'))
 assert r.wait_idle() and not stored_keys(ws)


def test_unapproved_draft_is_not_indexed(auto):
 ws,r=auto
 with ws.connect() as c:ws.save(c,'meeting',meeting('m2','논의: 납기 12/23 검토',status='작성 중'))
 assert r.wait_idle() and not stored_keys(ws)


def test_source_edit_replaces_old_chunks(auto):
 ws,r=auto
 with ws.connect() as c:ws.save(c,'meeting',meeting('m1','결정: 납기 12/18 유지'))
 r.wait_idle();before=stored_keys(ws)
 with ws.connect() as c:ws.save(c,'meeting',meeting('m1','결정: 납기 12/23으로 변경'))
 r.wait_idle();after=stored_keys(ws)
 assert before and after and not before&after


def test_unrelated_save_does_not_reschedule(auto):
 ws,r=auto
 m=meeting('m1','결정: 속도 합의')
 with ws.connect() as c:ws.save(c,'meeting',m)
 r.wait_idle();first=r.last
 with ws.connect() as c:ws.save(c,'meeting',{**m,'analysis_state':'done'})
 r.wait_idle()
 assert r.last is first and not r.pending


def test_trashed_project_forgets_vectors(auto):
 ws,r=auto
 with ws.connect() as c:ws.save(c,'meeting',meeting('m1','결정: 속도 합의'))
 r.wait_idle()
 with ws.connect() as c:ws.save(c,'project',{'id':'p1','name':'롤프레스','deleted_at':'2026-11-23'})
 assert r.wait_idle() and not stored_keys(ws)
