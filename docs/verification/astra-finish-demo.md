# Astra — finish-demo verification (2026-10-17)

## Preserved source and scope

Worktree: `owed-backend`, local branch `astra/finish-demo`, based on preserved
`wip/live-demo` **5b724d1** (includes main **492b2b6**). Existing planner clarification,
payroll, browser/server voice, pages, question card, connector arrows, General chat
title, and approval guard were retained. Main checkout was not edited. No commit,
push or merge was performed. This document describes **local uncommitted work**.

## Assigned items

- **3 Sidebar:** New chat empties/focuses Ask; root chats newest first; company/run-scoped
  local renames; saved child/grandchild replay; SSE/replay race regression coverage.
- **4 Reset:** `backend/scripts/demo_db.py` provisions a new local clone and permits
  reset only with an isolation marker, unique safe name, exact confirmation and no
  other connected clients. Shared `owed` was never reset or used for tests.
- **5 Recorder:** `npm run record` now performs live UI requests, with a fresh isolated
  database per take and its own API/bureau. `record:fixture` remains explicit offline.
  Video script updated to actual behavior and disclosures; no fixed success outcome.
- **6 Tests:** payment reference/URI contracts, wrong-reference and cross-invoice
  signature rejection; planner metadata/ScoreRow/levers/approval guard; DB isolation
  gate prevents accidental shared-DB execution.
- **7 History:** atomic event + metadata + daily series persistence in Timescale's
  `cash_projection` hypertable; company-scoped `/forecasts` endpoint and revision chart.
  Payment refresh preserves each forecast node's target and customer assumption.
  Local Timescale validated; Tiger Cloud deployment is not claimed.
- **8 PR27:** manually ported head **7691eea**. Real planner decisions call
  `resolveDecision`; no fake follow-up decision. Additive tool/row/book metadata,
  specialized workflow visuals and verdict strip; preserved detail/report handling.
- **9 E2E:** real Gemini clarification, no reminders before approval, actual UI Yes,
  three simulated reminders, actual local uAgent negotiation, pay-page form payment,
  reforecast/history, renamed saved-chat replay, late and Evergreen branches, Reports.

## Test results

- Backend full suite: **127 passed** on dedicated `span_test_astra_1792296918`.
- DB-free subset: **44 passed**, with an unreachable DATABASE_URL. (`test_pages.py`
  is read-only but **not DB-free**, so it belongs in the isolated full suite.)
- Frontend: **46 passed**; branch suite **4 passed**; production build passed.
- Lint: exits successfully with the same **10 pre-existing warnings**; no new warnings.
- `git diff --check`: clean.

The suite does not use real provider credentials. Test-local configuration pins the
fixture company instead of inheriting main's company selection and creates its own
mocked customer-agent registry.

## Successful live take

`frontend/demo-out/live-20261018042627680/` (ignored artifacts):

- `demo.webm`, nine actual screenshots, `thumbnail-1500x900.png`, `evidence.json`.
- Root: `run-3dc38429dd5344a19bd30169b9426243`.
- Planner branch: `run-5835d0b99e7a466299b94e835f9908b3`.
- Late branch: `run-17dcc9a9fb134522a8428a93f4993a16`.
- Evergreen what-if: `run-23f4ec4174824b928eb574dec3bb1804`.
- Dedicated database: `span_demo_record_20261018042627680`.
- Three reminders; local negotiation reached two installments.
- Actual UI card simulator receipt **$183.10**. Forecast gap **$668.96 → $544.45**.
  Four stored history snapshots across the planner/what-if runs. No false gap-closed claim.
- Messaging/customer reply/card payment are explicitly simulated. Browser interaction
  is not a telephone call. No Agentverse, live Photon or Tiger Cloud claim.
- Recorder stopped its own API/bureau after capture; the database remains inspectable.
- MP4 is optional and was not produced because ffmpeg is not installed. WebM is ready;
  voiceover/editing remains separate from raw capture.

Live checks also found and fixed two production integration bugs:

1. Home/Get paid SPA navigation was missing; `/reports` and `/customers` collided
   with JSON routes. HTML-preferring browser requests now receive the built SPA,
   while JSON and `/api/*`, `/hub`, missing assets and genuine 404s stay intact.
2. `/api/pay/:token/page` incorrectly parsed `pay` as the token. Both root and API
   pay aliases now locate the actual token; receipt was verified through that API alias.

See `docs/demo-recording.md` for safe repeatable commands. Contract additions were
written in `docs/api-contract.md` alongside their implementations.

PR #27 was closed **unmerged** after verification; provenance and the local-only
status are explicit in [the closing comment](https://github.com/comp-Ryan/span/pull/27#issuecomment-6245657709).
The successful take's report PDF was also fetched from its isolated database,
verified as HTTP 200 with `%PDF-` bytes, and saved as `report.pdf`. Browser HTML
navigation, JSON `/api/*`, genuine missing-API 404, and `/hub` were rechecked.
The worktree's ignored `.env` now points to that isolated demo database (company-020),
while retaining the re-copied provider keys and this worktree's original agent seed.
