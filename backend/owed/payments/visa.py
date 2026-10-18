"""Visa rail. Real call = Visa Direct AFT (pull funds) on the Visa Developer sandbox over two-way SSL.
Falls back to a clearly labelled simulated path when credentials are missing or the sandbox fails,
so the demo never blocks on Visa."""
from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime
from pathlib import Path

import httpx

from owed.config import settings

log = logging.getLogger(__name__)

SANDBOX_URL = "https://sandbox.api.visa.com/visadirect/fundstransfer/v1/pullfundstransactions"


class CardError(ValueError):
    pass


def luhn_ok(number: str) -> bool:
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 12 or len(digits) > 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def validate_card(card: dict) -> dict:
    number = "".join(ch for ch in str(card.get("number", "")) if ch.isdigit())
    if not luhn_ok(number):
        raise CardError("invalid card number")
    try:
        month, year = int(card.get("exp_month")), int(card.get("exp_year"))
    except (TypeError, ValueError):
        raise CardError("invalid expiry") from None
    if year < 100:
        year += 2000
    now = datetime.now(UTC)
    if not 1 <= month <= 12 or (year, month) < (now.year, now.month):
        raise CardError("card expired")
    cvv = str(card.get("cvv", ""))
    if not (cvv.isdigit() and len(cvv) in (3, 4)):
        raise CardError("invalid cvv")
    return {"number": number, "exp_month": month, "exp_year": year, "cvv": cvv, "name": card.get("name") or ""}


def configured() -> bool:
    return bool(settings.visa_user_id and settings.visa_password
                and settings.visa_cert_path and settings.visa_key_path
                and Path(settings.visa_cert_path).exists() and Path(settings.visa_key_path).exists())


def _aft_payload(card: dict, amount: float, reference: str) -> dict:
    now = datetime.now(UTC)
    return {
        "acquirerCountryCode": "840",
        "acquiringBin": settings.visa_acquiring_bin,
        "amount": f"{amount:.2f}",
        "businessApplicationId": "AA",
        "cardAcceptor": {"address": {"country": "USA", "state": "CA", "zipCode": "94404"},
                         "idCode": "ABCD1234ABCD123", "name": "Span", "terminalId": "ABCD1234"},
        "localTransactionDateTime": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "retrievalReferenceNumber": now.strftime("%y%j%H") + reference[-6:].rjust(6, "0"),
        "senderCardExpiryDate": f"{card['exp_year']:04d}-{card['exp_month']:02d}",
        "senderCurrencyCode": "USD",
        "senderPrimaryAccountNumber": card["number"],
        "systemsTraceAuditNumber": reference[-6:].rjust(6, "0"),
        "cavv": "0700100038238906000013405823891061668252",
        "surcharge": "0.00",
    }


def _sandbox_charge(card: dict, amount: float, reference: str) -> dict | None:
    try:
        with httpx.Client(cert=(settings.visa_cert_path, settings.visa_key_path),
                          auth=(settings.visa_user_id, settings.visa_password), timeout=8.0) as client:
            r = client.post(SANDBOX_URL, json=_aft_payload(card, amount, reference),
                            headers={"Accept": "application/json"})
        if r.status_code != 200:
            log.warning("visa sandbox returned %s: %s", r.status_code, r.text[:300])
            return None
        body = r.json()
        return {"transaction_identifier": body.get("transactionIdentifier"),
                "approval_code": body.get("approvalCode"), "action_code": body.get("actionCode")}
    except (httpx.HTTPError, OSError, ValueError) as e:  # network, TLS, cert, JSON: never block the demo
        log.warning("visa sandbox unreachable: %s", e)
        return None


def charge(card: dict, amount: float, reference: str) -> dict:
    """Returns receipt fields: last4, sandbox_mode ('sandbox' | 'simulated'), plus provider refs."""
    card = validate_card(card)
    out: dict = {"last4": card["number"][-4:], "sandbox": True, "sandbox_mode": "simulated"}
    if configured():
        result = _sandbox_charge(card, amount, reference)
        if result:
            out.update(result, sandbox_mode="sandbox")
            return out
    out["approval_code"] = secrets.token_hex(3).upper()
    return out
