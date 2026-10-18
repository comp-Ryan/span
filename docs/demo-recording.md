# Reproducible live demo and isolated tests

Branch `wip/live-demo`. Package names remain `owed`. Do not use the shared `owed`
database for pytest; reset it only with `scripts/reset_demo.py` (below).

## Recording (live by default)

Prerequisites: loaded Docker TimescaleDB on localhost:5433, model at
`backend/models/payment_model.pkl`, installed backend/frontend dependencies,
`GEMINI_API_KEY` + `AGENT_SEED` in `backend/.env`, Playwright Chromium or installed Chrome.

```sh
cd frontend
npm run record
# If ports are occupied, no process is killed:
RECORD_PORT=8038 RECORD_AGENT_PORT=8039 npm run record
```

Every take provisions a new `span_demo_record_*` database, clears only its runtime
state, builds the frontend, starts its own API/bureau and drives live UI requests.
Main's company selection is overridden to the documented demo company-020.
Simulated messaging and card rails are forced **for this recording process only**;
no customers are contacted or charged. uAgents exchange real local messages.
Gemini failures stop the take instead of fabricating an answer. Servers stop on exit;
the database and outputs remain for inspection. No source records are modified.

Outputs: `frontend/demo-out/live-*/` (ignored), with `demo.webm`, optional MP4,
eleven PNG stills, 1500×900 thumbnail, `report.pdf` and API-backed `evidence.json`.
The flow: Home → question → one clarifying question → owner's answer
(`RECORD_CLARIFY`, default "I'm not sure, go with your estimate.") → real approval →
simulated reminders and local uAgent negotiation → first installment of each agreement
on the real pay page → outcome card → "What if Evergreen doesn't pay?" → Get paid →
Reports → the report and its PDF. Incomplete
runs leave `failure.png`, logs and a partial video; do not submit them as success.
Voiceover is separate: `docs/submission/video-script.md`. `npm run record:fixture`
is retained **only** as the explicitly offline replay; it is not the live proof.

## A safe manual reset

Run from repo root; choose a unique suffix. Provisioning copies books read-only
from the source and never uses it as the reset destination.

```sh
backend/.venv/bin/python backend/scripts/demo_db.py create --name span_demo_manual_20261018
# Stop all API/test clients using this clone first. Exact name + provisioned marker required:
backend/.venv/bin/python backend/scripts/demo_db.py reset \
  --env .local/span_demo_manual_20261018.env --confirm span_demo_manual_20261018
```

The reset refuses remote hosts, shared names, unmarked databases, mismatched
confirmation, and a database with another client connected. Only explicit runtime
tables are truncated; books/model are retained. Env files are ignored and mode 0600.

## Test suite

```sh
backend/.venv/bin/python backend/scripts/demo_db.py create --name span_test_manual_20261018
set -a; source .local/span_test_manual_20261018.env; set +a
(cd backend && .venv/bin/pytest -q)
(cd frontend && npm test && npm run test:branches && npm run build && npm run lint)
```

Pytest requires a marked local `span_test_*` database for DB-backed modules and
disables live provider keys. Do not run a server or a second pytest process on this
clone concurrently. Tests provision their mocked agent registry, not an ambient bureau.

DB-free subset (an unreachable URL proves it doesn't depend on the shared server):

```sh
cd backend
DATABASE_URL=postgresql://invalid:invalid@127.0.0.1:1/dbfree .venv/bin/pytest -q \
  tests/test_voice.py tests/test_planner_conversation.py tests/test_solana_reference.py \
  tests/test_planner_workflow.py tests/test_demo_db.py
```

`test_pages.py` is **DB-backed**, even though its requests are read-only.

## Forecast history

`GET /api/forecasts?company=company-020&run_id=<id>&limit=20` returns immutable
forecast revisions and dated expected/pessimistic lines. The API writes event,
metadata and `cash_projection` hypertable rows atomically. Read endpoints do not
create revisions. Existing runs without stored history remain replayable; new
forecasts/payment refreshes begin their history. This validates local Timescale,
not a provisioned Tiger Cloud deployment.

## Resetting the shared demo database between live demos

`reset_demo.py` clears one company's runtime rows (runs, events, decisions, action_jobs,
reminders, pay_tokens, payments, negotiations, generated_reports, channel_inbox,
bill_deferrals, draw_holds, forecast_payments, forecast_history, cash_projection) and never
touches dataset tables. It refuses any non-local DATABASE_URL and only prints counts
unless `--yes` is passed. Stop the backend first so its workers do not race the delete.

```sh
cd backend
.venv/bin/python scripts/reset_demo.py --company company-020          # counts only
.venv/bin/python scripts/reset_demo.py --company company-020 --yes    # delete
```

## Phone bot without Twilio

`scripts/call_smoke.py` synthesizes caller speech with macOS `say`, converts it to 8 kHz
mono mu-law with `afconvert`, and streams Twilio Media Streams frames to `/voice/photon`.
It checks the greeting, the transcribed question, tool calls, the spoken answer, the one
clarifying question and a follow-up, saves the assistant's audio as a WAV and reports
whether Gemini Live accepted the configured model. The backend needs `VOICE_STREAM_TOKEN`
in its environment (it is not in `.env`):

```sh
cd backend
export VOICE_STREAM_TOKEN=$(openssl rand -hex 16)
.venv/bin/uvicorn owed.main:app --host 127.0.0.1 --port 8000 &
.venv/bin/python scripts/call_smoke.py            # report in .local/call-smoke-<stamp>/
```

## End-to-end checks in Chrome

`cd frontend && npm run e2e` starts its own API and bureau on an isolated database, opens
real Chrome (fake microphone input) and checks every rail page for data and console errors,
new chat / past chat / rename / reload, the dock and Home mics, a "yes" that resolves the
pending decision, the pay page updating Get paid, and the report (print + PDF). The Web
Speech checks are informational: Chrome's speech service is not available to automation.
