"""PM lookup and change-record rankings use records, not generated meeting prose."""
import pytest
from work.v3.test_connected import client, w
from work.v3.test_questions_trash import project, meeting, event
from work.v3.test_project_catalog import no_generation, send
from work.v3.query_intent import metadata_plan


@pytest.mark.parametrize('question', [
    '롤프레스 프로젝트 담당자 누구입니까', '롤 프레스 프로젝트 담당자는 누구야?',
    '롤프레스 프로젝트 PM 알려줘', '롤프레스 프로젝트 책임자가 누구인가요?',
    '롤프레스 프로젝트 누가 담당해?', '롤프레스 프로젝트 누가 관리하나요?',
])
def test_project_owner_is_registered_pm_not_task_owner(client, question):
    c, _ = client
    p=project(c, '한빛셀 전극 롤프레스 1호기')
    meeting(c,p,'진효창이 배치도 개정을 담당한다.')
    with w.connect() as db:
        p['pm']='team2';w.save(db,'project',p)
        expected=w.read(db,'person','team2')['name']
    _,result=send(c,question)
    assert result['mode']=='project_owner' and result['result_project_ids']==[p['id']]
    assert result['sources']==[] and expected in result['points'][0]['text']
    assert 'PM' in result['points'][0]['text']


def test_owner_lookup_without_meetings_missing_pm_and_same_name_choices(client):
    c,_=client;a=project(c,'한빛셀 롤프레스 1호기');b=project(c,'한빛셀 롤프레스 2호기')
    _,ambiguous=send(c,'롤프레스 프로젝트 담당자 누구입니까')
    assert ambiguous['kind']=='clarification'
    assert {p['id'] for p in ambiguous['projects']}=={a['id'],b['id']}
    with w.connect() as db:
        a.pop('pm');w.save(db,'project',a)
    _,result=send(c,a['id']+' 프로젝트 PM 알려줘')
    assert result['mode']=='project_owner'
    assert '확인할 수 없습니다' in result['points'][0]['text']
    _,all_owners=send(c,'전체 프로젝트 담당자 알려줘')
    assert len(all_owners['points'])==2


@pytest.mark.parametrize('question', [
    '가장 변경이력이 많은 프로젝트', '변경이력이 가장 많은 프로젝트 알려줘',
    '변경 기록이 제일 많은 프로젝트는 뭐야?', '프로젝트 중 변경이력이 가장 많은 것은?',
    '변경이력 최다 프로젝트 보여줘',
])
def test_change_count_compares_all_active_records(client,question):
    c,_=client;a=project(c,'한빛셀 롤프레스');b=project(c,'서린 코팅라인')
    m=meeting(c,a);n=meeting(c,b)
    # Several events for the same subject must count as records, not one item.
    event(m,'same','확정','120');event(m,'same','요청','135');event(m,'same','보류','135')
    event(n,'other','확정','650')
    for update in ({'review_state':'제외'},{'superseded_by_revision':2},{'source_revision':99},{'deleted_at':w.now()}):
        e=event(n,'ignored','요청','680');e.update(update)
        with w.connect() as db:w.save(db,'change_event',e)
    for update in ({'deleted_at':w.now()},{'analysis_stale':True}):
        ignored=meeting(c,b,'과거 자료 '+w.uid())
        for _ in range(4):event(ignored,'ignored','요청','680')
        ignored.update(update)
        with w.connect() as db:w.save(db,'meeting',ignored)
    hidden=project(c,'비공개 설비',members=['team1']);secret=meeting(c,hidden)
    removed=project(c,'휴지통 설비');gone=meeting(c,removed)
    for _ in range(5):event(secret,'secret','확정','999');event(gone,'gone','확정','999')
    with w.connect() as db:
        removed['deleted_at']=w.now();w.save(db,'project',removed)
    c.post('/api/demo-login',json={'username':'team2'})
    _,result=send(c,question)
    assert result['mode']=='change_rank'
    assert result['count']==3 and result['result_project_ids']==[a['id']]
    assert result['compared_projects']==2 and result['sources']==[]


def test_ties_zero_records_and_project_reference_followup(client):
    c,_=client;a=project(c,'한빛셀 롤프레스');b=project(c,'서린 코팅라인')
    _,result=send(c,'가장 변경이력이 많은 프로젝트')
    assert result['count']==0 and not result['result_project_ids']
    ma=meeting(c,a);mb=meeting(c,b)
    event(ma,'t1','확정','120');event(mb,'t2','요청','650')
    _,tie=send(c,'가장 변경이력이 많은 프로젝트')
    assert '공동 1위' in tie['message'] and set(tie['result_project_ids'])=={a['id'],b['id']}
    event(ma,'t1','철회','120')
    thread,rank=send(c,'가장 변경이력이 많은 프로젝트')
    assert rank['result_project_ids']==[a['id']]
    _,owner=send(c,'그 프로젝트 담당자는 누구야?',thread['id'])
    assert owner['mode']=='project_owner' and owner['result_project_ids']==[a['id']]


def test_rank_is_not_limited_to_preceding_project(client):
    c,_=client;a=project(c,'한빛셀 롤프레스');b=project(c,'서린 코팅라인')
    m=meeting(c,b);event(m,'t','요청','650')
    thread,_=send(c,'롤프레스 프로젝트 담당자 누구입니까')
    _,result=send(c,'가장 변경이력이 많은 프로젝트',thread['id'])
    assert result['result_project_ids']==[b['id']]


@pytest.mark.parametrize('question', [
    '프로젝트의 속도 변경 담당자는 누구야?', '프로젝트를 누가 생성했어?',
    '프로젝트 설계 담당자 누구입니까', '프로젝트가 변경이력이 많은 이유는 뭐야?',
    '7월 변경이력이 가장 많은 프로젝트', '합의된 변경이력이 가장 많은 프로젝트',
    '완료된 프로젝트 담당자 누구야?', '프로젝트 PM 변경해줘',
])
def test_other_meanings_never_silently_become_pm_or_all_time_counts(question):
    assert metadata_plan(question) is None
