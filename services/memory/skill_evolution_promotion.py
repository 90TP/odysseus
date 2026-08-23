"""Controlled promotion and rollback extensions for skill evolution.

Kept separate from the core lineage implementation so the evolution module
can remain small and backwards-compatible. The package initializer applies
these methods to SkillEvolutionManager at import time.
"""

from __future__ import annotations

import time
from typing import Dict, Optional

from .skill_format import slugify


def _snapshot(skill: Dict) -> Dict:
    fields = (
        "version", "description", "category", "tags", "platforms",
        "requires_toolsets", "fallback_for_toolsets", "status", "confidence",
        "source", "teacher_model", "when_to_use", "procedure", "pitfalls",
        "verification", "body_extra",
    )
    return {k: skill.get(k) for k in fields}


def _next_patch(version: str) -> str:
    try:
        major, minor, patch = [int(x) for x in str(version).split(".")[:3]]
    except (TypeError, ValueError):
        major, minor, patch = 1, 0, 0
    return f"{major}.{minor}.{patch + 1}"


def _history(self, name: str, owner: Optional[str]):
    return self._record(name, owner).get("history") or []


def extend(self, name: str, *, owner: Optional[str] = None, **kwargs):
    """Extend a skill while retaining the exact pre-change snapshot."""
    current = self._require(name, owner)
    record = self._record(name, owner)
    history = list(record.get("history") or [])
    current_version = current.get("version", "1.0.0")
    if not any(h.get("version") == current_version for h in history):
        history.append(_snapshot(current))

    result = self._original_extend(name, owner=owner, **kwargs)
    record = self._record(name, owner)
    record["history"] = history
    self._set_record(name, owner, record)
    return result


def promote(self, name: str, *, owner: Optional[str] = None, confidence: Optional[float] = None):
    """Publish only after an explicit passing audit for this owner."""
    current = self._require(name, owner)
    usage = self.sm._load_usage()
    entry = self.sm._usage_entry(usage, name, owner)
    verdict = str(entry.get("audit_verdict") or "").strip().lower()
    if verdict not in {"pass", "passed", "ok", "verified"}:
        raise self.__class__.evolution_error(
            f"Skill {name!r} cannot be promoted without a passing verification audit"
        )

    if confidence is None:
        confidence = current.get("confidence", 0.7)
    confidence = max(0.0, min(1.0, float(confidence)))
    if not self.sm.update_skill(
        name, {"status": "published", "confidence": confidence}, owner=owner
    ):
        raise self.__class__.evolution_error(f"Failed to promote skill {name!r}")

    rec = self._record(name, owner)
    rec.update({
        "retired": False,
        "promoted_at": time.time(),
        "promoted_from_audit": {
            "verdict": verdict,
            "by_teacher": bool(entry.get("audit_by_teacher")),
            "worker_model": entry.get("audit_worker_model"),
            "teacher_model": entry.get("audit_teacher_model"),
            "audited_at": entry.get("audited_at"),
        },
    })
    self._set_record(name, owner, rec)
    return self._with_lineage(self._require(name, owner), owner)


def rollback(self, name: str, *, owner: Optional[str] = None, version: str):
    """Restore a retained version as a new patch version.

    Rollback never rewrites history. It restores the requested snapshot and
    increments the current version so consumers can see that a rollback was
    itself a new evolution event.
    """
    current = self._require(name, owner)
    record = self._record(name, owner)
    history = list(record.get("history") or [])
    target = next((h for h in history if h.get("version") == version), None)
    if target is None:
        raise self.__class__.evolution_error(
            f"No retained history for skill {name!r} at version {version!r}"
        )

    updates = {k: target[k] for k in (
        "description", "category", "tags", "platforms", "requires_toolsets",
        "fallback_for_toolsets", "status", "confidence", "source",
        "teacher_model", "when_to_use", "procedure", "pitfalls",
        "verification", "body_extra",
    ) if k in target}
    from_version = current.get("version", "1.0.0")
    updates["version"] = _next_patch(from_version)
    if not self.sm.update_skill(name, updates, owner=owner):
        raise self.__class__.evolution_error(f"Failed to rollback skill {name!r}")

    record["rollback"] = {
        "from_version": from_version,
        "to_version": version,
        "at": time.time(),
    }
    record["history"] = history
    self._set_record(name, owner, record)
    return self._with_lineage(self._require(name, owner), owner)


def apply(manager_cls):
    """Install the controlled evolution methods onto the existing manager."""
    if getattr(manager_cls, "_promotion_layer_applied", False):
        return manager_cls
    manager_cls._original_extend = manager_cls.extend
    manager_cls.extend = extend
    manager_cls.promote = promote
    manager_cls.rollback = rollback

    # Avoid importing the exception in every call while preserving the public
    # class's existing error type and backwards-compatible constructor.
    from .skill_evolution import SkillEvolutionError
    manager_cls.evolution_error = staticmethod(SkillEvolutionError)
    manager_cls._promotion_layer_applied = True
    return manager_cls
