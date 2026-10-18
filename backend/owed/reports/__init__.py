"""One-page run report (docs/api-contract.md, GET /reports/{report_id}), rebuilt from the run's events."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import sentry_sdk
from psycopg.types.json import Jsonb

from owed.config import settings
from owed.reports.svg import render_svg

log = logging.getLogger(__name__)
METRICS = Path(__file__).resolve().parents[2] / "models" / "payment_model_metrics.json"
OPEN = ("running", "waiting")


def replay(events: list[dict]) -> dict:
    """Fold node.create/node.update/decision events into node state, keeping creation order."""
    nodes: dict[str, dict] = {}
    forecasts: list[dict] = []
    decisions: list[dict] = []
    run_start: dict = {}
    for e in events:
        kind, d = e["event"], e["data"]
        if kind == "run.start":
            run_start = d
        elif kind == "decision":
            decisions.append(d)
        elif kind == "node.create":
            nodes[d["node_id"]] = {"id": d["node_id"], "type": d["type"], "title": d.get("title", ""),
                                   "status": d.get("status", "running"), "parent": d.get("parent"),
                                   "data": dict(d.get("data") or {})}
        elif kind == "node.update" and d.get("node_id") in nodes:
            n = nodes[d["node_id"]]
            for k in ("status", "title"):
                if d.get(k):
                    n[k] = d[k]
            data = d.get("data") or {}
            if "round" in data:
                n["data"].setdefault("rounds", []).append(data["round"])
                data = {k: v for k, v in data.items() if k != "round"}
            n["data"].update(data)
            if "row" in d:
                n["data"].setdefault("rows", []).append(d["row"])
            if "progress" in d:
                n["data"]["progress"] = d["progress"]
            if n["type"] == "forecast" and "gap" in data:
                forecasts.append({**n["data"]})
    return {"nodes": nodes, "forecasts": forecasts, "decisions": decisions, "run_start": run_start}


def _first(nodes: dict, type_: str) -> dict:
    return next((n for n in nodes.values() if n["type"] == type_), {"data": {}})


def _children(nodes: dict, nid: str) -> list[dict]:
    return [n for n in nodes.values() if n["parent"] == nid]


def _descendants(nodes: dict, nid: str) -> list[dict]:
    out = []
    for c in _children(nodes, nid):
        out += [c, *_descendants(nodes, c["id"])]
    return out


def money(x: float) -> str:
    return f"${x:,.0f}" if abs(x) >= 1000 else f"${x:,.2f}"


def _customer_names(nodes: dict) -> dict[str, str]:
    names = {}
    for lever in _first(nodes, "levers")["data"].get("levers", []):
        for t in lever.get("targets", []):
            names[t["invoice_id"]] = t["customer"]
    return names


def _who(node: dict, names: dict) -> str:
    inv = node["data"].get("invoice_id")
    if inv in names:
        return names[inv]
    words = node["title"].split(" ", 1)
    return words[1] if len(words) > 1 else node["title"]


PAST = {"Texting": "Texted", "Emailing": "Emailed", "Calling": "Called", "Asking": "Asked", "Sending": "Sent"}


def _actions(nodes: dict, names: dict) -> list[dict]:
    out = []
    for n in nodes.values():
        if n["type"] != "action" or n["status"] != "done" or n["data"].get("kind") in ("reply", "negotiation", "payment"):
            continue
        verb, _, rest = n["title"].partition(" ")
        title = f"{PAST[verb]} {rest}" if verb in PAST else n["title"]
        sub = _descendants(nodes, n["id"])
        parts = []
        for s in sub:
            k = s["data"].get("kind")
            if k == "negotiation" and s["data"].get("agreement"):
                parts.append(f"Agreed to {len(s['data']['agreement'].get('installments', []))} installments")
        paid = sum(float(s["data"].get("amount", 0)) for s in sub if s["data"].get("kind") == "payment")
        if paid:
            parts.append(f"${paid:,.2f} paid")
        if not parts:
            reply = next((s for s in sub if s["data"].get("kind") == "reply"), None)
            parts.append(f"Replied: \"{reply['data'].get('text', '')}\"" if reply else
                         n["data"].get("result") or ("No reply yet" if n["data"].get("kind") == "reminder" else "Done"))
        out.append({"title": title, "result": "; ".join(parts)})
    # Payments that arrived without a reminder in this run still count as outcomes.
    for n in nodes.values():
        if n["data"].get("kind") == "payment" and not any(
                a["type"] == "action" and a["data"].get("kind") == "reminder" for a in _ancestors(nodes, n)):
            out.append({"title": n["title"], "result": f"${float(n['data'].get('amount', 0)):,.2f} paid"})
    return out


def _ancestors(nodes: dict, n: dict) -> list[dict]:
    out = []
    while n.get("parent") in nodes:
        n = nodes[n["parent"]]
        out.append(n)
    return out


def _decision_open(con, d: dict, nodes: dict) -> bool:
    row = con.execute("select resolved from decisions where decision_id=%s and run_id=%s",
                      (d["decision_id"], d.get("run_id"))).fetchone() if con else None
    if row is not None:
        return row["resolved"] is None
    # No decisions row (e.g. replayed fixture): later work under the node means it was answered.
    return not _children(nodes, d["node_id"])


def _open_items(con, nodes: dict, decisions: list[dict], names: dict) -> list[str]:
    items = []
    for n in nodes.values():
        if n["type"] != "action":
            continue
        kind = n["data"].get("kind")
        sub = _descendants(nodes, n["id"])
        if kind == "reminder" and n["status"] == "done" and not any(s["data"].get("kind") == "reply" for s in sub):
            items.append(f"{_who(n, names)}: no reply yet")
        elif n["status"] in OPEN:
            installments = n["data"].get("agreement", {}).get("installments", [])
            paid = sum(float(s["data"].get("amount", 0)) for s in sub if s["data"].get("kind") == "payment")
            pending = []
            for i, inst in enumerate(installments, 1):
                if paid >= float(inst["amount"]) - 0.005:
                    paid -= float(inst["amount"])
                else:
                    pending.append((i, inst))
            if pending:
                who = next((_who(a, names) for a in _ancestors(nodes, n) if a["data"].get("kind") == "reminder"), "Customer")
                items += [f"{who}: installment {i} of ${float(p['amount']):,.2f} due {p['due']}" for i, p in pending]
            else:
                items.append(f"{n['title']} ({n['status']})")
    for d in decisions:
        if _decision_open(con, d, nodes):
            items.append(f"Decision waiting on you: {d['prompt']}")
    levers = _first(nodes, "levers")["data"]
    done_kinds = {n["data"].get("kind") for n in nodes.values() if n["type"] == "action"}
    for lever in levers.get("levers", []):
        if lever["id"] in levers.get("recommended", []) and lever["id"] != "chase" and lever["id"] not in done_kinds:
            items.append(f"{lever['label']}: pending owner confirmation")
    return items


def _disclosures(nodes: dict) -> list[str]:
    out = []
    if any(n["data"].get("kind") == "negotiation" for n in nodes.values()):
        out.append("Customer agents simulated from payment history")
    rows = _first(nodes, "scoring")["data"].get("rows", [])
    if any(r.get("source") == "jev" for r in rows):
        out.append("Scoring by Jev")
    else:
        try:
            mae = json.loads(METRICS.read_text())["mae_days_late"]
            out.append(f"Scoring by Span model (held-out MAE {mae:g} days)")
        except (OSError, KeyError, ValueError):
            out.append("Scoring by Span model")
    if any(n["data"].get("kind") == "payment" and n["data"].get("rail") == "visa" for n in nodes.values()):
        simulated = any(n['data'].get('sandbox_mode')=='simulated' or n['data'].get('receipt',{}).get('sandbox_mode')=='simulated' for n in nodes.values())
        out.append("Card payments are simulated; no Visa transaction occurred" if simulated else "Card payments run in the Visa sandbox")
    return out


def _answer(verdict: str, gap_then: float | None, gap_now: float | None) -> str:
    if gap_then is None:
        return (verdict or "").capitalize()
    yes_no = (verdict or ("yes" if gap_then <= 0 else "no")).capitalize()
    then = f"{money(gap_then)} short" if gap_then > 0 else "payroll covered in the expected forecast"
    if gap_now is None or abs(gap_now - gap_then) < 0.005:
        return f"{yes_no}, {then}."
    now = f"{money(gap_now)} short now" if gap_now > 0 else "payroll covered now"
    return f"{yes_no}, {then} at the time of asking; {now}."


def template_narrative(r: dict, ctx: dict, forecast: dict) -> str:
    n = r["numbers"]
    p1 = (f"You asked \u201c{r['question']}\u201d {r['company']} had {money(n['bank_balance'] or 0)} in the bank "
          f"against {money(n['payroll'] or 0)} of payroll due {ctx.get('payroll_date', 'on payday')}")
    if forecast.get("bills_due_by_target"):
        p1 += f", with {money(forecast['bills_due_by_target'])} of bills due first"
    p1 += (f". Customers owe {money(n['owed'] or 0)}; the payment model expected about "
           f"{money(n['expected_by_target'] or 0)} of it to arrive in time, which left a gap of {money(n['gap_then'] or 0)}.")
    did = r["actions"]
    p2 = f"I took {len(did)} action{'s' if len(did) != 1 else ''}. " if did else "No actions have been taken yet. "
    p2 += " ".join(f"{a['title']}: {a['result'][:1].lower()}{a['result'][1:].rstrip('.')}."
                   for a in did if a["result"] != "No reply yet")
    if n["gap_now"] is not None and n["gap_then"] is not None and n["gap_now"] != n["gap_then"]:
        p2 += f" The gap is now {money(n['gap_now'])}." if n["gap_now"] > 0 else " Payroll is now covered."
    if r["open_items"]:
        p2 += f" {len(r['open_items'])} item{'s are' if len(r['open_items']) != 1 else ' is'} still open."
    return f"{p1}\n\n{p2.strip()}"


@sentry_sdk.trace(op="gen_ai.chat", name="report.gemini_narrative")
def gemini_narrative(r: dict) -> str | None:
    if not settings.gemini_api_key:
        return None
    brief = {k: r[k] for k in ("company", "question", "answer", "numbers", "actions", "open_items")}
    prompt = ("Write exactly two short paragraphs, plain language, for a small-business owner reading a one-page report. "
              "Paragraph one: the question, the answer and the numbers behind it. Paragraph two: what was done, what "
              "happened, and what is still open. No headings, no bullet points, no markdown, no invented numbers. "
              "Separate the paragraphs with one blank line.\n\n" + json.dumps(brief))
    try:
        res = httpx.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
            headers={"x-goog-api-key": settings.gemini_api_key},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.3, "thinkingConfig": {"thinkingBudget": 0}}},
            timeout=20)
        res.raise_for_status()
        text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        return text or None
    except Exception:
        log.exception("gemini narrative failed; using template")
        return None


def build_report(con, run_id: str, report_id: str | None = None, narrate: bool = True) -> dict:
    run = con.execute("select * from runs where run_id=%s", (run_id,)).fetchone()
    if not run:
        raise LookupError(run_id)
    rows = con.execute("select event, data, run_id from events where run_id=%s order by id", (run_id,)).fetchall()
    events = [{"event": e["event"], "data": {**e["data"], "run_id": e["run_id"]}} for e in rows]
    st = replay(events)
    nodes, forecasts = st["nodes"], st["forecasts"]
    ctx, answer = _first(nodes, "context")["data"], _first(nodes, "answer")["data"]
    first_fc, last_fc = (forecasts[0], forecasts[-1]) if forecasts else ({}, {})
    company = ctx.get("company")
    if not company:
        c = con.execute("select display_name from companies where company_id=%s", (run["company_id"],)).fetchone()
        company = c["display_name"] if c else run["company_id"]
    gap_then = first_fc.get("gap", answer.get("gap"))
    gap_now = last_fc.get("gap", gap_then)
    names = _customer_names(nodes)
    report_id = report_id or "rep-" + uuid4().hex[:12]
    report = {
        "report_id": report_id, "run_id": run_id, "generated_at": datetime.now(UTC).isoformat(),
        "company": company, "question": run["question"] or st["run_start"].get("question", ""),
        "answer": _answer(answer.get("answer"), gap_then, gap_now),
        "numbers": {"bank_balance": ctx.get("bank_balance"), "payroll": ctx.get("payroll_amount", first_fc.get("need")),
                    "owed": first_fc.get("owed_total"), "expected_by_target": first_fc.get("expected_by_target"),
                    "gap_then": gap_then, "gap_now": gap_now},
        "workflow": {"nodes": list(nodes.values()),
                     "edges": [{"from": n["parent"], "to": n["id"]} for n in nodes.values() if n["parent"] in nodes]},
        "actions": _actions(nodes, names),
        "open_items": _open_items(con, nodes, st["decisions"], names),
        "narrative": "",
        "disclosures": _disclosures(nodes),
        "pdf_url": f"{settings.public_base_url.rstrip('/')}/reports/{report_id}.pdf",
    }
    decided = {d["node_id"]: ("open" if _decision_open(con, d, nodes) else "resolved") for d in st["decisions"]}
    report["workflow"]["svg"] = render_svg(report["workflow"]["nodes"], decided)
    try:
        report["narrative"] = (gemini_narrative(report) if narrate else None) or template_narrative(report, ctx, first_fc)
    except Exception:
        log.exception("narrative failed")
        report["narrative"] = report["answer"]
    return report


def generate(con, run_id: str) -> dict:
    """Build, persist and announce a report. Caller commits; emit runs on its own connection afterwards."""
    report = build_report(con, run_id)
    run = con.execute("select company_id from runs where run_id=%s", (run_id,)).fetchone()
    con.execute("insert into generated_reports(report_id, run_id, company_id, doc) values (%s,%s,%s,%s)",
                (report["report_id"], run_id, run["company_id"], Jsonb(report)))
    con.execute("update runs set report_id=%s where run_id=%s", (report["report_id"], run_id))
    return report
