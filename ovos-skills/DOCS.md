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
| `GET /skills` | Installed skills: `{"skills": [{"skill_id", "package_name", "source", "version", "active", "name"}, ...]}`. `name` is `null` unless the skill ships its own `skill.json` (see "Display names" below). |
| `GET /skills/running` | Per-skill process status (running/dead, PID, restart count) |
| `POST /skills/install` | Body `{"url": "<source>"}`. Async — returns `{"status": "pending", "poll": "..."}` |
| `GET /skills/install/status?key=<url or skill_id>` | Poll for the real result; success includes the confirmed-real `skill_id` |
| `DELETE /skills/{skill_id}` | Uninstall — removes the skill's own venv |
| `GET`/`PUT /skills/{skill_id}/active` | Enable/disable a skill without uninstalling it. `PUT` body `{"active": true/false}` — see "Enabling/disabling a skill" below |
| `GET /skills/{skill_id}/settingsmeta` | The skill's settings schema, if it ships one |
| `GET`/`PUT /skills/{skill_id}/settings` | Read/write the skill's own `settings.json` |

## Enabling/disabling a skill

`PUT /skills/{skill_id}/active` sends `skillmanager.activate`/`skillmanager.deactivate` directly on the shared bus, confirmed by reading `ovos_workshop`'s own `skill_launcher.py` directly: each skill's own `SkillLoader` (one per subprocess -- this add-on launches one isolated venv/process per skill) registers its own bus listener for these exact messages, filtered by `message.data['skill'] == self.skill_id` -- entirely independent of `ovos-core`'s own `SkillManager`, which has no visibility into these subprocess-launched skills at all (see "The mycroft.ready nudge" below for the same, already-established limitation). This is what makes it safe to send directly: the right skill's own process reacts, no other skill's process does.

The desired state is persisted to `/share/ovos-skills/active_state.json` (absent = active, the default) and re-applied a few seconds after every (re)launch, since a freshly launched skill's own `SkillLoader` always starts `active = True` with no memory of a previous deactivation. This is a bus message, not a process kill — a deactivated skill's process keeps running (still visible in `GET /skills/running`), it just stops responding to intents/utterances until reactivated.

There's no bus message to ask a running skill its own state back, so `GET /skills/{skill_id}/active` reads from the same persisted file rather than a live query — kept in sync since every change goes through the same code path that writes it.

Installing prefers a real, published PyPI release over the catalog's git source when one exists — more stable than whatever's on a repo's default branch.

Individual catalog entries can also declare an optional `extra_deps` list — packages installed into that specific skill's own venv only, on top of the shared baseline below. Used for `ovos-skill-wikipedia` (`ovos-translate-plugin-server`, confirmed 0.0.33, see issue #10) rather than adding it to every skill's venv unnecessarily.

## Display names

Every skill in this add-on's own catalog already has a name (see the table above), so `GET /skills`' own `name` field is mostly redundant here — a skill installed some other way (directly against this API, bypassing the catalog) has no catalog entry to fall back on, so this reads the skill's own `skill.json` instead: a per-locale metadata file (`name`/`description`/`examples`/`tags`/`icon`) many modern OVOS skills ship under `<package>/locale/<lang>/skill.json`. Confirmed present for real on a real skill during development, with `"name": "Wiki Offline"`.

`null` when no `skill.json` exists anywhere in the installed package — plenty of skills genuinely don't ship one. Callers (`ha-ovos-integration`'s own device/subentry naming) already have their own last-resort fallback for that case.

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

## Skill launches are staggered, not simultaneous

`discover_and_launch_all()` sleeps 0.5s between each `subprocess.Popen` call rather than firing all of them back-to-back. Found via `ovos-core`'s own DOCS.md investigation (2026-08-29, once `padatious` became the default there): launching every skill at once clusters all their `padatious:register_intent` bus emissions into a very tight window, and `ovos-padatious`'s own training manager has a real, reproducible concurrency bug under that load (`dictionary changed size during iteration` / bare-string `KeyError`s during training) -- intents that hit it fail to train, then fail to load from cache too (the file was never written), and silently never match afterward. The stagger reduced this from roughly a dozen affected intents per full-catalog boot to about one, on the same dev VM -- a large improvement, not a complete fix; the underlying `ovos-padatious` bug itself is still open upstream, unreported as of this writing.

## Known limitations

- Reinstalling on every container rebuild/update needs network access at boot to restore previously-installed skills.
- A skill reinstalled from its manifest entry isn't pinned to an exact version — it resolves to whatever's currently the latest matching release.
