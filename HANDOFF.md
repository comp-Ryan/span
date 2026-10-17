# HANDOFF — Span backend (for Astra)  ·  product name is Span; the Python package stays `owed`

Written Sat Oct 17, 2026 ~3:30 PM PT by Claude. Ryan + Claude are moving to the Paper frontend. Devin has tasks 1–4 in `docs/devin/`. **Astra owns everything else in the backend from here.**

## Goal
Owner calls a number, asks "am I making payroll Friday?", hears a real answer in ~1 s, watches the reasoning draw itself as workflow nodes on a web canvas, says "yes", and the agent chases customers; payments make the gap tick down; a report is generated. Full spec: `docs/superpowers/specs/2026-10-17-owed-design.md`. Contract: `docs/api-contract.md` (source of truth for every shape). Deadline: Sun 12:00 PM PT, no buffer.

## Current state (verified)
- `backend/` FastAPI app runs: `uvicorn owed.main:app --reload --port 8000`. Only hub pages + `/health` exist. **No product endpoints yet.**
- Postgres (local TimescaleDB on :5433 via `docker compose up -d db`) holds all 100 companies. Loader: `python -m owed.db.load`. Row counts: 84,451 invoices, 143,616 customer payments, 39,563 bills, 25,733 payroll runs, 234,610 bank txns. Derived table `invoice_facts` (paid_amount, days_late, status ∈ paid/open/partial/written_off). 46 write-offs (journal purposes `bad_debt`, `client_default`).
- Payment model trained: `models/payment_model.pkl`, metrics in `models/payment_model_metrics.json`. Held-out (60-day window ending 60 days before dataset end): AUC paid-within-30d **0.968**, days-late MAE **1.25** (baseline customer-average 1.36), write-off AUC 5-fold CV **0.795** (46 positives). `owed.finance.model.load().score_open(rows, days_to_target)` returns per-invoice `p_paid_by_target`, `p_never`, `expected_days_to_pay`. `band(p_paid, p_never)` → green/amber/red.
- SQL helpers in `owed/finance/queries.py`: `bank_balance`, `payroll_due`, `bills_due`, `open_invoices` (with per-customer history features), `customer_history`, `peer_dso`, `companies`.
- NOTE (3:50 PM): two-week horizon gives cash_at_target ≈ +$1,214 (expected value), i.e. "barely covered". Add a pessimistic scenario (drop amber/red customers) to the forecast node so the answer can say "short by $X if slow payers slip". See docs/frontend/brief.md.
- Demo company: **company-020 Palletbay Storage & Warehousing**: bank $6,533.65; trailing payroll ≈ $6.9k/week; bills due next 2 weeks $9,268; open AR $28,509 of which $14,928 overdue across 204 invoices. Top overdue customers: Evergreen Juniper Flats Removals ($1,156, 6 inv), Yeoman Roasters ($669), Hearth Trading Partners ($643), Okonkwo & Daughters Roasters ($615). Dataset "today" = 2026-10-06; "Friday" = 2026-10-09; use a 14-day target (2026-10-20) if the question says "next two weeks".
- No keys yet: Gemini, Photon, ElevenLabs, Sentry, Tiger Cloud, Agentverse, Veri, Visa, Solana. Ryan is collecting. `backend/.env.example` lists them; add new ones there.

## Build order for Astra (each step leaves something demoable)
1. **Event bus + runs** (`owed/events.py`, `owed/runs.py`): `emit(run_id, event, data)` writes to `events` and fans out to SSE subscribers; `GET /events?company=` (SSE, replay last N on connect), `GET /runs`, `GET /runs/{id}`. Shapes exactly per contract.
2. **Payroll run, deterministic** (`owed/runs/payroll.py`): `POST /ask` with intent `payroll_check` → nodes: context → scoring (one `node.update` per invoice, scored by the payment model, ~50 ms apart so the canvas visibly ticks) → forecast → answer → levers → decision. Use the queries + model above. Spoken sentences from templates for now. This alone is the demo's first minute and needs no keys.
3. **Gemini tool loop for typed/SMS/ASI:One** (`owed/planner.py`): `gemini-2.5-flash` with function declarations: forecast_cash, predict_payment, score_customer, rank_chase, defer_bill, draft_reminder, send_message, query_books, show_node. Intent routing: payroll_check, order_check, chase_today, afford_check, client_status, free_question. Every tool call → node event.
4. **Gemini Live call path** (`owed/voice/live.py`): websocket endpoint `/voice/photon` receiving Photon's media stream; open Gemini Live session (`gemini-2.5-flash-native-audio` or current Live model) with the same tool declarations, response modality TEXT; pipe text to ElevenLabs streaming TTS (Flash v2.5) → audio back to Photon; handle barge-in. If Photon has no media streams, implement the same endpoint for Twilio Media Streams (mulaw 8k) and tell Ryan.
5. **Photon messaging** (`owed/channels/photon.py`): send SMS/email reminders with pay links (Devin's `create_pay_token`), inbound webhook `/inbound/photon` → classify reply with Gemini (will_pay / dispute / wants_plan / other) → `action` node; `wants_plan` → negotiation.
6. **uAgents** (`owed/agents/`): `owed-agent` with Chat Protocol on Agentverse → routes to `/ask`; `customer-agent` persona built from `customer_history`; negotiation protocol propose/counter/accept ≤4 rounds under owner rules (installments if paid-rate ≥0.8, max 5% discount, disputes escalate); every round → `node.update` on the negotiation node; `decision` event with 8 s auto-resolve.
7. **Levers that act**: defer_bill (vendor tolerance from `bills_due.hist_days_vs_due`), hold owner draw (journal purpose `owner_distribution` history), chase (steps 5–6). Forecast node re-fires on every payment (`card.updated` from Devin's pay page → recompute → `node.update` on the forecast node).
8. **Sentry**: init with tracing + logs + AI monitoring on every Gemini call. Find one real bug via a trace and write it in `docs/submission/devpost.json` → `sentry_bug_writeup`.
9. **Deploy** to Vultr (Docker: api + Postgres or Tiger Cloud URL), point Ryan's domain.

## Gotchas
- psycopg: `%` in SQL must be `%%` (bit me once in `load.py`).
- `company.yaml` is a list with one element.
- POS companies (14) have no invoices; `queries.companies()` already excludes them.
- IDs are company-scoped; always filter by `company_id`.
- Scoring 204 invoices through the model is fast (<100 ms total); the per-row `node.update` pacing is for the canvas, not the math.
- Hub pages (`/timeline`, `/questions`, `/architecture`, `/spec`) are Ryan's working tools; keep them mounted.

## Coordination
- Contract changes: edit `docs/api-contract.md` in the same PR, and tell Ryan (the Paper canvas consumes it).
- Devin's modules will land as PRs on `devin/*` branches; review and merge them, they're scoped not to overlap with the above.
- Fixture for the frontend: Devin task 2 produces `backend/tests/fixtures/run_palletbay.json`; until then, Claude is writing a hand-made one at `docs/frontend/fixture-run-palletbay.json`.
