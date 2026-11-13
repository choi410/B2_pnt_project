"""Exercise the simplified change-record workflow using disposable storage."""
import os,sys,tempfile
from fastapi.testclient import TestClient
from work.v17.test_demo import exercise

def main():
 with tempfile.TemporaryDirectory(prefix='b2-history-simple-') as temp:
  os.environ.update(B2_TEAM_DATA_DIR=temp,B2_TEAM_TESTING='1',B2_DEMO_MODE='1')
  from work.v17 import server as w
  ids=exercise(w)
  pm,staff=[TestClient(w.app,headers={'X-B2-Request':'workspace'}) for _ in range(2)]
  def req(client,method,path,status=200,**kwargs):
   r=client.request(method,'/api'+path,**kwargs)
   assert r.status_code==status,(path,r.status_code,r.text)
   return r.json()
  for i,c in enumerate([pm,staff]):req(c,'POST','/demo-login',json={'username':f'team{i+1}'})
  pid,mid=ids['project_id'],ids['meeting_id']
  payload={'meeting_id':mid,'source_revision':1,'title':'체결 구멍 유지','category':'사양','before':'','after':'기존 체결 구멍 유지','business_state':'확정','evidence':['L004'],'effective_date':'2026-11-11'}
  new=req(pm,'POST','/changes',201,json=payload)
  assert any(e['id']==new['id'] for e in req(staff,'GET','/changes')['events']), 'Immediately visible without confirmation'
  assert new['business_state']=='확정' and not new.get('confirmed_by')
  req(staff,'POST','/changes',403,json=payload)
  req(pm,'POST','/changes',422,json={**payload,'evidence':[]})
  # Existing verified records remain correctable. Historical metadata is retained in the archive.
  old=req(pm,'POST',f"/changes/{new['id']}/decision",json={'version':1,'action':'confirm'})
  revised=req(pm,'PATCH',f"/changes/{new['id']}",json={**payload,'version':old['version'],'after':'기존 체결 구멍 유지 · 원문에 따른 보완'})
  assert revised['edit_history'][0]['record']['review_state']=='확인됨'
  assert revised['edit_history'][0]['record']['after']==payload['after']
  assert revised['review_state']=='검토 전' and not revised.get('confirmed_by')
  req(pm,'PATCH',f"/changes/{new['id']}",409,json={**payload,'version':old['version']})
  req(pm,'PATCH',f"/changes/{new['id']}",409,json={**payload,'version':revised['version'],'source_revision':999})
  req(staff,'PATCH',f"/changes/{new['id']}",403,json={**payload,'version':revised['version']})
  verified=req(pm,'POST',f"/changes/{new['id']}/decision",json={'version':revised['version'],'action':'confirm'})
  excluded=req(pm,'POST',f"/changes/{new['id']}/decision",json={'version':verified['version'],'action':'exclude'})
  assert excluded['review_state']=='제외' and excluded['edit_history'][-1]['record']['review_state']=='확인됨'
  restored=req(pm,'POST',f"/changes/{new['id']}/decision",json={'version':excluded['version'],'action':'restore'})
  assert restored['review_state']=='검토 전' and restored['edit_history'][-1]['action']=='복원'
  print('PASS: immediate records, no implicit approval, source/role/version guards, legacy corrections, preserved snapshots, exclude/restore.',flush=True)
  if '--serve' in sys.argv:
   w.COOKIE='b2_demo_qa_session';w.team_config.ORIGINS.add('http://127.0.0.1:8773')
   import uvicorn
   uvicorn.run(w.app,host='127.0.0.1',port=8773,proxy_headers=False,access_log=False)

if __name__=='__main__':main()
