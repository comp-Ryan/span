# Devin task 2: report generator (JSON + PDF)

**Goal.** When a run finishes, or on request, generate the one-page report described in `docs/api-contract.md` under `GET /reports/{report_id}`: question, answer, the numbers used, the workflow picture, actions taken, outcomes, open items, a short narrative, disclosures. JSON for the Paper frontend to render, plus a PDF the owner can print or send to their accountant.

**Read first.** `docs/devin/README.md`, contract sections `GET /events`, `GET /runs/{run_id}`, `GET /reports/{report_id}`; schema tables `runs`, `events`, `generated_reports`.

**Build.**
1. `backend/owed/reports/__init__.py`:
   - `build_report(con, run_id) -> dict` that replays the `events` rows for the run and assembles the report JSON exactly per contract. Nodes come from `node.create` + the latest `node.update` per node; `actions` from nodes of type `action` with `status='done'`; `open_items` from `action` or `decision` nodes still `running`/`waiting`; `numbers` from the `context`, `forecast`, and `answer` nodes (first and latest forecast give `gap_then` and `gap_now`).
   - `narrative`: if `GEMINI_API_KEY` is set, ask Gemini (model `gemini-2.5-flash`) for two short paragraphs in plain language given the JSON; otherwise a deterministic template. Must never fail the report.
   - `POST /reports/generate?run_id=` creates a `generated_reports` row and emits an `events` row `report.ready`. `GET /reports/{report_id}` returns the JSON. `GET /reports/{report_id}.pdf` returns a PDF.
2. **Workflow picture.** Render the nodes/edges to an SVG server-side (simple top-to-bottom layered layout; six node types with the colors: context/scoring/forecast/levers neutral, answer accent `#ff7a45`, action grey, decision amber). Embed the SVG in the PDF and return it as `workflow.svg` in the JSON too.
3. **PDF.** Use `weasyprint` if it installs cleanly on macOS and Linux, else `reportlab`. One page, A4/Letter, the same calm style as the pay page. Add the dependency to `backend/pyproject.toml`.
4. **Fixture.** Create `backend/tests/fixtures/run_palletbay.json`: a realistic full event sequence for a payroll run on company-020 following the contract exactly (context → scoring with ~12 rows → forecast → answer → levers → decision → 3 actions → reply → negotiation → decision → payment → forecast update → speech → report.ready). Ryan's Paper frontend will replay this file, so it must be accurate to the contract.
5. **Tests** in `backend/tests/test_reports.py`: load the fixture into `events`, build the report, assert every top-level key, assert `gap_now < gap_then`, assert the PDF is non-empty and starts with `%PDF`.

**Acceptance.** `GET /reports/<id>` returns valid JSON per contract; the PDF opens and reads cleanly; `pytest -q` green.

**PR.** Branch `devin/reports`. Attach the rendered PDF.
