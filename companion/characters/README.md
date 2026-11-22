# Character sheets

An FF7-style status screen per character, fed by your phone, watch and ring.
Open `/api/companion/characters/aerith/page`. Any character id works
(lowercase letters, numbers and dashes), so other characters can have their
own sheet later.

| On the sheet | Comes from |
|---|---|
| **LV** | your age, from `birthdate` (or a fixed `level`) |
| **EXP / To next level** | days since / until your birthday |
| **SP** (FF7's HP) | `sleep_minutes` last night / `sleep_goal_minutes` (default 480) |
| **MP** | `energy_score` out of 100 (e.g. Galaxy Ring Energy Score) |
| **Limit** | `stress` 0–100; it flashes "LIMIT BREAK" at 100 |
| **Wpn. / Arm. / Acc.** | the newest `phone` / `watch` / `ring` device reported, with battery |
| **Materia** | apps on your devices, coloured by `category` |
| **Status** | location plus every other metric reported (heart rate, HRV, SpO2, steps…) |

Nothing is hard-coded to a device. Whatever reports in fills the slots. To
pin a slot to a particular device, set `slot_devices` in the profile.

Materia colours follow FF7:
- green (magic): health and fitness
- yellow (command): communication
- purple (independent): productivity, maps and tools
- blue (support): system, connectivity and anything uncategorised
- red (summon): music, media and games

## Setting it up

```http
PUT /api/companion/characters/aerith/profile
{"birthdate": "1990-06-15", "sleep_goal_minutes": 480, "avatar_url": "/static/..."}
```

`avatar_url` must be a path on your server or a `data:` image, so the page
never loads anything from elsewhere. Your birthdate stays on your server.

## Sending data (phone, Tasker, Home Assistant…)

Use a paired-device token (`/api/companion/pair`) or a signed-in browser:

```http
POST /api/companion/characters/aerith/telemetry
Authorization: Bearer ody_…
{
  "devices": [
    {"id": "s25",  "kind": "phone", "make": "Samsung", "model": "Galaxy S25 Ultra", "battery": 82},
    {"id": "ring", "kind": "ring",  "make": "Samsung", "model": "Galaxy Ring", "battery": 64, "charging": true}
  ],
  "metrics": {
    "sleep_minutes": {"value": 412, "source": "ring"},
    "energy_score": 72,
    "stress": 38,
    "heart_rate": {"value": 64, "unit": "bpm", "source": "ring"}
  },
  "apps": [{"name": "Samsung Health", "category": "health", "device": "s25"}],
  "location": {"label": "Home"}
}
```

- Send only what changed. Latest value wins.
- `apps` replaces the list for the devices it mentions.
- Location is a place name only. Coordinates are ignored.

**Where the data comes from:** the Galaxy Ring syncs to Samsung Health, which
can share with Android Health Connect. Any app that can read Health Connect
and make an HTTP request can feed this sheet, such as Tasker or the Home
Assistant companion app. A dedicated collector for the 7th Heaven app is a
good next proposal for Cid.
