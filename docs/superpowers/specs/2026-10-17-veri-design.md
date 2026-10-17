# Veri — Design Spec and Build Schedule

Hackathon: LA Hacks AI 2026, UCLA. Sat Oct 17 – Sun Oct 18, 2026. Deadline Sun 12:00 PM (confirm on Devpost at opening).
Builder: Ryan, solo. Devin does the frontend structure. Domain: veri.studio.

## Intent

**The one problem: getting paid.** Small businesses don't go under because they lack sales, they go under because customers pay late or never, and nobody has time to chase. Veri is a collections agent for a small-business owner. One calm screen each morning: here is the cash you can actually expect this month, here are the three customers to chase today, here is the reminder already drafted, tap to send it with a pay link. Discoverable through ASI:One so the same brain answers from a chat too.

Why this problem and not something else: the Intuit dataset (inspected Sat Oct 17) is 100 synthetic companies with one clean year of books. Its README says receivables carry the aging signal, most customers pay late, a slice of invoices is never paid and written off, and 7 of 100 companies are distressed. It explicitly lists "collections and AP prioritization, cash-flow dashboards, aging analysis, cross-company comparison" as well-supported. It also says the books are clean: no duplicate feed lines, and payables rarely age past 30 days. So "duplicate vendor" and "late bill to pay" cards would be fabrications. Collections is the real signal.

Intuit's framing is "work that used to be too slow or costly." Chasing invoices is exactly the bookkeeper chore every owner skips.

## Goals
- A judge opens veri.studio and understands the product in 10 seconds without a walkthrough.
- Every number on screen comes from a real query against the Intuit dataset in Snowflake. Nothing hardcoded.
- One action completes end to end in the demo: tap pay on a late invoice, Visa sandbox payment runs, receipt card appears.
- Same question asked in ASI:One returns the same brief.
- Qualify for Model Learning track + Intuit, Fetch.ai, Visa, Sentry, Cognition, Paper, MLH Gemini/Snowflake/ElevenLabs/Vultr/Domain.

## Non-goals
- Multi-user auth, real bank connections, real money.
- More than three cards on the brief screen. Ever.
- Mobile-native app. Mobile-width web is enough.

## Anti-goals (would make this a failure even if it works)
- A screen that looks like a generic Tailwind dashboard.
- Demo data that a judge can tell is fabricated.
- A chatbot as the primary interface. The chat is secondary; the brief is primary.

## The screen (designed in Paper first)

Single page, scrolls. Dark and light.

1. **Brief line.** One sentence from the agent, large type. "You're fine through January. Two things to look at."
2. **Cards.** Max three: the three customers to chase today, ranked by (balance × probability of slipping further) with a one-line reason the model produced. Each card: customer, amount, days past due, a tiny chart of that customer's payment history (each past invoice as a dot: days late), and one primary action, **Send reminder**. Sending opens the drafted message, then sends it with a Visa sandbox pay link. When the "customer" pays through the link (demo: you tap it on your phone), the card flips to a paid receipt.
   - Card variant: **Likely write-off.** When the model's never-pay probability is high, the action becomes "Call" or "Write off" instead of a reminder.
3. **Chase queue.** Every other overdue invoice with a drafted reminder and the model's expected pay date. Swipe or keyboard: send (→), edit (↓ opens the draft), skip (←). Counter shows remaining. Drafts come from Gemini with the customer's history in context; tone escalates with days late.
4. **Cash strip.** Expected cash in over the next 90 days, computed from each open invoice's predicted pay date, against payroll and bills due. Two sliders: "if the top 3 pay this week" and "if [worst customer] never pays". Line redraws live.
5. **Ask box.** One input at the bottom. Streams the answer. Powered by the same /ask endpoint the uAgent uses.
6. **Listen.** Small button next to the brief line. ElevenLabs reads the brief + card titles. ~20 seconds.

Type: one serif for the brief line, one sans for everything else. One accent color used only for actions. Motion: cards slide out on action, nothing else animates.

## Architecture

- **Data:** Intuit QuickBooks dataset (HF `CL251215/QuickBooks-Hackathon-2026`) loaded into Snowflake. Tables as shipped; one view per card type.
- **Backend:** Python, FastAPI. Endpoints: `GET /brief`, `GET /cards`, `GET /queue`, `POST /queue/{id}`, `POST /pay`, `POST /ask` (SSE), `GET /runway?hire=…&late=…`. Gemini for brief text, card explanations, ask. Jev (if key) or Gemini for categorization. Sentry SDK with Tracing + Logs + AI agent monitoring on every model call.
- **Agent:** uAgent in the same process (or sidecar) registered on Agentverse with Chat Protocol. Maps chat text → `/ask`, and "pay X" → `/pay`.
- **Payments:** Visa sandbox. The reminder carries a pay link; the payer's side is a minimal hosted checkout that runs a tokenized sandbox payment and marks the invoice paid. This is the "GenAI commerce with secure payments" story: the agent drafts, the customer pays, the books update.
- **Voice:** ElevenLabs TTS on the brief text, cached per brief.
- **Frontend:** Next.js + Tailwind. Devin builds scaffold, theme tokens, assistant/ask panel, queue component, payment flow, Playwright tests, Vultr deploy script. Ryan owns the brief screen layout, type, motion, and copy.
- **Hosting:** one Vultr VM, Docker compose (api + web). veri.studio → Vultr.

## Model Learning content (the "learned" part)
- **Per-customer payment-behavior model.** Training data: every company's `invoices.yaml` joined to `customer_payments.yaml` via `applications.document_id`, giving days-late per invoice per customer (~1,500 invoices and ~3,000 payments per company, ×100 companies). Features: customer's past days-late distribution, payment terms, invoice size relative to the customer's norm, company profile, month. Targets: (a) expected days to pay for an open invoice, (b) probability it is never paid (written off). Gradient-boosted trees or a simple hierarchical model; whatever is fitted by Sat 19:00.
- **Honest evaluation.** Hold out the last 60 simulated days of each company. Report MAE on pay date and AUC on write-off on the held-out set, in the Devpost write-up. Cross-company training is the thing a single business could never do, and the dataset makes it possible.
- **Chase ranking.** Cards and queue are ordered by expected recoverable cash × marginal effect of a reminder (approximated by how far past the customer's own typical lateness the invoice is).
- **Cash forecast.** Sum of predicted pay dates for open invoices minus payroll runs and bills due, per day, 90 days out. The sliders perturb the inputs.
- **Benchmark line.** Company's DSO (days sales outstanding) against the other companies in its profile ("you collect 11 days slower than similar wholesalers"). Shown once, in the brief line, when notable.
- **Jev.** If Intuit exposes a Jev/System One model this weekend, use it for the reminder drafting or for days-late prediction and say so. Otherwise Gemini drafts and the trees predict. Decided in hour one.

## API contract (write first, both sides build against it)
See `docs/api-contract.md` (to be written Sat ~11:45). JSON shapes for brief, card, queue item, payment, runway point, ask stream event.

## Risks and cutoffs
- **Visa sandbox onboarding slow:** cutoff Sat 23:30. If not working, Pay button runs a clearly labeled mock and Visa is dropped from the submission.
- **Jev not available:** decided in hour one at the Intuit booth. Gemini fallback, no schedule change.
- **Model underfits in time:** fallback is a per-customer empirical model (median days late, write-off rate) which is still learned from data and still honest. Cutoff Sat 19:00.
- **Dataset modifications:** none planned. If any row is changed, disclose it in the submission (hackathon rule in DATA_README.md).
- **Snowflake trial friction:** cutoff Sat 13:30. Fallback DuckDB locally; lose MLH Snowflake only.
- **Agentverse registration flaky:** cutoff Sun 00:30. If broken, submit with local uAgent + screenshot, note in write-up.
- **Scope creep on the screen:** three cards, hard rule.

## Schedule (Pacific)

### Saturday
- 10:00–11:00 Hour one. Keys: Gemini, Sentry, Snowflake, Visa sandbox, ElevenLabs, Vultr, Devin, Agentverse. Intuit booth: Jev access? Confirm Devpost deadline + multi-challenge entry. Read "Additional Information" for Intuit, Fetch, Visa, Sentry, Paper, Cognition. Point veri.studio DNS.
- 11:00–11:45 Paper: brief screen, card, queue, receipt, dark + light.
- 11:45–12:15 Write `docs/api-contract.md`. Brief Devin with spec + contract + Paper export. First ask: scaffold + theme tokens + deploy script.
- 12:15–14:00 Snowflake: flatten the YAML (invoices, customer_payments, customers, bills, payroll_runs, ar_aging, company) for all 100 companies into tables, load, write the core queries (open invoices with days late, per-customer payment history, cash out next 90 days).
- 14:00–16:00 FastAPI: /brief, /cards, /queue, /ask with Gemini. Sentry init with tracing. Devin second ask: queue component + ask panel with SSE.
- 16:00–17:00 Review and merge Devin PRs. Smoke test end to end with real data.
- 17:00–19:00 Payment-behavior model: build features, fit, hold out last 60 days, record MAE/AUC. Chase ranking and cash forecast. Devin third ask: Visa pay-link checkout page + receipt card + Playwright for three demo paths. **Model cutoff 19:00.**
- 19:00–20:00 Food. Review Devin PRs.
- 20:00–22:00 Brief screen craft: layout, type, motion, copy. Wire to real endpoints.
- 22:00–23:30 Visa sandbox end to end. Merge payment module. **Cutoff 23:30.**
- 23:30–00:30 uAgent + Agentverse registration + Chat Protocol. Test from ASI:One. **Cutoff 00:30.**
- 00:30–01:00 Feature freeze. Deploy to Vultr. Verify veri.studio loads. Sleep.

### Sunday
- 07:00–08:00 ElevenLabs listen button. Find one real bug via a Sentry trace and write it up (Sentry requirement).
- 08:00–09:30 Polish: dark/light pass, mobile width, empty states, copy. Runway sliders if not done.
- 09:30–10:30 Devpost: write-up, 6 screenshots, 2-minute video, Devin session link, Paper file link, Sentry screenshots.
- 10:30–11:30 Submit. Rehearse the 3-minute demo twice. Buffer.
- 12:00 Deadline.

### Add-ons only if ahead at Sat 22:00
- Photon: SMS the owner when a Pay card appears; reply "pay" triggers /pay. (+Photon prize, ~1h)
- StepFun: upload a receipt photo, step-5-preview extracts vendor/amount into the queue. (+StepFun prize, ~1.5h)

## Demo script (3 minutes)
Demo company: a wholesaler with real aging (e.g. Hearthloaf Bakeries has 1-30 and 31-60 buckets) or one of the 7 distressed companies for drama.
1. Open veri.studio. Brief line: "You'll collect about $21k of the $26k owed this month. Gallagher Apothecary is 53 days late and has paid late on 9 of 11 invoices." (15s)
2. Card 1: Gallagher. Show the dot chart of their history. Tap Send reminder, show the draft, send. (30s)
3. Phone: open the pay link as the customer, pay via Visa sandbox, card flips to paid on the laptop. (30s)
4. Drag "if the top 3 pay this week"; cash line moves. (15s)
5. Tap Listen; ElevenLabs reads the brief. (15s)
6. Chase queue: send two, edit one, with keyboard. (25s)
7. Phone: ASI:One, "who should I chase today," same three names. (25s)
8. Sentry: trace for that request and the bug it found. Mention the held-out MAE/AUC. (25s)

## Left to the builder
- Exact Snowflake schema. Dataset facts known now: 100 companies, 7 profiles (22 wholesale, 22 construction, 16 recurring, 14 pos, 12 mixed, 10 appointments, 4 nonprofit), one year ending 2026-10-06, YAML per entity, money as two-decimal strings, IDs company-scoped. Payments link to invoices via `applications[].document_id`. POS companies have no invoices; exclude them from the demo set.
- Which Gemini model tier (flash for queue, pro for brief) based on latency on the day.
- Whether the uAgent runs in-process or as a sidecar.
