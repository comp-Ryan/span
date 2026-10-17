"""Payment-behavior model.

Two learned pieces, trained across all 100 companies with a time-based holdout:
  * horizon classifier  P(paid within D days of due date)   -> gives a CDF over days-late, so for an invoice
    that is still unpaid at `dpd` days past due we get P(paid by target | unpaid now) = (F(D_t) - F(dpd)) / (1 - F(dpd))
  * write-off classifier P(never paid)
Features are the customer's history *before* the invoice (leakage-light; see notes in train()).
"""
from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
MODEL_PATH = MODEL_DIR / "payment_model.pkl"
METRICS_PATH = MODEL_DIR / "payment_model_metrics.json"

HORIZONS = [0, 7, 14, 21, 30, 45, 60, 90]
PROFILES = ["wholesale", "construction", "recurring", "mixed", "appointments", "nonprofit", "pos"]
NUM = ["terms_days", "n_paid", "avg_late", "sd_late", "late_rate", "max_late", "n_wo", "amount_ratio", "amount_log", "horizon"]


def _frame(rows: list[dict] | pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(rows) if not isinstance(rows, pd.DataFrame) else rows.copy()
    for c in ["terms_days", "n_paid", "avg_late", "sd_late", "late_rate", "max_late", "n_wo", "amount_ratio", "total_amount"]:
        if c not in df:
            df[c] = np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["amount_log"] = np.log1p(df["total_amount"].fillna(0).astype(float))
    for p in PROFILES:
        df[f"p_{p}"] = (df.get("profile") == p).astype(int)
    return df


def _X(df: pd.DataFrame) -> np.ndarray:
    cols = NUM + [f"p_{p}" for p in PROFILES]
    return df[cols].astype(float).to_numpy()


@dataclass
class PaymentModel:
    horizon_clf: object
    writeoff_clf: object
    metrics: dict
    days_reg: object = None

    def expected_days_late(self, rows: list[dict]) -> np.ndarray:
        df = _frame(rows)
        df["horizon"] = 0
        return self.days_reg.predict(_X(df))

    def cdf(self, rows: list[dict], horizons: np.ndarray) -> np.ndarray:
        """P(paid within `horizons[i]` days of due) for each row i."""
        df = _frame(rows)
        df["horizon"] = horizons
        return self.horizon_clf.predict_proba(_X(df))[:, 1]

    def p_never(self, rows: list[dict]) -> np.ndarray:
        df = _frame(rows)
        df["horizon"] = 0
        return self.writeoff_clf.predict_proba(_X(df))[:, 1]

    def score_open(self, rows: list[dict], days_to_target: int) -> list[dict]:
        """For open invoices at `days_past_due`, probability of payment by target and expected pay date offset."""
        if not rows:
            return []
        dpd = np.array([max(int(r["days_past_due"]), 0) for r in rows], dtype=float)
        f_now = np.clip(self.cdf(rows, dpd), 0, 0.98)
        f_tgt = np.clip(self.cdf(rows, dpd + days_to_target), 0, 0.995)
        p_nev = self.p_never(rows)
        cond = np.clip((f_tgt - f_now) / (1 - f_now), 0, 1) * (1 - p_nev)
        # expected pay date: regressor's days-late, but never earlier than "now" for an overdue invoice
        exp_late = self.expected_days_late(rows)
        out = []
        for i, r in enumerate(rows):
            remaining = max(int(round(exp_late[i] - dpd[i])), 1) if exp_late[i] > dpd[i] else int(round(7 + 0.5 * dpd[i]))
            out.append({**r, "p_paid_by_target": round(float(cond[i]), 3), "p_never": round(float(p_nev[i]), 3),
                        "expected_days_late": round(float(exp_late[i]), 1), "expected_days_to_pay": remaining})
        return out


def load() -> PaymentModel:
    with MODEL_PATH.open("rb") as fh:
        return pickle.load(fh)


def band(p_paid: float, p_never: float) -> str:
    if p_never > 0.35:
        return "red"
    if p_paid >= 0.6:
        return "green"
    return "amber"


TRAIN_SQL = """
with hist as (
  select i.company_id, i.invoice_id, i.customer_id,
         count(h.invoice_id) n_paid,
         avg(h.days_late) avg_late, stddev_pop(h.days_late) sd_late,
         avg((h.days_late>0)::int) late_rate, max(h.days_late) max_late,
         avg(h.total_amount) avg_amount
  from invoice_facts i
  left join invoice_facts h on h.company_id=i.company_id and h.customer_id=i.customer_id
       and h.status='paid' and h.last_paid_date < i.due_date
  group by i.company_id, i.invoice_id, i.customer_id),
wo as (
  select i.company_id, i.invoice_id, count(w.invoice_id) n_wo
  from invoice_facts i left join invoice_facts w on w.company_id=i.company_id and w.customer_id=i.customer_id
       and w.status='written_off' and w.due_date < i.due_date - 30
  group by i.company_id, i.invoice_id)
select i.company_id, i.invoice_id, i.due_date, i.total_amount, i.days_late, i.status,
       cu.payment_terms_days terms_days, co.profile,
       hist.n_paid, hist.avg_late, hist.sd_late, hist.late_rate, hist.max_late, wo.n_wo,
       case when hist.avg_amount>0 then i.total_amount/hist.avg_amount end amount_ratio
from invoice_facts i
join customers cu on cu.company_id=i.company_id and cu.id=i.customer_id
join companies co on co.company_id=i.company_id
join hist on hist.company_id=i.company_id and hist.invoice_id=i.invoice_id
join wo on wo.company_id=i.company_id and wo.invoice_id=i.invoice_id
where i.status in ('paid','written_off') and co.profile <> 'pos'
"""


def train(con, holdout_days: int = 60, period_end=pd.Timestamp("2026-10-06")) -> PaymentModel:
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, roc_auc_score
    from sklearn.model_selection import cross_val_predict

    df = pd.DataFrame(con.execute(TRAIN_SQL).fetchall())
    df["due_date"] = pd.to_datetime(df["due_date"])
    df["total_amount"] = df["total_amount"].astype(float)
    df["days_late"] = pd.to_numeric(df["days_late"], errors="coerce")
    # Outcomes for invoices due in the last `holdout_days`+60 are censored (might still pay later); keep the test
    # window one censoring-length back so labels are (mostly) settled.
    test_hi = period_end - pd.Timedelta(days=60)
    test_lo = test_hi - pd.Timedelta(days=holdout_days)
    train_df = df[df["due_date"] < test_lo]
    test_df = df[(df["due_date"] >= test_lo) & (df["due_date"] < test_hi)]

    def expand(d: pd.DataFrame) -> pd.DataFrame:
        parts = []
        for h in HORIZONS:
            x = d.copy()
            x["horizon"] = h
            x["y"] = ((x["status"] == "paid") & (x["days_late"] <= h)).astype(int)
            parts.append(x)
        return pd.concat(parts, ignore_index=True)

    tr, te = _frame(expand(train_df)), _frame(expand(test_df))
    hz = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, max_leaf_nodes=31, random_state=7)
    hz.fit(_X(tr), tr["y"])
    auc_h = roc_auc_score(te["y"], hz.predict_proba(_X(te))[:, 1])

    # 30-day-specific AUC (the number we quote)
    te30 = te[te["horizon"] == 30]
    auc_30 = roc_auc_score(te30["y"], hz.predict_proba(_X(te30))[:, 1])

    # write-off classifier
    trw, tew = _frame(train_df.copy()), _frame(test_df.copy())
    trw["horizon"] = 0; tew["horizon"] = 0
    yw_tr = (trw["status"] == "written_off").astype(int); yw_te = (tew["status"] == "written_off").astype(int)
    wo = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, class_weight="balanced", random_state=7)
    wo.fit(_X(trw), yw_tr)
    auc_wo = roc_auc_score(yw_te, wo.predict_proba(_X(tew))[:, 1]) if yw_te.sum() > 0 else None

    # write-off AUC: too few positives in any 60-day window, so report 5-fold CV on all settled invoices
    allw = _frame(df.copy()); allw["horizon"] = 0
    yw_all = (allw["status"] == "written_off").astype(int)
    cv_p = cross_val_predict(HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, class_weight="balanced", random_state=7),
                             _X(allw), yw_all, cv=5, method="predict_proba")[:, 1]
    auc_wo_cv = roc_auc_score(yw_all, cv_p)

    # days-late regressor (expected pay date). Compared against the customer's own average as the baseline.
    paid_tr = _frame(train_df[train_df["status"] == "paid"].copy()); paid_tr["horizon"] = 0
    paid_te = _frame(test_df[test_df["status"] == "paid"].copy()); paid_te["horizon"] = 0
    reg = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.06, loss="absolute_error", random_state=7)
    reg.fit(_X(paid_tr), paid_tr["days_late"].astype(float))
    mae = mean_absolute_error(paid_te["days_late"].astype(float), reg.predict(_X(paid_te)))
    baseline_mae = mean_absolute_error(paid_te["days_late"].astype(float), paid_te["avg_late"].fillna(train_df["days_late"].median()).astype(float))

    metrics = {
        "trained_at": pd.Timestamp.now(tz="America/Los_Angeles").isoformat(),
        "holdout_days": holdout_days, "test_window": [str(test_lo.date()), str(test_hi.date())],
        "n_companies": int(df["company_id"].nunique()), "n_invoices_train": int(len(train_df)), "n_invoices_test": int(len(test_df)),
        "auc_paid_within_30d": round(float(auc_30), 3), "auc_all_horizons": round(float(auc_h), 3),
        "auc_write_off_holdout": (round(float(auc_wo), 3) if auc_wo is not None else None),
        "auc_write_off_cv5": round(float(auc_wo_cv), 3), "n_write_offs": int(yw_all.sum()),
        "mae_days_late": round(float(mae), 2), "baseline_mae_customer_avg": round(float(baseline_mae), 2),
        "model": "HistGradientBoosting (horizon CDF classifier + write-off classifier)",
        "features": NUM + ["profile one-hot"],
        "notes": "History features use only invoices paid before the target invoice's due date. Test window is 60 days ending 60 days before the dataset end so labels are settled.",
    }
    m = PaymentModel(hz, wo, metrics, reg)
    MODEL_DIR.mkdir(exist_ok=True)
    with MODEL_PATH.open("wb") as fh:
        pickle.dump(m, fh)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    return m
