import asyncio
from datetime import date

from owed.config import settings
from owed.db import conn
from owed.runs import create, replay_run
from owed.runs.payroll import run_payroll, snapshot, target_for


def test_payroll_complete_real_data():
    before = settings.scoring_interval_ms
    settings.scoring_interval_ms = 0
    rid = create('company-020', 'Am I making payroll Friday?', 'web', 'payroll_check')
    try:
        asyncio.run(run_payroll(rid, 'company-020', date(2026, 10, 9)))
        events = replay_run(rid)['events']
        nodes = [e['data'] for e in events if e['event'] == 'node.create']
        assert [n['type'] for n in nodes] == ['context', 'scoring', 'forecast', 'answer', 'levers']
        assert [n['parent'] for n in nodes] == [None, 'n1', 'n2', 'n3', 'n4']
        rows = [e['data']['row'] for e in events if 'row' in e['data']]
        snap = snapshot('company-020', date(2026, 10, 9))
        assert len(rows) == len(snap['scored']) == 204
        assert abs(sum(r['amount'] for r in rows) - snap['forecast']['owed_total']) < .01
        assert all(0 <= r['p_paid_by_target'] <= 1 for r in rows)
        assert snap['bank'] == 6533.65
        assert snap['payroll']['due_by_target'] > 2844.64
        assert events[-1]['event'] == 'run.end'
        assert any(e['event'] == 'decision' for e in events)
    finally:
        settings.scoring_interval_ms = before
        with conn() as c:
            c.execute('delete from decisions where run_id=%s', (rid,))
            c.execute('delete from events where run_id=%s', (rid,))
            c.execute('delete from runs where run_id=%s', (rid,))

def test_target_uses_dataset_clock():
    assert target_for('payroll Friday') == date(2026, 10, 9)
    assert target_for('next two weeks') == date(2026, 10, 20)


def test_forecast_includes_overdue_unpaid_bills():
    snap = snapshot('company-020',date(2026,10,20))
    assert snap['forecast']['bills_due_by_target'] == 10866.86
    assert snap['forecast']['gap'] == 384.94
