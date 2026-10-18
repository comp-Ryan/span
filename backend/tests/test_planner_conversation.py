from datetime import date

import pytest

import owed.planner as planner
from owed.runs.payroll import planner_for_call


@pytest.mark.parametrize(('source', 'intent', 'configured', 'expected'), [
    ('call', 'payroll_check', True, True),
    ('call', 'payroll_check', False, False),
    ('web', 'payroll_check', True, False),
    ('call', 'what_if_customer', True, False),
    ('call', 'show_late', True, False),
])
def test_call_payroll_planner_routing(source, intent, configured, expected):
    assert planner_for_call(source, intent, configured) is expected


@pytest.mark.parametrize(('spoken', 'detail', 'expected'), [
    ('Should I assume Evergreen will pay by payday?', '', True),
    ('What date should I use?', '', True),
    ('Payroll looks covered. Should I continue?', '', False),
    ('Should I assume Evergreen will pay by payday?', 'Some report detail', False),
    ('Who is late?', '', False),
])
def test_awaiting_input_classification(spoken, detail, expected):
    assert planner.is_awaiting_input(spoken, detail) is expected


def test_planner_followup_carries_only_parent_question_and_spoken_context():
    prompt = planner.planner_followup_message(
        'Assume they pay.',
        parent_question='Will payroll clear in two weeks?',
        parent_speech='Should I assume Evergreen pays by payday, or treat them as not paying?',
    )

    assert 'Owner’s original question: Will payroll clear in two weeks?' in prompt
    assert 'Span’s most recent spoken response: Should I assume Evergreen pays by payday' in prompt
    assert 'Owner’s current reply or follow-up: Assume they pay.' in prompt
    assert 'not authorization' in prompt


def test_planner_followup_without_parent_keeps_typed_question_unchanged():
    assert planner.planner_followup_message('Who is late?') == 'Who is late?'


class Connection:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, *args):
        return self

    def fetchone(self):
        return self.row


def fake_books(bank=100, forecast=None):
    return {'forecast': {'bills_due_by_target': 0, **(forecast or {})}, 'bank': bank,
            'payroll': {'due_by_target': 10, 'headcount': 1}}


def test_forecast_tool_applies_the_explicit_customer_assumption(monkeypatch):
    calls = []
    monkeypatch.setattr(planner, 'conn', lambda: Connection({'id': 'customer-1'}))

    def fake_snapshot(company, target, excluded_customer_id=None, assumed_customer_id=None):
        calls.append((company, target, excluded_customer_id, assumed_customer_id))
        return fake_books()

    monkeypatch.setattr(planner, 'snapshot', fake_snapshot)
    ctx = planner.ToolContext('run-1', 'company-1', date(2026, 10, 9))
    ctx.snap = fake_books()

    no = ctx.read_tool('forecast_cash', {'customer_id': 'customer-1', 'will_pay': False})
    yes = ctx.read_tool('forecast_cash', {'customer_id': 'customer-1', 'will_pay': True})

    assert no['bank_balance'] == yes['bank_balance'] == 100
    assert calls == [
        ('company-1', date(2026, 10, 9), 'customer-1', None),
        ('company-1', date(2026, 10, 9), None, 'customer-1'),
    ]
    with pytest.raises(ValueError, match='Specify whether the customer will pay'):
        ctx.read_tool('forecast_cash', {'customer_id': 'customer-1', 'will_pay': 'yes'})


def test_forecast_uses_explicit_fourteen_day_target_and_persists_it(monkeypatch):
    monkeypatch.setattr(planner, 'conn', lambda: Connection(None))
    calls = []
    monkeypatch.setattr(planner, 'snapshot', lambda company, target, **kwargs: (
        calls.append((company, target, kwargs)) or
        fake_books(forecast={'cash_at_target': 125})
    ))
    ctx = planner.ToolContext('run-1', 'company-1', date(2026, 10, 9))

    result = ctx.read_tool('forecast_cash', {'target_date': '2026-10-20'})
    follow_up = ctx.read_tool('forecast_cash', {})

    assert result['target_date'] == '2026-10-20'
    assert follow_up['target_date'] == '2026-10-20'
    assert ctx.target == date(2026, 10, 20)
    assert calls == [('company-1', date(2026, 10, 20), {})]


@pytest.mark.parametrize(('target', 'message'), [
    ('2026-10-20T00:00:00', 'YYYY-MM-DD'),
    ('2026-10-05', 'between the dataset date'),
    ('2027-10-08', 'between the dataset date'),
])
def test_forecast_rejects_invalid_explicit_target(monkeypatch, target, message):
    monkeypatch.setattr(planner, 'snapshot', lambda *args, **kwargs: pytest.fail('invalid target snapshot'))
    ctx = planner.ToolContext('run-1', 'company-1', date(2026, 10, 9))

    with pytest.raises(ValueError, match=message):
        ctx.read_tool('forecast_cash', {'target_date': target})
    assert ctx.target == date(2026, 10, 9)


def test_customer_scenario_uses_selected_target_for_subsequent_levers(monkeypatch):
    calls = []
    baseline = fake_books(forecast={'source': 'baseline'})
    monkeypatch.setattr(planner, 'conn', lambda: Connection({'id': 'customer-1'}))

    def fake_snapshot(company, target, excluded_customer_id=None, assumed_customer_id=None):
        calls.append((company, target, excluded_customer_id, assumed_customer_id))
        if excluded_customer_id or assumed_customer_id:
            return fake_books(forecast={'source': 'scenario'})
        return baseline

    monkeypatch.setattr(planner, 'snapshot', fake_snapshot)
    ctx = planner.ToolContext('run-1', 'company-1', date(2026, 10, 9))
    ctx.snap = fake_books(90, {'source': 'old'})

    result = ctx.read_tool('forecast_cash', {
        'target_date': '2026-10-20', 'customer_id': 'customer-1', 'will_pay': True,
    })

    assert result['source'] == 'scenario' and result['bank_balance'] == 100 and result['target_date'] == '2026-10-20'
    assert ctx.target == date(2026, 10, 20)
    assert ctx.snap['forecast']['source'] == 'scenario'
    assert baseline['forecast']['source'] == 'baseline'
    assert calls == [
        ('company-1', date(2026, 10, 20), None, None),
        ('company-1', date(2026, 10, 20), None, 'customer-1'),
    ]


def test_only_one_owner_approval_can_be_pending(monkeypatch):
    monkeypatch.setattr(planner, 'conn', lambda: Connection({'decision_id': 'd-pending'}))
    ctx = planner.ToolContext('run-1', 'company-1', date(2026, 10, 9))

    assert ctx.approval('send_message', {'invoice_id': 'invoice-1'}) == {
        'status': 'waiting_for_owner',
        'decision_id': 'd-pending',
    }
