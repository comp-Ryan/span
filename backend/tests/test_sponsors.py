"""/sponsors/checks runs every integration check concurrently; a slow or broken one becomes a fail row, never a 500."""
import asyncio
import json

from fastapi.testclient import TestClient

from owed import sponsors
from owed.config import settings


def test_checks_page_is_resilient_and_never_leaks_secrets(monkeypatch):
    from owed.main import app

    async def ok():
        return 'pass', 'answered', True

    async def boom():
        raise RuntimeError('key sk-secret-123 exploded')

    async def slow():
        await asyncio.sleep(5)
        return 'pass', 'late', True

    monkeypatch.setattr(sponsors, 'TIMEOUT', 0.05)
    monkeypatch.setattr(sponsors, 'CHECKS', [('A', 'track a', ok), ('B', 'track b', boom), ('C', 'track c', slow)])
    monkeypatch.setattr(settings, 'gemini_api_key', 'AIza-very-secret')
    body = TestClient(app).get('/api/sponsors/checks').json()
    by = {c['name']: c for c in body['checks']}
    assert by['A']['status'] == 'pass' and by['A']['detail'] == 'answered'
    assert by['B']['status'] == 'fail' and 'RuntimeError' in by['B']['detail']
    assert by['C']['status'] == 'fail' and 'no answer' in by['C']['detail']
    assert body['summary'] == {'pass': 1, 'fail': 2} and all(c['ms'] >= 0 for c in body['checks'])
    assert 'AIza-very-secret' not in json.dumps(body)


def test_every_real_check_is_a_coroutine_with_a_track():
    assert len(sponsors.CHECKS) == 8 and {'Visa', 'Solana', 'Sentry', 'Vultr'}.isdisjoint(n for n, _, _ in sponsors.CHECKS)
    for name, track, fn in sponsors.CHECKS:
        assert name and track and asyncio.iscoroutinefunction(fn)


def test_the_public_site_may_call_a_backend_on_the_visitors_machine():
    """youare.cooking runs the checks against the laptop's backend; Chrome's private-network preflight must be allowed."""
    from owed.main import app
    r = TestClient(app).options('/api/sponsors/checks', headers={
        'Origin': 'https://youare.cooking', 'Access-Control-Request-Method': 'GET', 'Access-Control-Request-Private-Network': 'true'})
    assert r.status_code == 200
    assert r.headers.get('access-control-allow-private-network') == 'true'
    assert r.headers.get('access-control-allow-origin') in ('*', 'https://youare.cooking')


def test_ordinary_requests_do_not_get_the_private_network_header():
    from contextlib import nullcontext
    from types import SimpleNamespace
    from owed import db
    from owed.main import app
    import pytest
    mp = pytest.MonkeyPatch(); mp.setattr(db, 'conn', lambda: nullcontext(SimpleNamespace(execute=lambda *a: None)))
    try:
        r = TestClient(app).get('/api/health')
        assert r.status_code == 200 and 'access-control-allow-private-network' not in r.headers
    finally:
        mp.undo()


def test_openrouter_check_reports_the_account_balance_not_the_key_cap(monkeypatch):
    """The key's limit minus usage ($4.81) is a spending cap; the account itself had $0, so only the free models answer."""
    import httpx
    real = httpx.AsyncClient
    monkeypatch.setattr(settings, 'openrouter_api_key', 'sk-or-test')
    monkeypatch.setattr(settings, 'openrouter_model', 'google/gemini-3.8-flash, nvidia/nemotron-3-ultra-550b-a55b:free')

    def handle(request):
        if request.url.path.endswith('/auth/key'):
            return httpx.Response(200, json={'data': {'limit': 5, 'usage': 0.19}})
        if request.url.path.endswith('/credits'):
            return httpx.Response(200, json={'data': {'total_credits': 0, 'total_usage': 0.2}})
        return httpx.Response(404)
    monkeypatch.setattr(sponsors.httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(handle), **kw))
    status, detail, configured = asyncio.run(sponsors.check_openrouter())
    assert status == 'warn' and configured
    assert '$4.81' not in detail and 'no credit' in detail and 'nemotron-3-ultra-550b-a55b:free' in detail
