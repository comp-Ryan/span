# Owed API Contract v2

Single source of truth between the Paper frontend and the backend. Change this file before changing any endpoint.

- Base URL: dev `http://localhost:8000`, prod `https://api.<domain>` (domain bought at GoDaddy Sat hour one)
- All responses JSON, UTF-8. Money is a number in dollars with two decimals (e.g. `776.10`). Dates are ISO `YYYY-MM-DD`; timestamps ISO 8601 with timezone.
- Company selection: query param `company` (e.g. `company-001`). If omitted, the server's `DEMO_COMPANY` is used.
- Errors: HTTP 4xx/5xx with `{ "error": { "code": "string", "message": "string" } }`.
- CORS open for the production domain, `*.paper.design`, and `localhost`.

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
  "audio_url": "https://api.<domain>/audio/brief-company-001-2026-10-06.mp3"
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
- `status`: `"open" | "working" | "sent" | "replied" | "negotiating" | "agreed" | "pending_check" | "paid" | "dismissed"`.
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
{ "...item...", "status": "sent", "reminder": { "id": "rem-0001", "sent_at": "2026-10-17T18:40:00-07:00", "channel": "email", "pay_link": "https://<domain>/pay/tok_8f3a..." } }
```

## GET /pay/{token}
Payer-side page data (the customer opens the pay link).
```json
{ "company_name": "Hearthloaf Bakeries", "invoice": { "doc_number": "INV-2524", "amount": 776.10, "due_date": "2026-08-14" },
  "status": "unpaid", "payer_name": "Gallagher Apothecary Company" }
```

## POST /pay/{token}
Two rails. The pay page (Devin builds) shows both.
Visa sandbox card: `{ "rail": "visa", "card": { "number": "4111111111111111", "exp_month": 12, "exp_year": 2028, "cvv": "123", "name": "Gallagher AP" } }`
Solana devnet USDC (Tier 2): `{ "rail": "solana", "signature": "<tx signature from the payer's wallet>" }` — the backend verifies the transfer to the company's devnet address for the expected amount.
Response:
```json
{ "payment_id": "pay-0001", "status": "paid", "receipt": { "amount": 388.05, "paid_at": "2026-10-17T18:42:10-07:00", "rail": "visa", "last4": "1111", "sandbox": true } }
```
`GET /pay/{token}` additionally returns `"solana": { "recipient": "<devnet address>", "mint": "<devnet USDC mint>", "amount": 388.05 }`.
After this, the matching card's `status` becomes `"paid"` and an `events` message fires.

## GET /events?company=
Server-Sent Events. The frontend subscribes once. This stream IS the live action feed on the right side of the screen, and it also drives card state. Every event has `id`, `ts`, `company_id`, and `card_id` (nullable).

```
event: feed
data: { "id": "ev-0001", "ts": "2026-10-17T18:40:00-07:00", "card_id": "card-inv-01524",
        "kind": "drafting", "text": "Drafting a firm reminder to Gallagher Apothecary (53 days late).", "actor": "owed" }

event: feed
data: { "kind": "sent", "text": "Sent by SMS and email via Photon.", "channel": "sms", "reminder_id": "rem-0001", "actor": "owed" }

event: feed
data: { "kind": "reply", "text": "Gallagher: \"Can we split this into two payments?\"", "classification": "wants_plan", "actor": "customer" }

event: feed
data: { "kind": "negotiation", "negotiation_id": "neg-0001", "round": 1, "from": "owed", "text": "Proposing full payment of $776.10 by Oct 24." }

event: feed
data: { "kind": "negotiation", "negotiation_id": "neg-0001", "round": 1, "from": "customer", "text": "Counter: two payments of $388.05, Oct 24 and Nov 7." }

event: feed
data: { "kind": "decision", "negotiation_id": "neg-0001", "text": "Accepting: Gallagher has paid 9 of 11 invoices; owner rules allow installments above 80%.",
        "options": [ { "id": "accept", "label": "Accept" }, { "id": "decline", "label": "Decline" }, { "id": "call", "label": "Call them" } ],
        "auto_resolves_in_s": 8, "actor": "owed" }

event: feed
data: { "kind": "pay_link", "text": "Two pay links issued.", "pay_links": ["https://<domain>/pay/tok_a", "https://<domain>/pay/tok_b"] }

event: card.updated
data: { "card_id": "card-inv-01524", "status": "paid", "receipt": { "amount": 388.05, "paid_at": "...", "rail": "visa", "last4": "1111" } }

event: brief.updated
data: { "headline": "...", "expected_in_30d": 21418.55 }

event: speech
data: { "text": "Gallagher agreed to two payments. The first just landed.", "audio_url": "https://api.<domain>/audio/ev-0042.mp3" }
```
- `kind` for `feed`: `"drafting" | "sent" | "reply" | "classified" | "negotiation" | "decision" | "pay_link" | "paid" | "portal" | "check_photo" | "error" | "info"`.
- `actor`: `"owed" | "customer" | "owner" | "system"`.
- A `decision` event with `options` renders one-tap buttons; the owner answers with `POST /decisions/{negotiation_id}`. If unanswered within `auto_resolves_in_s`, Owed proceeds with its own choice.

## POST /command?company=
The command box and the mic both land here. Returns immediately; work streams on `/events`.
Request: `{ "text": "chase everyone over 30 days", "source": "typed" | "voice" }`
Response:
```json
{ "command_id": "cmd-0001", "intent": "chase", "targets": ["inv-01524", "inv-01676", "inv-01677"], "summary": "Chasing 3 invoices over 30 days past due." }
```
Intents: `chase`, `chase_one`, `status`, `pause`, `accept_plan`, `decline_plan`, `call`, `ask`. Unknown text falls back to `ask` and streams an answer as `feed` events with `kind: "info"`.

## POST /decisions/{negotiation_id}?company=
Owner overrules or confirms a `decision` event.
Request: `{ "option_id": "accept" | "decline" | "call", "note": "optional" }`
Response: `{ "negotiation_id": "neg-0001", "status": "agreed" | "declined" | "escalated" }`

## GET /negotiations/{id}?company=
Full transcript for the drawer when a feed line is clicked.
```json
{ "id": "neg-0001", "card_id": "card-inv-01524", "status": "agreed", "customer_agent": "agent1q...", "owner_rules_applied": ["installments_if_paid_rate_ge_0.8"],
  "rounds": [ { "round": 1, "from": "owed", "text": "...", "ts": "..." }, { "round": 1, "from": "customer", "text": "...", "ts": "..." } ],
  "agreement": { "installments": [ { "amount": 388.05, "due": "2026-10-24", "pay_token": "tok_a" }, { "amount": 388.05, "due": "2026-11-07", "pay_token": "tok_b" } ] } }
```

## POST /inbound/photon
Photon webhook (server-to-server, not called by the frontend). Body is Photon's payload. Text replies are classified; MMS images go to StepFun (Tier 3) and produce a `check_photo` feed event.

## POST /voice/transcribe
Mic audio → text. Request: multipart `audio` (webm/opus). Response: `{ "text": "chase gallagher" }`. The frontend then calls `/command`. ElevenLabs speech for responses arrives as `speech` events.

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
{ "payment_model": { "trained_at": "2026-10-17T19:05:00-07:00", "holdout_days": 60, "n_companies": 86, "n_invoices_train": 118422,
                     "mae_days": 6.4, "auc_write_off": 0.81, "model": "gradient_boosted_trees" },
  "drafter": { "base": "Qwen/Qwen3-1.7B", "platform": "veri.studio", "method": "sft_text", "train_rows": 1800, "holdout_rows": 200,
               "json_valid_rate": 0.985, "judge_win_rate_vs_base": 0.74, "serving": "llama.cpp q4 on vultr" | "gemini_fallback" },
  "disclosures": ["Customer agents are simulated from each customer's payment history in the dataset.", "No dataset rows modified."] }
```

## GET /health
`{ "ok": true, "db": "tiger", "gemini": true, "drafter": "finetuned" | "gemini_fallback", "photon": true, "visa": "sandbox", "solana": "devnet", "agentverse": true, "jev": false }`

## Demo defaults
- Owner rules (server config, shown read-only in the footer): installments allowed if customer paid-rate ≥ 0.8; max discount 5%; disputes escalate to owner; max 4 negotiation rounds.
- `DEMO_COMPANY=company-001` (Hearthloaf Bakeries, wholesale, has 1-30 and 31-60 aging) unless a distressed company reads better on the day.
- Visa sandbox test card: `4111 1111 1111 1111`, any future expiry, any CVV (confirm against Visa's sandbox docs in hour one).
