"""Supabase PostgreSQL에 백엔드가 직접 접속하는 작은 도우미 (SUPABASE_DB_URL 사용).

로그인 아이디(app_user_id)→이메일 조회와 관리자 화면의 직원 역할·상태 변경에 쓴다.
DB 연결 문자열은 서버의 .env에만 두며 브라우저로 보내지 않는다.
"""
import os


class DbError(Exception):
 def __init__(self,status,message):
  super().__init__(message);self.status=status;self.message=message


def url():
 # rag_store/auth_supabase와 같은 방식으로 .env를 한 번 읽는다.
 from work.v17 import auth_supabase
 auth_supabase._load_env()
 return (os.environ.get('SUPABASE_DB_URL') or '').strip()


def run(sql,params=(),fetch=True):
 """SQL 한 문장을 실행하고 (fetch면) 행 목록을 dict로 돌려준다."""
 target=url()
 if not target:raise DbError(503,'Supabase DB 연결 설정(SUPABASE_DB_URL)이 없습니다.')
 try:import psycopg
 except ImportError as exc:raise DbError(503,'psycopg가 설치되지 않았습니다. 01_처음한번_설치.cmd를 다시 실행해 주세요.') from exc
 try:
  with psycopg.connect(target,autocommit=True,connect_timeout=5,prepare_threshold=None) as con:
   with con.cursor() as cur:
    cur.execute(sql,params)
    if not fetch or cur.description is None:return []
    names=[d.name for d in cur.description]
    return [dict(zip(names,row)) for row in cur.fetchall()]
 except psycopg.Error as exc:
  raise DbError(503,'Supabase DB에 연결하지 못했습니다: '+str(exc).strip().splitlines()[0][:160]) from exc
