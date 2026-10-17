from datetime import date

from fastapi.testclient import TestClient

from owed.finance.cash import projection
from owed.main import app
from owed.runs.payroll import snapshot


def test_projection_dates_threshold_and_conservation():
    snap = {'bank': 100, 'draw': 0, 'bills': [{'due_date': date(2026, 10, 1), 'open_amount': 10}],
            'payroll': {'schedule': [{'date': date(2026, 10, 8), 'amount': 20}]},
            'scored': [dict(invoice_id=str(i), customer_id=str(i), open_balance=100,
                            p_paid_by_target=p, expected_days_to_pay=d)
                       for i, (p, d) in enumerate([(.7, 1), (.699, 2), (.9, 20)])]}
    result = projection(snap, date(2026, 10, 9))
    assert [d['date'] for d in result['days']] == ['2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09']
    assert [d['balance'] for d in result['days']] == [90, 160, 209.9, 209.9]
    assert [d['balance'] for d in result['pessimistic_days']] == [90, 160, 140, 140]
    assert result['payroll_dates'] == ['2026-10-08']
    assert projection(snap, date(2026, 10, 9), never_pays='0')['days'][-1]['balance'] == 139.9


def test_cash_endpoint_real_company():
    client = TestClient(app)
    response = client.get('/cash?company=company-020&target=2026-10-20')
    assert response.status_code == 200
    result = response.json()
    assert len(result['days']) == len(result['pessimistic_days']) == 15
    snap = snapshot('company-020', date(2026, 10, 20))
    assert abs(sum(d['outflow'] for d in result['days']) - snap['forecast']['bills_due_by_target'] - snap['forecast']['need']) < .01
    for key in ('days', 'pessimistic_days'):
        balance = result['opening_balance']
        for day in result[key]:
            balance = round(balance + day['inflow'] - day['outflow'], 2)
            assert day['balance'] == balance
    assert all(a['balance'] >= b['balance'] for a, b in zip(result['days'], result['pessimistic_days']))
    assert client.get('/cash?company=absent').status_code == 404
    assert client.get('/cash?target=2026-10-05').status_code == 422
    assert client.get('/cash?target=2028-10-05').status_code == 422
    assert client.get('/cash?never_pays=not-in-company').status_code == 404
