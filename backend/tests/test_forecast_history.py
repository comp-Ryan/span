import asyncio
from datetime import date

import pytest
from fastapi.testclient import TestClient

from owed.actions import refresh_forecasts
from owed.db import apply_runtime, conn
from owed.finance.history import history
from owed.main import app
from owed.planner import ToolContext
from owed.runs import create, replay_run


@pytest.fixture
def run_id():
    apply_runtime()
    rid = create('company-020', 'Forecast history test', 'web', 'free_question')
    yield rid
    with conn() as c:
        c.execute('delete from cash_projection where forecast_id in (select forecast_id from forecast_history where run_id=%s)', (rid,))
        c.execute('delete from events where run_id=%s', (rid,))
        c.execute('delete from runs where run_id=%s', (rid,))


def test_forecast_revisions_are_atomic_scoped_and_retain_customer_assumption(run_id):
    ctx = ToolContext(run_id, 'company-020', date(2026, 10, 20))
    for pays in (False, True):
        result = asyncio.run(ctx.execute('forecast_cash', {'customer_id': 'cust-customer-37', 'will_pay': pays}))
        assert 'error' not in result
        assert result['forecast_id']
    before = history('company-020', run_id, 20)['forecasts']
    assert len(before) == 2
    assert before[0]['forecast']['excluded_customer_id'] == 'cust-customer-37'
    assert before[1]['forecast']['assumed_customer_id'] == 'cust-customer-37'
    assert all(len(r['days']) == len(r['pessimistic_days']) == 15 for r in before)
    refresh_forecasts('company-020')
    after = history('company-020', run_id, 20)['forecasts']
    assert len(after) == 4 and after[:2] == before  # old estimates never overwritten
    assert after[2]['forecast']['excluded_customer_id'] == 'cust-customer-37'
    assert after[3]['forecast']['assumed_customer_id'] == 'cust-customer-37'
    updates = [e['data']['data'] for e in replay_run(run_id)['events'] if e['event'] == 'node.update']
    assert [r['forecast_id'] for r in updates] == [r['forecast_id'] for r in after]
    assert history('company-020', run_id, 1)['forecasts'] == after[-1:]
    client = TestClient(app)
    assert client.get(f'/api/forecasts?company=company-001&run_id={run_id}').status_code == 404
    assert client.get('/api/forecasts?company=company-020&limit=101').status_code == 422
    assert client.get(f'/api/forecasts?company=company-020&run_id={run_id}').json()['forecasts'][-1]['days']


def test_cash_assumption_is_scoped_and_not_written_on_read(run_id):
    client = TestClient(app)
    url = '/api/cash?company=company-020&target=2026-10-20'
    ordinary = client.get(url).json()
    assumed = client.get(url + '&will_pay=cust-customer-37').json()
    assert assumed['assumptions']['will_pay'] == 'cust-customer-37'
    assert assumed['days'][-1]['balance'] > ordinary['days'][-1]['balance']
    assert client.get(url + '&will_pay=foreign').status_code == 404
    assert client.get(url + '&will_pay=cust-customer-37&never_pays=cust-customer-37').status_code == 422
    assert history('company-020', run_id, 20)['forecasts'] == []


def test_history_and_event_roll_back_together(run_id, monkeypatch):
    import psycopg
    import owed.finance.cash as cash
    from owed.finance.history import emit_forecast
    from owed.runs.payroll import snapshot
    original = cash.projection
    def invalid(*args, **kwargs):
        value = original(*args, **kwargs)
        value['days'][0]['date'] = 'not-a-date'
        return value
    monkeypatch.setattr(cash, 'projection', invalid)
    before = replay_run(run_id, 'company-020')['events']
    with pytest.raises(psycopg.DataError):
        emit_forecast(run_id, 'forecast-test', snapshot('company-020', date(2026, 10, 20)))
    assert history('company-020', run_id, 20)['forecasts'] == []
    assert replay_run(run_id, 'company-020')['events'] == before


def test_cash_history_is_a_compact_company_series_for_the_home_chart(run_id):
    from owed.finance.history import cash_history
    ctx = ToolContext(run_id, 'company-020', date(2026, 10, 20))
    assert 'error' not in asyncio.run(ctx.execute('forecast_cash', {}))
    assert 'error' not in asyncio.run(ctx.execute('forecast_cash', {'customer_id': 'cust-customer-37', 'will_pay': False}))
    body = cash_history('company-020', 30)
    assert body['storage'] == 'timescaledb'
    points = [p for p in body['points'] if p['run_id'] == run_id]
    assert len(points) == 2 and points[0]['computed_at'] <= points[1]['computed_at']  # oldest first
    first, second = points
    assert first['target'] == '2026-10-20' and first['cash_at_target'] - first['need'] == pytest.approx(-first['gap'], abs=0.01)
    assert second['gap'] > first['gap'] and second['excluded_customer_id'] == 'cust-customer-37'
    assert {'forecast_id', 'run_id', 'computed_at', 'target', 'cash_at_target', 'need', 'gap', 'pessimistic_gap'} <= set(first)
    client = TestClient(app)
    assert client.get('/api/cash/history?company=company-020&limit=1').json()['points'][-1]['forecast_id'] == second['forecast_id']
    assert client.get('/api/cash/history?company=company-404').status_code == 404
    assert client.get('/api/cash/history?company=company-020&limit=0').status_code == 422
    assert client.get('/cash/history?company=company-020').status_code == 200
