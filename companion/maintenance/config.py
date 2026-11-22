"""Environment-driven configuration for Aerith self-maintenance."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _repo_default() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _data_default() -> str:
    try:
        from src.constants import DATA_DIR
    except Exception:  # pragma: no cover - only hit outside the app
        DATA_DIR = os.path.join(_repo_default(), "data")
    return os.path.join(DATA_DIR, "aerith", "maintenance")


@dataclass
class MaintenanceConfig:
    enabled: bool = False
    # Draft fixes automatically when a new error appears.  Drafts still need
    # human approval before they are merged.
    autofix: bool = True
    owner: str = ""
    repo_dir: str = field(default_factory=_repo_default)
    data_dir: str = field(default_factory=_data_default)
    log_file: str = ""
    test_cmd: str = "python -m pytest -q tests"
    poll_seconds: int = 30
    max_fixes_per_day: int = 3
    # An incident must occur at least this many times before a fix is drafted.
    min_occurrences: int = 1
    # Attempts per round: after a failed fix Aerith investigates why and tries
    # a different approach or a workaround, up to this many times in total.
    max_attempts: int = 3
    agent_timeout_seconds: int = 900
    test_timeout_seconds: int = 900

    @classmethod
    def from_env(cls) -> "MaintenanceConfig":
        cfg = cls(
            enabled=_flag("AERITH_MAINTENANCE_ENABLED", False),
            autofix=_flag("AERITH_AUTOFIX", True),
            owner=os.getenv("AERITH_MAINTENANCE_OWNER", "").strip(),
            test_cmd=os.getenv("AERITH_TEST_CMD", cls.test_cmd).strip() or cls.test_cmd,
            poll_seconds=max(5, _int("AERITH_MAINTENANCE_POLL_SECONDS", cls.poll_seconds)),
            max_fixes_per_day=max(0, _int("AERITH_MAX_FIXES_PER_DAY", cls.max_fixes_per_day)),
            min_occurrences=max(1, _int("AERITH_FIX_MIN_OCCURRENCES", cls.min_occurrences)),
            max_attempts=max(1, _int("AERITH_FIX_MAX_ATTEMPTS", cls.max_attempts)),
            agent_timeout_seconds=max(60, _int("AERITH_AGENT_TIMEOUT", cls.agent_timeout_seconds)),
            test_timeout_seconds=max(30, _int("AERITH_TEST_TIMEOUT", cls.test_timeout_seconds)),
        )
        if os.getenv("AERITH_REPO_DIR"):
            cfg.repo_dir = os.path.abspath(os.getenv("AERITH_REPO_DIR", ""))
        if os.getenv("AERITH_MAINTENANCE_DATA_DIR"):
            cfg.data_dir = os.path.abspath(os.getenv("AERITH_MAINTENANCE_DATA_DIR", ""))
        cfg.log_file = os.getenv("AERITH_LOG_FILE", "").strip() or cfg.default_log_file()
        return cfg

    @staticmethod
    def default_log_file() -> str:
        try:
            from src.constants import DATA_DIR
        except Exception:  # pragma: no cover
            return ""
        return os.path.join(DATA_DIR, "logs", "app.log")

    @property
    def worktree_root(self) -> str:
        return os.path.join(self.data_dir, "worktrees")
