#!/usr/bin/env python3
"""Provision/reset an explicitly isolated local demo database. Never resets the source.

Run from backend: .venv/bin/python scripts/demo_db.py create --name span_demo_<unique>
A 0600 .local/<name>.env points to the clone. No secrets are printed.
Reset only after stopping its API: ... reset --env ../.local/<name>.env --confirm <name>
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit, urlunsplit

from dotenv import dotenv_values
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ['forecast_payments', 'action_jobs', 'channel_inbox', 'bill_deferrals', 'draw_holds',
           'generated_reports', 'cash_projection', 'forecast_history', 'payments', 'pay_tokens',
           'negotiations', 'reminders', 'decisions', 'events', 'runs', 'customer_agents']


def isolated_name(name):
    if not re.fullmatch(r'span_(demo|test)_[a-z0-9_]{6,48}', name):
        raise ValueError('Use a unique span_demo_ or span_test_ database name (6+ suffix characters)')
    return name


def local_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('postgres', 'postgresql') or parsed.hostname not in ('localhost', '127.0.0.1'):
        raise ValueError('Only an explicit local PostgreSQL URL is allowed')
    return parsed


def reset(url, confirmation):
    parsed = local_url(url)
    name = isolated_name(parsed.path.lstrip('/'))
    if confirmation != name:
        raise ValueError('--confirm must exactly match the isolated database name')
    with psycopg.connect(url) as c:
        marker = c.execute("select shobj_description(oid,'pg_database') from pg_database where datname=current_database()").fetchone()[0]
        if marker != 'span-isolated-demo-v1':
            raise ValueError('Database was not provisioned by this tool; refusing to reset')
        if c.execute("select count(*) from pg_stat_activity where datname=current_database() and pid<>pg_backend_pid() and backend_type='client backend'").fetchone()[0]:
            raise ValueError('Stop the isolated API/test processes before resetting this database')
        c.execute((ROOT / 'backend/owed/db/runtime.sql').read_text())
        present = [t for t in RUNTIME if c.execute('select to_regclass(%s)', (t,)).fetchone()[0]]
        c.execute(sql.SQL('TRUNCATE {}').format(sql.SQL(',').join(map(sql.Identifier, present))))
    return name


def create(source, name, container):
    parsed = local_url(source)
    isolated_name(name)
    if parsed.port != 5433:
        raise ValueError('This Docker cloning helper expects the local dataset on port 5433')
    source_name = parsed.path.lstrip('/')
    if source_name == name:
        raise ValueError('Source and destination must differ')
    admin = urlunsplit(parsed._replace(path='/postgres'))
    target = urlunsplit(parsed._replace(path='/' + name))
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        c.execute(sql.SQL('COMMENT ON DATABASE {} IS {}').format(sql.Identifier(name), sql.Literal('span-isolated-demo-v1')))
    user = parsed.username or 'owed'
    with psycopg.connect(target, autocommit=True) as c:
        c.execute('CREATE EXTENSION IF NOT EXISTS timescaledb')
        c.execute('SELECT timescaledb_pre_restore()')
    dump = subprocess.Popen(['docker', 'exec', container, 'pg_dump', '-U', user, '-Fc', source_name], stdout=subprocess.PIPE)
    try:
        subprocess.run(['docker', 'exec', '-i', container, 'pg_restore', '-U', user, '--no-owner', '--no-privileges', '-d', name], stdin=dump.stdout, check=True)
    finally:
        dump.stdout.close()
        if dump.wait():
            raise RuntimeError('Source dump failed; isolated clone is incomplete')
        with psycopg.connect(target, autocommit=True) as c:
            c.execute('SELECT timescaledb_post_restore()')
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(sql.SQL('COMMENT ON DATABASE {} IS {}').format(sql.Identifier(name), sql.Literal('span-isolated-demo-v1')))
    reset(target, name)
    path = ROOT / '.local' / f'{name}.env'
    path.parent.mkdir(exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(f'DATABASE_URL={target}\nSPAN_ISOLATED_DB={name}\n')
    print(json.dumps({'database': name, 'env_file': str(path)}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    new = sub.add_parser('create'); new.add_argument('--name', required=True)
    new.add_argument('--container', default='la-hacks-ai-2026-db-1')
    clean = sub.add_parser('reset'); clean.add_argument('--env', type=Path, required=True); clean.add_argument('--confirm', required=True)
    args = p.parse_args()
    if args.command == 'create':
        source = os.environ.get('DATABASE_URL') or dotenv_values(ROOT / 'backend/.env').get('DATABASE_URL')
        if not source:
            p.error('DATABASE_URL source is missing')
        create(source, args.name, args.container)
    else:
        url = dotenv_values(args.env).get('DATABASE_URL')
        if not url:
            p.error('Isolated env file has no DATABASE_URL')
        print(json.dumps({'reset': reset(url, args.confirm)}))


if __name__ == '__main__':
    main()
