"""Character sheet: FF7-style stats from ring/watch/phone telemetry."""

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from companion.characters import stats
from companion.characters.routes import setup_character_routes
from companion.characters.store import CharacterStore


# -- stats ------------------------------------------------------------------

def test_level_is_age_and_exp_counts_days_around_birthday():
    out = stats.level_and_exp({"birthdate": "1990-06-15"}, today=date(2026, 11, 22))
    assert out == {"level": 36, "exp": 160, "next_level": 205}
    on_day = stats.level_and_exp({"birthdate": "1990-06-15"}, today=date(2027, 6, 15))
    assert on_day["level"] == 37 and on_day["exp"] == 0


def test_leap_day_birthday_and_fixed_level():
    out = stats.level_and_exp({"birthdate": "1992-02-29"}, today=date(2027, 2, 28))
    assert out["level"] == 34  # birthday counts from 1 March in non-leap years
    assert stats.level_and_exp({"level": 36})["level"] == 36
    assert stats.level_and_exp({})["level"] is None


def test_gauges_clamp_and_handle_missing():
    assert stats.gauge(412, 480)["fraction"] == pytest.approx(412 / 480)
    assert stats.gauge(600, 480)["fraction"] == 1.0
    assert stats.gauge(None, 480) is None
    assert stats.limit_gauge(100)["full"] is True
    assert stats.limit_gauge("x") is None


def test_equipment_uses_assignment_else_newest_of_kind():
    devices = {
        "old-phone": {"id": "old-phone", "kind": "phone", "updated_at": 1},
        "s25": {"id": "s25", "kind": "phone", "updated_at": 5},
        "ring": {"id": "ring", "kind": "ring", "updated_at": 3},
    }
    eq = {s["slot"]: s["device"] for s in stats.equipment({}, devices)}
    assert eq["weapon"]["id"] == "s25" and eq["armor"] is None and eq["accessory"]["id"] == "ring"
    eq = {s["slot"]: s["device"] for s in stats.equipment({"slot_devices": {"weapon": "old-phone"}}, devices)}
    assert eq["weapon"]["id"] == "old-phone"


def test_materia_colours_by_category():
    out = stats.materia([
        {"name": "Spotify", "category": "Music"},
        {"name": "Samsung Health", "category": "health"},
        {"name": "Mystery"},
    ])
    assert [(m["name"], m["materia"]) for m in out] == [
        ("Samsung Health", "magic"), ("Mystery", "support"), ("Spotify", "summon")]


def test_sheet_maps_sleep_energy_stress():
    sheet = stats.build_sheet({
        "character": "aerith",
        "profile": {"level": 36, "sleep_goal_minutes": 480},
        "metrics": {"sleep_minutes": {"value": 412}, "energy_score": {"value": 72},
                    "stress": {"value": 35}, "heart_rate": {"value": 64, "unit": "bpm"}},
    })
    assert sheet["name"] == "Aerith" and sheet["level"] == 36
    assert sheet["sp"]["current"] == 412 and sheet["sp"]["max"] == 480
    assert sheet["mp"]["current"] == 72 and sheet["limit"]["current"] == 35
    assert [r["label"] for r in sheet["status"]][:2] == ["Heart rate", "Stress"]


# -- store ------------------------------------------------------------------

def test_telemetry_merges_devices_and_replaces_apps_per_device(tmp_path):
    s = CharacterStore(str(tmp_path))
    s.apply_telemetry("tom", "aerith", {
        "devices": [{"id": "s25", "kind": "phone", "battery": 80}],
        "apps": [{"name": "A", "device": "s25"}, {"name": "W", "device": "watch"}],
    })
    data = s.apply_telemetry("tom", "aerith", {
        "devices": [{"id": "s25", "battery": 79}],
        "apps": [{"name": "B", "device": "s25"}],
    })
    assert data["devices"]["s25"] == {**data["devices"]["s25"], "kind": "phone", "battery": 79}
    assert sorted(a["name"] for a in data["apps"]) == ["B", "W"]
    assert s.load("alice", "aerith")["devices"] == {}  # owner-scoped


def test_bad_character_id_rejected(tmp_path):
    with pytest.raises(ValueError):
        CharacterStore(str(tmp_path)).load("tom", "../etc")


# -- routes -------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    app = FastAPI()

    @app.middleware("http")
    async def as_tom(request, call_next):
        request.state.api_token = True
        request.state.api_token_owner = "tom"
        return await call_next(request)

    app.include_router(setup_character_routes(CharacterStore(str(tmp_path))))
    return TestClient(app)


def test_phone_can_push_and_read_sheet(client):
    r = client.post("/api/companion/characters/aerith/telemetry", json={
        "devices": [{"id": "ring", "kind": "ring", "make": "Samsung", "model": "Galaxy Ring", "battery": 64}],
        "metrics": {"sleep_minutes": 400, "energy_score": {"value": 81, "source": "ring"}},
        "apps": [{"name": "Samsung Health", "category": "health", "device": "phone"}],
        "location": {"label": "Home", "lat": 53.8, "lon": -1.5},
    })
    assert r.status_code == 200
    client.put("/api/companion/characters/aerith/profile", json={"birthdate": "1990-06-15"})
    sheet = client.get("/api/companion/characters/aerith").json()
    assert sheet["sp"]["current"] == 400 and sheet["mp"]["current"] == 81
    assert sheet["equipment"][2]["device"]["model"] == "Galaxy Ring"
    assert sheet["location"]["label"] == "Home" and "lat" not in sheet["location"]
    assert sheet["level"] >= 36


def test_validation(client):
    bad_avatar = client.put("/api/companion/characters/aerith/profile",
                            json={"avatar_url": "https://example.com/a.png"})
    assert bad_avatar.status_code == 422
    assert client.put("/api/companion/characters/aerith/profile",
                      json={"avatar_url": "/static/icons/icon-192.png"}).status_code == 200
    assert client.post("/api/companion/characters/aerith/telemetry",
                       json={"devices": [{"id": "x", "battery": 150}]}).status_code == 422
    assert client.get("/api/companion/characters/Bad..Id").status_code == 400


def test_page_renders(client):
    r = client.get("/api/companion/characters/aerith/page")
    assert r.status_code == 200 and '"aerith"' in r.text and "Materia" in r.text
