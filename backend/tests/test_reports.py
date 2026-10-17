import json
import re
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from owed.config import settings
from owed.db import conn
from owed.main import app
from owed.reports import build_report

FIXTURE = Path(__file__).parent / "fixtures" / "run_palletbay.json"
ENVELOPE = ("id", "ts", "company_id", "run_id")
KEYS = {"report_id", "run_id", "generated_at", "company", "question", "answer", "numbers", "workflow", "actions",
        "open_items", "narrative", "disclosures", "pdf_url"}
NUMBERS = {"bank_balance", "payroll", "owed", "expected_by_target", "gap_then", "gap_now"}


def fixture_events():
    return json.loads(FIXTURE.read_text())["events"]


@pytest.fixture
def run(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    rid = "run-test-" + uuid4().hex
    events = [e for e in fixture_events() if e["event"] != "report.ready"]
    start = events[0]["data"]
    with conn() as c:
        c.execute("insert into runs(run_id, company_id, question, source, intent) values (%s,%s,%s,%s,'payroll_check')",
                  (rid, start["company_id"], start["question"], start["source"]))
        for e in events:
            data = {k: v for k, v in e["data"].items() if k not in ENVELOPE}
            c.execute("insert into events(run_id, company_id, ts, event, data) values (%s,%s,%s,%s,%s)",
                      (rid, e["data"]["company_id"], e["data"]["ts"], e["event"], Jsonb(data)))
    yield rid
    with conn() as c:
        c.execute("delete from generated_reports where run_id=%s", (rid,))
        c.execute("delete from events where run_id=%s", (rid,))
        c.execute("delete from runs where run_id=%s", (rid,))


def test_fixture_follows_contract():
    events = fixture_events()
    seen, kinds = set(), [e["event"] for e in events]
    assert kinds[0] == "run.start" and kinds[-1] == "run.end" and "report.ready" in kinds
    for i, e in enumerate(events, 1):
        d = e["data"]
        assert all(k in d for k in ENVELOPE) and d["id"] == str(i) and d["company_id"] == "company-020"
        if e["event"] == "node.create":
            assert d["type"] in {"context", "scoring", "forecast", "answer", "levers", "action"}
            assert d["status"] in {"running", "done", "failed", "waiting"}
            assert d["parent"] is None or d["parent"] in seen
            seen.add(d["node_id"])
        elif e["event"] in ("node.update", "decision"):
            assert d["node_id"] in seen
    rows = [e for e in events if e["event"] == "node.update" and "row" in e["data"]]
    assert 10 <= len(rows) <= 14
    actions = [e["data"]["data"]["kind"] for e in events if e["event"] == "node.create" and e["data"]["type"] == "action"]
    assert actions == ["reminder"] * 3 + ["reply", "negotiation", "payment"]


def test_build_report(run):
    with conn() as c:
        r = build_report(c, run)
    assert set(r) == KEYS and set(r["numbers"]) == NUMBERS
    assert r["company"] == "Palletbay Storage & Warehousing"
    assert r["numbers"]["gap_now"] < r["numbers"]["gap_then"]
    assert r["answer"] == "No, $8,515 short at the time of asking; $7,937 short now."
    assert len(r["workflow"]["nodes"]) == 11 and len(r["workflow"]["edges"]) == 10
    assert r["workflow"]["svg"].startswith("<svg")
    assert {"title": "Texted Evergreen Juniper Flats Removals",
            "result": "Agreed to 2 installments; $578.10 paid"} in r["actions"]
    assert len(r["actions"]) == 3
    assert "Yeoman Roasters Co.: no reply yet" in r["open_items"]
    assert "Evergreen Juniper Flats Removals: installment 2 of $578.10 due 2026-10-30" in r["open_items"]
    assert any("Havenwood" in i for i in r["open_items"])
    assert r["narrative"].count("\n\n") == 1


def test_narrative_falls_back_when_gemini_fails(run, monkeypatch):
    from owed import reports

    def boom(*a, **kw):
        raise RuntimeError("network down")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(reports.httpx, "post", boom)
    with conn() as c:
        r = build_report(c, run)
    assert r["narrative"].startswith("You asked")


def test_generate_endpoints_and_pdf(run):
    client = TestClient(app)
    res = client.post(f"/reports/generate?run_id={run}")
    assert res.status_code == 201
    rid = res.json()["report_id"]
    body = client.get(f"/reports/{rid}").json()
    assert set(body) == KEYS and body["pdf_url"].endswith(f"/reports/{rid}.pdf")
    pdf = client.get(f"/reports/{rid}.pdf")
    assert pdf.headers["content-type"] == "application/pdf"
    assert len(pdf.content) > 1000 and pdf.content.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page[^s]", pdf.content)) == 1
    with conn() as c:
        ev = c.execute("select data from events where run_id=%s and event='report.ready'", (run,)).fetchone()
        assert c.execute("select report_id from runs where run_id=%s", (run,)).fetchone()["report_id"] == rid
    assert ev["data"] == {"report_id": rid, "url": f"/reports/{rid}"}
    assert client.get("/reports/rep-missing").status_code == 404
    assert client.post("/reports/generate?run_id=run-missing").status_code == 404
