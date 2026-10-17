"""Capture an actual bills reconciliation as a local Sentry trace; no account required.
Run from backend: .venv/bin/python scripts/audit_forecast.py before|after
"""
import json
import sys
from datetime import date
from pathlib import Path

import sentry_sdk
from sentry_sdk.transport import Transport

from owed.db import conn
from owed.finance import queries as q

class Capture(Transport):
    def capture_envelope(self,envelope):
        for item in envelope.items:
            if item.headers.get('type')=='transaction':
                records.append(item.payload.json)

records=[]
sentry_sdk.init(dsn='http://local@localhost/1',transport=Capture,traces_sample_rate=1.0,
                default_integrations=False,send_default_pii=False)
with sentry_sdk.start_transaction(name='audit.payroll.bill_reconciliation',op='finance.audit') as transaction:
    with conn() as c:
        with sentry_sdk.start_span(op='finance.bills',name='forecast bills helper') as span:
            rows=q.bills_due(c,'company-020',q.AS_OF_DEFAULT,date(2026,10,20))
            reported=round(sum(max(0,q.f(r['open_amount'])) for r in rows),2)
            span.set_data('bills_total',reported)
        with sentry_sdk.start_span(op='finance.audit',name='reconcile all unpaid bills through target') as span:
            row=c.execute('''select sum(b.total_amount-coalesce(p.paid,0)) amount from bills b left join
                (select company_id,document_id,sum(amount) paid from bill_payment_applications group by company_id,document_id) p
                on p.company_id=b.company_id and p.document_id=b.id where b.company_id='company-020'
                and b.due_date<='2026-10-20' and b.txn_date<='2026-10-06' and b.total_amount-coalesce(p.paid,0)>0''').fetchone()
            actual=q.f(row['amount'])
            span.set_data('all_due_total',actual)
            span.set_data('excluded_liabilities',round(actual-reported,2))
    transaction.set_data('reported_bills',reported)
    transaction.set_data('actual_bills',actual)
    transaction.set_data('missing_bills',round(actual-reported,2))
    trace_id=transaction.trace_id
sentry_sdk.flush()
out=Path('../docs/submission') / ('sentry-bills-'+sys.argv[1]+'.json')
out.write_text(json.dumps({'capture':'local Sentry SDK transport; not uploaded to Sentry cloud','trace_id':trace_id,'reported':reported,'actual':actual,'missing':round(actual-reported,2),'transactions':records},indent=2,default=str)+'\n')
print({'trace_id':trace_id,'reported':reported,'actual':actual,'missing':round(actual-reported,2)})
