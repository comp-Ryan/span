"""Pay-link page and the two pay rails (Visa sandbox card, USDC on Solana devnet).

Shapes follow docs/api-contract.md `GET /pay/{token}` and `POST /pay/{token}`.
"""
from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse

from owed.config import settings
from owed.db import conn
from owed.payments import solana, visa

try:
    from owed.events import emit as _bus_emit  # type: ignore
except ImportError:
    _bus_emit = None

router = APIRouter(prefix="/pay", tags=["pay"])
PAGE = Path(__file__).parent / "page.html"


def create_pay_token(con, company_id: str, invoice_id: str, amount, run_id: str | None = None,
                     negotiation_id: str | None = None) -> str:
    """Mint a pay link token for one invoice (or one installment of it). Returns the token."""
    token = "tok_" + secrets.token_urlsafe(12)
    con.execute("""insert into pay_tokens (pay_token, company_id, invoice_id, amount, status, negotiation_id, run_id)
                   values (%s, %s, %s, %s, 'unpaid', %s, %s)""",
                (token, company_id, invoice_id, round(float(amount), 2), negotiation_id, run_id))
    con.commit()
    return token


def _load(con, token: str) -> dict:
    row = con.execute("""
        select t.pay_token, t.company_id, t.invoice_id, t.amount, t.status, t.negotiation_id, t.run_id,
               c.display_name company_name, i.doc_number, i.due_date, i.customer_name, i.customer_id
          from pay_tokens t
          join companies c on c.company_id = t.company_id
          left join invoices i on i.company_id = t.company_id and i.id = t.invoice_id
         where t.pay_token = %s""", (token,)).fetchone()
    if not row:
        raise HTTPException(404, "unknown pay link")
    return row


def _run_id(con, tok: dict) -> str | None:
    if tok.get("run_id"):
        return tok["run_id"]
    r = con.execute("select run_id from reminders where pay_token=%s and run_id is not null limit 1",
                    (tok["pay_token"],)).fetchone()
    return r["run_id"] if r else None


def _payment_row(con, token: str) -> dict | None:
    return con.execute("select * from payments where pay_token=%s order by paid_at limit 1", (token,)).fetchone()


def _receipt_response(p: dict) -> dict:
    return {"payment_id": p["payment_id"], "status": "paid", "receipt": p["receipt"]}


def _public(tok: dict, payment: dict | None = None) -> dict:
    amount = float(tok["amount"])
    out = {
        "company_name": tok["company_name"],
        "invoice": {"doc_number": tok["doc_number"], "amount": amount,
                    "due_date": tok["due_date"].isoformat() if tok["due_date"] else None},
        "status": tok["status"],
        "payer_name": tok["customer_name"],
        "solana": {"recipient": settings.solana_recipient, "mint": settings.solana_usdc_mint, "amount": amount},
        "visa": {"sandbox_mode": "sandbox" if visa.configured() else "simulated"},
    }
    if payment:
        out["payment"] = _receipt_response(payment)
    return out


def _wants_html(request: Request) -> bool:
    """Browsers lead with text/html; API clients ask for application/json or */*."""
    first = request.headers.get("accept", "").split(",")[0].strip()
    return first.startswith("text/html")


@router.get("/{token}/page", response_class=HTMLResponse, include_in_schema=False)
def pay_page(token: str):
    with conn() as con:
        _load(con, token)  # 404 for unknown tokens before serving the page
    return HTMLResponse(PAGE.read_text())


@router.get("/{token}")
def get_pay(token: str, request: Request):
    with conn() as con:
        tok = _load(con, token)
        payment = _payment_row(con, token) if tok["status"] == "paid" else None
    if _wants_html(request):
        return HTMLResponse(PAGE.read_text())
    return _public(tok, payment)


@router.post("/{token}")
def post_pay(token: str, body: dict = Body(...)):
    rail = body.get("rail")
    if rail not in ("visa", "solana"):
        raise HTTPException(400, "rail must be 'visa' or 'solana'")
    with conn() as con:
        tok = _load(con, token)
        if tok["status"] == "paid":
            existing = _payment_row(con, token)
            if existing:
                return _receipt_response(existing)
        amount = float(tok["amount"])
        payment_id = "pay-" + secrets.token_hex(4)
        paid_at = datetime.now(UTC).astimezone()
        receipt = {"amount": amount, "paid_at": paid_at.isoformat(timespec="seconds"), "rail": rail}
        try:
            if rail == "visa":
                receipt.update(visa.charge(body.get("card") or {}, amount, payment_id))
            else:
                receipt.update(solana.verify_transfer(body.get("signature") or "", settings.solana_recipient,
                                                      settings.solana_usdc_mint, amount))
        except (visa.CardError, solana.SolanaError) as e:
            raise HTTPException(402, str(e)) from None
        except httpx.HTTPError as e:  # RPC transport failure
            raise HTTPException(502, f"could not verify payment: {e}") from None

        con.execute("""insert into payments (payment_id, pay_token, company_id, invoice_id, rail, amount, paid_at, receipt)
                       values (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (payment_id, token, tok["company_id"], tok["invoice_id"], rail, amount, paid_at, json.dumps(receipt)))
        con.execute("update pay_tokens set status='paid' where pay_token=%s", (token,))
        run_id = _run_id(con, tok)
        card_id = f"card-{tok['invoice_id']}"
        customer = tok["customer_name"] or "Customer"
        _emit(con, run_id, tok["company_id"], "card.updated",
              {"run_id": run_id, "card_id": card_id, "invoice_id": tok["invoice_id"], "status": "paid",
               "payment_id": payment_id, "amount": amount, "rail": rail, "pay_token": token})
        _emit(con, run_id, tok["company_id"], "node.create",
              {"run_id": run_id, "node_id": f"n-{payment_id}", "type": "action",
               "title": f"{customer} paid ${amount:,.2f}", "status": "done", "parent": None,
               "data": {"card_id": card_id, "invoice_id": tok["invoice_id"], "doc_number": tok["doc_number"],
                        "customer": customer, "amount": amount, "rail": rail, "payment_id": payment_id,
                        "sandbox_mode": receipt.get("sandbox_mode", "devnet" if rail == "solana" else None)}})
        con.commit()
    return {"payment_id": payment_id, "status": "paid", "receipt": receipt}


def _emit(con, run_id: str | None, company_id: str, event: str, data: dict) -> None:
    """Write an event row in the contract shape; uses owed.events.emit once Astra lands the bus."""
    if _bus_emit:
        _bus_emit(run_id, event, data)
        return
    con.execute("insert into events (run_id, company_id, event, data) values (%s, %s, %s, %s)",
                (run_id, company_id, event, json.dumps(data)))
