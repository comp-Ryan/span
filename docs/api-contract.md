# Veri API Contract v1

Single source of truth between the Paper frontend and the backend. Change this file before changing any endpoint.

- Base URL: dev `http://localhost:8000`, prod `https://api.veri.studio`
- All responses JSON, UTF-8. Money is a number in dollars with two decimals (e.g. `776.10`). Dates are ISO `YYYY-MM-DD`; timestamps ISO 8601 with timezone.
- Company selection: query param `company` (e.g. `company-001`). If omitted, the server's `DEMO_COMPANY` is used.
- Errors: HTTP 4xx/5xx with `{ "error": { "code": "string", "message": "string" } }`.
- CORS open for `veri.studio`, `*.paper.design`, and `localhost`.

## GET /companies
Companies available for the demo (POS companies excluded, they have no invoices).
```json
{ "companies": [
  { "id": "company-001", "name": "Hearthloaf Bakeries", "profile": "wholesale", "distressed": false,
    "owed_total": 26128.87, "overdue_total": 5098.37 }
]}
```

## GET /brief?company=
The top of the screen.
```json
{
  "company": { "id": "company-001", "name": "Hearthloaf Bakeries", "profile": "wholesale" },
  "as_of": "2026-10-06",
  "headline": "You'll collect about $21k of the $26k you're owed this month. Gallagher Apothecary is 53 days late and has paid late on 9 of 11 invoices.",
  "owed_total": 26128.87,
  "overdue_total": 5098.37,
  "expected_in_30d": 21030.50,
  "benchmark": { "dso_days": 34, "peer_median_dso_days": 23, "peer_profile": "wholesale", "peer_count": 21 },
  "audio_url": "https://api.veri.studio/audio/brief-company-001-2026-10-06.mp3"
}
```
`benchmark` and `audio_url` may be `null`.

## GET /cards?company=
At most three. Ordered by priority. This is the center of the screen.
```json
{ "cards": [ {
  "id": "card-inv-01524",
  "kind": "chase",
  "status": "open",
  "customer": { "id": "cust-customer-12", "name": "Gallagher Apothecary Company", "email": "ap@gallagher.example", "phone": "(555) 201-8844", "terms": "Net 30" },
  "invoice": { "id": "inv-01524", "doc_number": "INV-2524", "amount": 776.10, "issued": "2026-07-15", "due_date": "2026-08-14", "days_past_due": 53 },
  "reason": "Paid late on 9 of 11 invoices, median 18 days. This one is 53 days late, far outside their pattern.",
  "history": [
    { "invoice_id": "inv-00231", "amount": 640.00, "due_date": "2025-12-01", "days_late": 12, "paid": true },
    { "invoice_id": "inv-00412", "amount": 702.50, "due_date": "2026-01-10", "days_late": 21, "paid": true }
  ],
  "prediction": { "expected_pay_date": "2026-10-20", "p_never_pay": 0.18, "confidence": "medium" },
  "draft": {
    "channel": "email",
    "subject": "Invoice INV-2524 — 53 days past due",
    "body": "Hi Gallagher team, ...",
    "tone": "firm"
  },
  "action": { "type": "send_reminder", "label": "Send reminder" }
} ] }
```
- `kind`: `"chase"` or `"write_off"`. For `write_off`, `action.type` is `"call"` or `"write_off"` and `draft` is a call script.
- `status`: `"open" | "sent" | "paid" | "dismissed"`.
- `history`: oldest first, max 24 entries, `days_late` may be negative (paid early). The dot chart is drawn from this.
- `tone`: `"friendly" | "firm" | "final"`.

## GET /queue?company=
Every other overdue invoice, with drafts. Same item shape as a card but without `history`.
```json
{ "items": [ { "...card fields minus history..." } ], "remaining": 7 }
```

## POST /queue/{invoice_id}?company=
Act on a queue item or card.
Request: `{ "action": "send" | "skip" | "edit" | "dismiss", "body": "optional edited draft text" }`
Response: the updated item (same shape as a queue item) plus, when sent:
```json
{ "...item...", "status": "sent", "reminder": { "id": "rem-0001", "sent_at": "2026-10-17T18:40:00-07:00", "channel": "email", "pay_link": "https://veri.studio/pay/tok_8f3a..." } }
```

## GET /pay/{token}
Payer-side page data (the customer opens the pay link).
```json
{ "company_name": "Hearthloaf Bakeries", "invoice": { "doc_number": "INV-2524", "amount": 776.10, "due_date": "2026-08-14" },
  "status": "unpaid", "payer_name": "Gallagher Apothecary Company" }
```

## POST /pay/{token}
Run a Visa sandbox tokenized payment.
Request: `{ "card": { "number": "4111111111111111", "exp_month": 12, "exp_year": 2028, "cvv": "123", "name": "Gallagher AP" } }`
Response:
```json
{ "payment_id": "pay-0001", "status": "paid", "receipt": { "amount": 776.10, "paid_at": "2026-10-17T18:42:10-07:00", "last4": "1111", "network": "visa", "sandbox": true } }
```
After this, the matching card's `status` becomes `"paid"` and an `events` message fires.

## GET /events?company=
Server-Sent Events. The frontend subscribes once and flips cards live.
```
event: card.updated
data: { "card_id": "card-inv-01524", "status": "paid", "receipt": { "amount": 776.10, "paid_at": "...", "last4": "1111" } }

event: brief.updated
data: { "headline": "...", "expected_in_30d": 21806.60 }
```

## GET /cash?company=&top3_pay_this_week=false&never_pays=
Expected cash over the next 90 days from predicted pay dates minus payroll and bills due.
- `top3_pay_this_week`: boolean slider.
- `never_pays`: optional customer id slider ("if X never pays").
```json
{
  "start": "2026-10-06", "opening_balance": 104107.55,
  "days": [ { "date": "2026-10-06", "inflow": 0, "outflow": 1200.00, "balance": 102907.55 } ],
  "payroll_dates": ["2026-10-10", "2026-10-24"],
  "low_point": { "date": "2026-11-21", "balance": 61240.10 },
  "assumptions": { "top3_pay_this_week": false, "never_pays": null }
}
```

## POST /ask?company=
Streams an answer. Also the endpoint the Agentverse uAgent calls.
Request: `{ "question": "who should I chase today" }`
Response: SSE
```
event: token
data: { "text": "Chase " }
...
event: done
data: { "answer": "Chase Gallagher Apothecary first ...", "cards": ["card-inv-01524"], "sources": ["ar_aging", "customer_payments"] }
```

## GET /model/metrics
Shown in the footer and the write-up.
```json
{ "trained_at": "2026-10-17T19:05:00-07:00", "holdout_days": 60, "n_companies": 86, "n_invoices_train": 118422,
  "mae_days": 6.4, "auc_write_off": 0.81, "model": "gradient_boosted_trees" }
```

## GET /health
`{ "ok": true, "snowflake": true, "gemini": true, "visa": "sandbox", "jev": false }`

## Demo defaults
- `DEMO_COMPANY=company-001` (Hearthloaf Bakeries, wholesale, has 1-30 and 31-60 aging) unless a distressed company reads better on the day.
- Visa sandbox test card: `4111 1111 1111 1111`, any future expiry, any CVV (confirm against Visa's sandbox docs in hour one).
