"""Mock vendor AP portal + Browser Use submission (docs/devin/task-4-mock-portal.md).

Routes (plain HTML, boring enterprise look):
  GET  /mock-portal/            login form (any email + any password)
  POST /mock-portal/login       sets a cookie, shows the "Submit invoice" form
  POST /mock-portal/submit      multipart form -> confirmation page with CONF-xxxxxx
  GET  /mock-portal/confirmations/{conf}   JSON lookup used by tests and the agent
  GET  /portal/screenshots/{name}          screenshots captured by Browser Use runs

submit_via_portal(run_id, invoice) drives a Browser Use cloud agent through the
portal, uploads the invoice PDF, and returns {"confirmation", "screenshot_path"}.
It emits node.create (type action, kind portal, running) then node.update done.
"""
from __future__ import annotations

import asyncio
import html
import json
import re
import secrets
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, Cookie, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from owed.config import settings
from owed.events import emit
from owed.portal.pdf import render_invoice_pdf

router = APIRouter(tags=["portal"])
PAGE = (Path(__file__).parent / "page.html").read_text()
SCREENSHOT_DIR = Path(__file__).resolve().parents[2] / "models" / "portal_screenshots"
CONF_RE = re.compile(r"CONF-[0-9A-Z]{6}")

# In-memory ledger of submissions: enough for a mock portal, inspectable in tests.
SUBMISSIONS: dict[str, dict] = {}


def _page(body: str) -> HTMLResponse:
    return HTMLResponse(PAGE.replace("<!--BODY-->", body))


LOGIN = """
<h1>Supplier sign in</h1>
<div class="sub">Enter your registered supplier credentials to submit invoices for payment.</div>
<form method="post" action="/mock-portal/login">
  <fieldset><legend>Credentials</legend>
    <label for="email">Email address <span class="req">*</span></label>
    <input type="email" id="email" name="email" required autocomplete="username">
    <label for="password">Password <span class="req">*</span></label>
    <input type="password" id="password" name="password" required autocomplete="current-password">
  </fieldset>
  <button type="submit" id="sign-in">Sign in</button>
</form>
"""

FORM = """
<h1>Submit invoice</h1>
<div class="sub">Signed in as <b>{email}</b>. Fields marked <span class="req">*</span> are required. Attach the invoice as PDF.</div>
<div class="note">Invoices are routed to the AP queue after submission. Record the confirmation number for your files.</div>
<form method="post" action="/mock-portal/submit" enctype="multipart/form-data">
  <fieldset><legend>Invoice details</legend>
    <label for="vendor_name">Vendor name <span class="req">*</span></label>
    <input type="text" id="vendor_name" name="vendor_name" required>
    <label for="invoice_number">Invoice number <span class="req">*</span></label>
    <input type="text" id="invoice_number" name="invoice_number" required>
    <label for="amount">Amount (USD) <span class="req">*</span></label>
    <input type="number" id="amount" name="amount" step="0.01" min="0.01" required>
    <label for="due_date">Due date <span class="req">*</span></label>
    <input type="date" id="due_date" name="due_date" required>
  </fieldset>
  <fieldset><legend>Attachment</legend>
    <label for="invoice_pdf">Invoice PDF <span class="req">*</span></label>
    <input type="file" id="invoice_pdf" name="invoice_pdf" accept="application/pdf" required>
  </fieldset>
  <button type="submit" id="submit-invoice">Submit invoice</button>
</form>
"""

CONFIRMED = """
<h1>Invoice received</h1>
<div class="ok">Your invoice has been accepted into the AP queue.<br><br>
  Confirmation number: <span class="conf" id="confirmation">{conf}</span></div>
<table class="kv">
  <tr><td>Vendor</td><td>{vendor}</td></tr>
  <tr><td>Invoice number</td><td>{number}</td></tr>
  <tr><td>Amount</td><td>${amount:,.2f}</td></tr>
  <tr><td>Due date</td><td>{due}</td></tr>
  <tr><td>Attachment</td><td>{filename} ({size:,} bytes)</td></tr>
  <tr><td>Received</td><td>{received}</td></tr>
</table>
<p><a href="/mock-portal/">Submit another invoice</a></p>
"""


@router.get("/mock-portal/", response_class=HTMLResponse, include_in_schema=False)
@router.get("/mock-portal", response_class=HTMLResponse, include_in_schema=False)
def portal_home(ap_session: str | None = Cookie(None)):
    if ap_session:
        return _page(FORM.format(email=html.escape(ap_session)))
    return _page(LOGIN)


@router.post("/mock-portal/login", response_class=HTMLResponse, include_in_schema=False)
def portal_login(email: str = Form(...), password: str = Form(...)):
    resp = _page(FORM.format(email=html.escape(email)))
    resp.set_cookie("ap_session", email, httponly=True, samesite="lax")
    return resp


@router.post("/mock-portal/submit", response_class=HTMLResponse, include_in_schema=False)
async def portal_submit(vendor_name: str = Form(...), invoice_number: str = Form(...), amount: float = Form(...),
                        due_date: str = Form(...), invoice_pdf: UploadFile = File(...),
                        ap_session: str | None = Cookie(None)):
    if amount <= 0:
        raise HTTPException(422, "Amount must be positive")
    blob = await invoice_pdf.read()
    if not blob.startswith(b"%PDF"):
        raise HTTPException(422, "Attachment must be a PDF")
    conf = "CONF-" + secrets.token_hex(3).upper()
    SUBMISSIONS[conf] = {"confirmation": conf, "vendor_name": vendor_name, "invoice_number": invoice_number,
                         "amount": round(amount, 2), "due_date": due_date, "filename": invoice_pdf.filename,
                         "pdf_bytes": len(blob), "submitted_by": ap_session,
                         "received_at": datetime.now(UTC).isoformat()}
    s = SUBMISSIONS[conf]
    return _page(CONFIRMED.format(conf=conf, vendor=html.escape(vendor_name), number=html.escape(invoice_number),
                                  amount=s["amount"], due=html.escape(due_date),
                                  filename=html.escape(invoice_pdf.filename or "invoice.pdf"), size=len(blob),
                                  received=s["received_at"][:19].replace("T", " ") + " UTC"))


@router.get("/mock-portal/confirmations/{conf}", include_in_schema=False)
def portal_confirmation(conf: str):
    if conf not in SUBMISSIONS:
        raise HTTPException(404, "Unknown confirmation")
    return SUBMISSIONS[conf]


@router.get("/portal/screenshots/{name}", include_in_schema=False)
def portal_screenshot(name: str):
    path = SCREENSHOT_DIR / Path(name).name
    if not path.is_file():
        raise HTTPException(404, "Screenshot not found")
    return FileResponse(path, media_type="image/png")


# ------------------------------------------------------------------ Browser Use

PORTAL_EMAIL = "ap-bot@owed.example"
PORTAL_PASSWORD = "portal-demo"


def configured() -> bool:
    return bool(settings.browser_use_api_key)


def portal_url() -> str:
    return (settings.portal_public_url or settings.public_base_url).rstrip("/") + "/mock-portal/"


def _client():
    """Factory so tests can monkeypatch the SDK."""
    from browser_use_sdk.v4 import BrowserUse
    return BrowserUse(api_key=settings.browser_use_api_key)


def task_prompt(invoice: dict, pdf_name: str) -> str:
    return (
        f"Open {portal_url()} . Sign in with email {PORTAL_EMAIL} and password {PORTAL_PASSWORD}. "
        "On the 'Submit invoice' form fill exactly: "
        f"Vendor name = {invoice['company_name']}; Invoice number = {invoice['doc_number']}; "
        f"Amount = {float(invoice['amount']):.2f}; Due date = {invoice['due_date']} (YYYY-MM-DD). "
        f"For the 'Invoice PDF' file input upload the file uploads/{pdf_name} from your workspace. "
        "Click 'Submit invoice'. On the confirmation page read the confirmation number, which looks like "
        "CONF-XXXXXX, and return it. Do not navigate anywhere else."
    )


OUTPUT_SCHEMA = {"type": "object", "properties": {"confirmation": {"type": "string"}},
                 "required": ["confirmation"]}


def _save_screenshot(client, run, run_id: str) -> str | None:
    """Best effort: pull the last screenshot the run recorded and save it under SCREENSHOT_DIR."""
    url = None
    try:
        events = client.runs.events(run.id)
        for ev in reversed(list(getattr(events, "events", events) or [])):
            data = ev if isinstance(ev, dict) else getattr(ev, "model_dump", dict)()
            text = json.dumps(data, default=str)
            m = re.search(r'https?://[^"\s]+\.(?:png|jpe?g)[^"\s]*', text)
            if m:
                url = m.group(0)
                break
    except Exception:  # noqa: BLE001 - screenshot is optional
        url = None
    if not url:
        return None
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{run_id}-{run.id}.png"
    try:
        r = httpx.get(url, timeout=30, follow_redirects=True)
        r.raise_for_status()
        (SCREENSHOT_DIR / name).write_bytes(r.content)
    except Exception:  # noqa: BLE001
        return None
    return f"/portal/screenshots/{name}"


def _submit_sync(run_id: str, invoice: dict, parent: str | None) -> dict:
    node_id = f"portal-{run_id}-{invoice.get('invoice_id') or invoice['doc_number']}"
    emit(run_id, "node.create", {
        "node_id": node_id, "type": "action", "status": "running", "parent": parent,
        "title": f"Submitting {invoice['doc_number']} to {invoice['customer_name']}'s AP portal",
        "data": {"kind": "portal", "invoice_id": invoice.get("invoice_id"), "doc_number": invoice["doc_number"],
                 "amount": float(invoice["amount"]), "portal_url": portal_url(), "provider": "browser_use"}})
    try:
        if not configured():
            raise RuntimeError("BROWSER_USE_API_KEY not set")
        pdf = render_invoice_pdf(invoice)
        pdf_name = f"invoice-{re.sub(r'[^A-Za-z0-9_-]', '_', str(invoice['doc_number']))}.pdf"
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / pdf_name
            pdf_path.write_bytes(pdf)
            client = _client()
            ws = client.workspaces.create(name=f"owed-portal-{uuid.uuid4().hex[:8]}")
            client.workspaces.upload(ws.id, pdf_path)
            run = client.runs.create(task_prompt(invoice, pdf_name), workspace_id=ws.id,
                                     output_schema=OUTPUT_SCHEMA, max_cost_usd=2.0)
            done = client.runs.wait_for_completion(run.id)
        out = getattr(done, "output", None) or {}
        text = (out.get("confirmation") if isinstance(out, dict) else None) or str(getattr(done, "result", "") or "")
        m = CONF_RE.search(text or "")
        if not m:
            raise RuntimeError(f"no confirmation number in agent result: {text[:200]!r}")
        confirmation = m.group(0)
        shot = _save_screenshot(client, done, run_id)
        screenshot_url = settings.public_base_url.rstrip("/") + shot if shot else None
        emit(run_id, "node.update", {
            "node_id": node_id, "status": "done",
            "title": f"{invoice['doc_number']} filed in portal · {confirmation}",
            "data": {"confirmation": confirmation, "screenshot_url": screenshot_url,
                     "browser_use_run_id": str(run.id), "submitted_at": datetime.now(UTC).isoformat()}})
        return {"confirmation": confirmation, "screenshot_path": shot, "node_id": node_id,
                "browser_use_run_id": str(run.id)}
    except Exception as e:
        emit(run_id, "node.update", {"node_id": node_id, "status": "failed",
                                     "data": {"error": str(e)[:300]}})
        raise


def submit_via_portal(run_id: str, invoice: dict, parent: str | None = None) -> dict:
    """Blocking. invoice: company_name, customer_name, doc_number, amount, due_date (+ invoice_id, terms, lines)."""
    return _submit_sync(run_id, invoice, parent)


async def submit_via_portal_async(run_id: str, invoice: dict, parent: str | None = None) -> dict:
    return await asyncio.to_thread(_submit_sync, run_id, invoice, parent)
