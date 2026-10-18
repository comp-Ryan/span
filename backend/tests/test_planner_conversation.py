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
    ('Who is the customer, and what are the order amount and payment terms?', '', True),
    ('What is the amount of the order?', '', True),
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


# ---------- routing ----------

@pytest.mark.parametrize(('question', 'intent'), [
    ('Will I make payroll in two weeks?', 'payroll_check'),
    ('Can I cover payroll on Friday?', 'payroll_check'),
    ('Can I afford a $3,000 forklift without missing payroll?', 'afford_check'),
    ('Can I purchase a truck?', 'afford_check'),  # "purchase" must not match "chase"
    ('Who should I chase today?', 'chase_today'),
    ('Should I take a $1,200 order from Yeoman Roasters on net 30?', 'order_check'),
    ('Is my border fence ok?', 'free_question'),  # "border" must not match "order"
    ('What bills are due this week?', 'bills_check'),
    ("Who's my worst payer?", 'client_status'),
    ('How reliable is Yeoman Roasters?', 'client_status'),
    ("What's my cash low point in the next month?", 'cash_check'),
    ('How much am I owed and how much is overdue?', 'cash_check'),
    ("What's the weather?", 'free_question'),
    ('What if Evergreen doesn’t pay?', 'what_if_customer'),
    ('Show me who’s late', 'show_late'),
])
def test_route_intent(question, intent):
    assert planner.route_intent(question) == intent


def test_new_tools_are_declared_with_valid_schemas():
    names = {t['name'] for t in planner.TOOLS}
    assert planner.NEW_TOOLS <= names
    for tool in planner.TOOLS:
        assert set(tool['parameters']['required']) <= set(tool['parameters']['properties'])


def test_system_prompt_anchors_relative_dates_to_dataset_clock():
    text = planner.system_prompt('company-1', date(2026, 10, 9))
    assert 'Friday = 2026-10-09' in text and 'through 2026-10-13' in text
    assert 'through 2026-11-05' in text and '"November" starts 2026-11-01' in text


# ---------- planner_tools (no DB) ----------

from owed import planner_tools as pt  # noqa: E402


class Rows:
    """Fake connection: returns queued result sets in order of execute() calls."""
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        self.current = self.results.pop(0) if self.results else []
        return self

    def fetchall(self):
        return self.current

    def fetchone(self):
        return self.current[0] if isinstance(self.current, list) and self.current else (self.current or None)

    def __iter__(self):
        return iter(self.current)


@pytest.mark.parametrize(('query', 'name', 'expected'), [
    ('Evergreen', 'Evergreen Juniper Flats Removals', True),
    ('yeoman roasters', 'Yeoman Roasters Co.', True),
    ('Yeoman Roasters Co', 'Yeoman Roasters Co.', True),
    ('utilities', 'Elmsworth Municipal Utilities', True),
    ('utility', 'bill utilities 03700', True),
    ('Grimaldi and Sons', 'Grimaldi & Sons Nursery', True),
    ('Evergreen', 'Yeoman Roasters Co.', False),
    ('the', 'The Company', False),
])
def test_name_matching(query, name, expected):
    assert pt.name_matches(query, name) is expected


def test_parse_inputs_validate_dates_and_amounts():
    default = date(2026, 10, 9)
    assert pt.parse_date(None, default) == default
    assert pt.parse_date('2026-11-01', default) == date(2026, 11, 1)
    for bad in ('2026-10-05', '2027-12-01', 'next week', 20261101):
        with pytest.raises(ValueError):
            pt.parse_date(bad, default)
    assert pt.parse_amount('3000') == 3000.0
    assert pt.parse_amount(0, allow_zero=True) == 0
    for bad in (0, -5, 'lots', None, float('nan')):
        with pytest.raises(ValueError):
            pt.parse_amount(bad)


def fake_projection(snap, target):
    days = [{'date': (date(2026, 10, 6) + __import__('datetime').timedelta(days=i)).isoformat(),
             'inflow': 0.0, 'outflow': 0.0, 'balance': b} for i, b in enumerate(snap['path'])]
    pess = [{**d, 'balance': d['balance'] - 50} for d in days]
    low = lambda ds: min(({'date': d['date'], 'balance': d['balance']} for d in ds), key=lambda x: x['balance'])
    return {'start': '2026-10-06', 'opening_balance': snap['bank'], 'days': days, 'pessimistic_days': pess,
            'low_point': low(days), 'pessimistic_low_point': low(pess)}


SNAP = {'bank': 1000, 'path': [1000, 900, 800, 1200, 1100, 1000, 950, 1500, 1400, 1300],
        'payroll': {'schedule': [{'date': date(2026, 10, 8), 'amount': 300}]},
        'bills': [{'due_date': date(2026, 10, 12), 'open_amount': 200}], 'draw': 0}


def test_cash_outlook_reports_low_point_and_first_negative_day():
    snap = {**SNAP, 'path': [500, 200, -100, -300, 400, 600, 700, 800]}
    out = pt.cash_outlook(snap, date(2026, 10, 13), fake_projection, {'net_per_week': -10})
    assert out['low_point'] == {'date': '2026-10-09', 'balance': -300}
    assert out['first_negative_date'] == '2026-10-08' and out['days_below_zero'] == 2
    assert out['ending_balance'] == 800 and out['payroll_total'] == 300
    assert out['bills_known_through'] == '2026-10-12' and out['trailing_8_weeks'] == {'net_per_week': -10}
    assert [w['week_ending'] for w in out['weekly']] == ['2026-10-12', '2026-10-13']
    assert 'cash_at_target' not in out  # must not be mistaken for the payroll CashNode


def test_affordability_once_and_monthly():
    once = pt.affordability(SNAP, fake_projection, 1000, date(2026, 10, 8), 'once', date(2026, 10, 15))
    assert once['baseline']['low_point'] == {'date': '2026-10-08', 'balance': 800}
    assert once['with_spend']['low_point'] == {'date': '2026-10-08', 'balance': -200}
    assert once['affordable'] is False and once['already_short_without_it'] is False
    assert once['with_spend']['first_negative_date'] == '2026-10-08'
    small = pt.affordability(SNAP, fake_projection, 100, date(2026, 10, 8), 'once', date(2026, 10, 15))
    assert small['affordable'] is True and small['low_point']['balance'] == 700
    assert pt.spend_schedule(4000, date(2026, 11, 1), date(2026, 12, 31), 'monthly') == [
        (date(2026, 11, 1), 4000), (date(2026, 12, 1), 4000)]
    assert len(pt.spend_schedule(50, date(2026, 10, 7), date(2026, 10, 28), 'weekly')) == 4
    with pytest.raises(ValueError, match='frequency'):
        pt.affordability(SNAP, fake_projection, 1, date(2026, 10, 8), 'daily', date(2026, 10, 15))


def bill(bill_id, vendor, due, amount, hist, role='utility'):
    return {'bill_id': bill_id, 'vendor_name': vendor, 'due_date': due, 'open_amount': amount,
            'supply_role': role, 'payment_terms_days': 0, 'hist_days_vs_due': hist}


def test_list_bills_filters_paid_deferred_and_query(monkeypatch):
    rows = [bill('bill-utilities-1', 'Foxglove Power & Light', date(2026, 10, 5), 67.9, 1.8),
            bill('bill-2', 'Havenwood Supply', date(2026, 10, 12), 8166.78, 9, 'product'),
            bill('bill-3', 'Paid Vendor', date(2026, 10, 7), 0, 2),
            bill('bill-4', 'Deferred Vendor', date(2026, 10, 8), 100, 2, 'operating')]
    monkeypatch.setattr(pt.q, 'bills_due', lambda c, company, as_of, through: rows)
    c = Rows([{'bill_id': 'bill-4', 'due_date': date(2026, 10, 20)}])
    out = pt.list_bills(c, 'company-1', date(2026, 10, 13))
    assert [b['bill_id'] for b in out['bills']] == ['bill-utilities-1', 'bill-2']
    assert out['total'] == 8234.68 and out['overdue_total'] == 67.9
    assert out['bills'][0]['status'] == 'overdue' and out['bills'][0]['deferral_tolerance'] == 'low'
    assert out['bills'][1]['deferral_tolerance'] == 'high'
    c = Rows([])
    assert [b['bill_id'] for b in pt.list_bills(c, 'company-1', date(2026, 10, 13), 'utilities')['bills']] == ['bill-utilities-1']
    assert c.calls[0][1] == ('company-1',)  # deferrals are company-scoped


def stats(cid, name, open_=0, overdue=0, late=10.0, paid=20, wo=0):
    return {'id': cid, 'display_name': name, 'payment_terms': None, 'payment_terms_days': 7, 'open_balance': open_,
            'overdue_balance': overdue, 'open_invoices': 1, 'avg_days_late': late, 'paid_invoices': paid, 'written_off': wo}


CUSTOMERS = [stats('c1', 'Evergreen Juniper Flats Removals', 1221.93, 1156.2, 23.0, 70),
             stats('c2', 'Evergreen Fulfillment Group', 423.31, 94.66, 14.0, 24),
             stats('c3', 'Yeoman Roasters Co.', 1338.01, 668.58, 21.1, 54),
             stats('c4', 'Bellrock Sterling Florals Company', 594.91, 373.35, 25.2, 49),
             stats('c5', 'Newbie LLC', 50, 50, 40.0, 2),
             stats('c6', 'Lost Cause Inc', 10, 10, 5.0, 30, wo=900)]


def test_find_customer_matches_partial_names_and_sorts_by_balance():
    out = pt.find_customer(Rows(CUSTOMERS), 'company-1', 'evergreen', [])
    assert [c['id'] for c in out['customers']] == ['c1', 'c2'] and out['matches'] == 2 and out['note']
    one = pt.find_customer(Rows(CUSTOMERS), 'company-1', 'Yeoman Roasters', [])
    assert [c['display_name'] for c in one['customers']] == ['Yeoman Roasters Co.'] and one['note'] is None
    assert pt.find_customer(Rows(CUSTOMERS), 'company-1', 'Nobody', [])['customers'] == []
    with pytest.raises(ValueError):
        pt.find_customer(Rows(CUSTOMERS), 'company-1', '  ', [])


def test_rank_customers_orders_and_skips_thin_history():
    worst = pt.rank_customers(Rows(CUSTOMERS), 'company-1', 'worst', [])
    assert [c['id'] for c in worst['customers']][:3] == ['c6', 'c4', 'c1']  # write-offs first, then days late
    assert 'c5' not in [c['id'] for c in worst['customers']]  # fewer than 5 paid invoices
    assert [c['id'] for c in pt.rank_customers(Rows(CUSTOMERS), 'company-1', 'most_overdue', [], 2)['customers']] == ['c1', 'c3']
    with pytest.raises(ValueError):
        pt.rank_customers(Rows(CUSTOMERS), 'company-1', 'tallest', [])


def test_receivables_summary_buckets_match_totals():
    scored = [{'customer_name': 'A', 'open_balance': 100, 'days_past_due': -3},
              {'customer_name': 'B', 'open_balance': 50, 'days_past_due': 10},
              {'customer_name': 'B', 'open_balance': 25, 'days_past_due': 45},
              {'customer_name': 'C', 'open_balance': 10, 'days_past_due': 120}]
    out = pt.receivables_summary(scored, 140.0)
    assert out['owed_total'] == 185 and out['overdue_total'] == 85 and out['not_yet_due_total'] == 100
    assert out['aging'] == {'not_yet_due': 100, '1_30_days': 50, '31_60_days': 25, '61_90_days': 0, 'over_90_days': 10}
    assert out['top_overdue_customers'][0] == {'customer': 'B', 'overdue': 75}
    assert out['expected_in_30_days'] == 140.0 and out['overdue_invoices'] == 3


class FakeModel:
    def expected_days_late(self, rows):
        return [rows[0]['avg_late']]

    def p_never(self, rows):
        return [0.1]

    def cdf(self, rows, horizons):
        return [0.0 if h < 21 else 1.0 for h in horizons]


def test_evaluate_order_scores_new_invoice_and_tests_upfront_cost():
    hist = {'n_paid': 54, 'avg_late': 21.0, 'sd_late': 0.5, 'late_rate': 1.0, 'max_late': 22, 'n_wo': 0, 'avg_amount': 300}
    c = Rows([hist], [{'profile': 'wholesale', 'size_tier': 'small'}])
    customer = {'id': 'c3', 'display_name': 'Yeoman Roasters Co.', 'open_balance': 1338.01}
    targets = []
    out = pt.evaluate_order(c, 'company-1', FakeModel(), customer, 1200, 30, 500,
                            lambda t: targets.append(t) or SNAP, fake_projection)
    assert c.calls[0][1] == ('company-1', 'c3', pt.AS_OF)
    assert out['payment_outlook']['expected_pay_date'] == '2026-11-26'  # net 30 + 21 days late
    assert out['payment_outlook']['p_never'] == 0.1
    assert out['payment_outlook']['p_paid_within_days_of_due'] == {'0': 0.0, '14': 0.0, '30': 0.9, '60': 0.9}
    assert out['exposure_after_order'] == 2538.01 and out['expected_value'] == 580.0
    assert out['track_record']['order_vs_average'] == 4.0
    assert out['customer']['id'] == 'c3'
    assert 'history' not in out  # 'history' is reserved for the payment-history strip on the canvas
    assert targets == [date(2026, 11, 26)] and out['low_point']['balance'] == 300


def test_defer_bill_refuses_vendor_without_tolerance(monkeypatch):
    ctx = planner.ToolContext('run-1', 'company-1', date(2026, 10, 9))
    ctx.snap = {'bills': [bill('bill-1', 'Foxglove', date(2026, 10, 5), 67.9, 1.8)], 'scored': []}
    monkeypatch.setattr(ctx, 'approval', lambda *a, **k: pytest.fail('no approval for a strict vendor'))
    out = ctx.read_tool('defer_bill', {'bill_id': 'bill-1'})
    assert out['status'] == 'not_supported' and out['usually_paid_days_after_due'] == 1.8


def test_planner_forces_a_final_answer_instead_of_exhausting_tools(monkeypatch):
    import asyncio
    from types import SimpleNamespace as NS

    emitted = []
    monkeypatch.setattr(planner, 'emit', lambda run_id, event, data: emitted.append((event, data)))
    monkeypatch.setattr(planner, 'finish', lambda run_id, status: emitted.append(('run.end', status)))
    monkeypatch.setattr(planner, 'conn', lambda: Connection(None))

    async def fake_execute(self, name, args):
        return {'ok': True}
    monkeypatch.setattr(planner.ToolContext, 'execute', fake_execute)
    configs = []

    class Models:
        async def generate_content(self, model, contents, config):
            configs.append(config)
            if config.tool_config is not None:
                return NS(candidates=[NS(content=NS(parts=[NS(function_call=None, thought=False,
                                                             text='Short answer.\n---\n## Why\nBudget.')]))])
            return NS(candidates=[NS(content=NS(parts=[NS(function_call=NS(name='cash_outlook', args={}, id='1'),
                                                         thought=False, text=None)]))])

    client = NS(aio=NS(models=Models()))
    monkeypatch.setattr(planner.types, 'Content', lambda role, parts: NS(role=role, parts=parts))
    asyncio.run(planner.run_planner('run-1', 'company-1', 'loop forever', date(2026, 10, 9), client=client))
    answers = [d for e, d in emitted if e == 'node.create' and d['node_id'] == 'answer']
    assert answers and answers[0]['data']['spoken'] == 'Short answer.'
    assert configs[-1].tool_config is not None and configs[0].tool_config is None
    assert len(configs) == planner.MAX_STEPS
    assert not any(d.get('node_id') == 'planner-error' for e, d in emitted if e == 'node.create')


def test_run_rate_converts_monthly_cost_to_weekly_and_weeks_of_cash():
    rr = pt.run_rate({'net_per_week': -1000.0}, 6000, 5200, 'monthly')
    assert rr['cost_per_week'] == 1200 and rr['net_per_week_with_spend'] == -2200
    assert rr['weeks_of_cash_now'] == 6.0 and rr['weeks_of_cash_with_spend'] == 2.7
    assert pt.run_rate({'net_per_week': 500.0}, 6000, 100, 'once')['weeks_of_cash_now'] is None
    assert pt.run_rate(None, 6000, 100, 'once') is None
