"""Supabase Auth over its REST API. Only the standard library is used."""
import json, urllib.error, urllib.parse, urllib.request
from work.v17 import storage


class AuthError(Exception):
 def __init__(self,status,code='',message=''):
  super().__init__(message or code or str(status));self.status=status;self.code=code or '';self.message=message or ''


def call(method,path,body=None,key=None,timeout=12):
 key=key or storage.ANON_KEY
 # Supabase reads the key from `apikey`; a bearer value is accepted only when identical.
 headers={'apikey':key,'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'application/json'}
 data=json.dumps(body).encode('utf-8') if body is not None else None
 request=urllib.request.Request(storage.SUPABASE_URL+'/auth/v1'+path,data=data,method=method,headers=headers)
 try:
  with urllib.request.urlopen(request,timeout=timeout) as response:
   raw=response.read()
   return json.loads(raw) if raw else {}
 except urllib.error.HTTPError as exc:
  try:detail=json.loads(exc.read() or b'{}')
  except ValueError:detail={}
  if not isinstance(detail,dict):detail={}
  raise AuthError(exc.code,str(detail.get('error_code') or detail.get('error') or ''),str(detail.get('msg') or detail.get('error_description') or detail.get('message') or '')) from None
 except (urllib.error.URLError,TimeoutError,OSError,ValueError):
  raise AuthError(503,'unreachable','') from None


def sign_in(email,password):
 """Check the e-mail and password. Returns the Supabase user (id, email, user_metadata)."""
 result=call('POST','/token?grant_type=password',{'email':email,'password':password})
 account=result.get('user') or {}
 if not account.get('id'):raise AuthError(502,'unexpected_response','')
 return account


def service_key():
 if not storage.SERVICE_KEY:raise AuthError(501,'service_key_missing','')
 return storage.SERVICE_KEY


def create_user(email,password,name):
 return call('POST','/admin/users',{'email':email,'password':password,'email_confirm':True,'user_metadata':{'name':name}},key=service_key())


def set_password(user_id,password):
 return call('PUT','/admin/users/'+urllib.parse.quote(str(user_id),safe=''),{'password':password},key=service_key())


def list_users():
 found=[];page=1
 while page<=50:
  result=call('GET',f'/admin/users?page={page}&per_page=200',key=service_key())
  batch=result.get('users',[]) if isinstance(result,dict) else result
  found.extend(batch)
  if len(batch)<200:break
  page+=1
 return found
