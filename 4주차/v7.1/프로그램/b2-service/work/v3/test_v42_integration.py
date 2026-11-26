"""Our AI/requirements base and team workflow must operate on the same records."""
import json
import pytest
from work.v3.test_connected import client,w
from work.v3.test_questions_trash import project,meeting
from work.v3 import local_generation,service
from work.v17 import llm

def stage_model(monkeypatch,text):
    monkeypatch.setattr(llm,'available',lambda:False)
    monkeypatch.setattr(local_generation,'available',lambda:True)
    monkeypatch.setattr(local_generation,'chat',lambda *a,**k:(json.dumps({'in_progress':text,'planned':'','stage':'설계(기구/전장)','reason':'현재 설계를 진행하고 있음','evidence':text},ensure_ascii=False),{'model':'controlled-local-test'}))

def test_stage_uses_our_runtime_preserves_source_and_team_lead_permissions(client,monkeypatch):
    c,_=client;p=project(c);text='구동부 설계를 진행하고 있다.'
    m=meeting(c,p,text)
    stage_model(monkeypatch,text)
    assert c.post('/api/demo-login',json={'username':'team2'}).status_code==200
    assert c.post('/api/v3/meetings/'+m['id']+'/stage-ai',json={'reason':'단계 판단 근거 검토'}).status_code==403
    c.post('/api/demo-login',json={'username':'team1'})
    r=c.post('/api/v3/meetings/'+m['id']+'/stage-ai',json={'reason':'단계 판단 근거 검토'})
    assert r.status_code==200,r.text
    with w.connect() as db:updated=w.read(db,'meeting',m['id'])
    assert updated['source']==m['source']
    assert updated['stage_ai']['model']=='controlled-local-test'
    assert updated['stage_ai']['evidence']==text
    flow=c.get('/api/v3/projects/'+p['id']+'/flow').json()
    assert flow['ai_ready'] and flow['per_detail'][m['id']]['source']=='ai'

def test_stage_result_cannot_overwrite_a_new_revision(client,monkeypatch):
    c,_=client;p=project(c);m=meeting(c,p,'구동부 설계를 진행하고 있다.')
    stage_model(monkeypatch,'구동부 설계를 진행하고 있다.')
    generate=local_generation.chat
    def changed(*args,**kwargs):
        with w.connect() as db:
            current=w.read(db,'meeting',m['id']);current['revision']+=1;w.save(db,'meeting',current)
        return generate(*args,**kwargs)
    monkeypatch.setattr(local_generation,'chat',changed)
    assert c.post('/api/v3/meetings/'+m['id']+'/stage-ai',json={'reason':'단계 판단 근거 검토'}).status_code==409
    with w.connect() as db:assert not w.read(db,'meeting',m['id']).get('stage_ai')

def test_review_gate_and_our_requirements_projection_coexist(client,monkeypatch):
    c,_=client;p=project(c)
    m=meeting(c,p,'압연 속도는 120 m/min으로 합의했다.\n진효창은 2026-12-01까지 배치도를 작성한다.')
    e={'id':w.uid(),'project_id':p['id'],'meeting_id':m['id'],'title':'압연 속도','category':'사양','before':'','after':'120 m/min','business_state':'확정','review_state':'검토 전','source_revision':m['revision'],'effective_date':m['date'],'evidence':[m['lines'][-2]['id']],'version':1,'quotes':[m['lines'][-2]['text']]}
    with w.connect() as db:w.save(db,'change_event',e)
    before=c.get('/api/v3/workspace').json()
    assert 'requirements' in before
    assert not c.get('/api/v3/search',params={'q':'압연','project_id':p['id']}).json()['items']
    assert c.post('/api/v3/meetings/'+m['id']+'/approval-requests',json={'email':'example@example.com'}).status_code==409
    reviewed=c.post('/api/v3/changes/'+e['id']+'/review',json={'version':1,'action':'확인'})
    assert reviewed.status_code==200,reviewed.text
    assert c.get('/api/v3/search',params={'q':'압연','project_id':p['id']}).json()['items'][0]['id']==m['id']
    after=c.get('/api/v3/workspace').json()
    assert after['requirements'] and after['changes'][0]['review_state']=='확인됨'
    # Existing AI conversation still reads the registered source.
    response=c.post('/api/conversations/questions',json={'question':'제일 최근 회의록이 뭐야?'})
    assert response.status_code==202,response.text
    thread=response.json();turn=thread['messages'][-1]
    assert turn['state']=='done' and turn['result']['sources']
    source=turn['result']['sources'][0]
    proof=c.get('/api/conversations/'+thread['id']+'/messages/'+turn['id']+'/sources/'+source['id'])
    assert proof.status_code==200 and proof.json()['meeting_id']==m['id']

@pytest.mark.parametrize('question',['그 회의에서 보류된 내용은?','그회의 안건은?','이 회의 내용 알려줘','그 회의록에서 보류된 내용은?'])
def test_meeting_followup_uses_actual_previous_document(client,question):
    from work.v3.conversations import resolve_question
    c,_=client;p=project(c)
    older=meeting(c,p,'압연 속도 120 m/min 합의.','2026-11-01')
    latest=meeting(c,p,'납품일 변경 요청은 보류했다.','2026-11-13')
    first=c.post('/api/conversations/questions',json={'question':'제일 최근 회의록이 뭐야?'}).json()
    with w.connect() as db:
        previous=w.read(db,'ai_message',first['messages'][-1]['id'])
        actor=w.read(db,'person','team1')
        context=resolve_question(w,db,actor,question,previous)
    assert not context.get('clarify'),context
    assert context['meeting_ids']==[latest['id']]
    assert older['id'] not in context['meeting_ids']

def test_meeting_followup_does_not_choose_arbitrary_document(client):
    from work.v3.conversations import resolve_question
    c,_=client;p=project(c)
    for day in ('2026-11-01','2026-11-13'):meeting(c,p,'납품일 변경 요청 보류.',day)
    first=c.post('/api/conversations/questions',json={'question':'회의록 목록 보여줘'}).json()
    with w.connect() as db:
        previous=w.read(db,'ai_message',first['messages'][-1]['id'])
        context=resolve_question(w,db,w.read(db,'person','team1'),'그 회의에서 보류된 내용은?',previous)
    assert context.get('clarify') and len(context['meetings'])==2,context
