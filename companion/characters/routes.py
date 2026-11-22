"""/api/companion/characters/{character}/*: a character's FF7-style sheet.

A paired phone (bearer token) or a signed-in browser can push telemetry and
read the sheet; data is scoped to the caller's own account.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Union

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

from companion.characters.page import render_page
from companion.characters.stats import build_sheet
from companion.characters.store import CHAR_RE, CharacterStore

Scalar = Union[float, int, str]


class Device(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    kind: Literal["phone", "watch", "ring", "tablet", "earbuds", "other"] = "other"
    make: str | None = Field(None, max_length=60)
    model: str | None = Field(None, max_length=80)
    battery: float | None = Field(None, ge=0, le=100)
    charging: bool | None = None


class Metric(BaseModel):
    value: Scalar
    unit: str = Field("", max_length=16)
    source: str = Field("", max_length=64)

    @field_validator("value")
    @classmethod
    def _short(cls, v):
        if isinstance(v, str) and len(v) > 64:
            raise ValueError("metric text is limited to 64 characters")
        return v


class App(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    package: str = Field("", max_length=160)
    category: str = Field("", max_length=40)
    device: str = Field("", max_length=64)


class Location(BaseModel):
    # A place name only ("Home", "Work", "Leeds"). Coordinates aren't stored.
    label: str = Field(..., min_length=1, max_length=80)


class Telemetry(BaseModel):
    devices: list[Device] = Field(default_factory=list, max_length=20)
    metrics: dict[str, Union[Metric, Scalar]] = Field(default_factory=dict)
    apps: list[App] | None = Field(None, max_length=300)
    location: Location | None = None

    @field_validator("metrics")
    @classmethod
    def _metrics(cls, v):
        if len(v) > 60:
            raise ValueError("too many metrics")
        for key in v:
            if not CHAR_RE.match(key.replace("_", "-")):
                raise ValueError(f"bad metric name: {key}")
        return v


class Profile(BaseModel):
    display_name: str | None = Field(None, max_length=40)
    avatar_url: str | None = Field(None, max_length=500)
    birthdate: date | None = None
    level: int | None = Field(None, ge=1, le=999)
    sleep_goal_minutes: int | None = Field(None, ge=60, le=1000)
    slot_devices: dict[str, str] | None = None

    @field_validator("avatar_url")
    @classmethod
    def _avatar(cls, v):
        # Only same-origin paths or data: images, so the sheet never calls out.
        if v and not (v.startswith("/") and not v.startswith("//") or v.startswith("data:image/")):
            raise ValueError("avatar_url must be a path on this server (e.g. /static/...) or a data: image")
        return v


def _owner(request: Request) -> str:
    from companion.routes import token_owner
    import os
    owner = token_owner(request)
    if not owner and os.getenv("AUTH_ENABLED", "true").lower() == "false":
        return "local"  # single-user install with auth switched off
    if not owner:
        raise HTTPException(401, "Sign in or pair this device first")
    return owner


def _character(character: str) -> str:
    if not CHAR_RE.match(character or ""):
        raise HTTPException(400, "Character ids are lowercase letters, numbers and dashes")
    return character


def setup_character_routes(store: CharacterStore | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/companion/characters", tags=["characters"])
    store_ = store or CharacterStore()

    @router.get("/{character}")
    def sheet(character: str, request: Request):
        return build_sheet(store_.load(_owner(request), _character(character)))

    @router.post("/{character}/telemetry")
    def telemetry(character: str, body: Telemetry, request: Request):
        payload = body.model_dump(exclude_none=True)
        payload["metrics"] = {
            k: (v if isinstance(v, dict) else {"value": v})
            for k, v in payload.get("metrics", {}).items()
        }
        if body.apps is not None:
            payload["apps"] = [a.model_dump() for a in body.apps]
        data = store_.apply_telemetry(_owner(request), _character(character), payload)
        return {"ok": True, "updated_at": data["updated_at"]}

    @router.get("/{character}/profile")
    def get_profile(character: str, request: Request):
        return store_.load(_owner(request), _character(character)).get("profile") or {}

    @router.put("/{character}/profile")
    def put_profile(character: str, body: Profile, request: Request):
        fields = body.model_dump(exclude_unset=True)
        if "birthdate" in fields and fields["birthdate"] is not None:
            fields["birthdate"] = fields["birthdate"].isoformat()
        data = store_.update_profile(_owner(request), _character(character), fields)
        return data.get("profile") or {}

    @router.get("/{character}/page")
    def page(character: str, request: Request):
        _owner(request)
        return HTMLResponse(render_page(_character(character), getattr(request.state, "csp_nonce", "")))

    return router
