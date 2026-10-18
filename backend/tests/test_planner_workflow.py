"""DB-free PR #27 verdict/row contract regression tests."""
import pytest
from owed.planner import score_row, verdict_of

@pytest.mark.parametrize(('text', 'expected'), [
    ('Yes, you have $1.2k to spare.', {'verdict': 'yes', 'number': 1200}),
    ('No, you are $385 short.', {'verdict': 'no', 'number': 385}),
    ('You cannot afford $2,000.', {'verdict': 'no', 'number': 2000}),
    ('Barely, with $42 left.', {'verdict': 'barely', 'number': 42}),
    ('Should Evergreen pay by payday?', {}),
])
def test_verdict(text, expected):
    assert verdict_of(text) == expected


def test_score_row_matches_frontend_contract():
    row = score_row({'invoice_id': 'i', 'customer_id': 'c', 'customer_name': 'Evergreen',
                     'open_balance': 12.5, 'days_past_due': 3, 'p_paid_by_target': .8,
                     'p_never': .01, 'expected_days_to_pay': 2})
    assert row['customer'] == 'Evergreen' and row['amount'] == 12.5
    assert row['band'] == 'green' and row['source'] == 'owed_model'
    assert row['expected_days_to_pay'] == 2
