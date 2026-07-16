import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import (
    agents,
    artifacts,
    audit,
    copado,
    demo,
    gates,
    github,
    jira,
    push,
    runs,
    settings,
    stories,
    work,
    ws,
)
from .config import get_settings
from .database import init_db
from .services.jira.rest_adapter import JiraApiError
from .services.scheduler import scheduler
from .services.workflow import NotFoundError, WorkflowError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pact.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    sync_task = asyncio.create_task(scheduler.run())
    yield
    scheduler.stop()
    sync_task.cancel()
    with suppress(asyncio.CancelledError):
        await sync_task


app = FastAPI(
    title="PACT Agentic QE Orchestration Platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(WorkflowError)
async def workflow_error_handler(request: Request, exc: WorkflowError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(JiraApiError)
async def jira_error_handler(request: Request, exc: JiraApiError):
    # Upstream Jira failure — surface as a gateway error, not a 500, with the
    # upstream status so the UI can show a meaningful message.
    return JSONResponse(
        status_code=502,
        content={"detail": f"Jira request failed (upstream {exc.status_code})"},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    # Last resort: log the full trace server-side, return a clean generic
    # message to the client (never leak internals / stack traces).
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500, content={"detail": "internal server error"}
    )


API_PREFIX = "/api/v1"
app.include_router(stories.router, prefix=API_PREFIX)
app.include_router(runs.router, prefix=API_PREFIX)
app.include_router(gates.router, prefix=API_PREFIX)
app.include_router(audit.router, prefix=API_PREFIX)
app.include_router(jira.router, prefix=API_PREFIX)
app.include_router(push.router, prefix=API_PREFIX)
app.include_router(settings.router, prefix=API_PREFIX)
app.include_router(work.router, prefix=API_PREFIX)
app.include_router(artifacts.router, prefix=API_PREFIX)
app.include_router(agents.router, prefix=API_PREFIX)
app.include_router(copado.router, prefix=API_PREFIX)
app.include_router(github.router, prefix=API_PREFIX)
app.include_router(demo.router, prefix=API_PREFIX)
app.include_router(ws.router)


@app.get("/health")
async def health():
    env = get_settings()
    return {"status": "ok", "demo_mode": env.demo_mode}
