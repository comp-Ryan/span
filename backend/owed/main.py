from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from owed.events import router as events_router
from owed.runs import router as runs_router
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from owed.config import settings
from owed.hub import STATIC as HUB_STATIC, router as hub_router

if settings.sentry_dsn:
    import sentry_sdk
    sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=1.0, enable_logs=True, send_default_pii=False)

app = FastAPI(title="Owed", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/hub/static", StaticFiles(directory=HUB_STATIC), name="hub-static")
app.include_router(hub_router)
app.include_router(events_router)
app.include_router(runs_router)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse({"error": {"code": str(exc.status_code), "message": str(exc.detail)}}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse({"error": {"code": "validation_error", "message": "Invalid request parameters"}}, status_code=422)


@app.get("/health")
def health():
    return {"ok": True, "planner": settings.planner, "finance_tools": settings.finance_tools}
