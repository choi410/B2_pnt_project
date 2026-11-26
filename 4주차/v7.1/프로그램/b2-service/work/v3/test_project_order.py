"""Project ordering uses project creation timestamps, not retrieved meeting prose."""
import pytest
from work.v3.test_connected import client,w
from work.v3.test_questions_trash import project,meeting
from work.v3 import question_policy as policy
from work.v17 import questions


@pytest.fixture(autouse=True)
def isolated_db(tmp_path,monkeypatch):
    monkeypatch.setattr(w,'DB',tmp_path/'projects.sqlite3')
    monkeypatch.setattr(w,'FILES',tmp_path/'files')
    monkeypatch.setattr(questions,'JOBS',{})
    class NoModel:
        def submit(self,*args):raise AssertionError('Project ordering must not generate a name from meeting text')
    monkeypatch.setattr(questions,'POOL',NoModel())


@pytest.mark.parametrize('q,direction',[
    ('제일 첫 프로젝트가 뭐야?','oldest'),
    ('제일 처음 프로젝트 알려줘','oldest'),
    ('가장 먼저 생성한 프로젝트 보여줘','oldest'),
    ('처음 만든 프로젝트가 무엇인가요?','oldest'),
    ('가장 오래된 프로젝트','oldest'),
    ('전체 프로젝트 중 제일 첫 프로젝트는 뭐야?','oldest'),
    ('제일 최근 프로젝트뭐야?','newest'),
    ('가장 최근에 등록된 프로젝트 알려줘','newest'),
    ('최신 프로젝트 찾아줘','newest'),
    ('마지막으로 만든 프로젝트는 뭐야?','newest'),
    ('프로젝트 중 가장 최근에 생긴 거 알려줘','newest'),
    ('그럼 제일 최근 프로젝트는 뭐야?','newest'),
])
def test_order_intent(q,direction):
    assert policy.project_order_question(q)=={'direction':direction,'basis':'created_at'}
    assert policy.project_lookup(q)


@pytest.mark.parametrize('q',[
    '최신 회의록이 뭐야?', '프로젝트의 최근 변경사항 알려줘',
    '제일 최근 프로젝트의 납품일은 언제야?', '첫 프로젝트의 압연 속도는 얼마야?',
    '최근 프로젝트에서 보류된 사항은?', '프로젝트 만들 때 제일 먼저 뭘 해야 해?',
])
def test_does_not_replace_content_questions(q):
    assert policy.project_order_question(q) is None


def stamp(p,value):
    with w.connect() as db:
        p=w.read(db,'project',p['id']);p['created_at']=value;w.save(db,'project',p)


def ask(c,q):
    r=c.post('/api/questions',json={'question':q});assert r.status_code==202,r.text
    data=r.json();assert data['state']=='done',data
    return data['result']


def test_first_and_latest_ignore_meeting_dates_names_and_registration(client):
    c,_=client;new=project(c,'aa');old=project(c,'한빛셀 롤프레스');middle=project(c,'서린 코팅라인')
    stamp(old,'2026-11-12T13:39:55+09:00');stamp(middle,'2026-11-13T11:16:04+09:00');stamp(new,'2026-11-17T10:51:30+09:00')
    meeting(c,new,new['id']+' 회의 제목을 프로젝트 이름으로 답하면 안 된다.','2026-07-09')
    meeting(c,old,date='2026-11-13');meeting(c,middle,date='2026-12-31')
    first=ask(c,'제일 첫 프로젝트가 뭐야?');latest=ask(c,'제일 최근 프로젝트뭐야?')
    assert [p['id'] for p in first['projects']]==[old['id']]
    assert [p['name'] for p in latest['projects']]==['aa']
    assert latest['projects'][0]['created_at']=='2026-11-17T10:51:30+09:00'
    assert '프로젝트를 생성한 시각' in first['notice']


def test_access_and_trash_are_applied_before_ordering(client):
    c,_=client;visible=project(c,'공개 프로젝트');private=project(c,'비공개 프로젝트',members=['team1']);deleted=project(c,'휴지통 프로젝트')
    stamp(visible,'2026-05-01T10:00:00+09:00');stamp(private,'2026-01-01T10:00:00+09:00');stamp(deleted,'2026-12-01T10:00:00+09:00')
    with w.connect() as db:
        deleted=w.read(db,'project',deleted['id']);deleted['deleted_at']=w.now();w.save(db,'project',deleted)
    c.post('/api/demo-login',json={'username':'team2'})
    for q in ('첫 프로젝트가 뭐야?','최근 프로젝트가 뭐야?'):
        assert [p['id'] for p in ask(c,q)['projects']]==[visible['id']]


def test_tied_and_unknown_creation_times_are_not_invented(client):
    c,_=client;a=project(c,'동시 생성 가');b=project(c,'동시 생성 나');unknown=project(c,'날짜 미정')
    stamp(a,'2026-11-18T09:00:00+09:00');stamp(b,'2026-11-18T00:00:00+00:00');stamp(unknown,None)
    result=ask(c,'제일 최근 프로젝트 뭐야?')
    assert {p['id'] for p in result['projects']}=={a['id'],b['id']}
    assert '2개' in result['notice'] and '1개는 비교에서 제외' in result['notice']
    stamp(a,None);stamp(b,'2026-11-18T00:00:00')
    result=ask(c,'첫 프로젝트가 뭐야?')
    assert not result['answerable'] and not result['projects']


@pytest.mark.parametrize('q',[
    '생산 시작일 기준 제일 첫 프로젝트가 뭐야?',
    '회의일 기준 제일 최근 프로젝트 보여줘',
    '회의록 등록일 기준 첫 프로젝트 알려줘',
    '제일 먼저 생산한 프로젝트가 뭐야?',
])
def test_other_date_bases_do_not_silently_use_creation_time(client,q):
    c,_=client;project(c)
    result=ask(c,q)
    assert not result['answerable'] and not result['projects']
    assert '다른 기준' in result['message']


def test_followup_compares_all_projects_not_only_previous_selection(client):
    c,_=client;old=project(c,'앞 대화 프로젝트');new=project(c,'나중 프로젝트')
    stamp(old,'2026-01-01T10:00:00+09:00');stamp(new,'2026-11-01T10:00:00+09:00')
    first=c.post('/api/conversations/questions',json={'question':old['id']+' 프로젝트 찾아줘'}).json()
    result=c.post('/api/conversations/questions',json={'conversation_id':first['id'],'question':'그럼 제일 최근 프로젝트뭐야?'}).json()['messages'][-1]
    assert result['state']=='done' and result['result']['mode']=='project_order'
    assert [p['id'] for p in result['result']['projects']]==[new['id']]
    assert not result['result']['sources']
