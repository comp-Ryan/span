# Veri — Design Spec and Build Schedule

Hackathon: LA Hacks AI 2026, UCLA. Sat Oct 17 – Sun Oct 18, 2026. Deadline Sun 12:00 PM (confirm on Devpost at opening).
Builder: Ryan, solo. Devin does the frontend structure. Domain: veri.studio.

## Intent

A personal finance agent for a small-business owner or freelancer. One calm screen each morning; the agent has already read the books, flags at most three things, and can act on them (pay, chase, categorize). Discoverable through ASI:One so the same brain answers from a chat too.

Why: finance work is slow and costly for small businesses (Intuit's own framing). Everyone else will ship a 12-widget dashboard; Veri wins on restraint and on taking action, not just talking.

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
2. **Cards.** Max three. Each: title, one-line reason, a tiny chart (sparkline or two-bar), and one primary action. Card types:
   - Duplicate vendor charge → action: Flag
   - Late invoice (receivable) → action: Send reminder (Photon add-on) or Mark chased
   - Late bill (payable) → action: Pay (Visa sandbox) → receipt card replaces it
   - Off-trend spend in a category → action: Explain (expands) / Dismiss
3. **Review queue.** Uncategorized transactions with a suggested category and confidence. Swipe or keyboard: approve (→), fix (↓ opens picker), skip (←). Counter shows remaining. Suggestions come from Jev if available, else Gemini.
4. **Runway strip.** Cash runway line, 6 months out. Two sliders: "new hire starts" and "largest invoice pays late by N days". Line redraws live.
5. **Ask box.** One input at the bottom. Streams the answer. Powered by the same /ask endpoint the uAgent uses.
6. **Listen.** Small button next to the brief line. ElevenLabs reads the brief + card titles. ~20 seconds.

Type: one serif for the brief line, one sans for everything else. One accent color used only for actions. Motion: cards slide out on action, nothing else animates.

## Architecture

- **Data:** Intuit QuickBooks dataset (HF `CL251215/QuickBooks-Hackathon-2026`) loaded into Snowflake. Tables as shipped; one view per card type.
- **Backend:** Python, FastAPI. Endpoints: `GET /brief`, `GET /cards`, `GET /queue`, `POST /queue/{id}`, `POST /pay`, `POST /ask` (SSE), `GET /runway?hire=…&late=…`. Gemini for brief text, card explanations, ask. Jev (if key) or Gemini for categorization. Sentry SDK with Tracing + Logs + AI agent monitoring on every model call.
- **Agent:** uAgent in the same process (or sidecar) registered on Agentverse with Chat Protocol. Maps chat text → `/ask`, and "pay X" → `/pay`.
- **Payments:** Visa sandbox tokenized payment. Mocked merchant, real sandbox call, store receipt.
- **Voice:** ElevenLabs TTS on the brief text, cached per brief.
- **Frontend:** Next.js + Tailwind. Devin builds scaffold, theme tokens, assistant/ask panel, queue component, payment flow, Playwright tests, Vultr deploy script. Ryan owns the brief screen layout, type, motion, and copy.
- **Hosting:** one Vultr VM, Docker compose (api + web). veri.studio → Vultr.

## Model Learning content (the "learned" part)
- Categorization: Jev or Gemini few-shot, calibrated with confidence; queue accepts/fixes are logged and fed back as examples (visible learning loop in the demo).
- Duplicate vendor detection: fuzzy vendor-name match + amount/date window.
- Off-trend spend: per-company, per-category monthly z-score against that company's own history; cross-company percentile as a second signal ("you spend 2x what similar companies do on software").
- Runway: simple cash forecast from historical inflow/outflow with the two what-if parameters.

## API contract (write first, both sides build against it)
See `docs/api-contract.md` (to be written Sat ~11:45). JSON shapes for brief, card, queue item, payment, runway point, ask stream event.

## Risks and cutoffs
- **Visa sandbox onboarding slow:** cutoff Sat 23:30. If not working, Pay button runs a clearly labeled mock and Visa is dropped from the submission.
- **Jev not available:** decided in hour one at the Intuit booth. Gemini fallback, no schedule change.
- **Snowflake trial friction:** cutoff Sat 13:30. Fallback DuckDB locally; lose MLH Snowflake only.
- **Agentverse registration flaky:** cutoff Sun 00:30. If broken, submit with local uAgent + screenshot, note in write-up.
- **Scope creep on the screen:** three cards, hard rule.

## Schedule (Pacific)

### Saturday
- 10:00–11:00 Hour one. Keys: Gemini, Sentry, Snowflake, Visa sandbox, ElevenLabs, Vultr, Devin, Agentverse. Intuit booth: Jev access? Confirm Devpost deadline + multi-challenge entry. Read "Additional Information" for Intuit, Fetch, Visa, Sentry, Paper, Cognition. Point veri.studio DNS.
- 11:00–11:45 Paper: brief screen, card, queue, receipt, dark + light.
- 11:45–12:15 Write `docs/api-contract.md`. Brief Devin with spec + contract + Paper export. First ask: scaffold + theme tokens + deploy script.
- 12:15–14:00 Snowflake: load dataset, inspect schema, write the three core queries (late payables, duplicate vendors, monthly category spend).
- 14:00–16:00 FastAPI: /brief, /cards, /queue, /ask with Gemini. Sentry init with tracing. Devin second ask: queue component + ask panel with SSE.
- 16:00–17:00 Review and merge Devin PRs. Smoke test end to end with real data.
- 17:00–19:00 Anomaly logic: duplicates, z-scores, runway forecast. Categorization with Jev/Gemini. Devin third ask: Visa payment flow + receipt card + Playwright for three demo paths.
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
1. Open veri.studio. Read the brief line aloud. (10s)
2. Card 1: duplicate vendor. Swipe to flag. (20s)
3. Card 2: late bill. Tap Pay. Visa receipt appears. (30s)
4. Drag the hire-date slider; runway line moves. (20s)
5. Tap Listen; ElevenLabs reads it. (20s)
6. Review queue: approve two, fix one with keyboard. (30s)
7. Phone: ASI:One, ask "how's my cash this month," same answer. (30s)
8. Sentry: show the trace for that request and the bug it found. (20s)

## Left to the builder
- Exact Snowflake schema mapping once the dataset is inspected.
- Which Gemini model tier (flash for queue, pro for brief) based on latency on the day.
- Whether the uAgent runs in-process or as a sidecar.
