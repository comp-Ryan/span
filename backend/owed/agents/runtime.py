"""Run: python -m owed.agents.runtime. Separate uAgents for Owed and each customer."""
import asyncio
import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from uagents import Agent, Bureau, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
    chat_protocol_spec,
)
from uagents_core.registration import AgentRegistrationPolicy, BatchRegistrationPolicy
from uagents_core.utils.registration import RegistrationRequestCredentials, register_chat_agent

from owed.agents.protocol import Counter, Proposal, counter
from owed.config import settings
from owed.db import apply_runtime, conn
from owed.finance import queries as q


class LocalOnly(AgentRegistrationPolicy):
    async def register(self, *args, **kwargs):
        return None


class LocalBatch(BatchRegistrationPolicy):
    async def register(self):
        return None

    def add_agent(self, *args, **kwargs):
        return None


def seed_for(customer=None):
    if not settings.agent_seed:
        raise ValueError('AGENT_SEED is required (stable private seed for agent identities)')
    return hashlib.sha256(f'{settings.agent_seed}:{settings.demo_company}:{customer or "owed"}'.encode()).hexdigest()


def customer_agent(customer_id):
    agent = Agent(name='customer-' + customer_id, seed=seed_for(customer_id),
                  registration_policy=None if settings.agentverse_api_key else LocalOnly(),
                  publish_agent_details=bool(settings.agentverse_api_key), enable_agent_inspector=False)

    @agent.on_message(model=Proposal, replies={Counter}, allow_unverified=True)
    async def handle(ctx: Context, sender: str, message: Proposal):
        if message.company_id != settings.demo_company or message.customer_id != customer_id:
            return
        with conn() as c:
            history = q.customer_history(c, message.company_id, customer_id, q.AS_OF_DEFAULT, limit=10000)
        await ctx.send(sender, counter(message, history))
    return agent


def build():
    apply_runtime()
    owed = Agent(name='owed-agent', seed=seed_for(),
                 registration_policy=None if settings.agentverse_api_key else LocalOnly(),
                 publish_agent_details=bool(settings.agentverse_api_key), enable_agent_inspector=False)
    chat = Protocol(spec=chat_protocol_spec)

    @chat.on_message(ChatMessage)
    async def handle_chat(ctx: Context, sender: str, message: ChatMessage):
        await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(UTC), acknowledged_msg_id=message.msg_id))
        question = ' '.join(part.text for part in message.content if isinstance(part, TextContent))
        if not question.strip():
            return
        async with httpx.AsyncClient(base_url=settings.internal_api_url, timeout=30) as client:
            response = await client.post('/ask', params={'company': settings.demo_company}, json={'question': question, 'source': 'asi_one'})
            response.raise_for_status()
            run_id = response.json()['run_id']
            answer = 'Your workflow is running.'
            for _ in range(45):
                replay = await client.get('/runs/' + run_id, params={'company': settings.demo_company})
                events = replay.json()['events']
                found = [e['data'] for e in events if e['event']=='node.create' and e['data'].get('type')=='answer']
                if found:
                    answer = found[-1].get('data', {}).get('spoken', found[-1]['title'])
                    break
                await asyncio.sleep(1)
        await ctx.send(sender, ChatMessage(timestamp=datetime.now(UTC), msg_id=uuid4(),
            content=[TextContent(type='text', text=answer + f' Run: {run_id}'), EndSessionContent(type='end-session')]))

    @chat.on_message(ChatAcknowledgement)
    async def acknowledge(ctx: Context, sender: str, message: ChatAcknowledgement):
        pass

    owed.include(chat, publish_manifest=True)
    with conn() as c:
        customers = c.execute('select distinct customer_id from invoice_facts where company_id=%s and open_balance>0', (settings.demo_company,)).fetchall()
    agents = [owed]
    for row in customers:
        agent = customer_agent(row['customer_id'])
        agents.append(agent)
        with conn() as c:
            c.execute('''insert into customer_agents(company_id,customer_id,address) values (%s,%s,%s)
                on conflict(company_id,customer_id) do update set address=excluded.address''',
                (settings.demo_company, row['customer_id'], agent.address))
    if settings.agentverse_api_key:
        register_chat_agent(name='Owed — payroll and collections', endpoint=settings.agent_public_endpoint,
            active=True, credentials=RegistrationRequestCredentials(agent_seed_phrase=seed_for(), agentverse_api_key=settings.agentverse_api_key),
            readme='Ask whether payroll is covered, inspect real payment-history forecasts, and request collection actions. Customer agents are simulated from dataset history.')
    bureau = Bureau(agents=agents, registration_policy=None if settings.agentverse_api_key else LocalBatch(), port=settings.agent_port, endpoint=settings.agent_public_endpoint or f'http://127.0.0.1:{settings.agent_port}/submit')
    return bureau


if __name__ == '__main__':
    build().run()
