"""Independent review counterexamples; expected scope is checked, not fluency."""
import pytest
from work.v3.test_dialogue_plan import records, result, mids, state
from work.v3.test_connected import client,w
from work.v3.test_questions_trash import meeting
from work.v3.test_conversations import send
from work.v3.conversations import resolve_question


def resolve(t,q):
    with w.connect() as db:
        previous=w.read(db,'ai_message',t['messages'][-1]['id'])
        return resolve_question(w,db,w.read(db,'person','team2'),q,previous)


def test_review_content_to_list_then_first_source(records):
    c,a,b,_,m=records
    t=send(c,'기간 관련 내용 있어?')
    t=send(c,'그 얘기 나온 회의 목록으로 줘',cid=t['id'])
    assert result(t)['mode']=='meeting_lookup' and result(t)['count']==5
    t=send(c,'그중 첫 회의 원문 보여줘',cid=t['id'])
    assert mids(t)=={m['a6']}


def test_review_change_project_and_year_then_scoped_content(records):
    c,a,b,_,m=records
    c.post('/api/demo-login',json={'username':'team1'})
    previous_year=meeting(c,b,'탱크 용량은 20 kL로 합의했다.','2025-07-20')
    c.post('/api/demo-login',json={'username':'team2'})
    t=send(c,'세척기 2026년 7월 회의록')
    t=send(c,'탱크로 바꾸고 작년 걸로',cid=t['id'])
    # Use the full registered project name to distinguish it from a typo in an unknown name.
    if result(t)['kind']=='clarification':t=send(c,'저장탱크로 바꾸고 작년 걸로',cid=t['id'])
    assert mids(t)=={previous_year['id']}
    ctx=resolve(t,'거기서 용량 얼마였어?')
    assert ctx['meeting_ids']==[previous_year['id']] and ctx['project_ids']==[b['id']]


def test_review_correction_replaces_month(records):
    c,_,_,_,m=records
    t=send(c,'2026년 8월 회의록 몇 건이야?');assert result(t)['count']==1
    t=send(c,'아니 8월 말고 7월',cid=t['id'])
    assert result(t)['count']==3 and not state(t)['retrieval_plan']['excluded_periods']
    t=send(c,'올해',cid=t['id']);assert result(t)['count']==3


def test_review_metadata_to_content_preserves_full_set(records):
    c,a,_,_,m=records
    t=send(c,'세척기 회의록 보여줘')
    ctx=resolve(t,'이 중에 펌프 얘기 있는 거')
    assert set(ctx['meeting_ids'])=={m['a6'],m['a71'],m['a72'],m['a8']}
    assert '펌프' in ctx['query'] and not ctx.get('clarify')


def test_review_invalid_then_future_month(records):
    c,_,_,_,m=records
    t=send(c,'13월 회의록 찾아줘');assert result(t)['kind']=='clarification'
    t=send(c,'다음 달 회의록은?',cid=t['id'])
    assert result(t)['mode']=='meeting_lookup' and result(t)['count']==0
    t=send(c,'세척기랑 세탁기 회의록',cid=t['id'])
    assert result(t)['kind']=='clarification'


def test_review_limited_records_to_content(records):
    c,_,_,_,m=records
    t=send(c,'최근 회의 3개만')
    assert mids(t)=={m['a8'],m['a72'],m['b7']}
    ctx=resolve(t,'그 회의들에서 아직 결정 안 된 거 있어?')
    assert set(ctx['meeting_ids'])==mids(t)
    assert not ctx.get('clarify')


def test_pending_records_quote_only_actual_pending_evidence(records):
    c,a,b,_,m=records
    c.post('/api/demo-login',json={'username':'team1'})
    pending=meeting(c,a,'고객은 배수 펌프 교체를 요청했다. 교체 여부는 아직 결정하지 않았다. 기존 펌프를 유지한다.','2026-09-01')
    agreed=meeting(c,b,'탱크 용량은 25 kL로 합의했다. 안전 펜스는 유지한다.','2026-09-02')
    c.post('/api/demo-login',json={'username':'team2'})
    t=send(c,'최근 회의 3개만');t=send(c,'그 회의들에서 아직 결정 안 된 거 있어?',cid=t['id'])
    assert mids(t)=={pending['id']} and result(t)['count']==1
    assert '현재 확정·미해결 상태를 뜻하지 않습니다' in result(t)['notice']


def test_unsettled_claim_needs_its_own_topic_evidence():
    from work.v3.answer_meaning import unsupported_unsettled
    source=[{'text':'탱크 용량은 25 kL로 합의했다. 안전 펜스는 유지한다.'}]
    assert unsupported_unsettled('탱크 용량 변경은 합의되었지만, 안전 펜스 관련 사항은 아직 결정되지 않았습니다',source)
    assert unsupported_unsettled('안전 펜스는 미정입니다.',source)
    source=[{'text':'배수 펌프 교체 여부는 아직 결정하지 않았다.'}]
    assert not unsupported_unsettled('배수 펌프 교체 여부는 아직 결정되지 않았습니다.',source)


def test_remaining_is_clarified_without_generation(records):
    c,_,_,_,_=records;t=send(c,'기간 관련 내용 있어?')
    t=send(c,'나머지도 보여줘',cid=t['id'])
    assert result(t)['kind']=='clarification' and '나머지' in result(t)['message']
