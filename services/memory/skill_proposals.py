"""Evidence-driven improvement proposals for the skill-evolution lifecycle.

This module deliberately stops at proposal generation. It analyses recorded
execution outcomes and returns a structured candidate change; it never edits
or publishes the live skill. Verification and promotion are separate gates.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .skill_evolution import SkillEvolutionError
from .skill_outcomes import SkillOutcomeRecorder


class SkillProposalError(ValueError):
    """Raised when proposal generation arguments are invalid."""


class SkillProposalManager:
    """Generate deterministic improvement proposals from execution evidence."""

    def __init__(self, skills_manager, outcomes: Optional[SkillOutcomeRecorder] = None):
        self.sm = skills_manager
        self.outcomes = outcomes or SkillOutcomeRecorder(skills_manager)

    def _require(self, name: str, owner: Optional[str]) -> Dict:
        for skill in self.sm.load(owner=owner):
            if skill.get("name") == name:
                return skill
        raise SkillProposalError(f"Skill {name!r} not found")

    def propose(
        self,
        skill: str,
        *,
        owner: Optional[str] = None,
        limit: int = 20,
        min_samples: int = 3,
        failure_rate_threshold: float = 0.4,
    ) -> Optional[Dict]:
        """Return an improvement proposal when outcome evidence warrants one.

        The proposal is based only on persisted outcomes.  No skill mutation is
        performed, making this safe to call after every execution.
        """
        name = str(skill or "").strip()
        if not name:
            raise SkillProposalError("skill is required")
        try:
            min_samples = max(1, int(min_samples))
            limit = max(1, min(200, int(limit)))
            threshold = float(failure_rate_threshold)
        except (TypeError, ValueError):
            raise SkillProposalError("proposal thresholds must be numeric")
        if not 0.0 <= threshold <= 1.0:
            raise SkillProposalError("failure_rate_threshold must be between 0 and 1")

        current = self._require(name, owner)
        summary = self.outcomes.summary(name, owner=owner, limit=limit)
        sample_size = summary["sample_size"]
        if sample_size < min_samples:
            return None
        failure_rate = 1.0 - float(summary["success_rate"] or 0.0)
        if failure_rate < threshold:
            return None

        failures = [row for row in summary["recent"] if not row.get("success")]
        failure_notes: List[str] = []
        tasks: List[str] = []
        for row in failures:
            note = str(row.get("notes") or "").strip()
            task = str(row.get("task") or "").strip()
            if note and note not in failure_notes:
                failure_notes.append(note)
            if task and task not in tasks:
                tasks.append(task)

        current_procedure = list(current.get("procedure") or current.get("steps") or [])
        evidence = {
            "sample_size": sample_size,
            "successes": summary["successes"],
            "failures": summary["failures"],
            "success_rate": summary["success_rate"],
            "failure_rate": failure_rate,
            "failure_notes": failure_notes[:10],
            "failed_tasks": tasks[:10],
        }
        confidence = min(0.95, 0.5 + min(0.35, sample_size / 40.0) + min(0.1, failure_rate / 10.0))
        return {
            "kind": "skill_improvement",
            "status": "proposed",
            "skill": name,
            "owner": owner,
            "base_version": str(current.get("version") or "1.0.0"),
            "title": f"Improve {name} after repeated execution failures",
            "reason": (
                f"{summary['failures']} of the last {sample_size} executions failed "
                f"({failure_rate:.0%} failure rate), exceeding the {threshold:.0%} threshold."
            ),
            "evidence": evidence,
            "current_procedure": current_procedure,
            "proposed_change": {
                "type": "review_and_extend",
                "instruction": (
                    "Review the recorded failure notes and failed tasks, then add a "
                    "targeted preventative step to the procedure. Do not remove existing "
                    "steps solely because of this proposal."
                ),
                "failure_notes": failure_notes[:10],
            },
            "confidence": round(confidence, 3),
            "requires_verification": True,
            "created_from_outcomes": [
                {"recorded_at": row.get("recorded_at"), "session_id": row.get("session_id", "")}
                for row in failures
            ],
        }

    def propose_all(
        self,
        *,
        owner: Optional[str] = None,
        limit: int = 20,
        min_samples: int = 3,
        failure_rate_threshold: float = 0.4,
    ) -> List[Dict]:
        """Generate proposals for every owner-visible skill with enough evidence."""
        proposals: List[Dict] = []
        for skill in self.sm.load(owner=owner):
            name = skill.get("name")
            if not name:
                continue
            proposal = self.propose(
                name,
                owner=owner,
                limit=limit,
                min_samples=min_samples,
                failure_rate_threshold=failure_rate_threshold,
            )
            if proposal:
                proposals.append(proposal)
        return proposals
