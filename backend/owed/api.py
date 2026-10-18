"""Company selection, the home-page brief, and honest model metadata for the product shell."""
import json
from datetime import timedelta

from fastapi import APIRouter, HTTPException

from owed.config import settings
from owed.db import conn
from owed.finance import queries as q
from owed.finance.model import METRICS_PATH
from owed.runs.payroll import snapshot

router=APIRouter()

@router.get('/companies')
def companies():
    with conn() as c:
        rows=q.companies(c)
    return {'companies':[{'id':r['company_id'],'name':r['display_name'],'profile':r['profile'],
        'distressed':r['distressed'],'owed_total':q.f(r['owed_total']),'overdue_total':q.f(r['overdue_total'])} for r in rows]}

@router.get('/brief')
def brief(company: str = settings.demo_company):
    """Today's money picture for /home: contract fields plus the four stat tiles."""
    as_of = q.AS_OF_DEFAULT
    with conn() as c:
        row = next((r for r in q.companies(c) if r['company_id'] == company), None)
        if not row:
            raise HTTPException(404, 'unknown company')
        payroll = q.payroll_due(c, company, as_of, as_of + timedelta(days=14))
        bills = [b for b in q.bills_due(c, company, as_of, as_of + timedelta(days=7)) if q.f(b['open_amount']) > 0]
        benchmark = q.peer_dso(c, company)
    snap = snapshot(company, as_of + timedelta(days=30))
    fc = snap['forecast']
    expected_30d = fc['expected_by_target']
    owed_total, overdue = q.f(row['owed_total']), q.f(row['overdue_total'])
    late = max((r for r in snap['scored'] if q.f(r['days_past_due']) > 0), key=lambda r: q.f(r['open_balance']), default=None)
    headline = f"You'll collect about ${expected_30d:,.0f} of the ${owed_total:,.0f} you're owed this month."
    if late:
        headline += f" {late['customer_name']} is {int(q.f(late['days_past_due']))} days late on ${q.f(late['open_balance']):,.0f}."
    next_pay = next((p for p in payroll['schedule'] if payroll['next_pay_date'] and p['date'] == payroll['next_pay_date']), None)
    return {'company': {'id': company, 'name': row['display_name'], 'profile': row['profile']},
            'as_of': as_of.isoformat(), 'headline': headline,
            'owed_total': owed_total, 'overdue_total': overdue, 'expected_in_30d': expected_30d,
            'benchmark': {**benchmark, 'peer_profile': row['profile']} if benchmark else None, 'audio_url': None,
            'bank_balance': fc['bank_balance'], 'open_invoices': int(row['n_open']),
            'payroll_next': {'date': payroll['next_pay_date'].isoformat(), 'amount': next_pay['amount'] if next_pay else payroll['weekly'],
                             'headcount': payroll['headcount']} if payroll['next_pay_date'] else None,
            'bills_due_week': {'total': round(sum(q.f(b['open_amount']) for b in bills), 2), 'count': len(bills),
                               'through': (as_of + timedelta(days=7)).isoformat()}}

@router.get('/model/metrics')
def metrics():
    measured=json.loads(METRICS_PATH.read_text())
    return {'payment_model':{**measured,'mae_days':measured['mae_days_late'],'auc_write_off':measured['auc_write_off_cv5']},
        'drafter':{'base':None,'platform':None,'method':None,'train_rows':0,'holdout_rows':0,
                   'json_valid_rate':None,'judge_win_rate_vs_base':None,'serving':'template_fallback'},
        'disclosures':['Customer agents are simulated from dataset payment history.',
                       'Write-off AUC is five-fold cross-validation on 46 positive cases, not held-out AUC.',
                       'No raw dataset rows modified. Runtime payments are separate records.',
                       'No fine-tuned drafting model is installed yet.']}
