"""Progress publication, edit guards and grounded concise notes. Disposable DB."""
import os,tempfile,time,threading
from unittest.mock import patch
from fastapi.testclient import TestClient


def main():
 with tempfile.TemporaryDirectory(prefix='b2-demo-progress-') as temp:
  os.environ.update(B2_TEAM_DATA_DIR=temp,B2_TEAM_TESTING='1',B2_DEMO_MODE='1')
  from work.v17 import server as w
  from work.v17.demo_ai import normalize_notes
  from work.v17.test_demo import SOURCE
  from server import lines
  w.init();c=TestClient(w.app,headers={'X-B2-Request':'workspace'})
  def req(method,path,status=200,**kw):
   r=c.request(method,'/api'+path,**kw);assert r.status_code==status,(path,r.status_code,r.text);return r.json()
  req('POST','/demo-login',json={'username':'team1'})
  p=req('POST','/projects',201,json={'name':'진행 상태 검증','members':['team2','team3']})
  d=req('POST','/meeting-imports',201,data={'text':SOURCE});iid=d['id']
  initial={'version':1,'title':'진행 상태 검증','body':SOURCE,'project_id':p['id'],'review_bundle':{},'review_confirmed':False}
  v=req('PATCH',f'/meeting-imports/{iid}',json=initial)['version']
  sample={'summary':[{'text':'고객이 커버 변경을 요청했다.','evidence':['L003']}],'decisions':[],
   'followups':[{'text':'진효창이 간섭 검토 도면을 2026-11-13까지 작성한다.','kind':'업무','evidence':['L005']}]}
  notes=normalize_notes(sample,lines(SOURCE));assert notes['items'][0]['owner_id'] is None
  assert '진효창' in notes['items'][0]['description'] and '2026-11-13' in notes['items'][0]['description']
  shorter=normalize_notes({'notes':[{'kind':'후속 조치','text':'진효창이 배치도를 개정한다.','evidence':['L001']}]},[{'id':'L001','text':'진효창: 폭 520 mm 기준 배치도와 사양서 개정 / 2026-11-12까지.'}])
  assert all(token in shorter['items'][0]['description'] for token in ('520','사양서','2026-11-12'))
  for bad in ({'text':'납품일 2030-12-31','evidence':['L003']},{'text':'근거 없음','evidence':['L999']}):
   try:normalize_notes({**sample,'summary':[bad]},lines(SOURCE))
   except ValueError:pass
   else:raise AssertionError('Unsupported content was accepted')
  entered=threading.Event();release=threading.Event()
  def slow_changes(*args):
   entered.set();assert release.wait(10);return {'items':[]},0
  def get():return req('GET',f'/meeting-imports/{iid}')
  with patch('work.v17.demo_ai.extract_notes',return_value=(notes,{'seconds':0.01,'model':'TEST FIXTURE'})),patch('work.v17.changes.extract_changes',side_effect=slow_changes):
   req('POST',f'/meeting-imports/{iid}/analyze',202,json={'version':v})
   try:
    assert entered.wait(5)
    partial=get();assert partial['analysis_state']=='running' and partial['analysis_phase']=='changes'
    assert partial['partial_bundle']['candidates'][0]['description']==notes['items'][0]['description']
    assert not partial.get('review_confirmed')
    req('PATCH',f'/meeting-imports/{iid}',409,json={**initial,'version':partial['draft_version']})
    req('POST',f'/meeting-imports/{iid}/finalize',409,json={'version':partial['draft_version']})
   finally:release.set()
   deadline=time.monotonic()+5
   while time.monotonic()<deadline:
    ready=get()
    if ready['analysis_state']=='ready':break
    time.sleep(.05)
   assert ready['analysis_phase']=='complete' and ready['partial_bundle'] is None
   assert ready['review_bundle']['changes']==[] and not ready['review_confirmed']
  with patch('work.v17.demo_ai.extract_notes',side_effect=ValueError('test failure')):
   req('POST',f'/meeting-imports/{iid}/analyze',202,json={'version':ready['draft_version']})
   deadline=time.monotonic()+5
   while time.monotonic()<deadline:
    failed=get()
    if failed['analysis_state']=='failed':break
    time.sleep(.05)
   assert failed['partial_bundle'] is None and failed['analysis_phase']=='failed'
  w.POOL.shutdown(wait=True);w.PREVIEW_POOL.shutdown(wait=True)
  print('PASS: grounded notes, names/dates retained, partial read before changes, edits/finalize blocked during analysis, retry clears partial output, failure does not retain partial output.',flush=True)

if __name__=='__main__':main()
