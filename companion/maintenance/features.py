"""Turn finished research into feature options the user can pick from.

Aerith reads each newly completed research report and asks the model whether
it suggests anything worth adding to the Android or desktop app.  Suggestions
are stored as ``offered`` feature proposals; nothing is built until the user
chooses one.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Callable

from companion.maintenance import store as st

logger = logging.getLogger(__name__)

Llm = Callable[[str], str]

MAX_OPTIONS = 4

FEATURE_IDEAS_PROMPT = """You help plan updates for a personal app with an Android
client and a desktop/server app (Odysseus, with the Aerith companion).

Below is a research report the user ran. Suggest up to {max_options} concrete
features this research could justify adding. Only suggest features the report
actually supports; return an empty list if nothing fits.

Return ONLY a JSON array. Each item:
{{"title": "...", "summary": "what it does, 1-3 sentences",
  "rationale": "which finding in the report supports it",
  "platforms": ["android" and/or "desktop" and/or "server"],
  "effort": "small" | "medium" | "large"}}

Research question: {query}

Report:
{report}"""


def parse_options(raw: str) -> list[dict]:
    """Pull a JSON array out of a model reply, tolerating code fences/prose."""
    if not raw:
        return []
    match = re.search(r"\[.*\]", raw, re.S)
    if not match:
        return []
    try:
        items = json.loads(match.group(0))
    except ValueError:
        return []
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or not str(item.get("title") or "").strip():
            continue
        platforms = item.get("platforms") or []
        if isinstance(platforms, str):
            platforms = [platforms]
        out.append({
            "title": str(item["title"]).strip(),
            "summary": str(item.get("summary") or "").strip(),
            "rationale": str(item.get("rationale") or "").strip(),
            "platforms": [str(p).strip().lower() for p in platforms],
            "effort": str(item.get("effort") or "medium").strip().lower(),
        })
    return out[:MAX_OPTIONS]


def offer_from_report(store: st.MaintenanceStore, llm: Llm, *, query: str, report: str,
                      research_id: str = "") -> list[dict]:
    if not report.strip():
        return []
    prompt = FEATURE_IDEAS_PROMPT.format(max_options=MAX_OPTIONS, query=query or "(unknown)",
                                         report=report[:20000])
    options = parse_options(llm(prompt))
    offered = []
    for opt in options:
        offered.append(store.add_proposal(
            "feature", opt["title"], opt["summary"] or opt["title"],
            status=st.OFFERED, platforms=opt["platforms"], rationale=opt["rationale"],
            effort=opt["effort"], research_id=research_id, research_query=query,
        ))
    return offered


def unseen_research(research_dir: str, owner: str, seen: set[str]) -> list[dict]:
    """Completed research reports for ``owner`` that Aerith hasn't read yet."""
    found = []
    try:
        names = sorted(os.listdir(research_dir))
    except OSError:
        return []
    for name in names:
        if not name.endswith(".json"):
            continue
        rid = name[:-5]
        if rid in seen:
            continue
        try:
            with open(os.path.join(research_dir, name), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if data.get("owner") != owner or data.get("status", "done") not in ("done", "complete", "completed"):
            continue
        report = data.get("result")
        if isinstance(report, str) and report.strip():
            found.append({"id": rid, "query": data.get("query", ""), "report": report})
    return found
