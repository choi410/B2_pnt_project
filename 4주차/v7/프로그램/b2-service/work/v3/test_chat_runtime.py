"""Read/state/model boundary checks on disposable records, not model accuracy."""
from copy import deepcopy
import json
import pytest
from fastapi import HTTPException
from work.v3.test_connected import client, w
from work.v3.test_questions_trash import project, meeting, event
from work.v3.chat_tools import ReadTools
from work.v3 import chat_model, chat_state, chat_interpreter as language, conversations
from work.v17 import questions


def test_tools_keep_empty_scope_and_read_original_exactly(client):
    c,_=client;p=project(c);m=meeting(c,p,'검토서는 박하늘이 2026-11-28까지 제출한다.')
    with w.connect() as db:
        tools=ReadTools(w,db,w.read(db,'person','team1'))
        before=db.execute('SELECT kind,id,payload FROM records ORDER BY kind,id').fetchall()
        assert tools.projects([])==[] and tools.meetings([])==[]
        assert tools.meetings([p['id']],meeting_ids=[])==[]
        doc=tools.meetings([p['id']],meeting_ids=[m['id']])[0]
        original=tools.original(m['id'],fingerprint=doc['fingerprint'])
        assert original['lines'][-1]['text']=='검토서는 박하늘이 2026-11-28까지 제출한다.'
        assert tools.original(m['id'],line_ids=[])['lines']==[]
        with pytest.raises(HTTPException) as stale:tools.original(m['id'],fingerprint='old')
        assert stale.value.status_code==409
        with pytest.raises(HTTPException):tools.original(m['id'],line_ids=['L999'])
        assert db.execute('SELECT kind,id,payload FROM records ORDER BY kind,id').fetchall()==before


@pytest.mark.parametrize('tool',['projects','meetings','original','changes','lookup'])
def test_every_tool_rechecks_access(client,tool):
    c,_=client;p=project(c,members=['team1']);m=meeting(c,p)
    with w.connect() as db:
        tools=ReadTools(w,db,w.read(db,'person','team2'))
        args=([m['id']] if tool=='original' else [[p['id']]])
        if tool=='lookup':args += [{},{}]
        with pytest.raises(HTTPException) as denied:getattr(tools,tool)(*args)
        assert denied.value.status_code==404


def test_change_tool_keeps_existing_revision_and_exclusion_rules(client):
    c,_=client;p=project(c);m=meeting(c,p)
    good=event(m,'topic','확정','2026-12-18')
    excluded=event(m,'topic','요청','2026-12-23');old=event(m,'topic','보류','2026-12-23')
    with w.connect() as db:
        excluded['review_state']='제외';w.save(db,'change_event',excluded)
        old['source_revision']=0;w.save(db,'change_event',old)
        rows,_=ReadTools(w,db,w.read(db,'person','team1')).changes([p['id']])
        assert [row['id'] for row in rows]==[good['id']]


@pytest.mark.parametrize('mode',['clarification','social'])
def test_saved_state_does_not_restore_revoked_scope(client,mode):
    c,_=client;p=project(c);m=meeting(c,p)
    with w.connect() as db:
        actor=w.read(db,'person','team2')
        context={'project_ids':[p['id']],'meeting_ids':[m['id']]}
        chat_state.pin_selection(w,db,actor,context)
        state=chat_state.memory(w,db,actor,{'context':context})
        state.update(query='비공개 조회',subject='비공개 항목',project_ids=[p['id']],person_ids=['team1'])
        current=w.read(db,'project',p['id']);current['members']=['team1'];w.save(db,'project',current)
        prev={'context':{'chat_memory':state},'job':{'result':{'kind':mode,'mode':mode}}}
        result=language.memory(w,db,actor,prev)
        assert result['project_ids']==result['scope_ids']==result['selected_meeting_ids']==result['person_ids']==[]
        assert result['query']==result['subject']==''


@pytest.mark.parametrize('kind',['documents','clarification'])
def test_selected_meeting_survives_no_answer_but_stale_evidence_does_not(client,kind):
    c,_=client;p=project(c);m=meeting(c,p)
    with w.connect() as db:
        actor=w.read(db,'person','team1');context={'project_ids':[p['id']],'meeting_ids':[m['id']]}
        chat_state.pin_selection(w,db,actor,context)
        context['chat_memory']={'project_ids':[],'scope_ids':[]}
        prev={'question':'선택한 회의 요약','state':'done','context':context,
              'job':{'result':{'kind':kind,'answerable':False,'sources':[],'points':[]}}}
        result=chat_state.memory(w,db,actor,prev)
        assert result['selected_meeting_ids']==[m['id']] and result['meeting_ids']==[]
        assert not result['evidence']
        next_context=conversations.resolve_question(w,db,actor,'그 회의록 안건은?',prev)
        assert next_context['meeting_ids']==[m['id']] and not next_context.get('clarify')
        changed=w.read(db,'meeting',m['id']);changed['revisions'][0]['body']+='\n원문이 수정됨.';w.save(db,'meeting',changed)
        assert chat_state.memory(w,db,actor,prev)['selected_meeting_ids']==[]
        next_context=conversations.resolve_question(w,db,actor,'그 회의록 안건은?',prev)
        assert next_context.get('clarify') and not next_context['meeting_ids']


def test_answer_prose_cannot_add_a_fact_to_memory(client):
    c,_=client;p=project(c);m=meeting(c,p)
    with w.connect() as db:
        actor=w.read(db,'person','team1');doc=ReadTools(w,db,actor).meetings([p['id']])[0]
        source={k:doc[k] for k in ('meeting_id','project_id','fingerprint')}
        source.update(line_ids=['L999'],text='없는 담당자 9999명')
        prev={'context':{'project_ids':[p['id']]},'job':{'result':{'sources':[source],
            'message':'없는 담당자 9999명','points':[{'text':'없는 담당자 9999명'}]}}}
        state=chat_state.memory(w,db,actor,prev)
        assert state['evidence']==[] and '9999' not in json.dumps(state,ensure_ascii=False)


def test_model_boundary_is_replaceable_without_changing_lookup(client,monkeypatch):
    c,_=client;p=project(c,'다온 검사장비')
    class Alternate:
        def generate_json(self,request):
            assert request.max_tokens==80 and request.max_input_tokens==3900
            assert request.payload['question']=='전체 프로젝트 보여줘'
            return {'action':'projects','relation':'new','unresolved':False}
    complete=chat_model.complete
    monkeypatch.setattr(chat_model,'complete',lambda w,request:complete(w,request,backend=Alternate()))
    proposal=language.infer(w,{'question':'전체 프로젝트 보여줘','previous':{}})
    with w.connect() as db:
        _,result=language.execute(w,db,w.read(db,'person','team1'),'전체 프로젝트 보여줘',proposal)
    assert p['id'] in [r['id'] for r in result['projects']]


def test_api_preserves_selection_after_unsuccessful_summary(client,monkeypatch):
    from work.v3 import question_policy
    c,_=client;p=project(c);old=meeting(c,p,date='2026-10-01');new=meeting(c,p,date='2026-10-08')
    monkeypatch.setattr(language,'needs_interpreter',lambda *a:False)
    monkeypatch.setattr(question_policy,'quick_answer',lambda *a,**kw:None)
    monkeypatch.setattr(questions,'JOBS',{})
    class Inline:
        def submit(self,fn,*args):fn(*args)
    monkeypatch.setattr(questions,'POOL',Inline())
    captured=[]
    def no_answer(_w,jid,*args):
        with questions.LOCK:captured.append(deepcopy(questions.JOBS[jid]['query_plan']))
        questions.update(jid,state='done',result={'kind':'documents','answerable':False,'points':[],'sources':[],'message':'요약 실패'})
    monkeypatch.setattr(questions,'answer_job',no_answer)
    r=c.post('/api/conversations/questions',json={'question':'선택한 회의 핵심 정리','meeting_id':new['id']})
    assert r.status_code==202,r.text
    thread=r.json();assert thread['messages'][-1]['state']=='done'
    r=c.post('/api/conversations/questions',json={'question':'그 회의록 안건은?','conversation_id':thread['id']})
    assert r.status_code==202,r.text
    assert len(captured)==2 and all(p['meeting_ids']==[new['id']] for p in captured)
    assert all(old['id'] not in p['meeting_ids'] for p in captured)


def source_previous(db,p,m,line_ids=None):
    doc=ReadTools(w,db,w.read(db,'person','team1')).original(m['id'])
    source={k:doc[k] for k in ('meeting_id','project_id','fingerprint')}
    source['line_ids']=line_ids or [l['id'] for l in doc['lines'][3:]]
    return {'state':'done','question':'왜 보류했지?',
        'context':{'project_ids':[p['id']],'query':'왜 보류했지?','time_scope':{'mode':'current','start':None,'end':None}},
        'job':{'result':{'sources':[source],'points':[{'text':'상세 사유는 원문에 있습니다.'}]}}}


def test_material_reference_is_a_source_candidate_not_a_person(client,monkeypatch):
    c,_=client;p=project(c,'푸른 계측장비')
    m=meeting(c,p,'절연 검토 자료가 없어 승인을 보류했다.\n오지훈은 2026-12-03까지 별도 배선 작업을 한다.\n절연 검토 자료 제출 담당자와 기한은 미정이다.')
    with w.connect() as db:
        actor=w.read(db,'person','team1');previous=source_previous(db,p,m)
        payload=language.payload_for(w,db,actor,'그 자료는 누가 언제까지 준비해?',previous)
        candidates=payload['reference_lines']
        assert candidates and all(row['target']=='절연 검토 자료' for row in candidates)
        def choose(_w,system,data,schema,max_tokens):
            assert 'target' not in schema['properties']
            assert all(row['name']!='오지훈' for row in data['candidates'])
            return {'choice':data['candidates'][0]['choice']}
        monkeypatch.setattr(language,'complete_json',choose)
        raw=language.infer(w,payload)
        context,result=language.execute(w,db,actor,'그 자료는 누가 언제까지 준비해?',raw,previous)
        assert result is None and context['subject']=='절연 검토 자료'
        assert context['project_ids']==[p['id']] and '오지훈' not in context['query']
        raw['reference']['target']='오지훈'
        _,denied=language.execute(w,db,actor,'그 자료는 누가 언제까지 준비해?',raw,previous)
        assert denied['kind']=='clarification'


@pytest.mark.parametrize('change',['revoked','revised','deleted'])
def test_reference_plan_is_revalidated_after_model_execution(client,monkeypatch,change):
    c,_=client;p=project(c);m=meeting(c,p,'절연 시험 보고서가 필요하다.')
    with w.connect() as db:
        actor=w.read(db,'person','team2');prev=source_previous(db,p,m)
        payload=language.payload_for(w,db,actor,'그 보고서는 누가 준비해?',prev)
        monkeypatch.setattr(language,'complete_json',lambda *a,**kw:{'choice':'E1'})
        raw=language.infer(w,payload)
        if change=='revoked':
            p=w.read(db,'project',p['id']);p['members']=['team1'];w.save(db,'project',p)
        else:
            m=w.read(db,'meeting',m['id'])
            if change=='deleted':m['deleted_at']=w.now()
            else:m['revisions'][0]['body']+='\n원문 수정'
            w.save(db,'meeting',m)
        _,result=language.execute(w,db,actor,'그 보고서는 누가 준비해?',raw,prev)
        assert result['kind']=='clarification' and not result['sources']


def test_reference_choices_do_not_read_uncited_or_other_project_text(client,monkeypatch):
    c,_=client;p=project(c);other=project(c,'다른 검사장비')
    m=meeting(c,p,'내압 성적서와 내열 보고서가 모두 필요하다.\n숨겨진 시험 자료는 담당자를 정했다.')
    with w.connect() as db:
        actor=w.read(db,'person','team1');doc=ReadTools(w,db,actor).original(m['id'])
        chosen=next(l for l in doc['lines'] if l['text'].startswith('내압'))
        prev=source_previous(db,p,m,[chosen['id']])
        payload=language.payload_for(w,db,actor,'그 자료는 누가 준비해?',prev)
        assert {r['target'] for r in payload['reference_lines']}=={'내압 성적서','내열 보고서'}
        assert language.reference_lines(w,db,actor,'그 자료는 누가 준비해?',prev,other['id'])==[]
        assert language.reference_lines(w,db,actor,'다른 프로젝트 그 자료는?',prev)==[]
        monkeypatch.setattr(language,'complete_json',lambda *a,**kw:{'choice':'none'})
        raw=language.infer(w,payload)
        assert raw['action']=='clarify' and raw['reference'] is None


def task_points(db,p,m):
    previous=source_previous(db,p,m)
    previous['question']='각 업무를 알려줘'
    previous['context'].update(project_id=p['id'],query='각 업무를 알려줘')
    doc=ReadTools(w,db,w.read(db,'person','team1')).original(m['id'])
    sources=[];points=[]
    for i,line in enumerate(doc['lines'][3:]):
        sid='S'+str(i+1)
        sources.append({k:doc[k] for k in ('meeting_id','project_id','fingerprint')}|
                       {'id':sid,'line_ids':[line['id']]})
        points.append({'project_id':p['id'],'text':line['text'],'sources':[sid]})
    previous['job']['result']={'kind':'documents','answerable':True,'points':points,'sources':sources}
    return previous


def test_answer_ordinal_selects_task_not_project_and_keeps_followup(client,monkeypatch):
    c,_=client;p=project(c,'새빛 계측장비');project(c,'다른 설비')
    m=meeting(c,p,'센서 교정은 박하늘이 2026-12-03까지 준비한다.\n절연 검증 자료의 담당자와 기한은 미정이다.')
    q='두 번째는 누가 해?'
    with w.connect() as db:
        actor=w.read(db,'person','team1');prev=task_points(db,p,m)
        context=conversations.resolve_question(w,db,actor,q,prev)
        assert context['point_followup'] and language.needs_interpreter(w,db,actor,q,context,prev)
        payload=language.payload_for(w,db,actor,q,prev)
        assert len(payload['answer_point']['rows'])==1
        assert '박하늘' not in str(payload['answer_point'])
        monkeypatch.setattr(language,'complete_json',lambda *a,**kw:{'choice':'E1','start':0,'end':2})
        raw=language.infer(w,payload)
        context,result=language.execute(w,db,actor,q,raw,prev)
        assert result is None and context['subject']=='절연 검증 자료'
        assert context['project_ids']==[p['id']] and '절연 검증 자료' in context['query']
        # The next deadline question inherits the selected task, not the list.
        next_message={'state':'done','question':q,'context':context,'job':{'result':{'answerable':True,'sources':[]}}}
        following=conversations.resolve_question(w,db,actor,'언제까지야?',next_message)
        assert following['subject']=='절연 검증 자료' and following['project_ids']==[p['id']]


def test_point_span_handles_punctuation_without_inventing_a_phrase():
    assert language.point_span({'text':'.'},0,0)==''
    assert language.point_span({'text':'센서 교정 계획을 작성한다.'},0,2)=='센서 교정 계획'
    text='박하늘은 2026-12-03까지 센서 교정 계획을 작성한다.'
    assert not language.point_target('박하늘은 2026-12-03까지',{'text':text},{'display':text})


@pytest.mark.parametrize('hint',['센서 교정을','없는 업무','절연 검증 자료'])
def test_planned_task_reference_reuses_only_a_live_source_bound_topic(client,monkeypatch,hint):
    c,_=client;p=project(c)
    m=meeting(c,p,'절연 검증 자료 담당자는 미정이다.\n박하늘은 2026-12-03까지 센서 교정 계획을 작성한다.')
    with w.connect() as db:
        actor=w.read(db,'person','team1');prev=task_points(db,p,m)
        prev['job']['result']['sources'][1]['query_scope']={'target_index':1,'target_label':hint}
        prev['context']['time_scope']={'mode':'as_of','start':None,'end':'2026-11-30'}
        payload=language.payload_for(w,db,actor,'두 번째는 언제까지야?',prev)
        raw=language.direct_reference(payload)
        if hint!='센서 교정을':
            assert raw is None  # A planned label alone is never original evidence.
            return
        assert raw['reference']['target']=='센서 교정'
        monkeypatch.setattr(language,'complete_json',lambda *a,**kw:pytest.fail('Known target needs no re-interpretation'))
        assert language.infer(w,payload)==raw
        ctx,result=language.execute(w,db,actor,'두 번째는 언제까지야?',raw,prev)
        assert result is None and ctx['subject']=='센서 교정'
        assert ctx['project_ids']==[p['id']] and ctx['time_scope']['end']=='2026-11-30'
        m=w.read(db,'meeting',m['id']);m['revisions'][0]['body']+='\n수정 내용';w.save(db,'meeting',m)
        _,result=language.execute(w,db,actor,'두 번째는 언제까지야?',raw,prev)
        assert result['kind']=='clarification' and not result['sources']


@pytest.mark.parametrize('span',[(-1,2),(0,999),(2,0),('0',2),(True,2),(3,3)])
def test_answer_point_cannot_invent_or_borrow_other_point_target(client,monkeypatch,span):
    c,_=client;p=project(c);m=meeting(c,p,'센서 교정은 박하늘이 2026-12-03까지 한다.\n절연 검증 자료는 미정이다.')
    with w.connect() as db:
        actor=w.read(db,'person','team1');prev=task_points(db,p,m)
        payload=language.payload_for(w,db,actor,'두 번째는 누가 해?',prev)
        monkeypatch.setattr(language,'complete_json',lambda *a,**kw:{'choice':'E1','start':span[0],'end':span[1]})
        assert language.infer(w,payload)['action']=='clarify'


@pytest.mark.parametrize('mutation',['revised','deleted','revoked'])
def test_answer_point_revalidates_sources_without_renumbering(client,monkeypatch,mutation):
    c,_=client;p=project(c);m=meeting(c,p,'센서 교정은 미정이다.\n절연 검증 자료는 미정이다.')
    with w.connect() as db:
        actor=w.read(db,'person','team2');prev=task_points(db,p,m)
        payload=language.payload_for(w,db,actor,'두 번째는 누가 해?',prev)
        monkeypatch.setattr(language,'complete_json',lambda *a,**kw:{'choice':'E1','start':0,'end':2})
        raw=language.infer(w,payload)
        if mutation=='revoked':p['members']=['team1'];w.save(db,'project',p)
        else:
            m=w.read(db,'meeting',m['id'])
            if mutation=='deleted':m['deleted_at']=w.now()
            else:m['revisions'][0]['body']+='\n수정 내용'
            w.save(db,'meeting',m)
        _,result=language.execute(w,db,actor,'두 번째는 누가 해?',raw,prev)
        assert result['kind']=='clarification' and not result['sources']


@pytest.mark.parametrize('question',['세 번째는 누가 해?','그건 누가 해?','언제까지야?'])
def test_answer_point_ambiguity_does_not_fall_through_to_project_lookup(client,question):
    c,_=client;p=project(c);m=meeting(c,p,'센서 교정은 미정이다.\n절연 검증 자료는 미정이다.')
    with w.connect() as db:
        actor=w.read(db,'person','team1');prev=task_points(db,p,m)
        context=conversations.resolve_question(w,db,actor,question,prev)
        assert context['point_followup'] and context['clarify']
        assert context['project_ids']==[p['id']]
        assert not language.needs_interpreter(w,db,actor,question,context,prev)
        from work.v3 import semantic_chat
        assert not semantic_chat.eligible(w,db,actor,question,context,prev,False)
        unanswered={'state':'done','question':question,'context':context,
                    'job':{'result':language.clarification(context['clarify'])}}
        next_context=conversations.resolve_question(w,db,actor,'센서 교정은 누가 해?',unanswered)
        assert next_context['project_ids']==[p['id']]


def test_answer_points_follow_ui_group_order_and_preserve_cutoff(client,monkeypatch):
    c,_=client;a=project(c,'푸른 설비');b=project(c,'노을 설비')
    ma=meeting(c,a,'센서 교정 계획\n절연 검증 자료');mb=meeting(c,b,'배선 수정 계획')
    with w.connect() as db:
        actor=w.read(db,'person','team1');prev=task_points(db,a,ma);other=task_points(db,b,mb)
        other['job']['result']['sources'][0]['id']='B1';other['job']['result']['points'][0]['sources']=['B1']
        prev['job']['result']['points'].insert(1,other['job']['result']['points'][0])
        prev['job']['result']['sources']+=other['job']['result']['sources']
        prev['context'].update(project_ids=[a['id'],b['id']],time_scope={'mode':'as_of','end':'2026-11-02','start':None})
        focus=chat_state.point_focus(w,db,actor,'두 번째는 누가 해?',prev)
        assert focus['display']=='절연 검증 자료'
        monkeypatch.setattr(language,'complete_json',lambda *a,**kw:{'choice':'E1','start':0,'end':2})
        raw=language.infer(w,language.payload_for(w,db,actor,'두 번째는 누가 해?',prev))
        ctx,result=language.execute(w,db,actor,'두 번째는 누가 해?',raw,prev)
        assert result is None and ctx['project_ids']==[a['id']] and ctx['time_scope']['end']=='2026-11-02'
        # Explicit meeting/project ordinals keep the existing metadata routes.
        assert chat_state.point_focus(w,db,actor,'두 번째 회의록을 보여줘',prev) is None
        assert chat_state.point_focus(w,db,actor,'두 번째 프로젝트 담당자는?',prev) is None
