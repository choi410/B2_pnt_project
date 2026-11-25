"""Tool binding tests; real-model quality is evaluated separately."""
from collections import deque
import pytest
from work.v3.test_connected import client,w
from work.v3.test_questions_trash import project,meeting
from work.v3 import semantic_chat as semantic,chat_interpreter as language
from work.v17 import questions,retrieval


def proposal(**kw):
    return {**dict(tool='search',project='previous',topic='',purpose='fact',meeting='all',unresolved=False),**kw}


@pytest.fixture
def pipeline(client,monkeypatch):
    c,_=client;pending=deque();seen=[]
    monkeypatch.setenv('B2_CHAT_SEMANTIC','1')
    monkeypatch.setattr(questions,'JOBS',{})
    class Inline:
        def submit(self,f,*args):f(*args)
    monkeypatch.setattr(questions,'POOL',Inline())
    def infer(_,system,data,schema,tokens):
        seen.append(data);reply=pending.popleft()
        return reply(data) if callable(reply) else reply
    monkeypatch.setattr(language,'complete_json',infer)
    monkeypatch.setattr(retrieval,'retrieve',lambda w,p,docs,q,**kw:[{'meeting_id':d['meeting_id'],'line_ids':[l['id'] for l in retrieval.document_lines(d)]} for d in docs])
    return c,pending,seen


def ask(c,q,cid=None):
    r=c.post('/api/conversations/questions',json={'question':q,'conversation_id':cid})
    assert r.status_code==202,r.text
    t=r.json();assert t['messages'][-1]['state']=='done',t
    return t,t['messages'][-1]['result']


def choose(fragment,focus=''):
    def select(data):
        row=next(l for l in data['lines'] if fragment in l['text'])
        return {'lines':[row['id']],'focus_line':row['id'],'focus_text':focus}
    return select


def test_material_reference_comes_from_verified_source_not_generated_prose(pipeline):
    c,pending,seen=pipeline;p=project(c,'다래소재 세척 설비')
    meeting(c,p,'세정제 변경은 내식성 시험 성적서가 없어 보류했다.\n내식성 시험 성적서 제출 담당자와 기한은 미정이다.\n최인혁은 2027-03-20까지 배치도를 작성한다.')
    pending.extend([proposal(project='P1',topic='세정제',purpose='reason'),choose('세정제 변경','내식성 시험 성적서')])
    t,r=ask(c,'다래 세정제 변경을 진행하지 못한 이유가 뭐지?')
    assert '성적서가 없어 보류' in r['points'][0]['text']
    pending.extend([proposal(topic='내식성 시험 성적서',purpose='responsibility'),choose('제출 담당자','내식성 시험 성적서')])
    t,r=ask(c,'그 자료는 누구한테 언제까지 달라고 해야 해?',t['id'])
    assert seen[-2]['previous'][-1]['focus']=='내식성 시험 성적서'
    assert '미정' in r['points'][0]['text'] and '최인혁' not in str(r['points'])
    s=r['sources'][0]
    opened=c.get(f'/api/conversations/{t["id"]}/messages/{t["messages"][-1]["id"]}/sources/{s["id"]}')
    assert opened.status_code==200 and opened.json()['highlight']


def test_unknown_project_and_invented_topic_are_not_executed(client):
    c,_=client;p=project(c,'다래소재 세척 설비');meeting(c,p)
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        ctx,r,_,_=semantic.bind(w,db,actor,'없는업체 납품일',proposal(project='unknown',topic='납품일'),[p],[])
        assert r['kind']=='clarification' and not ctx['project_ids']
        _,r,_,_=semantic.bind(w,db,actor,'다래 납품일',proposal(project='P1',topic='999원 위약금'),[p],[])
        assert r['kind']=='clarification'


def test_explicit_scope_and_cutoff_remain_server_owned(client):
    c,_=client;a=project(c,'다래소재 세척 설비');b=project(c,'모아전자 세척 설비')
    meeting(c,a,'운전 속도 30 m/min 합의','2027-03-01');meeting(c,a,'운전 속도 40 m/min 합의','2027-03-10');meeting(c,b,'다른 기록','2027-03-01')
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        ctx,r,docs,_=semantic.bind(w,db,actor,'3월 5일 기준 운전 속도는?',proposal(project='all',topic='운전 속도'),[a,b],[],project_id=a['id'])
        assert r is None and ctx['project_ids']==[a['id']] and [d['date'] for d in docs]==['2027-03-01']


def test_memory_revalidates_revision_and_permissions(client):
    c,_=client;a=project(c,'다래소재 세척 설비');meeting(c,a,'유해물질 시험 자료가 없다.')
    with w.connect() as db:
        actor=w.read(db,'person','team2');doc=questions.corpus(w,db,[a['id']])[0];line=retrieval.document_lines(doc)[-1]
        source={**doc,'line_ids':[line['id']]}
        m={'state':'done','question':'어떤 자료?','context':{'semantic_focus':{'meeting_id':doc['meeting_id'],'fingerprint':doc['fingerprint'],'line_id':line['id'],'text':'시험 자료'}},'job':{'result':{'sources':[source]}}}
        assert semantic.history(w,db,actor,[m])[0]['focus']=='시험 자료'
        source['fingerprint']='stale';assert semantic.history(w,db,actor,[m])[0]['focus']==''
        a['members']=['team1'];w.save(db,'project',a)
        assert semantic.history(w,db,actor,[m])==[]


def test_fabricated_source_ids_are_rejected():
    with pytest.raises(ValueError):semantic.render({'lines':['invented']},[],[],{})


def test_project_choice_does_not_drop_previous_date_cutoff(client):
    c,_=client;p=project(c,'다래소재 세척 설비')
    meeting(c,p,'필터 재질 검토','2027-03-01');meeting(c,p,'필터 재질 변경','2027-03-10')
    with w.connect() as db:
        actor=w.read(db,'person','team1')
        first,_,_,_=semantic.bind(w,db,actor,'3월 5일 기준 다래 필터는?',proposal(project='P1',topic='필터'),[p],[])
        prior={'project_ids':[p['id']],'time_scope':first['time_scope']}
        _,r,docs,_=semantic.bind(w,db,actor,'왜 그렇게 정했어?',proposal(project='P1',topic='필터',purpose='reason'),[p],[prior])
        assert r is None and [d['date'] for d in docs]==['2027-03-01']


def test_experiment_is_opt_in(monkeypatch):
    monkeypatch.delenv('B2_CHAT_SEMANTIC',raising=False)
    assert not semantic.enabled()


def test_legacy_reference_guard_is_kept_when_semantic_route_is_ineligible(pipeline,monkeypatch):
    c,_,seen=pipeline
    monkeypatch.setattr(semantic,'eligible',lambda *a:False)
    _,result=ask(c,'그 자료는 누가 내야 해?')
    assert result['kind']=='clarification' and not seen


def test_source_changed_during_model_read_is_not_published(pipeline):
    c,pending,_=pipeline;p=project(c,'다래소재 세척 설비');m=meeting(c,p,'세정제 변경은 성적서가 없어 보류했다.')
    def mutate(data):
        with w.connect() as db:
            m['deleted_at']=w.now();w.save(db,'meeting',m)
        return choose('성적서')(data)
    pending.extend([proposal(project='P1',topic='세정제',purpose='reason'),mutate])
    _,r=ask(c,'다래 세정제는 왜 보류했지?')
    assert r['kind']=='clarification' and not r['points']
