# Span — finished product spec

Status date: Saturday, October 17, 2026. Submission: Sunday, October 18, 12:00 PM PT.

Span is a cash assistant for a small-business owner. The owner asks a money question by
voice or text, watches Span work it out on a live workflow canvas against their real
books, and approves one action at a time. Every screen runs on live backend data. The
recorded fixture replay is kept only as an offline fallback, never as the demo.

## 1. Principles

- **Live, not staged.** The demo runs `?live` against the real API: real invoice scoring,
  real forecasts, real decisions, real (sandbox/devnet) payments.
- **One step at a time.** Span asks one clarifying question, waits, and lets the owner
  correct an answer. It proposes one action at a time and never acts without approval.
- **Honest labels.** Simulated customer agents, the Visa sandbox, Solana devnet and
  browser voice are labeled as such on screen.
- **Postgres is the private database.** Solana is settlement proof for payments only.

## 2. Shell (every page)

- Top bar: Span logo + wordmark, company name, global ask/search box, status pill
  (Live / Voice / Demo replay).
- Left rail: **Ask**, **Home**, **Get paid**, **Reports**, **Customers**. The active page is
  highlighted. No dead links.
- Company switcher persists through `?company=`; every API call is company-scoped.

## 3. Pages

### 3.1 Home (`/home`) — the hero

- Greeting and one-line headline from `/brief` ("You'll collect about $X of the $Y you're owed…").
- Four tiles: In the bank, Owed to you, Payroll next, Bills due this week.
- **Ask Span** card: big input, mic button (browser voice), three suggestion chips.
  Asking starts a new chat and opens it.
- Next 14 days cash sparkline from `/cash`.
- Recent chats (latest 8 root runs) with verdict pill, source and time; click opens the chat.

### 3.2 Ask (`/` and `/?run=<id>`) — the general chat interface

- **Chat list sidebar** (inside the page, left of the canvas):
  - **New chat** button: clears the canvas and focuses the ask box.
  - **Past chats**: root runs from `/runs`, newest first, showing title, verdict pill and
    relative time. Selecting one loads `/?run=<id>&live`.
  - Rename a chat by double-clicking its title. The title is stored per run in this browser.
- **Canvas** for the open chat:
  - First workflow card is the owner's question; each step is connected by an arrow.
  - Deterministic payroll runs: books → invoice scoring → cash forecast → verdict →
    levers → actions/messages → payment outcome.
  - Planner (Gemini) runs: each tool call renders as its matching visual (books, scoring
    dots, cash, customer history, levers), then the spoken answer and a collapsible
    full-reasoning card.
  - Follow-ups render below as branches of the same chat, with a link to the parent question.
  - A clarifying question shows as "Waiting for your answer" — no report until answered.
- Left column: live dated cash chart, slow-payers risk panel, one-page report card.
- **Decisions are real.** Approve/decline buttons call `POST /decisions/{id}`. Only one
  approval is pending at a time.

### 3.3 Calling interface (dock on the Ask page)

- Bottom-right bubble opens the call panel: status, live waveform, transcript.
- Transcript shows the owner's turns ("you"), Span's spoken turns and tool rows with timing.
- **Browser voice** (`&voice=browser`): tap the mic to speak one turn; Span answers aloud.
  The next tap continues the same chat. Spoken "yes"/"not now" resolves the pending
  decision; anything ambiguous is treated as a new follow-up question.
- Typed follow-ups work the same way from the panel's input.
- Server voice (Twilio Media Streams → Gemini Live → ElevenLabs) stays available for a
  future phone number; it is not required for the demo.

### 3.4 Get paid (`/get-paid`)

- Totals: open pay links, amount collected, amount outstanding.
- Table of pay links: customer, invoice, amount, status (unpaid/paid), created time, and
  an **Open pay page** link (`/pay/<token>`).
- Payments received: amount, rail (Visa sandbox / Solana devnet), reference or signature,
  time, and the chat it came from.
- Rail readiness: Visa sandbox vs simulated; Solana devnet vs unconfigured (from `/health`).

### 3.5 Reports (`/reports`)

- List of generated one-page reports: question, verdict, generated time, links to
  `/report/<id>` and the PDF.
- Chats that finished without a report show a **Generate report** button.
- `/report/<id>` remains the printable one-pager.

### 3.6 Customers (`/customers`, `/customers/<id>`)

- List: customer, open balance, overdue balance, number of open invoices, average days
  late, reliability band (from the payment model). Sortable; search box.
- Detail: payment-history strip, open invoices with probability of payment by payday,
  reminders sent, replies, negotiations and payments. Button: **Ask Span about this
  customer** starts a chat ("How is <customer> doing?").

### 3.7 Pay page (`/pay/<token>`) — customer-facing

- Invoice summary, Card tab (Visa sandbox/simulated), USDC tab (Phantom devnet, Solana Pay
  link and QR with the per-invoice reference), receipt after payment.

## 4. API needed by the pages

| Page | Endpoint | Status |
|---|---|---|
| Home | `GET /brief`, `GET /cash`, `GET /runs` | exists |
| Ask / chat list | `GET /runs`, `GET /runs/{id}`, `POST /ask`, `GET /events`, `POST /decisions/{id}` | exists |
| Get paid | `GET /payments?company=` → `{pay_links:[…], payments:[…], totals:{…}}` | **to build** |
| Reports | `GET /reports?company=` → `{reports:[{report_id, run_id, question, answer, generated_at}]}` | **to build** |
| Customers | `GET /customers?company=` and `GET /customers/{id}?company=` | **to build** |

All new endpoints are read-only, company-scoped, mounted with and without `/api`, and
return 404 for an unknown company or a customer outside it.

## 5. Demo (functional, 2 minutes)

Run against the live backend, company `company-020` (Palletbay Storage & Warehousing):

1. Home → tap mic → say "Am I going to make payroll these next two weeks?"
2. Canvas builds live: books, 204 invoices scored, forecast, verdict "No, about $385 short".
3. Span asks one question: "Should I assume Evergreen will pay by payday?" Owner answers
   "no", the forecast recalculates without Evergreen.
4. Span proposes one action (text the reliable late payers). Owner says "yes".
5. Reminders go out (simulated channel, labeled), a simulated customer agent negotiates
   two installments, the first is paid on the pay page with the Visa sandbox card.
6. Outcome card turns green; Get paid shows the payment; Reports shows the one-pager.

`npm run record` drives this live flow with Playwright (not the fixture) and writes the
video, stills and the 1500×900 thumbnail. Each run uses a fresh database reset so the
demo is repeatable.

## 6. Tests to pass before submission

Automated (no external services):

- Frontend: `npm test`, `npm run test:branches`, `npm run build`, `npm run lint` (no new warnings).
- Backend DB-free: `tests/test_voice.py`, `tests/test_planner_conversation.py`,
  `tests/test_solana_reference.py`, plus new endpoint tests.
- Backend DB-backed, against an **isolated** `DATABASE_URL` (never the demo DB):
  full `pytest`, including payments (updated for the Solana reference), planner tools,
  decisions, cash and the new page endpoints.

Manual, in Chrome on localhost:

- Every rail link opens a real page with data; no 404s in the console.
- New chat, past chat selection, rename, reload of `/?run=<id>` restores the chat and its branches.
- Browser voice: question → clarification → answer → correction → recalculation → spoken
  yes resolves the real decision; mic-denied and unsupported-browser messages appear.
- Pay page: Visa test card succeeds; paid link shows its receipt; Get paid updates.
- Report generates, opens, prints and the PDF downloads.

## 7. Deliverables

| Deliverable | Owner | Status |
|---|---|---|
| Get paid, Reports, Customers pages + endpoints | build | to do |
| Chat list (new chat, past chats, rename) | build | to do |
| Live recorder (`npm run record` on the live flow) + demo DB reset script | build | to do |
| PR #27 planner visuals merged with real decisions | build | to do |
| Tiger Data: persist forecast history in the `cash_projection` hypertable | build | to do |
| Solana Pay reference per invoice | build | done locally; payments tests to update |
| Commit and push all local work | build | to do |
| Demo video (2 min) + thumbnail + Devpost copy | Ryan | to do |
| Keys: Sentry DSN, Agentverse, Solana recipient (public address) | Ryan | to do |
| Vultr host, then GoDaddy domain (last), then deploy | Ryan | to do |
| Repo public before submission | Ryan | to do |
| Commit Fellowship form, DEV article (after event) | Ryan | optional |

Skipped on purpose: Snowflake, Base44, StepFun, Photon voice (not available on the project yet).
