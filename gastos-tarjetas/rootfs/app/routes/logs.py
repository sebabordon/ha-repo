from fastapi import APIRouter, Request, Query
from auth import require_auth
from app_log import read_logs, clear_logs, list_sources
from typing import Optional

router = APIRouter()


@router.get("/logs")
def get_logs(
    request: Request,
    limit:    int           = Query(300, ge=1, le=2000),
    source:   Optional[str] = Query(None),
    level:    Optional[str] = Query(None),
    since_id: Optional[int] = Query(None),
):
    require_auth(request)
    entries = read_logs(limit=limit, source=source, level=level, since_id=since_id)
    last_id = entries[-1]["id"] if entries else 0
    return {"entries": entries, "last_id": last_id}


@router.delete("/logs")
def delete_logs(request: Request):
    require_auth(request)
    clear_logs()
    return {"ok": True}


@router.get("/logs/sources")
def get_log_sources(request: Request):
    require_auth(request)
    return {"sources": list_sources()}
