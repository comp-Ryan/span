from fastapi import FastAPI
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


@app.get("/health")
def health():
    return {"ok": True, "planner": settings.planner, "finance_tools": settings.finance_tools}
