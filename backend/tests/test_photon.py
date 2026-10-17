import asyncio
import json
import httpx
from owed.channels.photon import Photon
from owed.config import settings


def test_photon_wire_format_and_idempotency(monkeypatch):
    monkeypatch.setattr(settings, 'photon_api_key', 'test-key')
    monkeypatch.setattr(settings, 'photon_project_id', 'test-project')
    monkeypatch.setattr(settings, 'photon_sms_sender_id', 'sender')
    requests=[]
    def handle(request):
        requests.append(request)
        assert request.headers['authorization'] == 'Bearer test-key'
        if request.url.path.endswith('/users'):
            return httpx.Response(200,json={'id':'recipient'})
        if request.url.path.endswith('/spaces'):
            assert json.loads(request.content)['participantIds'] == ['sender','recipient']
            return httpx.Response(200,json={'id':'space'})
        assert request.headers['idempotency-key']=='rem-test'
        assert json.loads(request.content)['content']=={'type':'text','format':'plain','text':'Please pay'}
        return httpx.Response(202,json={'id':'message','status':'dispatched'})
    result=asyncio.run(Photon(httpx.MockTransport(handle)).send('+15555550123','Please pay','sms','rem-test'))
    assert result['provider_message_id']=='message'
    assert len(requests)==3


def test_simulated_yes_actions_and_installment_payment(monkeypatch):
    from datetime import date
    from uuid import uuid4
    from uagents_core.envelope import Envelope
    from owed.actions import execute_decision, settle_negotiation, refresh_forecasts
    from owed.agents.protocol import counter
    from owed.agents import negotiation
    from owed.db import conn
    from owed.runs import create, replay_run
    from owed.runs.payroll import run_payroll, snapshot
    from owed.payments import post_pay
    from owed.finance import queries as q
    monkeypatch.setattr(settings, 'photon_api_key', '')
    monkeypatch.setattr(settings, 'gemini_api_key', '')
    monkeypatch.setattr(settings, 'scoring_interval_ms', 0)
    async def reply(address, proposal, **kwargs):
        with conn() as c:
            history = q.customer_history(c, proposal.company_id, proposal.customer_id, q.AS_OF_DEFAULT, limit=10000)
        envelope = Envelope(version=1, sender=address, target=address, session=uuid4(), schema_digest='test')
        envelope.encode_payload(counter(proposal, history).json())
        return envelope
    monkeypatch.setattr(negotiation, 'query', reply)
    rid = create('company-020', 'payroll two weeks', 'web', 'payroll_check', target_date=date(2026,10,20))
    try:
        asyncio.run(run_payroll(rid, 'company-020', date(2026,10,20)))
        with conn() as c:
            row = c.execute('select d.*,r.company_id from decisions d join runs r using(run_id) where d.run_id=%s', (rid,)).fetchone()
        row['resolved'] = 'chase_only'
        asyncio.run(execute_decision(row))
        events = replay_run(rid)['events']
        reminders = [e['data'] for e in events if e['event']=='node.create' and e['data'].get('data',{}).get('kind')=='reminder']
        assert len(reminders) == 3
        assert all(r['data']['channel']=='simulated' and r['data']['draft']['source']=='template' for r in reminders)
        assert len([e for e in events if e['data'].get('data',{}).get('kind')=='reply']) == 1
        with conn() as c:
            neg = c.execute('select * from negotiations where run_id=%s', (rid,)).fetchone()
            choice = c.execute("select d.*,r.company_id from decisions d join runs r using(run_id) where d.run_id=%s and payload->>'kind'='negotiation'", (rid,)).fetchone()
            # Prevent the separate local API worker racing this deterministic test.
            c.execute('update decisions set deadline=null where run_id=%s', (rid,))
        assert len(neg['rounds']) == 4
        choice['resolved'] = 'accept'
        asyncio.run(settle_negotiation(choice))
        with conn() as c:
            agreement = c.execute('select agreement from negotiations where negotiation_id=%s', (neg['negotiation_id'],)).fetchone()['agreement']
        assert len(agreement['installments']) == 2
        first = agreement['installments'][0]
        assert first['pay_link'].endswith(first['pay_token'])
        before = snapshot('company-020', date(2026,10,20))
        payment = post_pay(first['pay_token'], {'rail':'visa','card':{'number':'4111111111111111','exp_month':12,'exp_year':2028,'cvv':'123','name':'Demo customer'}})
        assert payment['receipt']['sandbox_mode']=='simulated'
        refresh_forecasts('company-020')
        assert round(snapshot('company-020',date(2026,10,20))['bank']-before['bank'],2)==first['amount']
        count_before = len([e for e in replay_run(rid)['events'] if e['data'].get('data',{}).get('kind')=='reminder'])
        asyncio.run(execute_decision(row))
        assert len([e for e in replay_run(rid)['events'] if e['data'].get('data',{}).get('kind')=='reminder'])==count_before
    finally:
        with conn() as c:
            c.execute('delete from forecast_payments where payment_id in (select payment_id from payments where pay_token in (select pay_token from pay_tokens where run_id=%s))', (rid,))
            c.execute('delete from payments where pay_token in (select pay_token from pay_tokens where run_id=%s)', (rid,))
            c.execute('delete from pay_tokens where run_id=%s', (rid,))
            c.execute('delete from reminders where run_id=%s', (rid,))
            c.execute('delete from negotiations where run_id=%s', (rid,))
            c.execute('delete from action_jobs where decision_id in (select decision_id from decisions where run_id=%s)', (rid,))
            c.execute('delete from decisions where run_id=%s', (rid,))
            c.execute('delete from events where run_id=%s', (rid,))
            c.execute('delete from runs where run_id=%s', (rid,))

        refresh_forecasts('company-020')
