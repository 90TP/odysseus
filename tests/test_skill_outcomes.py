from services.memory.skill_outcomes import SkillOutcomeError, SkillOutcomeRecorder
from services.memory.skills import SkillsManager


def _add(sm, name, owner="tom"):
    return sm.add_skill(
        name=name,
        description=f"{name} skill",
        category="test",
        when_to_use=f"Use {name}",
        procedure=[f"perform {name}"],
        status="published",
        source="user",
        owner=owner,
    )


def test_record_and_summary_are_owner_scoped(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm, "shared", "tom")
    _add(sm, "shared", "alice")
    recorder = SkillOutcomeRecorder(sm)

    recorder.record("shared", owner="tom", success=True, version="1.0.0", task="task A")
    recorder.record("shared", owner="tom", success=False, version="1.0.0", task="task B")
    recorder.record("shared", owner="alice", success=True, version="1.0.0", task="task C")

    summary = recorder.summary("shared", owner="tom")
    assert summary["sample_size"] == 2
    assert summary["successes"] == 1
    assert summary["failures"] == 1
    assert summary["success_rate"] == 0.5

    assert len(recorder.recent("shared", owner="alice")) == 1
    assert recorder.recent("shared", owner="alice")[0]["task"] == "task C"


def test_recent_is_newest_first_and_limited(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm, "runner")
    recorder = SkillOutcomeRecorder(sm)
    for i in range(4):
        recorder.record("runner", owner="tom", success=True, task=str(i))

    rows = recorder.recent("runner", owner="tom", limit=2)
    assert [r["task"] for r in rows] == ["3", "2"]


def test_record_rejects_unknown_skill(tmp_path):
    recorder = SkillOutcomeRecorder(SkillsManager(str(tmp_path)))
    try:
        recorder.record("missing", owner="tom", success=True)
    except SkillOutcomeError as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("expected SkillOutcomeError")
