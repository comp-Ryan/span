# Span jobs board

Universal prompt for any agent (Devin, Astra, Claude):
> Pull https://github.com/comp-Ryan/span main. Read docs/JOBS.md and docs/devin/README.md. Do job N only. Branch `<you>/job-N`, open a PR against main with a summary and screenshots, do not merge. If blocked by a missing key or credit, say exactly what is missing and stop.

State is tracked here. Mark a job `claimed` by putting your name on it in your PR description; the merger flips it to `done`.

| # | Job | Brief | Status |
|---|-----|-------|--------|
| 1 | Home page `/home` | docs/devin/task-7-home-page.md | open |
| 2 | Demo recorder (video, stills, 1500×900 thumbnail) | docs/devin/task-5-demo-recorder.md | open (a `span-recorder` clone has 1 unpushed commit; push it first) |
| 3 | Veri fine-tune of the reminder drafter | docs/devin/task-3-veri-finetune.md | open (needs VERI_API_KEY + credits; `owed-drafter` clone has 2 unpushed commits) |
| 4 | Mock vendor portal + Browser Use submission | docs/devin/task-4-mock-portal.md | open (Tier 3; `span-portal` clone is dirty) |
| 5 | Follow-up branches end to end | `POST /ask` with `parent_run_id` for `what_if_customer` ("what if Evergreen doesn't pay?") and `show_late`; frontend renders the branch under the first run with a "branches from" label and the left-column chart updates to the scenario. Verify from the UI in `?live` mode. | open |
| 6 | Planner runs look like workflows | Planner tool nodes (`tool-*`) currently render generically. Map each tool to the proper visual: `rank_chase`→levers card with selectable customers, `score_customer`→dot row + history, `forecast_cash`→cash node, `query_books`→books node. Answer becomes the verdict strip when it contains a yes/no/number. | open |
| 7 | Deploy | One `docker compose up` on Vultr: Postgres with the dataset loaded, API, built frontend served at `/`, `/hub` kept, HTTPS via Caddy, domain from Ryan. Update `deploy/`. | open |
| 8 | Sentry | Init with Tracing + Logs + AI agent monitoring on every Gemini call; find one real bug via a trace and write it into `docs/submission/devpost.json` → `sentry_bug_writeup`. Needs SENTRY_DSN. | open |
| 9 | Agentverse | Register the Span agent with Chat Protocol so ASI:One finds it; verify a question from ASI:One starts a run. Needs AGENTVERSE_API_KEY. | open |
| 10 | Voice path | Gemini Live (`gemini-3.8-live`) + ElevenLabs over Photon media stream, Twilio fallback. Needs PHOTON or TWILIO key + ELEVENLABS key. End-to-end: call in, ask, hear the answer, see the canvas move. | open |
| 11 | Tests | pytest for the payroll run (node sequence, numbers), planner tools (each returns per contract), decisions; vitest for `frontend/src/events.ts` reducer against `fixture.json`. | open |
| 12 | Devpost pack | README with screenshots and architecture, 2-min video script, `docs/submission/devpost.json` sections filled from the actual code (how we built it, challenges, what we learned), disclosures. | open |
| 13 | Repo hygiene | Remove stale nested clones once their branches are pushed; `frontend/README.md`; `.env.example` complete; `make dev` that starts db + api + frontend. | open |

Done: event stream, payroll run, Gemini planner (gemini-3.8-flash), day-by-day cash, pessimistic forecast, Photon/Twilio modules, decisions + negotiation + payments loop, pay page (Visa sandbox + Solana devnet), report JSON/PDF + `/report/:id`, frontend workspace (constants left, workflow right, iMessage panel), selectable customers, run replay by id.
