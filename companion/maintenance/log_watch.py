"""Turn raw log output into deduplicated error events.

Server logs come from the Python logging format used by app.py::

    2026-11-22 10:00:00,123 - routes.chat - ERROR - message
    Traceback (most recent call last):
      File "/app/routes/chat.py", line 10, in handler
    ValueError: boom

Client logs (Android / desktop) are posted to the ingest endpoint and go
through the same fingerprinting so repeats collapse into one incident.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field

LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d+)?) - (?P<logger>[^ ]+) - "
    r"(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL) - (?P<msg>.*)$"
)
FRAME_RE = re.compile(r'File "(?P<file>[^"]+)", line \d+, in (?P<func>\S+)')
# Android stack frames: "at com.example.Foo.bar(Foo.kt:42)"
JVM_FRAME_RE = re.compile(r"^\s*at (?P<func>[\w$.<>]+)\((?P<file>[^:)]+)")

ERROR_LEVELS = {"ERROR", "CRITICAL", "FATAL", "ASSERT", "E", "F"}
# Never turn Aerith's own maintenance logging into incidents: a failing fixer
# must not trigger a fix for the fixer, forever.
IGNORED_LOGGER_PREFIXES = ("companion.maintenance",)


@dataclass
class ErrorEvent:
    platform: str          # "server", "android", "desktop"
    source: str            # logger name / app id
    level: str
    message: str
    detail: str = ""       # traceback / stack trace
    timestamp: str = ""
    app_version: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.platform, self.source, self.message, self.detail)


_NOISE = [
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I), "<uuid>"),
    (re.compile(r"0x[0-9a-f]+", re.I), "<hex>"),
    (re.compile(r"\b[0-9a-f]{16,}\b", re.I), "<hash>"),
    (re.compile(r"'[^']*'|\"[^\"]*\""), "<str>"),
    (re.compile(r"\d+"), "<n>"),
]


def normalize(text: str) -> str:
    text = (text or "").strip()
    for pattern, repl in _NOISE:
        text = pattern.sub(repl, text)
    return re.sub(r"\s+", " ", text)[:300]


def _frames(detail: str) -> list[str]:
    frames = []
    for line in (detail or "").splitlines():
        m = FRAME_RE.search(line) or JVM_FRAME_RE.search(line)
        if m:
            frames.append(f"{os.path.basename(m.group('file'))}:{m.group('func')}")
    return frames


def _exception_line(detail: str) -> str:
    lines = [ln.strip() for ln in (detail or "").splitlines() if ln.strip()]
    for line in reversed(lines):
        if not line.startswith(("File ", "at ", "Traceback", "...")):
            return line.split(":", 1)[0]
    return ""


def fingerprint(platform: str, source: str, message: str, detail: str = "") -> str:
    """Stable id for "the same bug": exception type + innermost frames when a
    stack is available, otherwise the message with volatile parts stripped."""
    frames = _frames(detail)
    if frames:
        key = "|".join([platform, _exception_line(detail), *frames[-3:]])
    else:
        key = "|".join([platform, source, normalize(message)])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def parse_log_text(text: str, platform: str = "server") -> list[ErrorEvent]:
    """Extract ERROR/CRITICAL records (with their tracebacks) from log text."""
    events: list[ErrorEvent] = []
    current: ErrorEvent | None = None
    detail: list[str] = []

    def flush():
        nonlocal current, detail
        if current is not None:
            current.detail = "\n".join(detail).strip()
            events.append(current)
        current, detail = None, []

    for line in text.splitlines():
        m = LINE_RE.match(line)
        if m:
            flush()
            if m.group("level") in ERROR_LEVELS and not m.group("logger").startswith(IGNORED_LOGGER_PREFIXES):
                current = ErrorEvent(
                    platform=platform,
                    source=m.group("logger"),
                    level=m.group("level"),
                    message=m.group("msg").strip(),
                    timestamp=m.group("ts"),
                )
        elif current is not None:
            detail.append(line)
    flush()
    return events


class LogTailer:
    """Incrementally read a rotating log file.

    Remembers (inode, offset) so restarts don't re-report old errors and a
    rotation (new inode or truncated file) starts again from the top.
    """

    MAX_READ = 2 * 1024 * 1024

    def __init__(self, path: str, state: dict | None = None):
        self.path = path
        self.state = dict(state or {})

    def read_new(self) -> str:
        try:
            st = os.stat(self.path)
        except OSError:
            return ""
        inode, offset = self.state.get("inode"), int(self.state.get("offset") or 0)
        if inode is None:
            # First run: don't dump the whole history on the user; start at
            # the end and only watch errors that happen from now on.
            self.state = {"inode": st.st_ino, "offset": st.st_size}
            return ""
        if inode != st.st_ino or st.st_size < offset:
            offset = 0
        if st.st_size == offset:
            self.state = {"inode": st.st_ino, "offset": offset}
            return ""
        with open(self.path, "rb") as fh:
            fh.seek(offset)
            chunk = fh.read(self.MAX_READ)
        # Only consume whole lines; a half-written record is read next tick.
        cut = chunk.rfind(b"\n") + 1
        chunk = chunk[:cut]
        self.state = {"inode": st.st_ino, "offset": offset + len(chunk)}
        return chunk.decode("utf-8", errors="replace")
