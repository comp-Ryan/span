"""Read-only, company-scoped data for the Get paid, Reports and Customers pages."""
import json
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder

from owed.config import settings
from owed.db import conn
from owed.finance import queries as q
from owed.finance.model import band
from owed.runs import require_company
from owed.runs.payroll import snapshot

router = APIRouter()

LIMIT = 200
RELIABILITY_HORIZON = timedelta(days=14)


def _receipt(raw) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _reference(rail, receipt) -> str | None:
    r = _receipt(receipt)
    if rail == 'solana':
        return r.get('signature')
    return r.get('transaction_identifier') or r.get('approval_code')


@router.get('/payments')
def payments(company: str = settings.demo_company):
    require_company(company)
    with conn() as c:
        links = c.execute('''
            select t.pay_token, t.invoice_id, i.doc_number, coalesce(f.customer_id, i.customer_id) customer_id,
                   coalesce(cu.display_name, i.customer_name) customer_name, t.amount, t.status, t.created_at, t.run_id
              from pay_tokens t
              left join invoices i on i.company_id=t.company_id and i.id=t.invoice_id
              left join invoice_facts f on f.company_id=t.company_id and f.invoice_id=t.invoice_id
              left join customers cu on cu.company_id=t.company_id and cu.id=coalesce(f.customer_id, i.customer_id)
             where t.company_id=%s
             order by t.created_at desc nulls last, t.pay_token limit %s''', (company, LIMIT)).fetchall()
        paid = c.execute('''
            select p.payment_id, p.invoice_id, coalesce(cu.display_name, i.customer_name) customer_name,
                   p.amount, p.rail, p.receipt, p.paid_at, t.run_id
              from payments p
              left join pay_tokens t on t.pay_token=p.pay_token
              left join invoices i on i.company_id=p.company_id and i.id=p.invoice_id
              left join invoice_facts f on f.company_id=p.company_id and f.invoice_id=p.invoice_id
              left join customers cu on cu.company_id=p.company_id and cu.id=coalesce(f.customer_id, i.customer_id)
             where p.company_id=%s
             order by p.paid_at desc nulls last, p.payment_id limit %s''', (company, LIMIT)).fetchall()
        totals = c.execute('''
            select count(*) links, count(*) filter (where coalesce(status,'unpaid')<>'paid') unpaid,
                   coalesce(sum(amount) filter (where status='paid'),0) collected,
                   coalesce(sum(amount) filter (where coalesce(status,'unpaid')<>'paid'),0) outstanding
              from pay_tokens where company_id=%s''', (company,)).fetchone()
    return jsonable_encoder({
        'pay_links': [{**{k: r[k] for k in ('pay_token', 'invoice_id', 'doc_number', 'customer_id', 'customer_name',
                                            'status', 'created_at', 'run_id')},
                       'amount': q.f(r['amount']), 'pay_url': '/pay/' + r['pay_token']} for r in links],
        'payments': [{'payment_id': r['payment_id'], 'invoice_id': r['invoice_id'], 'customer_name': r['customer_name'],
                      'amount': q.f(r['amount']), 'rail': r['rail'], 'reference': _reference(r['rail'], r['receipt']),
                      'paid_at': r['paid_at'], 'run_id': r['run_id']} for r in paid],
        'totals': {'links': int(totals['links']), 'unpaid': int(totals['unpaid']),
                   'collected': round(q.f(totals['collected']), 2), 'outstanding': round(q.f(totals['outstanding']), 2)}})


@router.get('/reports')
def reports(company: str = settings.demo_company):
    require_company(company)
    with conn() as c:
        done = c.execute('''
            select g.report_id, g.run_id, r.question, coalesce(nullif(g.doc->>'answer',''), r.answer_title) answer, g.generated_at
              from generated_reports g left join runs r on r.run_id=g.run_id
             where g.company_id=%s order by g.generated_at desc nulls last, g.report_id limit %s''',
            (company, LIMIT)).fetchall()
        pending = c.execute('''
            select run_id, question, answer_title, started_at from runs
             where company_id=%s and status='closed' and answer_title is not null and report_id is null
             order by started_at desc nulls last, run_id limit %s''', (company, LIMIT)).fetchall()
    return jsonable_encoder({
        'reports': [{**dict(r), 'pdf_url': f"/reports/{r['report_id']}.pdf?company={company}"} for r in done],
        'unreported': [dict(r) for r in pending]})


# Same population as q.open_invoices / snapshot(): open or partial, issued by as_of, net of runtime payments.
CUSTOMER_STATS_SQL = '''
with paid as (select invoice_id, sum(amount) amount from payments where company_id=%(cid)s group by invoice_id),
open_inv as (
  select f.customer_id, f.due_date, greatest(0, f.open_balance - coalesce(p.amount,0)) bal
    from invoice_facts f left join paid p on p.invoice_id=f.invoice_id
   where f.company_id=%(cid)s and f.status in ('open','partial') and f.open_balance>0 and f.txn_date<=%(as_of)s),
o as (select customer_id, sum(bal) open_balance, sum(bal) filter (where due_date<%(as_of)s) overdue_balance,
             count(*) filter (where bal>0) open_invoices
        from open_inv group by customer_id),
h as (select customer_id, avg(days_late) filter (where status='paid') avg_days_late,
             count(*) filter (where status='paid') paid_invoices,
             coalesce(sum(written_off) filter (where status='written_off'),0) written_off
        from invoice_facts where company_id=%(cid)s group by customer_id)
select cu.id, cu.display_name, cu.payment_terms, cu.payment_terms_days,
       coalesce(o.open_balance,0) open_balance, coalesce(o.overdue_balance,0) overdue_balance,
       coalesce(o.open_invoices,0) open_invoices, h.avg_days_late,
       coalesce(h.paid_invoices,0) paid_invoices, coalesce(h.written_off,0) written_off
  from customers cu left join o on o.customer_id=cu.id left join h on h.customer_id=cu.id
 where cu.company_id=%(cid)s {extra}
'''


def _reliability(scored: list[dict]) -> dict:
    """Amount-weighted band per customer from one snapshot's open-invoice scores."""
    acc = {}
    for r in scored:
        w = q.f(r['open_balance'])
        if w <= 0:
            continue
        a = acc.setdefault(r['customer_id'], [0.0, 0.0, 0.0])
        a[0] += w
        a[1] += w * r['p_paid_by_target']
        a[2] += w * r['p_never']
    return {cid: band(paid / w, never / w) for cid, (w, paid, never) in acc.items()}


def _customer(r, reliability, detail=False) -> dict:
    out = {'id': r['id'], 'display_name': r['display_name'],
           'open_balance': round(q.f(r['open_balance']), 2), 'overdue_balance': round(q.f(r['overdue_balance']), 2),
           'open_invoices': int(r['open_invoices']),
           'avg_days_late': round(q.f(r['avg_days_late']), 1) if r['avg_days_late'] is not None else None,
           'paid_invoices': int(r['paid_invoices']), 'written_off': round(q.f(r['written_off']), 2),
           'reliability': reliability.get(r['id'])}
    if detail:
        out['payment_terms'] = r['payment_terms'] or (f"Net {r['payment_terms_days']}" if r['payment_terms_days'] else None)
        out['payment_terms_days'] = r['payment_terms_days']
    return out


@router.get('/customers')
def customers(company: str = settings.demo_company):
    require_company(company)
    with conn() as c:
        rows = c.execute(CUSTOMER_STATS_SQL.format(extra='') +
                         ' order by open_balance desc, overdue_balance desc, cu.display_name',
                         {'cid': company, 'as_of': q.AS_OF_DEFAULT}).fetchall()
    reliability = _reliability(snapshot(company, q.AS_OF_DEFAULT + RELIABILITY_HORIZON)['scored'])
    return {'customers': [_customer(r, reliability) for r in rows]}


HEATMAP_MONTHS = 12
HEATMAP_CAP = 60
# Worst-first: a month's status is the most severe outcome among its invoices.
HEATMAP_ORDER = ('written_off', 'overdue', 'very_late', 'paid_late', 'unpaid', 'paid_on_time')

# Same invoice source as q.customer_history (invoice_facts), netted against runtime payments
# exactly like CUSTOMER_STATS_SQL's open balance.
HEATMAP_SQL = '''
with paid as (select invoice_id, sum(amount) amount from payments where company_id=%(cid)s group by invoice_id)
select f.customer_id, f.due_date, f.total_amount, f.days_late, f.status,
       case when f.status in ('open','partial') and f.open_balance>0
            then greatest(0, f.open_balance - coalesce(p.amount,0)) else 0 end bal
  from invoice_facts f left join paid p on p.invoice_id=f.invoice_id
 where f.company_id=%(cid)s and f.txn_date<=%(as_of)s and f.due_date>=%(start)s and f.due_date<%(end)s
'''


def _heatmap_months(as_of) -> list[str]:
    y, m = as_of.year, as_of.month
    out = []
    for _ in range(HEATMAP_MONTHS):
        out.append(f'{y:04d}-{m:02d}')
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def _outcome(r, as_of) -> str:
    if r['status'] == 'written_off':
        return 'written_off'
    if q.f(r['bal']) > 0:
        return 'overdue' if r['due_date'] < as_of else 'unpaid'
    if r['status'] == 'paid':
        late = r['days_late'] or 0
    else:  # open/partial settled by runtime payments: count it as paid at the dataset clock
        late = (as_of - r['due_date']).days
    return 'paid_on_time' if late <= 0 else 'paid_late' if late <= 30 else 'very_late'


@router.get('/customers/heatmap')
def customers_heatmap(company: str = settings.demo_company):
    require_company(company)
    as_of = q.AS_OF_DEFAULT
    months = _heatmap_months(as_of)
    sy, sm = map(int, months[0].split('-'))
    ey, em = (as_of.year, as_of.month + 1) if as_of.month < 12 else (as_of.year + 1, 1)
    with conn() as c:
        rows = c.execute(HEATMAP_SQL, {'cid': company, 'as_of': as_of, 'start': date(sy, sm, 1),
                                       'end': date(ey, em, 1)}).fetchall()
        stats = {r['id']: r for r in c.execute(CUSTOMER_STATS_SQL.format(extra=''), {'cid': company, 'as_of': as_of})}
    cells = {}
    for r in rows:
        if r['customer_id'] not in stats:
            continue
        key = r['due_date'].strftime('%Y-%m')
        cell = cells.setdefault(r['customer_id'], {}).setdefault(
            key, {'invoices': 0, 'amount': 0.0, **{k: 0 for k in HEATMAP_ORDER}})
        cell['invoices'] += 1
        cell['amount'] += q.f(r['total_amount'])
        cell[_outcome(r, as_of)] += 1
    out = []
    for cid, by_month in cells.items():
        s = stats[cid]
        row = []
        for m in months:
            cell = by_month.get(m) or {'invoices': 0, 'amount': 0.0, **{k: 0 for k in HEATMAP_ORDER}}
            status = next((k for k in HEATMAP_ORDER if cell[k]), 'none')
            row.append({'month': m, **cell, 'amount': round(cell['amount'], 2), 'status': status})
        out.append({'id': cid, 'display_name': s['display_name'],
                    'open_balance': round(q.f(s['open_balance']), 2), 'cells': row})
    out.sort(key=lambda r: (-r['open_balance'], r['display_name'] or '', r['id']))
    return {'months': months, 'customers': out[:HEATMAP_CAP]}


def _activity(c, company, customer_id) -> list[dict]:
    items = []
    for r in c.execute('''select reminder_id, run_id, invoice_id, channel, status, body, sent_at from reminders
                          where company_id=%s and customer_id=%s and sent_at is not null''', (company, customer_id)):
        items.append({'kind': 'reminder', 'at': r['sent_at'], 'run_id': r['run_id'],
                      'title': f"Reminder sent ({r['channel'] or 'unknown'}) for {r['invoice_id']}",
                      'detail': r['body']})
    # Replies are workflow events: attached under a reminder node for this customer, or tagged with its id.
    for r in c.execute('''
            select distinct on (e.id) e.id, e.ts, e.run_id, e.data from events e
              left join reminders m on m.run_id=e.run_id and m.node_id=e.data->>'parent'
                   and m.company_id=%(cid)s and m.customer_id=%(cu)s
             where e.company_id=%(cid)s and e.event='node.create' and e.data->'data'->>'kind'='reply'
               and (m.reminder_id is not null or e.data->'data'->>'customer_id'=%(cu)s)''',
            {'cid': company, 'cu': customer_id}):
        data = r['data'].get('data') or {}
        items.append({'kind': 'reply', 'at': r['ts'], 'run_id': r['run_id'],
                      'title': r['data'].get('title') or 'Customer replied',
                      'detail': data.get('text')})
    for r in c.execute('''select n.negotiation_id, n.run_id, n.invoice_id, n.status, n.agreement, n.created_at
                            from negotiations n join invoice_facts f on f.company_id=n.company_id and f.invoice_id=n.invoice_id
                           where n.company_id=%s and f.customer_id=%s''', (company, customer_id)):
        items.append({'kind': 'negotiation', 'at': r['created_at'], 'run_id': r['run_id'],
                      'title': f"Negotiation {r['status'] or 'started'} on {r['invoice_id']}",
                      'detail': json.dumps(jsonable_encoder(r['agreement'])) if r['agreement'] else None})
    for r in c.execute('''select p.payment_id, p.invoice_id, p.amount, p.rail, p.receipt, p.paid_at, t.run_id
                            from payments p join invoice_facts f on f.company_id=p.company_id and f.invoice_id=p.invoice_id
                            left join pay_tokens t on t.pay_token=p.pay_token
                           where p.company_id=%s and f.customer_id=%s''', (company, customer_id)):
        ref = _reference(r['rail'], r['receipt'])
        items.append({'kind': 'payment', 'at': r['paid_at'], 'run_id': r['run_id'],
                      'title': f"Paid ${q.f(r['amount']):,.2f} on {r['invoice_id']} via {r['rail']}",
                      'detail': ref})
    items = [i for i in items if i['at'] is not None]
    items.sort(key=lambda i: i['at'], reverse=True)
    return items[:LIMIT]


@router.get('/customers/{customer_id}')
def customer(customer_id: str, company: str = settings.demo_company):
    require_company(company)
    with conn() as c:
        row = c.execute(CUSTOMER_STATS_SQL.format(extra='and cu.id=%(cu)s'),
                        {'cid': company, 'as_of': q.AS_OF_DEFAULT, 'cu': customer_id}).fetchone()
        if not row:
            raise HTTPException(404, 'Customer not found')
        history = q.customer_history(c, company, customer_id, q.AS_OF_DEFAULT)
        activity = _activity(c, company, customer_id)
        docs = {r['id']: r['doc_number'] for r in c.execute(
            'select id, doc_number from invoices where company_id=%s and customer_id=%s', (company, customer_id))}
    scored = snapshot(company, q.AS_OF_DEFAULT + RELIABILITY_HORIZON)['scored']
    mine = sorted((r for r in scored if r['customer_id'] == customer_id), key=lambda r: q.f(r['open_balance']), reverse=True)
    invoices = [{'invoice_id': r['invoice_id'], 'doc_number': docs.get(r['invoice_id']),
                 'open_balance': round(q.f(r['open_balance']), 2), 'due_date': r['due_date'],
                 'days_past_due': int(r['days_past_due']), 'p_paid_by_target': r['p_paid_by_target'],
                 'p_never': r['p_never'], 'band': band(r['p_paid_by_target'], r['p_never'])} for r in mine]
    return jsonable_encoder({'customer': _customer(row, _reliability(mine), detail=True),
                             'target_date': (q.AS_OF_DEFAULT + RELIABILITY_HORIZON).isoformat(),
                             'history': [{**dict(h), 'amount': q.f(h['amount'])} for h in history],
                             'invoices': invoices, 'activity': activity})
