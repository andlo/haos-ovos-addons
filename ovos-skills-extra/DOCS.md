# OVOS Skills Extra

🚧 **v0.1.x — new.**

## What it is

The free, unverified counterpart to the [OVOS Skills](../ovos-skills/DOCS.md) add-on. Same
underlying mechanism -- one isolated Python venv per skill, install/uninstall/settings via a
small HTTP API -- but with no catalog and no verification at all.

**Use OVOS Skills (the curated one) when:** you want the small set of skills this project has
actually confirmed make sense in this specific setup (a synchronous `/ask` bridge into
`ovos-core`, no `ovos-audio`, no continuous microphone listener). Picking from a list, not
typing anything.

**Use OVOS Skills Extra (this one) when:** you want a specific skill that isn't in the curated
catalog yet -- your own skill, an experimental one, or anything this project hasn't gotten
around to checking. You type a PyPI package name or a git URL directly; nothing about it is
vetted for this architecture. Some OVOS skills assume a full, standalone OVOS install with its
own audio subsystem and continuous wake-word listener -- neither exists here, so a skill that
depends on those (already confirmed for real: `ovos-skill-volume`, `ovos-skill-naptime`) may
load without error but not actually do anything useful. That's the tradeoff for the extra
reach; nothing here stops you from trying, but nothing here promises it'll work either.

The split mirrors Debian's main/contrib, or Home Assistant's own built-in integrations vs.
HACS: one side stays trustworthy by construction, the other stays unrestricted.

## API

Identical shape to OVOS Skills' own API, minus `GET /catalog` (there's nothing to browse --
`POST /skills/install` takes a raw `{"url": "<pypi-name-or-git-url>"}` body directly).

| Endpoint | What it does |
|---|---|
| `GET /health` | `{"bus_connected": true}` |
| `GET /skills` | Installed skills, from this add-on's own manifest |
| `GET /skills/running` | Per-skill process status |
| `POST /skills/install` | Body `{"url": "<pypi-name-or-git-url>"}`. Async, same pattern as OVOS Skills |
| `GET /skills/install/status?key=<url or skill_id>` | Poll for the real result |
| `DELETE /skills/{skill_id}` | Remove the skill's own venv |
| `GET /skills/{skill_id}/settingsmeta`, `GET`/`PUT /skills/{skill_id}/settings` | Same as OVOS Skills |

## Persistence, install mechanics, everything else

Identical to OVOS Skills -- see that add-on's own DOCS.md for the full architecture reasoning
(why one venv per skill, why nothing is persisted except a small manifest, PyPI-vs-git
handling, etc.). This add-on's own manifest lives at a separate path
(`/share/ovos-skills-extra/manifest.json`) so the two add-ons never interfere with each other,
even if both happen to install a skill with the same name.

One deliberate difference: OVOS Skills prefers a real PyPI package over a git URL when one
exists under the repo's own name (`_resolve_install_target`). This add-on does not -- whatever
the person typed is installed exactly as given, not second-guessed.
