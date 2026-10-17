from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from owed.db import conn
from owed.events import emit
from owed.reports import generate, build_report
from owed.config import settings
from psycopg.types.json import Jsonb
from owed.reports.pdf import render_pdf

router = APIRouter()


def _load(report_id: str, company: str) -> dict:
    with conn() as c:
        row = c.execute("select run_id from generated_reports where report_id=%s and company_id=%s", (report_id,company)).fetchone()
        if not row:
            raise HTTPException(404,"Report not found")
        report = build_report(c,row['run_id'],report_id,narrate=False)
        c.execute('update generated_reports set doc=%s where report_id=%s',(Jsonb(report),report_id))
    return report


@router.post("/reports/generate", status_code=201)
def generate_report(run_id: str, company: str = settings.demo_company):
    with conn() as c:
        if not c.execute('select run_id from runs where run_id=%s and company_id=%s',(run_id,company)).fetchone():
            raise HTTPException(404,'Run not found')
        try:
            report = generate(c, run_id)
        except LookupError:
            raise HTTPException(404, "Run not found")
    emit(run_id, "report.ready", {"report_id": report["report_id"], "url": f"/reports/{report['report_id']}"})
    return report


# Registered before the JSON route so "rep-x.pdf" is not captured as a report_id.
@router.get("/reports/{report_id}.pdf")
def report_pdf(report_id: str, company: str = settings.demo_company):
    return Response(render_pdf(_load(report_id,company)), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{report_id}.pdf"'})


@router.get("/reports/{report_id}")
def report_json(report_id: str, company: str = settings.demo_company):
    return _load(report_id,company)
