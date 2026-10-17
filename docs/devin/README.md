# Working in this repo (for Devin and Astra)

**Project:** Owed. A small-business owner calls a phone number and asks "am I making payroll Friday?" The backend answers with real numbers from the Intuit QuickBooks hackathon dataset, streams its reasoning as workflow nodes to a web canvas, and when told "yes" chases customers for money. Read `docs/superpowers/specs/2026-10-17-owed-design.md` (the spec) and `docs/api-contract.md` (the contract) before anything else. The contract is the source of truth for every endpoint and event shape; change the contract file first if you must change a shape.

**Hackathon deadline:** Sunday Oct 18, 2026, 12:00 PM Pacific. No buffer. Prefer working code over perfect code; prefer small PRs that merge today.

## Layout
```
backend/                 Python 3.12, FastAPI, uv
  owed/config.py         settings from backend/.env (see .env.example)
  owed/db/schema.sql     all tables (dataset + runtime)
  owed/db/load.py        python -m owed.db.load [--reset|--facts-only]   (YAML -> Postgres, ~65 s)
  owed/finance/queries.py  SQL for payroll context, open invoices with history features, bills, peers
  owed/finance/model.py    payment-behavior model (trained; models/payment_model.pkl + metrics json)
  owed/finance/train.py    python -m owed.finance.train
  owed/hub/              local hub pages: /timeline /questions /architecture /spec (not product UI)
  owed/main.py           FastAPI app
docs/api-contract.md     THE CONTRACT
docs/superpowers/specs/  the spec
data/raw/                dataset (gitignored; scripts/fetch_data.sh downloads it)
docker-compose.yml       local TimescaleDB on :5433 (stand-in for Tiger Cloud)
```

## Run locally
```bash
./scripts/fetch_data.sh
docker compose up -d db
cd backend && uv venv -p 3.12 && uv pip install -e ".[dev]" && cp .env.example .env
.venv/bin/python -m owed.db.load --reset        # loads 100 companies
.venv/bin/python -m owed.finance.train          # ~15 s, writes models/
.venv/bin/uvicorn owed.main:app --reload --port 8000
```

## Rules
- Branch per task: `devin/<task>` or `astra/<task>`. Open a PR against `main`. Keep PRs under ~500 lines where possible.
- Tests with pytest under `backend/tests/`. Run `cd backend && .venv/bin/pytest -q` before pushing.
- No frontend code in this repo (the product frontend is built in Paper by Ryan). The only HTML allowed is the pay-link page and the mock vendor portal, both served by FastAPI.
- Secrets only via env vars listed in `backend/.env.example`; add new ones there with empty defaults.
- Money is `numeric(14,2)` in Postgres and plain JSON numbers (dollars) in the API.
- Demo company is `company-020` (Palletbay Storage & Warehousing). Dataset "today" is `2026-10-06`.
- Every externally visible step must emit an event per the contract (`node.create`, `node.update`, `decision`, `speech`, `report.ready`) through `owed.events.emit(run_id, event, data)` once Astra lands it; until then, write to the `events` table directly in the same shape.
