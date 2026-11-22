"""Aerith self-maintenance: log parsing, incidents, drafting, approval gate."""

import asyncio
import json
import os
import subprocess
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from companion.maintenance import store as st
from companion.maintenance.builder import BuildError, ProposalBuilder
from companion.maintenance.config import MaintenanceConfig
from companion.maintenance.features import parse_options, unseen_research
from companion.maintenance.log_watch import ErrorEvent, LogTailer, fingerprint, parse_log_text
from companion.maintenance.monitor import AerithMaintainer

LOG = """2026-11-22 10:00:00,001 - routes.chat - INFO - fine
2026-11-22 10:00:01,002 - routes.chat - ERROR - Failed for session 1234
Traceback (most recent call last):
  File "/app/routes/chat.py", line 10, in handler
    x = d["k"]
KeyError: 'k'
2026-11-22 10:00:02,003 - companion.maintenance.builder - ERROR - fixer broke
2026-11-22 10:00:03,004 - src.llm - WARNING - slow
"""


# -- log parsing -----------------------------------------------------------

def test_parse_log_extracts_errors_with_tracebacks_and_skips_own_logger():
    events = parse_log_text(LOG)
    assert len(events) == 1
    ev = events[0]
    assert ev.source == "routes.chat" and ev.level == "ERROR"
    assert "KeyError" in ev.detail


def test_fingerprint_ignores_volatile_numbers():
    a = fingerprint("server", "x", "Failed for session 1234")
    b = fingerprint("server", "x", "Failed for session 98")
    c = fingerprint("android", "x", "Failed for session 98")
    assert a == b and a != c


def test_fingerprint_uses_stack_frames_when_present():
    d1 = 'File "/a/b.py", line 3, in f\nValueError: bad 1'
    d2 = 'File "/a/b.py", line 9, in f\nValueError: bad 2'
    assert fingerprint("server", "s", "m1", d1) == fingerprint("server", "s", "other", d2)


def test_tailer_starts_at_end_then_reads_new_and_handles_rotation(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("old line\n")
    t = LogTailer(str(log))
    assert t.read_new() == ""                     # history is not replayed
    with open(log, "a") as fh:
        fh.write("new line\npartial")
    assert t.read_new() == "new line\n"           # only whole lines
    log.write_text("rotated\n")                   # smaller file => rotation
    assert t.read_new() == "rotated\n"


# -- store ------------------------------------------------------------------

def _event(msg="boom", platform="server"):
    return ErrorEvent(platform=platform, source="s", level="ERROR", message=msg)


def test_store_dedupes_and_reopens_resolved(tmp_path):
    s = st.MaintenanceStore(str(tmp_path))
    inc, new = s.record_event(_event())
    assert new and inc["count"] == 1
    inc, new = s.record_event(_event())
    assert not new and inc["count"] == 2
    s.update_incident(inc["id"], status=st.RESOLVED)
    inc, new = s.record_event(_event())
    assert new and inc["status"] == st.OPEN and inc["reopened"] == 1


# -- features ---------------------------------------------------------------

def test_parse_options_tolerates_prose_and_bad_items():
    raw = 'Sure!\n```json\n[{"title":"Sleep chart","platforms":"android","summary":"s"},{"nope":1}]\n```'
    opts = parse_options(raw)
    assert [o["title"] for o in opts] == ["Sleep chart"]
    assert opts[0]["platforms"] == ["android"]
    assert parse_options("no json here") == []


def test_unseen_research_filters_owner_status_and_seen(tmp_path):
    def put(rid, **d):
        (tmp_path / f"{rid}.json").write_text(json.dumps(d))
    put("a", owner="tom", status="done", query="q", result="report")
    put("b", owner="other", status="done", result="report")
    put("c", owner="tom", status="running", result="report")
    put("d", owner="tom", status="done", result="report")
    found = unseen_research(str(tmp_path), "tom", seen={"d"})
    assert [r["id"] for r in found] == ["a"]


# -- builder (real git) -----------------------------------------------------

def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    (r / "app.py").write_text("x = 1\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "init")
    return r


def _builder(tmp_path, repo, agent, test_cmd="true"):
    cfg = MaintenanceConfig(enabled=True, repo_dir=str(repo), data_dir=str(tmp_path / "data"),
                            test_cmd=test_cmd)
    store = st.MaintenanceStore(cfg.data_dir)
    return ProposalBuilder(cfg, store, agent), store


def _writes(path, text):
    async def agent(prompt, workspace):
        full = os.path.join(workspace, path)
        os.makedirs(os.path.dirname(full) or workspace, exist_ok=True)
        with open(full, "w") as fh:
            fh.write(text)
        return "fixed it"
    return agent


def test_build_then_apply_merges_into_checkout(tmp_path, repo):
    b, s = _builder(tmp_path, repo, _writes("app.py", "x = 2\n"))
    inc, _ = s.record_event(_event())
    prop = s.add_proposal("bugfix", "Fix boom", "boom", incident_id=inc["id"])
    done = asyncio.run(b.build(prop["id"]))
    assert done["status"] == st.READY and done["files"] == ["app.py"]
    assert (repo / "app.py").read_text() == "x = 1\n"      # live checkout untouched
    assert "x = 2" in b.diff(prop["id"])
    assert s.incident(inc["id"])["status"] == st.PROPOSED

    applied = b.apply(prop["id"], approved_by="tom")
    assert applied["status"] == st.APPLIED and applied["approved_by"] == "tom"
    assert (repo / "app.py").read_text() == "x = 2\n"
    assert s.incident(inc["id"])["status"] == st.RESOLVED


def test_build_fails_when_tests_fail(tmp_path, repo):
    b, s = _builder(tmp_path, repo, _writes("app.py", "x = 3\n"), test_cmd="false")
    prop = s.add_proposal("bugfix", "Fix", "x")
    done = asyncio.run(b.build(prop["id"]))
    assert done["status"] == st.FAILED and done["tests_passed"] is False
    with pytest.raises(BuildError):
        b.apply(prop["id"], approved_by="tom")


def test_build_refuses_changes_to_its_own_safeguards(tmp_path, repo):
    b, s = _builder(tmp_path, repo, _writes("companion/maintenance/routes.py", "# no gate\n"))
    prop = s.add_proposal("feature", "Loosen", "x")
    done = asyncio.run(b.build(prop["id"]))
    assert done["status"] == st.FAILED and "protected" in done["error"]


def test_build_with_no_change_fails(tmp_path, repo):
    async def idle(prompt, workspace):
        return "couldn't find it"
    b, s = _builder(tmp_path, repo, idle)
    prop = s.add_proposal("bugfix", "Fix", "x")
    assert asyncio.run(b.build(prop["id"]))["status"] == st.FAILED


def test_reject_deletes_branch(tmp_path, repo):
    b, s = _builder(tmp_path, repo, _writes("app.py", "x = 4\n"))
    prop = s.add_proposal("feature", "Thing", "x")
    done = asyncio.run(b.build(prop["id"]))
    b.reject(prop["id"], rejected_by="tom")
    branches = subprocess.run(["git", "-C", str(repo), "branch"], capture_output=True, text=True).stdout
    assert done["branch"] not in branches
    assert not os.path.exists(done["worktree"])


def test_apply_refuses_dirty_checkout(tmp_path, repo):
    b, s = _builder(tmp_path, repo, _writes("app.py", "x = 5\n"))
    prop = s.add_proposal("bugfix", "Fix", "x")
    asyncio.run(b.build(prop["id"]))
    (repo / "app.py").write_text("local edit\n")
    with pytest.raises(BuildError, match="uncommitted"):
        b.apply(prop["id"], approved_by="tom")


# -- monitor ----------------------------------------------------------------

def _maintainer(tmp_path, **cfg):
    async def agent(prompt, workspace):
        return ""
    config = MaintenanceConfig(enabled=True, data_dir=str(tmp_path / "data"), **cfg)
    return AerithMaintainer(config, agent=agent, llm=lambda p: "[]", research_dir=str(tmp_path / "r"))


def test_autofix_respects_daily_budget(tmp_path):
    m = _maintainer(tmp_path, max_fixes_per_day=1)
    m.ingest([_event("one"), _event("two")])
    assert len(m.store.proposals(kind="bugfix")) == 1
    assert {i["status"] for i in m.store.incidents()} == {st.FIXING, st.OPEN}


def test_autofix_off_only_records(tmp_path):
    m = _maintainer(tmp_path, autofix=False)
    m.ingest([_event()])
    assert m.store.proposals() == [] and len(m.store.incidents()) == 1


def test_research_first_scan_only_marks_existing_as_seen(tmp_path):
    rdir = tmp_path / "r"
    rdir.mkdir()
    (rdir / "old.json").write_text(json.dumps({"owner": "tom", "status": "done", "result": "r"}))
    calls = []
    m = _maintainer(tmp_path, owner="tom")
    m.llm = lambda p: calls.append(p) or '[{"title":"Idea","platforms":["desktop"]}]'
    assert m.scan_research() == [] and calls == []
    (rdir / "new.json").write_text(json.dumps({"owner": "tom", "status": "done", "query": "q", "result": "r"}))
    offered = m.scan_research()
    assert [p["title"] for p in offered] == ["Idea"] and offered[0]["status"] == st.OFFERED
    assert m.scan_research() == []


# -- approval gate ------------------------------------------------------------

def _req(headers=None, **state):
    return SimpleNamespace(state=SimpleNamespace(**state), headers=headers or {},
                           app=SimpleNamespace(state=SimpleNamespace()))


def test_human_admin_gate_refuses_tokens_and_aerith():
    from companion.maintenance.routes import require_human_admin
    from core.middleware import INTERNAL_TOOL_HEADER, INTERNAL_TOOL_USER
    with pytest.raises(HTTPException) as e:
        require_human_admin(_req(api_token=True))
    assert e.value.status_code == 403
    with pytest.raises(HTTPException):
        require_human_admin(_req(current_user=INTERNAL_TOOL_USER))
    with pytest.raises(HTTPException):
        require_human_admin(_req(headers={INTERNAL_TOOL_HEADER: "x"}))


# -- when the usual fix doesn't work -----------------------------------------

from companion.maintenance.builder import SetupError, failing_tests  # noqa: E402
from companion.maintenance.cid import CidPlanner, split_reply  # noqa: E402


def test_failing_tests_parses_pytest_summary():
    out = "....\nFAILED tests/a.py::test_x - assert 1\nERROR tests/b.py - ImportError\n1 failed"
    assert failing_tests(out) == {"tests/a.py::test_x", "tests/b.py"}


FAIL_SAME = "sh -c 'echo FAILED tests/old.py::test_broken; exit 1'"


def test_failures_already_on_base_dont_block_a_fix(tmp_path, repo):
    b, s = _builder(tmp_path, repo, _writes("app.py", "x = 6\n"), test_cmd=FAIL_SAME)
    prop = s.add_proposal("bugfix", "Fix", "x")
    done = asyncio.run(b.build(prop["id"]))
    assert done["status"] == st.READY and "already failing" in done["test_output"]


def test_new_failures_still_block(tmp_path, repo):
    # Fails only when app.py has been changed (i.e. not on the base commit).
    cmd = "sh -c 'grep -q \"x = 1\" app.py || { echo FAILED tests/new.py::test_new; exit 1; }'"
    b, s = _builder(tmp_path, repo, _writes("app.py", "x = 7\n"), test_cmd=cmd)
    prop = s.add_proposal("bugfix", "Fix", "x")
    done = asyncio.run(b.build(prop["id"]))
    assert done["status"] == st.FAILED and done["failure_kind"] == "tests"
    assert "tests/new.py::test_new" in done["test_output"]


def _maintainer_with_repo(tmp_path, repo, agent, **cfg):
    config = MaintenanceConfig(enabled=True, repo_dir=str(repo), data_dir=str(tmp_path / "data"),
                               test_cmd="true", **cfg)
    return AerithMaintainer(config, agent=agent, llm=lambda p: "[]")


async def _drain(m):
    while m._jobs:
        await asyncio.gather(*list(m._jobs))


def test_failed_fix_is_investigated_and_retried_another_way(tmp_path, repo):
    prompts = []

    async def agent(prompt, workspace):
        prompts.append(prompt)
        if len(prompts) == 1:
            return "I couldn't see the problem"          # attempt 1: no change
        with open(os.path.join(workspace, "app.py"), "w") as fh:
            fh.write("x = 8  # guarded\n")
        return "Why the usual fix didn't work: wrong file. Added a guard."

    m = _maintainer_with_repo(tmp_path, repo, agent)

    async def run():
        m.ingest([_event("Crash in handler")])
        await _drain(m)
    asyncio.run(run())

    assert len(prompts) == 2
    assert "THIS IS ATTEMPT" not in prompts[0]
    assert "THIS IS ATTEMPT 2" in prompts[1] and "No change was made" in prompts[1]
    props = m.store.proposals(kind="bugfix")
    by_status = {p["status"]: p for p in props}
    assert set(by_status) == {st.SUPERSEDED, st.READY}
    assert by_status[st.READY]["attempt"] == 2
    assert m.store.incidents()[0]["status"] == st.PROPOSED


def test_retries_stop_at_max_attempts_and_button_starts_new_round(tmp_path, repo):
    calls = []

    async def stuck(prompt, workspace):
        calls.append(prompt)
        return "no idea"

    m = _maintainer_with_repo(tmp_path, repo, stuck, max_attempts=2)

    async def run():
        m.ingest([_event("Stubborn")])
        await _drain(m)
    asyncio.run(run())
    assert len(calls) == 2
    inc = m.store.incidents()[0]
    assert inc["status"] == st.FIX_FAILED

    async def press_button():
        m.queue_fix(inc["id"], force=True)
        await _drain(m)
    asyncio.run(press_button())
    assert len(calls) == 4                                   # a fresh round of 2
    assert "THIS IS ATTEMPT 3" in calls[2]                   # still knows the history


def test_setup_errors_are_not_retried(tmp_path, repo):
    calls = []

    async def no_model(prompt, workspace):
        calls.append(1)
        raise SetupError("Set AERITH_MAINTENANCE_OWNER")

    m = _maintainer_with_repo(tmp_path, repo, no_model)

    async def run():
        m.ingest([_event("x")])
        await _drain(m)
    asyncio.run(run())
    assert calls == [1]
    assert m.store.proposals()[0]["failure_kind"] == "setup"


# -- Cid ------------------------------------------------------------------------

def test_split_reply_separates_actions():
    text, actions = split_reply('Do it.\n<actions>{"agree": ["a1"]}</actions>')
    assert text == "Do it." and actions == {"agree": ["a1"]}
    assert split_reply("just words") == ("just words", {})
    assert split_reply("x <actions>not json</actions>")[1] == {}


def _cid(tmp_path, llm, notes=None):
    s = st.MaintenanceStore(str(tmp_path / "cid"))
    chosen = []

    def choose(pid, user):
        chosen.append((pid, user))
        return s.update_proposal(pid, status=st.QUEUED)

    async def notify(title, body):
        if notes is not None:
            notes.append((title, body))
    return CidPlanner(s, llm, notify=notify, choose=choose), s, chosen


def test_cid_messages_the_user_when_options_arrive(tmp_path):
    notes = []
    cid, s, _ = _cid(tmp_path, lambda p: "Oi. Two ideas. 1 is good, 2 is a time sink. Which?", notes)
    a = s.add_proposal("feature", "Sleep chart", "chart", research_query="sleep")
    b = s.add_proposal("feature", "Ring sync", "sync")
    asyncio.run(cid.announce([a, b]))
    assert len(notes) == 1 and "2 feature ideas" in notes[0][0]
    assert "updates page" in notes[0][1]
    msgs = s.cid_messages()
    assert msgs[0]["role"] == "cid" and msgs[0]["option_ids"] == [a["id"], b["id"]]
    assert s.cid_unread() == 1


def test_cid_only_builds_what_was_agreed_and_edits_the_rest(tmp_path):
    s_holder = {}

    def llm(prompt):
        a, b, c = s_holder["ids"]
        return ("Right, building the chart, binning sync, renaming the third.\n"
                "<actions>" + json.dumps({
                    "agree": [a, "not-a-real-id"],
                    "drop": [b],
                    "revise": [{"id": c, "title": "Battery widget", "platforms": ["android"]}],
                    "add": [{"title": "Dark mode", "summary": "for the page", "platforms": ["desktop"]}],
                }) + "</actions>")

    cid, s, chosen = _cid(tmp_path, llm)
    ids = [s.add_proposal("feature", t, t)["id"] for t in ("Sleep chart", "Ring sync", "Battery")]
    s_holder["ids"] = ids
    out = cid.reply("Do the chart, skip sync, and the battery one should be android only", "tom")

    assert chosen == [(ids[0], "tom")]
    assert out["changes"]["agreed"] == [ids[0]]
    assert s.proposal(ids[1])["status"] == st.REJECTED
    assert s.proposal(ids[2])["title"] == "Battery widget"
    assert s.proposal(ids[2])["platforms"] == ["android"]
    added = s.proposal(out["changes"]["added"][0])
    assert added["title"] == "Dark mode" and added["status"] == st.OFFERED
    assert [m["role"] for m in s.cid_messages()] == ["user", "cid"]
    assert "<actions>" not in s.cid_messages()[-1]["content"]


def test_cid_cannot_agree_options_that_are_not_on_the_table(tmp_path):
    cid, s, chosen = _cid(tmp_path, lambda p: '<actions>{"agree": ["x"]}</actions>')
    done = s.add_proposal("feature", "Old", "o", status=st.APPLIED)
    cid.apply_actions({"agree": [done["id"]]}, "tom")
    assert chosen == []


def test_cid_falls_back_when_the_model_returns_data_and_replies_are_read(tmp_path):
    cid, s, _ = _cid(tmp_path, lambda p: '[{"title": "x"}]')
    a = s.add_proposal("feature", "Sleep chart", "chart")
    asyncio.run(cid.announce([a]))
    assert s.cid_messages()[0]["content"].startswith("Right, research turned up")
    cid.reply("tell me more", "tom")
    assert s.cid_unread() == 0
