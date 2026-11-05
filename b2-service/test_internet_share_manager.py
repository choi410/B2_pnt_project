import importlib
import subprocess
from pathlib import Path
import pytest


def manager(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    return importlib.import_module('internet_share')


def test_failed_docker_inspection_never_claims_sharing_stopped(tmp_path, monkeypatch, capsys):
    module=manager(monkeypatch)
    state=tmp_path/'internet-share.json'
    state.write_text('{"url":"https://example.trycloudflare.com"}')
    monkeypatch.setattr(module,'STATE',state)
    monkeypatch.setattr(module,'run',lambda *args,**kwargs:subprocess.CompletedProcess(
        args,1,stdout='',stderr='error during connect: Docker endpoint access denied'))
    with pytest.raises(RuntimeError,match='access denied'):
        module.stop('docker')
    assert state.exists(), 'The last known link must remain available for recovery.'
    assert 'sharing stopped' not in capsys.readouterr().out


def test_confirmed_missing_connector_can_clear_stale_link(tmp_path, monkeypatch, capsys):
    module=manager(monkeypatch)
    state=tmp_path/'internet-share.json'
    state.write_text('{}')
    monkeypatch.setattr(module,'STATE',state)
    monkeypatch.setattr(module,'run',lambda *args,**kwargs:subprocess.CompletedProcess(
        args,1,stdout='',stderr='Error: No such object: b2-workspace-share'))
    module.stop('docker')
    assert not state.exists()
    assert 'sharing stopped' in capsys.readouterr().out
