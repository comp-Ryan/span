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
- Devpost: Veri claim removed (reminders use the template drafter).

## Results

| Check | Result |
|---|---|
| Backend full suite, isolated DB | 192 passed (`pytest -q`) |
| Backend DB-free subset | 105 passed |
| Frontend | vitest 54 passed · branches 4 passed · build OK · lint 11 pre-existing warnings, none new |
| Live question battery (20 questions incl. follow-up) | 20/20 answered, no failed nodes, numbers grounded in tool results |
| Planner voice routing | plain payroll question → one clarifying question → "no" → $668.96 short + one action; "go with your estimate" → $384.94 short + one action |
| Phone bridge without Twilio (`call_smoke.py`) | gemini-3.8-live accepted; greeting, transcription, tools, clarifying question, spoken answer, follow-up all PASS; 31 s of assistant audio |
| Live recorder (`npm run record`) | full take `frontend/demo-out/live-20261018050748376/` (11 stills, demo.webm, thumbnail, report.pdf, evidence.json); 1 of 3 reminders negotiated at that commit, $183.10 paid, outcome honestly not green |
| Chrome e2e (`npm run e2e`) | rail pages, customer detail, new chat / past chat / rename / reload, typed "yes" resolves the decision, reminders → negotiation → pay link, pay page updates Get paid, report generate/print/PDF: PASS. Home mic recognized the fake-microphone WAV in one run; Web Speech is otherwise not reliable headless (informational) |

## Known limits

- Gemini prepaid credits ran out at 05:26 (402 RESOURCE_EXHAUSTED); the second recorder
  take (three negotiations, expected green outcome) and further live checks need a top-up.
- Real phone calls need a Twilio number and a public URL (see `docs/voice-setup.md`).
- Nothing was deployed; no secrets or `.env` files were changed.
