"""Supabase sign-in, roles and the management API for users, permissions and project access."""
import re, time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from work.v17 import storage, supabase_auth

EMAIL=re.compile(r'[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s.]{2,}')
LEVELS={'admin':'관리자','leader':'PM','staff':'담당자'}
PERMISSIONS={
 'user.manage':'사용자·권한 관리',
 'project.create':'프로젝트 생성',
 'project.manage_any':'모든 프로젝트의 PM·참여자 지정',
}
# Without this one grant nobody could reach the management screen again.
LOCKED=('admin','user.manage')


def auth_failure(exc):
 if exc.code=='service_key_missing':return HTTPException(503,'계정 생성과 비밀번호 변경에는 SUPABASE_SERVICE_ROLE_KEY 설정이 필요합니다. 설정 전에는 Supabase 대시보드에서 계정을 만들어 주세요.')
 if exc.status==429:return HTTPException(429,'요청이 많습니다. 잠시 후 다시 시도해 주세요.')
 if exc.status>=500 or exc.code=='unreachable':return HTTPException(503,'Supabase 인증 서버에 연결하지 못했습니다. 네트워크와 SUPABASE_URL 을 확인해 주세요.')
 if exc.code in ('email_exists','user_already_exists') or 'already' in exc.message.lower():return HTTPException(409,'이미 등록된 이메일입니다.')
 if exc.code=='weak_password':return HTTPException(422,'더 안전한 비밀번호를 입력해 주세요.')
 if exc.status in (401,403):return HTTPException(503,'Supabase 키가 올바르지 않습니다. b2-service/.env 의 키를 확인해 주세요.')
 return HTTPException(422,'Supabase 가 요청을 처리하지 못했습니다. 입력값을 확인해 주세요.')


def ensure_profile(c,account,email):
 """The profile normally comes from the database trigger; create it here if it is missing."""
 uid=str(account['id'])
 found=storage.read_person(c,uid)
 if not found:
  name=str((account.get('user_metadata') or {}).get('name') or '').strip() or email.split('@')[0]
  c.execute('INSERT INTO profiles(id,email,name) VALUES(?::uuid,?,?) ON CONFLICT(id) DO NOTHING',(uid,email,name[:80]))
 c.execute('UPDATE profiles SET email=? WHERE id::text=? AND email<>?',(email,uid,email))
 if email in storage.ADMIN_EMAILS:c.execute("UPDATE profiles SET level='admin' WHERE id::text=? AND level<>'admin'",(uid,))
 return storage.read_person(c,uid)


def sign_in(w,email,password):
 email=(email or '').strip().lower()
 if not EMAIL.fullmatch(email):raise HTTPException(422,'이메일 주소를 확인해 주세요.')
 with w.connect() as c:
  limit=c.execute('SELECT failures,last FROM login_limits WHERE id=?',(email,)).fetchone()
  if limit and limit['failures']>=8 and time.time()-limit['last']<60:raise HTTPException(429,'잠시 후 다시 로그인해 주세요.')
 try:account=supabase_auth.sign_in(email,password)
 except supabase_auth.AuthError as exc:
  if exc.status==429:raise HTTPException(429,'로그인 시도가 많습니다. 잠시 후 다시 시도해 주세요.')
  if exc.status>=500 or exc.code=='unreachable':raise HTTPException(503,'Supabase 인증 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.')
  if exc.code=='email_not_confirmed':raise HTTPException(403,'이메일 인증이 끝나지 않은 계정입니다. 관리자에게 문의해 주세요.')
  with w.connect() as c:
   c.execute('INSERT INTO login_limits(id,failures,last) VALUES(?,1,?) ON CONFLICT(id) DO UPDATE SET failures=CASE WHEN login_limits.last < ? THEN 1 ELSE login_limits.failures+1 END,last=excluded.last',(email,time.time(),time.time()-60))
  raise HTTPException(401,'이메일 또는 비밀번호를 확인해 주세요.')
 with w.connect() as c:
  c.execute('BEGIN IMMEDIATE')
  found=ensure_profile(c,account,email)
  if not found:raise HTTPException(503,'프로필을 만들지 못했습니다. 관리자에게 문의해 주세요.')
  if not found['active']:raise HTTPException(403,'사용이 중지된 계정입니다. 관리자에게 문의해 주세요.')
  c.execute('DELETE FROM login_limits WHERE id=?',(email,))
  return w.issue_session(c,found['id'])


class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class NewUser(Strict):
 email:str=Field(max_length=254)
 password:str=Field(min_length=8,max_length=72)
 name:str=Field(min_length=1,max_length=80)
 department:str=Field(default='',max_length=80)
 position:str=Field(default='담당자',max_length=80)
 level:str='staff'
class UserEdit(Strict):
 name:str|None=Field(default=None,min_length=1,max_length=80)
 department:str|None=Field(default=None,max_length=80)
 position:str|None=Field(default=None,max_length=80)
 level:str|None=None
 active:bool|None=None
class Password(Strict):password:str=Field(min_length=8,max_length=72)
class Grant(Strict):level:str;permission:str;allowed:bool
class Access(Strict):
 pm_id:str=Field(max_length=80)
 members:list[str]=Field(max_length=500)


def build_router(w):
 r=APIRouter(prefix='/api')
 manage_users=w.require('user.manage')
 def shared():
  if not storage.SHARED:raise HTTPException(404,'Supabase 연결을 설정한 뒤 사용할 수 있습니다.')
 def account_rows(c):
  return [{'id':row['id'],'email':row['email'],'name':row['name'],'department':row['department'],'position':row['position'],'level':row['level'],'active':bool(row['active'])}
   for row in c.execute('SELECT id::text AS id,email,name,department,position,level,active FROM profiles ORDER BY created_at,id')]
 def active_admins(c,excluding=None):
  return sum(1 for row in account_rows(c) if row['level']=='admin' and row['active'] and row['id']!=excluding)
 def managed_projects(c,actor,granted):
  projects=w.all_records(c,'project')
  return projects if 'project.manage_any' in granted else [p for p in projects if p['pm']==actor['id']]

 @r.get('/me')
 def me(actor=Depends(w.user)):
  with w.connect() as c:
   granted=w.permissions(c,actor)
   return {'user':actor,'auth':'supabase' if storage.SHARED else 'local','permissions':sorted(granted),
    'can_manage_users':storage.SHARED and 'user.manage' in granted,
    'can_manage_projects':storage.SHARED and bool(managed_projects(c,actor,granted)),
    'can_create_project':w.can_create_project(c,actor)}

 @r.get('/admin/users')
 def users(actor=Depends(manage_users)):
  shared()
  with w.connect() as c:return {'items':account_rows(c),'levels':LEVELS,'can_create':bool(storage.SERVICE_KEY),'me':actor['id']}

 @r.post('/admin/users',status_code=201)
 def create_user(body:NewUser,actor=Depends(manage_users)):
  shared()
  email=body.email.strip().lower();name=body.name.strip()
  if not EMAIL.fullmatch(email):raise HTTPException(422,'이메일 주소를 확인해 주세요.')
  if body.level not in LEVELS:raise HTTPException(422,'역할을 확인해 주세요.')
  if not name:raise HTTPException(422,'이름을 입력해 주세요.')
  try:account=supabase_auth.create_user(email,body.password,name)
  except supabase_auth.AuthError as exc:raise auth_failure(exc)
  uid=str(account.get('id') or (account.get('user') or {}).get('id') or '')
  if not uid:raise HTTPException(502,'Supabase 응답에서 계정 정보를 확인하지 못했습니다.')
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   c.execute('INSERT INTO profiles(id,email,name) VALUES(?::uuid,?,?) ON CONFLICT(id) DO NOTHING',(uid,email,name))
   c.execute('UPDATE profiles SET email=?,name=?,department=?,position=?,level=?,active=? WHERE id::text=?',(email,name,body.department.strip(),body.position.strip() or '담당자',body.level,True,uid))
   return next(row for row in account_rows(c) if row['id']==uid)

 @r.patch('/admin/users/{uid}')
 def edit_user(uid:str,body:UserEdit,actor=Depends(manage_users)):
  shared()
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   current=next((row for row in account_rows(c) if row['id']==uid),None)
   if not current:raise HTTPException(404,'사용자를 찾을 수 없습니다.')
   changed=dict(current)
   for key in ('name','department','position'):
    value=getattr(body,key)
    if value is not None:changed[key]=value.strip()
   if not changed['name']:raise HTTPException(422,'이름을 입력해 주세요.')
   if body.level is not None:
    if body.level not in LEVELS:raise HTTPException(422,'역할을 확인해 주세요.')
    changed['level']=body.level
   if body.active is not None:changed['active']=body.active
   if uid==actor['id'] and not changed['active']:raise HTTPException(409,'자신의 계정은 사용 중지할 수 없습니다.')
   loses_admin=current['level']=='admin' and current['active'] and (changed['level']!='admin' or not changed['active'])
   if loses_admin and active_admins(c,excluding=uid)==0:raise HTTPException(409,'관리자는 한 명 이상 있어야 합니다. 다른 관리자를 먼저 지정해 주세요.')
   c.execute('UPDATE profiles SET name=?,department=?,position=?,level=?,active=? WHERE id::text=?',(changed['name'],changed['department'],changed['position'],changed['level'],changed['active'],uid))
   if not changed['active']:c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
   return changed

 @r.post('/admin/users/{uid}/password')
 def reset_password(uid:str,body:Password,actor=Depends(manage_users)):
  shared()
  with w.connect() as c:
   if not storage.read_person(c,uid):raise HTTPException(404,'사용자를 찾을 수 없습니다.')
  try:supabase_auth.set_password(uid,body.password)
  except supabase_auth.AuthError as exc:raise auth_failure(exc)
  # Sessions opened with the old password end now.
  with w.connect() as c:
   if uid!=actor['id']:c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
  return {'ok':True}

 @r.get('/admin/permissions')
 def permission_table(actor=Depends(manage_users)):
  shared()
  with w.connect() as c:
   granted={level:[] for level in LEVELS}
   for row in c.execute('SELECT level,permission FROM role_permissions ORDER BY level,permission'):
    if row['level'] in granted and row['permission'] in PERMISSIONS:granted[row['level']].append(row['permission'])
  return {'levels':LEVELS,'permissions':PERMISSIONS,'granted':granted,'locked':list(LOCKED)}

 @r.put('/admin/permissions')
 def grant(body:Grant,actor=Depends(manage_users)):
  shared()
  if body.level not in LEVELS or body.permission not in PERMISSIONS:raise HTTPException(422,'역할 또는 기능을 확인해 주세요.')
  if (body.level,body.permission)==LOCKED and not body.allowed:raise HTTPException(409,'관리자의 사용자·권한 관리 기능은 해제할 수 없습니다.')
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   if body.allowed:c.execute('INSERT INTO role_permissions(level,permission) VALUES(?,?) ON CONFLICT(level,permission) DO NOTHING',(body.level,body.permission))
   else:c.execute('DELETE FROM role_permissions WHERE level=? AND permission=?',(body.level,body.permission))
  return {'ok':True}

 @r.get('/admin/projects')
 def project_access(actor=Depends(w.user)):
  shared()
  with w.connect() as c:
   granted=w.permissions(c,actor);items=managed_projects(c,actor,granted)
   if not items and 'project.manage_any' not in granted:raise HTTPException(403,'참여자를 지정할 수 있는 프로젝트가 없습니다.')
   items.sort(key=lambda p:p.get('created_at') or '',reverse=True)
   return {'items':[{'id':p['id'],'name':p['name'],'pm':p['pm'],'members':p['members']} for p in items],'people':w.all_records(c,'person')}

 @r.put('/admin/projects/{pid}/access')
 def set_access(pid:str,body:Access,actor=Depends(w.user)):
  shared()
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   p=w.read(c,'project',pid)
   if p.get('deleted_at'):raise HTTPException(410,'휴지통에 있는 프로젝트입니다.')
   if 'project.manage_any' not in w.permissions(c,actor) and p['pm']!=actor['id']:raise HTTPException(403,'이 프로젝트의 PM 또는 관리자가 지정할 수 있습니다.')
   people={x['id']:x for x in w.all_records(c,'person')}
   members=list(dict.fromkeys([body.pm_id]+body.members))
   if any(x not in people for x in members):raise HTTPException(422,'등록된 사용자를 선택해 주세요.')
   if not people[body.pm_id]['active']:raise HTTPException(422,'사용 중인 계정을 PM으로 지정해 주세요.')
   added=[x for x in members if x not in p['members']]
   if any(not people[x]['active'] for x in added):raise HTTPException(422,'사용 중지된 계정은 새로 추가할 수 없습니다.')
   p['pm']=body.pm_id;p['members']=members;w.save(c,'project',p)
   return {'id':p['id'],'name':p['name'],'pm':p['pm'],'members':p['members']}
 return r
