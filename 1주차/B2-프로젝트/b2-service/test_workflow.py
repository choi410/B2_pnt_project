from test_service import client, create, result
import server

def registered_task(client):
    meeting=create(client)
    response=client.post('/api/meetings/'+meeting['id']+'/review',json={'version':meeting['version'],'reviewed':True,'analysis':result(),'actor_id':'pm'})
    assert response.status_code==200
    items=client.get('/api/work-items').json();assert len(items)==1
    return items[0],meeting

def action(client,item,kind,actor='design',note='가상 업무의 조치 내용을 확인했다.'):
    return client.post('/api/work-items/'+item['id']+'/actions',json={'version':item['version'],'action':kind,'actor_id':actor,'note':note})

def test_assignee_submit_pm_return_approve_reopen_and_audit(client):
    item,meeting=registered_task(client)
    assert item['status']=='미착수'
    assert action(client,item,'approve','pm').status_code==409
    assert action(client,item,'start','quality').status_code==403
    started=action(client,item,'start').json();assert started['status']=='진행중'
    assert action(client,item,'submit').status_code==409
    submitted=action(client,started,'submit').json();assert submitted['status']=='검토요청'
    assert action(client,submitted,'approve','design').status_code==403
    returned=action(client,submitted,'return','pm','간섭 확인 근거를 추가해 주세요.').json();assert returned['status']=='보완요청'
    resubmitted=action(client,returned,'submit','design','간섭 확인 근거를 보완했다.').json()
    approved=action(client,resubmitted,'approve','pm','보완한 검토 결과를 확인했다.').json();assert approved['status']=='완료'
    overview=client.get('/api/overview').json();assert overview['counts']['done']==1 and overview['counts']['open']==0
    meeting_status=client.get('/api/meetings/'+meeting['id']).json()['work_items'][0]
    assert meeting_status['status']=='완료' and meeting_status['owner']=='이준호'
    detail=client.get('/api/work-items/'+item['id']).json()
    assert len(detail['events'])==6 and detail['events'][0]['kind']=='완료 확인'
    assert detail['source_lines'][0]['text']==meeting['source']
    assert client.get('/api/meetings/'+meeting['id']).json()['reviewed']['items'][0]['due']=='2026-11-06'
    reopened=action(client,approved,'reopen','pm','추가 점검이 필요해 재개한다.').json();assert reopened['status']=='진행중'
    server.initialize()
    assert len(client.get('/api/work-items').json())==1
    assert client.get('/api/work-items/'+item['id']).json()['status']=='진행중'

def test_edits_preserve_meeting_and_create_audit(client):
    item,meeting=registered_task(client)
    edit={'version':item['version'],'content':item['content'],'owner':'정유진','due':'2026-11-10','agreement':None,'note':'담당 부서 협의로 담당자와 검토 일정을 변경한다.','actor_id':'pm'}
    response=client.patch('/api/work-items/'+item['id'],json=edit);assert response.status_code==200
    after=response.json();assert after['owner']=='정유진'
    assert client.patch('/api/work-items/'+item['id'],json=edit).status_code==409
    original=client.get('/api/meetings/'+meeting['id']).json()
    assert original['reviewed']['items'][0]['owner']=='이준호' and original['source']==meeting['source']
    history=client.get('/api/work-items/'+item['id']).json()['events'][0]
    assert history['before_json']['owner']=='이준호' and history['after_json']['owner']=='정유진'
    assert action(client,after,'start','design').status_code==403
    edit['version']=after['version'];edit['actor_id']='quality'
    assert client.patch('/api/work-items/'+item['id'],json=edit).status_code==403

def test_requirements_do_not_get_task_completion_and_manual_project_flow(client):
    project=client.post('/api/projects',json={'name':'별도 프로젝트','actor_id':'pm'}).json()
    body={'project_id':project['id'],'category':'설계변경','content':'가상 변경안 검토','owner':None,'due':None,'agreement':'확정','note':'가상 고객과 변경안을 합의한 사례','actor_id':'pm'}
    created=client.post('/api/work-items',json=body);assert created.status_code==201
    item=created.json();assert item['status'] is None
    assert action(client,item,'approve','pm').status_code==422
    assert client.get('/api/overview').json()['counts']['done']==0
    assert client.post('/api/projects',json={'name':'별도 프로젝트','actor_id':'pm'}).status_code==409
    assert client.post('/api/projects',json={'name':'무권한 프로젝트','actor_id':'design'}).status_code==403
    body['project_id']='missing';assert client.post('/api/work-items',json=body).status_code==404
    assert len(client.get('/api/work-items?project_id='+project['id']).json())==1
    assert '가상 변경안 검토' in client.get('/api/work-export?project_id='+project['id']).text

def test_notes_and_dates_must_be_valid(client):
    item,_=registered_task(client)
    assert action(client,item,'start',note='   ').status_code==422
    edit={'version':item['version'],'content':item['content'],'owner':'이준호','due':'2026-02-30','agreement':None,'note':'일정 변경','actor_id':'pm'}
    assert client.patch('/api/work-items/'+item['id'],json=edit).status_code==422
    assert client.get('/api/work-items/'+item['id']).json()['version']==item['version']
