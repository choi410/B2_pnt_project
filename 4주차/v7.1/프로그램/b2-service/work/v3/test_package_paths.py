"""Package relocation must preserve stored records and isolate test attachments."""
import json
from work.v17.storage_paths import rebase_record_paths
from work.v3.test_connected import client, w


def test_rebase_nested_attachments_preserves_content(tmp_path):
    old = 'C:\\old\\PNT_v4.2\\프로그램\\b2-service\\data\\v4.2\\files\\meeting.pdf'
    record = {'original_path': old, 'revisions': [{'files': {'pdf': old}}], 'txt': old[:-3] + 'txt',
              'body': old, 'title': 'PNT_v4.2'}
    encoded = json.dumps(record)
    root = tmp_path / 'files'
    expected = str((root / 'meeting.pdf').resolve())
    rebased = rebase_record_paths(record, root)
    assert rebased['original_path'] == expected
    assert rebased['revisions'][0]['files']['pdf'] == expected
    assert rebased['txt'] == str((root / 'meeting.txt').resolve())
    assert rebased['body'] == old and rebased['title'] == 'PNT_v4.2'
    assert json.dumps(record) == encoded


def test_rebase_keeps_paths_within_current_data(tmp_path):
    root = tmp_path / 'evaluation/files'
    old_root = tmp_path / 'old/b2-service/data/v17/files'
    old_root.mkdir(parents=True)
    old = old_root / 'meeting.pdf'
    old.write_bytes(b'old data')
    assert rebase_record_paths({'pdf': str(old)}, root)['pdf'] == str((root / old.name).resolve())
    for path in ('C:/unrelated/meeting.pdf', '/old/b2-service/data/v17/files/../secret',
                 '/old/b2-service/data/v17/files/C:/secret'):
        assert rebase_record_paths({'pdf': path}, root)['pdf'] == path


def test_loading_relocated_record_does_not_update_database(client):
    c, _ = client
    value = {'id': 'relocation-check', 'original_path':
             'C:/old/b2-service/data/v4.2/files/meeting.pdf'}
    payload = json.dumps(value)
    with w.connect() as db:
        db.execute('INSERT INTO records(kind,id,payload) VALUES(?,?,?)',
                   ('import', value['id'], payload))
        expected = str((w.FILES / 'meeting.pdf').resolve())
        assert w.read(db, 'import', value['id'])['original_path'] == expected
        assert next(row for row in w.all_records(db, 'import') if row['id'] == value['id'])['original_path'] == expected
        assert db.execute('SELECT payload FROM records WHERE kind=? AND id=?',
                          ('import', value['id'])).fetchone()[0] == payload


def test_testing_does_not_load_service_mail_credentials():
    from work.v3 import mailer
    import os
    assert os.environ['B2_TEAM_TESTING'] == '1'
    assert mailer.mode() == 'console'
