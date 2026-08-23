"""Verification gate for evidence-driven skill improvement proposals.

Verification is intentionally conservative: proposals are evaluated against
execution evidence supplied by the caller and are never published or applied
by this module. A proposal only becomes eligible for promotion when the
verification result shows measurable improvement over a baseline.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional


class SkillVerificationError(ValueError):
    """Raised when verification input is invalid."""


class SkillVerificationManager:
    SCHEMA_VERSION = 1

    def __init__(self, skills_manager):
        self.sm = skills_manager

    def _require(self, name: str, owner: Optional[str]) -> Dict:
        for skill in self.sm.load(owner=owner):
            if skill.get("name") == name:
                return skill
        raise SkillVerificationError(f"Skill {name!r} not found")

    @staticmethod
    def _normalise_outcomes(rows: Iterable[Dict]) -> List[Dict]:
        result = []
        for row in rows or []:
            if not isinstance(row, dict) or "success" not in row:
                continue
            result.append(dict(row))
        return result

    def verify(
        self,
        proposal: Dict,
        *,
        baseline: Iterable[Dict],
        candidate: Iterable[Dict],
        owner: Optional[str] = None,
        min_samples: int = 3,
        minimum_improvement: float = 0.10,
    ) -> Dict:
        """Compare baseline and candidate execution results.

        ``candidate`` represents executions performed with the proposed skill
        change. No files or live skills are modified. The returned verdict is
        ``verified`` only when both samples meet the minimum size and the
        candidate success rate improves by at least ``minimum_improvement``.
        """
        if not isinstance(proposal, dict):
            raise SkillVerificationError("proposal must be a dictionary")
        name = str(proposal.get("skill") or "").strip()
        if not name:
            raise SkillVerificationError("proposal skill is required")
        if proposal.get("status") not in ("proposed", "verification"):
            raise SkillVerificationError("proposal is not eligible for verification")

        self._require(name, owner if owner is not None else proposal.get("owner"))
        try:
            min_samples = max(1, int(min_samples))
            minimum_improvement = float(minimum_improvement)
        except (TypeError, ValueError):
            raise SkillVerificationError("verification thresholds must be numeric")
        if not 0.0 <= minimum_improvement <= 1.0:
            raise SkillVerificationError("minimum_improvement must be between 0 and 1")

        base = self._normalise_outcomes(baseline)
        cand = self._normalise_outcomes(candidate)
        if len(base) < min_samples or len(cand) < min_samples:
            return {
                "schema_version": self.SCHEMA_VERSION,
                "status": "insufficient_evidence",
                "verdict": "not_verified",
                "skill": name,
                "owner": owner if owner is not None else proposal.get("owner"),
                "baseline": self._stats(base),
                "candidate": self._stats(cand),
                "improvement": None,
                "minimum_improvement": minimum_improvement,
                "requires_more_runs": True,
            }

        baseline_stats = self._stats(base)
        candidate_stats = self._stats(cand)
        improvement = candidate_stats["success_rate"] - baseline_stats["success_rate"]
        verified = improvement >= minimum_improvement
        return {
            "schema_version": self.SCHEMA_VERSION,
            "status": "verified" if verified else "rejected",
            "verdict": "verified" if verified else "not_verified",
            "skill": name,
            "owner": owner if owner is not None else proposal.get("owner"),
            "base_version": proposal.get("base_version", ""),
            "baseline": baseline_stats,
            "candidate": candidate_stats,
            "improvement": improvement,
            "minimum_improvement": minimum_improvement,
            "requires_more_runs": False,
            "promotion_eligible": verified,
        }

    @staticmethod
    def _stats(rows: List[Dict]) -> Dict:
        successes = sum(1 for row in rows if bool(row.get("success")))
        failures = len(rows) - successes
        return {
            "sample_size": len(rows),
            "successes": successes,
            "failures": failures,
            "success_rate": successes / len(rows) if rows else None,
        }
