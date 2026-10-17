"""No-key follow-up branches with explicit, company-scoped ancestry."""
import asyncio
import logging
import re
from datetime import timedelta

from fastapi import HTTPException

from owed.config import settings
from owed.db import conn
from owed.events import emit
from owed.finance import queries as q
from owed.finance.model import band
from owed.runs import finish


def parent_run(run_id, company):
    with conn() as c:
        row = c.execute('select * from runs where run_id=%s and company_id=%s', (run_id, company)).fetchone()
    if not row:
        raise HTTPException(404, 'Parent run not found in this company')
    return row


def parent_node(run_id, kind):
    with conn() as c:
        row = c.execute("select data from events where run_id=%s and event='node.create' and data->>'type'=%s order by id limit 1", (run_id, kind)).fetchone()
    return row['data'] if row else None


def branch_customer(company, question):
    text = question.casefold().replace('’', "'")
    fragment = re.sub(r"^.*?what if\s+|\s+(doesn't pay|does not pay|never pays|won't pay).*$", '', text).strip(' ?.,')
    with conn() as c:
        rows = c.execute('select id,display_name from customers where company_id=%s', (company,)).fetchall()
    exact = [r for r in rows if r['display_name'].casefold() == fragment]
    if len(exact) == 1:
        return exact[0]
    # The product's documented demo shorthand (docs/frontend/brief.md).
    if company == settings.demo_company and fragment == 'evergreen':
        exact = [r for r in rows if r['display_name'] == 'Evergreen Juniper Flats Removals']
        if exact:
            return exact[0]
    matches = [r for r in rows if fragment and fragment in r['display_name'].casefold()]
    if len(matches) != 1:
        raise HTTPException(422, 'Name one customer unambiguously using their full name')
    return matches[0]


async def show_late(run_id, company, target, parent_run_id=None):
    from owed.runs.payroll import snapshot
    node = 'late-scoring'
    try:
        snap = await asyncio.to_thread(snapshot, company, target)
        rows = sorted((r for r in snap['scored'] if r['days_past_due'] > 0),
                      key=lambda r: (-r['days_past_due'], -q.f(r['open_balance']), r['invoice_id']))
        reference = parent_node(parent_run_id, 'scoring') if parent_run_id else None
        data = {'node_id': node, 'type': 'scoring', 'title': 'Overdue invoices, most days late first',
                'status': 'running', 'parent': reference['node_id'] if reference else None,
                'data': {'sort': 'days_past_due_desc', 'overdue_only': True}}
        if reference:
            data['parent_run_id'] = parent_run_id
            data['data']['reused_from'] = {'run_id': parent_run_id, 'node_id': reference['node_id']}
        await asyncio.to_thread(emit, run_id, 'node.create', data)
        for i, row in enumerate(rows, 1):
            await asyncio.to_thread(emit, run_id, 'node.update', {'node_id': node,
                'progress': {'done': i, 'total': len(rows)}, 'row': {
                    'invoice_id': row['invoice_id'], 'customer': row['customer_name'], 'amount': q.f(row['open_balance']),
                    'days_past_due': row['days_past_due'], 'p_paid_by_target': row['p_paid_by_target'],
                    'expected_pay_date': (q.AS_OF_DEFAULT + timedelta(days=max(1, row['expected_days_to_pay']))).isoformat(),
                    'p_never': row['p_never'], 'band': band(row['p_paid_by_target'], row['p_never']), 'source': 'owed_model'}})
        await asyncio.to_thread(emit, run_id, 'node.update', {'node_id': node, 'status': 'done'})
        await asyncio.to_thread(emit, run_id, 'speech', {'text': f'{len(rows)} overdue invoices, ordered most late first.', 'audio_url': None})
    except Exception:
        logging.getLogger(__name__).exception('Late-invoice branch failed')
        await asyncio.to_thread(emit, run_id, 'node.update', {'node_id': node, 'status': 'failed'})
    finally:
        await asyncio.to_thread(finish, run_id, 'closed')
