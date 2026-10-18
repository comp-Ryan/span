# wip/live-demo — verification record (Sat Oct 17 → Sun Oct 18, 2026)

Everything below ran on this machine against isolated clones of the local Timescale
database (`span_test_*`, `span_demo_record_*`, `span_test_e2e_*`); the shared `owed`
demo database was only read, plus the live question battery and phone smoke test
through the normal API.

## Branch contents (all pushed to `origin/wip/live-demo`)

- Preserved planner work (focused answer tools, routing, final-answer budget) and merged
  the finish-demo work (chat sidebar, live recorder, forecast history, PR #27 port,
  isolated test DB). PR #27 closed as superseded; a comment points at merge commit ac94fec.
- `scripts/ask_battery.py` (`--source call`, `--followup`), `scripts/call_smoke.py`,
  `scripts/reset_demo.py`, `scripts/demo_db.py`.
- The one clarifying question is data-driven (`planner_tools.pivotal_customer`): the
  dependable late payer whose payment by payday would flip the verdict; asked once per
  conversation; "yes", "no" or "go with your estimate" all continue; a shortfall then
  proposes one action (rank_chase) for the owner to approve.
- Chase memory: customers already texted are listed as `already_reminded`, not proposed again.
- Every simulated reminder gets its own (varied) reply and negotiation.
- Reports: planner runs carry the books (numbers no longer "—"); markdown narratives render
  on the page and in the PDF.
- `GET /cash/history` + "Forecast over time" on Home (TimescaleDB hypertable).
- Browser call mode (Call Span → greeting → listen → answer aloud via ElevenLabs → listen
  again → Hang up); `/health.voice`; `docs/voice-setup.md` for the Twilio phone path.
- Planner explains Gemini 402/401 errors and retries 429/5xx.
- Fresh-context review (7 Important findings) fixed: the clarifying question uses the signed
  payroll buffer, survives abbreviated customer names, is asked once per conversation
  (context and ancestor chain); customer scenarios never replace the baseline snapshot;
  payment refreshes keep each forecast node's own assumption; verdict cues never jump over
  another dollar amount; Home trend uses cash-before-payroll minus need; the phone smoke test
  counts only completed tools. A payroll chat now closes once the owner decides, so its report
  is generated.
- Devpost: Veri claim removed (reminders use the template drafter).

## Results

| Check | Result |
|---|---|
| Backend full suite, isolated DB | 208 passed (`pytest -q`, after the review fixes) |
| Backend DB-free subset | 119 passed |
| Frontend | vitest 54 passed · branches 4 passed · build OK · lint 11 pre-existing warnings, none new |
| Live question battery (20 questions incl. follow-up) | 20/20 answered, no failed nodes, numbers grounded in tool results |
| Planner voice routing | plain payroll question → one clarifying question → "no" → $668.96 short + one action; "go with your estimate" → $384.94 short + one action |
| Phone bridge without Twilio (`call_smoke.py`) | gemini-3.8-live accepted; greeting, transcription, tools, clarifying question, spoken answer, follow-up all PASS; 31 s of assistant audio |
| Live recorder (`npm run record`) | final take `frontend/demo-out/live-20261018063418712/` on the OpenRouter backup (11 stills, demo.webm, thumbnail, report.pdf, evidence.json): clarifying question → "go with your estimate" → $384.94 short → Yes → 3 simulated reminders → 3 local uAgent agreements → 4 real pay-page payments ($183.10, $173.72, $169.02, then $183.11 because $81.93 was still short) → outcome card green, gap 0 → Evergreen what-if → Get paid → Reports → report + PDF |
| Chrome e2e (`npm run e2e`, runs 5 and 6) | rail pages, customer detail, new chat / past chat / rename / reload, typed "yes" resolves the decision, three simulated reminders → negotiation → pay link, pay page updates Get paid, Generate report → report opens, Print observed, PDF downloads, no console errors: PASS (16 checks). Home mic recognized the fake-microphone WAV in two of four runs (informational); the dock mic check lost a click race with the call's own auto-listen (script, fixed); the browser-call check needs a planner answer and so needs Gemini credits |

| OpenRouter backup (`OPEN_ROUTER` key, 2026-10-18 06:40 UTC) | with Gemini at 402, battery questions 3 and 11 and the payroll flow (clarifying question → "go with your estimate" → $384.94 short → one action) all failed over to `google/gemini-3.8-flash` via OpenRouter and answered with the same numbers; runs carry `planner: openrouter` |

## Known limits

- Gemini prepaid credits ran out at 05:26 (402 RESOURCE_EXHAUSTED). The planner now fails over
  to OpenRouter, so typed questions and the browser call keep working; only the Twilio phone
  bridge (Gemini Live) still needs Gemini credits.
- Real phone calls need a Twilio number and a public URL (see `docs/voice-setup.md`).
- Nothing was deployed; no secrets or `.env` files were changed.

## 2026-10-18 08:30–09:00 UTC — New chat, mute, terminal chat, free-model backup

| What | Evidence |
|---|---|
| New chat page had no composer in its body (only the header search box; the dock needs a run) | `FreshChat` renders an input, three suggestions and "Call Span instead" on `/?live&new=1`; e2e "new chat" check types into it |
| Sidebar listed every test-battery run (120 roots, 28 distinct questions) | `rootChats(runs, keep)` shows one entry per question, newest run; the open chat always stays (`chatHistory.test.ts`) |
| "+ New chat" rendered with an underline | `.chat-sidebar > .btn { text-decoration: none }` |
| Mute on a browser call | reducer `mute`/`unmute` (`voiceCall.test.ts`): muted turns skip `speaking` and re-arm the mic; remembered in `localStorage` (`span.voiceMuted`); e2e browser-call check toggles Mute → Unmute |
| Which build is running | `/health.version` = git short SHA, `/health.branch`; `SPAN_VERSION` overrides (`test_version.py`) |
| Terminal chat for local testing | `backend/scripts/chat.py`: `/ask` → poll `/runs/{id}` → prompt on `decision` → `POST /decisions`; prints the backend commit first (`test_chat_cli.py`, 7 tests). Live: "Who should I chase today?" answered, approval left pending; `--decide no` resolves it and the run closes |
| Both LLM providers at $0 (Gemini 402 since 05:26 UTC; OpenRouter trial at 3,485 affordable tokens) | `OpenRouterClient` walks a model chain: 402 "can only afford N" → retry with N−64 tokens; 402/404/429/5xx → next model; 429 → one 1.5 s retry. Default chain ends in free tool-capable models (`nvidia/nemotron-3-ultra-550b-a55b:free`, `…-super-120b-a12b:free`, probed live: tool calls returned, cost 0). Context node records `planner_model` actually used |
| Chrome e2e run 8 (`demo-out/e2e-20261018085023479`) | 17 passed, 0 failed, 1 informational (Home mic transcript in headless Chrome). Dock-call check now passes only when the mic re-arms after Span speaks ("heard → Span is speaking → listening again") |
| Backend DB-free suite | 118 passed (`test_version`, `test_chat_cli`, `test_planner_backup` +5) |
