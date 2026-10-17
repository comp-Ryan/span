"""Durable event bus. Database-backed fan-out also works across API workers."""
import asyncio
import json

from fastapi import APIRouter, Header, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from psycopg.types.json import Jsonb

from owed.config import settings
from owed.db import conn

router = APIRouter()


def envelope(row):
    return {**row['data'], 'id': str(row['id']), 'ts': row['ts'].isoformat(),
            'company_id': row['company_id'], 'run_id': row['run_id']}


def emit(run_id: str, event: str, data: dict) -> dict:
    with conn() as c:
        # Serialize allocation through commit so reconnect cursors cannot skip a late commit.
        c.execute('select pg_advisory_xact_lock(781204)')
        run = c.execute('select company_id from runs where run_id=%s', (run_id,)).fetchone()
        if not run:
            raise ValueError(f'Unknown run: {run_id}')
        row = c.execute('''insert into events(run_id,company_id,event,data) values (%s,%s,%s,%s)
                           returning *''', (run_id, run['company_id'], event,
                                           Jsonb(jsonable_encoder(data)))).fetchone()
    return envelope(row)


def read_events(company: str, after: int | None = None, limit: int = 500):
    with conn() as c:
        if after is None:
            rows = c.execute('''select * from (select * from events where company_id=%s
                                order by id desc limit %s) e order by id''', (company, limit)).fetchall()
        else:
            rows = c.execute('''select * from events where company_id=%s and id>%s
                                order by id limit %s''', (company, after, limit)).fetchall()
    return rows


def frame(row):
    return f"id: {row['id']}\nevent: {row['event']}\ndata: {json.dumps(envelope(row))}\n\n"


@router.get('/events')
async def subscribe(request: Request, company: str = settings.demo_company,
                    last_event_id: str | None = Header(None), replay: int = Query(500, ge=1, le=5000)):
    from owed.runs import require_company
    await asyncio.to_thread(require_company, company)
    try:
        cursor = int(last_event_id) if last_event_id else None
        if cursor is not None and cursor < 0:
            raise ValueError()
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(400, 'Last-Event-ID must be a nonnegative integer')

    async def stream():
        nonlocal cursor
        # Capture a high-water mark even on an empty initial replay.
        rows = await asyncio.to_thread(read_events, company, cursor, replay)
        if cursor is None:
            cursor = 0
        for row in rows:
            cursor = row['id']
            yield frame(row)
        idle = 0
        while not await request.is_disconnected():
            rows = await asyncio.to_thread(read_events, company, cursor)
            for row in rows:
                cursor = row['id']
                yield frame(row)
            idle = 0 if rows else idle + 1
            if idle >= 60:
                yield ': heartbeat\n\n'
                idle = 0
            await asyncio.sleep(0.25)

    return StreamingResponse(stream(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
