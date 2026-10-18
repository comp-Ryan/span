# Devin task 1: pay-link page with Visa sandbox and Solana devnet rails

**Goal.** A customer receives a reminder SMS containing `https://<host>/pay/<token>`. Opening it shows a minimal, clean page: company name, invoice number, amount, due date, and two ways to pay: card (Visa sandbox) or USDC on Solana devnet. Paying marks the invoice paid in our database and records a payment row. This is the step that makes the gap on the canvas go down, so it must work end to end.

**Solana scope and data boundary.** The Solana rail is devnet-only. Each pay token has a deterministic 32-byte reference in its SPL transfer and Solana Pay URI; the chain provides settlement proof, not application storage. Postgres remains the private operational database for pay links, invoice state, and payment records.

**Read first.** `docs/devin/README.md`, then the `/pay/{token}` sections of `docs/api-contract.md`, then `backend/owed/db/schema.sql` tables `pay_tokens`, `payments`.

**Build.**
1. `backend/owed/payments/__init__.py` with a FastAPI router mounted at `/pay`:
   - `GET /pay/{token}` (JSON, per contract) and `GET /pay/{token}/page` (HTML page; also serve the HTML when `Accept: text/html`).
   - `POST /pay/{token}` accepting `{"rail":"visa","card":{...}}` or `{"rail":"solana","signature":"..."}`; returns the receipt per contract; sets `pay_tokens.status='paid'`, inserts into `payments`, and inserts an `events` row `{"event":"card.updated", ...}` plus `{"event":"node.create","data":{"type":"action","title":"<customer> paid $<amt>", ...}}` for the token's `run_id` (look up via `reminders.pay_token` → `run_id`; if no run, use run_id `null`).
   - Idempotent: paying an already-paid token returns the existing receipt with HTTP 200.
2. **Visa rail.** Use Visa Developer sandbox. Read https://developer.visa.com for the simplest tokenized payment or "Visa Direct / CyberSource sandbox" flow available to a new sandbox account; credentials via env `VISA_USER_ID`, `VISA_PASSWORD`, `VISA_CERT_PATH`, `VISA_KEY_PATH` (add to `.env.example`). If the sandbox cannot be reached or is not provisioned, the rail must still complete with `receipt.sandbox_mode = "simulated"` and the UI must label it "simulated sandbox". Never block the demo on Visa.
3. **Solana rail.** Devnet only. `GET /pay/{token}` returns `solana: {recipient, mint, amount, reference, uri}`. Page offers "Pay with Phantom (devnet)" that builds a USDC SPL transfer (devnet USDC mint `4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU`) to `SOLANA_RECIPIENT`, includes the token-specific readonly reference, and sends it via the wallet; then posts the signature. Backend verifies the signature via `SOLANA_RPC_URL` (default `https://api.devnet.solana.com`) with `getTransaction`, checking the reference and a token transfer to the recipient for >= amount (6 decimals). If no wallet is installed, show the recipient + amount and a "I've paid, here's my signature" input.
4. **Page design.** One column, max 420 px, system font, one accent color `#ff7a45`, dark and light via `prefers-color-scheme`, works on a phone. No frameworks; vanilla HTML/CSS/JS in `backend/owed/payments/page.html`. Keep it calm: this is what a judge sees on their own phone.
5. **Helper to mint tokens.** `owed.payments.create_pay_token(con, company_id, invoice_id, amount, run_id=None, negotiation_id=None) -> token`. Astra's reminder code will call this.
6. **Tests** in `backend/tests/test_payments.py`: token lifecycle, idempotency, Visa simulated path, Solana verification with a mocked RPC response.

**Acceptance.**
- `curl -X POST localhost:8000/pay/<tok> -d '{"rail":"visa","card":{"number":"4111111111111111","exp_month":12,"exp_year":2028,"cvv":"123","name":"Test"}}'` returns a receipt and the `payments` and `events` tables have rows.
- Opening the page on a phone and paying with the card form completes in under 10 seconds.
- `pytest -q` green.

**PR.** Branch `devin/pay-page`. Include screenshots of the page (dark and light) in the PR description, and note whether the real Visa sandbox or the simulated path was used.
