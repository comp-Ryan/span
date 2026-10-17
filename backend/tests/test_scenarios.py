from datetime import date

from owed.finance.scenarios import answer_title, pessimistic_forecast
from owed.runs.payroll import snapshot


def test_pessimistic_excludes_below_point_seven_not_bands():
    rows = [{'open_balance': 100, 'p_paid_by_target': p} for p in (.699, .7, .9)]
    assert pessimistic_forecast(rows, 100, 10, 5, 300) == {
        'expected_by_target': 160, 'cash_at_target': 245, 'gap': 55}
    assert answer_title({'gap': 0, 'pessimistic': {'gap': 55}}) == 'Barely, and $55 short if the slow payers slip.'
    assert answer_title({'gap': 10, 'pessimistic': {'gap': 55}}).startswith('No. $10 short')
    assert answer_title({'gap': 0, 'pessimistic': {'gap': 0}}).startswith('Yes.')


def test_real_forecast_scenario_reconciles():
    snap = snapshot('company-020', date(2026, 10, 20))
    f = snap['forecast']
    p = f['pessimistic']
    assert p['expected_by_target'] == round(sum(r['open_balance'] * r['p_paid_by_target'] for r in snap['scored'] if r['p_paid_by_target'] >= .7), 2)
    assert p['cash_at_target'] == round(snap['bank'] + p['expected_by_target'] - f['bills_due_by_target'] - snap['draw'], 2)
    assert p['gap'] == round(max(0, f['need'] - p['cash_at_target']), 2)
    assert p['gap'] >= f['gap']
