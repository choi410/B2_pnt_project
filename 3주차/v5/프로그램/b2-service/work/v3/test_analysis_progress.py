from copy import deepcopy
from datetime import datetime,timezone
from work.v3.analysis_progress import estimate_runtime,progress_snapshot,recent_batch
from work.v3.fast_ai import VERSION
from work.v3.test_history_edit import client,w
from work.v3.test_questions_trash import project


def history(size=1000):
    return [{'id':str(i),'source':'가'*size,'revision':1,'analysis_state':'ready','metrics':{'source_chars':size,'source_revision':1,'analysis_seconds':seconds,'passes':[{'pipeline':VERSION,'cache_hit':False,'cold_start':False,'model_load_seconds':0}]}} for i,seconds in enumerate([14,15,16,17])]


def test_estimates_need_comparable_uncached_current_runs():
    samples=history();estimate=estimate_runtime('가'*1000,samples,VERSION)
    assert estimate['sample_count']==4 and estimate['low_seconds']<14<17<estimate['high_seconds']
    assert estimate_runtime('가'*1000,samples[:2],VERSION) is None
    assert estimate_runtime('가'*9000,samples,VERSION) is None
    for field,value in [('cache_hit',True),('cold_start',True),('pipeline','other-model')]:
        changed=deepcopy(samples)
        for m in changed:m['metrics']['passes'][0][field]=value
        assert estimate_runtime('가'*1000,changed,VERSION) is None
    for m in samples:m['revision']=2
    assert estimate_runtime('가'*1000,samples,VERSION) is None


def test_queue_elapsed_and_remaining_include_predecessors():
    now=datetime(2026,11,13,1,0,30,tzinfo=timezone.utc).timestamp()
    base={'analysis_estimate':{'low_seconds':15,'high_seconds':30},'analysis_queued_at':'2026-11-13T01:00:00+00:00'}
    running={**base,'id':'run','analysis_state':'running','analysis_started_at':'2026-11-13T01:00:20+00:00','analysis_phase':'notes'}
    waiting={**base,'id':'wait','analysis_state':'queued','analysis_queued_at':'2026-11-13T01:00:10+00:00'}
    later={**base,'id':'later','analysis_state':'queued','analysis_queued_at':'2026-11-13T10:00:15+09:00'}
    result=progress_snapshot([later,waiting,running],now)
    assert result['run']['elapsed_seconds']==10 and result['run']['remaining_seconds']==[5,20]
    assert result['wait']['queue_ahead']==1 and result['wait']['elapsed_seconds']==20
    assert result['wait']['remaining_seconds']==[20,50]
    assert result['later']['queue_ahead']==2 and result['later']['remaining_seconds']==[35,80]
    assert progress_snapshot([running],now+25)['run']['estimate_status']=='overdue'
    running['analysis_phase']='loading'
    result=progress_snapshot([waiting,running],now)
    assert result['run']['remaining_seconds'] is None and result['wait']['estimate_status']=='waiting_unknown'
    running.update(analysis_phase='notes',analysis_loading_seconds=8)
    assert progress_snapshot([running],now)['run']['remaining_seconds']==[13,28]
    assert progress_snapshot([{**running,'analysis_state':'ready'}],now)=={}
    assert progress_snapshot([{**waiting,'deleted_at':'yes'}],now)=={}


def test_registration_api_sets_timestamps_estimate_and_batch(client):
    c,queue=client;p=project(c,'진행시간 검증')
    with w.connect() as db:
        for m in history(100):
            m.update(project_id=p['id'],author='team1',date='2026-11-01',title='기존 분석',version=1,lines=[{'id':'L001','text':'가'*100}],candidates=[],created_at='2026-11-01T00:00:00+00:00')
            w.save(db,'meeting',m)
    payloads=[f'회의명: 일정 검토 {i}\n프로젝트: {p["name"]}\n회의일: 2026-11-13\n'+'납품일과 변경 사양을 확인한다. '*4 for i in range(2)]
    imports=c.post('/api/v3/imports',files=[('files',(f'회의{i}.txt',text.encode(),'text/plain')) for i,text in enumerate(payloads)]).json()['items']
    response=c.post('/api/v3/register',json={'items':[{'id':x['id'],'project_id':p['id'],'confirmed':True} for x in imports]})
    assert response.status_code==202,response.text
    ids=[x['id'] for x in response.json()['registered']]
    data=c.get('/api/v3/workspace').json();rows=[m for m in data['meetings'] if m['id'] in ids]
    assert sorted(m['progress']['queue_ahead'] for m in rows)==[0,1]
    assert all(m['progress']['elapsed_seconds'] is not None and m['progress']['remaining_seconds'] for m in rows)
    assert data['recent_batch']['total']==2 and data['recent_batch']['pending']==2
    with w.connect() as db:
        m=w.read(db,'meeting',ids[0]);m.update(analysis_state='ready');w.save(db,'meeting',m)
    data=c.get('/api/v3/workspace').json()
    assert data['recent_batch']['completed']==1 and data['recent_batch']['pending']==1
    assert next(m for m in data['meetings'] if m['id']==ids[0])['progress'] is None
    assert c.post('/api/v3/meetings/'+ids[0]+'/analyze').status_code==202
    with w.connect() as db:
        m=w.read(db,'meeting',ids[0]);assert m['analysis_started_at'] is None and m['analysis_finished_at'] is None


def test_batch_uses_registration_not_later_retry_and_counts_failure():
    records=[{'id':'a','author':'team1','registration_batch_id':'old','registration_batch_at':'1','analysis_queued_at':'9','analysis_state':'queued'},
             {'id':'b','author':'team1','registration_batch_id':'new','registration_batch_at':'2','analysis_state':'ready'},
             {'id':'c','author':'team1','registration_batch_id':'new','registration_batch_at':'2','analysis_state':'failed'},
             {'id':'d','author':'team1','registration_batch_id':'new','registration_batch_at':'2','analysis_state':'queued','deleted_at':'yes'}]
    batch=recent_batch(records,'team1')
    assert batch=={'id':'new','total':3,'completed':1,'failed':1,'pending':0,'removed':1}
    assert recent_batch(records,'team2') is None
