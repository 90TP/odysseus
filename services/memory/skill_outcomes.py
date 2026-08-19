"""Execution outcome history for the skill-evolution lifecycle.

This is deliberately separate from SKILL.md and the lineage store.  A skill
execution can be recorded cheaply after a run, giving the later proposal and
promotion stages evidence without rewriting the skill itself.
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, List, Optional


class SkillOutcomeError(ValueError):
    """Raised when an execution outcome is invalid."""


class SkillOutcomeRecorder:
    SCHEMA_VERSION = 1

    def __init__(self, skills_manager):
        self.sm = skills_manager
        self.path = os.path.join(self.sm.skills_root, "_outcomes.json")

    def _load(self) -> Dict:
        if not os.path.exists(self.path):
            return {"schema_version": self.SCHEMA_VERSION, "outcomes": []}
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError
            outcomes = data.get("outcomes")
            if not isinstance(outcomes, list):
                outcomes = []
            return {
                "schema_version": data.get("schema_version", self.SCHEMA_VERSION),
                "outcomes": outcomes,
            }
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {"schema_version": self.SCHEMA_VERSION, "outcomes": []}

    def _save(self, data: Dict) -> None:
        from core.atomic_io import atomic_write_json
        atomic_write_json(self.path, data, indent=2)

    def record(
        self,
        skill: str,
        *,
        owner: Optional[str] = None,
        success: bool,
        version: str = "",
        task: str = "",
        notes: str = "",
        procedure_used: Optional[List[str]] = None,
        duration_seconds: Optional[float] = None,
        session_id: str = "",
    ) -> Dict:
        name = str(skill or "").strip()
        if not name:
            raise SkillOutcomeError("skill is required")
        if not any(s.get("name") == name for s in self.sm.load(owner=owner)):
            raise SkillOutcomeError(f"Skill {name!r} not found")
        if duration_seconds is not None:
            try:
                duration_seconds = max(0.0, float(duration_seconds))
            except (TypeError, ValueError):
                raise SkillOutcomeError("duration_seconds must be numeric")

        outcome = {
            "skill": name,
            "owner": owner,
            "success": bool(success),
            "version": str(version or ""),
            "task": str(task or ""),
            "notes": str(notes or ""),
            "procedure_used": [str(x) for x in (procedure_used or [])],
            "duration_seconds": duration_seconds,
            "session_id": str(session_id or ""),
            "recorded_at": time.time(),
        }
        data = self._load()
        data["outcomes"].append(outcome)
        self._save(data)
        return dict(outcome)

    def recent(
        self,
        skill: Optional[str] = None,
        *,
        owner: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        try:
            limit = max(1, min(200, int(limit)))
        except (TypeError, ValueError):
            limit = 20
        rows = self._load()["outcomes"]
        rows = [
            r for r in rows
            if isinstance(r, dict)
            and r.get("owner") == owner
            and (skill is None or r.get("skill") == skill)
        ]
        return [dict(r) for r in rows[-limit:]][::-1]

    def summary(self, skill: str, *, owner: Optional[str] = None, limit: int = 50) -> Dict:
        rows = self.recent(skill, owner=owner, limit=limit)
        successes = sum(1 for r in rows if r.get("success"))
        failures = len(rows) - successes
        return {
            "skill": skill,
            "owner": owner,
            "sample_size": len(rows),
            "successes": successes,
            "failures": failures,
            "success_rate": (successes / len(rows)) if rows else None,
            "recent": rows,
        }
