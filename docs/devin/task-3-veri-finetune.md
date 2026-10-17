# Devin task 3: fine-tune the reminder drafter on Veri (veri.studio)

**Goal.** A small open model (Qwen3-1.7B) that writes a collections reminder as JSON given a customer's history and the invoice. Fine-tuned on Veri for the veri.studio challenge ($800) and as the second learned component for the Model Learning track. Must be usable at runtime with a Gemini fallback.

**Read first.** `docs/devin/README.md`; Veri docs: https://docs.veri.studio and https://docs.veri.studio/llms.txt. Credits: Ryan must DM `@daniung` in the LA Hacks Discord and redeem at veri.studio/settings/billing BEFORE the first run (jobs on a $0 balance are stopped). Ask Ryan for the `VERI_API_KEY`.

**Build.**
1. `backend/owed/drafter/make_dataset.py`: generate ~2,000 training rows from the Postgres data.
   - Sample (company, open or recently-paid invoice) pairs across many companies and profiles. For each, build the **prompt**: a compact JSON with company name, customer name, invoice number, amount, due date, days past due, payment terms, and the customer's history summary (n paid, avg days late, late rate, max late, any write-offs, amount vs their usual), plus a `tone` target chosen by rule: `friendly` (≤7 days late and late_rate<0.5), `firm` (8–30 days or late_rate≥0.5), `final` (>30 days or prior write-off).
   - **Answer**: JSON `{"subject": str, "body": str (≤120 words, SMS-friendly first sentence), "acceptable_terms": {"installments_ok": bool, "max_installments": int, "discount_pct_max": number}, "tone": str}`. Generate answers with Gemini `gemini-2.5-flash` as the teacher (`GEMINI_API_KEY`), with a strict system prompt (no legal threats, no invented facts, mention the amount and invoice number, one clear ask, pay link placeholder `{pay_link}`). Validate JSON; drop invalid rows.
   - Write `data/drafter/train.jsonl` and `data/drafter/holdout.jsonl` (90/10) in Veri's format: `{"prompt": [{"role":"system","content":...},{"role":"user","content":"<prompt json>"}], "answer": "<answer json string>"}`. Commit a 20-row sample to `backend/tests/fixtures/drafter_sample.jsonl`; the full files are gitignored.
2. `backend/owed/drafter/veri_job.sh` (or `.py`): `veri jobs estimate` then submit `sft_text` on `Qwen/Qwen3-1.7B` (ungated), `max_steps` ~200, cheapest GPU that fits (L4 on AWS is ~$1/hr). Print the job id and URL. Document exact commands used in `docs/devin/veri-run-log.md` with the job link, cost, and duration.
3. **Evaluation**: `backend/owed/drafter/eval.py` runs the base model and the fine-tuned model on the holdout (via Veri inference if available, else by downloading weights and running with `transformers` on CPU for 50 rows). Report JSON-validity rate and a Gemini-judged pairwise win rate (fine-tuned vs base). Write results to `models/drafter_metrics.json` matching the `drafter` block in `GET /model/metrics` of the contract.
4. **Runtime**: `backend/owed/drafter/__init__.py` exposing `draft_reminder(ctx: dict) -> dict`. Order: fine-tuned model via Veri inference endpoint if `VERI_INFERENCE_URL` is set → local `llama.cpp` if a GGUF exists at `models/drafter.gguf` → Gemini fallback. Always returns valid JSON with `source` in `{"qwen_veri","qwen_local","gemini"}`.
5. Tests: dataset builder produces valid rows on a tiny sample; `draft_reminder` falls back correctly when nothing is configured.

**Acceptance.** A completed Veri job with a link; `models/drafter_metrics.json` populated; `draft_reminder` returns valid JSON from at least the Gemini fallback.

**PR.** Branch `devin/drafter`. Include the Veri job link and the metrics table in the description.
