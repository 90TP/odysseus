"""HTTP API for Aerith self-maintenance: /api/companion/aerith/maintenance/*.

Anyone authenticated (session or paired-device token) can report client logs
and read status.  Deciding what happens to the app (fix now, build a feature,
approve, reject) needs a human admin on a browser session: API tokens and
the in-process internal-tool token, which Aerith's own tools use, are
refused, so Aerith can never approve her own change.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from companion.maintenance import store as st
from companion.maintenance.builder import BuildError
from companion.maintenance.features import offer_from_report
from companion.maintenance.log_watch import ErrorEvent

logger = logging.getLogger(__name__)


class ClientLogEvent(BaseModel):
    level: str = "ERROR"
    message: str = Field(..., max_length=4000)
    detail: str = Field("", max_length=20000)
    source: str = Field("app", max_length=200)
    timestamp: str = Field("", max_length=64)


class ClientLogBatch(BaseModel):
    platform: Literal["android", "desktop"]
    app_id: str = Field("", max_length=200)
    app_version: str = Field("", max_length=64)
    events: list[ClientLogEvent] = Field(..., max_length=100)


class RejectBody(BaseModel):
    reason: str = Field("", max_length=500)


class ResearchBody(BaseModel):
    research_id: str = Field("", max_length=200)
    query: str = Field("", max_length=2000)
    report: str = Field("", max_length=100_000)


def require_human_admin(request: Request) -> str:
    """Admin on a real browser session; never a token, never Aerith herself."""
    from core.middleware import INTERNAL_TOOL_HEADER, INTERNAL_TOOL_USER, require_admin
    from src.auth_helpers import get_current_user

    if getattr(request.state, "api_token", False):
        raise HTTPException(403, "Approvals need an admin browser session, not an API token")
    if request.headers.get(INTERNAL_TOOL_HEADER) or \
            getattr(request.state, "current_user", None) == INTERNAL_TOOL_USER:
        raise HTTPException(403, "Aerith cannot approve her own changes")
    require_admin(request)
    return get_current_user(request) or "admin"


def _public(prop: dict) -> dict:
    return {k: v for k, v in prop.items() if k not in ("worktree",)}


def setup_maintenance_routes(get_maintainer) -> APIRouter:
    """``get_maintainer()`` returns the live AerithMaintainer, or None when off."""
    router = APIRouter(prefix="/api/companion/aerith/maintenance", tags=["aerith-maintenance"])

    def _m():
        m = get_maintainer()
        if m is None:
            raise HTTPException(503, "Aerith maintenance is off (set AERITH_MAINTENANCE_ENABLED=1)")
        return m

    def _admin(request: Request) -> None:
        # Incidents and diffs can contain stack traces and code: admins only.
        from core.middleware import require_admin
        require_admin(request)

    @router.get("/page")
    def page(request: Request):
        from fastapi.responses import HTMLResponse
        from companion.maintenance.page import render_page
        _admin(request)
        return HTMLResponse(render_page(getattr(request.state, "csp_nonce", "")))

    @router.get("/status")
    def status(request: Request):
        _admin(request)
        m = get_maintainer()
        if m is None:
            return {"enabled": False}
        props = m.store.proposals()
        return {
            "enabled": True,
            "autofix": m.config.autofix,
            "watching": m.config.log_file,
            "owner_configured": bool(m.config.owner),
            "fixes_today": m.store.fixes_in_last_day(),
            "max_fixes_per_day": m.config.max_fixes_per_day,
            "open_incidents": len([i for i in m.store.incidents() if i["status"] in (st.OPEN, st.FIXING)]),
            "ready_for_review": len([p for p in props if p["status"] == st.READY]),
            "feature_options": len([p for p in props if p["kind"] == "feature" and p["status"] == st.OFFERED]),
        }

    @router.post("/logs")
    def report_logs(batch: ClientLogBatch):
        """Android/desktop clients report errors and crashes here."""
        m = _m()
        events = [
            ErrorEvent(
                platform=batch.platform,
                source=(e.source or batch.app_id or batch.platform)[:200],
                level=e.level.upper(),
                message=e.message,
                detail=e.detail,
                timestamp=e.timestamp,
                app_version=batch.app_version,
            )
            for e in batch.events
            if e.level.upper() in {"ERROR", "CRITICAL", "FATAL", "CRASH", "E", "F"}
        ]
        fresh = m.ingest(events)
        return {"accepted": len(events), "new_incidents": [i["id"] for i in fresh]}

    @router.get("/incidents")
    def incidents(request: Request, status: str | None = None):
        _admin(request)
        return {"incidents": _m().store.incidents(status)}

    @router.post("/incidents/{incident_id}/fix")
    def fix_now(incident_id: str, request: Request):
        require_human_admin(request)
        prop = _m().queue_fix(incident_id, force=True)
        if not prop:
            raise HTTPException(404, "Unknown incident")
        return _public(prop)

    @router.post("/incidents/{incident_id}/dismiss")
    def dismiss(incident_id: str, request: Request):
        require_human_admin(request)
        inc = _m().store.update_incident(incident_id, status=st.DISMISSED)
        if not inc:
            raise HTTPException(404, "Unknown incident")
        return inc

    @router.get("/proposals")
    def proposals(request: Request, kind: str | None = None, status: str | None = None):
        _admin(request)
        return {"proposals": [_public(p) for p in _m().store.proposals(kind, status)]}

    @router.get("/proposals/{proposal_id}")
    def proposal(proposal_id: str, request: Request):
        _admin(request)
        m = _m()
        prop = m.store.proposal(proposal_id)
        if not prop:
            raise HTTPException(404, "Unknown proposal")
        return {**_public(prop), "diff": m.builder.diff(proposal_id)}

    @router.post("/proposals/{proposal_id}/choose")
    def choose(proposal_id: str, request: Request):
        """Pick an offered feature option; Aerith starts building it."""
        require_human_admin(request)
        prop = _m().choose_feature(proposal_id)
        if not prop:
            raise HTTPException(409, "That option can't be built right now")
        return _public(prop)

    @router.post("/proposals/{proposal_id}/approve")
    def approve(proposal_id: str, request: Request):
        """Merge a tested change into the running app's checkout."""
        who = require_human_admin(request)
        try:
            prop = _m().builder.apply(proposal_id, approved_by=who)
        except BuildError as exc:
            raise HTTPException(409, str(exc)) from exc
        logger.info("Aerith change %s approved by %s", proposal_id, who)
        return {**_public(prop), "message": "Merged. Restart Odysseus to load the update."}

    @router.post("/proposals/{proposal_id}/reject")
    def reject(proposal_id: str, request: Request, body: RejectBody | None = None):
        who = require_human_admin(request)
        try:
            prop = _m().builder.reject(proposal_id, rejected_by=who,
                                       reason=(body.reason if body else ""))
        except BuildError as exc:
            raise HTTPException(409, str(exc)) from exc
        return _public(prop)

    @router.post("/features/from-research")
    async def features_from_research(body: ResearchBody, request: Request):
        """Ask Aerith for feature options from a research report (by id or text)."""
        import asyncio
        import json

        who = require_human_admin(request)
        m = _m()
        query, report = body.query, body.report
        if body.research_id:
            from src.constants import DEEP_RESEARCH_DIR
            rid = os.path.basename(body.research_id)
            try:
                with open(os.path.join(DEEP_RESEARCH_DIR, f"{rid}.json"), encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError):
                raise HTTPException(404, "Research not found")
            if data.get("owner") != who:
                raise HTTPException(404, "Research not found")
            query, report = data.get("query", ""), data.get("result") or ""
        if not report.strip():
            raise HTTPException(400, "No report text to read")
        offered = await asyncio.to_thread(
            offer_from_report, m.store, m.llm, query=query, report=report,
            research_id=body.research_id,
        )
        return {"options": [_public(p) for p in offered]}

    return router
