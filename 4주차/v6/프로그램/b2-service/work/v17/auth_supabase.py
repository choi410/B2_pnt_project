"""Supabase Auth 로그인.

흐름
  0. 로그인 아이디(employees.app_user_id, 예: team1·admin)로 그 직원의 이메일을 서버에서 찾는다.
     (Supabase Auth는 이메일로만 비밀번호를 확인하므로, 이메일은 화면에 보이지 않고 서버 안에서만 쓴다.)
  1. 이메일·비밀번호를 Supabase Auth(/auth/v1/token)에 확인한다.
  2. 받은 사용자 토큰으로 public.employees에서 "내 행"을 읽는다 (RLS: auth_user_id = auth.uid()).
  3. account_status가 active가 아니면 거부한다.
  4. employees.app_user_id(team1·admin 등)로 기존 서비스의 사람 기록(person)을 맞추고,
     지금 쓰는 세션 쿠키를 발급한다. → 나머지 API·데이터는 그대로 동작한다.

설정 (b2-service/.env)
  B2_AUTH_MODE=supabase      켜면 이 로그인만 허용하고 이름 선택(체험) 로그인은 막는다. 비우면 기존 방식.
  SUPABASE_URL=https://<프로젝트ID>.supabase.co
  SUPABASE_ANON_KEY=<anon 또는 publishable 키>
  SUPABASE_DB_URL=postgresql://...   아이디→이메일 조회용 (벡터DB와 같은 값)
"""
import json,os,re,time,urllib.error,urllib.parse,urllib.request
from pydantic import BaseModel,ConfigDict,Field

ROLES={'admin':'관리자','pm':'PM','member':'팀원'}
EMPLOYEE_FIELDS='id,emp_no,name,department,position,email,role,account_status,app_user_id'
USER_ID=re.compile(r'^[A-Za-z0-9_.-]{1,64}$')
BAD_LOGIN='아이디 또는 비밀번호를 확인해 주세요.'


class AuthError(Exception):
 def __init__(self,status,message):
  super().__init__(message);self.status=status;self.message=message


_env_loaded=False


def _load_env():
 # .env는 프로세스에서 한 번만 읽는다. 매번 읽으면 실행 중에 지운 설정(테스트의 delenv 등)이 되살아난다.
 global _env_loaded
 if _env_loaded:return
 _env_loaded=True
 try:
  from work.v3.mailer import load_env
  load_env()
 except Exception:pass


_load_env()


def settings():
 _load_env()
 return {'mode':(os.environ.get('B2_AUTH_MODE') or '').strip().lower(),
         'url':(os.environ.get('SUPABASE_URL') or '').strip().rstrip('/'),
         'key':(os.environ.get('SUPABASE_ANON_KEY') or '').strip()}


def enabled():
 return settings()['mode']=='supabase'


def _request(method,url,key,body=None,token=None,timeout=8):
 headers={'apikey':key,'Accept':'application/json'}
 # 새 publishable 키(sb_publishable_)는 JWT가 아니므로 Authorization에 넣지 않는다.
 if token:headers['Authorization']='Bearer '+token
 elif key.startswith('eyJ'):headers['Authorization']='Bearer '+key
 data=None
 if body is not None:
  data=json.dumps(body).encode('utf-8');headers['Content-Type']='application/json'
 req=urllib.request.Request(url,data=data,headers=headers,method=method)
 try:
  with urllib.request.urlopen(req,timeout=timeout) as res:
   return res.status,json.loads(res.read().decode('utf-8') or 'null')
 except urllib.error.HTTPError as exc:
  try:payload=json.loads(exc.read().decode('utf-8') or 'null')
  except ValueError:payload=None
  return exc.code,payload
 except (urllib.error.URLError,OSError,TimeoutError) as exc:
  raise AuthError(503,'로그인 서버(Supabase)에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요.') from exc


def email_for(user_id):
 """로그인 아이디 → 이메일. 없는 아이디는 None (어떤 아이디가 있는지 알려 주지 않도록 호출 쪽에서 같은 오류로 처리)."""
 from work.v17 import supabase_db
 try:rows=supabase_db.run('select email from public.employees where app_user_id=%s',(user_id,))
 except supabase_db.DbError as exc:raise AuthError(exc.status,exc.message) from None
 return (rows[0].get('email') or None) if rows else None


def normalize_id(user_id):
 return (user_id or '').strip()


def authenticate(user_id,password,request=_request,lookup=None):
 """아이디(app_user_id)·비밀번호 확인 후 employees 행을 돌려준다. 실패하면 AuthError."""
 cfg=settings()
 if not cfg['url'] or not cfg['key']:raise AuthError(503,'Supabase 로그인 설정(SUPABASE_URL·SUPABASE_ANON_KEY)이 없습니다.')
 user_id=normalize_id(user_id)
 if not user_id or not password:raise AuthError(422,'아이디와 비밀번호를 입력해 주세요.')
 if not USER_ID.match(user_id):raise AuthError(401,BAD_LOGIN)
 email=(lookup or email_for)(user_id)
 if not email:raise AuthError(401,BAD_LOGIN)
 status,body=request('POST',cfg['url']+'/auth/v1/token?grant_type=password',cfg['key'],{'email':email.strip().lower(),'password':password})
 if status in (400,401):raise AuthError(401,BAD_LOGIN)
 if status==429:raise AuthError(429,'로그인 시도가 많습니다. 잠시 후 다시 시도해 주세요.')
 if status!=200 or not isinstance(body,dict) or not body.get('access_token'):
  raise AuthError(502,'로그인 서버 응답을 확인하지 못했습니다. ('+str(status)+')')
 auth_id=(body.get('user') or {}).get('id')
 query=urllib.parse.urlencode({'select':EMPLOYEE_FIELDS,'auth_user_id':'eq.'+str(auth_id)})
 status,rows=request('GET',cfg['url']+'/rest/v1/employees?'+query,cfg['key'],token=body['access_token'])
 if status!=200:
  detail=(rows or {}).get('message','') if isinstance(rows,dict) else ''
  if 'app_user_id' in detail:raise AuthError(500,'employees.app_user_id 칸이 없습니다. supabase_auth_step2.sql의 [B]를 실행해 주세요.')
  raise AuthError(500,'직원 정보를 읽지 못했습니다. supabase_auth_step2.sql의 [C](RLS 정책)를 확인해 주세요. '+detail[:120])
 if not rows:raise AuthError(403,'직원 정보에 연결되지 않은 계정입니다. 관리자에게 문의해 주세요.')
 emp=rows[0]
 if emp.get('account_status')!='active':raise AuthError(403,'사용이 중지된 계정입니다. 관리자에게 문의해 주세요.')
 if emp.get('role') not in ROLES:raise AuthError(403,'계정 역할이 지정되지 않았습니다. 관리자에게 문의해 주세요.')
 if not emp.get('app_user_id'):raise AuthError(403,'서비스 사용자 ID(app_user_id)가 없는 계정입니다. 관리자에게 문의해 주세요.')
 # 아이디로 찾은 이메일과 실제 로그인한 계정이 같은 직원인지 한 번 더 확인한다.
 if emp['app_user_id']!=user_id:raise AuthError(401,BAD_LOGIN)
 return emp


def person_from(emp,existing=None):
 """employees 행 → 서비스의 person 기록. 기존 기록의 다른 값은 유지한다."""
 person=dict(existing or {})
 person.update(id=emp['app_user_id'],name=emp['name'],department=emp.get('department') or '',
               position=emp.get('position') or ROLES[emp['role']],email=emp.get('email') or '',
               role=emp['role'],role_label=ROLES[emp['role']],employee_id=emp['id'],emp_no=emp.get('emp_no'),
               account_status=emp['account_status'],
               # 기존 코드(can_create_project)가 보는 값. 4단계에서 role 기준으로 바꾼다.
               level='leader' if emp['role']=='pm' else 'staff')
 return person


class IdLogin(BaseModel):
 model_config=ConfigDict(extra='forbid')
 user_id:str=Field(min_length=1,max_length=64)
 password:str=Field(min_length=1,max_length=128)


def build_router(w):
 from fastapi import APIRouter,HTTPException,Request
 from fastapi.responses import JSONResponse
 r=APIRouter(prefix='/api/auth')

 @r.get('/config')
 def config():
  # 프론트엔드가 로그인 화면 종류를 고를 때 쓴다. 키 값은 내보내지 않는다.
  cfg=settings()
  return {'mode':'supabase' if cfg['mode']=='supabase' else 'demo','configured':bool(cfg['url'] and cfg['key'])}

 @r.post('/login')
 def login(body:IdLogin):
  if not enabled():raise HTTPException(403,'Supabase 로그인이 꺼져 있습니다. .env에 B2_AUTH_MODE=supabase를 넣어 주세요.')
  limit_id='user:'+normalize_id(body.user_id).lower()
  with w.connect() as c:
   limit=c.execute('SELECT * FROM login_limits WHERE id=?',(limit_id,)).fetchone()
   if limit and limit['failures']>=8 and time.time()-limit['last']<60:raise HTTPException(429,'잠시 후 다시 로그인해 주세요.')
  try:emp=authenticate(body.user_id,body.password)
  except AuthError as exc:
   if exc.status==401:
    with w.connect() as c:
     c.execute('INSERT INTO login_limits VALUES(?,1,?) ON CONFLICT(id) DO UPDATE SET failures=CASE WHEN last < ? THEN 1 ELSE failures+1 END,last=excluded.last',(limit_id,time.time(),time.time()-60))
   raise HTTPException(exc.status,exc.message) from None
  with w.connect() as c:
   c.execute('DELETE FROM login_limits WHERE id=?',(limit_id,))
   row=c.execute("SELECT payload FROM records WHERE kind='person' AND id=?",(emp['app_user_id'],)).fetchone()
   person=person_from(emp,json.loads(row[0]) if row else None)
   w.save(c,'person',person)
   session=w.issue_session(c,person['id'])
  # 기존 세션 쿠키(httponly, samesite=strict)를 그대로 쓰고, 화면 분기용 역할만 함께 돌려준다.
  res=JSONResponse({'ok':True,'user':{k:person[k] for k in ('id','name','role','role_label')}})
  res.raw_headers.extend(h for h in session.raw_headers if h[0]==b'set-cookie')
  return res

 @r.get('/me')
 def me(req:Request):
  actor=w.user(req)
  return {k:actor.get(k) for k in ('id','name','department','position','email','role','role_label')}

 return r
