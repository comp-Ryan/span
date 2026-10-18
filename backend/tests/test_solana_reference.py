"""DB-free Solana reference verification tests; all RPC responses are mocked."""
from __future__ import annotations

import httpx
import pytest
from urllib.parse import parse_qs, urlparse

from owed.config import settings
from owed.payments import _public, solana

RECIPIENT = "Receiver111111111111111111111111111111111"
MINT = "Mint111111111111111111111111111111111111"
SIGNATURE = "5" * 88
ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _base58_decode(value: str) -> bytes:
    number = 0
    for char in value:
        number = number * 58 + ALPHABET.index(char)
    payload = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return b"\0" * (len(value) - len(value.lstrip("1"))) + payload


def _transaction(account_keys: list, err=None) -> dict:
    return {
        "slot": 42,
        "transaction": {"message": {"accountKeys": account_keys}},
        "meta": {
            "err": err,
            "preTokenBalances": [{
                "accountIndex": 1, "mint": MINT, "owner": RECIPIENT,
                "uiTokenAmount": {"amount": "100", "decimals": 6},
            }],
            "postTokenBalances": [{
                "accountIndex": 1, "mint": MINT, "owner": RECIPIENT,
                "uiTokenAmount": {"amount": "1000100", "decimals": 6},
            }],
        },
    }


def _mock_rpc(monkeypatch, tx):
    requests = []

    def fake_post(url, json=None, timeout=None):
        requests.append((url, json, timeout))
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "result": tx},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(solana.httpx, "post", fake_post)
    return requests


def test_reference_is_deterministic_unique_and_a_32_byte_base58_public_key():
    first = solana.reference_for_token("tok_random-pay-token-A")
    assert first == solana.reference_for_token("tok_random-pay-token-A")
    assert first != solana.reference_for_token("tok_random-pay-token-B")
    assert len(_base58_decode(first)) == 32
    assert all(char in ALPHABET for char in first)


def test_pay_link_data_exposes_reference_and_solana_pay_uri(monkeypatch):
    monkeypatch.setattr(settings, "solana_recipient", RECIPIENT)
    monkeypatch.setattr(settings, "solana_usdc_mint", MINT)
    token = "tok_pay-link-uri"
    data = _public({
        "pay_token": token, "amount": 12.34, "company_name": "Example Co",
        "doc_number": "INV-1", "due_date": None, "status": "unpaid",
        "customer_name": "Payer",
    })

    assert data["solana"]["reference"] == solana.reference_for_token(token)
    parsed = urlparse(data["solana"]["uri"])
    assert parsed.scheme == "solana" and parsed.path == RECIPIENT
    query = parse_qs(parsed.query)
    assert query["reference"] == [data["solana"]["reference"]]
    assert query["amount"] == ["12.34"] and query["spl-token"] == [MINT]
    assert query["cluster"] == ["devnet"]


def test_verify_accepts_transfer_with_expected_readonly_reference(monkeypatch):
    reference = solana.reference_for_token("tok_for-reference")
    requests = _mock_rpc(monkeypatch, _transaction([
        {"pubkey": RECIPIENT, "signer": False, "writable": False},
        {"pubkey": reference, "signer": False, "writable": False},
    ]))

    result = solana.verify_transfer(SIGNATURE, RECIPIENT, MINT, 1.0, reference)

    assert result["received"] == 1.0
    assert result["cluster"] == "devnet"
    assert requests[0][1]["method"] == "getTransaction"
    assert requests[0][1]["params"][0] == SIGNATURE


@pytest.mark.parametrize("keys", [
    [{"pubkey": RECIPIENT, "signer": False, "writable": False}],
    [{"pubkey": RECIPIENT}, {"pubkey": "WrongReference11111111111111111111111111111"}],
])
def test_verify_rejects_missing_or_wrong_reference(monkeypatch, keys):
    reference = solana.reference_for_token("tok_expected-reference")
    _mock_rpc(monkeypatch, _transaction(keys))

    with pytest.raises(solana.SolanaError, match="reference"):
        solana.verify_transfer(SIGNATURE, RECIPIENT, MINT, 1.0, reference)
