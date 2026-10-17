# Devin task 7: Home page (today's money picture)

**Goal.** The `Home` item in the left nav rail currently goes nowhere. Build `/home` in the React frontend: the screen an owner sees before they ask anything. Same visual language as the canvas (`frontend/src/styles.css`, `App.tsx`). Product name is **Span**.

**Read first.** `docs/devin/README.md`, `frontend/src/App.tsx` (component style, icons, `.card`, `.kv`, `.bar`, `.chips`), `frontend/src/Report.tsx` (how the simple router works in `main.tsx`), backend endpoints: `GET /companies`, `GET /runs?company=`, `GET /cash?company=&target=` (shape in `docs/api-contract.md` and `backend/owed`), `GET /brief?company=`.

**Build** `frontend/src/Home.tsx` at route `/home` (and make the rail's Home link point to it; Ask → `/`):
1. Header: "Good morning, Ryan" style greeting, company switcher (dropdown over `GET /companies`, default company-020), date.
2. Row of four stat tiles: In the bank · Owed to you (count of open invoices) · Payroll next (date + amount) · Bills due this week. Numbers from `/brief` and `/companies`.
3. "Ask Span" card: big input + mic icon + three suggestion chips ("Am I going to make payroll these next two weeks?", "Should I take Gallagher's order?", "Who should I chase today?"). Submitting navigates to `/` and starts a run via `POST /ask`.
4. "Recent threads": list from `GET /runs` — question, when, answer title (color pill: green/amber/red from the answer), link to `/?run=<id>` (the canvas should replay that run; add `?run=` support in `App.tsx` by calling `replay(runId)` from `api.ts` and feeding events through `apply` — keep that edit minimal).
5. Small cash sparkline for the next 14 days from `/cash` (reuse the SVG approach from `DailyCashChart.tsx` if practical).
6. Loading and error states; works at 1280–1600 px wide.

**Acceptance.** `/home` renders against the running backend with real numbers for company-020; clicking a suggestion lands on the canvas with a live run started; clicking a recent thread replays it. Screenshot in the PR.

**PR.** Branch `devin/home-page`. Keep `App.tsx` edits to the `?run=` replay hook and the nav links.
