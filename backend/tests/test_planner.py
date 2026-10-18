import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

from google.genai import types

from owed.db import conn
from owed.planner import ToolContext, route_intent, run_planner
from owed.runs import create, replay_run


def test_tool_loop_executes_and_preserves_events():
    rid = create('company-020', 'Who should I chase?', 'web', 'chase_today')
    tool = types.Content(role='model', parts=[types.Part(function_call=types.FunctionCall(name='rank_chase', args={}))])
    answer = types.Content(role='model', parts=[types.Part(text='Review these three overdue invoices before sending.')])
    generate = AsyncMock(side_effect=[SimpleNamespace(candidates=[SimpleNamespace(content=c)]) for c in [tool, answer]])
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    try:
        asyncio.run(run_planner(rid, 'company-020', 'Who should I chase?', date(2026,10,9), client))
        events = replay_run(rid)['events']
        assert any(e['event']=='node.update' and 'levers' in e['data'].get('data', {}) for e in events)
        assert events[-1]['event']=='run.end'
        assert generate.await_count == 2
        ctx = ToolContext(rid, 'company-020', date(2026,10,9))
        result = asyncio.run(ctx.execute('predict_payment', {'invoice_id': 'not-an-invoice'}))
        assert 'error' in result
        result = asyncio.run(ctx.execute('query_books', {'entity': 'drop table invoices'}))
        assert 'error' in result
    finally:
        with conn() as c:
            c.execute('delete from events where run_id=%s', (rid,))
            c.execute('delete from runs where run_id=%s', (rid,))


def test_intent_routes():
    assert route_intent('Can I make payroll Friday?') == 'payroll_check'
    assert route_intent('Should I take this order?') == 'order_check'
    assert route_intent('Who should I chase?') == 'chase_today'
    assert route_intent('Can I afford to hire?') == 'afford_check'
    assert route_intent("How is this customer doing?") == 'client_status'
    assert route_intent('Explain my books') == 'free_question'


def test_verdict_of():
    from owed.planner import verdict_of
    assert verdict_of('Yes, you make payroll with about $4,200 to spare.') == {'verdict': 'yes', 'number': 4200.0}
    assert verdict_of('No. You are $1,156 short on the twentieth.') == {'verdict': 'no', 'number': 1156.0}
    assert verdict_of('You cannot afford it; projected cash is $4,355.') == {'verdict': 'no', 'number': 4355.0}
    assert verdict_of('You can afford it, $2k to spare.') == {'verdict': 'yes', 'number': 2000.0}
    assert verdict_of('Barely. $300 to spare.')['verdict'] == 'barely'
    assert verdict_of('Evergreen owes $12.5k across three invoices.') == {'number': 12500.0}
    assert verdict_of('Chase Gallagher first.') == {}


def test_tool_nodes_carry_tool_and_payroll_shapes():
    rid = create('company-020', 'How is my cash?', 'web', 'free_question')
    try:
        ctx = ToolContext(rid, 'company-020', date(2026, 10, 9))
        fc = asyncio.run(ctx.execute('forecast_cash', {}))
        assert {'bank_balance', 'payroll_due_by_target', 'bills_due_by_target', 'cash_at_target', 'target_date'} <= set(fc)
        books = asyncio.run(ctx.execute('query_books', {'entity': 'invoices'}))
        assert books['rows'] and {'invoice_id', 'customer', 'amount', 'band', 'p_paid_by_target'} <= set(books['rows'][0])
        cust = asyncio.run(ctx.execute('score_customer', {'customer_id': books['rows'][0]['customer_id']}))
        assert 'summary' in cust and 'history' in cust and cust['rows']
        events = replay_run(rid)['events']
        creates = [e['data'] for e in events if e['event'] == 'node.create' and e['data']['node_id'].startswith('tool-')]
        assert [c['data']['tool'] for c in creates] == ['forecast_cash', 'query_books', 'score_customer']
        assert [c['type'] for c in creates] == ['forecast', 'context', 'scoring']
        assert creates[1]['title'] == 'Reading invoices'
    finally:
        with conn() as c:
            c.execute('delete from events where run_id=%s', (rid,))
            c.execute('delete from runs where run_id=%s', (rid,))
