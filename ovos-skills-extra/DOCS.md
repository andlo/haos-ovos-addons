# OVOS Skills Extra

The free, unverified counterpart to [OVOS Skills](../ovos-skills/DOCS.md). Same underlying mechanism — one isolated Python virtual environment per skill — but with no catalog and no verification: you type a PyPI package name or a git URL, and it gets installed exactly as given.

**Use OVOS Skills (the curated one) when** you want the small set of skills this project has confirmed work correctly in this specific setup.

**Use this add-on when** you want a specific skill that isn't in the curated catalog — your own skill, an experimental one, or anything not checked yet. Nothing here is vetted for this architecture: some OVOS skills assume a full, standalone OVOS install with its own audio subsystem or continuous microphone listener, neither of which exists here, so a skill may load without error but not actually do anything useful. That's the tradeoff for the extra reach.

The split mirrors Debian's main/contrib, or Home Assistant's built-in integrations vs. HACS: one side stays trustworthy by construction, the other stays unrestricted.

## Setup

Install and start the add-on. Add skills from Home Assistant, via `ha-ovos-integration`'s skill flow (choose "Extra" instead of the curated catalog) — or directly through this add-on's own API.

## API (port 8502)

| Endpoint | What it does |
|---|---|
| `GET /health` | `{"bus_connected": true}` |
| `GET /skills` | Installed skills, from this add-on's own manifest, plus a best-effort `name` (see "Display names" below) |
| `GET /skills/running` | Per-skill process status |
| `POST /skills/install` | Body `{"url": "<pypi-name-or-git-url>"}`. Async — returns `{"status": "pending", "poll": "..."}` |
| `GET /skills/install/status?key=<url or skill_id>` | Poll for the real result |
| `DELETE /skills/{skill_id}` | Uninstall — removes the skill's own venv |
| `GET /skills/{skill_id}/settingsmeta` | The skill's settings schema, if it ships one |
| `GET`/`PUT /skills/{skill_id}/settings` | Read/write the skill's own `settings.json` |

## Display names

This add-on has no catalog of its own, by design (see this file's own top -- install by typing a PyPI name or git URL directly, nothing curated). A skill installed here has nothing better than its raw `skill_id` to go by, UNLESS it ships its own `skill.json`: a per-locale metadata file (`name`/`description`/`examples`/`tags`/`icon`) many modern OVOS skills carry under `<package>/locale/<lang>/skill.json`. `GET /skills`' own `name` field reads this directly when present — confirmed for real during development on two different real skills installed exactly this way (one from a PyPI name, one from a git URL), both correctly returning their own real name (`"Wiki Offline"`, `"ChatGPT Fallback Skill"`).

`null` when no `skill.json` exists anywhere in the installed package. Callers (`ha-ovos-integration`'s own device/subentry naming) already have their own last-resort fallback (a crude cleanup of the raw `skill_id`) for that case.

## Configuration

| Option | Description |
|---|---|
| `log_level` | `debug`, `info`, `warning`, or `error` |

## Baseline packages

Same as OVOS Skills -- every fresh venv gets `ovos-workshop` and `ovos-plugin-manager` installed first, before the skill's own package, to cover skills with incomplete dependency declarations.

## Persistence

Same model as OVOS Skills — only a small manifest persists, on its own path (`/share/ovos-skills-extra/manifest.json`, separate from OVOS Skills' own, so the two add-ons never interfere even if both install a skill with the same name). Each skill's venv is rebuilt fresh from that manifest on every container start. A shared, persistent pip cache (`/share/ovos-pip-cache`, shared with every other add-on) means the underlying packages usually don't need re-downloading.

**One deliberate difference from OVOS Skills:** no PyPI-vs-git preference logic here — whatever source you type is installed exactly as given, never substituted.

## The "mycroft.ready" nudge

After launching any skill (fresh install or container restart), this add-on broadcasts a `mycroft.ready` bus message a few seconds later. Needed because `ovos-core`'s own readiness tracking only ever sees skills installed in its own environment -- it has no way to know skills running in this add-on's separate container exist at all, so a skill's own "is ovos-core ready?" check can answer "no" indefinitely otherwise, leaving it stuck waiting. Harmless for skills that already loaded correctly.
