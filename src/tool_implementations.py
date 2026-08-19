"""
tool_implementations.py

Extracted tool implementation functions (do_* and helpers) from agent_tools.py.
These handle the actual execution logic for each tool type.
"""

import logging
from typing import Dict, Optional

from src.tool_utils import get_mcp_manager  # re-exported: tests patch src.tool_implementations.get_mcp_manager

# System-domain tools were extracted to src/tools/system.py (slice 1,
# #4082/#4071); the admin manage_* tools live in src/agent_tools/admin_tools
# after the upstream registry migration (#3629). Re-imported here so this
# module stays a working facade.
from src.tools.system import (  # noqa: F401
    do_manage_skills as _do_manage_skills_base, _skill_dump, do_manage_tasks,
    do_api_call, do_app_api,
    _APP_API_BLOCKLIST_PREFIXES, _APP_API_BLOCKLIST_METHOD_PATH,
)


def _extend_manage_skills_schema() -> None:
    """Teach native function-calling about the evolution actions.

    The schema is defined in a large central registry, while the implementation
    is intentionally wrapped here. Mutating the already-loaded schema avoids a
    second copy of the registry and keeps the compatibility facade as the
    single integration point for this feature.
    """
    try:
        from src.tool_schemas import FUNCTION_TOOL_SCHEMAS
        for entry in FUNCTION_TOOL_SCHEMAS:
            fn = entry.get("function", {})
            if fn.get("name") != "manage_skills":
                continue
            params = fn.setdefault("parameters", {})
            props = params.setdefault("properties", {})
            action = props.get("action", {})
            enum = list(action.get("enum") or [])
            for value in ("compose", "extend", "lineage", "retire", "promote"):
                if value not in enum:
                    enum.append(value)
            action["enum"] = enum
            action["description"] = (
                "CRUD: list/view/view_ref/add/edit/patch/publish/delete/search. "
                "Evolution: compose combines existing skills; extend adds capability "
                "to an existing skill; lineage shows ancestry; retire hides a skill "
                "without deleting its history; promote publishes a verified evolved skill."
            )
            props.update({
                "parents": {"type": "array", "items": {"type": "string"}, "description": "Parent skill names for compose (minimum two)."},
                "procedure_append": {"type": "array", "items": {"type": "string"}, "description": "Steps to append when extending a skill."},
                "procedure_prepend": {"type": "array", "items": {"type": "string"}, "description": "Steps to prepend when extending a skill."},
                "pitfalls_append": {"type": "array", "items": {"type": "string"}, "description": "Additional pitfalls for extend."},
                "verification_append": {"type": "array", "items": {"type": "string"}, "description": "Additional verification steps for extend."},
                "tags_add": {"type": "array", "items": {"type": "string"}, "description": "Tags to add when extending."},
                "recursive": {"type": "boolean", "description": "For lineage, include the complete ancestry tree (default true)."},
                "reason": {"type": "string", "description": "Reason for retiring a skill."},
                "skills": {"type": "array", "items": {"type": "string"}, "description": "Alias for parents when composing."},
            })
            return
    except Exception:
        logging.getLogger(__name__).debug("Could not extend manage_skills native schema", exc_info=True)


_extend_manage_skills_schema()


async def do_manage_skills(content: str, owner: Optional[str] = None) -> Dict:
    """Extend the native skill registry with composition/evolution actions.

    Existing CRUD remains in ``src.tools.system``; the evolution manager is
    deliberately kept as a thin facade so the established tool schema and
    ownership checks continue to apply unchanged.
    """
    try:
        from src.tool_utils import _parse_tool_args
        args = _parse_tool_args(content)
    except (ValueError, TypeError):
        return await _do_manage_skills_base(content, owner=owner)

    action = str(args.get("action") or "").strip().lower()
    if action not in {"compose", "extend", "lineage", "retire", "promote"}:
        return await _do_manage_skills_base(content, owner=owner)

    from services.memory.skill_evolution import SkillEvolutionError, SkillEvolutionManager
    from services.memory.skills import SkillsManager
    from src.constants import DATA_DIR

    manager = SkillEvolutionManager(SkillsManager(DATA_DIR))
    name = str(args.get("name") or args.get("skill_id") or "").strip()
    try:
        if action == "compose":
            parents = args.get("parents") or args.get("skills") or []
            if not isinstance(parents, list):
                return {"error": "parents must be a list of skill names", "exit_code": 1}
            result = manager.compose(
                name,
                [str(p) for p in parents],
                owner=owner,
                description=str(args.get("description") or ""),
                when_to_use=str(args.get("when_to_use") or ""),
                procedure=args.get("procedure"),
                category=str(args.get("category") or "composed"),
                tags=args.get("tags") or [],
                status=str(args.get("status") or "draft"),
                confidence=float(args.get("confidence", 0.7)),
            )
            return {"results": f"Composed skill `{result['name']}` from {', '.join(result['lineage']['parents'])}.", "skill": result}

        if action == "extend":
            if not name:
                return {"error": "name is required for extend", "exit_code": 1}
            result = manager.extend(
                name,
                owner=owner,
                procedure_append=args.get("procedure_append") or args.get("append_steps") or [],
                procedure_prepend=args.get("procedure_prepend") or args.get("prepend_steps") or [],
                pitfalls_append=args.get("pitfalls_append") or [],
                verification_append=args.get("verification_append") or [],
                tags_add=args.get("tags_add") or [],
                description=args.get("description"),
                when_to_use=args.get("when_to_use"),
                confidence=args.get("confidence"),
            )
            return {"results": f"Extended `{name}` to version {result.get('version', '?')}.", "skill": result}

        if action == "lineage":
            if not name:
                return {"error": "name is required for lineage", "exit_code": 1}
            result = manager.lineage(name, owner=owner, recursive=bool(args.get("recursive", True)))
            return {"results": result}

        if action == "retire":
            if not name:
                return {"error": "name is required for retire", "exit_code": 1}
            result = manager.retire(name, owner=owner, reason=str(args.get("reason") or ""))
            return {"results": f"Retired `{name}` without deleting its lineage.", "skill": result}

        if action == "promote":
            if not name:
                return {"error": "name is required for promote", "exit_code": 1}
            result = manager.promote(name, owner=owner, confidence=args.get("confidence"))
            return {"results": f"Promoted `{name}` to published.", "skill": result}
    except (SkillEvolutionError, ValueError, TypeError) as exc:
        return {"error": str(exc), "exit_code": 1}

    return {"error": f"Unsupported evolution action: {action}", "exit_code": 1}


# Admin manage_* tools (endpoints/mcp/webhooks/tokens/settings) live in
# src/agent_tools/admin_tools after the upstream registry migration (#3629).
# Re-exported lazily via __getattr__: src.agent_tools.__init__ imports this
# facade at top level, so a eager `from src.agent_tools.admin_tools import`
# here would re-enter the partially-initialized agent_tools package (circular).
_ADMIN_TOOL_SYMBOLS = (
    "do_manage_endpoints", "do_manage_mcp", "do_manage_webhooks",
    "do_manage_tokens", "do_manage_settings",
    "_MCP_DENIED_COMMANDS", "_validate_mcp_command", "_mcp_allowed_commands",
)


def __getattr__(name):
    if name in _ADMIN_TOOL_SYMBOLS:
        from src.agent_tools import admin_tools
        return getattr(admin_tools, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Cookbook (model serving) domain extracted to src/tools/cookbook.py
# (slice 1, #4082/#4071). Re-imported here so this module stays a working
# facade. cookbook.py pulls `_internal_headers` / `_INTERNAL_BASE` back
# function-locally from this facade (which re-exports them from _common).
from src.tools.cookbook import (  # noqa: F401
    do_download_model, do_serve_model, do_list_served_models,
    do_stop_served_model, do_tail_serve_output, do_list_downloads,
    do_cancel_download, do_search_hf_models, do_adopt_served_model,
    do_list_cookbook_servers, do_list_serve_presets, do_serve_preset,
    do_list_cached_models,
    _cookbook_servers, _resolve_cookbook_host, _cookbook_env_for_host,
    _infer_serve_port, _infer_serve_host, _ensure_served_endpoint,
    _cookbook_register_task, _cookbook_apply_retry_suggestion,
    _scan_running_model_processes, _cookbook_kill_session,
    _MODEL_PROCESS_PATTERNS,
    _string_arg, _validate_cookbook_ssh_target,
)
# Search domain extracted to src/tools/search.py (slice 1, #4082/#4071).
# Re-imported here so this module stays a working facade.
from src.tools.search import do_search_chats  # noqa: F401
# Notes domain extracted to src/tools/notes.py (slice 1, #4082/#4071).
from src.tools.notes import do_manage_notes  # noqa: F401
# Calendar domain extracted to src/tools/calendar.py (slice 1, #4082/#4071).
from src.tools.calendar import do_manage_calendar  # noqa: F401
# Image domain extracted to src/tools/image.py (slice 1, #4082/#4071).
from src.tools.image import do_edit_image  # noqa: F401
# Research domain extracted to src/tools/research.py (slice 1, #4082/#4071).
from src.tools.research import do_manage_research, do_trigger_research  # noqa: F401
# Contacts domain extracted to src/tools/contacts.py (slice 1, #4082/#4071).
from src.tools.contacts import do_resolve_contact, do_manage_contact  # noqa: F401
# Vault domain extracted to src/tools/vault.py (slice 1, #4082/#4071).
from src.tools.vault import (  # noqa: F401
    _load_vault_config, _run_bw,
    do_vault_search, do_vault_get, do_vault_unlock,
)
# Shared helpers live in src/tools/_common.py. Re-exported here so the
# function-local `from src.tool_implementations import _INTERNAL_BASE` (and
# friends) used by domain files still resolve through this facade.
from src.tools._common import _parse_tool_args, _INTERNAL_BASE, _internal_headers  # noqa: F401

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Active email state
# ---------------------------------------------------------------------------

# When the user has an email reader window open, the frontend tells the
# backend about it on each chat submit. Email tools can resolve "this email"
# without guessing a UID. Cleared between requests by chat_routes.
_active_email_ref: Optional[Dict[str, str]] = None


def set_active_email(uid: Optional[str], folder: Optional[str] = None, account: Optional[str] = None,
                     subject: Optional[str] = None, sender: Optional[str] = None) -> None:
    """Stash the email currently open in the UI. None clears it."""
    global _active_email_ref
    if not uid:
        _active_email_ref = None
        return
    _active_email_ref = {
        "uid": str(uid),
        "folder": str(folder or "INBOX"),
        "account": str(account or ""),
        "subject": str(subject or ""),
        "from": str(sender or ""),
    }


def get_active_email() -> Optional[Dict[str, str]]:
    return _active_email_ref


def clear_active_email() -> None:
    global _active_email_ref
    _active_email_ref = None
