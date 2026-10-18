# Span — two-minute demo script (live flow)

`cd frontend && npm run record` records the real product, not a fixture: a fresh isolated copy
of the local Timescale database for every take, its own API and local customer-agent bureau,
the built frontend, real Gemini calls. Outputs land in `frontend/demo-out/live-<stamp>/`:
`demo.webm`, numbered stills (`01-home` … `11-report`), `thumbnail-1500x900.png`, `report.pdf`
and `evidence.json` (every run, every number). Add the voiceover in editing; trim Gemini
waits, never substitute outcomes. Read the numbers from the take, not from this script.

## 0:00–0:12 · Home and the question (01-home)
"This is Palletbay Storage, a small warehouse business on Intuit's QuickBooks dataset.
The owner asks Span one question." Type or speak: **Am I going to make payroll these next two
weeks?** (The mic is browser voice, a turn-based demo; the recording types it.)

## 0:12–0:30 · One clarifying question (02-clarifying-question)
"Span reads the books and forecasts cash on payday. Before answering it asks the one thing the
owner may know better than the model: the dependable late payer whose payment decides the
verdict." Span: *Should I assume Evergreen Juniper Flats Removals will pay the $1,222 they owe
by October 20, or treat them as not paying?* Owner: **I'm not sure, go with your estimate.**
(Say "no" instead and the forecast recalculates without Evergreen: about $669 short.)

## 0:30–0:50 · Verdict and one action (03-verdict-approval)
"Six and a half thousand in the bank, thirteen-three of payroll, almost eleven thousand of
bills, 204 invoices scored. The honest answer: no, about $385 short." Span proposes exactly
one action, texting the three reliable late payers, and waits. Click the real **Yes, text them**.

## 0:50–1:15 · Reminders, replies, negotiation (04-messages-negotiation)
"Three reminders go out on a labeled simulated channel. Each customer's agent, simulated from
that customer's real payment history, replies that cash is tight; Span's agent negotiates
installments under the owner's rules." Show the exchange and the agreements.

## 1:15–1:35 · Payment and the outcome (05–07)
"Each agreement comes with a real pay link. The first installments land on the Visa sandbox
card." Show the pay page and the receipt, then the outcome card: it turns green only when the
collected cash actually covers the gap; otherwise say how much is still short. The forecast
history keeps every revision in the Timescale hypertable.

## 1:35–1:50 · A follow-up (08-what-if-evergreen)
Owner: **What if Evergreen doesn't pay?** "Same chat, a branch: the new shortfall and one next
action, pending until the owner says yes." Leave it pending.

## 1:50–2:00 · Get paid, Reports, the report (09–11)
"Get paid shows the links and the money that came back. Reports keeps the one-page report:
the question, the numbers, what Span did, what's still open." End on the Span logo.

**Disclosures:** live Gemini planner and payment model on an isolated copy of the books;
browser-typed interaction, not a telephone call; simulated reminders, customer replies and
card payments (Visa sandbox / simulator, Solana devnet); local uAgents; dataset clock
2026-10-06; local TimescaleDB, no Tiger Cloud deployment claim.
