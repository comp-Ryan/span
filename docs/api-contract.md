# Owed API Contract v3 (workflow events)

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

## GET /brief?company=  (legacy; the canvas replaces it, keep for ASI:One text answers)
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

## GET /cards?company=  (legacy; superseded by `levers` node data)
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
Server-Sent Events. The frontend subscribes once. The stream draws the workflow canvas, drives decisions, carries speech, and announces reports. Every event JSON payload has `id` (string), `ts`, `company_id`, `run_id` (one run per question). SSE also sets `id:` for reconnects. On initial connect, replay the last `replay` events (default 500, max 5000), oldest first; `Last-Event-ID` instead replays all subsequent events for that company. Heartbeats are SSE comments.

```
event: run.start
data: { "run_id": "run-0001", "question": "Am I making payroll Friday?", "source": "call" | "sms" | "asi_one" | "web", "company_id": "company-001" }

event: node.create
data: { "run_id": "run-0001", "node_id": "n1", "type": "context", "title": "Pulling up context", "status": "running", "parent": null }

event: node.update
data: { "node_id": "n1", "status": "done",
        "data": { "company": "Hearthloaf Bakeries", "payroll_date": "2026-10-24", "payroll_amount": 18000.00, "bank_balance": 11000.00 } }

event: node.create
data: { "node_id": "n2", "type": "scoring", "title": "Scoring 23 open invoices", "status": "running", "parent": "n1" }

event: node.update
data: { "node_id": "n2", "progress": { "done": 7, "total": 23 },
        "row": { "invoice_id": "inv-01524", "customer": "Gallagher Apothecary", "amount": 776.10, "days_past_due": 53,
                 "p_paid_by_target": 0.62, "expected_pay_date": "2026-10-21", "p_never": 0.18, "band": "amber", "source": "jev" | "owed_model" } }
  (one node.update per invoice; the frontend appends rows and colors them by band)

event: node.create
data: { "node_id": "n3", "type": "forecast", "title": "Forecasting Friday", "status": "running", "parent": "n2" }
event: node.update
data: { "node_id": "n3", "status": "done", "data": { "owed_total": 26100.00, "expected_by_target": 4200.00, "bills_due_by_target": 3400.00, "cash_at_target": 11800.00, "need": 18000.00, "gap": 6200.00 } }

event: node.create
data: { "node_id": "n4", "type": "answer", "title": "No. $6,200 short.", "status": "done", "parent": "n3",
        "data": { "answer": "no", "gap": 6200.00, "spoken": "No. You're about six thousand two hundred short on Friday." } }

event: node.create
data: { "node_id": "n5", "type": "levers", "title": "What closes the gap", "status": "running", "parent": "n4" }
event: node.update
data: { "node_id": "n5", "status": "done", "data": { "levers": [
          { "id": "chase", "label": "Text 3 reliable late payers", "recovers": 6100.00,
            "targets": [ { "invoice_id": "inv-01524", "customer": "Gallagher Apothecary", "amount": 776.10, "reason": "53 days late, pays 9 of 11 times when reminded" } ] },
          { "id": "defer_bill", "label": "Slide Okonkwo bill 8 days", "recovers": 1400.00, "bill_id": "bill-00212", "vendor_tolerance": "high" },
          { "id": "hold_draw", "label": "Hold owner draw", "recovers": 2000.00 } ],
        "recommended": ["chase", "defer_bill"], "ask_spoken": "If I text Gallagher, Lowry and Mbeki and slide the Okonkwo bill a week, you clear it. Want me to text them?" } }

event: decision
data: { "run_id": "run-0001", "decision_id": "d1", "node_id": "n5", "prompt": "Text them?",
        "options": [ { "id": "yes", "label": "Yes, text them" }, { "id": "chase_only", "label": "Text, don't touch bills" }, { "id": "no", "label": "Not now" } ],
        "auto_resolves_in_s": null }

event: node.create
data: { "node_id": "n6", "type": "action", "title": "Texting Gallagher Apothecary", "status": "running", "parent": "n5",
        "data": { "kind": "reminder", "invoice_id": "inv-01524", "channel": "sms", "draft": { "body": "..." , "tone": "firm", "source": "qwen_veri" | "gemini" } } }
event: node.update
data: { "node_id": "n6", "status": "done", "data": { "sent_at": "...", "reminder_id": "rem-0001", "pay_link": "https://<domain>/pay/tok_a" } }

event: node.create
data: { "node_id": "n9", "type": "action", "title": "Gallagher replied", "status": "done", "parent": "n6",
        "data": { "kind": "reply", "text": "Can we split this into two?", "classification": "wants_plan" } }

event: node.create
data: { "node_id": "n10", "type": "action", "title": "Negotiating with Gallagher's agent", "status": "running", "parent": "n9",
        "data": { "kind": "negotiation", "negotiation_id": "neg-0001", "rounds": [] } }
event: node.update
data: { "node_id": "n10", "data": { "round": { "n": 1, "from": "owed" | "customer", "text": "..." , "cash_effect": -388.05, "p_honored": 0.81 } } }

event: decision
data: { "decision_id": "d2", "node_id": "n10", "prompt": "Accept two installments? (Gallagher has paid 9 of 11)",
        "options": [ {"id":"accept","label":"Accept"}, {"id":"decline","label":"Decline"}, {"id":"call","label":"Call them"} ], "auto_resolves_in_s": 8, "default": "accept" }

event: node.create
data: { "node_id": "n12", "type": "action", "title": "Gallagher paid $388.05", "status": "done", "parent": "n10",
        "data": { "kind": "payment", "rail": "visa" | "solana", "amount": 388.05, "receipt": { "last4": "1111", "paid_at": "..." } } }

event: node.update
data: { "node_id": "n3", "data": { "cash_at_target": 12188.05, "gap": 5811.95 } }
  (forecast node re-fires on every payment; the gap number ticks down)

event: speech
data: { "run_id": "run-0001", "text": "Gallagher agreed to two payments. The first just landed.", "audio_url": "https://api.<domain>/audio/ev-0042.mp3" }

event: report.ready
data: { "run_id": "run-0001", "report_id": "rep-0001", "url": "/reports/rep-0001" }

event: run.end
data: { "run_id": "run-0001", "status": "open" | "closed" }
```
- `speech.audio_url` may be `null` when TTS is not configured; text is still emitted.
- `type`: `"context" | "scoring" | "forecast" | "answer" | "levers" | "action"`. Six node types; the canvas needs no others.
- `status`: `"running" | "done" | "failed" | "waiting"`.
- `parent` defines edges. A node with `parent: null` is a root. Multiple children of one parent are siblings (branches).
- `decision` renders one-tap buttons on its node; answered via `POST /decisions/{decision_id}`. `auto_resolves_in_s: null` means wait for the human.
- Second-question runs (e.g. "should I take Gallagher's order?") use the same six types: context → scoring (one customer) → forecast (cash effect) → answer (green/amber/red in `data.verdict`) → levers (terms to offer) → action.

### Forecast and answer scenario fields
Forecast node data additionally includes `as_of`, `target_date`, and
`pessimistic: {expected_by_target, cash_at_target, gap}`. The pessimistic scenario
sets contribution to zero for every invoice with `p_paid_by_target < 0.7` and leaves
all other contributions probability-weighted. Bills, payroll, owner draw and bank
balance are identical in both scenarios. This is the same invoice-exclusion rule as `/cash`.
`cash_at_target` is **before payroll**, so the UI's surplus is `cash_at_target - need`,
and `gap = max(0, need - cash_at_target)`. `need` is payroll only; bills were already
subtracted from cash. The older `conservative` field is retained for compatibility;
new clients must use `pessimistic` (the old field uses band colors instead of 70%).
Context data includes `as_of`, `target_date`, `headcount`, and `bills_due_by_target`.
Answer titles explicitly report pessimistic shortfall, e.g. “Barely, and $X short if
the slow payers slip” when the expected scenario covers payroll but the pessimistic one does not.

## GET /runs?company=
Past and open runs for the sidebar. `{ "runs": [ { "run_id", "question", "source", "started_at", "status", "answer_title", "report_id" } ] }`

## GET /runs/{run_id}
Full replay: every event for the run in order. Used on page load so the canvas can redraw a run that happened while the page was closed. Optional `company` scopes the lookup (defaults to DEMO_COMPANY).
```json
{ "run_id": "run-0001", "events": [ { "event": "run.start", "data": { "id": "1", "ts": "2026-10-17T22:00:00+00:00", "company_id": "company-020", "run_id": "run-0001", "question": "Am I making payroll Friday?", "source": "web" } } ] }
```

## GET /reports/{report_id}
The generated one-page report as JSON the Paper template renders:
```json
{ "report_id": "rep-0001", "run_id": "run-0001", "generated_at": "...", "company": "Hearthloaf Bakeries",
  "question": "Am I making payroll Friday?", "answer": "No, $6,200 short at the time of asking; $5,812 short now.",
  "numbers": { "bank_balance": 11000.00, "payroll": 18000.00, "owed": 26100.00, "expected_by_target": 4200.00, "gap_then": 6200.00, "gap_now": 5811.95 },
  "workflow": { "nodes": [ { "id": "n1", "type": "context", "title": "Pulling up context", "status": "done", "parent": null, "data": { "...": "merged node.update data" } } ],
                "edges": [ { "from": "n1", "to": "n2" } ],
                "svg": "<svg ...>server-rendered workflow picture</svg>" },
  "actions": [ { "title": "Texted Gallagher Apothecary", "result": "Agreed to 2 installments; $388.05 paid" } ],
  "open_items": [ "Lowry & Daughters: no reply yet", "Okonkwo bill deferral pending owner confirmation" ],
  "narrative": "Two paragraphs written by the planner.",
  "disclosures": [ "Customer agents simulated from payment history", "Scoring by Jev" | "Scoring by Owed model (held-out MAE 6.4 days)" ],
  "pdf_url": "https://api.<domain>/reports/rep-0001.pdf" }
```
- Built by replaying the run's events. `workflow.nodes` are each `node.create` with every later `node.update` folded in: `status`/`title` replaced, `data` shallow-merged, scoring `row`s collected into `data.rows`, negotiation `round`s into `data.rounds`, `progress` into `data.progress`. `gap_then` is the first forecast `gap`, `gap_now` the latest.
- `POST /reports/generate?run_id=` builds and stores a report, sets `runs.report_id`, emits `report.ready`, and returns the report JSON (201). 404 if the run does not exist.
- `GET /reports/{report_id}.pdf` returns the same report as a one-page Letter PDF. `pdf_url` is prefixed with `PUBLIC_BASE_URL` (relative when unset).
- Sample replay of a full Palletbay payroll run: `backend/tests/fixtures/run_palletbay.json` (same shape as `GET /runs/{run_id}`).

## POST /decisions/{decision_id}?company=
Request: `{ "option_id": "yes", "note": "optional" }` → `{ "decision_id": "d1", "resolved": "yes" }`

## POST /ask?company=  (replaces /command)
Typed questions land here; calls and SMS land via the Photon webhook; ASI:One via the uAgent. All start a run. Returns immediately; the run streams on `/events`.
Request: `{ "question": "Am I making payroll Friday?", "source": "web" }`
Response:
```json
{ "run_id": "run-0001", "intent": "payroll_check", "target_date": "2026-10-24" }
```
Intents: `payroll_check`, `order_check`, `chase_today`, `afford_check`, `client_status`, `free_question`. Every intent produces a run with the same six node types.

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

## GET /cash?company=&target=&top3_pay_this_week=false&never_pays=
Dated cash projection from the dataset's “today” (`2026-10-06`) through `target`, inclusive.
`target` is ISO date; defaults to 90 days ahead; must be between today and today + 366 days.
Each day is an end-of-day balance **after payroll and bills**, unlike the forecast node's
`cash_at_target`, which is available cash **before payroll**.
- Expected receipts are residual invoice balance × `p_paid_by_target`, posted on the model's
  expected pay date. A receipt predicted after target is excluded (never pulled forward).
- `pessimistic_days` excludes invoices with `p_paid_by_target < 0.7`; others retain the same weighting.
- Payroll uses the trailing eight weeks' average per weekday, not calendar-day prorating.
  Bills use due dates (approved cash-plan deferrals override them); overdue unpaid bills fall on day one.
- Recorded runtime payments increase opening cash and reduce invoice balances, avoiding double-counting.
- `top3_pay_this_week=true` advances the three largest expected receipts to at most day seven.
  `never_pays` excludes that company-scoped customer's open invoices from both series (404 if none).
- Historical owner draw, when present and not held, is reserved at target; its timing is estimated.
- The forecast node's by-target classifier sum may differ from this point-date projection: the
  classifier can assign a chance of early payment to an invoice whose expected date is later.
```json
{
  "start": "2026-10-06", "target": "2026-10-20", "opening_balance": 6533.65,
  "days": [ { "date": "2026-10-06", "inflow": 0, "outflow": 1598.55, "balance": 4935.10 } ],
  "pessimistic_days": [ { "date": "2026-10-06", "inflow": 0, "outflow": 1598.55, "balance": 4935.10 } ],
  "payroll_dates": ["2026-10-07"],
  "low_point": { "date": "2026-10-06", "balance": 4935.10 },
  "pessimistic_low_point": { "date": "2026-10-06", "balance": 4935.10 },
  "assumptions": { "top3_pay_this_week": false, "never_pays": null, "pessimistic_threshold": 0.7,
    "clock": "dataset", "inflows": "probability_weighted_on_expected_date",
    "payroll": "trailing_8_week_weekday_average", "overdue_bills": "due_on_start", "owner_draw": "reserved_at_target" }
}
```
Both series have exactly one row per date; the abbreviated example omits subsequent rows.

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
- `DEMO_COMPANY=company-020` (Palletbay Storage & Warehousing).
- Visa sandbox test card: `4111 1111 1111 1111`, any future expiry, any CVV (confirm against Visa's sandbox docs in hour one).

## Voice transport (server-to-server)
`POST /voice/twiml` validates `X-Twilio-Signature` and returns TwiML connecting a bidirectional stream to `WS /voice/photon`.
Photon's published voice API exposes SIP destinations, not a bidirectional websocket; this endpoint currently implements the authorized Twilio fallback protocol.
Websocket messages follow Twilio Media Streams: `connected`, `start` (customParameters: `token`, `company`; mediaFormat: mono `audio/x-mulaw`, 8000 Hz), `media` (base64 payload), `stop`.
Backend sends `media` and `clear` (barge-in). Wrong credentials close with 1008; missing configuration closes with 1013.
Gemini native audio output transcription feeds ElevenLabs Flash v2.5. When ElevenLabs is unconfigured, Gemini native audio is used. Caller transcript fragments are `node.update.data.caller_text` on the call context node; Owed transcript fragments are `speech` events.

### Photon 2.0 callback setup
`POST /inbound/photon?token=<PHOTON_WEBHOOK_TOKEN>` accepts the provider event envelope with `data.id` or `data.message.id` identifying the message. The token can alternatively be sent as `X-Owed-Webhook-Token`. Until Beta signature headers are verified, this callback token plus an authenticated fetch of the canonical Photon message protects ingestion. Disable access logging of callback query strings.
Only human text messages in a space linked to a sent reminder are classified. Repeated completed message IDs return `{ "ok": true, "duplicate": true }`; unrelated events return `{ "ok": true, "ignored": true }`.
Reminder draft `source` additionally permits `"template"` for the deterministic fallback. A successful send means Photon accepted it for delivery, not that the customer received it; `provider_status` records Photon's acknowledgment.

### Pay-page additions
`GET /pay/{token}` returns HTML when `Accept` starts with `text/html`; `GET /pay/{token}/page` always serves HTML. JSON adds `visa: { "sandbox_mode": "sandbox" | "simulated" }` and, after payment, `payment` containing the POST receipt response. Visa receipts include `sandbox_mode`; simulation is labeled on the page. `/health.visa` may be `"simulated"` when Visa credentials are absent.
Payment emits `card.updated` with `card_id`, `invoice_id`, `status`, `payment_id`, `amount`, `rail`, and `pay_token`, plus the common event metadata. Payment action nodes include `data.kind="payment"` and `data.receipt`. Payment and its events commit atomically. A reused Solana signature or payment exceeding remaining balance returns 409 in the standard error envelope.

### Forecast scenarios and approvals
Forecast node data adds `owner_draw_by_target` and `conservative: { "assumption": "No amber or red invoice pays by target; green invoices remain probability-weighted.", "cash_at_target": 1000.00, "gap": 3000.00 }`. This is a stress scenario, not a calibrated percentile. `cash_at_target` is cash before payroll; `need` is payroll, and `gap=max(0,need-cash_at_target)`.
The expected answer may be covered while its spoken text warns about the conservative gap. Runtime payments increase cash and reduce remaining receivables before re-scoring, avoiding double counting. Recorded payments trigger forecast updates automatically, including after server restarts.
Resolved decisions emit `node.update` with `data.decision_id`, `data.resolved`, and `data.note`; repeated identical choices return the original result, conflicting choices return 409. Actions are queued durably. Bill deferral updates the owner cash plan and explicitly reports `vendor_confirmed: false`; it does not claim vendor agreement. Customer negotiation personas are simulated from dataset history; only policy-compliant accepted proposals auto-resolve after eight seconds.

Reports accept the standard `company` query parameter and are rebuilt from current events on read, preserving the report ID. Simulated card receipts are disclosed as simulation rather than a Visa sandbox transaction.

`bills_due_by_target` includes every still-unpaid bill due on or before the target, including overdue liabilities. Earlier fixture estimates omitted overdue bills; current live forecasts correct that omission.

When no drafting model is installed, `/model/metrics.drafter.serving` and `/health.drafter` are `"template_fallback"`; unmeasured metrics are null and row counts zero. `/health.db` is `"postgres"` for the local/Vultr database. Provider booleans report configuration presence; they do not attest successful live calls.

Canonical Photon messages from the configured `PHOTON_OWNER_HANDLE` start an `/ask`-equivalent run with source `sms`; other senders must match a reminder conversation. Live owner approval is handled through a `resolve_decision` tool scoped to the current call run.

## Follow-up runs
`POST /ask` additionally accepts optional `parent_run_id`. The parent must belong to
`company` (404 otherwise). The target date is inherited unless the question explicitly
specifies Friday or two weeks. `run.start` includes `parent_run_id` when present, and
`GET /runs` includes nullable `parent_run_id` for each item.

Two no-key intents are supported:
- `what_if_customer`: “what if Evergreen doesn't pay?” re-forecasts after removing that
  customer's residual open invoices from expected and pessimistic scenarios. Actual
  payments already received stay in cash. Emits context → scoring → forecast → answer
  → levers and an owner decision. Excluded invoices are not recommended for chasing.
  Forecast data includes `excluded_customer_id`; subsequent payment refreshes preserve
  this scenario and its target date. In the Palletbay demo, “Evergreen” explicitly means
  **Evergreen Juniper Flats Removals**, the shorthand used in `docs/frontend/brief.md`;
  the full selected name appears in the answer. Other ambiguous names return 422.
- `show_late`: “show me who's late” emits one scoring node containing only overdue
  open invoices, sorted descending by `days_past_due`, then amount, then invoice ID.
  Its data has `overdue_only: true` and `sort: "days_past_due_desc"`.

A child root can reference a node in the parent run using `parent` (the parent's node ID)
and `parent_run_id` together. Local edges still use just `parent`. Reused context is
identified by `data.reused_from: {run_id, node_id}`; financial values are refreshed from
the books rather than freezing stale payment balances. Node IDs are scoped to a run,
so a cross-run edge is always qualified with its run ID. Chase target objects also
include `customer_id`, allowing stable frontend keys.

## Live decision demo loop
Resolving the emitted payroll decision with `option_id: "yes"` (IDs are unique per run;
`d1` in examples is illustrative) enqueues the three selected reminder actions. Reminders
use the drafter (`draft.source: "gemini"` or disclosed `"template"` fallback).
With Photon key, project and sender configured, messages go only to the explicitly mapped
`PHOTON_DEMO_RECIPIENT`; a missing recipient is an error, and provider errors are never
reported as successful or silently simulated. Without the transport configuration,
reminder `data.channel` is `"simulated"` and `provider_status` is `"simulated"`; no SMS is sent.
`sent_at` in that case records completion of the simulation, not real delivery.

After all three simulated reminders, the first customer emits a reply with
`data.simulated: true` and `channel: "simulated"`, then uses the local uAgent negotiation.
Real Photon sends wait for real inbound replies instead. Customer agents remain simulated
personas in both cases. Action data includes `customer_id` and `customer` for grouping;
negotiations also include `simulated: true`. Agreements include `pay_link` alongside each
installment's `pay_token`. No payment occurs until the payer submits the pay page.
Payment actions explicitly label `sandbox_mode` (`"simulated"`, `"sandbox"`, or `"devnet"`).

`decision.resolved` is emitted atomically on a successful first resolution:
```json
{"decision_id":"d-unique","node_id":"n5","option_id":"yes"}
```
It has the common event envelope. Existing resolution `node.update` is retained.
Retries of the same resolution do not enqueue another action; conflicting retries return 409.
The live frontend acknowledges selection only after the API succeeds, and displays pay
links, synthetic-message labels, negotiation approval options and simulated receipts.

Forecast data also carries the current `bank_balance` (including runtime payments), so
clients must prefer it to the initial context bank value when rendering refreshed cash.

## Production UI and API routing
The built Vite frontend is served by FastAPI at `/`; `/?live` uses the same-origin
`/api` prefix, while the default view replays the fixture. `/?live&run=<run_id>` replays
an existing run and continues its live event stream. `/report/{report_id}` serves the
product report page; `/reports/{report_id}` remains the JSON API and `.pdf` remains PDF.
Every product API route (including events, pay, voice, health, runs and decisions) is
available at **both** its original path and `/api` + that path, with identical shapes.
Legacy callbacks and pay links therefore keep working. Static asset misses and unknown
API paths return 404, never an HTML success response.

The development/submission hub is at `/hub` → `/hub/timeline`, with `/hub/questions`,
`/hub/architecture`, `/hub/spec`, `/hub/static/*`, and `/hub/api/*`. Legacy hub page URLs
(`/timeline`, `/questions`, `/architecture`, `/spec`) are retained. With no product build,
`/` redirects to `/hub` rather than serving a broken app. Build/restart before production.
