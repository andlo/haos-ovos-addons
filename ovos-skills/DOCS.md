# OVOS Skills

Installs, removes, and configures OVOS skills — one isolated Python virtual environment per skill, so one skill's own dependencies can never conflict with another's, or with `ovos-core`'s own. Serves a small, **curated** catalog of skills this project has confirmed work correctly in this specific setup (a synchronous HTTP bridge into `ovos-core`, no `ovos-audio`, no continuous microphone listener).

For anything not in the curated catalog, use [OVOS Skills Extra](../ovos-skills-extra/DOCS.md) — same underlying mechanism, no catalog, install by typing a PyPI name or git URL directly.

## Setup

Install and start the add-on. A small set of sensible default skills installs automatically on first boot (see the catalog below). Manage skills from Home Assistant, via `ha-ovos-integration`'s "Add sub-entry → Skill" flow under the OpenVoiceOS integration — or directly through this add-on's own API.

## Catalog

Lives in `catalog.json`, not hardcoded in `api.py` — pure data (which skills, which are installed by default), editable without touching Python. `GET /catalog` re-reads it fresh on every call.

| Skill | Installed by default? | Notes |
|---|---|---|
| Date and Time | Yes | |
| Alerts | Yes | Alarms, timers, reminders |
| Fallback: Unknown | Yes | Gives a clear "I don't understand" instead of silence |
| Weather | Yes | |
| IP Address | No | |
| Stop | No | **Known broken** — old alpha package, crash-loops on this stack (legacy `mycroft`-namespace entry point, `ModuleNotFoundError`). Also redundant: `ovos-core`'s own built-in `stop_high`/`stop_medium` pipeline matchers already handle plain "stop" without it. |
| Dictation | No | |
| Confucius Quotes | No | |
| Days in History | No | |
| ISS Location | No | |
| MovieMaster | No | |
| Number Facts | No | |
| Personal | Yes | About the assistant itself |
| Speed Test | No | |
| WikiHow | Yes | |
| DuckDuckGo | Yes | Factual Q&A |
| Dad Jokes | Yes | |
| Parrot | No | Repeats back what you say |
| Spelling | No | |
| Wikipedia | Yes | |

Stop is kept visible, not deleted, so the gap is easy to revisit if a working replacement package turns up. (News Streams, previously listed here for the same reason, was dropped from the catalog entirely — it needed a separate audio-playback service, `ovos-media`, this project's architecture doesn't provide, and revisiting that gap is a bigger, separate decision than a single skill.)

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

Individual catalog entries can also declare an optional `extra_deps` list — packages installed into that specific skill's own venv only, on top of the shared baseline below. Used for `ovos-skill-wikipedia` (`ovos-translate-plugin-server`, confirmed 0.0.33, see issue #10) rather than adding it to every skill's venv unnecessarily.

## Configuration

| Option | Description |
|---|---|
| `log_level` | `debug`, `info`, `warning`, or `error` |

## Baseline packages

Every fresh venv gets `ovos-workshop`, `ovos-plugin-manager`, `setuptools<=80.9.0`, and `ovos-rake-keyword-extractor` installed first, before the skill's own package. Several OVOS skills (and even `ovos-workshop` itself, in some versions) don't declare their own real runtime dependencies correctly, assuming a full, shared OVOS environment is already present -- this baseline covers that gap without reintroducing any cross-skill conflict risk, since it's still per-venv and gets upgraded/downgraded automatically if a skill's own package requires a different version. `ovos-rake-keyword-extractor` specifically fixes `ovos-skill-ddg` and `ovos-skill-wikihow`, which both silently return no answer to every query without it (confirmed 0.0.32, see issue #9).

## Persistence

Only a small manifest (`skill_id → source, package_name`) persists, on `/share`. Each skill's own venv lives in the add-on's own container filesystem and is rebuilt from that manifest on every container start — a fresh install per skill, not a stored copy. This is deliberate: simpler and more robust than trying to persist and restore the venvs themselves. A shared, persistent pip cache (`/share/ovos-pip-cache`) means the underlying packages usually don't need re-downloading even so.

A skill's own settings (`settings.json`) are separate from its venv and always persist on `/share`, independent of any reinstall.

## The "mycroft.ready" nudge

After launching any skill (fresh install or container restart), this add-on broadcasts a `mycroft.ready` bus message a few seconds later. Needed because `ovos-core`'s own readiness tracking only ever sees skills installed in its own environment -- it has no way to know skills running in this add-on's separate container exist at all, so a skill's own "is ovos-core ready?" check can answer "no" indefinitely otherwise, leaving it stuck waiting. Harmless for skills that already loaded correctly.

## Known limitations

- Reinstalling on every container rebuild/update needs network access at boot to restore previously-installed skills.
- A skill reinstalled from its manifest entry isn't pinned to an exact version — it resolves to whatever's currently the latest matching release.
