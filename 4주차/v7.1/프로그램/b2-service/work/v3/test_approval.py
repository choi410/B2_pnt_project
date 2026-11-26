"""Customer approval mail: isolated database, console mail mode, no real SMTP."""
import os, tempfile
os.environ['B2_TEAM_TESTING']='1'
os.environ['B2_TEAM_DATA_DIR']=tempfile.mkdtemp(prefix='b2-v3-approval-tests-')
from fastapi.testclient import TestClient
from work.v3.server import app, legacy as w
from work.v3 import mailer
import pytest

class Queue:
    def __init__(self):self.jobs=[]
    def submit(self,*args):self.jobs.append(args)

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(w,'POOL',Queue());monkeypatch.setattr(w,'PREVIEW_POOL',Queue())
    for key in ('MAIL_MODE','SMTP_HOST','SMTP_USER','SMTP_PASSWORD','MAIL_FROM','APP_BASE_URL','APPROVAL_EXPIRE_DAYS'):monkeypatch.delenv(key,raising=False)
    with TestClient(app,headers={'X-B2-Request':'workspace'}) as c:
        assert c.post('/api/demo-login',json={'username':'team1'}).status_code==200
        with w.connect() as db:before={(r['kind'],r['id']) for r in db.execute('SELECT kind,id FROM records')}
        yield c
        # Test modules share one database; leave no projects or meetings behind for the others.
        with w.connect() as db:
            for kind,ident in {(r['kind'],r['id']) for r in db.execute('SELECT kind,id FROM records')}-before:
                db.execute('DELETE FROM records WHERE kind=? AND id=?',(kind,ident))

def meeting(c,name):
    p=c.post('/api/projects',json={'name':name,'members':['team1','team2']}).json()
    content=f'프로젝트: {p["name"]}\n회의명: 승인 대상 회의\n회의일: 2026-11-12\n라인 속도는 50 m/min으로 합의했다.\n납품일은 2026-12-18로 합의했다.'
    item=c.post('/api/v3/imports',files=[('files',(name+'.txt',content.encode(),'text/plain'))]).json()['items'][0]
    result=c.post('/api/v3/register',json={'items':[{'id':item['id'],'project_id':p['id'],'title':item['title'],'date':item['meeting_date']}]})
    assert result.status_code==202,result.text
    mid=result.json()['registered'][0]['id']
    # Registration is queued; approval is only allowed after analysis/review.
    assert c.post(f'/api/v3/meetings/{mid}/approval-requests',json={'email':'customer@example.com'}).status_code==409
    with w.connect() as db:
        record=w.read(db,'meeting',mid)
        record.update(analysis_state='ready',analysis_stale=False)
        w.save(db,'meeting',record)
    return p['id'],mid

def send(c,mid,**body):
    response=c.post(f'/api/v3/meetings/{mid}/approval-requests',json={'email':'customer@example.com',**body})
    assert response.status_code==201,response.text
    return response.json(),response.json()['link'].rsplit('/',1)[1]

def listed(c,mid):
    return next(m for m in c.get('/api/v3/workspace').json()['meetings'] if m['id']==mid)['approval']

def test_send_view_and_approve(client,capsys):
    c=client;_,mid=meeting(c,'승인 흐름 검증')
    assert listed(c,mid) is None
    assert c.post(f'/api/v3/meetings/{mid}/approval-requests',json={'email':'주소아님'}).status_code==422
    result,token=send(c,mid,name='홍길동',message='확인 부탁드립니다.')
    assert result['mode']=='console' and result['link'].startswith('http://testserver/#/approval/')   # the address the PM is using
    printed=capsys.readouterr().out
    assert result['link'] in printed and '홍길동님' in printed
    with w.connect() as db:
        stored=db.execute("SELECT payload FROM records WHERE kind='approval_request' AND json_extract(payload,'$.meeting_id')=?",(mid,)).fetchall()
    assert len(stored)==1 and token not in stored[0][0]   # only the hash is kept
    assert listed(c,mid)['status']=='sent'
    c.cookies.clear()   # the customer has no login
    view=c.get('/api/v3/approvals/'+token).json()
    assert view['status']=='sent' and view['project_name']=='승인 흐름 검증' and any('50 m/min' in x for x in view['lines'])
    assert view['pages']==0 and c.get(f'/api/v3/approvals/{token}/pages/1').status_code==404   # a text upload has no page images
    assert c.get('/api/v3/approvals/없는토큰').status_code==404
    assert c.post('/api/v3/approvals/'+token,json={'decision':'maybe'}).status_code==422
    assert c.post('/api/v3/approvals/'+token,json={'decision':'approved','comment':'확인했습니다.'}).json()=={'status':'approved'}
    assert c.post('/api/v3/approvals/'+token,json={'decision':'rejected'}).status_code==409   # single use
    assert c.get('/api/v3/approvals/'+token).json()['comment']=='확인했습니다.'
    assert c.post('/api/demo-login',json={'username':'team1'}).status_code==200
    state=listed(c,mid);assert state['status']=='approved' and state['comment']=='확인했습니다.' and not state['outdated']
    assert [x['status'] for x in c.get(f'/api/v3/meetings/{mid}/approval-requests').json()]==['approved']

def test_link_base_must_be_an_address_this_server_answers_on(client,monkeypatch):
    c=client;_,mid=meeting(c,'링크 주소 검증')
    monkeypatch.setenv('APP_BASE_URL','http://localhost:5173')   # copied from another project: ignored
    assert send(c,mid)[0]['link'].startswith('http://testserver/#/approval/')
    from work.v17 import team_config
    monkeypatch.setenv('APP_BASE_URL',f'http://localhost:{team_config.PORT}/')
    assert send(c,mid)[0]['link'].startswith(f'http://localhost:{team_config.PORT}/#/approval/')

def test_resend_reject_and_expiry(client):
    c=client;_,mid=meeting(c,'재발송 검증')
    _,first=send(c,mid);_,second=send(c,mid)
    old=c.get('/api/v3/approvals/'+first).json()
    assert old['status']=='canceled' and 'lines' not in old
    assert c.get(f'/api/v3/approvals/{first}/pages/1').status_code==410   # a replaced link shows no pages
    assert c.post('/api/v3/approvals/'+first,json={'decision':'approved'}).status_code==410
    assert c.post('/api/v3/approvals/'+second,json={'decision':'rejected','comment':'속도 재확인'}).status_code==200
    assert [x['status'] for x in c.get(f'/api/v3/meetings/{mid}/approval-requests').json()]==['rejected','canceled']
    assert listed(c,mid)['comment']=='속도 재확인'
    result,third=send(c,mid)
    with w.connect() as db:
        request=w.read(db,'approval_request',result['id']);request['expires_at']='2020-01-01T00:00:00+09:00';w.save(db,'approval_request',request)
    assert c.get('/api/v3/approvals/'+third).json()['status']=='expired'
    assert c.post('/api/v3/approvals/'+third,json={'decision':'approved'}).status_code==410
    assert listed(c,mid)['status']=='expired'

def test_only_project_pm_sends_and_failure_changes_nothing(client,monkeypatch):
    c=client;_,mid=meeting(c,'권한 검증')
    _,token=send(c,mid)
    assert c.post('/api/demo-login',json={'username':'team2'}).status_code==200
    assert c.post(f'/api/v3/meetings/{mid}/approval-requests',json={'email':'customer@example.com'}).status_code==403
    assert c.get(f'/api/v3/meetings/{mid}/approval-requests').status_code==200   # members may read
    assert c.post('/api/demo-login',json={'username':'team1'}).status_code==200
    monkeypatch.setenv('MAIL_MODE','smtp')   # no SMTP settings: sending fails before any write
    failed=c.post(f'/api/v3/meetings/{mid}/approval-requests',json={'email':'customer@example.com'})
    assert failed.status_code==502 and '메일 설정' in failed.json()['detail']
    def refuse(*args):raise mailer.MailError('메일을 보내지 못했습니다.')
    monkeypatch.setattr(mailer,'send',refuse)
    assert c.post(f'/api/v3/meetings/{mid}/approval-requests',json={'email':'customer@example.com'}).status_code==502
    assert len(c.get(f'/api/v3/meetings/{mid}/approval-requests').json())==1
    assert c.get('/api/v3/approvals/'+token).json()['status']=='sent'   # earlier link still valid

def test_source_edit_keeps_sent_body_and_trash_closes_link(client):
    c=client;_,mid=meeting(c,'본문 수정 검증')
    _,token=send(c,mid)
    with w.connect() as db:   # the body can be edited only after analysis has finished
        ready=w.read(db,'meeting',mid);ready.update(analysis_state='ready');w.save(db,'meeting',ready)
    m=c.get('/api/meetings/'+mid).json()
    edited=c.patch(f'/api/v3/meetings/{mid}/source',json={'version':m['version'],'title':m['title'],'date':m['date'],'reason':'합의 내용 정정','source':m['source']+'\n라인 속도는 60 m/min으로 다시 합의했다.'})
    assert edited.status_code==202,edited.text
    assert not any('60 m/min' in x for x in c.get('/api/v3/approvals/'+token).json()['lines'])
    assert listed(c,mid)['outdated']
    assert c.request('DELETE','/api/v3/meetings/'+mid,json={'reason':'최신 합의 회의록으로 대체'}).status_code==200
    assert c.get('/api/v3/approvals/'+token).status_code==410
    assert c.post('/api/v3/approvals/'+token,json={'decision':'approved'}).status_code==410
    assert c.post(f'/api/v3/meetings/{mid}/approval-requests',json={'email':'customer@example.com'}).status_code==409
    assert c.post(f'/api/v3/meetings/{mid}/restore').status_code==200
    assert c.get('/api/v3/approvals/'+token).json()['status']=='sent'
    assert c.request('DELETE','/api/v3/meetings/'+mid,json={'reason':'최신 합의 회의록으로 대체'}).status_code==200
    info=c.get('/api/v3/trash/meeting/'+mid).json();assert not info['blocked'],info
    purged=c.request('DELETE','/api/v3/trash/meeting/'+mid,json={'version':info['version'],'confirmed':True,'reason':'폐기 확정'})
    assert purged.status_code==200,purged.text
    assert c.get('/api/v3/approvals/'+token).status_code==404
    with w.connect() as db:
        assert not db.execute("SELECT 1 FROM records WHERE kind='approval_request' AND json_extract(payload,'$.meeting_id')=?",(mid,)).fetchone()


def test_internal_correction_changes_source_only_after_team_lead_approval(client):
    c=client
    pid,mid=meeting(c,'회의록 정정 승인 검증')
    original=c.get(f'/api/meetings/{mid}').json()
    change={'action':'source','project_id':pid,'target_id':mid,'title':original['title'],
            'date':original['date'],'source':original['source']+'\n납품 일정을 정정합니다.',
            'reason':'고객과 재확인한 일정 반영'}
    assert c.post('/api/demo-login',json={'username':'team2'}).status_code==200
    submitted=c.post('/api/v3/management/requests',json=change)
    assert submitted.status_code==201,submitted.text
    request_id=submitted.json()['id']
    assert c.get(f'/api/meetings/{mid}').json()['source']==original['source']
    assert c.get('/api/v3/management/news').json()['count']==0
    decision=f'/api/v3/management/requests/{request_id}/decision'
    assert c.post(decision,json={'approved':True}).status_code==403

    assert c.post('/api/demo-login',json={'username':'team1'}).status_code==200
    inbox=c.get('/api/v3/management/news').json()
    assert inbox['count']==1 and inbox['items'][0]['request_id']==request_id
    assert c.post(f"/api/v3/management/news/{inbox['items'][0]['id']}/read").status_code==200
    assert c.get('/api/v3/management/news').json()['count']==0
    assert c.get(f'/api/v3/management/requests/{request_id}').json()['status']=='pending'
    assert c.post(decision,json={'approved':True}).status_code==200
    assert c.post(decision,json={'approved':True}).status_code==409
    updated=c.get(f'/api/meetings/{mid}').json()
    assert updated['source']==change['source'] and updated['revision']==original['revision']+1
    assert updated['analysis_state']=='queued'

    assert c.post('/api/demo-login',json={'username':'team2'}).status_code==200
    inbox=c.get('/api/v3/management/news').json()
    assert inbox['count']==1 and inbox['items'][0]['request_id']==request_id
    history=c.get('/api/v3/management/history',params={'project_id':pid,'meeting_id':mid,'kind':'request'}).json()
    assert {event['label'] for event in history['items']}=={'회의록 정정 요청','회의록 정정 요청 승인'}


def test_grouped_history_keeps_request_approval_and_trash_together(client):
    c=client
    pid,mid=meeting(c,'통합 기록 묶음 검증')
    assert c.post('/api/demo-login',json={'username':'team2'}).status_code==200
    response=c.post('/api/v3/management/requests',json={
        'action':'trash','project_id':pid,'target_id':mid,'reason':'중복 등록'
    })
    assert response.status_code==201,response.text
    request_id=response.json()['id']
    assert c.post('/api/demo-login',json={'username':'team1'}).status_code==200
    assert c.post(f'/api/v3/management/requests/{request_id}/decision',json={'approved':True}).status_code==200
    params={'project_id':pid,'meeting_id':mid,'group_requests':True}
    for category in ('','request','trash'):
        result=c.get('/api/v3/management/history',params={**params,'kind':category}).json()
        groups=[item for item in result['items'] if item.get('request_id')==request_id]
        assert len(groups)==1
        assert {event['label'] for event in groups[0]['events']}=={
            '회의록 휴지통 이동 요청','회의록 휴지통 이동 요청 승인','회의록 휴지통 이동'
        }
    assert c.get('/api/v3/management/history',params={**params,'kind':'mail'}).json()['items']==[]
