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
        updates = {}
        for e in events:
            if e['event'] == 'node.update' and 'data' in e['data']:
                updates[e['data']['node_id']] = e['data']['data']
        progress = [e['data']['progress'] for e in events if 'progress' in e['data']]
        assert [p['done'] for p in progress] == list(range(1, 205)) and {p['total'] for p in progress} == {204}
        assert nodes[1]['title'] == 'Scoring 204 open invoices'
        assert updates['n1']['bank_balance'] == snap['bank']
        assert updates['n1']['payroll_amount'] == snap['payroll']['due_by_target']
        assert updates['n1']['company'] == 'Palletbay Storage & Warehousing'
        fc = updates['n3']
        assert fc['owed_total'] == snap['forecast']['owed_total'] == 28508.72
        assert fc['cash_at_target'] == round(fc['bank_balance'] + fc['expected_by_target']
                                             - fc['bills_due_by_target'] - fc['owner_draw_by_target'], 2)
        assert fc['gap'] == round(max(0, fc['need'] - fc['cash_at_target']), 2)
        assert fc['pessimistic']['cash_at_target'] <= fc['cash_at_target']
        assert fc['conservative']['cash_at_target'] <= fc['cash_at_target']
        assert abs(sum(r['amount'] * r['p_paid_by_target'] for r in rows) - fc['expected_by_target']) < .05
        answer = nodes[3]
        assert answer['data']['answer'] == ('no' if fc['gap'] else 'yes') and answer['data']['gap'] == fc['gap']
        assert answer['data']['spoken'].startswith(answer['title'])
        levers = updates['n5']['levers']
        assert updates['n5']['recommended'] == [l['id'] for l in levers]
        chase = next(l for l in levers if l['id'] == 'chase')
        assert len({t['customer_id'] for t in chase['targets']}) == len(chase['targets']) <= 3
        assert chase['recovers'] == round(sum(t['amount'] for t in chase['targets']), 2)
        decision = next(e['data'] for e in events if e['event'] == 'decision')
        assert decision['node_id'] == 'n5' and decision['auto_resolves_in_s'] is None
        assert [o['id'] for o in decision['options']] == ['yes', 'chase_only', 'no']
        speech = [e['data']['text'] for e in events if e['event'] == 'speech']
        assert speech == [answer['data']['spoken']]
        with conn() as c:
            row = c.execute('select node_id,resolved from decisions where decision_id=%s', (decision['decision_id'],)).fetchone()
            run = c.execute('select status,answer_title from runs where run_id=%s', (rid,)).fetchone()
        assert row == {'node_id': 'n5', 'resolved': None}
        assert run['answer_title'] == answer['title'] and run['status'] == 'open'
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
