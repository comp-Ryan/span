"""Run persistence and replay, shared by all entry channels."""
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from owed.config import settings
from owed.db import conn
from owed.events import emit, envelope

router = APIRouter()


def require_company(company):
    with conn() as c:
        row = c.execute('select * from companies where company_id=%s', (company,)).fetchone()
    if not row:
        raise HTTPException(404, 'Company not found')
    return row


def create(company, question, source, intent):
    require_company(company)
    run_id = 'run-' + uuid4().hex
    with conn() as c:
        c.execute('''insert into runs(run_id,company_id,question,source,intent)
                     values (%s,%s,%s,%s,%s)''', (run_id, company, question, source, intent))
    emit(run_id, 'run.start', {'question': question, 'source': source})
    return run_id


def finish(run_id, status='open'):
    with conn() as c:
        c.execute('update runs set status=%s, ended_at=now() where run_id=%s', (status, run_id))
    emit(run_id, 'run.end', {'status': status})


@router.get('/runs')
def list_runs(company: str = settings.demo_company):
    require_company(company)
    with conn() as c:
        rows = c.execute('''select run_id,question,source,started_at,status,answer_title,report_id
                            from runs where company_id=%s order by started_at desc''', (company,)).fetchall()
    return {'runs': rows}


@router.get('/runs/{run_id}')
def replay_run(run_id: str, company: str = settings.demo_company):
    with conn() as c:
        run = c.execute('select run_id from runs where run_id=%s and company_id=%s', (run_id, company)).fetchone()
        if not run:
            raise HTTPException(404, 'Run not found')
        rows = c.execute('select * from events where run_id=%s order by id', (run_id,)).fetchall()
    return {'run_id': run_id, 'events': [{'event': r['event'], 'data': envelope(r)} for r in rows]}
