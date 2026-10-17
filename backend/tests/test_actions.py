import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4

from fastapi import HTTPException
import pytest
from psycopg.types.json import Jsonb

from owed.actions import refresh_forecasts
from owed.agents.negotiation import policy
from owed.db import apply_runtime, conn
from owed.decisions import request_decision,resolve
from owed.events import emit
from owed.runs import create,replay_run
from owed.runs.payroll import snapshot


def test_policy_boundaries():
    history=[{'status':'paid'}]*8+[{'status':'written_off'}]*2
    assert policy(history,2,.05)[0]
    assert not policy(history,2,.051)[0]
    assert not policy(history[:-3]+[{'status':'written_off'}]*3,2,0)[0]
    assert not policy(history,2,0,disputed=True)[0]
    assert not policy([],2,0)[0]


def test_decision_race_only_queues_once():
    apply_runtime()
    rid=create('company-020','Decision race test','web','payroll_check')
    decision=request_decision(rid,'n5','Approve?', [{'id':'yes','label':'Yes'},{'id':'no','label':'No'}],{})
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            result=list(pool.map(lambda _:resolve(decision,'yes','company-020'),range(2)))
        assert result[0]==result[1]
        with pytest.raises(HTTPException) as exc:
            resolve(decision,'no','company-020')
        assert exc.value.status_code==409
        with conn() as c:
            assert c.execute('select count(*) n from action_jobs where decision_id=%s',(decision,)).fetchone()['n']==1
    finally:
        with conn() as c:
            c.execute('delete from action_jobs where decision_id=%s',(decision,))
            c.execute('delete from decisions where run_id=%s',(rid,))
            c.execute('delete from events where run_id=%s',(rid,))
            c.execute('delete from runs where run_id=%s',(rid,))


def test_payment_reforecast_does_not_double_count():
    before=snapshot('company-020',date(2026,10,9))
    invoice=before['scored'][0]
    amount=10
    payment='pay-test-'+uuid4().hex
    rid=create('company-020','payroll Friday','web','payroll_check')
    emit(rid,'node.create',{'node_id':'n3','type':'forecast','status':'done','parent':None})
    try:
        with conn() as c:
            c.execute("insert into payments(payment_id,company_id,invoice_id,rail,amount,paid_at,receipt) values (%s,'company-020',%s,'visa',%s,now(),%s)",(payment,invoice['invoice_id'],amount,Jsonb({'sandbox_mode':'simulated'})))
        after=snapshot('company-020',date(2026,10,9))
        assert round(after['bank']-before['bank'],2)==amount
        assert round(before['forecast']['owed_total']-after['forecast']['owed_total'],2)==amount
        assert round(after['forecast']['cash_at_target']-before['forecast']['cash_at_target'],2)==round(amount*(1-invoice['p_paid_by_target']),2)
        refresh_forecasts('company-020')
        assert replay_run(rid)['events'][-1]['data']['data']['owed_total']==after['forecast']['owed_total']
    finally:
        with conn() as c:
            c.execute('delete from payments where payment_id=%s',(payment,))
            c.execute('delete from events where run_id=%s',(rid,))
            c.execute('delete from runs where run_id=%s',(rid,))
