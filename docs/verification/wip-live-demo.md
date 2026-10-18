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
