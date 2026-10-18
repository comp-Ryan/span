"""Solana devnet rail: verify a USDC SPL transfer to our recipient via getTransaction."""
from __future__ import annotations

import hashlib

import httpx

from owed.config import settings

DECIMALS = 6
_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


class SolanaError(ValueError):
    pass


def _base58_encode(value: bytes) -> str:
    """Encode bytes with the Bitcoin/Solana base58 alphabet, preserving leading zero bytes."""
    zeros = len(value) - len(value.lstrip(b"\0"))
    number = int.from_bytes(value, "big")
    encoded = ""
    while number:
        number, digit = divmod(number, 58)
        encoded = _BASE58_ALPHABET[digit] + encoded
    return "1" * zeros + encoded


def reference_for_token(pay_token: str) -> str:
    """Return a deterministic, 32-byte public-key reference unique to a random pay token."""
    digest = hashlib.sha256(b"owed-solana-pay-reference:v1:" + pay_token.encode("utf-8")).digest()
    return _base58_encode(digest)


def get_transaction(signature: str, rpc_url: str | None = None) -> dict | None:
    body = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction",
            "params": [signature, {"encoding": "jsonParsed", "commitment": "confirmed",
                                   "maxSupportedTransactionVersion": 0}]}
    r = httpx.post(rpc_url or settings.solana_rpc_url, json=body, timeout=10.0)
    r.raise_for_status()
    payload = r.json()
    if "error" in payload:
        raise SolanaError(payload["error"].get("message", "rpc error"))
    return payload.get("result")


def received_amount(tx: dict, recipient: str, mint: str) -> int:
    """Base units of `mint` that `recipient` gained in this transaction (sum over its token accounts)."""
    meta = tx.get("meta") or {}
    pre = {b["accountIndex"]: b for b in meta.get("preTokenBalances") or []}
    gained = 0
    for post in meta.get("postTokenBalances") or []:
        if post.get("owner") != recipient or post.get("mint") != mint:
            continue
        after = int(post["uiTokenAmount"]["amount"])
        before_b = pre.get(post["accountIndex"])
        before = int(before_b["uiTokenAmount"]["amount"]) if before_b else 0
        gained += after - before
    return gained


def _account_key_strings(tx: dict) -> set[str]:
    message = ((tx.get("transaction") or {}).get("message") or {})
    keys = message.get("accountKeys") or []
    values = []
    for key in keys:
        if isinstance(key, str):
            values.append(key)
        elif isinstance(key, dict) and key.get("pubkey"):
            values.append(key["pubkey"])
    return set(values)


def verify_transfer(signature: str, recipient: str, mint: str, amount: float, reference: str,
                    rpc_url: str | None = None) -> dict:
    if not signature or len(signature) < 60:
        raise SolanaError("invalid signature")
    tx = get_transaction(signature, rpc_url)
    if tx is None:
        raise SolanaError("transaction not found on devnet (wait a few seconds and retry)")
    if (tx.get("meta") or {}).get("err"):
        raise SolanaError("transaction failed on chain")
    if reference not in _account_key_strings(tx):
        raise SolanaError("transaction is missing the expected pay-link reference")
    got = received_amount(tx, recipient, mint)
    need = round(amount * 10**DECIMALS)
    if got < need:
        raise SolanaError(f"transfer too small: got {got / 10**DECIMALS:.6f}, need {amount:.2f} USDC")
    return {"signature": signature, "slot": tx.get("slot"), "received": got / 10**DECIMALS,
            "cluster": "devnet", "sandbox": True}
