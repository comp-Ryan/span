# Job 5 — follow-up branches (Astra)

Scope: existing `parent_run_id`, `what_if_customer`, `show_late`, and `/cash`
contracts. No endpoint or event shape changes. No provider keys required.

## Fixes

- Saved-run replay now loads all descendant histories, then hands off to the buffered
  SSE stream with event-ID deduplication. Previously only child `run.start` events
  passed the saved-run filter; their subsequent node events were discarded.
- Branch headings link to the actual parent question, including on scoring-only runs.
  Cross-run node references retain `parent_run_id` in the frontend reducer.
- Late-payer runs render their one scoring node and the ordered invoice list, rather
  than a generic planner card. They do not show a never-finishing report placeholder.
- What-if charts explicitly label the excluded customer and use the existing scoped
  `/cash?never_pays=<customer_id>&target=<inherited target>` request. While loading,
  live mode never substitutes the browser's fixture estimate or a stale scenario line.

## Verification

Actual native Chrome interaction against the built frontend at `localhost:8015/?live`,
using an isolated clone of the loaded Intuit database (not the shared demo database):

1. Load the two-week payroll question, then type **What if Evergreen doesn't pay?**
   in the app's search/ask input and press Enter.
2. The new run appears below the parent, with a clickable **branches from** label.
   Evergreen means **Evergreen Juniper Flats Removals** (`cust-customer-37`).
3. Seven open invoices disappear from the scenario: **204 → 197**. Payroll and bills
   are unchanged. The expected shortfall changes **$384.94 → $668.96** and pessimistic
   shortfall **$2,752.92 → $3,023.03**. The chase lever excludes Evergreen.
4. The scenario's left-column daily chart ends at **-$1,778.73** expected and
   **-$3,484.96** pessimistic (baseline **-$1,508.63 / -$3,214.86**). These differ from
   the horizon forecast by design: the daily series posts receipts on predicted dates,
   whereas the forecast uses each invoice's by-target probability. See the contract.
5. Type **Show me who's late** and press Enter. A second branch shows **126 overdue
   invoices**, ordered from **21 days late down to 1**, with invoice IDs and amounts.

6. Reload `/?live&run=<root>`: both child headings, the scenario and the 126-row late
   scoring node are restored without re-asking either question.

Screenshots: [Evergreen scenario](screenshots/job-5-evergreen-live.png),
[late invoices](screenshots/job-5-late-live.png).

Tests: 41 backend tests pass against an isolated database; four focused frontend tests
(`npm run test:branches`) pass; production build passes. Lint has only the existing
App.tsx warnings. Integration tests must not share mutable payment tables with another
session or a running demo: use a separate `DATABASE_URL`.

Coordination: Devin PR #24 appeared during final verification. This is an independently
verified alternative, not a PR to merge on top of #24 unchanged. The initial open-PR
and remote-branch check showed no job-5 claim. Neither implementation was merged here.
