"""Persist each emitted forecast and its dated lines in one transaction, never on GET."""
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb

from owed.config import settings
from owed.db import conn
from owed.events import emit
from owed.runs import require_company

router = APIRouter()


def emit_forecast(run_id, node_id, snap, *, data=None, status=None, connection=None):
    from owed.finance.cash import projection
    forecast = {**snap['forecast'], **(data or {})}
    target = date.fromisoformat(forecast['target_date'])
    cash = projection(snap, target, forecast.get('excluded_customer_id'))

    def write(c):
        payload = {'node_id': node_id, 'data': forecast}
        if status:
            payload['status'] = status
        event = emit(run_id, 'node.update', payload, connection=c)
        fid = int(event['id'])
        forecast['forecast_id'] = str(fid)
        # Same event and transaction; SSE never sees a half-written history revision.
        c.execute('update events set data=%s where id=%s', (Jsonb(jsonable_encoder(payload)), fid))
        c.execute('''insert into forecast_history(forecast_id,company_id,run_id,node_id,target,forecast)
                     values (%s,%s,%s,%s,%s,%s)''',
                  (fid, event['company_id'], run_id, node_id, target, Jsonb(jsonable_encoder(forecast))))
        rows = [(event['company_id'], scenario, d['date'], d['inflow'], d['outflow'], d['balance'], fid)
                for scenario, days in [('expected', cash['days']), ('pessimistic', cash['pessimistic_days'])] for d in days]
        with c.cursor() as cur:
            cur.executemany('''insert into cash_projection(company_id,scenario,day,inflow,outflow,balance,forecast_id)
                               values (%s,%s,%s,%s,%s,%s,%s)''', rows)
        return forecast

    if connection is not None:
        return write(connection)
    with conn() as c:
        return write(c)


@router.get('/forecasts')
def history(company: str = settings.demo_company, run_id: str | None = None,
            limit: int = Query(20, ge=1, le=100)):
    require_company(company)
    with conn() as c:
        if run_id and not c.execute('select 1 from runs where run_id=%s and company_id=%s', (run_id, company)).fetchone():
            raise HTTPException(404, 'Run not found in this company')
        records = c.execute('''select * from forecast_history where company_id=%s
                               and (%s::text is null or run_id=%s)
                               order by forecast_id desc limit %s''', (company, run_id, run_id, limit)).fetchall()
        ids = [r['forecast_id'] for r in records]
        points = c.execute('''select forecast_id,scenario,day::text date,inflow,outflow,balance
                              from cash_projection where forecast_id=any(%s) and company_id=%s
                              order by day''', (ids, company)).fetchall() if ids else []
    grouped = {}
    for point in points:
        grouped.setdefault((point['forecast_id'], point['scenario']), []).append(
            {k: point[k] for k in ('date', 'inflow', 'outflow', 'balance')})
    return {'storage': 'timescaledb', 'forecasts': [
        {k: str(r[k]) if k == 'forecast_id' else r[k] for k in
         ('forecast_id', 'run_id', 'node_id', 'computed_at', 'target', 'forecast')} |
        {'days': grouped.get((r['forecast_id'], 'expected'), []),
         'pessimistic_days': grouped.get((r['forecast_id'], 'pessimistic'), [])}
        for r in reversed(records)]}


def cash_history(company, limit=30):
    """Compact company-wide series for the Home chart: one point per saved forecast, oldest first."""
    require_company(company)
    with conn() as c:
        rows = c.execute('''select forecast_id, run_id, node_id, computed_at, target, forecast from forecast_history
                            where company_id=%s order by forecast_id desc limit %s''', (company, limit)).fetchall()
    points = []
    for r in reversed(rows):
        f = r['forecast'] or {}
        points.append({'forecast_id': str(r['forecast_id']), 'run_id': r['run_id'], 'node_id': r['node_id'],
                       'computed_at': r['computed_at'], 'target': r['target'].isoformat(),
                       'cash_at_target': f.get('cash_at_target'), 'need': f.get('need'), 'gap': f.get('gap'),
                       'pessimistic_gap': (f.get('pessimistic') or {}).get('gap'),
                       'excluded_customer_id': f.get('excluded_customer_id'),
                       'assumed_customer_id': f.get('assumed_customer_id')})
    return {'storage': 'timescaledb', 'company': company, 'points': points}


@router.get('/cash/history')
def cash_history_route(company: str = settings.demo_company, limit: int = Query(30, ge=1, le=200)):
    return cash_history(company, limit)
