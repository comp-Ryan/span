"""Company selection and honest model metadata for the product shell."""
import json
from fastapi import APIRouter
from owed.db import conn
from owed.finance import queries as q
from owed.finance.model import METRICS_PATH

router=APIRouter()

@router.get('/companies')
def companies():
    with conn() as c:
        rows=q.companies(c)
    return {'companies':[{'id':r['company_id'],'name':r['display_name'],'profile':r['profile'],
        'distressed':r['distressed'],'owed_total':q.f(r['owed_total']),'overdue_total':q.f(r['overdue_total'])} for r in rows]}

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
