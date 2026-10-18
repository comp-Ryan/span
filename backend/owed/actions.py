"""Execute approved levers and recompute forecasts from runtime payment records."""
import asyncio
from datetime import date, timedelta
from decimal import Decimal

from psycopg.types.json import Jsonb

from owed.channels.photon import send_reminder, simulated_reply
from owed.db import conn
from owed.events import emit
from owed.finance import queries as q
from owed.runs import finish
from owed.runs.payroll import snapshot, target_for


def approved_levers(row):
    with conn() as c:
        events=c.execute("select data from events where run_id=%s and event='node.update' and data->'data' ? 'levers' order by id desc limit 1",(row['run_id'],)).fetchone()
    return events['data']['data']['levers'] if events else []


async def execute_decision(row):
    option=row['resolved']
    payload=row['payload'] or {}
    run_id,company,parent=row['run_id'],row['company_id'],row['node_id']
    if payload.get('kind')=='negotiation':
        return await settle_negotiation(row)
    if option in ('no','decline','call'):
        await asyncio.to_thread(emit,run_id,'node.create',{'node_id':'action-'+row['decision_id'],'type':'action',
            'title':'Owner follow-up requested' if option=='call' else 'No actions taken','status':'done','parent':parent})
        if not payload.get('kind'):
            await asyncio.to_thread(close_run,run_id)
        return
    if payload.get('kind')=='send_message':
        await send_reminder(run_id,company,payload['invoice_id'],parent,operation_id=row['decision_id'])
        return
    if payload.get('kind')=='defer_bill':
        await asyncio.to_thread(defer_bill,run_id,company,payload['bill_id'],parent,row['decision_id'])
        return
    sent = []
    keep = payload.get('selected_customers')
    for lever in approved_levers(row):
        if lever['id']=='chase':
            for target in lever['targets']:
                if keep is not None and target['customer_id'] not in keep:
                    continue
                sent.append(await send_reminder(run_id,company,target['invoice_id'],parent,operation_id=row['decision_id']+'-'+target['invoice_id']))
        elif lever['id']=='defer_bill' and option=='yes':
            await asyncio.to_thread(defer_bill,run_id,company,lever['bill_id'],parent,row['decision_id'])
        elif lever['id']=='hold_draw' and option=='yes':
            await asyncio.to_thread(hold_draw,run_id,company,parent,row['decision_id'])
    await asyncio.to_thread(refresh_forecasts,company)
    # The owner has decided: the question is answered and its report can be written. Replies, negotiations
    # and payments keep landing on the same run afterwards (the report is rebuilt from events on every open).
    await asyncio.to_thread(close_run,run_id)
    for reminder in sent:  # each disclosed simulated customer answers its own reminder
        await simulated_reply(run_id, company, reminder)


def close_run(run_id):
    with conn() as c:
        status=c.execute('select status from runs where run_id=%s',(run_id,)).fetchone()
    if status and status['status']=='open':
        finish(run_id,'closed')


def defer_bill(run_id,company,bill_id,parent,operation_id):
    with conn() as c:
        row=c.execute('''select b.*, (select avg(p.txn_date-bb.due_date) from bill_payments p
            join bill_payment_applications a on a.company_id=p.company_id and a.payment_id=p.id
            join bills bb on bb.company_id=a.company_id and bb.id=a.document_id
            where bb.company_id=b.company_id and bb.vendor_id=b.vendor_id) tolerance
            from bills b where b.company_id=%s and b.id=%s''',(company,bill_id)).fetchone()
        if not row or q.f(row['tolerance'])<7:
            raise ValueError('Vendor payment history does not support this deferral')
        new_date=max(row['due_date'],q.AS_OF_DEFAULT)+timedelta(days=8)
        c.execute('''insert into bill_deferrals(company_id,bill_id,due_date,run_id) values (%s,%s,%s,%s)
            on conflict(company_id,bill_id) do update set due_date=excluded.due_date,run_id=excluded.run_id''',(company,bill_id,new_date,run_id))
        emit(run_id,'node.create',{'node_id':'defer-'+operation_id+'-'+bill_id,'type':'action',
            'title':'Bill rescheduled in the cash plan','status':'done','parent':parent,
            'data':{'kind':'defer_bill','bill_id':bill_id,'due_date':new_date.isoformat(),
            'vendor_confirmed':False,'note':'Owner-approved schedule change; vendor agreement has not been obtained.'}},connection=c)
    refresh_forecasts(company)


def hold_draw(run_id,company,parent,operation_id):
    with conn() as c:
        amount=q.owner_draw(c,company,q.AS_OF_DEFAULT)
        if amount<=0:
            raise ValueError('No recurring owner draw exists in the books')
        c.execute('insert into draw_holds(company_id,run_id,amount) values (%s,%s,%s) on conflict(company_id) do nothing',(company,run_id,amount))
        emit(run_id,'node.create',{'node_id':'draw-'+operation_id,'type':'action','title':'Owner draw held in cash plan','status':'done','parent':parent,
            'data':{'kind':'hold_draw','amount':amount}},connection=c)
    refresh_forecasts(company)


async def settle_negotiation(row):
    payload=row['payload']
    with conn() as c:
        neg=c.execute('select * from negotiations where negotiation_id=%s and company_id=%s for update',
            (payload['negotiation_id'],row['company_id'])).fetchone()
        if neg['status']=='agreed':
            return
        if row['resolved']!='accept':
            c.execute('update negotiations set status=%s where negotiation_id=%s',('declined' if row['resolved']=='decline' else 'escalated',neg['negotiation_id']))
            emit(row['run_id'],'node.update',{'node_id':row['node_id'],'status':'done','data':{'result':row['resolved']}},connection=c)
            return
        from owed.agents.negotiation import policy
        from owed.payments import create_pay_token
        invoice=c.execute('select * from invoice_facts where company_id=%s and invoice_id=%s',(row['company_id'],neg['invoice_id'])).fetchone()
        history=q.customer_history(c,row['company_id'],invoice['customer_id'],q.AS_OF_DEFAULT,limit=10000)
        allowed,_=policy(history,payload['installments'],payload['discount'])
        if not allowed:
            raise ValueError('Owner policy rejects these terms')
        paid=c.execute('select coalesce(sum(amount),0) amount from payments where company_id=%s and invoice_id=%s',(row['company_id'],neg['invoice_id'])).fetchone()['amount']
        total=((invoice['open_balance']-paid)*(Decimal(1)-Decimal(str(payload['discount'])))).quantize(Decimal('.01'))
        count=payload['installments']; first=(total/count).quantize(Decimal('.01'))
        amounts=[first,total-first] if count==2 else [total]
        installments=[]
        for i,amount in enumerate(amounts):
            token=create_pay_token(c,row['company_id'],neg['invoice_id'],amount,run_id=row['run_id'],negotiation_id=neg['negotiation_id'])
            from owed.config import settings
            installments.append({'amount':float(amount),'due':(q.AS_OF_DEFAULT+timedelta(days=14*i)).isoformat(),
                                 'pay_token':token, 'pay_link':settings.public_base_url.rstrip('/')+'/pay/'+token})
        agreement={'installments':installments}
        c.execute("update negotiations set status='agreed',agreement=%s where negotiation_id=%s",(Jsonb(agreement),neg['negotiation_id']))
        emit(row['run_id'],'node.update',{'node_id':row['node_id'],'status':'waiting','data':{'agreement':agreement}},connection=c)
    await asyncio.to_thread(emit,row['run_id'],'speech',{'text':'The simulated customer agent agreed to the payment plan. The installment links are ready.','audio_url':None})


def refresh_forecasts(company):
    with conn() as c:
        runs=c.execute('''select r.run_id,r.question,r.target_date,r.excluded_customer_id from runs r where r.company_id=%s and exists
            (select 1 from events e where e.run_id=r.run_id and e.event='node.create' and e.data->>'type'='forecast')''',(company,)).fetchall()
    for run in runs:
        with conn() as c:
            nodes=c.execute("select data->>'node_id' node_id from events where run_id=%s and event='node.create' and data->>'type'='forecast'",(run['run_id'],)).fetchall()
        for node in nodes:
            with conn() as c:
                previous=c.execute("""select data->'data' data from events where run_id=%s
                    and data->>'node_id'=%s and data->'data' ? 'cash_at_target' order by id desc limit 1""",
                    (run['run_id'],node['node_id'])).fetchone()
            assumptions = previous['data'] if previous else {}
            target = date.fromisoformat(assumptions['target_date']) if assumptions.get('target_date') else run['target_date'] or target_for(run['question'])
            snap=snapshot(company,target,assumptions.get('excluded_customer_id',run['excluded_customer_id']),assumptions.get('assumed_customer_id'))
            from owed.finance.history import emit_forecast
            emit_forecast(run['run_id'],node['node_id'],snap)



async def payment_worker():
    while True:
        try:
            with conn() as c:
                job=c.execute('''select p.payment_id,p.company_id from payments p left join forecast_payments f using(payment_id)
                    where f.payment_id is null order by p.paid_at limit 1''').fetchone()
            if job:
                await asyncio.to_thread(refresh_forecasts,job['company_id'])
                with conn() as c:
                    c.execute('insert into forecast_payments(payment_id) values (%s) on conflict do nothing',(job['payment_id'],))
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Payment forecast refresh failed')
        await asyncio.sleep(.5)
