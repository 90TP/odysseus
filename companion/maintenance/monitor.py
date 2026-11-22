"""The background loop: watch logs, open incidents, draft fixes, read research."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from companion.maintenance import features
from companion.maintenance import store as st
from companion.maintenance.builder import RETRYABLE, AgentRunner, ProposalBuilder, describe_attempt
from companion.maintenance.cid import CidPlanner, Notifier
from companion.maintenance.config import MaintenanceConfig
from companion.maintenance.log_watch import ErrorEvent, LogTailer, parse_log_text

logger = logging.getLogger(__name__)


class AerithMaintainer:
    def __init__(self, config: MaintenanceConfig, agent: AgentRunner,
                 llm: Callable[[str], str], research_dir: str = "",
                 notify: Notifier | None = None):
        self.config = config
        self.store = st.MaintenanceStore(config.data_dir)
        self.builder = ProposalBuilder(config, self.store, agent)
        self.llm = llm
        self.research_dir = research_dir
        self.cid = CidPlanner(self.store, llm, notify=notify, choose=self.choose_feature)
        self._task: asyncio.Task | None = None
        self._jobs: set[asyncio.Task] = set()

    # -- events ------------------------------------------------------------
    def ingest(self, events: list[ErrorEvent]) -> list[dict]:
        """Record error events; returns the incidents that are new/reopened."""
        fresh = []
        for event in events:
            incident, is_new = self.store.record_event(event)
            if is_new:
                logger.info("Aerith noticed a new %s error: %s", event.platform, incident["id"])
            if incident["status"] == st.OPEN and incident["count"] >= self.config.min_occurrences:
                fresh.append(incident)
        if self.config.autofix:
            for incident in fresh:
                self.queue_fix(incident["id"])
        return fresh

    def scan_logs(self) -> list[dict]:
        if not self.config.log_file:
            return []
        tailer = LogTailer(self.config.log_file, self.store.cursor("server_log"))
        text = tailer.read_new()
        self.store.set_cursor("server_log", tailer.state)
        return self.ingest(parse_log_text(text, platform="server")) if text else []

    # -- fixes -------------------------------------------------------------
    def queue_fix(self, incident_id: str, *, force: bool = False) -> dict | None:
        """Create a bugfix proposal and start building it in the background."""
        incident = self.store.incident(incident_id)
        if not incident:
            return None
        if not force:
            if incident["status"] != st.OPEN:
                return None
            if self.store.fixes_in_last_day() >= self.config.max_fixes_per_day:
                logger.info("Aerith fix budget used up for today; %s waits", incident_id)
                return None
        last = self.store.proposal(incident.get("proposal_id") or "")
        if last and last.get("status") == st.FAILED:
            # Pressing "fix" again after failures: start a new round that still
            # knows everything the earlier attempts tried.
            return self.retry(last["id"], new_round=True)
        if not force:
            self.store.note_fix_attempt()
        first_line = incident["message"].splitlines()[0] if incident["message"] else incident_id
        proposal = self.store.add_proposal(
            "bugfix", f"Fix {incident['platform']} error: {first_line[:80]}",
            incident["message"], status=st.QUEUED, platforms=[incident["platform"]],
            incident_id=incident_id, attempt=1, round_attempt=1, previous_attempts=[],
        )
        self.store.update_incident(incident_id, status=st.FIXING, proposal_id=proposal["id"])
        self._spawn(proposal["id"])
        return proposal

    def retry(self, proposal_id: str, *, new_round: bool = False) -> dict | None:
        """Follow a failed attempt with one that investigates why it failed.

        The new proposal carries a short account of every earlier attempt, so
        Aerith can work out why the usual fix isn't working and go another way.
        """
        old = self.store.proposal(proposal_id)
        if not old or old.get("status") != st.FAILED:
            return None
        history = list(old.get("previous_attempts") or []) + [describe_attempt(old)]
        keep = ("kind", "title", "summary", "platforms", "incident_id", "rationale", "effort",
                "research_id", "research_query", "agreed_with")
        fields = {k: old[k] for k in keep if k in old}
        kind, title, summary = fields.pop("kind"), fields.pop("title"), fields.pop("summary")
        new = self.store.add_proposal(
            kind, title, summary, status=st.QUEUED,
            attempt=int(old.get("attempt") or 1) + 1,
            round_attempt=1 if new_round else int(old.get("round_attempt") or 1) + 1,
            previous_attempts=history[-4:], retry_of=old["id"], **fields,
        )
        # The failed attempt's diff is in the history now; free its worktree.
        self.builder._discard_worktree(old.get("worktree"), branch=old.get("branch"))
        self.store.update_proposal(old["id"], status=st.SUPERSEDED, superseded_by=new["id"])
        if new.get("incident_id"):
            self.store.update_incident(new["incident_id"], status=st.FIXING, proposal_id=new["id"])
        logger.info("Aerith is retrying %s as %s (attempt %s)", old["id"], new["id"], new["attempt"])
        self._spawn(new["id"])
        return new

    def choose_feature(self, proposal_id: str, agreed_with: str = "") -> dict | None:
        """The user picked an offered feature (directly or with Cid): build it."""
        prop = self.store.proposal(proposal_id)
        if not prop or prop["kind"] != "feature":
            return None
        if prop["status"] == st.FAILED:
            return self.retry(proposal_id, new_round=True)
        if prop["status"] != st.OFFERED:
            return None
        prop = self.store.update_proposal(proposal_id, status=st.QUEUED, attempt=1, round_attempt=1,
                                          previous_attempts=[], agreed_with=agreed_with or None)
        self._spawn(proposal_id)
        return prop

    def _spawn(self, proposal_id: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # tests / sync callers build explicitly
        task = loop.create_task(self._build(proposal_id))
        self._jobs.add(task)
        task.add_done_callback(self._jobs.discard)

    async def _build(self, proposal_id: str) -> None:
        try:
            result = await self.builder.build(proposal_id)
        except Exception as exc:
            logger.exception("Aerith build crashed for %s", proposal_id)
            result = self.store.update_proposal(proposal_id, status=st.FAILED, error=str(exc),
                                                failure_kind="agent")
        if self.should_retry(result):
            self.retry(proposal_id)

    def should_retry(self, result: dict | None) -> bool:
        return bool(
            result and result.get("status") == st.FAILED
            and result.get("failure_kind") in RETRYABLE
            and int(result.get("round_attempt") or 1) < self.config.max_attempts
        )

    # -- research ----------------------------------------------------------
    def scan_research(self) -> list[dict]:
        if not self.research_dir or not self.config.owner:
            return []
        cursor = self.store.cursor("research")
        seen = set(cursor.get("seen") or [])
        reports = features.unseen_research(self.research_dir, self.config.owner, seen)
        if not cursor.get("initialised"):
            # First run: only look at research done from now on.
            seen.update(r["id"] for r in reports)
            self.store.set_cursor("research", {"initialised": True, "seen": sorted(seen)})
            return []
        offered = []
        for report in reports:
            try:
                offered += features.offer_from_report(
                    self.store, self.llm, query=report["query"],
                    report=report["report"], research_id=report["id"],
                )
            except Exception:
                logger.exception("Aerith could not read research %s", report["id"])
            seen.add(report["id"])
        self.store.set_cursor("research", {"initialised": True, "seen": sorted(seen)})
        return offered

    # -- loop --------------------------------------------------------------
    async def tick(self) -> None:
        await asyncio.to_thread(self.scan_logs)
        offered = await asyncio.to_thread(self.scan_research)
        if offered:
            # Cid messages the user so they can agree together what to build.
            await self.cid.announce(offered)

    async def run_forever(self) -> None:
        logger.info("Aerith maintenance watching %s", self.config.log_file or "(no log file)")
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Aerith maintenance tick failed")
            await asyncio.sleep(self.config.poll_seconds)

    def start(self) -> asyncio.Task:
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self.run_forever())
        return self._task
