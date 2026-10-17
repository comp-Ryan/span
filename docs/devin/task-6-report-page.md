# Devin task 6: the one-page report in the frontend

**Goal.** `GET /reports/{report_id}` (which you built in task 2) rendered as a page in the React frontend at `/report/:id`, in the same visual language as the main screen, printable, with a "Download PDF" link to `/reports/{id}.pdf`.

**Read first.** `docs/devin/README.md`; `docs/api-contract.md` section `GET /reports/{report_id}`; `frontend/src/styles.css` (tokens: light ground, white cards, hairlines, green/blue/amber/red, Avenir Next); `frontend/src/App.tsx` for component style (no UI framework, inline SVG icons, `.node`, `.lever`, `.kv`, `.bar` classes). `backend/owed/reports/` for the JSON you produce.

**Build.**
1. Add a tiny router (no new deps if possible: read `location.pathname`; or `react-router-dom` if you prefer) so `/` stays the canvas and `/report/:id` renders `Report.tsx`.
2. `frontend/src/Report.tsx` fetching `/api/reports/:id`. Layout, top to bottom, one column max 880 px wide, white page on the grey ground:
   - header: brand mark, company, "Generated <time>", button "Download PDF" (→ `/api/reports/:id.pdf`) and "Print".
   - the question as the title; the answer line big; status pill (Covered / Tight / Short).
   - "Numbers used": a 2×3 grid of small stat tiles (bank, payroll, bills, owed, expected in time, cushion then → now).
   - "How I got there": render `workflow.svg` if present, else a compact horizontal list of the nodes with icons.
   - "What I did": the actions list (texted X, reply, agreement, payment) with icons and timestamps.
   - "Still open": open items as a checklist.
   - "Narrative": the two paragraphs.
   - footer: disclosures in small grey text (simulated customer agents; model scoring; no dataset rows modified).
3. Print stylesheet: hide nav/buttons, A4/Letter friendly.
4. Link from the main canvas: when a run has `report_id`, show a small "Open one-page report" link under the chart (edit `App.tsx` minimally: it's `run.report_id`).
5. Empty/error states: "Report not ready yet" with a retry.

**Acceptance.** `/report/<id>` renders for a real report from the backend (create one via `POST /reports/generate?run_id=...` after a run), looks like the main screen's family, prints cleanly. Screenshot in the PR.

**PR.** Branch `devin/report-page`. Keep changes to `App.tsx` to the link only.
