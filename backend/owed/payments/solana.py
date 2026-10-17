"""Solana devnet rail: verify a USDC SPL transfer to our recipient via getTransaction."""
from __future__ import annotations

import httpx

from owed.config import settings

DECIMALS = 6


class SolanaError(ValueError):
    pass


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


def verify_transfer(signature: str, recipient: str, mint: str, amount: float, rpc_url: str | None = None) -> dict:
    if not signature or len(signature) < 60:
        raise SolanaError("invalid signature")
    tx = get_transaction(signature, rpc_url)
    if tx is None:
        raise SolanaError("transaction not found on devnet (wait a few seconds and retry)")
    if (tx.get("meta") or {}).get("err"):
        raise SolanaError("transaction failed on chain")
    got = received_amount(tx, recipient, mint)
    need = round(amount * 10**DECIMALS)
    if got < need:
        raise SolanaError(f"transfer too small: got {got / 10**DECIMALS:.6f}, need {amount:.2f} USDC")
    return {"signature": signature, "slot": tx.get("slot"), "received": got / 10**DECIMALS,
            "cluster": "devnet", "sandbox": True}
