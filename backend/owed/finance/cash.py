"""Dated cash projection. Keep cash-after-payroll distinct from forecast cash-before-payroll."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException

from owed.config import settings
from owed.finance import queries as q
from owed.finance.scenarios import PESSIMISTIC_THRESHOLD, expected_receipt, reliable
from owed.runs import require_company
from owed.runs.payroll import snapshot

router = APIRouter()


def money(value):
    return Decimal(str(value)).quantize(Decimal('0.01'))


def projection(snap, target, never_pays=None, top3_pay_this_week=False):
    start = q.AS_OF_DEFAULT
    inflows, pessimistic, outflows = defaultdict(Decimal), defaultdict(Decimal), defaultdict(Decimal)
    rows = [r for r in snap['scored'] if r['customer_id'] != never_pays]
    top3 = {r['invoice_id'] for r in sorted(rows, key=expected_receipt, reverse=True)[:3]}
    for row in rows:
        day = start + timedelta(days=max(1, row['expected_days_to_pay']))
        if top3_pay_this_week and row['invoice_id'] in top3:
            day = min(day, start + timedelta(days=7))
        if day > target:
            continue  # Never move a model-predicted receipt into an earlier horizon.
        amount = money(expected_receipt(row))
        inflows[day] += amount
        if reliable(row):
            pessimistic[day] += amount
    for bill in snap['bills']:
        day = max(start, bill['due_date'])
        if day <= target:
            outflows[day] += money(bill['open_amount'])
    payroll = snap['payroll']['schedule']
    for item in payroll:
        outflows[item['date']] += money(item['amount'])
    # Historical estimated owner draw has no scheduled date; reserve it at the horizon.
    outflows[target] += money(snap.get('draw', 0))

    def series(incoming):
        balance = money(snap['bank'])
        result = []
        for n in range((target - start).days + 1):
            day = start + timedelta(days=n)
            balance += incoming[day] - outflows[day]
            result.append({'date': day.isoformat(), 'inflow': float(incoming[day]),
                           'outflow': float(outflows[day]), 'balance': float(balance)})
        return result

    days, pessimistic_days = series(inflows), series(pessimistic)
    def low_point(values):
        low = min(values, key=lambda item: item['balance'])
        return {'date': low['date'], 'balance': low['balance']}
    return {'start': start.isoformat(), 'target': target.isoformat(), 'opening_balance': snap['bank'],
            'days': days, 'pessimistic_days': pessimistic_days,
            'payroll_dates': [p['date'].isoformat() for p in payroll],
            'low_point': low_point(days), 'pessimistic_low_point': low_point(pessimistic_days),
            'assumptions': {'top3_pay_this_week': top3_pay_this_week, 'never_pays': never_pays,
                            'pessimistic_threshold': PESSIMISTIC_THRESHOLD,
                            'clock': 'dataset', 'inflows': 'probability_weighted_on_expected_date',
                            'payroll': 'trailing_8_week_weekday_average',
                            'overdue_bills': 'due_on_start', 'owner_draw': 'reserved_at_target'}}


@router.get('/cash')
def cash(company: str = settings.demo_company, target: date | None = None,
         never_pays: str | None = None, top3_pay_this_week: bool = False):
    require_company(company)
    target = target or q.AS_OF_DEFAULT + timedelta(days=90)
    if not q.AS_OF_DEFAULT <= target <= q.AS_OF_DEFAULT + timedelta(days=366):
        raise HTTPException(422, 'Target must be within 366 days of the dataset clock')
    snap = snapshot(company, target)
    if never_pays and never_pays not in {r['customer_id'] for r in snap['scored']}:
        raise HTTPException(404, 'Customer has no open invoices in this company')
    return projection(snap, target, never_pays, top3_pay_this_week)
