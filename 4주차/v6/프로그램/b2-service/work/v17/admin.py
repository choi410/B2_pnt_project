"""관리자 설정 API (/api/admin). 관리자 계정만 사용한다.

- 사용자 관리: 직원 목록, 역할 변경(PM ↔ 팀원), 계정 사용 중지·재사용
  → Supabase employees를 바꾸고, 서비스의 사용자 기록에도 바로 반영한 뒤 그 사람의 로그인 세션을 끊는다.
- 프로젝트 PM 교체: 프로젝트 이름·PM·참여자 수만 다루고 회의록·변경이력 내용은 보지 않는다.

비밀번호 변경·계정 생성은 Supabase 관리자 키가 필요해 여기서는 하지 않는다(대시보드에서 처리).
"""
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from work.v17 import permissions,supabase_db
from work.v17.auth_supabase import ROLES

STATUSES=('active','inactive')
ASSIGNABLE_ROLES=('pm','member')   # 관리자 역할 부여·해제는 대시보드에서만 (실수로 관리자가 없어지는 일 방지)


class UserChange(BaseModel):
 model_config=ConfigDict(extra='forbid')
 role:str|None=Field(default=None,max_length=20)
 account_status:str|None=Field(default=None,max_length=20)


class PmChange(BaseModel):
 model_config=ConfigDict(extra='forbid')
 pm_id:str=Field(min_length=1,max_length=64)
 version:int|None=None


def build_router(w):
 r=APIRouter(prefix='/api/admin')

 def admin(actor=Depends(w.user)):
  if not permissions.is_admin(actor):raise HTTPException(403,'관리자만 사용할 수 있습니다.')
  return actor

 def db(sql,params=(),fetch=True):
  try:return supabase_db.run(sql,params,fetch)
  except supabase_db.DbError as exc:raise HTTPException(exc.status,exc.message) from None

 def employees():
  return db('''select e.id,e.emp_no,e.name,e.department,e."position",e.email,e.role,e.account_status,e.app_user_id,
                      u.last_sign_in_at
               from public.employees e left join auth.users u on u.id=e.auth_user_id
               order by e.id''')

 def employee(employee_id):
  rows=db('select id,name,role,account_status,app_user_id from public.employees where id=%s',(employee_id,))
  if not rows:raise HTTPException(404,'직원을 찾을 수 없습니다.')
  return rows[0]

 def projects_led(c,app_user_id):
  return [p for p in w.all_records(c,'project') if p.get('pm')==app_user_id and not p.get('deleted_at')]

 def sync_person(c,emp):
  """서비스의 사용자 기록에 역할·상태를 반영하고 로그인 세션을 끊는다(다음 요청부터 바로 적용)."""
  pid=emp.get('app_user_id')
  if not pid:return
  row=c.execute("SELECT payload FROM records WHERE kind='person' AND id=?",(pid,)).fetchone()
  if row:
   import json
   person=json.loads(row[0])
   person.update(role=emp['role'],role_label=ROLES[emp['role']],account_status=emp['account_status'],
                 level='leader' if emp['role']=='pm' else 'staff')
   w.save(c,'person',person)
  c.execute('DELETE FROM sessions WHERE user_id=?',(pid,))

 @r.get('/users')
 def users(actor=Depends(admin)):
  rows=employees()
  with w.connect() as c:
   for e in rows:
    e['role_label']=ROLES.get(e['role'],e['role'])
    e['last_sign_in_at']=e['last_sign_in_at'].isoformat() if e.get('last_sign_in_at') else None
    e['pm_projects']=len(projects_led(c,e.get('app_user_id'))) if e.get('app_user_id') else 0
    e['is_me']=e.get('app_user_id')==actor['id']
  return {'users':rows,'roles':[{'value':k,'label':ROLES[k]} for k in ASSIGNABLE_ROLES],'statuses':list(STATUSES)}

 @r.patch('/users/{employee_id}')
 def change_user(employee_id:int,body:UserChange,actor=Depends(admin)):
  if body.role is None and body.account_status is None:raise HTTPException(422,'바꿀 항목을 골라 주세요.')
  emp=employee(employee_id)
  if emp.get('app_user_id')==actor['id']:raise HTTPException(409,'내 계정의 역할·상태는 여기서 바꿀 수 없습니다.')
  if emp['role']=='admin':raise HTTPException(409,'관리자 계정은 Supabase 대시보드에서만 바꿀 수 있습니다.')
  role=body.role if body.role is not None else emp['role']
  status=body.account_status if body.account_status is not None else emp['account_status']
  if role not in ASSIGNABLE_ROLES:raise HTTPException(422,'역할은 PM 또는 팀원 중에서 골라 주세요.')
  if status not in STATUSES:raise HTTPException(422,'계정 상태를 확인해 주세요.')
  if emp.get('app_user_id') and (role!='pm' or status!='active'):
   with w.connect() as c:led=projects_led(c,emp['app_user_id'])
   if led:
    names=', '.join(p['name'] for p in led[:3])+(' 외' if len(led)>3 else '')
    raise HTTPException(409,f'PM을 맡은 프로젝트가 {len(led)}개 있습니다({names}). 프로젝트 PM을 먼저 다른 사람으로 바꿔 주세요.')
  db('update public.employees set role=%s,account_status=%s where id=%s',(role,status,employee_id),fetch=False)
  emp.update(role=role,account_status=status)
  with w.connect() as c:sync_person(c,emp)
  return {'ok':True,'user':{**emp,'role_label':ROLES[role]}}

 @r.get('/projects')
 def projects(actor=Depends(admin)):
  with w.connect() as c:
   people={p['id']:p for p in w.all_records(c,'person')}
   items=[{'id':p['id'],'name':p['name'],'pm':p.get('pm'),'pm_name':people.get(p.get('pm'),{}).get('name') or p.get('pm'),
           'member_count':len(p.get('members') or []),'created_at':p.get('created_at'),'version':p.get('admin_version',1)}
          for p in w.all_records(c,'project')]
  items.sort(key=lambda p:p.get('created_at') or '',reverse=True)
  candidates=[{'id':e['app_user_id'],'name':e['name']} for e in employees() if e['role']=='pm' and e['account_status']=='active' and e.get('app_user_id')]
  return {'projects':items,'pm_candidates':candidates}

 @r.patch('/projects/{pid}/pm')
 def change_pm(pid:str,body:PmChange,actor=Depends(admin)):
  rows=db("select name,role,account_status from public.employees where app_user_id=%s",(body.pm_id,))
  if not rows or rows[0]['role']!='pm' or rows[0]['account_status']!='active':raise HTTPException(422,'사용 중인 PM 계정 중에서 골라 주세요.')
  with w.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   p=w.read(c,'project',pid)
   if p.get('deleted_at'):raise HTTPException(409,'휴지통에 있는 프로젝트입니다.')
   if body.version is not None and body.version!=p.get('admin_version',1):raise HTTPException(409,'다른 변경이 먼저 저장되었습니다. 목록을 새로 고쳐 주세요.')
   if p.get('pm')==body.pm_id:return {'ok':True,'project':{'id':pid,'pm':p['pm']}}
   before=p.get('pm')
   p['pm']=body.pm_id
   p['members']=list(dict.fromkeys([*(p.get('members') or []),body.pm_id]))
   p['admin_version']=p.get('admin_version',1)+1
   p.setdefault('lifecycle_events',[]).append({'at':w.now(),'by':actor['id'],'action':'pm_change','from':before,'to':body.pm_id})
   w.save(c,'project',p)
  return {'ok':True,'project':{'id':pid,'pm':body.pm_id,'pm_name':rows[0]['name'],'version':p['admin_version']}}

 return r
