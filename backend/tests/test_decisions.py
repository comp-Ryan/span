from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from owed.db import apply_runtime, conn
from owed.decisions import request_decision, resolve
from owed.main import app
from owed.runs import create, replay_run

OPTIONS = [{'id': 'accept', 'label': 'Accept'}, {'id': 'decline', 'label': 'Decline'}]


@pytest.fixture
def rid():
    apply_runtime()
    run_id = create('company-020', 'Decision contract test', 'web', 'free_question')
    yield run_id
    with conn() as c:
        c.execute('delete from action_jobs where decision_id in (select decision_id from decisions where run_id=%s)', (run_id,))
        c.execute('delete from decisions where run_id=%s', (run_id,))
        c.execute('delete from events where run_id=%s', (run_id,))
        c.execute('delete from runs where run_id=%s', (run_id,))


def emitted(rid, name):
    return [e['data'] for e in replay_run(rid)['events'] if e['event'] == name]


def test_request_decision_persists_and_emits_contract_shape(rid):
    did = request_decision(rid, 'n10', 'Accept two installments?', OPTIONS, {'kind': 'test', 'amount': 1.5}, timeout=8, default='accept')
    assert did.startswith('d-')
    event = emitted(rid, 'decision')[-1]
    assert {k: event[k] for k in ('decision_id', 'node_id', 'prompt', 'options', 'auto_resolves_in_s', 'default')} == {
        'decision_id': did, 'node_id': 'n10', 'prompt': 'Accept two installments?', 'options': OPTIONS,
        'auto_resolves_in_s': 8, 'default': 'accept'}
    with conn() as c:
        row = c.execute('select * from decisions where decision_id=%s', (did,)).fetchone()
    assert row['payload'] == {'kind': 'test', 'amount': 1.5} and row['default_option'] == 'accept'
    assert timedelta(seconds=6) < row['deadline'] - datetime.now(UTC) <= timedelta(seconds=8)
    assert row['resolved'] is None


def test_human_decision_has_no_deadline_or_default(rid):
    request_decision(rid, 'n5', 'Text them?', OPTIONS, {})
    event = emitted(rid, 'decision')[-1]
    assert event['auto_resolves_in_s'] is None and 'default' not in event
    with conn() as c:
        assert c.execute('select deadline from decisions where decision_id=%s', (event['decision_id'],)).fetchone()['deadline'] is None


def test_resolve_validates_scope_and_option(rid):
    did = request_decision(rid, 'n5', 'Approve?', OPTIONS, {})
    with pytest.raises(HTTPException) as exc:
        resolve(did, 'decline', 'company-001')
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        resolve('d-missing', 'decline', 'company-020')
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        resolve(did, 'maybe', 'company-020')
    assert exc.value.status_code == 422
    assert emitted(rid, 'decision.resolved') == []


def test_resolve_emits_once_and_queues_job(rid):
    did = request_decision(rid, 'n5', 'Approve?', OPTIONS, {})
    assert resolve(did, 'decline', 'company-020', note='not this week') == {'decision_id': did, 'resolved': 'decline'}
    assert resolve(did, 'decline', 'company-020') == {'decision_id': did, 'resolved': 'decline'}
    with pytest.raises(HTTPException) as exc:
        resolve(did, 'accept', 'company-020')
    assert exc.value.status_code == 409
    resolved = emitted(rid, 'decision.resolved')
    assert len(resolved) == 1
    assert {k: resolved[0][k] for k in ('decision_id', 'node_id', 'option_id')} == {'decision_id': did, 'node_id': 'n5', 'option_id': 'decline'}
    update = emitted(rid, 'node.update')[-1]
    assert update['node_id'] == 'n5' and update['data'] == {'decision_id': did, 'resolved': 'decline', 'note': 'not this week'}
    with conn() as c:
        row = c.execute('select resolved,resolved_at from decisions where decision_id=%s', (did,)).fetchone()
        jobs = c.execute('select count(*) n from action_jobs where decision_id=%s', (did,)).fetchone()['n']
    assert row['resolved'] == 'decline' and row['resolved_at'] is not None and jobs == 1


def test_decision_endpoint_and_api_alias(rid):
    client = TestClient(app)
    did = request_decision(rid, 'n5', 'Approve?', OPTIONS, {})
    assert client.post(f'/decisions/{did}', json={'option_id': 'nope'}).status_code == 422
    assert client.post(f'/decisions/{did}?company=company-001', json={'option_id': 'decline'}).status_code == 404
    response = client.post(f'/api/decisions/{did}', json={'option_id': 'decline', 'note': 'later'})
    assert response.status_code == 200 and response.json() == {'decision_id': did, 'resolved': 'decline'}
    assert client.post(f'/decisions/{did}', json={'option_id': 'decline'}).json() == response.json()
    assert client.post(f'/decisions/{did}', json={'option_id': 'accept'}).status_code == 409
    assert client.post(f'/decisions/{did}', json={'option_id': 'decline', 'note': 'x' * 4001}).status_code == 422
