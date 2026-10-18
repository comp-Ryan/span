# Span demo runbook (what the audience sees, in order)

Company: Palletbay Storage & Warehousing (Intuit dataset, books dated Oct 6, 2026). Payday: Oct 20.
Everything on screen is live against the local Timescale database; nothing is scripted.

## Before you start

```sh
cd backend && .venv/bin/python scripts/reset_demo.py --company company-020 --yes   # clean slate (runtime rows only)
cd backend && nohup .venv/bin/uvicorn owed.main:app --host 127.0.0.1 --port 8000 --no-access-log > /tmp/span-8000.log 2>&1 &
cd frontend && npm run dev                                                           # http://127.0.0.1:5173
```

Open http://127.0.0.1:5173/home in Chrome. If Gemini credits are out, the planner answers
through OpenRouter automatically (`/api/health` → `planner_backup: "openrouter"`).

## The two-minute story

| Step | What you do | What appears | Say |
|---|---|---|---|
| 1 | Home | Four tiles (in the bank $6,534, owed $28,509, payroll next, bills due), the "How customers pay" heatmap, "Forecast over time" | "Palletbay's real books. The owner has one question." |
| 2 | Tap the mic or type: **Am I going to make payroll these next two weeks?** | The chat opens; Span reads the books and forecasts Oct 20 | "Span scores every open invoice against that customer's payment history." |
| 3 | Wait | **One question**: "Should I assume Evergreen Juniper Flats Removals will pay the $1,222 they owe by October 20, or treat them as not paying?" | "It asks the one thing the owner knows better than the model." |
| 4 | Answer **I'm not sure, go with your estimate** (or **no**) | Verdict strip **No, $385 short** (about $669 with "no") and one action: *Text 3 reliable late payers, +$1,052*, with Yes / Not now | "Honest answer, one proposed action, nothing happens without a yes." |
| 5 | Click **Yes, text them** | Three reminders go out (labeled simulated), three different customer replies, Span's agent negotiates installments with each customer's local agent under the owner's rules, agreements with pay links | "Each customer agent is simulated from that customer's real history." |
| 6 | Get paid → **Open pay page** → card 4111 1111 1111 1111, any future date, any CVV | Receipt; back in the chat the **Where you stand now** card moves: −$385 → −$82 after the three first installments; one more installment → **+$43, green** | "The gap only closes when cash really lands; the first three left $82." |
| 7 | Type or say **What if Evergreen doesn't pay?** | A branch under the same chat: the new shortfall and one next action, left pending | "Follow-ups branch from the same conversation." |
| 8 | Reports → open the report | One-page report: numbers, workflow, what was done, still open, narrative; **Download PDF** | "A document the bookkeeper can keep." |

Also worth a glance: the chat sidebar (New chat, past chats, double-click to rename), **Call Span in the
browser** on Home (greeting, hands-free turns, Hang up), and `docs/voice-setup.md` for a real phone number.

## Recorded version

`frontend/demo-out/live-20261018063418712/`: `demo.webm` (the whole flow above, recorded live),
stills `01-home` … `11-report`, `thumbnail-1500x900.png`, `report.pdf`, `evidence.json` (every run and
number in the take). Voiceover text per segment: `docs/submission/video-script.md`.
Re-record any time with `cd frontend && npm run record` (fresh isolated database per take).

## If something goes wrong on stage

- Planner error on the canvas names the cause (Gemini credits, key, OpenRouter balance).
- Browser mic needs Chrome on localhost; typing the same sentence is identical for Span.
- The outcome card turns green only when collected cash covers the gap; say the number it shows.
