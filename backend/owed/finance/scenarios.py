"""Shared invoice assumptions for dated charts and horizon forecasts."""
from owed.finance import queries as q

PESSIMISTIC_THRESHOLD = 0.7


def expected_receipt(row):
    return q.f(row['open_balance']) * row['p_paid_by_target']


def reliable(row):
    return row['p_paid_by_target'] >= PESSIMISTIC_THRESHOLD


def pessimistic_forecast(rows, bank, bills, draw, payroll):
    expected = round(sum(expected_receipt(row) for row in rows if reliable(row)), 2)
    cash = round(bank + expected - bills - draw, 2)
    return {'expected_by_target': expected, 'cash_at_target': cash,
            'gap': round(max(0, payroll - cash), 2)}


def answer_title(forecast):
    gap, risk = forecast['gap'], forecast['pessimistic']['gap']
    if gap:
        return f'No. ${gap:,.0f} short; ${risk:,.0f} short if the slow payers slip.'
    if risk:
        return f'Barely, and ${risk:,.0f} short if the slow payers slip.'
    return 'Yes. Payroll is covered, including if the slow payers slip.'
