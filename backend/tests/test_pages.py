"""Read-only checks for /payments, /reports and /customers against the shared demo DB.

No lifespan (TestClient is not used as a context manager), so no workers or migrations run,
and every request is a GET: nothing here writes to the database.
"""
import pytest
from fastapi.testclient import TestClient

from owed.db import conn
from owed.main import app

CO = 'company-020'
client = TestClient(app)
BANDS = {'green', 'amber', 'red', None}


@pytest.mark.parametrize('prefix', ['', '/api'])
@pytest.mark.parametrize('path', ['/payments', '/reports', '/customers', '/customers/heatmap'])
def test_unknown_company_is_404(prefix, path):
    assert client.get(f'{prefix}{path}?company=company-does-not-exist').status_code == 404


def test_payments_shape_and_totals():
    for prefix in ('', '/api'):
        r = client.get(f'{prefix}/payments?company={CO}')
        assert r.status_code == 200
    d = r.json()
    assert set(d) == {'pay_links', 'payments', 'totals'}
    assert set(d['totals']) == {'links', 'unpaid', 'collected', 'outstanding'}
    for link in d['pay_links']:
        assert set(link) >= {'pay_token', 'invoice_id', 'doc_number', 'customer_id', 'customer_name', 'amount',
                             'status', 'created_at', 'run_id', 'pay_url'}
        assert link['pay_url'] == '/pay/' + link['pay_token']
    for p in d['payments']:
        assert set(p) >= {'payment_id', 'invoice_id', 'customer_name', 'amount', 'rail', 'reference', 'paid_at', 'run_id'}
    created = [l['created_at'] for l in d['pay_links'] if l['created_at']]
    assert created == sorted(created, reverse=True)
    t = d['totals']
    assert t['links'] >= len(d['pay_links'])
    if t['links'] == len(d['pay_links']):  # all links listed (under the 200 cap)
        assert round(t['collected'] + t['outstanding'], 2) == round(sum(l['amount'] for l in d['pay_links']), 2)
        assert t['unpaid'] == sum(l['status'] != 'paid' for l in d['pay_links'])


def test_reports_shape():
    d = client.get(f'/api/reports?company={CO}').json()
    assert set(d) == {'reports', 'unreported'}
    for r in d['reports']:
        assert set(r) == {'report_id', 'run_id', 'question', 'answer', 'generated_at', 'pdf_url'}
        assert r['pdf_url'].startswith(f"/reports/{r['report_id']}.pdf")
    for u in d['unreported']:
        assert set(u) == {'run_id', 'question', 'answer_title', 'started_at'}
        assert u['answer_title']
    gen = [r['generated_at'] for r in d['reports']]
    assert gen == sorted(gen, reverse=True)


def test_customers_list_sorted_and_banded():
    rows = client.get(f'/customers?company={CO}').json()['customers']
    assert rows
    keys = {'id', 'display_name', 'open_balance', 'overdue_balance', 'open_invoices', 'avg_days_late',
            'paid_invoices', 'written_off', 'reliability'}
    for c in rows:
        assert set(c) == keys
        assert c['reliability'] in BANDS
        assert c['overdue_balance'] <= c['open_balance'] + 0.01
        assert (c['reliability'] is None) == (c['open_invoices'] == 0)
    balances = [c['open_balance'] for c in rows]
    assert balances == sorted(balances, reverse=True)


def test_customer_detail_and_scoping():
    top = client.get(f'/api/customers?company={CO}').json()['customers'][0]
    d = client.get(f"/api/customers/{top['id']}?company={CO}").json()
    assert set(d) >= {'customer', 'history', 'invoices', 'activity'}
    assert d['customer']['id'] == top['id'] and 'payment_terms' in d['customer']
    assert d['customer']['reliability'] == top['reliability']
    assert len(d['invoices']) == top['open_invoices']
    assert round(sum(i['open_balance'] for i in d['invoices']), 2) == top['open_balance']
    for i in d['invoices']:
        assert set(i) >= {'invoice_id', 'doc_number', 'open_balance', 'due_date', 'days_past_due',
                          'p_paid_by_target', 'p_never', 'band'}
        assert i['band'] in {'green', 'amber', 'red'}
    for a in d['activity']:
        assert a['kind'] in {'reminder', 'reply', 'negotiation', 'payment'}
        assert set(a) >= {'kind', 'at', 'title', 'detail', 'run_id'}
    ats = [a['at'] for a in d['activity']]
    assert ats == sorted(ats, reverse=True)

    with conn() as c:
        other = c.execute('''select id from customers where company_id<>%s
                             and id not in (select id from customers where company_id=%s) limit 1''', (CO, CO)).fetchone()
    if other:
        assert client.get(f"/customers/{other['id']}?company={CO}").status_code == 404
    assert client.get(f'/customers/cust-does-not-exist?company={CO}').status_code == 404
    assert client.get(f"/customers/{top['id']}?company=company-does-not-exist").status_code == 404


HEAT_STATUSES = ('written_off', 'overdue', 'very_late', 'paid_late', 'unpaid', 'paid_on_time')


def test_customers_heatmap_shape_and_statuses():
    from owed.finance.queries import AS_OF_DEFAULT
    for prefix in ('', '/api'):
        r = client.get(f'{prefix}/customers/heatmap?company={CO}')
        assert r.status_code == 200
    d = r.json()
    assert set(d) == {'months', 'customers'}  # not the /customers/{id} detail payload
    months = d['months']
    assert len(months) == 12 and months == sorted(months) and len(set(months)) == 12
    assert months[-1] == AS_OF_DEFAULT.strftime('%Y-%m')
    rows = d['customers']
    assert rows and len(rows) <= 60
    balances = [c['open_balance'] for c in rows]
    assert balances == sorted(balances, reverse=True)
    known = {c['id']: c for c in client.get(f'/customers?company={CO}').json()['customers']}
    for c in rows:
        assert set(c) == {'id', 'display_name', 'open_balance', 'cells'}
        assert c['id'] in known and c['open_balance'] == known[c['id']]['open_balance']
        assert [x['month'] for x in c['cells']] == months
        assert any(x['invoices'] for x in c['cells'])
        for x in c['cells']:
            assert set(x) == {'month', 'invoices', 'amount', 'status', *HEAT_STATUSES}
            assert x['status'] in {*HEAT_STATUSES, 'none'}
            assert sum(x[k] for k in HEAT_STATUSES) == x['invoices']
            if x['invoices'] == 0:
                assert x['status'] == 'none' and x['amount'] == 0
            else:  # status is the worst outcome present
                assert x['status'] == next(k for k in HEAT_STATUSES if x[k])


def test_customers_heatmap_not_shadowed_by_customer_id():
    assert client.get(f'/customers/heatmap?company={CO}').json().keys() == {'months', 'customers'}
    assert 'customer' not in client.get(f'/api/customers/heatmap?company={CO}').json()
