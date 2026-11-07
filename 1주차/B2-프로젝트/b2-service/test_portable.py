from concurrent.futures import Future
import importlib.util
import re
import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
import server


def immediate(fn,*args):
    future=Future();future.set_result(fn(*args));return future


def test_without_ai_preserves_source_and_allows_manual_registration(tmp_path,monkeypatch):
    if importlib.util.find_spec('torch') is not None:
        pytest.skip('Run this check in the web-only environment.')
    monkeypatch.delenv('B2_MANUAL_ONLY',raising=False)
    monkeypatch.setattr(server,'DB',tmp_path/'manual.sqlite3')
    monkeypatch.setattr(server.POOL,'submit',immediate)
    source='이준호가 2026-11-06까지 안전커버 간섭 검토 결과를 공유한다.'
    with TestClient(server.app) as client:
        record=client.post('/api/meetings',json={'project':'이동 검증','source':source}).json()
        assert record['status']=='failed'
        assert '03_setup_ai.cmd' in record['error']
        assert record['source']==source
        analysis={'summary':'검토 결과 공유 예정','items':[{'category':'할일','content':'간섭 검토 결과 공유','owner':'이준호','due':'2026-11-06','agreement':None,'evidence_ids':['L001']}],'review_points':[]}
        response=client.post('/api/meetings/'+record['id']+'/review',json={'version':record['version'],'reviewed':True,'analysis':analysis,'actor_id':'pm'})
        assert response.status_code==200
        assert client.get('/api/work-items').json()[0]['status']=='미착수'
        assert client.get('/api/meetings/'+record['id']).json()['source']==source


def test_explicit_manual_mode_never_loads_model(monkeypatch):
    monkeypatch.setenv('B2_MANUAL_ONLY','1')
    engine=server.LocalModel()
    with pytest.raises(ValueError,match='직접 검토 모드'):
        engine.generate('원문은 직접 확인한다.')
    assert engine.model is None


def test_created_records_assets_and_sample_survive_relocation(tmp_path,monkeypatch):
    original=tmp_path/'original.sqlite3'
    copy=tmp_path/'moved.sqlite3'
    monkeypatch.setattr(server,'DB',original)
    monkeypatch.setenv('B2_MANUAL_ONLY','1')
    monkeypatch.setattr(server.POOL,'submit',immediate)
    source='이준호가 2026-11-06까지 안전커버 간섭 검토 결과를 공유한다.'
    with TestClient(server.app) as client:
        assert client.get('/api/meetings').json()==[]
        record=client.post('/api/meetings',json={'project':'이동 검증','source':source}).json()
        analysis={'summary':'검토 결과 공유 예정','items':[{'category':'할일','content':'간섭 검토 결과 공유','owner':'이준호','due':'2026-11-06','agreement':None,'evidence_ids':['L001']}],'review_points':[]}
        response=client.post('/api/meetings/'+record['id']+'/review',json={'version':record['version'],'reviewed':True,'analysis':analysis,'actor_id':'pm'})
        assert response.status_code==200
    # Use a consistent backup, independent of user data and SQLite WAL state.
    src=sqlite3.connect(original)
    dst=sqlite3.connect(copy)
    try:src.backup(dst)
    finally:dst.close();src.close()
    monkeypatch.setattr(server,'DB',copy)
    with TestClient(server.app) as client:
        assert [row['id'] for row in client.get('/api/meetings').json()]==[record['id']]
        restored=client.get('/api/meetings/'+record['id']).json()
        assert restored['source']==source and restored['reviewed']==analysis
        work=client.get('/api/work-items').json()
        assert len(work)==1 and work[0]['content']=='간섭 검토 결과 공유'
        assert work[0]['owner']=='이준호' and work[0]['due']=='2026-11-06'
        home=client.get('/')
        assert home.status_code==200
        for path in re.findall(r'(?:src|href)="(/assets/[^"]+)"',home.text):
            assert client.get(path).status_code==200
        assert client.get('/api/sample').status_code==200
        assert client.get('/api/sample/docx').status_code==200
