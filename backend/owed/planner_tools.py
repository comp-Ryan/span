"""Focused, read-only, company-scoped answer tools for the planner.

Each function takes an open connection and/or a payroll snapshot so it can be unit-tested
without a database. Nothing here writes; approvals stay in owed.planner.ToolContext.
"""
import re
from datetime import date, timedelta

import numpy as np

from owed.finance import queries as q

AS_OF = q.AS_OF_DEFAULT
MAX_HORIZON = timedelta(days=366)
STOPWORDS = {'the', 'co', 'inc', 'llc', 'company', 'and', 'group', 'ltd', 'corp'}
RANKINGS = ('worst', 'slowest', 'most_overdue', 'largest_balance', 'most_reliable')


def parse_date(raw, default, field='date'):
    """Optional ISO date inside the dataset window; default when absent."""
    if raw in (None, ''):
        return default
    if not isinstance(raw, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', raw):
        raise ValueError(f'{field} must use YYYY-MM-DD')
    try:
        value = date.fromisoformat(raw)
    except ValueError:
        raise ValueError(f'{field} must use YYYY-MM-DD') from None
    if not AS_OF <= value <= AS_OF + MAX_HORIZON:
        raise ValueError(f'{field} must be between the dataset date {AS_OF.isoformat()} and 366 days later')
    return value


def parse_amount(raw, field='amount', allow_zero=False):
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f'{field} must be a dollar amount') from None
    if value != value or value < 0 or (value == 0 and not allow_zero) or value > 10_000_000:
        raise ValueError(f'{field} must be a positive dollar amount')
    return round(value, 2)


def _norm(text):
    return re.sub(r'[^a-z0-9 ]+', ' ', str(text).casefold().replace('&', ' and ')).split()


def _stem(token):
    for suffix in ('ies', 'es', 's', 'y'):
        if len(token) > 4 and token.endswith(suffix):
            return token[:-len(suffix)]
    return token


def name_matches(query, name):
    """Every meaningful query token appears (prefix/stem-insensitive) in the name."""
    wanted = [_stem(t) for t in _norm(query) if t not in STOPWORDS]
    have = _norm(name)
    return bool(wanted) and all(any(h.startswith(w) or _stem(h) == w for h in have) for w in wanted)


# ---------- daily cash ----------

def _weekly(days):
    out = []
    for i in range(0, len(days), 7):
        chunk = days[i:i + 7]
        out.append({'week_ending': chunk[-1]['date'], 'low': round(min(d['balance'] for d in chunk), 2),
                    'ending': round(chunk[-1]['balance'], 2),
                    'inflow': round(sum(d['inflow'] for d in chunk), 2),
                    'outflow': round(sum(d['outflow'] for d in chunk), 2)})
    return out


def _low(days):
    low = min(days, key=lambda d: d['balance'])
    return {'date': low['date'], 'balance': round(low['balance'], 2)}


def _first_negative(days):
    return next((d['date'] for d in days if d['balance'] < 0), None)


def _bills_known_through(snap):
    dates = [b['due_date'] for b in snap['bills']]
    return max(dates).isoformat() if dates else None


TRAILING_SQL = """select kind, sum(amount) amount from bank_transactions
 where company_id=%s and txn_date > %s - 56 and txn_date <= %s group by kind"""


def trailing_weeks(c, company):
    """Actual bank movement over the last 8 weeks, for context the forward projection cannot see (new sales, new bills)."""
    rows = {r['kind']: q.f(r['amount']) for r in c.execute(TRAILING_SQL, (company, AS_OF, AS_OF)).fetchall()}
    money_in = sum(v for v in rows.values() if v > 0)
    money_out = -sum(v for v in rows.values() if v < 0)
    return {'money_in_per_week': round(money_in / 8, 2), 'money_out_per_week': round(money_out / 8, 2),
            'net_per_week': round((money_in - money_out) / 8, 2),
            'customer_payments_per_week': round(rows.get('customer_payment', 0) / 8, 2),
            'bills_paid_per_week': round(-rows.get('bill_payment', 0) / 8, 2),
            'wages_paid_per_week': round(-rows.get('wage_payment', 0) / 8, 2)}


def cash_outlook(snap, target, projection, trailing=None):
    """Daily balance path (after payroll and bills) to target: low point and first negative day."""
    p = projection(snap, target)
    days = p['days']
    payroll = round(sum(i['amount'] for i in snap['payroll']['schedule'] if i['date'] <= target), 2)
    return {
        'start': p['start'], 'target_date': target.isoformat(), 'opening_balance': round(p['opening_balance'], 2),
        'ending_balance': round(days[-1]['balance'], 2), 'low_point': p['low_point'],
        'pessimistic_low_point': p['pessimistic_low_point'], 'first_negative_date': _first_negative(days),
        'days_below_zero': sum(d['balance'] < 0 for d in days),
        'expected_inflows': round(sum(d['inflow'] for d in days), 2), 'payroll_total': payroll,
        'bills_total': round(sum(q.f(b['open_amount']) for b in snap['bills']), 2),
        'owner_draw_reserved': snap.get('draw', 0), 'bills_known_through': _bills_known_through(snap),
        'weekly': _weekly(days), 'trailing_8_weeks': trailing,
        'assumptions': ['Balances are after payroll, entered bills and probability-weighted collections on their expected dates.',
                        'Payroll repeats the trailing 8-week weekday pattern.',
                        'Only bills already entered in the books are included; later bills are not projected.',
                        'Only invoices already issued are collected; new sales are not projected (see trailing_8_weeks for the recent weekly run rate).',
                        'Pessimistic path counts only invoices at least 70% likely to pay.',
                        'Estimated owner draw is reserved on the last day.'],
    }


def spend_schedule(amount, start, end, frequency):
    if frequency == 'once':
        return [(start, amount)] if start <= end else []
    out, n, day = [], 0, start
    while day <= end:
        out.append((day, amount))
        n += 1
        if frequency == 'weekly':
            day = start + timedelta(days=7 * n)
        else:  # monthly, same day of month (clamped to 28 to stay valid)
            month = start.month - 1 + n
            day = date(start.year + month // 12, month % 12 + 1, min(start.day, 28))
    return out


def _subtract(days, schedule):
    spent, by_day, out = 0.0, {}, []
    for day, amount in schedule:
        by_day[day.isoformat()] = by_day.get(day.isoformat(), 0.0) + amount
    for d in days:
        extra = by_day.get(d['date'], 0.0)
        spent += extra
        out.append({**d, 'outflow': round(d['outflow'] + extra, 2), 'balance': round(d['balance'] - spent, 2)})
    return out


def run_rate(trailing, bank, amount, frequency):
    """Recurring costs judged against the actual recent weekly net, which (unlike the projection) includes new sales."""
    if not trailing:
        return None
    weekly_cost = {'weekly': amount, 'monthly': amount * 12 / 52}.get(frequency, 0.0)
    net = trailing['net_per_week']
    after = round(net - weekly_cost, 2)
    weeks = lambda n: round(bank / -n, 1) if n < 0 else None
    return {'net_per_week_now': net, 'cost_per_week': round(weekly_cost, 2), 'net_per_week_with_spend': after,
            'weeks_of_cash_now': weeks(net), 'weeks_of_cash_with_spend': weeks(after),
            'basis': 'Last 8 weeks of actual bank movement (customer payments in; bills and wages out).'}


def affordability(snap, projection, amount, start, frequency, target, trailing=None):
    """Compare the daily cash path with and without a new one-off or recurring cost."""
    if frequency not in ('once', 'weekly', 'monthly'):
        raise ValueError('frequency must be once, weekly or monthly')
    if start > target:
        raise ValueError('through_date must be on or after the spend date')
    p = projection(snap, target)
    schedule = spend_schedule(amount, start, target, frequency)
    with_days, with_pess = _subtract(p['days'], schedule), _subtract(p['pessimistic_days'], schedule)
    low_base, low_with = p['low_point'], _low(with_days)
    return {
        'spend': {'amount': amount, 'start_date': start.isoformat(), 'frequency': frequency,
                  'payments_in_window': len(schedule), 'total_in_window': round(sum(a for _, a in schedule), 2)},
        'target_date': target.isoformat(), 'opening_balance': round(p['opening_balance'], 2),
        'baseline': {'low_point': low_base, 'pessimistic_low_point': p['pessimistic_low_point'],
                     'ending_balance': round(p['days'][-1]['balance'], 2), 'first_negative_date': _first_negative(p['days'])},
        'with_spend': {'low_point': low_with, 'pessimistic_low_point': _low(with_pess),
                       'ending_balance': round(with_days[-1]['balance'], 2), 'first_negative_date': _first_negative(with_days)},
        'low_point': low_with,
        'affordable': low_with['balance'] >= 0, 'affordable_if_slow_payers_slip': _low(with_pess)['balance'] >= 0,
        'already_short_without_it': low_base['balance'] < 0,
        'bills_known_through': _bills_known_through(snap),
        'weekly': _weekly(with_days), 'weekly_baseline': _weekly(p['days']), 'trailing_8_weeks': trailing,
        'run_rate': run_rate(trailing, p['opening_balance'], amount, frequency),
        'assumptions': ['Same daily cash path as the cash outlook, with the new cost subtracted on its dates.',
                        'The cost amount is as stated by the owner; taxes, benefits or financing are not added.',
                        'Only bills already entered and invoices already issued are included; new sales and new bills are not projected.'],
    }


# ---------- bills ----------

def _tolerance(hist):
    if hist is None:
        return 'unknown'
    return 'high' if q.f(hist) >= 7 else 'some' if q.f(hist) >= 3 else 'low'


def list_bills(c, company, through, query=None):
    rows = q.bills_due(c, company, AS_OF, through)
    deferrals = {r['bill_id']: r['due_date'] for r in
                 c.execute('select bill_id,due_date from bill_deferrals where company_id=%s', (company,)).fetchall()}
    bills = []
    for b in rows:
        if q.f(b['open_amount']) <= 0:
            continue
        due = deferrals.get(b['bill_id'], b['due_date'])
        if due > through:
            continue
        if query and not any(name_matches(query, s) for s in
                             (b['vendor_name'] or '', b.get('supply_role') or '', b['bill_id'].replace('-', ' '))):
            continue
        hist = b.get('hist_days_vs_due')
        bills.append({'bill_id': b['bill_id'], 'vendor_name': b['vendor_name'], 'due_date': due.isoformat(),
                      'amount': round(q.f(b['open_amount']), 2), 'status': 'overdue' if due < AS_OF else 'due',
                      'days_until_due': (due - AS_OF).days, 'category': b.get('supply_role'),
                      'vendor_terms_days': b.get('payment_terms_days'),
                      'usually_paid_days_after_due': round(q.f(hist), 1) if hist is not None else None,
                      'deferral_tolerance': _tolerance(hist), 'deferred': b['bill_id'] in deferrals})
    bills.sort(key=lambda b: (b['due_date'], -b['amount']))
    return {'through_date': through.isoformat(), 'query': query or None, 'count': len(bills),
            'total': round(sum(b['amount'] for b in bills), 2),
            'overdue_total': round(sum(b['amount'] for b in bills if b['status'] == 'overdue'), 2),
            'bills': bills,
            'note': 'Deferral tolerance comes from how many days after the due date this vendor has historically been paid; it is not vendor agreement.'}


def find_bill(c, company, bill_id):
    for b in q.bills_due(c, company, AS_OF, AS_OF + timedelta(days=120)):
        if b['bill_id'] == bill_id and q.f(b['open_amount']) > 0:
            return b
    return None


# ---------- customers ----------

def _customer_stats(c, company):
    from owed.pages import CUSTOMER_STATS_SQL
    return c.execute(CUSTOMER_STATS_SQL.format(extra=''), {'cid': company, 'as_of': AS_OF}).fetchall()


def _customer_row(r, reliability):
    from owed.pages import _customer
    out = _customer(r, reliability, detail=True)
    out.pop('payment_terms', None)
    return out


def _reliability(scored):
    from owed.pages import _reliability as rel
    return rel(scored or [])


def find_customer(c, company, name, scored):
    if not isinstance(name, str) or not name.strip():
        raise ValueError('Give a customer name to look up')
    rows = [r for r in _customer_stats(c, company) if name_matches(name, r['display_name'])]
    reliability = _reliability(scored)
    found = sorted((_customer_row(r, reliability) for r in rows),
                   key=lambda r: (-r['open_balance'], r['display_name']))
    return {'query': name, 'matches': len(found), 'customers': found[:8],
            'note': ('No customer in these books matches that name.' if not found else
                     'Several customers match; the one with the largest open balance is listed first.' if len(found) > 1 else None)}


def rank_customers(c, company, by, scored, limit=5):
    if by not in RANKINGS:
        raise ValueError(f"by must be one of {', '.join(RANKINGS)}")
    reliability = _reliability(scored)
    rows = [_customer_row(r, reliability) for r in _customer_stats(c, company)]
    seasoned = [r for r in rows if r['paid_invoices'] >= 5 and r['avg_days_late'] is not None]
    keys = {
        'worst': (seasoned, lambda r: (-r['written_off'], -(r['avg_days_late'] or 0), -r['overdue_balance'])),
        'slowest': (seasoned, lambda r: (-(r['avg_days_late'] or 0), -r['overdue_balance'])),
        'most_overdue': ([r for r in rows if r['overdue_balance'] > 0], lambda r: -r['overdue_balance']),
        'largest_balance': ([r for r in rows if r['open_balance'] > 0], lambda r: -r['open_balance']),
        'most_reliable': (seasoned, lambda r: (r['written_off'], r['avg_days_late'] or 0, -r['paid_invoices'])),
    }
    pool, key = keys[by]
    criteria = {
        'worst': 'Written-off amount first, then average days late on paid invoices (customers with 5+ paid invoices), then overdue balance.',
        'slowest': 'Average days late on paid invoices, customers with 5+ paid invoices.',
        'most_overdue': 'Open balance past its due date today.',
        'largest_balance': 'Total open balance today.',
        'most_reliable': 'Fewest write-offs, then fewest average days late, customers with 5+ paid invoices.',
    }[by]
    return {'ranked_by': by, 'criteria': criteria, 'customers_considered': len(pool),
            'customers': sorted(pool, key=key)[:max(1, min(int(limit or 5), 10))]}


# ---------- the one clarifying question ----------

def pivotal_customer(scored, target, stats, gap):
    """The one customer whose payment by `target` could flip the payroll verdict, or None.

    stats maps customer_id -> {display_name, avg_days_late, paid_invoices, written_off}. gap > 0 means the
    payroll is short by gap; gap <= 0 means it is covered with a buffer of -gap. Only dependable payers
    (5+ paid invoices, no write-offs) qualify: their timing is what the owner may know better than the model."""
    per = {}
    for r in scored:
        due = r.get('due_date')
        due = due if isinstance(due, date) else (date.fromisoformat(str(due)) if due else None)
        if due is None or due > target:
            continue
        c = per.setdefault(r['customer_id'], {'owed': 0.0, 'counted': 0.0})
        amount = q.f(r['open_balance'])
        c['owed'] += amount
        c['counted'] += amount * float(r.get('p_paid_by_target') or 0)
    candidates = []
    for cid, c in per.items():
        st = stats.get(cid) or {}
        if (st.get('paid_invoices') or 0) < 5 or q.f(st.get('written_off') or 0) > 0:
            continue
        swing = c['owed'] - c['counted']
        if gap > 0 and swing >= gap:                                  # short: paying in full would close it
            candidates.append((swing, cid, c))
        elif gap <= 0 and 0 < c['counted'] and c['counted'] >= -gap:  # covered: not paying would open a hole
            candidates.append((c['counted'], cid, c))
    if not candidates:
        return None
    _, cid, c = max(candidates, key=lambda t: t[0])
    name = stats[cid].get('display_name') or cid
    payday = f'{target.strftime("%B")} {target.day}'
    return {'customer_id': cid, 'customer_name': name, 'owed_by_target': round(c['owed'], 2),
            'counted_on': round(c['counted'], 2), 'avg_days_late': stats[cid].get('avg_days_late'),
            'target_date': target.isoformat(),
            'question': f'Should I assume {name} will pay the ${c["owed"]:,.0f} they owe by {payday}, or treat them as not paying?'}


# ---------- receivables ----------

def receivables_summary(scored, expected_in_30_days):
    buckets = {'not_yet_due': 0.0, '1_30_days': 0.0, '31_60_days': 0.0, '61_90_days': 0.0, 'over_90_days': 0.0}
    for r in scored:
        amount, dpd = q.f(r['open_balance']), r['days_past_due']
        key = ('not_yet_due' if dpd <= 0 else '1_30_days' if dpd <= 30 else '31_60_days' if dpd <= 60
               else '61_90_days' if dpd <= 90 else 'over_90_days')
        buckets[key] += amount
    by_customer = {}
    for r in scored:
        if r['days_past_due'] > 0:
            by_customer[r['customer_name']] = by_customer.get(r['customer_name'], 0.0) + q.f(r['open_balance'])
    owed = round(sum(q.f(r['open_balance']) for r in scored), 2)
    overdue = round(sum(q.f(r['open_balance']) for r in scored if r['days_past_due'] > 0), 2)
    return {'owed_total': owed, 'overdue_total': overdue, 'not_yet_due_total': round(owed - overdue, 2),
            'expected_in_30_days': expected_in_30_days,
            'open_invoices': len(scored), 'overdue_invoices': sum(r['days_past_due'] > 0 for r in scored),
            'aging': {k: round(v, 2) for k, v in buckets.items()},
            'top_overdue_customers': [{'customer': k, 'overdue': round(v, 2)} for k, v in
                                      sorted(by_customer.items(), key=lambda kv: -kv[1])[:3]],
            'note': 'Expected in 30 days is probability-weighted from payment history; it is not guaranteed.'}


# ---------- orders ----------

HIST_SQL = '''select count(*) filter (where status='paid') n_paid,
       avg(days_late) filter (where status='paid') avg_late,
       stddev_pop(days_late) filter (where status='paid') sd_late,
       avg((days_late>0)::int) filter (where status='paid') late_rate,
       max(days_late) filter (where status='paid') max_late,
       count(*) filter (where status='written_off') n_wo,
       avg(total_amount) avg_amount
  from invoice_facts where company_id=%s and customer_id=%s and due_date < %s'''


def evaluate_order(c, company, model, customer, amount, terms_days, upfront_cost, snapshot_for, projection):
    """Score a hypothetical new invoice with the payment model and test any up-front cost against cash.

    snapshot_for(target) returns a payroll snapshot covering target (cached by the caller)."""
    hist = c.execute(HIST_SQL, (company, customer['id'], AS_OF)).fetchone() or {}
    company_row = c.execute('select profile, size_tier from companies where company_id=%s', (company,)).fetchone() or {}
    avg_amount = q.f(hist.get('avg_amount'))
    row = {'terms_days': terms_days, 'n_paid': hist.get('n_paid') or 0, 'avg_late': hist.get('avg_late'),
           'sd_late': hist.get('sd_late'), 'late_rate': hist.get('late_rate'), 'max_late': hist.get('max_late'),
           'n_wo': hist.get('n_wo') or 0, 'amount_ratio': amount / avg_amount if avg_amount else None,
           'total_amount': amount, 'profile': company_row.get('profile'), 'size_tier': company_row.get('size_tier')}
    late = max(0.0, float(model.expected_days_late([row])[0]))
    p_never = round(float(model.p_never([row])[0]), 3)
    horizons = [0, 14, 30, 60]
    cdf = model.cdf([row] * len(horizons), np.array(horizons, dtype=float))
    pay_date = AS_OF + timedelta(days=terms_days + int(round(late)))
    exposure = round(q.f(customer.get('open_balance')) + amount, 2)
    result = {
        'order': {'customer_id': customer['id'], 'customer': customer['display_name'], 'amount': amount,
                  'terms_days': terms_days, 'upfront_cost': upfront_cost,
                  'gross_margin': round(amount - upfront_cost, 2) if upfront_cost else None,
                  'invoice_date_assumed': AS_OF.isoformat(), 'due_date': (AS_OF + timedelta(days=terms_days)).isoformat()},
        'customer': customer,
        'track_record': {'paid_invoices': int(row['n_paid']), 'avg_days_late': round(q.f(row['avg_late']), 1) if row['avg_late'] is not None else None,
                    'max_days_late': row['max_late'], 'late_rate': round(q.f(row['late_rate']), 2) if row['late_rate'] is not None else None,
                    'written_off_invoices': int(row['n_wo']), 'average_invoice': round(avg_amount, 2),
                    'order_vs_average': round(amount / avg_amount, 1) if avg_amount else None},
        'payment_outlook': {'expected_days_late': round(late, 1), 'expected_pay_date': pay_date.isoformat(),
                            'p_never': p_never,
                            'p_paid_within_days_of_due': {str(h): round(float(v) * (1 - p_never), 3) for h, v in zip(horizons, cdf)}},
        'exposure_after_order': exposure,
        'expected_value': round(amount * (1 - p_never) - upfront_cost, 2),
    }
    if upfront_cost:
        target = min(max(pay_date, AS_OF + timedelta(days=14)), AS_OF + MAX_HORIZON)
        result['cash_with_upfront_cost'] = affordability(snapshot_for(target), projection, upfront_cost,
                                                         AS_OF + timedelta(days=1), 'once', target)
        result['low_point'] = result['cash_with_upfront_cost']['with_spend']['low_point']
        for key in ('weekly', 'weekly_baseline'):
            result['cash_with_upfront_cost'].pop(key, None)
    return result
