"""Pay-link page: token lifecycle, idempotency, Visa simulated path, Solana verification (mocked RPC).

Runs against the local Postgres (docker compose up -d db; python -m owed.db.load). Rows it creates are removed.
"""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from owed.db import conn, apply_runtime
from owed.runs import create
from owed.main import app
from owed.payments import create_pay_token, solana, visa

COMPANY = "company-020"
RECIPIENT = "7Zr5dP1yPZ9u4hV3cKqk3kYwJmP6Yd4yQsFz2dDkTEST"
MINT = "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"
SIG = "5VERYLONGFAKESIGNATURE" + "x" * 66
CARD = {"number": "4111111111111111", "exp_month": 12, "exp_year": 2028, "cvv": "123", "name": "Test"}


@pytest.fixture(scope="module")
def client():
    apply_runtime()
    return TestClient(app)


@pytest.fixture
def invoice():
    with conn() as con:
        row = con.execute("""select id, doc_number, customer_name, total_amount, due_date from invoices
                             where company_id=%s and doc_number is not null and id in (select invoice_id from invoice_facts where company_id='company-020' and open_balance>=123.45) order by id limit 1""", (COMPANY,)).fetchone()
    assert row, "dataset not loaded"
    return row


@pytest.fixture
def token(invoice):
    rid = create(COMPANY, "Test payment", "web", "free_question")
    with conn() as con:
        tok = create_pay_token(con, COMPANY, invoice["id"], 123.45, run_id=rid)
    yield tok
    with conn() as con:
        con.execute("delete from events where data->>'pay_token'=%s or data->>'run_id'='run-test'", (tok,))
        con.execute("delete from payments where pay_token=%s", (tok,))
        con.execute("delete from pay_tokens where pay_token=%s", (tok,))
        con.execute("delete from events where run_id=%s", (rid,))
        con.execute("delete from runs where run_id=%s", (rid,))
        con.commit()


@pytest.fixture
def simulated(monkeypatch):
    monkeypatch.setattr(visa, "configured", lambda: False)


@pytest.fixture
def solana_env(monkeypatch):
    from owed.config import settings
    monkeypatch.setattr(settings, "solana_recipient", RECIPIENT)
    monkeypatch.setattr(settings, "solana_usdc_mint", MINT)


def rpc_result(gained_base_units: int, owner: str = RECIPIENT, mint: str = MINT, err=None):
    return {"slot": 123456, "meta": {
        "err": err,
        "preTokenBalances": [{"accountIndex": 2, "mint": mint, "owner": owner,
                              "uiTokenAmount": {"amount": "1000000", "decimals": 6}}],
        "postTokenBalances": [{"accountIndex": 2, "mint": mint, "owner": owner,
                               "uiTokenAmount": {"amount": str(1000000 + gained_base_units), "decimals": 6}}]}}


def mock_rpc(monkeypatch, result):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(solana.httpx, "post", fake_post)
    return calls


# ---- token lifecycle -------------------------------------------------------------------------------------

def test_create_pay_token_and_get(client, token, invoice, solana_env, simulated):
    assert token.startswith("tok_")
    r = client.get(f"/pay/{token}")
    assert r.status_code == 200
    body = r.json()
    assert body["company_name"] == "Palletbay Storage & Warehousing"
    assert body["invoice"] == {"doc_number": invoice["doc_number"], "amount": 123.45,
                               "due_date": invoice["due_date"].isoformat()}
    assert body["status"] == "unpaid"
    assert body["payer_name"] == invoice["customer_name"]
    assert body["solana"] == {"recipient": RECIPIENT, "mint": MINT, "amount": 123.45}
    assert body["visa"]["sandbox_mode"] == "simulated"


def test_unknown_token_404(client):
    assert client.get("/pay/tok_nope").status_code == 404
    assert client.get("/pay/tok_nope/page").status_code == 404
    assert client.post("/pay/tok_nope", json={"rail": "visa", "card": CARD}).status_code == 404


def test_html_page(client, token):
    r = client.get(f"/pay/{token}/page")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "#ff7a45" in r.text and "prefers-color-scheme" in r.text and "Pay with Phantom" in r.text
    r = client.get(f"/pay/{token}", headers={"Accept": "text/html,application/xhtml+xml"})
    assert "text/html" in r.headers["content-type"]
    r = client.get(f"/pay/{token}", headers={"Accept": "application/json"})
    assert "application/json" in r.headers["content-type"]


# ---- Visa simulated path ----------------------------------------------------------------------------------

def test_visa_simulated_pays_and_records(client, token, invoice, simulated):
    r = client.post(f"/pay/{token}", json={"rail": "visa", "card": CARD})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "paid" and body["payment_id"].startswith("pay-")
    rc = body["receipt"]
    assert rc["amount"] == 123.45 and rc["rail"] == "visa" and rc["last4"] == "1111"
    assert rc["sandbox"] is True and rc["sandbox_mode"] == "simulated" and rc["paid_at"]

    with conn() as con:
        tok = con.execute("select status from pay_tokens where pay_token=%s", (token,)).fetchone()
        pay = con.execute("select * from payments where pay_token=%s", (token,)).fetchone()
        events = con.execute("""select event, run_id, data from events
                                where coalesce(data->>'payment_id', data->'data'->>'payment_id')=%s order by id""",
                             (body["payment_id"],)).fetchall()
    assert tok["status"] == "paid"
    assert pay["rail"] == "visa" and float(pay["amount"]) == 123.45 and pay["invoice_id"] == invoice["id"]
    assert [e["event"] for e in events] == ["card.updated", "node.create"]
    card, node = events
    assert card["run_id"].startswith("run-") and card["data"]["status"] == "paid"
    assert card["data"]["card_id"] == f"card-{invoice['id']}"
    assert node["data"]["type"] == "action" and node["data"]["status"] == "done"
    assert node["data"]["title"] == f"{invoice['customer_name']} paid $123.45"

    assert client.get(f"/pay/{token}").json()["status"] == "paid"


def test_visa_rejects_bad_card(client, token, simulated):
    r = client.post(f"/pay/{token}", json={"rail": "visa", "card": {**CARD, "number": "4111111111111112"}})
    assert r.status_code == 402 and "card number" in r.json()["error"]["message"]
    r = client.post(f"/pay/{token}", json={"rail": "visa", "card": {**CARD, "exp_year": 2020}})
    assert r.status_code == 402 and "expired" in r.json()["error"]["message"]
    with conn() as con:
        assert con.execute("select status from pay_tokens where pay_token=%s", (token,)).fetchone()["status"] == "unpaid"


def test_bad_rail(client, token):
    assert client.post(f"/pay/{token}", json={"rail": "cash"}).status_code == 400


def test_visa_falls_back_to_simulated_when_sandbox_fails(monkeypatch):
    monkeypatch.setattr(visa, "configured", lambda: True)
    monkeypatch.setattr(visa, "_sandbox_charge", lambda card, amount, ref: None)
    rc = visa.charge(CARD, 10.0, "pay-x")
    assert rc["sandbox_mode"] == "simulated" and rc["last4"] == "1111"


def test_visa_uses_sandbox_result_when_available(monkeypatch):
    monkeypatch.setattr(visa, "configured", lambda: True)
    monkeypatch.setattr(visa, "_sandbox_charge",
                        lambda card, amount, ref: {"transaction_identifier": 234234, "approval_code": "A1B2C3"})
    rc = visa.charge(CARD, 10.0, "pay-x")
    assert rc["sandbox_mode"] == "sandbox" and rc["transaction_identifier"] == 234234


# ---- idempotency -----------------------------------------------------------------------------------------

def test_paying_twice_returns_same_receipt(client, token, simulated):
    first = client.post(f"/pay/{token}", json={"rail": "visa", "card": CARD}).json()
    again = client.post(f"/pay/{token}", json={"rail": "visa", "card": {**CARD, "number": "0000"}})
    assert again.status_code == 200
    assert again.json() == first
    other_rail = client.post(f"/pay/{token}", json={"rail": "solana", "signature": SIG})
    assert other_rail.status_code == 200 and other_rail.json()["payment_id"] == first["payment_id"]
    with conn() as con:
        n = con.execute("select count(*) n from payments where pay_token=%s", (token,)).fetchone()["n"]
    assert n == 1
    assert client.get(f"/pay/{token}").json()["payment"] == first


# ---- Solana verification with mocked RPC ---------------------------------------------------------------------

def test_solana_verifies_transfer(client, token, solana_env, monkeypatch):
    calls = mock_rpc(monkeypatch, rpc_result(123_450_000))  # 123.45 USDC
    r = client.post(f"/pay/{token}", json={"rail": "solana", "signature": SIG})
    assert r.status_code == 200, r.text
    rc = r.json()["receipt"]
    assert rc["rail"] == "solana" and rc["signature"] == SIG and rc["received"] == 123.45 and rc["cluster"] == "devnet"
    assert calls[0][1]["method"] == "getTransaction" and calls[0][1]["params"][0] == SIG
    with conn() as con:
        assert con.execute("select status from pay_tokens where pay_token=%s", (token,)).fetchone()["status"] == "paid"


def test_solana_accepts_overpayment(monkeypatch):
    mock_rpc(monkeypatch, rpc_result(200_000_000))
    assert solana.verify_transfer(SIG, RECIPIENT, MINT, 123.45)["received"] == 200.0


def test_solana_rejects_short_transfer(client, token, solana_env, monkeypatch):
    mock_rpc(monkeypatch, rpc_result(123_440_000))
    r = client.post(f"/pay/{token}", json={"rail": "solana", "signature": SIG})
    assert r.status_code == 402 and "too small" in r.json()["error"]["message"]


def test_solana_rejects_wrong_recipient_or_mint(monkeypatch):
    mock_rpc(monkeypatch, rpc_result(500_000_000, owner="SomebodyElse" + "1" * 32))
    with pytest.raises(solana.SolanaError):
        solana.verify_transfer(SIG, RECIPIENT, MINT, 1.0)
    mock_rpc(monkeypatch, rpc_result(500_000_000, mint="OtherMint" + "1" * 35))
    with pytest.raises(solana.SolanaError):
        solana.verify_transfer(SIG, RECIPIENT, MINT, 1.0)


def test_solana_rejects_missing_or_failed_tx(client, token, solana_env, monkeypatch):
    mock_rpc(monkeypatch, None)
    r = client.post(f"/pay/{token}", json={"rail": "solana", "signature": SIG})
    assert r.status_code == 402 and "not found" in r.json()["error"]["message"]
    mock_rpc(monkeypatch, rpc_result(123_450_000, err={"InstructionError": [0, "Custom"]}))
    r = client.post(f"/pay/{token}", json={"rail": "solana", "signature": SIG})
    assert r.status_code == 402 and "failed" in r.json()["error"]["message"]
    r = client.post(f"/pay/{token}", json={"rail": "solana", "signature": "short"})
    assert r.status_code == 402


def test_solana_rpc_down_is_502(client, token, solana_env, monkeypatch):
    def boom(url, json=None, timeout=None):
        raise httpx.ConnectError("down", request=httpx.Request("POST", url))
    monkeypatch.setattr(solana.httpx, "post", boom)
    r = client.post(f"/pay/{token}", json={"rail": "solana", "signature": SIG})
    assert r.status_code == 502


def test_health_reports_rails(client, simulated):
    h = client.get("/health").json()
    assert h["visa"] == "simulated" and h["solana"] == "devnet"
