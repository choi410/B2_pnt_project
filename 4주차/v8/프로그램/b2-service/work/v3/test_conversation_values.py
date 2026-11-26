"""Conversation references must compare fresh, source-verified values only."""
import pytest
from work.v3.test_connected import client,w
from work.v3.test_questions_trash import project,meeting
from work.v3.test_question_scope import change
from work.v3.test_project_catalog import no_generation,send
from work.v3 import conversation_values


def record(c,p,title,value,day='2027-02-10'):
    m=meeting(c,p,f'{title}은 {value}로 합의했다.',day)
    change(m,title,value)
    return m


def test_three_date_references_sort_without_reusing_generated_values(client):
    c,_=client;a=project(c,'해든배터리 설비');b=project(c,'대원소재 설비');d=project(c,'한솔전자 설비')
    for p,value in ((a,'2027-05-15'),(b,'2027-04-10'),(d,'2027-06-12')):record(c,p,'장비 납품일',value)
    t,_=send(c,'해든 최종 납품일은?')
    t,_=send(c,'대원은?',t['id'])
    t,_=send(c,'한솔은?',t['id'])
    # Altering the generated display text must not alter comparison facts.
    with w.connect() as db:
        m=w.read(db,'ai_message',t['messages'][-1]['id']);m['job']['result']['points'][0]['text']='납품일 2099-01-01';w.save(db,'ai_message',m)
    t,r=send(c,'세 프로젝트를 빠른 날짜부터 정리해줘',t['id'])
    assert r['mode']=='value_comparison'
    assert [p['project_id'] for p in r['points']]==[b['id'],a['id'],d['id']]
    assert '2099' not in str(r)
    for s in r['sources']:
        proof=c.get(f'/api/conversations/{t["id"]}/messages/{t["messages"][-1]["id"]}/sources/{s["id"]}')
        assert proof.status_code==200 and proof.json()['highlight']


def test_units_are_compared_across_projects_not_separately(client):
    c,_=client;a=project(c,'해든배터리 롤프레스');b=project(c,'대원소재 믹서')
    record(c,a,'압연 속도','95 m/min');record(c,b,'교반 회전 속도 상한','700 rpm')
    t,_=send(c,'해든 압연 속도는 얼마야?')
    t,_=send(c,'대원 교반 회전 속도 상한은?',t['id'])
    t,r=send(c,'두 속도가 같은 단위야?',t['id'])
    assert '서로 다른 단위' in r['message'] and len(r['points'])==2
    assert '95 m/min' in str(r['points']) and '700 rpm' in str(r['points'])
    _,r=send(c,'대원 것만 다시 짧게',t['id'])
    assert len(r['points'])==1 and r['points'][0]['project_id']==b['id'] and '700 rpm' in str(r)


def test_previous_value_is_before_latest_change_not_first_ever(client):
    c,_=client;p=project(c,'해든배터리 슬리터')
    for day,value in [('2027-02-01','2027-05-01'),('2027-02-05','2027-05-08'),('2027-02-10','2027-05-12')]:
        record(c,p,'공장 검수일',value,day)
    t,_=send(c,'해든 공장 검수일은?')
    t,r=send(c,'원래는 언제였어?',t['id'])
    assert r['mode']=='previous_value' and '2027-05-08' in r['message']
    assert '2027-05-01' not in str(r['points']) and '2027-05-12' in r['message']


def test_requested_changes_do_not_become_comparison_values(client):
    c,_=client;a=project(c,'해든배터리 설비');b=project(c,'대원소재 설비')
    record(c,a,'장비 납품일','2027-04-10');record(c,b,'장비 납품일','2027-04-15')
    m=meeting(c,a,'납품일 2027-05-10 변경 요청은 보류했다. 기존 납품일 2027-04-10을 유지한다.','2027-02-12')
    change(m,'장비 납품일','2027-05-10','보류')
    t,_=send(c,'해든 납품일은?');t,_=send(c,'대원은?',t['id'])
    _,r=send(c,'그 둘 중 먼저 납품하는 건?',t['id'])
    # '그 둘' refers to the preceding result; a single preceding result must
    # clarify rather than silently use unrelated earlier turns.
    assert r['kind']=='clarification'
    _,r=send(c,'두 프로젝트 중 어느 납품일이 더 빨라?',t['id'])
    assert r['focus_project_ids']==[a['id']]
    assert '2027-05-10' not in str(r['points'])


def test_removed_access_and_missing_reference_do_not_expand_scope(client):
    c,_=client;a=project(c,'해든배터리 설비');b=project(c,'대원소재 설비')
    for p in (a,b):record(c,p,'장비 납품일','2027-04-10')
    c.post('/api/demo-login',json={'username':'team2'})
    t,_=send(c,'해든 납품일은?');t,_=send(c,'대원은?',t['id'])
    with w.connect() as db:a['members']=['team1'];w.save(db,'project',a)
    _,r=send(c,'두 프로젝트 날짜를 빠른 순으로 정리해줘',t['id'])
    assert r['kind']=='clarification' and a['name'] not in str(r)


def test_leading_date_in_title_search_does_not_find_planned_meeting(client):
    c,_=client;p=project(c,'해든배터리 믹서')
    meeting(c,p,'2027-03-20에 구매 사양 확인 회의를 진행한다.','2027-03-10')
    _,r=send(c,'3월 20일 해든 구매 사양 확인 회의록 보여줘')
    assert r['count']==0 and not r['sources'] and '예정일' in r['message']


def test_field_stems_are_unique_not_shared_equipment_labels():
    from work.v3.conversations import subject_in
    assert subject_in('검수는 언제야?',['공장 검수일','장비 납품일'])=='공장 검수일'
    assert subject_in('검수는 언제야?',['공장 검수일','현장 검수일'])==''
    assert subject_in('장비는?',['장비 납품일','압연 속도'])==''


def test_comparison_date_scope_and_unsupported_filter_are_not_dropped(client):
    c,_=client;a=project(c,'해든배터리 설비');b=project(c,'대원소재 설비')
    record(c,a,'장비 납품일','2027-04-10','2027-02-02');record(c,b,'장비 납품일','2027-04-15','2027-02-02')
    record(c,a,'장비 납품일','2027-05-10','2027-02-10')
    t,_=send(c,'해든 납품일은?');t,_=send(c,'대원은?',t['id'])
    t,r=send(c,'2월 5일 기준 두 프로젝트 중 어느 납품일이 더 빨라?',t['id'])
    assert r['focus_project_ids']==[a['id']] and '2027-05-10' not in str(r['points'])
    _,r=send(c,'취소된 두 프로젝트의 날짜를 빠른 순으로 정리해줘',t['id'])
    assert r['kind']=='clarification' and not r['points']


def test_invalidated_source_is_not_used_to_complete_comparison(client):
    c,_=client;a=project(c,'해든배터리 설비');b=project(c,'대원소재 설비')
    m=record(c,a,'장비 납품일','2027-04-10');record(c,b,'장비 납품일','2027-04-15')
    t,_=send(c,'해든 납품일은?');t,_=send(c,'대원은?',t['id'])
    with w.connect() as db:m['analysis_stale']=True;w.save(db,'meeting',m)
    _,r=send(c,'두 프로젝트 날짜를 빠른 순으로 정리해줘',t['id'])
    assert r['kind']=='clarification' and not r['points']


def test_equivalent_celsius_symbols_are_the_same_unit(client):
    c,_=client;a=project(c,'해든배터리 설비');b=project(c,'대원소재 설비')
    record(c,a,'건조로 온도','115 ℃');record(c,b,'건조로 온도','125 °C')
    t,_=send(c,'해든 건조로 온도는?');t,_=send(c,'대원은?',t['id'])
    _,r=send(c,'두 온도가 같은 단위야?',t['id'])
    assert r['mode']=='value_comparison' and '단위는 같습니다' in r['message']


def test_explicit_field_change_does_not_reuse_the_previous_field(client):
    c,_=client;a=project(c,'해든배터리 설비');b=project(c,'대원소재 설비')
    record(c,a,'장비 납품일','2027-04-10');record(c,b,'장비 납품일','2027-04-15')
    record(c,a,'공장 검수일','2027-04-08');record(c,b,'공장 검수일','2027-04-05')
    record(c,a,'압연 속도','90 m/min','2027-02-01');record(c,a,'압연 속도','95 m/min')
    t,_=send(c,'해든 납품일은?');t,_=send(c,'대원은?',t['id'])
    t,r=send(c,'두 프로젝트 검수일은 어느 게 더 빨라?',t['id'])
    assert r['focus_project_ids']==[b['id']] and all('공장 검수일' in p['text'] for p in r['points'])
    t,_=send(c,'해든 공장 검수일은?',t['id'])
    _,r=send(c,'원래 속도는 얼마였어?',t['id'])
    assert r['mode']=='previous_value' and '90 m/min' in r['message'] and '공장 검수일' not in r['message']
    _,r=send(c,'원래 가압력은 얼마였어?',t['id'])
    assert r['kind']=='clarification' and not r['points']
