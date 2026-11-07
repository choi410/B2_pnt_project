import pytest
from test_service import client


def test_public_host_is_blocked_by_default(client, monkeypatch):
    monkeypatch.delenv('B2_PUBLIC_ORIGIN', raising=False)
    response = client.get('/api/health', headers={'host':'sample-share.trycloudflare.com'})
    assert response.status_code == 403


def test_explicit_public_origin_allows_reads_and_same_origin_validation(client, monkeypatch):
    monkeypatch.setenv('B2_PUBLIC_ORIGIN', 'https://sample-share.trycloudflare.com')
    headers = {'host':'sample-share.trycloudflare.com', 'origin':'https://sample-share.trycloudflare.com'}
    assert client.get('/api/health', headers=headers).status_code == 200
    # Empty input must reach validation, without creating or changing any record.
    assert client.post('/api/requirement-trials', json={}, headers=headers).status_code == 422


def test_other_public_hosts_and_cross_site_writes_stay_blocked(client, monkeypatch):
    monkeypatch.setenv('B2_PUBLIC_ORIGIN', 'https://sample-share.trycloudflare.com')
    assert client.get('/api/health', headers={'host':'another-share.trycloudflare.com'}).status_code == 403
    for origin in ['https://untrusted.example', 'http://sample-share.trycloudflare.com', 'null']:
        assert client.post('/api/requirement-trials', json={}, headers={
            'host':'sample-share.trycloudflare.com','origin':origin}).status_code == 403
    assert client.get('/api/health').status_code == 200


@pytest.mark.parametrize('value', ['*', 'http://sample-share.trycloudflare.com',
    'https://sample-share.trycloudflare.com/path', 'https://user:password@sample-share.trycloudflare.com',
    'https://sample-share.trycloudflare.com?query=1'])
def test_invalid_public_origin_never_opens_public_host(client, monkeypatch, value):
    monkeypatch.setenv('B2_PUBLIC_ORIGIN', value)
    assert client.get('/api/health', headers={'host':'sample-share.trycloudflare.com'}).status_code == 403
