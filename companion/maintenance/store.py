"""Disk-backed state for incidents, proposals and the log cursor."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any

from companion.maintenance.log_watch import ErrorEvent

PLATFORMS = {"server", "android", "desktop"}

# Incident lifecycle
OPEN, FIXING, PROPOSED, RESOLVED, DISMISSED, FIX_FAILED = (
    "open", "fixing", "proposed", "resolved", "dismissed", "fix_failed",
)
# Proposal lifecycle
OFFERED, QUEUED, BUILDING, READY, FAILED, APPLIED, REJECTED, SUPERSEDED = (
    "offered", "queued", "building", "ready", "failed", "applied", "rejected", "superseded",
)


def _atomic_write(path: str, data: Any) -> None:
    try:
        from core.atomic_io import atomic_write_json
        atomic_write_json(path, data, indent=2)
        return
    except ImportError:  # pragma: no cover
        pass
    tmp = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


class MaintenanceStore:
    """Small JSON store. One file, guarded by a lock; volumes are tiny."""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, "state.json")
        self._lock = threading.RLock()

    # -- raw ---------------------------------------------------------------
    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                data.setdefault("incidents", {})
                data.setdefault("proposals", {})
                data.setdefault("cursor", {})
                data.setdefault("fix_log", [])
                data.setdefault("cid", {"messages": [], "unread": 0})
                return data
        except (OSError, ValueError):
            pass
        return {"incidents": {}, "proposals": {}, "cursor": {}, "fix_log": [],
                "cid": {"messages": [], "unread": 0}}

    def _save(self, data: dict) -> None:
        _atomic_write(self.path, data)

    # -- cursor ------------------------------------------------------------
    def cursor(self, name: str) -> dict:
        with self._lock:
            return dict(self._load()["cursor"].get(name) or {})

    def set_cursor(self, name: str, value: dict) -> None:
        with self._lock:
            data = self._load()
            data["cursor"][name] = value
            self._save(data)

    # -- incidents ---------------------------------------------------------
    def record_event(self, event: ErrorEvent) -> tuple[dict, bool]:
        """Add an event; returns (incident, is_new_or_reopened)."""
        now = time.time()
        fp = event.fingerprint
        with self._lock:
            data = self._load()
            inc = data["incidents"].get(fp)
            fresh = inc is None
            if fresh:
                inc = {
                    "id": fp,
                    "platform": event.platform,
                    "source": event.source,
                    "level": event.level,
                    "message": event.message[:2000],
                    "detail": event.detail[-8000:],
                    "app_version": event.app_version,
                    "first_seen": now,
                    "count": 0,
                    "status": OPEN,
                    "proposal_id": None,
                }
            elif inc["status"] in (RESOLVED,):
                # An applied fix that didn't hold: reopen so Aerith tries again.
                inc["status"] = OPEN
                inc["reopened"] = int(inc.get("reopened") or 0) + 1
                fresh = True
            inc["count"] = int(inc.get("count") or 0) + 1
            inc["last_seen"] = now
            if event.detail:
                inc["detail"] = event.detail[-8000:]
            if event.app_version:
                inc["app_version"] = event.app_version
            data["incidents"][fp] = inc
            self._save(data)
            return dict(inc), fresh

    def incidents(self, status: str | None = None) -> list[dict]:
        with self._lock:
            items = list(self._load()["incidents"].values())
        if status:
            items = [i for i in items if i.get("status") == status]
        return sorted(items, key=lambda i: i.get("last_seen", 0), reverse=True)

    def incident(self, incident_id: str) -> dict | None:
        with self._lock:
            inc = self._load()["incidents"].get(incident_id)
            return dict(inc) if inc else None

    def update_incident(self, incident_id: str, **fields) -> dict | None:
        with self._lock:
            data = self._load()
            inc = data["incidents"].get(incident_id)
            if not inc:
                return None
            inc.update(fields)
            self._save(data)
            return dict(inc)

    # -- proposals ---------------------------------------------------------
    def add_proposal(self, kind: str, title: str, summary: str, **fields) -> dict:
        now = time.time()
        prop = {
            "id": uuid.uuid4().hex[:12],
            "kind": kind,               # "bugfix" | "feature"
            "title": title.strip()[:200],
            "summary": summary.strip()[:4000],
            "status": fields.pop("status", OFFERED),
            "platforms": [p for p in fields.pop("platforms", []) if p in PLATFORMS] or ["server"],
            "created_at": now,
            "updated_at": now,
        }
        prop.update(fields)
        with self._lock:
            data = self._load()
            data["proposals"][prop["id"]] = prop
            self._save(data)
        return dict(prop)

    def proposals(self, kind: str | None = None, status: str | None = None) -> list[dict]:
        with self._lock:
            items = list(self._load()["proposals"].values())
        if kind:
            items = [p for p in items if p.get("kind") == kind]
        if status:
            items = [p for p in items if p.get("status") == status]
        return sorted(items, key=lambda p: p.get("created_at", 0), reverse=True)

    def proposal(self, proposal_id: str) -> dict | None:
        with self._lock:
            prop = self._load()["proposals"].get(proposal_id)
            return dict(prop) if prop else None

    def update_proposal(self, proposal_id: str, **fields) -> dict | None:
        with self._lock:
            data = self._load()
            prop = data["proposals"].get(proposal_id)
            if not prop:
                return None
            prop.update(fields)
            prop["updated_at"] = time.time()
            self._save(data)
            return dict(prop)

    # -- Cid's planning conversation -------------------------------------
    MAX_CID_MESSAGES = 200

    def add_cid_message(self, role: str, content: str, **fields) -> dict:
        msg = {"id": uuid.uuid4().hex[:10], "role": role, "content": content[:6000],
               "at": time.time(), **fields}
        with self._lock:
            data = self._load()
            cid = data["cid"]
            cid["messages"] = (cid.get("messages") or [])[-(self.MAX_CID_MESSAGES - 1):] + [msg]
            cid["unread"] = int(cid.get("unread") or 0) + 1 if role == "cid" else 0
            self._save(data)
        return dict(msg)

    def cid_messages(self) -> list[dict]:
        with self._lock:
            return list(self._load()["cid"].get("messages") or [])

    def cid_unread(self) -> int:
        with self._lock:
            return int(self._load()["cid"].get("unread") or 0)

    def mark_cid_read(self) -> None:
        with self._lock:
            data = self._load()
            data["cid"]["unread"] = 0
            self._save(data)

    # -- rate limiting -----------------------------------------------------
    def fixes_in_last_day(self) -> int:
        cutoff = time.time() - 86400
        with self._lock:
            return sum(1 for t in self._load()["fix_log"] if t >= cutoff)

    def note_fix_attempt(self) -> None:
        cutoff = time.time() - 86400
        with self._lock:
            data = self._load()
            data["fix_log"] = [t for t in data["fix_log"] if t >= cutoff] + [time.time()]
            self._save(data)
