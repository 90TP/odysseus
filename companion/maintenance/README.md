# Aerith self-maintenance

Aerith watches for errors, drafts fixes, and suggests features. **A person
approves every change.** Nothing Aerith writes reaches the running app until
an admin approves it.

```text
app.log ─┐                               ┌─> ready ──(you approve)──> merged, restart
android ─┼─> incidents ──(autofix)──> build in worktree ─┤
desktop ─┘                               └─> failed (kept for inspection)
research reports ──> feature options ──(you choose)──> build ──> ready ──> …
```

## Turning it on

```text
AERITH_MAINTENANCE_ENABLED=1
AERITH_MAINTENANCE_OWNER=<your Odysseus username>   # whose model/agent settings Aerith uses
```

Then open `/api/companion/aerith/maintenance/page`. The page works in the
desktop browser and in the Android WebView. All settings are in
`.env.example`.

## How a fix is made

1. The server log is tailed from the end, so old history isn't replayed. Each
   ERROR/CRITICAL record and its traceback is fingerprinted: exception type
   plus innermost frames, or the message with numbers/ids stripped. Repeats
   become a single **incident**.
2. For a new incident, Aerith creates `aerith/fix-…` in a separate git
   worktree under `<data>/aerith/maintenance/worktrees/`. The real Odysseus
   agent loop then works there with the error, the trace and fix instructions.
3. Aerith's work is committed. The proposal is **ready** only if the diff is
   non-empty and `AERITH_TEST_CMD` passes. Tests run with their own data dir,
   so their logs can't create new incidents.
4. When you approve, the branch is merged (`--no-ff`) into the live checkout.
   Restart Odysseus to load it. If the same error comes back, the incident
   reopens.

Guard rails:
- Approve, reject, choose and "fix now" need an **admin browser session**.
  API tokens and the internal-tool token Aerith's own tools use are refused.
- A diff that touches `companion/maintenance/`, `.github/` or `.env*` is
  refused, so Aerith can't loosen her own approval gate.
- Approval refuses to merge into a checkout with uncommitted changes. A
  conflicting merge is aborted.
- `AERITH_MAX_FIXES_PER_DAY` limits automatic drafts. Aerith's own log
  lines are never turned into incidents.
- Note: Aerith's bash tool runs with your user's permissions and is not
  sandboxed to the worktree. File tools are confined to it. Review diffs
  before approving.

## Reporting errors from Android / desktop clients

```http
POST /api/companion/aerith/maintenance/logs
Authorization: Bearer ody_…          (a paired-device token works)
{
  "platform": "android",             // or "desktop"
  "app_id": "com.seventhhaven.meals",
  "app_version": "0.2.0",
  "events": [
    {"level": "ERROR", "message": "NullPointerException", "detail": "<stack trace>",
     "source": "MainActivity", "timestamp": "2026-11-22T10:00:00Z"}
  ]
}
```

Only ERROR/CRITICAL/FATAL/CRASH events are kept. Android `at pkg.Class.fn(File.kt:12)`
frames are fingerprinted the same way as Python tracebacks. Fixes for
Android land under `android/`.

## Features from research

When a deep-research report finishes, Aerith asks the model for up to four
features the report supports, each tagged android/desktop/server. Only
reports finished after maintenance was switched on are read. Choosing one
builds it the same way as a fix. You can also ask directly:
`POST …/features/from-research {"research_id": "…"}`.

## API

| Method | Path (under `/api/companion/aerith/maintenance`) | Who |
|---|---|---|
| GET | `/page`, `/status`, `/incidents`, `/proposals`, `/proposals/{id}` (with diff) | admin |
| POST | `/logs` | any authenticated client |
| POST | `/incidents/{id}/fix`, `/incidents/{id}/dismiss` | admin browser session |
| POST | `/proposals/{id}/choose`, `/approve`, `/reject` | admin browser session |
| POST | `/features/from-research` | admin browser session |
