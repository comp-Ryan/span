# Backend status — October 17, 2026

Working copy: `LA-Hacks-AI-2026/owed-backend`, branch `astra/backend`.
It is a nested Git worktree, not the main checkout. All backend changes through PR #10
are merged to remote `main`; Devin payment and reporting PRs #5 and #7 were reviewed
and integrated. Local API: `http://localhost:8000`; customer-agent bureau: port 8001.

## Demoable now

- Company-020 deterministic payroll question → complete node chain → durable SSE/replay.
  204 invoice scores, company scoping, reconnect replay, and pending owner decision.
- Corrected two-week forecast: cash at target $12,890.06 before $13,275 payroll;
  shortfall **$384.94**. The accounting clock is October 6, not today's date.
- Local uAgents negotiation with deterministic simulated customer personas, four-message
  cap, owner-policy gate, eight-second acceptance window for compliant terms, and
  installment pay tokens. Local request/reply was exercised against the running bureau.
- Owner decision actions, simulated card payment, idempotent payment accounting,
  payment-triggered forecast updates, and JSON/PDF reports. These paths have automated
  integration coverage; live customer messaging is not yet verified.
- Sentry SDK local trace evidence caught $1,598.55 of omitted overdue bills. The query
  is fixed and the before/after artifacts are in `docs/submission/`. This is **not**
  yet a cloud Sentry trace demonstration.
- Docker image built and smoke-tested against the loaded local database, including
  health, companies, payroll, report generation/PDF, and bundled documentation.

## Numbered build status

| Step | Implemented | Remaining verification / limitation |
|---|---|---|
| 1 Events/runs/SSE | Durable Postgres event log, ordered IDs, replay and heartbeats | Local integration tests pass |
| 2 Deterministic payroll | Full node chain, trained model, real books | No keys required; ready |
| 3 Gemini tools | Bounded manual tool loop, scoped finance tools and owner approvals | Real Gemini key/model call |
| 4 Live voice | Gemini Live bridge, ElevenLabs streaming, barge-in cancellation | Live phone test; Photon publishes SIP, so implementation uses Twilio Media Streams fallback |
| 5 Photon | Beta message send, authenticated canonical inbound lookup, reply classification, owner SMS entry | Real project/senders/recipient; validate actual webhook event version; disputes currently surface as reply nodes, not a dedicated owner decision |
| 6 Agents | Local bureau, Chat Protocol, customer negotiation | Agentverse registration/discovery and ASI:One interaction; installment links are minted but not automatically messaged |
| 7 Levers/payment | Approval worker, reminder requests, cash-plan deferral/draw hold, forecast refresh | Vendor deferral is a cash-plan change, not a claim of vendor agreement; channel actions require live keys |
| 8 Sentry | SDK instrumentation, prompt/secret scrubbing, local trace evidence | DSN and cloud dashboard verification |
| 9 Vultr | Locked dependencies, Docker/Compose/Caddy, transfer/DB bootstrap script | Host or API key, domain, then actual public deployment |

Validation: **31 tests pass**. Focused Ruff checks pass. Python is pinned to 3.12
because the audio bridge uses `audioop`; its deprecation is known. No live service
success, public Agentverse registration, real Visa charge, or Vultr deployment is claimed.

## Resume with keys

Put credentials in the main checkout's ignored `backend/.env`, then tell the backend
session to re-copy it. Preserve the worktree's stable `AGENT_SEED` unless intentionally
rotating agent identities. Never commit `.env`, the model pickle, database dumps, or logs.
Use `backend/.env.example` for setting names and `deploy/README.md` for deployment.
Deployment additionally needs an SSH host (or Vultr API key to provision) and API domain.
