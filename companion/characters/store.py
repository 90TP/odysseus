"""Per-owner, per-character state on disk: profile, devices, metrics, apps."""

from __future__ import annotations

import json
import os
import re
import threading
import time

CHAR_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_lock = threading.RLock()


def _data_root() -> str:
    try:
        from src.constants import DATA_DIR
    except Exception:  # pragma: no cover
        DATA_DIR = "data"
    return os.path.join(DATA_DIR, "characters")


def _safe(part: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.@-]", "_", part or "_shared")[:80]


class CharacterStore:
    def __init__(self, root: str | None = None):
        self.root = root or _data_root()

    def _path(self, owner: str | None, character: str) -> str:
        if not CHAR_RE.match(character or ""):
            raise ValueError("Character ids are lowercase letters, numbers and dashes")
        return os.path.join(self.root, _safe(owner or ""), f"{character}.json")

    def load(self, owner: str | None, character: str) -> dict:
        path = self._path(owner, character)
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                data.setdefault("character", character)
                return data
        except (OSError, ValueError):
            pass
        return {"character": character, "profile": {}, "devices": {}, "metrics": {}, "apps": []}

    def _save(self, owner: str | None, character: str, data: dict) -> None:
        path = self._path(owner, character)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            from core.atomic_io import atomic_write_json
            atomic_write_json(path, data, indent=2)
        except ImportError:  # pragma: no cover
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)

    def update_profile(self, owner: str | None, character: str, fields: dict) -> dict:
        with _lock:
            data = self.load(owner, character)
            profile = dict(data.get("profile") or {})
            for key, value in fields.items():
                if value is None:
                    profile.pop(key, None)
                else:
                    profile[key] = value
            data["profile"] = profile
            self._save(owner, character, data)
            return data

    def apply_telemetry(self, owner: str | None, character: str, payload: dict) -> dict:
        """Merge a device report. Latest value wins; nothing is hard-coded."""
        now = time.time()
        with _lock:
            data = self.load(owner, character)
            devices = dict(data.get("devices") or {})
            for dev in payload.get("devices") or []:
                current = dict(devices.get(dev["id"]) or {})
                current.update({k: v for k, v in dev.items() if v is not None})
                current["updated_at"] = now
                devices[dev["id"]] = current
            data["devices"] = devices

            metrics = dict(data.get("metrics") or {})
            for key, metric in (payload.get("metrics") or {}).items():
                metrics[key] = {**metric, "updated_at": now}
            data["metrics"] = metrics

            if payload.get("apps") is not None:
                # Apps are reported per device: replace that device's list only.
                reported = {a.get("device") or "" for a in payload["apps"]}
                kept = [a for a in data.get("apps") or [] if (a.get("device") or "") not in reported]
                data["apps"] = kept + list(payload["apps"])

            if payload.get("location"):
                data["location"] = {**payload["location"], "updated_at": now}
            data["updated_at"] = now
            self._save(owner, character, data)
            return data
