# Span — 2-minute demo video script

Record with `cd frontend && npm run record` (writes `demo-out/demo.webm` + stills). This is a scripted fixture replay with voiceover, not an open-ended “try asking anything” demo and not a claim of a live phone call. Captions carry the numbers.

**0:00–0:10 — The question.**
Screen: General chat with Ryan's question in the workflow. VO: "Ryan runs Palletbay Storage. Payroll is coming up, and he wants to know: can the business make payroll over the next two weeks?"
Show the question as the first workflow step.

**0:10–0:30 — Watch it think.**
VO: "Span reads his actual books — six and a half grand in the bank, thirteen-three payroll, almost eleven grand in bills. Then it scores all 204 open invoices against each customer's real payment history — green will pay, amber maybe."
Beat: scoring dots ticking (02-scoring). Call transcript dock opens briefly.

**0:30–0:45 — The honest answer.**
VO: "The forecast: twenty-four grand goes out, under twenty-four comes in. The answer is no — about four hundred dollars short. Even if the usual payers pay."
Beat: verdict card "No. $385 short" + gauge (03-verdict).

**0:45–1:05 — One approval at a time.**
VO: "Span shows a supported next step and asks before acting. Ryan reviews the proposed reminders and approves that step; nothing else is bundled into the decision."
Beat: lever cards, click "Yes, text them" (04-levers).

**1:05–1:30 — It chases the money.**
VO: "The texts go out. Evergreen's agent replies — cash is tight. Span's agent negotiates, under Ryan's rules: two payments of five seventy-eight. First one lands on the Visa sandbox."
Beat: conversation bubbles, negotiation rounds, "Agreed", $578 receipt (05-actions). Cash chart ticks up, outcome card flips green.

**1:30–1:50 — A follow-up.**
VO: "Ryan asks what changes if Evergreen doesn't pay. Span keeps it on the same workflow, shows the new shortfall, and offers one next action. It waits for Ryan before doing anything else."
Beat: follow-up thread appears with one pending "Yes, text Yeoman" decision (06-followup). Leave it pending; do not approve a batch of actions.

**1:50–2:00 — The report.**
VO: "And it leaves a one-page report — the question, the numbers, what it did, what's still open. Reasoning on display, then a document that stays."
Beat: `/report/:id` page + PDF (docs/devin/samples/report-page.png).
End card: Span logo, "Call Span. Ask if you'll make payroll."
