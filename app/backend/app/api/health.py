"""Process liveness and readiness probes.

Readiness needs the runtime database role and the image's migration head (``app.db.readiness``)
and, after the start, the first search index (data-dictionary 009-search-settings Requirement 10,
application-foundation 002-kubernetes-delivery Requirement 6). Later rebuilds keep it ready.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.db.readiness import DatabaseReadiness
from app.db.session import engine

router = APIRouter(tags=["health"])

database_readiness = DatabaseReadiness(engine)


@router.get("/liveness")
async def liveness() -> dict[str, str]:
    """The process can serve requests."""

    return {"status": "alive"}


@router.get("/readiness", response_model=None)
async def readiness(request: Request) -> dict[str, str] | JSONResponse:
    """Return 503 until the database is ready and the first search index serves."""

    if not await database_readiness.is_ready() or not request.app.state.search_index.is_serving:
        return JSONResponse(status_code=503, content={"status": "not-ready"})
    return {"status": "ready"}
