"""Storage backend selection.

With SUPABASE_URL, SUPABASE_ANON_KEY and SUPABASE_DB_URL set (b2-service/.env), every
record, session and permission lives in the Supabase Postgres database and sign-in is
checked by Supabase Auth. Without them the service keeps its local SQLite file and the
local test sign-in, which the automated checks use.
"""
import os, sqlite3, threading
from contextlib import contextmanager
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
TESTING=os.environ.get('B2_TEAM_TESTING')=='1'


def load_env(path):
 """KEY=VALUE lines only. Values already in the process environment win."""
 if not path.is_file():return
 for raw in path.read_text(encoding='utf-8-sig').splitlines():
  line=raw.strip()
  if not line or line.startswith('#') or '=' not in line:continue
  key,value=line.split('=',1);key=key.strip();value=value.strip()
  if len(value)>=2 and value[0]==value[-1] and value[0] in '"\'':value=value[1:-1]
  if key and key not in os.environ:os.environ[key]=value


# Automated checks must never reach a real project, so they ignore the .env file.
if not TESTING:load_env(ROOT/'.env')


def setting(*names):
 for name in names:
  value=os.environ.get(name,'').strip()
  if value:return value
 return ''


SUPABASE_URL=setting('SUPABASE_URL').rstrip('/')
ANON_KEY=setting('SUPABASE_ANON_KEY','SUPABASE_PUBLISHABLE_KEY','SUPABASE_KEY')
SERVICE_KEY=setting('SUPABASE_SERVICE_ROLE_KEY','SUPABASE_SECRET_KEY')
DB_URL=setting('SUPABASE_DB_URL','DATABASE_URL')
ADMIN_EMAILS={x.strip().lower() for x in setting('B2_ADMIN_EMAILS').split(',') if x.strip()}
_given=[bool(SUPABASE_URL),bool(ANON_KEY),bool(DB_URL)]
if any(_given) and not all(_given):
 raise RuntimeError('Supabase 연결에는 SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_DB_URL 세 값이 모두 필요합니다. b2-service/.env 를 확인해 주세요.')
if SUPABASE_URL and not (SUPABASE_URL.startswith('https://') or SUPABASE_URL.startswith('http://127.0.0.1') or SUPABASE_URL.startswith('http://localhost')):
 raise RuntimeError('SUPABASE_URL 은 https:// 로 시작해야 합니다.')
SHARED=all(_given)
SCHEMA_FILE=ROOT/'supabase'/'schema.sql'
# One writer at a time, as with SQLite's BEGIN IMMEDIATE. Records are read, changed in
# Python and written back, so two concurrent writers would otherwise lose an update.
WRITE_LOCK=815001
POOL=None
# Column that records insertion order in the records table.
INSERT_ORDER='seq' if SHARED else 'rowid'
_pool_lock=threading.Lock()


class Row(tuple):
 """Index by position or by column name, like sqlite3.Row."""
 def __new__(cls,values,index):
  row=super().__new__(cls,values);row._index=index;return row
 def __getitem__(self,key):
  if isinstance(key,str):return tuple.__getitem__(self,self._index[key])
  return tuple.__getitem__(self,key)
 def keys(self):return list(self._index)


def row_factory(cursor):
 index={column.name:i for i,column in enumerate(cursor.description or [])}
 return lambda values:Row(values,index)


class Empty:
 rowcount=0
 def fetchone(self):return None
 def fetchall(self):return []
 def __iter__(self):return iter(())


class Cursor:
 def __init__(self,cursor):self.cursor=cursor
 @property
 def rowcount(self):return self.cursor.rowcount
 def fetchone(self):return self.cursor.fetchone() if self.cursor.description else None
 def fetchall(self):return self.cursor.fetchall() if self.cursor.description else []
 def __iter__(self):return iter(self.fetchall())


class PostgresConnection:
 """The small part of sqlite3.Connection this service uses, on a psycopg connection."""
 def __init__(self,raw):self.raw=raw;self.dirty=False
 def execute(self,sql,params=()):
  head=sql.lstrip()[:8].upper()
  if head.startswith('PRAGMA'):return Empty()
  # After its first write a transaction sees rows that may still be rolled back.
  if not head.startswith('SELECT'):self.dirty=True
  if head.startswith('BEGIN'):
   self.raw.execute('SELECT pg_advisory_xact_lock(%s)',(WRITE_LOCK,));return Empty()
  params=tuple(params)
  if not params:return Cursor(self.raw.execute(sql))
  return Cursor(self.raw.execute(sql.replace('%','%%').replace('?','%s'),params))
 def executemany(self,sql,rows):
  for row in rows:self.execute(sql,row)
 def commit(self):self.raw.commit()
 def rollback(self):self.raw.rollback()


def open_pool():
 global POOL
 with _pool_lock:
  if POOL is not None:return POOL
  try:
   from psycopg_pool import ConnectionPool
  except ImportError as exc:
   raise RuntimeError('Supabase 연결에 필요한 psycopg 가 설치되어 있지 않습니다. 01_처음한번_설치.cmd 를 다시 실행해 주세요.') from exc
  # prepare_threshold=None keeps the connection usable through Supabase's pooler.
  options={'row_factory':row_factory,'prepare_threshold':None,'connect_timeout':15}
  # Supabase is reached over the Internet; never fall back to an unencrypted connection.
  if 'supabase' in DB_URL and 'sslmode' not in DB_URL:options['sslmode']='require'
  pool=ConnectionPool(DB_URL,min_size=1,max_size=int(os.environ.get('SUPABASE_DB_POOL','5')),timeout=20,open=True,kwargs=options,
   # Supabase closes idle connections; test each one before it is handed out.
   check=getattr(ConnectionPool,'check_connection',None),max_idle=300,max_lifetime=1800)
  try:pool.wait(timeout=20)
  except Exception as exc:
   pool.close()
   raise RuntimeError('Supabase 데이터베이스에 연결하지 못했습니다. b2-service/.env 의 SUPABASE_DB_URL(Session pooler 주소, 비밀번호)과 네트워크를 확인해 주세요.') from exc
  POOL=pool
  return POOL


@contextmanager
def connect(sqlite_path):
 if SHARED:
  with (POOL or open_pool()).connection() as raw:
   yield PostgresConnection(raw)
  return
 c=sqlite3.connect(sqlite_path,timeout=20);c.row_factory=sqlite3.Row
 try:
  with c:yield c
 finally:c.close()


_records={}
def cached_payloads(c,kind):
 """Every record of a kind, re-read from Supabase only after that kind has changed.

 The screen refreshes every few seconds and each refresh reads whole record sets. A
 trigger numbers every change per kind, so an unchanged set costs one small query.
 Returns None when the caller must read directly (SQLite, or a transaction that wrote).
 """
 if not isinstance(c,PostgresConnection) or c.dirty:return None
 row=c.execute('SELECT version FROM record_versions WHERE kind=?',(kind,)).fetchone()
 version=row[0] if row else 0
 held=_records.get(kind)
 if held and held[0]==version:return held[1]
 payloads=[r[0] for r in c.execute('SELECT payload FROM records WHERE kind=?',(kind,))]
 _records[kind]=(version,payloads)
 return payloads


def ensure_schema(c):
 """Create the tables on first start. The same file can be pasted into the SQL editor."""
 if c.execute("SELECT to_regclass('public.records') IS NOT NULL AND to_regclass('public.role_permissions') IS NOT NULL AND to_regclass('public.record_versions') IS NOT NULL").fetchone()[0]:return
 c.execute(SCHEMA_FILE.read_text(encoding='utf-8'))


PERSON_COLUMNS="id::text AS id,name,department,position,level,active"
def person(row):
 return {'id':row['id'],'name':row['name'],'department':row['department'],'position':row['position'],'level':row['level'],'active':bool(row['active'])}
def read_person(c,id):
 row=c.execute('SELECT '+PERSON_COLUMNS+' FROM profiles WHERE id::text=?',(str(id),)).fetchone()
 return person(row) if row else None
def all_people(c):
 return [person(row) for row in c.execute('SELECT '+PERSON_COLUMNS+' FROM profiles ORDER BY created_at,id')]
def save_person(c,data):
 c.execute('UPDATE profiles SET name=?,department=?,position=?,level=?,active=? WHERE id::text=?',
  (data['name'],data.get('department') or '',data.get('position') or '',data.get('level') or 'staff',bool(data.get('active',True)),str(data['id'])))
