"""The background loop: watch logs, open incidents, draft fixes, read research."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from companion.maintenance import features
from companion.maintenance import store as st
from companion.maintenance.builder import AgentRunner, ProposalBuilder
from companion.maintenance.config import MaintenanceConfig
from companion.maintenance.log_watch import ErrorEvent, LogTailer, parse_log_text

logger = logging.getLogger(__name__)


class AerithMaintainer:
    def __init__(self, config: MaintenanceConfig, agent: AgentRunner,
                 llm: Callable[[str], str], research_dir: str = ""):
        self.config = config
        self.store = st.MaintenanceStore(config.data_dir)
        self.builder = ProposalBuilder(config, self.store, agent)
        self.llm = llm
        self.research_dir = research_dir
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
        self.store.note_fix_attempt()
        first_line = incident["message"].splitlines()[0] if incident["message"] else incident_id
        proposal = self.store.add_proposal(
            "bugfix", f"Fix {incident['platform']} error: {first_line[:80]}",
            incident["message"], status=st.QUEUED, platforms=[incident["platform"]],
            incident_id=incident_id,
        )
        self.store.update_incident(incident_id, status=st.FIXING, proposal_id=proposal["id"])
        self._spawn(proposal["id"])
        return proposal

    def choose_feature(self, proposal_id: str) -> dict | None:
        """The user picked an offered feature: build it."""
        prop = self.store.proposal(proposal_id)
        if not prop or prop["kind"] != "feature" or prop["status"] not in (st.OFFERED, st.FAILED):
            return None
        prop = self.store.update_proposal(proposal_id, status=st.QUEUED)
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
            await self.builder.build(proposal_id)
        except Exception as exc:
            logger.exception("Aerith build crashed for %s", proposal_id)
            self.store.update_proposal(proposal_id, status=st.FAILED, error=str(exc))

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
        await asyncio.to_thread(self.scan_research)

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
