"""Customer agents are explicitly simulated from dataset history."""
from uagents import Model


class Proposal(Model):
    company_id: str
    customer_id: str
    amount: float
    installments: int = 1
    discount: float = 0
    round: int = 1


class Counter(Model):
    installments: int
    discount: float
    accepted: bool
    text: str


def counter(proposal, history):
    if proposal.round > 4 or proposal.discount > .05 or proposal.installments not in (1, 2):
        return Counter(installments=1, discount=0, accepted=False, text='Please ask the owner to review these terms.')
    paid = [r for r in history if r['status'] == 'paid']
    settled = [r for r in history if r['status'] in ('paid', 'written_off')]
    rate = len(paid) / len(settled) if settled else 0
    wants_split = rate >= .8
    accepted = proposal.installments == (2 if wants_split else 1)
    return Counter(installments=2 if wants_split else 1, discount=0, accepted=accepted,
                   text='I can pay half now and half in two weeks.' if wants_split else 'I need the owner to contact me about payment.')
