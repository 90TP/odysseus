from services.memory.skill_evolution import SkillEvolutionError, SkillEvolutionManager
from services.memory.skills import SkillsManager


def _manager(tmp_path):
    return SkillEvolutionManager(SkillsManager(str(tmp_path)))


def _add(sm, name, *, owner="tom", procedure=None, confidence=0.8):
    return sm.add_skill(
        name=name,
        description=f"{name} skill",
        category="test",
        when_to_use=f"Use {name}",
        procedure=procedure or [f"perform {name}"],
        status="draft",
        source="user",
        owner=owner,
        confidence=confidence,
    )


def test_promote_requires_passed_audit(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm, "candidate")
    ev = _manager(tmp_path)

    try:
        ev.promote("candidate", owner="tom")
    except SkillEvolutionError as exc:
        assert "verification" in str(exc).lower()
    else:
        raise AssertionError("unverified skill was promoted")

    sm.set_audit("candidate", "fail", owner="tom")
    try:
        ev.promote("candidate", owner="tom")
    except SkillEvolutionError as exc:
        assert "verification" in str(exc).lower()
    else:
        raise AssertionError("failed skill was promoted")


def test_promote_records_verification_and_owner_scoped_metadata(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm, "candidate", owner="tom")
    alice = _add(sm, "candidate", owner="alice")  # stored as candidate-2
    sm.set_audit("candidate", "pass", by_teacher=True, worker_model="worker", teacher_model="teacher", owner="tom")
    ev = _manager(tmp_path)

    promoted = ev.promote("candidate", owner="tom")
    assert promoted["status"] == "published"
    assert promoted["lineage"]["promoted_from_audit"]["verdict"] == "pass"
    assert promoted["lineage"]["promoted_from_audit"]["by_teacher"] is True
    assert ev.metadata("candidate", owner="tom")["promoted_from_audit"]["verdict"] == "pass"

    assert ev.metadata(alice["name"], owner="alice") == {}
    try:
        ev.metadata("candidate", owner="alice")
    except SkillEvolutionError:
        pass
    else:
        raise AssertionError("alice could read tom's evolution metadata")


def test_extend_preserves_previous_version_for_rollback(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm, "candidate", procedure=["one"])
    ev = _manager(tmp_path)

    first = ev.extend("candidate", owner="tom", procedure_append=["two"])
    assert first["version"] == "1.0.1"
    assert first["procedure"] == ["one", "two"]

    history = ev.metadata("candidate", owner="tom")["history"]
    assert history[0]["version"] == "1.0.0"
    assert history[0]["procedure"] == ["one"]

    rolled = ev.rollback("candidate", owner="tom", version="1.0.0")
    assert rolled["version"] == "1.0.2"
    assert rolled["procedure"] == ["one"]
    assert rolled["lineage"]["rollback"]["from_version"] == "1.0.1"
    assert rolled["lineage"]["rollback"]["to_version"] == "1.0.0"


def test_rollback_is_owner_scoped(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm, "candidate", owner="tom", procedure=["tom-one"])
    alice = _add(sm, "candidate", owner="alice", procedure=["alice-one"])  # candidate-2
    ev = _manager(tmp_path)
    ev.extend("candidate", owner="tom", procedure_append=["tom-two"])

    # alice can't roll back tom's skill...
    try:
        ev.rollback("candidate", owner="alice", version="1.0.0")
    except SkillEvolutionError:
        pass
    else:
        raise AssertionError("cross-owner rollback succeeded")

    # ...and tom's history doesn't leak into her own skill.
    try:
        ev.rollback(alice["name"], owner="alice", version="1.0.0")
    except SkillEvolutionError as exc:
        assert "history" in str(exc).lower()
    else:
        raise AssertionError("rollback used another owner's history")
