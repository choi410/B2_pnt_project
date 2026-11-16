"""Sign-in, roles and project access on Postgres, with Supabase Auth replaced by a local stand-in.

Needs a throwaway Postgres database and must run on its own:

    set B2_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/b2_test
    python -m pytest work/v17/test_supabase_accounts.py -q

The tables in that database are dropped and recreated. A real Supabase project is refused.
"""
import json, os, tempfile
import pytest

URL=os.environ.get('B2_TEST_DATABASE_URL','')
if not URL:pytest.skip('B2_TEST_DATABASE_URL 이 없어 건너뜁니다.',allow_module_level=True)
os.environ.update(B2_TEAM_TESTING='1',B2_TEAM_DATA_DIR=tempfile.mkdtemp(prefix='b2-supabase-tests-'),SUPABASE_URL='https://example.supabase.co',
 SUPABASE_ANON_KEY='anon-test',SUPABASE_SERVICE_ROLE_KEY='service-test',SUPABASE_DB_URL=URL,B2_ADMIN_EMAILS='admin@pnt.test')
from work.v17 import storage
if not storage.SHARED:pytest.skip('다른 테스트와 함께 실행하면 로컬 저장소가 먼저 선택됩니다. 이 파일만 따로 실행해 주세요.',allow_module_level=True)
from fastapi.testclient import TestClient
from work.v3.server import app, legacy as w
from work.v17 import supabase_auth

HEADERS={'X-B2-Request':'workspace'}
TABLES='records,record_versions,profiles,role_permissions,sessions,login_limits,calendar_memos,rag_vectors'
directory={}

def fake_create_user(email,password,name):
    if email in directory:raise supabase_auth.AuthError(422,'email_exists','A user with this email address has already been registered')
    with w.connect() as c:
        row=c.execute('INSERT INTO auth.users(email,raw_user_meta_data) VALUES(?,?::jsonb) RETURNING id::text AS id',(email,json.dumps({'name':name}))).fetchone()
    directory[email]={'id':row['id'],'password':password,'name':name}
    return {'id':row['id'],'email':email}
def fake_sign_in(email,password):
    account=directory.get(email)
    if not account or account['password']!=password:raise supabase_auth.AuthError(400,'invalid_credentials','Invalid login credentials')
    return {'id':account['id'],'email':email,'user_metadata':{'name':account['name']}}
def fake_set_password(user_id,password):
    for account in directory.values():
        if account['id']==user_id:account['password']=password;return {}
    raise supabase_auth.AuthError(404,'user_not_found','')

@pytest.fixture(scope='module')
def site():
    with w.connect() as c:
        if c.execute("SELECT to_regclass('auth.identities')").fetchone()[0]:pytest.exit('실제 Supabase 프로젝트에서는 실행하지 않습니다. 비어 있는 테스트용 Postgres 를 지정해 주세요.')
        c.execute('CREATE SCHEMA IF NOT EXISTS auth')
        c.execute('DROP TABLE IF EXISTS '+','.join('public.'+t for t in TABLES.split(','))+' CASCADE')
        c.execute('DROP TABLE IF EXISTS auth.users CASCADE')
        c.execute('CREATE TABLE auth.users(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),email text,raw_user_meta_data jsonb)')
    patch=pytest.MonkeyPatch()
    patch.setattr(supabase_auth,'create_user',fake_create_user);patch.setattr(supabase_auth,'sign_in',fake_sign_in);patch.setattr(supabase_auth,'set_password',fake_set_password)
    directory.clear()
    with TestClient(app,headers=HEADERS) as first:
        # An account made in the Supabase dashboard: the trigger gives it a profile.
        fake_create_user('admin@pnt.test','admin-pass-1','관리자')
        yield first
    patch.undo()

def browser():return TestClient(app,headers=HEADERS)
def sign_in(email,password,status=200):
    c=browser();r=c.post('/api/login',json={'email':email,'password':password})
    assert r.status_code==status,r.text
    return c
def me(c):return c.get('/api/me').json()
def projects(c):return [p['name'] for p in c.get('/api/v3/workspace').json()['projects']]

def test_schema_and_trigger(site):
    with w.connect() as c:
        tables={r[0] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")}
        assert set(TABLES.split(','))<=tables
        assert all(r[0] for r in c.execute("SELECT relrowsecurity FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind='r'"))
        row=c.execute("SELECT name,level,active FROM profiles WHERE email='admin@pnt.test'").fetchone()
    assert (row['name'],row['level'],row['active'])==('관리자','staff',True)

def test_signed_out_requests_are_refused(site):
    c=browser()
    assert c.get('/',follow_redirects=False).status_code==303
    assert c.get('/admin',follow_redirects=False).status_code==303
    assert c.get('/login',follow_redirects=False).status_code==200
    assert c.get('/api/v3/workspace').status_code==401
    assert c.get('/api/me').status_code==401
    assert c.get('/api/demo-accounts').json()==[]
    assert c.post('/api/demo-login',json={'username':'team1'}).status_code==403

def test_sign_in_checks_supabase_and_limits_attempts(site):
    assert sign_in('admin@pnt.test','wrong',401).get('/api/me').status_code==401
    assert sign_in('not-an-email','x',422)
    assert sign_in('nobody@pnt.test','whatever1',401)
    for _ in range(8):sign_in('locked@pnt.test','bad-password',401)
    sign_in('locked@pnt.test','bad-password',429)
    admin=sign_in('admin@pnt.test','admin-pass-1')
    info=me(admin)
    # B2_ADMIN_EMAILS promotes the first administrator on sign-in.
    assert info['user']['level']=='admin' and info['auth']=='supabase'
    assert {'user.manage','project.create','project.manage_any'}<=set(info['permissions'])
    assert 'email' not in info['user']
    assert admin.get('/',follow_redirects=False).status_code==200 and 'location.replace' in admin.get('/').text
    assert admin.get('/login',follow_redirects=False).status_code==303

def test_admin_manages_accounts(site):
    admin=sign_in('admin@pnt.test','admin-pass-1')
    made={}
    for email,name,level,position in [('pm@pnt.test','김양일','leader','PM'),('staff@pnt.test','배근우','staff','담당자'),('other@pnt.test','최인혁','staff','담당자')]:
        r=admin.post('/api/admin/users',json={'email':email,'password':'first-pass-1','name':name,'level':level,'position':position,'department':'마스-1'})
        assert r.status_code==201,r.text
        made[email]=r.json();assert made[email]['level']==level and made[email]['active']
    assert admin.post('/api/admin/users',json={'email':'pm@pnt.test','password':'first-pass-1','name':'중복'}).status_code==409
    assert admin.post('/api/admin/users',json={'email':'short@pnt.test','password':'short','name':'짧은'}).status_code==422
    listing=admin.get('/api/admin/users').json()
    assert len(listing['items'])==4 and listing['can_create']
    staff=sign_in('staff@pnt.test','first-pass-1')
    assert me(staff)['permissions']==[] and not me(staff)['can_manage_users']
    for method,path,body in [('get','/api/admin/users',None),('post','/api/admin/users',{'email':'x@pnt.test','password':'first-pass-1','name':'x'}),
            ('patch','/api/admin/users/'+made['other@pnt.test']['id'],{'level':'admin'}),('get','/api/admin/permissions',None),('put','/api/admin/permissions',{'level':'staff','permission':'user.manage','allowed':True})]:
        r=getattr(staff,method)(path,json=body) if body else getattr(staff,method)(path)
        assert r.status_code==403,(path,r.status_code)
    # Role changes apply to the session that is already open.
    assert admin.patch('/api/admin/users/'+made['staff@pnt.test']['id'],json={'level':'admin'}).status_code==200
    assert staff.get('/api/admin/users').status_code==200
    assert admin.patch('/api/admin/users/'+made['staff@pnt.test']['id'],json={'level':'staff','department':'제조기술'}).status_code==200
    assert staff.get('/api/admin/users').status_code==403 and me(staff)['user']['department']=='제조기술'
    site.made=made

def test_project_functions_follow_role_and_membership(site):
    made=site.made
    admin=sign_in('admin@pnt.test','admin-pass-1');pm=sign_in('pm@pnt.test','first-pass-1');staff=sign_in('staff@pnt.test','first-pass-1');other=sign_in('other@pnt.test','first-pass-1')
    assert staff.post('/api/projects',json={'name':'담당자는 만들 수 없음'}).status_code==403
    # The screen's dialog sends everyone; a Supabase workspace starts with the creator only.
    r=pm.post('/api/projects',json={'name':'롤프레스 1호기','members':[x['id'] for x in made.values()]});assert r.status_code==201,r.text
    p=r.json();assert p['pm']==made['pm@pnt.test']['id'] and p['members']==[p['pm']]
    assert projects(pm)==['롤프레스 1호기'] and projects(staff)==[] and projects(admin)==[]
    access='/api/admin/projects/'+p['id']+'/access'
    assert staff.put(access,json={'pm_id':made['staff@pnt.test']['id'],'members':[]}).status_code==403
    assert staff.get('/api/admin/projects').status_code==403
    assert [x['id'] for x in pm.get('/api/admin/projects').json()['items']]==[p['id']]
    r=pm.put(access,json={'pm_id':p['pm'],'members':[made['staff@pnt.test']['id']]});assert r.status_code==200,r.text
    assert projects(staff)==['롤프레스 1호기'] and projects(other)==[]
    assert pm.put(access,json={'pm_id':p['pm'],'members':['00000000-0000-0000-0000-000000000000']}).status_code==422
    assert pm.put(access,json={'pm_id':p['pm'],'members':['not-a-user']}).status_code==422
    # A member reads the project; only its PM may move it to the trash; others see nothing.
    assert staff.get('/api/v3/search',params={'q':'롤프레스','project_id':p['id']}).status_code==200
    assert other.get('/api/v3/search',params={'q':'롤프레스','project_id':p['id']}).status_code==403
    assert staff.get('/api/projects/'+p['id']+'/trash-preview').status_code==403
    assert pm.get('/api/projects/'+p['id']+'/trash-preview').status_code==200
    # project.manage_any lets the administrator hand the project to another PM without being a member.
    r=admin.put(access,json={'pm_id':made['staff@pnt.test']['id'],'members':[p['pm']]});assert r.status_code==200,r.text
    assert r.json()['pm']==made['staff@pnt.test']['id'] and set(r.json()['members'])=={p['pm'],made['staff@pnt.test']['id']}
    assert me(staff)['can_manage_projects'] and me(staff)['can_create_project']
    site.project=p

def test_permission_table_drives_functions(site):
    admin=sign_in('admin@pnt.test','admin-pass-1');other=sign_in('other@pnt.test','first-pass-1')
    table=admin.get('/api/admin/permissions').json()
    assert table['granted']['leader']==['project.create'] and table['granted']['staff']==[]
    assert other.post('/api/projects',json={'name':'권한 전'}).status_code==403
    assert admin.put('/api/admin/permissions',json={'level':'staff','permission':'project.create','allowed':True}).status_code==200
    assert other.post('/api/projects',json={'name':'권한 후'}).status_code==201
    assert admin.put('/api/admin/permissions',json={'level':'staff','permission':'project.create','allowed':False}).status_code==200
    # The creator stays PM of the project made meanwhile, and a PM may still open projects.
    assert me(other)['permissions']==[] and me(other)['can_create_project']
    assert admin.put('/api/admin/permissions',json={'level':'admin','permission':'user.manage','allowed':False}).status_code==409
    assert admin.put('/api/admin/permissions',json={'level':'staff','permission':'no.such','allowed':True}).status_code==422

def test_deactivation_password_and_last_admin(site):
    made=site.made
    admin=sign_in('admin@pnt.test','admin-pass-1');other=sign_in('other@pnt.test','first-pass-1')
    admin_id=me(admin)['user']['id']
    assert admin.patch('/api/admin/users/'+admin_id,json={'active':False}).status_code==409
    assert admin.patch('/api/admin/users/'+admin_id,json={'level':'staff'}).status_code==409
    assert admin.patch('/api/admin/users/'+made['other@pnt.test']['id'],json={'active':False}).status_code==200
    assert other.get('/api/me').status_code==401
    sign_in('other@pnt.test','first-pass-1',403)
    assert admin.patch('/api/admin/users/'+made['other@pnt.test']['id'],json={'active':True}).status_code==200
    other=sign_in('other@pnt.test','first-pass-1')
    assert admin.post('/api/admin/users/'+made['other@pnt.test']['id']+'/password',json={'password':'second-pass-2'}).status_code==200
    assert other.get('/api/me').status_code==401
    sign_in('other@pnt.test','first-pass-1',401);other=sign_in('other@pnt.test','second-pass-2')
    assert other.post('/api/logout').status_code==200 and other.get('/api/me').status_code==401
    with w.connect() as c:
        assert not c.execute('SELECT 1 FROM sessions WHERE user_id=?',(made['other@pnt.test']['id'],)).fetchone()

def test_unchanged_records_are_not_downloaded_again(site):
    pm=sign_in('pm@pnt.test','first-pass-1')
    with w.connect() as c:
        before=c.execute("SELECT version FROM record_versions WHERE kind='project'").fetchone()[0]
        first=storage.cached_payloads(c,'project');again=storage.cached_payloads(c,'project')
        assert first is again and len(w.all_records(c,'project',include_archived=True))==len(first)
    assert pm.post('/api/projects',json={'name':'변경 번호 확인'}).status_code==201
    with w.connect() as c:
        assert c.execute("SELECT version FROM record_versions WHERE kind='project'").fetchone()[0]==before+1
        fresh=storage.cached_payloads(c,'project')
        assert fresh is not first and len(fresh)==len(first)+1
        # A transaction that has written reads its own rows directly and leaves the shared copy alone.
        c.execute('BEGIN IMMEDIATE')
        assert storage.cached_payloads(c,'project') is None
        assert len(w.all_records(c,'project',include_archived=True))==len(fresh)

def test_records_are_stored_in_postgres(site):
    with w.connect() as c:
        kinds={r[0] for r in c.execute('SELECT DISTINCT kind FROM records')}
        assert 'project' in kinds and 'person' not in kinds
        assert w.read(c,'project',site.project['id'])['name']=='롤프레스 1호기'
        assert {p['name'] for p in w.all_records(c,'person')}>={'관리자','김양일','배근우','최인혁'}
