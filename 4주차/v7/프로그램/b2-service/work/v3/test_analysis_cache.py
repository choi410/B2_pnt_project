"""Reuse must not survive changed inputs/models or silently mask a cache failure."""
from copy import deepcopy
import pytest
from work.v3 import analysis_cache, fast_ai
from work.v17 import llm

LINES = [{'id':'L001','text':'납품일은 2026-12-23으로 합의했다.'}]


@pytest.fixture
def cache(monkeypatch, tmp_path):
    monkeypatch.setenv('B2_ANALYSIS_CACHE_DIR', str(tmp_path/'cache'))
    monkeypatch.setattr(analysis_cache,'signature',lambda:'model-and-rules-A')
    monkeypatch.setattr(llm,'available',lambda:False)
    calls=[]
    def generate(w,lines,topics,on_phase=None,use_cache=True):
        calls.append(deepcopy(lines))
        return ({'summary':[],'decisions':[{'text':lines[0]['text'],'evidence':['L001']}],'items':[]},
                {'items':[]},{'seconds':35,'cold_start':True,'model_load_seconds':5,'pipeline':fast_ai.VERSION})
    monkeypatch.setattr(fast_ai,'_extract_validated',generate)
    return calls


def test_exact_source_reuses_validated_output_without_loading_model(cache):
    original=fast_ai.extract(None,LINES,[])
    reused=fast_ai.extract(None,LINES,[])
    assert len(cache)==1
    assert original[:2]==reused[:2]
    assert reused[2]['cache_hit'] and not reused[2]['cold_start']
    assert reused[2]['original_analysis_seconds']==35
    reused[0]['decisions'].clear()
    assert fast_ai.extract(None,LINES,[])[0]['decisions']


@pytest.mark.parametrize('changed',['source','topics','model'])
def test_changed_context_or_model_requires_fresh_analysis(cache,monkeypatch,changed):
    fast_ai.extract(None,LINES,[])
    lines=deepcopy(LINES);topics=[]
    if changed=='source':lines[0]['text']='납품일 변경은 보류했다.'
    if changed=='topics':topics=[{'id':'different','title':'장비 납품일','category':'납기'}]
    if changed=='model':monkeypatch.setattr(analysis_cache,'signature',lambda:'model-and-rules-B')
    result=fast_ai.extract(None,lines,topics)
    assert len(cache)==2 and not result[2]['cache_hit']


@pytest.mark.parametrize('broken',['{broken','[]','{"format":1}'])
def test_corrupted_entry_is_recomputed(cache,broken):
    fast_ai.extract(None,LINES,[])
    next(analysis_cache.root().glob('*.json')).write_text(broken,encoding='utf-8')
    assert not fast_ai.extract(None,LINES,[])[2]['cache_hit']
    assert len(cache)==2


def test_disabled_cache_does_not_store_or_reuse(cache,monkeypatch):
    folder=analysis_cache.root()
    monkeypatch.delenv('B2_ANALYSIS_CACHE_DIR')
    fast_ai.extract(None,LINES,[]);fast_ai.extract(None,LINES,[])
    assert len(cache)==2 and not folder.exists()


def test_failed_generation_is_never_cached(cache,monkeypatch):
    def fail(*a,**kw):raise ValueError('invalid evidence')
    monkeypatch.setattr(fast_ai,'_extract_validated',fail)
    with pytest.raises(ValueError):fast_ai.extract(None,LINES,[])
    assert not analysis_cache.root().exists()


def test_stage_reuse_preserves_previous_stage_context_and_new_revision(cache,monkeypatch):
    import json
    from work.v3 import service
    calls=[]
    monkeypatch.setattr(llm,'stage_available',lambda:True)
    def generate(*a,**kw):
        calls.append(1)
        return json.dumps({'stage':service.STAGES[1],'reason':'설계 중','evidence':LINES[0]['text'],
                           'in_progress':'설계','planned':''}),{'model':'test'}
    monkeypatch.setattr(llm,'stage_chat',generate)
    m={'lines':LINES,'title':'일정 회의','date':'2026-11-19','revision':1}
    first=service.judge_stage(m,'설계')
    m['revision']=2
    second=service.judge_stage(m,'설계')
    assert len(calls)==1 and second['cache_hit'] and second['revision']==2
    assert first['evidence']==second['evidence']
    service.judge_stage(m,'제작')
    assert len(calls)==2
