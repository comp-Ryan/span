# Owed — Design Spec and Build Schedule (v2, maximal stack)

Hackathon: LA Hacks AI 2026, UCLA. Sat Oct 17 – Sun Oct 18, 2026. Deadline Sun 12:00 PM (confirm on Devpost).
Builder: Ryan, solo. Workflow: Ryan builds the frontend in Paper; Claude builds the backend from this spec and `docs/api-contract.md`; Devin gets self-contained chunks for the Cognition entry.
Working name: **Owed** (Claude's call; "Veri" was dropped because veri.studio is a sponsor). Ryan picks the real domain at GoDaddy.

## Intent

**The problem: getting paid.** Small businesses die because customers pay late or never, and the owner has no time to chase. Owed is a live collections agent. You tell it what you want ("chase everyone over 30 days"), and you watch it work: it drafts, sends, negotiates with the customer's agent, takes the payment, updates the books, and tells you out loud what happened. It is an assistant with hands, not a report with buttons.

Grounded in the Intuit dataset (inspected Oct 17): 100 synthetic companies, one clean year, receivables carry the signal, most customers pay late, some invoices are written off, 7 companies distressed. README names "collections and AP prioritization, cash-flow, aging, cross-company comparison" as well supported. Books are clean (no duplicate charges, AP ages young), so collections is the honest problem.

## Goals
- Judge understands it in 10 seconds. Every number is a real query. One full loop closes live on stage: command → negotiation → pay link → payment → books updated → spoken confirmation.
- Enter Model Learning track and every challenge in the prize map below.
- Honest: simulated customer agents are labeled as such; model metrics are on held-out data; any dataset edits disclosed.

## Non-goals
Auth, real bank connections, real money, native mobile, more than three attention cards.

## Anti-goals
Generic dashboard look. Fabricated data a judge can catch. A chatbot as the primary surface.

## Prize map (what must be true for each)

| Prize | Requirement | Tier |
|---|---|---|
| Model Learning track | Learned payment-behavior model + fine-tuned drafting model, held-out metrics | 1 |
| Intuit | Real-time analysis on the QuickBooks dataset; Jev if available | 1 |
| Veri ($800) | Fine-tune an open model (Qwen3-1.7B) on Veri; it runs at demo time | 1 (async, start early) |
| Fetch.ai | uAgent on Agentverse, Chat Protocol, ASI:One discovery, agent-to-agent negotiation | 1 |
| Photon | Reminders out and customer replies in over SMS/iMessage/email | 1 |
| Visa | Pay link runs a tokenized sandbox payment; GenAI commerce story | 1 |
| Sentry | Tracing + AI agent monitoring + Logs; one bug found via trace in write-up | 1 |
| Cognition | Devin builds real chunks; session link submitted | 1 |
| Paper ($1,500) | Frontend designed and built in Paper by Ryan | 1 |
| MLH Gemini | Orchestration, classification, teacher for training data | 1 |
| MLH Tiger Data | Postgres (Tiger Cloud) is the app DB; cash series as a hypertable | 1 |
| MLH Vultr | Backend hosted on Vultr | 1 |
| MLH Domain | Bought at GoDaddy Registry | 1 |
| MLH ElevenLabs | Voice: spoken confirmations, talk-to-Owed mode | 2 |
| MLH Solana | Second pay rail: USDC on Solana devnet | 2 |
| StepFun | Customer texts a photo of a mailed check; step-5-preview reads it, marks invoice pending | 3 |
| Browser Use | When a customer requires portal submission, agent submits the invoice on a (mock) vendor portal | 3 |
| Creao AI (Best One-Person Company $1,000) | Ryan is solo; build the public landing page in Creao. Confirm rules on their info page | 3 |
| MLH Snowflake | Mirror flattened tables for the cross-company benchmark query | 3 |

Not entered: Agentverse track (one track only; Fetch challenge covers it), Workday, Base44, QNX, Espressif, Even Realities.

Tier 1 ships Saturday. Tier 2 Saturday night if on schedule. Tier 3 Sunday 07:00–09:30 only, each ≤ 1.5h, drop without regret.

## The screen (Ryan, in Paper)

Single page, dark and light. Two regions.

**Left: attention.**
1. Brief line, large type: "You'll collect about $21k of the $26k owed this month. Gallagher is 53 days late and pays late 9 times in 11."
2. Up to three cards: customer, amount, days late, dot chart of their payment history, model's expected pay date and never-pay risk, one primary action. Card states: open → working → sent → negotiating → agreed → paid, or dismissed.
3. Cash strip: expected cash in next 90 days vs payroll and bills; sliders "if top 3 pay this week" and "if X never pays".

**Right: the agent.**
4. Command box (type) and mic button (talk). "Chase everyone over 30 days." "What did Gallagher say?"
5. Live action feed, streaming: drafting, sent, reply received, classified, negotiating (transcript lines between Owed and the customer agent), pay link issued, paid. Each line is a real event from `/events`.
6. Interrupt: any feed line with a decision has a one-tap overrule (accept / decline / call them).
7. Footer: model metrics (held-out MAE days, write-off AUC), fine-tuned model name, "customer agents simulated from dataset history".

Type: one serif for the brief line, one sans elsewhere. One accent for actions. Motion: feed lines slide in, card state changes crossfade, nothing else.

## Architecture

- **DB: Tiger Cloud Postgres.** Flattened tables: companies, customers, vendors, invoices, invoice_lines, customer_payments, payment_applications, bills, bill_payments, payroll_runs, ar_aging, ap_aging, pnl_monthly. Hypertable `cash_projection(company_id, day, inflow, outflow, balance, scenario)`. Runtime tables: reminders, messages, negotiations, payments, events.
- **Backend: Python FastAPI** on Vultr. Endpoints per `docs/api-contract.md`. SSE for feed and card updates.
- **Models.**
  - *Payment-behavior model* (scikit-learn gradient-boosted trees or LightGBM): per open invoice → expected days-to-pay, p(never pay). Trained across all 100 companies, last 60 sim-days held out. Metrics reported.
  - *Drafter* (Qwen3-1.7B fine-tuned on Veri via `sft_text`): input = customer history summary + invoice + tone target; output = JSON {subject, body, acceptable_terms}. ~2,000 training rows generated Saturday from the dataset with Gemini as teacher. Served quantized on the Vultr box (llama.cpp) or Veri's inference if available. Fallback to Gemini drafting if serving fails, with the fine-tune still reported for Veri + Model Learning.
  - *Gemini*: command parsing, inbound reply classification (will_pay / dispute / wants_plan / other), negotiation policy reasoning, brief text, Q&A, and teacher for the drafter's training data.
  - *Jev*: if Intuit provides access, use it for the brief or prediction and say so. Decided at the booth in hour one.
- **Agents (Fetch uAgents).** `owed-agent` (one per demo company) registered on Agentverse with Chat Protocol; ASI:One queries route to `/ask` and `/command`. `customer-agent-<id>` for each customer in the demo company, also on Agentverse, persona = that customer's real payment history (median lateness, write-off history, terms). Negotiation protocol: propose → counter → accept/decline, max 4 rounds, every message mirrored to the feed. Owner rules (configurable): accept installments only for customers with ≥80% paid history; never discount more than 5%; escalate disputes to human.
- **Channels (Photon 2.0).** Outbound reminders via email and SMS; inbound replies webhook → classifier → feed → negotiation or human decision. Fallback if Photon beta fails in hour one: SMTP for email + Telegram Bot for inbound; lose Photon prize only.
- **Payments.** Pay link page (Devin builds): Visa sandbox card rail; Solana devnet USDC rail (Tier 2) via a Phantom-compatible devnet wallet and a backend that watches for the transfer. Either rail marks the invoice paid, writes a customer_payment row, fires `card.updated`.
- **Voice (ElevenLabs).** TTS on brief and feed confirmations; conversational mode if time: mic → STT → `/command`, reply → TTS.
- **StepFun (Tier 3).** Inbound Photon MMS with an image → step-5-preview extracts payer, amount, check number → invoice marked `pending_check`.
- **Browser Use (Tier 3).** Customers flagged `requires_portal` → Browser Use agent opens the mock vendor portal (a static page we host), fills invoice fields, uploads PDF, captures confirmation number → feed.
- **Observability (Sentry).** SDK with Tracing on every request, AI agent monitoring on every Gemini/drafter call, Logs. Write-up: the bug a trace found.
- **Devin chunks:** (1) YAML→Postgres flattener + loader with tests; (2) pay-link page with Visa + Solana rails; (3) mock vendor portal. Brief each with the contract. Keep session links.
- **Frontend:** Ryan in Paper, against the contract. Claude writes no frontend code unless asked.
- **Landing page (Tier 3):** Creao AI, for the Best One-Person Company entry.

## Honest evaluation
- Payment model: hold out last 60 sim-days per company. Report MAE on pay date, AUC on write-off.
- Drafter: hold out 10% of generated rows; report JSON-validity rate and Gemini-judged quality vs base Qwen3-1.7B.
- Dataset: no modifications planned; disclose any.

## Risks and cutoffs (Pacific)
- Photon beta broken: decide 11:00. Fallback SMTP + Telegram.
- Tiger Cloud signup friction: cutoff 13:30. Fallback local Postgres in Docker on Vultr; lose Tiger prize.
- Veri job fails: training rows generated by 15:30, job submitted by 16:00, retry once by 20:00. Fallback: report the attempt, draft with Gemini.
- Payment model underfits: cutoff 19:00, fallback per-customer empirical model (median lateness, write-off rate).
- Agentverse registration flaky: cutoff Sun 00:30. Fallback local agents + screenshots.
- Visa sandbox slow: cutoff Sat 23:30. Fallback clearly-labeled mock rail.
- Scope: three cards max, Tier 3 items ≤ 1.5h each, no exceptions.

## Schedule

### Saturday
- 10:30–11:30 Hour one. Keys: Gemini, Sentry, Tiger Cloud, Visa sandbox, Photon beta, ElevenLabs, Vultr, Devin, Agentverse, Veri credits (DM @daniung in Discord), Solana devnet wallet, Browser Use, Creao upgraded account. Intuit booth: Jev access? Read Additional Information for Fetch, Visa, Photon, Sentry, Paper, Cognition, Creao, Browser Use, Veri. Buy domain. Send one Photon SMS from code.
- 11:30–12:15 Ryan: Paper design. Claude: finalize `docs/api-contract.md` v2, brief Devin chunk 1 (flattener/loader).
- 12:15–14:00 Claude: FastAPI skeleton, Tiger Cloud schema, load data (merge Devin's loader when ready), core queries, Sentry init. Ryan: Paper build begins against contract.
- 14:00–15:30 Claude: drafter training-data generation with Gemini (2,000 rows). Submit Veri SFT job at ~15:30–16:00. Brief Devin chunk 2 (pay-link page).
- 15:30–17:30 Claude: payment-behavior model, hold-out eval, chase ranking, cash projection into hypertable. `/brief`, `/cards`, `/cash` live with real data.
- 17:30–19:30 Claude: Photon outbound + inbound webhook, reply classifier, `/command` parser, feed events over SSE. **Model cutoff 19:00.**
- 19:30–20:00 Food. Review Devin PRs. Check Veri job.
- 20:00–22:00 Claude: uAgents — owed-agent + customer agents, negotiation protocol, Agentverse registration, Chat Protocol. Ryan: wire Paper frontend to live endpoints.
- 22:00–23:30 Visa rail end to end via Devin's pay page. Serve fine-tuned drafter if job finished. **Visa cutoff 23:30.**
- 23:30–00:30 ElevenLabs TTS confirmations (Tier 2). Solana devnet rail if pay page ready (Tier 2). **Agentverse cutoff 00:30.**
- 00:30–01:00 Feature freeze. Deploy to Vultr, domain live. Sleep.

### Sunday
- 07:00–09:30 Tier 3, strictly ≤1.5h each, in this order: StepFun check-photo → Browser Use portal → Creao landing → Snowflake mirror. Sentry bug write-up.
- 09:30–10:30 Devpost: write-up, screenshots, 2-min video, Devin links, Paper link, Veri job link + metrics, Sentry screenshots, disclosure notes.
- 10:30–11:30 Submit. Rehearse demo twice.
- 12:00 Deadline.

## Demo script (3 minutes)
Demo company: a wholesaler with aging (Hearthloaf Bakeries) or a distressed one for drama.
1. Open the site. Brief line reads itself aloud (ElevenLabs). (15s)
2. Say "chase everyone over 30 days." Feed: three drafts, three sends via Photon. Phone buzzes with the SMS. (30s)
3. Reply from the phone as Gallagher: "can we split it?" Feed: classified wants_plan → Owed finds Gallagher's agent on Agentverse → negotiation transcript streams → Owed accepts two installments per owner rules. (40s)
4. Pay link arrives on the phone. Pay first installment via Visa sandbox (or USDC on Solana). Card flips to paid on the laptop. Owed says "Gallagher agreed to two payments, the first just landed." (30s)
5. Drag "if top 3 pay this week"; cash line moves. (10s)
6. ASI:One on the phone: "who should I chase today?" same names. (20s)
7. Sentry trace of the negotiation request; footer metrics; mention the fine-tuned Qwen drafter on Veri and the held-out numbers. (25s)

## Left to the builder
- Exact Tiger schema mapping (dataset facts: 7 profiles, YAML per entity, money as 2-dp strings, IDs company-scoped, payments link via `applications[].document_id`, POS companies have no invoices).
- Qwen3-1.7B vs 4B for the drafter based on Veri credits and serving.
- Whether customer agents run as separate processes or one multiplexed uAgent.
