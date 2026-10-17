from fastapi.testclient import TestClient

from owed.main import app


def test_brief_real_company():
    r = TestClient(app).get('/brief?company=company-020')
    assert r.status_code == 200
    b = r.json()
    assert b['company'] == {'id': 'company-020', 'name': 'Palletbay Storage & Warehousing', 'profile': b['company']['profile']}
    assert b['as_of'] == '2026-10-06'
    assert b['bank_balance'] > 0 and b['open_invoices'] > 0
    assert 0 < b['expected_in_30d'] <= b['owed_total'] and 0 <= b['overdue_total'] <= b['owed_total']
    assert b['payroll_next'] and b['payroll_next']['date'] > b['as_of'] and b['payroll_next']['amount'] > 0
    assert b['bills_due_week']['count'] >= 0 and b['bills_due_week']['total'] >= 0
    assert 'collect about' in b['headline']


def test_brief_unknown_company():
    assert TestClient(app).get('/brief?company=company-999').status_code == 404
