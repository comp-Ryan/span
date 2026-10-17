"""Mock AP portal over plain HTTP, invoice PDF, and submit_via_portal with the Browser Use SDK mocked."""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from owed import portal
from owed.config import settings
from owed.db import apply_runtime, conn
from owed.main import app
from owed.portal.pdf import render_invoice_pdf
from owed.runs import create

COMPANY = "company-020"
INVOICE = {"invoice_id": "inv-test-1", "company_name": "Palletbay Storage & Warehousing",
           "customer_name": "Meridian Procurement", "doc_number": "INV-7731", "amount": 1842.50,
           "due_date": "2026-10-10", "txn_date": "2026-09-10", "terms": "Net 30"}


@pytest.fixture(scope="module")
def client():
    apply_runtime()
    return TestClient(app)


def test_invoice_pdf_renders():
    pdf = render_invoice_pdf(INVOICE)
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000


def test_portal_login_then_submit_over_http(client):
    home = client.get("/mock-portal/")
    assert home.status_code == 200 and 'name="email"' in home.text and "Submit invoice" not in home.text

    form = client.post("/mock-portal/login", data={"email": "ap@vendor.test", "password": "x"})
    assert form.status_code == 200 and 'name="invoice_number"' in form.text and "ap@vendor.test" in form.text
    assert client.cookies.get("ap_session").strip('"') == "ap@vendor.test"
    assert "Submit invoice" in client.get("/mock-portal/").text  # cookie keeps the session

    pdf = render_invoice_pdf(INVOICE)
    done = client.post("/mock-portal/submit",
                       data={"vendor_name": INVOICE["company_name"], "invoice_number": INVOICE["doc_number"],
                             "amount": "1842.50", "due_date": INVOICE["due_date"]},
                       files={"invoice_pdf": ("INV-7731.pdf", pdf, "application/pdf")})
    assert done.status_code == 200
    m = re.search(r"CONF-[0-9A-F]{6}", done.text)
    assert m, done.text
    conf = m.group(0)
    assert "$1,842.50" in done.text and "INV-7731" in done.text

    rec = client.get(f"/mock-portal/confirmations/{conf}").json()
    assert rec["invoice_number"] == "INV-7731" and rec["amount"] == 1842.5
    assert rec["pdf_bytes"] == len(pdf) and rec["submitted_by"] == "ap@vendor.test"


def test_portal_rejects_non_pdf_and_bad_amount(client):
    bad = client.post("/mock-portal/submit", data={"vendor_name": "V", "invoice_number": "1", "amount": "10",
                                                   "due_date": "2026-10-10"},
                      files={"invoice_pdf": ("x.txt", b"hello", "text/plain")})
    assert bad.status_code == 422
    neg = client.post("/mock-portal/submit", data={"vendor_name": "V", "invoice_number": "1", "amount": "-5",
                                                   "due_date": "2026-10-10"},
                      files={"invoice_pdf": ("x.pdf", b"%PDF-1.4 ...", "application/pdf")})
    assert neg.status_code == 422
    assert client.get("/mock-portal/confirmations/CONF-NOPE00").status_code == 404


class FakeBrowserUse:
    """Minimal stand-in for browser_use_sdk.v4.BrowserUse."""
    created: list = []  # noqa: RUF012

    def __init__(self):
        self.workspaces = SimpleNamespace(create=self._ws_create, upload=self._ws_upload)
        self.runs = SimpleNamespace(create=self._run_create, wait_for_completion=self._wait, events=lambda rid: [])
        self.uploaded = []

    def _ws_create(self, name):
        return SimpleNamespace(id="ws-1", name=name)

    def _ws_upload(self, ws_id, *paths):
        self.uploaded += [(ws_id, p.name, p.read_bytes()[:4]) for p in paths]
        return []

    def _run_create(self, task, **kw):
        FakeBrowserUse.created.append({"task": task, **kw})
        return SimpleNamespace(id="run-bu-1")

    def _wait(self, run_id):
        return SimpleNamespace(id=run_id, output={"confirmation": "CONF-ABC123"}, result="Done: CONF-ABC123")


@pytest.fixture
def run_id():
    rid = create(COMPANY, "Submit to portal (test)", "web", "free_question")
    yield rid
    with conn() as c:
        c.execute("delete from events where run_id=%s", (rid,))
        c.execute("delete from runs where run_id=%s", (rid,))
        c.commit()


def _events(rid):
    with conn() as c:
        return c.execute("select event, data from events where run_id=%s and event like 'node.%%' order by id",
                         (rid,)).fetchall()


def test_submit_via_portal_mocked_sdk(monkeypatch, run_id):
    monkeypatch.setattr(settings, "browser_use_api_key", "bu_test")
    monkeypatch.setattr(settings, "portal_public_url", "https://demo.example")
    fake = FakeBrowserUse()
    monkeypatch.setattr(portal, "_client", lambda: fake)

    out = portal.submit_via_portal(run_id, INVOICE, parent="n5")
    assert out["confirmation"] == "CONF-ABC123" and out["browser_use_run_id"] == "run-bu-1"
    assert out["screenshot_path"] is None  # fake run has no screenshot events

    assert fake.uploaded and fake.uploaded[0][1] == "invoice-INV-7731.pdf" and fake.uploaded[0][2] == b"%PDF"
    req = FakeBrowserUse.created[-1]
    assert req["workspace_id"] == "ws-1" and req["output_schema"]["required"] == ["confirmation"]
    assert "https://demo.example/mock-portal/" in req["task"] and "INV-7731" in req["task"] and "1842.50" in req["task"]

    ev = _events(run_id)
    assert [e["event"] for e in ev] == ["node.create", "node.update"]
    created, updated = ev[0]["data"], ev[1]["data"]
    assert created["type"] == "action" and created["status"] == "running" and created["parent"] == "n5"
    assert created["data"]["kind"] == "portal" and created["data"]["doc_number"] == "INV-7731"
    assert updated["node_id"] == created["node_id"] and updated["status"] == "done"
    assert updated["data"]["confirmation"] == "CONF-ABC123" and "screenshot_url" in updated["data"]


def test_submit_via_portal_unconfigured_marks_failed(monkeypatch, run_id):
    monkeypatch.setattr(settings, "browser_use_api_key", "")
    with pytest.raises(RuntimeError):
        portal.submit_via_portal(run_id, INVOICE)
    ev = _events(run_id)
    assert ev[-1]["event"] == "node.update" and ev[-1]["data"]["status"] == "failed"


def test_submit_via_portal_bad_result(monkeypatch, run_id):
    monkeypatch.setattr(settings, "browser_use_api_key", "bu_test")
    fake = FakeBrowserUse()
    fake.runs.wait_for_completion = lambda rid: SimpleNamespace(id=rid, output=None, result="could not find it")
    monkeypatch.setattr(portal, "_client", lambda: fake)
    with pytest.raises(RuntimeError, match="no confirmation"):
        portal.submit_via_portal(run_id, INVOICE)
    assert _events(run_id)[-1]["data"]["status"] == "failed"
