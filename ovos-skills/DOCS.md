# OVOS Skills

Installs, removes, and configures OVOS skills — one isolated Python virtual environment per skill, so one skill's own dependencies can never conflict with another's, or with `ovos-core`'s own. Serves a small, **curated** catalog of skills this project has confirmed work correctly in this specific setup (a synchronous HTTP bridge into `ovos-core`, no `ovos-audio`, no continuous microphone listener).

For anything not in the curated catalog, use [OVOS Skills Extra](../ovos-skills-extra/DOCS.md) — same underlying mechanism, no catalog, install by typing a PyPI name or git URL directly.

## Setup

Install and start the add-on. A small set of sensible default skills installs automatically on first boot (see the catalog below). Manage skills from Home Assistant, via `ha-ovos-integration`'s "Add sub-entry → Skill" flow under the OpenVoiceOS integration — or directly through this add-on's own API.

## Catalog

| Skill | Installed by default? | Notes |
|---|---|---|
| Date and Time | Yes | |
| Alerts | Yes | Alarms, timers, reminders |
| Fallback: Unknown | Yes | Gives a clear "I don't understand" instead of silence |
| Weather | Yes | |
| IP Address | Yes | |
| Dictation | No | |
| Stop | No | **Known broken** — missing an upstream dependency (`ovos-plugin-manager`), fails to launch |
| News Streams | No | **Known broken** — needs a separate audio-playback service (`ovos-media`) this project doesn't provide |

The two "known broken" entries are kept visible, not deleted, so the gaps are easy to revisit once fixed upstream (Stop) or once a real media-playback bridge exists (News).

## API (port 8500)

| Endpoint | What it does |
|---|---|
| `GET /health` | `{"bus_connected": true}` |
| `GET /catalog` | This add-on's own curated skill list, as `{"items": [...]}` |
| `GET /skills` | Installed skills: `{"skills": [{"skill_id", "package_name", "source", "version"}, ...]}` |
| `GET /skills/running` | Per-skill process status (running/dead, PID, restart count) |
| `POST /skills/install` | Body `{"url": "<source>"}`. Async — returns `{"status": "pending", "poll": "..."}` |
| `GET /skills/install/status?key=<url or skill_id>` | Poll for the real result; success includes the confirmed-real `skill_id` |
| `DELETE /skills/{skill_id}` | Uninstall — removes the skill's own venv |
| `GET /skills/{skill_id}/settingsmeta` | The skill's settings schema, if it ships one |
| `GET`/`PUT /skills/{skill_id}/settings` | Read/write the skill's own `settings.json` |

Installing prefers a real, published PyPI release over the catalog's git source when one exists — more stable than whatever's on a repo's default branch.

## Configuration

| Option | Description |
|---|---|
| `log_level` | `debug`, `info`, `warning`, or `error` |

## Baseline packages

Every fresh venv gets `ovos-workshop` and `ovos-plugin-manager` installed first, before the skill's own package. Several OVOS skills (and even `ovos-workshop` itself, in some versions) don't declare their own real runtime dependencies correctly, assuming a full, shared OVOS environment is already present -- this baseline covers that gap without reintroducing any cross-skill conflict risk, since it's still per-venv and gets upgraded/downgraded automatically if a skill's own package requires a different version.

## Persistence

Only a small manifest (`skill_id → source, package_name`) persists, on `/share`. Each skill's own venv lives in the add-on's own container filesystem and is rebuilt from that manifest on every container start — a fresh install per skill, not a stored copy. This is deliberate: simpler and more robust than trying to persist and restore the venvs themselves. A shared, persistent pip cache (`/share/ovos-pip-cache`) means the underlying packages usually don't need re-downloading even so.

A skill's own settings (`settings.json`) are separate from its venv and always persist on `/share`, independent of any reinstall.

## Known limitations

- Reinstalling on every container rebuild/update needs network access at boot to restore previously-installed skills.
- A skill reinstalled from its manifest entry isn't pinned to an exact version — it resolves to whatever's currently the latest matching release.
