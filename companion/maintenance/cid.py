"""Cid: talks feature options through with the user before anything is built.

When research turns up feature options, Cid messages the user (through the
user's normal reminder channel: browser, email, ntfy or webhook) and opens a
planning conversation on the updates page.  Together they reword, add, drop and
agree options.  Only an option the user has agreed to in that conversation is
handed to Aerith to build, and the result still needs approval before merging.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Awaitable, Callable

from companion.maintenance import store as st

logger = logging.getLogger(__name__)

Llm = Callable[[str], str]
Notifier = Callable[[str, str], Awaitable[None]]

PAGE_PATH = "/api/companion/aerith/maintenance/page"
MAX_TURNS_IN_PROMPT = 16

CID_PERSONA = """You are Cid, the gruff, blunt airship engineer who runs the workshop where
updates to the user's apps get planned: an Android app and the desktop app
(Odysseus, home of the Aerith companion). Aerith does the building; you and the
user decide WHAT gets built. You're impatient and grumble a bit, but you're
practical, honest about effort and risk, and on the user's side. Keep it clean
apart from the odd "damn". Keep messages short: under 150 words."""

REPLY_RULES = """How to plan:
- Give a straight opinion on options when it helps: value, effort, risk, and which
  platform (android/desktop/server) they touch. Suggest an order if there are several.
- Ask what the user wants; don't decide for them.
- Mark an option "agree" ONLY if the user clearly said yes to building it in their
  latest message. If they're vague, ask them to confirm.
- You may reword, merge or split options, drop ones the user rejects, and add new
  ones the user asks for.
- Only use ids from the option list below.

Current options:
{options}

Conversation so far:
{conversation}

User: {message}

Reply with your message to the user. Then, on the last line, the changes as JSON
inside <actions></actions>, for example:
<actions>{{"agree": [], "drop": [], "revise": [{{"id": "...", "title": "...", "summary": "...", "platforms": ["android"]}}], "add": [{{"title": "...", "summary": "...", "platforms": ["desktop"], "effort": "small"}}]}}</actions>
Use empty lists when nothing changes."""

ANNOUNCE_PROMPT = """New feature options just came out of the user's research{about}.
Write your opening message to the user: say there are options to look at, give a
one-line take on each (by number), and ask which they want in the next update.

Options:
{options}"""

ACTIONS_RE = re.compile(r"<actions>(.*?)</actions>", re.S)


def _option_lines(options: list[dict]) -> str:
    if not options:
        return "(none)"
    lines = []
    for n, p in enumerate(options, 1):
        lines.append(f"{n}. [id {p['id']}] {p['title']} ({', '.join(p.get('platforms') or [])}; "
                     f"{p.get('effort') or '?'} effort; status {p['status']}): {p.get('summary', '')}")
    return "\n".join(lines)


def split_reply(raw: str) -> tuple[str, dict]:
    """Separate Cid's words from the trailing <actions> JSON."""
    raw = raw or ""
    actions: dict = {}
    match = ACTIONS_RE.search(raw)
    if match:
        try:
            parsed = json.loads(match.group(1).strip())
            if isinstance(parsed, dict):
                actions = parsed
        except ValueError:
            pass
        raw = raw[:match.start()] + raw[match.end():]
    return raw.strip(), actions


class CidPlanner:
    def __init__(self, store: st.MaintenanceStore, llm: Llm, notify: Notifier | None = None,
                 choose: Callable[[str, str], dict | None] | None = None):
        self.store = store
        self.llm = llm
        self.notify = notify
        self.choose = choose  # monitor.choose_feature

    # -- state ---------------------------------------------------------------
    def options(self) -> list[dict]:
        """Options still under discussion, plus ones agreed and in progress."""
        active = {st.OFFERED, st.QUEUED, st.BUILDING, st.READY}
        return [p for p in reversed(self.store.proposals(kind="feature")) if p["status"] in active]

    def messages(self) -> list[dict]:
        return self.store.cid_messages()

    # -- Cid starts the conversation --------------------------------------
    async def announce(self, offered: list[dict]) -> dict | None:
        if not offered:
            return None
        import asyncio
        queries = sorted({p.get("research_query") for p in offered if p.get("research_query")})
        about = f" on {', '.join(queries)}" if queries else ""
        try:
            raw = await asyncio.to_thread(
                self.llm, CID_PERSONA + "\n\n" + ANNOUNCE_PROMPT.format(
                    about=about, options=_option_lines(offered)))
            text, _ = split_reply(raw)
        except Exception:
            logger.exception("Cid couldn't write his opener")
            text = ""
        if text.lstrip().startswith(("[", "{")):
            text = ""  # the model answered with data, not a message
        if not text:
            text = ("Right, research turned up some ideas. Have a look and tell me which ones "
                    "are worth building:\n" + "\n".join(f"{n}. {p['title']}" for n, p in enumerate(offered, 1)))
        msg = self.store.add_cid_message("cid", text, option_ids=[p["id"] for p in offered])
        if self.notify:
            try:
                await self.notify(
                    f"Cid: {len(offered)} feature idea{'s' if len(offered) != 1 else ''} to talk through",
                    f"{text}\n\nReply on the updates page: {PAGE_PATH}",
                )
            except Exception:
                logger.exception("Cid couldn't send his message")
        return msg

    # -- the user replies ----------------------------------------------------
    def reply(self, message: str, user: str) -> dict:
        message = message.strip()
        if not message:
            raise ValueError("Say something to Cid")
        history = self.messages()[-MAX_TURNS_IN_PROMPT:]
        self.store.add_cid_message("user", message)
        conversation = "\n".join(
            f"{'Cid' if m['role'] == 'cid' else 'User'}: {m['content']}" for m in history
        ) or "(new conversation)"
        prompt = CID_PERSONA + "\n\n" + REPLY_RULES.format(
            options=_option_lines(self.options()), conversation=conversation, message=message)
        try:
            text, actions = split_reply(self.llm(prompt))
        except Exception:
            logger.exception("Cid couldn't answer")
            text, actions = "", {}
        changes = self.apply_actions(actions, user)
        if not text:
            text = "Damn radio's on the fritz. Say that again?"
        msg = self.store.add_cid_message("cid", text, changes=changes)
        self.store.mark_cid_read()  # the user is in the chat, so this isn't "new"
        return {"message": msg, "changes": changes}

    def apply_actions(self, actions: dict, user: str) -> dict:
        offered = {p["id"]: p for p in self.store.proposals(kind="feature", status=st.OFFERED)}
        done = {"agreed": [], "dropped": [], "revised": [], "added": []}

        for item in actions.get("revise") or []:
            if not isinstance(item, dict) or item.get("id") not in offered:
                continue
            fields = {}
            if str(item.get("title") or "").strip():
                fields["title"] = str(item["title"]).strip()[:200]
            if str(item.get("summary") or "").strip():
                fields["summary"] = str(item["summary"]).strip()[:4000]
            plats = [p for p in (item.get("platforms") or []) if p in st.PLATFORMS]
            if plats:
                fields["platforms"] = plats
            if fields:
                self.store.update_proposal(item["id"], **fields)
                done["revised"].append(item["id"])

        for item in (actions.get("add") or [])[:4]:
            if not isinstance(item, dict) or not str(item.get("title") or "").strip():
                continue
            plats = item.get("platforms") or []
            prop = self.store.add_proposal(
                "feature", str(item["title"]), str(item.get("summary") or item["title"]),
                status=st.OFFERED, platforms=plats if isinstance(plats, list) else [plats],
                effort=str(item.get("effort") or "medium"), rationale="Added while planning with Cid",
                source="cid",
            )
            offered[prop["id"]] = prop
            done["added"].append(prop["id"])

        for pid in actions.get("drop") or []:
            if pid in offered:
                self.store.update_proposal(pid, status=st.REJECTED, rejected_by=user,
                                           reject_reason="Dropped while planning with Cid")
                offered.pop(pid)
                done["dropped"].append(pid)

        for pid in actions.get("agree") or []:
            if pid in offered and self.choose and self.choose(pid, user):
                done["agreed"].append(pid)
        return done
