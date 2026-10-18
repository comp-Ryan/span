"""Never run this suite against the shared development database or live providers."""
import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest

# Set before app modules capture default company arguments; don't depend on local .env.
os.environ['DEMO_COMPANY'] = 'company-020'
for name in ('GEMINI_API_KEY', 'PHOTON_API_KEY', 'SENTRY_DSN', 'AGENTVERSE_API_KEY', 'ELEVENLABS_API_KEY',
             'BROWSER_USE_API_KEY', 'VISA_USER_ID', 'VISA_PASSWORD'):
    os.environ[name] = ''
DB_FREE = {'test_voice.py', 'test_planner_conversation.py', 'test_solana_reference.py', 'test_call_smoke.py', 'test_reset_demo.py',
           'test_planner_workflow.py', 'test_demo_db.py'}


def pytest_collection_modifyitems(config, items):
    if all(Path(str(item.path)).name in DB_FREE for item in items):
        return
    url = os.environ.get('DATABASE_URL', '')
    parsed = urlsplit(url)
    if not parsed.path.lstrip('/').startswith('span_test_') or parsed.hostname not in ('localhost', '127.0.0.1'):
        raise pytest.UsageError('DB tests require an explicitly isolated local DATABASE_URL (span_test_*). Use scripts/demo_db.py create.')
    import psycopg
    with psycopg.connect(url, connect_timeout=3) as c:
        marker = c.execute("select shobj_description(oid,'pg_database') from pg_database where datname=current_database()").fetchone()[0]
        if marker != 'span-isolated-demo-v1':
            raise pytest.UsageError('Test database lacks the isolation marker; refusing to run.')
