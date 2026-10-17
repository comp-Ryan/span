"""Flatten the Intuit hackathon-100 YAML dataset into Postgres.

Usage: python -m owed.db.load [--companies company-001,company-002] [--reset]
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

import psycopg
import yaml

from owed.config import settings
from owed.db import apply_schema

try:
    Loader = yaml.CSafeLoader  # libyaml, much faster
except AttributeError:  # pragma: no cover
    Loader = yaml.SafeLoader

SECONDARY = ["items", "projects", "estimates", "terms", "accounts"]
REPORTS = ["profit_and_loss", "balance_sheet", "ar_aging", "ap_aging"]


def load_yaml(path: Path):
    if not path.exists():
        return None
    with path.open("rb") as f:
        return yaml.load(f, Loader=Loader)


def money(v) -> str:
    if v is None:
        return r"\N"
    return str(Decimal(str(v)).quantize(Decimal("0.01")))


def esc(v) -> str:
    """COPY text-format escaping."""
    if v is None:
        return r"\N"
    if isinstance(v, bool):
        return "t" if v else "f"
    if isinstance(v, (dict, list)):
        v = json.dumps(v, default=str)
    s = str(v)
    return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def copy_rows(cur, table: str, cols: list[str], rows: list[tuple]):
    if not rows:
        return
    buf = io.StringIO()
    for r in rows:
        buf.write("\t".join(esc(x) for x in r) + "\n")
    buf.seek(0)
    with cur.copy(f"copy {table} ({', '.join(cols)}) from stdin") as cp:
        cp.write(buf.read())


def company_dir(root: Path, company_id: str) -> Path:
    worlds = list((root / company_id / "rwm-v4").glob("world-*"))
    if not worlds:
        raise FileNotFoundError(f"no world dir for {company_id}")
    return worlds[0]


def load_company(cur, root: Path, idx: dict) -> dict:
    cid = idx["company_id"]
    w = company_dir(root, cid)
    counts: dict[str, int] = {}

    comp = load_yaml(w / "company.yaml") or {}
    if isinstance(comp, list):
        comp = comp[0] if comp else {}
    pnl = load_yaml(w / "reports" / "profit_and_loss.yaml") or {}
    fin = idx.get("financials_cents", {})
    cents = lambda k: (Decimal(fin.get(k, 0)) / 100).quantize(Decimal("0.01")) if fin else None
    copy_rows(cur, "companies", [
        "company_id", "display_name", "industry_naics", "industry_title", "profile", "archetype", "size_tier",
        "business_status", "distressed", "dataset_id", "world_dir", "fiscal_year_start", "state",
        "cash", "revenue", "profit", "receivables", "payables", "debt", "period_start", "period_end",
    ], [(
        cid, idx.get("display_name"), idx.get("industry_naics"), idx.get("industry_title"), idx.get("profile"),
        idx.get("archetype"), idx.get("size_tier"), idx.get("business_status"), idx.get("distressed"),
        idx.get("dataset_id"), str(w.relative_to(root)), str(comp.get("fiscal_year_start_month", "")),
        (comp.get("address") or {}).get("state"),
        cents("cash"), cents("revenue"), cents("profit"), cents("receivables"), cents("payables"), cents("debt"),
        pnl.get("period_start_date"), pnl.get("period_end_date"),
    )])

    rows = load_yaml(w / "customers.yaml") or []
    copy_rows(cur, "customers", ["company_id", "id", "display_name", "company_name", "email", "phone", "state",
                                 "payment_terms", "payment_terms_days", "credit_limit", "joined_date", "ended_date"],
              [(cid, c["id"], c.get("display_name"), c.get("company_name"), c.get("email"), c.get("phone"),
                (c.get("address") or {}).get("state"), c.get("payment_terms"), c.get("payment_terms_days"),
                money(c.get("credit_limit_amount")), c.get("joined_date"), c.get("ended_date")) for c in rows])
    counts["customers"] = len(rows)

    rows = load_yaml(w / "vendors.yaml") or []
    copy_rows(cur, "vendors", ["company_id", "id", "display_name", "email", "phone", "payment_terms",
                               "payment_terms_days", "supply_role", "joined_date"],
              [(cid, v["id"], v.get("display_name"), v.get("email"), v.get("phone"), v.get("payment_terms"),
                v.get("payment_terms_days"), v.get("supply_role"), v.get("joined_date")) for v in rows])
    counts["vendors"] = len(rows)

    rows = load_yaml(w / "employees.yaml") or []
    copy_rows(cur, "employees", ["company_id", "id", "display_name", "job_title", "hired_date", "released_date", "weekly_wage"],
              [(cid, e["id"], e.get("display_name"), e.get("job_title"), e.get("hired_date"), e.get("released_date"),
                money(e.get("weekly_wage_amount"))) for e in rows])
    counts["employees"] = len(rows)

    rows = load_yaml(w / "invoices.yaml") or []
    copy_rows(cur, "invoices", ["company_id", "id", "doc_number", "customer_id", "customer_name", "txn_date", "due_date",
                                "total_amount", "deposit_applied", "retainage", "project_id", "memo"],
              [(cid, i["id"], i.get("doc_number"), i.get("customer_id"), i.get("customer_name"), i.get("txn_date"),
                i.get("due_date"), money(i.get("total_amount")), money(i.get("deposit_applied_amount")),
                money(i.get("retainage_amount")), i.get("project_id"), i.get("memo")) for i in rows])
    copy_rows(cur, "invoice_lines", ["company_id", "invoice_id", "line_num", "item_id", "item_name", "description",
                                     "quantity", "unit_price", "amount"],
              [(cid, i["id"], ln.get("line_num"), ln.get("item_id"), ln.get("item_name"), ln.get("description"),
                ln.get("quantity"), money(ln.get("unit_price_amount")), money(ln.get("amount")))
               for i in rows for ln in (i.get("lines") or [])])
    counts["invoices"] = len(rows)

    rows = load_yaml(w / "customer_payments.yaml") or []
    copy_rows(cur, "customer_payments", ["company_id", "id", "customer_id", "customer_name", "txn_date", "amount", "unapplied", "project_id"],
              [(cid, p["id"], p.get("customer_id"), p.get("customer_name"), p.get("txn_date"), money(p.get("amount")),
                money(p.get("unapplied_amount")), p.get("project_id")) for p in rows])
    copy_rows(cur, "payment_applications", ["company_id", "payment_id", "document_id", "amount"],
              [(cid, p["id"], a["document_id"], money(a.get("amount"))) for p in rows for a in (p.get("applications") or [])])
    counts["customer_payments"] = len(rows)

    rows = load_yaml(w / "sales_receipts.yaml") or []
    copy_rows(cur, "sales_receipts", ["company_id", "id", "customer_id", "txn_date", "total_amount"],
              [(cid, s["id"], s.get("customer_id"), s.get("txn_date"), money(s.get("total_amount"))) for s in rows])
    counts["sales_receipts"] = len(rows)

    rows = load_yaml(w / "bills.yaml") or []
    copy_rows(cur, "bills", ["company_id", "id", "doc_number", "vendor_id", "vendor_name", "expense_kind", "cost_category",
                             "txn_date", "due_date", "total_amount", "project_id", "memo"],
              [(cid, b["id"], b.get("doc_number"), b.get("vendor_id"), b.get("vendor_name"), b.get("expense_kind"),
                b.get("cost_category"), b.get("txn_date"), b.get("due_date"), money(b.get("total_amount")),
                b.get("project_id"), b.get("memo")) for b in rows])
    counts["bills"] = len(rows)

    rows = load_yaml(w / "bill_payments.yaml") or []
    copy_rows(cur, "bill_payments", ["company_id", "id", "vendor_id", "vendor_name", "txn_date", "amount"],
              [(cid, p["id"], p.get("vendor_id"), p.get("vendor_name"), p.get("txn_date"), money(p.get("amount"))) for p in rows])
    copy_rows(cur, "bill_payment_applications", ["company_id", "payment_id", "document_id", "amount"],
              [(cid, p["id"], a["document_id"], money(a.get("amount"))) for p in rows for a in (p.get("applications") or [])])
    counts["bill_payments"] = len(rows)

    rows = load_yaml(w / "payroll_runs.yaml") or []
    copy_rows(cur, "payroll_runs", ["company_id", "id", "run_date", "total_amount"],
              [(cid, r["id"], r.get("date"), money(r.get("total_amount"))) for r in rows])
    copy_rows(cur, "payroll_lines", ["company_id", "run_id", "employee_id", "employee_name", "gross_amount"],
              [(cid, r["id"], ln["employee_id"], ln.get("employee_name"), money(ln.get("gross_amount")))
               for r in rows for ln in (r.get("lines") or [])])
    counts["payroll_runs"] = len(rows)

    rows = load_yaml(w / "bank_transactions.yaml") or []
    copy_rows(cur, "bank_transactions", ["company_id", "id", "txn_date", "amount", "direction", "running_balance",
                                         "source_document_id", "memo", "kind"],
              [(cid, t["id"], t.get("date"), money(t.get("amount")), t.get("direction"), money(t.get("running_balance_amount")),
                t.get("source_document_id"), t.get("memo"), t.get("kind")) for t in rows])
    counts["bank_transactions"] = len(rows)

    rows = load_yaml(w / "journal_entries.yaml") or []
    copy_rows(cur, "journal_entries", ["company_id", "id", "doc_number", "purpose", "txn_date", "memo", "project_id"],
              [(cid, j["id"], j.get("doc_number"), j.get("purpose"), j.get("txn_date"), j.get("memo"), j.get("project_id")) for j in rows])
    copy_rows(cur, "journal_lines", ["company_id", "je_id", "line_num", "account_id", "account_name", "description",
                                     "debit", "credit", "customer_id", "vendor_id", "document_id"],
              [(cid, j["id"], ln.get("line_num"), ln.get("account_id"), ln.get("account_name"), ln.get("description"),
                money(ln.get("debit_amount")), money(ln.get("credit_amount")), ln.get("customer_id"), ln.get("vendor_id"),
                ln.get("document_id")) for j in rows for ln in (j.get("lines") or [])])
    counts["journal_entries"] = len(rows)

    for ent in SECONDARY:
        rows = load_yaml(w / f"{ent}.yaml") or []
        copy_rows(cur, "docs", ["company_id", "entity", "id", "doc"], [(cid, ent, d.get("id", str(n)), d) for n, d in enumerate(rows)])
        counts[ent] = len(rows)

    for rep in REPORTS:
        doc = load_yaml(w / "reports" / f"{rep}.yaml")
        if doc is not None:
            copy_rows(cur, "reports", ["company_id", "name", "doc"], [(cid, rep, doc)])
            if rep in ("ar_aging", "ap_aging"):
                copy_rows(cur, rep, ["company_id", "document_id", "party", "due_date", "days_past_due", "bucket", "balance"],
                          [(cid, r["document_id"], r.get("party"), r.get("due_date"), r.get("days_past_due"), r.get("bucket"),
                            money(r.get("balance"))) for r in (doc.get("rows") or [])])
    return counts


INVOICE_FACTS_SQL = """
insert into invoice_facts (company_id, invoice_id, customer_id, txn_date, due_date, total_amount,
                           paid_amount, first_paid_date, last_paid_date, written_off, open_balance, days_late, status)
select i.company_id, i.id, i.customer_id, i.txn_date, i.due_date, i.total_amount,
       coalesce(p.paid, 0), p.first_paid, p.last_paid,
       coalesce(w.wo, 0),
       i.total_amount - coalesce(i.deposit_applied, 0) - coalesce(p.paid, 0) - coalesce(w.wo, 0),
       case when p.last_paid is not null and i.total_amount - coalesce(i.deposit_applied,0) - coalesce(p.paid,0) - coalesce(w.wo,0) <= 0.005
            then (p.last_paid - i.due_date) end,
       case when coalesce(w.wo,0) > 0 then 'written_off'
            when i.total_amount - coalesce(i.deposit_applied,0) - coalesce(p.paid,0) <= 0.005 then 'paid'
            when coalesce(p.paid,0) > 0 then 'partial'
            else 'open' end
from invoices i
left join (
  select pa.company_id, pa.document_id, sum(pa.amount) paid, min(cp.txn_date) first_paid, max(cp.txn_date) last_paid
  from payment_applications pa join customer_payments cp on cp.company_id = pa.company_id and cp.id = pa.payment_id
  group by pa.company_id, pa.document_id
) p on p.company_id = i.company_id and p.document_id = i.id
left join (
  select jl.company_id, jl.document_id, sum(jl.credit) wo
  from journal_lines jl join journal_entries je on je.company_id = jl.company_id and je.id = jl.je_id
  where jl.account_id = 'acct-receivable' and jl.credit > 0 and je.purpose in ('bad_debt','client_default')
  group by jl.company_id, jl.document_id
) w on w.company_id = i.company_id and w.document_id = i.id
where i.company_id = any(%s)
"""

ALL_TABLES = ["companies", "customers", "vendors", "employees", "invoices", "invoice_lines", "customer_payments",
              "payment_applications", "sales_receipts", "bills", "bill_payments", "bill_payment_applications",
              "payroll_runs", "payroll_lines", "bank_transactions", "journal_entries", "journal_lines", "docs",
              "reports", "ar_aging", "ap_aging", "invoice_facts"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--companies", help="comma-separated company ids (default all)")
    ap.add_argument("--reset", action="store_true", help="truncate dataset tables first")
    ap.add_argument("--facts-only", action="store_true", help="only rebuild invoice_facts")
    args = ap.parse_args(argv)

    root = Path(settings.data_dir).resolve()
    index = json.loads((root / "index.json").read_text())
    wanted = set(args.companies.split(",")) if args.companies else None
    todo = [c for c in index if not wanted or c["company_id"] in wanted]

    apply_schema()
    t0 = time.time()
    if args.facts_only:
        with psycopg.connect(settings.database_url) as con:
            ids = [c["company_id"] for c in todo]
            con.execute("delete from invoice_facts where company_id = any(%s)", (ids,))
            con.execute(INVOICE_FACTS_SQL, (ids,))
            con.commit()
        print(f"rebuilt invoice_facts for {len(ids)} companies in {time.time()-t0:.1f}s")
        return
    with psycopg.connect(settings.database_url) as con:
        with con.cursor() as cur:
            ids = [c["company_id"] for c in todo]
            if args.reset:
                cur.execute("truncate " + ", ".join(ALL_TABLES))
            else:
                for t in ALL_TABLES:
                    cur.execute(f"delete from {t} where company_id = any(%s)", (ids,))
            total: dict[str, int] = {}
            for n, c in enumerate(todo, 1):
                counts = load_company(cur, root, c)
                for k, v in counts.items():
                    total[k] = total.get(k, 0) + v
                print(f"[{n:3}/{len(todo)}] {c['company_id']} {c['display_name']}: {counts.get('invoices',0)} inv, "
                      f"{counts.get('customer_payments',0)} pay, {counts.get('bills',0)} bills", file=sys.stderr)
            cur.execute(INVOICE_FACTS_SQL, (ids,))
        con.commit()
    print(f"loaded {len(todo)} companies in {time.time()-t0:.1f}s: {total}")


if __name__ == "__main__":
    main()
