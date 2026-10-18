#!/usr/bin/env python3
"""Clear one company's runtime rows (runs, events, decisions, reminders, pay links, payments, negotiations,
reports, inbox, deferrals, draw holds, forecast history, cash projections) so the demo starts clean.

Dataset tables are never touched, and only a local database is accepted. Without --yes it only prints counts.

Run from backend/:  .venv/bin/python scripts/reset_demo.py [--company company-020] [--yes]
"""
import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1'}
RUNS = 'select run_id from runs where company_id=%(c)s'
# Children before parents; every predicate is scoped to the company. Dataset tables are deliberately absent.
SCOPES = [
    ('forecast_payments', 'payment_id in (select payment_id from payments where company_id=%(c)s)'),
    ('payments', 'company_id=%(c)s'),
    ('pay_tokens', 'company_id=%(c)s'),
    ('negotiations', 'company_id=%(c)s'),
    ('reminders', 'company_id=%(c)s'),
    ('channel_inbox', 'company_id=%(c)s'),
    ('action_jobs', f'decision_id in (select decision_id from decisions where run_id in ({RUNS}))'),
    ('decisions', f'run_id in ({RUNS})'),
    ('generated_reports', 'company_id=%(c)s'),
    ('bill_deferrals', 'company_id=%(c)s'),
    ('draw_holds', 'company_id=%(c)s'),
    ('forecast_history', 'company_id=%(c)s'),
    ('cash_projection', 'company_id=%(c)s'),
    ('events', f'company_id=%(c)s or run_id in ({RUNS})'),
    ('runs', 'company_id=%(c)s'),
]


def database_url():
    url = os.environ.get('DATABASE_URL')
    if not url:
        from dotenv import dotenv_values
        url = dotenv_values(ROOT / 'backend/.env').get('DATABASE_URL') or dotenv_values(Path('.env')).get('DATABASE_URL')
    if not url:
        sys.exit('DATABASE_URL is not set (environment or backend/.env)')
    return url


def require_local(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme not in ('postgres', 'postgresql') or host not in LOCAL_HOSTS:
        sys.exit(f'Refusing to reset a non-local database (host {host or "?"}); only localhost/127.0.0.1 are allowed')
    return host


def connect(url):
    require_local(url)
    return psycopg.connect(url)


def present(c, table):
    return c.execute('select to_regclass(%s)', (table,)).fetchone()[0] is not None


def counts(c, company):
    out = {}
    for table, where in SCOPES:
        if present(c, table):
            out[table] = c.execute(sql.SQL('select count(*) from {} where ' + where).format(sql.Identifier(table)),
                                   {'c': company}).fetchone()[0]
    return out


def reset(url, company, yes=False):
    """Print per-table counts; delete them in one transaction only when yes=True. Returns the counts."""
    with connect(url) as c:
        before = counts(c, company)
        name = urlsplit(url).path.lstrip('/')
        print(f'{name}: runtime rows for {company}')
        for table, n in before.items():
            print(f'  {table:20} {n:>6}')
        print(f'  {"total":20} {sum(before.values()):>6}')
        if not yes:
            print('Dry run: nothing deleted. Pass --yes to delete these rows.')
            c.rollback()
            return before
        deleted = {}
        for table, where in SCOPES:
            if table in before:
                deleted[table] = c.execute(sql.SQL('delete from {} where ' + where).format(sql.Identifier(table)),
                                           {'c': company}).rowcount
        c.commit()
        print(f'Deleted {sum(deleted.values())} rows for {company}; dataset tables untouched.')
        return deleted


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--company', default='company-020')
    p.add_argument('--yes', action='store_true', help='actually delete (otherwise print counts only)')
    a = p.parse_args()
    reset(database_url(), a.company, a.yes)


if __name__ == '__main__':
    main()
