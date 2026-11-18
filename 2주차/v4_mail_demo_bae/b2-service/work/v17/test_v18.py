"""Integration regressions for registration, assignment and trustworthy baselines.

All records live in a temporary database; no live team data or model is changed.
"""
import os,tempfile,json,time
from copy import deepcopy
from unittest.mock import patch
from fastapi.testclient import TestClient

def exercise():
 from work.v17 import server as w,questions as qa,baseline_questions as bq
 from work.v17.retrieval import registered_document
 w.init()
 clients=[TestClient(w.app,headers={'X-B2-Request':'workspace'}) for _ in range(4)]
 pm,staff,other,outside=clients
 def req(client,method,path,status=200,**kwargs):
  r=client.request(method,'/api'+path,**kwargs)
  assert r.status_code==status,(method,path,r.status_code,r.text)
  return r.json()
 for i,c in enumerate(clients):req(c,'POST','/demo-login',json={'username':f'team{i+1}'})
 p=req(pm,'POST','/projects',201,json={'name':'등록 분리 통합 검증','members':['team2','team3']});pid=p['id']
 def count():
  with w.connect() as c:return {k:len(w.all_records(c,k)) for k in ('meeting','task','notification','change_event','change_topic')}
 def document(mid):return req(pm,'GET','/meetings/'+mid)
 def notices(client,mid):return [n for n in req(client,'GET','/notifications')['items'] if n['target_id']==mid]
 def draft(client,title,change=None):
  source=f'회의명: {title}\n납기를 2026-12-13으로 합의했다.\n팀원 2가 도면 개정본과 간섭 검토 결과를 2026-11-13까지 제출한다.\n새 납기 2026-12-18은 고객 요청이며 아직 합의하지 않았다.'
  d=req(client,'POST','/meeting-imports',201,data={'text':source})
  bundle={'summary':[{'text':'도면과 납기 협의','evidence':['L002','L003']}],'decisions':[],
   'candidates':[{'id':'draw','title':'도면 개정본과 간섭 검토 결과 제출','description':'기존 체결부를 유지하고 개정본과 간섭 검토 결과를 제출한다.','kind':'업무','owner_id':'team2','reviewer_id':'team1','due':'2026-11-13','evidence':['L003']},
                 {'id':'unknown','title':'추가 일정 확인','kind':'업무','owner_id':None,'reviewer_id':'team1','due':None,'evidence':[]}],
   'changes':[change or {'title':'납기','category':'납기','before':'','after':'2026-12-13','business_state':'확정','evidence':['L002']} ]}
  v=req(client,'PATCH','/meeting-imports/'+d['id'],json={'version':d.get('draft_version',1),'title':title,'meeting_date':'2026-11-09','body':source,'project_id':pid,'review_bundle':bundle,'review_confirmed':True})['version']
  return d,v,bundle
 def finalize(client,d,v,selected=(),status=201):return req(client,'POST','/meeting-imports/'+d['id']+'/finalize',status,json={'version':v,'selected':list(selected),'confirm_changes':True})
 before=count();d,v,bundle=draft(staff,'사원 작성')
 assert count()==before
 finalize(staff,d,v,['draw','unknown'],422);assert count()==before
 result=finalize(staff,d,v,['draw']);mid=result['id'];m=document(mid)
 assert m['document_status']=='등록 완료' and m['approved_revision'] is None and m['registered_revision']==m['revision']
 assert result['created']==[] and result['requested']==1 and count()['task']==0
 assert notices(pm,mid)[0]['target_type']=='assignment_request'
 assert len(notices(pm,mid))==len(notices(other,mid))==1 and not notices(outside,mid)
 assert not notices(staff,mid)
 assert len(req(pm,'GET','/work-proposals')[0]['candidates'])==2
 req(outside,'GET','/work-proposals?meeting_id='+mid,403)
 req(other,'POST','/meetings/'+mid+'/assignment-request',403,json={'version':m['version'],'candidates':m['candidates'],'selected':['draw']})
 data=req(pm,'GET','/changes?project_id='+pid)
 assert data['events'][0]['review_state']=='검토 전' and not data['topics'],'Registration must not accept changes even if an older client sends confirm_changes'
 before=count();invalid=deepcopy(m['candidates']);invalid[0]['owner_id']='team4'
 req(pm,'POST','/meetings/'+mid+'/review',422,json={'version':m['version'],'candidates':invalid,'selected':['draw']});assert count()==before
 req(staff,'POST','/meetings/'+mid+'/review',403,json={'version':m['version'],'candidates':m['candidates'],'selected':['draw']})
 applied=req(pm,'POST','/meetings/'+mid+'/review',json={'version':m['version'],'candidates':m['candidates'],'selected':['draw']})
 assert len(applied['created'])==1
 req(pm,'POST','/meetings/'+mid+'/review',409,json={'version':m['version'],'candidates':m['candidates'],'selected':['draw']})
 m=document(mid);assert not m['requested_task_ids']
 req(staff,'POST','/meetings/'+mid+'/assignment-request',422,json={'version':m['version'],'candidates':m['candidates'],'selected':['draw']})
 assert count()['task']==1
 task=next(t for t in req(staff,'GET','/bootstrap')['tasks'] if t['id']==applied['created'][0])
 assert task['description']==bundle['candidates'][0]['description'] and task['source_revision']==m['revision']
 task=req(staff,'POST','/tasks/'+task['id']+'/actions',json={'version':task['version'],'action':'start'})
 # The action response is deliberately not assumed to contain a task snapshot.
 task=req(staff,'GET','/bootstrap')['tasks'][0]
 req(staff,'POST','/tasks/'+task['id']+'/actions',json={'version':task['version'],'action':'submit','note':'도면 개정본과 간섭 검토 결과를 확인해 제출합니다.','reviewer_id':'team1'})
 task=req(pm,'GET','/bootstrap')['tasks'][0]
 req(pm,'POST','/tasks/'+task['id']+'/actions',json={'version':task['version'],'action':'approve'})
 assert req(pm,'GET','/bootstrap')['tasks'][0]['status']=='완료'
 # Optional document review never assigns work or accepts changes.
 m=document(mid);before=count()
 req(staff,'POST','/meetings/'+mid+'/document-action',json={'version':m['version'],'action':'submit'})
 m=document(mid)
 req(pm,'POST','/meetings/'+mid+'/document-action',422,json={'version':m['version'],'action':'approve','selected':['unknown']})
 req(pm,'POST','/meetings/'+mid+'/document-action',json={'version':m['version'],'action':'approve'})
 assert count()['task']==before['task'] and count()['change_topic']==0
 # PM performs a separate per-item source check; document approval is not required.
 d,v,_=draft(staff,'검토 요청 없이 등록');second=finalize(staff,d,v)['id']
 e=next(e for e in req(pm,'GET','/changes?project_id='+pid)['events'] if e['meeting_id']==second)
 req(staff,'POST','/changes/'+e['id']+'/decision',403,json={'version':e['version'],'action':'confirm'})
 req(pm,'POST','/changes/'+e['id']+'/decision',json={'version':e['version'],'action':'confirm'})
 assert document(second)['document_status']=='등록 완료'
 change={'title':'납기','category':'납기','before':'2026-12-13','after':'2026-12-18 요청','business_state':'요청','evidence':['L004']}
 d,v,_=draft(staff,'납기 변경 요청',change);third=finalize(staff,d,v)['id']
 e=next(e for e in req(pm,'GET','/changes?project_id='+pid)['events'] if e['meeting_id']==third)
 req(pm,'POST','/changes/'+e['id']+'/decision',json={'version':e['version'],'action':'confirm'})
 with w.connect() as c:
  result=bq.answer(w,c,[p],'현재 확정 납기는 언제야?')
  assert result['points'][0]['text']=='납기: 2026-12-13' and '2026-12-18' not in result['points'][0]['text']
  docs=qa.corpus(w,c,[pid]);assert len(docs)==3
  assert next(x for x in docs if x['meeting_id']==third)['review_status']=='작성자 확인'
 assert bq.baseline_intent('현재 확정 사양 알려줘') and not bq.baseline_intent('납기 변경 이유가 뭐야?')
 # Full Q&A endpoint, permissions, and historical evidence without invoking a GPU.
 def ask(client,question):
  jid=req(client,'POST','/questions',202,json={'project_id':pid,'question':question})['id']
  for _ in range(60):
   job=req(client,'GET','/questions/'+jid)
   if job['state'] in ('done','failed'):return jid,job
   time.sleep(.02)
  raise AssertionError('Question did not finish')
 jid,job=ask(staff,'현재 확정 납기는 언제야?');assert job['state']=='done',job
 source=req(staff,'GET','/questions/'+jid+'/sources/S1');assert source['review_status']=='기준 반영 확인'
 req(outside,'GET','/questions/'+jid,404)
 # Unreviewed but registered discussion is searchable, and citations retain that status.
 from work.v17.retrieval import chunks
 def retrieve_fixture(_w,_pid,documents,_question):
  return [dict(x,score=1.0) for x in chunks(documents) if x['meeting_id']==third]
 def generate_fixture(_w,_question,sources):
  assert sources and sources[0]['review_status']=='작성자 확인'
  return {'answerable':True,'points':[{'text':'고객이 새 납기 2026-12-18을 요청했지만 아직 합의하지 않았습니다.','sources':[sources[0]['id']]}]}
 with patch.object(qa,'retrieve',side_effect=retrieve_fixture),patch.object(qa,'generate',side_effect=generate_fixture):
  discussion_id,discussion=ask(staff,'고객이 어떤 납기 변경을 요청했어?')
  assert discussion['state']=='done' and discussion['result']['answerable'],discussion
  assert req(staff,'GET','/questions/'+discussion_id+'/sources/S1')['review_status']=='작성자 확인'
 # Editing creates a registered revision and queues one change scan after commit.
 before_doc=document(second);old_source=registered_document(before_doc)
 with patch('work.v17.changes.submit_scan') as scan:
  req(staff,'PATCH','/meetings/'+second+'/content',json={'version':before_doc['version'],'title':before_doc['title'],'meeting_date':before_doc['date'],'body':before_doc['source']+'\n추가 메모: 고객 답변을 기다린다.'})
  scan.assert_called_once()
 new_doc=document(second)
 assert new_doc['document_status']=='등록 완료' and new_doc['revision']==before_doc['revision']+1
 assert registered_document(new_doc)['fingerprint']!=old_source['fingerprint']
 assert new_doc['candidates'][0]['needs_recheck'] and not new_doc['candidates'][0]['evidence']
 assert req(staff,'GET','/questions/'+jid)['state']=='failed','Previously displayed baseline answer must detect source changes'
 jid,job=ask(staff,'현재 확정 납기는 언제야?');assert job['state']=='done'
 assert req(staff,'GET','/questions/'+jid+'/sources/S1')['revision']==before_doc['revision'],'A confirmed baseline retains its original evidence revision'
 # Manual work remains possible without meeting evidence.
 req(pm,'POST','/tasks',201,json={'project_id':pid,'title':'현장 확인 결과 정리','description':'회의 밖에서 요청받은 점검 결과를 정리한다.','owner_id':'team2','reviewer_id':'team1'})
 # PM registration without the optional work step does not auto-assign or confirm.
 before=count();d,v,_=draft(pm,'PM 회의록만 등록');last=finalize(pm,d,v)
 assert last['created']==[] and count()['task']==before['task'] and document(last['id'])['document_status']=='등록 완료'
 before=count();assert finalize(pm,d,v)['id']==last['id'] and count()==before
 print('PASS: author registration, optional assignment requests/review, atomic rollback, access control, completion cycle, baseline QA, version evidence, notifications, idempotency')

if __name__=='__main__':
 with tempfile.TemporaryDirectory(prefix='b2-v18-') as temp:
  os.environ['B2_TEAM_DATA_DIR']=temp
  os.environ['B2_DEMO_MODE']='1'
  os.environ['B2_TEAM_TESTING']='1'
  exercise()
