"""DB-free PR #27 verdict/row contract regression tests."""
import pytest
from owed.planner import score_row, verdict_of

@pytest.mark.parametrize(('text', 'expected'), [
    ('Yes, you have $1.2k to spare.', {'verdict': 'yes', 'number': 1200}),
    ('No, you are $385 short.', {'verdict': 'no', 'number': 385}),
    ('You cannot afford $2,000.', {'verdict': 'no', 'number': 2000}),
    ('Barely, with $42 left.', {'verdict': 'barely', 'number': 42}),
    ('Should Evergreen pay by payday?', {}),
    # several amounts: take the one next to a shortfall/buffer cue, never the first number mentioned
    ('No, you cannot afford the $3,000 forklift because cash is already projected to dip to -$6,892.08 and this '
     'purchase would deepen that shortfall to -$9,892.08.', {'verdict': 'no', 'number': 9892.08}),
    ('No, you are facing a projected shortfall of $384.94 for payroll on October 20. You will need at least $385.',
     {'verdict': 'no', 'number': 384.94}),
    # several amounts and no cue: a yes/no without a headline number
    ('You can take the order, but their balance would reach $2,538.01 and $668.58 is overdue.', {'verdict': 'yes'}),
    # the cue window must not jump over another dollar amount
    ("No, payroll is $13,275 and you'll be $669 short.", {'verdict': 'no', 'number': 669}),
    ('Yes, you can cover the $9,800 payroll with $600 to spare.', {'verdict': 'yes', 'number': 600}),
    ("No problem, you're covered with $600 to spare.", {'verdict': 'yes', 'number': 600}),
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
