"""계정 역할 규칙(관리자·PM·팀원) 단위 검사 + 실제 API 시나리오(fastapi가 있을 때)."""
import importlib,os,tempfile
import pytest
from work.v17 import permissions as perm

ADMIN={'id':'admin','role':'admin','account_status':'active'}
PM={'id':'team1','role':'pm','level':'leader','account_status':'active'}
MEMBER={'id':'team3','role':'member','level':'staff','account_status':'active'}
DEMO_LEADER={'id':'team1','level':'leader'}
DEMO_STAFF={'id':'team3','level':'staff'}


def test_roles_and_project_creation():
 assert perm.role(ADMIN)=='admin' and perm.role(PM)=='pm' and perm.role(MEMBER)=='member'
 assert perm.can_create_project(PM) and not perm.can_create_project(MEMBER) and not perm.can_create_project(ADMIN)
 # 이미 어떤 프로젝트의 PM이어도 계정 역할이 member면 새 프로젝트를 만들 수 없다.
 assert not perm.can_create_project(MEMBER,is_pm_of_any=True)
 # 체험 로그인(role 없음)은 기존 규칙 유지
 assert perm.can_create_project(DEMO_LEADER) and perm.can_create_project(DEMO_STAFF,is_pm_of_any=True)
 assert not perm.can_create_project(DEMO_STAFF)


def test_assignment_rules():
 assert not perm.assignable(ADMIN) and perm.assignable(MEMBER)
 assert not perm.assignable({**MEMBER,'account_status':'inactive'})
 assert perm.can_be_project_pm(PM) and not perm.can_be_project_pm(MEMBER) and perm.can_be_project_pm(DEMO_STAFF)


@pytest.mark.parametrize('path,ok',[
 ('/api/auth/me',True),('/api/logout',True),('/api/admin/users',True),('/api/health',True),
 ('/api/bootstrap',False),('/api/v3/workspace',False),('/api/projects',False),('/api/logout-all',False),
])
def test_admin_paths(path,ok):
 assert perm.admin_path_allowed(path)==ok


# ---- 실제 API 시나리오: PC에서 fastapi 설치 후 실행됨 ----
EMPLOYEES={
 'admin':{'id':1,'emp_no':'E001','name':'홍길동','role':'admin','account_status':'active','app_user_id':'admin','email':'admin@x'},
 'team1':{'id':6,'emp_no':'T001','name':'김양일','department':'마스-1','position':'PM','role':'pm','account_status':'active','app_user_id':'team1','email':'team1@example.com'},
 'team2':{'id':7,'emp_no':'T002','name':'진효창','department':'마스-1','position':'담당자','role':'member','account_status':'active','app_user_id':'team2','email':'team2@example.com'},
 'team3':{'id':8,'emp_no':'T003','name':'배근우','department':'마스-1','position':'담당자','role':'member','account_status':'active','app_user_id':'team3','email':'team3@example.com'},
}


def fake_db(sql,params=(),fetch=True):
 """관리자 API가 보내는 SQL만 흉내 낸다. EMPLOYEES를 그대로 고쳐서 로그인(fake)에도 반영된다."""
 by_id={e['id']:e for e in EMPLOYEES.values()}
 if 'left join auth.users' in sql:return [{**e,'last_sign_in_at':None} for e in sorted(by_id.values(),key=lambda e:e['id'])]
 if sql.startswith('select id,name,role,account_status,app_user_id from public.employees where id'):
  e=by_id.get(params[0]);return [dict(e)] if e else []
 if sql.startswith('update public.employees set role'):
  role,status,ident=params;by_id[ident].update(role=role,account_status=status);return []
 if sql.startswith('select name,role,account_status from public.employees where app_user_id'):
  e=EMPLOYEES.get(params[0]);return [dict(e)] if e else []
 raise AssertionError('예상하지 못한 SQL: '+sql)


@pytest.fixture(scope='module')
def api(tmp_path_factory):
 pytest.importorskip('fastapi')
 os.environ.setdefault('B2_TEAM_TESTING','1')
 os.environ.setdefault('B2_TEAM_DATA_DIR',tempfile.mkdtemp(prefix='b2-roles-'))
 from contextlib import ExitStack
 from fastapi.testclient import TestClient
 app=importlib.import_module('work.v3.server').app
 w=importlib.import_module('work.v17.server')
 auth=importlib.import_module('work.v17.auth_supabase')
 def fake(email,password,request=None):
  emp=EMPLOYEES.get(email.strip())
  if not emp or password!='pw':raise auth.AuthError(401,'이메일 또는 비밀번호를 확인해 주세요.')
  if emp['account_status']!='active':raise auth.AuthError(403,'사용이 중지된 계정입니다.')
  return emp
 tmp=tmp_path_factory.mktemp('roles')
 headers={'X-B2-Request':'workspace','Origin':'http://testserver'}
 # 다른 테스트와 같은 서버 모듈을 쓰므로, 이 모듈 동안만 DB·설정을 바꾸고 끝나면 되돌린다.
 with pytest.MonkeyPatch.context() as mp, ExitStack() as stack:
  mp.setattr(w,'DB',tmp/'workspace.sqlite3');mp.setattr(w,'FILES',tmp/'files')
  mp.setenv('B2_AUTH_MODE','supabase');mp.setenv('SUPABASE_URL','https://unit.test');mp.setenv('SUPABASE_ANON_KEY','sb_publishable_test')
  mp.setattr(auth,'authenticate',fake)
  mp.setattr(importlib.import_module('work.v17.supabase_db'),'run',fake_db)
  w.init()
  anon=stack.enter_context(TestClient(app,headers=headers))
  def client(email):
   c=stack.enter_context(TestClient(app,headers=headers))
   r=c.post('/api/auth/login',json={'user_id':email,'password':'pw'});assert r.status_code==200,r.text
   return c
  yield w,client,anon


def check(client,method,path,status,**kw):
 r=client.request(method,path,**kw)
 assert r.status_code==status,f'{method} {path} → {r.status_code} (기대 {status}) {r.text[:200]}'
 return r


def test_role_scenarios(api):
 w,client,anon=api
 check(anon,'POST','/api/demo-login',403,json={'username':'team1'})
 assert anon.get('/api/demo-accounts').json()==[]
 check(anon,'POST','/api/auth/login',401,json={'user_id':'team3','password':'wrong'})
 admin,pm,staff2,staff3=(client(e) for e in ('admin','team1','team2','team3'))
 assert admin.get('/api/auth/me').json()['role']=='admin'
 check(admin,'GET','/api/bootstrap',403)
 check(admin,'GET','/api/v3/workspace',403)
 check(admin,'POST','/api/projects',403,json={'name':'관리자 생성 시도'})
 boot=staff3.get('/api/bootstrap').json()
 assert boot['permissions']['role']=='member' and not boot['can_create_project']
 assert 'admin' not in {p['id'] for p in boot['people']}
 v3=staff3.get('/api/v3/workspace').json()
 assert v3['permissions']['role']=='member' and not v3['can_create_project'] and 'admin' not in {p['id'] for p in v3['people']}
 check(staff3,'POST','/api/projects',403,json={'name':'팀원 생성 시도'})
 assert pm.get('/api/bootstrap').json()['can_create_project']
 check(pm,'POST','/api/projects',422,json={'name':'PM 아닌 PM 지정','pm_id':'team2'})
 check(pm,'POST','/api/projects',422,json={'name':'관리자 참여 시도','members':['admin']})
 p=pm.post('/api/projects',json={'name':'권한 시험 프로젝트','members':['team2','team3']})
 assert p.status_code==201,p.text;pid=p.json()['id']

 check(staff3,'POST',f'/api/v3/projects/{pid}/stage',403,json={'stage':''})
 check(staff3,'POST',f'/api/projects/{pid}/trash',403,json={'version':1})
 check(staff3,'PATCH',f'/api/projects/{pid}/members',403,json={'ids':['team2']})
 check(pm,'POST',f'/api/v3/projects/{pid}/stage',200,json={'stage':''})
 # 사용 중지: 이미 발급된 세션도 바로 막힌다.
 with w.connect() as c:
  person=w.read(c,'person','team2');person['account_status']='inactive';w.save(c,'person',person)
 check(staff2,'GET','/api/bootstrap',401)
 check(pm,'PATCH',f'/api/projects/{pid}/members',422,json={'ids':['team2']})
 check(staff3,'POST','/api/logout',200)
 check(staff3,'GET','/api/auth/me',401)

def test_admin_users_and_project_pm(api):
 w,client,anon=api
 admin,pm,member=client('admin'),client('team1'),client('team3')
 p=check(pm,'POST','/api/projects',201,json={'name':'PM 교체 시험','members':['team3']}).json()
 check(member,'GET','/api/admin/users',403)
 check(pm,'GET','/api/admin/projects',403)

 users=check(admin,'GET','/api/admin/users',200).json()['users']
 assert {u['app_user_id'] for u in users}=={'admin','team1','team2','team3'}
 check(admin,'PATCH','/api/admin/users/1',409,json={'role':'member'})            # 내 계정
 check(admin,'PATCH','/api/admin/users/8',422,json={'role':'admin'})             # 관리자 부여는 대시보드에서
 check(admin,'PATCH','/api/admin/users/6',409,json={'role':'member'})            # PM을 맡은 프로젝트가 있음

 # 팀원 → PM: 그 사람의 세션은 바로 끊기고, 다시 로그인하면 PM 권한
 check(admin,'PATCH','/api/admin/users/8',200,json={'role':'pm'})
 check(member,'GET','/api/auth/me',401)
 new_pm=client('team3')
 assert new_pm.get('/api/bootstrap').json()['can_create_project']

 listed=check(admin,'GET','/api/admin/projects',200).json()
 row=next(x for x in listed['projects'] if x['id']==p['id'])
 assert row['pm']=='team1' and 'team3' in {x['id'] for x in listed['pm_candidates']}
 check(admin,'PATCH',f"/api/admin/projects/{p['id']}/pm",422,json={'pm_id':'team2'})   # 팀원은 PM 불가
 check(admin,'PATCH',f"/api/admin/projects/{p['id']}/pm",200,json={'pm_id':'team3','version':row['version']})
 check(admin,'PATCH',f"/api/admin/projects/{p['id']}/pm",409,json={'pm_id':'team1','version':row['version']})  # 낡은 화면
 with w.connect() as c:
  project=w.read(c,'project',p['id'])
 assert project['pm']=='team3' and 'team3' in project['members']
 check(new_pm,'POST',f"/api/v3/projects/{p['id']}/stage",200,json={'stage':''})          # 새 PM은 PM 권한
 check(pm,'POST',f"/api/v3/projects/{p['id']}/stage",403,json={'stage':''})              # 이전 PM은 아님

 # 사용 중지 → 세션 즉시 차단, 다시 사용
 assert check(admin,'PATCH','/api/admin/users/7',200,json={'account_status':'inactive'}).json()['user']['account_status']=='inactive'
 check(admin,'PATCH','/api/admin/users/7',200,json={'account_status':'active'})


def test_pm_manages_members(api):
 w,client,anon=api
 pm,member=client('team1'),client('team3')
 with w.connect() as c:   # 앞 테스트에서 사용 중지했을 수 있으므로 되돌린다.
  person=w.read(c,'person','team2');person['account_status']='active';w.save(c,'person',person)
 p=check(pm,'POST','/api/projects',201,json={'name':'참여자 관리 시험','members':['team3']}).json()
 pid=p['id']
 assert set(p['members'])=={'team1','team3'}
 check(member,'PATCH',f'/api/projects/{pid}/members',403,json={'ids':['team2']})
 check(member,'DELETE',f'/api/projects/{pid}/members/team1',403)
 check(pm,'PATCH',f'/api/projects/{pid}/members',422,json={'ids':['admin']})
 assert 'team2' in check(pm,'PATCH',f'/api/projects/{pid}/members',200,json={'ids':['team2']}).json()['members']
 check(pm,'DELETE',f'/api/projects/{pid}/members/team1',409)                 # PM 본인
 check(pm,'DELETE',f'/api/projects/{pid}/members/nobody',404)
 # 진행 중인 업무가 있으면 막고, 끝나면 뺄 수 있다.
 task={'id':w.uid(),'project_id':pid,'title':'도면 확인','owner_id':'team3','reviewer_id':'team1','status':'진행','kind':'업무'}
 with w.connect() as c:w.save(c,'task',task)
 impact=check(pm,'GET',f'/api/projects/{pid}/members/team3/impact',200).json()
 assert impact['open_tasks']==1 and impact['open_task_titles']==['도면 확인'] and not impact['is_pm']
 check(pm,'DELETE',f'/api/projects/{pid}/members/team3',409)
 with w.connect() as c:task['status']='완료';w.save(c,'task',task)
 assert 'team3' not in check(pm,'DELETE',f'/api/projects/{pid}/members/team3',200).json()['members']
 # 빠진 사람은 그 프로젝트를 볼 수 없다.
 assert pid not in {x['id'] for x in check(member,'GET','/api/v3/workspace',200).json()['projects']}
 check(member,'GET',f'/api/v3/projects/{pid}/flow',403)
