import asyncio
from datetime import date

import pytest
from fastapi import BackgroundTasks, HTTPException

from owed.config import settings
from owed.db import conn
from owed.planner import route_intent
from owed.runs import create, replay_run
from owed.runs.payroll import Ask, ask, run_payroll, snapshot


def clean(rids):
    with conn() as c:
        for rid in rids:
            c.execute('delete from decisions where run_id=%s', (rid,))
            c.execute('delete from events where run_id=%s', (rid,))
            c.execute('delete from runs where run_id=%s', (rid,))


def test_follow_up_inherits_target_excludes_customer_and_branches():
    old = settings.scoring_interval_ms
    settings.scoring_interval_ms = 0
    rids = []
    try:
        parent = create('company-020', 'payroll next two weeks', 'web', 'payroll_check', target_date=date(2026, 10, 20))
        rids.append(parent)
        asyncio.run(run_payroll(parent, 'company-020', date(2026, 10, 20)))
        tasks = BackgroundTasks()
        reply = ask(Ask(question='what if Evergreen doesn’t pay?', parent_run_id=parent), tasks, 'company-020')
        rids.append(reply['run_id'])
        assert reply['intent'] == 'what_if_customer'
        assert reply['target_date'] == '2026-10-20'
        asyncio.run(tasks())
        events = replay_run(reply['run_id'])['events']
        assert events[0]['data']['parent_run_id'] == parent
        root = next(e['data'] for e in events if e['event'] == 'node.create')
        assert root['parent_run_id'] == parent and root['parent'] == 'n1'
        assert root['data']['reused_from'] == {'run_id': parent, 'node_id': 'n1'}
        rows = [e['data']['row'] for e in events if 'row' in e['data']]
        assert not any(r['customer'] == 'Evergreen Juniper Flats Removals' for r in rows)
        forecast = next(e['data']['data'] for e in events if e['event'] == 'node.update' and e['data']['node_id'] == 'n3')
        baseline = snapshot('company-020', date(2026, 10, 20))
        assert forecast['expected_by_target'] < baseline['forecast']['expected_by_target']
        assert forecast['gap'] > baseline['forecast']['gap']
        with conn() as c:
            persisted = c.execute('select target_date,excluded_customer_id from runs where run_id=%s', (reply['run_id'],)).fetchone()
        assert persisted['target_date'] == date(2026, 10, 20)
        assert persisted['excluded_customer_id'] == forecast['excluded_customer_id']
        levers = next(e['data']['data']['levers'] for e in events if 'levers' in e['data'].get('data', {}))
        assert all(t['customer_id'] != forecast['excluded_customer_id'] for l in levers for t in l.get('targets', []))
        tasks = BackgroundTasks()
        late = ask(Ask(question="show me who's late", parent_run_id=parent), tasks, 'company-020')
        rids.append(late['run_id'])
        asyncio.run(tasks())
        events = replay_run(late['run_id'])['events']
        nodes = [e['data'] for e in events if e['event'] == 'node.create']
        assert len(nodes) == 1 and nodes[0]['type'] == 'scoring'
        assert nodes[0]['parent'] == 'n2' and nodes[0]['parent_run_id'] == parent
        days = [e['data']['row']['days_past_due'] for e in events if 'row' in e['data']]
        assert days == sorted(days, reverse=True) and min(days) > 0
        with pytest.raises(HTTPException) as error:
            ask(Ask(question='show late', parent_run_id=parent), BackgroundTasks(), 'company-001')
        assert error.value.status_code == 404
    finally:
        settings.scoring_interval_ms = old
        clean(rids[::-1])


def test_branch_intents_handle_smart_apostrophes():
    assert route_intent('What if Evergreen doesn’t pay?') == 'what_if_customer'
    assert route_intent('Show me who’s late') == 'show_late'
