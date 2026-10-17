# Devin task 4 (Tier 3, only after tasks 1–3): mock vendor portal + Browser Use submission

**Goal.** Some customers only pay invoices submitted through their vendor portal. When a customer is flagged `requires_portal`, Owed uses Browser Use to open the portal, fill in the invoice, upload a PDF, and capture a confirmation number, which becomes an `action` node.

**Build.**
1. A static mock portal served at `/mock-portal/` (login with any email, "Submit invoice" form: vendor name, invoice number, amount, due date, PDF upload; shows a confirmation number `CONF-xxxxxx`). Plain HTML, looks like a boring enterprise AP portal.
2. `backend/owed/portal/__init__.py`: `submit_via_portal(run_id, invoice) -> {"confirmation": str, "screenshot_path": str}` using the Browser Use SDK (`BROWSER_USE_API_KEY`), task-prompted to log in and submit. Emit `node.create` (`type: action`, `data.kind: portal`, status running) then `node.update` done with the confirmation and screenshot URL.
3. Generate the invoice PDF with the same library as task 2.
4. Test: the portal form works via a plain HTTP client; the Browser Use path is tested with the SDK mocked.

**PR.** Branch `devin/portal`. Include the screenshot Browser Use captured.
