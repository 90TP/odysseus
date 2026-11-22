"""Pure calculations that turn raw device data into an FF7-style sheet.

Mapping (all overridable later without touching the data):
- Lv      = age (from birthdate) or a fixed level
- EXP     = days since the last birthday; "next level" = days to the next one
- SP      = minutes slept last night / recommended minutes   (FF7's HP)
- MP      = energy score / 100 (e.g. Galaxy Ring Energy Score)
- Limit   = stress 0-100: it fills as the day "deals damage", like FF7
- Equip   = phone (weapon), watch (armour), ring (accessory)
- Materia = apps on those devices, coloured by what they do
"""

from __future__ import annotations

import time
from datetime import date

DEFAULT_SLOTS = [
    {"slot": "weapon", "label": "Wpn.", "kind": "phone"},
    {"slot": "armor", "label": "Arm.", "kind": "watch"},
    {"slot": "accessory", "label": "Acc.", "kind": "ring"},
]

# FF7 materia colours, by what kind of app it is.
MATERIA_COLOURS = {
    "magic": "#3ccf5a",        # green: health, fitness, wellbeing
    "command": "#f2d23c",      # yellow: communication, social
    "independent": "#b45cf0",  # purple: productivity, tools
    "support": "#3c8cf2",      # blue: system, utilities, connectivity
    "summon": "#f04a4a",       # red: media, music, games
}
CATEGORY_TO_MATERIA = {
    "health": "magic", "fitness": "magic", "medical": "magic", "wellbeing": "magic", "sleep": "magic",
    "communication": "command", "social": "command", "messaging": "command", "email": "command",
    "productivity": "independent", "tools": "independent", "finance": "independent",
    "education": "independent", "business": "independent", "maps": "independent",
    "navigation": "independent",
    "system": "support", "utilities": "support", "connectivity": "support", "security": "support",
    "media": "summon", "music": "summon", "music_and_audio": "summon", "video": "summon",
    "games": "summon", "game": "summon", "entertainment": "summon", "photography": "summon",
}

# Status-screen rows: metric key -> label. Unknown keys still show, titled.
STATUS_LABELS = {
    "heart_rate": "Heart rate",
    "resting_heart_rate": "Resting HR",
    "hrv": "HRV",
    "stress": "Stress",
    "spo2": "Blood oxygen",
    "skin_temperature": "Skin temp",
    "respiratory_rate": "Breathing",
    "steps": "Steps",
    "active_minutes": "Active mins",
    "calories": "Calories",
    "energy_score": "Energy score",
    "sleep_score": "Sleep score",
    "sleep_minutes": "Sleep",
}


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _birthday_in(year: int, born: date) -> date:
    try:
        return born.replace(year=year)
    except ValueError:  # 29 Feb in a non-leap year
        return date(year, 3, 1)


def level_and_exp(profile: dict, today: date | None = None) -> dict:
    today = today or date.today()
    born = _parse_date(profile.get("birthdate"))
    if born:
        this_year = _birthday_in(today.year, born)
        last = this_year if this_year <= today else _birthday_in(today.year - 1, born)
        nxt = _birthday_in(last.year + 1, born)
        return {
            "level": last.year - born.year,
            "exp": (today - last).days,
            "next_level": (nxt - today).days,
        }
    level = profile.get("level")
    return {"level": int(level) if str(level or "").isdigit() else None, "exp": None, "next_level": None}


def metric_value(metrics: dict, key: str):
    m = metrics.get(key)
    if isinstance(m, dict):
        return m.get("value")
    return m


def gauge(current, maximum) -> dict | None:
    try:
        cur = float(current)
        mx = float(maximum)
    except (TypeError, ValueError):
        return None
    if mx <= 0:
        return None
    return {"current": round(cur), "max": round(mx), "fraction": max(0.0, min(1.0, cur / mx))}


def limit_gauge(stress) -> dict | None:
    try:
        value = max(0.0, min(100.0, float(stress)))
    except (TypeError, ValueError):
        return None
    return {"current": round(value), "max": 100, "fraction": value / 100.0, "full": value >= 100}


def equipment(profile: dict, devices: dict) -> list[dict]:
    """Fill each slot with the assigned device, else the newest device of its kind."""
    slots = profile.get("slots") or DEFAULT_SLOTS
    assigned = profile.get("slot_devices") or {}
    out = []
    for slot in slots:
        device = devices.get(assigned.get(slot["slot"]) or "")
        if device is None:
            matching = [d for d in devices.values() if d.get("kind") == slot.get("kind")]
            device = max(matching, key=lambda d: d.get("updated_at", 0)) if matching else None
        out.append({**slot, "device": device})
    return out


def materia(apps: list[dict]) -> list[dict]:
    out = []
    for app in apps:
        category = str(app.get("category") or "").strip().lower().replace(" ", "_")
        kind = CATEGORY_TO_MATERIA.get(category, "support" if not category else "independent")
        out.append({**app, "materia": kind, "colour": MATERIA_COLOURS[kind]})
    order = list(MATERIA_COLOURS)
    return sorted(out, key=lambda a: (order.index(a["materia"]), str(a.get("name", "")).lower()))


# Shown as SP / MP at the top of the sheet, so not repeated in Status.
HEADLINE_METRICS = {"sleep_minutes", "energy_score"}


def status_rows(metrics: dict) -> list[dict]:
    rows = []
    for key, m in metrics.items():
        if key in HEADLINE_METRICS:
            continue
        if not isinstance(m, dict) or m.get("value") in (None, ""):
            continue
        rows.append({
            "key": key,
            "label": STATUS_LABELS.get(key, key.replace("_", " ").capitalize()),
            "value": m.get("value"),
            "unit": m.get("unit") or "",
            "source": m.get("source") or "",
            "updated_at": m.get("updated_at"),
        })
    order = list(STATUS_LABELS)
    return sorted(rows, key=lambda r: (order.index(r["key"]) if r["key"] in order else 99, r["label"]))


def build_sheet(state: dict, today: date | None = None, now: float | None = None) -> dict:
    profile = state.get("profile") or {}
    metrics = state.get("metrics") or {}
    devices = state.get("devices") or {}
    now = now or time.time()
    sleep_goal = profile.get("sleep_goal_minutes") or 480
    return {
        "character": state.get("character"),
        "name": profile.get("display_name") or str(state.get("character") or "").capitalize(),
        "avatar_url": profile.get("avatar_url") or "",
        **level_and_exp(profile, today),
        "sp": gauge(metric_value(metrics, "sleep_minutes"), sleep_goal),
        "mp": gauge(metric_value(metrics, "energy_score"), 100),
        "limit": limit_gauge(metric_value(metrics, "stress")),
        "location": state.get("location") or None,
        "equipment": equipment(profile, devices),
        "materia": materia(state.get("apps") or []),
        "status": status_rows(metrics),
        "updated_at": state.get("updated_at"),
        "stale": bool(state.get("updated_at")) and now - float(state["updated_at"]) > 6 * 3600,
    }
