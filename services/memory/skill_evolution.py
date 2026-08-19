"""Skill composition and evolution support.

The normal skill registry remains the source of truth for executable
SKILL.md procedures.  This module adds a small, disk-backed lineage layer so
new capabilities can be derived from existing skills without inventing a
second skill format.

Evolution metadata lives in ``data/skills/_evolution.json``.  Keeping lineage
out of SKILL.md preserves compatibility with existing skills and the Agent
Skills format while allowing composition, extension, retirement and ancestry
queries.
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, Iterable, List, Optional

from .skill_format import slugify


class SkillEvolutionError(ValueError):
    """Raised when a requested evolution operation is invalid."""


class SkillEvolutionManager:
    """Manage lineage and controlled evolution of SkillsManager skills."""

    SCHEMA_VERSION = 1

    def __init__(self, skills_manager):
        self.sm = skills_manager
        self.path = os.path.join(self.sm.skills_root, "_evolution.json")

    def _load(self) -> Dict:
        if not os.path.exists(self.path):
            return {"schema_version": self.SCHEMA_VERSION, "skills": {}}
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError
            data.setdefault("schema_version", self.SCHEMA_VERSION)
            data.setdefault("skills", {})
            if not isinstance(data["skills"], dict):
                data["skills"] = {}
            return data
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {"schema_version": self.SCHEMA_VERSION, "skills": {}}

    def _save(self, data: Dict) -> None:
        from core.atomic_io import atomic_write_json
        atomic_write_json(self.path, data, indent=2)

    @staticmethod
    def _key(name: str, owner: Optional[str]) -> str:
        return f"{owner or ''}::{slugify(name)}"

    def _record(self, name: str, owner: Optional[str]) -> Dict:
        data = self._load()
        return data["skills"].get(self._key(name, owner), {})

    def _set_record(self, name: str, owner: Optional[str], record: Dict) -> None:
        data = self._load()
        data["skills"][self._key(name, owner)] = record
        self._save(data)

    def _find(self, name: str, owner: Optional[str]) -> Optional[Dict]:
        for skill in self.sm.load(owner=owner):
            if skill.get("name") == name:
                return skill
        return None

    def _require(self, name: str, owner: Optional[str]) -> Dict:
        skill = self._find(name, owner)
        if not skill:
            raise SkillEvolutionError(f"Skill {name!r} not found")
        return skill

    def _parents_of(self, name: str, owner: Optional[str]) -> List[str]:
        rec = self._record(name, owner)
        return list(rec.get("parents") or [])

    def _would_cycle(self, child: str, parents: Iterable[str], owner: Optional[str]) -> bool:
        """Return True if adding parents would make child an ancestor of itself."""
        target = slugify(child)
        todo = [slugify(p) for p in parents]
        seen = set()
        while todo:
            current = todo.pop()
            if current == target:
                return True
            if current in seen:
                continue
            seen.add(current)
            todo.extend(self._parents_of(current, owner))
        return False

    @staticmethod
    def _next_patch(version: str) -> str:
        try:
            major, minor, patch = [int(x) for x in str(version).split(".")[:3]]
        except (TypeError, ValueError):
            major, minor, patch = 1, 0, 0
        return f"{major}.{minor}.{patch + 1}"

    def _merge_unique(self, *lists: Iterable[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        for values in lists:
            for value in values or []:
                value = str(value).strip()
                if value and value not in seen:
                    seen.add(value)
                    out.append(value)
        return out

    def _combined(self, parents: List[Dict]) -> Dict:
        return {
            "tags": self._merge_unique(*(p.get("tags", []) for p in parents)),
            "platforms": self._merge_unique(*(p.get("platforms", []) for p in parents)),
            "requires_toolsets": self._merge_unique(*(p.get("requires_toolsets", []) for p in parents)),
            "fallback_for_toolsets": self._merge_unique(*(p.get("fallback_for_toolsets", []) for p in parents)),
            "pitfalls": self._merge_unique(*(p.get("pitfalls", []) for p in parents)),
            "verification": self._merge_unique(*(p.get("verification", []) for p in parents)),
        }

    def compose(
        self,
        name: str,
        parents: List[str],
        *,
        owner: Optional[str] = None,
        description: str = "",
        when_to_use: str = "",
        procedure: Optional[List[str]] = None,
        category: str = "composed",
        tags: Optional[List[str]] = None,
        status: str = "draft",
        confidence: float = 0.7,
    ) -> Dict:
        """Create a new skill by composing multiple existing skills."""
        child = slugify(name)
        parent_names = list(dict.fromkeys(slugify(p) for p in parents if p))
        if len(parent_names) < 2:
            raise SkillEvolutionError("compose requires at least two parent skills")
        if child in parent_names:
            raise SkillEvolutionError("a skill cannot compose itself")
        if self._find(child, owner):
            raise SkillEvolutionError(f"Skill {child!r} already exists")
        if self._would_cycle(child, parent_names, owner):
            raise SkillEvolutionError("composition would create a circular skill dependency")

        parent_skills = [self._require(p, owner) for p in parent_names]
        inherited = self._combined(parent_skills)
        if procedure is None:
            procedure = []
            for parent in parent_skills:
                procedure.extend(parent.get("procedure") or parent.get("steps") or [])

        entry = self.sm.add_skill(
            name=child,
            description=description or f"Composed capability from {', '.join(parent_names)}.",
            category=category,
            tags=self._merge_unique(inherited["tags"], tags or []),
            platforms=inherited["platforms"],
            requires_toolsets=inherited["requires_toolsets"],
            fallback_for_toolsets=inherited["fallback_for_toolsets"],
            when_to_use=when_to_use or "Use when the combined capabilities of the parent skills are required.",
            procedure=procedure,
            pitfalls=inherited["pitfalls"],
            verification=inherited["verification"],
            status=status,
            confidence=confidence,
            source="evolved",
            owner=owner,
        )
        if entry.get("_deduped"):
            raise SkillEvolutionError(f"A near-identical skill already exists: {entry['name']}")
        self._set_record(child, owner, {
            "parents": parent_names,
            "kind": "composition",
            "version": entry.get("version", "1.0.0"),
            "created_at": time.time(),
            "retired": False,
        })
        return self._with_lineage(entry, owner)

    def extend(
        self,
        name: str,
        *,
        owner: Optional[str] = None,
        procedure_append: Optional[List[str]] = None,
        procedure_prepend: Optional[List[str]] = None,
        pitfalls_append: Optional[List[str]] = None,
        verification_append: Optional[List[str]] = None,
        tags_add: Optional[List[str]] = None,
        description: Optional[str] = None,
        when_to_use: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> Dict:
        """Evolve an existing skill in place and record a new patch version."""
        current = self._require(name, owner)
        record = self._record(name, owner)
        updates: Dict = {"version": self._next_patch(current.get("version", "1.0.0"))}
        proc = list(current.get("procedure") or [])
        proc = list(procedure_prepend or []) + proc + list(procedure_append or [])
        if procedure_prepend or procedure_append:
            updates["procedure"] = proc
        if pitfalls_append:
            updates["pitfalls"] = self._merge_unique(current.get("pitfalls", []), pitfalls_append)
        if verification_append:
            updates["verification"] = self._merge_unique(current.get("verification", []), verification_append)
        if tags_add:
            updates["tags"] = self._merge_unique(current.get("tags", []), tags_add)
        if description is not None:
            updates["description"] = description
        if when_to_use is not None:
            updates["when_to_use"] = when_to_use
        if confidence is not None:
            updates["confidence"] = max(0.0, min(1.0, float(confidence)))
        if not self.sm.update_skill(name, updates, owner=owner):
            raise SkillEvolutionError(f"Failed to update skill {name!r}")
        record.update({"version": updates["version"], "last_evolved_at": time.time()})
        record.setdefault("parents", [])
        record["kind"] = record.get("kind", "evolved")
        self._set_record(name, owner, record)
        return self._with_lineage(self._require(name, owner), owner)

    def lineage(self, name: str, *, owner: Optional[str] = None, recursive: bool = True) -> Dict:
        """Return direct or recursive ancestry for a skill."""
        self._require(name, owner)
        seen = set()

        def walk(current: str) -> Dict:
            key = current
            if key in seen:
                return {"name": current, "cycle": True}
            seen.add(key)
            rec = self._record(current, owner)
            node = {"name": current, **rec}
            if recursive:
                node["parents_tree"] = [walk(p) for p in rec.get("parents") or []]
            return node

        return walk(name)

    def retire(self, name: str, *, owner: Optional[str] = None, reason: str = "") -> Dict:
        """Hide a skill from normal discovery without deleting its lineage."""
        current = self._require(name, owner)
        if not self.sm.update_skill(name, {"status": "retired"}, owner=owner):
            raise SkillEvolutionError(f"Failed to retire skill {name!r}")
        rec = self._record(name, owner)
        rec.update({"retired": True, "retired_at": time.time(), "retire_reason": str(reason or "")})
        self._set_record(name, owner, rec)
        return self._with_lineage(self._require(name, owner), owner)

    def promote(self, name: str, *, owner: Optional[str] = None, confidence: Optional[float] = None) -> Dict:
        """Publish a successfully verified evolved skill."""
        current = self._require(name, owner)
        if confidence is None:
            confidence = current.get("confidence", 0.7)
        confidence = max(0.0, min(1.0, float(confidence)))
        if not self.sm.update_skill(name, {"status": "published", "confidence": confidence}, owner=owner):
            raise SkillEvolutionError(f"Failed to promote skill {name!r}")
        rec = self._record(name, owner)
        rec.update({"retired": False, "promoted_at": time.time()})
        self._set_record(name, owner, rec)
        return self._with_lineage(self._require(name, owner), owner)

    def _with_lineage(self, skill: Dict, owner: Optional[str]) -> Dict:
        out = dict(skill)
        rec = self._record(skill.get("name", ""), owner)
        out["lineage"] = rec
        return out

    def metadata(self, name: Optional[str] = None, *, owner: Optional[str] = None) -> Dict:
        data = self._load()["skills"]
        if name is not None:
            self._require(name, owner)
            return dict(data.get(self._key(name, owner), {}))
        prefix = f"{owner or ''}::"
        return {k: v for k, v in data.items() if k.startswith(prefix)}
