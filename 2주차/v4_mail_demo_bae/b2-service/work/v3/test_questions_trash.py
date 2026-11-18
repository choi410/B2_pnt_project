"""Regression coverage with disposable DB/files; never touches demo records."""
from work.v3.test_connected import client,w
from work.v3 import question_policy as policy
from work.v17 import questions
from fastapi import HTTPException
import pytest


def test_inline_source_ids_are_not_spec_numbers():
    sources=[{'id':'S2','text':'속도 변경을 요청했다.','date':'2026-11-05','project_id':'p','project_name':'롤프레스'},
             {'id':'S3','text':'통로 공간이 부족해 측면 슬라이드 요청을 철회했다.','date':'2026-11-12','project_id':'p','project_name':'롤프레스'}]
    raw={'answerable':True,'points':[{'text':'S3에서 통로 공간이 부족해 요청을 철회했다.','sources':['S2']}]}
    result=questions.validate_answer(raw,sources)
    assert result[0]['sources']==['S2','S3'] and 'S3' not in result[0]['text']
    raw['points'][0]['text']='S99에서 요청을 철회했다.'
    with pytest.raises(ValueError):questions.validate_answer(raw,sources)
    raw['points'][0]['text']='속도는 999 m/min으로 확정했다.'
    with pytest.raises(ValueError):questions.validate_answer(raw,sources)
    sources[1]['project_id']='other';raw['points'][0]['text']='S3에서 요청을 철회했다.'
    with pytest.raises(ValueError):questions.validate_answer(raw,sources)


def project(c,name='한빛셀 롤프레스 1호기',members=None):
    r=c.post('/api/projects',json={'name':name,'members':members or ['team1','team2']});assert r.status_code==201,r.text
    return r.json()


def meeting(c,p,text='납품일은 2026-12-18로 합의했다.',date='2026-11-01'):
    content=f'회의명: {date} 협의\n회의일: {date}\n프로젝트: {p["name"]}\n{text}'
    item=c.post('/api/v3/imports',files=[('files',('회의.txt',content.encode(),'text/plain'))]).json()['items'][0]
    r=c.post('/api/v3/register',json={'items':[{'id':item['id'],'project_id':p['id'],'date':date}]});assert r.status_code==202,r.text
    mid=r.json()['registered'][0]['id']
    with w.connect() as db:
        m=w.read(db,'meeting',mid);m.update(analysis_state='ready');w.save(db,'meeting',m)
    return m


def event(m,tid,state,value,ident=None):
    e={'id':ident or w.uid(),'project_id':m['project_id'],'meeting_id':m['id'],'topic_id':tid,'title':'장비 납품일','category':'납기','after':value,'before':'','business_state':state,'review_state':'검토 전','source_revision':m['revision'],'effective_date':m['date'],'evidence':[m['lines'][-1]['id']]}
    with w.connect() as db:w.save(db,'change_event',e)
    return e


def test_partial_name_permissions_and_ambiguity(client):
    c,_=client;p=project(c,'고유고객 롤프레스 1호기');p2=project(c,'고유고객 롤프레스 2호기');secret=project(c,'비공개 코팅라인',members=['team1'])
    c.post('/api/demo-login',json={'username':'team2'})
    r=c.post('/api/questions',json={'question':p['id']+' 프로젝트 찾아줘'}).json()
    assert r['state']=='done' and [x['id'] for x in r['result']['projects']]==[p['id']]
    r=c.post('/api/questions',json={'question':'비공개 프로젝트 찾아줘'}).json()
    assert r['result']['projects']==[]
    r=c.post('/api/questions',json={'question':'고유고객 납품일은 언제야?'}).json()
    assert r['result']['kind']=='clarification' and len(r['result']['projects'])==2
    r=c.post('/api/questions',json={'question':'롤프레스 2호기 프로젝트 찾아줘'}).json()
    assert [x['id'] for x in r['result']['projects']]==[p2['id']]
    c.post('/api/demo-login',json={'username':'team1'})
    v=c.get('/api/projects/'+p2['id']+'/trash-preview').json()['version']
    c.post('/api/projects/'+p2['id']+'/trash',json={'version':v})
    r=c.post('/api/questions',json={'question':'고유고객 프로젝트 찾아줘'}).json()
    assert [x['id'] for x in r['result']['projects']]==[p['id']]


def test_agreement_answer_keeps_hold_request_and_sources(client,monkeypatch):
    c,_=client;p=project(c,'기준검증 롤프레스');m1=meeting(c,p);m2=meeting(c,p,'납품일 2026-12-23 변경 요청은 보류했다. 기존 납품일 2026-12-18을 유지한다.','2026-11-12')
    tid=w.uid()
    with w.connect() as db:w.save(db,'change_topic',{'id':tid,'project_id':p['id'],'title':'장비 납품일','category':'납기'})
    event(m1,tid,'확정','2026-12-18');event(m2,tid,'보류','2026-12-23')
    class NoModel:
        def submit(self,*args):raise AssertionError('Fast answers must not use model queue')
    monkeypatch.setattr(questions,'POOL',NoModel())
    r=c.post('/api/questions',json={'question':'기준검증 현재 납품일은 언제야?'}).json()
    assert r['state']=='done',r
    result=r['result'];assert result['answerable'] and '2026-12-18' in result['points'][0]['text']
    assert '2026-12-23' not in result['points'][0]['text'] and '보류' in result['points'][0]['text']
    assert len(result['sources'])==2 and '확인·반영된' not in result['notice']
    s=result['sources'][0]
    proof=c.get('/api/questions/'+r['id']+'/sources/'+s['id']);assert proof.status_code==200,proof.text
    assert proof.json()['highlight']
    # Editing the source invalidates an already displayed answer.
    with w.connect() as db:
        m=w.read(db,'meeting',m1['id']);m['revision']+=1;m['analysis_stale']=True;w.save(db,'meeting',m)
    assert c.get('/api/questions/'+r['id']).json()['state']=='failed'
    with w.connect() as db:
        assert policy.recorded_agreements(w,db,[p],'현재 납품일은 언제야?') is None


def test_generic_question_searches_all_without_forcing_choice(client,monkeypatch):
    c,_=client;p=project(c,'전체검색 검증 1');p2=project(c,'전체검색 검증 2')
    meeting(c,p,'고객 요청은 보류했다.');meeting(c,p2,'온도 변경은 보류했다.')
    class Immediate:
        def submit(self,fn,*args):fn(*args)
    monkeypatch.setattr(questions,'POOL',Immediate())
    def retrieve(w,pid,docs,q):
        d=docs[0];return [{k:v for k,v in d.items() if k!='body'}|{'text':d['body'],'line_ids':['L004'],'score':1}]
    monkeypatch.setattr(questions,'retrieve',retrieve)
    monkeypatch.setattr(questions,'generate',lambda w,q,sources,compact=False:{'answerable':True,'points':[{'text':'회의록에 보류 기록이 있습니다.','sources':[sources[0]['id']]}]})
    r=c.post('/api/questions',json={'question':'최근 회의에서 보류된 사항은?'}).json()
    result=c.get('/api/questions/'+r['id']).json()['result']
    assert result['kind']=='documents'
    assert {p['id'],p2['id']}<={x['project_id'] for x in result['points']}


def test_v3_events_without_topics_and_false_agreement(client):
    c,_=client;p=project(c,'원문 대조 검증');m=meeting(c,p,'납품일은 2026-12-18로 합의했다.')
    event(m,None,'확정','2026-12-18로 합의했다')
    newer=meeting(c,p,'납품일 2026-12-23을 요청했다. 아직 합의하지 않았다.','2026-11-12')
    # Even a wrong model classification must not silently publish the request.
    e=event(newer,'auto-topic','확정','2026-12-23')
    with w.connect() as db:assert policy.recorded_agreements(w,db,[p],'현재 납품일은 언제야?') is None
    with w.connect() as db:
        e['business_state']='요청';w.save(db,'change_event',e)
        a=policy.recorded_agreements(w,db,[p],'현재 납품일은 언제야?')
    assert a['points'][0]['text'].startswith('장비 납품일: 2026-12-18 ')


def test_held_items_use_explicit_source_not_wrong_classification(client):
    c,_=client;p=project(c,'보류 원문 검증')
    held=meeting(c,p,'납품일 2026-12-23 변경 요청을 보류했다.')
    event(held,None,'보류','2026-12-23')
    withdrawn=meeting(c,p,'슬라이드 방식 요청은 철회했다. 여닫이 방식을 유지한다.','2026-11-12')
    e=event(withdrawn,None,'보류','여닫이 유지')
    with w.connect() as db:
        e.update(title='점검 커버',category='사양');w.save(db,'change_event',e)
        r=policy.held_items(w,db,[p],'최근 회의에서 보류된 사항은?')
    assert len(r['points'])==1 and '2026-12-23' in r['points'][0]['text']
    assert '여닫이' not in r['points'][0]['text']


def trash_item(c,m):
    assert c.delete('/api/v3/meetings/'+m['id']).status_code==200
    return c.get('/api/v3/trash/meeting/'+m['id']).json()


def purge(c,item):
    return c.request('DELETE','/api/v3/trash/'+item['kind']+'/'+item['id'],json={'version':item['version'],'confirmed':True})


def test_meeting_purge_cleans_own_changes_and_files_only(client):
    c,_=client;p=project(c,'삭제 검증');m=meeting(c,p);other=meeting(c,p,'다른 회의록은 남긴다.','2026-11-02');tid=w.uid()
    with w.connect() as db:w.save(db,'change_topic',{'id':tid,'project_id':p['id'],'title':'납품일','category':'납기'})
    e=event(m,tid,'확정','2026-12-18')
    path=w.FILES/'shared-proof.txt';path.write_text('shared')
    with w.connect() as db:
        # A file referenced by another record must not be removed.
        x=w.read(db,'meeting',m['id']);x['pdf']=str(path);w.save(db,'meeting',x)
        x=w.read(db,'meeting',other['id']);x['pdf']=str(path);w.save(db,'meeting',x)
    assert c.get('/api/v3/trash/meeting/'+m['id']).status_code==409
    item=trash_item(c,m)
    c.post('/api/demo-login',json={'username':'team2'})
    assert purge(c,item).status_code in (403,409)
    c.post('/api/demo-login',json={'username':'team1'})
    assert c.request('DELETE','/api/v3/trash/meeting/'+m['id'],json={'version':item['version']-1,'confirmed':True}).status_code==409
    assert purge(c,item).status_code==200
    assert path.exists() and not __import__('pathlib').Path(m['original_path']).exists()
    with w.connect() as db:
        assert w.read(db,'meeting',other['id'])
        assert not any(x['id']==e['id'] for x in w.all_records(db,'change_event'))
        assert not any(x['id']==tid for x in w.all_records(db,'change_topic'))
    assert c.post('/api/v3/meetings/'+m['id']+'/restore').status_code==404


def test_purge_blocks_linked_tasks_and_external_paths(client):
    c,_=client;p=project(c,'보호 검증');m=meeting(c,p);item=trash_item(c,m)
    with w.connect() as db:w.save(db,'task',{'id':'linked-'+m['id'],'project_id':p['id'],'meeting_id':m['id']})
    assert purge(c,item).status_code==409
    with w.connect() as db:
        db.execute('DELETE FROM records WHERE kind=? AND id=?',('task','linked-'+m['id']))
        x=w.read(db,'meeting',m['id']);x['original_path']=str(w.DATA_DIR/'outside-files.txt');w.save(db,'meeting',x)
    r=purge(c,item);assert r.status_code==409 and '경로' in r.text
    with w.connect() as db:assert w.read(db,'meeting',m['id'])


def test_project_restore_and_purge_cascade(client):
    c,_=client;p=project(c,'프로젝트 영구 삭제');m=meeting(c,p);other=project(c,'유지 프로젝트')
    version=c.get('/api/projects/'+p['id']+'/trash-preview').json()['version']
    assert c.post('/api/projects/'+p['id']+'/trash',json={'version':version}).status_code==200
    item=c.get('/api/v3/trash/project/'+p['id']).json();assert item['counts']['meeting']==1
    assert c.post('/api/projects/'+p['id']+'/restore',json={'version':item['version']}).status_code==200
    assert purge(c,item).status_code==409
    version=c.get('/api/projects/'+p['id']+'/trash-preview').json()['version']
    c.post('/api/projects/'+p['id']+'/trash',json={'version':version})
    item=c.get('/api/v3/trash/project/'+p['id']).json()
    assert purge(c,item).status_code==200
    with w.connect() as db:
        assert w.read(db,'project',other['id'])
        assert not any(x['id']==m['id'] for x in w.all_records(db,'meeting'))
    assert not __import__('pathlib').Path(m['original_path']).exists()
    assert c.post('/api/projects/'+p['id']+'/restore',json={'version':item['version']}).status_code==404

