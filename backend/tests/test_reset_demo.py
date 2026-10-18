"""scripts/reset_demo.py: clears company-020's runtime rows only, never dataset tables, never a remote DB."""
import importlib.util
from datetime import date
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('reset_demo', Path(__file__).parents[1] / 'scripts/reset_demo.py')
reset_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reset_demo)

REQUIRED = {'runs', 'events', 'decisions', 'action_jobs', 'reminders', 'pay_tokens', 'payments', 'negotiations',
            'generated_reports', 'channel_inbox', 'bill_deferrals', 'draw_holds', 'forecast_payments', 'cash_projection'}
DATASET = {'companies', 'customers', 'invoices', 'invoice_facts', 'bills', 'bank_transactions', 'payroll_runs', 'customer_agents'}


def test_only_runtime_tables_are_listed_children_first():
    tables = [t for t, _ in reset_demo.SCOPES]
    assert REQUIRED <= set(tables) and not DATASET & set(tables)
    assert tables.index('forecast_payments') < tables.index('payments') < tables.index('pay_tokens')
    assert tables.index('action_jobs') < tables.index('decisions') < tables.index('runs')
    assert tables.index('events') < tables.index('runs')


@pytest.mark.parametrize('url', ['postgresql://owed:owed@db.example.com:5432/owed', 'postgresql://owed:owed@10.0.0.4:5433/owed'])
def test_refuses_non_local_database(url):
    with pytest.raises(SystemExit):
        reset_demo.require_local(url)
    assert reset_demo.require_local('postgresql://owed:owed@localhost:5433/owed') == 'localhost'
    assert reset_demo.require_local('postgresql://owed:owed@127.0.0.1:5433/owed') == '127.0.0.1'
