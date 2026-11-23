"""Supabase login by user ID (app_user_id): ID→email lookup, credential check, employee row through RLS, account state."""
import pytest
from work.v17 import auth_supabase as auth

EMP={'id':8,'emp_no':'T003','name':'배근우','department':'마스-1','position':'담당자','email':'team3@example.com',
     'role':'member','account_status':'active','app_user_id':'team3'}


@pytest.fixture(autouse=True)
def env(monkeypatch):
 monkeypatch.setenv('B2_AUTH_MODE','supabase')
 monkeypatch.setenv('SUPABASE_URL','https://demo.supabase.co/')
 monkeypatch.setenv('SUPABASE_ANON_KEY','sb_publishable_test')


LOOKUP=lambda user_id:{'team3':'Team3@Example.com'}.get(user_id)


def fake(token_status=200,rows=(EMP,),rows_status=200,calls=None):
 def request(method,url,key,body=None,token=None,timeout=8):
  if calls is not None:calls.append((method,url,body,token))
  if '/auth/v1/token' in url:
   return (token_status,{'access_token':'user-jwt','user':{'id':'62c726b1'}}) if token_status==200 else (token_status,{'error':'invalid_grant'})
  return rows_status,list(rows) if rows_status==200 else {'message':'permission denied'}
 return request


def test_login_reads_own_employee_row_with_user_token():
 calls=[]
 emp=auth.authenticate(' team3 ','pw',request=fake(calls=calls),lookup=LOOKUP)
 assert emp['app_user_id']=='team3'
 assert calls[0][2]=={'email':'team3@example.com','password':'pw'}
 method,url,_,token=calls[1]
 assert method=='GET' and 'auth_user_id=eq.62c726b1' in url and token=='user-jwt'
 assert url.startswith('https://demo.supabase.co/rest/v1/employees?')


@pytest.mark.parametrize('kwargs,status',[
 ({'token_status':400},401),
 ({'token_status':429},429),
 ({'rows':()},403),
 ({'rows':({**EMP,'account_status':'inactive'},)},403),
 ({'rows':({**EMP,'role':'guest'},)},403),
 ({'rows':({**EMP,'app_user_id':None},)},403),
 ({'rows_status':401},500),
])
def test_rejections(kwargs,status):
 with pytest.raises(auth.AuthError) as exc:auth.authenticate('team3','pw',request=fake(**kwargs),lookup=LOOKUP)
 assert exc.value.status==status


@pytest.mark.parametrize('user_id',['nobody','team3@example.com','../admin','a'*65])
def test_unknown_or_malformed_id_looks_like_wrong_password(user_id):
 calls=[]
 with pytest.raises(auth.AuthError) as exc:auth.authenticate(user_id,'pw',request=fake(calls=calls),lookup=LOOKUP)
 assert exc.value.status==401 and exc.value.message==auth.BAD_LOGIN
 assert not calls   # Supabase Auth is not even asked


def test_id_must_match_logged_in_employee():
 # 이메일 조회 결과와 실제 로그인한 직원이 다르면 거부한다.
 with pytest.raises(auth.AuthError) as exc:
  auth.authenticate('team3','pw',request=fake(rows=({**EMP,'app_user_id':'team9'},)),lookup=LOOKUP)
 assert exc.value.status==401


def test_missing_settings(monkeypatch):
 monkeypatch.setenv('SUPABASE_URL','')
 with pytest.raises(auth.AuthError) as exc:auth.authenticate('team3','pw',request=fake(),lookup=LOOKUP)
 assert exc.value.status==503


def test_person_keeps_existing_fields_and_maps_role():
 person=auth.person_from({**EMP,'role':'pm','app_user_id':'team1','name':'김양일'},{'id':'team1','calendar_color':'blue'})
 assert person['calendar_color']=='blue' and person['level']=='leader' and person['role_label']=='PM'
 admin=auth.person_from({**EMP,'role':'admin','app_user_id':'admin','name':'홍길동','position':None})
 assert admin['level']=='staff' and admin['position']=='관리자'


def test_mode_switch(monkeypatch):
 assert auth.enabled()
 monkeypatch.setenv('B2_AUTH_MODE','')
 assert not auth.enabled()


def test_publishable_key_is_not_sent_as_bearer(monkeypatch):
 seen={}
 class Res:
  status=200
  def read(self):return b'{}'
  def __enter__(self):return self
  def __exit__(self,*a):pass
 def urlopen(req,timeout):seen.update(req.headers);return Res()
 monkeypatch.setattr(auth.urllib.request,'urlopen',urlopen)
 auth._request('GET','https://x','sb_publishable_test')
 assert 'Authorization' not in seen and seen['Apikey']=='sb_publishable_test'
 auth._request('GET','https://x','eyJlegacy')
 assert seen['Authorization']=='Bearer eyJlegacy'
