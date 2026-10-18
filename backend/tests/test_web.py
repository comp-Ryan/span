from fastapi import FastAPI
from fastapi.testclient import TestClient

from owed.main import app
from owed.web import install_frontend


def test_production_static_and_deep_report_do_not_shadow_api(tmp_path):
    (tmp_path / 'index.html').write_text('<html>Owed product</html>')
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'assets' / 'app.js').write_text('window.owed = true')
    test_app = FastAPI()
    @test_app.get('/api/health')
    def health():
        return {'ok': True}
    install_frontend(test_app, tmp_path)
    client = TestClient(test_app)
    assert client.get('/').text == '<html>Owed product</html>'
    assert client.get('/report/rep-test').text == '<html>Owed product</html>'
    for path in ('/home', '/get-paid', '/reports', '/customers', '/customers/customer-1'):
        assert client.get(path, headers={'accept': 'text/html,application/xhtml+xml'}).text == '<html>Owed product</html>'
    assert client.get('/api/health').json() == {'ok': True}
    assert client.get('/assets/app.js').status_code == 200
    for path in ('/assets/missing.js', '/api/missing', '/.env', '/owed/config.py'):
        assert client.get(path).status_code == 404


def test_missing_build_redirect_and_real_api_aliases(tmp_path):
    test_app = FastAPI()
    install_frontend(test_app, tmp_path)
    assert TestClient(test_app).get('/', follow_redirects=False).headers['location'] == '/hub'
    assert TestClient(test_app).get('/report/rep-missing').status_code == 503
    client = TestClient(app)
    assert client.get('/api/health').json() == client.get('/health').json()
    assert client.get('/api/companies').json() == client.get('/companies').json()
    assert client.get('/api/cash?target=2026-10-09').json() == client.get('/cash?target=2026-10-09').json()
    assert client.get('/hub').status_code == 200
    assert 'Span API Contract' in client.get('/hub/api/doc/contract').text
    assert client.get('/api/pay/missing').status_code == 404


def test_span_brand_preserves_package_and_protocol_identifiers():
    from owed.agents.runtime import seed_for
    from owed.config import settings
    from owed.payments import PAGE
    from owed.planner import system_prompt
    from owed.finance import queries
    assert app.title == 'Span'
    assert 'You are Span' in system_prompt(settings.demo_company, queries.AS_OF_DEFAULT)
    assert 'Secured by Span' in PAGE.read_text()
    assert seed_for.__module__ == 'owed.agents.runtime'
