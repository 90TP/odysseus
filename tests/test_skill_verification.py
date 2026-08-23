from services.memory.skills import SkillsManager
from services.memory.skill_verification import SkillVerificationError, SkillVerificationManager


def _add(sm, name="runner", owner="tom"):
    return sm.add_skill(
        name=name,
        description=f"{name} skill",
        category="test",
        when_to_use=f"Use {name}",
        procedure=["check prerequisites", f"perform {name}"],
        status="published",
        source="user",
        owner=owner,
    )


def _rows(values):
    return [{"success": value} for value in values]


def _proposal(owner="tom"):
    return {
        "status": "proposed",
        "skill": "runner",
        "owner": owner,
        "base_version": "1.0.0",
    }


def test_verified_when_candidate_improves_enough(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm)
    result = SkillVerificationManager(sm).verify(
        _proposal(),
        baseline=_rows([True, False, False, False]),
        candidate=_rows([True, True, True, False]),
        owner="tom",
        minimum_improvement=0.25,
    )
    assert result["verdict"] == "verified"
    assert result["promotion_eligible"] is True
    assert result["improvement"] == 0.5


def test_rejected_when_improvement_is_below_threshold(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm)
    result = SkillVerificationManager(sm).verify(
        _proposal(),
        baseline=_rows([True, True, False]),
        candidate=_rows([True, True, False]),
        owner="tom",
        minimum_improvement=0.1,
    )
    assert result["verdict"] == "not_verified"
    assert result["promotion_eligible"] is False


def test_requires_more_runs_when_samples_are_small(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm)
    result = SkillVerificationManager(sm).verify(
        _proposal(),
        baseline=_rows([False, False]),
        candidate=_rows([True, True]),
        owner="tom",
        min_samples=3,
    )
    assert result["status"] == "insufficient_evidence"
    assert result["requires_more_runs"] is True


def test_verification_is_owner_scoped(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm, owner="tom")
    _add(sm, owner="alice")
    manager = SkillVerificationManager(sm)
    result = manager.verify(
        _proposal(owner="tom"),
        baseline=_rows([False, False, False]),
        candidate=_rows([True, True, True]),
        owner="tom",
    )
    assert result["owner"] == "tom"

    try:
        manager.verify(
            _proposal(owner="alice"),
            baseline=_rows([False, False, False]),
            candidate=_rows([True, True, True]),
            owner="nobody",
        )
    except SkillVerificationError as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("expected SkillVerificationError")


def test_invalid_threshold_is_rejected(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm)
    try:
        SkillVerificationManager(sm).verify(
            _proposal(), baseline=_rows([True] * 3), candidate=_rows([True] * 3), minimum_improvement=2
        )
    except SkillVerificationError as exc:
        assert "between 0 and 1" in str(exc)
    else:
        raise AssertionError("expected SkillVerificationError")
