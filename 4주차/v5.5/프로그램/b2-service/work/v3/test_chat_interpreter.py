"""Test server execution independently from language-model accuracy."""
from copy import deepcopy
import threading
import pytest
from work.v3.test_connected import client,w
from work.v3.test_questions_trash import project,meeting,event
from work.v3.test_project_order import stamp
from work.v3 import chat_interpreter as language, chat_jobs
from work.v17 import questions


def plan(action,**kw):return language.Plan(action=action,**kw).model_dump()


def answer(c,q,cid=None):
    r=c.post('/api/conversations/questions',json={'question':q,'conversation_id':cid})
    assert r.status_code==202,r.text
    t=r.json();assert t['messages'][-1]['state']=='done',t
    return t,t['messages'][-1]['result']


@pytest.fixture
def plans(monkeypatch):
    pending=[];used=[]
    monkeypatch.setattr(questions,'JOBS',{})
    class Inline:
        def submit(self,f,*args):f(*args)
    monkeypatch.setattr(questions,'POOL',Inline())
    def infer(_,payload):
        used.append(deepcopy(payload));assert pending,'Unexpected model interpretation'
        return pending.pop(0)
    monkeypatch.setattr(language,'infer',infer)
    return pending,used


@pytest.mark.parametrize('relation',['others','previous'])
def test_model_reference_chain_uses_records_and_excludes_hidden(client,plans,relation):
    c,_=client;pending,used=plans
    a=project(c,'세척기 교체');b=project(c,'저장탱크 증설');h=project(c,'비공개 설비',members=['team1'])
    stamp(a,'2026-01-02T09:00:00+09:00');stamp(b,'2026-01-01T09:00:00+09:00')
    with w.connect() as db:
        for p in (a,b,h):p['pm']='team2';w.save(db,'project',p)
    c.post('/api/demo-login',json={'username':'team2'})
    pending.append(plan('projects'))
    t,r=answer(c,'프로젝트 좀 알려줄래')
    assert [p['id'] for p in r['projects']]==[a['id'],b['id']]
    pending.append(plan('owner',scope='results',selection=2))
    t,r=answer(c,'두 번째 거 책임지는 사람은?',t['id'])
    assert r['result_project_ids']==[b['id']]
    pending.append(plan('owner_projects',scope=relation,person='last'))
    t,r=answer(c,'그 사람 다른 건도 맡아?',t['id'])
    assert [p['id'] for p in r['projects']]==[a['id']]
    assert all('비공개' not in str(p) for p in used)
    assert not pending


def test_smalltalk_preserves_last_business_query_without_model(client,plans):
    c,_=client;pending,used=plans
    p=project(c,'세척기 교체')
    t,first=answer(c,'전체 프로젝트 보여줘')
    assert first.get('mode')=='project_list',first
    t,r=answer(c,'고마워, 근데 넌 이름이 뭐야',t['id'])
    assert r['mode']=='social' and not used
    pending.append(plan('owner',scope='results',selection=1))
    _,r=answer(c,'아까 첫 번째 거 책임자는?',t['id'])
    assert r['result_project_ids']==[p['id']]


def test_pm_correction_and_meeting_count(client,plans):
    c,_=client;pending,used=plans
    a=project(c,'혼합기 개조');b=project(c,'저장탱크 증설');meeting(c,b);meeting(c,b,'다른 회의')
    t,first=answer(c,'혼합기 프로젝트 PM 알려줘')
    assert first.get('mode')=='project_owner',first
    pending.append(plan('owner',scope='named',projects=['탱크']))
    t,r=answer(c,'아 혼합기 말고 탱크',t['id'])
    assert r.get('result_project_ids')==[b['id']],r
    pending.append(plan('meeting_count',scope='previous'))
    _,r=answer(c,'회의는 몇 번 했어?',t['id'])
    assert r['count']==2


@pytest.mark.parametrize('raw,q',[
    (plan('projects',scope='named',projects=['다른이름']),'세척기 보여줘'),
    (plan('projects',scope='named',projects=['비공개']),'비공개 프로젝트 알려줘'),
    (plan('projects',unresolved='우리 팀'),'우리 팀 거만'),
    (plan('projects'),'완료된 프로젝트만'),
    (plan('owner',scope='results'),'거기 책임자는?'),
    (plan('owner_projects',person='last'),'그 사람이 맡은 건?'),
    (plan('meetings',period='2026년 7월'),'회의 알려줘'),
    (plan('owner',period='7월'),'7월 PM은?'),
])
def test_unresolved_or_invented_filters_never_broaden(client,raw,q):
    c,_=client;project(c,'세척기 교체')
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        _,r=language.execute(w,db,actor,q,raw)
    assert r['kind']=='clarification' and not r.get('answerable')


def test_person_negation_uses_current_pm_only(client):
    c,_=client;a=project(c,'세척기');b=project(c,'탱크')
    with w.connect() as db:
        a['pm']='team2';b['pm']='team3';w.save(db,'project',a);w.save(db,'project',b)
        actor=w.read(db,'person','team1');person=w.read(db,'person','team2')['name']
        _,r=language.execute(w,db,actor,person+'이 PM 아닌 프로젝트',plan('owner_projects',person=person,exclude_person=True))
    assert [p['id'] for p in r['projects']]==[b['id']]


def test_reference_permission_rechecked_after_model(client):
    c,_=client;p=project(c,'세척기',members=['team1','team2'])
    previous={'state':'done','context':{'project_ids':[p['id']]},'job':{'result':{'kind':'projects','mode':'project_list','projects':[p]}}}
    with w.connect() as db:
        p['members']=['team1'];w.save(db,'project',p);actor=w.read(db,'person','team2')
        _,r=language.execute(w,db,actor,'첫 번째 PM은?',plan('owner',scope='results',selection=1),previous)
    assert r['kind']=='clarification' and not r['projects']


def test_busy_gpu_does_not_guess_or_wait_indefinitely(client,monkeypatch,plans):
    c,_=client;project(c,'세척기')
    class Busy:
        def acquire(self,timeout):assert timeout==3;return False
    monkeypatch.setattr(w,'AI_LOCK',Busy())
    _,r=answer(c,'프로젝트 좀 알려줄래')
    assert r['kind']=='clarification' and '분석' in r['message']


def test_invalid_model_output_fails_closed(client,plans):
    c,_=client;project(c,'세척기');plans[0].append({'action':'delete_all'})
    _,r=answer(c,'프로젝트 좀 알려줄래')
    assert r['kind']=='clarification' and not r['projects']


def test_plan_schema_disallows_unknown_fields():
    with pytest.raises(ValueError):language.Plan(action='projects',sql='SELECT * FROM records')


def test_deleted_first_result_does_not_shift_ordinal_to_another_project(client):
    c,_=client;a=project(c,'세척기');b=project(c,'혼합기')
    previous={'state':'done','context':{'project_ids':[a['id'],b['id']]},'job':{'result':{
        'kind':'projects','mode':'project_list','projects':[a,b]}}}
    with w.connect() as db:
        a['deleted_at']=w.now();w.save(db,'project',a);actor=w.read(db,'person','team1')
        _,r=language.execute(w,db,actor,'첫 번째 책임자는?',plan('owner',scope='results',selection=1),previous)
    assert r['kind']=='clarification' and not r['projects']


def test_model_cannot_drop_explicit_project_name(client):
    c,_=client;a=project(c,'세척기 교체');b=project(c,'혼합기 개조');meeting(c,a);meeting(c,b)
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        _,r=language.execute(w,db,actor,'세척기 회의 몇 번 했어?',plan('meetings',scope='all'))
    assert r['mode']=='count' and r['count']==1 and r['result_project_ids']==[a['id']]


def test_registered_person_filter_survives_generic_project_action(client):
    c,_=client;a=project(c,'세척기 교체');b=project(c,'혼합기 개조')
    with w.connect() as db:
        a['pm']='team2';b['pm']='team3';w.save(db,'project',a);w.save(db,'project',b)
        actor=w.read(db,'person','team1');name=w.read(db,'person','team2')['name']
        _,r=language.execute(w,db,actor,name+' PM이 하는 프로젝트 다 알려줘',plan('projects',scope='previous'))
    assert [p['id'] for p in r['projects']]==[a['id']]


def test_latest_reference_keeps_meeting_entity_and_period(client):
    c,_=client;p=project(c,'세척기 교체')
    meeting(c,p,'회의 하나','2026-07-05');meeting(c,p,'회의 둘','2026-07-20');meeting(c,p,'회의 셋','2026-09-01')
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        ctx,r=language.execute(w,db,actor,'세척기 7월 회의 목록',plan('meetings',period='7월'))
        previous={'state':'done','context':ctx,'job':{'result':r}}
        _,r=language.execute(w,db,actor,'제일 최근 건 언제야?',plan('projects',scope='previous'),previous)
    assert r['mode']=='meeting_lookup' and len(r['sources'])==1
    assert r['sources'][0]['date']=='2026-07-20'


def test_pending_comparison_uses_counts_not_rag_or_guessed_scope(client):
    c,_=client;a=project(c,'세척기 교체');b=project(c,'혼합기 개조');meeting(c,b)
    previous={'state':'done','context':{},'job':{'result':{**language.clarification('비교 기준은?'),'pending_comparison':True}}}
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        _,r=language.execute(w,db,actor,'그럼 회의 수로',plan('meetings',scope='previous'),previous)
    assert r['mode']=='meeting_comparison' and r['result_project_ids']==[b['id']] and r['count']==1


def test_casual_reaction_never_swallows_information_request():
    assert language.social('두 개나 하네, 바쁘겠다')
    assert language.social('많네. 그럼 담당자 누구야?') is None
