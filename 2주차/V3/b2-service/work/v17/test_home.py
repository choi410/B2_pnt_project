"""Home integration fixture and notification regression, isolated from team data."""
import os,tempfile,json,sys
from fastapi.testclient import TestClient

def seed(w):
 with TestClient(w.app,headers={'X-B2-Request':'workspace'}) as c:
  def req(method,path,status=200,**kw):
   r=c.request(method,'/api'+path,**kw);assert r.status_code==status,(path,r.status_code,r.text);return r.json()
  def login(who):req('POST','/demo-login',json={'username':who})
  login('team1');p=req('POST','/projects',201,json={'name':'화면 점검 프로젝트','members':['team2','team3','team4']})
  def task(title,owner,start,end):return req('POST','/tasks',201,json={'project_id':p['id'],'title':title,'description':'시험용 업무 처리 내용입니다.','owner_id':owner,'reviewer_id':'team1' if owner!='team1' else None,'requires_review':owner!='team1','start':start,'due':end})
  tasks=[task('주를 넘기는 점검 일정','team1','2026-11-08','2026-11-12'),task('도면 번호 대조','team2','2026-11-09','2026-11-11'),task('시운전 준비','team3','2026-11-09','2026-11-13'),task('완료 목표일만 있는 업무','team4',None,'2026-11-10'),task('지난 업무','team1',None,'2026-11-01')]
  login('team2');submitted=req('POST','/tasks/'+tasks[1]['id']+'/actions',json={'version':1,'action':'submit','note':'도면 번호 대조를 완료했습니다.'})
  field=req('POST','/field-reports',201,json={'project_id':p['id'],'title':'현장 센서 고정 상태 확인','description':'시운전 준비 중 센서 고정 상태를 확인해야 합니다.'})
  login('team1');notices=req('GET','/notifications')['items'];matching=[n for n in notices if n['target_id']==field['id']]
  assert len(matching)==1 and matching[0]['recipient']=='team1' and matching[0]['target_type']=='task' and matching[0]['title'].startswith('새 현장 이슈 접수')
  for who in ('team2','team3','team4'):
   login(who);assert not any(n['target_id']==field['id'] for n in req('GET','/notifications')['items'])
  login('team1');own=req('POST','/field-reports',201,json={'project_id':p['id'],'title':'PM 직접 접수 확인','description':'본인이 접수한 항목에는 자신에게 알림을 보내지 않습니다.'})
  assert not any(n['target_id']==own['id'] for n in req('GET','/notifications')['items'])
  ids={}
  for title,changes in [('변경 제안 없는 회의록',[]),('분석 미완료 회의록',[]),('변경 요청이 있는 회의록',[{'title':'점검 커버','category':'사양','before':'여닫이','after':'슬라이딩 변경 요청','business_state':'요청','evidence':['L003']}])]:
   login('team2');text='회의명: '+title+'\n회의일: 2026-11-09\n고객은 점검 커버를 여닫이에서 슬라이딩으로 변경 요청했다. 승인 전이다.'
   d=req('POST','/meeting-imports',201,data={'text':text})
   version=req('PATCH','/meeting-imports/'+d['id'],json={'version':1,'title':title,'meeting_date':'2026-11-09','body':text,'project_id':p['id'],'review_bundle':{'changes':changes},'review_confirmed':True})['version']
   mid=req('POST','/meeting-imports/'+d['id']+'/finalize',201,json={'version':version})['id'];ids[title]=mid
   if title=='분석 미완료 회의록':
    with w.connect() as db:
     m=w.read(db,'meeting',mid);m.update(change_scan_state='failed',change_scan_error='검증용 분석 오류');w.save(db,'meeting',m)
  print('PASS: field report notifies only project PM; self-notification suppressed; existing task/meeting review fixtures ready.',flush=True)
  return {'project_id':p['id'],'task_id':submitted['id'],'field_id':field['id'],'meetings':ids}

def main():
 with tempfile.TemporaryDirectory(prefix='b2-home-qa-') as tmp:
  os.environ.update(B2_TEAM_DATA_DIR=tmp,B2_TEAM_TESTING='1')
  from work.v17 import server as w
  w.COOKIE='b2_home_qa_session';w.team_config.ORIGINS.add('http://localhost:8772')
  fixture=seed(w);print(json.dumps({'database':str(w.DB),**fixture},ensure_ascii=False),flush=True)
  if '--serve' in sys.argv:
   import uvicorn
   uvicorn.run(w.app,host='127.0.0.1',port=8772,proxy_headers=False,access_log=False)
if __name__=='__main__':main()
