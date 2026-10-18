import asyncio
from datetime import date

import pytest
from fastapi.encoders import jsonable_encoder

from owed.db import conn
from owed.decisions import request_decision
from owed.planner import TOOLS, ToolContext
from owed.runs import create, replay_run
from owed.runs.payroll import levers_for, snapshot

COMPANY, TARGET, EVERGREEN = 'company-020', date(2026, 10, 9), 'cust-customer-37'


@pytest.fixture(scope='module')
def snap():
    return snapshot(COMPANY, TARGET)


@pytest.fixture
def ctx():
    rid = create(COMPANY, 'Planner tool contract test', 'web', 'free_question')
    yield ToolContext(rid, COMPANY, TARGET)
    with conn() as c:
        c.execute('delete from action_jobs where decision_id in (select decision_id from decisions where run_id=%s)', (rid,))
        c.execute('delete from decisions where run_id=%s', (rid,))
        c.execute('delete from events where run_id=%s', (rid,))
        c.execute('delete from runs where run_id=%s', (rid,))


def run(ctx, name, args=None):
    return asyncio.run(ctx.execute(name, args or {}))


def node_events(ctx):
    events = replay_run(ctx.run_id)['events']
    return ([e['data'] for e in events if e['event'] == 'node.create'],
            [e['data'] for e in events if e['event'] == 'node.update'])


def test_every_declared_tool_has_a_schema():
    for tool in TOOLS:
        params = tool['parameters']
        assert params['type'] == 'OBJECT'
        assert set(params['required']) <= set(params['properties'])
    assert len({t['name'] for t in TOOLS}) == len(TOOLS)


def test_forecast_cash_returns_snapshot_forecast(ctx, snap):
    result = run(ctx, 'forecast_cash')
    assert result['bank_balance'] == snap['bank'] and result['target_date'] == '2026-10-09'
    for key in ('owed_total', 'expected_by_target', 'bills_due_by_target', 'cash_at_target', 'need', 'gap',
                'conservative', 'pessimistic', 'owner_draw_by_target'):
        assert result[key] == jsonable_encoder(snap['forecast'][key])
    created, updated = node_events(ctx)
    assert created[0]['type'] == 'forecast' and created[0]['title'] == 'Forecast cash'
    assert created[0]['status'] == 'running' and created[0]['parent'] == 'context'
    assert updated[-1]['status'] == 'done' and updated[-1]['data']['gap'] == result['gap']


def test_rank_chase_matches_payroll_levers(ctx, snap):
    result = run(ctx, 'rank_chase')
    assert result == {'levers': jsonable_encoder(levers_for(snap))}
    chase = result['levers'][0]
    assert chase['id'] == 'chase' and 1 <= len(chase['targets']) <= 3
    assert all({'invoice_id', 'customer_id', 'customer', 'amount', 'reason'} <= set(t) for t in chase['targets'])
    assert node_events(ctx)[0][0]['type'] == 'levers'


def test_score_customer_is_company_scoped(ctx, snap):
    result = run(ctx, 'score_customer', {'customer_id': EVERGREEN})
    assert result['customer'] == {'id': EVERGREEN, 'display_name': 'Evergreen Juniper Flats Removals'}
    assert result['history'] and result['invoices']
    assert {r['customer_id'] for r in result['invoices']} == {EVERGREEN}
    assert len(result['invoices']) == sum(r['customer_id'] == EVERGREEN for r in snap['scored'])
    with conn() as c:
        other = c.execute("select id from customers where company_id<>%s and id not in (select id from customers where company_id=%s) limit 1",
                          (COMPANY, COMPANY)).fetchone()
    assert run(ctx, 'score_customer', {'customer_id': other['id'] if other else 'nope'}) == {'error': 'Customer not found in this company'}
    created, updated = node_events(ctx)
    assert [n['type'] for n in created] == ['scoring', 'scoring']
    assert [u['status'] for u in updated] == ['done', 'failed']


def test_query_books_entities(ctx, snap):
    assert run(ctx, 'query_books', {'entity': 'company'})['company']['company_id'] == COMPANY
    invoices = run(ctx, 'query_books', {'entity': 'invoices'})['invoices']
    assert len(invoices) == len(snap['scored']) == 204
    bills = run(ctx, 'query_books', {'entity': 'bills'})['bills']
    assert [b['bill_id'] for b in bills] == [b['bill_id'] for b in snap['bills']]
    customers = run(ctx, 'query_books', {'entity': 'customers'})['customers']
    assert customers and EVERGREEN in {c['id'] for c in customers}
    assert set(customers[0]) == {'id', 'display_name', 'payment_terms'}
    assert run(ctx, 'query_books', {'entity': 'payments'}) == {'error': 'Unsupported books entity'}
    assert all(n['type'] == 'context' for n in node_events(ctx)[0])


def test_invoice_tools(ctx, snap):
    row = max(snap['scored'], key=lambda r: r['days_past_due'])
    assert run(ctx, 'predict_payment', {'invoice_id': row['invoice_id']})['invoice']['invoice_id'] == row['invoice_id']
    draft = run(ctx, 'draft_reminder', {'invoice_id': row['invoice_id']})
    assert draft['sent'] is False and draft['invoice_id'] == row['invoice_id']
    assert draft['tone'] == ('firm' if row['days_past_due'] > 30 else 'friendly')
    assert row['invoice_id'] in draft['body'] and row['customer_name'] in draft['body']
    assert run(ctx, 'draft_reminder', {'invoice_id': 'inv-nope'}) == {'error': 'Open invoice not found in this company'}


def test_actions_require_approval_and_never_send(ctx, snap):
    invoice = snap['scored'][0]['invoice_id']
    sent = run(ctx, 'send_message', {'invoice_id': invoice})
    assert sent['status'] == 'approval_required' and sent['invoice_id'] == invoice
    bill = snap['bills'][0]['bill_id']
    deferred = run(ctx, 'defer_bill', {'bill_id': bill})
    assert deferred['status'] == 'approval_required' and deferred['bill_id'] == bill
    assert run(ctx, 'defer_bill', {'bill_id': 'bill-nope'}) == {'error': 'Unpaid bill not found in forecast window'}
    with conn() as c:
        rows = c.execute('select decision_id,node_id,payload,resolved from decisions where run_id=%s order by created_at',
                         (ctx.run_id,)).fetchall()
    assert [r['decision_id'] for r in rows] == [sent['decision_id'], deferred['decision_id']]
    assert [r['payload'] for r in rows] == [{'kind': 'send_message', 'invoice_id': invoice}, {'kind': 'defer_bill', 'bill_id': bill}]
    assert all(r['resolved'] is None for r in rows)
    created, _ = node_events(ctx)
    assert [r['node_id'] for r in rows] == [created[0]['node_id'], created[1]['node_id']]
    assert all(n['type'] == 'action' for n in created)


def test_resolve_decision_only_within_run(ctx):
    other = create(COMPANY, 'Other conversation', 'web', 'free_question')
    options = [{'id': 'yes', 'label': 'Approve'}, {'id': 'no', 'label': 'Not now'}]
    try:
        foreign = request_decision(other, 'n1', 'Approve?', options, {})
        assert run(ctx, 'resolve_decision', {'decision_id': foreign, 'option_id': 'no'}) == {
            'error': 'Decision does not belong to this conversation'}
        own = request_decision(ctx.run_id, 'context', 'Approve?', options, {})
        assert run(ctx, 'resolve_decision', {'decision_id': own, 'option_id': 'no'}) == {'decision_id': own, 'resolved': 'no'}
    finally:
        with conn() as c:
            c.execute('delete from decisions where run_id=%s', (other,))
            c.execute('delete from events where run_id=%s', (other,))
            c.execute('delete from runs where run_id=%s', (other,))


def test_show_node_unknown_tool_and_parent_chain(ctx):
    assert run(ctx, 'show_node', {'title': 't', 'text': 'x' * 5000}) == {'text': 'x' * 4000}
    assert run(ctx, 'drop_tables') == {'error': 'Unknown tool'}
    created, updated = node_events(ctx)
    assert [n['parent'] for n in created] == ['context', created[0]['node_id']]
    assert all(n['node_id'].startswith('tool-') for n in created)
    assert [u['status'] for u in updated] == ['done', 'failed']
    assert ctx.parent == created[-1]['node_id']
