"""HTTP bridge between the Aerith interaction layer and the 3D companion."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.database import ModelEndpoint, SessionLocal
from core.middleware import INTERNAL_TOOL_HEADER, INTERNAL_TOOL_TOKEN
from src.aerith_interaction import AerithInteraction
from src.llm_core import llm_call
from src.settings import get_setting
from src.endpoint_resolver import resolve_endpoint_runtime, normalize_base

logger = logging.getLogger(__name__)


class AerithInteractionRequest(BaseModel):
    message: str


class AerithInteractionResponse(BaseModel):
    response: str


def _resolve_default_route() -> tuple[str, str, dict[str, str]]:
    """Resolve the configured default chat route for the Aerith companion."""
    endpoint_id = str(get_setting("default_endpoint_id", "") or "").strip()
    default_model = str(get_setting("default_model", "") or "").strip()

    db = SessionLocal()
    try:
        query = db.query(ModelEndpoint).filter(ModelEndpoint.is_enabled == True)  # noqa: E712
        endpoint = None
        if endpoint_id:
            endpoint = query.filter(ModelEndpoint.id == endpoint_id).first()
        if endpoint is None:
            endpoint = query.order_by(ModelEndpoint.created_at.asc()).first()
        if endpoint is None:
            raise RuntimeError("No enabled model endpoint is configured")

        base_url, api_key = resolve_endpoint_runtime(endpoint)
        model = default_model
        if not model:
            try:
                import json
                cached = json.loads(endpoint.cached_models or "[]")
                model = next((str(m) for m in cached if str(m).strip()), "")
            except Exception:
                model = ""
        if not model:
            raise RuntimeError("No default model is configured")

        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return normalize_base(base_url), model, headers
    finally:
        db.close()


def _llm(prompt: str) -> str:
    """Synchronous adapter used by AerithInteraction."""
    url, model, headers = _resolve_default_route()
    return llm_call(
        url,
        model,
        [{"role": "user", "content": prompt}],
        headers=headers,
        temperature=0.4,
        max_tokens=512,
        prompt_type="aerith",
        session_id="aerith-3d-companion",
    )


# The companion is deliberately backed by one process-local interaction state:
# its conversation should survive individual HTTP requests from Godot.
aerith_interaction = AerithInteraction(_llm)


def _authorised(request: Request) -> bool:
    """Only permit the local 3D companion/internal tool to use this bridge."""
    token = request.headers.get(INTERNAL_TOOL_HEADER, "")
    return bool(token) and token == INTERNAL_TOOL_TOKEN


def setup_aerith_routes() -> APIRouter:
    router = APIRouter(prefix="/api/aerith", tags=["aerith"])

    @router.post("/interact", response_model=AerithInteractionResponse)
    async def interact(payload: AerithInteractionRequest, request: Request) -> Any:
        if not _authorised(request):
            raise HTTPException(status_code=401, detail="Aerith companion authentication required")

        message = payload.message.strip()
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")

        try:
            response = await asyncio.to_thread(aerith_interaction.respond, message)
        except Exception as exc:
            logger.exception("Aerith interaction failed")
            raise HTTPException(status_code=502, detail="Aerith interaction failed") from exc

        return AerithInteractionResponse(response=response)

    @router.get("/state")
    async def state(request: Request) -> dict[str, Any]:
        if not _authorised(request):
            raise HTTPException(status_code=401, detail="Aerith companion authentication required")
        snapshot = aerith_interaction.snapshot()
        return {
            "listening": snapshot.listening,
            "speaking": snapshot.speaking,
            "acting": snapshot.acting,
            "last_user_message": snapshot.last_user_message,
            "last_aerith_response": snapshot.last_aerith_response,
            "visual": {
                "description": snapshot.visual.description,
                "monitor_id": snapshot.visual.monitor_id,
                "age": snapshot.visual.age,
                "pending": snapshot.visual.pending,
            },
        }

    return router
