from services.memory.skill_outcomes import SkillOutcomeRecorder
from services.memory.skill_proposals import SkillProposalError, SkillProposalManager
from services.memory.skills import SkillsManager


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


def test_propose_after_repeated_failures_without_mutating_skill(tmp_path):
    sm = SkillsManager(str(tmp_path))
    original = _add(sm)
    recorder = SkillOutcomeRecorder(sm)
    recorder.record("runner", owner="tom", success=False, version="1.0.0", task="deploy", notes="container was missing")
    recorder.record("runner", owner="tom", success=False, version="1.0.0", task="deploy", notes="container was missing")
    recorder.record("runner", owner="tom", success=True, version="1.0.0", task="deploy")

    proposal = SkillProposalManager(sm, recorder).propose("runner", owner="tom")

    assert proposal["status"] == "proposed"
    assert proposal["base_version"] == "1.0.0"
    assert proposal["evidence"]["failures"] == 2
    assert proposal["evidence"]["failure_rate"] == 2 / 3
    assert "container was missing" in proposal["proposed_change"]["failure_notes"]
    assert proposal["requires_verification"] is True
    current = sm.load(owner="tom")[0]
    assert current["procedure"] == original["procedure"]


def test_proposal_requires_enough_evidence(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm)
    recorder = SkillOutcomeRecorder(sm)
    recorder.record("runner", owner="tom", success=False, notes="bad")

    assert SkillProposalManager(sm, recorder).propose("runner", owner="tom") is None


def test_proposal_is_owner_scoped(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm, owner="tom")
    _add(sm, owner="alice")
    recorder = SkillOutcomeRecorder(sm)
    for _ in range(3):
        recorder.record("runner", owner="tom", success=False, notes="tom failure")
    for _ in range(3):
        recorder.record("runner", owner="alice", success=True)

    manager = SkillProposalManager(sm, recorder)
    assert manager.propose("runner", owner="tom") is not None
    assert manager.propose("runner", owner="alice") is None


def test_invalid_threshold_is_rejected(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm)
    try:
        SkillProposalManager(sm).propose("runner", owner="tom", failure_rate_threshold=2)
    except SkillProposalError as exc:
        assert "between 0 and 1" in str(exc)
    else:
        raise AssertionError("expected SkillProposalError")
