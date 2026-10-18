# Span — live two-minute demo script

`cd frontend && npm run record` builds the frontend, creates a **new isolated local
Timescale database for every take**, launches its own API + local uAgent bureau,
and clicks the actual UI. Outputs: `frontend/demo-out/live-<timestamp>/demo.webm`,
optional MP4 (if ffmpeg is installed), stills, 1500×900 thumbnail, and `evidence.json`.
The recording has no narration track; add this voiceover in editing. Gemini latency
is real; trim waits, never substitute outcomes. Offline fixtures are explicitly
separate: `npm run record:fixture`.

## 0:00–0:15 · Home and the question
“Span turns the business owner's cash question into a visible workflow. These are
Palletbay's books from the Intuit dataset, with October 6 as the accounting clock.”
Show Home, then a new General chat: “Am I going to make payroll these next two weeks?
Evergreen may be late.”

## 0:15–0:35 · One clarification, not a guessed assumption
“Before answering, Span asks one question: should Evergreen pay by payday?
We say no. That answer becomes a branch of the original conversation.”
Show the actual clarification and the owner reply. If the model doesn't clarify,
stop the take and investigate; don't stage a replacement card.

## 0:35–0:55 · Forecast and explicit approval
“Here is the expected cash line, and the downside if slow payers slip. The workflow
shows the books, invoice scores and supported next steps. It asks before acting.”
Read **the actual gap displayed in this take**, not a fixed $385 script. Review the
selected recipients, then click the real **Yes, text them** decision.

## 0:55–1:20 · Messages and negotiation
“Approved reminders are drafted, and a simulated customer asks for installments.
Separate local uAgents negotiate within the owner's policy.”
Show the simulated channel labels, the four-message exchange, and actual agreement.
Do not claim real SMS delivery or an Agentverse registration.

## 1:20–1:40 · Payment and history
“Open the installment's real pay link from Get paid. This is a simulated card payment,
not a live charge. The receipt triggers a new forecast, saved alongside the previous
one in the Timescale hypertable—the local Tiger Data-compatible development setup.”
Read the actual receipt amount. If a shortfall remains, **say so**. Never force a
successful-payroll claim or a green outcome. Chart revisions retain their assumptions.

## 1:40–2:00 · Continuity and the report
“Saved chats keep their branches and their own names. Ask who's late to inspect
another branch. Reports preserve the numbers and actions for the bookkeeper.”
Show renamed/reloaded chat, the late-payer branch, and Reports. Close with Span logo.

**Disclosures:** live Gemini tool loop and local database; browser-typed interaction,
not a live telephone call; simulated customer reply/messages/card payment; local
uAgent exchange; dataset clock, probabilistic estimates, no Tiger Cloud deployment
claim. Payment/model outputs must match `evidence.json` for the selected take.
