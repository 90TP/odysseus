"""Draft, test, apply and discard Aerith-authored changes.

Every change is built in its own git worktree on an ``aerith/…`` branch, so
the running checkout is never touched while Aerith works.  A proposal becomes
``ready`` only when it has a non-empty diff and the test command passes.
Merging into the live checkout happens solely in :meth:`ProposalBuilder.apply`,
which the routes expose to a human admin and nothing else.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import shutil
import subprocess
from typing import Awaitable, Callable

from companion.maintenance import store as st
from companion.maintenance.config import MaintenanceConfig

logger = logging.getLogger(__name__)

AgentRunner = Callable[[str, str], Awaitable[str]]

# Paths Aerith may not change in her own updates: the approval gate itself and
# CI configuration.  A diff touching these is refused, whatever it does.
PROTECTED_PATHS = ("companion/maintenance/", ".github/", ".env")

BUGFIX_PROMPT = """You are fixing a bug in the app you run inside. Work ONLY in the
current workspace (a scratch git worktree on branch {branch}); it is not the
live app, and a human will review your change before it is merged.

Platform: {platform}
Source: {source}
Seen {count} time(s). App version: {version}

Error:
{message}

Stack trace / detail:
{detail}

Do this:
1. Find the root cause in the code. Read the relevant files first.
2. Make the smallest change that fixes it. Android code lives under android/;
   desktop/server code is the Python app and static/.
3. Add or update a test that would have caught it, if a test suite covers that area.
4. Commit your work with git (a short message starting "fix:").
Do NOT push, do NOT edit {protected}, do NOT touch secrets or .env files.
If you cannot find a safe fix, change nothing and explain why.
End with a 2-4 sentence summary of the cause and the fix."""

FEATURE_PROMPT = """You are adding a feature to the app you run inside. Work ONLY in the
current workspace (a scratch git worktree on branch {branch}); it is not the
live app, and a human will review your change before it is merged.

Feature: {title}
Platforms: {platforms}

What the user chose:
{summary}

Why it was suggested:
{rationale}

Do this:
1. Read the surrounding code and follow its existing patterns.
2. Implement the feature in small, focused changes. Android code lives under
   android/; desktop/server code is the Python app and static/.
3. Add tests for new behaviour where the area has tests.
4. Commit your work with git (a short message starting "feat:").
Do NOT push, do NOT edit {protected}, do NOT touch secrets or .env files.
End with a short summary of what you built and anything left to do."""


RETRY_SECTION = """

THIS IS ATTEMPT {attempt}. The usual fix has already failed {failed} time(s):
{history}

Before changing anything, investigate WHY the earlier attempt(s) failed:
- Reproduce the problem (run the failing test or code path) and read the real output.
- Decide which of these it was: wrong root cause; correct cause but the fix broke
  something else; the cause is outside this codebase (a dependency, the OS/device,
  an external service, config or bad data); a test that was already broken; or the
  real fix needs a protected file.
- If the earlier change was close, build on it. If it was the wrong approach, drop it.

Then fix it a DIFFERENT way. If the root cause can't be fixed directly here, work
around it at our boundary: validate or guard the input, add a fallback or retry,
degrade gracefully with a clear log message, or put the risky path behind a check.
Never repeat a change that already failed.

Start your final summary with "Why the usual fix didn't work:" and one or two
sentences, then describe the workaround."""

MAX_HISTORY_CHARS = 2500


class BuildError(RuntimeError):
    pass


class SetupError(RuntimeError):
    """Aerith can't work at all (no model, no owner). Retrying won't help."""


# Failure kinds; only some are worth an investigative retry.
SETUP, AGENT, NO_CHANGE, PROTECTED, TESTS = "setup", "agent", "no_change", "protected", "tests"
RETRYABLE = {AGENT, NO_CHANGE, PROTECTED, TESTS}

FAILED_TEST_RE = re.compile(r"^(?:FAILED|ERROR) (\S+)", re.M)


def failing_tests(output: str) -> set[str]:
    """Test ids pytest reports as failed/errored (from its short summary)."""
    return set(FAILED_TEST_RE.findall(output or ""))


def describe_attempt(prop: dict) -> str:
    """Short account of a failed attempt, fed into the next attempt's prompt."""
    lines = [f"- Attempt {prop.get('attempt', 1)} failed: {prop.get('error') or 'unknown error'}"]
    if prop.get("files"):
        lines.append(f"  Files it changed: {', '.join(prop['files'][:15])}")
    if prop.get("report"):
        lines.append(f"  What Aerith said: {prop['report'][-600:]}")
    if prop.get("test_output") and not prop.get("tests_passed", True):
        lines.append(f"  Test output (end):\n{prop['test_output'][-900:]}")
    if prop.get("attempt_diff"):
        lines.append(f"  Its diff (start):\n{prop['attempt_diff'][:900]}")
    return "\n".join(lines)


def _git(repo: str, *args: str, timeout: int = 120, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True, text=True, timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise BuildError(f"git {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "change"


class ProposalBuilder:
    def __init__(self, config: MaintenanceConfig, store: st.MaintenanceStore, agent: AgentRunner):
        self.config = config
        self.store = store
        self.agent = agent
        self._lock = asyncio.Lock()

    # -- helpers -----------------------------------------------------------
    def _worktree_path(self, proposal_id: str) -> str:
        return os.path.join(self.config.worktree_root, proposal_id)

    def _prompt(self, proposal: dict, branch: str) -> str:
        prompt = self._base_prompt(proposal, branch)
        previous = proposal.get("previous_attempts") or []
        if previous:
            history = "\n".join(previous)[-MAX_HISTORY_CHARS * 2:]
            prompt += RETRY_SECTION.format(attempt=len(previous) + 1, failed=len(previous),
                                           history=history)
        return prompt

    def _base_prompt(self, proposal: dict, branch: str) -> str:
        protected = ", ".join(PROTECTED_PATHS)
        if proposal["kind"] == "bugfix":
            inc = self.store.incident(proposal.get("incident_id") or "") or {}
            return BUGFIX_PROMPT.format(
                branch=branch,
                platform=inc.get("platform", "server"),
                source=inc.get("source", "?"),
                count=inc.get("count", 1),
                version=inc.get("app_version") or "unknown",
                message=inc.get("message", proposal["summary"]),
                detail=(inc.get("detail") or "(none)")[-6000:],
                protected=protected,
            )
        return FEATURE_PROMPT.format(
            branch=branch,
            title=proposal["title"],
            platforms=", ".join(proposal.get("platforms") or ["server"]),
            summary=proposal["summary"],
            rationale=proposal.get("rationale") or "(not given)",
            protected=protected,
        )

    def _check_tests(self, cwd: str, base: str) -> tuple[bool, str]:
        """Run tests; failures that already happen on the base commit don't
        count against Aerith's change (a broken suite shouldn't block every fix)."""
        ok, out = self._run_tests(cwd)
        if ok:
            return ok, out
        now_failing = failing_tests(out)
        if not now_failing:
            return False, out
        baseline = self._baseline_failures(base)
        if baseline is None:
            return False, out
        new = now_failing - baseline
        if new:
            return False, out + "\n\nNew failures caused by this change: " + ", ".join(sorted(new))
        return True, (out + f"\n\nAll {len(now_failing)} failing test(s) were already failing "
                           f"before this change, so they don't block it.")

    def _baseline_failures(self, base: str) -> set[str] | None:
        cache = self.store.cursor("test_baseline")
        if cache.get("commit") == base:
            return set(cache.get("failing") or [])
        path = os.path.join(self.config.worktree_root, f"baseline-{base[:10]}")
        try:
            if os.path.exists(path):
                self._discard_worktree(path, branch=None)
            _git(self.config.repo_dir, "worktree", "add", "--detach", path, base)
            ok, out = self._run_tests(path)
        except BuildError:
            return None
        finally:
            self._discard_worktree(path, branch=None)
        failing = set() if ok else failing_tests(out)
        if not ok and not failing:
            return None  # couldn't tell what failed
        self.store.set_cursor("test_baseline", {"commit": base, "failing": sorted(failing)})
        return failing

    def _run_tests(self, cwd: str) -> tuple[bool, str]:
        if not self.config.test_cmd:
            return True, "(no test command configured)"
        # Give the test run its own data dir so anything it logs can't land in
        # the live app.log and be mistaken for a new production error.
        env = dict(os.environ, ODYSSEUS_DATA_DIR=os.path.join(
            self.config.data_dir, "test-data", os.path.basename(cwd)))
        try:
            proc = subprocess.run(
                shlex.split(self.config.test_cmd), cwd=cwd, env=env,
                capture_output=True, text=True, timeout=self.config.test_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return False, f"Tests timed out after {self.config.test_timeout_seconds}s"
        except OSError as exc:
            return False, f"Could not run tests: {exc}"
        out = (proc.stdout + "\n" + proc.stderr).strip()
        return proc.returncode == 0, out[-4000:]

    # -- build -------------------------------------------------------------
    async def build(self, proposal_id: str) -> dict:
        """Have Aerith implement a proposal in an isolated worktree."""
        async with self._lock:
            return await self._build_locked(proposal_id)

    async def _build_locked(self, proposal_id: str) -> dict:
        proposal = self.store.proposal(proposal_id)
        if not proposal:
            raise BuildError("Unknown proposal")
        repo = self.config.repo_dir
        prefix = "fix" if proposal["kind"] == "bugfix" else "feature"
        branch = f"aerith/{prefix}-{_slug(proposal['title'])}-{proposal_id[:6]}"
        path = self._worktree_path(proposal_id)
        base = _git(repo, "rev-parse", "HEAD")
        os.makedirs(self.config.worktree_root, exist_ok=True)
        if os.path.exists(path):
            self._discard_worktree(path, branch=None)
        _git(repo, "worktree", "add", "-b", branch, path, base)
        self.store.update_proposal(proposal_id, status=st.BUILDING, branch=branch,
                                   base_commit=base, worktree=path, error=None)
        self._set_incident(proposal, st.FIXING)

        try:
            report = await asyncio.wait_for(
                self.agent(self._prompt(proposal, branch), path),
                timeout=self.config.agent_timeout_seconds,
            )
        except SetupError as exc:
            return self._fail(proposal_id, proposal, str(exc), kind=SETUP)
        except asyncio.TimeoutError:
            return self._fail(proposal_id, proposal,
                              f"Aerith ran out of time ({self.config.agent_timeout_seconds}s).",
                              kind=AGENT, **self._partial(path, base))
        except Exception as exc:  # agent failure
            return self._fail(proposal_id, proposal, f"Aerith could not finish: {exc!r}",
                              kind=AGENT, **self._partial(path, base))

        # Commit anything the agent left uncommitted.
        if _git(path, "status", "--porcelain"):
            _git(path, "add", "-A")
            _git(path, "-c", "user.name=Aerith", "-c", "user.email=aerith@localhost",
                 "commit", "-m", f"{prefix}: {proposal['title']}")
        changed = [f for f in _git(path, "diff", "--name-only", f"{base}..HEAD").splitlines() if f]
        if not changed:
            return self._fail(proposal_id, proposal, "No change was made.", kind=NO_CHANGE,
                              report=(report or "")[-4000:])
        blocked = [f for f in changed if f.startswith(PROTECTED_PATHS)]
        if blocked:
            return self._fail(proposal_id, proposal,
                              "Refused: the change touches protected files: " + ", ".join(blocked),
                              kind=PROTECTED, report=(report or "")[-4000:], files=changed,
                              attempt_diff=_git(path, "diff", f"{base}..HEAD")[:6000])

        ok, test_out = await asyncio.to_thread(self._check_tests, path, base)
        fields = dict(
            report=(report or "")[-4000:],
            files=changed,
            diff_stat=_git(path, "diff", "--stat", f"{base}..HEAD"),
            tests_passed=ok,
            test_output=test_out,
        )
        if not ok:
            return self._fail(proposal_id, proposal, "Tests failed on Aerith's change.", kind=TESTS,
                              attempt_diff=_git(path, "diff", f"{base}..HEAD")[:6000], **fields)
        self._set_incident(proposal, st.PROPOSED)
        logger.info("Aerith drafted %s on %s (%d files)", proposal_id, branch, len(changed))
        return self.store.update_proposal(proposal_id, status=st.READY, **fields)

    def _partial(self, path: str, base: str) -> dict:
        """What a timed-out/crashed attempt managed, so the next one can build on it."""
        try:
            diff = _git(path, "diff", base)  # includes uncommitted work
        except BuildError:
            return {}
        return {"attempt_diff": diff[:6000]} if diff else {}

    def _fail(self, proposal_id: str, proposal: dict, error: str, kind: str = AGENT, **fields) -> dict:
        logger.warning("Aerith proposal %s failed (%s): %s", proposal_id, kind, error)
        self._set_incident(proposal, st.FIX_FAILED)
        return self.store.update_proposal(proposal_id, status=st.FAILED, error=error,
                                          failure_kind=kind, **fields)

    def _set_incident(self, proposal: dict, status: str) -> None:
        if proposal.get("incident_id"):
            self.store.update_incident(proposal["incident_id"], status=status,
                                       proposal_id=proposal["id"])

    # -- diff --------------------------------------------------------------
    def diff(self, proposal_id: str) -> str:
        prop = self.store.proposal(proposal_id) or {}
        if not prop.get("branch") or not prop.get("base_commit"):
            return ""
        try:
            return _git(self.config.repo_dir, "diff", f"{prop['base_commit']}..{prop['branch']}")[:200_000]
        except BuildError:
            return ""

    # -- apply / reject ----------------------------------------------------
    def apply(self, proposal_id: str, approved_by: str) -> dict:
        """Merge a ready proposal into the live checkout. Human-approved only."""
        prop = self.store.proposal(proposal_id)
        if not prop or prop.get("status") != st.READY:
            raise BuildError("Only a ready, tested proposal can be applied")
        repo = self.config.repo_dir
        if _git(repo, "status", "--porcelain", "--untracked-files=no"):
            raise BuildError("The app checkout has uncommitted changes; commit or stash them first")
        merge = subprocess.run(
            ["git", "-C", repo, "-c", "user.name=Aerith", "-c", "user.email=aerith@localhost",
             "merge", "--no-ff", "--no-edit", prop["branch"]],
            capture_output=True, text=True, timeout=120,
        )
        if merge.returncode != 0:
            subprocess.run(["git", "-C", repo, "merge", "--abort"], capture_output=True)
            raise BuildError("Merge conflict with the current code; ask Aerith to rebuild it")
        self._discard_worktree(prop.get("worktree"), branch=None)
        if prop.get("incident_id"):
            # Resolved, but if the error comes back the incident reopens.
            self.store.update_incident(prop["incident_id"], status=st.RESOLVED)
        return self.store.update_proposal(
            proposal_id, status=st.APPLIED, approved_by=approved_by,
            merged_commit=_git(repo, "rev-parse", "HEAD"), restart_required=True,
        )

    def reject(self, proposal_id: str, rejected_by: str, reason: str = "") -> dict:
        prop = self.store.proposal(proposal_id)
        if not prop:
            raise BuildError("Unknown proposal")
        if prop.get("status") == st.APPLIED:
            raise BuildError("Already applied; revert it with git instead")
        self._discard_worktree(prop.get("worktree"), branch=prop.get("branch"))
        if prop.get("incident_id"):
            self.store.update_incident(prop["incident_id"], status=st.DISMISSED)
        return self.store.update_proposal(proposal_id, status=st.REJECTED,
                                          rejected_by=rejected_by, reject_reason=reason[:500])

    def _discard_worktree(self, path: str | None, branch: str | None) -> None:
        repo = self.config.repo_dir
        if path and os.path.exists(path):
            _git(repo, "worktree", "remove", "--force", path, check=False)
            shutil.rmtree(path, ignore_errors=True)
        _git(repo, "worktree", "prune", check=False)
        if branch:
            _git(repo, "branch", "-D", branch, check=False)
