from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from owed.db import conn
from owed.events import emit
from owed.reports import generate
from owed.reports.pdf import render_pdf

router = APIRouter()


def _load(report_id: str) -> dict:
    with conn() as c:
        row = c.execute("select doc from generated_reports where report_id=%s", (report_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Report not found")
    return row["doc"]


@router.post("/reports/generate", status_code=201)
def generate_report(run_id: str):
    with conn() as c:
        try:
            report = generate(c, run_id)
        except LookupError:
            raise HTTPException(404, "Run not found")
    emit(run_id, "report.ready", {"report_id": report["report_id"], "url": f"/reports/{report['report_id']}"})
    return report


# Registered before the JSON route so "rep-x.pdf" is not captured as a report_id.
@router.get("/reports/{report_id}.pdf")
def report_pdf(report_id: str):
    return Response(render_pdf(_load(report_id)), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{report_id}.pdf"'})


@router.get("/reports/{report_id}")
def report_json(report_id: str):
    return _load(report_id)
