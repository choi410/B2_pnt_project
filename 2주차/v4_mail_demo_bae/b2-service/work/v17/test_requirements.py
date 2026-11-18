"""Requirement extraction and registration regressions; isolated DB, optional real GPU run."""
import json,os,sys,tempfile
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from fastapi.testclient import TestClient

def regression():
 from work.v17 import server as w,changes as ch,intake_review as ir
 from server import lines
 w.init()
 pm=TestClient(w.app,headers={'X-B2-Request':'workspace'})
 def req(method,path,status=200,**kwargs):
  r=pm.request(method,'/api'+path,**kwargs)
  assert r.status_code==status,(path,r.status_code,r.text)
  return r.json()
 req('POST','/demo-login',json={'username':'team1'})
 p=req('POST','/projects',201,json={'name':'요구사항 검증','members':['team2']})
 def item(title,value,state='확정',before='',topic_id=None):
  return dict(title=title,category='사양',before=before,after=value,business_state=state,evidence=['L001'],topic_id=topic_id)
 def register(text,items,day='2026-11-01'):
  d=req('POST','/meeting-imports',201,data={'text':text})
  req('PATCH','/meeting-imports/'+d['id'],json={'version':1,'project_id':p['id'],'title':text[:30],'body':text,'meeting_date':day,'review_bundle':{}})
  with patch('work.v17.ai.extract',return_value=({'summary':[],'decisions':[],'items':[]},{})),patch.object(ch,'extract_changes',return_value=({'items':items},0.1)):
   ir.analyze_import(w,d['id'])
  d=req('GET','/meeting-imports/'+d['id'])
  assert d['change_analysis_version']==ch.EXTRACTION_VERSION and not d.get('change_analysis_error'),d
  v=req('PATCH','/meeting-imports/'+d['id'],json={'version':d['draft_version'],'project_id':p['id'],'title':d['title'],'meeting_date':day,'body':text,'review_bundle':d['review_bundle'],'review_confirmed':True})['version']
  mid=req('POST','/meeting-imports/'+d['id']+'/finalize',201,json={'version':v,'confirm_changes':True})['id']
  events=[e for e in req('GET','/changes?project_id='+p['id'])['events'] if e['meeting_id']==mid]
  assert all(e['review_state']=='검토 전' for e in events),'Registration must only create proposals'
  for e in events:req('POST','/changes/'+e['id']+'/decision',json={'version':e['version'],'action':'confirm'})
  return mid
 def ledger():return req('GET','/changes?project_id='+p['id'])
 def current(tid):return next(t for t in ledger()['topics'] if t['id']==tid)['current_value']
 baseline=[item('압연 속도','120 m/min')]+[item('초기 사양 '+str(i),str(i)+' mm') for i in range(2,7)]
 mid=register('계약 합의: 압연 속도 120 m/min 및 초기 사양 2~6을 각각 확정한다.',baseline)
 data=ledger();assert len(data['events'])==6,'More than five initial requirements must survive registration'
 topic=next(t for t in data['topics'] if t['title']=='압연 속도');tid=topic['id']
 assert current(tid)=='120 m/min'
 assert next(s for s in data['scans'] if s['id']==mid)['state']=='ready'
 for day,state,value in [('02','요청','135 m/min 요청'),('03','보류','135 m/min 요청 보류'),('04','철회','135 m/min 요청 철회')]:
  # A reviewed title edit must not lose the model's selected same-project topic.
  register('압연 속도 120 m/min에서 '+value,[item('압연 속도 검토',value,state,'120 m/min',tid)],'2026-11-'+day)
  assert current(tid)=='120 m/min',(state,current(tid))
 register('압연 속도 135 m/min 변경 확정',[item('압연 속도','135 m/min','확정','120 m/min',tid)],'2026-11-05')
 assert current(tid)=='135 m/min'
 register('새 요구: 세척 커버 재질 SUS304 요청. 승인 전이다.',[item('세척 커버 재질','SUS304 요청','요청')],'2026-11-06')
 material=next(t for t in ledger()['topics'] if t['title']=='세척 커버 재질')
 assert material['current_value'] is None,'An initial request must not become an approved specification'
 assert len(ledger()['topics'])==7,'Existing topic links must survive import/save/finalize'
 with w.connect() as c:
  w.save(c,'change_topic',{'id':'outside','project_id':'other','title':'압연 속도','category':'사양'})
 for bad in [item('압연 속도','135 m/min',topic_id='outside'),dict(item('압연 속도','135 m/min',topic_id=tid),category='납기')]:
  try:ir.validate_bundle(w,{'changes':[bad]},'원문',p)
  except Exception as e:assert getattr(e,'status_code',None)==422
  else:raise AssertionError('Cross-project/category link was accepted')
 # Extraction validation never accepts fabricated source lines or silently drops overflow.
 for bad in [[dict(baseline[0],evidence=['L999'])],baseline*(ch.MAX_ITEMS//len(baseline)+1)]:
  try:ch.normalize_extraction({'lines':lines('원문')},bad,[])
  except ValueError:pass
  else:raise AssertionError('Invalid evidence or overflow was accepted')
 assert ch.normalize_extraction({'lines':lines('원문')},[dict(baseline[0],topic_id=tid)],[topic])[0]['topic_id']==tid
 assert not ch.relevant_topics(lines('권취 장력 25 N을 새로 요청했다.'),[topic])
 assert not ch.relevant_topics(lines('이송 속도 45 m/min을 확정했다.'),[topic]),'Different equipment speeds must not be linked just because both say speed'
 assert not ch.relevant_topics(lines('전극 롤프레스의 압연 속도를 요청했다.'),[{'id':'width','title':'전극 폭 대응 범위','category':'사양'}])
 assert len(ch.normalize_extraction({'lines':lines('원문')},[baseline[0],dict(baseline[0],after='',evidence=[])],[]))==1
 assert ch.relevant_topics(lines('압연 공정의 최대 속도를 135 m/min으로 요청했다.'),[topic])==[topic]
 for text in ('기존 압연 속도 120 m/min은 그대로다.','압연 속도 140 m/min 가능 여부는 문의일 뿐 변경 요청으로 접수하지 않는다.'):
  assert not ch.normalize_extraction({'lines':lines(text)},[dict(baseline[0],topic_id=tid)],[topic])
 for text in ('압연 속도 135 m/min 요청을 철회했다. 기존 사양은 유지한다.','압연 속도 135 m/min 요청을 보류했다. 기존 사양은 유지한다.','기존 압연 속도 120 m/min에서 135 m/min으로 변경하기로 확정했다.'):
  assert len(ch.normalize_extraction({'lines':lines(text)},[dict(baseline[0],topic_id=tid)],[topic]))==1
 state_lines=lines('색상 변경 요청을 철회했다.\n회의에서 변경 요청 보류 여부를 논의할 예정이다.')
 assert ch.missed_state_lines(state_lines,[])==state_lines[:1]
 assert not ch.missed_state_lines(state_lines,[baseline[0]])
 held='전극 폭 650 mm 확대 요청은 프레임 재설계가 필요하여 보류했다.'
 fixed=ch.normalize_extraction({'lines':lines(held)},[item('전극 폭','보류','보류')],[])
 assert fixed[0]['after']==held and fixed[0]['business_state']=='보류'
 # Old completed scans can be rerun after the extractor update without deleting history.
 with w.connect() as c:
  m=w.read(c,'meeting',mid);m.pop('change_scan_extraction_version');w.save(c,'meeting',m)
 assert next(s for s in ledger()['scans'] if s['id']==mid)['state']=='stale'
 with patch.object(ch,'submit_scan') as submitted:
  result=req('POST','/changes/analyze-scope',202,json={'project_id':p['id']})
 assert result['total']==1 and submitted.call_count==1
 job=result['jobs'][0]
 before=deepcopy(ledger()['events'])
 recovered=item('누락된 초기 조건','IP54','요청')
 with patch.object(ch,'extract_changes',return_value=({'items':baseline+[recovered]},0.1)):
  ch.infer_changes(w,mid,job['job'])
 after=ledger()['events'];assert len(after)==len(before)+1
 assert all(x==next(y for y in after if y['id']==x['id']) for x in before),'Rescan must preserve existing records'
 assert next(x for x in after if x['title']=='누락된 초기 조건')['review_state']=='검토 전'
 with w.connect() as c:
  m=w.read(c,'meeting',mid);job2=ch.prepare_scan(w,m);w.save(c,'meeting',m)
 with patch.object(ch,'extract_changes',return_value=({'items':baseline+[recovered]},0.1)):
  ch.infer_changes(w,mid,job2)
 assert ledger()['events']==after,'Repeated scans must not duplicate the recovered requirement'
 assert next(s for s in ledger()['scans'] if s['id']==mid)['state']=='ready'
 print('PASS: six initial requirements; import/topic round trip; request/hold/withdraw keep approved value; later new requirement; explicit approval; cross-project/category rejection; evidence validation; old-scan retry and deduplication.',flush=True)

def model_check():
 from work.v17 import changes as ch,server as w
 from server import lines
 original_normalize=ch.normalize_extraction
 def debug_normalize(m,items,topics):
  try:return original_normalize(m,items,topics)
  except ValueError:
   print('INVALID MODEL RESPONSE: '+json.dumps(items,ensure_ascii=False),flush=True)
   raise
 ch.normalize_extraction=debug_normalize
 # Frozen meeting text from the earlier evaluation. No gold topic IDs supplied:
 # subsequent runs receive only the titles/categories actually extracted earlier.
 folder=w.ROOT.parent/'클로드'/'시연데이터_v1'
 earlier=json.loads((folder/'채점결과'/'예측_20261109_2110.json').read_text(encoding='utf-8'))
 outputs=[]
 topics=[{'id':'speed','title':'압연 속도','category':'사양'}]
 cases=[
  ('later-new-request','회의명: 제7차 시운전 협의\n논의: 고객이 처음으로 세척 커버에 SUS316L을 사용해 달라고 요청했다. 재질 적용은 승인하지 않았다.\n압연 속도 120 m/min은 기존 사양 그대로다.\n후속 조치: 팀원 2가 견적을 작성한다.'),
  ('no-requirement','시운전 80% 진행 상황을 보고했다. 팀원 2가 잔여 점검표를 제출한다.\n기존 압연 속도 120 m/min과 납품일에는 변경이 없다.\n고객이 140 m/min 운전 가능 여부를 단순 문의했으나 요구나 변경 요청으로 접수하지 않았다.'),
  ('mixed-states','첫 기술 협의\n고객은 권취 장력을 25 N으로 요청했으며 아직 승인하지 않았다.\n고객과 PM은 프레임 재질을 AL6061로 합의했다.\n고객은 터치패널에 베트남어 표시를 새로 요청했다. 이 요청은 번역 범위가 없어 보류했다.\n먼저 언급한 커버 색상 RAL9002 요청은 고객이 철회했다. 다른 색상은 정하지 않았다.'),
  ('six-initial','초기 사양 합의: 이송 속도 45 m/min, 유효 폭 720 mm, 권취 장력 32 N, 건조 온도 165 ℃, 프레임 재질 AL6061, 납품일 2027-02-17을 각각 고객과 PM이 확정했다.')]
 for name,source in cases:
  result,secs=ch.extract_changes(w,{'lines':lines(source)},topics)
  outputs.append({'case':name,'seconds':secs,'items':result['items']})
  print(json.dumps(outputs[-1],ensure_ascii=False),flush=True)
  if name=='no-requirement':assert not result['items'],result
  if name=='later-new-request':assert len(result['items'])==1 and result['items'][0]['business_state']=='요청' and not result['items'][0]['before'] and 'SUS316L' in result['items'][0]['after'],result
  if name=='mixed-states':assert sorted(x['business_state'] for x in result['items'])==sorted(['요청','확정','보류','철회']),result
  if name=='six-initial':assert len(result['items'])==6 and all(not x['before'] and x['business_state']=='확정' for x in result['items']),result
 projects={}
 for key,entry in earlier['meetings'].items():
  topics=projects.setdefault(entry['project'],[])
  result,secs=ch.extract_changes(w,{'lines':entry['lines']},topics)
  outputs.append({'case':key,'seconds':secs,'items':result['items']})
  print(json.dumps(outputs[-1],ensure_ascii=False),flush=True)
  expected_initial={'P-2616-M01':['120m/min','600mm','여닫이','SS400','2026-12-13'],'P-2618-M01':['150','500mm','2027-01-15']}.get(key)
  if expected_initial:
   assert len(result['items'])==len(expected_initial),result
   for value in expected_initial:
    assert any(value in x['after'].replace(' ','') and x['before']=='' and x['business_state']=='확정' for x in result['items']),(key,value,result)
  if key=='P-2616-M05':assert not any('140' in x['before']+x['after'] or '압연 속도' in x['title'] for x in result['items']),result
  for x in result['items']:
   if x['topic_id'] is None and not any(t['title']==x['title'] and t['category']==x['category'] for t in topics):
    topics.append({'id':f"T{len(topics)+1}",'title':x['title'],'category':x['category']})
 print('PASS: novel model cases; inspect printed regression values/state/linkage before claiming accuracy.',flush=True)

def main():
 with tempfile.TemporaryDirectory(prefix='b2-requirements-qa-') as tmp:
  os.environ.update(B2_TEAM_DATA_DIR=tmp,B2_TEAM_TESTING='1',B2_DEMO_MODE='1')
  os.environ.pop('B2_TEAM_LAN_IP',None);os.environ.pop('B2_TEAM_LAN_CIDR',None)
  regression()
  if '--model' in sys.argv:model_check()
if __name__=='__main__':main()
