from test_service import client, create, result
import server


def reviewed_with_decision(client):
    meeting=create(client)
    payload=result()
    payload['review_points']=[{'content':'고객 치수 자료의 회신 담당자와 기한을 확인한다.','evidence_ids':['L001']}]
    response=client.post('/api/meetings/'+meeting['id']+'/review',json={'version':meeting['version'],'reviewed':True,'analysis':payload,'actor_id':'pm'})
    assert response.status_code==200
    return meeting,client.get('/api/work-items').json()[0]


def test_only_saved_human_review_seeds_group_and_decisions_once(client):
    meeting=create(client)
    assert client.get('/api/work-flow').json()=={'agendas':[],'decisions':[]}
    meeting,item=reviewed_with_decision(client)
    flow=client.get('/api/work-flow').json()
    assert len(flow['agendas'])==len(flow['decisions'])==1
    assert item['agenda_id']==flow['agendas'][0]['id']
    point=flow['decisions'][0]
    assert point['owner'] is None and point['due'] is None and point['state']=='대기'
    assert point['source_lines']==[{'id':'L001','text':meeting['source']}]
    server.initialize();server.initialize()
    assert client.get('/api/work-flow').json()==flow
    assert client.get('/api/overview').json()['counts']['tasks']==1


def test_grouping_optimistic_lock_audit_and_restart_do_not_restore_removed_links(client):
    meeting,item=reviewed_with_decision(client)
    agenda=client.get('/api/work-flow').json()['agendas'][0]
    body={'project_id':item['project_id'],'title':'간섭 검토 안건','item_ids':[],'item_versions':{item['id']:item['version']},'version':agenda['version'],'note':'회의 안건을 나누어 관리한다.','actor_id':'design'}
    url='/api/agendas/'+agenda['id']
    assert client.patch(url,json=body).status_code==403
    body['actor_id']='pm';body['item_versions'][item['id']]=0
    assert client.patch(url,json=body).status_code==409
    assert client.get('/api/work-items').json()[0]['agenda_id']==agenda['id']
    body['item_versions'][item['id']]=item['version']
    assert client.patch(url,json=body).status_code==200
    assert client.patch(url,json=body).status_code==409
    current=client.get('/api/work-items').json()[0]
    assert current['agenda_id'] is None and current['version']==item['version']+1
    assert client.get('/api/work-items/'+item['id']).json()['events'][0]['kind']=='안건 연결'
    server.initialize()
    assert client.get('/api/work-items').json()[0]['agenda_id'] is None
    body.update(item_ids=[item['id']],item_versions={item['id']:current['version']},title='새 실행 안건')
    created=client.post('/api/agendas',json=body)
    assert created.status_code==201
    assert client.get('/api/work-items').json()[0]['agenda_id']==created.json()['id']


def test_cross_project_members_cannot_be_moved_and_changes_are_atomic(client):
    _,item=reviewed_with_decision(client)
    project=client.post('/api/projects',json={'name':'다른 프로젝트','actor_id':'pm'}).json()
    body={'project_id':project['id'],'title':'잘못된 연결','item_ids':[item['id']],'item_versions':{item['id']:item['version']},'note':'잘못된 프로젝트 연결 시도','actor_id':'pm'}
    assert client.post('/api/agendas',json=body).status_code==422
    assert len(client.get('/api/work-flow').json()['agendas'])==1


def test_decision_owner_due_resolution_history_and_reopen_preserve_meeting(client):
    meeting,_=reviewed_with_decision(client)
    original=client.get('/api/meetings/'+meeting['id']).json()['reviewed']
    point=client.get('/api/work-flow').json()['decisions'][0]
    url='/api/decisions/'+point['id']
    body={'version':1,'owner':'정유진','due':'2026-11-09','state':'해결','result':'','note':'고객 회신 확인','actor_id':'pm'}
    assert client.patch(url,json=body).status_code==422
    body.update(state='대기',due='2026-02-30')
    assert client.patch(url,json=body).status_code==422
    body.update(due='2026-11-09',actor_id='quality')
    assert client.patch(url,json=body).status_code==403
    body.update(actor_id='pm',state='해결',result='고객 치수 자료를 수신하여 확인했다.')
    assert client.patch(url,json=body).status_code==200
    assert client.patch(url,json=body).status_code==409
    server.initialize()
    saved=client.get('/api/work-flow').json()['decisions'][0]
    assert saved['state']=='해결' and saved['owner']=='정유진' and saved['due']=='2026-11-09'
    assert len(saved['events'])==1 and saved['events'][0]['actor_name']=='박서연'
    assert client.get('/api/meetings/'+meeting['id']).json()['reviewed']==original
    assert client.get('/api/work-items').json()[0]['status']=='미착수'
    body.update(version=saved['version'],state='보류',result='추가 치수 확인이 필요하다.')
    assert client.patch(url,json=body).status_code==200
    assert len(client.get('/api/work-flow').json()['decisions'][0]['events'])==2
