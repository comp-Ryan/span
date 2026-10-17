"""Generate docs/frontend/fixture-run-palletbay.json from real queries + the trained model.
Usage: .venv/bin/python scripts/make_fixture.py [--company company-020] [--days 14]
"""
import argparse, json, psycopg
from datetime import date, timedelta
from psycopg.rows import dict_row
from owed.config import settings
from owed.finance import queries as q
from owed.finance.model import load, band

ap = argparse.ArgumentParser(); ap.add_argument("--company", default="company-020"); ap.add_argument("--days", type=int, default=14)
ap.add_argument("--out", default="../docs/frontend/fixture-run-palletbay.json")
a = ap.parse_args()
CID = a.company; AS_OF = date(2026, 10, 6); TARGET = AS_OF + timedelta(days=a.days)
QUESTION = "Am I going to make payroll these next two weeks?" if a.days >= 10 else "Am I making payroll Friday?"
m = load()
D = lambda x: float(x) if x is not None else None
with psycopg.connect(settings.database_url, row_factory=dict_row) as con:
    co = q.company(con, CID); bal = q.bank_balance(con, CID, AS_OF); pay = q.payroll_due(con, CID, AS_OF, TARGET)
    bills = q.bills_due(con, CID, AS_OF, TARGET); inv = q.open_invoices(con, CID, AS_OF)
    scored = m.score_open(inv, (TARGET - AS_OF).days); peers = q.peer_dso(con, CID)
    hist = {r["customer_id"]: q.customer_history(con, CID, r["customer_id"], AS_OF) for r in scored[:8]}

owed_total = sum(D(r["open_balance"]) for r in scored)
exp = sum(D(r["open_balance"]) * r["p_paid_by_target"] for r in scored)
bills_total = sum(D(b["open_amount"]) for b in bills if D(b["open_amount"]) > 0)
need = pay["due_by_target"] + bills_total
cash_at = bal + exp - need
gap = round(max(0, -cash_at), 2)
cands = sorted([r for r in scored if r["days_past_due"] > 0 and band(r["p_paid_by_target"], r["p_never"]) != "red"],
               key=lambda r: D(r["open_balance"]) * r["p_paid_by_target"], reverse=True)
bycust = {}
for r in cands:
    c = bycust.setdefault(r["customer_id"], {"customer": r["customer_name"], "customer_id": r["customer_id"], "amount": 0, "n": 0, "max_dpd": 0,
                                             "p": r["p_paid_by_target"], "late_rate": D(r["late_rate"]), "avg_late": D(r["avg_late"]), "n_paid": r["n_paid"], "invoices": []})
    c["amount"] += D(r["open_balance"]); c["n"] += 1; c["max_dpd"] = max(c["max_dpd"], r["days_past_due"]); c["invoices"].append(r["invoice_id"])
top = sorted(bycust.values(), key=lambda c: c["amount"] * c["p"], reverse=True)[:3]
recovers = round(sum(c["amount"] for c in top), 2)
defer = [b for b in bills if (b["hist_days_vs_due"] or 0) >= -2 and D(b["open_amount"]) > 0][:2]
defer_amt = round(sum(D(b["open_amount"]) for b in defer), 2)
first = lambda c: c["customer"].split(" ")[0]

ev = []
def E(event, data, t=0.0):
    ev.append({"event": event, "ts_offset_s": round(t, 2), "run_id": "run-demo-020", "company_id": CID, "data": data})
E("run.start", {"question": QUESTION, "source": "call"}, 0)
E("node.create", {"node_id": "n1", "type": "context", "title": "Pulling up context", "status": "running", "parent": None}, 0.1)
E("node.update", {"node_id": "n1", "status": "done", "data": {"company": co["display_name"], "profile": co["profile"], "next_payroll_date": str(pay["next_pay_date"]), "target_date": str(TARGET),
   "payroll_due_by_target": pay["due_by_target"], "weekly_payroll": pay["weekly"], "headcount": pay["headcount"], "bills_due_by_target": round(bills_total, 2), "bank_balance": bal}}, 0.5)
E("node.create", {"node_id": "n2", "type": "scoring", "title": f"Scoring {len(scored)} open invoices", "status": "running", "parent": "n1"}, 0.6)
t = 0.6
for i, r in enumerate(sorted(scored, key=lambda r: D(r["open_balance"]), reverse=True)):
    t += 0.03
    E("node.update", {"node_id": "n2", "progress": {"done": i + 1, "total": len(scored)}, "row": {"invoice_id": r["invoice_id"], "customer": r["customer_name"], "amount": D(r["open_balance"]),
       "days_past_due": r["days_past_due"], "p_paid_by_target": r["p_paid_by_target"], "p_never": r["p_never"], "expected_days_to_pay": r["expected_days_to_pay"],
       "band": band(r["p_paid_by_target"], r["p_never"]), "source": "owed_model"}}, t)
E("node.update", {"node_id": "n2", "status": "done"}, t + 0.05)
E("node.create", {"node_id": "n3", "type": "forecast", "title": f"Forecasting through {TARGET.strftime('%b %-d')}", "status": "running", "parent": "n2"}, t + 0.1)
fc = {"owed_total": round(owed_total, 2), "expected_by_target": round(exp, 2), "payroll_due_by_target": pay["due_by_target"], "bills_due_by_target": round(bills_total, 2),
      "bank_balance": bal, "cash_at_target": round(cash_at, 2), "need": round(need, 2), "gap": gap}
E("node.update", {"node_id": "n3", "status": "done", "data": fc}, t + 0.6)
short = f"${gap:,.0f}"
ans = f"No. About {short} short." if gap > 0 else "Yes. You're covered."
spoken = (f"No. You're about {int(round(gap, -2)):,} dollars short over the next two weeks. {owed_total:,.0f} dollars is owed to you, but only about {exp:,.0f} of it is likely to land in time."
          if gap > 0 else "Yes, you're covered.")
E("node.create", {"node_id": "n4", "type": "answer", "title": ans, "status": "done", "parent": "n3", "data": {"answer": "no" if gap > 0 else "yes", "gap": gap, "spoken": spoken}}, t + 0.7)
E("speech", {"text": spoken, "audio_url": None}, t + 0.7)
E("node.create", {"node_id": "n5", "type": "levers", "title": "What closes the gap", "status": "running", "parent": "n4"}, t + 0.9)
levers = [{"id": "chase", "label": f"Text {len(top)} reliable late payers", "recovers": recovers, "targets": [
            {"customer_id": c["customer_id"], "customer": c["customer"], "amount": round(c["amount"], 2), "n_invoices": c["n"], "days_past_due": c["max_dpd"], "p_paid_by_target": c["p"],
             "reason": f"{c['max_dpd']} days late on {c['n']} invoices. Has paid {c['n_paid']} before, usually {c['avg_late']:.0f} days late, so a nudge works."} for c in top]},
          {"id": "defer_bill", "label": f"Slide {len(defer)} tolerant vendor bills a week", "recovers": defer_amt, "bills": [
            {"bill_id": b["bill_id"], "vendor": b["vendor_name"], "amount": D(b["open_amount"]), "due_date": str(b["due_date"]), "vendor_tolerance": "high" if (b["hist_days_vs_due"] or 0) > 0 else "medium"} for b in defer]},
          {"id": "hold_draw", "label": "Hold owner draw this month", "recovers": 0}]
ask = f"If I text {', '.join(first(c) for c in top)} and we slide two vendor bills a week, that covers about ${recovers + defer_amt:,.0f} of it. Want me to text them?"
E("node.update", {"node_id": "n5", "status": "done", "data": {"levers": levers, "recommended": ["chase", "defer_bill"], "ask_spoken": ask}}, t + 2.4)
E("speech", {"text": ask, "audio_url": None}, t + 2.4)
E("decision", {"decision_id": "d1", "node_id": "n5", "prompt": "Text them?", "options": [{"id": "yes", "label": "Yes, text them"}, {"id": "chase_only", "label": "Text, don't touch bills"}, {"id": "no", "label": "Not now"}], "auto_resolves_in_s": None}, t + 2.5)
t2 = t + 6.0
for i, c in enumerate(top):
    nid = f"n{6 + i}"
    E("node.create", {"node_id": nid, "type": "action", "title": f"Texting {c['customer']}", "status": "running", "parent": "n5", "data": {"kind": "reminder", "customer_id": c["customer_id"], "amount": round(c["amount"], 2), "channel": "sms",
       "draft": {"tone": "firm" if c["max_dpd"] > 7 else "friendly", "body": f"Hi {first(c)} team, this is Palletbay. {c['n']} invoices totaling ${c['amount']:,.2f} are past due, the oldest by {c['max_dpd']} days. Could you settle this week? Pay here: {{pay_link}}. Thanks, Palletbay", "source": "qwen_veri"}}}, t2 + i * 0.8)
    E("node.update", {"node_id": nid, "status": "done", "data": {"sent_at": "...", "reminder_id": f"rem-000{i + 1}", "pay_link": f"https://owed.example/pay/tok_{i + 1}"}}, t2 + i * 0.8 + 0.6)
c0 = top[0]; half = round(c0["amount"] / 2, 2)
E("node.create", {"node_id": "n9", "type": "action", "title": f"{first(c0)} replied", "status": "done", "parent": "n6", "data": {"kind": "reply", "text": "Can we split this into two payments?", "classification": "wants_plan"}}, t2 + 40)
E("node.create", {"node_id": "n10", "type": "action", "title": f"Negotiating with {first(c0)}'s agent", "status": "running", "parent": "n9", "data": {"kind": "negotiation", "negotiation_id": "neg-0001", "rounds": []}}, t2 + 41)
E("node.update", {"node_id": "n10", "data": {"round": {"n": 1, "from": "owed", "text": f"Full payment of ${c0['amount']:,.2f} by {TARGET.strftime('%b %-d')}.", "cash_effect": round(c0["amount"], 2), "p_honored": round(c0["p"], 2)}}}, t2 + 42)
E("node.update", {"node_id": "n10", "data": {"round": {"n": 1, "from": "customer", "text": f"Two payments of ${half:,.2f}, {TARGET.strftime('%b %-d')} and two weeks later.", "cash_effect": half, "p_honored": 0.81}}}, t2 + 44)
E("decision", {"decision_id": "d2", "node_id": "n10", "prompt": f"Accept two installments? ({first(c0)} has paid {c0['n_paid']} invoices, {int(100 * (1 - (c0['late_rate'] or 0)))}% on time)", "options": [{"id": "accept", "label": "Accept"}, {"id": "decline", "label": "Decline"}, {"id": "call", "label": "Call them"}], "auto_resolves_in_s": 8, "default": "accept"}, t2 + 45)
E("node.update", {"node_id": "n10", "status": "done", "data": {"agreement": {"installments": [{"amount": half, "due": str(TARGET), "pay_token": "tok_a"}, {"amount": half, "due": str(TARGET + timedelta(days=14)), "pay_token": "tok_b"}]}}}, t2 + 53)
E("node.create", {"node_id": "n12", "type": "action", "title": f"{first(c0)} paid ${half:,.2f}", "status": "done", "parent": "n10", "data": {"kind": "payment", "rail": "visa", "amount": half, "receipt": {"last4": "1111", "paid_at": "..."}}}, t2 + 90)
fc2 = dict(fc); fc2["cash_at_target"] = round(fc["cash_at_target"] + half, 2); fc2["gap"] = round(max(0, fc["gap"] - half), 2)
E("node.update", {"node_id": "n3", "data": fc2}, t2 + 90.2)
E("speech", {"text": f"{first(c0)} agreed to two payments. The first just landed. You're now about {int(round(fc2['gap'], -2)):,} short.", "audio_url": None}, t2 + 90.5)
E("report.ready", {"report_id": "rep-demo-020", "url": "/reports/rep-demo-020"}, t2 + 91)
E("run.end", {"status": "open"}, t2 + 91.1)

out = {"meta": {"company": co["display_name"], "as_of": str(AS_OF), "target": str(TARGET), "question": QUESTION, "generated_from": "real queries + trained model (scripts/make_fixture.py)",
       "peers": peers, "history_samples": {k: [{"invoice_id": h["invoice_id"], "amount": D(h["amount"]), "due_date": str(h["due_date"]), "days_late": h["days_late"], "status": h["status"]} for h in v] for k, v in hist.items()}},
       "events": ev}
json.dump(out, open(a.out, "w"), indent=1, default=str)
print(json.dumps({"events": len(ev), "context": ev[2]["data"]["data"], "forecast": fc, "answer": ans,
                  "levers": [{k: v for k, v in l.items() if k in ("label", "recovers")} for l in levers],
                  "top": [(c["customer"], round(c["amount"]), c["n"], c["max_dpd"], c["p"]) for c in top]}, indent=1, default=str))
