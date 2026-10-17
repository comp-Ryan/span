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
