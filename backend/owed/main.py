import asyncio

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from owed.events import router as events_router
from owed.runs import router as runs_router
from owed.reports.api import router as reports_router
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from owed.runs.payroll import router as payroll_router
from owed.voice.live import router as voice_router
from owed.channels.photon import router as photon_router
from owed.db import apply_runtime
from owed.decisions import router as decisions_router, worker as decision_worker
from owed.agents.negotiation import router as negotiation_router
from owed.actions import payment_worker
from owed.finance.cash import router as cash_router
from owed.api import router as product_router
from owed.config import settings
from owed.hub import STATIC as HUB_STATIC, router as hub_router
from owed.payments import router as pay_router
from owed.payments import visa

from owed.observability import init as init_observability

init_observability()

@asynccontextmanager
async def lifespan(app):
    apply_runtime()
    task = asyncio.create_task(decision_worker())
    payments_task = asyncio.create_task(payment_worker())
    try:
        yield
    finally:
        task.cancel()
        payments_task.cancel()
        await asyncio.gather(task, payments_task, return_exceptions=True)


app = FastAPI(title="Owed", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/hub/static", StaticFiles(directory=HUB_STATIC), name="hub-static")
app.include_router(hub_router)
app.include_router(product_router)
app.include_router(cash_router)
app.include_router(events_router)
app.include_router(runs_router)
app.include_router(payroll_router)
app.include_router(voice_router)
app.include_router(photon_router)
app.include_router(decisions_router)
app.include_router(negotiation_router)
app.include_router(reports_router)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse({"error": {"code": str(exc.status_code), "message": str(exc.detail)}}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse({"error": {"code": "validation_error", "message": "Invalid request parameters"}}, status_code=422)
app.include_router(pay_router)


@app.get("/health")
def health():
    from owed.db import conn
    with conn() as c:
        c.execute('select 1')
    return {"ok": True, "db": "postgres", "gemini": bool(settings.gemini_api_key),
            "drafter": "template_fallback", "photon": bool(settings.photon_api_key and settings.photon_project_id),
            "visa": "sandbox" if visa.configured() else "simulated", "solana": "devnet",
            "agentverse": bool(settings.agentverse_api_key and settings.agent_public_endpoint), "jev": False,
            "planner": settings.planner, "finance_tools": settings.finance_tools}
