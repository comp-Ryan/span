"""DB-backed: reset_demo removes only the given company's runtime rows (isolated span_test_* database)."""
import importlib.util
from datetime import date
from pathlib import Path

from owed.db import apply_runtime, conn
from owed.events import emit
from owed.runs import create

spec = importlib.util.spec_from_file_location('reset_demo', Path(__file__).parents[1] / 'scripts/reset_demo.py')
reset_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reset_demo)


def seed(company):
    rid = create(company, 'reset test', 'web', 'free_question', target_date=date(2026, 10, 20))
    emit(rid, 'node.create', {'node_id': 'context', 'type': 'context', 'title': 'q', 'status': 'done', 'parent': None})
    with conn() as c:
        c.execute("insert into cash_projection(company_id,scenario,day,inflow,outflow,balance) values (%s,'expected','2026-10-07',1,1,1)", (company,))
        c.execute("insert into generated_reports(report_id,run_id,company_id,doc) values (%s,%s,%s,'{}')", ('rep-' + rid, rid, company))
    return rid


def test_reset_clears_one_company_and_keeps_the_dataset(capsys):
    apply_runtime()
    with conn() as c:
        invoices = c.execute('select count(*) n from invoice_facts').fetchone()['n']
        agents = c.execute('select count(*) n from customer_agents').fetchone()['n']
    mine, other = seed('company-020'), seed('company-001')
    try:
        with conn() as c:
            other_events = c.execute('select count(*) n from events where run_id=%s', (other,)).fetchone()['n']
        counts = reset_demo.counts(reset_demo.connect(reset_demo.database_url()), 'company-020')
        assert counts['runs'] >= 1 and counts['events'] >= 1 and counts['cash_projection'] >= 1
        deleted = reset_demo.reset(reset_demo.database_url(), 'company-020', yes=True)
        assert deleted['runs'] >= 1 and deleted['generated_reports'] >= 1
        with conn() as c:
            assert c.execute('select count(*) n from runs where company_id=%s', ('company-020',)).fetchone()['n'] == 0
            assert c.execute('select count(*) n from events where company_id=%s', ('company-020',)).fetchone()['n'] == 0
            assert c.execute('select count(*) n from cash_projection where company_id=%s', ('company-020',)).fetchone()['n'] == 0
            assert c.execute('select count(*) n from runs where run_id=%s', (other,)).fetchone()['n'] == 1
            assert c.execute('select count(*) n from events where run_id=%s', (other,)).fetchone()['n'] == other_events
            assert c.execute('select count(*) n from invoice_facts').fetchone()['n'] == invoices
            assert c.execute('select count(*) n from customer_agents').fetchone()['n'] == agents
        dry = reset_demo.reset(reset_demo.database_url(), 'company-001', yes=False)
        assert dry['runs'] >= 1  # counted, not deleted
        with conn() as c:
            assert c.execute('select count(*) n from runs where run_id=%s', (other,)).fetchone()['n'] == 1
    finally:
        with conn() as c:
            for rid in (mine, other):
                c.execute('delete from generated_reports where run_id=%s', (rid,))
                c.execute('delete from events where run_id=%s', (rid,))
                c.execute('delete from runs where run_id=%s', (rid,))
            c.execute("delete from cash_projection where company_id='company-001' and forecast_id is null and inflow=1")
