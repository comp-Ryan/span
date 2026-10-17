"""SQL that answers the payroll question. All functions take an open psycopg connection (dict_row)."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

AS_OF_DEFAULT = date(2026, 10, 6)  # dataset observation day


def f(x) -> float:
    return float(x) if x is not None else 0.0


def company(con, company_id: str) -> dict:
    return con.execute("select * from companies where company_id=%s", (company_id,)).fetchone()


def companies(con) -> list[dict]:
    return con.execute("""
        select c.company_id, c.display_name, c.profile, c.distressed, c.cash,
               coalesce(a.open_ar,0) owed_total, coalesce(a.overdue,0) overdue_total, coalesce(a.n_open,0) n_open
        from companies c left join (
          select company_id, sum(open_balance) open_ar, sum(open_balance) filter (where due_date < %s) overdue,
                 count(*) filter (where open_balance>0) n_open
          from invoice_facts where status in ('open','partial') group by company_id) a using (company_id)
        where c.profile <> 'pos' order by c.company_id""", (AS_OF_DEFAULT,)).fetchall()


def bank_balance(con, company_id: str, as_of: date) -> float:
    r = con.execute("""select running_balance from bank_transactions where company_id=%s and txn_date<=%s
                       order by txn_date desc, id desc limit 1""", (company_id, as_of)).fetchone()
    return f(r["running_balance"]) if r else 0.0


def payroll_due(con, company_id: str, as_of: date, target: date) -> dict:
    """Payroll expected between as_of and target, estimated from the trailing 8 weeks' cadence."""
    rows = con.execute("""select run_date, sum(total_amount) amt from payroll_runs
                          where company_id=%s and run_date > %s - interval '56 days' and run_date <= %s
                          group by run_date order by run_date""", (company_id, as_of, as_of)).fetchall()
    weekly = sum(f(r["amt"]) for r in rows) / 8.0 if rows else 0.0
    weeks = max((target - as_of).days, 1) / 7.0
    # next pay date: continue the most recent weekday pattern
    next_date = None
    if rows:
        last = rows[-1]["run_date"]
        next_date = last + timedelta(days=7)
        while next_date <= as_of:
            next_date += timedelta(days=7)
    headcount = con.execute("""select count(*) n from employees where company_id=%s and hired_date<=%s
                               and (released_date is null or released_date>%s)""", (company_id, as_of, as_of)).fetchone()["n"]
    return {"weekly": round(weekly, 2), "due_by_target": round(weekly * weeks, 2), "next_pay_date": next_date,
            "headcount": headcount, "trailing_runs": len(rows)}


def bills_due(con, company_id: str, as_of: date, target: date) -> list[dict]:
    return con.execute("""
        select b.id bill_id, b.vendor_id, b.vendor_name, b.due_date, b.total_amount,
               b.total_amount - coalesce((select sum(a.amount) from bill_payment_applications a
                                          where a.company_id=b.company_id and a.document_id=b.id),0) open_amount,
               v.supply_role, v.payment_terms_days,
               (select round(avg(bp.txn_date - bb.due_date),1) from bill_payments bp
                  join bill_payment_applications ba on ba.company_id=bp.company_id and ba.payment_id=bp.id
                  join bills bb on bb.company_id=ba.company_id and bb.id=ba.document_id
                  where bb.company_id=b.company_id and bb.vendor_id=b.vendor_id) hist_days_vs_due
        from bills b left join vendors v on v.company_id=b.company_id and v.id=b.vendor_id
        where b.company_id=%s and b.due_date between %s and %s
        order by b.due_date""", (company_id, as_of, target)).fetchall()


OPEN_INVOICE_FEATURES_SQL = """
with hist as (
  select company_id, customer_id,
         count(*) filter (where status='paid') n_paid,
         avg(days_late) filter (where status='paid') avg_late,
         stddev_pop(days_late) filter (where status='paid') sd_late,
         avg((days_late>0)::int) filter (where status='paid') late_rate,
         max(days_late) filter (where status='paid') max_late,
         count(*) filter (where status='written_off') n_wo,
         avg(total_amount) avg_amount,
         max(last_paid_date) last_paid
  from invoice_facts where company_id=%(cid)s and due_date < %(as_of)s group by company_id, customer_id)
select i.invoice_id, i.customer_id, cu.display_name customer_name, cu.email, cu.phone,
       i.txn_date, i.due_date, i.total_amount, i.open_balance,
       (%(as_of)s - i.due_date) days_past_due,
       cu.payment_terms_days terms_days,
       coalesce(h.n_paid,0) n_paid, h.avg_late, h.sd_late, h.late_rate, h.max_late, coalesce(h.n_wo,0) n_wo,
       case when h.avg_amount>0 then i.total_amount/h.avg_amount end amount_ratio, h.last_paid,
       co.profile, co.size_tier
from invoice_facts i
join customers cu on cu.company_id=i.company_id and cu.id=i.customer_id
join companies co on co.company_id=i.company_id
left join hist h on h.company_id=i.company_id and h.customer_id=i.customer_id
where i.company_id=%(cid)s and i.status in ('open','partial') and i.open_balance>0 and i.txn_date<=%(as_of)s
order by i.open_balance desc
"""


def open_invoices(con, company_id: str, as_of: date) -> list[dict]:
    return con.execute(OPEN_INVOICE_FEATURES_SQL, {"cid": company_id, "as_of": as_of}).fetchall()


def customer_history(con, company_id: str, customer_id: str, as_of: date, limit: int = 24) -> list[dict]:
    return con.execute("""select invoice_id, total_amount amount, due_date, days_late, status
                          from invoice_facts where company_id=%s and customer_id=%s and due_date<%s
                          order by due_date desc limit %s""", (company_id, customer_id, as_of, limit)).fetchall()[::-1]


def peer_dso(con, company_id: str) -> dict | None:
    """Days-sales-outstanding proxy: avg days_late + terms, for this company vs same-profile peers."""
    r = con.execute("""
        with per as (select f.company_id, co.profile, avg(f.days_late + coalesce(cu.payment_terms_days,0)) dso
                     from invoice_facts f join companies co using(company_id)
                     join customers cu on cu.company_id=f.company_id and cu.id=f.customer_id
                     where f.status='paid' group by f.company_id, co.profile)
        select (select dso from per where company_id=%s) mine,
               (select percentile_cont(0.5) within group (order by dso) from per where profile=(select profile from companies where company_id=%s) and company_id<>%s) peer_median,
               (select count(*) from per where profile=(select profile from companies where company_id=%s) and company_id<>%s) peer_count""",
        (company_id, company_id, company_id, company_id, company_id)).fetchone()
    if not r or r["mine"] is None:
        return None
    return {"dso_days": round(f(r["mine"])), "peer_median_dso_days": round(f(r["peer_median"])), "peer_count": r["peer_count"]}
