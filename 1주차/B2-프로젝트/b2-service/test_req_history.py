from test_service import client
import json
import server
import req_analysis


def demo(client):
    response=client.post('/api/requirements/import-demo',json={'actor_id':'pm'})
    assert response.status_code==200,response.text
    return response.json()['project_id']


def candidate(**updates):
    item={'matched_requirement_id':'REQ-P001-001','title':'생산속도','event_type':'재검토','value':'60','unit':'m/min','tolerance':'','reference_point':'','state':'검토중','owner_id':'2022-001','due':'2026-12-11','evidence_ids':['SEG-P001-04-01']}
    return item|updates


def test_import_is_idempotent_and_reference_source_is_honest(client):
    existing=client.post('/api/projects',json={'name':'기존 프로젝트','actor_id':'pm'}).json()
    pid=demo(client)
    assert demo(client)==pid
    projects=client.get('/api/projects').json()
    assert len(projects)==2 and any(p['id']==existing['id'] for p in projects)
    project=next(p for p in projects if p['id']==pid)
    assert project['requirement_count']==12 and project['requirement_event_count']==32 and project['meeting_count']==5
    assert client.get('/api/work-items').json()==[]
    meetings=client.get('/api/meetings').json()
    assert len(meetings)==5 and all(m['reference_info'] for m in meetings)
    record=client.get('/api/meetings/'+meetings[0]['id']).json()
    assert record['analysis'] is None and record['reviewer_name']=='제공된 가상자료' and record['reviewed_at'] is None
    assert client.get('/api/requirement-meetings/MTG-P001-04/docx').content.startswith(b'PK')
    server.initialize()
    assert len(client.get('/api/meetings').json())==5
    assert client.get('/api/meetings/'+record['id']).json()['reviewer_name']=='제공된 가상자료'


def test_replay_keeps_request_and_approved_values_separate(client):
    pid=demo(client)
    def at(seq):return {r['id']:r for r in client.get('/api/requirements',params={'project_id':pid,'through':seq}).json()['items']}
    assert len(at(1))==5 and at(1)['REQ-P001-001']['approved_value'] is None
    assert at(3)['REQ-P001-001']['approved_value']=='50'
    fourth=at(4)['REQ-P001-001']
    assert fourth['value']=='60' and fourth['approved_value']=='50' and fourth['state']=='검토중'
    final=at(5)
    assert final['REQ-P001-001']['value']==final['REQ-P001-001']['approved_value']=='55'
    assert final['REQ-P001-006']['value']=='350' and final['REQ-P001-008']['value']=='18'
    assert final['REQ-P001-009']['state']=='재검토' and final['REQ-P001-009']['owner_name']==''
    assert at(4)['REQ-P001-009']['state']=='철회'
    history=client.get('/api/requirements/REQ-P001-001/history').json()['events']
    assert [e['data']['변경후값'] for e in history]==['40','55','50','60','55']
    assert history[3]['snapshot']['approved_value']=='50'
    source=client.get('/api/requirement-meetings/'+history[3]['meeting_code']).json()
    assert any(s['원문구간ID']==history[3]['data']['근거원문구간ID'] for s in source['segments'])


def trial(client,monkeypatch,pid,output,code='MTG-P001-04'):
    captured=[]
    def fake(context):captured.append(context);return {'candidates':output},{'seconds':0,'model':'TEST DOUBLE'}
    monkeypatch.setattr(req_analysis,'generate',fake)
    response=client.post('/api/requirement-trials',json={'project_id':pid,'meeting_code':code,'actor_id':'pm'})
    assert response.status_code==202,response.text
    result=next(t for t in client.get('/api/requirement-trials',params={'project_id':pid}).json() if t['id']==response.json()['id'])
    return result,captured[0]


def test_ai_context_has_no_future_or_gold_and_review_is_separate(client,monkeypatch):
    pid=demo(client)
    output,context=trial(client,monkeypatch,pid,[candidate()])
    previous={r['id']:r for r in context['previous_requirements']}
    assert previous['REQ-P001-001']['value']=='50' and previous['REQ-P001-001']['approved_value']=='50'
    assert 'REQ-P001-010' not in previous and 'REQ-P001-012' not in previous
    assert all(s['id'].startswith('SEG-P001-04-') for s in context['source_segments'])
    assert output['status']=='review'
    assert client.get('/api/requirements',params={'project_id':pid,'basis':'reviewed','through':4}).json()['items'][0]['origin']=='reference'
    body={'version':output['version'],'candidates':[candidate(decision='accept',value='58')],'actor_id':'pm','note':'원문 대조 후 수정한 검토 결과'}
    url='/api/requirement-trials/'+output['id']+'/review'
    assert client.post(url,json=body|{'actor_id':'design'}).status_code==403
    assert client.post(url,json=body).status_code==200
    assert client.post(url,json=body).status_code==409
    ref={r['id']:r for r in client.get('/api/requirements',params={'project_id':pid,'through':4}).json()['items']}
    edited={r['id']:r for r in client.get('/api/requirements',params={'project_id':pid,'basis':'reviewed','through':4}).json()['items']}
    assert ref['REQ-P001-001']['value']=='60' and edited['REQ-P001-001']['value']=='58'
    assert edited['REQ-P001-001']['approved_value']=='50'
    assert len(client.get('/api/requirements/REQ-P001-001/history',params={'basis':'reviewed'}).json()['events'])==5
    changed_history=client.get('/api/requirements/REQ-P001-001/history',params={'basis':'reviewed'}).json()['events']
    assert changed_history[-1]['effective_before']=='58'
    server.initialize()
    assert client.get('/api/requirement-trials',params={'project_id':pid}).json()[0]['status']=='done'


def test_candidate_validation_stale_context_and_rollback(client,monkeypatch):
    pid=demo(client)
    bad,_=trial(client,monkeypatch,pid,[candidate(evidence_ids=['SEG-P001-05-01'])])
    assert bad['status']=='failed'
    first,_=trial(client,monkeypatch,pid,[candidate()])
    second,_=trial(client,monkeypatch,pid,[candidate()])
    def review(t,items):return client.post('/api/requirement-trials/'+t['id']+'/review',json={'version':t['version'],'candidates':items,'actor_id':'pm','note':'원문 대조'})
    assert review(first,[candidate(decision='accept',matched_requirement_id='not-a-requirement')]).status_code==422
    assert review(first,[candidate(decision='accept',due='2026-02-30')]).status_code==422
    assert review(first,[candidate(decision='accept',event_type='유지확인')]).status_code==422
    assert review(first,[candidate(decision='accept',event_type='철회',state='철회',matched_requirement_id=None)]).status_code==422
    assert review(first,[candidate(decision='accept')]).status_code==200
    assert review(second,[candidate(decision='accept')]).status_code==409


def test_editing_past_review_invalidates_later_ai_but_keeps_reference(client,monkeypatch):
    pid=demo(client)
    fifth,_=trial(client,monkeypatch,pid,[candidate(value='55',event_type='값변경',state='확정',evidence_ids=['SEG-P001-05-01'])],code='MTG-P001-05')
    body={'version':fifth['version'],'candidates':[candidate(value='55',event_type='값변경',state='확정',evidence_ids=['SEG-P001-05-01'],decision='accept')],'note':'5차 회의 대조','actor_id':'pm'}
    assert client.post('/api/requirement-trials/'+fifth['id']+'/review',json=body).status_code==200
    fourth,_=trial(client,monkeypatch,pid,[candidate()])
    body.update(version=fourth['version'],candidates=[candidate(decision='accept')],note='앞선 4차 회의의 이력을 검토')
    assert client.post('/api/requirement-trials/'+fourth['id']+'/review',json=body).status_code==200
    trials=client.get('/api/requirement-trials',params={'project_id':pid}).json()
    assert next(t for t in trials if t['id']==fifth['id'])['status']=='stale'
    history=client.get('/api/requirements/REQ-P001-001/history',params={'basis':'reviewed'}).json()['events']
    assert history[-1]['origin']=='reference' and history[-2]['origin']=='reviewed'


def test_constrained_schema_accepts_null_and_known_identifiers():
    from lmformatenforcer import JsonSchemaParser, CharacterLevelParserConfig
    for matched in [None,'REQ-P001-001']:
        context={'previous_requirements':[{'id':matched}] if matched else [],'people':[{'id':'2022-001'}],'source_segments':[{'id':'SEG-P001-04-01'}]}
        output={'candidates':[candidate(matched_requirement_id=matched,owner_id='2022-001' if matched else None)]}
        text=json.dumps(output,ensure_ascii=False)
        config=CharacterLevelParserConfig()
        config.alphabet+=''.join(set(text))
        parser=JsonSchemaParser(req_analysis.schema_for(context),config=config)
        for char in text:
            assert char in parser.get_allowed_characters(),repr(char)
            parser=parser.add_character(char)
