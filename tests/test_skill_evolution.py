from services.memory.skill_evolution import SkillEvolutionError, SkillEvolutionManager
from services.memory.skills import SkillsManager


def _manager(tmp_path):
    return SkillEvolutionManager(SkillsManager(str(tmp_path)))


def _add(sm, name, *, owner="tom", procedure=None):
    return sm.add_skill(
        name=name,
        description=f"{name} skill",
        category="test",
        when_to_use=f"Use {name}",
        procedure=procedure or [f"perform {name}"],
        status="published",
        source="user",
        owner=owner,
    )


def test_compose_creates_lineage_and_inherits_metadata(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm, "network-analysis", procedure=["inspect hosts"])
    _add(sm, "target-context", procedure=["identify authorised target"])

    ev = SkillEvolutionManager(sm)
    result = ev.compose(
        "authorised-network-recon",
        ["network-analysis", "target-context"],
        owner="tom",
        description="Combine target context and network analysis.",
        procedure=["identify target", "inspect hosts"],
    )

    assert result["name"] == "authorised-network-recon"
    assert result["source"] == "evolved"
    assert result["lineage"]["parents"] == ["network-analysis", "target-context"]
    assert result["procedure"] == ["identify target", "inspect hosts"]

    lineage = ev.lineage("authorised-network-recon", owner="tom")
    assert {p["name"] for p in lineage["parents_tree"]} == {"network-analysis", "target-context"}


def test_compose_rejects_cycles_and_missing_parents(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm, "one")
    _add(sm, "two")
    ev = SkillEvolutionManager(sm)

    with __import__("pytest").raises(SkillEvolutionError):
        ev.compose("bad", ["one"], owner="tom")

    ev.compose("combined", ["one", "two"], owner="tom")
    with __import__("pytest").raises(SkillEvolutionError):
        ev.compose("one", ["combined", "two"], owner="tom")


def test_extend_bumps_patch_version_and_preserves_lineage(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm, "base")
    ev = _manager(tmp_path)
    ev._set_record("base", "tom", {"parents": ["one"], "kind": "composition", "version": "1.0.0"})

    result = ev.extend(
        "base",
        owner="tom",
        procedure_append=["verify result"],
        tags_add=["verification"],
    )

    assert result["version"] == "1.0.1"
    assert result["procedure"][-1] == "verify result"
    assert "verification" in result["tags"]
    assert result["lineage"]["parents"] == ["one"]


def test_retire_hides_without_deleting_and_promote_reactivates(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm, "capability", owner="tom")
    ev = _manager(tmp_path)

    retired = ev.retire("capability", owner="tom", reason="superseded")
    assert retired["status"] == "retired"
    assert retired["lineage"]["retired"] is True
    assert sm.load(owner="tom")[0]["name"] == "capability"

    promoted = ev.promote("capability", owner="tom", confidence=0.95)
    assert promoted["status"] == "published"
    assert promoted["confidence"] == 0.95
    assert promoted["lineage"]["retired"] is False


def test_lineage_is_owner_scoped(tmp_path):
    sm = SkillsManager(str(tmp_path))
    _add(sm, "shared", owner="tom")
    _add(sm, "shared", owner="alice")
    ev = _manager(tmp_path)
    ev._set_record("shared", "tom", {"parents": ["tom-parent"]})
    ev._set_record("shared", "alice", {"parents": ["alice-parent"]})

    assert ev.lineage("shared", owner="tom")["parents"] == ["tom-parent"]
    assert ev.lineage("shared", owner="alice")["parents"] == ["alice-parent"]
