"""Four-message negotiation with simulated customer uAgents and owner policy gates."""
import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb
from uagents.query import query
from uagents.resolver import RulesBasedResolver
from uagents_core.envelope import Envelope

from owed.agents.protocol import Counter, Proposal
from owed.config import settings
from owed.db import conn
from owed.decisions import request_decision
from owed.events import emit
from owed.finance import queries as q

router = APIRouter()


def policy(history, installments, discount, disputed=False):
    settled = [r for r in history if r['status'] in ('paid','written_off')]
    rate = sum(r['status']=='paid' for r in settled) / len(settled) if settled else 0
    return not disputed and 0 <= discount <= .05 and installments in (1,2) and (installments==1 or rate>=.8), rate


async def negotiate(run_id, company, invoice_id, parent):
    with conn() as c:
        invoice = c.execute('select * from invoice_facts where company_id=%s and invoice_id=%s', (company,invoice_id)).fetchone()
        if not invoice or invoice['open_balance']<=0:
            raise ValueError('Open invoice not found')
        history = q.customer_history(c,company,invoice['customer_id'],q.AS_OF_DEFAULT,limit=10000)
        agent = c.execute('select address from customer_agents where company_id=%s and customer_id=%s', (company,invoice['customer_id'])).fetchone()
        existing = c.execute('select negotiation_id from negotiations where run_id=%s and invoice_id=%s and status in (\'negotiating\',\'pending\',\'agreed\')', (run_id,invoice_id)).fetchone()
        if existing:
            return existing['negotiation_id']
        neg = 'neg-' + uuid4().hex
        c.execute("insert into negotiations(negotiation_id,run_id,company_id,invoice_id,status) values (%s,%s,%s,%s,'negotiating')", (neg,run_id,company,invoice_id))
    node = 'node-' + neg
    await asyncio.to_thread(emit,run_id,'node.create', {'node_id':node,'type':'action','title':'Negotiating with the simulated customer agent',
        'status':'running','parent':parent,'data':{'kind':'negotiation','negotiation_id':neg,'rounds':[]}})
    rounds=[]
    async def record(speaker,text,installments):
        _, rate=policy(history,installments,0)
        item={'n':len(rounds)+1,'from':speaker,'text':text,'cash_effect':round(-float(invoice['open_balance'])/2,2) if installments==2 else 0,'p_honored':round(rate,3)}
        rounds.append({**item,'round':item['n'],'ts':datetime.now(UTC).isoformat()})
        with conn() as c:
            c.execute('update negotiations set rounds=%s where negotiation_id=%s',(Jsonb(rounds),neg))
        await asyncio.to_thread(emit,run_id,'node.update',{'node_id':node,'data':{'round':item}})
    try:
        if not agent:
            raise ValueError('Customer uAgent is not running')
        installments,discount=1,0
        accepted=False
        for round_number in range(1,3):
            proposal=Proposal(company_id=company,customer_id=invoice['customer_id'],amount=float(invoice['open_balance']),installments=installments,discount=discount,round=round_number)
            await record('owed',f'Propose {installments} payment(s), {discount:.0%} discount.',installments)
            response=await query(agent['address'],proposal,resolver=RulesBasedResolver({agent['address']:settings.customer_agent_endpoint}),timeout=10)
            if not isinstance(response,Envelope):
                raise TypeError('Customer agent did not respond')
            reply=Counter.parse_raw(response.decode_payload())
            await record('customer',reply.text,reply.installments)
            allowed,rate=policy(history,reply.installments,reply.discount)
            if not allowed:
                break
            installments,discount=reply.installments,reply.discount
            if reply.accepted:
                accepted=True
                break
        allowed,rate=policy(history,installments,discount)
        auto=accepted and allowed
        options=[{'id':'accept','label':'Accept'},{'id':'decline','label':'Decline'},{'id':'call','label':'Call them'}] if auto else [{'id':'decline','label':'Decline'},{'id':'call','label':'Call them'}]
        request_decision(run_id,node,f'Accept {installments} installment(s)? Paid rate on settled history: {rate:.0%}.',options,
            {'kind':'negotiation','negotiation_id':neg,'invoice_id':invoice_id,'installments':installments,'discount':discount},timeout=8 if auto else None,default='accept' if auto else None)
        with conn() as c:
            c.execute("update negotiations set status='pending' where negotiation_id=%s",(neg,))
        await asyncio.to_thread(emit,run_id,'node.update',{'node_id':node,'status':'waiting'})
    except Exception:
        with conn() as c:
            c.execute("update negotiations set status='failed' where negotiation_id=%s",(neg,))
        await asyncio.to_thread(emit,run_id,'node.update',{'node_id':node,'status':'failed','data':{'error':'Customer agent unavailable; owner follow-up required.'}})
        raise
    return neg


@router.get('/negotiations/{negotiation_id}')
def transcript(negotiation_id: str,company: str=settings.demo_company):
    with conn() as c:
        row=c.execute('select * from negotiations where negotiation_id=%s and company_id=%s',(negotiation_id,company)).fetchone()
        if not row:
            raise HTTPException(404,'Negotiation not found')
        agent=c.execute('''select a.address from customer_agents a join invoice_facts f on f.company_id=a.company_id and f.customer_id=a.customer_id
            where f.company_id=%s and f.invoice_id=%s''',(company,row['invoice_id'])).fetchone()
    return {'id':negotiation_id,'card_id':'card-'+row['invoice_id'],'status':row['status'],'customer_agent':agent['address'] if agent else None,
            'owner_rules_applied':['installments_if_paid_rate_ge_0.8','max_discount_0.05','max_4_rounds'], 'rounds':row['rounds'],'agreement':row['agreement']}
