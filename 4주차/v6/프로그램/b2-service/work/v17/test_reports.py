"""D3 integration QA in a disposable database; never edits team data."""
import os,tempfile,io,json,time
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

def regression():
 from work.v17 import server as w
 w.init();clients=[TestClient(w.app,headers={'X-B2-Request':'workspace'}) for _ in range(4)]
 def req(c,method,path,status=200,**kw):
  r=c.request(method,'/api'+path,**kw);assert r.status_code==status,(path,r.status_code,r.text);return r.json()
 for i,c in enumerate(clients):req(c,'POST','/demo-login',json={'username':'team'+str(i+1)})
 pm,author,reader,outside=clients
 p=req(pm,'POST','/projects',201,json={'name':'보고서 검증용 롤프레스','members':['team2','team3']});pid=p['id']
 source='회의 안건: 점검 커버 간섭 검토\n결정: 도면 확인 전 제작에 착수하지 않는다.\n후속 조치: 진효창이 변경 도면을 2026-11-13까지 제출한다.\n추가 확인: 가공 가능 여부는 미정이다.'
 new={'project_id':pid,'kind':'minutes','title':'점검 커버 검토','start':'2026-11-10','end':'2026-11-10','memo':source}
 req(outside,'POST','/reports',403,json=new)
 d=req(author,'POST','/reports',201,json=new);rid=d['id']
 assert len(d['sources'])==4 and d['sections'][0]['text']==source
 assert req(outside,'GET','/reports')==[]
 req(outside,'GET','/reports/'+rid,403)
 assert len(req(reader,'GET','/reports'))==1
 body={'version':1,'title':'수정한 회의록','sections':d['sections'],'actions':[{'task':'변경 도면 제출','owner':'진효창','due':'2026-11-13'}],'checked':True}
 body['sections'][0]['text']='점검 커버 간섭 검토 결과를 정리했다.'
 req(reader,'PATCH','/reports/'+rid,403,json=body)
 d=req(author,'PATCH','/reports/'+rid,json=body);assert d['version']==2 and d['sources'][0]['text']=='회의 안건: 점검 커버 간섭 검토'
 req(author,'PATCH','/reports/'+rid,409,json=body)
 req(author,'PATCH','/reports/'+rid,422,json={**body,'version':2,'sections':[]})
 from work.v17.reports_ai import validate
 valid={'sections':[{'text':'도면 확인 전 제작에 착수하지 않는다.','evidence':['S2']},{'text':'도면 확인 전 제작에 착수하지 않는다.','evidence':['S2']},{'text':'가공 가능 여부는 미정이다.','evidence':['S4']}],'actions':[{'task':'변경 도면 제출','owner':'없는 담당자','due':'미정','evidence':['S3']}]}
 result=validate(valid,'minutes',d['sources']);assert result['actions'][0]['owner']=='진효창'
 for bad in ({'text':'추측','evidence':['BAD']},{'text':'999mm 이동','evidence':['S2']}):
  try:validate({**valid,'sections':[bad,*valid['sections'][1:]]},'minutes',d['sources']);raise AssertionError('ungrounded draft accepted')
  except ValueError:pass
 with patch('work.v17.reports_ai.generate',return_value=result):
  req(author,'POST','/reports/'+rid+'/ai',202,json={'version':2})
  for _ in range(100):
   d=req(author,'GET','/reports/'+rid)
   if d['ai_state'] not in ('queued','running'):break
   time.sleep(.02)
  assert d['ai_state']=='ready' and d['sections'][0]['text']==body['sections'][0]['text'] and d['checked']
 # Saving edits invalidates the old AI candidate; it must not reappear as a fresh suggestion.
 d=req(author,'PATCH','/reports/'+rid,json={**body,'version':2});assert d['ai_result'] is None and d['ai_state']=='idle'
 # Word export contains saved edits; access denied to outsiders.
 assert outside.get('/api/reports/'+rid+'/word').status_code==403
 exported=author.get('/api/reports/'+rid+'/word');assert exported.status_code==200
 from docx import Document
 doc=Document(io.BytesIO(exported.content));text='\n'.join(p.text for p in doc.paragraphs)+'\n'+'\n'.join(c.text for t in doc.tables for row in t.rows for c in row.cells)
 assert '수정한 회의록' in text and '변경 도면 제출' in text and '2026-11-13' in text
 out=Path('work/v17/.history/qa-v19');out.mkdir(parents=True,exist_ok=True);(out/'minutes.docx').write_bytes(exported.content)
 req(author,'POST','/reports',422,json={**new,'kind':'weekly','start':'2026-12-01','end':'2026-11-01'})
 t=req(pm,'POST','/tasks',201,json={'project_id':pid,'title':'도면 간섭 검토','description':'커버와 프레임 간섭을 확인하고 검토표를 남긴다.','owner_id':'team2','reviewer_id':'team1','start':'2026-11-10','due':'2026-11-13'})
 weekly=req(author,'POST','/reports',201,json={**new,'kind':'weekly','title':'11월 주간 업무보고','start':'2026-11-01','end':'2026-11-10','memo':''});assert weekly['actions'][0]['task']==t['title']
 before=json.dumps(weekly['sources'],ensure_ascii=False)
 with w.connect() as c:
  task=w.read(c,'task',t['id']);task['title']='나중에 수정된 업무';w.save(c,'task',task)
 assert json.dumps(req(author,'GET','/reports/'+weekly['id'])['sources'],ensure_ascii=False)==before
 (out/'weekly.docx').write_bytes(author.get('/api/reports/'+weekly['id']+'/word').content)
 # Input routes parse stored cell text, reject formulas and never execute macros.
 from openpyxl import Workbook
 wb=Workbook();wb.active.append(['업무','담당자','기한']);wb.active.append(['도면 확인','진효창','2026-11-13']);buf=io.BytesIO();wb.save(buf)
 parsed=req(author,'POST','/reports/read-file',files={'file':('자료.xlsx',buf.getvalue())});assert '도면 확인' in parsed['text'] and parsed['note']
 wb.active['A3']='=1+1';buf=io.BytesIO();wb.save(buf);req(author,'POST','/reports/read-file',422,files={'file':('수식.xlsx',buf.getvalue())})
 parsed=req(author,'POST','/reports/read-file',files={'file':('회의.docx',exported.content)});assert '수정한 회의록' in parsed['text']
 req(author,'POST','/reports/read-file',422,files={'file':('bad.docx',b'not a zip')})
 req(author,'POST','/reports/read-file',422,files={'file':('bad.txt',('가'*18001).encode())})
 print('PASS: project access; author/PM edits; optimistic conflict; immutable evidence; AI draft never auto-applies; invalid evidence/numbers rejected; saved Word export; docx/xlsx/text validation.',flush=True)
 return {'project_id':pid,'report_id':rid,'weekly_id':weekly['id']}

def main():
 with tempfile.TemporaryDirectory(prefix='b2-report-qa-') as tmp:
  os.environ.update(B2_TEAM_DATA_DIR=tmp,B2_TEAM_TESTING='1',B2_DEMO_MODE='1');os.environ.pop('B2_TEAM_LAN_IP',None);os.environ.pop('B2_TEAM_LAN_CIDR',None)
  from work.v17 import server as w
  w.COOKIE='b2_report_qa_session';w.team_config.ORIGINS.add('http://127.0.0.1:8772')
  result=regression();print(json.dumps(result),flush=True)
  import sys
  if '--serve' in sys.argv:
   import uvicorn
   uvicorn.run(w.app,host='127.0.0.1',port=8772,proxy_headers=False,access_log=False)
if __name__=='__main__':main()
