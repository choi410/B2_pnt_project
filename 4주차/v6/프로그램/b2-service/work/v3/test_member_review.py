"""팀원 검수(2026-11-23): 참여자는 검수가 끝나기 전까지 확인·제외·수정, 끝나면 PM만. 등록·검수 완료는 PM에게 알림."""
from work.v3.test_connected import w,app,Queue
from fastapi.testclient import TestClient
from work.v3.test_questions_trash import project,meeting,event as raw_event
import pytest


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(w,'DATA_DIR',tmp_path)
    monkeypatch.setattr(w,'DB',tmp_path/'workspace.sqlite3')
    monkeypatch.setattr(w,'FILES',tmp_path/'files')
    monkeypatch.setattr(w,'POOL',Queue())
    with TestClient(app,headers={'X-B2-Request':'workspace'}) as c:
        assert c.post('/api/demo-login',json={'username':'team1'}).status_code==200
        yield c


def event(m,tid,state,value):
    e=raw_event(m,tid,state,value)
    with w.connect() as db:
        e=w.read(db,'change_event',e['id']) if isinstance(e,dict) and e.get('id') else e
        e.setdefault('version',1);e.setdefault('quotes',[m['lines'][-1]['text']]);w.save(db,'change_event',e)
    return e


def login(c,who):
    assert c.post('/api/demo-login',json={'username':who}).status_code==200


def review(c,e,action):
    with w.connect() as db:version=w.read(db,'change_event',e['id'])['version']
    return c.post('/api/v3/changes/'+e['id']+'/review',json={'version':version,'action':action,'link_to':''})


def notices(c):
    return c.get('/api/notifications').json()['items']


def test_member_reviews_until_done_and_pm_is_notified(client):
    c=client
    p=project(c,'팀원 검수 '+w.uid()[:6],members=['team1','team2','team3'])
    login(c,'team2')
    m=meeting(c,p,'납품일은 2026-12-18로 합의했다.\n라인 속도는 135 m/min으로 합의했다.')
    a=event(m,'t-a','확정','2026-12-18');b=event(m,'t-b','확정','135 m/min')

    # 등록 알림: PM(team1)에게만
    login(c,'team1')
    reg=[n for n in notices(c) if n['target_id']==m['id']]
    assert len(reg)==1 and reg[0]['title'].startswith('회의록 등록') and reg[0]['actor']=='team2'

    # 참여자(team3)도 검수 가능 — 첫 항목 확인, 아직 알림 없음
    login(c,'team3')
    assert review(c,a,'확인').status_code==200
    login(c,'team1')
    assert not any('검수 완료' in n['title'] for n in notices(c))

    # 마지막 항목 제외 → 검수 완료, PM에게 결과 알림 한 번
    login(c,'team3')
    r=review(c,b,'제외');assert r.status_code==200,r.text
    assert r.json()['reviewed_by']=='team3'
    login(c,'team1')
    done=[n for n in notices(c) if '검수 완료' in n['title']]
    assert len(done)==1 and '확인 1 · 제외 1' in done[0]['title'] and done[0]['target_id']==m['id']

    # 검수가 끝난 뒤 되돌리기·수정은 PM만
    login(c,'team3')
    assert review(c,a,'검토 전').status_code==403
    login(c,'team1')
    assert review(c,a,'검토 전').status_code==200
    # PM이 되돌린 뒤에는 다시 검수가 열려 참여자가 할 수 있다(완료 알림은 중복되지 않음)
    login(c,'team3')
    assert review(c,a,'확인').status_code==200
    login(c,'team1')
    assert len([n for n in notices(c) if '검수 완료' in n['title']])==1


def test_non_member_and_pm_own_work(client):
    c=client
    p=project(c,'참여자 아님 '+w.uid()[:6],members=['team1','team2'])
    m=meeting(c,p,'납품일은 2026-12-18로 합의했다.')
    e=event(m,'t-x','확정','2026-12-18')
    login(c,'team4')                                   # 참여자가 아님
    assert review(c,e,'확인').status_code==403
    login(c,'team1')                                   # PM이 등록·검수한 것은 본인에게 알리지 않음
    assert review(c,e,'확인').status_code==200
    assert not [n for n in notices(c) if n['target_id']==m['id']]
