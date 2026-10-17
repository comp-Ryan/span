"""Atomic human/timeout decisions with a durable action queue."""
import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from owed.config import settings
from owed.db import conn
from owed.events import emit

router = APIRouter()
log = logging.getLogger(__name__)


def request_decision(run_id, node_id, prompt, options, payload, timeout=None, default=None):
    decision_id = 'd-' + uuid4().hex
    deadline = datetime.now(UTC) + timedelta(seconds=timeout) if timeout else None
    with conn() as c:
        c.execute('''insert into decisions(decision_id,run_id,node_id,prompt,options,payload,deadline,default_option)
            values (%s,%s,%s,%s,%s,%s,%s,%s)''',
            (decision_id, run_id, node_id, prompt, Jsonb(options), Jsonb(jsonable_encoder(payload)), deadline, default))
        data = {'decision_id': decision_id, 'node_id': node_id, 'prompt': prompt,
                'options': options, 'auto_resolves_in_s': timeout}
        if default:
            data['default'] = default
        emit(run_id, 'decision', data, connection=c)
    return decision_id


class Choice(BaseModel):
    option_id: str
    note: str | None = Field(None, max_length=4000)


def resolve(decision_id, option, company, note=None):
    with conn() as c:
        row = c.execute('''select d.*,r.company_id from decisions d join runs r using(run_id)
            where d.decision_id=%s and r.company_id=%s for update of d''', (decision_id, company)).fetchone()
        if not row:
            raise HTTPException(404, 'Decision not found')
        if row['resolved']:
            if row['resolved'] != option:
                raise HTTPException(409, 'Decision has already been resolved')
            return {'decision_id': decision_id, 'resolved': option}
        if option not in {o['id'] for o in row['options']}:
            raise HTTPException(422, 'Invalid decision option')
        c.execute('update decisions set resolved=%s,resolved_at=now() where decision_id=%s', (option, decision_id))
        c.execute('insert into action_jobs(decision_id) values (%s) on conflict do nothing', (decision_id,))
        emit(row['run_id'], 'node.update', {'node_id': row['node_id'], 'data': {
            'decision_id': decision_id, 'resolved': option, 'note': note}}, connection=c)
    return {'decision_id': decision_id, 'resolved': option}


@router.post('/decisions/{decision_id}')
def choose(decision_id: str, body: Choice, company: str = settings.demo_company):
    return resolve(decision_id, body.option_id, company, body.note)


async def worker():
    while True:
        try:
            with conn() as c:
                expired = c.execute('''select d.decision_id,d.default_option,r.company_id from decisions d join runs r using(run_id)
                    where d.resolved is null and d.deadline<=now() and d.default_option is not null''').fetchall()
            for item in expired:
                try:
                    await asyncio.to_thread(resolve, item['decision_id'], item['default_option'], item['company_id'])
                except HTTPException as exc:
                    if exc.status_code != 409:
                        raise
            with conn() as c:
                job = c.execute('''update action_jobs set status='working',claimed_at=now() where decision_id=(
                    select decision_id from action_jobs where status='pending' or
                    (status='working' and claimed_at<now()-interval '5 minutes') order by created_at
                    for update skip locked limit 1) returning decision_id''').fetchone()
                row = c.execute('''select d.*,r.company_id from decisions d join runs r using(run_id)
                    where decision_id=%s''', (job['decision_id'],)).fetchone() if job else None
            if row:
                try:
                    from owed.actions import execute_decision
                    await execute_decision(row)
                except Exception:
                    log.exception('Decision action failed: %s', row['decision_id'])
                    await asyncio.to_thread(emit, row['run_id'], 'node.create', {'node_id': 'failed-' + row['decision_id'],
                        'type': 'action', 'title': 'Action could not complete', 'status': 'failed', 'parent': row['node_id'],
                        'data': {'error': 'Check channel configuration and retry the action.'}})
                    status = 'failed'
                else:
                    status = 'done'
                with conn() as c:
                    c.execute('update action_jobs set status=%s where decision_id=%s', (status, row['decision_id']))
        except Exception:
            log.exception('Decision worker iteration failed')
        await asyncio.sleep(.5)
