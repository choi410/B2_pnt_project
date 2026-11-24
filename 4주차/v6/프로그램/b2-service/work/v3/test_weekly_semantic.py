"""주간보고 연결의 의미 점수(2026-11-24): 표현이 다른 메모도 후보로 찾되 자동 선택하지 않고,
회의록 단위 벡터는 벡터 저장소의 '#weekly' 구역에 캐시한다."""
import sqlite3
from contextlib import contextmanager
import pytest
from work.v3 import weekly_match as wm
from work.v3 import weekly_semantic as ws
from work.v3.test_weekly_match import index,row

S,E='2026-11-16','2026-11-20'


def unit_id(idx,text):
    return next(u['id'] for u in idx['units'] if u['kind']=='change' and text in u['text'])


def test_paraphrase_without_shared_words_becomes_unselected_candidate():
    idx=index()
    memo=row('고객 출하 전 점검 날짜 미룸')                 # '공장 검수일'과 겹치는 낱말 없음
    target=unit_id(idx,'공장 검수일: 2026-11-24 → 2026-11-27')
    before,_=wm.match_rows([memo],idx,S,E)
    assert not any(c['id']==target for c in before[0]['candidates'])
    after,_=wm.match_rows([memo],idx,S,E,semantic={'R1':{target:0.9}})
    cand=next(c for c in after[0]['candidates'] if c['id']==target)
    assert not cand['selected'] and any('뜻이 비슷함' in r and '겹치는 말 없음' in r for r in cand['reasons'])
    assert after[0]['match_state']=='check'


def test_low_similarity_is_ignored_and_keyword_result_unchanged():
    idx=index()
    memo=row('롤프레스 속도 135 재협의','2026-11-18')
    plain,_=wm.match_rows([memo],idx,S,E)
    noisy,_=wm.match_rows([memo],idx,S,E,semantic={'R1':{u['id']:0.8 for u in idx['units']}})   # e5 기본 수준
    assert [(c['id'],c['score'],c['selected']) for c in plain[0]['candidates']]==[(c['id'],c['score'],c['selected']) for c in noisy[0]['candidates']]


def test_similarity_adds_bonus_to_keyword_match_and_keeps_selection():
    idx=index()
    memo=row('롤프레스 속도 135 재협의','2026-11-18')
    target=unit_id(idx,'압연 속도')
    plain,_=wm.match_rows([memo],idx,S,E)
    boosted,_=wm.match_rows([memo],idx,S,E,semantic={'R1':{target:0.95}})
    a=next(c for c in plain[0]['candidates'] if c['id']==target);b=next(c for c in boosted[0]['candidates'] if c['id']==target)
    assert b['score']==pytest.approx(a['score']+wm.SEM_BONUS) and b['selected']==a['selected']
    assert any(r.startswith('뜻이 비슷함') for r in b['reasons'])


# ---- 벡터 캐시 ----
class Workspace:
    def __init__(self,path):self.path=path
    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.path)
        try:
            with c:yield c
        finally:c.close()


def fake_embed_factory(calls):
    import hashlib
    def embed(texts,prefix):
        calls.append((prefix,len(texts)))
        out=[]
        for t in texts:
            v=[0.0]*16
            for a,b in zip(t,t[1:]):v[int(hashlib.md5((a+b).encode()).hexdigest(),16)%16]+=1
            n=sum(x*x for x in v)**0.5 or 1
            out.append([x/n for x in v])
        return out
    return embed


@pytest.fixture
def store_env(tmp_path,monkeypatch):
    monkeypatch.setenv('B2_WEEKLY_SEMANTIC','1')
    monkeypatch.setenv('B2_VECTOR_STORE','sqlite')
    from work.v17 import rag_store
    rag_store._state.update(down_until=0.0,warned='')
    return Workspace(tmp_path/'w.sqlite3')


def test_unit_vectors_are_cached_in_weekly_namespace(store_env):
    calls=[];embed=fake_embed_factory(calls);idx=index()
    first=ws.semantic_scores(store_env,idx,[row('공장 검수 일정 조정')],embed=embed)
    assert first['backend']=='sqlite' and set(first['scores']['R1'])=={u['id'] for u in idx['units']}
    passages=sum(n for p,n in calls if p=='passage: ');assert passages>0
    with store_env.connect() as c:
        spaces={r[0] for r in c.execute('SELECT DISTINCT project_id FROM rag_vectors')}
    assert spaces=={'P1#weekly','P2#weekly'}          # AI 대화용 구역(P1, P2)과 섞이지 않는다
    calls.clear()
    ws.semantic_scores(store_env,idx,[row('다른 메모')],embed=embed)
    assert calls==[('query: ',1)]                      # 회의록 쪽은 캐시를 써서 다시 계산하지 않는다


def test_missing_model_or_switch_off_means_keyword_only(store_env,monkeypatch):
    def broken(texts,prefix):raise ImportError('No module named torch')
    assert ws.semantic_scores(store_env,index(),[row('검수')],embed=broken) is None
    monkeypatch.setenv('B2_WEEKLY_SEMANTIC','0')
    assert ws.semantic_scores(store_env,index(),[row('검수')],embed=fake_embed_factory([])) is None


def test_forget_project_also_clears_weekly_vectors(store_env):
    from work.v17 import rag_store
    ws.semantic_scores(store_env,index(),[row('검수')],embed=fake_embed_factory([]))
    rag_store.forget_project(store_env,'P2')
    with store_env.connect() as c:
        spaces={r[0] for r in c.execute('SELECT DISTINCT project_id FROM rag_vectors')}
    assert spaces=={'P1#weekly'}
