"""Isolated visual QA fixture for the home and requirement timeline. Never uses live data."""
import os,sys,tempfile,json
from fastapi.testclient import TestClient

def seed():
 from work.v17.test_requirements import regression
 regression()
 from work.v17 import server as w
 client=TestClient(w.app,headers={'X-B2-Request':'workspace'})
 def req(method,path,status=200,**kwargs):
  r=client.request(method,'/api'+path,**kwargs)
  assert r.status_code==status,(path,r.status_code,r.text)
  return r.json()
 req('POST','/demo-login',json={'username':'team1'})
 with w.connect() as c:
  p=w.all_records(c,'project')[0];p['name']='롤프레스 1호기 · 화면 검증';p['overview']={'version':1,'purpose':'고객 요구에 맞춰 압연 조건을 검증하고 제작 도면을 확정합니다.','customer':'가상 D사','equipment':'롤프레스 1호기','start_date':'2026-10-01','due_date':'2027-02-15','scope':'압연 유닛 · 안전커버 · FAT','next_goal':'변경 도면 고객 확인','stages':['요구 협의','설계','제작','시운전','인수'],'current_stage':'설계','updated_by':'team1','updated_at':w.now()};w.save(c,'project',p)
  tid=next(t['id'] for t in w.all_records(c,'change_topic') if t['title']=='압연 속도')
  # Reopen one genuine test agreement so the browser can verify inline confirmation.
  e=next(e for e in w.all_records(c,'change_event') if e['topic_id']==tid and e['after']=='135 m/min')
  e.update(review_state='검토 전',confirmed_by=None,confirmed_at=None,version=e['version']+1);w.save(c,'change_event',e)
  for e in w.all_records(c,'change_event'):
   if e['topic_id']==tid and e['business_state']!='확정':
    e.update(review_state='검토 전',confirmed_by=None,confirmed_at=None,version=e['version']+1);w.save(c,'change_event',e)
 for i,(title,status,due) in enumerate([('압연 조건 시험 결과 정리','완료','2026-11-06'),('안전커버 도면 개정','진행중','2026-11-12'),('고객 확인 자료 작성','미착수','2026-11-13'),('제작 착수 조건 확인','검토대기','2026-11-09')]):
  t=req('POST','/tasks',201,json={'project_id':p['id'],'title':title,'description':'원문과 도면을 대조하고 검토 결과를 남깁니다.','owner_id':'team2','reviewer_id':'team1','start':'2026-11-05','due':due})
  with w.connect() as c:
   t=w.read(c,'task',t['id']);t['status']=status;t['meeting_id']=sorted(w.all_records(c,'meeting'),key=lambda m:m.get('date',''))[0]['id'];w.save(c,'task',t)
 req('POST','/demo-login',json={'username':'team2'})
 req('POST','/field-reports',201,json={'project_id':p['id'],'title':'시운전 중 커버 간섭 발견','description':'커버를 열 때 배선 덕트에 닿습니다. 간섭 위치와 수정 방법을 확인해야 합니다.'})
 req('POST','/demo-login',json={'username':'team1'})
 req('POST','/projects',201,json={'name':'신규 코팅라인 · 업무 미등록','members':['team2']})
 print(json.dumps({'project_id':p['id'],'topic_id':tid},ensure_ascii=False),flush=True)

def main():
 with tempfile.TemporaryDirectory(prefix='b2-flow-qa-') as tmp:
  os.environ.update(B2_TEAM_DATA_DIR=tmp,B2_TEAM_TESTING='1',B2_DEMO_MODE='1')
  os.environ.pop('B2_TEAM_LAN_IP',None);os.environ.pop('B2_TEAM_LAN_CIDR',None)
  from work.v17 import server as w
  w.COOKIE='b2_flow_qa_session';w.team_config.ORIGINS.add('http://127.0.0.1:8772')
  seed()
  if '--serve' in sys.argv:
   import uvicorn
   uvicorn.run(w.app,host='127.0.0.1',port=8772,proxy_headers=False,access_log=False)
if __name__=='__main__':main()
