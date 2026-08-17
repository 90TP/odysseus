"""Companion bridge — /api/companion/*.

A thin, additive layer so a LAN client (e.g. a phone) can discover what a server
offers and pair to it, without duplicating any LLM logic.

Auth is enforced globally by AuthMiddleware (app.py), so reaching a handler here
means the caller is authenticated by either a cookie session or a Bearer `ody_`
API token. Ping/info accept either credential type, models requires a chat-
scoped API token for bearer callers, and the pairing endpoints are admin-cookie
only.

Pairing CSRF posture: minting happens ONLY on POST. The session cookie is
SameSite=Lax (routes/auth_routes.py), which a browser does not send on a
cross-site POST, so an admin's cookie can't be used by a malicious page to mint
a token -- the same protection the existing POST /api/tokens relies on. Minting
on a GET would be unsafe (Lax cookies ride top-level GET navigations), so GET
/pair only renders a form.
"""

import asyncio
import base64
import html
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from core.middleware import require_admin
from src.auth_helpers import get_current_user
from src.aerith_interaction import AerithInteraction
from src.aerith_speech import AerithSpeech, AerithSpeechError
from src.endpoint_resolver import normalize_base, resolve_endpoint_runtime
from src.llm_core import llm_call
from src.settings import get_setting

from companion import pairing as _pairing

logger = logging.getLogger(__name__)


class AerithInteractionRequest(BaseModel):
    message: str
    voice: bool = False


class AerithSpeakRequest(BaseModel):
    text: str


_aerith_interactions: dict[str, AerithInteraction] = {}
_aerith_speech = AerithSpeech()


def token_owner(request: Request) -> str | None:
    """The real owner to attribute a request to, for read-scoping.

    Cookie sessions resolve to the logged-in username via get_current_user.
    Bearer-token callers come through as the sandboxed pseudo-user "api"; their
    real owner is stamped on request.state.api_token_owner by the auth
    middleware. Returns None when no owner can be resolved.
    """
    if getattr(request.state, "api_token", False):
        return getattr(request.state, "api_token_owner", None)
    return get_current_user(request)


def owner_can_see(row_owner, owner) -> bool:
    """Owner-scope rule for read endpoints.

    A caller sees a row when it is their own, or when it is a legacy null-owner
    ("shared") row. A caller must NEVER see another owner's row. Mirrors the
    `owner_filter` rule used elsewhere, expressed as a pure predicate so it can
    be tested directly and used as a defensive in-Python check alongside the
    SQL filter.
    """
    return row_owner is None or row_owner == owner


def require_models_scope(request: Request) -> None:
    """Require the companion chat scope for bearer-token model inventory."""
    if not getattr(request.state, "api_token", False):
        return
    scopes = getattr(request.state, "api_token_scopes", None) or []
    if isinstance(scopes, str):
        scopes = [scope.strip() for scope in scopes.split(",")]
    scope_set = {str(scope).strip() for scope in scopes if str(scope).strip()}
    if _pairing.COMPANION_SCOPE not in scope_set:
        raise HTTPException(403, "API token requires chat scope")


def _resolve_aerith_route(owner: str | None) -> tuple[str, str, dict[str, str]]:
    """Resolve the owner's configured default LLM route."""
    endpoint_id = str(get_setting("default_endpoint_id", "") or "").strip()
    default_model = str(get_setting("default_model", "") or "").strip()

    from core.database import ModelEndpoint, SessionLocal

    db = SessionLocal()
    try:
        q = db.query(ModelEndpoint).filter(
            ModelEndpoint.is_enabled == True,  # noqa: E712
            (ModelEndpoint.model_type == "llm") | (ModelEndpoint.model_type == None),  # noqa: E711
        )
        if owner:
            q = q.filter((ModelEndpoint.owner == owner) | (ModelEndpoint.owner == None))  # noqa: E711

        endpoint = None
        if endpoint_id:
            endpoint = q.filter(ModelEndpoint.id == endpoint_id).first()
        if endpoint is None:
            endpoint = q.order_by(ModelEndpoint.created_at.asc()).first()
        if endpoint is None:
            raise RuntimeError("No enabled LLM endpoint is configured for Aerith")
        if not owner_can_see(endpoint.owner, owner):
            raise RuntimeError("Configured Aerith endpoint is not available to this owner")

        base_url, api_key = resolve_endpoint_runtime(endpoint, owner=owner)
        model = default_model
        if not model:
            try:
                cached = json.loads(endpoint.cached_models or "[]")
                hidden = set(json.loads(endpoint.hidden_models or "[]"))
                model = next(
                    (str(m) for m in cached if str(m).strip() and str(m) not in hidden),
                    "",
                )
            except Exception:
                model = ""
        if not model:
            raise RuntimeError("No default Aerith model is configured")

        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return normalize_base(base_url), model, headers
    finally:
        db.close()


def _get_aerith_interaction(owner: str | None) -> AerithInteraction:
    """Return the persistent Aerith interaction state for one companion owner."""
    key = owner or "__shared__"
    interaction = _aerith_interactions.get(key)
    if interaction is not None:
        return interaction

    def _llm(prompt: str) -> str:
        url, model, headers = _resolve_aerith_route(owner)
        return llm_call(
            url,
            model,
            [{"role": "user", "content": prompt}],
            headers=headers,
            temperature=0.4,
            max_tokens=512,
            prompt_type="aerith",
        )

    interaction = AerithInteraction(_llm)
    _aerith_interactions[key] = interaction
    return interaction


def mint_pairing_token(owner: str, invalidate=None) -> tuple[str, str]:
    """Mint a pairing token AND invalidate the auth middleware's in-memory token
    cache, so the new token is accepted on the very next request without a server
    restart. Returns (token_id, raw_token); the raw token is shown once.

    `invalidate` is the app's request.app.state.invalidate_token_cache callable
    (passed in so this stays a pure, testable unit).
    """
    token_id, raw_token = _pairing.mint_token(owner)
    if callable(invalidate):
        invalidate()
    return token_id, raw_token


async def _synth_aerith_voice(interaction: AerithInteraction, text: str) -> tuple[str, str]:
    """Generate voice while keeping Aerith's speaking state accurate."""
    interaction.set_speaking(True)
    try:
        result = await _aerith_speech.synthesize(text)
        return base64.b64encode(result.audio).decode("ascii"), result.media_type
    finally:
        interaction.set_speaking(False)


def setup_companion_routes() -> APIRouter:
    router = APIRouter(prefix="/api/companion", tags=["companion"])

    @router.get("/ping")
    def ping(request: Request):
        """Cheap, auth-validated health check. A 200 with ok=true confirms the
        host/port and credential are valid; middleware returns 401 otherwise."""
        from core.constants import APP_VERSION
        return {
            "ok": True,
            "name": "odysseus",
            "version": APP_VERSION,
            "auth": "token" if getattr(request.state, "api_token", False) else "session",
        }

    @router.get("/info")
    def info(request: Request):
        """Server identity + coarse capability flags. `owner` is the caller's own
        identity (the token's owner for bearer callers)."""
        from core.constants import APP_VERSION
        return {
            "name": "odysseus",
            "version": APP_VERSION,
            "owner": token_owner(request),
            "capabilities": {
                "chat": True,
                "streaming": True,
                "aerith_interaction": True,
                "aerith_voice": _aerith_speech.enabled,
            },
        }

    @router.get("/models")
    def models(request: Request):
        """LLM model endpoints the CALLER can use.

        The stock /api/models route scopes to get_current_user, which for a
        bearer token is the sandboxed pseudo-user "api" (owns nothing). Here we
        scope to the token's real owner instead, plus legacy null-owner shared
        rows -- the same rule as owner_filter. Read-only; never returns api_key
        material.
        """
        require_models_scope(request)
        import json as _json

        from core.database import SessionLocal, ModelEndpoint
        from src.endpoint_resolver import build_chat_url

        owner = token_owner(request)
        out = []
        db = SessionLocal()
        try:
            q = db.query(ModelEndpoint).filter(
                ModelEndpoint.is_enabled == True,  # noqa: E712
                (ModelEndpoint.model_type == "llm") | (ModelEndpoint.model_type == None),  # noqa: E711
            )
            if owner:
                q = q.filter((ModelEndpoint.owner == owner) | (ModelEndpoint.owner == None))  # noqa: E711
            for ep in q.all():
                if not owner_can_see(ep.owner, owner):
                    continue
                try:
                    model_ids = _json.loads(ep.cached_models) if ep.cached_models else []
                except (ValueError, TypeError):
                    model_ids = []
                try:
                    hidden = set(_json.loads(ep.hidden_models)) if ep.hidden_models else set()
                except (ValueError, TypeError):
                    hidden = set()
                model_ids = [m for m in model_ids if m not in hidden]
                try:
                    chat_url = build_chat_url(ep.base_url)
                except Exception:
                    chat_url = ep.base_url
                out.append({
                    "endpoint_id": ep.id,
                    "name": ep.name,
                    "endpoint_url": chat_url,
                    "models": model_ids,
                    "supports_tools": ep.supports_tools,
                })
        finally:
            db.close()
        return {"endpoints": out}

    @router.post("/aerith/interact")
    async def aerith_interact(payload: AerithInteractionRequest, request: Request):
        """Send a message from the 3D Aerith companion into Odysseus.

        Set ``voice=true`` for a complete voice-chat response.  The audio is
        returned as base64 so a browser/3D client can play it with a Blob or
        data URL while still sending its normal Authorization header to this
        endpoint.
        """
        owner = token_owner(request)
        if not owner:
            raise HTTPException(401, "Aerith interaction requires an authenticated companion")
        message = payload.message.strip()
        if not message:
            raise HTTPException(400, "Message is required")

        interaction = _get_aerith_interaction(owner)
        try:
            response = await asyncio.to_thread(interaction.respond, message)
        except Exception as exc:
            logger.exception("Aerith interaction failed")
            raise HTTPException(502, "Aerith interaction failed") from exc

        result = {"response": response}
        if payload.voice:
            if not _aerith_speech.enabled:
                raise HTTPException(503, "Aerith voice is not enabled")
            try:
                audio, media_type = await _synth_aerith_voice(interaction, response)
            except AerithSpeechError as exc:
                logger.exception("Aerith speech synthesis failed")
                raise HTTPException(502, f"Aerith speech synthesis failed: {exc}") from exc
            result.update({"audio_base64": audio, "audio_media_type": media_type, "voice": True})
        else:
            result["voice"] = False
        return result

    @router.post("/aerith/speak")
    async def aerith_speak(payload: AerithSpeakRequest, request: Request):
        """Synthesise arbitrary already-generated Aerith text into her voice."""
        owner = token_owner(request)
        if not owner:
            raise HTTPException(401, "Aerith speech requires an authenticated companion")
        text = payload.text.strip()
        if not text:
            raise HTTPException(400, "Text is required")
        if not _aerith_speech.enabled:
            raise HTTPException(503, "Aerith voice is not enabled")
        interaction = _get_aerith_interaction(owner)
        try:
            audio, media_type = await _synth_aerith_voice(interaction, text)
        except AerithSpeechError as exc:
            logger.exception("Aerith speech synthesis failed")
            raise HTTPException(502, f"Aerith speech synthesis failed: {exc}") from exc
        return {"audio_base64": audio, "audio_media_type": media_type, "voice": True}

    @router.post("/aerith/audio")
    async def aerith_audio(payload: AerithSpeakRequest, request: Request):
        """Return generated speech directly as an audio response.

        This is useful for clients which already have an authenticated HTTP
        wrapper and want a native WAV/MP3 response instead of base64 JSON.
        """
        owner = token_owner(request)
        if not owner:
            raise HTTPException(401, "Aerith speech requires an authenticated companion")
        text = payload.text.strip()
        if not text:
            raise HTTPException(400, "Text is required")
        if not _aerith_speech.enabled:
            raise HTTPException(503, "Aerith voice is not enabled")
        interaction = _get_aerith_interaction(owner)
        interaction.set_speaking(True)
        try:
            result = await _aerith_speech.synthesize(text)
        except AerithSpeechError as exc:
            logger.exception("Aerith speech synthesis failed")
            raise HTTPException(502, f"Aerith speech synthesis failed: {exc}") from exc
        finally:
            interaction.set_speaking(False)
        return Response(content=result.audio, media_type=result.media_type)

    @router.get("/aerith/state")
    async def aerith_state(request: Request):
        """Return the current interaction state for the paired companion."""
        owner = token_owner(request)
        if not owner:
            raise HTTPException(401, "Aerith interaction requires an authenticated companion")
        snapshot = _get_aerith_interaction(owner).snapshot()
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

    @router.get("/pair")
    def pair_page(request: Request):
        """Admin-only pairing page. Renders a form that POSTs to mint a code.

        A GET never mints a credential: SameSite=Lax session cookies ride
        top-level GET navigations, so minting on GET would be triggerable by a
        link or <img> (CSRF). The actual mint is the POST handler below.
        """
        require_admin(request)
        page = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pair a device</title>
<style>
  body{font-family:-apple-system,system-ui,sans-serif;max-width:520px;margin:48px auto;padding:0 20px;color:#e8e8e8;background:#16161a}
  .card{background:#1f1f25;border:1px solid #2c2c35;border-radius:14px;padding:28px;text-align:center}
  button{background:#7c9cff;color:#0e0e12;border:none;border-radius:10px;padding:12px 20px;font-size:15px;font-weight:600;cursor:pointer}
</style></head>
<body><div class="card">
  <h2>Pair a device</h2>
  <p>Generate a one-time pairing code (a chat-scoped API token) for a LAN client.</p>
  <form method="POST" action="/api/companion/pair">
    <button type="submit">Generate pairing code</button>
  </form>
  <p style="color:#8a8a96;font-size:12px;margin-top:18px">Admin only. Each code mints a new token, shown once. Manage or revoke under Settings &rarr; API tokens.</p>
</div></body></html>"""
        return HTMLResponse(page)

    @router.post("/pair")
    def pair_create(request: Request):
        """Mint a pairing code. Admin-cookie only; CSRF-safe because the
        SameSite=Lax session cookie is not sent on a cross-site POST (same
        protection as POST /api/tokens). Minting invalidates the token cache so
        the code works immediately, no restart. `?format=json` returns the
        payload for an in-app pairing screen."""
        require_admin(request)
        owner = get_current_user(request)
        invalidate = getattr(request.app.state, "invalidate_token_cache", None)
        token_id, raw_token = mint_pairing_token(owner, invalidate)

        hosts = _pairing.lan_ip_candidates()
        host = hosts[0] if hosts else "127.0.0.1"
        port = request.url.port or _pairing.default_port()
        payload = _pairing.pairing_payload(host, port, raw_token)
        qr = _pairing.pairing_qr_png_data_uri(payload)
        qr_ok = bool(qr and qr.startswith("data:image/png;base64,"))

        if (request.query_params.get("format") or "").lower() == "json":
            return {
                "host": host,
                "port": port,
                "token": raw_token,
                "token_id": token_id,
                "hosts": hosts,
                "payload": payload,
                "qr": qr if qr_ok else None,
            }

        import json as _json
        payload_json = _json.dumps(payload, separators=(",", ":"))
        # Only ever emit a known PNG data-URI into the src; every other value is
        # html.escaped.
        qr_block = (
            f'<img src="{html.escape(qr)}" alt="Pairing QR" width="260" height="260">'
            if qr_ok else "<p><em>QR rendering unavailable -- enter the details manually.</em></p>"
        )
        page = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pairing code</title>
<style>
  body{{font-family:-apple-system,system-ui,sans-serif;max-width:520px;margin:40px auto;padding:0 20px;color:#e8e8e8;background:#16161a}}
  .card{{background:#1f1f25;border:1px solid #2c2c35;border-radius:14px;padding:24px;text-align:center}}
  code{{background:#0e0e12;padding:2px 6px;border-radius:6px;word-break:break-all}}
  .row{{text-align:left;margin:10px 0;font-size:14px;color:#bdbdc7}}
  .warn{{color:#e0a85e;font-size:13px;margin-top:18px}}
</style></head>
<body><div class="card">
  <h2>Pairing code</h2>
  {qr_block}
  <div class="row"><strong>Host:</strong> <code>{html.escape(host)}</code></div>
  <div class="row"><strong>Port:</strong> <code>{html.escape(str(port))}</code></div>
  <div class="row"><strong>Token:</strong> <code>{html.escape(raw_token)}</code></div>
  <div class="row"><strong>Payload:</strong> <code>{html.escape(payload_json)}</code></div>
  <p class="warn">Shown once. This grants chat access to your Odysseus; revoke it
  in Settings &rarr; API tokens (id <code>{html.escape(token_id)}</code>). The
  device must be on the same network, and the server must bind to your LAN.</p>
</div></body></html>"""
        return HTMLResponse(page)

    return router
