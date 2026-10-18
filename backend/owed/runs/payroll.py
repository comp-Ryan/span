"""Deterministic payroll workflow grounded in the books and trained model."""
import asyncio
import logging
from datetime import date, timedelta
from functools import lru_cache
from typing import Literal
from uuid import uuid4

import sentry_sdk
from fastapi import APIRouter, BackgroundTasks, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from owed.config import settings
from owed.db import conn
from owed.events import emit
from owed.finance import queries as q
from owed.finance.model import band, load
from owed.finance.scenarios import answer_title, pessimistic_forecast
from owed.runs import create, finish

router = APIRouter()
log = logging.getLogger(__name__)

class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    source: Literal['web', 'call', 'sms', 'asi_one'] = 'web'
    parent_run_id: str | None = Field(None, max_length=100)

@lru_cache(maxsize=1)
def payment_model():
    return load()

def target_for(question: str) -> date:
    if 'two weeks' in question.lower() or '2 weeks' in question.lower():
        return q.AS_OF_DEFAULT + timedelta(days=14)
    return q.AS_OF_DEFAULT + timedelta(days=(4 - q.AS_OF_DEFAULT.weekday()) % 7 or 7)


def planner_for_call(source: str, intent: str, gemini_configured: bool) -> bool:
    """Use the conversational planner for configured voice payroll questions only."""
    return source == 'call' and intent == 'payroll_check' and gemini_configured

@sentry_sdk.trace(op="finance.snapshot")
def snapshot(company: str, target: date, excluded_customer_id=None, assumed_customer_id=None):
    with conn() as c:
        company_row = q.company(c, company)
        bank = q.bank_balance(c, company, q.AS_OF_DEFAULT)
        payroll = q.payroll_due(c, company, q.AS_OF_DEFAULT, target)
        bills = [r for r in q.bills_due(c, company, q.AS_OF_DEFAULT, target) if q.f(r['open_amount']) > 0]
        invoices = q.open_invoices(c, company, q.AS_OF_DEFAULT)
        payments = c.execute('select invoice_id,sum(amount) amount from payments where company_id=%s group by invoice_id',(company,)).fetchall()
        paid = {r['invoice_id']: q.f(r['amount']) for r in payments}
        bank = round(bank + sum(paid.values()), 2)
        invoices = [{**r, 'open_balance': max(0, q.f(r['open_balance'])-paid.get(r['invoice_id'],0))} for r in invoices]
        invoices = [r for r in invoices if r['open_balance'] > 0 and r['customer_id'] != excluded_customer_id]
        deferrals = {r['bill_id']: r['due_date'] for r in c.execute('select bill_id,due_date from bill_deferrals where company_id=%s',(company,)).fetchall()}
        bills = [{**b, 'due_date': deferrals.get(b['bill_id'], b['due_date'])} for b in bills
                 if deferrals.get(b['bill_id'], b['due_date']) <= target]
        draw = q.owner_draw(c,company,q.AS_OF_DEFAULT)
        held = c.execute('select amount from draw_holds where company_id=%s',(company,)).fetchone()
        draw_due = 0 if held else draw

    scored = payment_model().score_open(invoices, (target - q.AS_OF_DEFAULT).days)
    if assumed_customer_id:
        horizon = (target - q.AS_OF_DEFAULT).days
        scored = [{**r, 'p_paid_by_target': 1.0, 'p_never': 0.0,
                   'expected_days_to_pay': min(r['expected_days_to_pay'], horizon),
                   'band': band(1.0, 0.0)} if r['customer_id'] == assumed_customer_id else r for r in scored]
    expected = round(sum(q.f(r['open_balance']) * r['p_paid_by_target'] for r in scored), 2)
    bills_total = round(sum(q.f(b['open_amount']) for b in bills), 2)
    cash = round(bank + expected - bills_total - draw_due, 2)
    forecast = {'bank_balance': bank, 'as_of': q.AS_OF_DEFAULT.isoformat(), 'target_date': target.isoformat(),
                'owed_total': round(sum(q.f(r['open_balance']) for r in scored), 2),
                'expected_by_target': expected, 'bills_due_by_target': bills_total,
                'cash_at_target': cash, 'need': payroll['due_by_target'],
                'gap': round(max(0, payroll['due_by_target'] - cash), 2)}
    conservative_in = round(sum(q.f(r['open_balance'])*r['p_paid_by_target'] for r in scored if band(r['p_paid_by_target'],r['p_never'])=='green'),2)
    conservative_cash = round(bank+conservative_in-bills_total-draw_due,2)
    forecast['conservative'] = {'assumption': 'No amber or red invoice pays by target; green invoices remain probability-weighted.',
        'cash_at_target': conservative_cash, 'gap': round(max(0,payroll['due_by_target']-conservative_cash),2)}
    forecast['pessimistic'] = pessimistic_forecast(scored, bank, bills_total, draw_due, payroll['due_by_target'])
    forecast['owner_draw_by_target'] = draw_due
    if excluded_customer_id:
        forecast['excluded_customer_id'] = excluded_customer_id
    if assumed_customer_id:
        forecast['assumed_customer_id'] = assumed_customer_id
    return {'draw':draw_due,'company': company_row, 'bank': bank, 'payroll': payroll, 'bills': bills,
            'scored': scored, 'forecast': forecast}

def levers_for(snap):
    candidates = sorted((r for r in snap['scored'] if r['days_past_due'] > 0 and r['n_paid'] > 0),
                        key=lambda r: q.f(r['open_balance']) * (1-r['p_never']), reverse=True)
    targets, seen = [], set()
    for r in candidates:
        if r['customer_id'] in seen:
            continue
        seen.add(r['customer_id'])
        targets.append({'invoice_id': r['invoice_id'], 'customer_id': r['customer_id'], 'customer': r['customer_name'],
                        'amount': q.f(r['open_balance']),
                        'reason': f"{r['days_past_due']} days overdue; {r['n_paid']} paid invoices in history, average {q.f(r['avg_late']):.0f} days late."})
        if len(targets) == 3:
            break
    levers = []
    if targets:
        levers.append({'id': 'chase', 'label': f'Text {len(targets)} reliable late payers',
                       'recovers': round(sum(t['amount'] for t in targets), 2), 'targets': targets})
    tolerant = [b for b in snap['bills'] if q.f(b['hist_days_vs_due']) >= 7]
    if tolerant:
        bill = max(tolerant, key=lambda b: q.f(b['open_amount']))
        levers.append({'id': 'defer_bill', 'label': f"Request an 8-day deferral from {bill['vendor_name']}",
                       'recovers': q.f(bill['open_amount']), 'bill_id': bill['bill_id'], 'vendor_tolerance': 'high'})
    if snap.get('draw',0)>0:
        levers.append({'id':'hold_draw','label':'Hold estimated owner draw','recovers':snap['draw']})
    return levers

async def run_payroll(run_id: str, company: str, target: date, parent_run_id=None, excluded_customer=None):
    current = 'n1'
    async def event(name, data):
        return await asyncio.to_thread(emit, run_id, name, data)
    try:
        from owed.runs.branches import parent_node
        reused = parent_node(parent_run_id, 'context') if parent_run_id else None
        root = {'node_id': 'n1', 'type': 'context', 'title': 'Pulling up context', 'status': 'running', 'parent': None}
        if reused:
            root.update(parent=reused['node_id'], parent_run_id=parent_run_id, data={'reused_from': {'run_id': parent_run_id, 'node_id': reused['node_id']}})
        await event('node.create', root)
        snap = await asyncio.to_thread(snapshot, company, target, excluded_customer['id'] if excluded_customer else None)
        await event('node.update', {'node_id': 'n1', 'status': 'done', 'data': {
            'company': snap['company']['display_name'], 'payroll_date': target.isoformat(),
            'payroll_amount': snap['payroll']['due_by_target'], 'bank_balance': snap['bank'],
            'target_date': target.isoformat(), 'as_of': q.AS_OF_DEFAULT.isoformat(),
            'headcount': snap['payroll']['headcount'], 'bills_due_by_target': snap['forecast']['bills_due_by_target']}})
        current = 'n2'
        await event('node.create', {'node_id': 'n2', 'type': 'scoring', 'title': f"Scoring {len(snap['scored'])} open invoices", 'status': 'running', 'parent': 'n1'})
        for i, row in enumerate(snap['scored'], 1):
            await event('node.update', {'node_id': 'n2', 'progress': {'done': i, 'total': len(snap['scored'])}, 'row': {
                'invoice_id': row['invoice_id'], 'customer': row['customer_name'], 'amount': q.f(row['open_balance']),
                'days_past_due': row['days_past_due'], 'p_paid_by_target': row['p_paid_by_target'],
                'expected_pay_date': (q.AS_OF_DEFAULT + timedelta(days=max(1, row['expected_days_to_pay']))).isoformat(),
                'p_never': row['p_never'], 'band': band(row['p_paid_by_target'], row['p_never']), 'source': 'owed_model'}})
            await asyncio.sleep(settings.scoring_interval_ms / 1000)
        await event('node.update', {'node_id': 'n2', 'status': 'done'})
        current = 'n3'
        await event('node.create', {'node_id': 'n3', 'type': 'forecast', 'title': f"Forecasting without {excluded_customer['display_name']}" if excluded_customer else f'Forecasting {target.isoformat()}', 'status': 'running', 'parent': 'n2'})
        await event('node.update', {'node_id': 'n3', 'status': 'done', 'data': snap['forecast']})
        gap = snap['forecast']['gap']
        title = answer_title(snap['forecast'])
        if excluded_customer:
            title = f"Without {excluded_customer['display_name']}: {title}"
        spoken = f"{title} This estimate uses payment history and bills due by {target.isoformat()}."
        await event('node.create', {'node_id': 'n4', 'type': 'answer', 'title': title, 'status': 'done', 'parent': 'n3',
                                   'data': {'answer': 'no' if gap else 'yes', 'gap': gap, 'spoken': spoken}})
        with conn() as c:
            c.execute('update runs set answer_title=%s where run_id=%s', (title, run_id))
        await event('speech', {'text': spoken, 'audio_url': None})
        current = 'n5'
        await event('node.create', {'node_id': 'n5', 'type': 'levers', 'title': 'What closes the gap', 'status': 'running', 'parent': 'n4'})
        levers = levers_for(snap)
        ask = 'Want me to text these customers? Collection amounts are potential, not guaranteed.' if levers else 'No supported collection or bill deferral levers were found.'
        await event('node.update', {'node_id': 'n5', 'status': 'done', 'data': {'levers': levers, 'recommended': [l['id'] for l in levers], 'ask_spoken': ask}})
        if levers:
            decision_id = 'd-' + uuid4().hex
            options = [{'id': 'yes', 'label': 'Yes, text them'}, {'id': 'chase_only', 'label': "Text, don't touch bills"}, {'id': 'no', 'label': 'Not now'}]
            with conn() as c:
                c.execute('insert into decisions(decision_id,run_id,node_id,prompt,options) values (%s,%s,%s,%s,%s)',
                          (decision_id, run_id, 'n5', 'Text them?', Jsonb(options)))
            await event('decision', {'decision_id': decision_id, 'node_id': 'n5', 'prompt': 'Text them?', 'options': options, 'auto_resolves_in_s': None})
        await asyncio.to_thread(finish, run_id, 'open' if levers else 'closed')
    except Exception:
        log.exception('Payroll run failed: %s', run_id)
        await event('node.update', {'node_id': current, 'status': 'failed', 'data': {'error': 'Could not complete this step. Please retry.'}})
        await asyncio.to_thread(finish, run_id, 'closed')

@router.post('/ask')
def ask(body: Ask, tasks: BackgroundTasks, company: str = settings.demo_company):
    if not body.question.strip():
        raise HTTPException(422, 'Question must not be blank')
    from owed.planner import route_intent, run_planner
    from owed.runs.branches import branch_customer, parent_run, show_late
    parent = parent_run(body.parent_run_id, company) if body.parent_run_id else None
    target = (parent.get('target_date') or target_for(parent['question'])) if parent else target_for(body.question)
    # An explicit horizon on a follow-up overrides inherited context.
    if any(word in body.question.lower() for word in ('friday', 'two weeks', '2 weeks')):
        target = target_for(body.question)
    intent = route_intent(body.question)
    customer = branch_customer(company, body.question) if intent == 'what_if_customer' else None
    run_id = create(company, body.question, body.source, intent, body.parent_run_id, target,
                    customer['id'] if customer else None)
    parent_context = None
    if parent:
        with conn() as c:
            prior = c.execute('''select data from events where run_id=%s and event='speech'
                                 and coalesce(data->>'speaker','') <> 'caller'
                                 and coalesce(data->>'kind','') <> 'caller'
                                 order by id desc limit 1''', (body.parent_run_id,)).fetchone()
        parent_context = {
            'parent_question': parent['question'],
            'parent_speech': (prior['data'].get('text') if prior else None),
        }
    if intent == 'payroll_check' and planner_for_call(body.source, intent, bool(settings.gemini_api_key)):
        tasks.add_task(run_planner, run_id, company, body.question, target, parent_context=parent_context)
    elif intent in ('payroll_check', 'what_if_customer'):
        tasks.add_task(run_payroll, run_id, company, target, body.parent_run_id, customer)
    elif intent == 'show_late':
        tasks.add_task(show_late, run_id, company, target, body.parent_run_id)
    else:
        tasks.add_task(run_planner, run_id, company, body.question, target, parent_context=parent_context)
    return {'run_id': run_id, 'intent': intent, 'target_date': target.isoformat()}
