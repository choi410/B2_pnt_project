"""변경이력 2단계 승인: 참여자 1차 검수 → PM 최종 승인 → 공식 변경이력·AI 답변 반영."""
import pytest
from work.v3.test_member_review import client,event,login,review,notices
from work.v3.test_connected import w
from work.v3.test_questions_trash import project,meeting
from work.v3.project_facts import active_changes


@pytest.fixture
def approval_on(monkeypatch):
    monkeypatch.setenv('B2_CHANGE_APPROVAL','1')


def workspace(c,m):
    d=c.get('/api/v3/workspace').json()
    meeting_=next(x for x in d['meetings'] if x['id']==m['id'])
    return meeting_['change_approval'],{e['id']:e for e in d['changes'] if e['meeting_id']==m['id']}


def approve(c,m):
    with w.connect() as db:rev=w.read(db,'meeting',m['id'])['revision']
    return c.post('/api/v3/meetings/'+m['id']+'/approve-changes',json={'revision':rev})


def official(m):
    with w.connect() as db:
        p=w.read(db,'project',m['project_id'])
        return {e['id'] for e in active_changes(w,db,[p])[0]}


def setup(c):
    p=project(c,'승인 흐름 '+w.uid()[:6],members=['team1','team2','team3'])   # PM: team1
    login(c,'team2')
    m=meeting(c,p,'납품일은 2026-12-18로 합의했다.\n라인 속도는 135 m/min으로 합의했다.')
    return p,m,event(m,'t-a','확정','2026-12-18'),event(m,'t-b','확정','135 m/min')


def test_member_review_then_pm_approval_publishes(client,approval_on):
    c=client;p,m,a,b=setup(c)
    assert workspace(c,m)[0]['state']=='reviewing' and not official(m)

    login(c,'team3')
    assert review(c,a,'확인').status_code==200 and review(c,b,'제외').status_code==200
    state,items=workspace(c,m)
    assert state['state']=='pending' and not items[a['id']]['listed'] and not official(m)
    # 승인 전에는 참여자가 아직 고칠 수 있다.
    assert review(c,a,'검토 전').status_code==200 and review(c,a,'확인').status_code==200
    # 승인은 PM만
    assert approve(c,m).status_code==403

    login(c,'team1')
    assert any('승인 대기' in n['title'] for n in notices(c) if n['target_id']==m['id'])
    stale=c.post('/api/v3/meetings/'+m['id']+'/approve-changes',json={'revision':99})
    assert stale.status_code==409
    r=approve(c,m);assert r.status_code==200,r.text
    assert r.json()['change_approval']['state']=='approved'
    state,items=workspace(c,m)
    assert state['state']=='approved' and state['by']=='team1'
    assert items[a['id']]['listed'] and not items[b['id']]['listed']
    assert official(m)=={a['id']}
    assert approve(c,m).status_code==409                       # 두 번 승인하지 않는다

    for who in ('team2','team3'):                               # 등록자·검수자에게 승인 알림
        login(c,who)
        assert any(n['title'].startswith('변경이력 승인') for n in notices(c) if n['target_id']==m['id'])


def test_change_after_approval_needs_pm_and_reapproval(client,approval_on):
    c=client;p,m,a,b=setup(c)
    login(c,'team3');review(c,a,'확인');review(c,b,'확인')
    login(c,'team1');assert approve(c,m).status_code==200
    assert official(m)=={a['id'],b['id']}

    login(c,'team3')
    assert review(c,a,'검토 전').status_code==403              # 승인 뒤에는 PM만
    login(c,'team1')
    assert review(c,a,'검토 전').status_code==200
    assert workspace(c,m)[0]['state']=='reviewing' and not official(m)   # 승인이 풀린다

    login(c,'team3')
    assert review(c,a,'확인').status_code==200                  # 다시 열려 참여자가 검수
    assert workspace(c,m)[0]['state']=='pending' and not official(m)
    login(c,'team1')
    assert approve(c,m).status_code==200 and official(m)=={a['id'],b['id']}


def test_cannot_approve_with_open_items(client,approval_on):
    c=client;p,m,a,b=setup(c)
    login(c,'team1');review(c,a,'확인')
    r=approve(c,m);assert r.status_code==409 and '검토 전' in r.json()['detail']


def test_existing_meetings_keep_review_only_rule(client,monkeypatch):
    monkeypatch.setenv('B2_CHANGE_APPROVAL','0')
    c=client;p,m,a,b=setup(c)
    login(c,'team3');review(c,a,'확인');review(c,b,'제외')
    state,items=workspace(c,m)
    assert state['state']=='legacy' and items[a['id']]['listed'] and official(m)=={a['id']}
    login(c,'team1')
    assert approve(c,m).status_code==409
