from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from owed.db import conn
from owed.events import emit, read_events
from owed.main import app
from owed.runs import create


@pytest.fixture
def run():
    rid = create('company-020', 'test ' + uuid4().hex, 'web', 'payroll_check')
    yield rid
    with conn() as c:
        c.execute('delete from events where run_id=%s', (rid,))
        c.execute('delete from runs where run_id=%s', (rid,))


def test_persistence_replay_and_company_isolation(run):
    first = emit(run, 'node.create', {'node_id': 'n1', 'type': 'context', 'parent': None})
    second = emit(run, 'node.update', {'node_id': 'n1', 'status': 'done'})
    rows = read_events('company-020', int(first['id']))
    assert any(str(r['id']) == second['id'] for r in rows)
    assert all(r['company_id'] == 'company-020' for r in rows)
    client = TestClient(app)
    replay = client.get(f'/runs/{run}').json()['events']
    assert [e['event'] for e in replay] == ['run.start', 'node.create', 'node.update']
    assert replay[-1]['data']['id'] == second['id']
    assert client.get(f'/runs/{run}?company=company-001').status_code == 404
    assert client.get('/runs?company=missing').json()['error']['code'] == '404'
