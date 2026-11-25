"""Portable examples must retain references and never overwrite local work."""
import json
import shutil
import sqlite3
from pathlib import Path
import pytest
from work.v3.test_connected import client, w
from work.v3 import sample_workspace as sample


def seed(monkeypatch):
    monkeypatch.setenv('B2_INCLUDE_SAMPLE', '1')
    sample.initialize(w)


def test_sample_downloads_and_reviewed_state(client, monkeypatch):
    c, _ = client
    seed(monkeypatch)
    data = c.get('/api/v3/workspace').json()
    assert [len(data[k]) for k in ('projects', 'meetings', 'changes')] == [6, 10, 27]
    assert all(e['review_state'] == '확인됨' for e in data['changes'])
    for meeting in data['meetings']:
        response = c.get('/api/v3/meetings/' + meeting['id'] + '/download')
        assert response.status_code == 200 and response.content.startswith(b'%PDF')
    with w.connect() as db:
        assert not w.all_records(db, 'approval_request')
        assert not w.all_records(db, 'ai_conversation')


def test_sample_is_once_only_even_after_deleting_examples(client, monkeypatch):
    seed(monkeypatch)
    with w.connect() as db:
        project = w.all_records(db, 'project')[0]
        project['name'] = '팀원이 수정한 이름'
        w.save(db, 'project', project)
    sample.initialize(w)
    with w.connect() as db:
        assert w.read(db, 'project', project['id'])['name'] == '팀원이 수정한 이름'
        db.execute("DELETE FROM records WHERE kind != 'person'")
    sample.initialize(w)
    with w.connect() as db:
        assert not w.all_records(db, 'project')


def test_sample_does_not_mix_with_existing_workspace(client, monkeypatch):
    c, _ = client
    result = c.post('/api/projects', json={'name': '기존 업무', 'members': ['team1']})
    assert result.status_code == 201
    seed(monkeypatch)
    data = c.get('/api/v3/workspace').json()
    assert len(data['projects']) == 1 and data['projects'][0]['name'] == '기존 업무'
    assert data['meetings'] == []


def test_data_folder_relocation_keeps_originals(client, monkeypatch, tmp_path):
    c, _ = client
    seed(monkeypatch)
    moved = tmp_path / '옮긴 폴더'
    moved.mkdir()
    shutil.copytree(w.FILES, moved / 'files')
    with sqlite3.connect(w.DB) as source, sqlite3.connect(moved / 'workspace.sqlite3') as target:
        source.backup(target)
    monkeypatch.setattr(w, 'DB', moved / 'workspace.sqlite3')
    monkeypatch.setattr(w, 'FILES', moved / 'files')
    sample.initialize(w)
    with w.connect() as db:
        for meeting in w.all_records(db, 'meeting'):
            assert Path(meeting['pdf']).is_relative_to(moved)
            assert Path(meeting['pdf']).is_file()
            assert meeting['pdf'] == meeting['original_path']


def test_corrupt_sample_does_not_partially_seed(client, monkeypatch, tmp_path):
    damaged = tmp_path / 'damaged'
    shutil.copytree(sample.SAMPLE, damaged)
    bundle = json.loads((damaged / 'workspace.json').read_text(encoding='utf-8'))
    name = next(iter(bundle['files']))
    (damaged / 'files' / name).write_bytes(b'corrupt')
    monkeypatch.setattr(sample, 'SAMPLE', damaged)
    monkeypatch.setenv('B2_INCLUDE_SAMPLE', '1')
    with pytest.raises(ValueError, match='손상'):
        sample.initialize(w)
    with w.connect() as db:
        assert not w.all_records(db, 'project')
        assert not db.execute('SELECT 1 FROM workspace_meta WHERE key=?', (sample.MARKER,)).fetchone()
